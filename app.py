from gevent import monkey
monkey.patch_all()
import os
import json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli_anahtar_v4_fix'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_database_v4.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)
    bg_image = db.Column(db.Text, default="") 
    blocked_users = db.Column(db.Text, default='[]') 

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(50), nullable=True)
    admin = db.Column(db.String(50))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100), index=True)
    sender = db.Column(db.String(50))
    sender_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    m_type = db.Column(db.String(20)) 
    timestamp = db.Column(db.DateTime, default=datetime.now)
    status = db.Column(db.String(20), default='sent')

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    music_data = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    viewers = db.Column(db.Text, default='[]')

class Music(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    data = db.Column(db.Text)
    uploader = db.Column(db.String(50))

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'index'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- ROTALAR ---
@app.route('/')
def index():
    if current_user.is_authenticated: return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    user = User.query.filter_by(username=username, password=password).first()
    if user: login_user(user); return redirect(url_for('chat'))
    return "Hatalı giriş. <a href='/'>Geri dön</a>"

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')
    gender = request.form.get('gender')
    avatar_data = request.form.get('avatar_data')
    if User.query.filter_by(username=username).first(): return "Kullanıcı var. <a href='/'>Geri dön</a>"
    if not avatar_data: avatar_data = "https://cdn-icons-png.flaticon.com/512/149/149071.png"
    
    # Yeni kullanıcıda blocked_users boş liste olarak başlar
    new_user = User(username=username, password=password, gender=gender, avatar=avatar_data, blocked_users='[]', bg_image="")
    db.session.add(new_user); db.session.commit(); login_user(new_user)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat():
    # Eski kullanıcılarda blocked_users NULL ise düzelt
    if current_user.blocked_users is None:
        current_user.blocked_users = '[]'
        db.session.commit()
    return render_template('chat.html', user=current_user)

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('index'))

# --- SOCKET ---
@socketio.on('connect')
def on_connect():
    groups = Group.query.all()
    group_list = [{'name': g.name, 'protected': bool(g.password)} for g in groups]
    emit('update_group_list', group_list)

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    msgs = Message.query.filter_by(room=room).order_by(Message.timestamp).all()
    history = []
    
    # Hata koruması: JSON parse hatası olursa boş liste kullan
    try:
        blocked = json.loads(current_user.blocked_users)
    except:
        blocked = []

    for m in msgs:
        if m.sender not in blocked:
            history.append({
                'id': m.id, 'sender': m.sender, 'avatar': m.sender_avatar,
                'content': m.content, 'type': m.m_type, 
                'time': m.timestamp.strftime('%H:%M'), 'status': 'read'
            })
    emit('load_history', history)
    
    users = User.query.all()
    user_list = [{'username': u.username, 'avatar': u.avatar, 'is_me': (u.username == current_user.username)} for u in users]
    emit('update_user_list', user_list, broadcast=True)

@socketio.on('send_message')
def handle_msg(data):
    msg = Message(room=data['room'], sender=current_user.username, sender_avatar=current_user.avatar, content=data['msg'], m_type=data['type'])
    db.session.add(msg); db.session.commit()
    emit('new_message', {
        'id': msg.id, 'sender': current_user.username, 'avatar': current_user.avatar,
        'content': data['msg'], 'type': data['type'], 
        'time': datetime.now().strftime('%H:%M'), 'status': 'sent'
    }, room=data['room'])

@socketio.on('delete_message')
def delete_msg(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.sender == current_user.username:
        db.session.delete(msg); db.session.commit()
        emit('message_deleted', {'id': data['id']}, room=msg.room)

@socketio.on('delete_account_confirm')
def delete_acc(data):
    if current_user.password == data.get('password'):
        u_name = current_user.username
        Message.query.filter_by(sender=u_name).delete()
        Story.query.filter_by(username=u_name).delete()
        Music.query.filter_by(uploader=u_name).delete()
        db.session.delete(current_user); db.session.commit()
        logout_user()
        emit('account_deleted_success', {'url': url_for('index')})
    else:
        emit('account_deleted_error', {'msg': 'Şifre Yanlış!'})

@socketio.on('create_group')
def create_group(data):
    if not Group.query.filter_by(name=data['name']).first():
        g = Group(name=data['name'], password=data.get('password'), admin=current_user.username)
        db.session.add(g); db.session.commit()
        groups = Group.query.all()
        emit('update_group_list', [{'name': grp.name, 'protected': bool(grp.password)} for grp in groups], broadcast=True)

@socketio.on('update_profile')
def update_prof(data):
    if 'avatar' in data: current_user.avatar = data['avatar']
    if 'bg' in data: current_user.bg_image = data['bg']
    if 'reset_bg' in data: current_user.bg_image = ""
    db.session.commit()
    emit('profile_updated', {'username': current_user.username, 'avatar': current_user.avatar}, broadcast=True)

@socketio.on('block_user')
def block_user(data):
    try: blocked = json.loads(current_user.blocked_users)
    except: blocked = []
    
    target = data['username']
    if target not in blocked: blocked.append(target)
    else: blocked.remove(target)
    current_user.blocked_users = json.dumps(blocked)
    db.session.commit()
    emit('block_updated', {'blocked_list': blocked})

@socketio.on('post_story')
def post_story(data):
    s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['content'], media_type=data['type'], music_data=data.get('music'))
    db.session.add(s); db.session.commit()
    broadcast_stories()

@socketio.on('get_stories')
def get_stories(): broadcast_stories()

def broadcast_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'username': s.username, 'avatar': s.user_avatar, 'items': []}
        try: viewers = json.loads(s.viewers)
        except: viewers = []
        grouped[s.username]['items'].append({'id': s.id, 'content': s.content, 'type': s.media_type, 'music': s.music_data, 'viewers': viewers, 'seen_by_me': (current_user.username in viewers)})
    emit('stories_update', grouped, broadcast=True)

@socketio.on('story_seen')
def story_seen(data):
    s = db.session.get(Story, data['id'])
    if s:
        try: v = json.loads(s.viewers)
        except: v = []
        if current_user.username not in v:
            v.append(current_user.username); s.viewers = json.dumps(v); db.session.commit()

@socketio.on('delete_story')
def del_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username: db.session.delete(s); db.session.commit(); broadcast_stories()

@socketio.on('add_music')
def add_music(data):
    db.session.add(Music(title=data['name'], data=data['content'], uploader=current_user.username)); db.session.commit(); send_music()

@socketio.on('get_music')
def get_music(): send_music()

def send_music():
    ms = Music.query.all()
    emit('music_list', [{'id': m.id, 'title': m.title, 'src': m.data, 'uploader': m.uploader} for m in ms], broadcast=True)

@socketio.on('delete_music')
def del_music(data):
    m = db.session.get(Music, data['id'])
    if m and m.uploader == current_user.username: db.session.delete(m); db.session.commit(); send_music()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
