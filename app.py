from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra-secure-2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'ultra_database_v15.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=50 * 1024 * 1024)

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(10))
    timestamp = db.Column(db.String(10))
    is_read = db.Column(db.Boolean, default=False)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.relationship('StoryView', backref='story', lazy=True, cascade="all, delete-orphan")

class StoryView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('story.id'), nullable=False)
    viewer_username = db.Column(db.String(50))

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

# --- ROUTES (YÖNLENDİRMELER) ---
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
        u = request.form.get('username')
        p = request.form.get('password')
        av = request.form.get('avatar_choice') or "https://www.w3schools.com/howto/img_avatar.png"
        if not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password=p, avatar=av))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', user=current_user)

# --- SOKET OLAYLARI ---
@socketio.on('join')
def on_join(data):
    join_room('Genel')
    msgs = Message.query.filter_by(room='Genel').order_by(Message.id.desc()).limit(50).all()
    history = [{'id': m.id, 'user': m.username, 'avatar': m.user_avatar, 'msg': m.content, 'type': m.msg_type, 'time': m.timestamp, 'is_read': m.is_read} for m in reversed(msgs)]
    emit('history', history)
    send_stories()

def send_stories():
    stories = Story.query.order_by(Story.created_at.asc()).all()
    grouped = {}
    for s in stories:
        if s.username not in grouped:
            grouped[s.username] = {'avatar': s.user_avatar, 'stories': []}
        grouped[s.username]['stories'].append({'id': s.id, 'content': s.content, 'views': [v.viewer_username for v in s.views]})
    emit('story_list', grouped, broadcast=True)

@socketio.on('add_story')
def handle_story(data):
    new_s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['image'])
    db.session.add(new_s)
    db.session.commit()
    send_stories()

@socketio.on('view_story')
def view_story(data):
    story_id = data.get('story_id')
    exists = StoryView.query.filter_by(story_id=story_id, viewer_username=current_user.username).first()
    if not exists:
        db.session.add(StoryView(story_id=story_id, viewer_username=current_user.username))
        db.session.commit()
        send_stories()

@socketio.on('update_profile_pic')
def update_profile(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    Message.query.filter_by(username=current_user.username).update({Message.user_avatar: user.avatar})
    Story.query.filter_by(username=current_user.username).update({Story.user_avatar: user.avatar})
    db.session.commit()
    emit('profile_updated', {'username': current_user.username, 'avatar': user.avatar}, broadcast=True)

@socketio.on('message')
def handle_msg(data):
    now = datetime.now().strftime("%H:%M")
    msg = Message(username=current_user.username, user_avatar=current_user.avatar, content=data['msg'], msg_type=data.get('type', 'text'), room='Genel', timestamp=now)
    db.session.add(msg)
    db.session.commit()
    emit('message', {'id': msg.id, 'user': current_user.username, 'avatar': current_user.avatar, 'msg': data['msg'], 'type': msg.msg_type, 'time': now, 'is_read': False}, to='Genel')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
