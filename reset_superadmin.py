from app import app, db
from models import User
import time

with app.app_context():
    # 1. Buscar CUALQUIER super admin que ya exista en la base de datos
    admin = User.query.filter_by(is_super_admin=True).first()
    
    if admin:
        print(f"🔍 Super Admin encontrado: {admin.email} (Usuario: {admin.username})")
        # Solo actualizamos la contraseña y nos aseguramos que esté activo
        admin.set_password('Admin2024!')
        admin.is_active = True
        db.session.commit()
        print("✅ Contraseña del Super Admin actualizada exitosamente.")
    else:
        print("🔍 No se encontró ningún Super Admin. Creando uno nuevo...")
        # Usamos un email con la hora actual para garantizar que sea 100% único
        unique_email = f"superadmin_{int(time.time())}@quickgo.com"
        admin = User(
            username='superadmin_definitivo',
            email=unique_email,
            phone='0981000000',
            is_active=True,
            is_super_admin=True
        )
        admin.set_password('Admin2024!')
        db.session.add(admin)
        db.session.commit()
        print("✅ Nuevo Super Admin creado exitosamente.")
        
    print("\n" + "="*60)
    print("🚀 CREDENCIALES PARA INICIAR SESIÓN:")
    print(f"📧 Email: {admin.email}")
    print(f"👤 Usuario: {admin.username}")
    print("🔑 Contraseña: Admin2024!")
    print("="*60)