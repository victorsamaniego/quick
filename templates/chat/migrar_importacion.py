from app import app, db

with app.app_context():
    try:
        # Agregar columna si es Importación
        db.session.execute('ALTER TABLE products ADD COLUMN es_importacion BOOLEAN DEFAULT 0')
        db.session.commit()
        print("✅ Columna 'es_importacion' creada")
        
        # Agregar columna para cantidad mínima
        db.session.execute('ALTER TABLE products ADD COLUMN minimo_pedido INTEGER DEFAULT 12')
        db.session.commit()
        print("✅ Columna 'minimo_pedido' creada (Default: 12)")
        
        print("🎉 ¡Base de datos lista para Importación!")
    except Exception as e:
        print(f"⚠️ Nota: Si ya tenés las columnas, podés ignorar este error: {e}")