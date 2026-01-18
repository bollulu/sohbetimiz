from flask import Flask, render_template, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

login_manager = LoginManager(app)
login_manager.login_view = "auth"

# ---------------- MODELS ----------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default="static/avatars/default.png")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    user = db.Column(db.String(50))
    text = db.Column(db.Text)

# -------- CREATE TABLES (IMPORTANT) --------

with app.app_context():
    db.create_all()

# ---------------- LOGIN ----------------

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- ROUTES ----------------

@app.route("/", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        action = request.form["action"]
        username = request.form["username"]
        password = request.form["password"]

        if action == "register":
            if User.query.filter_by(username=username).first():
                return "Kullanıcı zaten var"
            user = User(
                username=username,
                password=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect("/chat")

        if action == "login":
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect("/chat")
            return "Hatalı giriş"

    return render_template("auth.html")

@app.route("/chat")
@login_required
def chat():
    users = User.query.all()
    return render_template("chat.html", users=users)

@app.route("/logout")
def logout():
    logout_user()
    return redirect("/")

# ---------------- SOCKET.IO ----------------

@socketio.on("join")
def on_join(data):
    room = data.get("room")
    if room:
        join_room(room)

@socketio.on("send_message")
def handle_message(data):
    room = data["room"]
    msg = Message(
        room=room,
        user=current_user.username,
        text=data["message"]
    )
    db.session.add(msg)
    db.session.commit()

    emit("receive_message", {
        "user": current_user.username,
        "message": data["message"]
    }, room=room)

# ---------------- RUN ----------------

if __name__ == "__main__":
    socketio.run(app)
