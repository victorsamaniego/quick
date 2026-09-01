import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Seguridad
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'quickgo-secret-key-production-2026'
    
    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hora
    
    # Base de datos
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = database_url or f'sqlite:///{os.path.join(BASE_DIR, "pods_luxury.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Sesiones
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Upload de imágenes
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
  
    
    # OTP Settings
    OTP_EXPIRY_MINUTES = 10
    
    # SocketIO
    SOCKETIO_ASYNC_MODE = os.environ.get('SOCKETIO_ASYNC_MODE', 'threading')
