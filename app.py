from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chat-pro-v2026-final-ultra'
basedir = os.path.abspath(os.path.dirname(__file__))

# Veritabanı dosya yolu
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_v26_final.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Flask dosya yükleme limiti (100MB)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

db = SQLAlchemy(app)

# SocketIO: Büyük veri transferi ve timeout ayarları
socketio = SocketIO(app, 
                    cors_allowed_origins="*", 
                    async_mode='gevent', 
                    max_http_buffer_size=100 * 1024 * 1024, # 100MB tampon bellek
                    ping_timeout=120,
                    ping_interval=25)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Çevrimiçi kullanıcıları ve avatarlarını tutan sözlük
online_users = {}

# --- VERİTABANI MODELLERİ ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text) # Base64 profil resmi

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(100))
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(10)) # 'text', 'image', 'video'
    timestamp = db.Column(db.String(10))
    is_read = db.Column(db.Boolean, default=False)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text) # Base64 medya
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- LOGIN YÖNETİMİ ---

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

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
        av = request.form.get('avatar_choice') # Kayıttaki sıkıştırılmış resim
        if not User.query.filter_by(username=u).first():
            new_user = User(username=u, password=p, avatar=av)
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', user=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- SOCKET.IO OLAYLARI ---

@socketio.on('join')
def on_join(data):
    room = data.get('room', 'Genel')
    join_room(room)
    session['room'] = room
    
    # Kullanıcıyı çevrimiçi listesine ekle
    online_users[current_user.username] = current_user.avatar
    emit('user_list', online_users, broadcast=True)
    
    # Geçmiş mesajları yükle (Son 50 mesaj)
    msgs = Message.query.filter_by(room=room).order_by(Message.id.desc()).limit(50).all()
    history = [{
        'id': m.id, 
        'user': m.username, 
        'avatar': m.user_avatar, 
        'msg': m.content, 
        'type': m.msg_type, 
        'time': m.timestamp
    } for m in reversed(msgs)]
    emit('history', history)
    
    # Hikayeleri gönder
    send_stories()

def send_stories():
    stories = Story.query.order_by(Story.created_at.asc()).all()
    grouped = {}
    for s in stories:
        if s.username not in grouped:
            grouped[s.username] = {'avatar': s.user_avatar, 'stories': []}
        grouped[s.username]['stories'].append({'id': s.id, 'content': s.content})
    emit('story_list', grouped, broadcast=True)

@socketio.on('message')
def handle_msg(data):
    room = data.get('room', session.get('room', 'Genel'))
    now = datetime.now().strftime("%H:%M")
    
    msg = Message(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['msg'],
        msg_type=data.get('type', 'text'),
        room=room,
        timestamp=now
    )
    db.session.add(msg)
    db.session.commit()
    
    emit('message', {
        'id': msg.id,
        'user': current_user.username,
        'avatar': current_user.avatar,
        'msg': data['msg'],
        'type': msg.msg_type,
        'time': now
    }, to=room)

@socketio.on('upload_story')
def handle_story(data):
    new_story = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['img']
    )
    db.session.add(new_story)
    db.session.commit()
    send_stories()

# PROFIL RESMI GÜNCELLEME SOKETI
@socketio.on('update_profile_pic')
def update_profile_pic(data):
    if not current_user.is_authenticated:
        return
    
    new_avatar = data.get('avatar')
    if new_avatar:
        # 1. Kullanıcı tablosunu güncelle
        user = db.session.get(User, current_user.id)
        user.avatar = new_avatar
        
        # 2. Mesajlar ve Hikayelerdeki eski avatarları güncelle (Senkronizasyon)
        Message.query.filter_by(username=current_user.username).update({Message.user_avatar: new_avatar})
        Story.query.filter_by(username=current_user.username).update({Story.user_avatar: new_avatar})
        
        db.session.commit()
        
        # 3. Global online listesini güncelle
        online_users[current_user.username] = new_avatar
        emit('user_list', online_users, broadcast=True)
        
        # 4. Hikaye listesini de yenile (Avatarların değişmesi için)
        send_stories()

@socketio.on('delete_story')
def delete_story(data):
    story = Story.query.filter_by(id=data['id'], username=current_user.username).first()
    if story:
        db.session.delete(story)
        db.session.commit()
        send_stories()

@socketio.on('disconnect')
def on_disconnect():
    if current_user.is_authenticated and current_user.username in online_users:
        del online_users[current_user.username]
        emit('user_list', online_users, broadcast=True)

if __name__ == '__main__':
    # Render ve diğer platformlar için port ayarı
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app, host='0.0.0.0', port=port)
