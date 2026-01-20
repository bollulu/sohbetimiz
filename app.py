import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, redirect, url_for, request
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret123"

socketio = SocketIO(app, cors_allowed_origins="*")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ---- SAHTE VERİTABANI ----
users = {}
messages = []
user_counter = 1
msg_counter = 1

# ---- USER MODEL ----
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username
        self.avatar = "https://i.pravatar.cc/150?u=" + username

@login_manager.user_loader
def load_user(user_id):
    return users.get(int(user_id))

# ---- ROUTES ----
@app.route("/", methods=["GET"])
def index():
    if current_user.is_authenticated:
        return redirect("/chat")
    return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    global user_counter
    if request.method == "POST":
        username = request.form["username"]
        for u in users.values():
            if u.username == username:
                login_user(u)
                return redirect("/chat")
        user = User(user_counter, username)
        users[user_counter] = user
        user_counter += 1
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

# ---- SOCKET EVENTS ----
@socketio.on("connect")
def on_connect():
    emit("history", messages)
    emit("update_user_list", [
        {"username": u.username, "avatar": u.avatar}
        for u in users.values()
    ], broadcast=True)

@socketio.on("send_message")
def send_message(data):
    global msg_counter
    msg = {
        "id": msg_counter,
        "user": current_user.username,
        "ava": current_user.avatar,
        "msg": data["msg"],
        "type": data.get("type", "text"),
        "time": datetime.now().strftime("%H:%M")
    }
    msg_counter += 1
    messages.append(msg)
    emit("message", msg, broadcast=True)

@socketio.on("delete_message")
def delete_message(data):
    global messages
    messages = [m for m in messages if m["id"] != data["id"]]
    emit("message_deleted", data, broadcast=True)

# ---- RUN ----
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
