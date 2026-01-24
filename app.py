from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ultra_secret_key_123')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

# Veritabanı Ayarı
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELLER ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    avatar = db.Column(db.Text) 
    background = db.Column(db.Text, default="") # İSTEK 7: Kalıcı arka plan
    blocked_users = db.Column(db.Text, default="") # İSTEK 6: Engellenenler (virgülle ayrılmış ID'ler)

class Room(db.Model): # İSTEK 4: Odalar
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=True) # Şifreli oda için
    creator = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50))
    recipient = db.Column(db.String(50), nullable=True) # Özel mesaj için (User ID veya Username)
    room = db.Column(db.String(50), default='general') # Oda ismi
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20), default='text') 
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- YARDIMCI FONKSİYONLAR ---
def is_blocked(user, target_username):
    target = User.query.filter_by(username=target_username).first()
    if not target: return False
    blocked_list = user.blocked_users.split(',') if user.blocked_users else []
    return str(target.id) in blocked_list

# --- ROUTES ---

@app.route('/')
def index():
    return redirect(url_for('chat'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('chat'))
        flash('Hatalı kullanıcı adı veya şifre!')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        hashed_pw = generate_password_hash(request.form['password'])
        new_user = User(
            username=request.form['username'],
            password=hashed_pw,
            avatar=request.form.get('avatar_data', '')
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        except:
            flash('Bu kullanıcı adı zaten alınmış!')
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    # Genel odadaki mesajları getir
    messages = Message.query.filter_by(room='general', recipient=None).order_by(Message.timestamp.asc()).all()
    rooms = Room.query.all()
    users = User.query.filter(User.username != current_user.username).all()
    return render_template('chat.html', messages=messages, rooms=rooms, users=users)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- SOCKET.IO ---

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        join_room('general') # Herkes varsayılan odaya katılır
        join_room(f"user_{current_user.id}") # Özel mesajlar için kişisel oda
        emit('user_status', {'username': current_user.username, 'status': 'online'}, broadcast=True)

@socketio.on('join_room_event')
def handle_join_room(data):
    room_name = data['room']
    # Şifre kontrolü gerekirse burada yapılır
    room = Room.query.filter_by(name=room_name).first()
    if room:
        if room.password and room.password != data.get('password'):
            emit('error_notice', {'msg': 'Yanlış Oda Şifresi'})
            return
        
        leave_room(data.get('previous_room', 'general'))
        join_room(room_name)
        
        # O odanın mesajlarını yükle
        msgs = Message.query.filter_by(room=room_name).order_by(Message.timestamp.asc()).all()
        history = [{'username': m.sender, 'content': m.content, 'type': m.msg_type, 'avatar': get_avatar(m.sender)} for m in msgs]
        emit('room_history', {'history': history, 'room': room_name})

@socketio.on('private_chat_start')
def handle_private_chat(data):
    target_username = data['username']
    # İSTEK 5: Özel mesaj geçmişini getir
    # (Ben gönderdim O aldı) VEYA (O gönderdi BEN aldım)
    msgs = Message.query.filter(
        ((Message.sender == current_user.username) & (Message.recipient == target_username)) |
        ((Message.sender == target_username) & (Message.recipient == current_user.username))
    ).order_by(Message.timestamp.asc()).all()
    
    history = [{'username': m.sender, 'content': m.content, 'type': m.msg_type, 'avatar': get_avatar(m.sender)} for m in msgs]
    emit('private_history', {'history': history, 'partner': target_username})

@socketio.on('send_msg')
def handle_msg(data):
    msg_type = data.get('type', 'text')
    content = data['content']
    room = data.get('room', 'general')
    recipient = data.get('recipient') # Özel mesaj ise dolu gelir

    # İSTEK 6: Engelleme Kontrolü
    if recipient:
        target_user = User.query.filter_by(username=recipient).first()
        if target_user:
            # Eğer hedef kişi beni engellemişse mesaj gitmez
            if is_blocked(target_user, current_user.username):
                emit('error_notice', {'msg': 'Bu kullanıcıya mesaj gönderemezsiniz.'})
                return

    new_msg = Message(
        sender=current_user.username,
        content=content,
        msg_type=msg_type,
        room=room if not recipient else None,
        recipient=recipient
    )
    db.session.add(new_msg)
    db.session.commit()
    
    msg_payload = {
        'id': new_msg.id,
        'username': new_msg.sender,
        'content': new_msg.content,
        'type': new_msg.msg_type,
        'avatar': current_user.avatar,
        'room': room,
        'recipient': recipient
    }

    if recipient:
        target = User.query.filter_by(username=recipient).first()
        if target:
            emit('receive_msg', msg_payload, room=f"user_{target.id}") # Hedefe
            emit('receive_msg', msg_payload, room=f"user_{current_user.id}") # Kendime
    else:
        emit('receive_msg', msg_payload, room=room)

@socketio.on('create_room')
def create_new_room(data):
    if Room.query.filter_by(name=data['name']).first():
        emit('error_notice', {'msg': 'Bu isimde oda zaten var!'})
        return
    
    new_room = Room(name=data['name'], creator=current_user.username, password=data.get('password'))
    db.session.add(new_room)
    db.session.commit()
    emit('new_room_created', {'name': new_room.name, 'private': bool(new_room.password)}, broadcast=True)

@socketio.on('update_profile')
def update_profile(data):
    # İSTEK 3: Avatar değişince her yerde değişsin
    if 'avatar' in data:
        current_user.avatar = data['avatar']
        emit('avatar_updated', {'username': current_user.username, 'avatar': data['avatar']}, broadcast=True)
    
    # İSTEK 7: Arka planı kaydet
    if 'background' in data:
        current_user.background = data['background']
    
    db.session.commit()

@socketio.on('block_user')
def block_user_action(data):
    target_username = data['username']
    target = User.query.filter_by(username=target_username).first()
    if target:
        blocked_list = current_user.blocked_users.split(',') if current_user.blocked_users else []
        if str(target.id) not in blocked_list:
            blocked_list.append(str(target.id))
            current_user.blocked_users = ",".join(blocked_list)
            db.session.commit()
            emit('error_notice', {'msg': f'{target_username} engellendi.'})

@socketio.on('add_story')
def add_story(data):
    new_story = Story(
        username=current_user.username,
        avatar=current_user.avatar,
        content=data['content'],
        media_type=data.get('type', 'image')
    )
    db.session.add(new_story)
    db.session.commit()
    # Hikaye eklendiğini herkese duyur
    emit('new_story_alert', {'username': current_user.username}, broadcast=True)

def get_avatar(username):
    u = User.query.filter_by(username=username).first()
    return u.avatar if u else ''

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, host='0.0.0.0', port=port)
