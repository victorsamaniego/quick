from app import app, db

with app.app_context():
    print("🔧 Agregando columnas de geolocalización a negocios...\n")
    
    try:
        db.session.execute('ALTER TABLE businesses ADD COLUMN latitude FLOAT')
        print("✅ Columna 'latitude' agregada")
    except Exception as e:
        print(f"⚠️  Columna 'latitude': {e}")
    
    try:
        db.session.execute('ALTER TABLE businesses ADD COLUMN longitude FLOAT')
        print("✅ Columna 'longitude' agregada")
    except Exception as e:
        print(f"⚠️  Columna 'longitude': {e}")
    
    try:
        db.session.execute('ALTER TABLE businesses ADD COLUMN delivery_radius_km FLOAT DEFAULT 10.0')
        print("✅ Columna 'delivery_radius_km' agregada")
    except Exception as e:
        print(f"⚠️  Columna 'delivery_radius_km': {e}")
    
    db.session.commit()
    
    print("\n✅ Migración completada")
    print("\n💡 PRÓXIMO PASO:")
    print("Ejecutá: python agregar_coordenadas_negocios.py")