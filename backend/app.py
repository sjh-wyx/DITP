import eventlet
eventlet.monkey_patch()

from dotenv import load_dotenv; load_dotenv()
from flask import Flask, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from database import db
from limiter_config import limiter
import os
import secrets

app = Flask(__name__, static_folder='../frontend', static_url_path='')

# === 安全加固：SECRET_KEY ===
_secret = os.getenv('SECRET_KEY', '')
if not _secret or _secret == 'dev-secret':
    _secret = secrets.token_hex(32)
    os.environ['SECRET_KEY'] = _secret
    print(f'[安全] 已自动生成强 SECRET_KEY')
app.config['SECRET_KEY'] = _secret

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('MYSQL_URL', 'sqlite:///datatutor.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# === 安全加固：请求体最大 1MB ===
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024

CORS(app, supports_credentials=True)
db.init_app(app)
redis_url = os.getenv('REDIS_URL')

# === 安全加固：全局限流器（Redis 后端） ===
app.config['RATELIMIT_STORAGE_URI'] = redis_url or 'memory://'
app.config['RATELIMIT_STRATEGY'] = 'fixed-window'
limiter.init_app(app)

socketio = SocketIO(app, cors_allowed_origins='*', message_queue=redis_url)

from routes.auth import auth_bp
from routes.courses import courses_bp
from routes.classes import classes_bp
from routes.progress import progress_bp
from routes.chat import chat_bp
from routes.ai import ai_bp
from routes.assessments import assessments_bp
from routes.reports import reports_bp
from routes.analytics import analytics_bp

app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(courses_bp, url_prefix='/api/courses')
app.register_blueprint(classes_bp, url_prefix='/api/classes')
app.register_blueprint(progress_bp, url_prefix='/api/progress')
app.register_blueprint(chat_bp, url_prefix='/api/chat')
app.register_blueprint(ai_bp, url_prefix='/api/ai')
app.register_blueprint(assessments_bp, url_prefix='/api/assessments')
app.register_blueprint(reports_bp, url_prefix='/api/reports')
app.register_blueprint(analytics_bp, url_prefix='/api/analytics')

from terminal_ws.terminal import register_terminal_handlers
register_terminal_handlers(socketio)

@socketio.on('join_report_room')
def on_join_report_room(data):
    from flask_socketio import join_room
    uid = data.get('user_id')
    if uid:
        join_room(f'student_{uid}')

try:
    from metrics import metrics_endpoint
    @app.route('/metrics')
    def metrics():
        return metrics_endpoint()
except ImportError:
    pass

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'login.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    print('DataTutor started on MySQL')
    socketio.run(app, host='0.0.0.0', port=80, allow_unsafe_werkzeug=True)
