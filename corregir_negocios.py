from app import app, db
from models import Business, User, Product, Order

with app.app_context():
    print("=" * 60)
    print("🔧 CORRECCIÓN DE NEGOCIOS Y PEDIDOS")
    print("=" * 60)
    
    # 1. Verificar el admin cacique
    cacique = User.query.filter_by(username='cacique').first()
    print(f"\n👤 Admin cacique: {cacique.email}")
    print(f"   Business_ID actual: {cacique.business_id}")
    
    # 2. Verificar los productos del negocio ID 1 (Pods Luxury)
    productos_pods = Product.query.filter_by(business_id=1).all()
    print(f"\n📦 Productos en Pods Luxury (ID 1): {len(productos_pods)}")
    for p in productos_pods:
        print(f"   - {p.name} (ID: {p.id})")
    
    # 3. OPCIÓN A: Cambiar el business_id del admin cacique a 1 (Pods Luxury)
    #    Esto hace que cacique sea admin de Pods Luxury
    print("\n" + "=" * 60)
    print("¿Qué querés hacer?")
    print("1. Hacer que 'cacique' sea admin de 'Pods Luxury' (ID 1)")
    print("2. Mover los productos de 'Pods Luxury' al negocio de 'cacique' (ID 3)")
    print("=" * 60)
    
    opcion = input("Elegí una opción (1 o 2): ").strip()
    
    if opcion == '1':
        # Opción 1: Cambiar el business_id del admin cacique a 1
        cacique.business_id = 1
        db.session.commit()
        print(f"\n✅ Admin 'cacique' ahora es admin de 'Pods Luxury' (ID 1)")
        print(f"   Los pedidos ya le aparecerán en su panel")
        
    elif opcion == '2':
        # Opción 2: Mover los productos al negocio de cacique (ID 3)
        for producto in productos_pods:
            producto.business_id = 3
            print(f"    Producto '{producto.name}' movido al negocio ID 3")
        
        # También reasignar los pedidos
        pedidos = Order.query.filter_by(business_id=1).all()
        for pedido in pedidos:
            pedido.business_id = 3
            print(f"    Pedido #{pedido.id} reasignado al negocio ID 3")
        
        db.session.commit()
        print(f"\n✅ Productos y pedidos movidos al negocio de 'cacique' (ID 3)")
        
    else:
        print("❌ Opción no válida")
    
    print("\n" + "=" * 60)
    print("✅ Corrección completada")
    print("=" * 60)