const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/js/reset_token.js'), 'utf8');
test('recovery fragment is removed from history and placed only in hidden field', () => {
    const field = {value: ''}; const calls = [];
    vm.runInNewContext(source, {window: {location: {hash: '#' + 'a'.repeat(43), pathname: '/recover/token'},
        history: {replaceState: (...args) => calls.push(args)}}, document: {getElementById: () => field}});
    assert.equal(field.value, 'a'.repeat(43));
    assert.deepEqual(calls[0], [null, '', '/recover/token']);
});
test('malformed fragment is removed and never inserted into form', () => {
    const field = {value: ''}; let clean = false;
    vm.runInNewContext(source, {window: {location: {hash: '#<script>', pathname: '/recover/token'},
        history: {replaceState: () => {clean = true;}}}, document: {getElementById: () => field}});
    assert.equal(field.value, ''); assert.equal(clean, true);
});
