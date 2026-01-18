import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.secret_key = "faz28secret"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chat.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet"
)

# MODELLER
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    text = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ROUTES
@app.route("/", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        session["username"] = request.form["username"]
        return redirect("/chat")
    return render_template("auth.html")

@app.route("/chat")
def chat():
    if "username" not in session:
        return redirect("/")
    messages = Message.query.order_by(Message.timestamp).all()
    return render_template("chat.html", messages=messages, username=session["username"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# SOCKET EVENTS
@socketio.on("send_message")
def handle_message(data):
    msg = Message(username=data["username"], text=data["message"])
    db.session.add(msg)
    db.session.commit()

    emit("receive_message", {
        "username": data["username"],
        "message": data["message"]
    }, broadcast=True)

# MAIN
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app)
