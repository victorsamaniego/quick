from app import app, db
from models import OrderItem, Product
from sqlalchemy import text, inspect

with app.app_context():
    print("\n" + "="*70)
    print("🔧 MIGRACIÓN: Agregando campo product_name a order_items")
    print("="*70 + "\n")
    
    # Verificar si la columna ya existe
    inspector = inspect(db.engine)
    columns = [col['name'] for col in inspector.get_columns('order_items')]
    
    if 'product_name' not in columns:
        print("📝 Agregando columna product_name a la tabla order_items...")
        
        # Ejecutar SQL para agregar la columna
        with db.engine.connect() as conn:
            conn.execute(text('ALTER TABLE order_items ADD COLUMN product_name VARCHAR(200)'))
            conn.commit()
        
        print("✅ Columna product_name agregada exitosamente\n")
    else:
        print("ℹ️  La columna product_name ya existe\n")
    
    # Actualizar order_items existentes con el nombre del producto
    print("🔄 Actualizando order_items existentes con el nombre del producto...")
    
    order_items = OrderItem.query.all()
    updated = 0
    not_found = 0
    
    for item in order_items:
        # Si no tiene product_name pero tiene product_id
        if not item.product_name and item.product_id:
            product = Product.query.get(item.product_id)
            if product:
                item.product_name = product.name
                updated += 1
            else:
                item.product_name = f'Producto ID {item.product_id} (eliminado)'
                not_found += 1
        elif not item.product_name:
            item.product_name = 'Producto desconocido'
            not_found += 1
    
    db.session.commit()
    
    print(f"✅ {updated} order_items actualizados con el nombre del producto")
    print(f"⚠️  {not_found} order_items no tenían producto asociado")
    
    print("\n" + "="*70)
    print("✅ MIGRACIÓN COMPLETADA")
    print("="*70)
    print("\n💡 De ahora en adelante:")
    print("   • Los nuevos pedidos guardarán el nombre del producto")
    print("   • Aunque elimines el producto, el historial mostrará el nombre correcto")
    print("   • Nunca más verás 'Producto eliminado' en los pedidos\n")