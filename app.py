import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite3"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode="eventlet")

# ---------------- MODELS ---------------- #

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    avatar = db.Column(db.String(200))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user = db.Column(db.String(50))
    avatar = db.Column(db.String(200))
    text = db.Column(db.Text)
    room = db.Column(db.String(50))
    created = db.Column(db.DateTime, default=datetime.utcnow)

# ---------------- HELPERS ---------------- #

def serialize(m):
    return {
        "id": m.id,
        "user": m.user,
        "avatar": m.avatar,
        "text": m.text,
        "me": False
    }

# ---------------- ROUTES ---------------- #

@app.route("/", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        avatar = request.form.get("avatar") or "/static/avatar.png"

        user = User.query.filter_by(username=u).first()
        if user:
            if check_password_hash(user.password, p):
                session["user"] = u
                return redirect("/chat")
        else:
            user = User(
                username=u,
                password=generate_password_hash(p),
                avatar=avatar
            )
            db.session.add(user)
            db.session.commit()
            session["user"] = u
            return redirect("/chat")

    return render_template("auth.html")

@app.route("/chat")
def chat():
    if "user" not in session:
        return redirect("/")
    return render_template("chat.html", user=session["user"])

# ---------------- SOCKET.IO ---------------- #

@socketio.on("join")
def join():
    if "user" not in session:
        return

    join_room("main")
    msgs = Message.query.filter_by(room="main").order_by(Message.id).all()

    out = []
    for m in msgs:
        d = serialize(m)
        d["me"] = (m.user == session["user"])
        out.append(d)

    emit("history", out)

@socketio.on("send")
def send(data):
    if "user" not in session:
        return

    u = User.query.filter_by(username=session["user"]).first()

    m = Message(
        user=u.username,
        avatar=u.avatar,
        text=data["text"],
        room="main"
    )
    db.session.add(m)
    db.session.commit()

    d = serialize(m)
    d["me"] = True

    emit("new", d, to="main")

# ---------------- MAIN ---------------- #

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, host="0.0.0.0", port=5000)
