from app import app, db
from models import Order, User

with app.app_context():
    orders = Order.query.all()
    
    print(f"\n{'='*70}")
    print(f"🔍 VERIFICACIÓN DE PEDIDOS EN LA BASE DE DATOS")
    print(f"{'='*70}\n")
    print(f"Total de pedidos encontrados: {len(orders)}\n")
    
    if not orders:
        print("⚠️ No hay pedidos en la base de datos.")
    else:
        # Agrupar por usuario
        orders_by_user = {}
        for order in orders:
            if order.user_id not in orders_by_user:
                orders_by_user[order.user_id] = []
            orders_by_user[order.user_id].append(order)
        
        print(f"📊 Pedidos agrupados por usuario:\n")
        
        for user_id, user_orders in orders_by_user.items():
            user = User.query.get(user_id)
            print(f"{'─'*70}")
            print(f"👤 USUARIO ID: {user_id}")
            print(f"   Email: {user.email if user else '❌ USUARIO NO EXISTE'}")
            print(f"   Total de pedidos: {len(user_orders)}")
            print(f"   Pedidos:")
            for order in user_orders:
                print(f"      • Pedido #{order.id} - GS {order.total_amount:,.0f} - {order.status} - {order.created_at.strftime('%d/%m/%Y %H:%M')}")
            print()
        
        print(f"{'='*70}")
        print(f"📋 RESUMEN:")
        print(f"{'='*70}")
        for user_id, user_orders in orders_by_user.items():
            user = User.query.get(user_id)
            email = user.email if user else 'USUARIO NO EXISTE'
            print(f"   • {email}: {len(user_orders)} pedido(s)")
        
        # Verificar si hay pedidos con user_id incorrecto
        print(f"\n{'='*70}")
        print(f"⚠️ POSIBLES PROBLEMAS:")
        print(f"{'='*70}")
        
        for order in orders:
            user = User.query.get(order.user_id)
            if not user:
                print(f"   ❌ Pedido #{order.id} tiene user_id={order.user_id} pero ese usuario NO EXISTE")
        
        # Verificar si hay usuarios con pedidos duplicados
        print(f"\n💡 Si ves que un usuario tiene pedidos de otro usuario,")
        print(f"   el problema está en la base de datos (user_id incorrecto).")
        print(f"   En ese caso, ejecutá el script fix_orders.py para corregirlo.\n")