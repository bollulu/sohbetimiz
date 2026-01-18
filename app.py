import eventlet
eventlet.monkey_patch()

import os
from datetime import datetime
from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = "faz27-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["STORY_FOLDER"] = "static/stories"

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode="eventlet")

login_manager = LoginManager(app)
login_manager.login_view = "auth"

# ================= MODELS =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    username = db.Column(db.String(50))
    text = db.Column(db.Text)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    file = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ================= LOGIN =================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ================= ROUTES =================

@app.route("/", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if "login" in request.form:
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect("/chat")
        else:
            if not User.query.filter_by(username=username).first():
                user = User(
                    username=username,
                    password=generate_password_hash(password)
                )
                db.session.add(user)
                db.session.commit()
                login_user(user)
                return redirect("/chat")

    return render_template("auth.html")

@app.route("/chat")
@login_required
def chat():
    rooms = Room.query.all()
    stories = Story.query.all()
    return render_template(
        "chat.html",
        rooms=rooms,
        stories=stories,
        current_room="genel",
        messages=Message.query.filter_by(room="genel").all()
    )

@app.route("/room/<room>")
@login_required
def room(room):
    rooms = Room.query.all()
    messages = Message.query.filter_by(room=room).all()
    stories = Story.query.all()
    return render_template(
        "chat.html",
        rooms=rooms,
        messages=messages,
        current_room=room,
        stories=stories
    )

@app.route("/add-story", methods=["GET", "POST"])
@login_required
def add_story():
    if request.method == "POST":
        file = request.files["story"]
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["STORY_FOLDER"], filename))
        db.session.add(Story(username=current_user.username, file=filename))
        db.session.commit()
        return redirect("/chat")
    return render_template("add_story.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")

# ================= SOCKET =================

@socketio.on("join")
def join(data):
    room = data["room"]
    join_room(room)

    Message.query.filter_by(room=room, read=False)\
        .filter(Message.username != current_user.username)\
        .update({"read": True})
    db.session.commit()

@socketio.on("message")
def message(data):
    msg = Message(
        room=data["room"],
        username=current_user.username,
        text=data["msg"]
    )
    db.session.add(msg)
    db.session.commit()

    emit("message", {
        "user": msg.username,
        "msg": msg.text,
        "read": msg.read
    }, room=data["room"])

# ================= INIT =================

with app.app_context():
    db.create_all()
    if not Room.query.first():
        db.session.add(Room(name="genel"))
        db.session.add(Room(name="grup1"))
        db.session.add(Room(name="grup2"))
        db.session.commit()

if __name__ == "__main__":
    socketio.run(app, debug=True)
