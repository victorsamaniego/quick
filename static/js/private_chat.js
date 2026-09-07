(function () {
    const box = document.getElementById('private-chat');
    if (!box || !window.socket || !window.QuickRealtime) return;
    const channel = box.dataset.channel;
    box.querySelectorAll('[data-private-message-id]').forEach(el => window.QuickRealtime.remember(channel + ':' + el.dataset.privateMessageId));
    let running = false, dirty = false;
    async function refresh() {
        dirty = true;
        if (running) return;
        running = true;
        try {
            while (dirty) {
                dirty = false;
                const response = await fetch(location.href, {cache: 'no-store'});
                if (!response.ok || response.redirected) throw new Error('Chat no disponible');
                const page = new DOMParser().parseFromString(await response.text(), 'text/html');
                const fresh = page.getElementById('private-chat');
                if (!fresh) return;
                fresh.querySelectorAll('[data-private-message-id]').forEach(el => window.QuickRealtime.remember(channel + ':' + el.dataset.privateMessageId));
                box.replaceChildren(...fresh.childNodes);
                box.scrollTop = box.scrollHeight;
            }
        } catch (error) { console.error(error); }
        finally { running = false; }
    }
    const join = () => window.socket.emit('join', {room: channel}, result => { if (result?.success) refresh(); });
    window.QuickRealtime.on('connect', join);
    window.QuickRealtime.on('private_chat_message', data => { if (data.channel === channel) refresh(); });
    if (window.socket.connected) join();
})();
