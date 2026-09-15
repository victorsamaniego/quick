/* Explicit one-shot availability location; never continuous order tracking. */
(function () {
    const button = document.getElementById('delivery-availability-location');
    const status = document.getElementById('delivery-availability-status');
    button.addEventListener('click', () => {
        if (!navigator.geolocation) { status.textContent = 'GPS no disponible.'; return; }
        button.disabled = true;
        navigator.geolocation.getCurrentPosition(async position => {
            try {
                const response = await fetch('/delivery/api/location/update', {method: 'POST',
                    headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content},
                    body: JSON.stringify({latitude: position.coords.latitude, longitude: position.coords.longitude})});
                status.textContent = response.ok ? 'Ubicación actualizada para buscar solicitudes cercanas.' : 'No se pudo actualizar la ubicación.';
            } catch (_) { status.textContent = 'Sin conexión. Intentá de nuevo.'; }
            finally { button.disabled = false; }
        }, () => { button.disabled = false; status.textContent = 'No se pudo obtener tu ubicación. Revisá el permiso GPS.'; },
        {enableHighAccuracy: true, maximumAge: 0, timeout: 15000});
    });
})();
