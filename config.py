import os
from datetime import timedelta
from dotenv import load_dotenv

# 🔐 Cargar variables de entorno desde archivo .env
load_dotenv()

class Config:
    # 🔐 Seguridad
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'quickgo-secret-key-production-2026'
    
    # 🗄️ Base de datos
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.join(BASE_DIR, "pods_luxury.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ⏱️ Sesiones
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # 📁 Upload de imágenes
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # 📧 Email (SMTP)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', '1']
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@quickgo.com')
    
    # 🔢 OTP Settings
    OTP_EXPIRY_MINUTES = 10
    
    # 🔌 SocketIO
    SOCKETIO_ASYNC_MODE = 'threading'