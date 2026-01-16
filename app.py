from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'cok_gizli_anahtar'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Klasör yoksa oluştur
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth'

# --- Veritabanı Modelleri ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    gender = db.Column(db.String(50))
    avatar = db.Column(db.String(300), default='default.png')
    blocked_users = db.Column(db.String(500), default='') # Virgülle ayrılmış ID'ler

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(50)) # 'general', 'group_X' veya 'private_X_Y'
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    sender_name = db.Column(db.String(150))
    sender_avatar = db.Column(db.String(300))
    content = db.Column(db.String(1000)) # Metin veya dosya yolu
    msg_type = db.Column(db.String(50), default='text') # text, image, audio, video
    timestamp = db.Column(db.DateTime, default=datetime.now)
    read_status = db.Column(db.Boolean, default=False)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    content = db.Column(db.String(300)) # Medya yolu
    story_type = db.Column(db.String(50)) # image, video
    music = db.Column(db.String(300), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    viewers = db.Column(db.String(1000), default='') # Virgülle ayrılmış ID'ler

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    members = db.Column(db.String(500)) # Virgülle ayrılmış ID'ler

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Rotalar ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('chat'))
    return redirect(url_for('auth'))

@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')
        
        if action == 'register':
            gender = request.form.get('gender')
            file = request.files.get('avatar')
            avatar_path = 'default.png'
            
            if User.query.filter_by(username=username).first():
                flash('Bu kullanıcı adı zaten var.')
                return redirect(url_for('auth'))

            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                avatar_path = filename

            hashed_pw = generate_password_hash(password, method='scrypt')
            new_user = User(username=username, password=hashed_pw, gender=gender, avatar=avatar_path)
            db.session.add(new_user)
            db.session.commit()
            flash('Kayıt başarılı, giriş yapın.')
        
        elif action == 'login':
            user = User.query.filter_by(username=username).first()
            if user and check_password_hash(user.password, password):
                login_user(user)
                return redirect(url_for('chat'))
            else:
                flash('Hatalı bilgiler.')
    
    return render_template('auth.html')

@app.route('/chat')
@login_required
def chat():
    users = User.query.filter(User.id != current_user.id).all()
    groups = Group.query.filter(Group.members.contains(str(current_user.id))).all()
    stories = Story.query.order_by(Story.timestamp.desc()).all()
    return render_template('chat.html', users=users, groups=groups, stories=stories)

@app.route('/music')
@login_required
def music():
    return render_template('music.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    file = request.files.get('file')
    if file:
        filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'filename': filename})
    return jsonify({'error': 'No file'}), 400

@app.route('/create_group', methods=['POST'])
@login_required
def create_group():
    name = request.form.get('group_name')
    # Basitlik için tüm kullanıcıları ekle veya seçim yap
    # Burada sadece oluşturan kişiyi ekliyoruz, demo amaçlı
    new_group = Group(name=name, members=str(current_user.id))
    db.session.add(new_group)
    db.session.commit()
    return redirect(url_for('chat'))

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    file = request.files.get('avatar')
    if file:
        filename = secure_filename(f"upd_{current_user.id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        current_user.avatar = filename
        db.session.commit()
    return redirect(url_for('chat'))

@app.route('/add_story', methods=['POST'])
@login_required
def add_story():
    file = request.files.get('story_file')
    music = request.files.get('music_file')
    if file:
        f_name = secure_filename(f"story_{current_user.id}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], f_name))
        
        m_name = None
        if music:
            m_name = secure_filename(f"music_{current_user.id}_{music.filename}")
            music.save(os.path.join(app.config['UPLOAD_FOLDER'], m_name))
            
        ftype = 'video' if f_name.endswith(('mp4', 'mov')) else 'image'
        new_story = Story(user_id=current_user.id, content=f_name, story_type=ftype, music=m_name)
        db.session.add(new_story)
        db.session.commit()
    return redirect(url_for('chat'))

# --- SocketIO Olayları ---
@socketio.on('join')
def on_join(data):
    room = data['room']
    join_room(room)
    # Eski mesajları yükle
    messages = Message.query.filter_by(room=room).order_by(Message.timestamp).all()
    history = []
    for m in messages:
        history.append({
            'id': m.id, 'sender': m.sender_name, 'avatar': m.sender_avatar,
            'text': m.content, 'type': m.msg_type, 'read': m.read_status,
            'timestamp': m.timestamp.strftime('%H:%M')
        })
    emit('load_history', history)

@socketio.on('send_message')
def handle_message(data):
    room = data['room']
    msg = Message(
        room=room, sender_id=current_user.id, sender_name=current_user.username,
        sender_avatar=current_user.avatar, content=data['message'], msg_type=data['type']
    )
    db.session.add(msg)
    db.session.commit()
    
    emit('receive_message', {
        'id': msg.id,
        'sender': current_user.username,
        'avatar': current_user.avatar,
        'text': data['message'],
        'type': data['type'],
        'timestamp': datetime.now().strftime('%H:%M'),
        'read': False
    }, room=room)

@socketio.on('delete_message')
def delete_message(data):
    msg_id = data['id']
    msg = Message.query.get(msg_id)
    if msg and msg.sender_id == current_user.id:
        db.session.delete(msg)
        db.session.commit()
        emit('message_deleted', {'id': msg_id}, room=msg.room)

@socketio.on('read_receipt')
def mark_read(data):
    # Basit okundu mantığı
    emit('mark_as_read', {'room': data['room']}, room=data['room'])

# WebRTC Sinyalleşme (Görüntülü Konuşma)
@socketio.on('call_user')
def call_user(data):
    emit('call_made', {'offer': data['offer'], 'socket': request.sid}, room=data['to'])

@socketio.on('make_answer')
def make_answer(data):
    emit('answer_made', {'answer': data['answer'], 'socket': request.sid}, room=data['to'])

@socketio.on('ice_candidate')
def ice_candidate(data):
    emit('ice_candidate_received', {'candidate': data['candidate']}, room=data['to'])

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)
