from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra_whatsapp_final_2026'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)
    gender = db.Column(db.String(20))
    blocked_list = db.Column(db.Text, default="") # Virgülle ayrılmış kullanıcı adları

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    m_type = db.Column(db.String(10)) # image/video
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username')
        if User.query.filter_by(username=u).first(): return "Bu isim alınmış!", 400
        new_u = User(username=u, password=request.form.get('password'), 
                     gender=request.form.get('gender'), avatar=request.form.get('avatar_data'))
        db.session.add(new_u); db.session.commit()
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
def chat(): return render_template('chat.html', user=current_user)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

@app.route('/delete_acc', methods=['POST'])
@login_required
def delete_acc():
    if current_user.password == request.form.get('password'):
        db.session.delete(current_user); db.session.commit()
        logout_user(); return "OK"
    return "Error", 403

# --- SOCKET OLAYLARI ---
online_users = {}

@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        online_users[current_user.username] = {"avatar": current_user.avatar, "gender": current_user.gender}
        emit('update_online', online_users, broadcast=True)
        send_all_stories()

@socketio.on('send_msg')
def handle_msg(data):
    emit('new_msg', {
        'id': datetime.now().timestamp(),
        'sender': current_user.username,
        'avatar': current_user.avatar,
        'content': data['content'],
        'type': data['type'],
        'time': datetime.now().strftime("%H:%M")
    }, broadcast=True)

@socketio.on('delete_msg')
def delete_msg(data):
    emit('msg_deleted', data, broadcast=True)

@socketio.on('add_story')
def handle_story(data):
    s = Story(username=current_user.username, avatar=current_user.avatar, content=data['content'], m_type=data['type'])
    db.session.add(s); db.session.commit()
    send_all_stories()

def send_all_stories():
    stories = Story.query.all()
    out = []
    for s in stories:
        out.append({"username": s.username, "avatar": s.avatar, "content": s.content, "type": s.m_type, "id": s.id})
    emit('all_stories', out, broadcast=True)

@socketio.on('update_profile_all')
def up_all(data):
    current_user.avatar = data['avatar']
    db.session.commit()
    online_users[current_user.username]['avatar'] = data['avatar']
    emit('update_online', online_users, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
