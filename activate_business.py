from app import app, db
from models import Business
from datetime import datetime, timedelta, timezone

with app.app_context():
    # Buscar el negocio
    business = Business.query.filter_by(slug='pods-luxury').first()
    
    if not business:
        print("❌ No se encontró el negocio 'pods-luxury'")
        exit()
    
    # Activar suscripción por 1 mes
    now = datetime.now(timezone.utc)
    business.subscription_status = 'active'
    business.billing_start = now.date()
    business.billing_end = (now + timedelta(days=30)).date()  # 30 días de prueba
    business.activation_code = None  # Limpiar código
    business.code_expires_at = None
    
    db.session.commit()
    
    print(f"\n✅ ¡SUSCRIPCIÓN ACTIVADA!")
    print(f"   Negocio: {business.name}")
    print(f"   Estado: {business.subscription_status}")
    print(f"   Inicio: {business.billing_start}")
    print(f"   Fin: {business.billing_end}")
    print(f"\n🎉 Ahora podés operar normalmente!")
    print("   Refrescá la página del admin y ya no verás el mensaje de suscripción.")