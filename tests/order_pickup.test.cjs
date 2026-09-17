const test = require('node:test'), assert = require('node:assert/strict'), vm = require('node:vm'), fs = require('node:fs'), path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/order_pickup.js'), 'utf8');
function harness({confirm = true, ok = true} = {}) {
    let submit; const calls = [], button = {disabled:false};
    const form = {matches:()=>true, action:'/admin/orders/7/pick-up', querySelector:()=>button};
    const document = {addEventListener:(name, fn)=>submit=fn};
    const window = {confirm:()=>confirm, alert:message=>calls.push(message), QuickRealtime:{refreshOrders:async()=>calls.push('refresh')}};
    vm.runInNewContext(source, {window, document, FormData:class {constructor(value){assert.equal(value, form);}},
        fetch:async(url, options)=>{calls.push(options); return {ok, json:async()=>ok?{success:true,status_label:'Retirado del local'}:{error:'Delivery asignado'}};}});
    return {calls,button,submit:()=>submit({target:form,preventDefault(){}})};
}
test('confirmation cancel sends nothing',async()=>{const h=harness({confirm:false});await h.submit();assert.deepEqual(h.calls,[]);});
test('success refreshes existing realtime view and prevents repeat',async()=>{const h=harness();await h.submit();assert.equal(h.calls[0].method,'POST');assert.equal(h.calls[1],'refresh');assert.equal(h.button.textContent,'Retirado del local');await h.submit();assert.equal(h.calls.length,2);});
test('server conflict displays reason and permits retry',async()=>{const h=harness({ok:false});await h.submit();assert.equal(h.calls[1],'Delivery asignado');assert.equal(h.button.disabled,false);});
