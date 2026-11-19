import test from 'node:test';
import assert from 'node:assert/strict';
import worker, {
    handleRequest, resolveRedirect, validateRegistry, REGISTRY_URL, MAX_REGISTRY_BYTES,
} from '../cloudflare/property-redirects.mjs';

const ID = '12345678-abcd-4321-9876-123456789012';
const OTHER = '12345678-abcd-4321-9876-123456789013';
const registry = { version: 1, ready_for_redirects: true, slugs: { [ID]: 'nyali-studio' } };
const enabled = { PROPERTY_URLS_ENABLED: 'true' };

function registryResponse(value = registry, options = {}) {
    return new Response(JSON.stringify(value), {
        headers: { 'Content-Type': 'application/json' }, ...options,
    });
}

function fetchStub(response = () => registryResponse()) {
    const calls = [];
    const origin = new Response('unchanged origin', { status: 200 });
    const fetcher = async (input, options) => {
        calls.push([input, options]);
        return input === REGISTRY_URL ? response() : origin;
    };
    return { calls, fetcher, origin };
}

test('GET and HEAD legacy paths redirect 301 to the fixed friendly origin', async () => {
    for (const method of ['GET', 'HEAD']) {
        for (const suffix of ['', '/', '/index.html']) {
            const { calls, fetcher } = fetchStub();
            const result = await handleRequest(new Request(`https://pwanistays.com/stays/${ID}${suffix}`, { method }), enabled, fetcher);
            assert.equal(result.status, 301);
            assert.equal(result.headers.get('Location'), 'https://pwanistays.com/stays/nyali-studio/');
            assert.equal(await result.text(), '');
            assert.equal(calls.length, 1);
            assert.equal(calls[0][0], REGISTRY_URL);
            assert.equal(calls[0][1].cf.cacheTtl, 300);
            assert.equal(calls[0][1].redirect, 'error');
        }
    }
});

test('legacy query routes preserve booking and UTM fields while removing identities', () => {
    for (const path of [`/property.html?id=${ID}`, `/?property=${ID}`]) {
        const extraIdentity = path.startsWith('/property.html') ? '&property=' + OTHER : '&id=' + OTHER;
        const result = new URL(resolveRedirect('https://pwanistays.com' + path +
            '&checkin=2026-12-01&checkout=2026-12-03&guests=3&utm_source=WhatsApp&utm_campaign=Coast%20stays' + extraIdentity, registry));
        assert.equal(result.searchParams.get('checkin'), '2026-12-01');
        assert.equal(result.searchParams.get('checkout'), '2026-12-03');
        assert.equal(result.searchParams.get('guests'), '3');
        assert.equal(result.searchParams.get('utm_source'), 'WhatsApp');
        assert.equal(result.searchParams.get('utm_campaign'), 'Coast stays');
        assert.equal(result.searchParams.has('id'), false);
        assert.equal(result.searchParams.has('property'), false);
    }
});

test('disabled mode and non-GET methods only pass the original request to origin', async () => {
    for (const env of [{}, { PROPERTY_URLS_ENABLED: 'false' }, { PROPERTY_URLS_ENABLED: true }]) {
        const { calls, fetcher, origin } = fetchStub();
        const request = new Request(`https://pwanistays.com/stays/${ID}/`);
        assert.equal(await handleRequest(request, env, fetcher), origin);
        assert.deepEqual(calls, [[request, undefined]]);
    }
    const { calls, fetcher, origin } = fetchStub();
    const request = new Request(`https://pwanistays.com/property.html?id=${ID}`, { method: 'POST', body: 'unchanged payload' });
    assert.equal(await handleRequest(request, enabled, fetcher), origin);
    assert.deepEqual(calls, [[request, undefined]]);
    assert.equal(await request.text(), 'unchanged payload');
});

test('normal, friendly, different-host and malformed routes do not fetch a registry', async () => {
    const routes = [
        'https://pwanistays.com/', 'https://pwanistays.com/?location=Nyali',
        'https://pwanistays.com/stays/nyali-studio/', 'https://pwanistays.com/stays/not-a-uuid/',
        `https://other.example/stays/${ID}/`, `https://pwanistays.com:8443/stays/${ID}/`,
        `https://pwanistays.com/stays/${ID}/extra`, `https://pwanistays.com/property.html?id=${ID}&id=${OTHER}`,
        `https://pwanistays.com/?property=${ID}&property=${OTHER}`,
    ];
    for (const url of routes) {
        const { calls, fetcher, origin } = fetchStub();
        const request = new Request(url);
        assert.equal(await handleRequest(request, enabled, fetcher), origin);
        assert.deepEqual(calls, [[request, undefined]], url);
    }
});

test('a known-shaped but unmapped UUID looks up the map then passes through', async () => {
    const { calls, fetcher, origin } = fetchStub();
    const request = new Request(`https://pwanistays.com/stays/${OTHER}/`);
    assert.equal(await handleRequest(request, enabled, fetcher), origin);
    assert.equal(calls[0][0], REGISTRY_URL);
    assert.equal(calls[1][0], request);
    assert.equal(calls.length, 2);
});

test('a staged or missing readiness flag keeps current URLs usable even if the Worker is enabled', async () => {
    for (const ready of [false, undefined, 'true', 1]) {
        const value = { ...registry, ready_for_redirects: ready };
        const { calls, fetcher, origin } = fetchStub(() => registryResponse(value));
        const request = new Request(`https://pwanistays.com/stays/${ID}/`);
        assert.equal(await handleRequest(request, enabled, fetcher), origin);
        assert.equal(calls.length, 2);
        assert.equal(calls[1][0], request);
    }
});

test('unsafe, duplicate, reserved and UUID-shaped slugs cannot redirect', async () => {
    const invalid = [
        { version: 2, slugs: { [ID]: 'nyali-studio' } },
        { version: 1, slugs: [] },
        { version: 1, slugs: { invalid: 'nyali-studio' } },
        { version: 1, slugs: { [ID]: 'nyali-studio', [OTHER]: 'nyali-studio' } },
        ...['https://evil.example', '//evil.example', '../outside', 'x?next=evil', 'Nyali', 'école',
            '-invalid', 'invalid-', 'x'.repeat(33), ID, '', 'assets', 'property', 'index-html'].map(slug => ({
            version: 1, slugs: { [ID]: slug },
        })),
    ];
    for (const value of invalid) {
        assert.throws(() => validateRegistry(value));
        const { calls, fetcher, origin } = fetchStub(() => registryResponse(value));
        const request = new Request(`https://pwanistays.com/stays/${ID}/`);
        assert.equal(await handleRequest(request, enabled, fetcher), origin);
        assert.equal(calls.length, 2);
    }
});

test('registry network failures, invalid JSON/type/status and size overflow preserve origin', async () => {
    const replies = [
        () => { throw new Error('fetch failed'); },
        () => new Response('not json', { headers: { 'Content-Type': 'application/json' } }),
        () => new Response('{}', { headers: { 'Content-Type': 'text/html' } }),
        () => registryResponse(registry, { status: 503 }),
        () => new Response('{}', { headers: { 'Content-Type': 'application/json', 'Content-Length': String(MAX_REGISTRY_BYTES + 1) } }),
        () => new Response(' '.repeat(MAX_REGISTRY_BYTES + 1), { headers: { 'Content-Type': 'application/json' } }),
    ];
    for (const reply of replies) {
        const { calls, fetcher, origin } = fetchStub(reply);
        const request = new Request(`https://pwanistays.com/stays/${ID}/`);
        assert.equal(await handleRequest(request, enabled, fetcher), origin);
        assert.equal(calls.length, 2);
    }
});

test('public map requests never inherit customer authorization or cookies', async () => {
    const { calls, fetcher } = fetchStub();
    const request = new Request(`https://pwanistays.com/stays/${ID}/`, {
        headers: { Authorization: 'Bearer private-customer-value', Cookie: 'session=private' },
    });
    await handleRequest(request, enabled, fetcher);
    assert.deepEqual(calls[0][1].headers, { Accept: 'application/json' });
});

test('Cloudflare module wrapper ignores the runtime ExecutionContext argument', async () => {
    const previous = globalThis.fetch;
    const { calls, fetcher, origin } = fetchStub();
    const request = new Request(`https://pwanistays.com/stays/${ID}/`);
    globalThis.fetch = fetcher;
    try {
        assert.equal(await worker.fetch(request, {}, { waitUntil() {} }), origin);
        assert.deepEqual(calls, [[request, undefined]]);
    } finally {
        globalThis.fetch = previous;
    }
});

test('legacy public HTML paths redirect once with the original query string', async () => {
    const env = { SITE_HTML_REDIRECTS_ENABLED: 'true' };
    const query = '?utm_source=coast%20trip&tag=a&tag=b&empty=';
    const paths = {
        '/index.html': '/',
        '/how-it-works.html': '/how-it-works',
        '/stays.html': '/stays',
        '/header.html': '/header',
        '/property.html': '/property',
        '/guides/diani/index.html': '/guides/diani/',
        '/stays/nyali-studio/index.html': '/stays/nyali-studio/',
    };
    for (const [legacy, clean] of Object.entries(paths)) {
        for (const method of ['GET', 'HEAD']) {
            const { calls, fetcher } = fetchStub();
            const response = await handleRequest(new Request('https://pwanistays.com' + legacy + query, { method }), env, fetcher);
            assert.equal(response.status, 301, legacy);
            assert.equal(response.headers.get('Location'), 'https://pwanistays.com' + clean + query);
            assert.equal(calls.length, 0);
        }
    }
});

test('clean routes serve the existing origin file with its query and method', async () => {
    for (const path of ['/how-it-works', '/stays', '/header']) {
        const { calls, fetcher, origin } = fetchStub();
        const request = new Request('https://pwanistays.com' + path + '?tag=a&tag=b', { method: 'HEAD' });
        assert.equal(await handleRequest(request, {}, fetcher), origin);
        assert.equal(calls[0][0].url, 'https://pwanistays.com' + path + '.html?tag=a&tag=b');
        assert.equal(calls[0][0].method, 'HEAD');
    }
});

test('HTML property redirects preserve the full query even when resolving a friendly slug', async () => {
    const { fetcher } = fetchStub();
    const query = `?id=${ID}&checkin=2030-02-03&tag=a&tag=b&utm_source=coast%20trip`;
    const env = { ...enabled, SITE_HTML_REDIRECTS_ENABLED: 'true' };
    const request = new Request('https://pwanistays.com/property.html' + query);
    const response = await handleRequest(request, env, fetcher);
    assert.equal(response.status, 301);
    assert.equal(response.headers.get('Location'), 'https://pwanistays.com/stays/nyali-studio/' + query);
});
