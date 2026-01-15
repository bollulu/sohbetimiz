from gevent import monkey
monkey.patch_all()
import os
import json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'wa_ultra_pro_v15'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 500 # 500MB Limit

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) # text, image, audio
    timestamp = db.Column(db.String(10))
    status = db.Column(db.String(10), default='sent') # sent, read

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    content = db.Column(db.Text)      # Resim veya Video
    audio_data = db.Column(db.Text)   # Arka plan müziği
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@socketio.on('join')
def on_join(data):
    join_room('Genel')
    # Kullanıcı bilgilerini ve hikayeleri tazele
    send_user_updates()
    send_stories()

@socketio.on('message')
def handle_msg(data):
    now = datetime.now().strftime("%H:%M")
    msg = Message(username=current_user.username, content=data['msg'], msg_type=data.get('type','text'), timestamp=now)
    db.session.add(msg); db.session.commit()
    # Önce 'gönderildi' (tek tık) olarak yayınla
    emit('message', {'id':msg.id, 'user':current_user.username, 'msg':data['msg'], 'type':msg.msg_type, 'time':now, 'status':'sent'}, broadcast=True)
    
    # Simüle edilmiş 'okundu' (çift tık) işlemi
    socketio.sleep(1)
    msg.status = 'read'
    db.session.commit()
    emit('msg_status_update', {'id': msg.id, 'status': 'read'}, broadcast=True)

@socketio.on('update_profile')
def update_profile(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    db.session.commit()
    send_user_updates()

def send_user_updates():
    users = User.query.all()
    user_data = {u.username: u.avatar for u in users}
    emit('update_user_list', user_data, broadcast=True)

def send_stories():
    all_stories = Story.query.all()
    grouped = {}
    for s in all_stories:
        if s.username not in grouped: grouped[s.username] = []
        grouped[s.username].append({'id': s.id, 'content': s.content, 'audio': s.audio_data, 'type': s.media_type})
    emit('story_list', grouped, broadcast=True)

# (Diğer route'lar: login, register, delete_message, delete_story vs. önceki kodlarla aynıdır)
