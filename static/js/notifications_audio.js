/* Synthesized locally; no media files, network requests or pending sound queue. */
(function (window, document) {
    'use strict';
    if (window.QuickGoAudio) return;
    const patterns = {
        message: [[660, 0, .10]],
        new_order: [[784, 0, .16], [988, .21, .16], [1175, .42, .22]],
        delivery: [[440, 0, .23], [554, .30, .23]],
        completed: [[880, 0, .08], [1320, .09, .13]]
    };
    let context, unlocked = false, pending, muted = false;
    try { muted = localStorage.getItem('quickgo-sound') === 'off'; } catch (_) {}
    async function unlock() {
        if (pending) return pending;
        try {
            const Constructor = window.AudioContext || window.webkitAudioContext;
            if (!Constructor) return;
            context = context || new Constructor();
            if (unlocked && context.state === 'running') return;
            pending = context.resume();
            await pending;
            unlocked = context.state === 'running';
        } catch (_) { unlocked = false; }
        finally { pending = null; }
    }
    function play(type) {
        if (muted || !unlocked || context?.state !== 'running' || !patterns[type]) return;
        try {
            const now = context.currentTime;
            for (const [frequency, delay, duration] of patterns[type]) {
                const oscillator = context.createOscillator(), gain = context.createGain();
                oscillator.type = 'sine';
                oscillator.frequency.value = frequency;
                oscillator.connect(gain); gain.connect(context.destination);
                gain.gain.setValueAtTime(.001, now + delay);
                gain.gain.linearRampToValueAtTime(.055, now + delay + .01);
                gain.gain.exponentialRampToValueAtTime(.001, now + delay + duration);
                oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
                oscillator.start(now + delay); oscillator.stop(now + delay + duration + .01);
            }
        } catch (_) { /* Visual updates must succeed even when audio fails. */ }
    }
    window.QuickGoAudio = {play, unlock, isMuted: () => muted, setMuted(value) {
        muted = Boolean(value);
        try { localStorage.setItem('quickgo-sound', muted ? 'off' : 'on'); } catch (_) {}
    }};
    for (const event of ['click', 'touchstart', 'keydown']) document.addEventListener(event, unlock, {passive: true});
})(window, document);
