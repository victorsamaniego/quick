const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '..');
const css = fs.readFileSync(path.join(root, 'static/css/merchant_status.css'), 'utf8');
const html = fs.readFileSync(path.join(root, 'templates/merchant_status.html'), 'utf8');
test('waiting animation loops continuously with reduced-motion override', () => {
  assert.match(css, /satellite-orbit 10s linear infinite/);
  assert.match(css, /100% \{ offset-distance: 100%/);
  assert.match(css, /brand-color 14s ease-in-out infinite/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /animation: none/);
  assert.match(css, /offset-rotate: 0deg/);
});
test('exclusive page has accessible branding, local assets and protected logout', () => {
  assert.match(html, /aria-label="QuickGo"/);
  assert.match(html, /aria-labelledby="approval-title"/);
  assert.match(html, /name="csrf_token"/);
  assert.match(html, /method="POST"/);
  assert.doesNotMatch(html, /<script|innerHTML|https?:\/\/|<nav/);
  assert.doesNotMatch(html, /user-scalable=no|maximum-scale=1/);
});
