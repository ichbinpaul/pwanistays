import assert from 'node:assert/strict';
import test from 'node:test';
import { bookedAmounts, bookingLocation, bookingLocationReview, bookingReport, bookingWrite, furnishingScenario, isoDay, legacyComparison, stayNights, unitNameResolver } from '../bookings/metrics.js';

test('stay dates use calendar days, and never turn reversed dates into positive nights', () => {
    assert.equal(isoDay('2026-02-30'), '');
    assert.equal(isoDay('2026-02-28T10:00:00+03:00'), '2026-02-28');
    assert.equal(stayNights('2026-10-31', '2026-11-02'), 2);
    assert.equal(stayNights('2026-11-02', '2026-10-31'), null);
    assert.equal(stayNights('2026-11-02', '2026-11-02'), null);
    assert.equal(stayNights('', '2026-11-02'), null);
});

test('contribution uses zero for blank costs but requires a recorded guest payment', () => {
    assert.deepEqual(bookedAmounts({ guest_paid: '1000', host_cost: 0, charges: '0' }), { paid: 1000, contribution: 1000 });
    assert.deepEqual(bookedAmounts({ guest_paid: '1000', host_cost: '500', charges: '' }), { paid: 1000, contribution: 500 });
    assert.deepEqual(bookedAmounts({ guest_paid: '1000', host_cost: null, charges: ' ' }), { paid: 1000, contribution: 1000 });
    assert.deepEqual(bookedAmounts({ guest_paid: '1000', host_cost: 'invalid' }), { paid: 1000, contribution: null });
    assert.deepEqual(bookedAmounts({ guest_paid: '', host_cost: 0 }), { paid: null, contribution: null });
    assert.deepEqual(bookedAmounts({ guest_paid: '0', host_cost: '10.01', charges: '0.02' }), { paid: 0, contribution: -10.03 });
});

test('reports keep pipeline out of financials and attribute periods by check-in', () => {
    const base = { status: 'Complete', unit_name: 'Villa A', location: 'Diani', source: 'Referral',
        check_in: '2026-11-30', check_out: '2026-12-02', guest_paid: 12000, host_cost: 7000, charges: 1000 };
    const rows = [
        base,
        { ...base, unit_name: '  villa a ', host_cost: null, check_out: null },
        { ...base, location: 'Nyali' },
        { ...base, status: 'Pending', guest_paid: 999999 },
        { ...base, status: 'In Progress' },
        { ...base, check_in: null },
        { ...base, check_in: '2026-12-02', check_out: '2026-12-03' },
    ];
    const report = bookingReport(rows, '2026-11-01', '2026-11-30');
    assert.equal(report.totals.count, 3);
    assert.equal(report.totals.nights, 4);
    assert.equal(report.totals.paid, 36000);
    assert.equal(report.totals.costedCount, 3);
    assert.equal(report.totals.contribution, 19000);
    assert.equal(report.totals.costedNights, 4);
    assert.equal(report.totals.nightlyContribution, 8000);
    assert.equal(report.units.length, 2);
    assert.equal(report.units[0].count, 2);
    assert.equal(report.months[0].label, '2026-11');
    assert.equal(report.pending, 1);
    assert.equal(report.inProgress, 1);
    assert.equal(report.undated, 1);
    assert.equal(bookingReport(rows).totals.count, 5);
});

test('projected payback allows for expenses, zero bookings and impossible break-even', () => {
    const inputs = { budget: 240000, days: 30, occupancy: 50, nightly: 4000, fixed: 20000 };
    const forecast = furnishingScenario(inputs);
    assert.equal(forecast.cash, 40000);
    assert.equal(forecast.payback, 6);
    assert.equal(forecast.annualReturn, 200);
    assert.equal(forecast.breakEven, 20_000 / 120_000 * 100);
    assert.equal(furnishingScenario({ ...inputs, budget: null }), null);
    assert.equal(furnishingScenario({ ...inputs, occupancy: 101 }), null);
    assert.equal(furnishingScenario({ ...inputs, occupancy: 0 }).payback, null);
    assert.equal(furnishingScenario({ ...inputs, nightly: 0 }).breakEven, null);
    assert.equal(furnishingScenario({ ...inputs, fixed: 150000 }).breakEven, 125);
});

test('the former totals include pending contribution and treat missing costs as zero', () => {
    const completed = { status: 'Complete', guest_paid: 12_000, host_cost: 9_000, charges: 500, profit: 123 };
    const pending = { status: 'Pending', guest_paid: 4_000, host_cost: 3_500, charges: 0 };
    const completedWithoutCharges = { status: 'Complete', guest_paid: 2_000, host_cost: 500, charges: '' };
    const completedWithoutPayment = { status: 'Complete', guest_paid: null, host_cost: 250 };
    const bookings = [completed, pending, completedWithoutCharges, completedWithoutPayment];

    const comparison = legacyComparison(bookings);
    assert.deepEqual(comparison.totals, { count: 4, paid: 18_000, contribution: 4_250 });
    assert.deepEqual(comparison.otherStatus, { count: 1, paid: 4_000, contribution: 500 });
    assert.equal(comparison.withoutContribution.contribution, -250);
    assert.equal(comparison.withContribution.contribution, 4_000);
    assert.equal(bookingReport(bookings).totals.paid, 14_000);
    assert.equal(bookingReport(bookings).totals.contribution, 4_000);
    assert.equal(completed.profit, 123);
});

test('unit names combine verified aliases and matching suffixes without merging different locations or unit numbers', () => {
    const bookings = [
        ['Aqua   Gardens', 'Nyali'], ['Aqua Garden', 'nyali'],
        ['Coral Gables Apart', 'Diani'], ['Coral Gables', 'Diani'], ['Coral Gables Apartment', 'Diani'],
        ['Coral Gables Apartments', 'Diani'], ['Coral Gables Apartment(s)', 'Diani'],
        ['Bxton Point', 'Mombasa'], ['Buxton Point', 'Mombasa'],
        ['Palm Court', 'Watamu'], ['palm court apartments', 'Watamu'], ['Palm Court Apartment', 'Malindi'],
        ['Palm Court Unit 4', 'Watamu'], ['Palm Court Unit 5 Apartment', 'Watamu'],
        ['Mango Apartment', 'Shanzu'], ['Mango Apartments', 'Shanzu'],
    ].map(([unit_name, location]) => ({ unit_name, location, status: 'Complete', guest_paid: 500 }));

    const unitName = unitNameResolver(bookings);
    assert.equal(unitName('AQUA GARDENS', 'Nyali'), 'Aqua Garden');
    assert.equal(unitName('bxton point', ''), 'Buxton Point');
    assert.equal(unitName('Coral Gables Apart', ''), 'Coral Gables');
    assert.equal(unitName('Coral Gables Apartments', ''), 'Coral Gables');
    assert.equal(unitName('Palm Court Apartment', 'watamu'), 'Palm Court');
    assert.equal(unitName('Palm Court Apartment', 'Malindi'), 'Palm Court Apartment');
    assert.equal(unitName('Palm Court Unit 5 Apartment', 'Watamu'), 'Palm Court Unit 5 Apartment');
    assert.equal(unitName('Mango Apartments', 'Shanzu'), 'Mango');
    const { units } = bookingReport(bookings);
    assert.equal(units.length, 8);
    assert.equal(units.find(unit => unit.label === 'Aqua Garden · Nyali').contribution, 1000);
    assert.equal(units.find(unit => unit.label === 'Coral Gables · Diani').contribution, 2500);
    assert.equal(units.find(unit => unit.label === 'Buxton Point · Mombasa').contribution, 1000);
    assert.equal(bookings[0].unit_name, 'Aqua   Gardens');
});

test('confirmed locations repair reporting while the review still counts original locations', () => {
    const completed = (unit_name, location) => ({ unit_name, location, status: 'Complete', guest_paid: 500 });
    const bookings = [
        completed('Coral Sands', 'Diani'),
        completed('Coral Sands Residences', 'Nyali'),
        completed('Coral Sands Recidences', ''),
        { ...completed('Coral Sands Apartments - Nyali', 'nyali'), status: 'Pending' },
        completed('Mwembe TayariNyali', 'Nyali'),
        completed('Mwembe Tayari', 'Mombasa'),
        completed('Palm Villa', 'Watamu'),
        completed('Palm Villa', 'Malindi'),
        completed('Coral Sands Unit 2', 'Diani'),
    ];

    assert.equal(bookingLocation('Coral Sands Unit 2', 'Diani'), 'Diani');
    assert.equal(bookingLocation('Mwembe Tayari - Nyali', ''), 'Mombasa');
    const report = bookingReport(bookings);
    assert.equal(report.units.find(unit => unit.label === 'Coral Sands Residences · Nyali').contribution, 1500);
    assert.equal(report.units.find(unit => unit.label === 'Mwembe Tayari · Mombasa').contribution, 1000);
    assert.equal(report.locations.find(location => location.label === 'Diani').count, 1);
    assert.equal(report.units.filter(unit => unit.unit === 'Palm Villa').length, 2);

    const { patterns } = bookingLocationReview(bookings);
    assert.deepEqual(patterns.find(row => row.unit === 'Coral Sands Residences'), {
        unit: 'Coral Sands Residences', confirmed: 'Nyali', missing: 1,
        recorded: [{ location: 'Nyali', count: 2 }, { location: 'Diani', count: 1 }],
    });
    assert.deepEqual(patterns.find(row => row.unit === 'Mwembe Tayari').recorded,
        [{ location: 'Mombasa', count: 1 }, { location: 'Nyali', count: 1 }]);
    assert.equal(patterns.find(row => row.unit === 'Palm Villa').confirmed, '');
    assert.equal(bookings[0].location, 'Diani');
});

test('location review identifies individual bookings across locations and statuses', () => {
    const bookings = [
        ['PS001', 'Coral Sands Residences', 'Diani', 'Complete'],
        ['PS002', 'Coral Sands', 'Nyali', 'Pending'],
        ['PS003', 'Mwembe TayariNyali', 'Nyali', 'In Progress'],
        ['PS004', 'Palm Court', 'Watamu', 'Complete'],
        ['PS005', 'Palm Court Apartment', 'Malindi', 'Pending'],
        ['PS006', 'Palm Court Apartments', 'Watamu', 'Complete'],
        ['PS007', 'Bungalow 5', 'Bamburi', 'Complete'],
        ['PS008', 'Bungalow 5', 'Kilifi', 'Complete'],
        ['PS009', 'Ocean Home', '', 'Complete'],
        ['PS010', '', '', 'Pending'],
        ['PS011', 'PK Ocean Apartments', 'Mombasa', 'Complete'],
        ['PS012', 'No Name', 'Bamburi', 'Complete'],
        ['PS013', 'No Name', 'Mtwapa', 'Complete'],
    ].map(([id, unit_name, location, status]) => ({ id, unit_name, location, status, guest_paid: 500 }));
    const { conflicts } = bookingLocationReview(bookings);
    assert.deepEqual(conflicts.map(row => row.id).sort(), ['PS001', 'PS003', 'PS005', 'PS007', 'PS008', 'PS009', 'PS010', 'PS011']);
    assert.equal(conflicts.find(row => row.id === 'PS001').locationToCheck, 'Nyali');
    assert.equal(conflicts.find(row => row.id === 'PS003').locationToCheck, 'Mombasa');
    assert.equal(conflicts.find(row => row.id === 'PS005').locationToCheck, 'Watamu');
    assert.equal(conflicts.find(row => row.id === 'PS005').status, 'Pending');
    assert.equal(conflicts.find(row => row.id === 'PS007').locationToCheck, '');
    assert.equal(conflicts.find(row => row.id === 'PS010').contribution, 500);
    assert.equal(conflicts.find(row => row.id === 'PS011').locationToCheck, 'Nyali');
});

test('Buxton Point rolls up both spellings with Mombasa in the unit name', () => {
    const bookings = [
        ['Bxton Point Mombasa', 'Mombasa'],
        ['Buxton Point Mombasa', 'Mombasa'],
        [' BUXTON Point – Mombasa Town. ', 'Mombasa Town'],
        ['Bxton PointMombasa', null],
        ['Buxton Point Unit 12', 'Mombasa'],
    ].map(([unit_name, location]) => ({ unit_name, location, status: 'Complete', guest_paid: 500 }));

    const { units, totals } = bookingReport(bookings);
    assert.deepEqual(units.map(row => [row.label, row.count, row.contribution]), [
        ['Buxton Point · Mombasa', 4, 2000],
        ['Buxton Point Unit 12 · Mombasa', 1, 500],
    ]);
    assert.equal(totals.contribution, 2500);
});

test('confirmed apartment aliases roll up corrected locations and keep distinct numbered units separate', () => {
    const bookings = [
        ['PS001', 'Silent Springs Villas', ''],
        ['PS002', 'Third Avenue Beach Apartments', 'Mombasa'],
        ['PS003', '3rd Avenue Beach Apartments', 'Nyali'],
        ['PS004', 'APA Apartments Nyali', 'Shanzu'],
        ['PS005', 'APA Apartment', 'Nyali'],
        ['PS006', 'PK Ocean Apartments', 'Nyali'],
        ['PS007', 'PK Ocean View Apartments', 'Mombasa'],
        ['PS008', 'PK Ocean View Apartments A3', 'Nyali'],
    ].map(([id, unit_name, location]) => ({ id, unit_name, location, status: 'Complete', guest_paid: 500 }));

    const { locations, units } = bookingReport(bookings);
    assert.deepEqual(locations.map(row => [row.label, row.count]), [['Nyali', 7], ['Diani', 1]]);
    assert.equal(units.find(row => row.label === '3rd Avenue Beach Apartments · Nyali').contribution, 1000);
    assert.equal(units.find(row => row.label === 'APA Apartments Nyali · Nyali').contribution, 1000);
    assert.equal(units.find(row => row.label === 'PK Ocean Apartments · Nyali').contribution, 1000);
    assert.equal(units.find(row => row.label === 'PK Ocean View Apartments A3 · Nyali').contribution, 500);

    const { conflicts } = bookingLocationReview(bookings);
    assert.deepEqual(conflicts.map(row => [row.id, row.locationToCheck]).sort(),
        [['PS001', 'Diani'], ['PS002', 'Nyali'], ['PS004', 'Nyali'], ['PS007', 'Nyali']]);
    assert.equal(bookings[3].location, 'Shanzu');
});

test('Golden Sun and Zuriluxe aliases consolidate without treating N/A as a property', () => {
    const bookings = [
        ['Golden Sand Resort', 'Diani'],
        ['Golden Sun Aprtments', 'Diani'],
        ['Golden Sun Resort', 'Diani'],
        ['Zuriluxe', 'Malindi'],
        ['Zuriluxe Oasis Village', 'Malindi'],
        ['No Name', 'Bamburi'],
        ['NA', 'Malindi'],
        ['N/A', 'Malindi'],
        ['', 'Mtwapa'],
    ].map(([unit_name, location]) => ({ unit_name, location, status: 'Complete', guest_paid: 500 }));

    const name = unitNameResolver(bookings);
    assert.equal(name('No Name', 'Bamburi'), 'N/A');
    const { units, locations } = bookingReport(bookings);
    assert.equal(units.find(row => row.label === 'Golden Sun Resort · Diani').contribution, 1500);
    assert.equal(units.find(row => row.label === 'Zuriluxe Oasis Village · Malindi').contribution, 1000);
    const unavailable = units.find(row => row.label === 'N/A');
    assert.equal(unavailable.count, 4);
    assert.equal(unavailable.unit, undefined);
    assert.equal(locations.find(row => row.label === 'Bamburi').contribution, 500);
    assert.equal(bookingLocationReview(bookings).conflicts.length, 0);
});

test('confirmed names take precedence over generic Apartment suffix grouping', () => {
    const bookings = [
        ['Gayla Apartment', 'Nyali'],
        ['Gayla Place Apartments', 'Nyali'],
        ['Harmony Park', 'Diani'],
        ['Harmony Park Diani', 'Diani'],
        ['Mtwapa Pride', 'Mtwapa'],
        ['Mtwapa Pride Apartments', 'Mtwapa'],
        ['Nightingale Apartment', 'Shanzu'],
        ['Nightingale Apartments', 'Shanzu'],
    ].map(([unit_name, location]) => ({ unit_name, location, status: 'Complete', guest_paid: 500 }));
    const { units } = bookingReport(bookings);
    assert.deepEqual(units.map(row => [row.label, row.count, row.contribution]), [
        ['Gayla Place Apartments · Nyali', 2, 1000],
        ['Harmony Park · Diani', 2, 1000],
        ['Mtwapa Pride Apartments · Mtwapa', 2, 1000],
        ['Nightingale Apartments · Shanzu', 2, 1000],
    ]);
});

test('edits to unrelated fields leave stored amounts and derived fields untouched', () => {
    const existing = {
        guest_paid: 10_000, host_cost: 8_000, charges: null, profit: 2_000,
        check_in: '2026-11-22', check_out: '2026-11-25', month: '2026-11', nights: 3,
    };
    assert.deepEqual(bookingWrite({ notes: 'Arrives in the evening' }, existing), { notes: 'Arrives in the evening' });
    assert.deepEqual(bookingWrite({ status: 'Complete', profit: 10 }, existing), { status: 'Complete' });
    assert.deepEqual(bookingWrite({ guest_paid: 9_000 }, existing), { guest_paid: 9_000, profit: 1_000 });
    assert.deepEqual(bookingWrite({ check_out: '2026-11-26' }, existing), { check_out: '2026-11-26', nights: 4, month: '2026-11' });
    assert.deepEqual(bookingWrite({ guest_paid: 500 }), { guest_paid: 500, profit: 500, nights: null, month: null });
});
