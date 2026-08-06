from app import app, db
from models import UserMessage

with app.app_context():
    # Crear solo la tabla user_messages
    db.create_all()
    print("✅ Tabla user_messages creada exitosamente")python crear_tabla_mensajes.py