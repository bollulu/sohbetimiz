from gevent import monkey
monkey.patch_all()

import os, json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "wa_ultra_music_v12"
app.config["JSON_AS_ASCII"] = False   # 🔑 TÜRKÇE KARAKTER
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="gevent",
    json=json
)

# ================= MODELS =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20))
    time = db.Column(db.String(10))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default="[]")
    created = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ================= LOGIN =================

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))

# ================= ROUTES =================

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["username"]).first()
        if u and u.password == request.form["password"]:
            login_user(u)
            return redirect(url_for("chat"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not User.query.filter_by(username=request.form["username"]).first():
            u = User(
                username=request.form["username"],
                password=request.form["password"],
                avatar="https://www.w3schools.com/howto/img_avatar.png"
            )
            db.session.add(u)
            db.session.commit()
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", user=current_user)

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))

# ================= SOCKET =================

@socketio.on("join")
def join(data):
    join_room("Genel")

    msgs = Message.query.all()
    emit("history", json.loads(json.dumps([
        {
            "id": m.id,
            "user": m.username,
            "avatar": m.avatar,
            "msg": m.content,
            "type": m.msg_type,
            "time": m.time
        } for m in msgs
    ], ensure_ascii=False)))

    send_stories()

@socketio.on("message")
def message(data):
    now = datetime.now().strftime("%H:%M")
    m = Message(
        username=current_user.username,
        avatar=current_user.avatar,
        content=data["msg"],
        msg_type=data.get("type", "text"),
        time=now
    )
    db.session.add(m)
    db.session.commit()

    emit("message", json.loads(json.dumps({
        "id": m.id,
        "user": m.username,
        "avatar": m.avatar,
        "msg": m.content,
        "type": m.msg_type,
        "time": now
    }, ensure_ascii=False)), broadcast=True)

@socketio.on("add_story")
def add_story(data):
    s = Story(
        username=current_user.username,
        avatar=current_user.avatar,
        content=data["content"],
        media_type=data["type"]
    )
    db.session.add(s)
    db.session.commit()
    send_stories()

@socketio.on("view_story")
def view_story(data):
    s = db.session.get(Story, data["id"])
    if s:
        viewers = json.loads(s.viewers)
        if current_user.username not in viewers:
            viewers.append(current_user.username)
            s.viewers = json.dumps(viewers, ensure_ascii=False)
            db.session.commit()

def send_stories():
    stories = Story.query.all()
    data = {}
    for s in stories:
        data.setdefault(s.username, {
            "avatar": s.avatar,
            "items": []
        })
        data[s.username]["items"].append({
            "id": s.id,
            "content": s.content,
            "type": s.media_type,
            "viewers": json.loads(s.viewers)
        })

    emit("story_list", json.loads(json.dumps(data, ensure_ascii=False)), broadcast=True)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
