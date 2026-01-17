import os
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_gizli_2026'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'final_app.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=100 * 1024 * 1024)

# MODELLER
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    avatar = db.Column(db.Text)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    created_by = db.Column(db.String(80))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(80))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    type = db.Column(db.String(20)) # text, image, audio, video
    status = db.Column(db.String(10), default='sent') # sent, read
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    music = db.Column(db.Text, nullable=True)
    type = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# ÇEVRİMİÇİ TAKİBİ
online_users = set()

@app.route('/')
def index():
    if current_user.is_authenticated: return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user: login_user(user); return redirect(url_for('chat'))
    return "Hata!"

@app.route('/register', methods=['POST'])
def register():
    u, p, a = request.form.get('username'), request.form.get('password'), request.form.get('avatar_data')
    new = User(username=u, password=p, avatar=a)
    db.session.add(new); db.session.commit(); login_user(new)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat():
    all_u = User.query.all()
    grps = Group.query.all()
    stors = Story.query.order_by(Story.created_at.desc()).all()
    return render_template('chat.html', user=current_user, all_users=all_u, groups=grps, stories=stors)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

# SOCKETIO
@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        online_users.add(current_user.username)
        emit('online_list', list(online_users), broadcast=True)

@socketio.on('disconnect')
def disconnect():
    if current_user.is_authenticated:
        online_users.discard(current_user.username)
        emit('online_list', list(online_users), broadcast=True)

@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    # Mesajları 'okundu' yap (başkası odaya girdiğinde)
    unread = Message.query.filter_by(room=room, status='sent').filter(Message.sender != current_user.username).all()
    for m in unread: m.status = 'read'
    db.session.commit()
    
    msgs = Message.query.filter_by(room=room).all()
    history = [{'id':m.id,'sender':m.sender,'avatar':m.avatar,'content':m.content,'type':m.type,'time':m.timestamp,'status':m.status} for m in msgs]
    emit('load_history', history)
    if unread: emit('status_update', room, room=room)

@socketio.on('message')
def handle_msg(data):
    time = datetime.now().strftime("%H:%M")
    new_m = Message(room=data['room'], sender=current_user.username, avatar=current_user.avatar, content=data['content'], type=data['type'], timestamp=time)
    db.session.add(new_m); db.session.commit()
    data.update({'id':new_m.id, 'sender':current_user.username, 'avatar':current_user.avatar, 'time':time, 'status':'sent'})
    emit('message', data, room=data['room'])

@socketio.on('delete_msg')
def delete_msg(data):
    m = db.session.get(Message, data['id'])
    if m and m.sender == current_user.username:
        db.session.delete(m); db.session.commit()
        emit('msg_deleted', data['id'], room=m.room)

@socketio.on('create_group')
def create_grp(data):
    if not Group.query.filter_by(name=data['name']).first():
        new_g = Group(name=data['name'], created_by=current_user.username)
        db.session.add(new_g); db.session.commit()
        emit('group_created', {'name': data['name']}, broadcast=True)

@socketio.on('delete_group')
def delete_grp(data):
    g = Group.query.filter_by(name=data['name']).first()
    if g:
        Message.query.filter_by(room="Grup_"+g.name).delete()
        db.session.delete(g); db.session.commit()
        emit('group_deleted', data['name'], broadcast=True)

@socketio.on('post_story')
def post_story(data):
    new_s = Story(username=current_user.username, avatar=current_user.avatar, content=data['content'], music=data.get('music'), type=data['type'])
    db.session.add(new_s); db.session.commit()
    emit('new_story_alert', {'username': current_user.username}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)
