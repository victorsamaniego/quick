/* Originals remain usable without JavaScript and while AI delivery is unavailable. */
(function () {
    'use strict';
    function fallback(image) {
        if (!image.dataset || !image.dataset.placeholderSrc || image.dataset.catalogState === 'placeholder') return;
        if (image.dataset.catalogState !== 'original' && image.dataset.originalSrc) {
            image.dataset.catalogState = 'original';
            image.src = image.dataset.originalSrc;
        } else if (image.dataset.catalogState !== 'placeholder') {
            image.dataset.catalogState = 'placeholder';
            image.src = image.dataset.placeholderSrc;
        }
    }
    function prepare(image) {
        image.dataset.catalogState = 'derived';
        if (image.dataset.catalogSrc) image.src = image.dataset.catalogSrc;
    }
    document.addEventListener('error', event => {
        if (event.target.tagName === 'IMG') fallback(event.target);
    }, true);
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('img[data-catalog-src]').forEach(prepare);
    });
    window.QuickGoProductImages = {prepare, fallback};
}());
