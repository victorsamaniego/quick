from flask import Flask, session, render_template, request, current_app
from flask_mail import Mail
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, current_user
from config import Config
from models import db, User, Order
from routes import main_bp, admin_bp, delivery_bp, super_admin_bp
from extensions import limiter
import os
from datetime import datetime, timezone

# Inicializar extensiones
mail = Mail()
socketio = SocketIO(cors_allowed_origins="*")  # ✅ SIN eventlet
login_manager = LoginManager()


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    
    # Crear carpetas necesarias
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads', 'receipts'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'uploads', 'logos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'icons'), exist_ok=True)
    
    # Inicializar extensiones
    db.init_app(app)
    mail.init_app(app)
    
    # Configurar SocketIO según el entorno (threading para dev, eventlet para prod)
    async_mode = app.config.get('SOCKETIO_ASYNC_MODE', 'threading')
    socketio.init_app(app, async_mode=async_mode, cors_allowed_origins="*")
    
    login_manager.init_app(app)
    limiter.init_app(app)
    
    # Flask-Login: cargar usuario
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Registrar TODOS los blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(delivery_bp)
    app.register_blueprint(super_admin_bp)
    
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
    
    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error.html', error_code=404, message='Pagina no encontrada'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('error.html', error_code=500, message='Error interno del servidor'), 500
    
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
    
    # ========== SOCKETIO EVENTS ==========
    
    @socketio.on('connect')
    def handle_connect():
        print(f'Cliente conectado: {request.sid}')
    
    @socketio.on('disconnect')
    def handle_disconnect():
        print(f'Cliente desconectado: {request.sid}')
    
    @socketio.on('join_admin_room')
    def handle_join_admin(data):
        if current_user.is_authenticated and current_user.is_admin:
            join_room('admin')
            print(f'Admin {current_user.email} se unio a admin room')
            emit('admin_connected', {'status': 'connected'}, room=request.sid)
    
    @socketio.on('join_user_room')
    def handle_join_user(data):
        if current_user.is_authenticated:
            user_id = data.get('user_id')
            if user_id == current_user.id:
                join_room(f'user_{user_id}')
                print(f'Usuario {current_user.email} se unio a user_{user_id}')
                emit('user_connected', {'status': 'connected'}, room=request.sid)
    
    @socketio.on('join_delivery_room')
    def handle_join_delivery(data):
        if current_user.is_authenticated and current_user.is_delivery:
            user_id = data.get('user_id')
            if user_id == current_user.id:
                join_room(f'delivery_{user_id}')
                print(f'Delivery {current_user.email} se unio a delivery_{user_id}')
                emit('delivery_connected', {'status': 'connected'}, room=request.sid)
    
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
    
    # ========== SOCKETIO EVENTS - GEOLOCALIZACION ==========
    
    @socketio.on('user_location_update')
    def handle_user_location(data):
        user_id = data.get('user_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if user_id and latitude and longitude:
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