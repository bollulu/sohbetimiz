from gevent import monkey
monkey.patch_all()

import os, json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'wa_ultra_music_v12'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="gevent",
    max_http_buffer_size=1024 * 1024 * 1024
)

# ===================== MODELS =====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20))
    timestamp = db.Column(db.String(10))
    room = db.Column(db.String(50), default="Genel")

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    audio_data = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default="[]")
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ===================== LOGIN =====================

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ===================== ROUTES =====================

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username")).first()
        if user and user.password == request.form.get("password"):
            login_user(user)
            return redirect(url_for("chat"))
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if not User.query.filter_by(username=request.form.get("username")).first():
            avatar = request.form.get("avatar_data")
            if not avatar:
                avatar = "https://www.w3schools.com/howto/img_avatar.png"
            u = User(
                username=request.form.get("username"),
                password=request.form.get("password"),
                gender=request.form.get("gender"),
                avatar=avatar
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

# ===================== SOCKET =====================

@socketio.on("join")
def join(data):
    join_room("Genel")
    msgs = Message.query.all()
    emit("history", [
        {
            "id": m.id,
            "user": m.username,
            "avatar": m.user_avatar,
            "msg": m.content,
            "type": m.msg_type,
            "time": m.timestamp
        } for m in msgs
    ])
    send_stories()
    emit("update_user_list", get_users(), broadcast=True)

@socketio.on("message")
def message(data):
    now = datetime.now().strftime("%H:%M")
    m = Message(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data["msg"],
        msg_type=data.get("type", "text"),
        timestamp=now
    )
    db.session.add(m)
    db.session.commit()
    emit("message", {
        "id": m.id,
        "user": m.username,
        "avatar": m.user_avatar,
        "msg": m.content,
        "type": m.msg_type,
        "time": now
    }, broadcast=True)

@socketio.on("add_story")
def add_story(data):
    s = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data["content"],
        audio_data=data.get("music"),
        media_type=data["type"]
    )
    db.session.add(s)
    db.session.commit()
    send_stories()

@socketio.on("delete_story")
def delete_story(data):
    s = db.session.get(Story, data["id"])
    if s and s.username == current_user.username:
        db.session.delete(s)
        db.session.commit()
        send_stories()

@socketio.on("view_story")
def view_story(data):
    s = db.session.get(Story, data["id"])
    if s:
        viewers = json.loads(s.viewers)
        if current_user.username not in viewers:
            viewers.append(current_user.username)
            s.viewers = json.dumps(viewers)
            db.session.commit()
            send_stories()

def send_stories():
    stories = Story.query.all()
    data = {}
    for s in stories:
        data.setdefault(s.username, {
            "avatar": s.user_avatar,
            "items": []
        })
        data[s.username]["items"].append({
            "id": s.id,
            "content": s.content,
            "music": s.audio_data,
            "type": s.media_type,
            "viewers": json.loads(s.viewers)
        })
    emit("story_list", data, broadcast=True)

def get_users():
    return {u.username: {"avatar": u.avatar} for u in User.query.all()}

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
