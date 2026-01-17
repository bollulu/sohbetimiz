from flask import Flask, render_template, request, redirect, session
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import uuid

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app)

### MODELS ###

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    avatar = db.Column(db.String(200), default="https://i.pravatar.cc/150")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    user = db.Column(db.String(50))
    msg = db.Column(db.Text)
    time = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    content = db.Column(db.Text)
    music = db.Column(db.Text)
    type = db.Column(db.String(10))
    viewers = db.Column(db.Text, default="")
    created = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

### AUTH ###

@app.route("/", methods=["GET","POST"])
def auth():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        user = User.query.filter_by(username=u).first()
        if user and bcrypt.check_password_hash(user.password, p):
            session["user"] = u
            return redirect("/chat")
    return render_template("auth.html")

@app.route("/register", methods=["POST"])
def register():
    u = request.form["username"]
    p = bcrypt.generate_password_hash(request.form["password"]).decode()
    if not User.query.filter_by(username=u).first():
        db.session.add(User(username=u, password=p))
        db.session.commit()
    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

### CHAT ###

@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")
    user = User.query.filter_by(username=session["user"]).first()
    return render_template("chat.html", user=user)

### SOCKET ###

@socketio.on("join_room")
def join(data):
    join_room(data["room"])
    msgs = Message.query.filter_by(room=data["room"]).all()
    emit("history", [{"user":m.user,"msg":m.msg} for m in msgs])

@socketio.on("send_message")
def send(data):
    m = Message(room=data["room"], user=session["user"], msg=data["msg"])
    db.session.add(m)
    db.session.commit()
    emit("message", {"user":m.user,"msg":m.msg}, to=data["room"])

@socketio.on("add_story")
def add_story(data):
    s = Story(
        username=session["user"],
        content=data["content"],
        music=data.get("music"),
        type=data["type"]
    )
    db.session.add(s)
    db.session.commit()
    send_stories()

@socketio.on("view_story")
def view_story(data):
    s = Story.query.get(data["id"])
    if session["user"] not in s.viewers:
        s.viewers += session["user"] + ","
        db.session.commit()

def send_stories():
    now = datetime.utcnow()
    stories = {}
    for s in Story.query.all():
        if now - s.created < timedelta(hours=24):
            if s.username not in stories:
                stories[s.username] = {
                    "avatar": User.query.filter_by(username=s.username).first().avatar,
                    "items": []
                }
            stories[s.username]["items"].append({
                "id": s.id,
                "content": s.content,
                "music": s.music,
                "type": s.type,
                "viewers": s.viewers.split(",") if s.viewers else []
            })
        else:
            db.session.delete(s)
            db.session.commit()
    socketio.emit("story_list", stories)

@socketio.on("connect")
def on_connect():
    send_stories()

if __name__ == "__main__":
    socketio.run(app, debug=True)
