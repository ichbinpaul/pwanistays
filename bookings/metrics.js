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
    if (value == null || String(value).trim() === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

export function bookedAmounts(booking) {
    const paid = amount(booking.guest_paid);
    const host = amount(booking.host_cost);
    const charges = amount(booking.charges);
    const contribution = [paid, host, charges].includes(null) ? null : roundMoney(paid - host - charges);
    return { paid, contribution };
}

function roundMoney(number) {
    return Math.round((number + Math.sign(number) * Number.EPSILON) * 100) / 100;
}

function groupLabel(value, fallback) {
    return String(value ?? '').trim().replace(/\s+/g, ' ') || fallback;
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
        const unit = groupLabel(booking.unit_name, '');
        const location = groupLabel(booking.location, 'Location missing');
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
            if (!group.has(key)) group.set(key, { label, ...summary() });
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
