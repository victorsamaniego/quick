/**
 * PODS LUXURY - JavaScript Principal
 * SocketIO + Notificaciones en Tiempo Real
 */

document.addEventListener('DOMContentLoaded', function() {
    
    // ===== CONFIGURACIÓN DE SOCKET.IO =====
    const socket = io();
    window.socket = socket;  // Hacer socket disponible globalmente
    
    // ===== CONEXIÓN INICIAL =====
    socket.on('connect', function() {
        console.log('✅ Conectado a SocketIO:', socket.id);
        
        // Unirse a rooms según el rol del usuario
        if (window.currentUser) {
            if (window.currentUser.isAdmin) {
                // Admin se une a la sala de admin
                socket.emit('join_admin_room');
                console.log('👑 Admin conectado a sala de notificaciones');
            } else {
                // Cliente se une a su sala personal
                socket.emit('join_user_room', { user_id: window.currentUser.id });
                console.log('👤 Cliente conectado a su sala personal');
            }
        }
    });
    
    socket.on('disconnect', function() {
        console.log('❌ Desconectado de SocketIO');
    });
    
    // ===== NOTIFICACIONES PARA ADMIN =====
    
    // Nuevo pedido entrante
    socket.on('new_order', function(data) {
        console.log('🆕 Nuevo pedido recibido:', data);
        
        // Reproducir sonido
        const notificationSound = document.getElementById('notificationSound');
        if (notificationSound) {
            notificationSound.play().catch(() => {
                console.log('No se pudo reproducir el sonido');
            });
        }
        
        // Mostrar notificación del navegador
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('🆕 Nuevo Pedido Recibido', {
                body: `Pedido #${data.order_id} - GS ${Number(data.total).toLocaleString()}`,
                icon: '/static/images/icon.png',
                tag: `order-${data.order_id}`
            });
        }
        
        // Actualizar contador de pedidos pendientes si existe
        const pendingBadge = document.getElementById('pendingOrdersBadge');
        if (pendingBadge) {
            const current = parseInt(pendingBadge.textContent) || 0;
            pendingBadge.textContent = current + 1;
            pendingBadge.classList.add('animate-pulse');
            setTimeout(() => pendingBadge.classList.remove('animate-pulse'), 2000);
        }
        
        // Mostrar alerta en el dashboard
        if (window.currentUser && window.currentUser.isAdmin) {
            showAlert('success', `🆕 Nuevo pedido #${data.order_id} de ${data.customer}`);
        }
    });
    
    // ===== NOTIFICACIONES PARA CLIENTES =====
    
    // Actualización de estado de pedido
    socket.on('order_status_update', function(data) {
        console.log('📦 Actualización de pedido:', data);
        
        const statusLabels = {
            'pending': '⏳ Pendiente',
            'shipped': '🚚 Enviado',
            'delivered': '✅ Entregado',
            'cancelled': '❌ Cancelado'
        };
        
        const statusColors = {
            'pending': 'warning',
            'shipped': 'info',
            'delivered': 'success',
            'cancelled': 'danger'
        };
        
        // Actualizar badge de estado si existe
        const statusBadge = document.getElementById(`order-status-${data.order_id}`);
        if (statusBadge) {
            statusBadge.textContent = statusLabels[data.status];
            statusBadge.className = `badge bg-${statusColors[data.status]}`;
        }
        
        // Mostrar notificación
        showAlert('info', `📦 Tu pedido #${data.order_id} ahora está: ${statusLabels[data.status]}`);
        
        // Reproducir sonido suave
        if (data.status === 'delivered') {
            const notificationSound = document.getElementById('notificationSound');
            if (notificationSound) {
                notificationSound.play().catch(() => {});
            }
        }
    });
    
    // ===== SOLICITAR ACTUALIZACIÓN DE PEDIDO =====
    
    window.requestOrderUpdate = function(orderId) {
        socket.emit('request_order_update', { order_id: orderId });
    };
    
    // ===== UTILIDADES =====
    
    function showAlert(type, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = 'top: 80px; right: 20px; z-index: 9999; min-width: 300px;';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        document.body.appendChild(alertDiv);
        
        setTimeout(() => {
            alertDiv.remove();
        }, 5000);
    }
    
    // ===== PERMISO DE NOTIFICACIONES =====
    
    if ('Notification' in window && Notification.permission === 'default') {
        document.addEventListener('click', function requestNotificationPermission() {
            Notification.requestPermission();
            document.removeEventListener('click', requestNotificationPermission);
        }, { once: true });
    }
    
    // ===== AUTO-HIDE ALERTS =====
    document.querySelectorAll('.alert:not(.alert-permanent)').forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });
    
    // ===== SOLICITAR PERMISO DE NOTIFICACIONES PARA ADMIN =====
    if (window.currentUser && window.currentUser.isAdmin) {
        if ('Notification' in window && Notification.permission === 'default') {
            setTimeout(() => {
                Notification.requestPermission();
            }, 3000);
        }
    }
    
    console.log('✨ Pods Luxury cargado correctamente');
});