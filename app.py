from gevent import monkey
monkey.patch_all()

import os, json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_2026'

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat.db')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# ================= MODELLER =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)
    blocked_users = db.Column(db.Text, default='[]')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20))
    timestamp = db.Column(db.String(10))
    status = db.Column(db.String(10), default='sent')

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    audio = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')
    duration = db.Column(db.Integer, default=30)

with app.app_context():
    db.create_all()

# ================= LOGIN =================

login_manager = LoginManager(app)
login_manager.login_view = 'auth'

@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))

# ================= ROUTES =================

@app.route('/')
def auth():
    if current_user.is_authenticated:
        return redirect('/chat')
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login_proc():
    u = User.query.filter_by(username=request.form['username']).first()
    if u and u.password == request.form['password']:
        login_user(u)
        return redirect('/chat')
    return redirect('/')

@app.route('/register', methods=['POST'])
def register_proc():
    if User.query.filter_by(username=request.form['username']).first():
        return redirect('/')
    avatar = request.form.get('avatar_data') or "https://cdn-icons-png.flaticon.com/512/847/847969.png"
    u = User(username=request.form['username'], password=request.form['password'], avatar=avatar)
    db.session.add(u)
    db.session.commit()
    login_user(u)
    return redirect('/chat')

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect('/')

# ================= SOCKET =================

@socketio.on('connect')
def connect():
    emit('update_users', get_users(), broadcast=True)

@socketio.on('join_room')
def join(data):
    join_room(data['room'])
    msgs = Message.query.filter_by(room=data['room']).all()
    emit('history', [{
        'id':m.id,'user':m.sender,'ava':m.avatar,
        'msg':m.content,'type':m.msg_type,
        'time':m.timestamp,'status':m.status
    } for m in msgs])

@socketio.on('send_message')
def send_msg(d):
    now = datetime.now().strftime("%H:%M")
    m = Message(room=d['room'], sender=current_user.username,
                avatar=current_user.avatar, content=d['msg'],
                msg_type=d['type'], timestamp=now)
    db.session.add(m)
    db.session.commit()
    emit('message',{
        'id':m.id,'room':d['room'],'user':current_user.username,
        'ava':current_user.avatar,'msg':d['msg'],
        'type':d['type'],'time':now,'status':'sent'
    },to=d['room'])

# ================= STORY =================

@socketio.on('add_story')
def add_story(d):
    s = Story(username=current_user.username,
              user_avatar=current_user.avatar,
              content=d['content'], audio=d.get('music'),
              media_type=d['type'])
    db.session.add(s)
    db.session.commit()
    send_stories()

def send_stories():
    data = {}
    for s in Story.query.all():
        data.setdefault(s.username, {'avatar':s.user_avatar,'items':[]})
        data[s.username]['items'].append({
            'id':s.id,'content':s.content,'music':s.audio,
            'type':s.media_type,'viewers':json.loads(s.viewers),
            'can_delete':s.username==current_user.username
        })
    emit('story_list', data, broadcast=True)

def get_users():
    return [{'username':u.username,'avatar':u.avatar} for u in User.query.all()]

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)
