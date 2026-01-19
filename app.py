from gevent import monkey
monkey.patch_all()
import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_secret_key_2026'
# Kalıcı veritabanı dosyası
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_v2.db')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)
    blocked_users = db.Column(db.Text, default='[]') 

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100)) # Genel, Ozel_ID veya Grup_ID
    sender = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) # text, image, video, audio
    timestamp = db.Column(db.String(20))
    status = db.Column(db.String(10), default='sent')

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    audio_data = db.Column(db.Text) # Müzikli hikaye için
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')
    duration = db.Column(db.Integer, default=30) 

class Music(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    src = db.Column(db.Text)
    uploader = db.Column(db.String(50))

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    members = db.Column(db.Text) # JSON listesi
    created_by = db.Column(db.String(50))

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'auth'
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

# --- ROTALAR ---
@app.route('/', methods=['GET', 'POST'])
def auth():
    if current_user.is_authenticated: return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login_proc():
    user = User.query.filter_by(username=request.form.get('username')).first()
    if user and user.password == request.form.get('password'):
        login_user(user)
        return redirect(url_for('chat'))
    return redirect(url_for('auth'))

@app.route('/register', methods=['POST'])
def register_proc():
    u = request.form.get('username')
    if User.query.filter_by(username=u).first(): return redirect(url_for('auth'))
    
    ava = request.form.get('avatar_data')
    # Avatar yoksa varsayılan
    if not ava or len(ava) < 100:
        gender = request.form.get('gender')
        if gender == 'Erkek': ava = "https://cdn-icons-png.flaticon.com/512/236/236831.png"
        else: ava = "https://cdn-icons-png.flaticon.com/512/236/236832.png"

    new_user = User(username=u, password=request.form.get('password'), gender=request.form.get('gender'), avatar=ava)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth'))

# --- SOCKET ---
@socketio.on('connect')
def on_connect():
    emit('update_user_list', get_all_users(), broadcast=True)

@socketio.on('join_room')
def on_join_room(data):
    room = data['room']
    join_room(room)
    msgs = Message.query.filter_by(room=room).all()
    history = []
    blocked = json.loads(current_user.blocked_users)
    for m in msgs:
        if m.sender not in blocked:
            history.append({
                'id':m.id, 'user':m.sender, 'ava':m.avatar, 
                'msg':m.content, 'type':m.msg_type, 
                'time':m.timestamp, 'status':m.status
            })
    emit('history', history)
    send_stories()

@socketio.on('send_message')
def on_send(data):
    now = datetime.now().strftime("%H:%M")
    msg = Message(room=data['room'], sender=current_user.username, avatar=current_user.avatar, content=data['msg'], msg_type=data['type'], timestamp=now)
    db.session.add(msg); db.session.commit()
    
    # Okundu simülasyonu
    socketio.start_background_task(mark_read_later, msg.id, data['room'])
    
    emit('message', {
        'id':msg.id, 'room':data['room'], 'user':current_user.username, 
        'ava':current_user.avatar, 'msg':data['msg'], 'type':data['type'], 
        'time':now, 'status':'sent'
    }, to=data['room'])

def mark_read_later(msg_id, room):
    socketio.sleep(1.5)
    with app.app_context():
        m = db.session.get(Message, msg_id)
        if m:
            m.status = 'read'
            db.session.commit()
            socketio.emit('msg_status_update', {'id':m.id, 'status':'read'}, to=room)

@socketio.on('delete_message')
def delete_message(data):
    m = db.session.get(Message, data['id'])
    if m and m.sender == current_user.username:
        db.session.delete(m); db.session.commit()
        emit('message_deleted', {'id':data['id']}, to=m.room)

@socketio.on('create_group')
def create_group(data):
    members = data['members'] # liste
    members.append(current_user.username)
    name = data['name']
    new_grp = Group(name=name, members=json.dumps(members), created_by=current_user.username)
    db.session.add(new_grp); db.session.commit()
    emit('group_created', {'id':new_grp.id, 'name':name, 'members':members}, broadcast=True)

@socketio.on('block_user')
def block_user(data):
    target = data['username']
    blocked = json.loads(current_user.blocked_users)
    if target not in blocked:
        blocked.append(target)
        current_user.blocked_users = json.dumps(blocked)
        db.session.commit()
        emit('notification', {'msg': f'{target} engellendi.'})

@socketio.on('update_profile')
def update_profile(data):
    current_user.avatar = data['avatar']
    # Geçmiş verileri güncelle
    Message.query.filter_by(sender=current_user.username).update({'avatar':data['avatar']})
    Story.query.filter_by(sender=current_user.username).update({'user_avatar':data['avatar']}) # Modelde sender değil username
    db.session.commit()
    emit('update_user_list', get_all_users(), broadcast=True)

# --- Müzik ---
@socketio.on('add_music')
def add_music(data):
    m = Music(title=data['name'], src=data['src'], uploader=current_user.username)
    db.session.add(m); db.session.commit()
    send_music_list()

@socketio.on('get_music')
def get_music_list_evt(): send_music_list()

def send_music_list():
    musics = Music.query.all()
    data = [{'id':m.id, 'title':m.title, 'src':m.src} for m in musics]
    emit('music_list', data)

# --- Hikaye ---
@socketio.on('add_story')
def add_story(data):
    # Eğer müzik veya video uzunsa duration client'tan gelir, yoksa 30
    dur = data.get('duration', 30)
    s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['content'], audio_data=data.get('music'), media_type=data['type'], duration=dur)
    db.session.add(s); db.session.commit()
    send_stories()

@socketio.on('view_story')
def view_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username != current_user.username:
        v = json.loads(s.viewers)
        if current_user.username not in v:
            v.append(current_user.username)
            s.viewers = json.dumps(v)
            db.session.commit()

@socketio.on('delete_story')
def del_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        db.session.delete(s); db.session.commit()
        send_stories()

def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar':s.user_avatar, 'items':[]}
        grouped[s.username]['items'].append({
            'id':s.id, 'content':s.content, 'music':s.audio_data, 
            'type':s.media_type, 'duration':s.duration, 
            'viewers':json.loads(s.viewers), 'can_delete': (s.username == current_user.username)
        })
    socketio.emit('story_list', grouped)

# --- Video Arama (WebRTC Signal) ---
@socketio.on('call_signal')
def call_signal(data):
    emit('call_signal_receive', data, broadcast=True)

def get_all_users():
    return [{'username':u.username, 'avatar':u.avatar} for u in User.query.all()]

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
