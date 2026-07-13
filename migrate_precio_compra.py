from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        try:
            # Usar text() para ejecutar SQL en SQLAlchemy 2.0
            conn.execute(text("ALTER TABLE products ADD COLUMN precio_compra REAL DEFAULT 0"))
            conn.commit()
            print("✅ Campo 'precio_compra' agregado exitosamente")
        except Exception as e:
            print(f"ℹ️ El campo puede ya existir: {e}")