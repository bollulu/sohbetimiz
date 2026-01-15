import eventlet
eventlet.monkey_patch(all=True)

import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chat-2026-final-v6'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_v6.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text, nullable=True, default='')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50), nullable=False, default='Genel')
    username = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.String(10))

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        if u and p and not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password=p)); db.session.commit()
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

active_users = {}

@socketio.on('join')
def on_join(data):
    room = data['room']
    if room.startswith("Özel") and data.get('password') != "1234":
        emit('error', {'msg': 'Hatalı Şifre!'}); return
    join_room(room)
    session['room'] = room
    
    # Geçmişi çekerken her kullanıcının güncel avatarını eşleştiriyoruz
    msgs = Message.query.filter_by(room=room).all()
    history = []
    for m in msgs:
        u = User.query.filter_by(username=m.username).first()
        history.append({
            'id': m.id, 'user': m.username, 'msg': m.content, 'time': m.timestamp,
            'avatar': u.avatar if u and u.avatar else ''
        })
    emit('history', history)
    
    active_users[request.sid] = {"name": current_user.username, "room": room, "avatar": current_user.avatar or ''}
    # Sadece o odadaki kullanıcıları gönder
    room_users = [u for u in active_users.values() if u['room'] == room]
    emit('user_list', room_users, to=room)

@socketio.on('message')
def handle_msg(data):
    room = session.get('room', 'Genel')
    now = datetime.now().strftime("%H:%M")
    new_m = Message(username=current_user.username, content=data['msg'], room=room, timestamp=now)
    db.session.add(new_m); db.session.commit()
    emit('message', {
        'id': new_m.id, 'user': current_user.username, 'msg': data['msg'], 
        'time': now, 'avatar': current_user.avatar or ''
    }, to=room)

@socketio.on('delete_message')
def delete_msg(data):
    msg = Message.query.get(data['id'])
    if msg and msg.username == current_user.username:
        room = msg.room
        db.session.delete(msg); db.session.commit()
        emit('remove_message', {'id': data['id']}, to=room)

@socketio.on('update_avatar')
def update_avatar(data):
    user = User.query.get(current_user.id)
    user.avatar = data['img']
    db.session.commit()
    if request.sid in active_users:
        active_users[request.sid]['avatar'] = data['img']
    emit('user_list', [u for u in active_users.values() if u['room'] == session.get('room')], to=session.get('room'))

@socketio.on('disconnect')
def disconnect():
    if request.sid in active_users:
        room = active_users[request.sid]['room']
        active_users.pop(request.sid)
        emit('user_list', [u for u in active_users.values() if u['room'] == room], to=room)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
