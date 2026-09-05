// Display the order snapshot only. No GPS, polling, or live-location subscriptions.
document.addEventListener('DOMContentLoaded', function () {
    const maps = [];
    document.querySelectorAll('[data-order-destination]').forEach(function (element) {
        const lat = Number(element.dataset.latitude);
        const lon = Number(element.dataset.longitude);
        if (!element.dataset.latitude || !element.dataset.longitude ||
            !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
            element.textContent = 'Ubicación de entrega no disponible';
            return;
        }
        if (typeof L === 'undefined') {
            element.textContent = 'No se pudo cargar el mapa. Podés abrir el destino con el enlace de abajo.';
            return;
        }
        const map = L.map(element).setView([lat, lon], 15);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors', maxZoom: 19
        }).addTo(map);
        L.marker([lat, lon], {draggable: false}).addTo(map).bindPopup('Destino de entrega guardado');
        const businessLat = Number(element.dataset.businessLatitude);
        const businessLon = Number(element.dataset.businessLongitude);
        let bounds = null;
        if (element.dataset.businessLatitude && element.dataset.businessLongitude &&
                Number.isFinite(businessLat) && Number.isFinite(businessLon) &&
                Math.abs(businessLat) <= 90 && Math.abs(businessLon) <= 180) {
            L.marker([businessLat, businessLon], {draggable: false}).addTo(map).bindPopup('Comercio');
            const line = L.polyline([[lat, lon], [businessLat, businessLon]], {
                color: '#D4AF37', weight: 3, dashArray: '10, 10'
            }).addTo(map);
            bounds = line.getBounds();
            map.fitBounds(bounds, {padding: [30, 30]});
        }
        maps.push({element, map, bounds});
    });
    // Buyer order details live in Bootstrap modals, initially hidden.
    document.addEventListener('shown.bs.modal', function (event) {
        maps.forEach(function (entry) {
            if (event.target.contains(entry.element)) {
                entry.map.invalidateSize();
                if (entry.bounds) entry.map.fitBounds(entry.bounds, {padding: [30, 30]});
            }
        });
    });
});
