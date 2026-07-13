from app import app, db
from models import Order

with app.app_context():
    # Usamos el inspector de SQLAlchemy para ver columnas existentes
    from sqlalchemy import inspect
    
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('orders')]
    
    print(f"Columnas actuales en 'orders': {columns}")
    
    # Lista de columnas que DEBEN existir
    required_columns = ['payment_method', 'cash_bill_amount', 'needs_change', 'payment_receipt_url']
    
    # Verificar y agregar las que faltan
    for col in required_columns:
        if col not in columns:
            print(f"⚠️ Falta columna: {col}. Agregándola...")
            with db.engine.connect() as conn:
                if col == 'payment_method':
                    conn.execute(db.text("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'cash'"))
                elif col == 'cash_bill_amount':
                    conn.execute(db.text("ALTER TABLE orders ADD COLUMN cash_bill_amount REAL DEFAULT 0.0"))
                elif col == 'needs_change':
                    conn.execute(db.text("ALTER TABLE orders ADD COLUMN needs_change BOOLEAN DEFAULT 0"))
                elif col == 'payment_receipt_url':
                    conn.execute(db.text("ALTER TABLE orders ADD COLUMN payment_receipt_url TEXT"))
                conn.commit()
            print(f"✅ Columna '{col}' agregada")
        else:
            print(f"✅ Columna '{col}' ya existe")
    
    print("\n🎉 ¡Base de datos actualizada! Reiniciá Flask y probá de nuevo.")