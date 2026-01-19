from gevent import monkey
monkey.patch_all()

import os, json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    logout_user, login_required, current_user
)
from flask_socketio import SocketIO, join_room

# ---------------- APP ----------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev_key")

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_v2.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# ---------------- MODELS ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    media = db.Column(db.Text)        # image / video base64
    music = db.Column(db.Text)        # optional base64 audio
    media_type = db.Column(db.String(10))  # image | video
    viewers = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ---------------- LOGIN ----------------
login_manager = LoginManager(app)
login_manager.login_view = "auth"

@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))

# ---------------- ROUTES ----------------
@app.route("/", methods=["GET"])
def auth():
    if current_user.is_authenticated:
        return redirect(url_for("chat"))
    return render_template("auth.html")

@app.route("/login", methods=["POST"])
def login_proc():
    u = User.query.filter_by(username=request.form["username"]).first()
    if u and u.password == request.form["password"]:
        login_user(u)
        return redirect(url_for("chat"))
    return redirect(url_for("auth"))

@app.route("/register", methods=["POST"])
def register_proc():
    if User.query.filter_by(username=request.form["username"]).first():
        return redirect(url_for("auth"))

    u = User(
        username=request.form["username"],
        password=request.form["password"],
        avatar="https://cdn-icons-png.flaticon.com/512/847/847969.png"
    )
    db.session.add(u)
    db.session.commit()
    login_user(u)
    return redirect(url_for("chat"))

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", user=current_user)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth"))

# ---------------- SOCKET ----------------
@socketio.on("connect")
def on_connect():
    send_stories()

# -------- STORY EVENTS --------
@socketio.on("add_story")
def add_story(data):
    s = Story(
        username=current_user.username,
        avatar=current_user.avatar,
        media=data["media"],
        music=data.get("music"),
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
    if not s:
        return
    viewers = json.loads(s.viewers)
    if current_user.username not in viewers:
        viewers.append(current_user.username)
        s.viewers = json.dumps(viewers)
        db.session.commit()

def send_stories():
    stories = Story.query.order_by(Story.created_at.asc()).all()
    grouped = {}
    me = current_user.username if current_user.is_authenticated else None

    for s in stories:
        if s.username not in grouped:
            grouped[s.username] = {
                "avatar": s.avatar,
                "items": []
            }
        grouped[s.username]["items"].append({
            "id": s.id,
            "media": s.media,
            "music": s.music,
            "type": s.media_type,
            "viewers": json.loads(s.viewers),
            "can_delete": s.username == me
        })

    socketio.emit("story_list", grouped)

# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host="0.0.0.0", port=port)
