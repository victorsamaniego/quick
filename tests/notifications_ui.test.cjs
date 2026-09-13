const test=require('node:test'), assert=require('node:assert/strict'), vm=require('node:vm'), fs=require('node:fs'), path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/js/notifications.js'),'utf8');
function harness() {
    const events={},nodes={},remembered=[];let toastCount=0;
    function node(tag){return {tag,children:[],setAttribute(){},append(...items){this.children.push(...items);},appendChild(item){this.children.push(item);if(item.id)nodes[item.id]=item;if(item.id==='quickgo-notification-toast')toastCount++;},prepend(item){this.children.unshift(item);if(item.id)nodes[item.id]=item;},remove(){delete nodes[this.id];}};}
    nodes['notification-list']=node('div');nodes['notification-unread-count']=node('span');
    const document={hidden:false,body:node('body'),getElementById:id=>nodes[id]||null,createElement:node,addEventListener:(event,fn)=>events[event]=fn};
    const window={realtimeUser:{id:1},QuickRealtime:{on:(event,fn)=>events[event]=fn,remember:key=>remembered.push(key)},setInterval(){},setTimeout(){}};
    let snapshot={notifications:[],unread_count:0};
    vm.runInNewContext(source,{window,document,fetch:async()=>({ok:true,json:async()=>snapshot})});
    return {events,nodes,remembered,toastCount:()=>toastCount,snapshot:value=>snapshot=value,settle:()=>new Promise(resolve=>setImmediate(resolve))};
}
test('inbox recovery is silent, live toast and list deduplicate after reconnect',async()=>{
    const h=harness(), old={notification_id:1,title:'Anterior',message:'Mensaje',is_read:false};
    h.snapshot({notifications:[old],unread_count:1}); await h.events.DOMContentLoaded();
    assert.equal(h.toastCount(),0);assert.deepEqual(h.remembered,['notification:1']);
    const item={notification_id:2,title:'<img onerror=bad>',message:'<script>bad</script>'};
    h.snapshot({notifications:[item,old],unread_count:2});
    h.events.superadmin_notification(item);await h.settle();
    h.events.superadmin_notification(item);await h.events.connect();await h.settle();
    assert.equal(h.toastCount(),1);
    assert.equal(h.nodes['notification-list'].children.length,2);
    assert.equal(h.nodes['notification-2'].children[0].textContent,item.title);
    assert.equal(h.nodes['notification-2'].children[1].textContent,item.message);
    assert.equal(h.nodes['notification-unread-count'].textContent,'2');
    assert.doesNotMatch(source,/innerHTML|\bio\(/);
});
