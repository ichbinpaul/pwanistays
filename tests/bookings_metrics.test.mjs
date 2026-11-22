import assert from 'node:assert/strict';
import test from 'node:test';
import { bookedAmounts, bookingReport, bookingWrite, furnishingScenario, isoDay, legacyComparison, stayNights } from '../bookings/metrics.js';

test('stay dates use calendar days, and never turn reversed dates into positive nights', () => {
    assert.equal(isoDay('2026-02-30'), '');
    assert.equal(isoDay('2026-02-28T10:00:00+03:00'), '2026-02-28');
    assert.equal(stayNights('2026-10-31', '2026-11-02'), 2);
    assert.equal(stayNights('2026-11-02', '2026-10-31'), null);
    assert.equal(stayNights('2026-11-02', '2026-11-02'), null);
    assert.equal(stayNights('', '2026-11-02'), null);
});

test('contribution distinguishes an explicit zero, missing inputs and a loss', () => {
    assert.deepEqual(bookedAmounts({ guest_paid: '1000', host_cost: 0, charges: '0' }), { paid: 1000, contribution: 1000 });
    assert.deepEqual(bookedAmounts({ guest_paid: '1000', host_cost: 0, charges: '' }), { paid: 1000, contribution: null });
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
    assert.equal(report.totals.costedCount, 2);
    assert.equal(report.totals.contribution, 8000);
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
    const incomplete = { status: 'Complete', guest_paid: 2_000, host_cost: 500, charges: '' };
    const bookings = [completed, pending, incomplete];

    const comparison = legacyComparison(bookings);
    assert.deepEqual(comparison.totals, { count: 3, paid: 18_000, contribution: 4_500 });
    assert.deepEqual(comparison.otherStatus, { count: 1, paid: 4_000, contribution: 500 });
    assert.equal(comparison.missingAmounts.contribution, 1_500);
    assert.equal(comparison.fullyCosted.contribution, 2_500);
    assert.equal(bookingReport(bookings).totals.paid, 14_000);
    assert.equal(bookingReport(bookings).totals.contribution, 2_500);
    assert.equal(completed.profit, 123);
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
