from gevent import monkey
monkey.patch_all()

import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

# Uygulama Başlatma
app = Flask(__name__)
app.config['SECRET_KEY'] = 'wa_ultra_pro_2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
# Base64 veri transferi için limitleri yüksek tutuyoruz
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=100 * 1024 * 1024)

# --- VERİTABANI MODELLERİ ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text) # Base64 Profil Resmi
    bg_img = db.Column(db.Text) # Kişisel Arka Plan Resmi

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
    content = db.Column(db.Text) # Base64 Medya
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]') # İzleyenler listesi (JSON)

with app.app_context():
    db.create_all()

# --- LOGIN YÖNETİMİ ---
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    return db.session.get(User, int(id))

# --- SAYFA ROUTLARI ---

@app.route('/')
def index():
    return redirect(url_for('chat'))

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
        existing_user = User.query.filter_by(username=request.form['username']).first()
        if existing_user:
            return "Bu kullanıcı adı zaten alınmış!", 400
        
        # register.html'den gelen avatar_data'yı alıyoruz
        avatar_data = request.form.get('avatar_data')
        
        new_user = User(
            username=request.form['username'],
            password=request.form['password'],
            avatar=avatar_data if avatar_data else ""
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    # Son 50 mesajı getir
    msgs = Message.query.order_by(Message.id.desc()).limit(50).all()
    return render_template('chat.html', user=current_user, initial_msgs=reversed(list(msgs)))

@app.route('/live')
@login_required
def live():
    return render_template('live.html', user=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- SOCKET.IO MANTIĞI ---

online_users = {} # {username: {avatar, sid}}

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = {
            'avatar': current_user.avatar,
            'sid': request.sid
        }
        emit('update_user_list', online_users, broadcast=True)
        # Giriş yapınca güncel hikayeleri de gönder
        send_stories_to_user(request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        online_users.pop(current_user.username, None)
        emit('update_user_list', online_users, broadcast=True)

@socketio.on('message')
def handle_message(data):
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
    
    emit('new_message', {
        'id': new_msg.id,
        'user': new_msg.username,
        'avatar': new_msg.user_avatar,
        'msg': new_msg.content,
        'type': new_msg.msg_type,
        'time': new_msg.timestamp
    }, broadcast=True)

@socketio.on('delete_message')
def delete_message(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.username == current_user.username:
        db.session.delete(msg)
        db.session.commit()
        emit('message_deleted', {'id': data['id']}, broadcast=True)

@socketio.on('update_profile')
def update_profile(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    
    # Eski mesajlardaki avatarları da güncelle (Opsiyonel ama tutarlılık sağlar)
    Message.query.filter_by(username=user.username).update({'user_avatar': data['avatar']})
    Story.query.filter_by(username=user.username).update({'user_avatar': data['avatar']})
    
    db.session.commit()
    
    # Online listesini güncelle
    if user.username in online_users:
        online_users[user.username]['avatar'] = data['avatar']
    
    emit('profile_sync', {'username': user.username, 'avatar': data['avatar']}, broadcast=True)
    emit('update_user_list', online_users, broadcast=True)

@socketio.on('update_bg')
def update_bg(data):
    user = db.session.get(User, current_user.id)
    user.bg_img = data.get('bg') # None gelirse varsayılana döner
    db.session.commit()

# --- HİKAYE YÖNETİMİ ---

def get_grouped_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped:
            grouped[s.username] = {'avatar': s.user_avatar, 'items': []}
        grouped[s.username]['items'].append({
            'id': s.id,
            'content': s.content,
            'type': s.media_type
        })
    return grouped

def send_stories_to_user(sid=None):
    data = get_grouped_stories()
    if sid:
        emit('receive_stories', data, room=sid)
    else:
        emit('receive_stories', data, broadcast=True)

@socketio.on('get_stories')
def handle_get_stories():
    send_stories_to_user(request.sid)

@socketio.on('add_story')
def add_story(data):
    new_story = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['content'],
        media_type=data.get('type', 'image')
    )
    db.session.add(new_story)
    db.session.commit()
    send_stories_to_user() # Herkese güncel listeyi gönder

# --- GÖRÜNTÜLÜ KONUŞMA (WebRTC Sinyal) ---
@socketio.on('signal')
def handle_signal(data):
    # Gelen sinyali gönderen hariç herkese (veya hedefe) ilet
    emit('signal', data, broadcast=True, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
