from gevent import monkey
monkey.patch_all()  # Websocket için en üstte olmalı

import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ultra_secret_key_123')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB Sınırı

# --- VERİTABANI AYARI (Render PostgreSQL Uyumlu) ---
# Eğer Render'da DATABASE_URL varsa onu kullanır, yoksa yerel sqlite oluşturur.
db_url = os.environ.get('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url or 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# Render'da gunicorn ile çalışırken async_mode='gevent' şart
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    avatar = db.Column(db.Text) 
    gender = db.Column(db.String(20))
    blocked_list = db.Column(db.Text, default="") 

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20), default='text') # text, image, audio, video
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(20)) # image, video
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- YOLLAR (ROUTES) ---
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
            avatar=request.form.get('avatar_data', ''),
            gender=request.form.get('gender', 'Belirtilmemiş')
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
    messages = Message.query.order_by(Message.timestamp.asc()).all()
    return render_template('chat.html', messages=messages)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- SOCKET.IO ETKİNLİKLERİ ---
online_users = {}

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = {
            'avatar': current_user.avatar,
            'gender': current_user.gender
        }
        emit('update_online', online_users, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        online_users.pop(current_user.username, None)
        emit('update_online', online_users, broadcast=True)

@socketio.on('send_msg')
def handle_msg(data):
    new_msg = Message(
        username=current_user.username,
        content=data['content'],
        msg_type=data.get('type', 'text')
    )
    db.session.add(new_msg)
    db.session.commit()
    
    emit('receive_msg', {
        'id': new_msg.id,
        'username': new_msg.username,
        'content': new_msg.content,
        'type': new_msg.msg_type,
        'avatar': current_user.avatar
    }, broadcast=True)

@socketio.on('delete_msg')
def delete_message(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.username == current_user.username: # Sadece kendi mesajını silebilir
        db.session.delete(msg)
        db.session.commit()
        emit('msg_deleted', {'id': data['id']}, broadcast=True)

# Veritabanını oluştur
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    # Render portunu otomatik algıla
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, host='0.0.0.0', port=port)
