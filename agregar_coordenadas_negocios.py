from app import app, db
from models import Business

with app.app_context():
    print("🔧 Agregando coordenadas a negocios existentes...\n")
    
    #  IMPORTANTE: Reemplazá con los datos REALES de tu negocio
    negocios_data = [
        {
            'id': 1,  # ← ID de tu negocio (dejá 1 si es el primero)
            'name': 'Pods Luxury',
            'lat': -25.2637,  # ← CAMBIÁ por tu latitud real
            'lon': -57.5759,  # ← CAMBIÁ por tu longitud real
            'radius': 10      # ← Radio de delivery en km
        },
    ]
    
    actualizados = 0
    
    for data in negocios_data:
        business = Business.query.get(data['id'])
        
        if business:
            business.latitude = data['lat']
            business.longitude = data['lon']
            business.delivery_radius_km = data['radius']
            
            print(f"✅ {business.name}")
            print(f"   📍 Coordenadas: {data['lat']}, {data['lon']}")
            print(f"   📏 Radio de delivery: {data['radius']} km")
            print()
            actualizados += 1
        else:
            print(f"❌ Negocio ID {data['id']} no encontrado")
    
    db.session.commit()
    
    print("="*50)
    print(f"✅ Negocios actualizados: {actualizados}")
    print("="*50)
    
    print("\n LISTA DE NEGOCIOS CON COORDENADAS:")
    print("="*50)
    
    all_businesses = Business.query.all()
    for business in all_businesses:
        if business.latitude and business.longitude:
            print(f"✅ {business.name}")
            print(f"   ID: {business.id}")
            print(f"   📍 {business.latitude}, {business.longitude}")
            print(f"   📏 Radio: {business.delivery_radius_km} km")
            print()
        else:
            print(f"⚠️  {business.name} - SIN COORDENADAS")
            print()
    
    print("="*50)
    print("\n💡 PRÓXIMO PASO:")
    print("1. Reiniciá Flask: Ctrl+C y luego python app.py")
    print("2. Entrá como cliente y actualizá tu ubicación")
    print("3. Solo verás productos de negocios cercanos")
    print("="*50)