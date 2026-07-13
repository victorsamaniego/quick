from app import app, db
from models import User

with app.app_context():
    # Buscar si existe el admin
    admin = User.query.filter_by(email='admingeneral@quickgo.com').first()
    
    if admin:
        # Si existe, actualizar contraseña
        admin.set_password('4959761.sama')
        admin.is_super_admin = True
        admin.is_active = True
        print(f"✅ Super Admin actualizado: {admin.email}")
    else:
        # Si no existe, crearlo
        admin = User(
            email='admingeneral@quickgo.com',
            phone='0981234567',
            is_super_admin=True,
            is_active=True
        )
        admin.set_password('4959761.sama')
        db.session.add(admin)
        print(f"✅ Super Admin creado: {admin.email}")
    
    db.session.commit()
    print("🎉 ¡Listo! Ya podés ingresar con:")
    print("   Email: admingeneral@quickgo.com")
    print("   Contraseña: 4959761.sama")