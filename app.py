from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sohbet-gevent-2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_final.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
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
    room = db.Column(db.String(50), default='Genel')
    username = db.Column(db.String(50))
    content = db.Column(db.Text)
    timestamp = db.Column(db.String(10))

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Rotalar
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user)
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p = request.form.get('username'), request.form.get('password')
        if u and p and not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password=p))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', user=current_user)

@app.route('/live')
@login_required
def live():
    # Burası 404 hatasını çözen yer!
    return render_template('live.html', user=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# Socket Olayları
@socketio.on('join')
def on_join(data):
    room = data.get('room', 'Genel')
    join_room(room)
    session['room'] = room
    msgs = Message.query.filter_by(room=room).order_by(Message.id.desc()).limit(50).all()
    history = [{'id': m.id, 'user': m.username, 'msg': m.content, 'time': m.timestamp} for m in reversed(msgs)]
    emit('history', history)

@socketio.on('message')
def handle_msg(data):
    room = session.get('room', 'Genel')
    now = datetime.now().strftime("%H:%M")
    msg = Message(username=current_user.username, content=data['msg'], room=room, timestamp=now)
    db.session.add(msg)
    db.session.commit()
    emit('message', {'id': msg.id, 'user': current_user.username, 'msg': data['msg'], 'time': now}, to=room)

# WebRTC Sinyalleşme (Canlı Yayın İçin)
@socketio.on('signal')
def handle_signal(data):
    emit('signal', data, to=data['to'], include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
