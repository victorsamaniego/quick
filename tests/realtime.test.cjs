const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const audioSource = fs.readFileSync(require('node:path').join(__dirname, '../static/js/notifications_audio.js'), 'utf8');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/js/main.js'), 'utf8');
function harness(options = {}) {
    const events = {}, dom = {}, counters = {connections: 0, sounds: 0, resumes: 0, contexts: 0, types: []};
    const socket = {on(name, cb) { (events[name] ||= []).push(cb); }};
    class AudioContext {
        constructor() { counters.contexts++; this.state = 'running'; this.currentTime = 0; }
        async resume() { counters.resumes++; if (options.blocked) throw Error('NotAllowedError'); }
        createOscillator() { return {connect() {}, frequency: {}, start() { counters.sounds++; if (options.audioError) throw Error('Audio failure'); }, stop() {}}; }
        createGain() { return {connect() {}, gain: {setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {}}}; }
    }
    const document = options.document || {addEventListener(name, cb) { (dom[name] ||= []).push(cb); }, getElementById() { return null; }, querySelectorAll() { return []; }};
    const window = {realtimeUser: {id: 1, isAdmin: true, businessId: 7, ...options.user}, io() { counters.connections++; return socket; }, AudioContext, setTimeout() {}};
    const context = vm.createContext({window, document, console, localStorage: {getItem() {return options.muted ? 'off' : null;}}, fetch: options.fetch, DOMParser: options.DOMParser});
    context.sessionStorage = options.storage || {getItem() {return null;}, setItem() {}};
    vm.runInContext(audioSource, context);
    const play = window.QuickGoAudio.play;
    window.QuickGoAudio.play = type => { counters.types.push(type); play(type); };
    vm.runInContext(source, context);
    events.realtime_ready[0]({live_since: 100});
    return {window, context, counters, dom, emit(name, data) { for (const cb of events[name] || []) cb({emitted_at: 101, ...data}); }, async unlock() { for (const cb of dom.click) await cb(); }};
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
    assert.equal(calls, 2); assert.ok(h.counters.sounds > 0);
});
test('own messages stay silent', async () => {
    const h = harness(); await h.unlock(); h.emit('new_chat_message', {message: {id: 1, sender_id: 1}}); assert.equal(h.counters.sounds, 0);
});
test('correct business receives one order notification', async () => {
    const h = harness(); await h.unlock(); let calls = 0; h.window.QuickRealtime.on('new_order', () => calls++);
    h.emit('new_order', {business_id: 7, order_id: 3}); h.emit('new_order', {business_id: 7, order_id: 3});
    assert.equal(calls, 2); assert.ok(h.counters.sounds > 0);
});
test('foreign business and non-seller receive no order notification', async () => {
    for (const user of [{businessId: 8}, {isAdmin: false}]) {
        const h = harness({user}); await h.unlock(); let calls = 0; h.window.QuickRealtime.on('new_order', () => calls++);
        h.emit('new_order', {business_id: 7, order_id: 3}); assert.equal(calls, 0); assert.equal(h.counters.sounds, 0);
    }
});
test('delivery request sounds once for delivery', async () => {
    const h = harness({user: {isDelivery: true}}); await h.unlock();
    h.emit('new_delivery_request', {request_id: 8, delivery_driver_id: 1}); h.emit('new_delivery_request', {request_id: 8, delivery_driver_id: 1}); assert.ok(h.counters.sounds > 0);
});
test('completion transition has one sound; snapshot stays silent', async () => {
    const h = harness(); await h.unlock();
    h.emit('order_status_update', {event_id: 'transition-a', order_id: 4, old_status: 'on_way', status: 'delivered'});
    h.emit('order_status_update', {event_id: 'transition-a', order_id: 4, old_status: 'on_way', status: 'delivered'});
    h.emit('order_status_update', {status: 'delivered'}); assert.ok(h.counters.sounds > 0);
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
    assert.equal(rendered.size, 1); assert.equal(live, 1); assert.equal(h.counters.sounds, 0);
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
    h.emit('delivery_assigned', {event_id: 'assignment-1', order_id: 8, delivery_driver_id: 1});
    h.emit('delivery_assigned', {event_id: 'assignment-1', order_id: 8, delivery_driver_id: 1});
    assert.ok(h.counters.sounds > 0);
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
test('event types select distinct synthesized patterns exactly once', async () => {
    const h = harness({user: {isDelivery: true}}); await h.unlock();
    const cases = [
        ['new_chat_message', {message: {id: 90, sender_id: 2}}, 'message', 1],
        ['new_order', {business_id: 7, order_id: 90}, 'new_order', 3],
        ['new_delivery_request', {request_id: 90, delivery_driver_id: 1}, 'delivery', 2],
        ['order_status_update', {event_id: 'a', order_id: 90, old_status: 'on_way', status: 'delivered'}, 'completed', 2]
    ];
    for (const [event, data, type, tones] of cases) {
        const before = h.counters.sounds;
        h.emit(event, data); h.emit(event, data);
        assert.equal(h.counters.types.at(-1), type);
        assert.equal(h.counters.sounds - before, tones);
    }
    assert.deepEqual(h.counters.types, ['message', 'new_order', 'delivery', 'completed']);
});
test('reload and reconnection suppress old events but allow new ones', async () => {
    let saved = null;
    const storage = {getItem() {return saved;}, setItem(key, value) {saved = value;}};
    const first = harness({storage}); await first.unlock();
    first.emit('new_order', {business_id: 7, order_id: 30});
    const h = harness({storage}); await h.unlock();
    h.emit('new_order', {business_id: 7, order_id: 30});
    h.emit('new_order', {business_id: 7, order_id: 29, emitted_at: 99});
    h.emit('disconnect');
    h.emit('new_order', {business_id: 7, order_id: 31});
    h.emit('realtime_ready', {live_since: 200}); h.emit('connect');
    h.emit('new_order', {business_id: 7, order_id: 32, emitted_at: 199});
    assert.equal(h.counters.sounds, 0);
    h.emit('new_order', {business_id: 7, order_id: 33, emitted_at: 201});
    assert.equal(h.counters.sounds, 3);
});
test('blocked audio drops events; subsequent interaction permits only fresh sounds', async () => {
    const options = {blocked: true}; const h = harness(options);
    await h.unlock();
    h.emit('new_chat_message', {message: {id: 20, sender_id: 2}});
    options.blocked = false; await h.unlock();
    assert.equal(h.counters.sounds, 0);
    h.emit('new_chat_message', {message: {id: 20, sender_id: 2}});
    h.emit('new_chat_message', {message: {id: 21, sender_id: 2}});
    assert.equal(h.counters.sounds, 1);
    assert.equal(h.counters.contexts, 1);
});
test('global audio initializes once and every required gesture unlocks', async () => {
    for (const gesture of ['click', 'touchstart', 'keydown']) {
        const h = harness(); vm.runInContext(audioSource, h.context); vm.runInContext(source, h.context);
        for (const name of ['click', 'touchstart', 'keydown']) assert.equal(h.dom[name].length, 1);
        await h.dom[gesture][0](); await h.dom[gesture][0]();
        assert.equal(h.counters.contexts, 1); assert.equal(h.counters.resumes, 1);
        h.window.QuickGoAudio.play('message'); assert.equal(h.counters.sounds, 1);
    }
});
test('foreign delivery and repeated completion state stay silent', async () => {
    const h = harness({user: {isDelivery: true}}); await h.unlock();
    h.emit('new_delivery_request', {request_id: 2, delivery_driver_id: 8});
    h.emit('delivery_assigned', {event_id: 'a', order_id: 2, delivery_driver_id: 8});
    assert.equal(h.counters.sounds, 0);
    h.emit('order_status_update', {event_id: 'a', order_id: 2, old_status: 'on_way', status: 'delivered'});
    h.emit('order_status_update', {event_id: 'b', order_id: 2, old_status: 'delivered', status: 'delivered'});
    assert.equal(h.counters.sounds, 2);
});
function dashboardHarness() {
    const nodes = {}, gestures = {};
    function node(id, textContent, className = '', childNodes = []) {
        return {id, textContent, className, childNodes,
            replaceWith(replacement) { nodes[id] = replacement; },
            replaceChildren(...children) { this.childNodes = children; }};
    }
    nodes['realtime-total-orders'] = node('realtime-total-orders', '5');
    nodes['realtime-pending-orders'] = node('realtime-pending-orders', '0');
    nodes['realtime-orders-card'] = node('realtime-orders-card', 'Sin pendientes', 'no-pending');
    nodes['realtime-orders'] = node('realtime-orders', '', '', ['order-5']);
    let requests = 0, pending = 1;
    const document = {addEventListener(name, cb) {(gestures[name] ||= []).push(cb);},
        getElementById(id) {return nodes[id] || null;}, querySelector() {return null;},
        body: {appendChild(modal) {nodes[modal.id] = modal;}}};
    class DOMParser {
        parseFromString(html) {
            assert.equal(html, 'server-rendered-dashboard');
            const card = node('realtime-orders-card', pending ? '1 pendiente' : 'Sin pendientes', pending ? 'has-pending' : 'no-pending');
            card.badge = pending ? {textContent: '1', className: 'badge bg-warning'} : null;
            const fresh = {
                'realtime-total-orders': node('realtime-total-orders', '6'),
                'realtime-pending-orders': node('realtime-pending-orders', String(pending)),
                'realtime-orders-card': card,
                'realtime-orders': node('realtime-orders', '', '', ['order-6', 'order-5'])
            };
            return {getElementById(id) {return fresh[id] || null;}, querySelectorAll() {return [node('viewModal6', 'Detalle #6')];}};
        }
    }
    const h = harness({document, DOMParser, fetch: async () => {
        requests++; return {ok: true, text: async () => 'server-rendered-dashboard'};
    }});
    h.window.location = {href: '/admin/dashboard'};
    return {...h, nodes, requests: () => requests, setPending(value) {pending = value;},
        async activate() {await gestures.click[0]();},
        async settle() {await new Promise(resolve => setImmediate(resolve));}};
}
test('dashboard 5/0 becomes 6/1 with badge, card, order, modal and exactly one new_order sound', async () => {
    const h = dashboardHarness(); await h.activate();
    assert.equal(h.nodes['realtime-total-orders'].textContent, '5');
    assert.equal(h.nodes['realtime-pending-orders'].textContent, '0');
    assert.equal(h.nodes['realtime-orders-card'].badge, undefined);
    const event = {order_id: 6, business_id: 7};
    h.emit('new_order', event); await h.settle();
    function check() {
        assert.equal(h.nodes['realtime-total-orders'].textContent, '6');
        assert.equal(h.nodes['realtime-pending-orders'].textContent, '1');
        assert.equal(h.nodes['realtime-orders-card'].badge.textContent, '1');
        assert.match(h.nodes['realtime-orders-card'].badge.className, /bg-warning/);
        assert.equal(h.nodes['realtime-orders-card'].textContent, '1 pendiente');
        assert.equal(h.nodes['realtime-orders-card'].className, 'has-pending');
        assert.deepEqual(h.nodes['realtime-orders'].childNodes, ['order-6', 'order-5']);
        assert.equal(h.nodes.viewModal6.textContent, 'Detalle #6');
        assert.deepEqual(h.counters.types, ['new_order']);
        assert.equal(h.counters.sounds, 3); // One playback of the three-tone pattern.
    }
    check(); h.emit('new_order', event); await h.settle(); check();
});
test('foreign business cannot fetch or alter dashboard counters, card, list or sound', async () => {
    const h = dashboardHarness(); await h.activate();
    h.emit('new_order', {order_id: 6, business_id: 8}); await h.settle();
    assert.equal(h.requests(), 0);
    assert.equal(h.nodes['realtime-total-orders'].textContent, '5');
    assert.equal(h.nodes['realtime-pending-orders'].textContent, '0');
    assert.equal(h.nodes['realtime-orders-card'].className, 'no-pending');
    assert.equal(h.nodes['realtime-orders-card'].badge, undefined);
    assert.deepEqual(h.nodes['realtime-orders'].childNodes, ['order-5']);
    assert.equal(h.counters.sounds, 0);
});
test('server status refresh removes pending badge and restores card with no pending orders', async () => {
    const h = dashboardHarness();
    h.emit('new_order', {order_id: 6, business_id: 7}); await h.settle();
    h.setPending(0);
    h.emit('order_status_update', {order_id: 6, status: 'delivered', old_status: 'pending', event_id: 'complete-6'});
    await h.settle();
    assert.equal(h.nodes['realtime-total-orders'].textContent, '6');
    assert.equal(h.nodes['realtime-pending-orders'].textContent, '0');
    assert.equal(h.nodes['realtime-orders-card'].badge, null);
    assert.equal(h.nodes['realtime-orders-card'].textContent, 'Sin pendientes');
    assert.equal(h.nodes['realtime-orders-card'].className, 'no-pending');
});
test('dashboard template exposes server-calculated regions and refresh never reloads the page', () => {
    const template = fs.readFileSync(require('node:path').join(__dirname, '../templates/admin/dashboard.html'), 'utf8');
    assert.match(template, /id="realtime-total-orders">{{ total_orders }}/);
    assert.match(template, /id="realtime-pending-orders">{{ pending_orders }}/);
    assert.match(template, /<a id="realtime-orders-card"[\s\S]*?badge-pending[\s\S]*?<\/a>/);
    assert.doesNotMatch(source, /location\.(reload|assign|replace)\s*\(/);
});
