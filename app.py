from gevent import monkey
monkey.patch_all()

import os, json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra_pro_2026_fixed'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100MB

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)
    bg_image = db.Column(db.Text, default="")
    gender = db.Column(db.String(20))

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender = db.Column(db.String(50))
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) # text, image, video, audio
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    content = db.Column(db.Text) # Resim/Video Base64
    audio = db.Column(db.Text, default="") # Müzik Base64
    media_type = db.Column(db.String(10)) 
    views = db.Column(db.Text, default="[]") # JSON list of usernames
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- Socket Events ---
@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        emit('update_online_list', broadcast=True)
        # Mesaj geçmişi
        msgs = Message.query.all()
        history = []
        for m in msgs:
            u = User.query.filter_by(username=m.sender).first()
            history.append({'id':m.id,'sender':m.sender,'avatar':u.avatar if u else '','content':m.content,'type':m.msg_type,'time':m.timestamp})
        emit('load_history', history)
        send_stories()

@socketio.on('update_avatar')
def update_ava(data):
    current_user.avatar = data['avatar']
    db.session.commit()
    emit('force_avatar_update', {'username':current_user.username, 'new_avatar':data['avatar']}, broadcast=True)

@socketio.on('update_bg')
def update_bg(data):
    current_user.bg_image = data['bg']
    db.session.commit()

@socketio.on('send_msg')
def handle_msg(data):
    m = Message(sender=current_user.username, content=data['content'], msg_type=data['type'], timestamp=datetime.now().strftime("%H:%M"))
    db.session.add(m); db.session.commit()
    emit('new_msg', {'id':m.id,'sender':m.sender,'avatar':current_user.avatar,'content':m.content,'type':m.msg_type,'time':m.timestamp}, broadcast=True)

@socketio.on('add_story')
def add_st(data):
    st = Story(username=current_user.username, content=data['content'], media_type=data['type'], audio=data.get('audio', ""))
    db.session.add(st); db.session.commit()
    send_stories()

@socketio.on('view_story')
def view_st(data):
    st = db.session.get(Story, data['id'])
    if st:
        views = json.loads(st.views)
        if current_user.username not in views:
            views.append(current_user.username)
            st.views = json.dumps(views)
            db.session.commit()
            send_stories()

def send_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        u = User.query.filter_by(username=s.username).first()
        if s.username not in grouped: grouped[s.username] = []
        grouped[s.username].append({
            'id':s.id, 'username':s.username, 'avatar':u.avatar if u else '',
            'content':s.content, 'type':s.media_type, 'audio':s.audio, 'views':json.loads(s.views)
        })
    emit('all_stories', grouped, broadcast=True)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        u = User(username=request.form['username'], password=request.form['password'], gender=request.form['gender'], avatar=request.form['avatar_data'])
        db.session.add(u); db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
