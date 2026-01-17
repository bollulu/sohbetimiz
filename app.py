from flask import Flask, render_template, request, redirect, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import os, uuid

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ================= MODELS =================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    avatar = db.Column(db.String(200), default="/static/default.png")
    online = db.Column(db.Boolean, default=False)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))

class GroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group = db.Column(db.String(50))
    username = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    user = db.Column(db.String(50))
    avatar = db.Column(db.String(200))
    msg = db.Column(db.Text)
    read_by = db.Column(db.Text, default="")
    created = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    media = db.Column(db.Text)
    created = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ================= AUTH =================

@app.route("/", methods=["GET","POST"])
def auth():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        user = User.query.filter_by(username=u).first()
        if user and check_password_hash(user.password, p):
            session["user"] = u
            user.online = True
            db.session.commit()
            return redirect("/chat")
    return render_template("auth.html")

@app.route("/register", methods=["POST"])
def register():
    u = request.form["username"]
    p = generate_password_hash(request.form["password"])
    if not User.query.filter_by(username=u).first():
        db.session.add(User(username=u, password=p))
        db.session.commit()
    return redirect("/")

@app.route("/logout")
def logout():
    u = User.query.filter_by(username=session.get("user")).first()
    if u:
        u.online = False
        db.session.commit()
    session.clear()
    return redirect("/")

# ================= CHAT =================

@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")
    user = User.query.filter_by(username=session["user"]).first()
    groups = Group.query.all()
    users = User.query.all()
    return render_template("chat.html", user=user, groups=groups, users=users)

# ================= AVATAR =================

@app.route("/upload_avatar", methods=["POST"])
def upload_avatar():
    f = request.files["file"]
    name = f"{uuid.uuid4().hex}.png"
    path = os.path.join(UPLOAD_DIR, name)
    f.save(path)
    u = User.query.filter_by(username=session["user"]).first()
    u.avatar = "/" + path
    db.session.commit()
    return jsonify({"avatar": u.avatar})

# ================= SOCKET =================

@socketio.on("join_room")
def join(data):
    room = data["room"]
    join_room(room)

    msgs = Message.query.filter_by(room=room).all()
    emit("history", [{
        "id": m.id,
        "user": m.user,
        "avatar": m.avatar,
        "msg": m.msg,
        "read": session["user"] in m.read_by.split(",")
    } for m in msgs])

@socketio.on("send_msg")
def send(data):
    u = User.query.filter_by(username=session["user"]).first()
    m = Message(
        room=data["room"],
        user=u.username,
        avatar=u.avatar,
        msg=data["msg"],
        read_by=u.username
    )
    db.session.add(m)
    db.session.commit()
    emit("new_msg", {
        "id": m.id,
        "user": m.user,
        "avatar": m.avatar,
        "msg": m.msg
    }, to=data["room"])

@socketio.on("read_msg")
def read(data):
    m = Message.query.get(data["id"])
    if m and session["user"] not in m.read_by:
        m.read_by += session["user"] + ","
        db.session.commit()
        emit("read_update", {"id": m.id}, broadcast=True)

@socketio.on("edit_msg")
def edit(data):
    m = Message.query.get(data["id"])
    if m and m.user == session["user"]:
        if datetime.utcnow() - m.created < timedelta(minutes=5):
            m.msg = data["msg"]
            db.session.commit()
            emit("edit_update", {"id": m.id, "msg": m.msg}, broadcast=True)

@socketio.on("disconnect")
def disconnect():
    if "user" in session:
        u = User.query.filter_by(username=session["user"]).first()
        if u:
            u.online = False
            db.session.commit()
