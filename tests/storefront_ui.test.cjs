const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = name => fs.readFileSync(require('node:path').join(__dirname, '../static/js/', name), 'utf8');

test('business GPS is requested only by a click and POST includes CSRF', async () => {
    const events = {}, status = {}, requests = []; let gps = 0, success;
    const button = {dataset: {url: '/admin/business/location'}, addEventListener(event, cb) { events[event] = cb; }};
    const document = {addEventListener(event, cb) { events[event] = cb; }, getElementById(id) { return id === 'save-business-location' ? button : status; }, querySelector() {return {value: 'test-csrf'};}};
    vm.runInNewContext(source('business_location.js'), {document, navigator: {geolocation: {getCurrentPosition(cb) { gps++; success = cb; }}}, fetch: async (url, options) => {requests.push({url, options}); return {ok:true, json:async () => ({message:'Ubicación del negocio guardada'})};}});
    events.DOMContentLoaded(); assert.equal(gps, 0);
    events.click(); assert.equal(gps, 1); assert.equal(button.disabled, true);
    await success({coords: {latitude: -25, longitude: -57}});
    assert.equal(requests[0].options.method, 'POST');
    assert.equal(requests[0].options.headers['X-CSRFToken'], 'test-csrf');
    assert.deepEqual(JSON.parse(requests[0].options.body), {latitude:-25, longitude:-57});
    assert.equal(button.disabled, false);
    assert.equal(status.textContent, 'Ubicación del negocio guardada');
});

test('catalog uses shared socket, ignores foreign businesses and reloads once on closure', async () => {
    const events = {}; let reloads = 0;
    const document = {hidden:false, addEventListener(event, cb) {events[event]=cb;}, querySelectorAll() {return [{dataset:{storefrontBusiness:'1', storefrontOpen:'true', storefrontActive:'true'}}];}};
    const window = {QuickRealtime:{on(event, cb) {events[event]=cb;}}, location:{reload(){reloads++;}}, setInterval(){}};
    vm.runInNewContext(source('storefront_status.js'), {window, document, fetch:async () => ({ok:true,json:async () => ({'1':{is_open:true,is_active:true}})})});
    events.DOMContentLoaded();
    events.business_status_update({business_id:2,is_open:false,is_active:true}); assert.equal(reloads,0);
    events.business_status_update({business_id:1,is_open:false,is_active:true});
    events.business_status_update({business_id:1,is_open:false,is_active:true}); assert.equal(reloads,1);
});

test('audio envelopes are stronger, distinct and bounded during bursts', async () => {
    const peaks = [], frequencies = []; let oscillators = 0;
    class AudioContext {
        constructor() {this.state='running';this.currentTime=0;}
        async resume() {}
        createOscillator() {const frequency={}; return {frequency,connect(){},start(){oscillators++;frequencies.push(frequency.value);},stop(){}};}
        createGain(){return {connect(){},gain:{setValueAtTime(){},linearRampToValueAtTime(value){peaks.push(value);},exponentialRampToValueAtTime(){}}};}
    }
    const window={AudioContext};
    vm.runInNewContext(source('notifications_audio.js'), {window, document:{addEventListener(){}},localStorage:{getItem(){return null;}}});
    await window.QuickGoAudio.unlock();
    for (const type of ['message','new_order','delivery','completed']) window.QuickGoAudio.play(type);
    assert.equal(oscillators,8); assert.equal(new Set(peaks).size,4);
    assert.ok(Math.max(...peaks)>.055); assert.ok(Math.max(...peaks)*4<1);
    for(let i=0;i<100;i++) window.QuickGoAudio.play('new_order');
    assert.equal(oscillators,8);
    assert.ok(new Set(frequencies).size>=5);
});
