const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function run({reduced=false,target='/account/settings',media=true}={}){
 const timers=[],destinations=[],events={},classes=new Set();let change;
 const motion={matches:reduced,addEventListener:(event,fn)=>change=fn};
 const window={location:{href:'https://quickgo.test/login/transition',origin:'https://quickgo.test',replace:x=>destinations.push(x)},setTimeout:(fn,ms)=>timers.push({fn,ms}),addEventListener:(event,fn)=>events[event]=fn};
 if(media)window.matchMedia=()=>motion;
 const document={getElementById:()=>({href:target}),body:{classList:{add:x=>classes.add(x)}}};
 vm.runInNewContext(fs.readFileSync('static/js/login_transition.js','utf8'),{window,document,URL});
 return {timers,destinations,events,classes,reduce:()=>change({matches:true})};
}
test('normal motion waits 1600ms and replaces history only once',()=>{
 const h=run();assert.equal(h.timers[0].ms,1600);assert.ok(h.classes.has('transition-running'));
 assert.equal(h.destinations.length,0);h.timers[0].fn();h.timers[0].fn();
 assert.deepEqual(h.destinations,['https://quickgo.test/account/settings']);
});
test('reduced motion and missing media support continue after 100ms',()=>{
 for(const options of [{reduced:true},{media:false}])assert.equal(run(options).timers[0].ms,100);
 const h=run();h.reduce();assert.equal(h.destinations.length,1);
});
test('external and executable targets never auto navigate',()=>{
 for(const target of ['https://evil.example','//evil.example','javascript:alert(1)']){
  const h=run({target});assert.equal(h.timers.length,0);assert.equal(h.destinations.length,0);
 }
});
test('back-forward cache does not replay or trap the authenticated user',()=>{
 const h=run();h.events.pageshow({persisted:true});assert.equal(h.destinations.length,1);
});
test('fallback link, CSS trajectory and reduced motion exist without external dependencies',()=>{
 const html=fs.readFileSync('templates/post_login_transition.html','utf8');
 assert.match(html,/id="transition-continue" href="{{ target }}"/);
 assert.doesNotMatch(html,/socket\.io|cdn\.|<nav|<footer|<form/);
 const css=fs.readFileSync('static/css/login_transition.css','utf8');
 assert.match(css,/prefers-reduced-motion:reduce/);assert.match(css,/animation:none/);
 assert.match(css,/@keyframes go-flight/);assert.match(css,/nth-child\(5\)/);
 assert.doesNotMatch(fs.readFileSync('static/css/login.css','utf8'),/animation:qg-/);
});
