from app import app, db
from models import Business
from sqlalchemy import inspect, text

with app.app_context():
    print("🔧 Verificando y aplicando migración de geolocalización...\n")
    
    # Verificar qué columnas tiene la tabla businesses
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('businesses')]
    
    print(f"📋 Columnas actuales en 'businesses': {len(columns)}")
    print(f"   {', '.join(columns)}\n")
    
    # Verificar si faltan las columnas de geolocalización
    needed_columns = ['latitude', 'longitude', 'delivery_radius_km']
    missing_columns = [col for col in needed_columns if col not in columns]
    
    if missing_columns:
        print(f"⚠️  Faltan columnas: {', '.join(missing_columns)}")
        print("🔧 Aplicando migración...\n")
        
        # Intentar agregar las columnas faltantes
        for col in missing_columns:
            try:
                if col == 'latitude':
                    db.session.execute(text('ALTER TABLE businesses ADD COLUMN latitude FLOAT'))
                    print(f"✅ Columna 'latitude' agregada")
                elif col == 'longitude':
                    db.session.execute(text('ALTER TABLE businesses ADD COLUMN longitude FLOAT'))
                    print(f"✅ Columna 'longitude' agregada")
                elif col == 'delivery_radius_km':
                    db.session.execute(text('ALTER TABLE businesses ADD COLUMN delivery_radius_km FLOAT DEFAULT 10.0'))
                    print(f"✅ Columna 'delivery_radius_km' agregada")
            except Exception as e:
                print(f"⚠️  Error con columna '{col}': {e}")
        
        db.session.commit()
        print("\n✅ Migración completada")
    else:
        print("✅ Todas las columnas de geolocalización ya existen")
    
    # Verificar que todo esté bien
    print("\n" + "="*50)
    print("🔍 VERIFICACIÓN FINAL:")
    print("="*50)
    
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('businesses')]
    
    if all(col in columns for col in needed_columns):
        print("✅ ¡Migración exitosa! Todas las columnas están presentes")
        print("\n💡 PRÓXIMO PASO:")
        print("Ejecutá: python agregar_coordenadas_negocios.py")
    else:
        print("❌ Error: Algunas columnas aún faltan")
        print(f"   Columnas presentes: {', '.join(columns)}")
        print(f"   Columnas faltantes: {[c for c in needed_columns if c not in columns]}")