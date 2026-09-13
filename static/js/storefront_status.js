/* Reuse the shared socket. HTTP recovers public status after missed events. */
document.addEventListener('DOMContentLoaded', () => {
    const forms = [...document.querySelectorAll('[data-storefront-business]')];
    if (!forms.length) return;
    let reloading = false, fetching = false;
    function reconcile(data) {
        const changed = forms.some(form => {
            const state = data[form.dataset.storefrontBusiness];
            return state && (String(state.is_open) !== form.dataset.storefrontOpen ||
                             String(state.is_active) !== form.dataset.storefrontActive);
        });
        if (changed && !reloading) { reloading = true; window.location.reload(); }
    }
    async function recover() {
        if (fetching || document.hidden || reloading) return;
        fetching = true;
        try {
            const ids = [...new Set(forms.map(form => form.dataset.storefrontBusiness))];
            for (let offset = 0; offset < ids.length; offset += 100) {
                const response = await fetch('/api/business-status?ids=' + ids.slice(offset, offset + 100).join(','), {cache: 'no-store', credentials: 'same-origin'});
                if (response.ok && !response.redirected) reconcile(await response.json());
            }
        } catch (_) { /* Existing server-side purchase checks remain authoritative. */ }
        finally { fetching = false; }
    }
    window.QuickRealtime?.on('business_status_update', data => reconcile({[data.business_id]: data}));
    window.QuickRealtime?.on('connect', recover);
    document.addEventListener('visibilitychange', recover);
    window.setInterval(recover, 15000);
    recover();
});
