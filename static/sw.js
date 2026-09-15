const CACHE_NAME = 'quickgo-public-v6';
// Explicit public assets only. Navigations and all private responses use the network.
const urlsToCache = ['/static/css/style.css', '/static/js/main.js', '/static/css/storefront.css', '/static/css/themes.css', '/static/css/login.css', '/static/css/login_transition.css', '/static/js/login_transition.js', '/static/js/theme_settings.js', '/static/vendor/bootstrap-icons/bootstrap-icons.min.css', '/static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff2', '/static/vendor/bootstrap-icons/fonts/bootstrap-icons.woff'];
const publicURLs = new Set(urlsToCache.map(path => new URL(path, self.location.origin).href));
const cacheable = response => response.ok && !response.redirected &&
    !/no-store|private/i.test(response.headers.get('Cache-Control') || '');
self.addEventListener('install', event => {
    event.waitUntil(caches.open(CACHE_NAME).then(async cache => {
        await Promise.all(urlsToCache.map(async path => {
            const response = await fetch(path, {credentials: 'omit', cache: 'reload'});
            if (cacheable(response)) await cache.put(path, response);
        }));
    }));
});
self.addEventListener('activate', event => {
    event.waitUntil(caches.keys().then(names => Promise.all(names
        .filter(name => name.startsWith('quickgo-') && name !== CACHE_NAME)
        .map(name => caches.delete(name)))));
});
self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET' || request.mode === 'navigate' || !publicURLs.has(request.url)) return;
    event.respondWith(caches.open(CACHE_NAME).then(async cache => {
        const cached = await cache.match(request);
        if (cached) return cached;
        const response = await fetch(request);
        if (cacheable(response)) await cache.put(request, response.clone());
        return response;
    }));
});

function internalURL(value) {
    if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || /[\\\u0000-\u0020]/.test(value)) return '/';
    try {
        const url = new URL(value, self.location.origin);
        return url.origin === self.location.origin ? url.pathname + url.search : '/';
    } catch (_) { return '/'; }
}
const seenPush = new Set();
self.addEventListener('push', event => {
    event.waitUntil((async () => {
        let data;
        try { data = event.data?.json(); } catch (_) { return; }
        if (!data || typeof data.event_id !== 'string' || data.event_id.length > 200) return;
        const clients = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
        if (clients.some(client => client.visibilityState === 'visible' && new URL(client.url).origin === self.location.origin)) return;
        const tag = 'quickgo:' + data.event_id;
        if (seenPush.has(tag) || (await self.registration.getNotifications({tag})).length) return;
        seenPush.add(tag);
        if (seenPush.size > 256) seenPush.delete(seenPush.values().next().value);
        await self.registration.showNotification(String(data.title || 'QuickGo').slice(0, 100), {
            body: String(data.body || 'Abrí QuickGo para ver los detalles.').slice(0, 200),
            icon: '/static/icons/icon-192.png', badge: '/static/icons/icon-192.png',
            tag, renotify: false, data: {url: internalURL(data.url)}
        });
    })());
});
self.addEventListener('notificationclick', event => {
    event.notification.close();
    event.waitUntil((async () => {
        const url = internalURL(event.notification.data?.url);
        const clients = await self.clients.matchAll({type: 'window', includeUncontrolled: true});
        for (const client of clients) {
            if (new URL(client.url).origin !== self.location.origin) continue;
            const navigated = await client.navigate(url);
            if (navigated) return navigated.focus();
        }
        return self.clients.openWindow(url);
    })());
});
self.addEventListener('message', event => {
    if (event.data?.type !== 'quickgo-visibility' || !event.ports?.[0]) return;
    event.waitUntil(self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(clients => {
        event.ports[0].postMessage({visible: clients.some(client => client.visibilityState === 'visible')});
    }));
});
