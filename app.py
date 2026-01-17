from flask import Flask, render_template, request, redirect, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import os, uuid

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ================= MODELS =================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    avatar = db.Column(db.String(200), default="/static/default.png")

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    user = db.Column(db.String(50))
    msg = db.Column(db.Text)
    time = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    media = db.Column(db.Text)
    music = db.Column(db.Text)
    type = db.Column(db.String(10))
    viewers = db.Column(db.Text, default="")
    created = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()
    if not Group.query.filter_by(name="genel").first():
        db.session.add(Group(name="genel"))
        db.session.commit()

# ================= AUTH =================

@app.route("/", methods=["GET","POST"])
def auth():
    if request.method=="POST":
        u=request.form["username"]
        p=request.form["password"]
        user=User.query.filter_by(username=u).first()
        if user and bcrypt.check_password_hash(user.password,p):
            session["user"]=u
            return redirect("/chat")
    return render_template("auth.html")

@app.route("/register", methods=["POST"])
def register():
    u=request.form["username"]
    p=bcrypt.generate_password_hash(request.form["password"]).decode()
    if not User.query.filter_by(username=u).first():
        db.session.add(User(username=u,password=p))
        db.session.commit()
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ================= CHAT =================

@app.route("/chat")
def chat():
    if "user" not in session: return redirect("/")
    user = User.query.filter_by(username=session["user"]).first()
    groups = [g.name for g in Group.query.all()]
    return render_template("chat.html", user=user, groups=groups)

# ================= AVATAR =================

@app.route("/upload_avatar", methods=["POST"])
def upload_avatar():
    f=request.files["file"]
    name=f"{uuid.uuid4().hex}.png"
    path=os.path.join(UPLOAD_DIR,name)
    f.save(path)
    u=User.query.filter_by(username=session["user"]).first()
    u.avatar="/"+path
    db.session.commit()
    return jsonify({"avatar":u.avatar})

# ================= SOCKET =================

@socketio.on("join_room")
def join_room_event(data):
    join_room(data["room"])
    msgs=Message.query.filter_by(room=data["room"]).all()
    emit("history",[
        {"id":m.id,"user":m.user,"msg":m.msg}
        for m in msgs
    ])

@socketio.on("send_msg")
def send_msg(data):
    m=Message(room=data["room"],user=session["user"],msg=data["msg"])
    db.session.add(m)
    db.session.commit()
    emit("new_msg",{
        "id":m.id,
        "user":m.user,
        "msg":m.msg
    },to=data["room"])

@socketio.on("delete_msg")
def delete_msg(data):
    m=Message.query.get(data["id"])
    if m and m.user == session["user"]:
        db.session.delete(m)
        db.session.commit()
        emit("msg_deleted",{"id":data["id"]},broadcast=True)

@socketio.on("create_group")
def create_group(data):
    if not Group.query.filter_by(name=data["name"]).first():
        db.session.add(Group(name=data["name"]))
        db.session.commit()
    emit("groups",[g.name for g in Group.query.all()],broadcast=True)

# ================= STORY =================

@socketio.on("add_story")
def add_story(data):
    s=Story(
        username=session["user"],
        media=data["media"],
        music=data.get("music"),
        type=data["type"]
    )
    db.session.add(s)
    db.session.commit()
    send_stories()

@socketio.on("view_story")
def view_story(data):
    s=Story.query.get(data["id"])
    if session["user"] not in s.viewers:
        s.viewers+=session["user"]+","
        db.session.commit()

def send_stories():
    now=datetime.utcnow()
    out={}
    for s in Story.query.all():
        if now-s.created>timedelta(hours=24):
            db.session.delete(s); db.session.commit(); continue
        if s.username not in out:
            u=User.query.filter_by(username=s.username).first()
            out[s.username]={"avatar":u.avatar,"items":[]}
        out[s.username]["items"].append({
            "id":s.id,
            "media":s.media,
            "music":s.music,
            "type":s.type,
            "viewers":s.viewers.split(",") if s.viewers else []
        })
    socketio.emit("stories",out)

@socketio.on("connect")
def on_connect():
    send_stories()
