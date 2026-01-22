from gevent import monkey
monkey.patch_all()

import os
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------------------------------
# APP AYARLARI
# -------------------------------------------------
app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev_secret_key")

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = (
    "sqlite:///" + os.path.join(basedir, "chat_v2.db")
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

db = SQLAlchemy(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="gevent"
)

# -------------------------------------------------
# MODELLER
# -------------------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)
    blocked_users = db.Column(db.Text, default="[]")


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20))
    timestamp = db.Column(db.String(20))
    status = db.Column(db.String(10), default="sent")


class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    audio_data = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default="[]")
    duration = db.Column(db.Integer, default=30)


class Music(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    src = db.Column(db.Text)
    uploader = db.Column(db.String(50))


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    members = db.Column(db.Text)
    created_by = db.Column(db.String(50))


with app.app_context():
    db.create_all()

# -------------------------------------------------
# LOGIN
# -------------------------------------------------
login_manager = LoginManager(app)
login_manager.login_view = "auth"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# -------------------------------------------------
# ROUTES
# -------------------------------------------------
@app.route("/", methods=["GET"])
def auth():
    if current_user.is_authenticated:
        return redirect(url_for("chat"))
    return render_template("auth.html")


@app.route("/login", methods=["POST"])
def login_proc():
    user = User.query.filter_by(username=request.form.get("username")).first()
    if user and check_password_hash(user.password, request.form.get("password")):
        login_user(user)
        return redirect(url_for("chat"))
    return redirect(url_for("auth"))


@app.route("/register", methods=["POST"])
def register_proc():
    username = request.form.get("username")
    password = request.form.get("password")
    gender = request.form.get("gender")
    avatar = request.form.get("avatar_data")

    if User.query.filter_by(username=username).first():
        return redirect(url_for("auth"))

    if not avatar or len(avatar) < 100:
        avatar = (
            "https://cdn-icons-png.flaticon.com/512/236/236831.png"
            if gender == "Erkek"
            else "https://cdn-icons-png.flaticon.com/512/236/236832.png"
        )

    user = User(
        username=username,
        password=generate_password_hash(password),
        gender=gender,
        avatar=avatar
    )
    db.session.add(user)
    db.session.commit()
    login_user(user)

    return redirect(url_for("chat"))


@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", user=current_user)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth"))

# -------------------------------------------------
# SOCKET.IO
# -------------------------------------------------
@socketio.on("connect")
def on_connect():
    emit("update_user_list", get_all_users(), broadcast=True)


@socketio.on("join_room")
def join(data):
    room = data["room"]
    join_room(room)

    msgs = Message.query.filter_by(room=room).all()
    blocked = json.loads(current_user.blocked_users)

    history = []
    for m in msgs:
        if m.sender not in blocked:
            history.append({
                "id": m.id,
                "user": m.sender,
                "ava": m.avatar,
                "msg": m.content,
                "type": m.msg_type,
                "time": m.timestamp,
                "status": m.status
            })

    emit("history", history)
    send_stories()


@socketio.on("send_message")
def send_message(data):
    now = datetime.now().strftime("%H:%M")

    msg = Message(
        room=data["room"],
        sender=current_user.username,
        avatar=current_user.avatar,
        content=data["msg"],
        msg_type=data["type"],
        timestamp=now
    )

    db.session.add(msg)
    db.session.commit()

    socketio.start_background_task(mark_read_later, msg.id, data["room"])

    emit("message", {
        "id": msg.id,
        "room": data["room"],
        "user": msg.sender,
        "ava": msg.avatar,
        "msg": msg.content,
        "type": msg.msg_type,
        "time": now,
        "status": "sent"
    }, to=data["room"])


def mark_read_later(msg_id, room):
    socketio.sleep(1.5)
    with app.app_context():
        m = db.session.get(Message, msg_id)
        if m:
            m.status = "read"
            db.session.commit()
            socketio.emit(
                "msg_status_update",
                {"id": m.id, "status": "read"},
                to=room
            )


@socketio.on("delete_message")
def delete_message(data):
    m = db.session.get(Message, data["id"])
    if m and m.sender == current_user.username:
        room = m.room
        db.session.delete(m)
        db.session.commit()
        emit("message_deleted", {"id": data["id"]}, to=room)

# -------------------------------------------------
# HİKAYELER
# -------------------------------------------------
def send_stories():
    stories = Story.query.all()
    grouped = {}

    for s in stories:
        if s.username not in grouped:
            grouped[s.username] = {
                "avatar": s.user_avatar,
                "items": []
            }

        grouped[s.username]["items"].append({
            "id": s.id,
            "content": s.content,
            "music": s.audio_data,
            "type": s.media_type,
            "duration": s.duration,
            "viewers": json.loads(s.viewers),
            "can_delete": s.username == current_user.username
        })

    emit("story_list", grouped, broadcast=True)


@socketio.on("add_story")
def add_story(data):
    s = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data["content"],
        audio_data=data.get("music"),
        media_type=data["type"],
        duration=data.get("duration", 30)
    )
    db.session.add(s)
    db.session.commit()
    send_stories()


@socketio.on("view_story")
def view_story(data):
    s = db.session.get(Story, data["id"])
    if s and s.username != current_user.username:
        viewers = json.loads(s.viewers)
        if current_user.username not in viewers:
            viewers.append(current_user.username)
            s.viewers = json.dumps(viewers)
            db.session.commit()


@socketio.on("delete_story")
def delete_story(data):
    s = db.session.get(Story, data["id"])
    if s and s.username == current_user.username:
        db.session.delete(s)
        db.session.commit()
        send_stories()

# -------------------------------------------------
# YARDIMCI
# -------------------------------------------------
def get_all_users():
    return [{"username": u.username, "avatar": u.avatar} for u in User.query.all()]

# -------------------------------------------------
# RUN (Render uyumlu)
# -------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
