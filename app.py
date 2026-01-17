from gevent import monkey
monkey.patch_all()
import os, json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sohbetimiz_ultra_v8'
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 # 1 GB Limit

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_final.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, index=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)
    gender = db.Column(db.String(10))
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
    content = db.Column(db.Text)
    m_type = db.Column(db.String(20), default='text') # text, image, video, audio
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

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- ROTALAR ---
@app.route('/')
def index():
    return redirect(url_for('chat_page')) if current_user.is_authenticated else render_template('auth.html')

@app.route('/chat')
@login_required
def chat_page():
    return render_template('chat.html', user=current_user)

@app.route('/register', methods=['POST'])
def register():
    u, p = request.form.get('username'), request.form.get('password')
    a, g = request.form.get('avatar_data'), request.form.get('gender')
    if not User.query.filter_by(username=u).first():
        new_u = User(username=u, password=p, avatar=a, gender=g)
        db.session.add(new_u); db.session.commit()
        login_user(new_u)
    return redirect(url_for('chat_page'))

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user: login_user(user)
    return redirect(url_for('chat_page'))

@app.route('/logout')
def logout():
    logout_user(); return redirect(url_for('index'))

# --- SOCKET ---
@socketio.on('join')
def on_join(data):
    join_room(data['room'])
    msgs = Message.query.filter_by(room=data['room']).all()
    emit('load_history', [{'sender':m.sender,'content':m.content,'type':m.m_type} for m in msgs])

@socketio.on('send_message')
def handle_msg(data):
    m = Message(room=data['room'], sender=current_user.username, content=data['msg'], m_type=data.get('type','text'))
    db.session.add(m); db.session.commit()
    emit('new_message', {'sender':current_user.username, 'content':data['msg'], 'type':data.get('type','text'), 'room':data['room']}, room=data['room'])

@socketio.on('post_story')
def handle_story(data):
    s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['content'], media_type=data['type'], audio_data=data.get('audio'))
    db.session.add(s); db.session.commit()
    send_stories()

def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar':s.user_avatar, 'items':[]}
        grouped[s.username]['items'].append({'id':s.id,'content':s.content,'type':s.media_type,'audio':s.audio_data,'username':s.username})
    emit('stories_update', grouped, broadcast=True)

if __name__ == '__main__':
    socketio.run(app)
