from gevent import monkey
monkey.patch_all()

import os, json
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra_final_v2026_pro'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 # 500MB
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text) 
    gender = db.Column(db.String(20))
    blocked_list = db.Column(db.Text, default="[]") # JSON listesi olarak tutulacak

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50))
    recipient = db.Column(db.String(50), default="global") # Madde 5: DM için
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20))
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    text_overlay = db.Column(db.Text, default="") # Madde 11: Hikaye yazısı
    media_type = db.Column(db.String(10)) 
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username')
        if User.query.filter_by(username=u).first(): return "Hata!", 400
        new_u = User(username=u, password=request.form.get('password'), gender=request.form.get('gender'), avatar=request.form.get('avatar_data'))
        db.session.add(new_u); db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

# Senin Orijinal Hesap Silme Fonksiyonun
@app.route('/delete_acc', methods=['POST'])
@login_required
def delete_acc():
    pw = request.form.get('password')
    if current_user.password == pw:
        db.session.delete(current_user); db.session.commit()
        logout_user(); return "OK"
    return "Hatalı Şifre", 400

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

online_users = {}

@socketio.on('connect')
def on_connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = {"avatar": current_user.avatar, "sid": request.sid}
        emit('update_online', online_users, broadcast=True)
        send_history()
        send_stories()

def send_history():
    msgs = Message.query.filter((Message.recipient == 'global') | (Message.recipient == current_user.username) | (Message.sender == current_user.username)).all()
    history = [{'id': m.id, 'sender': m.sender, 'recipient': m.recipient, 'content': m.content, 'type': m.msg_type, 'time': m.timestamp} for m in msgs]
    emit('load_history', history)

@socketio.on('send_msg')
def handle_msg(data):
    recipient = data.get('recipient', 'global')
    m = Message(sender=current_user.username, recipient=recipient, content=data['content'], msg_type=data['type'], timestamp=datetime.now().strftime("%H:%M"))
    db.session.add(m); db.session.commit()
    msg_data = {'id': m.id, 'sender': m.sender, 'recipient': m.recipient, 'content': m.content, 'type': m.msg_type, 'time': m.timestamp}
    if recipient == 'global':
        emit('new_msg', msg_data, broadcast=True)
    else:
        emit('new_msg', msg_data)
        if recipient in online_users:
            emit('new_msg', msg_data, room=online_users[recipient]['sid'])

@socketio.on('block_user')
def block_user(data):
    target = data['username']
    blocks = json.loads(current_user.blocked_list)
    if target not in blocks:
        blocks.append(target)
        current_user.blocked_list = json.dumps(blocks)
        db.session.commit()
        emit('user_blocked_status', {'blocked': blocks})

@socketio.on('delete_msg')
def delete_message(data):
    msg = db.session.get(Message, data['id'])
    if msg:
        db.session.delete(msg); db.session.commit()
        emit('msg_deleted', {'id': data['id']}, broadcast=True)

@socketio.on('update_avatar')
def update_avatar_func(data):
    current_user.avatar = data['avatar']
    db.session.commit()
    online_users[current_user.username]['avatar'] = data['avatar']
    emit('update_online', online_users, broadcast=True)
    emit('avatar_changed_globally', {'username': current_user.username, 'avatar': data['avatar']}, broadcast=True)

@socketio.on('add_story')
def add_story(data):
    s = Story(username=current_user.username, avatar=current_user.avatar, content=data['content'], text_overlay=data.get('text', ''), media_type=data['type'])
    db.session.add(s); db.session.commit()
    send_stories()

def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = []
        grouped[s.username].append({'id': s.id, 'username': s.username, 'avatar': s.avatar, 'content': s.content, 'text': s.text_overlay, 'type': s.media_type})
    emit('all_stories', grouped, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
