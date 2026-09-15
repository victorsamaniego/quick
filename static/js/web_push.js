/* Permission is requested only by the explicit activation button. */
(function (window, document) {
    'use strict';
    const nav = window.navigator;
    if (!window.realtimeUser || !('serviceWorker' in nav)) return;
    let registration, subscription, device, config;
    const button = document.getElementById('push-enable'), disable = document.getElementById('push-disable');
    const status = document.getElementById('push-status');
    if (!button) return;
    function explain(message) { status.textContent = message; }
    async function post(path, data, keepalive = false) {
        const response = await fetch('/api/push/' + path, {method: 'POST', credentials: 'same-origin', keepalive,
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content}, body: JSON.stringify(data)});
        if (!response.ok || response.redirected) throw new Error('No se pudo guardar la preferencia.');
        return response.json();
    }
    async function presence() {
        if (!device) return;
        let visible = !document.hidden;
        // The worker aggregates tabs, so a hidden tab cannot mute a visible one.
        if (registration?.active && typeof window.MessageChannel === 'function') {
            visible = await new Promise(resolve => {
                const channel = new window.MessageChannel();
                const timer = window.setTimeout(() => { channel.port1.close(); resolve(!document.hidden); }, 500);
                channel.port1.onmessage = event => { window.clearTimeout(timer); channel.port1.close(); resolve(Boolean(event.data.visible)); };
                registration.active.postMessage({type: 'quickgo-visibility'}, [channel.port2]);
            });
        }
        try { await post('presence', {device, visible: visible && Boolean(window.socket?.connected)}, true); } catch (_) {}
    }
    function keyBytes(value) {
        const raw = window.atob(value.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - value.length % 4) % 4));
        return Uint8Array.from(raw, char => char.charCodeAt(0));
    }
    async function sync() {
        const result = await post('subscribe', subscription.toJSON());
        device = result.device;
        disable.hidden = false;
        button.hidden = true;
        explain('Notificaciones activadas. El sonido y la vibración dependen del sistema y de tus ajustes.');
        await presence();
    }
    button.addEventListener('click', async () => {
        if (!config?.enabled || !registration) return;
        if (!('PushManager' in window) || !('Notification' in window)) { explain('En iPhone, agregá QuickGo a la pantalla de inicio y abrilo desde su ícono para activar notificaciones.'); return; }
        button.disabled = true;
        try {
            // Keep permission request directly in the user gesture (iOS).
            const permission = await window.Notification.requestPermission();
            if (permission !== 'granted') { explain('Permiso no concedido. Podés cambiarlo en los ajustes del navegador.'); return; }
            subscription = await registration.pushManager.getSubscription() || await registration.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: keyBytes(config.public_key)});
            await sync();
        } catch (_) { explain('No se pudieron activar las notificaciones. Revisá los permisos e intentá de nuevo.'); }
        finally { button.disabled = false; }
    });
    disable.addEventListener('click', async () => {
        try {
            await post('unsubscribe', {device});
            await subscription?.unsubscribe();
            device = subscription = null; button.hidden = false; disable.hidden = true;
            explain('Notificaciones desactivadas en este navegador.');
        } catch (_) { explain('No se pudo desactivar. Intentá de nuevo.'); }
    });
    async function init() {
        try {
            const response = await fetch('/api/push/config', {cache: 'no-store'});
            if (!response.ok || response.redirected) return;
            config = await response.json();
            if (!config.enabled) { explain('Las notificaciones del sistema todavía no están habilitadas.'); return; }
            registration = await nav.serviceWorker.register('/sw.js', {scope: '/'});
            await nav.serviceWorker.ready;
            button.disabled = false;
            explain('En iPhone, usá QuickGo agregado a pantalla de inicio.');
            subscription = await registration.pushManager?.getSubscription();
            if (subscription && window.Notification?.permission === 'granted') await sync();
        } catch (_) { explain('Las notificaciones no están disponibles en este navegador.'); }
    }
    document.addEventListener('visibilitychange', presence);
    window.QuickRealtime?.on('connect', presence);
    window.QuickRealtime?.on('disconnect', presence);
    window.addEventListener('pagehide', () => { if (device) post('presence', {device, visible: false}, true).catch(() => {}); });
    window.setInterval(presence, 15000);
    init();
})(window, document);
