from gevent import monkey
monkey.patch_all()
import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whatsapp_ultra_v5'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'whatsapp_v5.db')
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 # 1GB Limit

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=1024 * 1024 * 1024)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    gender = db.Column(db.String(10)) # Erkek / Kiz
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) # text, image, video, audio
    timestamp = db.Column(db.String(10))
    is_read = db.Column(db.Boolean, default=False)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form.get('username')
        if not User.query.filter_by(username=u).first():
            gen = request.form.get('gender')
            # Varsayılan avatar cinsiyete göre
            def_avatar = "https://www.w3schools.com/howto/img_avatar.png" if gen == "Erkek" else "https://www.w3schools.com/howto/img_avatar2.png"
            new_u = User(username=u, password=request.form.get('password'), gender=gen, avatar=def_avatar)
            db.session.add(new_u); db.session.commit()
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@app.route('/logout')
def logout(): logout_user(); return redirect(url_for('login'))

online_users = {}

@socketio.on('join')
def on_join(data):
    join_room('Genel')
    online_users[current_user.username] = {"avatar": current_user.avatar, "sid": request.sid}
    emit('update_user_list', online_users, broadcast=True)
    send_stories()
    msgs = Message.query.all()
    history = [{'id':m.id,'user':m.username,'avatar':m.user_avatar,'msg':m.content,'type':m.msg_type,'time':m.timestamp,'read':m.is_read} for m in msgs]
    emit('history', history)

@socketio.on('message')
def handle_msg(data):
    now = datetime.now().strftime("%H:%M")
    msg = Message(username=current_user.username, user_avatar=current_user.avatar, content=data['msg'], msg_type=data.get('type','text'), timestamp=now)
    db.session.add(msg); db.session.commit()
    emit('message', {'id':msg.id,'user':current_user.username,'avatar':current_user.avatar,'msg':data['msg'],'type':msg.msg_type,'time':now,'read':False}, broadcast=True)

@socketio.on('mark_as_read')
def mark_read(data):
    msg = db.session.get(Message, data['id'])
    if msg:
        msg.is_read = True; db.session.commit()
        emit('msg_read_status', {'id': msg.id}, broadcast=True)

@socketio.on('delete_message')
def delete_msg(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.username == current_user.username:
        db.session.delete(msg); db.session.commit()
        emit('msg_deleted', {'id': data['id']}, broadcast=True)

@socketio.on('update_profile')
def update_profile(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    db.session.commit()
    online_users[current_user.username]['avatar'] = data['avatar']
    # Hikaye ve mesajlardaki avatarları da güncellemek için yayınla
    emit('update_user_list', online_users, broadcast=True)
    send_stories()

@socketio.on('add_story')
def add_story(data):
    new_s = Story(username=current_user.username, user_avatar=current_user.avatar, content=data['image'])
    db.session.add(new_s); db.session.commit(); send_stories()

@socketio.on('delete_story')
def del_story(data):
    Story.query.filter_by(id=data['id'], username=current_user.username).delete()
    db.session.commit(); send_stories()

def send_stories():
    stories = Story.query.order_by(Story.created_at.asc()).all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar': s.user_avatar, 'items': []}
        grouped[s.username]['items'].append({'id': s.id, 'content': s.content})
    emit('story_list', grouped, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
