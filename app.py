from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whatsapp_ultra_v4_2026'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024 

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=200 * 1024 * 1024)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)
    bg_img = db.Column(db.Text, default="")

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    music = db.Column(db.Text, default="")

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

@app.route('/')
def home():
    if current_user.is_authenticated: return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/chat')
@login_required
def chat():
    msgs = Message.query.all()
    return render_template('chat.html', user=current_user, initial_msgs=msgs)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

# SOCKET ETKİLEŞİMLERİ
online_users = {}

@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = {"avatar": current_user.avatar}
        emit('user_status', online_users, broadcast=True)
        send_all_stories()

@socketio.on('message')
def handle_msg(data):
    msg_time = datetime.now().strftime("%H:%M")
    m = Message(username=current_user.username, user_avatar=current_user.avatar, content=data['content'], timestamp=msg_time)
    db.session.add(m)
    db.session.commit()
    emit('new_message', {'id': m.id, 'user': m.username, 'avatar': m.user_avatar, 'content': m.content, 'time': m.timestamp}, broadcast=True)

@socketio.on('delete_msg')
def delete_msg(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.username == current_user.username:
        db.session.delete(msg)
        db.session.commit()
        emit('msg_deleted', {'id': data['id']}, broadcast=True)

@socketio.on('add_story')
def add_story(data):
    s = Story(username=current_user.username, user_avatar=current_user.avatar, 
              content=data['content'], media_type=data['type'], music=data.get('music',''))
    db.session.add(s)
    db.session.commit()
    send_all_stories()

@socketio.on('delete_story')
def delete_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        db.session.delete(s)
        db.session.commit()
        send_all_stories()

def send_all_stories():
    stories = Story.query.all()
    output = {}
    for s in stories:
        if s.username not in output: output[s.username] = {"avatar": s.user_avatar, "items": []}
        output[s.username]["items"].append({"id": s.id, "content": s.content, "type": s.media_type, "music": s.music})
    emit('all_stories', output, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, host='0.0.0.0', port=port)
