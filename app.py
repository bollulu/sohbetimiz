from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chat-ultra-v2026-final'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_final_v10.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100MB Limit

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=100 * 1024 * 1024)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

online_users = {} # {username: {avatar: str, sid: str}}

# --- VERİTABANI MODELLERİ ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(10)) # text, image, video, audio
    timestamp = db.Column(db.String(10))

with app.app_context():
    db.create_all()

# --- AUTH ---
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p, av = request.form.get('username'), request.form.get('password'), request.form.get('avatar_choice')
        if not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password=p, avatar=av))
            db.session.commit(); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

# --- SOKET OLAYLARI ---
@socketio.on('join')
def on_join(data):
    room = data.get('room', 'Genel')
    join_room(room)
    session['room'] = room
    online_users[current_user.username] = {'avatar': current_user.avatar, 'sid': request.sid}
    emit('user_list', {u: info['avatar'] for u, info in online_users.items()}, broadcast=True)
    
    msgs = Message.query.filter_by(room=room).order_by(Message.id.desc()).limit(50).all()
    history = [{'id': m.id, 'user': m.username, 'avatar': m.user_avatar, 'msg': m.content, 'type': m.msg_type, 'time': m.timestamp} for m in reversed(msgs)]
    emit('history', history)

@socketio.on('message')
def handle_msg(data):
    room = data.get('room', session.get('room', 'Genel'))
    now = datetime.now().strftime("%H:%M")
    msg = Message(username=current_user.username, user_avatar=current_user.avatar, content=data['msg'], msg_type=data.get('type', 'text'), room=room, timestamp=now)
    db.session.add(msg); db.session.commit()
    emit('message', {'id': msg.id, 'user': current_user.username, 'avatar': current_user.avatar, 'msg': data['msg'], 'type': msg.msg_type, 'time': now}, to=room)

@socketio.on('delete_msg')
def delete_msg(data):
    msg = db.session.get(Message, data.get('id'))
    if msg and msg.username == current_user.username:
        db.session.delete(msg); db.session.commit()
        emit('msg_deleted', {'id': data.get('id')}, broadcast=True)

# --- WEBRTC SIGNALLING ---
@socketio.on('call-user')
def call_user(data):
    target = online_users.get(data['to'])
    if target: emit('call-made', {'offer': data['offer'], 'from': current_user.username}, to=target['sid'])

@socketio.on('make-answer')
def make_answer(data):
    target = online_users.get(data['to'])
    if target: emit('answer-made', {'answer': data['answer'], 'from': current_user.username}, to=target['sid'])

@socketio.on('ice-candidate')
def ice_candidate(data):
    target = online_users.get(data['to'])
    if target: emit('ice-candidate', {'candidate': data['candidate'], 'from': current_user.username}, to=target['sid'])

@socketio.on('disconnect')
def on_disconnect():
    if current_user.is_authenticated and current_user.username in online_users:
        del online_users[current_user.username]
        emit('user_list', {u: info['avatar'] for u, info in online_users.items()}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
