/* Share public property links without copying or uploading property photos. */
(function () {
    'use strict';

    window.createPropertyShareLink = function (property) {
        const propertyUrl = new URL(window.PwaniListings.permalink(property.id), 'https://pwanistays.com');
        const message = `${property.title || 'PwaniStays property'}\nView photos and property details: ${propertyUrl.href}`;
        const whatsappUrl = new URL('https://wa.me/');
        whatsappUrl.searchParams.set('text', message);

        const link = document.createElement('a');
        link.href = whatsappUrl.href;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.className = 'property-share-link';
        link.textContent = 'Share on WhatsApp';
        link.setAttribute('aria-label', `Share ${property.title || 'property'} on WhatsApp`);
        return link;
    };
}());
