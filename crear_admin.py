from app import app, db
from models import User

with app.app_context():
    admin = User(
        username='admin_quickgo',  # Username diferente
        email='superadmin@quickgo.com',  # Email diferente
        phone='0981000000',
        is_active=True,
        is_super_admin=True
    )
    admin.set_password('Admin2024!')  # Contraseña diferente
    db.session.add(admin)
    db.session.commit()
    print('✅ Super Admin creado')
    print('📧 Email: superadmin@quickgo.com')
    print(' Usuario: admin_quickgo')
    print('🔑 Contraseña: Admin2024!')