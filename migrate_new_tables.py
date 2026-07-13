from app import app, db
from models import DeliveryRequest, ChatMessage
from sqlalchemy import text, inspect

with app.app_context():
    print("\n" + "="*70)
    print("🔧 MIGRACIÓN: Creando nuevas tablas")
    print("="*70 + "\n")
    
    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()
    
    # Crear tabla delivery_requests si no existe
    if 'delivery_requests' not in existing_tables:
        print("📝 Creando tabla delivery_requests...")
        with db.engine.connect() as conn:
            conn.execute(text('''
                CREATE TABLE delivery_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    business_id INTEGER NOT NULL,
                    driver_id INTEGER,
                    status VARCHAR(20) DEFAULT 'pending',
                    search_radius FLOAT NOT NULL,
                    created_at DATETIME,
                    accepted_at DATETIME,
                    expires_at DATETIME,
                    FOREIGN KEY (order_id) REFERENCES orders (id),
                    FOREIGN KEY (business_id) REFERENCES businesses (id),
                    FOREIGN KEY (driver_id) REFERENCES users (id)
                )
            '''))
            conn.commit()
        print("✅ Tabla delivery_requests creada\n")
    else:
        print("ℹ️  La tabla delivery_requests ya existe\n")
    
    # Crear tabla chat_messages si no existe
    if 'chat_messages' not in existing_tables:
        print("📝 Creando tabla chat_messages...")
        with db.engine.connect() as conn:
            conn.execute(text('''
                CREATE TABLE chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    created_at DATETIME,
                    is_read BOOLEAN DEFAULT 0,
                    FOREIGN KEY (order_id) REFERENCES orders (id),
                    FOREIGN KEY (sender_id) REFERENCES users (id)
                )
            '''))
            conn.commit()
        print("✅ Tabla chat_messages creada\n")
    else:
        print("ℹ️  La tabla chat_messages ya existe\n")
    
    print("="*70)
    print("✅ MIGRACIÓN COMPLETADA")
    print("="*70)
    print("\n💡 Ahora podés usar:")
    print("   • Buscar deliverys externos")
    print("   • Chat entre negocio, cliente y delivery")
    print("   • Notificaciones en tiempo real\n")