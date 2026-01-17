from gevent import monkey
monkey.patch_all()

import os, json, time
from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from flask_bcrypt import Bcrypt
from datetime import datetime

# ================= APP =================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret2026'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 📦 50MB LIMIT

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat.db')

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# ================= MODELS =================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(200))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20))
    timestamp = db.Column(db.String(10))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    music = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')
    created_at = db.Column(db.Integer)  # ⏱️ timestamp

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    members = db.Column(db.Text)

with app.app_context():
    db.create_all()

# ================= LOGIN =================
login_manager = LoginManager(app)
login_manager.login_view = '/'

@login_manager.user_loader
def load_user(uid):
    return db.session.get(User, int(uid))

# ================= ROUTES =================

@app.route('/')
def auth():
    return render_template('auth.html')

@app.route('/register', methods=['POST'])
def register():
    pw = bcrypt.generate_password_hash(request.form['password']).decode()
    u = User(username=request.form['username'], password=pw,
             avatar="https://cdn-icons-png.flaticon.com/512/847/847969.png")
    db.session.add(u)
    db.session.commit()
    login_user(u)
    return redirect('/chat')

@app.route('/login', methods=['POST'])
def login():
    u = User.query.filter_by(username=request.form['username']).first()
    if u and bcrypt.check_password_hash(u.password, request.form['password']):
        login_user(u)
        return redirect('/chat')
    return redirect('/')

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

@socketio.on('join_room')
def join(data):
    join_room(data['room'])
    msgs = Message.query.filter_by(room=data['room']).all()
    emit('history',[{
        'user':m.sender,'msg':m.content,'type':m.msg_type,'ava':m.avatar
    } for m in msgs])

@socketio.on('send_message')
def send_msg(d):
    m = Message(room=d['room'], sender=current_user.username,
                avatar=current_user.avatar,
                content=d['msg'], msg_type=d['type'],
                timestamp=datetime.now().strftime("%H:%M"))
    db.session.add(m)
    db.session.commit()
    emit('message',{
        'user':m.sender,'msg':m.content,'type':m.msg_type,'ava':m.avatar
    }, to=d['room'])

# ================= GROUP =================

@socketio.on('create_group')
def create_group(d):
    g = Group(name=d['name'], members=json.dumps(d['members']))
    db.session.add(g)
    db.session.commit()
    emit('group_created', {'id':g.id,'name':g.name}, broadcast=True)

# ================= STORY =================

def clean_old_stories():
    now = int(time.time())
    Story.query.filter(Story.created_at < now - 86400).delete()
    db.session.commit()

@socketio.on('add_story')
def add_story(d):
    clean_old_stories()
    s = Story(
        username=current_user.username,
        avatar=current_user.avatar,
        content=d['content'],
        music=d.get('music'),
        media_type=d['type'],
        created_at=int(time.time())
    )
    db.session.add(s)
    db.session.commit()
    send_stories()

@socketio.on('view_story')
def view_story(d):
    s = db.session.get(Story, d['id'])
    if s:
        v = json.loads(s.viewers)
        if current_user.username not in v:
            v.append(current_user.username)
            s.viewers = json.dumps(v)
            db.session.commit()

def send_stories():
    clean_old_stories()
    data = {}
    for s in Story.query.all():
        data.setdefault(s.username,{
            'avatar':s.avatar,'items':[]
        })
        data[s.username]['items'].append({
            'id':s.id,
            'content':s.content,
            'music':s.music,
            'type':s.media_type,
            'viewers':json.loads(s.viewers)
        })
    emit('story_list', data, broadcast=True)

# ================= USERS =================

@socketio.on('connect')
def users():
    emit('users',[{'u':u.username,'a':u.avatar} for u in User.query.all()], broadcast=True)

# ================= RUN =================

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)
