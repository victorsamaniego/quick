from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta
import random
import string

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    username = db.Column(db.String(80), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    security_question_id = db.Column(db.Integer, db.ForeignKey('security_questions.id'), nullable=True)
    security_answer_hash = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    is_delivery = db.Column(db.Boolean, default=False)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=True)
    theme_color = db.Column(db.String(20), default='gold')
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    security_question = db.relationship('SecurityQuestion', foreign_keys=[security_question_id], lazy=True)
    orders = db.relationship('Order', backref='customer', lazy=True, foreign_keys='Order.user_id')
    delivery_orders = db.relationship('Order', backref='driver', lazy=True, foreign_keys='Order.delivery_driver_id')
    otp_codes = db.relationship('OTPCode', backref='user', lazy=True, cascade='all, delete-orphan')
    business = db.relationship('Business', back_populates='admin_user', lazy=True)
    received_notifications = db.relationship('NotificationRecipient', foreign_keys='NotificationRecipient.user_id', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def set_security_answer(self, answer):
        if answer:
            self.security_answer_hash = generate_password_hash(answer.strip().lower())
    
    def check_security_answer(self, answer):
        if not self.security_answer_hash or not answer:
            return False
        return check_password_hash(self.security_answer_hash, answer.strip().lower())
    
    @staticmethod
    def validate_strong_password(password):
        errors = []
        if len(password) < 8:
            errors.append('Mínimo 8 caracteres')
        if not any(c.isupper() for c in password):
            errors.append('Debe tener al menos una mayúscula')
        if not any(c.islower() for c in password):
            errors.append('Debe tener al menos una minúscula')
        if not any(c.isdigit() for c in password):
            errors.append('Debe tener al menos un número')
        if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?/' for c in password):
            errors.append('Debe tener al menos un signo (!@#$%^&* etc)')
        return errors
    
    def get_pending_order(self):
        return Order.query.filter_by(user_id=self.id, status='pending').first()
    
    @property
    def is_customer(self):
        return not self.is_admin and not self.is_delivery and not self.is_super_admin
    
    @property
    def business_name(self):
        return self.business.name if self.business else None
    
    @property
    def display_name(self):
        return self.username or self.email.split('@')[0]
    
    @staticmethod
    def find_nearby_deliveries(latitude, longitude, radius_km, business_id=None):
        from math import radians, sin, cos, sqrt, atan2
        query = User.query.filter_by(is_delivery=True, is_active=True)
        active_delivery_ids = db.session.query(Order.delivery_driver_id).filter(
            Order.status.in_(['pending', 'shipped'])
        ).all()
        active_delivery_ids = [id[0] for id in active_delivery_ids if id[0]]
        if active_delivery_ids:
            query = query.filter(~User.id.in_(active_delivery_ids))
        deliveries = query.all()
        nearby_deliveries = []
        R = 6371
        for delivery in deliveries:
            if delivery.latitude and delivery.longitude:
                lat1, lon1 = radians(latitude), radians(longitude)
                lat2, lon2 = radians(delivery.latitude), radians(delivery.longitude)
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                c = 2 * atan2(sqrt(a), sqrt(1-a))
                distance = R * c
                if distance <= radius_km:
                    nearby_deliveries.append({
                        'delivery': delivery,
                        'distance': round(distance, 2)
                    })
        nearby_deliveries.sort(key=lambda x: x['distance'])
        return nearby_deliveries
    
    def __repr__(self):
        return f'<User {self.username or self.email}>'

class SecurityQuestion(db.Model):
    __tablename__ = 'security_questions'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(200), nullable=False, unique=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def __repr__(self):
        return f'<SecurityQuestion {self.question[:30]}...>'
    
    @staticmethod
    def get_random_question(exclude_ids=None):
        query = SecurityQuestion.query.filter_by(is_active=True)
        if exclude_ids:
            query = query.filter(~SecurityQuestion.id.in_(exclude_ids))
        questions = query.all()
        if questions:
            return random.choice(questions)
        return None
    
    @staticmethod
    def seed_default_questions():
        default_questions = [
            "¿Cómo se llama tu mascota favorita?",
            "¿Cuál es el nombre de tu escuela primaria?",
            "¿En qué ciudad naciste?",
            "¿Cuál es tu comida favorita?",
            "¿Cuál es el nombre de tu primer mejor amigo?",
            "¿Cuál es tu película favorita de la infancia?",
            "¿En qué mes conociste a tu mejor amigo?",
            "¿Cuál es el nombre de tu primo/a mayor?",
            "¿Cuál era tu apodo en la infancia?",
            "¿Cuál es el nombre de la calle donde creciste?",
            "¿Cuál es tu deporte favorito?",
            "¿Cuál es el nombre de tu primer profesor/a?",
            "¿En qué país te gustaría vivir?",
            "¿Cuál es tu color favorito?",
            "¿Cuál es el nombre de tu tío/a favorito/a?",
            "¿Cuál fue tu primer trabajo?",
            "¿Cuál es tu canción favorita?",
            "¿Cuál es el nombre de tu barrio?",
            "¿Cuál es tu libro favorito?",
            "¿Cuál es el nombre de tu abuelo/a materno/a?"
        ]
        created_count = 0
        for q in default_questions:
            existing = SecurityQuestion.query.filter_by(question=q).first()
            if not existing:
                new_q = SecurityQuestion(question=q)
                db.session.add(new_q)
                created_count += 1
        db.session.commit()
        return created_count

class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    logo_url = db.Column(db.String(500), nullable=True)  # 🔥 CAMBIADO a 500
    phone = db.Column(db.String(20))
    address = db.Column(db.String(255))
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    delivery_radius_km = db.Column(db.Float, default=10.0)
    is_quickgold = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    requires_subscription = db.Column(db.Boolean, default=True)
    subscription_exempt_reason = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    commission_rate = db.Column(db.Float, default=0.10)
    delivery_fee_base = db.Column(db.Float, default=5000)
    delivery_fee_per_km = db.Column(db.Float, default=1000)
    total_sales = db.Column(db.Float, default=0)
    total_orders = db.Column(db.Integer, default=0)
    total_products = db.Column(db.Integer, default=0)
    monthly_fee = db.Column(db.Float, default=0.0)
    billing_start = db.Column(db.Date, nullable=True)
    billing_end = db.Column(db.Date, nullable=True)
    subscription_status = db.Column(db.String(20), default='pending')
    activation_code = db.Column(db.String(50), nullable=True)
    code_expires_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    admin_user = db.relationship('User', back_populates='business', lazy=True, uselist=False)
    products = db.relationship('Product', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('Order', lazy=True)
    categories = db.relationship('Category', lazy=True)
    delivery_drivers = db.relationship('User', lazy=True,
                                      primaryjoin="and_(User.business_id==Business.id, User.is_delivery==True)",
                                      overlaps="business")
    
    @property
    def revenue_last_30_days(self):
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        result = db.session.query(db.func.sum(Order.total_amount)).filter(
            Order.business_id == self.id,
            Order.status == 'delivered',
            Order.created_at >= thirty_days_ago
        ).scalar()
        return result or 0
    
    @property
    def orders_last_30_days(self):
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        return Order.query.filter(
            Order.business_id == self.id,
            Order.created_at >= thirty_days_ago
        ).count()
    
    @property
    def active_products_count(self):
        return Product.query.filter_by(business_id=self.id, is_active=True).count()
    
    @property
    def platform_commission(self):
        return self.total_sales * self.commission_rate
    
    def __repr__(self):
        return f'<Business {self.name}>'

class OTPCode(db.Model):
    __tablename__ = 'otp_codes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    purpose = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    used = db.Column(db.Boolean, default=False)
    
    @staticmethod
    def generate_code():
        return ''.join(random.choices(string.digits, k=6))
    
    def is_expired(self, expiry_minutes=10):
        return datetime.now(timezone.utc) > self.created_at + timedelta(minutes=expiry_minutes)
    
    def __repr__(self):
        return f'<OTPCode {self.code} for user {self.user_id}>'

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    products = db.relationship('Product', backref='category', lazy=True)
    
    @property
    def active_products_count(self):
        return Product.query.filter_by(category_id=self.id, is_active=True).count()
    
    def __repr__(self):
        return f'<Category {self.name}>'

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    precio_compra = db.Column(db.Float, nullable=False, default=0)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False, index=True)
    image_url = db.Column(db.String(500))  # 🔥 CAMBIADO a 500
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    order_items = db.relationship('OrderItem', lazy=True)
    
    @property
    def ganancia_unitaria(self):
        return self.price - self.precio_compra
    
    @property
    def margen_ganancia(self):
        if self.precio_compra > 0:
            return ((self.price - self.precio_compra) / self.precio_compra) * 100
        return 0
    
    @property
    def valor_inventario(self):
        return self.precio_compra * self.stock
    
    @property
    def ganancia_potencial(self):
        return self.ganancia_unitaria * self.stock
    
    @property
    def valor_venta_total(self):
        return self.price * self.stock
    
    @property
    def is_low_stock(self):
        return self.stock < 10
    
    @property
    def is_available(self):
        return self.is_active and self.stock > 0
    
    @property
    def stock_status(self):
        if self.stock == 0:
            return 'sin_stock'
        elif self.stock < 10:
            return 'bajo'
        elif self.stock < 30:
            return 'medio'
        else:
            return 'completo'
    
    @property
    def stock_status_color(self):
        colors = {
            'sin_stock': 'secondary',
            'bajo': 'danger',
            'medio': 'warning',
            'completo': 'success'
        }
        return colors.get(self.stock_status, 'secondary')
    
    @property
    def business_name(self):
        return self.business.name if self.business else 'Sin negocio'
    
    def __repr__(self):
        return f'<Product {self.name}>'

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    product_name = db.Column(db.String(200), nullable=True)
    quantity = db.Column(db.Integer, default=1)
    price_at_purchase = db.Column(db.Float, nullable=False)
    
    order = db.relationship('Order', backref='order_items_list', lazy=True)
    product = db.relationship('Product', lazy=True)
    
    @property
    def subtotal(self):
        return self.quantity * self.price_at_purchase
    
    @property
    def ganancia_item(self):
        if self.product and self.product.precio_compra:
            return (self.price_at_purchase - self.product.precio_compra) * self.quantity
        return 0
    
    def __repr__(self):
        return f'<OrderItem {self.quantity}x {self.product_name or self.product_id}>'

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False, index=True)
    delivery_driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='pending')
    total_amount = db.Column(db.Float, nullable=False)
    shipping_address = db.Column(db.String(500), nullable=False)
    shipping_phone = db.Column(db.String(20), nullable=False)
    shipping_reference = db.Column(db.String(200))
    client_latitude = db.Column(db.Float)
    client_longitude = db.Column(db.Float)
    delivery_latitude = db.Column(db.Float)
    delivery_longitude = db.Column(db.Float)
    delivery_fee = db.Column(db.Float, default=0)
    driver_arrived = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    delivered_at = db.Column(db.DateTime)
    payment_method = db.Column(db.String(20), default='cash')
    cash_bill_amount = db.Column(db.Float, default=0.0)
    needs_change = db.Column(db.Boolean, default=False)
    payment_receipt_url = db.Column(db.String(500), nullable=True)  # 🔥 CAMBIADO a 500
    
    @property
    def items_list(self):
        return [{
            'product_name': item.product_name or (item.product.name if item.product else 'Producto eliminado'),
            'quantity': item.quantity,
            'price': item.price_at_purchase,
            'subtotal': item.subtotal,
            'ganancia': item.ganancia_item
        } for item in self.order_items_list]
    
    @property
    def status_label(self):
        labels = {
            'pending': '⏳ Pendiente',
            'shipped': '🚚 Enviado',
            'delivered': '✅ Entregado',
            'cancelled': '❌ Cancelado'
        }
        return labels.get(self.status, self.status)
    
    @property
    def status_color(self):
        colors = {
            'pending': 'warning',
            'shipped': 'info',
            'delivered': 'success',
            'cancelled': 'danger'
        }
        return colors.get(self.status, 'secondary')
    
    @property
    def driver_arrived_label(self):
        if self.driver_arrived:
            return '🎉 ¡Delivery llegó!'
        elif self.status == 'shipped':
            return '🛵 En camino'
        else:
            return '⏳ Pendiente'
    
    @property
    def ganancia_obtenida(self):
        ganancia = 0
        for item in self.order_items_list:
            if item.product and item.product.precio_compra:
                ganancia += (item.price_at_purchase - item.product.precio_compra) * item.quantity
        return ganancia
    
    @property
    def platform_commission(self):
        if self.business and self.business.commission_rate:
            return self.total_amount * self.business.commission_rate
        return 0
    
    @property
    def net_revenue_for_business(self):
        return self.total_amount - self.platform_commission
    
    @property
    def distance_to_client(self):
        if self.delivery_latitude and self.client_latitude:
            try:
                from services.geolocation import calcular_distancia_km
                return calcular_distancia_km(
                    self.delivery_latitude, self.delivery_longitude,
                    self.client_latitude, self.client_longitude
                )
            except:
                return None
        return None
    
    @property
    def business_name(self):
        return self.business.name if self.business else 'Sin negocio'
    
    def __repr__(self):
        return f'<Order #{self.id} - {self.status}>'

class DeliveryRequest(db.Model):
    __tablename__ = 'delivery_requests'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(20), default='pending')
    search_radius = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())
    accepted_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    
    order = db.relationship('Order', backref='delivery_request', lazy=True)
    business = db.relationship('Business', lazy=True)
    driver = db.relationship('User', foreign_keys=[driver_id], lazy=True)
    
    @property
    def status_label(self):
        labels = {
            'pending': '⏳ Buscando delivery',
            'accepted': '✅ Aceptado',
            'rejected': '❌ Rechazado',
            'expired': '⌛ Expirado'
        }
        return labels.get(self.status, self.status)
    
    @property
    def status_color(self):
        colors = {
            'pending': 'warning',
            'accepted': 'success',
            'rejected': 'danger',
            'expired': 'secondary'
        }
        return colors.get(self.status, 'secondary')
    
    def is_expired(self):
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at
    
    def __repr__(self):
        return f'<DeliveryRequest #{self.id} - {self.status}>'

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())
    is_read = db.Column(db.Boolean, default=False)
    
    order = db.relationship('Order', backref='chat_messages', lazy=True)
    sender = db.relationship('User', foreign_keys=[sender_id], lazy=True)
    
    def to_dict(self):
        sender_role = 'customer'
        if self.order:
            if self.sender_id == self.order.user_id:
                sender_role = 'customer'
            elif self.order.delivery_driver_id and self.sender_id == self.order.delivery_driver_id:
                sender_role = 'delivery'
            elif self.sender.is_admin and self.sender.business_id == self.order.business_id:
                sender_role = 'business'
            elif self.sender.business_id == self.order.business_id:
                sender_role = 'business'
        
        py_timezone = timezone(timedelta(hours=-3))
        if self.created_at.tzinfo is None:
            created_at_utc = self.created_at.replace(tzinfo=timezone.utc)
        else:
            created_at_utc = self.created_at.astimezone(timezone.utc)
        local_time = created_at_utc.astimezone(py_timezone)
        
        return {
            'id': self.id,
            'order_id': self.order_id,
            'sender_id': self.sender_id,
            'sender_name': self.sender.email.split('@')[0],
            'sender_role': sender_role,
            'message': self.message,
            'created_at': local_time.strftime('%H:%M'),
            'created_at_full': local_time.strftime('%Y-%m-%d %H:%M:%S'),
            'created_at_utc': created_at_utc.isoformat(),
            'is_read': self.is_read
        }
    
    def __repr__(self):
        return f'<ChatMessage #{self.id} - Order {self.order_id}>'

class SupportChat(db.Model):
    __tablename__ = 'support_chats'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_from_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, default=False)
    
    business = db.relationship('Business', lazy=True)
    sender = db.relationship('User', foreign_keys=[sender_id], lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'business_id': self.business_id,
            'business_name': self.business.name if self.business else '',
            'sender_name': self.sender.display_name if self.sender else '',
            'message': self.message,
            'is_from_admin': self.is_from_admin,
            'created_at': self.created_at.strftime('%H:%M %d/%m'),
            'is_read': self.is_read
        }

class DeliveryBusinessChat(db.Model):
    __tablename__ = 'delivery_business_chats'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_from_delivery = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_read = db.Column(db.Boolean, default=False)
    
    order = db.relationship('Order', lazy=True)
    sender = db.relationship('User', foreign_keys=[sender_id], lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'sender_name': self.sender.display_name if self.sender else '',
            'message': self.message,
            'is_from_delivery': self.is_from_delivery,
            'created_at': self.created_at.strftime('%H:%M'),
            'is_read': self.is_read
        }

class UserMessage(db.Model):
    __tablename__ = 'user_messages'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    sender = db.relationship('User', foreign_keys=[sender_id], lazy=True)
    recipient = db.relationship('User', foreign_keys=[recipient_id], lazy=True, backref='received_messages')
    
    def __repr__(self):
        return f'<UserMessage {self.id} - Para {self.recipient_id}>'

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)
    sent_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_sent = db.Column(db.Boolean, default=False)
    
    sender = db.relationship('User', foreign_keys=[sent_by], lazy=True)
    recipients = db.relationship('NotificationRecipient', backref='notification', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Notification {self.title}>'

class NotificationRecipient(db.Model):
    __tablename__ = 'notification_recipients'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    notification_id = db.Column(db.Integer, db.ForeignKey('notifications.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)
    
    user = db.relationship('User', lazy=True)
    
    def __repr__(self):
        return f'<NotificationRecipient {self.user_id}>'