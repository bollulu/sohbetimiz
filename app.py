from gevent import monkey
monkey.patch_all()
import os, json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sohbetimiz_v3_2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)
    blocked_users = db.Column(db.Text, default='[]') # JSON list

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(50), nullable=True) # Grup Şifresi
    admin = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(50))
    sender_ava = db.Column(db.Text)
    content = db.Column(db.Text)
    m_type = db.Column(db.String(20), default='text')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(10)) # image/video
    audio_data = db.Column(db.Text, nullable=True)
    viewers = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Music(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    data = db.Column(db.Text)
    owner = db.Column(db.String(50))

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('auth.html') if not current_user.is_authenticated else redirect(url_for('chat'))

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user: login_user(user); return redirect(url_for('chat'))
    return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    u, p, a = request.form.get('username'), request.form.get('password'), request.form.get('avatar_data')
    if not User.query.filter_by(username=u).first():
        new_u = User(username=u, password=p, avatar=a)
        db.session.add(new_u); db.session.commit(); login_user(new_u)
    return redirect(url_for('chat'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user = db.session.get(User, current_user.id)
    db.session.delete(user); db.session.commit()
    logout_user(); return redirect(url_for('index'))

@app.route('/chat')
@login_required
def chat():
    all_users = User.query.all()
    all_groups = Group.query.all()
    all_musics = Music.query.all()
    return render_template('chat.html', user=current_user, all_users=all_users, groups=all_groups, musics=all_musics)

# --- SOCKET EVENTS ---
online_users = {}

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = current_user.avatar
        emit('online_list', online_users, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated and current_user.username in online_users:
        del online_users[current_user.username]
        emit('online_list', online_users, broadcast=True)

@socketio.on('join')
def on_join(data):
    join_room(data['room'])
    msgs = Message.query.filter_by(room=data['room']).order_by(Message.timestamp.asc()).all()
    emit('load_history', [{'sender':m.sender, 'ava':m.sender_ava, 'content':m.content, 'type':m.m_type} for m in msgs])

@socketio.on('send_message')
def handle_msg(data):
    # Engel kontrolü
    target_user = User.query.filter_by(username=data.get('target')).first()
    if target_user:
        blocks = json.loads(target_user.blocked_users)
        if current_user.username in blocks: return # Mesajı gönderme
    
    new_m = Message(room=data['room'], sender=current_user.username, sender_ava=current_user.avatar, content=data['msg'], m_type=data.get('type','text'))
    db.session.add(new_m); db.session.commit()
    emit('new_message', {'sender':current_user.username, 'ava':current_user.avatar, 'content':data['msg'], 'type':data.get('type','text'), 'room':data['room']}, room=data['room'])

@socketio.on('create_group')
def create_group(data):
    if not Group.query.filter_by(name=data['name']).first():
        g = Group(name=data['name'], password=data.get('password'), admin=current_user.username)
        db.session.add(g); db.session.commit()
        emit('refresh_groups', broadcast=True)

@socketio.on('delete_group')
def delete_group(data):
    g = Group.query.filter_by(name=data['name'], admin=current_user.username).first()
    if g: db.session.delete(g); db.session.commit(); emit('refresh_groups', broadcast=True)

@socketio.on('block_user')
def block(data):
    user = db.session.get(User, current_user.id)
    blocks = json.loads(user.blocked_users)
    if data['target'] not in blocks:
        blocks.append(data['target'])
        user.blocked_users = json.dumps(blocks)
        db.session.commit()
    emit('block_status', {'blocked': True})

@socketio.on('unblock_user')
def unblock(data):
    user = db.session.get(User, current_user.id)
    blocks = json.loads(user.blocked_users)
    if data['target'] in blocks:
        blocks.remove(data['target'])
        user.blocked_users = json.dumps(blocks)
        db.session.commit()
    emit('block_status', {'blocked': False})

@socketio.on('post_story')
def handle_story(data):
    s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['content'], media_type=data['type'], audio_data=data.get('audio'))
    db.session.add(s); db.session.commit()
    emit('refresh_stories', broadcast=True)

@socketio.on('view_story')
def view_s(data):
    s = db.session.get(Story, data['id'])
    if s and s.username != current_user.username:
        v = json.loads(s.viewers)
        if current_user.username not in v:
            v.append(current_user.username); s.viewers = json.dumps(v); db.session.commit()
            emit('refresh_stories', broadcast=True)

@socketio.on('delete_story')
def del_s(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        db.session.delete(s); db.session.commit(); emit('refresh_stories', broadcast=True)

@socketio.on('add_music')
def add_m(data):
    m = Music(title=data['title'], data=data['data'], owner=current_user.username)
    db.session.add(m); db.session.commit(); emit('refresh_music', broadcast=True)

@socketio.on('delete_music')
def del_m(data):
    m = db.session.get(Music, data['id'])
    if m and m.owner == current_user.username:
        db.session.delete(m); db.session.commit(); emit('refresh_music', broadcast=True)

@socketio.on('update_avatar')
def up_ava(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    db.session.commit()
    emit('refresh_all', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
