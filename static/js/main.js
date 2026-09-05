/* One transport, one event dispatcher, optional sound, silent HTTP recovery. */
(function (window, document) {
    'use strict';
    if (window.QuickRealtime) return;
    const user = window.realtimeUser;
    const socket = window.socket || (user && typeof window.io === 'function' ? window.io() : null);
    if (socket) window.socket = socket;
    const listeners = new Map(), seen = new Set();
    let audio, unlocked = false, muted = false;
    try { muted = localStorage.getItem('quickgo-sound') === 'off'; } catch (_) {}
    function remember(key) {
        if (!key) return true;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    }
    async function unlock() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            audio = audio || new AudioContext();
            await audio.resume();
            unlocked = audio.state === 'running';
        } catch (_) { unlocked = false; }
    }
    function sound(type) {
        if (muted || !unlocked || !audio) return;
        try {
            if (audio.state !== 'running') { unlocked = false; return; }
            const oscillator = audio.createOscillator(), gain = audio.createGain();
            oscillator.connect(gain); gain.connect(audio.destination);
            oscillator.frequency.value = {chat: 660, order: 880, delivery: 740, complete: 1046}[type] || 660;
            gain.gain.setValueAtTime(0.06, audio.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.18);
            oscillator.start(); oscillator.stop(audio.currentTime + 0.2);
        } catch (_) { /* Audio never interrupts transport/rendering. */ }
    }
    document.addEventListener('pointerdown', unlock);
    document.addEventListener('keydown', unlock);
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
        let key;
        if (event === 'new_chat_message') key = 'chat:' + data.message?.id;
        if (event === 'private_chat_message') key = data.channel + ':' + data.message?.id;
        if (event === 'new_order') key = 'order:' + data.order_id;
        if (event === 'new_delivery_request') key = 'request:' + data.request_id;
        if (event === 'order_status_update' || event === 'delivery_assigned') key = data.event_id;
        if (!remember(key)) return;
        if ((event === 'new_chat_message' || event === 'private_chat_message') && Number(data.message?.sender_id) !== Number(user?.id)) sound('chat');
        if (event === 'new_order') sound('order');
        if (event === 'delivery_assigned' && data.event_id && user?.isDelivery) sound('delivery');
        if (event === 'new_delivery_request' && user?.isDelivery) sound('delivery');
        if (event === 'order_status_update' && data.event_id && data.status === 'delivered') sound('complete');
        else if (event === 'order_status_update' && data.event_id && user?.isDelivery) sound('delivery');
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
                if (document.querySelector('.modal.show')) { dirty = true; break; }
                document.getElementById('realtime-orders').replaceChildren(...fresh.childNodes);
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
    on('connect', refreshOrders);
    document.addEventListener('hidden.bs.modal', () => { if (dirty) refreshOrders(); });
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-message-id]').forEach(el => remember('chat:' + el.dataset.messageId));
        refreshOrders();
        if (!user) return;
        const button = document.createElement('button');
        button.type = 'button'; button.className = 'btn btn-sm btn-outline-secondary';
        const update = () => { button.textContent = muted ? 'Activar sonidos' : 'Silenciar sonidos'; button.setAttribute('aria-pressed', String(!muted)); };
        update();
        button.addEventListener('click', () => { muted = !muted; try { localStorage.setItem('quickgo-sound', muted ? 'off' : 'on'); } catch (_) {} update(); unlock(); });
        (document.querySelector('footer .container') || document.body).appendChild(button);
    });
})(window, document);
