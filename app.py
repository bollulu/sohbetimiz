from gevent import monkey
monkey.patch_all()
import os, json
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sohbetimiz_v4_2026'
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

# HATANIN ÇÖZÜMÜ BURASI: 500 MB limit tanımlıyoruz
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024 

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# --- MODELLER ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    avatar = db.Column(db.Text) # Base64 veri burada tutulur
    blocked_users = db.Column(db.Text, default='[]')

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(50), nullable=True)
    admin = db.Column(db.String(50))

# Veritabanını oluştur
with app.app_context():
    db.create_all()

login_manager = LoginManager(app)
@login_manager.user_loader
def load_user(id): return db.session.get(User, int(id))

@app.route('/')
def index():
    return render_template('auth.html') if not current_user.is_authenticated else redirect(url_for('chat'))

@app.route('/login', methods=['POST'])
def login():
    u, p = request.form.get('username'), request.form.get('password')
    user = User.query.filter_by(username=u, password=p).first()
    if user: login_user(user); return redirect(url_for('chat'))
    return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    u = request.form.get('username')
    p = request.form.get('password')
    a = request.form.get('avatar_data')
    
    if not u or not p:
        return "Kullanıcı adı ve şifre gerekli", 400
        
    if not User.query.filter_by(username=u).first():
        # Eğer avatar seçilmediyse varsayılan ata
        if not a or len(a) < 100:
            a = "https://cdn-icons-png.flaticon.com/512/149/149071.png"
            
        new_u = User(username=u, password=p, avatar=a)
        db.session.add(new_u)
        db.session.commit()
        login_user(new_u)
        return redirect(url_for('chat'))
    return "Bu kullanıcı adı zaten alınmış", 400

@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html', user=current_user)

if __name__ == '__main__':
    socketio.run(app, debug=True)
