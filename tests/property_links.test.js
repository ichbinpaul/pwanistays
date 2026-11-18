const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const id = '12345678-abcd-4321-9876-123456789012';

function load(file, context) {
    vm.runInNewContext(fs.readFileSync(path.join(root, file), 'utf8'), context);
}

test('unit links keep dates separate from their stable preview identity', () => {
    const context = { window: {}, URLSearchParams, Date };
    load('listing-utils.js', context);
    const u = context.window.PwaniListings;
    assert.equal(u.permalink(id), `/stays/${id}/`);
    assert.equal(u.permalink(id.toUpperCase()), `/stays/${id}/`);
    const url = new URL(u.link(id, {checkin: '2030-02-03', checkout: '2030-02-05', guests: 3}), 'https://pwanistays.com');
    assert.equal(url.pathname, `/stays/${id}/`);
    assert.equal(url.searchParams.get('checkin'), '2030-02-03');
    assert.equal(url.searchParams.get('checkout'), '2030-02-05');
    assert.equal(url.searchParams.get('guests'), '3');
    assert.equal(url.searchParams.has('id'), false);
    assert.equal(u.link('not-a-property'), '/#stays');
});

test('WhatsApp draft uses the property preview URL and preserves its title', () => {
    const context = { window: {}, URL, URLSearchParams, Date,
        document: {createElement() {return {setAttribute(k,v) {this[k] = v;}};}} };
    load('listing-utils.js', context);
    load('property-sharing.js', context);
    const title = 'Paul’s & Jane’s <villa> 🏖';
    const link = context.window.createPropertyShareLink({id, title});
    const target = new URL(link.href);
    assert.equal(target.origin, 'https://wa.me');
    const text = target.searchParams.get('text');
    assert.ok(text.startsWith(title));
    assert.ok(text.includes(`https://pwanistays.com/stays/${id}/`));
    assert.equal(link.rel, 'noopener noreferrer');
});

test('a pending static page falls back to the same unit with date selections', () => {
    const href = `https://pwanistays.com/stays/${id}/?checkin=2030-02-03&checkout=2030-02-05&guests=3&next=https://elsewhere.example`;
    let redirected;
    const location = { href, pathname: new URL(href).pathname, replace(value) {redirected = value;} };
    load('property-route-fallback.js', {window: {location}, URL});
    const url = new URL(redirected, 'https://pwanistays.com');
    assert.equal(url.pathname, '/property.html');
    assert.equal(url.searchParams.get('id'), id);
    assert.equal(url.searchParams.get('checkin'), '2030-02-03');
    assert.equal(url.searchParams.get('guests'), '3');
    assert.equal(url.searchParams.has('next'), false);
});

test('ordinary missing pages and invalid unit paths retain the 404 page', () => {
    for (const pathname of ['/missing', '/stays/../secret/', '/stays/not-a-uuid/']) {
        let redirected = false;
        load('property-route-fallback.js', {window: {location: {pathname, replace() {redirected = true;}}}, URL});
        assert.equal(redirected, false);
    }
});
