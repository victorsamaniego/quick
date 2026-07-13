from app import app, db
from models import Order, Business, User

with app.app_context():
    print("=" * 60)
    print("🔍 VERIFICACIÓN DE PEDIDOS Y NEGOCIOS")
    print("=" * 60)
    
    # Ver todos los pedidos
    pedidos = Order.query.all()
    print(f"\n📦 Total de pedidos: {len(pedidos)}")
    for p in pedidos:
        negocio = Business.query.get(p.business_id)
        print(f"   Pedido #{p.id} | Estado: {p.status} | Business_ID: {p.business_id} | Negocio: {negocio.name if negocio else 'NO EXISTE'}")
    
    # Ver admins y sus negocios
    print(f"\n Administradores:")
    admins = User.query.filter_by(is_admin=True).all()
    for a in admins:
        negocio = Business.query.get(a.business_id)
        print(f"   {a.email} | Business_ID: {a.business_id} | Negocio: {negocio.name if negocio else 'SIN NEGOCIO'}")
    
    # Ver negocios
    print(f"\n🏪 Negocios registrados:")
    negocios = Business.query.all()
    for n in negocios:
        print(f"   ID: {n.id} | {n.name} | Slug: {n.slug}")python verificar_pedido.py