import os
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_gizli_anahtar_2026'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100MB Limit

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'data.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=100 * 1024 * 1024)

# VERİTABANI MODELLERİ
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    sender = db.Column(db.String(80))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    type = db.Column(db.String(20))
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    type = db.Column(db.String(10)) # image or video
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# ROUTES
@app.route('/')
def index():
    if current_user.is_authenticated: return redirect(url_for('chat'))
    return render_template('auth.html')

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user: login_user(user, remember=True); return redirect(url_for('chat'))
    return "Hata: Giriş başarısız!"

@app.route('/register', methods=['POST'])
def register():
    u, p, a = request.form.get('username'), request.form.get('password'), request.form.get('avatar_data')
    if User.query.filter_by(username=u).first(): return "Bu kullanıcı zaten var!"
    new_user = User(username=u, password=p, avatar=a)
    db.session.add(new_user); db.session.commit(); login_user(new_user)
    return redirect(url_for('chat'))

@app.route('/chat')
@login_required
def chat():
    users = User.query.all()
    stories = Story.query.order_by(Story.created_at.desc()).all()
    return render_template('chat.html', user=current_user, all_users=users, stories=stories)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('index'))

# SOCKETIO OLAYLARI
@socketio.on('join')
def on_join(data):
    join_room(data['room'])
    msgs = Message.query.filter_by(room=data['room']).all()
    emit('load_history', [{'id':m.id,'sender':m.sender,'avatar':m.avatar,'content':m.content,'type':m.type,'time':m.timestamp} for m in msgs])

@socketio.on('message')
def handle_msg(data):
    time = datetime.now().strftime("%H:%M")
    new_m = Message(room=data['room'], sender=current_user.username, avatar=current_user.avatar, content=data['content'], type=data['type'], timestamp=time)
    db.session.add(new_m); db.session.commit()
    data.update({'id':new_m.id, 'sender':current_user.username, 'avatar':current_user.avatar, 'time':time})
    emit('message', data, room=data['room'])

@socketio.on('delete_group')
def delete_group(data):
    # Gruba ait tüm mesajları siler
    Message.query.filter_by(room=data['room']).delete()
    db.session.commit()
    emit('group_deleted', data['room'], broadcast=True)

@socketio.on('post_story')
def post_story(data):
    new_s = Story(username=current_user.username, avatar=current_user.avatar, content=data['content'], type=data['type'])
    db.session.add(new_s); db.session.commit()
    emit('new_story', {'username':current_user.username, 'avatar':current_user.avatar})

if __name__ == '__main__':
    socketio.run(app, debug=True)
