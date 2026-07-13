from app import app, db
from models import User, Business

with app.app_context():
    # Buscar el admin
    admin = User.query.filter_by(email='admin@podsluxury.com').first()
    
    if not admin:
        print("❌ No se encontró el usuario admin@podsluxury.com")
        exit()
    
    # Buscar cualquier negocio activo
    business = Business.query.filter_by(is_active=True).first()
    
    if not business:
        print("❌ No hay negocios disponibles en la base de datos")
        print("Creando un negocio de prueba...")
        
        business = Business(
            name='Pods Luxury',
            slug='pods-luxury',
            description='Negocio principal',
            phone='0981234567',
            address='Asunción, Paraguay',
            is_active=True
        )
        db.session.add(business)
        db.session.commit()
        print(f"✅ Negocio '{business.name}' creado con ID: {business.id}")
    
    # Asignar el negocio al admin
    admin.business_id = business.id
    admin.is_admin = True
    db.session.commit()
    
    print(f"\n✅ ÉXITO!")
    print(f"   Usuario: {admin.email}")
    print(f"   Negocio asignado: {business.name} (ID: {business.id})")
    print(f"   Slug: {business.slug}")
    print("\n🎉 Ahora podés crear productos como admin!")