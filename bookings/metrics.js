export function isoDay(value) {
    const day = String(value ?? '').slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return '';
    const date = new Date(day);
    return Number.isFinite(+date) && date.toISOString().slice(0, 10) === day ? day : '';
}

export function stayNights(checkIn, checkOut) {
    const start = isoDay(checkIn);
    const end = isoDay(checkOut);
    return start && end && end > start ? (Date.parse(end) - Date.parse(start)) / 86400000 : null;
}

export function amount(value) {
    if (blankAmount(value)) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function blankAmount(value) {
    return value == null || String(value).trim() === '';
}

export function bookedAmounts(booking) {
    const paid = amount(booking.guest_paid);
    const host = blankAmount(booking.host_cost) ? 0 : amount(booking.host_cost);
    const charges = blankAmount(booking.charges) ? 0 : amount(booking.charges);
    const contribution = [paid, host, charges].includes(null) ? null : roundMoney(paid - host - charges);
    return { paid, contribution };
}

function legacyAmount(value) {
    return parseFloat(value) || 0;
}

function legacyContribution(booking) {
    return legacyAmount(booking.guest_paid) - legacyAmount(booking.host_cost) - legacyAmount(booking.charges);
}

export function legacyComparison(bookings) {
    const empty = () => ({ count: 0, paid: 0, contribution: 0 });
    const totals = empty(), otherStatus = empty(), withoutContribution = empty(), withContribution = empty();
    for (const booking of bookings) {
        const paid = legacyAmount(booking.guest_paid);
        const contribution = legacyContribution(booking);
        const group = booking.status?.trim().toLowerCase() !== 'complete' ? otherStatus
            : bookedAmounts(booking).contribution === null ? withoutContribution : withContribution;
        for (const row of [totals, group]) {
            row.count++;
            row.paid += paid;
            row.contribution += contribution;
        }
    }
    return { totals, otherStatus, withoutContribution, withContribution };
}

export function bookingWrite(fields, previous = null) {
    const { profit, month, nights, ...patch } = fields;
    const booking = { ...previous, ...patch };
    if (!previous || ['guest_paid', 'host_cost', 'charges'].some(field => Object.hasOwn(patch, field))) {
        patch.profit = legacyContribution(booking);
    }
    if (!previous || ['check_in', 'check_out'].some(field => Object.hasOwn(patch, field))) {
        patch.nights = stayNights(booking.check_in, booking.check_out);
        patch.month = isoDay(booking.check_in).slice(0, 7) || null;
    }
    return patch;
}

function roundMoney(number) {
    return Math.round((number + Math.sign(number) * Number.EPSILON) * 100) / 100;
}

export function groupLabel(value, fallback = '') {
    return String(value ?? '').trim().replace(/\s+/g, ' ') || fallback;
}

const unitAliases = new Map([
    ['aqua garden', 'Aqua Garden'],
    ['aqua gardens', 'Aqua Garden'],
    ['buxton point', 'Buxton Point'],
    ['bxton point', 'Buxton Point'],
    ['coral gables', 'Coral Gables'],
    ['coral gables apart', 'Coral Gables'],
    ['coral gables apartment', 'Coral Gables'],
    ['coral gables apartments', 'Coral Gables'],
    ['coral gables apartment(s)', 'Coral Gables'],
]);

const confirmedUnits = [
    {
        name: 'Coral Sands Residences',
        location: 'Nyali',
        aliases: /^coral sands(?: (?:(?:residen|reciden)ce|apartment)(?:s|\(s\))?)?(?: (?:nyali|diani))?$/,
    },
    {
        name: 'Mwembe Tayari',
        location: 'Mombasa',
        aliases: /^mwembe tayari(?: ?(?:nyali|mombasa(?: town)?))?$/,
    },
];

function confirmedUnit(name) {
    const label = groupLabel(String(name ?? '').toLowerCase().replace(/[,–—-]/g, ' '));
    return confirmedUnits.find(unit => unit.aliases.test(label));
}

function knownUnitName(name) {
    const label = groupLabel(name);
    return confirmedUnit(label)?.name ?? unitAliases.get(label.toLowerCase()) ?? label;
}

export function bookingLocation(name, recordedLocation) {
    return confirmedUnit(name)?.location ?? groupLabel(recordedLocation);
}

export function unitNameResolver(bookings) {
    const byLocation = new Map();
    for (const booking of bookings) {
        const location = bookingLocation(booking.unit_name, booking.location).toLowerCase();
        const name = knownUnitName(booking.unit_name);
        if (!location || !name) continue;
        if (!byLocation.has(location)) byLocation.set(location, new Map());
        const names = byLocation.get(location);
        if (!names.has(name.toLowerCase())) names.set(name.toLowerCase(), name);
    }
    return (name, location) => {
        const confirmed = confirmedUnit(name);
        if (confirmed) return confirmed.name;
        const label = knownUnitName(name);
        const names = byLocation.get(groupLabel(location).toLowerCase());
        const shortName = label.replace(/\s+apartments?$/i, '');
        const key = shortName.toLowerCase();
        const base = names?.get(key);
        if (base) return base;
        const singular = names?.get(`${key} apartment`);
        if (singular && names.has(`${key} apartments`)) return singular.replace(/\s+apartment$/i, '');
        return names?.get(label.toLowerCase()) ?? label;
    };
}

export function bookingLocationReview(bookings) {
    const units = new Map();
    for (const booking of bookings) {
        const name = knownUnitName(booking.unit_name);
        const confirmed = bookingLocation(name);
        const unit = confirmed ? name : name.replace(/\s+apartments?$/i, '');
        const key = unit.toLowerCase();
        if (!units.has(key)) {
            units.set(key, { unit, confirmed, recorded: new Map(), missing: 0, bookings: [] });
        }
        const review = units.get(key);
        const location = groupLabel(booking.location);
        review.bookings.push({ booking, location });
        if (!location) {
            review.missing++;
            continue;
        }
        const locationKey = location.toLowerCase();
        if (!review.recorded.has(locationKey)) review.recorded.set(locationKey, { location, count: 0 });
        review.recorded.get(locationKey).count++;
    }
    const patterns = [];
    const conflicts = [];
    for (const review of units.values()) {
        const { unit, confirmed, missing } = review;
        const recorded = [...review.recorded.values()].sort((a, b) => b.count - a.count || a.location.localeCompare(b.location));
        const [first, second] = recorded;
        const tied = first && first.count === second?.count;
        const usual = unit && !tied ? first?.location : '';
        if (unit && (confirmed || recorded.length > 1 || missing)) patterns.push({ unit, confirmed, missing, recorded });

        for (const { booking, location } of review.bookings) {
            const key = location.toLowerCase();
            let reason;
            if (confirmed && key !== confirmed.toLowerCase()) reason = 'Conflicts with confirmed location';
            else if (!location) reason = 'Location is blank';
            else if (unit && !confirmed && recorded.length > 1) {
                if (tied) reason = 'Tie between recorded locations';
                else if (key !== usual.toLowerCase()) reason = 'Unit recorded more often elsewhere';
            }
            if (reason) conflicts.push({
                id: booking.id,
                unit: groupLabel(booking.unit_name),
                status: groupLabel(booking.status, 'Unspecified'),
                location,
                locationToCheck: confirmed || usual || '',
                reason,
                contribution: bookedAmounts(booking).contribution,
            });
        }
    }
    patterns.sort((a, b) => a.unit.localeCompare(b.unit));
    conflicts.sort((a, b) => a.unit.localeCompare(b.unit) || String(a.id ?? '').localeCompare(String(b.id ?? ''), undefined, { numeric: true }));
    return { patterns, conflicts };
}

function summary() {
    return { count: 0, nightCount: 0, nights: 0, paidCount: 0, paid: 0, costedCount: 0,
        contribution: 0, costedNights: 0, nightlyContribution: 0, pricedNights: 0, nightlyPaid: 0 };
}

function accumulate(group, nights, { paid, contribution }) {
    group.count++;
    if (nights !== null) {
        group.nightCount++;
        group.nights += nights;
    }
    if (paid !== null) {
        group.paidCount++;
        group.paid += paid;
        if (nights !== null) {
            group.pricedNights += nights;
            group.nightlyPaid += paid;
        }
    }
    if (contribution !== null) {
        group.costedCount++;
        group.contribution += contribution;
        if (nights !== null) {
            group.costedNights += nights;
            group.nightlyContribution += contribution;
        }
    }
}

export function bookingReport(bookings, from, through) {
    const unitName = unitNameResolver(bookings);
    const totals = summary();
    const groups = { units: new Map(), months: new Map(), sources: new Map(), locations: new Map(),
        unitTypes: new Map(), guestTypes: new Map() };
    let pending = 0, inProgress = 0, other = 0, undated = 0;

    for (const booking of bookings) {
        const date = isoDay(booking.check_in);
        const status = booking.status?.trim().toLowerCase();
        if (!date && status === 'complete') undated++;
        if ((from && (!date || date < from)) || (through && (!date || date > through))) continue;
        if (status !== 'complete') {
            if (status === 'pending') pending++;
            else if (status === 'in progress') inProgress++;
            else other++;
            continue;
        }

        const nights = stayNights(date, booking.check_out);
        const money = bookedAmounts(booking);
        const unit = unitName(booking.unit_name, booking.location);
        const location = bookingLocation(booking.unit_name, booking.location) || 'Location missing';
        const unitLabel = unit ? `${unit} · ${location}` : 'Unit missing';
        const labels = {
            units: [unitLabel, unit ? JSON.stringify([unit.toLowerCase(), location.toLowerCase()]) : null],
            months: [date ? date.slice(0, 7) : 'Check-in missing'],
            sources: [groupLabel(booking.source, 'Source missing')],
            locations: [location],
            unitTypes: [groupLabel(booking.unit_type, 'Unit type missing')],
            guestTypes: [groupLabel(booking.sub_source, 'Sub-source missing')],
        };
        accumulate(totals, nights, money);
        for (const [dimension, [label, key = label.toLowerCase()]] of Object.entries(labels)) {
            const group = groups[dimension];
            if (!group.has(key)) group.set(key, { label, ...summary(), ...(dimension === 'units' && unit ? { unit, location } : {}) });
            accumulate(group.get(key), nights, money);
        }
    }
    const sections = Object.fromEntries(Object.entries(groups).map(([name, group]) => {
        const rows = Array.from(group.values());
        rows.sort(name === 'months' ? (a, b) => a.label.localeCompare(b.label)
            : (a, b) => b.count - a.count || a.label.localeCompare(b.label));
        return [name, rows];
    }));
    return { totals, pending, inProgress, other, undated, ...sections };
}

export function furnishingScenario({ budget, days, occupancy, nightly, fixed }) {
    if ([budget, days, occupancy, nightly, fixed].some(value => value == null || !Number.isFinite(value)) ||
        budget <= 0 || days <= 0 || days > 31 || occupancy < 0 || occupancy > 100 || fixed < 0) return null;

    const booked = days * occupancy / 100;
    const cash = roundMoney(booked * nightly - fixed);
    return {
        cash,
        payback: cash > 0 ? budget / cash : null,
        annualReturn: cash * 12 / budget * 100,
        breakEven: nightly > 0 ? fixed / (days * nightly) * 100 : null,
    };
}
