document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('orderForm');
    const latitude = form.elements.client_latitude;
    const longitude = form.elements.client_longitude;
    const confirmed = form.elements.destination_confirmed;
    const submit = document.getElementById('confirmBtn');
    const confirmLocation = document.getElementById('confirmLocationBtn');
    const status = document.getElementById('destinationStatus');
    const gpsButton = document.getElementById('getLocationBtn');
    let pending = null;
    let gpsRequest = 0;
    let marker = null;
    confirmed.value = '';
    submit.disabled = true;
    if (typeof L === 'undefined') {
        status.textContent = 'No se pudo cargar el mapa. Recargá la página para elegir el destino.';
        return;
    }
    // Default coordinates center the map only; they are never a delivery destination.
    const map = L.map('locationMap').setView([-25.2637, -57.5759], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors', maxZoom: 19
    }).addTo(map);

    function selectPoint(lat, lon) {
        if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return;
        pending = {lat: lat, lon: lon};
        confirmed.value = '';
        latitude.value = '';
        longitude.value = '';
        submit.disabled = true;
        confirmLocation.disabled = false;
        status.textContent = `Punto elegido: ${lat.toFixed(6)}, ${lon.toFixed(6)}. Confirmá este destino.`;
        if (!marker) {
            marker = L.marker([lat, lon], {draggable: true}).addTo(map);
            marker.on('dragend', function () {
                gpsRequest++;
                const point = marker.getLatLng();
                selectPoint(point.lat, point.lng);
            });
        } else marker.setLatLng([lat, lon]);
        document.getElementById('deliveryFeeBox').style.display = 'none';
        document.getElementById('deliveryFeeRow').style.display = 'none';
    }
    map.on('click', function (event) {
        gpsRequest++;
        selectPoint(event.latlng.lat, event.latlng.lng);
    });
    document.getElementById('chooseLocationBtn').addEventListener('click', function () {
        gpsRequest++;
        confirmed.value = '';
        submit.disabled = true;
        status.textContent = 'Tocá el mapa o arrastrá el marcador y confirmá el destino.';
        map.invalidateSize();
    });
    gpsButton.addEventListener('click', function () {
        const requestId = ++gpsRequest;
        confirmed.value = '';
        submit.disabled = true;
        confirmLocation.disabled = true;
        pending = null;
        if (!navigator.geolocation) {
            status.textContent = 'Geolocalización no disponible. Elegí un punto en el mapa.';
            return;
        }
        status.textContent = 'Obteniendo ubicación…';
        navigator.geolocation.getCurrentPosition(function (position) {
            if (requestId !== gpsRequest) return;
            selectPoint(position.coords.latitude, position.coords.longitude);
            map.setView([position.coords.latitude, position.coords.longitude], 16);
        }, function () {
            if (requestId !== gpsRequest) return;
            status.textContent = 'No se pudo obtener tu ubicación. Elegí un punto en el mapa o intentá nuevamente.';
        }, {enableHighAccuracy: true, timeout: 10000, maximumAge: 0});
    });
    confirmLocation.addEventListener('click', function () {
        if (!pending) return;
        latitude.value = pending.lat;
        longitude.value = pending.lon;
        confirmed.value = 'yes';
        submit.disabled = false;
        status.textContent = `Destino confirmado: ${pending.lat.toFixed(6)}, ${pending.lon.toFixed(6)}. Se guardará en tu pedido.`;
        calculateDeliveryFee(pending.lat, pending.lon);
    });
    form.addEventListener('submit', function (event) {
        if (confirmed.value !== 'yes' || !latitude.value || !longitude.value) {
            event.preventDefault();
            status.textContent = 'Confirmá el punto de entrega antes de realizar el pedido.';
        }
    });
    window.addEventListener('pageshow', function () {
        confirmed.value = '';
        submit.disabled = true;
    });
    function calculateDeliveryFee(lat, lon) {
        fetch('/api/location/calculate-delivery', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ latitude: lat, longitude: lon })
        })
        .then(res => res.json())
        .then(data => {
            if (confirmed.value !== 'yes' || Number(latitude.value) !== lat || Number(longitude.value) !== lon) return;
            document.getElementById('deliveryFeeBox').style.display = 'block';
            document.getElementById('deliveryFeeRow').style.display = 'flex';
            document.getElementById('deliveryFeeValue').textContent = data.fee_formatted;
            document.getElementById('deliveryFeeSummary').textContent = data.fee_formatted;
            if (data.distance_km) {
                document.getElementById('distanceValue').textContent = `📏 Distancia: ${data.distance_km} km`;
            }
            const subtotal = Number(form.dataset.subtotal);
            const totalWithDelivery = subtotal + data.delivery_fee;
            document.getElementById('totalValue').textContent = `GS ${totalWithDelivery.toLocaleString('es-PY')}`;
        })
        .catch(err => console.error('Error:', err));
    }
    
    window.togglePayment = function() {
        const isCash = document.getElementById('pay_cash') && document.getElementById('pay_cash').checked;
        const isTransfer = document.getElementById('pay_transfer').checked;
        const isQr = document.getElementById('pay_qr').checked;
        const cashFields = document.getElementById('cash_fields');
        if (cashFields) cashFields.classList.toggle('d-none', !isCash);
        document.getElementById('transfer_fields').classList.toggle('d-none', !isTransfer);
        document.getElementById('qr_fields').classList.toggle('d-none', !isQr);
    }
    

    if (form.dataset.importation === 'true') document.getElementById('pay_transfer').checked = true;
    else document.getElementById('pay_cash').checked = true;
    togglePayment();
});
