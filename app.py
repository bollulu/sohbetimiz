import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sohbetimiz-gizli-anahtar-2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Klasörleri oluştur
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
login_manager = LoginManager(app)
login_manager.login_view = 'auth'

# --- VERİTABANI MODELLERİ ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    gender = db.Column(db.String(20))
    avatar = db.Column(db.String(200), default='default.png')
    blocked_users = db.Column(db.Text, default='') # Virgülle ayrılmış ID'ler

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender_id = db.Column(db.Integer)
    sender_name = db.Column(db.String(80))
    sender_avatar = db.Column(db.String(200))
    content = db.Column(db.Text)
    m_type = db.Column(db.String(20), default='text') # text, image, video, audio
    timestamp = db.Column(db.DateTime, default=datetime.now)
    is_read = db.Column(db.Boolean, default=False)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    media = db.Column(db.String(200))
    m_type = db.Column(db.String(20)) # image, video
    music = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    views = db.Column(db.Text, default='') # İzleyenlerin ID'leri

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    members = db.Column(db.Text) # Virgülle ayrılmış ID'ler

# Tabloları oluştur (Render Hatası Çözümü)
with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROTALAR ---
@app.route('/')
def index():
    return redirect(url_for('chat')) if current_user.is_authenticated else redirect(url_for('auth'))

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')
        
        if action == 'register':
            if User.query.filter_by(username=username).first():
                flash('Bu kullanıcı adı alınmış.')
                return redirect(url_for('auth'))
            
            avatar_file = request.files.get('avatar')
            avatar_name = 'default.png'
            if avatar_file:
                avatar_name = secure_filename(f"v_{username}_{avatar_file.filename}")
                avatar_file.save(os.path.join(app.config['UPLOAD_FOLDER'], avatar_name))

            new_user = User(
                username=username, 
                password=generate_password_hash(password),
                gender=request.form.get('gender'),
                avatar=avatar_name
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Kayıt başarılı! Giriş yapabilirsiniz.')
            
        elif action == 'login':
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('chat'))
            flash('Hatalı giriş!')
    return render_template('auth.html')

@app.route('/chat')
@login_required
def chat():
    users = User.query.all()
    groups = Group.query.all()
    stories = Story.query.order_by(Story.timestamp.desc()).all()
    return render_template('chat.html', users=users, groups=groups, stories=stories)

@app.route('/music')
@login_required
def music_page():
    return render_template('music.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth'))

# --- SOCKET OLAYLARI ---
@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    # Geçmiş mesajlar
    msgs = Message.query.filter_by(room=room).order_by(Message.timestamp.asc()).all()
    history = [{
        'id': m.id, 'sender': m.sender_name, 'avatar': m.sender_avatar, 
        'text': m.content, 'type': m.m_type, 'read': m.is_read,
        'time': m.timestamp.strftime('%H:%M'), 'mine': m.sender_id == current_user.id
    } for m in msgs]
    emit('load_history', history)

@socketio.on('send_msg')
def handle_msg(data):
    room = data['room']
    new_m = Message(
        room=room, sender_id=current_user.id, sender_name=current_user.username,
        sender_avatar=current_user.avatar, content=data['text'], m_type=data['type']
    )
    db.session.add(new_m)
    db.session.commit()
    emit('receive_msg', {
        'id': new_m.id, 'sender': current_user.username, 'avatar': current_user.avatar,
        'text': data['text'], 'type': data['type'], 'read': False, 'time': datetime.now().strftime('%H:%M')
    }, room=room)

@socketio.on('delete_msg')
def delete_msg(data):
    m = Message.query.get(data['id'])
    if m and m.sender_id == current_user.id:
        db.session.delete(m)
        db.session.commit()
        emit('msg_deleted', {'id': data['id']}, room=m.room)

if __name__ == '__main__':
    socketio.run(app)
