import eventlet
eventlet.monkey_patch(all=True) # En üstte kalmalı

import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'render-safe-key-2026'

# --- VERİTABANI HATASINI ÇÖZEN KISIM ---
# Dosya yolunu sunucunun anlayacağı 'mutlak yol' (absolute path) haline getiriyoruz
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'chat_data.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# --------------------------------------

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Modeller
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text, nullable=True, default='')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(10), default='text')
    timestamp = db.Column(db.String(10))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Rotalar
@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        uname, pwd = request.form.get('username'), request.form.get('password')
        if not User.query.filter_by(username=uname).first():
            db.session.add(User(username=uname, password=pwd))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/chat')
@login_required
def chat():
    messages = Message.query.all()
    history = []
    for m in messages:
        sender = User.query.filter_by(username=m.username).first()
        history.append({
            'id': m.id, 'username': m.username, 'content': m.content, 
            'type': m.type, 'timestamp': m.timestamp, 'avatar': sender.avatar if sender else ''
        })
    return render_template('chat.html', user=current_user, history=history)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

# Socket Olayları
@socketio.on('message')
def handle_msg(data):
    now = datetime.now().strftime("%H:%M")
    new_m = Message(username=current_user.username, content=data['msg'], type=data.get('type', 'text'), timestamp=now)
    db.session.add(new_m); db.session.commit()
    emit('message', {'id': new_m.id, 'user': current_user.username, 'msg': data['msg'], 'time': now, 'type': data.get('type', 'text'), 'avatar': current_user.avatar or ''}, broadcast=True)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
