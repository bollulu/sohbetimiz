from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ultra_safe_story_v5'
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024 

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text)

class Story(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text)  # Base64 Verisi
    media_type = db.Column(db.String(20)) # 'image' veya 'video'
    music = db.Column(db.Text, default="") # Müzik Base64
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# Login/Auth süreçleri aynı kalıyor...
@app.route('/chat')
@login_required
def chat(): return render_template('chat.html', user=current_user)

@socketio.on('add_story')
def add_story(data):
    new_s = Story(
        username=current_user.username,
        user_avatar=current_user.avatar,
        content=data['content'],
        media_type=data['type'],
        music=data.get('music', '')
    )
    db.session.add(new_s)
    db.session.commit()
    send_all_stories()

@socketio.on('delete_story')
def delete_story(data):
    s = db.session.get(Story, data['id'])
    if s and s.username == current_user.username:
        db.session.delete(s)
        db.session.commit()
        send_all_stories()

def send_all_stories():
    stories = Story.query.order_by(Story.timestamp.asc()).all()
    output = {}
    for s in stories:
        if s.username not in output:
            output[s.username] = {"avatar": s.user_avatar, "items": []}
        output[s.username]["items"].append({
            "id": s.id, "content": s.content, "type": s.media_type, "music": s.music
        })
    emit('all_stories', output, broadcast=True)

# Gerekli diğer route'lar (login, register, logout) önceki kodla aynı kalsın.
