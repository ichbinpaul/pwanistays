import { amount, bookedAmounts, bookingLocation, bookingWrite, groupLabel, isoDay, stayNights, unitNameResolver } from './metrics.js?v=9';
import { escapeHtml, money, number, saveCsv, setupReport } from './report.js?v=9';

const SUPABASE_URL = "https://aanyrtsfeeynykskwxen.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_jda30uQX9ZzR_V8CzkeERw_nfx-QWkD";
const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
let bookings = [];
let unitName = unitNameResolver(bookings);
let filteredStatus = '';
let filterText = '';
let page = 0;
const pageSize = 40;
let dataReady = false;
let loadRequest = 0;
let drawReport;
let originalForm;
let activeTab = 'bookings';
const statusOptions = ['Complete', 'In Progress', 'Pending'];
const fieldOptions = ['location', 'unit_type', 'source', 'sub_source', 'unit_name', 'host'];

const fields = [
    'id', 'guest_name', 'gender', 'phone', 'unit_name', 'location', 'unit_type', 'check_in',
    'check_out', 'nights', 'guest_paid', 'host_cost', 'charges', 'profit', 'status',
    'source', 'sub_source', 'month', 'host', 'notes',
];
const moneyFields = ['guest_paid', 'host_cost', 'charges'];

function addSuggestions() {
    for (const field of fieldOptions) {
        const list = document.getElementById(`${field}_options`);
        const values = new Set(bookings.map(booking => {
            if (field === 'unit_name') return unitName(booking.unit_name, booking.location);
            if (field === 'location') return bookingLocation(booking.unit_name, booking.location);
            return booking[field]?.trim();
        }).filter(Boolean));
        if (field === 'unit_name') values.add('N/A');
        list.replaceChildren(...Array.from(values).sort((a, b) => a.localeCompare(b)).map(value => new Option(value)));
    }
}

async function loadBookings() {
    const request = ++loadRequest;
    const status = document.getElementById('bookingsStatus');
    const add = document.getElementById('addBtn');
    const importer = document.getElementById('importBtn');
    const refresh = document.getElementById('refreshBtn');
    dataReady = false;
    add.disabled = importer.disabled = refresh.disabled = true;
    status.textContent = 'Loading bookings…';
    renderBookingsTable();
    if (activeTab === 'analytics') drawReport();
    const records = [];
    const size = 500;
    try {
        for (let offset = 0; ; offset += size) {
            const { data, error } = await supabaseClient.from('bookings').select('*')
                .order('created_at', { ascending: false }).order('id').range(offset, offset + size - 1);
            if (request !== loadRequest) return;
            if (error) throw error;
            records.push(...data);
            if (data.length < size) break;
        }
        bookings = records;
        unitName = unitNameResolver(bookings);
        addSuggestions();
        dataReady = true;
        add.disabled = importer.disabled = false;
        status.textContent = '';
    } catch {
        if (request !== loadRequest) return;
        bookings = [];
        unitName = unitNameResolver(bookings);
        status.textContent = 'Could not load bookings. Try Refresh.';
    } finally {
        if (request === loadRequest) {
            refresh.disabled = false;
            renderBookingsTable();
            if (activeTab === 'analytics') drawReport();
        }
    }
}

function renderBookingsTable() {
    const container = document.getElementById('bookingsContainer');
    if (!dataReady) { container.replaceChildren(); return; }
    const statusOrder = new Map([['Pending', 0], ['In Progress', 1], ['Complete', 2]]);
    const filtered = bookings.filter(booking =>
        (!filteredStatus || (filteredStatus === 'needs-review'
            ? booking.status?.trim().toLowerCase() === 'complete' && (
                !stayNights(booking.check_in, booking.check_out) ||
                bookedAmounts(booking).contribution === null || !booking.unit_name?.trim())
            : booking.status === filteredStatus)) &&
        (!filterText || [booking.id, booking.guest_name, booking.unit_name, bookingLocation(booking.unit_name, booking.location), booking.phone]
            .some(value => String(value ?? '').toLowerCase().includes(filterText)) ||
            unitName(booking.unit_name, booking.location).toLowerCase().includes(unitName(filterText, booking.location).toLowerCase()))
    ).sort((a, b) => (statusOrder.get(a.status) ?? 3) - (statusOrder.get(b.status) ?? 3));

    if (!filtered.length) {
        container.innerHTML = `<p class="empty">${bookings.length ? 'No matches. Try another search or status.' : 'Add your first booking to get started.'}</p>`;
        return;
    }
    const totalPages = Math.ceil(filtered.length / pageSize);
    page = Math.min(page, totalPages - 1);
    const start = page * pageSize;
    const visible = filtered.slice(start, start + pageSize);
    container.innerHTML = `
        <div class="table-tools">
            <span>${number(start + 1)}–${number(start + visible.length)} of ${number(filtered.length)} bookings</span>
            <div class="inline-actions">
                <button id="exportAllBtn" class="secondary" type="button">Export bookings CSV</button>
                <select id="bulkAction" aria-label="Apply to selected bookings" disabled>
                    <option value="">With selected…</option>
                    <option value="export">Export as CSV</option>
                    ${statusOptions.map(status => `<option value="${status}">Mark ${status.toLowerCase()}</option>`).join('')}
                    <option value="delete">Delete</option>
                </select>
            </div>
        </div>
        <div class="table-wrap" role="region" tabindex="0" aria-label="Booking records">
        <table class="bookings-table"><thead><tr>
            <th scope="col"><input type="checkbox" id="selectAllCheckbox" aria-label="Select bookings on this page"></th>
            <th scope="col">Guest and booking</th><th scope="col">Unit</th><th scope="col">Stay dates</th>
            <th scope="col">Status</th><th scope="col">Guest paid</th><th scope="col">Contribution</th><th scope="col">Actions</th>
        </tr></thead><tbody>${visible.map(booking => {
            const id = escapeHtml(booking.id);
            const status = escapeHtml(booking.status || 'Unspecified');
            const dates = [isoDay(booking.check_in), isoDay(booking.check_out)].filter(Boolean);
            const nights = stayNights(booking.check_in, booking.check_out);
            const { paid, contribution } = bookedAmounts(booking);
            return `<tr>
                <td><input type="checkbox" class="rowCheckbox" data-id="${id}" aria-label="Select booking ${id}"></td>
                <th scope="row">${escapeHtml(booking.guest_name || 'Unnamed guest')}<small>${id}</small></th>
                <td>${escapeHtml(unitName(booking.unit_name, booking.location) || 'N/A')}<small>${escapeHtml(bookingLocation(booking.unit_name, booking.location))}</small>
                    <small class="mobile-dates">${dates.join(' → ')}</small></td>
                <td>${dates.join(' → ') || '—'}<small>${nights ? `${number(nights)} nights` : ''}</small></td>
                <td><span class="badge badge-${statusOrder.get(booking.status) ?? 3}">${status}</span></td>
                <td>${money(paid)}</td>
                <td>${money(contribution)}</td>
                <td><button class="secondary editBtn" type="button" data-id="${id}" aria-label="Edit booking ${id}">Edit</button></td>
            </tr>`;
        }).join('')}</tbody></table></div>
        ${totalPages > 1 ? `<div class="pagination">
            <button id="previousPage" type="button" class="secondary" ${page === 0 ? 'disabled' : ''}>Previous</button>
            <span>Page ${page + 1} of ${totalPages}</span>
            <button id="nextPage" type="button" class="secondary" ${page === totalPages - 1 ? 'disabled' : ''}>Next</button>
        </div>` : ''}`;

    const all = container.querySelector('#selectAllCheckbox');
    const checkboxes = Array.from(container.querySelectorAll('.rowCheckbox'));
    const bulk = container.querySelector('#bulkAction');
    function updateSelection() {
        const checked = checkboxes.filter(box => box.checked).length;
        all.checked = checked === checkboxes.length;
        all.indeterminate = checked > 0 && !all.checked;
        bulk.disabled = checked === 0;
    }
    all.addEventListener('change', () => {
        checkboxes.forEach(box => { box.checked = all.checked; });
        updateSelection();
    });
    checkboxes.forEach(box => box.addEventListener('change', updateSelection));
    bulk.addEventListener('change', () => {
        const action = bulk.value;
        bulk.value = '';
        if (action === 'export') exportBookings(true);
        else if (action === 'delete') deleteSelectedBookings();
        else if (statusOptions.includes(action)) bulkUpdateStatus(action);
    });
    container.querySelectorAll('.editBtn').forEach(button => button.addEventListener('click', () => {
        editBooking(button.dataset.id);
    }));
    container.querySelector('#exportAllBtn').addEventListener('click', () => exportBookings(false));
    for (const [id, step] of [['nextPage', 1], ['previousPage', -1]]) {
        container.querySelector(`#${id}`)?.addEventListener('click', () => {
            page += step;
            renderBookingsTable();
            const target = container.querySelector(`#${id}:enabled`) || container.querySelector('.table-wrap');
            target.focus();
        });
    }
}

function nextBookingId() {
    const max = bookings.reduce((latest, { id }) => {
        const match = /^PS(\d+)$/.exec(id);
        return match ? Math.max(latest, Number(match[1])) : latest;
    }, 0);
    return `PS${String(max + 1).padStart(3, '0')}`;
}

function formValues(form) {
    return Object.fromEntries(fields.filter(field => form.elements[field]).map(field =>
        [field, form.elements[field].value.trim() || null]));
}

function standardizeUnitFields(patch, previous = null) {
    if (!Object.hasOwn(patch, 'unit_name') && !Object.hasOwn(patch, 'location')) return;
    const { unit_name, location } = { ...previous, ...patch };
    const confirmedLocation = bookingLocation(unit_name);
    if (patch.unit_name || confirmedLocation) patch.unit_name = unitName(unit_name, location);
    if (confirmedLocation) patch.location = confirmedLocation;
}

function showUnitLocation(form) {
    const name = form.elements.unit_name.value;
    const recorded = groupLabel(form.elements.location.value);
    const confirmed = bookingLocation(name);
    document.getElementById('unitLocationNotice').textContent = confirmed && recorded.toLowerCase() !== confirmed.toLowerCase()
        ? `Reports use ${confirmed} for ${unitName(name, recorded)}. Set the location to ${confirmed} to correct this booking.`
        : '';
}

function editBooking(id) {
    const booking = bookings.find(row => String(row.id) === id);
    if (booking) openModal(booking);
}

function openModal(booking = null) {
    const dialog = document.getElementById('modal');
    const form = document.getElementById('bookingForm');
    for (const field of ['status', 'gender']) {
        const select = form.elements[field];
        while (select.options.length > (field === 'status' ? 3 : 4)) select.remove(select.options.length - 1);
    }
    form.reset();
    form.dataset.id = booking?.id ?? '';
    document.getElementById('modalTitle').textContent = booking ? `Edit booking ${booking.id}` : 'New booking';
    const returning = document.getElementById('returningGuestSection');
    returning.hidden = Boolean(booking);
    returning.open = false;
    document.getElementById('returningGuestSearch').value = '';
    document.getElementById('bookingDetails').open = Boolean(booking && ['source', 'sub_source', 'host', 'notes']
        .some(key => booking[key]));
    document.getElementById('returningGuestResults').replaceChildren();
    document.getElementById('bookingError').textContent = '';
    for (const field of fields) {
        const input = form.elements[field];
        if (!input || !booking) continue;
        input.value = field.startsWith('check_') ? isoDay(booking[field]) : booking[field] ?? '';
        if (field === 'unit_name') input.value = unitName(booking.unit_name, booking.location);
        if (field === 'status' && !booking[field]) {
            input.add(new Option('Unspecified', '', false, true));
        } else if (['status', 'gender'].includes(field) && booking[field] && input.value !== booking[field]) {
            input.add(new Option(booking[field], booking[field], false, true));
        }
    }
    originalForm = formValues(form);
    updatePreview();
    showUnitLocation(form);
    dialog.showModal();
    form.elements.guest_name.focus();
}

function updatePreview() {
    const form = document.getElementById('bookingForm');
    const { check_in, check_out } = form.elements;
    const nights = stayNights(check_in.value, check_out.value);
    check_out.setCustomValidity(check_in.value && check_out.value && !nights ? 'Check-out must be after check-in.' : '');
    const amounts = Object.fromEntries(moneyFields.map(field => [field, form.elements[field].value]));
    const { contribution } = bookedAmounts(amounts);
    document.getElementById('stayPreview').textContent = nights === null ? '—' : `${number(nights)} ${nights === 1 ? 'night' : 'nights'}`;
    document.getElementById('contributionPreview').textContent = money(contribution);
}

async function saveBooking(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const id = form.dataset.id;
    const save = document.getElementById('modalSave');
    const message = document.getElementById('bookingError');
    if (save.disabled) return;
    message.textContent = '';
    const data = formValues(form);
    if (!data.guest_name) {
        message.textContent = 'Enter the guest’s name.';
        form.elements.guest_name.focus();
        return;
    }
    const original = bookings.find(row => String(row.id) === id);
    if (id && !original) {
        message.textContent = 'This booking is no longer in the loaded records. Close this form and refresh.';
        return;
    }
    if (data.status === 'Complete' && original?.status !== 'Complete' && (!data.unit_name || !stayNights(data.check_in, data.check_out))) {
        message.textContent = 'Enter a unit and both stay dates before marking this booking complete.';
        form.elements[data.unit_name ? 'check_in' : 'unit_name'].focus();
        return;
    }

    const changes = id
        ? Object.fromEntries(Object.entries(data).filter(([field, value]) => value !== originalForm[field]))
        : data;
    standardizeUnitFields(changes, original);
    if (!Object.keys(changes).length) {
        document.getElementById('modal').close();
        return;
    }
    const patch = bookingWrite(changes, original);
    const now = new Date().toISOString();
    patch.updated_at = now;
    save.disabled = document.getElementById('modalCancel').disabled = true;
    save.textContent = 'Saving…';
    try {
        const operation = id
            ? supabaseClient.from('bookings').update(patch).eq('id', id)
            : supabaseClient.from('bookings').insert([{ ...patch, id: nextBookingId(), created_at: now }]);
        const { data: saved, error } = await operation.select('id').single();
        if (error?.code === '23505' && !id) {
            await loadBookings();
            message.textContent = 'Another booking used this ID. Your entries are still here. Save again to use the next ID.';
            return;
        }
        if (error || !saved) throw new Error('No booking confirmed');
        document.getElementById('modal').close();
        await loadBookings();
        if (dataReady) {
            document.getElementById('bookingsStatus').textContent = `Booking ${saved.id} saved${data.status ? ` as ${data.status}` : ''}.`;
        }
    } catch {
        message.textContent = 'Could not save the booking. Your entries are still here. Check your connection or sign-in and try again.';
    } finally {
        save.disabled = document.getElementById('modalCancel').disabled = false;
        save.textContent = 'Save booking';
    }
}

async function deleteSelectedBookings() {
    const selected = Array.from(document.querySelectorAll('.rowCheckbox:checked')).map(cb => cb.dataset.id);
    if (selected.length === 0) { alert('No bookings selected.'); return; }
    if (!confirm(`Delete ${selected.length} booking(s) permanently?`)) return;
    const { error } = await supabaseClient.from('bookings').delete().in('id', selected);
    if (error) alert(`Delete failed: ${error.message}`);
    else loadBookings();
}

async function bulkUpdateStatus(newStatus) {
    const selected = Array.from(document.querySelectorAll('.rowCheckbox:checked')).map(cb => cb.dataset.id);
    if (selected.length === 0) { alert('No bookings selected.'); return; }
    if (!confirm(`Update ${selected.length} booking(s) to "${newStatus}"?`)) return;
    const { error } = await supabaseClient.from('bookings').update({ status: newStatus }).in('id', selected);
    if (error) alert(`Update failed: ${error.message}`);
    else loadBookings();
}

function exportBookings(onlySelected) {
    let dataToExport;
    if (onlySelected) {
        const selectedIds = Array.from(document.querySelectorAll('.rowCheckbox:checked')).map(cb => cb.dataset.id);
        if (selectedIds.length === 0) { alert('No bookings selected.'); return; }
        dataToExport = bookings.filter(b => selectedIds.includes(String(b.id)));
    } else {
        dataToExport = bookings;
    }
    if (dataToExport.length === 0) { alert('No bookings to export.'); return; }
    const headers = ['Booking ID','Guest Name','Gender','Phone Number','Unit Name','Location','Unit Type','Check-In','Check-Out','Nights','Guest Paid (KES)','Host Cost (KES)','Charges (KES)','Profit (KES)','Status','Source','Sub-Source','Month','Host','Notes'];
    const rows = dataToExport.map(booking => fields.map(col => {
        if (col === 'check_in' || col === 'check_out') return isoDay(booking[col]);
        if (['guest_paid', 'host_cost', 'charges', 'profit', 'nights'].includes(col)) {
            return booking[col] == null ? '' : Number(booking[col]);
        }
        return booking[col] ?? '';
    }));
    saveCsv([headers, ...rows], 'pwanistays-bookings');
}

// ----- CSV Import with comma stripping -----
async function importCSVWithProgress() {
    const input = document.createElement('input'); input.type = 'file'; input.accept = '.csv';
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const modalDiv = document.createElement('div');
        modalDiv.id = 'progressModal';
        modalDiv.className = 'progress-modal';
        modalDiv.innerHTML = `
            <div class="progress-card">
                <h3>Importing CSV...</h3>
                <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
                <p id="progressStatus">Parsing CSV...</p>
                <p id="progressDetail"></p>
            </div>
        `;
        document.body.appendChild(modalDiv);
        const progressFill = document.getElementById('progressFill');
        const progressStatus = document.getElementById('progressStatus');
        const progressDetail = document.getElementById('progressDetail');

        const results = await new Promise((resolve) => {
            Papa.parse(file, {
                header: true,
                skipEmptyLines: true,
                complete: resolve,
                error: (err) => resolve({ error: err })
            });
        });
        if (results.error) {
            modalDiv.remove();
            alert(`CSV parsing error: ${results.error.message}`);
            return;
        }
        const data = results.data;
        if (data.length === 0) { modalDiv.remove(); alert('CSV is empty.'); return; }
        const rawKeys = Object.keys(data[0]);
        const cleanKeys = rawKeys.map(k => k.replace(/^\uFEFF/, '').trim());
        const columnMap = {
            'Booking ID': 'id',
            'Guest Name': 'guest_name',
            'Gender': 'gender',
            'Phone Number': 'phone',
            'Unit Name': 'unit_name',
            'Location': 'location',
            'Unit Type': 'unit_type',
            'Check-In': 'check_in',
            'Check-Out': 'check_out',
            'Nights': 'nights',
            'Guest Paid (KES)': 'guest_paid',
            'Host Cost (KES)': 'host_cost',
            'Charges (KES)': 'charges',
            'Profit (KES)': 'profit',
            'Status': 'status',
            'Source': 'source',
            'Sub-Source': 'sub_source',
            'Sub Source': 'sub_source',
            'Subsource': 'sub_source',
            'Month': 'month',
            'Host': 'host',
            'Notes': 'notes'
        };
        const headerMap = rawKeys.flatMap((key, i) => Object.hasOwn(columnMap, cleanKeys[i])
            ? [[key, columnMap[cleanKeys[i]]]] : []);
        if (!cleanKeys.includes('Booking ID') || !cleanKeys.includes('Guest Name')) {
            modalDiv.remove();
            alert('CSV must contain "Booking ID" and "Guest Name" columns.');
            return;
        }
        let imported = 0, skipped = 0;
        let skippedRows = [];
        const totalRows = data.length;
        for (let idx = 0; idx < totalRows; idx++) {
            const row = data[idx];
            const dbRow = {};
            for (const [friendly, dbCol] of headerMap) {
                let val = row[friendly];
                if (val !== undefined && val !== null && val !== '') {
                    val = val.toString().trim();
                    if (moneyFields.includes(dbCol)) {
                        val = val.replace(/,/g, '');
                    }
                    if (dbCol === 'phone' && val.startsWith("'+")) val = val.slice(1);
                    dbRow[dbCol] = val || null;
                } else {
                    dbRow[dbCol] = null;
                }
            }
            if (!dbRow.id || !dbRow.guest_name || moneyFields.some(field => dbRow[field] != null && amount(dbRow[field]) === null)) {
                skipped++;
                skippedRows.push(idx + 2);
                continue;
            }
            if (dbRow.check_in) dbRow.check_in = dbRow.check_in.substring(0,10);
            if (dbRow.check_out) dbRow.check_out = dbRow.check_out.substring(0,10);
            const { id, ...input } = dbRow;
            const { data: existing, error: lookupError } = await supabaseClient.from('bookings')
                .select('guest_paid,host_cost,charges,check_in,check_out,unit_name,location').eq('id', id).maybeSingle();
            if (lookupError) {
                skipped++;
                skippedRows.push(idx + 2);
            } else if (existing) {
                standardizeUnitFields(input, existing);
                for (const field of [...moneyFields, 'check_in', 'check_out']) {
                    if (Object.hasOwn(input, field) && (input[field] == null
                        ? existing[field] == null : String(input[field]) === String(existing[field]))) delete input[field];
                }
                const { error } = await supabaseClient.from('bookings').update(bookingWrite(input, existing)).eq('id', id);
                if (!error) imported++;
                else { skipped++; skippedRows.push(idx+2); }
            } else {
                const now = new Date().toISOString();
                standardizeUnitFields(input);
                const { error } = await supabaseClient.from('bookings')
                    .insert([{ ...bookingWrite(input), id, created_at: now, updated_at: now }]);
                if (!error) imported++;
                else { skipped++; skippedRows.push(idx+2); }
            }
            const percent = Math.round(((idx+1)/totalRows)*100);
            progressFill.style.width = `${percent}%`;
            progressStatus.innerText = `Processing row ${idx+1} of ${totalRows}...`;
            progressDetail.innerText = `Imported: ${imported}, Skipped: ${skipped}`;
            await new Promise(r => setTimeout(r, 5));
        }
        modalDiv.remove();
        let msg = `Import completed: ${imported} imported/updated, ${skipped} skipped/errors.`;
        if (skippedRows.length) msg += `\nSkipped rows (approx): ${skippedRows.join(', ')}.`;
        alert(msg);
        loadBookings();
    };
    input.click();
}

function switchTab(tab) {
    activeTab = tab;
    for (const [name, button, panel] of [
        ['bookings', 'tabBookings', 'contentBookings'], ['analytics', 'tabAnalytics', 'contentAnalytics'],
    ]) {
        document.getElementById(button).setAttribute('aria-pressed', String(tab === name));
        document.getElementById(panel).hidden = tab !== name;
    }
    if (tab === 'analytics') drawReport();
}

const field = (label, control) => `<label class="field"><span>${label}</span>${control}</label>`;
const input = (id, label, attributes = '') => field(label, `<input id="${id}" name="${id}" ${attributes}>`);
const choice = (id, label, options) => field(label, `<select id="${id}" name="${id}">${options}</select>`);
const suggest = (id, label) => input(id, label, `list="${id}_options" autocomplete="off"`);
const cost = (id, label) => input(id, label, 'type="number" step="0.01" inputmode="decimal"');

const bookingDialog = `
    <dialog id="modal" aria-labelledby="modalTitle">
        <div class="dialog-heading">
            <h2 id="modalTitle">New booking</h2>
            <button id="modalCancel" type="button" class="secondary">Cancel</button>
        </div>
        <div class="dialog-body">
            <details id="returningGuestSection" class="returning">
                <summary>Look up a returning guest</summary>
                ${input('returningGuestSearch', 'Name or phone', 'type="search" autocomplete="off"')}
                <div id="returningGuestResults" class="guest-results"></div>
            </details>
            <form id="bookingForm">
                <fieldset>
                    <legend>Guest</legend>
                    <div class="form-grid">
                        ${input('guest_name', 'Full name <span class="required">*</span>', 'required autocomplete="off"')}
                        ${input('phone', 'Phone', 'type="tel" autocomplete="off"')}
                        ${choice('gender', 'Gender (optional)', '<option value="">Optional</option><option>Male</option><option>Female</option><option>Prefer not to say</option>')}
                    </div>
                </fieldset>
                <fieldset>
                    <legend>Stay</legend>
                    <div class="form-grid">
                        ${suggest('unit_name', 'Apartment or unit')}
                        ${suggest('location', 'Location')}
                        ${suggest('unit_type', 'Unit type')}
                        ${input('check_in', 'Check-in', 'type="date"')}
                        ${input('check_out', 'Check-out', 'type="date"')}
                        ${choice('status', 'Status', '<option>Pending</option><option>In Progress</option><option>Complete</option>')}
                    </div>
                    <p class="field-help">Use N/A when the unit name is unavailable.</p>
                    <p id="unitLocationNotice" class="field-help"></p>
                </fieldset>
                <fieldset>
                    <legend>Booking amounts (KES)</legend>
                    <p class="field-help">Blank host costs and direct charges count as zero. Enter the guest payment to calculate contribution.</p>
                    <div class="form-grid">
                        ${cost('guest_paid', 'Guest paid')}
                        ${cost('host_cost', 'Host cost')}
                        ${cost('charges', 'Direct charges')}
                    </div>
                </fieldset>
                <details id="bookingDetails" class="booking-details">
                    <summary>Source, host and notes</summary>
                    <div class="form-grid">
                        ${suggest('source', 'Booking source')}
                        ${suggest('sub_source', 'Sub-source')}
                        ${suggest('host', 'Host')}
                        <label class="field wide"><span>Notes</span><textarea id="notes" name="notes" rows="3"></textarea></label>
                    </div>
                </details>
                ${fieldOptions.map(id => `<datalist id="${id}_options"></datalist>`).join('')}
            </form>
        </div>
        <div class="dialog-footer">
            <div class="entry-preview">
                <span>Stay <output id="stayPreview" for="check_in check_out">—</output></span>
                <span>Contribution <output id="contributionPreview" for="guest_paid host_cost charges">—</output></span>
            </div>
            <button id="modalSave" type="submit" form="bookingForm">Save booking</button>
            <p id="bookingError" class="error" role="alert"></p>
        </div>
    </dialog>`;

const reportPanel = `
    <div class="section-heading">
        <div><h2>Booking performance</h2><p>Compare completed stays by check-in date, unit and booking source.</p></div>
        <button type="button" id="exportReport" class="secondary" disabled>Export summary CSV</button>
    </div>
    <form id="reportFilters" class="filter-bar">
        ${input('from', 'Check-in from', 'type="date"')}
        ${input('through', 'Check-in through', 'type="date"')}
        ${choice('dimension', 'Group by', '<option value="units">Unit</option><option value="months">Check-in month</option><option value="sources">Booking source</option><option value="locations">Location</option><option value="unitTypes">Unit type</option><option value="guestTypes">Sub-source</option>')}
        ${choice('sort', 'Sort groups by', '<option value="default">Default order</option><option value="contribution">Contribution</option><option value="nightly">Contribution per night</option>')}
        <button type="button" id="clearReportDates" class="secondary">All dates</button>
    </form>
    <div id="reportOutput"></div>
    <details id="unitLocationReviewPanel" class="report-notes" hidden>
        <summary>Review unit locations (all dates)</summary>
        <div id="unitLocationReview"></div>
    </details>
    <section class="calculator" aria-labelledby="furnishingTitle">
        <h2 id="furnishingTitle">Furnishing calculator</h2>
        <p>Estimate how long a unit would take to repay furnishing costs. Enter a typical month for the proposed operating model.</p>
        <form id="furnishingForm">
            <div class="evidence">
                ${choice('unit', 'Unit history (optional)', '<option value="">Select a unit</option>')}
                <p id="furnishingEvidence" role="status"></p>
            </div>
            <div class="form-grid">
                ${input('budget', 'Furnishing spend (KES)', 'type="number" required min="0.01" step="0.01" inputmode="decimal"')}
                ${input('days', 'Nights available per month', 'type="number" required min="1" max="31" step="1" inputmode="numeric"')}
                ${input('occupancy', 'Expected occupancy (%)', 'type="number" required min="0" max="100" step="0.01" inputmode="decimal"')}
                ${input('nightly', 'Contribution per occupied night (KES)', 'type="number" required step="0.01" inputmode="decimal" aria-describedby="nightlyHelp"')}
                ${input('fixed', 'Monthly fixed costs (KES)', 'type="number" required min="0" step="0.01" inputmode="decimal"')}
            </div>
            <p id="nightlyHelp" class="field-help">For contribution per occupied night, enter the expected guest rate less variable costs such as platform fees, cleaning and any host payout. Include rent or other recurring costs in monthly fixed costs. Results are before tax and financing and use the same assumptions each month.</p>
            <button type="submit">Calculate</button>
        </form>
        <div id="furnishingResult" role="status"></div>
    </section>`;

function setupBookingForm() {
    const dialog = document.getElementById('modal');
    const form = document.getElementById('bookingForm');
    document.getElementById('modalCancel').addEventListener('click', () => dialog.close());
    dialog.addEventListener('cancel', event => {
        if (document.getElementById('modalSave').disabled) event.preventDefault();
    });
    form.addEventListener('submit', saveBooking);
    form.addEventListener('input', updatePreview);
    form.elements.unit_name.addEventListener('input', () => showUnitLocation(form));
    form.elements.location.addEventListener('input', () => showUnitLocation(form));
    form.elements.unit_name.addEventListener('change', () => {
        const normalize = value => groupLabel(value).toLowerCase();
        const name = form.elements.unit_name.value;
        if (!name) return;
        const canonical = unitName(name, form.elements.location.value);
        if (canonical === 'N/A') {
            form.elements.unit_name.value = canonical;
            showUnitLocation(form);
            return;
        }
        const confirmed = bookingLocation(name);
        if (confirmed) form.elements.location.value = confirmed;
        const matches = bookings.filter(booking =>
            unitName(booking.unit_name, booking.location).toLowerCase() === unitName(name, booking.location).toLowerCase() &&
            (!form.elements.location.value || normalize(bookingLocation(booking.unit_name, booking.location)) === normalize(form.elements.location.value)));
        for (const property of ['location', 'unit_type', 'host']) {
            const known = new Set(matches.map(booking => booking[property]?.trim()).filter(Boolean));
            if (!form.elements[property].value && known.size === 1) {
                form.elements[property].value = known.values().next().value;
            }
        }
        form.elements.unit_name.value = unitName(name, form.elements.location.value);
        showUnitLocation(form);
    });

    const lookup = document.getElementById('returningGuestSearch');
    const results = document.getElementById('returningGuestResults');
    lookup.addEventListener('input', () => {
        const query = lookup.value.trim().toLowerCase();
        results.replaceChildren();
        if (query.length < 2) return;
        const seen = new Set();
        for (const booking of bookings) {
            const name = booking.guest_name || '';
            const phone = booking.phone || '';
            const key = phone.trim() || name.trim().toLowerCase();
            if (!key || seen.has(key)) continue;
            seen.add(key);
            if (!name.toLowerCase().includes(query) && !phone.includes(query)) continue;
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'secondary guest-result';
            button.textContent = [name, phone].filter(Boolean).join(' · ');
            button.addEventListener('click', () => {
                form.elements.guest_name.value = name;
                form.elements.phone.value = phone;
                form.elements.gender.value = booking.gender || '';
                form.elements.sub_source.value = 'Returning';
                results.replaceChildren();
                lookup.value = '';
                document.getElementById('returningGuestSection').open = false;
                form.elements.guest_name.focus();
            });
            results.append(button);
            if (results.childElementCount >= 8) break;
        }
        if (!results.childElementCount) results.textContent = 'No matching guest.';
    });
}

async function renderApp() {
    const app = document.getElementById('app');
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) {
        ++loadRequest;
        bookings = [];
        unitName = unitNameResolver(bookings);
        dataReady = false;
        app.innerHTML = `
            <section class="sign-in">
                <img src="/logo-header.png" alt="PwaniStays" class="brand">
                <h1>Booking Manager</h1>
                <p>Sign in to manage your bookings.</p>
                <form id="loginForm">
                    ${input('email', 'Email', 'type="email" autocomplete="username" required')}
                    ${input('password', 'Password', 'type="password" autocomplete="current-password" required')}
                    <p id="loginError" class="error" role="alert"></p>
                    <button type="submit">Sign in</button>
                </form>
            </section>`;
        document.getElementById('loginForm').addEventListener('submit', async event => {
            event.preventDefault();
            const form = event.currentTarget;
            const button = form.querySelector('button');
            const errorText = document.getElementById('loginError');
            button.disabled = true;
            errorText.textContent = '';
            try {
                const { error } = await supabaseClient.auth.signInWithPassword({
                    email: form.elements.email.value,
                    password: form.elements.password.value,
                });
                if (error) {
                    errorText.textContent = error.message;
                } else {
                    await renderApp();
                }
            } catch {
                errorText.textContent = 'Could not reach the sign-in service. Try again.';
            } finally {
                button.disabled = false;
            }
        });
        return;
    }
    filterText = filteredStatus = '';
    page = 0;
    activeTab = 'bookings';
    app.innerHTML = `
        <div class="workspace">
            <header class="masthead">
                <img src="/logo-header.png" alt="PwaniStays" class="brand">
                <button type="button" id="logoutBtn" class="secondary">Sign out</button>
            </header>
            <div class="workspace-intro">
                <h1>Booking Manager</h1>
                <p>Manage stays, track booking performance and plan furnishing investments.</p>
            </div>
            <nav class="tab-bar" aria-label="Booking workspace">
                <button type="button" id="tabBookings" aria-controls="contentBookings" aria-pressed="true">Bookings</button>
                <button type="button" id="tabAnalytics" aria-controls="contentAnalytics" aria-pressed="false">Performance</button>
            </nav>
            <section id="contentBookings" class="panel" aria-labelledby="bookingsTitle">
                <div class="section-heading">
                    <div><h2 id="bookingsTitle">Booking records</h2><p>Search, update and import your stays.</p></div>
                    <div class="inline-actions">
                        <button type="button" id="refreshBtn" class="secondary">Refresh</button>
                        <button type="button" id="importBtn" class="secondary" disabled>Import CSV</button>
                        <button type="button" id="addBtn" disabled>New booking</button>
                    </div>
                </div>
                <div class="filter-bar">
                    ${input('searchInput', 'Search bookings', 'type="search" placeholder="Guest, phone, unit or booking ID"')}
                    ${choice('statusFilter', 'Status or review', '<option value="">All statuses</option><option>Pending</option><option>In Progress</option><option>Complete</option><option value="needs-review">Completed · missing data</option>')}
                </div>
                <p id="bookingsStatus" role="status"></p>
                <div id="bookingsContainer"></div>
            </section>
            <section id="contentAnalytics" class="panel" aria-label="Booking performance" hidden>${reportPanel}</section>
        </div>
        ${bookingDialog}`;
    drawReport = setupReport(document.getElementById('contentAnalytics'), () => dataReady ? bookings : null, editBooking);
    document.getElementById('tabBookings').addEventListener('click', () => switchTab('bookings'));
    document.getElementById('tabAnalytics').addEventListener('click', () => switchTab('analytics'));
    document.getElementById('addBtn').addEventListener('click', () => openModal());
    document.getElementById('importBtn').addEventListener('click', importCSVWithProgress);
    document.getElementById('refreshBtn').addEventListener('click', loadBookings);
    document.getElementById('logoutBtn').addEventListener('click', async () => {
        const { error } = await supabaseClient.auth.signOut();
        if (error) alert('Could not sign out. Try again.');
        else renderApp();
    });
    document.getElementById('searchInput').addEventListener('input', event => {
        filterText = event.target.value.trim().toLowerCase();
        page = 0;
        renderBookingsTable();
    });
    document.getElementById('statusFilter').addEventListener('change', event => {
        filteredStatus = event.target.value;
        page = 0;
        renderBookingsTable();
    });
    setupBookingForm();
    await loadBookings();
}

renderApp().catch(() => {
    document.getElementById('app').innerHTML = '<p class="loading" role="alert">Booking Manager could not load. Refresh to try again.</p>';
});
