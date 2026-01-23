from gevent import monkey
monkey.patch_all()

import os, json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra_wa_v2_2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100MB

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=100 * 1024 * 1024)

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text) # Base64 profil resmi

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) # text, image, video
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- ROUTES ---
@app.route('/')
def index(): return redirect(url_for('chat'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_user = User(
            username=request.form['username'],
            password=request.form['password'],
            avatar=request.form.get('avatar_data', '') # Profil resmi kaydediliyor
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    msgs = Message.query.order_by(Message.id.desc()).limit(50).all()
    return render_template('chat.html', user=current_user, initial_msgs=reversed(list(msgs)))

@app.route('/live')
@login_required
def live(): return render_template('live.html', user=current_user)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

# --- SOCKETS ---
online_users = {}

@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = {
            "avatar": current_user.avatar,
            "id": request.sid
        }
        emit('update_user_list', online_users, broadcast=True)

@socketio.on('disconnect')
def disconnect():
    if current_user.is_authenticated:
        online_users.pop(current_user.username, None)
        emit('update_user_list', online_users, broadcast=True)

@socketio.on('message')
def handle_msg(data):
    time_str = datetime.now().strftime("%H:%M")
    msg = Message(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['msg'],
        msg_type=data.get('type', 'text'),
        timestamp=time_str
    )
    db.session.add(msg)
    db.session.commit()
    emit('new_message', {
        'id': msg.id, 'user': msg.username, 'avatar': msg.user_avatar,
        'msg': msg.content, 'type': msg.msg_type, 'time': msg.timestamp
    }, broadcast=True)

@socketio.on('update_profile')
def update_profile(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    Message.query.filter_by(username=user.username).update({'user_avatar': data['avatar']})
    db.session.commit()
    online_users[user.username]['avatar'] = data['avatar']
    emit('profile_sync', {'username': user.username, 'avatar': data['avatar']}, broadcast=True)
    emit('update_user_list', online_users, broadcast=True)

@socketio.on('delete_message')
def del_msg(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.username == current_user.username:
        db.session.delete(msg)
        db.session.commit()
        emit('message_deleted', {'id': data['id']}, broadcast=True)

# WebRTC Signaling
@socketio.on('signal')
def handle_signal(data):
    emit('signal', data, broadcast=True, include_self=False)

@socketio.on('get_stories')
def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar': s.user_avatar, 'items': []}
        grouped[s.username]['items'].append({'id': s.id, 'content': s.content, 'type': s.media_type})
    emit('receive_stories', grouped)

@socketio.on('add_story')
def add_story(data):
    s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['content'], media_type=data['type'])
    db.session.add(s)
    db.session.commit()
    send_stories()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
