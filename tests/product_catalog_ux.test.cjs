const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = name => fs.readFileSync(path.join(__dirname, '../static/js', name), 'utf8');

function setup() {
    const handlers = {}, timers = new Map(), requests = [];
    let nextTimer = 0;
    const document = {activeElement: null, addEventListener(name, fn) {handlers[name] = fn;}};
    class Element {
        constructor(tag) {this.tagName = tag.toUpperCase(); this.dataset = {}; this.events = {}; this.children = []; this.attributes = {}; this.hidden = false; this.value = '';}
        addEventListener(name, fn) {this.events[name] = fn;}
        setAttribute(name, value) {this.attributes[name] = value;}
        append(...nodes) {this.children.push(...nodes); nodes.forEach(node => node.parent = this);}
        replaceChildren(...nodes) {this.children = []; this.append(...nodes);}
        querySelectorAll() {return this.children.filter(node => node.tagName === 'A');}
        querySelector() {return null;}
        contains(node) {return node === this || this.children.some(child => child.contains(node));}
        focus() {document.activeElement = this;}
    }
    const form = new Element('form'), input = new Element('input'), results = new Element('div'), status = new Element('span');
    form.dataset.searchUrl = '/api/products/search'; form.append(input, results, status);
    const elements = {'product-search-form': form, 'product-search': input, 'product-search-results': results, 'product-search-status': status};
    document.getElementById = id => elements[id]; document.createElement = tag => new Element(tag);
    const window = {location: {origin: 'https://quickgo.test'}};
    vm.runInNewContext(source('product_live_search.js'), {document, window, URL, AbortController,
        setTimeout(fn, ms) {assert.equal(ms, 300); timers.set(++nextTimer, fn); return nextTimer;},
        clearTimeout(id) {timers.delete(id);},
        fetch(url, options) {return new Promise(resolve => requests.push({url, options, resolve}));}});
    handlers.DOMContentLoaded();
    return {form,input,results,status,document,requests,handlers,
        type(value) {input.value = value; input.events.input();},
        tick() {const callbacks = [...timers.values()]; timers.clear(); callbacks.forEach(fn => fn());},
        async answer(index, rows, ok = true) {requests[index].resolve({ok, json: async () => rows}); await new Promise(resolve => setImmediate(resolve));}};
}
const row = {name:'<img src=x onerror=alert(1)>', business_name:'<script>shop</script>', price:100,
    url:'/product/1', image:'/derived.jpg', image_original:'/original.jpg'};

test('debounces, ignores short input, aborts old request and rejects stale response', async () => {
    const t = setup();
    t.type('c');t.tick();assert.equal(t.requests.length,0);
    t.type('ce');t.type('cer');t.tick();assert.equal(t.requests.length,1);
    assert.equal(t.requests[0].url.searchParams.get('q'),'cer');
    t.type('cerveza');assert.equal(t.requests[0].options.signal.aborted,true);t.tick();
    await t.answer(1,[row]);assert.equal(t.results.children.length,1);
    await t.answer(0,[]);assert.equal(t.results.children.length,1);
    t.type('');assert.equal(t.results.hidden,true);
});

test('safe text nodes and native keyboard links allow arrows, Enter and Escape', async () => {
    const t=setup();t.type('ce');t.tick();await t.answer(0,[row]);
    const link=t.results.children[0];
    assert.equal(link.href,'https://quickgo.test/product/1');
    assert.equal(link.children[1].children[0].textContent,row.name);
    assert.equal(link.children[1].children[1].textContent,row.business_name);
    let prevented=0;
    t.input.focus();t.form.events.keydown({key:'ArrowDown',preventDefault(){prevented++;}});
    assert.equal(t.document.activeElement,link);assert.equal(prevented,1);
    t.form.events.keydown({key:'Enter',preventDefault(){prevented++;}});
    assert.equal(prevented,1); // Native anchor Enter behavior is preserved.
    t.form.events.keydown({key:'Escape'});
    assert.equal(t.results.hidden,true);assert.equal(t.document.activeElement,t.input);
});

test('HTTP failure keeps submit available; outside focus invalidates in-flight results', async () => {
    const t=setup();t.type('ce');t.tick();await t.answer(0,[],false);
    assert.match(t.status.textContent,/botón Buscar/);assert.equal(t.results.hidden,true);
    t.type('cer');t.tick();t.form.events.focusout({relatedTarget:null});
    await t.answer(1,[row]);assert.equal(t.results.hidden,true);
    let prevented=false;t.form.events.submit({preventDefault(){prevented=true;}});assert.equal(prevented,false);
});

test('limits results and rejects links to another origin', async () => {
    const t=setup();t.type('ce');t.tick();await t.answer(0,Array(12).fill(row));
    assert.equal(t.results.children.length,10);
    t.type('cer');t.tick();await t.answer(1,[{...row,url:'https://evil.test/'}]);
    assert.equal(t.results.children.length,0);
});

test('derived image errors fall back to original then placeholder and stop', () => {
    const events={},window={};
    const image={tagName:'IMG',dataset:{catalogSrc:'/derived.jpg',originalSrc:'/original.jpg',placeholderSrc:'/placeholder.svg'}};
    const document={addEventListener(event,cb){events[event]=cb;},querySelectorAll(){return [image];}};
    vm.runInNewContext(source('product_images.js'),{document,window});
    events.DOMContentLoaded();assert.equal(image.src,'/derived.jpg');
    events.error({target:image});assert.equal(image.src,'/original.jpg');
    events.error({target:image});assert.equal(image.src,'/placeholder.svg');
    for(let n=0;n<5;n++) events.error({target:image});
    assert.equal(image.src,'/placeholder.svg');
});
