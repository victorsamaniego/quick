const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/sw.js'),'utf8');
function worker(visible=false,withClient=true){
    const events={},notifications=[],opened=[],focused=[],closed=[];
    const client={url:'https://quickgo.test/dashboard',visibilityState:visible?'visible':'hidden',async navigate(url){opened.push(url);return this;},async focus(){focused.push(true);}};
    const self={location:{origin:'https://quickgo.test'},addEventListener:(name,fn)=>events[name]=fn,
        clients:{matchAll:async()=>withClient?[client]:[],openWindow:async url=>opened.push(url)},
        registration:{getNotifications:async()=>[],showNotification:async(title,data)=>notifications.push({title,...data})}};
    vm.runInNewContext(source,{self,URL,Set});
    return {notifications,opened,focused,async push(data){let promise;events.push({data:{json:()=>data},waitUntil:p=>promise=p});await promise;},
        async click(url){let promise;events.notificationclick({notification:{data:{url},close:()=>closed.push(true)},waitUntil:p=>promise=p});await promise;}};
}
test('visible app suppresses duplicate system notification',async()=>{const w=worker(true);await w.push({event_id:'a',title:'Test',url:'/orders/1/tracking'});assert.equal(w.notifications.length,0);});
test('background and closed app receive system notification; event IDs deduplicate',async()=>{
    for(const open of [false,true]){const w=worker(false,open);const data={event_id:'a',title:'Pedido',url:'/orders/1/tracking'};await w.push(data);await w.push(data);assert.equal(w.notifications.length,1);assert.equal(w.notifications[0].data.url,data.url);}
});
test('notificationclick focuses existing client or opens internal URL',async()=>{
    for(const open of [false,true]){const w=worker(false,open);await w.click('/chat/order/7');assert.deepEqual(w.opened,['/chat/order/7']);assert.equal(w.focused.length,open?1:0);}
});
test('external URLs, protocol-relative URLs and backslash redirects are blocked on push and click',async()=>{
    for(const url of ['https://evil.test/','//evil.test/','/\\evil.test/','javascript:alert(1)','/\n/evil.test']){
        const w=worker();await w.push({event_id:'a',url});assert.equal(w.notifications[0].data.url,'/');await w.click(url);assert.deepEqual(w.opened,['/']);
    }
});
test('subscription permission is tied to explicit click and worker scope covers private pages',()=>{
    const js=fs.readFileSync(path.join(__dirname,'../static/js/web_push.js'),'utf8');
    const base=fs.readFileSync(path.join(__dirname,'../templates/base.html'),'utf8');
    assert.ok(js.indexOf("button.addEventListener('click'")<js.indexOf('Notification.requestPermission()'));
    assert.equal((js.match(/requestPermission\(/g)||[]).length,1);
    assert.match(base,/register\('\/sw.js', \{scope: '\/'\}\)/);
    assert.doesNotMatch(fs.readFileSync(path.join(__dirname,'../templates/delivery/dashboard.html'),'utf8'),/requestPermission|watchPosition|setInterval\(updateLocation/);
});
