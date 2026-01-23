from gevent import monkey
monkey.patch_all()

import os, json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'full_power_wa_2026'
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
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text) # Base64 Fotoğraf
    bg_img = db.Column(db.Text) # Kalıcı Arka Plan

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) # text, file
    file_name = db.Column(db.String(100))
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- ROUTLAR ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        gender = request.form.get('gender')
        avatar_data = request.form.get('avatar_data')
        
        # Eğer kullanıcı resim yüklemediyse cinsiyete göre varsayılan ata
        if not avatar_data or len(avatar_data) < 100:
            avatar_data = "https://cdn-icons-png.flaticon.com/512/4140/4140037.png" if gender == "Erkek" else "https://cdn-icons-png.flaticon.com/512/4140/4140047.png"

        new_user = User(
            username=request.form['username'],
            password=request.form['password'],
            gender=gender,
            avatar=avatar_data
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/chat')
@login_required
def chat():
    msgs = Message.query.order_by(Message.id.desc()).limit(100).all()
    return render_template('chat.html', user=current_user, initial_msgs=reversed(list(msgs)))

# --- SOCKET ---
online_users = {}

@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = {"avatar": current_user.avatar, "sid": request.sid}
        emit('update_user_list', online_users, broadcast=True)
        send_stories()

@socketio.on('message')
def handle_msg(data):
    msg = Message(
        username=current_user.username, user_avatar=current_user.avatar,
        content=data['content'], msg_type=data.get('type', 'text'),
        file_name=data.get('file_name', ''),
        timestamp=datetime.now().strftime("%H:%M")
    )
    db.session.add(msg)
    db.session.commit()
    emit('new_message', {
        'id': msg.id, 'user': msg.username, 'avatar': msg.user_avatar,
        'content': msg.content, 'type': msg.msg_type, 'file_name': msg.file_name, 'time': msg.timestamp
    }, broadcast=True)

@socketio.on('add_story')
def add_story(data):
    s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['content'])
    db.session.add(s)
    db.session.commit()
    send_stories()

def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar': s.user_avatar, 'content': s.content}
    emit('receive_stories', grouped, broadcast=True)

@socketio.on('update_profile')
def update_profile(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    db.session.commit()
    online_users[user.username]['avatar'] = data['avatar']
    emit('update_user_list', online_users, broadcast=True)

@socketio.on('update_bg')
def update_bg(data):
    user = db.session.get(User, current_user.id)
    user.bg_img = data['bg']
    db.session.commit()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
