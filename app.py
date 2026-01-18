import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode="eventlet")

login_manager = LoginManager(app)
login_manager.login_view = "login"

# ---------------- MODELS ---------------- #

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default="default.png")

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    user2_id = db.Column(db.Integer, db.ForeignKey("user.id"))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey("chat.id"))
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

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
    users = User.query.filter(User.id != current_user.id).all()
    return render_template("chat.html", users=users)

@app.route("/start-chat/<int:user_id>")
@login_required
def start_chat(user_id):
    chat = Chat.query.filter(
        ((Chat.user1_id == current_user.id) & (Chat.user2_id == user_id)) |
        ((Chat.user1_id == user_id) & (Chat.user2_id == current_user.id))
    ).first()

    if not chat:
        chat = Chat(user1_id=current_user.id, user2_id=user_id)
        db.session.add(chat)
        db.session.commit()

    return redirect(url_for("open_chat", chat_id=chat.id))

@app.route("/chat/<int:chat_id>")
@login_required
def open_chat(chat_id):
    messages = Message.query.filter_by(chat_id=chat_id).all()
    return render_template("chat.html", messages=messages, chat_id=chat_id)

# ---------------- SOCKET ---------------- #

@socketio.on("join")
def join(data):
    join_room(data["chat_id"])

@socketio.on("send_message")
def send_message(data):
    msg = Message(
        chat_id=data["chat_id"],
        sender_id=current_user.id,
        text=data["text"]
    )
    db.session.add(msg)
    db.session.commit()

    emit("receive_message", {
        "text": data["text"],
        "sender": current_user.username
    }, room=data["chat_id"])

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app)
