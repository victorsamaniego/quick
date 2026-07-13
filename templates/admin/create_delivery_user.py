from app import app, db
from models import User

with app.app_context():
    # Verificar si ya existe
    existing = User.query.filter_by(email='delivery@podsluxury.com').first()
    if existing:
        print("⚠️ El usuario delivery ya existe")
    else:
        # Crear nuevo usuario delivery
        delivery = User(
            email='delivery@podsluxury.com',
            phone='0981234567',
            is_active=True,
            is_admin=False,
            is_delivery=True  # ✅ IMPORTANTE
        )
        delivery.set_password('delivery123')
        db.session.add(delivery)
        db.session.commit()
        print("✅ Usuario delivery creado exitosamente")
        print(f"📧 Email: delivery@podsluxury.com")
        print(f"🔑 Password: delivery123")
        print(f"🛵 Rol: Delivery Driver")