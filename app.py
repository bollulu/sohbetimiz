import eventlet
eventlet.monkey_patch()

import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

############################
# APP CONFIG
############################

app = Flask(__name__)
app.config["SECRET_KEY"] = "super-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["STORY_FOLDER"] = "static/stories"
app.config["AVATAR_FOLDER"] = "static/avatars"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

############################
# EXTENSIONS
############################

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode="eventlet")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth"

############################
# MODELS
############################

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default="default.png")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    room = db.Column(db.String(50))
    text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    file = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

############################
# LOGIN
############################

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

############################
# ROUTES
############################

@app.route("/", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # LOGIN
        if "login" in request.form:
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for("chat"))

        # REGISTER
        else:
            if not User.query.filter_by(username=username).first():
                hashed = generate_password_hash(password)
                new_user = User(username=username, password=hashed)
                db.session.add(new_user)
                db.session.commit()
                login_user(new_user)
                return redirect(url_for("chat"))

    return render_template("auth.html")

@app.route("/chat")
@login_required
def chat():
    stories = Story.query.order_by(Story.created_at.desc()).all()
    return render_template("chat.html", stories=stories)

@app.route("/add-story", methods=["GET", "POST"])
@login_required
def add_story():
    if request.method == "POST":
        file = request.files.get("story")
        if file:
            filename = secure_filename(file.filename)
            path = os.path.join(app.config["STORY_FOLDER"], filename)
            file.save(path)

            story = Story(username=current_user.username, file=filename)
            db.session.add(story)
            db.session.commit()

            return redirect(url_for("chat"))

    return render_template("add_story.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth"))

############################
# SOCKET.IO
############################

@socketio.on("join")
def handle_join(data):
    room = data.get("room")
    join_room(room)

@socketio.on("message")
def handle_message(data):
    room = data.get("room")
    text = data.get("msg")

    msg = Message(
        username=current_user.username,
        room=room,
        text=text
    )
    db.session.add(msg)
    db.session.commit()

    emit("message", {
        "user": current_user.username,
        "msg": text
    }, room=room)

############################
# INIT DB (RENDER SAFE)
############################

with app.app_context():
    db.create_all()
