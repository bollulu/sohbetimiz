from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'süper-sohbet-final-2026'
basedir = os.path.abspath(os.path.dirname(__file__))
# Temiz bir veritabanı başlangıcı için dosya ismini güncelledik
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'whatsapp_v3.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# Ses kayıtları ve HD dosyalar için 100MB limit
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=100 * 1024 * 1024)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

online_users = {}

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text, nullable=True, default='https://www.w3schools.com/howto/img_avatar.png')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50), default='Genel')
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text) # Mesaj anındaki avatarı saklamak için
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(10), default='text') # text, image, video, audio
    timestamp = db.Column(db.String(10))
    status = db.Column(db.String(10), default='sent') # sent, read

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- ROUTER ---
@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user)
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        if u and p and not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password=p))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@app.route('/live')
@login_required
def live(): return render_template('live.html', user=current_user)

@app.route('/logout')
def logout():
    if current_user.is_authenticated and current_user.username in online_users:
        del online_users[current_user.username]
    logout_user()
    return redirect(url_for('login'))

# --- SOCKET.IO ---

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'Genel')
    join_room(room)
    session['room'] = room
    online_users[current_user.username] = current_user.avatar
    emit('user_list', online_users, broadcast=True)
    
    msgs = Message.query.filter_by(room=room).order_by(Message.id.desc()).limit(40).all()
    history = [{
        'id': m.id, 
        'user': m.username, 
        'avatar': m.user_avatar, 
        'msg': m.content, 
        'type': m.msg_type, 
        'time': m.timestamp,
        'status': m.status
    } for m in reversed(msgs)]
    emit('history', history)

@socketio.on('message')
def handle_msg(data):
    room = session.get('room', 'Genel')
    now = datetime.now().strftime("%H:%M")
    m_type = data.get('type', 'text')
    
    msg = Message(
        username=current_user.username, 
        user_avatar=current_user.avatar,
        content=data['msg'], 
        msg_type=m_type, 
        room=room, 
        timestamp=now,
        status='sent'
    )
    db.session.add(msg)
    db.session.commit()
    
    emit('message', {
        'id': msg.id, 
        'user': current_user.username, 
        'avatar': current_user.avatar,
        'msg': data['msg'], 
        'type': m_type, 
        'time': now,
        'status': '
