from app import app, db
from models import Notification, NotificationRecipient

with app.app_context():
    # Crear solo las tablas que faltan
    db.create_all()
    print("✅ Tablas 'notifications' y 'notification_recipients' creadas exitosamente")