from gevent import monkey
monkey.patch_all()

import os, json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra_fast_wa_2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
# Bellek hatalarını önlemek için sınırı 100MB'a çekiyoruz (Render ücretsiz planı için güvenli)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 

db = SQLAlchemy(app)
# Loglardaki WebSocket hatasını çözen özel konfigürasyon
socketio = SocketIO(app, 
    cors_allowed_origins="*", 
    async_mode='gevent', 
    max_http_buffer_size=100 * 1024 * 1024,
    ping_timeout=60,
    ping_interval=25
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) # 'text', 'image', 'video'
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    audio_data = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- ROUTER ---
@app.route('/chat')
@login_required
def chat():
    msgs = Message.query.order_by(Message.id.desc()).limit(50).all()
    return render_template('chat.html', user=current_user, initial_msgs=reversed(list(msgs)), stories=get_grouped_stories())

# --- SOCKET EVENTS ---
@socketio.on('message')
def handle_msg(data):
    time_str = datetime.now().strftime("%H:%M")
    new_msg = Message(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['msg'],
        msg_type=data.get('type', 'text'),
        timestamp=time_str
    )
    db.session.add(new_msg)
    db.session.commit()
    # KISMİ GÜNCELLEME: Sadece yeni mesajı gönder
    emit('new_message', {
        'id': new_msg.id, 'user': new_msg.username, 'avatar': new_msg.user_avatar,
        'msg': new_msg.content, 'type': new_msg.msg_type, 'time': new_msg.timestamp
    }, broadcast=True)

@socketio.on('update_profile')
def update_profile(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    # Veritabanındaki geçmiş kayıtları da güncelle (Tutarlılık için)
    Message.query.filter_by(username=user.username).update({'user_avatar': data['avatar']})
    Story.query.filter_by(username=user.username).update({'user_avatar': data['avatar']})
    db.session.commit()
    # Tüm kullanıcılara bu kişinin resminin değiştiğini bildir
    emit('profile_sync', {'username': user.username, 'avatar': data['avatar']}, broadcast=True)

@socketio.on('add_story')
def add_story(data):
    story = Story(
        username=current_user.username, user_avatar=current_user.avatar,
        content=data['content'], audio_data=data.get('music'), media_type=data.get('type')
    )
    db.session.add(story)
    db.session.commit()
    emit('story_refresh', get_grouped_stories(), broadcast=True)

@socketio.on('delete_message')
def del_msg(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.username == current_user.username:
        db.session.delete(msg)
        db.session.commit()
        emit('message_deleted', {'id': data['id']}, broadcast=True)

def get_grouped_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar': s.user_avatar, 'items': []}
        grouped[s.username]['items'].append({
            'id': s.id, 'content': s.content, 'music': s.audio_data, 
            'type': s.media_type, 'viewers': json.loads(s.viewers)
        })
    return grouped

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
