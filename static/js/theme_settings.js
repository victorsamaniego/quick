/* Preview only; persistence uses the authenticated CSRF-protected form POST. */
(function () {
    'use strict';
    const allowed = ['gold-classic', 'dark-gold', 'black-gold', 'sand'];
    for (const choice of document.querySelectorAll('input[name="theme"]')) choice.addEventListener('change', function () {
        if (!this.checked || !allowed.includes(this.value)) return;
        for (const theme of allowed) document.body.classList.remove('theme-' + theme);
        document.body.classList.add('theme-' + this.value);
        document.documentElement.dataset.theme = this.value;
        document.getElementById('theme-preview-status').textContent = 'Vista previa. Guardá para conservar esta apariencia.';
    });
})();
