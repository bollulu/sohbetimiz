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
app.config['SECRET_KEY'] = 'ultimate_2026_fixed'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'final_v3.db')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)
    bg_image = db.Column(db.Text, default="")
    blocked_users = db.Column(db.Text, default='[]') # JSON Liste

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
    m_type = db.Column(db.String(20)) 
    status = db.Column(db.String(20), default='sent') # sent / read
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

# --- ROTALAR ---
@app.route('/')
def index():
    if current_user.is_authenticated: return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user: login_user(user); return redirect(url_for('chat'))
    return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    u, p, a = request.form.get('username'), request.form.get('password'), request.form.get('avatar_data')
    if User.query.filter_by(username=u).first(): return "Mevcut!"
    new_user = User(username=u, password=p, avatar=a or "")
    db.session.add(new_user); db.session.commit(); login_user(new_user)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

# --- SOCKET OLAYLARI ---
@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    # Mesajları okundu yap (Çift Tık)
    Message.query.filter_by(room=room).filter(Message.sender != current_user.username).update({Message.status: 'read'})
    db.session.commit()
    
    msgs = Message.query.filter_by(room=room).order_by(Message.timestamp).all()
    history = [{
        'id': m.id, 'sender': m.sender, 'avatar': m.sender_avatar, 
        'content': m.content, 'type': m.m_type, 'status': m.status,
        'time': m.timestamp.strftime('%d/%m %H:%M')
    } for m in msgs]
    emit('load_history', history)
    
    # Kullanıcı ve Grup Listesi
    emit('update_user_list', [{'username': u.username, 'avatar': u.avatar, 'is_me': (u.username == current_user.username)} for u in User.query.all()], broadcast=True)
    emit('update_group_list', [{'name': g.name, 'admin': g.admin, 'has_pass': bool(g.password)} for g in Group.query.all()])
    send_stories()

@socketio.on('send_message')
def handle_msg(data):
    # Engelleme kontrolü
    target_user = User.query.filter_by(username=data['room']).first()
    if target_user:
        blocked = json.loads(target_user.blocked_users)
        if current_user.username in blocked: return # Mesaj gitmez
        
    msg = Message(room=data['room'], sender=current_user.username, sender_avatar=current_user.avatar, content=data['msg'], m_type=data['type'])
    db.session.add(msg); db.session.commit()
    emit('new_message', {
        'id': msg.id, 'sender': current_user.username, 'avatar': current_user.avatar, 
        'content': data['msg'], 'type': data['type'], 'status': 'sent',
        'time': datetime.now().strftime('%d/%m %H:%M')
    }, room=data['room'])

@socketio.on('delete_message')
def delete_msg(data):
    m = db.session.get(Message, data['id'])
    if m and m.sender == current_user.username:
        db.session.delete(m); db.session.commit()
        emit('message_deleted', {'id': data['id']}, room=m.room)

@socketio.on('block_user')
def block_user(data):
    blocked = json.loads(current_user.blocked_users)
    if data['username'] not in blocked:
        blocked.append(data['username'])
        current_user.blocked_users = json.dumps(blocked)
        db.session.commit()
        emit('user_blocked_success', {'username': data['username']})

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

@socketio.on('update_profile')
def update_prof(data):
    if 'avatar' in data:
        current_user.avatar = data['avatar']
        Message.query.filter_by(sender=current_user.username).update({Message.sender_avatar: data['avatar']})
        Story.query.filter_by(username=current_user.username).update({Story.user_avatar: data['avatar']})
    if 'bg' in data: current_user.bg_image = data['bg']
    db.session.commit()
    emit('user_info_updated', {'username': current_user.username, 'avatar': current_user.avatar, 'bg': current_user.bg_image}, broadcast=True)

@socketio.on('create_group')
def create_group(data):
    if not Group.query.filter_by(name=data['name']).first():
        g = Group(name=data['name'], admin=current_user.username, password=data.get('password'))
        db.session.add(g); db.session.commit()
        emit('update_group_list', [{'name': gr.name, 'admin': gr.admin, 'has_pass': bool(gr.password)} for gr in Group.query.all()], broadcast=True)

@socketio.on('factory_reset')
def factory_reset():
    Message.query.filter_by(sender=current_user.username).delete()
    db.session.commit()
    emit('reload_page')

# WebRTC (Görüntülü Arama)
@socketio.on('call_user')
def call_user(data):
    emit('call_received', {'from': current_user.username, 'offer': data['offer']}, room=data['to'])

@socketio.on('answer_call')
def answer_call(data):
    emit('call_answered', {'from': current_user.username, 'answer': data['answer']}, room=data['to'])

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
