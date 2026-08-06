from app import app, db
from models import User, Order, OrderItem, Business, Product, Category, OTPCode, ChatMessage, SupportChat, DeliveryBusinessChat, UserMessage, Notification, NotificationRecipient, DeliveryRequest

with app.app_context():
    print("🧹 INICIANDO LIMPIEZA DE BASE DE DATOS...\n")
    
    # 1. Mantener el Super Admin
    super_admin = User.query.filter_by(is_super_admin=True).first()
    if not super_admin:
        print("❌ ERROR: No se encontró ningún Super Admin. Abortando limpieza.")
        exit()
    
    print(f"✅ Super Admin encontrado: {super_admin.email} (ID: {super_admin.id})")
    print(f"   Este usuario NO será eliminado.\n")
    
    # 2. Contar datos antes de eliminar
    total_usuarios = User.query.count()
    total_pedidos = Order.query.count()
    total_negocios = Business.query.count()
    total_productos = Product.query.count()
    total_mensajes = UserMessage.query.count()
    total_notificaciones = Notification.query.count()
    
    print(f"📊 Datos actuales en la base de datos:")
    print(f"   - Usuarios: {total_usuarios}")
    print(f"   - Pedidos: {total_pedidos}")
    print(f"   - Negocios: {total_negocios}")
    print(f"   - Productos: {total_productos}")
    print(f"   - Mensajes: {total_mensajes}")
    print(f"   - Notificaciones: {total_notificaciones}\n")
    
    # Confirmación
    respuesta = input("⚠️  ¿Estás seguro de eliminar TODO excepto el Super Admin? (s/n): ")
    if respuesta.lower() != 's':
        print("❌ Operación cancelada.")
        exit()
    
    print("\n️  Eliminando datos...\n")
    
    # 3. Eliminar en orden (respetando dependencias)
    
    # Items de pedidos
    OrderItem.query.delete()
    print("✅ OrderItems eliminados")
    
    # Pedidos
    Order.query.delete()
    print("✅ Pedidos eliminados")
    
    # Chats de pedidos
    ChatMessage.query.delete()
    print("✅ ChatMessages eliminados")
    
    # Chats de delivery-negocio
    DeliveryBusinessChat.query.delete()
    print("✅ DeliveryBusinessChats eliminados")
    
    # Solicitudes de delivery
    DeliveryRequest.query.delete()
    print("✅ DeliveryRequests eliminados")
    
    # Chats de soporte
    SupportChat.query.delete()
    print("✅ SupportChats eliminados")
    
    # Mensajes de usuario
    UserMessage.query.delete()
    print("✅ UserMessages eliminados")
    
    # Destinatarios de notificaciones
    NotificationRecipient.query.delete()
    print("✅ NotificationRecipients eliminados")
    
    # Notificaciones
    Notification.query.delete()
    print("✅ Notifications eliminados")
    
    # Códigos OTP
    OTPCode.query.delete()
    print("✅ OTPCodes eliminados")
    
    # Productos
    Product.query.delete()
    print("✅ Productos eliminados")
    
    # Categorías
    Category.query.delete()
    print("✅ Categorías eliminadas")
    
    # Negocios (excepto si el Super Admin tiene uno)
    if super_admin.business_id:
        Business.query.filter(Business.id != super_admin.business_id).delete()
        print("✅ Negocios eliminados (excepto el del Super Admin)")
    else:
        Business.query.delete()
        print("✅ Negocios eliminados")
    
    # Usuarios (excepto el Super Admin)
    User.query.filter(User.id != super_admin.id).delete()
    print("✅ Usuarios eliminados (excepto el Super Admin)\n")
    
    # 4. Commit
    db.session.commit()
    
    print("🎉 ¡LIMPIEZA COMPLETADA EXITOSAMENTE!\n")
    print(f"📊 Resumen final:")
    print(f"   - Usuarios restantes: {User.query.count()}")
    print(f"   - Pedidos restantes: {Order.query.count()}")
    print(f"   - Negocios restantes: {Business.query.count()}")
    print(f"   - Productos restantes: {Product.query.count()}")
    print(f"\n✅ Solo queda el Super Admin: {super_admin.email}")