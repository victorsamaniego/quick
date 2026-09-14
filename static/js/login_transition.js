/* Authentication and destination are server-owned. The link also works without JS. */
(function () {
    'use strict';
    const link = document.getElementById('transition-continue');
    if (!link) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin || !['http:', 'https:'].includes(target.protocol)) return;
    const motion = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    let finished = false;
    function finish() {
        if (finished) return;
        finished = true;
        window.location.replace(target.href);
    }
    document.body.classList.add('transition-running');
    // CSS owns the visual timeline; keep a bounded fallback if styles are unavailable.
    const styledDuration = window.getComputedStyle
        ? Number(window.getComputedStyle(document.body).getPropertyValue('--transition-duration')) : 0;
    const duration = Number.isFinite(styledDuration) && styledDuration >= 1600 && styledDuration <= 2800
        ? styledDuration : 1600;
    window.setTimeout(finish, !motion || motion.matches ? 100 : duration);
    if (motion && motion.addEventListener) motion.addEventListener('change', event => {
        if (event.matches) finish();
    });
    window.addEventListener('pageshow', event => { if (event.persisted) finish(); });
})();
