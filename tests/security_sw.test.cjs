const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function worker({noStore = false, redirected = false} = {}) {
    const events = {}, deleted = [], saved = [];
    const response = {ok: true, redirected, headers: {get: () => noStore ? 'no-store' : ''}, clone() {return this;}};
    const cache = {match: async () => null, put: async key => saved.push(key)};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/sw.js'), 'utf8'), {
        URL, Set, self: {location: {origin: 'https://quickgo.test'}, addEventListener: (key, fn) => events[key] = fn},
        caches: {open: async () => cache, keys: async () => ['quickgo-v1', 'quickgo-public-v2', 'unrelated'], delete: async name => deleted.push(name)},
        fetch: async () => response
    });
    return {events, deleted, saved};
}
test('private pages, API, chat, navigations and POST never use Cache Storage', () => {
    const w = worker();
    for (const target of ['/admin', '/api/orders', '/chat/1', '/dashboard', '/', '/cart', '/delivery/']) {
        w.events.fetch({request: {method: 'GET', url: 'https://quickgo.test' + target}, respondWith() {assert.fail(target);}});
    }
    for (const request of [{method: 'POST'}, {method: 'GET', mode: 'navigate'}]) {
        w.events.fetch({request: {...request, url: 'https://quickgo.test/static/js/main.js'}, respondWith() {assert.fail('private request');}});
    }
});
test('explicit public assets cache successfully', async () => {
    const w = worker(); let pending;
    w.events.fetch({request: {method: 'GET', url: 'https://quickgo.test/static/js/main.js'}, respondWith(p) {pending = p;}});
    await pending; assert.equal(w.saved.length, 1);
});
test('no-store and redirected assets never enter cache, including install', async () => {
    for (const options of [{noStore: true}, {redirected: true}]) {
        const w = worker(options); let pending;
        w.events.install({waitUntil(p) {pending = p;}}); await pending;
        w.events.fetch({request: {method: 'GET', url: 'https://quickgo.test/static/js/main.js'}, respondWith(p) {pending = p;}}); await pending;
        assert.equal(w.saved.length, 0);
    }
});
test('activate purges old QuickGo private cache and preserves unrelated caches', async () => {
    const w = worker(); let pending;
    w.events.activate({waitUntil(p) {pending = p;}}); await pending;
    assert.deepEqual(w.deleted, ['quickgo-v1']);
});
