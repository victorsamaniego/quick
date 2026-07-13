from app import app, db
from sqlalchemy import text

with app.app_context():
    print("🔧 Agregando nuevos campos y tablas...")
    
    try:
        db.session.execute(text('ALTER TABLE businesses ADD COLUMN requires_subscription BOOLEAN DEFAULT 1'))
        print("✅ requires_subscription agregado")
    except Exception as e:
        print(f"⚠️  requires_subscription: ya existe o error")
    
    try:
        db.session.execute(text('ALTER TABLE businesses ADD COLUMN subscription_exempt_reason VARCHAR(200)'))
        print("✅ subscription_exempt_reason agregado")
    except Exception as e:
        print(f"️  subscription_exempt_reason: ya existe o error")
    
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS support_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_from_admin BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_read BOOLEAN DEFAULT 0
            )
        '''))
        print("✅ Tabla support_chats creada")
    except Exception as e:
        print(f"️  support_chats: {e}")
    
    try:
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS delivery_business_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_from_delivery BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_read BOOLEAN DEFAULT 0
            )
        '''))
        print("✅ Tabla delivery_business_chats creada")
    except Exception as e:
        print(f"️  delivery_business_chats: {e}")
    
    db.session.commit()
    print("\n✅ ¡Migración completada!")