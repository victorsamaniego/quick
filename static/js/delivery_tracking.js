/* Dedicated order context. GPS is never started by login or a global dashboard. */
(function (window, document) {
    'use strict';
    function mount(root) {
        const id = Number(root.dataset.orderId), rt = window.QuickRealtime, socket = window.socket;
        if (!rt || !socket) return;
        const state = root.querySelector('[data-tracking-state]'), age = root.querySelector('[data-tracking-age]');
        const heading = root.querySelector('[data-tracking-heading]'), gps = root.querySelector('[data-gps-message]');
        let active = false, authorized = false, driverId, watch = null, lastSent = -Infinity;
        let position = null, map = null, marker = null, initialized = false, revision = 0, busy = false, disposed = false;
        function stop() {
            if (watch !== null) window.navigator.geolocation.clearWatch(watch);
            watch = null;
        }
        function display() {
            if (!active) return;
            if (!position) { state.textContent = age.textContent = 'Esperando ubicación del delivery…'; return; }
            const seconds = Math.max(0, Math.floor((Date.now() / 1000) - position.updated_at));
            const live = seconds <= 25 && socket.connected;
            state.textContent = live ? 'Delivery en vivo' : 'Última ubicación disponible';
            age.textContent = (live ? 'Actualizado hace ' : 'Última ubicación hace ') + seconds + ' segundos';
        }
        function valid(p) {
            return p && Number.isFinite(p.latitude) && Number.isFinite(p.longitude) && Math.abs(p.latitude) <= 90 && Math.abs(p.longitude) <= 180;
        }
        function icon(label) { return window.L.divIcon({html: label, className: 'quickgo-tracking-marker', iconSize: [32, 32], iconAnchor: [16, 16]}); }
        function updatePosition(p) {
            if (!valid(p) || !Number.isFinite(p.updated_at) || (position && p.updated_at < position.updated_at)) return;
            position = p;
            if (map) {
                if (marker) marker.setLatLng([p.latitude, p.longitude]);
                else marker = window.L.marker([p.latitude, p.longitude], {icon: icon('🛵')}).addTo(map).bindPopup('🛵 Delivery');
            }
            display();
        }
        function buildMap(data) {
            if (initialized || !window.L) return;
            initialized = true;
            map = window.L.map(root.querySelector('[data-tracking-map]'));
            window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {attribution: '© OpenStreetMap contributors', maxZoom: 19}).addTo(map);
            const bounds = [];
            for (const [p, label] of [[data.pickup, '🏪'], [data.dropoff, '📍']]) {
                if (!valid(p)) continue;
                const coords = [p.latitude, p.longitude]; bounds.push(coords);
                window.L.marker(coords, {icon: icon(label)}).addTo(map).bindPopup(label === '🏪' ? '🏪 Comercio' : '📍 Lugar de entrega');
            }
            if (valid(data.position)) bounds.push([data.position.latitude, data.position.longitude]);
            if (bounds.length) map.fitBounds(bounds, {padding: [32, 32], maxZoom: 16});
            else map.setView([-25.2637, -57.5759], 12);
        }
        function start() {
            if (!active || !authorized || !socket.connected || document.hidden || disposed || watch !== null) return;
            if (!window.navigator.geolocation) { if (gps) gps.textContent = 'Este navegador no permite obtener tu ubicación.'; return; }
            watch = window.navigator.geolocation.watchPosition(p => {
                if (!active || !authorized || !socket.connected || document.hidden || disposed) return;
                if (Date.now() - lastSent < 5000 || !valid(p.coords)) return;
                lastSent = Date.now();
                socket.emit('delivery_location_update', {order_id: id, latitude: p.coords.latitude,
                    longitude: p.coords.longitude, accuracy: p.coords.accuracy}, result => {
                    if (!result?.success && result?.error === 'inactive') { authorized = false; stop(); recover(); }
                    else if (result?.success && gps) gps.textContent = 'Compartiendo ubicación durante este pedido.';
                });
            }, error => {
                if (gps) gps.textContent = error.code === 1 ? 'Permiso de ubicación denegado. Habilitalo en el navegador y volvé a abrir el pedido.' : 'GPS no disponible. Conservamos la última ubicación.';
                if (error.code === 1) stop();
            }, {enableHighAccuracy: true, maximumAge: 0, timeout: 15000});
        }
        function inactive(status) {
            active = authorized = false; stop();
            const text = status === 'picked_up' ? 'Retirado del local' : status === 'delivered' ? 'Pedido entregado' : status === 'cancelled' ? 'Pedido cancelado' : 'Reparto no activo';
            heading.textContent = state.textContent = text;
            age.textContent = 'Ubicación en vivo finalizada';
        }
        async function recover() {
            if (busy || disposed || document.hidden) return;
            busy = true;
            const version = revision;
            try {
                const response = await window.fetch('/api/orders/' + id + '/tracking', {credentials: 'same-origin', cache: 'no-store'});
                if (response.status === 403 || response.status === 401 || response.redirected) {
                    inactive(); state.textContent = 'Ya no tenés acceso al seguimiento de este pedido.';
                    if (map) { map.remove(); map = null; marker = null; initialized = false; }
                    position = null; return;
                }
                if (!response.ok) { stop(); return; }
                const data = await response.json();
                if (version !== revision || disposed) return;
                if (driverId !== data.delivery_driver_id) {
                    position = null;
                    if (marker && map) map.removeLayer(marker);
                    marker = null;
                }
                driverId = data.delivery_driver_id;
                active = data.active; authorized = data.can_transmit;
                buildMap(data);
                if (data.position) updatePosition(data.position);
                if (!active) inactive(data.status);
                else { heading.textContent = 'Tu pedido está en camino'; display(); if (!authorized) stop(); else start(); }
            } catch (_) { stop(); }
            finally { busy = false; }
        }
        const off = [
            rt.on('delivery_location_update', data => {
                if (data.order_id === id && active && data.delivery_driver_id === driverId) updatePosition(data);
            }),
            rt.on('order_status_update', data => {
                if (data.order_id !== id) return;
                revision++;
                if (data.status !== 'shipped') inactive(data.status);
                else { authorized = false; stop(); recover(); }
            }),
            rt.on('delivery_assigned', data => { if (data.order_id === id) { revision++; authorized = false; stop(); recover(); } }),
            rt.on('disconnect', () => { revision++; authorized = false; stop(); display(); }),
            rt.on('connect', () => { socket.emit('join_order_room', {order_id: id}); recover(); })
        ];
        const timer = window.setInterval(display, 1000), recovery = window.setInterval(recover, 15000);
        function visibility() { revision++; if (document.hidden) stop(); else recover(); }
        function pagehide() { disposed = true; stop(); window.clearInterval(timer); window.clearInterval(recovery); off.forEach(fn => fn()); }
        document.addEventListener('visibilitychange', visibility);
        window.addEventListener('pagehide', pagehide, {once: true});
        window.addEventListener('pageshow', event => { if (event.persisted) window.location.reload(); });
        if (socket.connected) socket.emit('join_order_room', {order_id: id});
        recover();
    }
    document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('[data-delivery-tracking]').forEach(mount));
})(window, document);
