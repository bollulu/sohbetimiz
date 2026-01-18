import eventlet
eventlet.monkey_patch()

import os, uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret-key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode="eventlet")

os.makedirs("static/uploads", exist_ok=True)
os.makedirs("static/avatars", exist_ok=True)

# ================= MODELS =================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True)
    password = db.Column(db.String(200))
    gender = db.Column(db.String(10))
    avatar = db.Column(db.String(200))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(40))
    avatar = db.Column(db.String(200))
    text = db.Column(db.Text)
    type = db.Column(db.String(10))  # text,image,audio
    room = db.Column(db.String(40))
    created = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

# ================= AUTH =================

@app.route("/", methods=["GET","POST"])
def auth():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        g = request.form["gender"]
        avatar = request.files["avatar"]

        user = User.query.filter_by(username=u).first()

        if not user:
            name = f"avatars/{uuid.uuid4().hex}.png"
            avatar.save("static/" + name)

            user = User(
                username=u,
                password=generate_password_hash(p),
                gender=g,
                avatar="/static/" + name
            )
            db.session.add(user)
            db.session.commit()

        if check_password_hash(user.password, p):
            session["user"] = u
            return redirect("/chat")

    return render_template("auth.html")

# ================= CHAT =================

@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")
    user = User.query.filter_by(username=session["user"]).first()
    return render_template("chat.html", user=user)

# ================= UPLOAD =================

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]
    ext = file.filename.rsplit(".",1)[1].lower()
    name = f"uploads/{uuid.uuid4().hex}.{ext}"
    file.save("static/" + name)

    u = User.query.filter_by(username=session["user"]).first()
    m = Message(
        user=u.username,
        avatar=u.avatar,
        text="/static/" + name,
        type="image" if ext in ["png","jpg","jpeg"] else "audio",
        room="main"
    )
    db.session.add(m)
    db.session.commit()

    socketio.emit("new", serialize(m), to="main")
    return "ok"

# ================= SOCKET =================

@socketio.on("join")
def join():
    join_room("main")
    msgs = Message.query.filter_by(room="main").order_by(Message.id).all()
    emit("history", [serialize(m) for m in msgs])

@socketio.on("send")
def send(data):
    u = User.query.filter_by(username=session["user"]).first()
    m = Message(
        user=u.username,
        avatar=u.avatar,
        text=data["text"],
        type="text",
        room="main"
    )
    db.session.add(m)
    db.session.commit()
    emit("new", serialize(m), to="main")

@socketio.on("read")
def read(mid):
    m = Message.query.get(mid)
    if m:
        m.read = True
        db.session.commit()

# ================= HELPER =================

def serialize(m):
    return {
        "id": m.id,
        "user": m.user,
        "avatar": m.avatar,
        "text": m.text,
        "type": m.type,
        "me": m.user == session.get("user"),
        "read": m.read
    }

# ================= RUN =================

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
