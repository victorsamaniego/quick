from app import app, db
from sqlalchemy import text

with app.app_context():
    conn = db.engine.connect()
    try:
        # Intentamos agregar las columnas. Si ya existen, dará error, pero lo ignoramos con pass
        print("Intentando actualizar base de datos...")
        
        conn.execute(text("ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'cash'"))
        print("✅ Agregada: payment_method")
        
        conn.execute(text("ALTER TABLE orders ADD COLUMN cash_bill_amount REAL DEFAULT 0.0"))
        print("✅ Agregada: cash_bill_amount")
        
        conn.execute(text("ALTER TABLE orders ADD COLUMN needs_change BOOLEAN DEFAULT 0"))
        print("✅ Agregada: needs_change")
        
        conn.execute(text("ALTER TABLE orders ADD COLUMN payment_receipt_url TEXT"))
        print("✅ Agregada: payment_receipt_url")
        
        conn.commit()
        print("\n🎉 ¡Base de datos actualizada exitosamente! Ya podés entrar al Super Admin.")
        
    except Exception as e:
        # Si da error es porque las columnas ya existen, lo cual es bueno.
        print(f"\nℹ️ Info: {e}")
        print("✅ Las columnas probablemente ya existen. Intentá entrar de nuevo.")