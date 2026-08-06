from flask import Flask, session, render_template, request, current_app, jsonify, url_for
from flask_mail import Mail
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
from models import db, User, Order
from routes import main_bp, admin_bp, delivery_bp, super_admin_bp
from extensions import limiter
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
    print("✅ Cloudinary configurado correctamente")
except Exception as e:
    print(f"⚠️ Error configurando Cloudinary: {e}")

# ============ LOGGING DE SEGURIDAD ============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('security.log'),
        logging.StreamHandler()
    ]
)
security_logger = logging.getLogger('security')

# Inicializar extensiones
mail = Mail()
socketio = SocketIO(cors_allowed_origins="*")
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
        print("✅ Conectado a PostgreSQL (Railway)")
    else:
        # Desarrollo local con SQLite
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quickgo.db'
        print("✅ Usando SQLite local (desarrollo)")
    
    # 🔥 CRÍTICO: Cookies seguras en producción
    if os.environ.get('FLASK_ENV') == 'production' or database_url:
        app.config['SESSION_COOKIE_SECURE'] = True
        app.config['REMEMBER_COOKIE_SECURE'] = True
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        print("🔒 Cookies seguras activadas (HTTPS)")
    
    # Crear carpetas necesarias (para compatibilidad local)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads', 'receipts'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads', 'logos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'icons'), exist_ok=True)
    
    # Inicializar extensiones
    db.init_app(app)
    mail.init_app(app)
    
    # 🔥 CORREGIDO: SocketIO detecta automáticamente el mejor modo (gevent/threading)
    socketio.init_app(app, cors_allowed_origins="*")
    
    login_manager.init_app(app)
    limiter.init_app(app)
    
    # Configurar LoginManager
    login_manager.login_view = 'main.login'
    login_manager.login_message = 'Debés iniciar sesión para acceder a esta página.'
    login_manager.login_message_category = 'warning'
    
    # Flask-Login: cargar usuario
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
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
        
        # Previene MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        
        # Activa el filtro XSS del navegador
        response.headers['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Política de seguridad de contenido (CSP) - Agregado unpkg.com para Leaflet
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.socket.io https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com; "
            "font-src 'self' https://fonts.gstatic.com https://unpkg.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: ws: https://unpkg.com https://cdn.socket.io;"
        )
        
        # Fuerza HTTPS en producción
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        # Prevenir caché de páginas sensibles
        if request.path.startswith('/admin') or request.path.startswith('/super-admin'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
        
        return response
    
    # ============ LOGGING DE SEGURIDAD ============
    @app.before_request
    def log_request():
        """Registra todas las peticiones para auditoría"""
        if request.method in ['POST', 'PUT', 'DELETE']:
            security_logger.info(
                f"Petición {request.method} a {request.path} desde {request.remote_addr}"
            )
    
    # Error handlers mejorados
    @app.errorhandler(404)
    def not_found_error(error):
        security_logger.warning(f"404 - {request.path} desde {request.remote_addr}")
        return render_template('error.html', error_code=404, message='Pagina no encontrada'), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        security_logger.warning(f"403 - Acceso denegado a {request.path} desde {request.remote_addr}")
        return render_template('error.html', error_code=403, message='Acceso denegado'), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        security_logger.error(f"500 - Error interno en {request.path}")
        return render_template('error.html', error_code=500, message='Error interno del servidor'), 500
    
    @app.errorhandler(429)
    def ratelimit_handler(e):
        security_logger.warning(f"Rate limit excedido en {request.path} desde {request.remote_addr}")
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
    
    # ============ SOCKETIO EVENTS ============
    
    @socketio.on('connect')
    def handle_connect():
        print(f'✅ Cliente conectado: {request.sid}')
        security_logger.info(f"SocketIO conectado: {request.sid} desde {request.remote_addr}")
    
    @socketio.on('disconnect')
    def handle_disconnect():
        print(f'❌ Cliente desconectado: {request.sid}')
    
    @socketio.on('join_admin_room')
    def handle_join_admin(data):
        if current_user.is_authenticated and current_user.is_admin:
            join_room('admin')
            print(f'Admin {current_user.email} se unio a admin room')
            emit('admin_connected', {'status': 'connected'}, room=request.sid)
        else:
            security_logger.warning(f"Intento de unirse a admin room sin permisos: {request.sid}")
    
    @socketio.on('join_user_room')
    def handle_join_user(data):
        if current_user.is_authenticated:
            user_id = data.get('user_id')
            if user_id == current_user.id:
                join_room(f'user_{user_id}')
                print(f'Usuario {current_user.email} se unio a user_{user_id}')
                emit('user_connected', {'status': 'connected'}, room=request.sid)
            else:
                security_logger.warning(f"Intento de unirse a room de otro usuario: {request.sid}")
    
    @socketio.on('join_delivery_room')
    def handle_join_delivery(data):
        if current_user.is_authenticated and current_user.is_delivery:
            user_id = data.get('user_id')
            if user_id == current_user.id:
                join_room(f'delivery_{user_id}')
                print(f'Delivery {current_user.email} se unio a delivery_{user_id}')
                emit('delivery_connected', {'status': 'connected'}, room=request.sid)
            else:
                security_logger.warning(f"Intento de unirse a room de otro delivery: {request.sid}")
    
    @socketio.on('request_order_update')
    def handle_order_update(data):
        if current_user.is_authenticated:
            order_id = data.get('order_id')
            order = Order.query.get(order_id)
            if order and order.user_id == current_user.id:
                emit('order_status_update', {
                    'order_id': order.id,
                    'status': order.status,
                    'status_label': order.status_label,
                    'status_color': order.status_color
                }, room=request.sid)
            else:
                security_logger.warning(f"Intento de acceder a pedido ajeno: {request.sid}")
    
    # ========== SOCKETIO EVENTS - GEOLOCALIZACION ==========
    
    @socketio.on('user_location_update')
    def handle_user_location(data):
        user_id = data.get('user_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if user_id and latitude and longitude:
            # Validar coordenadas
            try:
                lat = float(latitude)
                lon = float(longitude)
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    security_logger.warning(f"Coordenadas inválidas: {lat}, {lon}")
                    return
            except (ValueError, TypeError):
                security_logger.warning(f"Coordenadas no válidas: {latitude}, {longitude}")
                return
            
            emit('client_location_update', {
                'user_id': user_id,
                'latitude': latitude,
                'longitude': longitude,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }, room='admin')
    
    @socketio.on('delivery_location_update')
    def handle_delivery_location(data):
        order_id = data.get('order_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if order_id and latitude and longitude:
            emit('delivery_location_update', {
                'order_id': order_id,
                'latitude': latitude,
                'longitude': longitude,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }, room=f'order_{order_id}')
    
    @socketio.on('join_order_room')
    def handle_join_order_room(data):
        if current_user.is_authenticated:
            order_id = data.get('order_id')
            if order_id:
                join_room(f'order_{order_id}')
                print(f'Usuario {current_user.email} se unio a order_{order_id}')
    
    # ========== SOCKETIO EVENTS - CHAT Y DELIVERY REQUESTS ==========
    
    @socketio.on('join')
    def handle_join(data):
        """Unirse a una room específica (para chat o notificaciones)"""
        room = data.get('room')
        if room and current_user.is_authenticated:
            join_room(room)
            print(f'✅ Usuario {current_user.email} se unió a room: {room}')
            emit('joined_room', {'room': room, 'user': current_user.email}, room=room)
    
    @socketio.on('leave')
    def handle_leave(data):
        """Salir de una room específica"""
        room = data.get('room')
        if room and current_user.is_authenticated:
            leave_room(room)
            print(f'❌ Usuario {current_user.email} salió de room: {room}')
    
    @socketio.on('new_delivery_request')
    def handle_new_delivery_request(data):
        """Notificar al delivery sobre nueva solicitud de pedido"""
        request_id = data.get('request_id')
        order_id = data.get('order_id')
        print(f'📦 Nueva solicitud de delivery #{request_id} para pedido #{order_id}')
    
    @socketio.on('delivery_request_accepted')
    def handle_delivery_request_accepted(data):
        """Notificar al negocio que el delivery aceptó el pedido"""
        request_id = data.get('request_id')
        order_id = data.get('order_id')
        driver_name = data.get('driver_name')
        print(f'✅ Delivery aceptó solicitud #{request_id} para pedido #{order_id} - Driver: {driver_name}')
    
    @socketio.on('delivery_request_rejected')
    def handle_delivery_request_rejected(data):
        """Notificar al negocio que el delivery rechazó el pedido"""
        request_id = data.get('request_id')
        order_id = data.get('order_id')
        print(f'❌ Delivery rechazó solicitud #{request_id} para pedido #{order_id}')
    
    @socketio.on('new_chat_message')
    def handle_new_chat_message(data):
        """Manejar nuevos mensajes de chat"""
        order_id = data.get('order_id')
        message = data.get('message')
        if order_id and message:
            print(f'💬 Nuevo mensaje en chat del pedido #{order_id}: {message.get("message", "")[:50]}...')
    
    return app


# Instancia de la app para ejecutar
app = create_app()

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)