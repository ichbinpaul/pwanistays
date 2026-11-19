/* Date-first inquiries on a static GitHub Pages property detail page. */
document.addEventListener('DOMContentLoaded', async () => {
  const u = window.PwaniListings;
  const params = new URLSearchParams(location.search);
  // Generated pages embed their own identity; a query cannot switch units.
  // Keep older /property.html?id=... links usable for existing conversations.
  const id = document.documentElement.dataset.propertyId || params.get('id');
  const declaredPath = document.documentElement.dataset.propertyPath;
  const canonicalPath = /^\/stays\/[a-z0-9-]+\/$/.test(declaredPath || '')
    ? declaredPath : u.permalink(id);
  const status = document.getElementById('propertyStatus');
  const content = document.getElementById('propertyContent');
  const checkin = document.getElementById('checkin');
  const checkout = document.getElementById('checkout');
  const guests = document.getElementById('guests');
  const errorEl = document.getElementById('quoteError');
  const summary = document.getElementById('nightsSummary');
  const form = document.getElementById('quoteForm');
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = true;
  if (!u.UUID.test(id || '')) {
    status.hidden = false;
    content.hidden = true;
    status.textContent = 'This property link is invalid. Browse our current accommodation listings instead.';
    return;
  }
  const today = u.localISO(new Date());
  checkin.min = today;
  checkout.min = today;
  const inParam = params.get('checkin'), outParam = params.get('checkout');
  if (u.validISO(inParam) && inParam >= today) checkin.value = inParam;
  if (u.validISO(outParam) && outParam > (checkin.value || today)) checkout.value = outParam;
  const g = Number(params.get('guests'));
  if (Number.isInteger(g) && g >= 1 && g <= 16) guests.value = String(g);
  function updateDates() {
    checkout.min = checkin.value ? u.localISO(new Date(Date.parse(checkin.value + 'T12:00:00') + 86400000)) : today;
    if (checkout.value && (checkout.value <= checkin.value || checkout.value < today)) checkout.value = '';
    const n = u.nights(checkin.value,checkout.value);
    summary.textContent = n > 0 ? `${n} night${n === 1 ? '' : 's'} selected` : 'Select both dates to see your number of nights.';
    errorEl.textContent = '';
  }
  checkin.addEventListener('change', updateDates);
  checkout.addEventListener('change',updateDates);
  guests.addEventListener('change',() => { errorEl.textContent = ''; });
  updateDates();
  let property;
  try {
    const db = u.client();
    const {data, error} = await db.from('properties').select(u.FIELDS).eq('id', id).eq('is_active',true).maybeSingle();
    if (error) throw error;
    if (!data) {
      content.hidden = true;
      status.hidden = false;
      status.textContent = 'This property is not currently listed. Browse other available accommodation.';
      const robots = document.querySelector('meta[name="robots"]');
      if (robots) robots.content = 'noindex,follow';
      return;
    }
    property = data;
    const canonicalUrl = 'https://pwanistays.com' + canonicalPath;
    if (!document.documentElement.dataset.propertyId ||
        (window.PwaniPropertyRoutes && window.PwaniPropertyRoutes.enabled === true && location.pathname !== canonicalPath)) {
      const dated = new URL(location.href);
      dated.pathname = canonicalPath;
      dated.searchParams.delete('id');
      dated.searchParams.delete('property');
      history.replaceState(null, '', dated.pathname + dated.search);
    }
    const pageTitle = `${data.title || 'Coastal accommodation'} | PwaniStays`;
    const pageDescription = `Explore ${data.title || 'this stay'} in ${data.location || 'coastal Kenya'}. View amenities and photos, then request current rates and availability from PwaniStays.`;
    document.title = pageTitle;
    const descMeta = document.querySelector('meta[name="description"]');
    if (descMeta) descMeta.content = pageDescription;
    // A single stable canonical URL for each property, regardless of dates or guests.
    let canonicalMeta = document.querySelector('link[rel="canonical"]');
    if (!canonicalMeta) {
      canonicalMeta = document.createElement('link');
      canonicalMeta.rel = 'canonical';
      document.head.appendChild(canonicalMeta);
    }
    canonicalMeta.href = canonicalUrl;
    for (const [selector, value] of [
      ['meta[property="og:url"]', canonicalUrl],
      ['meta[property="og:title"]', pageTitle],
      ['meta[property="og:description"]', pageDescription]
    ]) {
      let tag = document.querySelector(selector);
      if (!tag) {
        tag = document.createElement('meta');
        tag.setAttribute('property', selector.match(/meta\[property="([^"]+)"/)[1]);
        document.head.appendChild(tag);
      }
      tag.content = value;
    }
    // Descriptive structured data only, without unverified prices or availability.
    if (!document.getElementById('property-structured-data')) {
      const structured = document.createElement('script');
      structured.id = 'property-structured-data';
      structured.type = 'application/ld+json';
      structured.textContent = JSON.stringify({
      '@context': 'https://schema.org',
      '@type': 'WebPage',
      name: pageTitle,
      description: pageDescription,
      url: canonicalUrl,
      isPartOf: { '@type': 'WebSite', name: 'PwaniStays', url: 'https://pwanistays.com/' }
      });
      document.head.appendChild(structured);
    }
    document.getElementById('breadcrumbTitle').textContent = data.title || 'Property details';
    document.getElementById('propertyTitle').textContent = data.title || 'Coastal accommodation';
    document.getElementById('propertyLocation').textContent = '📍 ' + (data.location || 'Coastal Kenya');
    const types = {'studio':'Studio','1br':'1 bedroom','2br':'2 bedrooms','3br':'3 bedrooms','4br':'4 bedrooms','5br':'5 bedrooms','villa':'Villa'};
    document.getElementById('propertyType').textContent = types[data.unit_type] || (data.unit_type || 'Holiday accommodation');
    document.getElementById('propertyBeds').textContent = Number(data.beds) > 0
      ? '🛏 ' + Number(data.beds) + ' bed' + (Number(data.beds) === 1 ? '' : 's') : '';
    // The database's legacy "description" column can contain a full caption.
    // Render only its amenities, never its introductory promotional paragraph.
    const amenitiesList = document.getElementById('propertyAmenities');
    amenitiesList.replaceChildren();
    const items = u.amenities(data.description || '');
    for (const text of (items.length ? items : ['Please contact PwaniStays to confirm the property amenities.'])) {
      const li = document.createElement('li');
      li.textContent = text;
      amenitiesList.appendChild(li);
    }
    const urls = await u.images(db, data);
    const main = document.getElementById('pwMainImage');
    const ownedCover = main.dataset.seoSource === String(data.image_url || '').trim()
      ? main.dataset.seoImage : null;
    const cover = ownedCover || urls[0];
    if (urls.length) {
      for (const selector of ['meta[property="og:image"]', 'meta[property="og:image:secure_url"]', 'meta[name="twitter:image"]']) {
        const tag = document.querySelector(selector);
        if (tag) tag.content = cover;
      }
    }
    const thumbs = document.getElementById('pwThumbs');
    if (!urls.length) document.getElementById('pwNoPhoto').hidden = false;
    else {
      main.src = cover; main.alt = `${data.title || 'Accommodation'} — photo 1`; main.hidden = false;
      if (urls.length > 1) {
        thumbs.hidden = false;
        urls.slice(0,18).forEach((src,i) => {
          const b = document.createElement('button'); b.type = 'button';
          b.setAttribute('aria-label',`View property photo ${i+1}`);
          b.setAttribute('aria-pressed',i===0 ? 'true' : 'false');
          const img = document.createElement('img'); img.src=src; img.alt=''; img.loading='lazy';
          b.appendChild(img);
          b.addEventListener('click',() => {
            main.src = src; main.alt = `${data.title || 'Accommodation'} — photo ${i+1}`;
            thumbs.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x===b ? 'true':'false'));
          });
          thumbs.appendChild(b);
        });
      }
    }
    status.hidden = true; content.hidden = false;
  } catch (err) {
    console.error('Unable to load property:',err);
    status.hidden = false;
    status.textContent = 'We could not load this property right now. Please try again, or message PwaniStays directly.';
    return;
  }
  const propertyLink = 'https://pwanistays.com' + canonicalPath;
  document.getElementById('emailInquiry').addEventListener('click', (e) => {
    e.currentTarget.href = `mailto:bookings@pwanistays.com?subject=${encodeURIComponent('PwaniStays quotation — '+property.title)}&body=${encodeURIComponent('Hello PwaniStays,\n\nPlease send me the current rate and availability for:\nProperty: '+property.title+'\nLink: '+propertyLink+'\nCheck-in: '+(checkin.value || 'To be confirmed')+'\nCheck-out: '+(checkout.value || 'To be confirmed')+'\nGuests: '+guests.value+'\n\nThank you.')}`;
  });
  form.addEventListener('submit',(e) => {
    e.preventDefault();
    const n = u.nights(checkin.value,checkout.value);
    if (!checkin.value || checkin.value < today || !u.validISO(checkin.value) || !u.validISO(checkout.value) || n <= 0 || !Number.isInteger(+guests.value) || +guests.value < 1 || +guests.value > 16) {
      errorEl.textContent = 'Please select a valid check-in date, check-out date and number of guests.';
      return;
    }
    if (n > 365) {errorEl.textContent = 'For stays over one year, please contact us directly.';return;}
    const message = [`Hello PwaniStays! I would like a quotation for this property.`,
      ``, `Property: ${property.title}`, `Location: ${property.location || 'Coastal Kenya'}`,
      `Link: ${propertyLink}`, `Check-in: ${u.formatDate(checkin.value)}`,
      `Check-out: ${u.formatDate(checkout.value)}`, `Nights: ${n}`, `Guests: ${guests.value}`,
      ``, `Please confirm availability and the total price. Thank you!`].join('\n');
    location.href = `https://wa.me/254738544784?text=${encodeURIComponent(message)}`;
  });
  if (submit) submit.disabled = false;
});
