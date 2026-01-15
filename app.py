from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whatsapp-final-2026-complete'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'ultimate_v20.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=100 * 1024 * 1024)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

online_users = {}

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
    is_read = db.Column(db.Boolean, default=False)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

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

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'Genel')
    join_room(room)
    session['room'] = room
    online_users[current_user.username] = current_user.avatar
    emit('user_list', online_users, broadcast=True)
    
    msgs = Message.query.filter_by(room=room).order_by(Message.id.desc()).limit(50).all()
    history = [{'id':m.id, 'user':m.username, 'avatar':m.user_avatar, 'msg':m.content, 'type':m.msg_type, 'time':m.timestamp, 'read':m.is_read} for m in reversed(msgs)]
    emit('history', history)
    send_stories()

def send_stories():
    stories = Story.query.order_by(Story.created_at.asc()).all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar': s.user_avatar, 'imgs': []}
        grouped[s.username]['imgs'].append(s.content)
    emit('story_list', grouped)

@socketio.on('message')
def handle_msg(data):
    room = data.get('room', session.get('room', 'Genel'))
    now = datetime.now().strftime("%H:%M")
    msg = Message(username=current_user.username, user_avatar=current_user.avatar, content=data['msg'], msg_type=data.get('type','text'), room=room, timestamp=now)
    db.session.add(msg); db.session.commit()
    emit('message', {'id':msg.id, 'user':current_user.username, 'avatar':current_user.avatar, 'msg':data['msg'], 'type':msg.msg_type, 'time':now, 'read':False}, to=room)

@socketio.on('mark_read')
def mark_read(data):
    msg = db.session.get(Message, data['id'])
    if msg:
        msg.is_read = True; db.session.commit()
        emit('msg_read_status', {'id': data['id']}, room=session.get('room'), include_self=False)

@socketio.on('upload_story')
def handle_story(data):
    db.session.add(Story(username=current_user.username, user_avatar=current_user.avatar, content=data['img']))
    db.session.commit()
    send_stories()

@socketio.on('update_avatar')
def change_av(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['img']
    db.session.commit()
    online_users[user.username] = data['img']
    emit('user_list', online_users, broadcast=True)

@socketio.on('delete_msg')
def delete_msg(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.username == current_user.username:
        db.session.delete(msg); db.session.commit()
        emit('msg_deleted', {'id': data['id']}, room=session.get('room'))

@socketio.on('disconnect')
def on_disconnect():
    if current_user.is_authenticated and current_user.username in online_users:
        del online_users[current_user.username]
        emit('user_list', online_users, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
