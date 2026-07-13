#!/usr/bin/env python3
from app import app, db
from models import Order

with app.app_context():
    # Agregar columnas si no existen (SQLite)
    with db.engine.connect() as conn:
        try:
            conn.execute("ALTER TABLE orders ADD COLUMN client_latitude REAL")
            conn.execute("ALTER TABLE orders ADD COLUMN client_longitude REAL")
            conn.execute("ALTER TABLE orders ADD COLUMN delivery_latitude REAL")
            conn.execute("ALTER TABLE orders ADD COLUMN delivery_longitude REAL")
            conn.execute("ALTER TABLE orders ADD COLUMN delivery_fee REAL DEFAULT 0")
            conn.commit()
            print("✅ Columnas de geolocalización agregadas")
        except Exception as e:
            print(f"ℹ️ Columnas pueden ya existir: {e}")