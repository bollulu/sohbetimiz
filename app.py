from gevent import monkey
monkey.patch_all() # Ağ bağlantıları için kritik

import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whatsapp_ultra_v5_2026'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024 # Dosya yükleme limiti (200MB)

# Veritabanı Yapılandırması
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- VERİTABANI MODELLERİ ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text, default="https://www.w3schools.com/howto/img_avatar.png")

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
    content = db.Column(db.Text) # Base64 Medya
    media_type = db.Column(db.String(20)) # image/video
    music = db.Column(db.Text, default="") # Base64 Müzik
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- LOGIN YÖNETİMİ ---
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    return db.session.get(User, int(id))

# --- SAYFA ROTALARI (ROUTES) ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        user = User.query.filter_by(username=u).first()
        if user and user.password == p:
            login_user(user)
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        if not User.query.filter_by(username=u).first():
            new_user = User(username=u, password=p)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    # Sayfa yüklenince eski mesajları çekmek için
    initial_msgs = Message.query.all()
    return render_template('chat.html', user=current_user, initial_msgs=initial_msgs)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- SOCKET.IO ETKİLEŞİMLERİ ---
@socketio.on('message')
def handle_msg(data):
    time_now = datetime.now().strftime("%H:%M")
    m = Message(username=current_user.username, user_avatar=current_user.avatar, content=data['content'], timestamp=time_now)
    db.session.add(m)
    db.session.commit()
    emit('new_message', {'user': m.username, 'avatar': m.user_avatar, 'content': m.content, 'time': m.timestamp}, broadcast=True)

@socketio.on('add_story')
def handle_story(data):
    s = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['content'],
        media_type=data['type'],
        music=data.get('music', '')
    )
    db.session.add(s)
    db.session.commit()
    broadcast_stories()

@socketio.on('delete_story')
def delete_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        db.session.delete(s)
        db.session.commit()
        broadcast_stories()

def broadcast_stories():
    stories = Story.query.order_by(Story.timestamp.asc()).all()
    output = {}
    for s in stories:
        if s.username not in output:
            output[s.username] = {"avatar": s.user_avatar, "items": []}
        output[s.username]["items"].append({
            "id": s.id, "content": s.content, "type": s.media_type, "music": s.music
        })
    emit('all_stories', output, broadcast=True)

# --- VİDEO CHAT SİNYALLEŞME (WebRTC) ---
@socketio.on('video-offer')
def handle_offer(data):
    emit('video-offer', data, broadcast=True, include_self=False)

@socketio.on('video-answer')
def handle_answer(data):
    emit('video-answer', data, broadcast=True, include_self=False)

@socketio.on('new-ice-candidate')
def handle_candidate(data):
    emit('new-ice-candidate', data, broadcast=True, include_self=False)

@socketio.on('connect')
def on_connect():
    broadcast_stories() # Bağlanan herkese hikayeleri yolla

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    socketio.run(app, host='0.0.0.0', port=port)
