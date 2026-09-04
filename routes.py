from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, session, abort
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, timezone
import os
import secrets
import cloudinary.uploader
from functools import wraps
from math import radians, sin, cos, sqrt, atan2, isfinite
from models import db, User, Product, Category, Order, OrderItem, Business, DeliveryRequest, ChatMessage, SecurityQuestion, SupportChat, DeliveryBusinessChat, UserMessage, Notification, NotificationRecipient
from forms import (
    RegistrationForm, LoginForm, PasswordResetForm,
    ProductForm, OrderForm, AdminUserForm, CategoryForm, BusinessCoverageForm
)
from extensions import limiter

# Blueprints
main_bp = Blueprint('main', __name__)
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
delivery_bp = Blueprint('delivery', __name__, url_prefix='/delivery')
super_admin_bp = Blueprint('super_admin', __name__, url_prefix='/super-admin')


# ============ FUNCIÓN PARA CALCULAR DISTANCIA ============

def calcular_distancia_negocio_km(lat1, lon1, lat2, lon2):
    """Calcula distancia entre dos puntos en km (fórmula Haversine)"""
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c


# ============ DECORADORES DE SEGURIDAD ============

def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_super_admin:
            flash('Acceso denegado. Solo Super Admin.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def business_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Acceso denegado.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return f(*args, **kwargs)
        
        if current_user.is_delivery or current_user.is_super_admin:
            return f(*args, **kwargs)
        
        if current_user.is_admin and current_user.business:
            business = current_user.business
            now = datetime.now(timezone.utc).date()
            
            if hasattr(business, 'requires_subscription') and not business.requires_subscription:
                return f(*args, **kwargs)
            
            if business.billing_end and business.billing_end < now:
                business.subscription_status = 'expired'
                db.session.commit()
            
            if business.subscription_status != 'active':
                if request.endpoint not in ['main.activate_subscription', 'main.submit_activation_code']:
                    flash('Tu suscripcion ha expirado. Ingresa el codigo de activacion para continuar operando.', 'warning')
                    return redirect(url_for('main.activate_subscription'))
                    
        return f(*args, **kwargs)
    return decorated_function


# ============ UTILIDADES ============

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def upload_to_cloudinary(file_obj, folder='quickgo'):
    """Sube un archivo a Cloudinary y retorna la URL pública"""
    try:
        result = cloudinary.uploader.upload(
            file_obj,
            folder=folder,
            resource_type='auto'
        )
        return result['secure_url']
    except Exception as e:
        print(f"❌ Error subiendo a Cloudinary: {e}")
        return None


def get_featured_products(limit=8):
    return Product.query.filter_by(is_active=True).filter(Product.stock > 0)\
        .order_by(Product.created_at.desc()).limit(limit).all()


def get_recent_orders(user_id, limit=3):
    return Order.query.filter_by(user_id=user_id)\
        .order_by(Order.created_at.desc()).limit(limit).all()


def validar_coordenadas(latitude, longitude):
    latitude, longitude = float(latitude), float(longitude)
    if not (isfinite(latitude) and isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError('Coordenadas inválidas')
    return latitude, longitude


def leer_cobertura_negocio(form):
    latitude, longitude = validar_coordenadas(form.get('latitude'), form.get('longitude'))
    radius = float(form.get('delivery_radius_km', 10))
    if not isfinite(radius) or radius < 0:
        raise ValueError('Radio inválido')
    return latitude, longitude, radius


def obtener_negocios_cercanos(user_lat, user_lon):
    """Retorna lista de negocios dentro del radio de delivery del cliente"""
    negocios_cercanos = []
    all_businesses = Business.query.filter_by(is_active=True).all()
    
    try:
        user_lat, user_lon = validar_coordenadas(user_lat, user_lon)
    except (TypeError, ValueError):
        return []

    for business in all_businesses:
        try:
            latitude, longitude = validar_coordenadas(business.latitude, business.longitude)
            radius = float(business.delivery_radius_km)
            if not isfinite(radius) or radius < 0:
                continue
        except (TypeError, ValueError):
            continue
        distancia = calcular_distancia_negocio_km(user_lat, user_lon, latitude, longitude)
        if distancia <= radius:
            negocios_cercanos.append({'business': business, 'distance': round(distancia, 2)})

    negocios_cercanos.sort(key=lambda x: x['distance'])
    return negocios_cercanos


# ============ ROUTES PRINCIPALES (CLIENTE) ============

@main_bp.route('/')
def index():
    if current_user.is_authenticated and current_user.is_delivery:
        return redirect(url_for('delivery.dashboard'))
    
    if current_user.is_authenticated and current_user.is_super_admin:
        return redirect(url_for('super_admin.dashboard'))
    
    if current_user.is_authenticated and current_user.is_admin and current_user.business_id:
        return redirect(url_for('admin.dashboard'))
    
    user_lat = session.get('user_latitude', -25.2637)
    user_lon = session.get('user_longitude', -57.5759)
    
    negocios_cercanos = obtener_negocios_cercanos(user_lat, user_lon)
    business_ids = [n['business'].id for n in negocios_cercanos]
    
    if business_ids:
        products = Product.query.filter(
            Product.business_id.in_(business_ids),
            Product.is_active == True,
            Product.stock > 0
        ).order_by(Product.created_at.desc()).limit(20).all()
    else:
        products = []
    
    categories = Category.query.all()
    
    return render_template('products.html', 
                          products=products, 
                          categories=categories,
                          negocios_cercanos=negocios_cercanos,
                          user_lat=user_lat,
                          user_lon=user_lon,
                          current_category=None,
                          search_term='')


@main_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_username = User.query.filter_by(username=form.username.data).first()
        if existing_username:
            flash('❌ Este nombre de usuario ya está en uso. Probá con otro.', 'danger')
            return render_template('register.html', form=form)
        
        existing_email = User.query.filter_by(email=form.email.data).first()
        if existing_email:
            flash('❌ Este email ya está registrado.', 'danger')
            return render_template('register.html', form=form)
        
        password_errors = User.validate_strong_password(form.password.data)
        if password_errors:
            flash(f'❌ Contraseña débil: {" - ".join(password_errors)}', 'danger')
            return render_template('register.html', form=form)
        
        es_comerciante = (form.account_type.data == 'business')
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            phone=form.phone.data,
            is_active=True,
            security_question_id=form.security_question_id.data,
            is_admin=es_comerciante
        )
        user.set_password(form.password.data)
        user.set_security_answer(form.security_answer.data)
        
        db.session.add(user)
        db.session.flush()
        
        if es_comerciante:
            new_business = Business(
                name=f"Pendiente - {user.username}",
                slug=f"pending-{user.id}",
                description="Solicitud de comerciante pendiente de aprobación",
                phone=user.phone,
                is_active=False,
                subscription_status='pending'
            )
            user.business_id = new_business.id
            db.session.add(new_business)
            db.session.commit()
            
            flash('📋 Tu solicitud de comerciante fue enviada. El Super Admin la revisará y activará tu cuenta pronto.', 'info')
            return redirect(url_for('main.login'))
        
        db.session.commit()
        login_user(user)
        flash(f'🎉 ¡Bienvenido {user.username}! Tu cuenta de comprador fue creada exitosamente.', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('register.html', form=form)


@main_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.username.data.strip()
        
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()
        
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('️ Tu cuenta no está activada.', 'warning')
                return redirect(url_for('main.login'))
            
            login_user(user, remember=form.remember_me.data)
            flash(f' 👋 ¡Bienvenido de nuevo, {user.display_name}!', 'success')
            
            next_page = request.args.get('next')
            
            if user.is_super_admin:
                return redirect(next_page or url_for('super_admin.dashboard'))
            elif user.is_admin:
                return redirect(next_page or url_for('admin.dashboard'))
            elif user.is_delivery:
                return redirect(next_page or url_for('delivery.dashboard'))
            else:
                return redirect(next_page or url_for('main.dashboard'))
        else:
            flash('❌ Usuario/email o contraseña incorrectos.', 'danger')
    
    return render_template('login.html', form=form)


@main_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesion cerrada. Hasta pronto en QuickGo!', 'info')
    return redirect(url_for('main.index'))


@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_super_admin:
        return redirect(url_for('super_admin.dashboard'))
    
    if current_user.is_delivery:
        return redirect(url_for('delivery.dashboard'))
    
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    
    pending_order = current_user.get_pending_order()
    recent_orders = get_recent_orders(current_user.id, limit=10)
    featured_products = get_featured_products(limit=8)
    user_name = current_user.display_name
    
    return render_template('dashboard.html',
        user_name=user_name,
        pending_order=pending_order,
        recent_orders=recent_orders,
        featured_products=featured_products
    )


@main_bp.route('/products')
def products():
    if current_user.is_authenticated and current_user.is_admin:
        flash('Como administrador, usa el panel de gestion.', 'info')
        return redirect(url_for('admin.manage_products'))
    
    if current_user.is_authenticated and current_user.is_delivery:
        flash('Como delivery, usa tu panel de gestion.', 'info')
        return redirect(url_for('delivery.dashboard'))
    
    category_id = request.args.get('category', type=int)
    search = request.args.get('search', type=str)
    
    user_lat = session.get('user_latitude', -25.2637)
    user_lon = session.get('user_longitude', -57.5759)
    
    negocios_cercanos = obtener_negocios_cercanos(user_lat, user_lon)
    business_ids = [n['business'].id for n in negocios_cercanos]
    
    if not business_ids:
        return render_template('products.html', 
                              products=[], 
                              categories=[],
                              negocios_cercanos=[],
                              user_lat=user_lat,
                              user_lon=user_lon,
                              current_category=category_id,
                              search_term=search)
    
    query = Product.query.filter(
        Product.is_active == True,
        Product.stock > 0,
        Product.business_id.in_(business_ids)
    )
    
    if category_id:
        query = query.filter_by(category_id=category_id)
    
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    
    products = query.order_by(Product.created_at.desc()).all()
    categories = Category.query.all()
    
    return render_template('products.html', 
                          products=products, 
                          categories=categories,
                          negocios_cercanos=negocios_cercanos,
                          user_lat=user_lat,
                          user_lon=user_lon,
                          current_category=category_id, 
                          search_term=search)


@main_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin.manage_products'))
    
    if current_user.is_authenticated and current_user.is_delivery:
        return redirect(url_for('delivery.dashboard'))
    
    product = Product.query.get_or_404(product_id)
    if not product.is_available:
        flash('Este producto no esta disponible.', 'warning')
        return redirect(url_for('main.products'))
    return render_template('product_detail.html', product=product)


@main_bp.route('/cart/add/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    if current_user.is_admin or current_user.is_delivery:
        flash('No puedes realizar compras.', 'warning')
        return redirect(url_for('main.dashboard'))
    
    if current_user.get_pending_order():
        flash('Ya tienes un pedido pendiente. Completa o cancela ese pedido primero.', 'warning')
        return redirect(url_for('main.dashboard'))
    
    product = Product.query.get_or_404(product_id)
    if not product.is_available:
        flash('Producto no disponible.', 'danger')
        return redirect(url_for('main.products'))
    
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session['cart'] = cart
    
    flash(f'{product.name} agregado al carrito.', 'success')
    return redirect(request.referrer or url_for('main.products'))


@main_bp.route('/cart')
@login_required
def cart():
    if current_user.is_admin or current_user.is_delivery:
        return redirect(url_for('main.dashboard'))
    
    if current_user.get_pending_order():
        flash('Ya tienes un pedido pendiente.', 'warning')
        return redirect(url_for('main.dashboard'))
    
    cart = session.get('cart', {})
    cart_items = []
    total = 0
    
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product and product.is_available:
            subtotal = product.price * quantity
            cart_items.append({
                'product': product,
                'quantity': quantity,
                'subtotal': subtotal
            })
            total += subtotal
    
    return render_template('cart.html', cart_items=cart_items, total=total)


@main_bp.route('/cart/update/<int:product_id>', methods=['POST'])
@login_required
def update_cart(product_id):
    if current_user.is_admin or current_user.is_delivery:
        return redirect(url_for('main.dashboard'))
    
    action = request.form.get('action')
    cart = session.get('cart', {})
    
    if action == 'increase':
        cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    elif action == 'decrease':
        if cart.get(str(product_id), 0) > 1:
            cart[str(product_id)] -= 1
        else:
            cart.pop(str(product_id), None)
    elif action == 'remove':
        cart.pop(str(product_id), None)
    
    session['cart'] = cart
    return redirect(url_for('main.cart'))


@main_bp.route('/order/create', methods=['GET', 'POST'])
@login_required
def create_order():
    if current_user.is_admin or current_user.is_delivery:
        flash('No puedes realizar compras.', 'warning')
        return redirect(url_for('main.dashboard'))
    
    if current_user.get_pending_order():
        flash('Ya tienes un pedido pendiente.', 'warning')
        return redirect(url_for('main.dashboard'))
    
    cart = session.get('cart', {})
    if not cart:
        flash('Tu carrito esta vacio.', 'warning')
        return redirect(url_for('main.products'))
    
    form = OrderForm()
    if form.validate_on_submit():
        total = 0
        order_items_temp = []
        tiene_importacion = False
        
        for product_id, quantity in cart.items():
            product = Product.query.get(int(product_id))
            if product and product.is_available and product.stock >= quantity:
                
                if product.category and product.category.name.upper() == 'IMPORTACION':
                    tiene_importacion = True
                    if quantity < 12:
                        flash(f'️ {product.name}: Pedido mínimo de 12 unidades para productos de importación. Tenés {quantity}.', 'warning')
                        return redirect(url_for('main.cart'))
                
                subtotal = product.price * quantity
                total += subtotal
                order_items_temp.append({
                    'product': product,
                    'product_name': product.name,
                    'quantity': quantity,
                    'price': product.price
                })
        
        if total <= 0:
            flash('Error en el calculo del total', 'danger')
            return redirect(url_for('main.cart'))
        
        business_id = None
        if order_items_temp:
            first_product = Product.query.get(order_items_temp[0]['product'].id)
            if first_product:
                business_id = first_product.business_id
        
        payment_method = request.form.get('payment_method', 'cash')
        
        if tiene_importacion and payment_method == 'cash':
            flash('❌ Los productos de IMPORTACIÓN requieren pago anticipado (Transferencia o QR). Seleccioná otro método.', 'danger')
            return redirect(url_for('main.order_confirm'))
        
        needs_change = request.form.get('needs_change') == 'on'
        cash_bill_amount = float(request.form.get('cash_bill_amount', 0)) if payment_method == 'cash' else 0.0
        receipt_path = None
        
        # 🔥 CLOUDINARY: Subir comprobante de pago a la nube
        if payment_method == 'transfer' and 'payment_receipt' in request.files:
            file = request.files['payment_receipt']
            if file and file.filename != '':
                ext = file.filename.rsplit('.', 1)[1].lower()
                if ext in {'png', 'jpg', 'jpeg', 'pdf'}:
                    receipt_url = upload_to_cloudinary(file, folder='quickgo/receipts')
                    if receipt_url:
                        receipt_path = receipt_url
                    else:
                        flash('⚠️ Error al subir el comprobante. Intentá de nuevo.', 'danger')
                        return redirect(url_for('main.order_confirm'))

        order = Order(
            user_id=current_user.id,
            business_id=business_id or 1,
            total_amount=total,
            shipping_address=form.shipping_address.data,
            shipping_phone=form.shipping_phone.data,
            shipping_reference=form.shipping_reference.data or '',
            status='pending',
            payment_method=payment_method,
            needs_change=needs_change,
            cash_bill_amount=cash_bill_amount,
            payment_receipt_url=receipt_path
        )
        
        user_location = session.get('user_location')
        
        if user_location:
            order.client_latitude = user_location['latitude']
            order.client_longitude = user_location['longitude']
        
        if user_location and business_id:
            business = Business.query.get(business_id)
            if business and business.latitude and business.longitude:
                distancia = calcular_distancia_negocio_km(
                    user_location['latitude'], user_location['longitude'],
                    business.latitude, business.longitude
                )
                order.delivery_fee = 10000 + (distancia * 1000)
                total += order.delivery_fee
                order.total_amount = total
            else:
                order.delivery_fee = 10000
                total += order.delivery_fee
                order.total_amount = total
        else:
            order.delivery_fee = 10000
            total += order.delivery_fee
            order.total_amount = total
        
        for item_data in order_items_temp:
            order_item = OrderItem(
                order=order,
                product=item_data['product'],
                product_name=item_data['product_name'],
                quantity=item_data['quantity'],
                price_at_purchase=item_data['price']
            )
            db.session.add(order_item)
            item_data['product'].stock -= item_data['quantity']
        
        db.session.add(order)
        db.session.commit()
        
        session.pop('cart', None)
        session.pop('user_location', None)
        
        if tiene_importacion:
            flash('✅ ¡Pedido de IMPORTACIÓN registrado! Esperá a que confirmemos tu pago y gestionemos tu pedido. Podrás seguir el progreso en tu panel.', 'success')
        else:
            flash('Pedido creado exitosamente en QuickGo!', 'success')
        
        return redirect(url_for('main.dashboard'))
    
    cart_items = []
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product:
            cart_items.append({
                'name': product.name,
                'quantity': quantity,
                'price': product.price,
                'subtotal': product.price * quantity
            })
    
    total = sum(item['subtotal'] for item in cart_items)
    return render_template('order_confirm.html', form=form, cart_items=cart_items, total=total)


@main_bp.route('/order/<int:order_id>/receive', methods=['POST'])
@login_required
def mark_order_received(order_id):
    if current_user.is_admin or current_user.is_delivery:
        return redirect(url_for('main.dashboard'))
    
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if order.status == 'shipped':
        order.status = 'delivered'
        order.delivered_at = datetime.now(timezone.utc)
        db.session.commit()
        flash('Pedido marcado como recibido. Gracias por tu compra en QuickGo!', 'success')
    else:
        flash('Este pedido aun no ha sido enviado.', 'warning')
    
    return redirect(url_for('main.dashboard'))


@main_bp.route('/account/settings', methods=['GET', 'POST'])
@login_required
def account_settings():
    if current_user.is_admin or current_user.is_delivery:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        theme = request.form.get('theme', 'gold')
        current_user.theme_color = theme
        db.session.commit()
        flash('Tema actualizado.', 'success')
        return redirect(url_for('main.account_settings'))
    
    return render_template('account_settings.html', current_theme=current_user.theme_color or 'gold')


# ============ RECUPERACIÓN DE CONTRASEÑA (SOLO PREGUNTAS DE SEGURIDAD) ============

@main_bp.route('/recover', methods=['GET', 'POST'])
def recover_account():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        
        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()
        
        if not user:
            flash('❌ Usuario no encontrado.', 'danger')
            return render_template('recover_account.html')
        
        if not user.security_question_id or not user.security_answer_hash:
            flash('️ Este usuario no tiene pregunta de seguridad configurada. Contactá al soporte.', 'warning')
            return render_template('recover_account.html')
        
        session['recover_user_id'] = user.id
        return redirect(url_for('main.answer_security_question'))
    
    return render_template('recover_account.html')


@main_bp.route('/recover/answer', methods=['GET', 'POST'])
def answer_security_question():
    user_id = session.get('recover_user_id')
    if not user_id:
        flash('️ Sesión expirada. Iniciá de nuevo.', 'warning')
        return redirect(url_for('main.recover_account'))
    
    user = User.query.get(user_id)
    if not user:
        session.pop('recover_user_id', None)
        flash('❌ Usuario no encontrado.', 'danger')
        return redirect(url_for('main.recover_account'))
    
    if request.method == 'POST':
        answer = request.form.get('answer', '').strip()
        
        if user.check_security_answer(answer):
            session['security_verified'] = True
            return redirect(url_for('main.select_correct_answer'))
        else:
            flash(' Respuesta incorrecta. Intentá de nuevo.', 'danger')
    
    return render_template('answer_security_question.html', 
                          question=user.security_question.question,
                          username=user.display_name)


@main_bp.route('/recover/select-answer', methods=['GET', 'POST'])
def select_correct_answer():
    user_id = session.get('recover_user_id')
    security_verified = session.get('security_verified')
    
    if not user_id or not security_verified:
        flash('⚠️ Debés completar los pasos anteriores.', 'warning')
        return redirect(url_for('main.recover_account'))
    
    user = User.query.get(user_id)
    if not user:
        session.pop('recover_user_id', None)
        session.pop('security_verified', None)
        flash('❌ Usuario no encontrado.', 'danger')
        return redirect(url_for('main.recover_account'))
    
    if request.method == 'POST':
        written_answer = request.form.get('written_answer', '').strip()
        
        if user.check_security_answer(written_answer):
            session['final_verified'] = True
            return redirect(url_for('main.reset_password_final'))
        else:
            flash(' Respuesta incorrecta. Intentá de nuevo.', 'danger')
            return redirect(url_for('main.select_correct_answer'))
    
    return render_template('select_answer.html', 
                         question=user.security_question.question,
                         username=user.display_name)


@main_bp.route('/recover/reset-password', methods=['GET', 'POST'])
def reset_password_final():
    user_id = session.get('recover_user_id')
    final_verified = session.get('final_verified')
    
    if not user_id or not final_verified:
        flash('⚠️ Debés completar la verificación primero.', 'warning')
        return redirect(url_for('main.recover_account'))
    
    user = User.query.get(user_id)
    if not user:
        session.pop('recover_user_id', None)
        session.pop('security_verified', None)
        session.pop('final_verified', None)
        flash('❌ Usuario no encontrado.', 'danger')
        return redirect(url_for('main.login'))
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if new_password != confirm_password:
            flash(' Las contraseñas no coinciden.', 'danger')
            return render_template('reset_password_final.html', username=user.display_name)
        
        password_errors = User.validate_strong_password(new_password)
        if password_errors:
            flash(f'❌ Contraseña débil: {" - ".join(password_errors)}', 'danger')
            return render_template('reset_password_final.html', username=user.display_name)
        
        user.set_password(new_password)
        db.session.commit()
        
        session.pop('recover_user_id', None)
        session.pop('security_verified', None)
        session.pop('final_verified', None)
        
        flash('✅ ¡Contraseña actualizada! Ya podés iniciar sesión.', 'success')
        return redirect(url_for('main.login'))
    
    return render_template('reset_password_final.html', username=user.display_name)


# ============ API ENDPOINTS ============

@main_bp.route('/api/validate-password', methods=['POST'])
def validate_password():
    data = request.get_json()
    password = data.get('password', '')
    
    result = {
        'length': len(password) >= 8,
        'uppercase': any(c.isupper() for c in password),
        'lowercase': any(c.islower() for c in password),
        'number': any(c.isdigit() for c in password),
        'special': any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?/' for c in password),
        'valid': False
    }
    
    result['valid'] = all([
        result['length'],
        result['uppercase'],
        result['lowercase'],
        result['number'],
        result['special']
    ])
    
    return jsonify(result)


@main_bp.route('/api/check-username', methods=['POST'])
def check_username():
    data = request.get_json()
    username = data.get('username', '').strip()
    
    if not username:
        return jsonify({'available': False, 'message': 'Ingresá un nombre de usuario'})
    
    if len(username) < 3:
        return jsonify({'available': False, 'message': 'Mínimo 3 caracteres'})
    
    user = User.query.filter_by(username=username).first()
    
    if user:
        return jsonify({'available': False, 'message': '❌ Este nombre ya está en uso'})
    else:
        return jsonify({'available': True, 'message': '✅ Nombre disponible'})


@main_bp.route('/api/update-user-location', methods=['POST'])
def update_user_location():
    data = request.get_json()
    try:
        latitude, longitude = validar_coordenadas(data.get('latitude'), data.get('longitude'))
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Coordenadas inválidas'}), 400

    session['user_latitude'] = latitude
    session['user_longitude'] = longitude
    session.modified = True

    negocios_cercanos = obtener_negocios_cercanos(latitude, longitude)

    return jsonify({
        'status': 'ok',
        'negocios_count': len(negocios_cercanos),
        'negocios': [{
            'id': n['business'].id,
            'name': n['business'].name,
            'distance': n['distance']
        } for n in negocios_cercanos[:5]]
    })


# ============ SUSCRIPCIÓN ============

@main_bp.route('/activate', methods=['GET', 'POST'])
@login_required
def activate_subscription():
    if not current_user.is_admin or not current_user.business:
        return redirect(url_for('main.dashboard'))
        
    business = current_user.business
    
    if hasattr(business, 'requires_subscription') and not business.requires_subscription:
        if business.subscription_status != 'active':
            business.subscription_status = 'active'
            db.session.commit()
        return redirect(url_for('admin.dashboard'))
    
    now = datetime.now(timezone.utc)
    
    if business.subscription_status == 'active' and business.billing_end:
        billing_end = business.billing_end
        if billing_end.tzinfo is None:
            billing_end = billing_end.replace(tzinfo=timezone.utc)
        if billing_end >= now:
            return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        code_input = request.form.get('activation_code', '').strip().upper()
        
        if business.activation_code and business.activation_code == code_input:
            code_expires = business.code_expires_at
            if code_expires:
                if code_expires.tzinfo is None:
                    code_expires = code_expires.replace(tzinfo=timezone.utc)
                
                if code_expires > now:
                    business.subscription_status = 'active'
                    
                    today = datetime.now(timezone.utc).date()
                    if not business.billing_start:
                        business.billing_start = today
                    business.billing_end = today + timedelta(days=30)
                    
                    business.activation_code = None
                    business.code_expires_at = None
                    
                    db.session.commit()
                    
                    flash('✅ Suscripción activada exitosamente por 30 días! Ya podés operar normalmente.', 'success')
                    return redirect(url_for('main.dashboard'))
                else:
                    flash(' El código ha expirado. Solicitá uno nuevo al administrador.', 'danger')
            else:
                flash('❌ No hay código de activación configurado.', 'danger')
        else:
            flash('❌ Código inválido. Verificá e intentá de nuevo.', 'danger')
            
    return render_template('activate_subscription.html', business=business)


# ============ ADMIN ROUTES ============

@admin_bp.route('/business/coverage', methods=['POST'])
@login_required
@business_admin_required
def update_business_coverage():
    # Ownership comes exclusively from the authenticated merchant.
    if current_user.is_delivery or current_user.is_super_admin or not current_user.business_id:
        abort(403)
    business = db.session.get(Business, current_user.business_id)
    if business is None:
        abort(403)
    allowed_fields = {'csrf_token', 'address', 'latitude', 'longitude', 'delivery_radius_km'}
    if request.args or set(request.form) - allowed_fields:
        abort(403)
    if any(len(request.form.getlist(key)) != 1 for key in request.form):
        abort(400, description='Formulario de cobertura inválido.')
    form = BusinessCoverageForm()
    if not form.validate_on_submit():
        abort(400, description='Ubicación o radio inválidos, o formulario vencido. Volvé al panel e intentá nuevamente.')
    try:
        latitude, longitude = validar_coordenadas(form.latitude.data, form.longitude.data)
    except (TypeError, ValueError):
        abort(400, description='Coordenadas inválidas.')
    business.latitude = latitude
    business.longitude = longitude
    business.address = form.address.data
    business.delivery_radius_km = form.delivery_radius_km.data
    db.session.commit()
    flash('Ubicación y radio de cobertura actualizados.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/')
@login_required
@business_admin_required
@subscription_required
def dashboard():
    if current_user.is_delivery:
        flash('Redirigiendo al panel de delivery.', 'info')
        return redirect(url_for('delivery.dashboard'))
    
    if current_user.is_super_admin:
        return redirect(url_for('super_admin.dashboard'))
    
    business_id = current_user.business_id
    
    from sqlalchemy import func
    
    total_users = User.query.filter_by(business_id=business_id).count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).filter_by(business_id=business_id, status='delivered').scalar() or 0
    total_orders = Order.query.filter_by(business_id=business_id).count()
    pending_orders = Order.query.filter_by(business_id=business_id, status='pending').count()
    
    best_seller_query = db.session.query(
        Product.name,
        func.sum(OrderItem.quantity).label('total_sold')
    ).join(OrderItem, Product.id == OrderItem.product_id)\
     .join(Order, OrderItem.order_id == Order.id)\
     .filter(Order.business_id == business_id, Order.status == 'delivered')\
     .group_by(Product.id)\
     .order_by(func.sum(OrderItem.quantity).desc())\
     .first()
    
    best_seller = list(best_seller_query) if best_seller_query else None
    
    top_customer_query = db.session.query(
        User.email,
        func.count(Order.id).label('order_count')
    ).join(Order, User.id == Order.user_id)\
     .filter(Order.business_id == business_id, Order.status == 'delivered')\
     .group_by(User.id)\
     .order_by(func.count(Order.id).desc())\
     .first()
    
    top_customer = list(top_customer_query) if top_customer_query else None
    
    recent_orders = Order.query.filter_by(business_id=business_id).order_by(Order.created_at.desc()).limit(10).all()
    
    low_stock_products = Product.query.filter(
        Product.business_id == business_id,
        Product.is_active == True,
        Product.stock > 0,
        Product.stock < 10
    ).order_by(Product.stock.asc()).limit(5).all()
    
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    sales_by_category_query = db.session.query(
        Category.name,
        func.sum(OrderItem.quantity * OrderItem.price_at_purchase).label('revenue')
    ).join(Product, Category.id == Product.category_id)\
     .join(OrderItem, Product.id == OrderItem.product_id)\
     .join(Order, OrderItem.order_id == Order.id)\
     .filter(Order.business_id == business_id, Order.created_at >= thirty_days_ago, Order.status == 'delivered')\
     .group_by(Category.id)\
     .all()
    
    sales_by_category = [[row[0], float(row[1])] for row in sales_by_category_query]
    
    orders_by_status_query = db.session.query(
        Order.status,
        func.count(Order.id).label('count')
    ).filter(Order.business_id == business_id).group_by(Order.status).all()
    
    orders_by_status = [[row[0], row[1]] for row in orders_by_status_query]
    
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    daily_sales_query = db.session.query(
        db.func.date(Order.created_at).label('date'),
        func.sum(Order.total_amount).label('total')
    ).filter(Order.business_id == business_id, Order.created_at >= seven_days_ago, Order.status == 'delivered')\
     .group_by(db.func.date(Order.created_at))\
     .order_by(db.func.date(Order.created_at))\
     .all()
    
    daily_sales = [[str(row[0]), float(row[1])] for row in daily_sales_query]
    
    stock_products_query = Product.query.filter(
        Product.business_id == business_id,
        Product.is_active == True,
        Product.stock > 0
    ).order_by(Product.stock.desc()).limit(10).all()
    
    stock_products = [{
        'id': p.id,
        'name': p.name,
        'stock': p.stock,
        'price': p.price,
        'category': p.category.name if p.category else 'Sin categoria'
    } for p in stock_products_query]
    
    delivery_users = User.query.filter_by(business_id=business_id, is_delivery=True, is_active=True).all()
    
    return render_template('admin/dashboard.html',
                          coverage_form=BusinessCoverageForm(obj=current_user.business),
        total_users=total_users,
        total_sales=total_sales,
        total_orders=total_orders,
        pending_orders=pending_orders,
        best_seller=best_seller,
        top_customer=top_customer,
        recent_orders=recent_orders,
        low_stock_products=low_stock_products,
        sales_by_category=sales_by_category,
        orders_by_status=orders_by_status,
        daily_sales=daily_sales,
        stock_products=stock_products,
        delivery_users=delivery_users
    )


@admin_bp.route('/users')
@login_required
@business_admin_required
@subscription_required
def manage_users():
    business_id = current_user.business_id
    users = User.query.filter_by(business_id=business_id).order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@business_admin_required
@subscription_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.business_id != current_user.business_id:
        flash('❌ No podés editar usuarios de otros negocios.', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    if user.is_super_admin:
        flash('❌ No podés editar a un Super Admin.', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    form = AdminUserForm(obj=user)
    
    if form.validate_on_submit():
        user.email = form.email.data
        user.phone = form.phone.data
        user.is_active = form.is_active.data
        user.is_admin = form.is_admin.data
        user.is_delivery = request.form.get('is_delivery') == 'true'
        
        db.session.commit()
        flash('✅ Usuario actualizado.', 'success')
        return redirect(url_for('admin.manage_users'))
    
    return render_template('admin/user_form.html', form=form, user=user)


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@business_admin_required
@subscription_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.business_id != current_user.business_id:
        flash('❌ No podés resetear contraseñas de usuarios de otros negocios.', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    if user.is_super_admin:
        flash('❌ No podés resetear la contraseña de un Super Admin.', 'danger')
        return redirect(url_for('admin.manage_users'))
    
    new_password = secrets.token_urlsafe(8)
    user.set_password(new_password)
    db.session.commit()
    
    flash(f'🔑 Contraseña reseteada. Nueva contraseña temporal: {new_password}', 'success')
    return redirect(url_for('admin.manage_users'))


@admin_bp.route('/products')
@login_required
@business_admin_required
@subscription_required
def manage_products():
    products = Product.query.filter_by(business_id=current_user.business_id).order_by(Product.created_at.desc()).all()
    categories = Category.query.filter_by(business_id=current_user.business_id).all()
    return render_template('admin/products.html', products=products, categories=categories)


@admin_bp.route('/products/new', methods=['GET', 'POST'])
@login_required
@business_admin_required
@subscription_required
def create_product():
    if not current_user.business_id:
        flash('Tu cuenta de administrador no tiene un negocio asignado. Contacta al Super Admin.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    form = ProductForm()
    categories = Category.query.filter_by(business_id=current_user.business_id).all()
    form.populate_categories(categories)
    
    if form.validate_on_submit():
        product = Product(
            name=form.name.data,
            description=form.description.data,
            precio_compra=form.precio_compra.data,
            price=form.price.data,
            stock=form.stock.data,
            category_id=form.category_id.data,
            business_id=current_user.business_id,
            image_url=None
        )
        
        # 🔥 CLOUDINARY: Subir imagen de producto a la nube
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, folder='quickgo/products')
                if image_url:
                    product.image_url = image_url
        
        db.session.add(product)
        db.session.commit()
        flash('Producto creado.', 'success')
        return redirect(url_for('admin.manage_products'))
    
    return render_template('admin/product_form.html', form=form, categories=categories)


@admin_bp.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@business_admin_required
@subscription_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.business_id != current_user.business_id:
        flash('No podes editar productos de otros negocios.', 'danger')
        return redirect(url_for('admin.manage_products'))
    
    form = ProductForm(obj=product)
    categories = Category.query.filter_by(business_id=current_user.business_id).all()
    form.populate_categories(categories)
    
    if form.validate_on_submit():
        product.name = form.name.data
        product.description = form.description.data
        product.precio_compra = form.precio_compra.data
        product.price = form.price.data
        product.stock = form.stock.data
        product.category_id = form.category_id.data
        
        # 🔥 CLOUDINARY: Subir nueva imagen si se proporciona
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename != '' and allowed_file(file.filename):
                image_url = upload_to_cloudinary(file, folder='quickgo/products')
                if image_url:
                    product.image_url = image_url
        
        db.session.commit()
        flash('Producto actualizado.', 'success')
        return redirect(url_for('admin.manage_products'))
    
    return render_template('admin/product_form.html', form=form, product=product, categories=categories)


@admin_bp.route('/products/<int:product_id>/delete', methods=['POST'])
@login_required
@business_admin_required
@subscription_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.business_id != current_user.business_id:
        flash('No podes eliminar productos de otros negocios.', 'danger')
        return redirect(url_for('admin.manage_products'))
    
    # Con Cloudinary no borramos el archivo, solo el registro de la BD
    db.session.delete(product)
    db.session.commit()
    flash('Producto eliminado.', 'info')
    return redirect(url_for('admin.manage_products'))


@admin_bp.route('/categories', methods=['GET', 'POST'])
@login_required
@business_admin_required
@subscription_required
def manage_categories():
    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            existing = Category.query.filter_by(name=name, business_id=current_user.business_id).first()
            if not existing:
                category = Category(name=name, business_id=current_user.business_id)
                db.session.add(category)
                db.session.commit()
                flash('Categoria creada.', 'success')
            else:
                flash('Esta categoria ya existe en tu negocio.', 'warning')
        return redirect(url_for('admin.manage_categories'))
    
    categories = Category.query.filter_by(business_id=current_user.business_id).order_by(Category.name).all()
    return render_template('admin/categories.html', categories=categories)


@admin_bp.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@business_admin_required
@subscription_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    if category.business_id and category.business_id != current_user.business_id:
        flash('No podes eliminar categorias de otros negocios.', 'danger')
        return redirect(url_for('admin.manage_categories'))
    
    if len(category.products) > 0:
        flash('No se puede eliminar: hay productos asociados.', 'warning')
    else:
        db.session.delete(category)
        db.session.commit()
        flash('Categoria eliminada.', 'info')
    
    return redirect(url_for('admin.manage_categories'))


@admin_bp.route('/orders')
@login_required
@business_admin_required
@subscription_required
def manage_orders():
    status_filter = request.args.get('status', 'all')
    query = Order.query.filter_by(business_id=current_user.business_id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    delivery_users = User.query.filter_by(business_id=current_user.business_id, is_delivery=True, is_active=True).all()
    
    return render_template('admin/orders.html', 
                          orders=orders, 
                          current_status=status_filter, 
                          delivery_users=delivery_users)


@admin_bp.route('/orders/<int:order_id>/update-status', methods=['POST'])
@login_required
@business_admin_required
@subscription_required
def update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    if order.business_id != current_user.business_id:
        flash('No podes actualizar pedidos de otros negocios.', 'danger')
        return redirect(url_for('admin.manage_orders'))
    
    new_status = request.form.get('status')
    delivery_driver_id = request.form.get('delivery_driver_id', type=int)
    
    if new_status in ['pending', 'shipped', 'delivered', 'cancelled']:
        order.status = new_status
        
        if delivery_driver_id and new_status == 'shipped':
            driver = User.query.get(delivery_driver_id)
            if driver and driver.business_id == current_user.business_id:
                order.delivery_driver_id = delivery_driver_id
        
        if new_status == 'delivered':
            order.delivered_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        flash(f'Estado actualizado: {order.status_label}', 'success')
    else:
        flash('Estado invalido.', 'danger')
    
    return redirect(url_for('admin.manage_orders'))


@admin_bp.route('/api/orders/<int:order_id>/location')
@login_required
@business_admin_required
@subscription_required
def get_order_location(order_id):
    order = Order.query.get_or_404(order_id)
    if order.business_id != current_user.business_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({
        'order_id': order.id,
        'client': {
            'latitude': order.client_latitude,
            'longitude': order.client_longitude,
            'address': order.shipping_address
        },
        'delivery': {
            'latitude': order.delivery_latitude,
            'longitude': order.delivery_longitude
        } if order.delivery_latitude else None,
        'status': order.status,
        'delivery_fee': order.delivery_fee
    })


@admin_bp.route('/pedido/<int:order_id>/ubicacion')
@login_required
@business_admin_required
def ver_ubicacion_pedido(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.business_id != current_user.business_id:
        flash('No tenés permiso para ver este pedido.', 'danger')
        return redirect(url_for('admin.manage_orders'))
    
    return render_template('admin/ver_ubicacion_pedido.html', order=order)


@admin_bp.route('/pedido/<int:order_id>/actualizar-delivery', methods=['POST'])
@login_required
@business_admin_required
def actualizar_costo_delivery(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.business_id != current_user.business_id:
        return jsonify({'error': 'No autorizado'}), 403
    
    data = request.get_json()
    nuevo_costo = float(data.get('delivery_fee', 10000))
    
    subtotal = order.total_amount - order.delivery_fee
    order.delivery_fee = nuevo_costo
    order.total_amount = subtotal + nuevo_costo
    
    db.session.commit()
    
    from app import socketio
    socketio.emit('delivery_fee_updated', {
        'order_id': order.id,
        'new_fee': nuevo_costo,
        'new_total': order.total_amount
    }, room=f'order_{order.id}')
    
    return jsonify({'success': True, 'new_fee': nuevo_costo, 'new_total': order.total_amount})


@admin_bp.route('/api/pedido/<int:order_id>/datos')
@login_required
@business_admin_required
def api_pedido_datos(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.business_id != current_user.business_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({
        'order_id': order.id,
        'status': order.status,
        'status_label': order.status_label,
        'delivery_fee': order.delivery_fee,
        'total_amount': order.total_amount,
        'client_lat': order.client_latitude,
        'client_lon': order.client_longitude,
        'delivery_lat': order.delivery_latitude,
        'delivery_lon': order.delivery_longitude
    })


@admin_bp.route('/orders/<int:order_id>/request-delivery', methods=['GET', 'POST'])
@login_required
@business_admin_required
def request_delivery(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.business_id != current_user.business_id:
        flash('No tenés permiso para este pedido.', 'danger')
        return redirect(url_for('admin.manage_orders'))
    
    if order.status != 'pending':
        flash('El pedido ya fue procesado.', 'warning')
        return redirect(url_for('admin.manage_orders'))
    
    if not order.client_latitude or not order.client_longitude:
        flash('No hay ubicación del cliente disponible.', 'danger')
        return redirect(url_for('admin.manage_orders'))
    
    if request.method == 'POST':
        radius = float(request.form.get('radius', 5))
        
        nearby_deliveries = User.find_nearby_deliveries(
            order.client_latitude,
            order.client_longitude,
            radius,
            business_id=None
        )
        
        if not nearby_deliveries:
            flash(f'No hay deliverys disponibles en un radio de {radius}km.', 'warning')
            return redirect(url_for('admin.manage_orders'))
        
        delivery_request = DeliveryRequest(
            order_id=order.id,
            business_id=current_user.business_id,
            search_radius=radius,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2)
        )
        db.session.add(delivery_request)
        db.session.commit()
        
        from app import socketio
        
        for item in nearby_deliveries:
            delivery = item['delivery']
            distance = item['distance']
            
            socketio.emit('new_delivery_request', {
                'request_id': delivery_request.id,
                'order_id': order.id,
                'business_name': current_user.business.name,
                'distance_km': distance,
                'pickup_address': current_user.business.address,
                'delivery_address': order.shipping_address,
                'total_amount': order.total_amount
            }, room=f'delivery_{delivery.id}')
        
        flash(f'📢 Solicitud enviada a {len(nearby_deliveries)} deliverys en un radio de {radius}km', 'success')
        return redirect(url_for('admin.delivery_request_status', request_id=delivery_request.id))
    
    return render_template('admin/request_delivery.html', order=order)


@admin_bp.route('/delivery-request/<int:request_id>/status')
@login_required
@business_admin_required
def delivery_request_status(request_id):
    delivery_request = DeliveryRequest.query.get_or_404(request_id)
    
    if delivery_request.business_id != current_user.business_id:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('admin.manage_orders'))
    
    if delivery_request.status == 'pending' and delivery_request.is_expired():
        delivery_request.status = 'expired'
        db.session.commit()
        
        flash(' La solicitud expiró. Buscando más deliverys...', 'warning')
        return redirect(url_for('admin.request_delivery', order_id=delivery_request.order_id))
    
    return render_template('admin/delivery_request_status.html', request=delivery_request)


@main_bp.route('/delivery-requests')
@login_required
def delivery_requests_list():
    if not current_user.is_delivery:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.index'))
    
    requests = DeliveryRequest.query.filter_by(status='pending').all()
    
    if current_user.latitude and current_user.longitude:
        filtered_requests = []
        for req in requests:
            order = req.order
            if order.client_latitude and order.client_longitude:
                nearby = User.find_nearby_deliveries(
                    current_user.latitude,
                    current_user.longitude,
                    req.search_radius
                )
                for item in nearby:
                    if item['delivery'].id == current_user.id:
                        filtered_requests.append({
                            'request': req,
                            'distance': item['distance']
                        })
                        break
        requests = filtered_requests
    
    return render_template('delivery/requests.html', requests=requests)


@main_bp.route('/delivery-request/<int:request_id>/accept', methods=['POST'])
@login_required
def accept_delivery_request(request_id):
    if not current_user.is_delivery:
        return jsonify({'error': 'Unauthorized'}), 403
    
    delivery_request = DeliveryRequest.query.get_or_404(request_id)
    
    if delivery_request.status != 'pending':
        flash('Esta solicitud ya no está disponible.', 'warning')
        return redirect(url_for('delivery.dashboard'))
    
    delivery_request.driver_id = current_user.id
    delivery_request.status = 'accepted'
    delivery_request.accepted_at = datetime.now(timezone.utc)
    
    order = delivery_request.order
    order.delivery_driver_id = current_user.id
    order.status = 'shipped'
    
    db.session.commit()
    
    from app import socketio
    
    socketio.emit('delivery_request_accepted', {
        'request_id': delivery_request.id,
        'order_id': order.id,
        'driver_name': current_user.email,
        'driver_phone': current_user.phone
    }, room=f'business_{delivery_request.business_id}')
    
    socketio.emit('delivery_assigned', {
        'order_id': order.id,
        'driver_name': current_user.email,
        'driver_phone': current_user.phone
    }, room=f'user_{order.user_id}')
    
    flash('✅ Solicitud aceptada. ¡A retirar el pedido!', 'success')
    return redirect(url_for('delivery.dashboard'))


@main_bp.route('/delivery-request/<int:request_id>/reject', methods=['POST'])
@login_required
def reject_delivery_request(request_id):
    if not current_user.is_delivery:
        return jsonify({'error': 'Unauthorized'}), 403
    
    delivery_request = DeliveryRequest.query.get_or_404(request_id)
    
    if delivery_request.status != 'pending':
        flash('Esta solicitud ya no está disponible.', 'warning')
        return redirect(url_for('delivery.dashboard'))
    
    delivery_request.status = 'rejected'
    db.session.commit()
    
    from app import socketio
    socketio.emit('delivery_request_rejected', {
        'request_id': delivery_request.id,
        'order_id': delivery_request.order.id,
        'driver_id': current_user.id
    }, room=f'business_{delivery_request.business_id}')
    
    flash(' Solicitud rechazada', 'info')
    return redirect(url_for('delivery.dashboard'))


@main_bp.route('/chat/order/<int:order_id>')
@login_required
def order_chat(order_id):
    order = Order.query.get_or_404(order_id)
    
    has_permission = False
    
    if current_user.id == order.user_id:
        has_permission = True
    
    if order.delivery_driver_id and current_user.id == order.delivery_driver_id:
        has_permission = True
    
    if current_user.is_admin and current_user.business_id == order.business_id:
        has_permission = True
    
    if not has_permission:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    messages = ChatMessage.query.filter_by(order_id=order_id)\
        .order_by(ChatMessage.created_at.asc()).all()
    
    for msg in messages:
        if msg.sender_id != current_user.id and not msg.is_read:
            msg.is_read = True
    db.session.commit()
    
    return render_template('chat/order_chat.html', order=order, messages=messages)


@main_bp.route('/api/chat/order/<int:order_id>/send', methods=['POST'])
@login_required
def send_chat_message(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.status in ['delivered', 'cancelled']:
        return jsonify({'error': 'Este pedido está cerrado. No se pueden enviar mensajes.'}), 403
    
    has_permission = False
    if current_user.id == order.user_id:
        has_permission = True
    if order.delivery_driver_id and current_user.id == order.delivery_driver_id:
        has_permission = True
    if current_user.is_admin and current_user.business_id == order.business_id:
        has_permission = True
    
    if not has_permission:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    message_text = data.get('message', '').strip()
    
    if not message_text:
        return jsonify({'error': 'Mensaje vacío'}), 400
    
    message = ChatMessage(
        order_id=order_id,
        sender_id=current_user.id,
        message=message_text
    )
    db.session.add(message)
    db.session.commit()
    
    from app import socketio
    
    message_data = {
        'order_id': order_id,
        'message': message.to_dict()
    }
    
    socketio.emit('new_chat_message', message_data, room=f'order_chat_{order_id}')
    socketio.emit('new_chat_message', message_data, room=f'user_{order.user_id}')
    
    if order.delivery_driver_id:
        socketio.emit('new_chat_message', message_data, room=f'delivery_{order.delivery_driver_id}')
    
    socketio.emit('new_chat_message', message_data, room=f'business_{order.business_id}')
    
    return jsonify({'success': True, 'message': message.to_dict()})


# ============ DELIVERY ROUTES ============

@delivery_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_delivery:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.index'))
    
    paraguay_tz = timezone(timedelta(hours=-3))
    now = datetime.now(paraguay_tz)
    today = now.date()
    
    delivery_orders = Order.query.filter_by(
        delivery_driver_id=current_user.id,
        status='shipped'
    ).order_by(Order.created_at.desc()).all()
    
    all_delivery_orders = Order.query.filter_by(
        delivery_driver_id=current_user.id
    ).filter(
        Order.status.in_(['delivered', 'cancelled'])
    ).order_by(Order.created_at.desc()).all()
    
    today_earnings = 0
    today_deliveries = 0
    night_earnings = 0
    night_deliveries = 0
    total_deliveries = len([o for o in all_delivery_orders if o.status == 'delivered'])
    completed_orders = total_deliveries
    rejected_orders = len([o for o in all_delivery_orders if o.status == 'cancelled'])
    
    for order in all_delivery_orders:
        if order.status == 'delivered' and order.delivery_fee:
            delivered_at = order.delivered_at
            
            if delivered_at:
                if delivered_at.tzinfo is None:
                    delivered_at = delivered_at.replace(tzinfo=timezone.utc)
                
                delivered_at_local = delivered_at.astimezone(paraguay_tz)
                delivered_date = delivered_at_local.date()
                delivered_hour = delivered_at_local.hour
                
                if delivered_date == today:
                    today_earnings += order.delivery_fee
                    today_deliveries += 1
                
                if delivered_hour >= 18 or delivered_hour < 6:
                    night_earnings += order.delivery_fee
                    night_deliveries += 1
    
    return render_template('delivery/dashboard.html', 
                          delivery_orders=delivery_orders,
                          all_delivery_orders=all_delivery_orders,
                          today_earnings=today_earnings,
                          today_deliveries=today_deliveries,
                          night_earnings=night_earnings,
                          night_deliveries=night_deliveries,
                          total_deliveries=total_deliveries,
                          completed_orders=completed_orders,
                          rejected_orders=rejected_orders)


@delivery_bp.route('/orders')
@login_required
def orders():
    if not current_user.is_delivery:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.index'))
    
    status_filter = request.args.get('status', 'all')
    
    query = Order.query.filter_by(delivery_driver_id=current_user.id)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    return render_template('delivery/orders.html', 
                          orders=orders, 
                          current_status=status_filter)


@delivery_bp.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    if not current_user.is_delivery:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.index'))
    
    order = Order.query.get_or_404(order_id)
    
    if order.delivery_driver_id != current_user.id:
        flash('Este pedido no te pertenece.', 'danger')
        return redirect(url_for('delivery.dashboard'))
    
    return render_template('delivery/order_detail.html', order=order)


@delivery_bp.route('/api/location/update', methods=['POST'])
@login_required
@limiter.exempt
def update_location():
    if not current_user.is_delivery:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    
    if not data.get('latitude') or not data.get('longitude'):
        return jsonify({'error': 'Coordenadas requeridas'}), 400
    
    current_user.latitude = data['latitude']
    current_user.longitude = data['longitude']
    db.session.commit()
    
    return jsonify({'status': 'ok'})


@delivery_bp.route('/api/arrived/<int:order_id>', methods=['POST'])
@login_required
@limiter.exempt
def mark_arrived(order_id):
    if not current_user.is_delivery:
        return jsonify({'error': 'Unauthorized'}), 403
    
    order = Order.query.get_or_404(order_id)
    
    if order.delivery_driver_id != current_user.id:
        return jsonify({'error': 'No autorizado'}), 403
    
    order.driver_arrived = True
    db.session.commit()
    
    return jsonify({'success': True})


@delivery_bp.route('/order/<int:order_id>/mark-delivered', methods=['POST'])
@login_required
def mark_delivered(order_id):
    if not current_user.is_delivery:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.index'))
    
    order = Order.query.get_or_404(order_id)
    
    if order.delivery_driver_id != current_user.id:
        flash('No autorizado.', 'danger')
        return redirect(url_for('delivery.dashboard'))
    
    order.status = 'delivered'
    order.delivered_at = datetime.now(timezone.utc)
    db.session.commit()
    
    flash('Pedido marcado como entregado.', 'success')
    return redirect(url_for('delivery.dashboard'))


@main_bp.route('/api/location/update', methods=['POST'])
@login_required
@limiter.exempt
def update_location_client():
    data = request.get_json()
    
    if not data.get('latitude') or not data.get('longitude'):
        return jsonify({'error': 'Coordenadas requeridas'}), 400
    
    session['user_location'] = {
        'latitude': data['latitude'],
        'longitude': data['longitude'],
        'updated_at': datetime.utcnow().isoformat()
    }
    
    return jsonify({'status': 'ok'})


@main_bp.route('/api/location/calculate-delivery', methods=['POST'])
@login_required
@limiter.exempt
def calculate_delivery_fee():
    try:
        data = request.get_json()
        client_lat = data.get('latitude')
        client_lon = data.get('longitude')
        
        admin_lat = -25.2637
        admin_lon = -57.5759
        
        if current_user.is_authenticated and current_user.business_id:
            business = Business.query.get(current_user.business_id)
            if business and business.latitude and business.longitude:
                admin_lat = business.latitude
                admin_lon = business.longitude
        
        distancia = calcular_distancia_negocio_km(client_lat, client_lon, admin_lat, admin_lon)
        
        costo = 10000 + (distancia * 1000)
        
        return jsonify({
            'distance_km': round(distancia, 2),
            'delivery_fee': costo,
            'fee_formatted': f'GS {costo:,.0f}'.replace(',', '.')
        })
    except Exception as e:
        print(f"Error calculando envio: {e}")
        return jsonify({
            'distance_km': None,
            'delivery_fee': 10000,
            'fee_formatted': 'GS 10.000'
        })


@main_bp.route('/api/products/search')
def api_search_products():
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    products = Product.query.filter(
        Product.is_active == True,
        Product.stock > 0,
        Product.name.ilike(f'%{query}%')
    ).limit(10).all()
    
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'price': p.price,
        'image': p.image_url or '/static/images/placeholder.png'
    } for p in products])


# ============ SUPER ADMIN ROUTES ============

@super_admin_bp.route('/')
@login_required
@super_admin_required
def dashboard():
    total_businesses = Business.query.count()
    active_businesses = Business.query.filter_by(is_active=True).count()
    total_users = User.query.count()
    total_deliveries = User.query.filter_by(is_delivery=True).count()
    total_products = Product.query.filter_by(is_active=True).count()
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter_by(status='delivered').scalar() or 0
    
    from sqlalchemy import func
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    top_businesses = db.session.query(
        Business.name,
        Business.slug,
        Business.id,
        db.func.sum(Order.total_amount).label('revenue'),
        db.func.count(Order.id).label('orders')
    ).join(Order, Business.id == Order.business_id)\
     .filter(Order.created_at >= thirty_days_ago, Order.status == 'delivered')\
     .group_by(Business.id)\
     .order_by(db.func.sum(Order.total_amount).desc())\
     .limit(10).all()
    
    top_deliveries = db.session.query(
        User.email,
        User.phone,
        db.func.count(Order.id).label('deliveries'),
        Business.name.label('business_name')
    ).join(Order, User.id == Order.delivery_driver_id)\
     .join(Business, Order.business_id == Business.id)\
     .filter(Order.status == 'delivered')\
     .group_by(User.id, Business.name)\
     .order_by(db.func.count(Order.id).desc())\
     .limit(10).all()
    
    low_performers = Business.query.filter_by(is_active=True)\
        .outerjoin(Order, Business.id == Order.business_id)\
        .group_by(Business.id)\
        .having(db.func.count(Order.id) < 5)\
        .all()
    
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(20).all()
    recent_businesses = Business.query.order_by(Business.created_at.desc()).limit(10).all()
    
    messages_sent_count = UserMessage.query.filter_by(sender_id=current_user.id).count()
    
    return render_template('super_admin/dashboard.html',
        total_businesses=total_businesses,
        active_businesses=active_businesses,
        total_users=total_users,
        total_deliveries=total_deliveries,
        total_products=total_products,
        total_orders=total_orders,
        total_revenue=total_revenue,
        top_businesses=top_businesses,
        top_deliveries=top_deliveries,
        low_performers=low_performers,
        recent_orders=recent_orders,
        recent_businesses=recent_businesses,
        messages_sent_count=messages_sent_count
    )


@super_admin_bp.route('/businesses')
@login_required
@super_admin_required
def manage_businesses():
    businesses = Business.query.order_by(Business.created_at.desc()).all()
    return render_template('super_admin/businesses.html', businesses=businesses)


@super_admin_bp.route('/businesses/search')
@login_required
@super_admin_required
def search_businesses():
    query = request.args.get('q', '').strip()
    if query:
        businesses = Business.query.filter(
            (Business.name.ilike(f'%{query}%')) | (Business.slug.ilike(f'%{query}%'))
        ).order_by(Business.created_at.desc()).all()
    else:
        businesses = Business.query.order_by(Business.created_at.desc()).all()
    return render_template('super_admin/businesses.html', businesses=businesses)


@super_admin_bp.route('/businesses/new', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_business():
    if request.method == 'POST':
        try:
            latitude, longitude, radius = leer_cobertura_negocio(request.form)
        except (TypeError, ValueError):
            flash('Ingresá latitud, longitud y radio de cobertura válidos (km).', 'danger')
            return render_template('super_admin/business_form.html', business=None), 400

        slug = request.form.get('slug').lower().replace(' ', '-')
        if Business.query.filter_by(slug=slug).first():
            flash('Este nombre de negocio ya existe.', 'warning')
            return redirect(url_for('super_admin.create_business'))
        
        business = Business(
            name=request.form.get('name'),
            slug=slug,
            description=request.form.get('description'),
            phone=request.form.get('phone'),
            address=request.form.get('address'),
            latitude=latitude,
            longitude=longitude,
            delivery_radius_km=radius,
            commission_rate=float(request.form.get('commission_rate', 0.10)),
            delivery_fee_base=float(request.form.get('delivery_fee_base', 5000)),
            delivery_fee_per_km=float(request.form.get('delivery_fee_per_km', 1000))
        )
        
        # 🔥 CLOUDINARY: Subir logo del negocio a la nube
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename != '':
                logo_url = upload_to_cloudinary(file, folder='quickgo/logos')
                if logo_url:
                    business.logo_url = logo_url
        
        db.session.add(business)
        db.session.commit()
        flash(f'Negocio "{business.name}" creado exitosamente.', 'success')
        return redirect(url_for('super_admin.manage_businesses'))
    
    return render_template('super_admin/business_form.html', business=None)


@super_admin_bp.route('/businesses/<int:business_id>/edit', methods=['GET', 'POST'])
@login_required
@super_admin_required
def edit_business(business_id):
    business = Business.query.get_or_404(business_id)
    
    if request.method == 'POST':
        try:
            latitude, longitude, radius = leer_cobertura_negocio(request.form)
        except (TypeError, ValueError):
            flash('Ingresá latitud, longitud y radio de cobertura válidos (km).', 'danger')
            return render_template('super_admin/business_form.html', business=business), 400

        business.latitude = latitude
        business.longitude = longitude
        business.delivery_radius_km = radius
        business.name = request.form.get('name')
        business.description = request.form.get('description')
        business.phone = request.form.get('phone')
        business.address = request.form.get('address')
        business.commission_rate = float(request.form.get('commission_rate', 0.10))
        business.delivery_fee_base = float(request.form.get('delivery_fee_base', 5000))
        business.delivery_fee_per_km = float(request.form.get('delivery_fee_per_km', 1000))
        business.is_active = 'is_active' in request.form
        
        if 'monthly_fee' in request.form:
            business.monthly_fee = float(request.form.get('monthly_fee', 0))
        if 'billing_start' in request.form and request.form.get('billing_start'):
            business.billing_start = datetime.strptime(request.form.get('billing_start'), '%Y-%m-%d').date()
        if 'billing_end' in request.form and request.form.get('billing_end'):
            business.billing_end = datetime.strptime(request.form.get('billing_end'), '%Y-%m-%d').date()
        
        business.requires_subscription = 'requires_subscription' in request.form
        business.subscription_exempt_reason = request.form.get('subscription_exempt_reason', '').strip()
        
        if not business.requires_subscription:
            business.subscription_status = 'active'
            business.activation_code = None
            business.code_expires_at = None
        
        db.session.commit()
        flash(f'Negocio "{business.name}" actualizado.', 'success')
        return redirect(url_for('super_admin.edit_business', business_id=business_id))
    
    return render_template('super_admin/business_form.html', business=business)


@super_admin_bp.route('/businesses/<int:business_id>/generate-code', methods=['POST'])
@login_required
@super_admin_required
def generate_activation_code(business_id):
    business = Business.query.get_or_404(business_id)
    
    if not business.requires_subscription:
        flash(f'ℹ️ El negocio "{business.name}" está EXENTO de suscripción. No necesita código.', 'info')
        return redirect(url_for('super_admin.edit_business', business_id=business_id))
    
    new_code = secrets.token_hex(4).upper()
    
    business.activation_code = new_code
    business.code_expires_at = datetime.now(timezone.utc) + timedelta(hours=5)
    business.subscription_status = 'pending'
    
    if not business.billing_start:
        business.billing_start = datetime.now(timezone.utc).date()
    if not business.billing_end:
        business.billing_end = datetime.now(timezone.utc).date() + timedelta(days=30)
    
    db.session.commit()
    
    flash(f'🔑 CÓDIGO GENERADO: {new_code}', 'warning')
    flash(f' Válido por 5 horas (hasta {business.code_expires_at.strftime("%H:%M %d/%m/%Y")})', 'info')
    flash(f' Copiá este código y envíaselo al negocio para que active su suscripción', 'info')
    
    return redirect(url_for('super_admin.edit_business', business_id=business_id))


@super_admin_bp.route('/businesses/<int:business_id>/view')
@login_required
@super_admin_required
def view_business(business_id):
    business = Business.query.get_or_404(business_id)
    
    business_products = Product.query.filter_by(business_id=business.id, is_active=True).count()
    business_orders = Order.query.filter_by(business_id=business.id).count()
    business_revenue = db.session.query(db.func.sum(Order.total_amount)).filter_by(business_id=business.id, status='delivered').scalar() or 0
    business_customers = db.session.query(db.func.count(db.distinct(Order.user_id))).filter_by(business_id=business.id).scalar() or 0
    
    recent_orders = Order.query.filter_by(business_id=business.id).order_by(Order.created_at.desc()).limit(10).all()
    products = Product.query.filter_by(business_id=business.id).order_by(Product.created_at.desc()).limit(10).all()
    delivery_drivers = User.query.filter_by(business_id=business.id, is_delivery=True).all()
    
    return render_template('super_admin/view_business.html',
        business=business,
        business_products=business_products,
        business_orders=business_orders,
        business_revenue=business_revenue,
        business_customers=business_customers,
        recent_orders=recent_orders,
        products=products,
        delivery_drivers=delivery_drivers
    )


@super_admin_bp.route('/users')
@login_required
@super_admin_required
def manage_users():
    users = User.query.order_by(User.created_at.desc()).all()
    businesses = Business.query.all()
    return render_template('super_admin/users.html', users=users, businesses=businesses)


@super_admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@super_admin_required
def reset_user_password(user_id):
    user = User.query.get_or_404(user_id)
    
    new_password = secrets.token_urlsafe(8)
    
    user.set_password(new_password)
    db.session.commit()
    
    flash(f'Contrasena reseteada para {user.email}. Nueva contrasena: {new_password}', 'warning')
    return redirect(url_for('super_admin.manage_users'))


@super_admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@super_admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    businesses = Business.query.all()
    
    if request.method == 'POST':
        user.email = request.form.get('email')
        user.phone = request.form.get('phone')
        
        user.is_active = 'is_active' in request.form
        user.is_admin = 'is_admin' in request.form
        user.is_delivery = 'is_delivery' in request.form
        user.is_super_admin = 'is_super_admin' in request.form
        
        business_id_val = request.form.get('business_id')
        user.business_id = int(business_id_val) if business_id_val else None
            
        db.session.commit()
        flash(f'Usuario {user.email} actualizado exitosamente.', 'success')
        return redirect(url_for('super_admin.manage_users'))
        
    return render_template('super_admin/user_form.html', user=user, businesses=businesses)


@super_admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('No puedes eliminar tu propia cuenta de Super Admin.', 'danger')
        return redirect(url_for('super_admin.manage_users'))
        
    db.session.delete(user)
    db.session.commit()
    flash('Usuario eliminado permanentemente.', 'warning')
    return redirect(url_for('super_admin.manage_users'))


@super_admin_bp.route('/analytics')
@login_required
@super_admin_required
def analytics():
    from sqlalchemy import func
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    revenue_by_business = db.session.query(
        Business.name,
        db.func.sum(Order.total_amount).label('revenue')
    ).join(Order, Business.id == Order.business_id)\
     .filter(Order.created_at >= thirty_days_ago, Order.status == 'delivered')\
     .group_by(Business.id)\
     .order_by(db.func.sum(Order.total_amount).desc())\
     .all()
    
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    
    orders_by_day = db.session.query(
        db.func.date(Order.created_at).label('date'),
        db.func.count(Order.id).label('count')
    ).filter(Order.created_at >= seven_days_ago)\
     .group_by(db.func.date(Order.created_at))\
     .order_by(db.func.date(Order.created_at))\
     .all()
    
    top_products = db.session.query(
        Product.name,
        Business.name.label('business_name'),
        db.func.sum(OrderItem.quantity).label('sold')
    ).join(OrderItem, Product.id == OrderItem.product_id)\
     .join(Order, OrderItem.order_id == Order.id)\
     .join(Business, Product.business_id == Business.id)\
     .filter(Order.status == 'delivered')\
     .group_by(Product.id)\
     .order_by(db.func.sum(OrderItem.quantity).desc())\
     .limit(10).all()
    
    return render_template('super_admin/analytics.html',
        revenue_by_business=revenue_by_business,
        orders_by_day=orders_by_day,
        top_products=top_products
    )


# ============ CHAT SOPORTE Y CHAT DELIVERY-NEGOCIO ============

@main_bp.route('/soporte', methods=['GET', 'POST'])
@login_required
def soporte():
    """Chat de soporte para comerciantes con Super Admin"""
    if not current_user.is_admin or not current_user.business:
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    business = current_user.business
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            chat = SupportChat(
                business_id=business.id,
                sender_id=current_user.id,
                message=message,
                is_from_admin=False
            )
            db.session.add(chat)
            db.session.commit()
            flash('✅ Mensaje enviado al Super Admin.', 'success')
            return redirect(url_for('main.soporte'))
    
    mensajes = SupportChat.query.filter_by(business_id=business.id).order_by(SupportChat.created_at.asc()).all()
    
    for m in mensajes:
        if m.is_from_admin and not m.is_read:
            m.is_read = True
    db.session.commit()
    
    return render_template('soporte.html', business=business, mensajes=mensajes)


@super_admin_bp.route('/soporte')
@login_required
@super_admin_required
def soporte_lista():
    """Lista de negocios con mensajes de soporte"""
    from sqlalchemy import func
    
    negocios_con_mensajes = db.session.query(
        Business.id,
        Business.name,
        func.count(SupportChat.id).label('total_mensajes'),
        func.sum(db.case((SupportChat.is_read == False, 1), else_=0)).label('no_leidos')
    ).join(SupportChat, Business.id == SupportChat.business_id)\
     .group_by(Business.id)\
     .order_by(func.max(SupportChat.created_at).desc())\
     .all()
    
    return render_template('super_admin/soporte_lista.html', negocios=negocios_con_mensajes)


@super_admin_bp.route('/soporte/<int:business_id>', methods=['GET', 'POST'])
@login_required
@super_admin_required
def soporte_admin(business_id):
    """Chat de soporte desde Super Admin hacia comerciante"""
    business = Business.query.get_or_404(business_id)
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            chat = SupportChat(
                business_id=business.id,
                sender_id=current_user.id,
                message=message,
                is_from_admin=True
            )
            db.session.add(chat)
            db.session.commit()
            return redirect(url_for('super_admin.soporte_admin', business_id=business_id))
    
    mensajes = SupportChat.query.filter_by(business_id=business.id).order_by(SupportChat.created_at.asc()).all()
    
    for m in mensajes:
        if not m.is_from_admin and not m.is_read:
            m.is_read = True
    db.session.commit()
    
    return render_template('super_admin/soporte_admin.html', business=business, mensajes=mensajes)


@main_bp.route('/chat-delivery/<int:order_id>', methods=['GET', 'POST'])
@login_required
def chat_delivery_negocio(order_id):
    """Chat entre delivery y negocio para un pedido específico"""
    order = Order.query.get_or_404(order_id)
    
    es_delivery = current_user.is_delivery and order.delivery_driver_id == current_user.id
    es_admin_negocio = current_user.is_admin and current_user.business_id == order.business_id
    
    if not (es_delivery or es_admin_negocio):
        flash('Acceso denegado.', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            chat = DeliveryBusinessChat(
                order_id=order.id,
                sender_id=current_user.id,
                message=message,
                is_from_delivery=current_user.is_delivery
            )
            db.session.add(chat)
            db.session.commit()
            return redirect(url_for('main.chat_delivery_negocio', order_id=order.id))
    
    mensajes = DeliveryBusinessChat.query.filter_by(order_id=order.id).order_by(DeliveryBusinessChat.created_at.asc()).all()
    
    for m in mensajes:
        if m.sender_id != current_user.id and not m.is_read:
            m.is_read = True
    db.session.commit()
    
    negocio = Business.query.get(order.business_id)
    return render_template('chat_delivery.html', order=order, negocio=negocio, mensajes=mensajes)


# ============ MENSAJES DEL SUPER ADMIN A USUARIOS ============

@super_admin_bp.route('/users/<int:user_id>/send-message', methods=['GET', 'POST'])
@login_required
@super_admin_required
def send_message_to_user(user_id):
    """Super Admin envía mensaje a cualquier usuario"""
    recipient = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        message_text = request.form.get('message', '').strip()
        
        if not subject or not message_text:
            flash('❌ El asunto y el mensaje son obligatorios.', 'danger')
            return redirect(url_for('super_admin.send_message_to_user', user_id=user_id))
        
        new_message = UserMessage(
            sender_id=current_user.id,
            recipient_id=recipient.id,
            subject=subject,
            message=message_text
        )
        db.session.add(new_message)
        db.session.commit()
        
        flash(f'✅ Mensaje enviado a {recipient.display_name} ({recipient.email})', 'success')
        return redirect(url_for('super_admin.manage_users'))
    
    return render_template('super_admin/send_message.html', recipient=recipient)


@super_admin_bp.route('/messages/sent')
@login_required
@super_admin_required
def sent_messages():
    """Super Admin ve todos los mensajes enviados"""
    messages = UserMessage.query.filter_by(sender_id=current_user.id)\
        .order_by(UserMessage.created_at.desc()).all()
    return render_template('super_admin/sent_messages.html', messages=messages)


@main_bp.route('/mis-mensajes')
@login_required
def my_messages():
    """Usuario ve sus mensajes recibidos del Super Admin"""
    messages = UserMessage.query.filter_by(recipient_id=current_user.id)\
        .order_by(UserMessage.created_at.desc()).all()
    
    for msg in messages:
        if not msg.is_read:
            msg.is_read = True
    db.session.commit()
    
    return render_template('user_messages.html', messages=messages)


@main_bp.route('/mis-mensajes/<int:message_id>')
@login_required
def read_message(message_id):
    """Usuario lee un mensaje específico"""
    message = UserMessage.query.get_or_404(message_id)
    
    if message.recipient_id != current_user.id:
        flash(' Acceso denegado.', 'danger')
        return redirect(url_for('main.my_messages'))
    
    if not message.is_read:
        message.is_read = True
        db.session.commit()
    
    return render_template('read_message.html', message=message)


# ============ NOTIFICACIONES MASIVAS ============

@super_admin_bp.route('/notifications')
@login_required
@super_admin_required
def notifications_list():
    """Lista de todas las notificaciones enviadas"""
    notifications = Notification.query.order_by(Notification.created_at.desc()).all()
    return render_template('super_admin/notifications_list.html', notifications=notifications)


@super_admin_bp.route('/notifications/new', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_notification():
    """Crear nueva notificación masiva"""
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        notification_type = request.form.get('notification_type', 'all')
        
        if not title or not message:
            flash('❌ El título y el mensaje son obligatorios.', 'danger')
            return redirect(url_for('super_admin.create_notification'))
        
        notification = Notification(
            title=title,
            message=message,
            notification_type=notification_type,
            sent_by=current_user.id
        )
        db.session.add(notification)
        db.session.flush()
        
        if notification_type == 'all':
            recipients = User.query.filter_by(is_active=True).all()
        elif notification_type == 'business':
            recipients = User.query.filter_by(is_active=True, is_admin=True, is_super_admin=False).all()
        elif notification_type == 'delivery':
            recipients = User.query.filter_by(is_active=True, is_delivery=True).all()
        elif notification_type == 'customer':
            recipients = User.query.filter_by(is_active=True, is_admin=False, is_delivery=False, is_super_admin=False).all()
        else:
            recipients = []
        
        for user in recipients:
            recipient = NotificationRecipient(
                notification_id=notification.id,
                user_id=user.id
            )
            db.session.add(recipient)
        
        notification.is_sent = True
        db.session.commit()
        
        flash(f'✅ Notificación enviada a {len(recipients)} usuario(s).', 'success')
        return redirect(url_for('super_admin.notifications_list'))
    
    return render_template('super_admin/create_notification.html')


@super_admin_bp.route('/notifications/<int:notification_id>')
@login_required
@super_admin_required
def view_notification(notification_id):
    """Ver detalles de una notificación"""
    notification = Notification.query.get_or_404(notification_id)
    return render_template('super_admin/view_notification.html', notification=notification)


@main_bp.route('/mis-notificaciones')
@login_required
def my_notifications():
    """Usuario ve sus notificaciones"""
    recipients = NotificationRecipient.query.filter_by(user_id=current_user.id)\
        .join(Notification)\
        .order_by(Notification.created_at.desc()).all()
    
    for recipient in recipients:
        if not recipient.is_read:
            recipient.is_read = True
            recipient.read_at = datetime.now(timezone.utc)
    
    db.session.commit()
    
    return render_template('user_notifications.html', recipients=recipients)


@main_bp.route('/notificacion/<int:notification_id>')
@login_required
def view_user_notification(notification_id):
    """Usuario lee una notificación específica"""
    notification = Notification.query.get_or_404(notification_id)
    
    recipient = NotificationRecipient.query.filter_by(
        notification_id=notification_id,
        user_id=current_user.id
    ).first()
    
    if not recipient:
        flash('❌ No tienes permiso para ver esta notificación.', 'danger')
        return redirect(url_for('main.my_notifications'))
    
    if not recipient.is_read:
        recipient.is_read = True
        recipient.read_at = datetime.now(timezone.utc)
        db.session.commit()
    
    return render_template('view_notification_user.html', notification=notification)
