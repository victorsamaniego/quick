from app import app, db
from models import User, Business

with app.app_context():
    # Buscar el delivery
    delivery = User.query.filter_by(email='delivery@gmail.com').first()
    
    if not delivery:
        print("❌ No se encontró delivery@gmail.com")
        print("Usuarios en la base de datos:")
        for u in User.query.all():
            print(f"  - {u.email} (ID: {u.id})")
        exit()
    
    # Buscar el negocio
    business = Business.query.filter_by(slug='pods-luxury').first()
    
    if not business:
        print("❌ No se encontró el negocio 'pods-luxury'")
        print("Negocios en la base de datos:")
        for b in Business.query.all():
            print(f"  - {b.name} (slug: {b.slug}, ID: {b.id})")
        exit()
    
    # Asignar negocio al delivery
    delivery.business_id = business.id
    delivery.is_delivery = True
    delivery.is_active = True
    db.session.commit()
    
    print(f"\n✅ ¡DELIVERY ASIGNADO EXITOSAMENTE!")
    print(f"   Usuario: {delivery.email}")
    print(f"   Negocio: {business.name} (ID: {business.id})")
    print(f"   Rol: Delivery")
    print(f"\n🎉 Ahora podés asignar este delivery a los pedidos!")
    print("   Refrescá la página de pedidos (F5) y probá de nuevo.")