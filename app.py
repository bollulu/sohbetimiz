from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra_whatsapp_fixed_final_2026'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB Limit

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)
    gender = db.Column(db.String(20))
    blocked_list = db.Column(db.Text, default="")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50))
    avatar = db.Column(db.Text) # Gönderildiği andaki avatar (gerekirse güncellenecek)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) # text, image, video, audio
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(10)) # image/video
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- ROTALAR ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username')
        if User.query.filter_by(username=u).first(): return "Bu isim alınmış!", 400
        new_u = User(
            username=u, 
            password=request.form.get('password'), 
            gender=request.form.get('gender'), 
            avatar=request.form.get('avatar_data')
        )
        db.session.add(new_u); db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/delete_acc', methods=['POST'])
@login_required
def delete_acc():
    if current_user.password == request.form.get('password'):
        db.session.delete(current_user); db.session.commit()
        logout_user(); return "OK"
    return "FAIL", 403

# --- SOCKET EVENTS ---
online_users = {}

@socketio.on('connect')
def on_connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = {"avatar": current_user.avatar}
        emit('update_online', online_users, broadcast=True)
        
        # Geçmiş Mesajlar
        msgs = Message.query.all()
        history = []
        for m in msgs:
            # Güncel avatarı user tablosundan çekelim ki eski kalmasın
            u = User.query.filter_by(username=m.sender).first()
            current_ava = u.avatar if u else m.avatar
            history.append({
                'id': m.id, 'sender': m.sender, 'avatar': current_ava, 
                'content': m.content, 'type': m.msg_type, 'time': m.timestamp
            })
        emit('load_history', history)
        send_stories()

@socketio.on('disconnect')
def on_disconnect():
    if current_user.is_authenticated and current_user.username in online_users:
        del online_users[current_user.username]
        emit('update_online', online_users, broadcast=True)

@socketio.on('send_msg')
def handle_msg(data):
    m = Message(
        sender=current_user.username, 
        avatar=current_user.avatar, 
        content=data['content'], 
        msg_type=data['type'], 
        timestamp=datetime.now().strftime("%H:%M")
    )
    db.session.add(m); db.session.commit()
    emit('new_msg', {
        'id': m.id, 'sender': m.sender, 'avatar': m.avatar, 
        'content': m.content, 'type': m.msg_type, 'time': m.timestamp
    }, broadcast=True)

@socketio.on('delete_msg')
def delete_message(data):
    msg = db.session.get(Message, data['id'])
    if msg:
        db.session.delete(msg); db.session.commit()
        emit('msg_deleted', {'id': data['id']}, broadcast=True)

# HİKAYE EKLEME
@socketio.on('add_story')
def add_story(data):
    s = Story(username=current_user.username, avatar=current_user.avatar, 
              content=data['content'], media_type=data['type'])
    db.session.add(s); db.session.commit()
    send_stories()

@socketio.on('delete_story')
def delete_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        db.session.delete(s); db.session.commit()
        send_stories()

# PROFİL GÜNCELLEME (HER YERDE DEĞİŞSİN DİYE)
@socketio.on('update_avatar')
def update_avatar_func(data):
    current_user.avatar = data['avatar']
    db.session.commit()
    
    online_users[current_user.username]['avatar'] = data['avatar']
    
    # 1. Online Listesini Güncelle
    emit('update_online', online_users, broadcast=True)
    
    # 2. Özel Event Gönder: "Bu kullanıcının avatarı değişti, herkes yenilesin"
    emit('force_avatar_update', {
        'username': current_user.username,
        'new_avatar': data['avatar']
    }, broadcast=True)
    
    # 3. Hikayeleri de güncelle ki oradaki kafa resmi değişsin
    send_stories()

def send_stories():
    stories = Story.query.all()
    # User tablosundan en güncel avatarları alarak birleştir
    grouped = {}
    for s in stories:
        # Veritabanından o kullanıcının güncel fotosunu bul
        u = User.query.filter_by(username=s.username).first()
        real_avatar = u.avatar if u else s.avatar
        
        if s.username not in grouped: grouped[s.username] = []
        grouped[s.username].append({
            'id': s.id, 'username': s.username, 'avatar': real_avatar, 
            'content': s.content, 'type': s.media_type
        })
    emit('all_stories', grouped, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
