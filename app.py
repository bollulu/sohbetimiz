import eventlet
eventlet.monkey_patch()  # Render hatasını çözen kritik satır

import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

# Uygulama ve Veritabanı Yapılandırması
app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-chat-key-2026'

# Render/Linux sunucuları için veritabanı yolu düzeltmesi
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
# Render üzerinde stabilite için async_mode='eventlet'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Modeller
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text, nullable=True, default='')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(10), default='text')
    timestamp = db.Column(db.String(10))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Rotalar (Routes)
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname = request.form.get('username')
        pwd = request.form.get('password')
        if not User.query.filter_by(username=uname).first():
            new_user = User(username=uname, password=pwd)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user)
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/chat')
@login_required
def chat():
    all_messages = Message.query.all()
    history = []
    for m in all_messages:
        sender = User.query.filter_by(username=m.username).first()
        history.append({
            'id': m.id,
            'username': m.username,
            'content': m.content,
            'type': m.type,
            'timestamp': m.timestamp,
            'avatar': sender.avatar if sender else ''
        })
    return render_template('chat.html', user=current_user, history=history)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# Socket.io Olayları
active_users = {}

@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        active_users[request.sid] = {"name": current_user.username, "avatar": current_user.avatar or ''}
        emit('user_list', list(active_users.values()), broadcast=True)

@socketio.on('disconnect')
def disconnect():
    active_users.pop(request.sid, None)
    emit('user_list', list(active_users.values()), broadcast=True)

@socketio.on('message')
def handle_msg(data):
    now = datetime.now().strftime("%H:%M")
    m_type = data.get('type', 'text')
    new_m = Message(username=current_user.username, content=data['msg'], type=m_type, timestamp=now)
    db.session.add(new_m)
    db.session.commit()
    
    emit('message', {
        'id': new_m.id,
        'user': current_user.username,
        'msg': data['msg'],
        'time': now,
        'type': m_type,
        'avatar': current_user.avatar or ''
    }, broadcast=True)

@socketio.on('delete_message')
def delete_msg(data):
    msg = Message.query.get(data['id'])
    if msg and msg.username == current_user.username:
        db.session.delete(msg)
        db.session.commit()
        emit('remove_message', {'id': data['id']}, broadcast=True)

@socketio.on('update_avatar')
def update_avatar(data):
    user = User.query.get(current_user.id)
    user.avatar = data['img']
    db.session.commit()
    # Aktif kullanıcılar listesini güncelle
    for sid, info in active_users.items():
        if info['name'] == user.username:
            info['avatar'] = data['img']
    emit('user_list', list(active_users.values()), broadcast=True)

# Uygulamayı Başlat
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    
    # Render'ın verdiği PORT'u kullan, yoksa 5000'de çalış
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)