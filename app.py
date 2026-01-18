from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["UPLOAD_FOLDER"] = "static/uploads"
app.config["STORY_FOLDER"] = "static/stories"
app.config["AVATAR_FOLDER"] = "static/avatars"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(app)
login_manager = LoginManager(app)
login_manager.login_view = "auth"

### MODELLER ###

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    avatar = db.Column(db.String(200), default="default.png")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(50))
    room = db.Column(db.String(50))
    text = db.Column(db.Text)
    time = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(50))
    file = db.Column(db.String(200))
    time = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

### ROUTES ###

@app.route("/", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        if "login" in request.form:
            user = User.query.filter_by(username=request.form["username"]).first()
            if user and check_password_hash(user.password, request.form["password"]):
                login_user(user)
                return redirect("/chat")
        else:
            hashed = generate_password_hash(request.form["password"])
            db.session.add(User(username=request.form["username"], password=hashed))
            db.session.commit()
    return render_template("auth.html")

@app.route("/chat")
@login_required
def chat():
    stories = Story.query.all()
    return render_template("chat.html", stories=stories)

@app.route("/add-story", methods=["GET", "POST"])
@login_required
def add_story():
    if request.method == "POST":
        file = request.files["story"]
        name = secure_filename(file.filename)
        path = os.path.join(app.config["STORY_FOLDER"], name)
        file.save(path)
        db.session.add(Story(user=current_user.username, file=name))
        db.session.commit()
        return redirect("/chat")
    return render_template("add_story.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")

### SOCKET.IO ###

@socketio.on("join")
def join(data):
    join_room(data["room"])

@socketio.on("message")
def handle_message(data):
    msg = Message(user=current_user.username, room=data["room"], text=data["msg"])
    db.session.add(msg)
    db.session.commit()
    emit("message", {
        "user": msg.user,
        "msg": msg.text
    }, room=data["room"])

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app)
