const CACHE_NAME = 'quickgo-public-v2';
// Explicit public assets only. Navigations and all private responses use the network.
const urlsToCache = ['/static/css/style.css', '/static/js/main.js'];
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
