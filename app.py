import eventlet
eventlet.monkey_patch(all=True)

import os
from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'render-safe-key-2026'

# --- VERİTABANI YOLU (Hata Veren Bölge) ---
# Render'da en güvenli yol budur: /tmp dizini bazen daha iyi sonuç verir 
# ama biz önce ana dizinde mutlak yol (absolute path) ile zorlayacağız.
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

# Uygulama Başlarken Tabloları Manuel Oluşturma Fonksiyonu
def init_db():
    with app.app_context():
        db.create_all()

# Rotalar
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            uname = request.form.get('username')
            pwd = request.form.get('password')
            if uname and pwd:
                user_exists = User.query.filter_by(username=uname).first()
                if not user_exists:
                    new_user = User(username=uname, password=pwd)
                    db.session.add(new_user)
                    db.session.commit()
                    return redirect(url_for('login'))
        except Exception as e:
            print(f"Kayıt Hatası: {e}")
            return "Veritabanı hatası! Lütfen sayfayı yenileyip tekrar deneyin.", 500
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            user = User.query.filter_by(username=request.form.get('username')).first()
            if user and user.password == request.form.get('password'):
                login_user(user)
                return redirect(url_for('chat'))
        except Exception as e:
            print(f"Giriş Hatası: {e}")
            return "Giriş yapılamadı!", 500
    return render_template('login.html')

@app.route('/chat')
@login_required
def chat():
    # Chat sayfasını render ederken hata almamak için sessiz bir sorgu yapıyoruz
    history = []
    try:
        messages = Message.query.all()
        for m in messages:
            sender = User.query.filter_by(username=m.username).first()
            history.append({
                'id': m.id, 'username': m.username, 'content': m.content,
                'type': m.type, 'timestamp': m.timestamp,
                'avatar': sender.avatar if sender else ''
            })
    except:
        pass
    return render_template('chat.html', user=current_user, history=history)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@socketio.on('message')
def handle_msg(data):
    if current_user.is_authenticated:
        now = datetime.now().strftime("%H:%M")
        new_m = Message(username=current_user.username, content=data['msg'], type=data.get('type', 'text'), timestamp=now)
        db.session.add(new_m)
        db.session.commit()
        emit('message', {'id': new_m.id, 'user': current_user.username, 'msg': data['msg'], 'time': now, 'type': data.get('type', 'text'), 'avatar': current_user.avatar or ''}, broadcast=True)

# Sunucu Başlatma
init_db() # Tabloları hemen oluştur
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
