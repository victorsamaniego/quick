/* Private notifications reuse QuickRealtime; HTTP recovery is always silent. */
(function(window, document) {
    'use strict';
    const rt = window.QuickRealtime;
    if (!rt || !window.realtimeUser || window.realtimeUser.isSuperAdmin) return;
    const seen = new Set();
    let running = false, dirty = false;
    function remember(item) {
        const id = Number(item.notification_id);
        if (!Number.isSafeInteger(id) || id <= 0) return false;
        rt.remember('notification:' + id);
        const fresh = !seen.has(id); seen.add(id);
        return fresh;
    }
    function render(item) {
        const list = document.getElementById('notification-list');
        if (!list || document.getElementById('notification-' + item.notification_id)) return;
        document.getElementById('notification-empty')?.remove();
        const link = document.createElement('a');
        link.id = 'notification-' + item.notification_id;
        link.href = '/notificacion/' + item.notification_id;
        link.className = 'list-group-item list-group-item-action';
        const title = document.createElement('strong'), message = document.createElement('p');
        title.textContent = item.title; message.textContent = item.message.slice(0, 100);
        message.className = 'text-muted mb-0';
        link.append(title, message);
        list.prepend(link);
    }
    async function recover() {
        dirty = true;
        if (running) return;
        running = true;
        try {
            while (dirty) {
                dirty = false;
                const response = await fetch('/api/notifications', {credentials:'same-origin', cache:'no-store'});
                if (!response.ok || response.redirected) return;
                const data = await response.json();
                const badge = document.getElementById('notification-unread-count');
                if (badge) { badge.textContent = String(data.unread_count); badge.hidden = !data.unread_count; }
                for (const item of [...data.notifications].reverse()) { remember(item); render(item); }
            }
        } catch (_) { /* Durable inbox remains accessible on the next request. */ }
        finally { running = false; }
    }
    rt.on('superadmin_notification', item => {
        if (remember(item)) {
            document.getElementById('quickgo-notification-toast')?.remove();
            const toast = document.createElement('aside');
            toast.id = 'quickgo-notification-toast'; toast.className = 'quickgo-notification-toast';
            toast.setAttribute('role', 'status');
            const title = document.createElement('strong'), link = document.createElement('a');
            title.textContent = item.title; link.textContent = 'Ver notificación';
            link.className = 'd-block mt-2'; link.href = '/notificacion/' + item.notification_id;
            toast.append(title, link); document.body.appendChild(toast);
            window.setTimeout(() => toast.remove(), 8000);
        }
        render(item); recover();
    });
    rt.on('connect', recover);
    document.addEventListener('DOMContentLoaded', recover);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) recover(); });
    window.setInterval(() => { if (!document.hidden) recover(); }, 30000);
})(window, document);
