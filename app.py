from gevent import monkey
monkey.patch_all()
import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sohbetimiz_2026_key'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'sohbetimiz.db')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100MB Limit

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(50))
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20), default='text') # text, image, video, audio
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text) # Base64 Media
    media_type = db.Column(db.String(10)) # image or video
    audio_data = db.Column(db.Text, nullable=True) # Müzik verisi
    viewers = db.Column(db.Text, default='[]') # İzleyenlerin JSON listesi
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('auth.html') if not current_user.is_authenticated else redirect(url_for('chat'))

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
        new_u = User(username=u, password=p, avatar=a)
        db.session.add(new_u); db.session.commit(); login_user(new_u)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat():
    all_users = User.query.all()
    return render_template('chat.html', user=current_user, all_users=all_users)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

# --- SOCKET EVENTS ---
@socketio.on('join')
def on_join(data):
    join_room(data['room'])
    msgs = Message.query.filter_by(room=data['room']).order_by(Message.timestamp.asc()).all()
    emit('load_history', [{'sender':m.sender, 'content':m.content, 'type':m.msg_type} for m in msgs])

@socketio.on('send_message')
def handle_msg(data):
    new_m = Message(room=data['room'], sender=current_user.username, content=data['msg'], msg_type=data.get('type','text'))
    db.session.add(new_m); db.session.commit()
    emit('new_message', data, room=data['room'])

@socketio.on('post_story')
def handle_story(data):
    s = Story(username=current_user.username, user_avatar=current_user.avatar, 
              content=data['content'], media_type=data['type'], audio_data=data.get('audio'))
    db.session.add(s); db.session.commit()
    send_stories_update()

@socketio.on('view_story')
def view_story(data):
    s = db.session.get(Story, data['story_id'])
    if s and s.username != current_user.username:
        viewers = json.loads(s.viewers)
        if current_user.username not in viewers:
            viewers.append(current_user.username)
            s.viewers = json.dumps(viewers)
            db.session.commit()
            send_stories_update()

@socketio.on('get_stories')
def get_stories():
    send_stories_update()

@socketio.on('delete_story')
def delete_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        db.session.delete(s); db.session.commit()
        send_stories_update()

def send_stories_update():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar': s.user_avatar, 'items': []}
        grouped[s.username]['items'].append({
            'id': s.id, 'content': s.content, 'type': s.media_type, 
            'audio': s.audio_data, 'viewers': json.loads(s.viewers), 'owner': s.username
        })
    emit('stories_list', grouped, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
