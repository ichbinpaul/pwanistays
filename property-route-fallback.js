/* Keep newly added unit links usable while their first static page is pending. */
(function () {
    'use strict';
    const match = window.location.pathname.match(/^\/stays\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\/(?:index\.html)?$/i);
    if (!match) return;
    const current = new URL(window.location.href);
    const target = new URL('/property.html', current.origin);
    target.searchParams.set('id', match[1].toLowerCase());
    for (const key of ['checkin', 'checkout', 'guests']) {
        if (current.searchParams.has(key)) target.searchParams.set(key, current.searchParams.get(key));
    }
    window.location.replace(target.pathname + target.search);
}());
