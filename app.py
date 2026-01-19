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
from flask_socketio import SocketIO, emit

# --------------------
# APP CONFIG
# --------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "secret_123"
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "chat.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(
    app,
    async_mode="gevent",
    cors_allowed_origins="*"
)

# --------------------
# MODELS
# --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    text = db.Column(db.Text)
    time = db.Column(db.String(10))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    content = db.Column(db.Text)  # base64 image/video

with app.app_context():
    db.create_all()

# --------------------
# LOGIN
# --------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --------------------
# ROUTES
# --------------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        user = User.query.filter_by(username=u).first()
        if not user:
            user = User(username=u, password=p)
            db.session.add(user)
            db.session.commit()

        login_user(user)
        return redirect(url_for("chat"))

    return render_template("auth.html")

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", user=current_user)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# --------------------
# SOCKET.IO
# --------------------
@socketio.on("connect")
def connect():
    emit("stories", get_stories())
    emit("messages", get_messages())

@socketio.on("send_message")
def send_message(data):
    m = Message(
        username=current_user.username,
        text=data["text"],
        time=datetime.now().strftime("%H:%M")
    )
    db.session.add(m)
    db.session.commit()
    emit("new_message", {
        "user": m.username,
        "text": m.text,
        "time": m.time
    }, broadcast=True)

@socketio.on("add_story")
def add_story(data):
    s = Story(
        username=current_user.username,
        content=data["content"]
    )
    db.session.add(s)
    db.session.commit()
    emit("stories", get_stories(), broadcast=True)

# --------------------
# HELPERS
# --------------------
def get_messages():
    return [
        {"user": m.username, "text": m.text, "time": m.time}
        for m in Message.query.all()
    ]

def get_stories():
    grouped = {}
    for s in Story.query.all():
        grouped.setdefault(s.username, []).append(s.content)
    return grouped

# --------------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)
