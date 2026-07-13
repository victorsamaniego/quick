from app import app, db
from models import ChatMessage

with app.app_context():
    ChatMessage.query.delete()
    db.session.commit()
    print("✅ Mensajes antiguos borrados")