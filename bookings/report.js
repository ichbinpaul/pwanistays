import { amount, bookingReport, furnishingScenario, legacyComparison } from './metrics.js?v=3';

const digits = new Intl.NumberFormat('en-KE', { maximumFractionDigits: 2 });
export const number = value => value == null ? '—' : digits.format(value);
export const money = value => value == null ? '—' : `KES ${number(value)}`;
export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));
export function today() {
    return new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Africa/Nairobi', year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date());
}

export function saveCsv(rows, filename) {
    const csv = window.Papa.unparse(rows, { escapeFormulae: true });
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${filename}_${today()}.csv`;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const sections = [
    ['units', 'Unit'], ['months', 'Check-in month'], ['sources', 'Booking source'],
    ['locations', 'Location'], ['unitTypes', 'Unit type'], ['guestTypes', 'Sub-source'],
];

const details = [
    ['Completed stays', row => row.count],
    ['Booked nights', row => row.nightCount ? row.nights : null],
    ['Guest payments (KES)', row => row.paidCount ? row.paid : null],
    ['Guest payment per night (KES)', row => row.pricedNights ? row.nightlyPaid / row.pricedNights : null],
    ['Stays with contribution', row => row.costedCount],
    ['Contribution (KES)', row => row.costedCount ? row.contribution : null],
    ['Contribution per night (KES)', row => row.costedNights ? row.nightlyContribution / row.costedNights : null],
];

function reportTable(rows, label) {
    if (!rows.length) return '<p class="empty">No completed stays in this period.</p>';
    return `<div class="table-wrap" role="region" tabindex="0" aria-label="${label} performance">
        <table class="report-table"><thead><tr><th scope="col">${label}</th>
        ${details.map(([name]) => `<th scope="col">${name}</th>`).join('')}</tr></thead>
        <tbody>${rows.map(row => `<tr><th scope="row">${escapeHtml(row.unit || row.label)}${row.location ? `<small>${escapeHtml(row.location)}</small>` : ''}</th>
            ${details.map(([, read]) => `<td>${number(read(row))}</td>`).join('')}</tr>`).join('')}</tbody></table>
        </div>`;
}

function exportReport(report, from, through) {
    const rows = [
        ['PwaniStays booking performance'],
        ['Check-in from', from || 'All dates'], ['Check-in through', through || 'All dates'],
        ['Reporting basis', 'Whole stay attributed to check-in. Financial measures only include Complete stays.'],
        ['Contribution', 'Recorded guest payments less host cost and direct charges. Blank costs and charges count as zero.'],
        ['Completed stays with unknown check-in, across all dates', report.undated],
        ['Completed stays with valid nights', report.totals.nightCount],
        ['Completed stays with recorded payment', report.totals.paidCount],
        ['Pending', report.pending], ['In progress', report.inProgress], ['Other status', report.other],
        [],
        ...[['total', 'Portfolio'], ...sections].flatMap(([key, label]) => [
            [label, ...details.map(([name]) => name)],
            ...(key === 'total' ? [{ label: 'Total', ...report.totals }] : report[key]).map(row => [
                row.label, ...details.map(([, read]) => {
                    const value = read(row);
                    return value == null ? '' : Number(value.toFixed(2));
                }),
            ]),
            [],
        ]),
    ];
    saveCsv(rows, 'pwanistays-performance');
}

function card(label, value, context) {
    return `<div class="metric"><h3>${label}</h3><strong>${value}</strong><p>${context}</p></div>`;
}

function drawComparison(bookings) {
    const { totals, otherStatus, withoutContribution, withContribution } = legacyComparison(bookings);
    const rows = [
        ['Former dashboard totals', totals],
        ['Pending, In Progress and other statuses', otherStatus],
        ['Completed with contribution unavailable', withoutContribution],
        ['Completed with contribution available', withContribution],
    ];
    return `<p>The former dashboard included all statuses and counted blank amounts as zero. This comparison uses all dates and the bookings loaded today.</p>
        <div class="table-wrap" role="region" tabindex="0" aria-label="Comparison with the former dashboard">
            <table class="reconciliation-table">
                <thead><tr><th scope="col">Booking group</th><th scope="col">Bookings</th>
                    <th scope="col">Guest payments (KES)</th><th scope="col">Contribution by the old formula (KES)</th></tr></thead>
                <tbody>${rows.map(([label, row]) => `<tr><th scope="row">${label}</th>
                    <td>${number(row.count)}</td><td>${number(row.paid)}</td><td>${number(row.contribution)}</td></tr>`).join('')}
                </tbody>
            </table>
        </div>
        <p>The performance report uses completed stays. Contribution requires a recorded guest payment. Blank host costs and direct charges count as zero.</p>
        ${totals.count > 1000 ? '<p>The former dashboard fetched bookings in one request. Its totals could have omitted records beyond the database response limit.</p>' : ''}`;
}

export function setupReport(root, readBookings) {
    const form = root.querySelector('#reportFilters');
    const from = form.elements.from;
    const through = form.elements.through;
    const dimension = form.elements.dimension;
    const sort = form.elements.sort;
    const output = root.querySelector('#reportOutput');
    const comparison = root.querySelector('#legacyComparison');
    const exportButton = root.querySelector('#exportReport');
    const calculator = root.querySelector('#furnishingForm');
    const unit = calculator.elements.unit;
    const result = root.querySelector('#furnishingResult');
    const evidence = root.querySelector('#furnishingEvidence');
    let report = null;

    function showEvidence() {
        const row = unit.value ? report?.units[Number(unit.value)] : null;
        const contribution = row?.costedNights ? money(row.nightlyContribution / row.costedNights) : 'Unavailable';
        evidence.textContent = row
            ? `${row.count} completed stays in this period. Contribution per night: ${contribution}${row.costedNights ? ` across ${row.costedNights} nights` : ''}.`
            : 'Select a unit to see its booking history alongside your assumptions.';
    }

    function draw() {
        if (!form.reportValidity()) return;
        const bookings = readBookings();
        exportButton.disabled = bookings === null;
        if (bookings === null) {
            output.innerHTML = '<p class="empty">Booking data is unavailable. Refresh bookings to try again.</p>';
            comparison.innerHTML = '';
            report = null;
            unit.replaceChildren(new Option('Select a unit', ''));
            showEvidence();
            return;
        }

        const unitLabel = unit.selectedOptions[0]?.text;
        report = bookingReport(bookings, from.value, through.value);
        comparison.innerHTML = drawComparison(bookings);
        const { totals, pending, inProgress, other, undated } = report;
        const missingDates = totals.count - totals.nightCount;
        const rows = Array.from(report[dimension.value]);
        if (sort.value !== 'default') {
            const value = sort.value === 'contribution'
                ? row => row.costedCount ? row.contribution : -Infinity
                : row => row.costedNights ? row.nightlyContribution / row.costedNights : -Infinity;
            rows.sort((a, b) => value(b) - value(a));
        }
        output.innerHTML = `
            <div class="metric-grid">
                ${card('Completed stays', number(totals.count), `${pending} pending · ${inProgress} in progress${other ? ` · ${other} other` : ''}`)}
                ${card('Booked nights', number(totals.nightCount ? totals.nights : null), `Valid dates for ${totals.nightCount} of ${totals.count} stays`)}
                ${card('Completed guest payments', money(totals.paidCount ? totals.paid : null), `Recorded on ${totals.paidCount} of ${totals.count} completed stays`)}
                ${card('Booking contribution', money(totals.costedCount ? totals.contribution : null), `Calculated for ${totals.costedCount} of ${totals.count} completed stays`)}
            </div>
            <div class="report-section">
                ${reportTable(rows, sections.find(([key]) => key === dimension.value)[1])}
            </div>
            <details class="report-notes" ${(missingDates || undated || totals.count > totals.costedCount) ? 'open' : ''}>
                <summary>How these figures are calculated</summary>
                <p>Each stay is counted in full in the period of its check-in. Booking contribution is guest payment minus host cost and direct charges. Blank costs and charges count as zero. Overheads, furnishing, tax and financing are outside this figure. Booked nights sum stays, so an occupancy rate also needs a record of nights available.</p>
                <p>Completed stays with contribution unavailable: ${totals.count - totals.costedCount}. Completed stays with missing or invalid stay dates: ${missingDates}.
                ${undated && (from.value || through.value) ? `${undated} completed stays across all dates have an unknown check-in and are excluded by this filter.` : ''}</p>
            </details>`;
        unit.replaceChildren(new Option('Select a unit', ''), ...report.units.flatMap((row, index) =>
            row.label === 'Unit missing' ? [] : [new Option(row.label, index, false, row.label === unitLabel)]));
        showEvidence();
    }

    form.addEventListener('submit', event => { event.preventDefault(); draw(); });
    form.addEventListener('change', () => {
        through.setCustomValidity(through.value && from.value > through.value ? 'Choose an end date on or after the start.' : '');
        draw();
    });
    root.querySelector('#clearReportDates').addEventListener('click', () => {
        from.value = '';
        through.value = '';
        through.setCustomValidity('');
        draw();
    });
    exportButton.addEventListener('click', () => {
        if (report && form.reportValidity()) exportReport(report, from.value, through.value);
    });
    unit.addEventListener('change', showEvidence);
    calculator.addEventListener('submit', event => {
        event.preventDefault();
        const assumptions = Object.fromEntries(['budget', 'days', 'occupancy', 'nightly', 'fixed']
            .map(name => [name, amount(calculator.elements[name].value)]));
        const scenario = furnishingScenario(assumptions);
        if (!scenario) return;
        result.innerHTML = `<div class="metric-grid">
            ${card('Monthly operating surplus', money(scenario.cash), 'After the monthly costs entered')}
            ${card('Simple payback', scenario.payback === null ? 'No payback' : `${number(scenario.payback)} months`, 'At the projected monthly surplus')}
            ${card('Annual cash yield', `${number(scenario.annualReturn)}%`, 'Annualized surplus ÷ furnishing spend')}
            ${card('Break-even occupancy', scenario.breakEven === null ? 'Unavailable' : `${number(scenario.breakEven)}%`,
                scenario.breakEven > 100 ? 'Above available capacity' : 'To cover monthly fixed costs')}
            </div>`;
    });
    calculator.addEventListener('input', event => {
        if (event.target !== unit && result.textContent) result.textContent = 'Recalculate to apply your changes.';
    });
    return draw;
}
