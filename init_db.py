"""
🚀 Script para inicializar la base de datos de QuickGo desde cero
Elimina la DB antigua y crea todas las tablas + datos iniciales
"""

from app import app, db
from models import User, Business, Product, Category, Order, OrderItem, OTPCode
import os

def init_database():
    with app.app_context():
        # Si existe la DB antigua, borrarla
        db_path = os.path.join(os.path.dirname(__file__), 'pods_luxury.db')
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"🗑️ Base de datos antigua eliminada: {db_path}")
        
        # Crear TODAS las tablas según los modelos
        print("🔄 Creando tablas...")
        db.create_all()
        print("✅ Tablas creadas exitosamente")
        
        # Crear el negocio principal "Pods Luxury"
        print("🏢 Creando negocio principal...")
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
        
        # Crear SUPER ADMIN
        print("👑 Creando Super Admin...")
        if not User.query.filter_by(email='admingeneral@quickgo.com').first():
            super_admin = User(
                email='admingeneral@quickgo.com',
                phone='0981234567',
                is_super_admin=True,
                is_active=True
            )
            super_admin.set_password('4959761.sama')
            db.session.add(super_admin)
            print("✅ Super Admin: admingeneral@quickgo.com / 4959761.sama")
        
        # Crear Admin del negocio principal
        print("👤 Creando Admin de Pods Luxury...")
        if not User.query.filter_by(email='admin@podsluxury.com').first():
            admin = User(
                email='admin@podsluxury.com',
                phone='0981234567',
                is_admin=True,
                is_active=True,
                business_id=main_business.id
            )
            admin.set_password('4959761.sama')
            db.session.add(admin)
            print("✅ Admin: admin@podsluxury.com / 4959761.sama")
        
        # Crear usuario Delivery de prueba
        print("🛵 Creando Delivery de prueba...")
        if not User.query.filter_by(email='delivery@podsluxury.com').first():
            delivery = User(
                email='delivery@podsluxury.com',
                phone='0987654321',
                is_delivery=True,
                is_active=True,
                business_id=main_business.id
            )
            delivery.set_password('delivery123')
            db.session.add(delivery)
            print("✅ Delivery: delivery@podsluxury.com / delivery123")
        
        # Crear categorías de prueba
        print("📁 Creando categorías...")
        categories = [
            Category(name='Pods Desechables', business_id=main_business.id),
            Category(name='Pods Recargables', business_id=main_business.id),
            Category(name='Accesorios', business_id=main_business.id),
            Category(name='Líquidos', business_id=main_business.id),
        ]
        db.session.add_all(categories)
        db.session.commit()
        
        # Crear productos de prueba
        print("📦 Creando productos de prueba...")
        products = [
            Product(
                name='Pod Premium Gold',
                description='Pod desechable premium sabor dorado',
                precio_compra=15000,
                price=25000,
                stock=50,
                category_id=categories[0].id,
                business_id=main_business.id,
                image_url='uploads/placeholder.png'
            ),
            Product(
                name='Pod Classic Silver',
                description='Pod clásico sabor plata',
                precio_compra=12000,
                price=20000,
                stock=30,
                category_id=categories[0].id,
                business_id=main_business.id,
                image_url='uploads/placeholder.png'
            ),
        ]
        db.session.add_all(products)
        db.session.commit()
        
        # Actualizar estadísticas del negocio
        main_business.total_products = Product.query.filter_by(business_id=main_business.id, is_active=True).count()
        db.session.commit()
        
        print("\n" + "="*60)
        print("🎉 ¡BASE DE DATOS INICIALIZADA EXITOSAMENTE!")
        print("="*60)
        print(f"📊 Resumen:")
        print(f"   • Negocios: {Business.query.count()}")
        print(f"   • Usuarios: {User.query.count()}")
        print(f"   • Productos: {Product.query.count()}")
        print(f"   • Categorías: {Category.query.count()}")
        print(f"\n🔐 Credenciales de prueba:")
        print(f"   👑 Super Admin: admingeneral@quickgo.com / 4959761.sama")
        print(f"   👤 Admin: admin@podsluxury.com / 4959761.sama")
        print(f"   🛵 Delivery: delivery@podsluxury.com / delivery123")
        print("="*60)

if __name__ == '__main__':
    init_database()