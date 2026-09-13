/* A business location is fixed; only an explicit button click requests GPS. */
document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('save-business-location');
    if (!button) return;
    const status = document.getElementById('business-location-status');
    button.addEventListener('click', () => {
        if (!navigator.geolocation) { status.textContent = 'Este navegador no permite obtener la ubicación.'; return; }
        button.disabled = true;
        status.textContent = 'Obteniendo ubicación del negocio…';
        navigator.geolocation.getCurrentPosition(async position => {
            try {
                const response = await fetch(button.dataset.url, {
                    method: 'POST', credentials: 'same-origin',
                    headers: {'Content-Type': 'application/json', 'X-CSRFToken': document.querySelector('#business-coverage [name="csrf_token"]').value},
                    body: JSON.stringify({latitude: position.coords.latitude, longitude: position.coords.longitude})
                });
                if (!response.ok || response.redirected) throw new Error();
                const data = await response.json();
                status.textContent = data.message;
                button.textContent = 'Actualizar ubicación del negocio';
            } catch (_) { status.textContent = 'No se pudo guardar la ubicación. Volvé al panel e intentá nuevamente.'; }
            finally { button.disabled = false; }
        }, () => {
            status.textContent = 'No se pudo obtener la ubicación. Permití el acceso y volvé a intentar.';
            button.disabled = false;
        }, {enableHighAccuracy: true, timeout: 15000, maximumAge: 0});
    });
});
