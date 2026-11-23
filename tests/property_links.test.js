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

test('friendly links activate together and preserve date selections and sharing identity', () => {
    const routes = { enabled: false, paths: { [id]: '/stays/cozy-studio-bamburi/' } };
    const context = { window: { PwaniPropertyRoutes: routes }, URL, URLSearchParams, Date,
        document: {createElement() {return {setAttribute(k,v) {this[k] = v;}};}} };
    load('listing-utils.js', context);
    load('property-sharing.js', context);
    const u = context.window.PwaniListings;
    assert.equal(u.permalink(id), `/stays/${id}/`, 'staging keeps current canonical links');
    routes.enabled = true;
    assert.equal(u.permalink(id.toUpperCase()), '/stays/cozy-studio-bamburi/');
    const url = new URL(u.link(id, {checkin: '2030-02-03', checkout: '2030-02-05', guests: 3}), 'https://pwanistays.com');
    assert.equal(url.pathname, '/stays/cozy-studio-bamburi/');
    assert.equal(url.searchParams.get('checkin'), '2030-02-03');
    assert.equal(url.searchParams.get('checkout'), '2030-02-05');
    assert.equal(url.searchParams.get('guests'), '3');
    const share = context.window.createPropertyShareLink({id, title: 'Cozy Studio'});
    assert.ok(new URL(share.href).searchParams.get('text').includes('https://pwanistays.com/stays/cozy-studio-bamburi/'));
    assert.equal(u.permalink('12345678-abcd-4321-9876-123456789099'), '/stays/12345678-abcd-4321-9876-123456789099/');
});

test('invalid or inactive client mappings safely use the current UUID path', () => {
    const routes = {enabled: true, paths: {}};
    const context = {window: {PwaniPropertyRoutes: routes}, URLSearchParams, Date};
    load('listing-utils.js', context);
    for (const unsafe of ['https://elsewhere.example/', '//elsewhere.example/', '/stays/../secret/', '/stays/Studio/', '/stays/x?next=bad/', '/stays/' + 'x'.repeat(33) + '/']) {
        routes.paths[id] = unsafe;
        assert.equal(context.window.PwaniListings.permalink(id), `/stays/${id}/`);
    }
    routes.paths[id] = '/stays/valid-slug/';
    for (const inactive of ['true', false, undefined]) {
        routes.enabled = inactive;
        assert.equal(context.window.PwaniListings.permalink(id), `/stays/${id}/`);
    }
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

test('public amenities omit rates and contact captions', () => {
    const context = {window: {}, URLSearchParams, Date};
    load('listing-utils.js', context);
    const caption = 'Introductory caption\nAmenities:\n• WiFi\n• Swimming pool\n• KES 6000 per night\n• WhatsApp +254738544784\nRates:\nKES 9000';
    assert.deepEqual(Array.from(context.window.PwaniListings.amenities(caption)), ['WiFi', 'Swimming pool']);
    assert.deepEqual(Array.from(context.window.PwaniListings.amenities('• Ksh6500\n• 12,000 per night\n• $100\n• 6000/=\n• Parking')), ['Parking']);
});

test('the full property gallery includes later storage pages and keeps one designated cover', async () => {
    const context = {window: {}, console};
    load('listing-utils.js', context);
    const u = context.window.PwaniListings;
    const prefix = id + '/_pwani_v6_0123456789abcdef';
    const base = 'https://aanyrtsfeeynykskwxen.supabase.co/storage/v1/object/public/property_images/';
    const files = Array.from({length: 105}, (_, index) => ({
        name: String(index + 1).padStart(3, '0') + '.jpg', metadata: {mimetype: 'image/jpeg'}
    }));
    const offsets = [];
    const bucket = {
        list(folder, {limit, offset}) {
            assert.equal(folder, prefix);
            offsets.push(offset);
            return {data: files.slice(offset, offset + limit)};
        },
        getPublicUrl: name => ({data: {publicUrl: base + name}})
    };
    const cover = base + prefix + '/015.jpg?cache=1';
    const urls = await u.images({storage: {from: () => bucket}}, {id, image_url: cover});
    assert.deepEqual(offsets, [0, 100]);
    assert.equal(urls.length, 105);
    assert.equal(urls[0], cover);
    assert.equal(urls.at(-1), base + prefix + '/105.jpg');
});
