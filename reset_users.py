from app import app, db
from models import User, Business

with app.app_context():
    # Buscar o crear negocio de prueba (opcional, para vincular admins)
    business = Business.query.filter_by(slug='pods-luxury').first()
    
    # 1️⃣ Super Admin
    admin = User.query.filter_by(email='admingeneral@quickgo.com').first()
    if not admin:
        admin = User(email='admingeneral@quickgo.com', phone='0981234567', is_super_admin=True, is_active=True)
        db.session.add(admin)
    admin.set_password('4959761.sama')
    
    # 2️⃣ Admin de Negocio
    admin_neg = User.query.filter_by(email='admin@podsluxury.com').first()
    if not admin_neg:
        admin_neg = User(email='admin@podsluxury.com', phone='0981234567', is_admin=True, is_active=True, business_id=business.id if business else None)
        db.session.add(admin_neg)
    admin_neg.set_password('4959761.sama')
    
    # 3️⃣ Delivery
    delivery = User.query.filter_by(email='delivery@podsluxury.com').first()
    if not delivery:
        delivery = User(email='delivery@podsluxury.com', phone='0987654321', is_delivery=True, is_active=True, business_id=business.id if business else None)
        db.session.add(delivery)
    delivery.set_password('delivery123')
    
    db.session.commit()
    
    print("\n✅ Usuarios listos para ingresar:")
    print(" admingeneral@quickgo.com / 4959761.sama")
    print("👤 admin@podsluxury.com / 4959761.sama")
    print("🛵 delivery@podsluxury.com / delivery123")