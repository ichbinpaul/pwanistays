/* Preparation only: keep PROPERTY_URLS_ENABLED disabled until every friendly
 * target is published and the canonical migration is ready. This Worker
 * does not deploy itself, create pages, or change a catalogue. */

export const REGISTRY_URL = 'https://pwanistays.com/catalogue/property-slugs.json';
export const MAX_REGISTRY_BYTES = 1024 * 1024;
const ORIGIN = 'https://pwanistays.com';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const RESERVED = new Set([
    'index', 'index-html', 'new', 'search', 'feed', 'assets', 'images',
    'directory', 'stays', 'properties', 'property',
]);

export function validateRegistry(registry) {
    if (!registry || registry.version !== 1 || !registry.slugs ||
        typeof registry.slugs !== 'object' || Array.isArray(registry.slugs)) {
        throw new Error('Invalid public property registry');
    }
    const slugs = new Map();
    const unique = new Set();
    for (const [id, slug] of Object.entries(registry.slugs)) {
        if (!UUID.test(id) || typeof slug !== 'string' || slug.length > 32 ||
            !SLUG.test(slug) || UUID.test(slug) || RESERVED.has(slug) || unique.has(slug)) {
            throw new Error('Invalid or conflicting public property mapping');
        }
        slugs.set(id, slug);
        unique.add(slug);
    }
    return slugs;
}

function legacyId(url) {
    if (url.hostname !== 'pwanistays.com' || !['http:', 'https:'].includes(url.protocol) || url.port) return null;
    const match = url.pathname.match(/^\/stays\/([0-9a-f-]+)(?:\/(?:index\.html)?)?$/);
    if (match) return UUID.test(match[1]) ? match[1] : null;
    const parameter = url.pathname === '/property.html' ? 'id' : url.pathname === '/' ? 'property' : null;
    if (!parameter || url.searchParams.getAll(parameter).length !== 1) return null;
    const id = url.searchParams.get(parameter);
    return UUID.test(id || '') ? id : null;
}

/** Return a fixed-origin friendly URL, or null. No network or account writes. */
export function resolveRedirect(input, registry) {
    const url = input instanceof URL ? input : new URL(input);
    const id = legacyId(url);
    if (!id) return null;
    const slug = validateRegistry(registry).get(id);
    if (!slug) return null;
    const target = new URL('/stays/' + slug + '/', ORIGIN);
    target.search = url.search;
    target.searchParams.delete('id');
    target.searchParams.delete('property');
    return target.href;
}

async function readRegistry(response) {
    const mime = (response.headers.get('content-type') || '').split(';')[0].trim();
    if (!response.ok || !/^application\/(?:[a-z0-9.+-]+\+)?json$/i.test(mime)) {
        throw new Error('Public registry unavailable');
    }
    const length = response.headers.get('content-length');
    if (length !== null && (!/^\d+$/.test(length) || Number(length) > MAX_REGISTRY_BYTES)) {
        throw new Error('Registry size is invalid');
    }
    if (!response.body) throw new Error('Registry body is empty');
    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8', { fatal: true });
    let bytes = 0;
    let text = '';
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            bytes += value.byteLength;
            if (bytes > MAX_REGISTRY_BYTES) {
                await reader.cancel();
                throw new Error('Registry exceeds size limit');
            }
            text += decoder.decode(value, { stream: true });
        }
        text += decoder.decode();
    } finally {
        reader.releaseLock();
    }
    return JSON.parse(text);
}

export async function handleRequest(request, env = {}, fetcher = fetch) {
    if (env.PROPERTY_URLS_ENABLED !== 'true' || !['GET', 'HEAD'].includes(request.method)) {
        return fetcher(request);
    }
    const url = new URL(request.url);
    // Normal pages, friendly paths and invalid UUIDs never fetch the registry.
    if (!legacyId(url)) return fetcher(request);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    try {
        const response = await fetcher(REGISTRY_URL, {
            method: 'GET', redirect: 'error', signal: controller.signal,
            headers: { Accept: 'application/json' },
            cf: { cacheTtl: 300, cacheEverything: true },
        });
        const registry = await readRegistry(response);
        // A dashboard toggle alone must not activate a staged canonical map.
        // The site build publishes this only with the friendly canonical release.
        if (registry.ready_for_redirects === true) {
            const target = resolveRedirect(url, registry);
            if (target) return Response.redirect(target, 301);
        }
    } catch {
        // Bad maps/network failures must leave the existing site usable.
    } finally {
        clearTimeout(timeout);
    }
    return fetcher(request);
}

export default {
    // Cloudflare's third argument is an ExecutionContext, not our test fetcher.
    fetch(request, env) {
        return handleRequest(request, env);
    },
};
