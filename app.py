from gevent import monkey
monkey.patch_all()

import os, json, uuid
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super_secret_key_2026'

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'chat_v2.db')
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static/media/stories')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="gevent")

# ---------------- MODELLER ----------------

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
    timestamp = db.Column(db.String(20))
    status = db.Column(db.String(10), default='sent')

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    media_url = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ---------------- LOGIN ----------------

login_manager = LoginManager(app)
login_manager.login_view = 'auth'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ---------------- ROUTES ----------------

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
    u = User(
        username=request.form['username'],
        password=request.form['password'],
        avatar=request.form.get('avatar_data')
    )
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

# ---------------- STORY UPLOAD (🔥 ANA NOKTA) ----------------

@app.route('/upload_story', methods=['POST'])
@login_required
def upload_story():
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'no file'}), 400

    ext = secure_filename(file.filename).split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)

    media_type = 'video' if ext in ['mp4', 'webm'] else 'image'

    story = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        media_url=f"/static/media/stories/{filename}",
        media_type=media_type
    )
    db.session.add(story)
    db.session.commit()

    socketio.emit('story_updated')
    return jsonify({'success': True})

# ---------------- SOCKET ----------------

@socketio.on('join_room')
def join(data):
    join_room(data['room'])
    send_stories()

@socketio.on('get_stories')
def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        grouped.setdefault(s.username, {
            'avatar': s.user_avatar,
            'items': []
        })
        grouped[s.username]['items'].append({
            'id': s.id,
            'url': s.media_url,
            'type': s.media_type,
            'can_delete': s.username == current_user.username
        })
    emit('story_list', grouped, broadcast=True)

@socketio.on('delete_story')
def delete_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        try:
            os.remove(BASE_DIR + s.media_url)
        except:
            pass
        db.session.delete(s)
        db.session.commit()
        send_stories()

# ---------------- RUN ----------------

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=10000)
