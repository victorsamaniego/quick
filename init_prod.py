from app import create_app
from models import db, User, SecurityQuestion

app = create_app()
with app.app_context():
    db.create_all()
    SecurityQuestion.seed_default_questions()
    if not User.query.filter_by(is_super_admin=True).first():
        admin = User(
            email='admin@quickgo.com',
            username='SuperAdmin',
            phone='0981000000',
            is_active=True,
            is_super_admin=True
        )
        admin.set_password('Admin123!')
        db.session.add(admin)
        db.session.commit()
        print('SUPER ADMIN CREADO: admin@quickgo.com / Admin123!')
    print('TABLAS LISTAS')