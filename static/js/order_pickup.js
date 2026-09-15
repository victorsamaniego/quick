/* Delegation survives the existing realtime order fragment replacement. */
(function (window, document) {
    'use strict';
    document.addEventListener('submit', async function (event) {
        const form = event.target;
        if (!form.matches('[data-store-pickup]')) return;
        event.preventDefault();
        const button = form.querySelector('button');
        if (button.disabled || !window.confirm('¿Confirmás que el cliente ya retiró este pedido del local?')) return;
        button.disabled = true;
        try {
            const response = await fetch(form.action, {method: 'POST', body: new FormData(form), credentials: 'same-origin'});
            if (response.redirected) throw new Error('Tu sesión o tus permisos cambiaron. Volvé a ingresar.');
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'No se pudo registrar el retiro.');
            button.textContent = data.status_label;
            await window.QuickRealtime.refreshOrders();
        } catch (error) {
            window.alert(error.message || 'No se pudo registrar el retiro.');
            button.disabled = false;
        }
    });
})(window, document);
