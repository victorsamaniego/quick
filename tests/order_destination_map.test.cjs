const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/order_destination_map.js'), 'utf8');
function render(dataset, available = true) {
    const element = {dataset};
    const points = [];
    const listeners = {};
    let resized = 0;
    const map = {setView() {return this}, fitBounds() {}, invalidateSize() {resized++}};
    const context = {
        document: {querySelectorAll: () => [element], addEventListener(event, fn) {
            if (event === 'DOMContentLoaded') fn(); else listeners[event] = fn;
        }},
        navigator: {get geolocation() {throw Error('Saved destination must not read GPS')}},
        window: {get socket() {throw Error('Saved destination must not subscribe to live updates')}}
    };
    if (available) context.L = {map: () => map, tileLayer: () => ({addTo() {}}),
        marker(point, options) {
            assert.equal(options.draggable, false);
            points.push(point);
            return {addTo() {return this}, bindPopup() {return this}};
        }, polyline: () => ({addTo() {return this}, getBounds() {return []}})};
    vm.runInNewContext(source, context);
    return {element, points: JSON.parse(JSON.stringify(points)), listeners, resized: () => resized};
}
test('saved coordinates create a fixed marker; modal opening only resizes the map', () => {
    const r = render({latitude: '-25.01', longitude: '-57.02'});
    assert.deepEqual(r.points, [[-25.01, -57.02]]);
    r.listeners['shown.bs.modal']({target: {contains: () => true}});
    assert.equal(r.resized(), 1);
    assert.deepEqual(r.points, [[-25.01, -57.02]]);
});
test('zero coordinates are valid', () => {
    assert.deepEqual(render({latitude: '0', longitude: '0'}).points, [[0, 0]]);
});
test('invalid or missing coordinates never create a made-up point', () => {
    for (const latitude of ['', 'null', 'NaN', '91']) {
        const r = render({latitude, longitude: '-57'});
        assert.equal(r.points.length, 0);
        assert.equal(r.element.textContent, 'Ubicación de entrega no disponible');
    }
});
test('merchant marker uses actual coordinates, never a hardcoded location', () => {
    const r = render({latitude: '-25', longitude: '-57', businessLatitude: '0', businessLongitude: '0'});
    assert.deepEqual(r.points, [[-25, -57], [0, 0]]);
});
test('map library failure leaves a helpful message and no invented destination', () => {
    const r = render({latitude: '-25', longitude: '-57'}, false);
    assert.equal(r.points.length, 0);
    assert.match(r.element.textContent, /No se pudo cargar el mapa/);
});
