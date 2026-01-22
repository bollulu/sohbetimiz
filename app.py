from gevent import monkey
monkey.patch_all()
import os, json
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'wa_ultra_fast_v1'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 # 500MB Limit

db = SQLAlchemy(app)
# Buffer size'ı yüksek tutarak dosya transferini kolaylaştırıyoruz
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent', max_http_buffer_size=500 * 1024 * 1024)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    avatar = db.Column(db.Text)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    msg_type = db.Column(db.String(20)) 
    timestamp = db.Column(db.String(20))

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)
    audio_data = db.Column(db.Text)
    media_type = db.Column(db.String(20))
    viewers = db.Column(db.Text, default='[]')

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
login_manager.login_view = 'login'
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

@app.route('/chat')
@login_required
def chat():
    msgs = Message.query.all()
    stories = get_grouped_stories()
    return render_template('chat.html', user=current_user, initial_msgs=msgs, initial_stories=stories)

# --- SOCKET EVENTLERI ---
@socketio.on('message')
def handle_msg(data):
    time_str = datetime.now().strftime("%H:%M")
    msg = Message(username=current_user.username, user_avatar=current_user.avatar, 
                  content=data['msg'], msg_type=data.get('type','text'), timestamp=time_str)
    db.session.add(msg)
    db.session.commit()
    # Sadece yeni mesajı gönder (Trafiği şişirme)
    emit('new_message', {'id':msg.id, 'user':msg.username, 'avatar':msg.user_avatar, 
                         'msg':msg.content, 'type':msg.msg_type, 'time':msg.timestamp}, broadcast=True)

@socketio.on('delete_message')
def del_msg(data):
    msg = db.session.get(Message, data['id'])
    if msg and msg.username == current_user.username:
        db.session.delete(msg)
        db.session.commit()
        emit('message_deleted', {'id': data['id']}, broadcast=True)

@socketio.on('add_story')
def add_story(data):
    story = Story(username=current_user.username, user_avatar=current_user.avatar,
                  content=data['content'], audio_data=data.get('music'), media_type=data.get('type'))
    db.session.add(story)
    db.session.commit()
    # Hikaye eklenince tüm listeyi yenile (Hikaye barı hafiftir)
    emit('story_update', get_grouped_stories(), broadcast=True)

@socketio.on('delete_story')
def delete_story(data):
    story = db.session.get(Story, data['id'])
    if story and story.username == current_user.username:
        db.session.delete(story)
        db.session.commit()
        emit('story_update', get_grouped_stories(), broadcast=True)

@socketio.on('update_profile')
def update_profile(data):
    user = db.session.get(User, current_user.id)
    user.avatar = data['avatar']
    # Tüm eski verileri güncelle
    Message.query.filter_by(username=user.username).update({'user_avatar': data['avatar']})
    Story.query.filter_by(username=user.username).update({'user_avatar': data['avatar']})
    db.session.commit()
    emit('profile_refreshed', {'username': user.username, 'avatar': data['avatar']}, broadcast=True)
    emit('story_update', get_grouped_stories(), broadcast=True)

@socketio.on('signal')
def call_signal(data):
    emit('signal', data, broadcast=True, include_self=False)

def get_grouped_stories():
    stories = Story.query.all()
    grouped = {}
    for s in stories:
        if s.username not in grouped: grouped[s.username] = {'avatar': s.user_avatar, 'items': []}
        grouped[s.username]['items'].append({'id':s.id, 'content':s.content, 'music':s.audio_data, 'type':s.media_type, 'viewers': json.loads(s.viewers)})
    return grouped

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
