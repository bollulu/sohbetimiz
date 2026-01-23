from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'master_whatsapp_2026'

# Veritabanı Yolu
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

# Dosya Boyutu Sınırı (Resim, Video ve Müzik için 500MB)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=500 * 1024 * 1024)

# --- VERİTABANI MODELLERİ ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(10))     # Erkek / Kadın
    avatar = db.Column(db.Text)          # Kalıcı Profil (Base64)
    bg_img = db.Column(db.Text)          # Kalıcı Arka Plan (Base64)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)         # Mesaj metni veya Dosya Base64
    msg_type = db.Column(db.String(20))   # text / file
    file_name = db.Column(db.String(100))
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)         # Resim veya Video Base64
    music = db.Column(db.Text)           # Müzik Base64 (Opsiyonel)
    media_type = db.Column(db.String(20)) # image / video
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Veritabanını oluştur
with app.app_context():
    db.create_all()

# --- OTURUM YÖNETİMİ ---

login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    return db.session.get(User, int(id))

# --- ANA ROUTLAR ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        gender = request.form.get('gender')
        avatar_data = request.form.get('avatar_data')
        
        # Cinsiyete göre varsayılan avatar mantığı
        if not avatar_data or len(avatar_data) < 100:
            if gender == "Erkek":
                avatar_data = "https://cdn-icons-png.flaticon.com/512/4140/4140037.png"
            else:
                avatar_data = "https://cdn-icons-png.flaticon.com/512/4140/4140047.png"

        new_user = User(
            username=username, 
            password=password, 
            gender=gender, 
            avatar=avatar_data,
            bg_img=""
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('login'))
        except:
            db.session.rollback()
            return "Hata: Kullanıcı adı zaten mevcut!"
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/chat')
@login_required
def chat():
    # Son 100 mesajı getir
    msgs = Message.query.order_by(Message.id.desc()).limit(100).all()
    return render_template('chat.html', user=current_user, initial_msgs=reversed(list(msgs)))

@app.route('/live')
@login_required
def live():
    return render_template('live.html', user=current_user)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- SOCKET.IO ETKİLEŞİMLERİ ---

online_users = {}

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        # Online listesine ekle ve yayınla
        online_users[current_user.username] = {"avatar": current_user.avatar}
        emit('update_user_list', online_users, broadcast=True)
        # Mevcut hikayeleri gönder
        send_stories()

@socketio.on('message')
def handle_message(data):
    # Mesajı veritabanına kaydet
    msg = Message(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['content'],
        msg_type=data.get('type', 'text'),
        file_name=data.get('file_name', ''),
        timestamp=datetime.now().strftime("%H:%M")
    )
    db.session.add(msg)
    db.session.commit()
    
    # Herkese yayınla
    emit('new_message', {
        'user': msg.username,
        'avatar': msg.user_avatar,
        'content': msg.content,
        'type': msg.msg_type,
        'file_name': msg.file_name,
        'time': msg.timestamp
    }, broadcast=True)

@socketio.on('add_story')
def handle_story(data):
    # Hikayeyi kaydet
    new_story = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['content'],
        music=data.get('music'),
        media_type=data.get('media_type', 'image')
    )
    db.session.add(new_story)
    db.session.commit()
    send_stories()

def send_stories():
    # Tüm hikayeleri kullanıcı bazlı grupla
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        grouped[s.username] = {
            'avatar': s.user_avatar,
            'content': s.content,
            'music': s.music,
            'media_type': s.media_type
        }
    emit('receive_stories', grouped, broadcast=True)

@socketio.on('update_profile')
def handle_profile_update(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    db.session.commit()
    # Online listesini güncelle
    online_users[user.username]['avatar'] = data['avatar']
    emit('update_user_list', online_users, broadcast=True)

@socketio.on('update_bg')
def handle_bg_update(data):
    user = db.session.get(User, current_user.id)
    user.bg_img = data['bg']
    db.session.commit()

@socketio.on('signal')
def handle_webrtc_signal(data):
    # Görüntülü arama sinyallerini diğer kullanıcıya ilet
    emit('signal', data, broadcast=True, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000, debug=True)
