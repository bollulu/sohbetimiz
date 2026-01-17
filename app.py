from gevent import monkey
monkey.patch_all()
import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'full_system_2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'final_chat.db')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)
    blocked_users = db.Column(db.Text, default='[]')

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    admin = db.Column(db.String(50))
    password = db.Column(db.String(50), nullable=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100), index=True)
    sender = db.Column(db.String(50))
    sender_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    m_type = db.Column(db.String(20)) # text, image, video, audio
    timestamp = db.Column(db.DateTime, default=datetime.now)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.now)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'index'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated: return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user: login_user(user); return redirect(url_for('chat'))
    return "Hata! <a href='/'>Geri dön</a>"

@app.route('/register', methods=['POST'])
def register():
    u, p, g, a = request.form.get('username'), request.form.get('password'), request.form.get('gender'), request.form.get('avatar_data')
    if User.query.filter_by(username=u).first(): return "Kullanıcı mevcut."
    new_user = User(username=u, password=p, gender=g, avatar=a or "")
    db.session.add(new_user); db.session.commit(); login_user(new_user)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

# --- SOCKET EVENTS ---

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    msgs = Message.query.filter_by(room=room).order_by(Message.timestamp).all()
    history = [{'id': m.id, 'sender': m.sender, 'avatar': m.sender_avatar, 'content': m.content, 'type': m.m_type, 'time': m.timestamp.strftime('%H:%M')} for m in msgs]
    emit('load_history', history)
    
    users = User.query.all()
    emit('update_user_list', [{'username': u.username, 'avatar': u.avatar, 'is_me': (u.username == current_user.username)} for u in users], broadcast=True)
    emit('update_group_list', [{'name': g.name, 'admin': g.admin} for g in Group.query.all()])
    send_stories()

@socketio.on('send_message')
def handle_msg(data):
    msg = Message(room=data['room'], sender=current_user.username, sender_avatar=current_user.avatar, content=data['msg'], m_type=data['type'])
    db.session.add(msg); db.session.commit()
    emit('new_message', {'id': msg.id, 'sender': current_user.username, 'avatar': current_user.avatar, 'content': data['msg'], 'type': data['type'], 'time': datetime.now().strftime('%H:%M')}, room=data['room'])

@socketio.on('delete_message')
def delete_msg(data):
    m = db.session.get(Message, data['id'])
    if m and m.sender == current_user.username:
        db.session.delete(m); db.session.commit()
        emit('message_deleted', {'id': data['id']}, room=m.room)

@socketio.on('delete_group')
def delete_group(data):
    g = Group.query.filter_by(name=data['name']).first()
    if g and g.admin == current_user.username:
        Message.query.filter_by(room=g.name).delete()
        db.session.delete(g); db.session.commit()
        emit('update_group_list', [{'name': gr.name, 'admin': gr.admin} for gr in Group.query.all()], broadcast=True)

@socketio.on('create_group')
def create_group(data):
    if not Group.query.filter_by(name=data['name']).first():
        g = Group(name=data['name'], admin=current_user.username)
        db.session.add(g); db.session.commit()
        emit('update_group_list', [{'name': gr.name, 'admin': gr.admin} for gr in Group.query.all()], broadcast=True)

@socketio.on('update_profile')
def update_prof(data):
    if 'avatar' in data:
        current_user.avatar = data['avatar']
        # Tüm eski mesajlardaki ve hikayelerdeki resimleri güncelle
        Message.query.filter_by(sender=current_user.username).update({Message.sender_avatar: data['avatar']})
        Story.query.filter_by(username=current_user.username).update({Story.user_avatar: data['avatar']})
        db.session.commit()
        emit('user_info_updated', {'username': current_user.username, 'avatar': data['avatar']}, broadcast=True)

@socketio.on('post_story')
def post_story(data):
    s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['content'], media_type=data['type'])
    db.session.add(s); db.session.commit()
    send_stories()

def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'username': s.username, 'avatar': s.user_avatar, 'items': []}
        grouped[s.username]['items'].append({'id': s.id, 'content': s.content, 'type': s.media_type})
    emit('stories_update', grouped, broadcast=True)

# WebRTC (Görüntülü Arama)
@socketio.on('call_user')
def call_user(data):
    emit('call_received', {'from': current_user.username, 'offer': data['offer']}, room=data['to'])

@socketio.on('answer_call')
def answer_call(data):
    emit('call_answered', {'from': current_user.username, 'answer': data['answer']}, room=data['to'])

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
