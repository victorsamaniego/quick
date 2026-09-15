const test = require('node:test'), assert = require('node:assert/strict'), vm = require('node:vm'), fs = require('node:fs'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/delivery_tracking.js'), 'utf8');
function harness({transmit = false, active = true, initialPosition = null} = {}) {
    const events = {}, dom = {}, page = {}, intervals = [], nodes = {}, stats = {maps:0, moves:0, bounds:0, watches:0, clears:0, emits:[], removed:0};
    let now = 100000, geo, snapshot = {order_id:1, status:active ? 'shipped' : 'delivered', active, can_transmit:transmit,
        delivery_driver_id:3, pickup:{latitude:-25,longitude:-57}, dropoff:{latitude:-25.1,longitude:-57.1}, position:initialPosition};
    const root = {dataset:{orderId:'1'}, querySelector(selector) {return nodes[selector] ||= {textContent:''};}};
    const document = {hidden:false, querySelectorAll:()=>[root], addEventListener:(name, fn)=>dom[name]=fn};
    function marker() {return {addTo(){return this;}, bindPopup(){return this;}, setLatLng(coords){stats.moves++;stats.last=coords;}};}
    const map = {fitBounds(){stats.bounds++;},setView(){},removeLayer(){},remove(){stats.removed++;}};
    const window = {
        QuickRealtime:{on(name,fn){events[name]=fn;return ()=>delete events[name];}},
        socket:{connected:true,emit(name,data,ack){stats.emits.push([name,data]);if(ack)ack({success:true});}},
        navigator:{geolocation:{watchPosition(fn){geo=fn;stats.watches++;return 9;},clearWatch(id){assert.equal(id,9);stats.clears++;}}},
        L:{map(){stats.maps++;return map;},tileLayer(){return {addTo(){}};},divIcon:options=>options,marker},
        fetch:async()=>({ok:true,status:200,json:async()=>snapshot}),
        setInterval(fn,ms){intervals.push([fn,ms]);return intervals.length;},clearInterval(){},
        addEventListener:(name,fn)=>page[name]=fn
    };
    vm.runInNewContext(source, {window,document,Date:{now:()=>now},Number,Math,Infinity});
    dom.DOMContentLoaded();
    return {events,dom,page,stats,nodes,window,document,intervals,settle:()=>new Promise(r=>setImmediate(r)),
        tick(ms){now+=ms;intervals.filter(([,n])=>n===1000).forEach(([fn])=>fn());},
        gps(){geo({coords:{latitude:-25.01,longitude:-57.01,accuracy:5}});},
        snapshot(value){snapshot={...snapshot,...value};}, async recover(){await intervals.find(([,ms])=>ms===15000)[0]();}};
}
test('waiting, one map, marker changes without F5 or refit; stale after 25 seconds', async()=>{
    const h=harness();await h.settle();
    assert.match(h.nodes['[data-tracking-state]'].textContent,/Esperando/);
    for (const latitude of [-25.01,-25.02,-25.03]) h.events.delivery_location_update({order_id:1,delivery_driver_id:3,latitude,longitude:-57,updated_at:100});
    assert.equal(h.stats.maps,1);assert.equal(h.stats.bounds,1);assert.equal(h.stats.moves,2);
    assert.match(h.nodes['[data-tracking-state]'].textContent,/en vivo/);
    h.tick(26000);assert.match(h.nodes['[data-tracking-age]'].textContent,/Última ubicación hace 26/);
});
test('only authorized active driver starts watch; other roles never transmit',async()=>{
    for (const options of [{}, {transmit:true,active:false}]) {const h=harness(options);await h.settle();assert.equal(h.stats.watches,0);}
    const h=harness({transmit:true});await h.settle();assert.equal(h.stats.watches,1);
    h.gps();h.gps();h.tick(4999);h.gps();assert.equal(h.stats.emits.filter(([event])=>event==='delivery_location_update').length,1);
    h.tick(1);h.gps();assert.equal(h.stats.emits.filter(([event])=>event==='delivery_location_update').length,2);
});
test('delivered clears GPS immediately and removes live state for all roles',async()=>{
    for(const transmit of [false,true]){
        const h=harness({transmit});await h.settle();
        h.events.order_status_update({order_id:1,status:'delivered'});
        assert.equal(h.stats.clears,transmit?1:0);assert.equal(h.nodes['[data-tracking-state]'].textContent,'Pedido entregado');
        h.events.delivery_location_update({order_id:1,delivery_driver_id:3,latitude:0,longitude:0,updated_at:100});h.tick(1000);
        assert.equal(h.nodes['[data-tracking-state]'].textContent,'Pedido entregado');
    }
});
test('hidden/disconnect/pagehide stop GPS; foreground and reconnect reauthorize and restore snapshot',async()=>{
    const h=harness({transmit:true});await h.settle();
    h.document.hidden=true;h.dom.visibilitychange();assert.equal(h.stats.clears,1);
    h.document.hidden=false;h.dom.visibilitychange();await h.settle();assert.equal(h.stats.watches,2);
    h.window.socket.connected=false;h.events.disconnect();assert.equal(h.stats.clears,2);
    h.snapshot({position:{latitude:-25,longitude:-57,updated_at:100}});
    h.window.socket.connected=true;h.events.connect();await h.settle();assert.equal(h.stats.watches,3);assert.equal(h.stats.maps,1);
    h.page.pagehide();assert.equal(h.stats.clears,3);
});
test('assignment revoked stops watch, old driver samples are ignored',async()=>{
    const h=harness({transmit:true});await h.settle();
    h.snapshot({delivery_driver_id:4,can_transmit:false});h.events.delivery_assigned({order_id:1});await h.settle();
    assert.equal(h.stats.clears,1);
    h.events.delivery_location_update({order_id:1,delivery_driver_id:3,latitude:0,longitude:0,updated_at:100});
    assert.match(h.nodes['[data-tracking-state]'].textContent,/Esperando/);
});
test('late HTTP snapshot cannot resurrect completed tracking',async()=>{
    const h=harness({transmit:true});await h.settle();let resolve;
    h.window.fetch=()=>new Promise(r=>resolve=r);
    const request=h.recover();h.events.order_status_update({order_id:1,status:'cancelled'});
    resolve({ok:true,status:200,json:async()=>({active:true,can_transmit:true,status:'shipped'})});await request;
    assert.equal(h.nodes['[data-tracking-state]'].textContent,'Pedido cancelado');assert.equal(h.stats.watches,1);
});

test('picked_up stops GPS and displays store pickup',async()=>{
    const h=harness({transmit:true});await h.settle();
    h.events.order_status_update({order_id:1,status:'picked_up'});
    assert.equal(h.stats.clears,1);
    assert.equal(h.nodes['[data-tracking-state]'].textContent,'Retirado del local');
});
