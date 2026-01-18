import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required, logout_user, current_user
)
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "super-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "static/stories"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

db = SQLAlchemy(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet"
)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------------- MODELS ---------------- #

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    text = db.Column(db.String(500))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.String(200))
    username = db.Column(db.String(50))

# ---------------- LOGIN ---------------- #

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- ROUTES ---------------- #

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"]).first()
        if user and check_password_hash(user.password, request.form["password"]):
            login_user(user)
            return redirect("/chat")
    return render_template("auth.html")

@app.route("/register", methods=["POST"])
def register():
    hashed = generate_password_hash(request.form["password"])
    user = User(username=request.form["username"], password=hashed)
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return redirect("/chat")

@app.route("/chat")
@login_required
def chat():
    messages = Message.query.all()
    stories = Story.query.all()
    return render_template("chat.html", messages=messages, stories=stories)

@app.route("/add-story", methods=["GET", "POST"])
@login_required
def add_story():
    if request.method == "POST":
        file = request.files["image"]
        filename = secure_filename(file.filename)
        path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(path)

        story = Story(image=filename, username=current_user.username)
        db.session.add(story)
        db.session.commit()
        return redirect("/chat")

    return render_template("add_story.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")

# ---------------- SOCKET ---------------- #

@socketio.on("send_message")
def handle_message(data):
    msg = Message(username=data["username"], text=data["message"])
    db.session.add(msg)
    db.session.commit()
    emit("receive_message", data, broadcast=True)

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app)
