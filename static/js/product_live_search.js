(function () {
    'use strict';
    document.addEventListener('DOMContentLoaded', () => {
        const form = document.getElementById('product-search-form');
        if (!form) return;
        const input = document.getElementById('product-search');
        const results = document.getElementById('product-search-results');
        const status = document.getElementById('product-search-status');
        let timer, controller, generation = 0;
        function close() {
            results.hidden = true;
            input.setAttribute('aria-expanded', 'false');
        }
        function cancel() {
            clearTimeout(timer);
            generation += 1;
            if (controller) controller.abort();
            close();
        }
        function links() { return Array.from(results.querySelectorAll('a')); }
        async function search(query, version) {
            controller = new AbortController();
            status.textContent = 'Buscando productos…';
            try {
                const url = new URL(form.dataset.searchUrl, window.location.origin);
                url.searchParams.set('q', query);
                const category = form.querySelector('[name="category"]');
                if (category) url.searchParams.set('category', category.value);
                const response = await fetch(url, {signal: controller.signal, credentials: 'same-origin'});
                if (!response.ok) throw new Error('search unavailable');
                const rows = await response.json();
                if (version !== generation) return;
                results.replaceChildren();
                rows.slice(0, 10).forEach(row => {
                    const target = new URL(row.url, window.location.origin);
                    if (target.origin !== window.location.origin) return;
                    const link = document.createElement('a');
                    link.className = 'product-search-result'; link.href = target.href;
                    const image = document.createElement('img');
                    image.alt = ''; image.loading = 'lazy';
                    image.dataset.catalogSrc = row.image;
                    image.dataset.originalSrc = row.image_original;
                    image.dataset.placeholderSrc = '/static/images/product-placeholder.svg';
                    image.src = row.image_original;
                    if (window.QuickGoProductImages) window.QuickGoProductImages.prepare(image);
                    const text = document.createElement('span');
                    const name = document.createElement('strong'); name.textContent = row.name;
                    const business = document.createElement('small'); business.textContent = row.business_name;
                    const price = document.createElement('small');
                    price.textContent = 'GS ' + Number(row.price).toLocaleString('es-PY', {maximumFractionDigits: 0});
                    text.append(name, business, price); link.append(image, text); results.append(link);
                });
                const count = links().length;
                status.textContent = count ? `${count} productos encontrados. Usá Tab o flecha abajo para explorarlos.` : 'No encontramos productos.';
                results.hidden = !count;
                input.setAttribute('aria-expanded', String(Boolean(count)));
            } catch (error) {
                if (version === generation && error.name !== 'AbortError') {
                    close(); status.textContent = 'Búsqueda instantánea no disponible. Podés usar el botón Buscar.';
                }
            }
        }
        input.addEventListener('input', () => {
            cancel(); results.replaceChildren(); status.textContent = '';
            const query = input.value.trim();
            if (query.length < 2 || query.length > 200) return;
            const version = generation;
            timer = setTimeout(() => search(query, version), 300);
        });
        form.addEventListener('keydown', event => {
            if (event.key === 'Escape') { cancel(); input.focus(); return; }
            if (results.hidden || !['ArrowDown', 'ArrowUp'].includes(event.key)) return;
            const items = links(); if (!items.length) return;
            event.preventDefault();
            const current = items.indexOf(document.activeElement);
            const next = current < 0 ? (event.key === 'ArrowDown' ? 0 : items.length - 1)
                : (current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
            items[next].focus();
        });
        form.addEventListener('submit', cancel);
        form.addEventListener('focusout', event => { if (!form.contains(event.relatedTarget)) cancel(); });
        document.addEventListener('click', event => { if (!form.contains(event.target)) cancel(); });
    });
}());
