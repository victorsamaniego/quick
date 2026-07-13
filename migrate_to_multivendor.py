from app import app, db
from models import Business, User, Product, Category, Order

with app.app_context():
    print("🔄 Iniciando migración a Multi-Vendedor...")
    
    # 1. Crear el negocio principal si no existe
    main_business = Business.query.filter_by(slug='pods-luxury').first()
    if not main_business:
        main_business = Business(
            name='Pods Luxury',
            slug='pods-luxury',
            description='Tu tienda de pods y accesorios premium',
            phone='0981234567',
            address='Asunción, Paraguay',
            commission_rate=0.10,
            delivery_fee_base=5000,
            delivery_fee_per_km=1000
        )
        db.session.add(main_business)
        db.session.commit()
        print(f"✅ Negocio creado: {main_business.name}")
    
    # 2. Asignar productos existentes al negocio principal
    products_without_business = Product.query.filter_by(business_id=None).all()
    for product in products_without_business:
        product.business_id = main_business.id
    db.session.commit()
    print(f"✅ {len(products_without_business)} productos asignados al negocio")
    
    # 3. Asignar categorías existentes al negocio principal
    categories_without_business = Category.query.filter_by(business_id=None).all()
    for category in categories_without_business:
        category.business_id = main_business.id
    db.session.commit()
    print(f"✅ {len(categories_without_business)} categorías asignadas")
    
    # 4. Asignar pedidos existentes al negocio principal
    orders_without_business = Order.query.filter_by(business_id=None).all()
    for order in orders_without_business:
        order.business_id = main_business.id
    db.session.commit()
    print(f"✅ {len(orders_without_business)} pedidos asignados")
    
    # 5. Asignar admin existente al negocio principal
    admin_user = User.query.filter_by(email='admin@podsluxury.com').first()
    if admin_user and not admin_user.business_id:
        admin_user.business_id = main_business.id
        admin_user.is_admin = True
        db.session.commit()
        print(f"✅ Admin asignado al negocio")
    
    # 6. Crear SUPER ADMIN si no existe
    super_admin = User.query.filter_by(email='admingeneral@quickgo.com').first()
    if not super_admin:
        super_admin = User(
            email='admingeneral@quickgo.com',
            phone='0981234567',
            is_super_admin=True,
            is_active=True
        )
        super_admin.set_password('4959761.sama')
        db.session.add(super_admin)
        db.session.commit()
        print(f"✅ Super Admin creado: admingeneral@quickgo.com / 4959761.sama")
    
    # 7. Actualizar estadísticas de negocios
    businesses = Business.query.all()
    for business in businesses:
        business.total_products = Product.query.filter_by(business_id=business.id, is_active=True).count()
        business.total_orders = Order.query.filter_by(business_id=business.id).count()
        business.total_sales = db.session.query(db.func.sum(Order.total_amount)).filter_by(business_id=business.id, status='delivered').scalar() or 0
    db.session.commit()
    
    print("🎉 Migración completada exitosamente!")
    print(f"📊 Resumen:")
    print(f"   - Negocios: {Business.query.count()}")
    print(f"   - Productos: {Product.query.count()}")
    print(f"   - Usuarios: {User.query.count()}")
    print(f"   - Super Admin: admingeneral@quickgo.com")