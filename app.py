from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra_secret_2026'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50MB Limit

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text) # Base64
    gender = db.Column(db.String(10))
    blocked_users = db.Column(db.Text, default="") # Virgülle ayrılmış kullanıcı adları

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50))
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20), default="text") # text, file, audio
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    content = db.Column(db.Text)
    media_type = db.Column(db.String(10)) # image/video
    views = db.Column(db.Text, default="") # Gördü listesi

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
        if User.query.filter_by(username=u).first(): return "Bu kullanıcı adı alınmış!", 400
        new_u = User(
            username=u,
            password=request.form.get('password'),
            gender=request.form.get('gender'),
            avatar=request.form.get('avatar_data')
        )
        db.session.add(new_u); db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    pw = request.form.get('password')
    if current_user.password == pw:
        db.session.delete(current_user)
        db.session.commit()
        logout_user()
        return redirect(url_for('register'))
    return "Şifre yanlış!", 403

# Diğer login/logout/chat rotaları standart...
@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

# --- SOCKET OLAYLARI ---
active_users = {}

@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        active_users[current_user.username] = {"avatar": current_user.avatar, "gender": current_user.gender}
        emit('update_users', active_users, broadcast=True)

@socketio.on('send_msg')
def handle_msg(data):
    # Engelleme kontrolü
    target_user = User.query.filter_by(username=data.get('to')).first()
    if target_user and current_user.username in (target_user.blocked_users or "").split(','):
        return # Engellenmişse gönderme
    
    m = Message(sender=current_user.username, content=data['content'], msg_type=data.get('type', 'text'), timestamp=datetime.now().strftime("%H:%M"))
    db.session.add(m); db.session.commit()
    emit('new_msg', {'id': m.id, 'sender': m.sender, 'content': m.content, 'type': m.msg_type, 'avatar': current_user.avatar, 'time': m.timestamp}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
