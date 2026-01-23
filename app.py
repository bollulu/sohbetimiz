from gevent import monkey
monkey.patch_all()

import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'whatsapp_ultra_v4'
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
    msg_type = db.Column(db.String(20))
    timestamp = db.Column(db.String(20))
    is_read = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user); return redirect(url_for('chat'))
    return render_template('login.html')

@socketio.on('connect')
def connect():
    if current_user.is_authenticated:
        msgs = Message.query.all()
        history = [{'id':m.id,'sender':m.sender,'content':m.content,'type':m.msg_type,'time':m.timestamp,'is_read':m.is_read} for m in msgs]
        emit('load_history', history)

@socketio.on('send_msg')
def handle_msg(data):
    m = Message(sender=current_user.username, content=data['content'], msg_type=data['type'], timestamp=datetime.now().strftime("%H:%M"))
    db.session.add(m); db.session.commit()
    emit('new_msg', {'id':m.id,'sender':m.sender,'avatar':current_user.avatar,'content':m.content,'type':m.msg_type,'time':m.timestamp}, broadcast=True)

@socketio.on('delete_msg')
def delete_msg(data):
    m = db.session.get(Message, data['id'])
    if m and m.sender == current_user.username:
        db.session.delete(m); db.session.commit()
        emit('msg_deleted', {'id': data['id']}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
