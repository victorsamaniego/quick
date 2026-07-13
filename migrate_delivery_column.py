from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        try:
            # Agregar columna is_delivery a la tabla users
            conn.execute(text("ALTER TABLE users ADD COLUMN is_delivery BOOLEAN DEFAULT FALSE"))
            conn.commit()
            print("✅ Columna 'is_delivery' agregada exitosamente")
        except Exception as e:
            print(f"ℹ️ La columna puede ya existir: {e}")