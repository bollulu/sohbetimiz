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
app.config['SECRET_KEY'] = 'gizli_anahtar_v3_final'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 # 500 MB Limit

# Veritabanı Yolu
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_database_v3.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)
    bg_image = db.Column(db.Text, default="") 
    blocked_users = db.Column(db.Text, default='[]') 

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(50), nullable=True)
    admin = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100), index=True)
    sender = db.Column(db.String(50))
    sender_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    m_type = db.Column(db.String(20)) 
    timestamp = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='sent')

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    music_data = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    viewers = db.Column(db.Text, default='[]')

class Music(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    data = db.Column(db.Text)
    uploader = db.Column(db.String(50))

# Veritabanı oluştur
with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'index'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- ROTALAR ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    user = User.query.filter_by(username=username, password=password).first()
    if user:
        login_user(user)
        return redirect(url_for('chat'))
    return "Hatalı giriş. <a href='/'>Geri dön</a>"

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')
    gender = request.form.get('gender')
    avatar_data = request.form.get('avatar_data')

    if User.query.filter_by(username=username).first():
        return "Bu isimde kullanıcı var. <a href='/'>Geri dön</a>"

    if not avatar_data:
        avatar_data = "https://cdn-icons-png.flaticon.com/512/149/149071.png"

    new_user = User(username=username, password=password, gender=gender, avatar=avatar_data)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- SOCKET OLAYLARI ---

@socketio.on('connect')
def on_connect():
    # Bağlanınca grupları gönder
    groups = Group.query.all()
    group_list = [{'name': g.name, 'protected': bool(g.password)} for g in groups]
    emit('update_group_list', group_list)

@socketio.on('delete_account_confirm')
def delete_account_confirm(data):
    password = data.get('password')
    if current_user.password == password:
        username = current_user.username
        # 1. Kullanıcının attığı mesajları sil
        Message.query.filter_by(sender=username).delete()
        # 2. Hikayelerini sil
        Story.query.filter_by(username=username).delete()
        # 3. Müziklerini sil
        Music.query.filter_by(uploader=username).delete()
        # 4. Kullanıcıyı sil
        db.session.delete(current_user)
        db.session.commit()
        logout_user()
        emit('account_deleted_success', {'url': url_for('index')})
    else:
        emit('account_deleted_error', {'msg': 'Şifre Yanlış!'})

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    
    # Mesajları yükle
    messages = Message.query.filter_by(room=room).order_by(Message.timestamp).all()
    history = []
    blocked = json.loads(current_user.blocked_users)
    
    for m in messages:
        if m.sender not in blocked:
            history.append({
                'id': m.id, 'sender': m.sender, 'avatar': m.sender_avatar,
                'content': m.content, 'type': m.m_type, 
                'time': m.timestamp.strftime('%H:%M'),
                'status': 'read'
            })
    emit('load_history', history)
    
    # Kişi listesi güncelle
    users = User.query.all()
    user_list = []
    for u in users:
        user_list.append({'username': u.username, 'avatar': u.avatar, 'is_me': (u.username == current_user.username)})
    emit('update_user_list', user_list, broadcast=True)

@socketio.on('send_message')
def handle_message(data):
    room = data['room']
    content = data['msg']
    m_type = data['type']
    
    msg = Message(room=room, sender=current_user.username, sender_avatar=current_user.avatar, content=content, m_type=m_type)
    db.session.add(msg)
    db.session.commit()
    
    emit('new_message', {
        'id': msg.id, 'sender': current_user.username, 'avatar': current_user.avatar,
        'content': content, 'type': m_type, 
        'time': datetime.now().strftime('%H:%M'), 'status': 'sent'
    }, room=room)

@socketio.on('delete_message')
def delete_msg(data):
    msg = db.session.get(Message, data['id'])
    # Sadece gönderen silebilir
    if msg and msg.sender == current_user.username:
        db.session.delete(msg)
        db.session.commit()
        emit('message_deleted', {'id': data['id']}, room=msg.room)

@socketio.on('update_profile')
def update_profile(data):
    if 'avatar' in data:
        current_user.avatar = data['avatar']
    if 'bg' in data:
        current_user.bg_image = data['bg']
    if 'reset_bg' in data:
        current_user.bg_image = ""
        
    db.session.commit()
    emit('profile_updated', {'username': current_user.username, 'avatar': current_user.avatar}, broadcast=True)

@socketio.on('block_user')
def block_user(data):
    target = data['username']
    blocked = json.loads(current_user.blocked_users)
    if target not in blocked:
        blocked.append(target)
    else:
        blocked.remove(target)
    current_user.blocked_users = json.dumps(blocked)
    db.session.commit()
    emit('block_updated', {'blocked_list': blocked})

@socketio.on('create_group')
def create_group(data):
    name = data['name']
    password = data.get('password', '')
    if not Group.query.filter_by(name=name).first():
        g = Group(name=name, password=password, admin=current_user.username)
        db.session.add(g)
        db.session.commit()
        
        # Tüm kullanıcılara yeni grup listesini yolla
        groups = Group.query.all()
        group_list = [{'name': grp.name, 'protected': bool(grp.password)} for grp in groups]
        emit('update_group_list', group_list, broadcast=True)

@socketio.on('post_story')
def post_story(data):
    s = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['content'],
        media_type=data['type'],
        music_data=data.get('music')
    )
    db.session.add(s)
    db.session.commit()
    broadcast_stories()

@socketio.on('get_stories')
def get_stories():
    broadcast_stories()

def broadcast_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped:
            grouped[s.username] = {'username': s.username, 'avatar': s.user_avatar, 'items': []}
        
        viewers = json.loads(s.viewers)
        grouped[s.username]['items'].append({
            'id': s.id, 'content': s.content, 'type': s.media_type, 
            'music': s.music_data, 'viewers': viewers,
            'seen_by_me': (current_user.username in viewers)
        })
    emit('stories_update', grouped, broadcast=True)

@socketio.on('story_seen')
def story_seen(data):
    s = db.session.get(Story, data['id'])
    if s:
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
        broadcast_stories()

@socketio.on('add_music')
def add_music(data):
    m = Music(title=data['name'], data=data['content'], uploader=current_user.username)
    db.session.add(m)
    db.session.commit()
    send_music_list()

@socketio.on('get_music')
def get_music():
    send_music_list()

def send_music_list():
    musics = Music.query.all()
    data = [{'id': m.id, 'title': m.title, 'src': m.data, 'uploader': m.uploader} for m in musics]
    emit('music_list', data, broadcast=True)

@socketio.on('delete_music')
def del_music(data):
    m = db.session.get(Music, data['id'])
    if m and m.uploader == current_user.username:
        db.session.delete(m)
        db.session.commit()
        send_music_list()

# WebRTC
@socketio.on('video_signal')
def video_signal(data):
    emit('video_signal', data, room=data['room'], include_self=False)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
