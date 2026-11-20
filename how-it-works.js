/* ── Country code searchable datalist (all countries) ── */
document.getElementById('quest-details').addEventListener('toggle', function populateCodes() {
    if (!this.open) return;
    this.removeEventListener('toggle', populateCodes);
    var inp = document.getElementById('q_cc');
    var dl  = document.getElementById('cc_list');
    if (!inp || !dl) return;

    // Full world dial code list [code, name]
    var ALL = [
        ['+1','USA'],['+1','Canada'],['+7','Russia'],['+7','Kazakhstan'],
        ['+20','Egypt'],['+27','South Africa'],['+30','Greece'],['+31','Netherlands'],
        ['+32','Belgium'],['+33','France'],['+34','Spain'],['+36','Hungary'],
        ['+39','Italy'],['+40','Romania'],['+41','Switzerland'],['+43','Austria'],
        ['+44','UK'],['+45','Denmark'],['+46','Sweden'],['+47','Norway'],
        ['+48','Poland'],['+49','Germany'],['+51','Peru'],['+52','Mexico'],
        ['+53','Cuba'],['+54','Argentina'],['+55','Brazil'],['+56','Chile'],
        ['+57','Colombia'],['+58','Venezuela'],['+60','Malaysia'],['+61','Australia'],
        ['+62','Indonesia'],['+63','Philippines'],['+64','New Zealand'],['+65','Singapore'],
        ['+66','Thailand'],['+81','Japan'],['+82','South Korea'],['+84','Vietnam'],
        ['+86','China'],['+90','Turkey'],['+91','India'],['+92','Pakistan'],
        ['+93','Afghanistan'],['+94','Sri Lanka'],['+95','Myanmar'],['+98','Iran'],
        ['+212','Morocco'],['+213','Algeria'],['+216','Tunisia'],['+218','Libya'],
        ['+220','Gambia'],['+221','Senegal'],['+222','Mauritania'],['+223','Mali'],
        ['+224','Guinea'],['+225','Ivory Coast'],['+226','Burkina Faso'],['+227','Niger'],
        ['+228','Togo'],['+229','Benin'],['+230','Mauritius'],['+231','Liberia'],
        ['+232','Sierra Leone'],['+233','Ghana'],['+234','Nigeria'],['+235','Chad'],
        ['+236','Central African Republic'],['+237','Cameroon'],['+238','Cape Verde'],
        ['+239','São Tomé and Príncipe'],['+240','Equatorial Guinea'],['+241','Gabon'],
        ['+242','Republic of the Congo'],['+243','DR Congo'],['+244','Angola'],
        ['+245','Guinea-Bissau'],['+246','British Indian Ocean Territory'],
        ['+247','Ascension Island'],['+248','Seychelles'],['+249','Sudan'],
        ['+250','Rwanda'],['+251','Ethiopia'],['+252','Somalia'],['+253','Djibouti'],
        ['+254','Kenya'],['+255','Tanzania'],['+256','Uganda'],['+257','Burundi'],
        ['+258','Mozambique'],['+260','Zambia'],['+261','Madagascar'],['+262','Réunion'],
        ['+263','Zimbabwe'],['+264','Namibia'],['+265','Malawi'],['+266','Lesotho'],
        ['+267','Botswana'],['+268','Eswatini'],['+269','Comoros'],['+290','Saint Helena'],
        ['+291','Eritrea'],['+297','Aruba'],['+298','Faroe Islands'],['+299','Greenland'],
        ['+350','Gibraltar'],['+351','Portugal'],['+352','Luxembourg'],['+353','Ireland'],
        ['+354','Iceland'],['+355','Albania'],['+356','Malta'],['+357','Cyprus'],
        ['+358','Finland'],['+359','Bulgaria'],['+370','Lithuania'],['+371','Latvia'],
        ['+372','Estonia'],['+373','Moldova'],['+374','Armenia'],['+375','Belarus'],
        ['+376','Andorra'],['+377','Monaco'],['+378','San Marino'],['+380','Ukraine'],
        ['+381','Serbia'],['+382','Montenegro'],['+383','Kosovo'],['+385','Croatia'],
        ['+386','Slovenia'],['+387','Bosnia and Herzegovina'],['+389','North Macedonia'],
        ['+420','Czech Republic'],['+421','Slovakia'],['+423','Liechtenstein'],
        ['+500','Falkland Islands'],['+501','Belize'],['+502','Guatemala'],
        ['+503','El Salvador'],['+504','Honduras'],['+505','Nicaragua'],['+506','Costa Rica'],
        ['+507','Panama'],['+508','Saint Pierre and Miquelon'],['+509','Haiti'],
        ['+590','Guadeloupe'],['+591','Bolivia'],['+592','Guyana'],['+593','Ecuador'],
        ['+594','French Guiana'],['+595','Paraguay'],['+596','Martinique'],['+597','Suriname'],
        ['+598','Uruguay'],['+599','Netherlands Antilles'],['+670','East Timor'],
        ['+672','Norfolk Island'],['+673','Brunei'],['+674','Nauru'],['+675','Papua New Guinea'],
        ['+676','Tonga'],['+677','Solomon Islands'],['+678','Vanuatu'],['+679','Fiji'],
        ['+680','Palau'],['+681','Wallis and Futuna'],['+682','Cook Islands'],['+683','Niue'],
        ['+685','Samoa'],['+686','Kiribati'],['+687','New Caledonia'],['+688','Tuvalu'],
        ['+689','French Polynesia'],['+690','Tokelau'],['+691','Micronesia'],
        ['+692','Marshall Islands'],['+850','North Korea'],['+852','Hong Kong'],
        ['+853','Macau'],['+855','Cambodia'],['+856','Laos'],['+880','Bangladesh'],
        ['+886','Taiwan'],['+960','Maldives'],['+961','Lebanon'],['+962','Jordan'],
        ['+963','Syria'],['+964','Iraq'],['+965','Kuwait'],['+966','Saudi Arabia'],
        ['+967','Yemen'],['+968','Oman'],['+970','Palestine'],['+971','UAE'],
        ['+972','Israel'],['+973','Bahrain'],['+974','Qatar'],['+975','Bhutan'],
        ['+976','Mongolia'],['+977','Nepal'],['+992','Tajikistan'],['+993','Turkmenistan'],
        ['+994','Azerbaijan'],['+995','Georgia'],['+996','Kyrgyzstan'],['+998','Uzbekistan']
    ];

    // Populate datalist
    ALL.forEach(function(c) {
        var opt = document.createElement('option');
        opt.value = c[0] + ' ' + c[1];
        dl.appendChild(opt);
    });

    // Auto-detect based on locale
    var locale = (navigator.language || '').toLowerCase();
    var localeMap = {
        'en-us':'Kenya', 'en-gb':'UK', 'da':'Denmark', 'nb':'Norway',
        'sv':'Sweden', 'de':'Germany', 'fr':'France', 'es':'Spain',
        'it':'Italy', 'nl':'Netherlands', 'en-au':'Australia'
    };
    var detected = '+254 Kenya';
    for (var k in localeMap) {
        if (locale.startsWith(k)) { detected = ALL.find(function(a){ return a[1]===localeMap[k]; }); detected = detected ? detected[0]+' '+detected[1] : '+254 Kenya'; break; }
    }
    if (!inp.value) inp.value = detected;
});

const form = document.getElementById('custForm');
const whatsappDraft = document.getElementById('custWhatsApp');

form.addEventListener('submit', function(e) {
    e.preventDefault();
    var msgDiv = document.getElementById('custMsg');
    msgDiv.textContent = '';
    whatsappDraft.hidden = true;

    var name  = document.getElementById('q_name').value.trim();
    var email = document.getElementById('q_email').value.trim();
    var phone = document.getElementById('q_phone').value.trim();
    if (!name || !email || !phone) {
        msgDiv.textContent = 'Please fill in your name, email, and phone number.';
        return;
    }

    var ccRaw = document.getElementById('q_cc').value.trim();
    var cc = ccRaw.match(/^\+\d+/) ? ccRaw.match(/^\+\d+/)[0] : '';
    var fullPhone = cc + phone.replace(/\s/g, '');

    function radio(n) { var r = document.querySelector('input[name="' + n + '"]:checked'); return r ? r.value : ''; }
    function checks(cls) { return Array.from(document.querySelectorAll('.' + cls + ':checked')).map(function(c){return c.value;}).join(', '); }
    function val(id) { var el = document.getElementById(id); return el ? el.value.trim() : ''; }
    var travelDates = val('q_dateFree') || (val('q_dateFrom') ? val('q_dateFrom') + (val('q_dateTo') ? ' → ' + val('q_dateTo') : '') : '');

    var payload = {
        full_name: name, email: email, phone: fullPhone,
        residence_country: val('q_country'), first_time_kenya: radio('firstTime'),
        travel_dates: travelDates, group_size: val('q_group'),
        special_occasion: val('q_occasion'),
        flight_assistance: radio('flights'), visa_assistance: radio('visa'), arrival_airport: radio('arrival'),
        nairobi_stopover: radio('nairobi'), nairobi_to_coast: radio('nairobi_coast'), safari_interest: radio('safari'),
        nairobi_wildlife: checks('nrb_act'), accommodation_type: val('q_accom'), environment: val('q_env'),
        amenities: checks('amenity'), pace: radio('pace'), guided_pref: radio('guided'), transport: radio('transport'),
        group_pref: radio('group_pref'), seafood: radio('seafood'), swahili_cuisine: radio('swahili'),
        food_tour_interest: radio('foodtour'), welcome_drink: radio('welcome'),
        coastal_activities: checks('activity'), marine_interest: radio('marine'),
        communication_level: radio('comm'), contact_method: radio('contact'), planning_style: radio('planning'),
        departure_transfer: radio('departure'), extend_stay: radio('extend'),
        ideal_trip: val('q_ideal'), avoid_experiences: val('q_avoid'), referral_source: val('q_referral'),
        created_at: new Date().toISOString()
    };

    var lines = [
        '🏝️ *NEW GUEST JOURNEY PROFILE* 🏝️', '',
        '👤 Name: ' + name, '📧 Email: ' + email, '📞 Phone: ' + fullPhone,
        '🌍 Residence: ' + val('q_country'), '🆕 First time? ' + radio('firstTime'),
        '📅 Dates: ' + travelDates, '👥 Group: ' + val('q_group'),
        '🎉 Occasion: ' + val('q_occasion'), '',
        '✈️ Flights: ' + radio('flights'), '🛂 Visa: ' + radio('visa'),
        '🛬 Arrival: ' + radio('arrival'), '🌆 Nairobi stop? ' + radio('nairobi'),
        '🚆 NBO→Coast: ' + radio('nairobi_coast'), '',
        '🦁 Safari: ' + radio('safari'), '🐘 Nairobi wildlife: ' + checks('nrb_act'), '',
        '🏠 Accommodation: ' + val('q_accom') + ' / ' + val('q_env'),
        '✨ Amenities: ' + checks('amenity'), '🚶 Pace: ' + radio('pace'),
        '🗺️ Guided: ' + radio('guided'), '🚗 Transport: ' + radio('transport'),
        '👥 Group pref: ' + radio('group_pref'), '',
        '🦐 Seafood: ' + radio('seafood'), '🍛 Swahili: ' + radio('swahili'),
        '🛒 Food tours: ' + radio('foodtour'),
        '🍻 Welcome drink: ' + radio('welcome'), '',
        '🌿 Activities: ' + checks('activity'), '🌊 Marine: ' + radio('marine'), '',
        '📢 Comm: ' + radio('comm') + ' via ' + radio('contact'),
        '📋 Planning: ' + radio('planning'),
        '✈️ Departure help: ' + radio('departure'), '⏳ Extend? ' + radio('extend'), '',
        '✨ Ideal: ' + val('q_ideal'), '🚫 Avoid: ' + val('q_avoid'),
        '🔗 Referral: ' + val('q_referral')
    ].join('\n');

    whatsappDraft.href = 'https://wa.me/254738544784?text=' + encodeURIComponent(lines);
    whatsappDraft.hidden = false;
    whatsappDraft.click();
    msgDiv.textContent = 'Your draft is ready. Tap Send in WhatsApp to contact our team.';
    saveQuestionnaire(payload);
});
form.querySelector('button[type="submit"]').disabled = false;

let supabaseClient;
async function saveQuestionnaire(payload) {
    try {
        supabaseClient ??= import('https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm')
            .then(({ createClient }) => createClient(
                'https://aanyrtsfeeynykskwxen.supabase.co',
                'sb_publishable_jda30uQX9ZzR_V8CzkeERw_nfx-QWkD'
            ))
            .catch(error => {
                supabaseClient = undefined;
                throw error;
            });
        const client = await supabaseClient;
        const { error } = await client.from('questionnaire_responses').insert([payload]);
        if (error) throw error;
    } catch {
        console.warn('Could not save the questionnaire. The WhatsApp draft is still available.');
    }
}

document.getElementById('currentYear').textContent = new Date().getFullYear();
