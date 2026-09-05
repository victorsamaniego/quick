const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/js/main.js'), 'utf8');
function harness(options = {}) {
    const events = {}, dom = {}, counters = {connections: 0, sounds: 0, resumes: 0};
    const socket = {on(name, cb) { (events[name] ||= []).push(cb); }};
    class AudioContext {
        constructor() { this.state = 'running'; this.currentTime = 0; }
        async resume() { counters.resumes++; if (options.blocked) throw Error('NotAllowedError'); }
        createOscillator() { return {connect() {}, frequency: {}, start() { counters.sounds++; if (options.audioError) throw Error('Audio failure'); }, stop() {}}; }
        createGain() { return {connect() {}, gain: {setValueAtTime() {}, exponentialRampToValueAtTime() {}}}; }
    }
    const document = options.document || {addEventListener(name, cb) { (dom[name] ||= []).push(cb); }, getElementById() { return null; }, querySelectorAll() { return []; }};
    const window = {realtimeUser: {id: 1, isAdmin: true, businessId: 7, ...options.user}, io() { counters.connections++; return socket; }, AudioContext, setTimeout() {}};
    const context = vm.createContext({window, document, console, localStorage: {getItem() {return options.muted ? 'off' : null;}}, fetch: options.fetch, DOMParser: options.DOMParser});
    vm.runInContext(source, context);
    return {window, context, counters, dom, emit(name, data) { for (const cb of events[name] || []) cb(data); }, async unlock() { for (const cb of dom.pointerdown) await cb(); }};
}
test('initialization reuses exactly one socket and dispatcher', () => {
    const h = harness(); vm.runInContext(source, h.context); assert.equal(h.counters.connections, 1);
    let calls = 0; const cb = () => calls++; h.window.QuickRealtime.on('new_order', cb); h.window.QuickRealtime.on('new_order', cb);
    h.emit('new_order', {order_id: 9, business_id: 7}); assert.equal(calls, 1);
});
test('new message is rendered logically and sounds once across duplicates/reconnect', async () => {
    const h = harness(); await h.unlock(); let calls = 0;
    h.window.QuickRealtime.on('new_chat_message', () => calls++);
    const data = {message: {id: 4, sender_id: 2}};
    h.emit('new_chat_message', data); h.emit('connect'); h.emit('new_chat_message', data);
    assert.equal(calls, 1); assert.equal(h.counters.sounds, 1);
});
test('own messages stay silent', async () => {
    const h = harness(); await h.unlock(); h.emit('new_chat_message', {message: {id: 1, sender_id: 1}}); assert.equal(h.counters.sounds, 0);
});
test('correct business receives one order notification', async () => {
    const h = harness(); await h.unlock(); let calls = 0; h.window.QuickRealtime.on('new_order', () => calls++);
    h.emit('new_order', {business_id: 7, order_id: 3}); h.emit('new_order', {business_id: 7, order_id: 3});
    assert.equal(calls, 1); assert.equal(h.counters.sounds, 1);
});
test('foreign business and non-seller receive no order notification', async () => {
    for (const user of [{businessId: 8}, {isAdmin: false}]) {
        const h = harness({user}); await h.unlock(); let calls = 0; h.window.QuickRealtime.on('new_order', () => calls++);
        h.emit('new_order', {business_id: 7, order_id: 3}); assert.equal(calls, 0); assert.equal(h.counters.sounds, 0);
    }
});
test('delivery request sounds once for delivery', async () => {
    const h = harness({user: {isDelivery: true}}); await h.unlock();
    h.emit('new_delivery_request', {request_id: 8}); h.emit('new_delivery_request', {request_id: 8}); assert.equal(h.counters.sounds, 1);
});
test('completion transition has one sound; snapshot stays silent', async () => {
    const h = harness(); await h.unlock();
    h.emit('order_status_update', {event_id: 'transition-a', status: 'delivered'});
    h.emit('order_status_update', {event_id: 'transition-a', status: 'delivered'});
    h.emit('order_status_update', {status: 'delivered'}); assert.equal(h.counters.sounds, 1);
});
test('autoplay rejection never breaks delivery or queues old sounds', async () => {
    const h = harness({blocked: true}); await h.unlock(); let calls = 0; h.window.QuickRealtime.on('new_chat_message', () => calls++);
    h.emit('new_chat_message', {message: {id: 2, sender_id: 3}}); assert.equal(calls, 1); assert.equal(h.counters.sounds, 0);
});
test('audio runtime error never breaks dispatch', async () => {
    const h = harness({audioError: true}); await h.unlock(); let calls = 0; h.window.QuickRealtime.on('new_chat_message', () => calls++);
    h.emit('new_chat_message', {message: {id: 2, sender_id: 3}}); assert.equal(calls, 1);
});
test('muted preference keeps audio silent', async () => {
    const h = harness({muted: true}); await h.unlock(); h.emit('new_chat_message', {message: {id: 2, sender_id: 3}}); assert.equal(h.counters.sounds, 0);
});
test('HTTP history merges silently and deduplicates subsequent socket delivery', async () => {
    const h = harness({fetch: async () => ({ok: true, json: async () => ({messages: [{id: 10, sender_id: 3}]})})});
    await h.unlock(); const rendered = new Set(); let live = 0; h.window.QuickRealtime.on('new_chat_message', () => live++);
    await h.window.QuickRealtime.recoverChat(1, m => rendered.add(m.id));
    await h.window.QuickRealtime.recoverChat(1, m => rendered.add(m.id));
    h.emit('new_chat_message', {message: {id: 10, sender_id: 3}});
    assert.equal(rendered.size, 1); assert.equal(live, 0); assert.equal(h.counters.sounds, 0);
});
test('private channels keep independent IDs', async () => {
    const h = harness(); await h.unlock();
    for (const channel of ['support_7', 'delivery_chat_7', 'support_7']) h.emit('private_chat_message', {channel, message: {id: 1, sender_id: 2}});
    assert.equal(h.counters.sounds, 2);
});
test('partial order refresh inserts rows and action modals without page navigation', async () => {
    const rows = [], modals = [];
    const fragment = {replaceChildren(...nodes) { rows.push(...nodes); }};
    const document = {addEventListener() {}, querySelector() { return null; }, getElementById(id) { return id === 'realtime-orders' ? fragment : null; }, body: {appendChild(node) {modals.push(node);}}};
    const actionModal = {id: 'viewModal9'};
    class DOMParser { parseFromString() { return {getElementById() {return {childNodes: ['order-9']};}, querySelectorAll() {return [actionModal];}}; } }
    let fetches = 0;
    const h = harness({document, DOMParser, fetch: async () => {fetches++; return {ok: true, text: async () => '<server-rendered-orders>'};}});
    h.window.location = {href: '/admin/orders'};
    await h.window.QuickRealtime.refreshOrders();
    assert.deepEqual(rows, ['order-9']); assert.equal(modals[0].id, 'viewModal9'); assert.equal(fetches, 1);
});
test('delivery reassignment sounds once for assigned delivery', async () => {
    const h = harness({user: {isDelivery: true}}); await h.unlock();
    h.emit('delivery_assigned', {event_id: 'assignment-1', order_id: 8});
    h.emit('delivery_assigned', {event_id: 'assignment-1', order_id: 8});
    assert.equal(h.counters.sounds, 1);
});
test('delivery listeners load after the shared socket and separately from map initialization', () => {
    const template = fs.readFileSync(require('node:path').join(__dirname, '../templates/delivery/dashboard.html'), 'utf8');
    const listener = template.indexOf("window.QuickRealtime.on('new_delivery_request'");
    assert.ok(template.indexOf('{% block extra_js %}') < listener);
    assert.ok(template.indexOf('</script>', template.indexOf('updateLocation();')) < listener);
    const base = fs.readFileSync(require('node:path').join(__dirname, '../templates/base.html'), 'utf8');
    assert.ok(base.indexOf("filename='js/main.js'") < base.indexOf('{% block extra_js %}'));
    assert.doesNotMatch(base, /\bio\(\)/);
});
