from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whatsapp-ultra-v2'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'wa_v17.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100MB limit (Videolar için)

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=100 * 1024 * 1024)

# MODELLER
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(10)) # 'text', 'image', 'video'
    timestamp = db.Column(db.String(10))

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
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u, p, av = request.form.get('username'), request.form.get('password'), request.form.get('avatar_data')
        if not User.query.filter_by(username=u).first():
            db.session.add(User(username=u, password=p, avatar=av))
            db.session.commit(); return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@socketio.on('join')
def on_join(data):
    join_room('Genel')
    send_stories()
    msgs = Message.query.order_by(Message.id.desc()).limit(30).all()
    history = [{'id': m.id, 'user': m.username, 'avatar': m.user_avatar, 'msg': m.content, 'type': m.msg_type, 'time': m.timestamp} for m in reversed(msgs)]
    emit('history', history)

def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar': s.user_avatar, 'stories': []}
        grouped[s.username]['stories'].append({'id': s.id, 'content': s.content, 'views': [v.viewer_username for v in s.views]})
    emit('story_list', grouped, broadcast=True)

@socketio.on('add_story')
def handle_add_story(data):
    new_s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['image'])
    db.session.add(new_s); db.session.commit(); send_stories()

@socketio.on('message')
def handle_msg(data):
    now = datetime.now().strftime("%H:%M")
    msg = Message(username=current_user.username, user_avatar=current_user.avatar, content=data['msg'], msg_type=data.get('type', 'text'), timestamp=now)
    db.session.add(msg); db.session.commit()
    emit('message', {'id': msg.id, 'user': current_user.username, 'avatar': current_user.avatar, 'msg': data['msg'], 'type': msg.msg_type, 'time': now}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
