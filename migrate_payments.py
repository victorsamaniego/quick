from app import app, db
from sqlalchemy import text

with app.app_context():
    conn = db.engine.connect()
    try:
        conn.execute(text("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'cash'"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN cash_bill_amount REAL DEFAULT 0.0"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN needs_change BOOLEAN DEFAULT 0"))
        conn.execute(text("ALTER TABLE orders ADD COLUMN payment_receipt TEXT"))
        conn.commit()
        print("✅ Columnas de pago agregadas a la base de datos")
    except Exception as e:
        print("ℹ️ Las columnas ya existen o hubo un error menor:", e)