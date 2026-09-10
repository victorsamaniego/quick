from flask import Flask, session, render_template, request, current_app, jsonify, url_for
from realtime import socketio, register_realtime
from flask_login import LoginManager, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
from models import db, User, Order
from routes import main_bp, admin_bp, delivery_bp, super_admin_bp
from extensions import limiter, csrf
from runtime_security import configure_runtime_security
from auth_identity import load_security_user
import os
import logging
from datetime import datetime, timezone
import cloudinary
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# ============ CONFIGURACIÓN DE CLOUDINARY ============
try:
    cloudinary.config(
        cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
        api_key=os.getenv('CLOUDINARY_API_KEY'),
        api_secret=os.getenv('CLOUDINARY_API_SECRET'),
        secure=True
    )
except Exception:
    logging.getLogger(__name__).warning('No se pudo configurar el proveedor de imágenes.')

# ============ LOGGING DE SEGURIDAD ============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
security_logger = logging.getLogger('security')

# Inicializar extensiones

login_manager = LoginManager()


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    
    # 🔥 CRÍTICO: Configurar base de datos para Railway (PostgreSQL)
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # Railway usa postgres://, pero SQLAlchemy requiere postgresql://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        # Desarrollo local con SQLite
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quickgo.db'
    
    configure_runtime_security(app)
    
    # Crear carpetas necesarias (para compatibilidad local)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads', 'receipts'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads', 'logos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'icons'), exist_ok=True)
    
    # Inicializar extensiones
    db.init_app(app)
   
    
    # 🔥 CORREGIDO: SocketIO detecta automáticamente el mejor modo (gevent/threading)
    socketio.init_app(app, max_http_buffer_size=65536)
    
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app)
    
    # Configurar LoginManager
    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Debés iniciar sesión para acceder a esta página.'
    login_manager.login_message_category = 'warning'
    
    # Flask-Login: cargar usuario
    @login_manager.user_loader
    def load_user(user_id):
        return load_security_user(user_id)
    
    # Registrar TODOS los blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(delivery_bp)
    app.register_blueprint(super_admin_bp)
    
    # 🔥 NUEVO: Filtro para mostrar imágenes de Cloudinary O locales
    @app.template_filter('smart_image')
    def smart_image(url_value):
        if not url_value:
            return url_for('static', filename='images/placeholder.png')
        if url_value.startswith('http'):
            return url_value  # Es de Cloudinary → usar tal cual
        return url_for('static', filename=url_value)  # Es local
    
    # Context processor con tema global
    @app.context_processor
    def inject_globals():
        theme = 'gold'
        if current_user.is_authenticated and current_user.theme_color:
            theme = current_user.theme_color
        
        return {
            'now': datetime.now(timezone.utc),
            'current_year': datetime.now(timezone.utc).year,
            'current_user': current_user,
            'current_theme': theme
        }
    
    # ============ SECURITY HEADERS ============
    @app.after_request
    def set_security_headers(response):
        # Evita que tu sitio sea embebido en iframes (anti-clickjacking)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=(self)'

        # Previene MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Legacy browser filters are not a substitute for CSP and escaping.
        response.headers['X-XSS-Protection'] = '0'
        
        # Referrer Policy
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        
        # Política de seguridad de contenido (CSP) - Agregado unpkg.com para Leaflet
        response.headers.setdefault('Content-Security-Policy', (
            "default-src 'self'; frame-ancestors 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.socket.io https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com; "
            "font-src 'self' https://fonts.gstatic.com https://unpkg.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: ws: https://unpkg.com https://cdn.socket.io;"
        ))
        
        # Fuerza HTTPS en producción
        if app.config['SECURITY_PRODUCTION']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        # Prevenir caché de páginas sensibles
        if request.endpoint != 'static' and (current_user.is_authenticated or request.path.startswith(('/admin', '/super-admin', '/delivery', '/recover', '/chat', '/api', '/order', '/cart', '/soporte'))):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
        
        return response
    
    # ============ LOGGING DE SEGURIDAD ============
    @app.before_request
    def log_request():
        """Registra todas las peticiones para auditoría"""
        if request.method in ['POST', 'PUT', 'DELETE']:
            security_logger.info(
                f"Petición {request.method} endpoint={request.endpoint}"
            )
    
    # Error handlers mejorados
    @app.errorhandler(404)
    def not_found_error(error):
        security_logger.warning('404 - endpoint no encontrado')
        return render_template('error.html', error_code=404, message='Pagina no encontrada'), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        security_logger.warning(f'403 - endpoint={request.endpoint}')
        return render_template('error.html', error_code=403, message='Acceso denegado'), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        security_logger.error(f'500 - endpoint={request.endpoint}')
        return render_template('error.html', error_code=500, message='Error interno del servidor'), 500
    
    @app.errorhandler(429)
    def ratelimit_handler(e):
        security_logger.warning(f'Rate limit excedido endpoint={request.endpoint}')
        return jsonify({
            'error': 'Demasiadas peticiones. Por favor, intentá de nuevo en unos minutos.'
        }), 429
    
    # Servir manifest.json con tipo correcto
    @app.route('/manifest.json')
    def manifest():
        response = current_app.send_static_file('manifest.json')
        response.headers['Content-Type'] = 'application/manifest+json'
        response.headers['Cache-Control'] = 'public, max-age=31536000'
        return response
    
    # Servir service worker con headers correctos
    @app.route('/sw.js')
    def service_worker():
        response = current_app.send_static_file('sw.js')
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Service-Worker-Allowed'] = '/'
        return response
    
    register_realtime(app)
    return app


# Instancia de la app para ejecutar
app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)
