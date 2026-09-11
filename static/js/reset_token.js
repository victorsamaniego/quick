'use strict';
// Keep the one-time credential out of URLs sent to the server and browser history.
const resetToken = window.location.hash.slice(1);
window.history.replaceState(null, '', window.location.pathname);
if (/^[A-Za-z0-9_-]{43}$/.test(resetToken)) {
    document.getElementById('reset-token').value = resetToken;
}
