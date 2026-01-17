import os
import json
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sohbetimiz_gizli_anahtar_2026'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024 # 200MB limit

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sohbetimiz.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- VERİ MODELLERİ ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    type = db.Column(db.String(20)) # text, image, video, audio
    status = db.Column(db.String(10), default='sent')
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text) # Base64 Media
    type = db.Column(db.String(10)) # image/video
    music = db.Column(db.String(100), nullable=True)
    viewers = db.Column(db.Text, default='[]') # JSON listesi
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- YOLLAR (ROUTES) ---
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
    if not User.query.filter_by(username=u).first():
        new = User(username=u, password=p, avatar=a if a else "https://cdn-icons-png.flaticon.com/512/149/149071.png")
        db.session.add(new); db.session.commit(); login_user(new)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat():
    all_users = User.query.all()
    groups = Group.query.all()
    raw_stories = Story.query.order_by(Story.created_at.desc()).all()
    
    grouped_stories = {}
    for s in raw_stories:
        if s.username not in grouped_stories: grouped_stories[s.username] = []
        grouped_stories[s.username].append({
            'id': s.id, 'content': s.content, 'type': s.type, 
            'music': s.music, 'viewers': json.loads(s.viewers), 'avatar': s.avatar
        })
    return render_template('chat.html', user=current_user, all_users=all_users, groups=groups, stories=grouped_stories)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

# --- SOCKET.IO ---
@socketio.on('join')
def on_join(data):
    join_room(data['room'])
    msgs = Message.query.filter_by(room=data['room']).all()
    emit('load_history', [{'id':m.id,'sender':m.sender,'avatar':m.avatar,'content':m.content,'type':m.type,'time':m.timestamp,'status':m.status} for m in msgs])

@socketio.on('message')
def handle_msg(data):
    time = datetime.now().strftime("%H:%M")
    new_m = Message(room=data['room'], sender=current_user.username, avatar=current_user.avatar, content=data['content'], type=data['type'], timestamp=time)
    db.session.add(new_m); db.session.commit()
    emit('message', {'id':new_m.id,'sender':current_user.username,'avatar':current_user.avatar,'content':data['content'],'type':data['type'],'time':time,'room':data['room']}, room=data['room'])

@socketio.on('post_story')
def post_story(data):
    new_s = Story(username=current_user.username, avatar=current_user.avatar, content=data['content'], type=data['type'], music=data.get('music'))
    db.session.add(new_s); db.session.commit()
    emit('refresh_all', broadcast=True)

@socketio.on('mark_story_watched')
def watch_story(data):
    s = db.session.get(Story, data['story_id'])
    if s and s.username != current_user.username:
        viewers = json.loads(s.viewers)
        if current_user.username not in viewers:
            viewers.append(current_user.username)
            s.viewers = json.dumps(viewers)
            db.session.commit()
            emit('refresh_all', broadcast=True)

@socketio.on('delete_story')
def del_story(data):
    s = Story.query.filter_by(id=data['id'], username=current_user.username).first()
    if s: db.session.delete(s); db.session.commit(); emit('refresh_all', broadcast=True)

@socketio.on('update_avatar')
def update_ava(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    db.session.commit()
    emit('refresh_all', broadcast=True)

if __name__ == '__main__':
    socketio.run(app)
