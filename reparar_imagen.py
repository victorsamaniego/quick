from app import create_app
from models import db, Product

app = create_app()
with app.app_context():
    p = Product.query.filter_by(name='fdsf').first()
    if p:
        p.image_url = 'uploads/ed6c566d1199a503_pilsen.png'
        db.session.commit()
        print("✅ LISTO! Ahora fdsf tiene imagen:", p.image_url)
    else:
        print("❌ No se encontró el producto fdsf")