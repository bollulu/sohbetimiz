from flask import Flask, render_template, request, redirect, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, join_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = "super-secret-key"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "db.sqlite3")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode="eventlet")

# ------------------ MODELS ------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    avatar = db.Column(db.String(200), default="default.png")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50))
    user = db.Column(db.String(80))
    text = db.Column(db.Text)

# ------------------ ROUTES ------------------

@app.route("/", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session["user"] = username
            return redirect("/chat")

        return "Hatalı giriş"

    return render_template("auth.html")

@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"]
    password = generate_password_hash(request.form["password"])

    if User.query.filter_by(username=username).first():
        return "Kullanıcı var"

    user = User(username=username, password=password)
    db.session.add(user)
    db.session.commit()
    return redirect("/")

@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")
    return render_template("chat.html", username=session["user"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ------------------ SOCKET.IO ------------------

@socketio.on("join")
def on_join(data):
    room = data.get("room", "genel")
    join_room(room)

@socketio.on("message")
def handle_message(data):
    msg = Message(
        room=data["room"],
        user=data["user"],
        text=data["text"]
    )
    db.session.add(msg)
    db.session.commit()

    emit("message", data, room=data["room"])

# ------------------ INIT ------------------

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
