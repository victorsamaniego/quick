from app import app, db
from models import Business

with app.app_context():
    db.create_all()
    print("✅ Base de datos actualizada con las columnas de suscripción")