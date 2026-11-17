/* PwaniStays public listing utilities. No internal rate or commission fields. */
(function () {
  'use strict';
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const FIELDS = 'id,title,location,unit_type,description,image_url,created_at,is_active,is_featured,beds,folder_path';
  const SUPABASE_URL = 'https://aanyrtsfeeynykskwxen.supabase.co';
  const PUBLISHABLE_KEY = 'sb_publishable_jda30uQX9ZzR_V8CzkeERw_nfx-QWkD';
  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function localISO(date) {
    if (!(date instanceof Date) || isNaN(date)) return '';
    return [date.getFullYear(), String(date.getMonth() + 1).padStart(2,'0'), String(date.getDate()).padStart(2,'0')].join('-');
  }
  function validISO(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return false;
    const d = new Date(value + 'T12:00:00');
    return !isNaN(d) && localISO(d) === value;
  }
  function nights(a, b) {
    if (!validISO(a) || !validISO(b)) return 0;
    const start = Date.parse(a + 'T12:00:00Z');
    const end = Date.parse(b + 'T12:00:00Z');
    return Math.round((end - start) / 86400000);
  }
  function link(id, dates) {
    if (!UUID.test(id || '')) return '/accommodation.html';
    const params = new URLSearchParams({id});
    if (dates && validISO(dates.checkin)) params.set('checkin', dates.checkin);
    if (dates && validISO(dates.checkout)) params.set('checkout', dates.checkout);
    if (dates && Number.isInteger(+dates.guests) && +dates.guests >= 1 && +dates.guests <= 16) params.set('guests', String(dates.guests));
    return '/property.html?' + params.toString();
  }
  function client() {
    if (!window.supabase) throw new Error('Unable to connect to our listings right now.');
    if (!window.pwaniListingClient) window.pwaniListingClient = window.supabase.createClient(SUPABASE_URL, PUBLISHABLE_KEY);
    return window.pwaniListingClient;
  }
  const allowedImage = /\.(jpe?g|png|webp|avif|gif)(?:$|\?)/i;
  async function images(db, property) {
    const result = [];
    if (UUID.test(property.id || '')) {
      try {
        const {data, error} = await db.storage.from('property_images').list(property.id, {limit: 100});
        if (!error && data) {
          const sorted = data.filter(f => f.name && allowedImage.test(f.name)).sort((a,b) => {
            const x = +(a.name.match(/\d+/) || [0])[0], y = +(b.name.match(/\d+/) || [0])[0];
            return x-y || a.name.localeCompare(b.name);
          });
          for (const file of sorted) {
            const {data: url} = db.storage.from('property_images').getPublicUrl(property.id+'/'+file.name);
            if (url && url.publicUrl && /^https:\/\//.test(url.publicUrl)) result.push(url.publicUrl);
          }
        }
      } catch (error) { console.warn('Property image request failed', error); }
    }
    if (!result.length && /^https:\/\//.test(property.image_url || '')) result.push(property.image_url);
    return result;
  }
  function formatDate(s) {
    if (!validISO(s)) return 'Not selected';
    return new Date(s + 'T12:00:00').toLocaleDateString('en-KE',{day:'numeric',month:'short',year:'numeric'});
  }

  // Display amenity lines only; exclude prose from older caption imports.
  function amenities(value) {
    const rows = String(value ?? '').split(/\r?\n/);
    const headingText = line => String(line).trim()
      .replace(/^[^\p{L}\p{N}]+/gu, '').replace(/[:\s]+$/g, '').toLowerCase();
    const amenitiesHeading = /^(?:(?:key|main|top|apartment|property|house|room|unit)\s+)?(?:amenities|facilities|features|highlights|inclusions|what you(?:'ll| will) (?:love|enjoy))(?:\s*(?:&|and|\/)\s*(?:amenities|facilities|features|highlights))?$/;
    const otherHeading = /^(?:location|contacts?|bookings?|reservations?|rates?|prices?|payments?|terms?|house rules|check[ -]?in(?:\/out)?|check[ -]?out|availability|cancellation|notes?|important|nearby|how to book)$/;
    const clean = line => String(line).trim().replace(/^(?:[-*•]\s+|\d+[.)]\s+)/, '').trim();
    let inSection = false;
    let foundSection = false;
    const items = [];
    for (const row of rows) {
      const text = row.trim();
      if (!text) continue;
      const heading = headingText(text);
      if (amenitiesHeading.test(heading)) {
        foundSection = true;
        inSection = true;
        continue;
      }
      if (otherHeading.test(heading) || /^(?:dm|book|call|whatsapp|contact|inbox|message us)\b/.test(heading)) {
        inSection = false;
        continue;
      }
      if (inSection) items.push(clean(text));
    }
    if (foundSection) return items.filter(Boolean);
    // v4 importer prefixes amenities with bullets; never guess from prose.
    return rows.filter(row => /^\s*•\s+/.test(row)).map(clean).filter(Boolean);
  }

  window.PwaniListings = {FIELDS, UUID, escapeHtml, localISO, validISO, nights, link, client, images, formatDate, amenities};
})();
