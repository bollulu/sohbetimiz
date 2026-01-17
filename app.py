from gevent import monkey
monkey.patch_all()
import os, json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sohbetimiz_v5_full'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

# --- KRİTİK AYAR: 1 GB LİMİT ---
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024 

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- STABİLİZE EDİLMİŞ MODELLER ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password = db.Column(db.String(100), nullable=False)
    avatar = db.Column(db.Text)
    blocked_users = db.Column(db.Text, default='[]')
    # İlişkiler: Kullanıcı silinirse her şeyi silinir (Cascade)
    stories = db.relationship('Story', backref='owner', lazy=True, cascade="all, delete-orphan")

class Group(db.Model):
    __tablename__ = 'groups'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=True)
    admin = db.Column(db.String(50))

class Story(db.Model):
    __tablename__ = 'stories'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    username = db.Column(db.String(50))
    user_avatar = db.Column(db.Text)
    content = db.Column(db.Text, nullable=False)
    media_type = db.Column(db.String(10)) # image/video
    audio_data = db.Column(db.Text, nullable=True)
    viewers = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

# --- ROUTES ---
@app.route('/register', methods=['POST'])
def register():
    u, p, a = request.form.get('username'), request.form.get('password'), request.form.get('avatar_data')
    if User.query.filter_by(username=u).first():
        return "Bu kullanıcı adı zaten var", 400
    
    # Avatar boşsa varsayılan ata
    if not a: a = "https://cdn-icons-png.flaticon.com/512/149/149071.png"
    
    new_user = User(username=u, password=p, avatar=a)
    db.session.add(new_user)
    db.session.commit()
    login_user(new_user)
    return redirect(url_for('chat'))

@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    db.session.delete(current_user)
    db.session.commit()
    logout_user()
    return redirect(url_for('index'))

# Chat ve diğer socket fonksiyonları önceki stabil sürümle aynı kalacak...
