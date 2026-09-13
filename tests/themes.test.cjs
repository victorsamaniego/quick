const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('preview preserves page classes, accepts only palettes, and makes no persistence request',()=>{
 const classes=new Set(['quickgo-shell','qg-internal','storefront-modern','theme-gold-classic']);
 const choices=['gold-classic','dark-gold','black-gold','sand','arbitrary'].map(value=>({value,checked:true,addEventListener(_,fn){this.change=fn;}}));
 const status={textContent:''},html={dataset:{}};
 const document={querySelectorAll:()=>choices,body:{classList:{remove:x=>classes.delete(x),add:x=>classes.add(x)}},documentElement:html,getElementById:()=>status};
 vm.runInNewContext(fs.readFileSync('static/js/theme_settings.js','utf8'),{document});
 for(const choice of choices.slice(0,4)){
   choice.change.call(choice);
   assert.ok(classes.has('theme-'+choice.value));
   assert.equal([...classes].filter(x=>x.startsWith('theme-')).length,1);
   assert.ok(classes.has('qg-internal')&&classes.has('storefront-modern')&&classes.has('quickgo-shell'));
   assert.equal(html.dataset.theme,choice.value);
 }
 choices[4].change.call(choices[4]);assert.equal(html.dataset.theme,'sand');
 assert.match(status.textContent,/Guardá/);
});
