import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_secret_key_2026'
# Büyük dosya transferi için limitleri 100MB yapıyoruz
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'superapp.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=100 * 1024 * 1024)

# MODELLER
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)
    blocked_users = db.Column(db.Text, default='[]')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(80))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    type = db.Column(db.String(20)) # text, image, audio, video
    timestamp = db.Column(db.String(20))
    status = db.Column(db.String(20), default='sent')

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    content = db.Column(db.Text)
    type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'auth'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# YOLLAR (ROUTES)
@app.route('/')
def index():
    return redirect(url_for('auth'))

@app.route('/auth')
def auth():
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user:
        login_user(user, remember=True)
        return redirect(url_for('chat'))
    return "Hata: Kullanıcı adı veya şifre yanlış!"

@app.route('/register', methods=['POST'])
def register():
    u, p, g = request.form.get('username'), request.form.get('password'), request.form.get('gender')
    a = request.form.get('avatar_data') or ""
    if User.query.filter_by(username=u).first():
        return "Bu kullanıcı adı zaten mevcut."
    new_user = User(username=u, password=p, gender=g, avatar=a)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat():
    users = User.query.all()
    return render_template('chat.html', user=current_user, all_users=users)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth'))

# SOCKETIO ISLEMLERI
@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    msgs = Message.query.filter_by(room=room).all()
    history = [{'id': m.id, 'sender': m.sender, 'content': m.content, 'type': m.type, 'avatar': m.avatar, 'time': m.timestamp, 'status': m.status} for m in msgs]
    emit('load_history', history)

@socketio.on('message')
def handle_message(data):
    time_now = datetime.now().strftime("%H:%M")
    new_msg = Message(room=data['room'], sender=current_user.username, avatar=current_user.avatar, content=data['content'], type=data['type'], timestamp=time_now)
    db.session.add(new_msg)
    db.session.commit()
    data.update({'id': new_msg.id, 'sender': current_user.username, 'avatar': current_user.avatar, 'time': time_now, 'status': 'sent'})
    emit('message', data, room=data['room'])

@socketio.on('delete_msg')
def delete_msg(data):
    m = db.session.get(Message, data['id'])
    if m and m.sender == current_user.username:
        db.session.delete(m)
        db.session.commit()
        emit('msg_deleted', data['id'], room=m.room)

@socketio.on('mark_read')
def mark_read(data):
    m = db.session.get(Message, data['id'])
    if m and m.sender != current_user.username:
        m.status = 'read'
        db.session.commit()
        emit('status_updated', {'id': m.id, 'status': 'read'}, room=m.room)

@socketio.on('update_profile')
def update_profile(data):
    current_user.avatar = data['new_avatar']
    db.session.commit()
    emit('profile_synced', {'username': current_user.username, 'new_avatar': data['new_avatar']}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
