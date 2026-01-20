import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, redirect, url_for, request
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
import uuid

# ---------------- APP ----------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "super-secret-key"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet"
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ---------------- FAKE DB ----------------
USERS = {}
MESSAGES = {}          # room -> [messages]
STORIES = {}           # username -> stories
MUSIC = []             # music list
BLOCKS = {}            # user -> [blocked users]

# ---------------- MODELS ----------------
class User(UserMixin):
    def __init__(self, uid, username):
        self.id = uid
        self.username = username
        self.avatar = f"https://i.pravatar.cc/150?u={username}"

@login_manager.user_loader
def load_user(uid):
    return USERS.get(uid)

# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return redirect("/chat") if current_user.is_authenticated else redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        for u in USERS.values():
            if u.username == username:
                login_user(u)
                return redirect("/chat")

        uid = str(uuid.uuid4())
        user = User(uid, username)
        USERS[uid] = user
        BLOCKS[username] = []
        login_user(user)
        return redirect("/chat")

    return render_template("login.html")

@app.route("/register")
def register():
    return redirect("/login")

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", user=current_user)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/login")

# ---------------- SOCKET CORE ----------------
@socketio.on("connect")
def on_connect():
    emit("update_user_list", user_list(), broadcast=True)
    emit("story_list", STORIES)

@socketio.on("join_room")
def on_join(data):
    room = data.get("room", "Genel")
    join_room(room)
    emit("history", MESSAGES.get(room, []))

# ---------------- MESSAGE ----------------
@socketio.on("send_message")
def send_message(data):
    room = data.get("room", "Genel")
    msg = {
        "id": str(uuid.uuid4()),
        "user": current_user.username,
        "ava": current_user.avatar,
        "msg": data["msg"],
        "type": data.get("type", "text"),
        "time": datetime.now().strftime("%H:%M"),
        "status": "sent"
    }
    MESSAGES.setdefault(room, []).append(msg)
    emit("message", msg, room=room)

@socketio.on("delete_message")
def delete_message(data):
    mid = data["id"]
    for room in MESSAGES:
        MESSAGES[room] = [m for m in MESSAGES[room] if m["id"] != mid]
    emit("message_deleted", {"id": mid}, broadcast=True)

# ---------------- STATUS ----------------
@socketio.on("read_message")
def read_message(data):
    mid = data["id"]
    for room in MESSAGES:
        for m in MESSAGES[room]:
            if m["id"] == mid:
                m["status"] = "read"
                emit("msg_status_update", {"id": mid}, room=room)

# ---------------- PROFILE ----------------
@socketio.on("update_profile")
def update_profile(data):
    current_user.avatar = data["avatar"]
    emit("update_user_list", user_list(), broadcast=True)
    emit("story_list", STORIES, broadcast=True)

# ---------------- USERS ----------------
def user_list():
    return [
        {"username": u.username, "avatar": u.avatar}
        for u in USERS.values()
    ]

# ---------------- BLOCK ----------------
@socketio.on("block_user")
def block_user(data):
    BLOCKS[current_user.username].append(data["username"])

# ---------------- STORY ----------------
@socketio.on("add_story")
def add_story(data):
    user = current_user.username
    STORIES.setdefault(user, {
        "avatar": current_user.avatar,
        "items": []
    })

    story = {
        "id": str(uuid.uuid4()),
        "content": data["content"],
        "music": data.get("music"),
        "type": data["type"],
        "viewers": [],
        "can_delete": True,
        "duration": 30
    }

    STORIES[user]["items"].append(story)
    emit("story_list", STORIES, broadcast=True)

@socketio.on("view_story")
def view_story(data):
    sid = data["id"]
    for u in STORIES:
        for s in STORIES[u]["items"]:
            if s["id"] == sid and current_user.username not in s["viewers"]:
                s["viewers"].append(current_user.username)

@socketio.on("delete_story")
def delete_story(data):
    sid = data["id"]
    user = current_user.username
    STORIES[user]["items"] = [s for s in STORIES[user]["items"] if s["id"] != sid]
    emit("story_list", STORIES, broadcast=True)

# ---------------- MUSIC ----------------
@socketio.on("add_music")
def add_music(data):
    MUSIC.append({
        "title": data["name"],
        "src": data["src"]
    })
    emit("music_list", MUSIC, broadcast=True)

@socketio.on("get_music")
def get_music():
    emit("music_list", MUSIC)

# ---------------- CALL SIGNAL (UI ONLY) ----------------
@socketio.on("call_signal")
def call_signal(data):
    emit("call_signal", data, room=data["room"], include_self=False)

# ---------------- RUN ----------------
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
