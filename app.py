from gevent import monkey
monkey.patch_all()

import os, json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    login_required, current_user
)
from flask_socketio import SocketIO, emit, join_room

# -------------------------------------------------
# APP
# -------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_secret_key_2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# -------------------------------------------------
# MODELS
# -------------------------------------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)
    blocked_users = db.Column(db.Text, default='[]')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20))
    timestamp = db.Column(db.String(10))
    status = db.Column(db.String(10), default='sent')

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    audio_data = db.Column(db.Text)
    media_type = db.Column(db.String(20))  # image | video
    viewers = db.Column(db.Text, default='[]')
    duration = db.Column(db.Integer, default=30)

with app.app_context():
    db.create_all()

# -------------------------------------------------
# LOGIN
# -------------------------------------------------
login_manager = LoginManager(app)
login_manager.login_view = 'auth'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# -------------------------------------------------
# ROUTES
# -------------------------------------------------
@app.route('/')
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login_proc():
    u = User.query.filter_by(username=request.form['username']).first()
    if u and u.password == request.form['password']:
        login_user(u)
        return redirect(url_for('chat'))
    return redirect(url_for('auth'))

@app.route('/register', methods=['POST'])
def register_proc():
    if User.query.filter_by(username=request.form['username']).first():
        return redirect(url_for('auth'))

    ava = request.form.get('avatar_data')
    if not ava:
        ava = "https://cdn-icons-png.flaticon.com/512/847/847969.png"

    u = User(
        username=request.form['username'],
        password=request.form['password'],
        avatar=ava
    )
    db.session.add(u)
    db.session.commit()
    login_user(u)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth'))

# -------------------------------------------------
# SOCKET.IO – CHAT
# -------------------------------------------------
@socketio.on('join_room')
def join(data):
    room = data['room']
    join_room(room)

    msgs = Message.query.filter_by(room=room).all()
    blocked = json.loads(current_user.blocked_users)

    history = []
    for m in msgs:
        if m.sender not in blocked:
            history.append({
                'id': m.id,
                'user': m.sender,
                'ava': m.avatar,
                'msg': m.content,
                'type': m.msg_type,
                'time': m.timestamp,
                'status': m.status
            })
    emit('history', history)
    send_stories()

@socketio.on('send_message')
def send_msg(data):
    now = datetime.now().strftime('%H:%M')
    m = Message(
        room=data['room'],
        sender=current_user.username,
        avatar=current_user.avatar,
        content=data['msg'],
        msg_type=data['type'],
        timestamp=now
    )
    db.session.add(m)
    db.session.commit()

    emit('message', {
        'id': m.id,
        'user': m.sender,
        'ava': m.avatar,
        'msg': m.content,
        'type': m.msg_type,
        'time': now,
        'status': 'sent'
    }, to=data['room'])

# -------------------------------------------------
# SOCKET.IO – STORY (HİKAYE)
# -------------------------------------------------
@socketio.on('add_story')
def add_story(data):
    s = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['content'],
        audio_data=data.get('music'),
        media_type=data['type'],
        duration=data.get('duration', 30)
    )
    db.session.add(s)
    db.session.commit()
    send_stories()

@socketio.on('view_story')
def view_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username != current_user.username:
        viewers = json.loads(s.viewers)
        if current_user.username not in viewers:
            viewers.append(current_user.username)
            s.viewers = json.dumps(viewers)
            db.session.commit()

@socketio.on('delete_story')
def delete_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        db.session.delete(s)
        db.session.commit()
        send_stories()

def send_stories():
    stories = Story.query.all()
    grouped = {}

    for s in stories:
        if s.username not in grouped:
            grouped[s.username] = {
                'avatar': s.user_avatar,
                'items': []
            }

        grouped[s.username]['items'].append({
            'id': s.id,
            'content': s.content,
            'music': s.audio_data,
            'type': s.media_type,
            'duration': s.duration,
            'viewers': json.loads(s.viewers),
            'can_delete': s.username == current_user.username
        })

    emit('story_list', grouped, broadcast=True)

# -------------------------------------------------
# RUN
# -------------------------------------------------
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
