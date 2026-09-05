// Unit tests of the actual UI controller, with browser/GPS/Leaflet boundaries simulated.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/order_destination.js'), 'utf8');
function setup() {
  const nodes = new Map();
  function node(id) {
    if (!nodes.has(id)) {
      let value = '';
      nodes.set(id, {get value() {return value}, set value(v) {value = String(v)},
        disabled: false, checked: false, style: {}, dataset: {}, handlers: {},
        classList: {toggle() {}}, addEventListener(event, fn) {this.handlers[event] = fn}});
    }
    return nodes.get(id);
  }
  const form = node('orderForm');
  form.elements = {client_latitude: node('lat'), client_longitude: node('lon'), destination_confirmed: node('confirmed')};
  form.dataset = {subtotal: '100', importation: 'false'};
  const gps = [];
  const map = {handlers: {}, setView() {return this}, invalidateSize() {}, on(event, fn) {this.handlers[event] = fn}};
  let marker;
  const context = {console, Number, navigator: {geolocation: {getCurrentPosition(ok, fail) {gps.push({ok, fail})}}},
    window: {addEventListener() {}}, document: {getElementById: node, addEventListener(event, fn) {fn()}},
    fetch: () => Promise.resolve({json: () => Promise.resolve({delivery_fee: 10000, fee_formatted: 'GS 10.000', distance_km: 1})}),
    L: {map: () => map, tileLayer: () => ({addTo() {}}), marker: (point) => {
      marker = {point, handlers: {}, addTo() {return this}, on(event, fn) {this.handlers[event] = fn},
        setLatLng(point) {this.point = point}, getLatLng() {return {lat: this.point[0], lng: this.point[1]}}};
      return marker;
    }}};
  context.window = context; // Browser globals are window properties.
  context.addEventListener = () => {};
  vm.runInNewContext(source, context);
  return {node, form, gps, map, marker: () => marker, click: id => node(id).handlers.click()};
}
{
  const s = setup();
  assert.equal(s.node('confirmBtn').disabled, true);
  s.click('getLocationBtn');
  s.gps[0].ok({coords: {latitude: -25, longitude: -57}});
  assert.equal(s.node('confirmBtn').disabled, true);
  s.click('confirmLocationBtn');
  assert.equal(s.form.elements.client_latitude.value, '-25');
  assert.equal(s.form.elements.client_longitude.value, '-57');
  assert.equal(s.form.elements.destination_confirmed.value, 'yes');
  console.log('PASS GPS requires confirmation and submits chosen coordinates');
}
{
  const s = setup();
  s.click('getLocationBtn');
  s.click('chooseLocationBtn');
  s.map.handlers.click({latlng: {lat: -26, lng: -58}});
  s.click('confirmLocationBtn');
  s.gps[0].ok({coords: {latitude: -25, longitude: -57}});
  assert.equal(s.form.elements.client_latitude.value, '-26');
  assert.equal(s.form.elements.client_longitude.value, '-58');
  console.log('PASS manual destination survives late GPS response');
  s.marker().point = [0, 0];
  s.marker().handlers.dragend();
  assert.equal(s.node('confirmBtn').disabled, true);
  s.click('confirmLocationBtn');
  assert.equal(s.form.elements.client_latitude.value, '0');
  assert.equal(s.form.elements.client_longitude.value, '0');
  console.log('PASS drag requires reconfirmation; zero coordinates accepted');
}
{
  const s = setup();
  s.click('getLocationBtn');
  s.gps[0].fail();
  assert.equal(s.node('confirmBtn').disabled, true);
  assert.equal(s.form.elements.destination_confirmed.value, '');
  let blocked = false;
  s.form.handlers.submit({preventDefault() {blocked = true}});
  assert.ok(blocked);
  assert.equal(s.form.elements.client_latitude.value, '');
  console.log('PASS GPS denial never confirms a default destination');
}
