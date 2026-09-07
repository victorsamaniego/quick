/* One transport, one event dispatcher, optional sound, silent HTTP recovery. */
(function (window, document) {
    'use strict';
    if (window.QuickRealtime) return;
    const user = window.realtimeUser;
    const socket = window.socket || (user && typeof window.io === 'function' ? window.io() : null);
    if (socket) window.socket = socket;
    const listeners = new Map(), seen = new Set();
    const soundSeen = new Set();
    const storageKey = 'quickgo-audio-seen:' + user?.id;
    try { for (const key of JSON.parse(sessionStorage.getItem(storageKey) || '[]')) soundSeen.add(key); } catch (_) {}
    let liveSince = Infinity;
    function rememberSound(key) {
        if (!key || soundSeen.has(key)) return false;
        soundSeen.add(key);
        try { sessionStorage.setItem(storageKey, JSON.stringify([...soundSeen])); } catch (_) {}
        return true;
    }
    function remember(key) {
        if (!key) return true;
        rememberSound(key);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    }
    const sound = type => window.QuickGoAudio?.play(type);
    function on(event, fn) {
        if (!listeners.has(event)) {
            listeners.set(event, new Set());
            if (socket) socket.on(event, data => dispatch(event, data));
        }
        listeners.get(event).add(fn);
        return () => listeners.get(event).delete(fn);
    }
    function dispatch(event, data) {
        data = data || {};
        if (event === 'new_order' && (!user || !user.isAdmin || Number(data.business_id) !== Number(user.businessId))) return;
        let key, type;
        if (event === 'new_chat_message' && data.message?.id != null) key = 'chat:' + data.message.id;
        if (event === 'private_chat_message' && data.channel && data.message?.id != null) key = data.channel + ':' + data.message.id;
        if (event === 'new_order' && data.order_id != null) { key = 'order:' + data.order_id; type = 'new_order'; }
        const driver = user?.isDelivery && Number(data.delivery_driver_id) === Number(user.id);
        if (event === 'new_delivery_request' && data.request_id != null) {
            key = 'request:' + data.request_id;
            if (driver) type = 'delivery';
        }
        if (event === 'delivery_assigned' && data.event_id && data.order_id != null) {
            key = 'assignment:' + data.order_id + ':' + data.event_id;
            if (driver) type = 'delivery';
        }
        if (event === 'order_status_update' && data.event_id && data.order_id != null) {
            key = 'status:' + data.order_id + ':' + data.status;
            if (data.status === 'delivered' && data.old_status !== data.status) type = 'completed';
            else if (driver) type = 'delivery';
        }
        if ((event === 'new_chat_message' || event === 'private_chat_message') && data.message?.sender_id != null && Number(data.message.sender_id) !== Number(user?.id)) type = 'message';
        const freshSound = rememberSound(key);
        // Audio deduplication never prevents a visual update.
        if (freshSound && type && Number.isFinite(data.emitted_at) && data.emitted_at >= liveSince) {
            try { sound(type); } catch (_) {}
        }
        for (const fn of listeners.get(event) || []) {
            try { fn(data); } catch (error) { console.error('Realtime listener failed', error); }
        }
    }
    let refreshing = false, dirty = false;
    async function refreshOrders() {
        if (!document.getElementById('realtime-orders')) return;
        dirty = true;
        if (refreshing) return;
        refreshing = true;
        try {
            while (dirty) {
                dirty = false;
                const response = await fetch(window.location.href, {credentials: 'same-origin', cache: 'no-store'});
                if (!response.ok || response.redirected) throw new Error('No se pudo actualizar pedidos');
                const page = new DOMParser().parseFromString(await response.text(), 'text/html');
                const fresh = page.getElementById('realtime-orders');
                if (!fresh) throw new Error('Listado no disponible');
                // Reuse the server-rendered values, including the conditional badge
                // and card classes. Other order pages may not have these regions.
                const regions = ['realtime-total-orders', 'realtime-pending-orders', 'realtime-orders-card']
                    .map(id => [document.getElementById(id), page.getElementById(id)])
                    .filter(([current]) => current);
                if (regions.some(([, replacement]) => !replacement)) throw new Error('Resumen de pedidos no disponible');
                if (document.querySelector('.modal.show')) { dirty = true; break; }
                document.getElementById('realtime-orders').replaceChildren(...fresh.childNodes);
                for (const [current, replacement] of regions) current.replaceWith(replacement);
                if (user?.isAdmin) {
                    page.querySelectorAll('.modal[id]').forEach(modal => {
                        const old = document.getElementById(modal.id);
                        if (old) old.replaceWith(modal); else document.body.appendChild(modal);
                    });
                }
            }
        } catch (error) {
            console.error(error);
            window.setTimeout(refreshOrders, 5000);
        } finally { refreshing = false; }
    }
    const recovery = new Map();
    async function recoverChat(orderId, render) {
        if (recovery.get(orderId)) return;
        recovery.set(orderId, true);
        try {
            let after = 0;
            while (true) {
                const response = await fetch(`/api/chat/order/${orderId}/messages?after=${after}`, {cache:'no-store'});
                if (!response.ok) throw new Error('Historial no disponible');
                const {messages} = await response.json();
                for (const message of messages) { remember('chat:' + message.id); render(message); after = Math.max(after, message.id); }
                if (messages.length < 200) break;
            }
        } catch (error) { console.error(error); }
        finally { recovery.delete(orderId); }
    }
    window.QuickRealtime = {on, remember, recoverChat, refreshOrders, sound};
    window.playNotificationSound = sound;
    on('new_chat_message', () => {});
    on('private_chat_message', () => {});
    on('new_order', refreshOrders);
    on('new_delivery_request', refreshOrders);
    on('order_status_update', data => {
        const badge = document.getElementById(`order-status-${data.order_id}`);
        if (badge) { badge.textContent = data.status_label; badge.className = `badge bg-${data.status_color}`; }
        refreshOrders();
    });
    on('delivery_assigned', refreshOrders);
    on('realtime_ready', data => { liveSince = Number.isFinite(data.live_since) ? data.live_since : Infinity; });
    on('disconnect', () => { liveSince = Infinity; });
    on('connect', refreshOrders);
    document.addEventListener('hidden.bs.modal', () => { if (dirty) refreshOrders(); });
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-message-id]').forEach(el => remember('chat:' + el.dataset.messageId));
        refreshOrders();
        if (!user) return;
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'btn btn-sm btn-outline-secondary';
        const update = () => { button.textContent = window.QuickGoAudio.isMuted() ? 'Activar sonidos' : 'Silenciar sonidos'; button.setAttribute('aria-pressed', String(!window.QuickGoAudio.isMuted())); };
        update();
        button.addEventListener('click', () => { window.QuickGoAudio.setMuted(!window.QuickGoAudio.isMuted()); update(); window.QuickGoAudio.unlock(); });
        (document.querySelector('footer .container') || document.body).appendChild(button);
    });
})(window, document);
