# Reminder-type Custom Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `reminder` custom-field type that behaves identically to
`date` in every rendering/storage/formatting respect, plus an on-demand
(never-polling) check that surfaces any due/overdue reminder-type field
value across the library, with a per-row snooze so acknowledged reminders
don't keep resurfacing.

**Architecture:** A fifth `fields.type` value (`'reminder'`, alongside
`text`/`number`/`date`/`checkbox`/`person`) reuses `date`'s existing
render/format code paths verbatim. A new `reminder_snoozes` table tracks
per-(document, field) snooze state. A pure, synchronous `checkReminders()`
function scans already-loaded in-memory data (`allDocs`, `fieldDefs`,
`reminderSnoozes`) — no filesystem or network I/O — triggered only by
library-open and a new toolbar button, surfacing results in a new modal.

**Tech Stack:** Vanilla JS inside `dossiary.html` (no build step); Python +
Playwright for the test suite (`tests/test_reminders.py`, new file).

## Global Constraints

- New field type name is exactly `'reminder'`, added to the existing
  `text`/`number`/`date`/`checkbox`/`person` set — never a flag on `date`.
- A `reminder`-type field renders/stores/formats **identically** to
  `date` in every place that already branches on `field.type === 'date'`.
- New `settings` row `reminder_lookahead_days` (text-stored integer),
  default `30` when unset (never absent-means-off).
- New table `reminder_snoozes (document_id INTEGER, field_id INTEGER,
  snoozed_until TEXT, PRIMARY KEY (document_id, field_id))`.
- The check (`checkReminders()`) never touches the filesystem or network —
  a pure scan over data already loaded into memory.
- Two trigger points only, both explicit: once automatically right after a
  library finishes opening (silent if nothing is due), and a new "🔔 Check
  reminders" toolbar button (reports "No reminders due." if nothing is
  due). No live/persistent badge, no polling, no push notification.
- A reminder is due when its date is `<= today + reminder_lookahead_days`
  **and** the document is not archived and not deleted **and** there is
  no active (`snoozed_until` in the future) snooze for that exact
  `(document_id, field_id)` pair.
- Snooze choices: 1 week, 1 month (30 days), 3 months (90 days), or a
  custom date — writing `reminder_snoozes.snoozed_until`, never touching
  the reminder's own underlying field value.
- Every new user-facing string needs a key in all six `STRINGS` blocks
  (`en`/`es`/`fr`/`de`/`zh-Hans`/`zh-Hant`) — `tests/test_i18n_coverage.py`
  fails the whole suite if any language is missing a key. `zh-Hant`
  entries are hand-converted from the finished `zh-Hans` wording to
  traditional characters, per this repo's established convention (never
  translated independently a second time).

---

### Task 1: The `reminder` field type — render, format, create

**Files:**
- Modify: `dossiary.html:3595-3602` (`renderGenericFieldHtml()`'s input-type/value logic), `dossiary.html:4131` (`formatCustomFieldValue()`), `dossiary.html:5228-5234` (edit form's `#e-new-field-type`), `dossiary.html:5861-5867` (capture form's `#f-new-field-type`), all six `STRINGS` blocks (new `captureAddFieldTypeReminder` key, next to each block's existing `captureAddFieldTypePerson`)
- Test: `tests/test_reminders.py` (new file)

**Interfaces:**
- Produces: the string literal `'reminder'` as a valid `fields.type`
  value, understood identically to `'date'` by `renderGenericFieldHtml()`
  and `formatCustomFieldValue()`. Later tasks (3, 4) rely on
  `fieldDefs` entries having `type === 'reminder'` to identify reminder
  sources.

Read `dossiary.html` yourself before editing — line numbers above are
from the plan's own research pass and may have drifted slightly; find
each exact site by searching for the function/string names given.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reminders.py`. This first scenario creates a
`reminder`-type field inline (mirroring how `test_person_type_field.py`
creates a new "Author" field) and confirms it behaves exactly like a
`date`-type field: same `<input type="date">`, same value round-trip,
same display formatting.

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [
        {
            "id": 1, "title": "Insurance Policy", "category": "Finance", "document_type": "Policy",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [], "settings": [],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)

        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)

        # === Scenario 1: creating a 'reminder'-type field inline behaves
        # identically to 'date' in every respect except the type stored ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.click('#e-add-field-toggle')
        await page.wait_for_timeout(100)
        await page.fill('#e-new-field-name', 'Renewal Date')
        reminder_option_present = await page.locator('#e-new-field-type option[value="reminder"]').count()
        print("Reminder option present in the type dropdown:", reminder_option_present == 1)
        await page.select_option('#e-new-field-type', 'reminder')
        await page.click('#e-new-field-btn')
        await page.wait_for_timeout(100)

        input_type = await page.get_attribute('#e-field-1', 'type')
        print("new reminder field renders as a native date input:", input_type == 'date')
        await page.fill('#e-field-1', '2026-03-15')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        field_row = next((f for f in persisted['fields'] if f['name'] == 'Renewal Date'), None)
        print("field persisted with type 'reminder':", field_row['type'] if field_row else None)
        value_row = next((v for v in persisted['document_field_values'] if v['field_id'] == field_row['id']), None)
        print("value persisted as a plain ISO date string:", value_row['value'] if value_row else None)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        displayed = await page.locator('.modal-meta', has_text='Renewal Date').inner_text()
        print("detail panel shows the reminder field's value like any date field:", '2026' in displayed)

        # No Autocomplete checkbox, matching 'date' -- but the Column checkbox IS
        # offered (capabilitiesHtml()'s guard is exclusion-based: person + Amount
        # only, so 'reminder' gets it automatically like every other non-excluded type).
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.click('.fs-list-item:has-text("Policy")')
        await page.wait_for_timeout(150)
        reminder_item = page.locator('#fs-available-list .fs-field-item[data-field="Renewal Date"], #fs-display-list .fs-field-item[data-field="Renewal Date"]').first
        column_checkbox_present = await reminder_item.locator('.fs-col-toggle').count()
        autocomplete_checkbox_present = await reminder_item.locator('.fs-autocomplete-toggle').count()
        print("Column checkbox offered for a reminder field:", column_checkbox_present == 1)
        print("Autocomplete checkbox NOT offered for a reminder field:", autocomplete_checkbox_present == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: fails at `reminder_option_present` (prints `False`) or a later
line, since no `reminder` option exists in the type dropdown yet.

- [ ] **Step 3: Implement**

In `dossiary.html`, inside `renderGenericFieldHtml()`, find:

```js
    let inputType = 'text', extra = '';
    if(field.type === 'number'){ inputType = 'number'; extra = 'step="any"'; }
    else if(field.type === 'date'){ inputType = 'date'; }
```

Change to:

```js
    let inputType = 'text', extra = '';
    if(field.type === 'number'){ inputType = 'number'; extra = 'step="any"'; }
    else if(field.type === 'date' || field.type === 'reminder'){ inputType = 'date'; }
```

A few lines below, find:

```js
    let value = field.type === 'date' ? (existingValue ? existingValue.slice(0, 10) : '') : (existingValue || '');
```

Change to:

```js
    let value = (field.type === 'date' || field.type === 'reminder') ? (existingValue ? existingValue.slice(0, 10) : '') : (existingValue || '');
```

In `formatCustomFieldValue()`, find:

```js
    if(def.type === 'date') return formatDate(rawValue);
```

Change to:

```js
    if(def.type === 'date' || def.type === 'reminder') return formatDate(rawValue);
```

In `addInlineCustomField()`'s markup (the edit form's type-select block,
search for `id="e-new-field-type"`), find:

```html
              <select id="e-new-field-type">
                <option value="text">${t('captureAddFieldTypeText')}</option>
                <option value="number">${t('captureAddFieldTypeNumber')}</option>
                <option value="date">${t('captureAddFieldTypeDate')}</option>
                <option value="checkbox">${t('captureAddFieldTypeCheckbox')}</option>
                <option value="person">${t('captureAddFieldTypePerson')}</option>
              </select>
```

Change to:

```html
              <select id="e-new-field-type">
                <option value="text">${t('captureAddFieldTypeText')}</option>
                <option value="number">${t('captureAddFieldTypeNumber')}</option>
                <option value="date">${t('captureAddFieldTypeDate')}</option>
                <option value="checkbox">${t('captureAddFieldTypeCheckbox')}</option>
                <option value="person">${t('captureAddFieldTypePerson')}</option>
                <option value="reminder">${t('captureAddFieldTypeReminder')}</option>
              </select>
```

Apply the identical change to the capture form's block (search for
`id="f-new-field-type"` — same five existing `<option>`s, same new sixth
one added the same way).

Note: `addInlineCustomField()`'s own `const autocomplete = type === 'text' ? 1 : 0;`
line needs no change — `'reminder'` already falls into the `0` branch,
matching `'date'`/`'checkbox'`/`'person'`. `capabilitiesHtml()` (Field
Settings) also needs no change — its guard,
`if(!fieldDef || fieldDef.type === 'person' || fieldName === 'Amount') return '';`,
is an exclusion list, so a new `'reminder'` type automatically gets the
Column checkbox, and the Autocomplete checkbox's own
`fieldDef.type === 'text'` guard already excludes it. `populateFilters()`'s
filter-dropdown gate (`type === 'text' || type === 'checkbox'`) also
needs no change — `'reminder'` is excluded there for free, same as
`'date'`.

Now add the new i18n key to all six `STRINGS` blocks. In each block, find
the line containing `captureAddFieldTypePerson:` (all six read exactly
`captureAddFieldTypePerson: '<translation>',` followed by more keys on
the same or next line) and add `captureAddFieldTypeReminder:
'<translation>'` immediately after it, on the same line, matching each
block's existing dense formatting style:

- `en`: `captureAddFieldTypeReminder: 'Reminder',`
- `es`: `captureAddFieldTypeReminder: 'Recordatorio',`
- `fr`: `captureAddFieldTypeReminder: 'Rappel',`
- `de`: `captureAddFieldTypeReminder: 'Erinnerung',`
- `zh-Hans`: `captureAddFieldTypeReminder: '提醒',`
- `zh-Hant`: `captureAddFieldTypeReminder: '提醒',` (identical characters
  in both scripts — 提 and 醒 have no distinct traditional forms)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: every line prints `True` (or the persisted values described),
`JS ERRORS: []`.

- [ ] **Step 5: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `PASS`, confirming the new key exists in all six languages with
no key-count mismatch.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Add the 'reminder' custom-field type

Renders/stores/formats identically to 'date' -- the only difference is
the type value itself, which later tasks use to identify reminder
sources. No changes needed to capabilitiesHtml() or populateFilters();
both already generalize correctly via their existing exclusion-based
guards."
```

---

### Task 2: `reminder_lookahead_days` setting

**Files:**
- Modify: `dossiary.html` (new module-level `reminderLookaheadDays` var
  near `defaultCurrency`'s own declaration, `loadReminderLookaheadDays()`/
  `saveReminderLookaheadDays()` functions near `loadDefaultCurrency()`/
  `saveDefaultCurrency()`, the call site inside `loadDocumentsFromDb()`
  near its existing `loadDefaultCurrency();` call, `resetAll()`'s reset
  block, `openFieldSettingsModal()`'s markup/wiring), all six `STRINGS`
  blocks (new `fieldSettingsReminderLookaheadLabel` key)
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Produces: module-level `let reminderLookaheadDays` (number, default
  `30`), read by Task 4's `checkReminders()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reminders.py`, right before the final
`print("JS ERRORS:", errors)` / `await browser.close()` lines:

```python
        # === Scenario 2: reminder_lookahead_days defaults to 30 when unset,
        # persists an explicit value, and survives a reopen ===
        lookahead_default = await page.evaluate("document.getElementById('fs-reminder-lookahead').value")
        print("reminder lookahead defaults to 30 with no persisted setting:", lookahead_default)  # set below, after opening Field Settings again

        await page.fill('#fs-reminder-lookahead', '14')
        await page.dispatch_event('#fs-reminder-lookahead', 'change')
        await page.wait_for_timeout(200)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        lookahead_row = next((s for s in persisted2['settings'] if s['key'] == 'reminder_lookahead_days'), None)
        print("reminder_lookahead_days persisted as '14':", lookahead_row['value'] if lookahead_row else None)

        # Reopen (same convention test_nav.py/test_recent_libraries.py use: re-seed
        # a fresh root with the setting already present, simulating a real reopen
        # reading the same on-disk library.sqlite back)
        seed_with_lookahead = dict(SEED)
        seed_with_lookahead['settings'] = [{'key': 'reminder_lookahead_days', 'value': '14'}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_lookahead)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        lookahead_after_reopen = await page.evaluate("document.getElementById('fs-reminder-lookahead').value")
        print("reminder_lookahead_days reads back as '14' after reopening:", lookahead_after_reopen)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)
```

Move the pre-existing final `print("JS ERRORS:", errors)` /
`await browser.close()` to after this new block (there should be exactly
one such pair, at the true end of `main()`).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: fails at `lookahead_default` — `#fs-reminder-lookahead` doesn't
exist yet.

- [ ] **Step 3: Implement**

In `dossiary.html`, find the module-level declaration:

```js
  let defaultCurrency = null;     // prefills Currency (as a dismissible guess) on new captures; unset means no guess
```

Add immediately after it:

```js
  let reminderLookaheadDays = 30; // how many days ahead a reminder-type field value counts as "coming up soon"; see checkReminders()
```

Find `loadDefaultCurrency()`/`saveDefaultCurrency()`:

```js
  function loadDefaultCurrency(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'default_currency'").rows;
    defaultCurrency = rows.length ? rows[0][0] : null;
  }

  async function saveDefaultCurrency(value){
    defaultCurrency = value.trim() || null;
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_currency', ?)", [defaultCurrency || '']);
    await persistDb();
  }
```

Add immediately after:

```js
  function loadReminderLookaheadDays(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'reminder_lookahead_days'").rows;
    const parsed = rows.length ? parseInt(rows[0][0], 10) : NaN;
    reminderLookaheadDays = (Number.isFinite(parsed) && parsed >= 0) ? parsed : 30;
  }

  async function saveReminderLookaheadDays(value){
    const parsed = parseInt(value, 10);
    reminderLookaheadDays = (Number.isFinite(parsed) && parsed >= 0) ? parsed : 30;
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('reminder_lookahead_days', ?)", [String(reminderLookaheadDays)]);
    await persistDb();
  }
```

In `loadDocumentsFromDb()`, find:

```js
    loadDefaultCurrency();
```

Change to:

```js
    loadDefaultCurrency();
    loadReminderLookaheadDays();
```

In `resetAll()`, find:

```js
    defaultDocumentType = null; defaultCurrency = null; fsSelectedType = null;
```

Change to:

```js
    defaultDocumentType = null; defaultCurrency = null; fsSelectedType = null; reminderLookaheadDays = 30;
```

In `openFieldSettingsModal()`'s markup, find:

```html
            <div class="field">
              <label for="fs-default-currency">${t('fieldSettingsDefaultCurrencyLabel')}</label>
              <input type="text" id="fs-default-currency" list="currency-list" value="${escapeHtml(defaultCurrency || '')}" placeholder="${t('commonNone')}" />
            </div>
          </div>
```

Change to:

```html
            <div class="field">
              <label for="fs-default-currency">${t('fieldSettingsDefaultCurrencyLabel')}</label>
              <input type="text" id="fs-default-currency" list="currency-list" value="${escapeHtml(defaultCurrency || '')}" placeholder="${t('commonNone')}" />
            </div>
            <div class="field">
              <label for="fs-reminder-lookahead">${t('fieldSettingsReminderLookaheadLabel')}</label>
              <input type="number" id="fs-reminder-lookahead" min="0" step="1" value="${reminderLookaheadDays}" />
            </div>
          </div>
```

And find:

```js
    el('fs-default-currency').addEventListener('change', (e) => saveDefaultCurrency(e.target.value));
```

Change to:

```js
    el('fs-default-currency').addEventListener('change', (e) => saveDefaultCurrency(e.target.value));
    el('fs-reminder-lookahead').addEventListener('change', (e) => saveReminderLookaheadDays(e.target.value));
```

Add the new i18n key to all six `STRINGS` blocks, next to each block's
own `fieldSettingsDefaultCurrencyLabel:` line:

- `en`: `fieldSettingsReminderLookaheadLabel: 'Reminder lookahead (days)',`
- `es`: `fieldSettingsReminderLookaheadLabel: 'Antelación de recordatorios (días)',`
- `fr`: `fieldSettingsReminderLookaheadLabel: 'Anticipation des rappels (jours)',`
- `de`: `fieldSettingsReminderLookaheadLabel: 'Erinnerungsvorlauf (Tage)',`
- `zh-Hans`: `fieldSettingsReminderLookaheadLabel: '提醒提前天数',`
- `zh-Hant`: `fieldSettingsReminderLookaheadLabel: '提醒提前天數',`
  (数→數 is the one character that changes between the two scripts here —
  confirmed against this file's own existing
  `captureAddFieldNamePlaceholder: '字段名称'` (`zh-Hans`, line ~1563) vs.
  `captureAddFieldNamePlaceholder: '字段名稱'` (`zh-Hant`, line ~1808) pair,
  which uses the identical 数/數 substitution)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: all lines from Task 1 and the new Scenario 2 print `True`/the
expected persisted values, `JS ERRORS: []`.

- [ ] **Step 5: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `PASS`.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Add the reminder_lookahead_days setting

Same settings-table load/save pattern as default_currency, wired into
Field Settings alongside it. Defaults to 30 when unset so reminders
surface sensibly without requiring configuration first."
```

---

### Task 3: `reminder_snoozes` table

**Files:**
- Modify: `dossiary.html:2055-2097` (`SCHEMA`), new module-level
  `reminderSnoozes` var + `loadReminderSnoozes()` near `loadCollections()`,
  its call site in `loadDocumentsFromDb()`, `resetAll()`'s reset block
- Modify: `tests/stub_studio2.js` (register the new table in both table
  lists, add compound-key `INSERT OR REPLACE` dedupe handling)
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Produces: module-level `let reminderSnoozes` (object, keyed by
  `` `${documentId}:${fieldId}` ``, value is the `snoozed_until` ISO date
  string), read by Task 4's `checkReminders()` and written by Task 5's
  `snoozeReminder()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reminders.py`, before the final
`print("JS ERRORS:", errors)`/`await browser.close()`:

```python
        # === Scenario 3: reminder_snoozes rows load correctly into memory,
        # and a real INSERT OR REPLACE against the compound (document_id,
        # field_id) key replaces an existing row rather than duplicating it ===
        seed_with_snooze = dict(SEED)
        seed_with_snooze['reminder_snoozes'] = [
            {'document_id': 1, 'field_id': 1, 'snoozed_until': '2026-06-01'},
        ]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_snooze)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        # window.__DEBUG_reminderSnoozes is a small test-only hook loadReminderSnoozes()
        # sets at the end of its own body (see Step 3 below) -- the simplest way to
        # assert on this module-private variable from outside the page's own closure.
        loaded_snooze = await page.evaluate("window.__DEBUG_reminderSnoozes ? window.__DEBUG_reminderSnoozes['1:1'] : undefined")
        print("seeded snooze row loads into memory:", loaded_snooze)

        # Directly exercise the real INSERT OR REPLACE path the app itself uses,
        # confirming the stub correctly replaces (not duplicates) on the same
        # compound key -- this is the one thing this table needed new stub support
        # for, since every prior INSERT OR REPLACE dedupe in this stub has been a
        # single-column key (settings.key, field_descriptions.field_name).
        replaced_value = await page.evaluate("""
            () => {
                db.run('INSERT OR REPLACE INTO reminder_snoozes (document_id, field_id, snoozed_until) VALUES (?, ?, ?)', [1, 1, '2026-07-15']);
                loadReminderSnoozes(); // re-read from the table, same as a real reopen would
                return window.__DEBUG_reminderSnoozes['1:1'];
            }
        """)
        print("after a second INSERT OR REPLACE on the same (document_id, field_id), the row's snoozed_until is the NEW value:", replaced_value == '2026-07-15')
```

Note: `window.__DEBUG_reminderSnoozes` is a small dev/test-only debug
hook (matching no existing convention exactly, but harmless and the
simplest way to assert on this module-private variable from outside the
page's own closure) — Step 3 below defines it, at the end of
`loadReminderSnoozes()`. An alternative is reading `library.sqlite`'s
persisted JSON the same way other scenarios do, which also works and
avoids a new debug global; use whichever this task's implementer finds
cleaner, but keep the assertion's actual meaning — snoozes load correctly
into memory, keyed by `"docId:fieldId"` — intact either way.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: fails — `reminder_snoozes` isn't a registered table in the stub
yet, so seeding it either silently does nothing or the `INSERT OR REPLACE`
call throws `unhandled SQL` (no `fields`/`table` match).

- [ ] **Step 3: Implement the app-side schema and loading**

In `dossiary.html`, inside the `SCHEMA` template string, find:

```
    CREATE TABLE IF NOT EXISTS field_descriptions (
      field_name TEXT PRIMARY KEY, description TEXT
    );
  `;
```

Change to:

```
    CREATE TABLE IF NOT EXISTS field_descriptions (
      field_name TEXT PRIMARY KEY, description TEXT
    );
    CREATE TABLE IF NOT EXISTS reminder_snoozes (
      document_id INTEGER, field_id INTEGER, snoozed_until TEXT,
      PRIMARY KEY (document_id, field_id)
    );
  `;
```

(No `SCHEMA_MIGRATIONS` entry is needed — that array is exclusively for
`ALTER TABLE ... ADD COLUMN` on tables that already exist; a brand new
table only needs adding to `SCHEMA` itself, since `CREATE TABLE IF NOT
EXISTS` is already a safe no-op for a library that already has it and
correctly creates it for one that doesn't. `collections`, `collection_documents`,
and `field_descriptions` were all added to this codebase the same way,
with no corresponding `SCHEMA_MIGRATIONS` entries.)

Find the module-level declaration block containing `let collections = [];`:

```js
  let collections = [];        // [{id, name, kind, criteria}, ...] from the `collections` table
```

Add a new declaration nearby (anywhere in that same block of `let`
declarations is fine):

```js
  let reminderSnoozes = {};    // { "<documentId>:<fieldId>": "<snoozed_until ISO date>", ... }
```

Find `loadCollections()`:

```js
  function loadCollections(){
    const { rows } = queryAll('SELECT id, name, kind, criteria FROM collections');
```

Add a new function immediately before it:

```js
  function loadReminderSnoozes(){
    reminderSnoozes = {};
    const { rows } = queryAll('SELECT document_id, field_id, snoozed_until FROM reminder_snoozes');
    for(const [documentId, fieldId, snoozedUntil] of rows){
      reminderSnoozes[`${documentId}:${fieldId}`] = snoozedUntil;
    }
    window.__DEBUG_reminderSnoozes = reminderSnoozes; // test-only hook (tests/test_reminders.py) -- the simplest way to assert on this module-private variable from outside the page's own closure
  }

```

In `loadDocumentsFromDb()`, find:

```js
    loadFieldDefs();
    loadFieldDescriptions();
    loadCollections();
    loadFieldValues();
```

Change to:

```js
    loadFieldDefs();
    loadFieldDescriptions();
    loadCollections();
    loadReminderSnoozes();
    loadFieldValues();
```

In `resetAll()`, find:

```js
    collections = []; collectionDocIds = {}; nextCollectionId = 1; collectionsNavExpanded = true; selectedDocIds = new Set();
```

Change to:

```js
    collections = []; collectionDocIds = {}; nextCollectionId = 1; collectionsNavExpanded = true; selectedDocIds = new Set();
    reminderSnoozes = {};
```

- [ ] **Step 4: Add stub support**

In `tests/stub_studio2.js`, find both occurrences of the table-lists
object literal (one in the seeded-load branch, one in the empty-init
branch):

```js
        this.tables = { documents: parsed.documents || [], tags: parsed.tags || [], document_tags: parsed.document_tags || [], people: parsed.people || [], document_people: parsed.document_people || [], document_field_people: parsed.document_field_people || [], settings: parsed.settings || [], document_type_fields: parsed.document_type_fields || [], fields: parsed.fields || [], document_field_values: parsed.document_field_values || [], collections: parsed.collections || [], collection_documents: parsed.collection_documents || [], field_descriptions: parsed.field_descriptions || [] };
```

Change to:

```js
        this.tables = { documents: parsed.documents || [], tags: parsed.tags || [], document_tags: parsed.document_tags || [], people: parsed.people || [], document_people: parsed.document_people || [], document_field_people: parsed.document_field_people || [], settings: parsed.settings || [], document_type_fields: parsed.document_type_fields || [], fields: parsed.fields || [], document_field_values: parsed.document_field_values || [], collections: parsed.collections || [], collection_documents: parsed.collection_documents || [], field_descriptions: parsed.field_descriptions || [], reminder_snoozes: parsed.reminder_snoozes || [] };
```

And the other two occurrences (the empty-init branches, both currently
identical to each other):

```js
        this.tables = { documents: [], tags: [], document_tags: [], people: [], document_people: [], document_field_people: [], settings: [], document_type_fields: [], fields: [], document_field_values: [], collections: [], collection_documents: [], field_descriptions: [] };
```

Change each to:

```js
        this.tables = { documents: [], tags: [], document_tags: [], people: [], document_people: [], document_field_people: [], settings: [], document_type_fields: [], fields: [], document_field_values: [], collections: [], collection_documents: [], field_descriptions: [], reminder_snoozes: [] };
```

Find the `__makeSeededRoot`-adjacent seed defaults block:

```js
    collections: seed.collections || [], collection_documents: seed.collection_documents || [],
    field_descriptions: seed.field_descriptions || [],
```

Change to:

```js
    collections: seed.collections || [], collection_documents: seed.collection_documents || [],
    field_descriptions: seed.field_descriptions || [], reminder_snoozes: seed.reminder_snoozes || [],
```

Now add the compound-key dedupe. Find:

```js
    if (table === 'field_descriptions' && isReplace) {
      this.tables.field_descriptions = this.tables.field_descriptions.filter(r => r.field_name !== row.field_name);
    }
```

Add immediately after:

```js
    if (table === 'reminder_snoozes' && isReplace) {
      this.tables.reminder_snoozes = this.tables.reminder_snoozes.filter(r => !(r.document_id === row.document_id && r.field_id === row.field_id));
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: all prior scenarios plus Scenario 3 print `True`/expected
values (`loaded_snooze` reads `'2026-06-01'`, and the replaced-value
check reads `True`), `JS ERRORS: []`.

- [ ] **Step 6: Run the full existing suite to confirm the stub change is safe**

Run: `cd tests && for f in test_*.py; do python3 "$f" > /tmp/task3_$f.log 2>&1; echo "EXIT:$? for $f"; done`
Expected: 63/64 exit 0 (63 pre-existing scripts plus this new one — every
script should still pass, since the stub changes only *add* a new table
and a new dedupe branch, touching nothing existing tables/branches rely
on).

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/stub_studio2.js tests/test_reminders.py
git commit -m "Add the reminder_snoozes table and its stub support

New table added directly to SCHEMA (no SCHEMA_MIGRATIONS entry needed --
that array is only for ALTER TABLE ADD COLUMN on existing tables).
stub_studio2.js needed new compound-key INSERT OR REPLACE dedupe support
-- every prior dedupe branch in this stub keyed on a single column."
```

---

### Task 4: `checkReminders()` — the due-reminder scan

**Files:**
- Modify: `dossiary.html` (new `addDaysToIsoDate()`, `reminderDueLabel()`,
  and `checkReminders()` functions), new i18n keys for the due-label
  phrasing (singular/plural pairs) across all six `STRINGS` blocks
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Consumes: `reminderLookaheadDays` (Task 2), `reminderSnoozes` (Task 3),
  `allDocs` (each entry has `.customFields`, `.archived`, `.deleted`,
  per existing conventions), `fieldDefs` (existing, entries have `.id`,
  `.name`, `.type`), `todayIsoDate()` (existing), `displayName(d)`
  (existing).
- Produces: `checkReminders()` → `Array<{documentId, fieldId, fieldName,
  date, docTitle}>`, sorted by `date` ascending. Task 5's
  `openRemindersModal()` and Task 6's toolbar-button handler both call
  this directly. `addDaysToIsoDate(iso, days)` → ISO date string.
  `reminderDueLabel(dateIso, todayIso)` → translated string (used by
  Task 5's row rendering).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reminders.py`, before the final block:

```python
        # === Scenario 4: checkReminders() -- due/overdue inclusion, lookahead
        # window boundary, archived/deleted exclusion, active-snooze exclusion,
        # expired-snooze inclusion, multi-field-per-document correctness, sort
        # order. All dates are computed relative to the real "today" the test
        # runs on, so this scenario is deliberately date-arithmetic rather than
        # hardcoded, to stay correct regardless of when the suite runs. ===
        multi_field_seed = {
            "documents": [
                {  # doc 1: due today
                    "id": 1, "title": "Doc Due Today", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 2: overdue by 5 days
                    "id": 2, "title": "Doc Overdue", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 3: due in 10 days (within a 14-day lookahead)
                    "id": 3, "title": "Doc Due Soon", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 4: due in 60 days (OUTSIDE a 14-day lookahead -- must be excluded)
                    "id": 4, "title": "Doc Too Far Out", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 5: due today, but ARCHIVED -- must be excluded
                    "id": 5, "title": "Doc Archived", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 1, "needs_review": 0, "deleted": 0,
                },
                {  # doc 6: due today, but DELETED -- must be excluded
                    "id": 6, "title": "Doc Deleted", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 1,
                },
                {  # doc 7: due today, but ACTIVELY snoozed -- must be excluded
                    "id": 7, "title": "Doc Snoozed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 8: due today, snooze already EXPIRED -- must be included
                    "id": 8, "title": "Doc Snooze Expired", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 9: TWO reminder fields, one due (Insurance) one not (Warranty)
                    "id": 9, "title": "Doc Two Reminders", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "settings": [{"key": "reminder_lookahead_days", "value": "14"}],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
                {"id": 2, "name": "Warranty End", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [],  # filled in below via JS, using real relative-to-today dates
            "reminder_snoozes": [],       # filled in below via JS, same reason
        }

        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(multi_field_seed)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        # Compute every date relative to the app's own todayIsoDate() and write
        # document_field_values / reminder_snoozes directly via db.run(), then
        # reload from the in-memory db so allDocs/reminderSnoozes reflect them --
        # this keeps the scenario correct regardless of what "today" actually is
        # when the suite runs.
        result = await page.evaluate("""
            () => {
                const add = (days) => addDaysToIsoDate(todayIsoDate(), days);
                const values = [
                    [1, 1, add(0)],   // doc1 field1 (Renewal Date): due today
                    [2, 1, add(-5)],  // doc2: overdue by 5 days
                    [3, 1, add(10)],  // doc3: due in 10 days (within 14-day lookahead)
                    [4, 1, add(60)],  // doc4: due in 60 days (outside lookahead)
                    [5, 1, add(0)],   // doc5: due today, but archived
                    [6, 1, add(0)],   // doc6: due today, but deleted
                    [7, 1, add(0)],   // doc7: due today, but actively snoozed
                    [8, 1, add(0)],   // doc8: due today, snooze already expired
                    [9, 1, add(0)],   // doc9 Renewal Date: due today
                    [9, 2, add(60)],  // doc9 Warranty End: not due
                ];
                for(const [documentId, fieldId, value] of values){
                    db.run('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [documentId, fieldId, value]);
                }
                db.run('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until) VALUES (?, ?, ?)', [7, 1, add(5)]);  // active: 5 days in the future
                db.run('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until) VALUES (?, ?, ?)', [8, 1, add(-1)]); // expired: 1 day in the past
                loadDocumentsFromDb();
                const due = checkReminders();
                return due.map(r => ({ documentId: r.documentId, fieldId: r.fieldId, fieldName: r.fieldName, date: r.date, docTitle: r.docTitle }));
            }
        """)
        due_doc_ids = sorted(r['documentId'] for r in result)
        print("checkReminders() includes exactly docs 1, 2, 3, 8, 9 (not 4/5/6/7):", due_doc_ids == [1, 2, 3, 8, 9])

        doc9_entries = [r for r in result if r['documentId'] == 9]
        print("doc 9 contributes exactly one due entry (Renewal Date only, not Warranty End):", len(doc9_entries) == 1 and doc9_entries[0]['fieldName'] == 'Renewal Date')

        sorted_dates = [r['date'] for r in result]
        print("results are sorted by date ascending (most overdue first):", sorted_dates == sorted(sorted_dates))
        print("doc 2 (most overdue) sorts first:", result[0]['documentId'] == 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: fails with a JS error (`checkReminders is not defined`) or
similar, since neither `checkReminders()` nor `addDaysToIsoDate()` exist
yet.

- [ ] **Step 3: Implement**

In `dossiary.html`, find `todayIsoDate()`:

```js
  function todayIsoDate(){ return nowIso().slice(0, 10); } // YYYY-MM-DD, matches <input type="date">
```

Add immediately after it:

```js
  function addDaysToIsoDate(iso, days){
    const d = new Date(iso + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
  }

  // "N days overdue" / "due in N days" / "due today", used by openRemindersModal().
  function reminderDueLabel(dateIso, todayIso){
    const dateMs = Date.parse(dateIso + 'T00:00:00Z');
    const todayMs = Date.parse(todayIso + 'T00:00:00Z');
    const diffDays = Math.round((dateMs - todayMs) / 86400000);
    if(diffDays === 0) return t('reminderDueToday');
    if(diffDays < 0){
      const overdueDays = -diffDays;
      return overdueDays === 1 ? t('reminderOverdueSingular', {days: overdueDays}) : t('reminderOverduePlural', {days: overdueDays});
    }
    return diffDays === 1 ? t('reminderDueInSingular', {days: diffDays}) : t('reminderDueInPlural', {days: diffDays});
  }

  // Pure, synchronous scan over already-loaded in-memory data -- no filesystem
  // or network I/O, matching this app's "no silent/background work" principle
  // (see CLAUDE.md's Inbox note for the same reasoning applied to file staging).
  // Only two call sites ever invoke this: once automatically right after a
  // library opens (afterDbReady()), and the "Check reminders" toolbar button.
  function checkReminders(){
    const todayIso = todayIsoDate();
    const cutoff = addDaysToIsoDate(todayIso, reminderLookaheadDays);
    const reminderFields = fieldDefs.filter(f => f.type === 'reminder');
    if(!reminderFields.length) return [];
    const results = [];
    for(const d of allDocs){
      if(d.deleted || d.archived) continue;
      const customFields = d.customFields || {};
      for(const field of reminderFields){
        const raw = customFields[field.name];
        if(!raw) continue;
        const dateOnly = raw.slice(0, 10);
        if(dateOnly > cutoff) continue;
        const snoozedUntil = reminderSnoozes[`${d.id}:${field.id}`];
        if(snoozedUntil && snoozedUntil > todayIso) continue;
        results.push({ documentId: d.id, fieldId: field.id, fieldName: field.name, date: dateOnly, docTitle: displayName(d) });
      }
    }
    results.sort((a, b) => a.date < b.date ? -1 : (a.date > b.date ? 1 : 0));
    return results;
  }
```

Add the new i18n keys (`reminderDueToday`, `reminderOverdueSingular`/
`reminderOverduePlural`, `reminderDueInSingular`/`reminderDueInPlural`) to
all six `STRINGS` blocks, anywhere convenient within each block (e.g.
near the existing singular/plural pairs like `dragdropAddedToReviewQueueSingular`):

- `en`: `reminderDueToday: 'Due today', reminderOverdueSingular: '{days} day overdue', reminderOverduePlural: '{days} days overdue', reminderDueInSingular: 'Due in {days} day', reminderDueInPlural: 'Due in {days} days',`
- `es`: `reminderDueToday: 'Vence hoy', reminderOverdueSingular: 'Vencido hace {days} día', reminderOverduePlural: 'Vencido hace {days} días', reminderDueInSingular: 'Vence en {days} día', reminderDueInPlural: 'Vence en {days} días',`
- `fr`: `reminderDueToday: 'Échéance aujourd\\'hui', reminderOverdueSingular: 'En retard de {days} jour', reminderOverduePlural: 'En retard de {days} jours', reminderDueInSingular: 'Échéance dans {days} jour', reminderDueInPlural: 'Échéance dans {days} jours',`
- `de`: `reminderDueToday: 'Heute fällig', reminderOverdueSingular: '{days} Tag überfällig', reminderOverduePlural: '{days} Tage überfällig', reminderDueInSingular: 'Fällig in {days} Tag', reminderDueInPlural: 'Fällig in {days} Tagen',`
- `zh-Hans`: `reminderDueToday: '今天到期', reminderOverdueSingular: '逾期 {days} 天', reminderOverduePlural: '逾期 {days} 天', reminderDueInSingular: '{days} 天后到期', reminderDueInPlural: '{days} 天后到期',`
- `zh-Hant`: `reminderDueToday: '今天到期', reminderOverdueSingular: '逾期 {days} 天', reminderOverduePlural: '逾期 {days} 天', reminderDueInSingular: '{days} 天後到期', reminderDueInPlural: '{days} 天後到期',`
  (Chinese doesn't inflect for grammatical number, per this repo's own
  established convention for singular/plural pairs in these two
  languages — both slots carry identical text; 后→後 is the one character
  that changes between the two scripts here)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: all prior scenarios plus Scenario 4 print `True`, `JS ERRORS: []`.

- [ ] **Step 5: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `PASS`.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Add checkReminders() -- the pure, synchronous due-reminder scan

Covers the full 'what counts as due' rule from the spec in one pass:
lookahead-window inclusion, archived/deleted exclusion, active-snooze
exclusion, expired-snooze inclusion, multiple reminder fields per
document each evaluated independently, sorted by date ascending."
```

---

### Task 5: The reminders modal and snoozing

**Files:**
- Modify: `dossiary.html` (new CSS for `.reminder-row`, new
  `openRemindersModal()`, `renderReminderRowHtml()`, `wireReminderRows()`,
  `snoozeReminder()` functions), new i18n keys across all six `STRINGS`
  blocks
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Consumes: `checkReminders()`'s return shape (Task 4), `formatDate()`
  (existing), `reminderDueLabel()` (Task 4), `addDaysToIsoDate()`
  (Task 4), `closeModal()`/`onModalKeydown()`/`modalRoot` (existing modal
  machinery), `selectedDocId`/`render()`/`openDetail()` (existing
  select-and-show sequence, same one `saveEditedDocument()`'s own
  success path already uses).
- Produces: `openRemindersModal(dueReminders)` (takes the array
  `checkReminders()` returns), called by Task 6's trigger wiring.
  `snoozeReminder(documentId, fieldId, snoozedUntil)` (async, persists and
  updates in-memory `reminderSnoozes`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reminders.py`, before the final block. This reuses
the `multi_field_seed` data already loaded by Task 4's Scenario 4 (the
page is still open on that library, with docs 1/2/3/8/9 due) — no need to
reseed.

```python
        # === Scenario 5: openRemindersModal() renders every due reminder,
        # clicking a row opens that document, and each of the four snooze
        # choices persists correctly and removes that row from the list ===
        due_now = await page.evaluate("checkReminders()")
        await page.evaluate("(due) => openRemindersModal(due)", due_now)
        await page.wait_for_timeout(200)

        row_count = await page.locator('.reminder-row').count()
        print("modal shows exactly one row per due reminder:", row_count == len(due_now))

        # Snooze doc 3's reminder for "1 week" -- confirm it persists and the row disappears
        doc3_row = page.locator('.reminder-row[data-document-id="3"]')
        await doc3_row.locator('.reminder-snooze-select').select_option('1w')
        await page.wait_for_timeout(200)
        doc3_row_gone = await page.locator('.reminder-row[data-document-id="3"]').count()
        print("doc 3's row is removed from the modal after snoozing 1 week:", doc3_row_gone == 0)

        persisted3 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        snooze_row_3 = next((s for s in persisted3['reminder_snoozes'] if s['document_id'] == 3 and s['field_id'] == 1), None)
        expected_1w = await page.evaluate("addDaysToIsoDate(todayIsoDate(), 7)")
        print("doc 3's snooze persisted as exactly today + 7 days:", snooze_row_3['snoozed_until'] if snooze_row_3 else None, "==", expected_1w)

        # Custom-date snooze on doc 1
        doc1_row = page.locator('.reminder-row[data-document-id="1"]')
        await doc1_row.locator('.reminder-snooze-select').select_option('custom')
        await page.wait_for_timeout(100)
        custom_date_visible = await doc1_row.locator('.reminder-snooze-custom-date').is_visible()
        print("choosing 'Custom date' reveals a date picker:", custom_date_visible)
        await doc1_row.locator('.reminder-snooze-custom-date').fill('2026-12-25')
        await doc1_row.locator('.reminder-snooze-custom-date').dispatch_event('change')
        await page.wait_for_timeout(200)
        doc1_row_gone = await page.locator('.reminder-row[data-document-id="1"]').count()
        print("doc 1's row is removed after a custom-date snooze:", doc1_row_gone == 0)

        # Clicking a remaining row (not its snooze control) opens that document
        # and closes the modal
        remaining_row = page.locator('.reminder-row').first
        remaining_doc_id = await remaining_row.get_attribute('data-document-id')
        await remaining_row.click()
        await page.wait_for_timeout(200)
        modal_closed = await page.locator('.reminder-row').count()
        print("clicking a row closes the modal:", modal_closed == 0)
        selected_row_highlighted = await page.locator(f'tr[data-id="{remaining_doc_id}"].row-selected').count()
        print("clicking a row selects/highlights that document in the table:", selected_row_highlighted == 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: fails with `openRemindersModal is not defined`.

- [ ] **Step 3: Implement**

In `dossiary.html`, find the existing `.fs-list-empty` CSS rule:

```css
  .fs-list-empty{ padding:14px 10px; font-size:11.5px; color:var(--text-dim); font-family:var(--font-mono); }
```

Add nearby:

```css
  .reminder-row{
    display:flex; align-items:center; justify-content:space-between; gap:12px;
    padding:10px 12px; border-bottom:1px solid rgba(217,210,189,0.06); cursor:pointer;
  }
  .reminder-row:last-child{ border-bottom:none; }
  .reminder-row:hover{ background:rgba(79,224,166,0.06); }
  .reminder-row-title{ font-size:13px; color:var(--text); }
  .reminder-row-sub{ font-size:11.5px; color:var(--text-dim); font-family:var(--font-mono); margin-top:2px; }
  .reminder-snooze{ display:flex; align-items:center; gap:6px; flex-shrink:0; }
  .reminder-snooze select, .reminder-snooze-custom-date{
    background:var(--ink-2); border:1px solid var(--line); color:var(--text);
    font-family:var(--font-mono); font-size:11.5px; padding:5px 7px; border-radius:var(--radius);
  }
```

Find `openLibrariesModal()` (for reference on the modal-shell pattern —
no code changes needed there) and add a new function nearby:

```js
  function openRemindersModal(dueReminders){
    const todayIso = todayIsoDate();
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <h2>${t('reminderModalTitle')}</h2>
          <div class="fs-list" id="reminders-list">
            ${dueReminders.map(r => renderReminderRowHtml(r, todayIso)).join('')}
          </div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
    wireReminderRows();
  }

  function renderReminderRowHtml(r, todayIso){
    return `
      <div class="reminder-row" data-document-id="${r.documentId}" data-field-id="${r.fieldId}">
        <div>
          <div class="reminder-row-title">${escapeHtml(r.docTitle)}</div>
          <div class="reminder-row-sub">${escapeHtml(r.fieldName)} · ${formatDate(r.date)} · ${reminderDueLabel(r.date, todayIso)}</div>
        </div>
        <span class="reminder-snooze" onclick="event.stopPropagation()">
          <select class="reminder-snooze-select" data-document-id="${r.documentId}" data-field-id="${r.fieldId}">
            <option value="">${t('reminderSnoozeLabel')}</option>
            <option value="1w">${t('reminderSnooze1Week')}</option>
            <option value="1m">${t('reminderSnooze1Month')}</option>
            <option value="3m">${t('reminderSnooze3Months')}</option>
            <option value="custom">${t('reminderSnoozeCustom')}</option>
          </select>
          <input type="date" class="reminder-snooze-custom-date" style="display:none;" data-document-id="${r.documentId}" data-field-id="${r.fieldId}" />
        </span>
      </div>
    `;
  }

  function wireReminderRows(){
    modalRoot.querySelectorAll('.reminder-row').forEach(row => {
      row.addEventListener('click', () => {
        const documentId = Number(row.dataset.documentId);
        closeModal();
        selectedDocId = documentId;
        render();
        openDetail(documentId);
      });
    });
    modalRoot.querySelectorAll('.reminder-snooze-select').forEach(select => {
      select.addEventListener('change', async (e) => {
        const documentId = Number(select.dataset.documentId);
        const fieldId = Number(select.dataset.fieldId);
        const choice = select.value;
        if(choice === 'custom'){
          const dateInput = select.nextElementSibling;
          dateInput.style.display = 'inline-block';
          dateInput.focus();
          return;
        }
        if(!choice) return;
        const days = choice === '1w' ? 7 : choice === '1m' ? 30 : 90;
        const snoozedUntil = addDaysToIsoDate(todayIsoDate(), days);
        await snoozeReminder(documentId, fieldId, snoozedUntil);
        removeReminderRow(select.closest('.reminder-row'));
      });
    });
    modalRoot.querySelectorAll('.reminder-snooze-custom-date').forEach(dateInput => {
      dateInput.addEventListener('change', async () => {
        if(!dateInput.value) return;
        const documentId = Number(dateInput.dataset.documentId);
        const fieldId = Number(dateInput.dataset.fieldId);
        await snoozeReminder(documentId, fieldId, dateInput.value);
        removeReminderRow(dateInput.closest('.reminder-row'));
      });
    });
  }

  function removeReminderRow(rowEl){
    if(!rowEl) return;
    rowEl.remove();
    // Every reminder snoozed away -- nothing left to show, close automatically
    // rather than leaving an empty modal open.
    if(!modalRoot.querySelectorAll('.reminder-row').length) closeModal();
  }

  async function snoozeReminder(documentId, fieldId, snoozedUntil){
    reminderSnoozes[`${documentId}:${fieldId}`] = snoozedUntil;
    db.run('INSERT OR REPLACE INTO reminder_snoozes (document_id, field_id, snoozed_until) VALUES (?, ?, ?)', [documentId, fieldId, snoozedUntil]);
    await persistDb();
  }
```

Add the new i18n keys to all six `STRINGS` blocks:

- `en`: `reminderModalTitle: 'Reminders due', reminderSnoozeLabel: 'Snooze…', reminderSnooze1Week: '1 week', reminderSnooze1Month: '1 month', reminderSnooze3Months: '3 months', reminderSnoozeCustom: 'Custom date…',`
- `es`: `reminderModalTitle: 'Recordatorios pendientes', reminderSnoozeLabel: 'Posponer…', reminderSnooze1Week: '1 semana', reminderSnooze1Month: '1 mes', reminderSnooze3Months: '3 meses', reminderSnoozeCustom: 'Fecha personalizada…',`
- `fr`: `reminderModalTitle: 'Rappels à traiter', reminderSnoozeLabel: 'Reporter…', reminderSnooze1Week: '1 semaine', reminderSnooze1Month: '1 mois', reminderSnooze3Months: '3 mois', reminderSnoozeCustom: 'Date personnalisée…',`
- `de`: `reminderModalTitle: 'Fällige Erinnerungen', reminderSnoozeLabel: 'Zurückstellen…', reminderSnooze1Week: '1 Woche', reminderSnooze1Month: '1 Monat', reminderSnooze3Months: '3 Monate', reminderSnoozeCustom: 'Eigenes Datum…',`
- `zh-Hans`: `reminderModalTitle: '到期提醒', reminderSnoozeLabel: '推迟…', reminderSnooze1Week: '1 周', reminderSnooze1Month: '1 个月', reminderSnooze3Months: '3 个月', reminderSnoozeCustom: '自定义日期…',`
- `zh-Hant`: `reminderModalTitle: '到期提醒', reminderSnoozeLabel: '推遲…', reminderSnooze1Week: '1 週', reminderSnooze1Month: '1 個月', reminderSnooze3Months: '3 個月', reminderSnoozeCustom: '自訂日期…',`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: all prior scenarios plus Scenario 5 print `True`, `JS ERRORS: []`.

- [ ] **Step 5: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `PASS`.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Add the reminders modal and per-row snoozing

Reuses .fs-list's existing scrollable-list styling. Clicking a row
follows the exact same 'select, render, closeModal, openDetail' sequence
saveEditedDocument()'s own success path already uses. All four snooze
choices (1 week/1 month/3 months/custom date) persist via
INSERT OR REPLACE and remove that row from the current list; the modal
closes itself automatically once every reminder has been snoozed away."
```

---

### Task 6: Trigger wiring — toolbar button and automatic library-open check

**Files:**
- Modify: `dossiary.html:659` (new toolbar button markup), `dossiary.html`
  (`afterDbReady()`, a new `checkRemindersAndShowStatus()` function, its
  click-listener wiring near `#inbox-check-btn`'s own), new i18n keys
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Consumes: `checkReminders()` (Task 4), `openRemindersModal()` (Task 5),
  `setStatusT()` (existing).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reminders.py`, before the final block:

Add `import datetime` near the top of `tests/test_reminders.py`, alongside
its existing `import asyncio, json` line (needed to compute a real
"today" ISO date directly in Python, so the seed data itself already
contains a due reminder — no need to mutate the database mid-session or
reload twice).

```python
        # === Scenario 6: the automatic library-open check surfaces the modal
        # only when something is due, and stays silent otherwise; the manual
        # "Check reminders" button reports "No reminders due." when nothing
        # is due, and opens the modal when something is ===
        today_iso = datetime.date.today().isoformat()
        due_seed = dict(SEED)
        due_seed['fields'] = [{'id': 1, 'name': 'Renewal Date', 'type': 'reminder', 'show_as_column': 0, 'autocomplete': 0}]
        due_seed['document_field_values'] = [{'document_id': 1, 'field_id': 1, 'value': today_iso}]

        # A genuinely fresh library open (the real afterDbReady() flow) with a due
        # reminder already present in the seed data -- not a mid-session mutation --
        # should surface the modal automatically, with no manual action.
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(due_seed)}); window.__TEST_ROOT.name = 'DueLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        modal_shown_automatically = await page.locator('.reminder-row').count()
        print("library open with a due reminder shows the reminders modal automatically:", modal_shown_automatically > 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # Manual button, something due
        check_btn_present = await page.locator('#check-reminders-btn').count()
        print("Check reminders toolbar button is present:", check_btn_present == 1)
        await page.click('#check-reminders-btn')
        await page.wait_for_timeout(200)
        modal_shown_by_button = await page.locator('.reminder-row').count()
        print("clicking Check reminders opens the modal when something is due:", modal_shown_by_button > 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # Manual button, nothing due (fresh empty-reminders library)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'EmptyLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        no_modal_on_open = await page.locator('.reminder-row').count()
        print("library open with nothing due shows no modal:", no_modal_on_open == 0)
        await page.click('#check-reminders-btn')
        await page.wait_for_timeout(200)
        status_text = await page.locator('#status').inner_text()
        print("Check reminders with nothing due reports the empty-case status message:", 'no reminders' in status_text.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: fails at `check_btn_present` (button doesn't exist yet), or
earlier if the automatic-check assertion also fails.

- [ ] **Step 3: Implement**

In `dossiary.html`, find:

```html
        <button id="inbox-check-btn" data-i18n="toolbarCheckInbox">📥 Check inbox</button>
```

Change to:

```html
        <button id="inbox-check-btn" data-i18n="toolbarCheckInbox">📥 Check inbox</button>
        <button id="check-reminders-btn" data-i18n="toolbarCheckReminders">🔔 Check reminders</button>
```

Find `afterDbReady()`:

```js
  function afterDbReady(){
    emptyState.style.display = 'none';
    initState.style.display = 'none';
    loadDocumentsFromDb();
    setStatusT('statusOpenedLibrary', {count: allDocs.length, name: rootDirHandle.name}, 'ok');
    checkInbox(); // fire-and-forget -- best effort, doesn't block the library from opening
    recordRecentLibrary(rootDirHandle); // fire-and-forget, same reasoning as checkInbox() above
  }
```

Change to:

```js
  function afterDbReady(){
    emptyState.style.display = 'none';
    initState.style.display = 'none';
    loadDocumentsFromDb();
    setStatusT('statusOpenedLibrary', {count: allDocs.length, name: rootDirHandle.name}, 'ok');
    checkInbox(); // fire-and-forget -- best effort, doesn't block the library from opening
    recordRecentLibrary(rootDirHandle); // fire-and-forget, same reasoning as checkInbox() above
    // Silent when nothing's due, same as checkInbox() finding nothing staged --
    // checkReminders() is a pure in-memory scan, no I/O, so this can run
    // synchronously right here rather than needing its own fire-and-forget treatment.
    const dueOnOpen = checkReminders();
    if(dueOnOpen.length) openRemindersModal(dueOnOpen);
  }
```

Find the existing `#inbox-check-btn` wiring (near the end of the file,
alongside other toolbar button listeners):

```js
  el('inbox-check-btn').addEventListener('click', async () => { await checkInbox(); await addAllInboxFilesAndShowStatus(); });
```

Add nearby:

```js
  el('check-reminders-btn').addEventListener('click', checkRemindersAndShowStatus);
```

Add the new function itself near `addAllInboxFilesAndShowStatus()`:

```js
  function checkRemindersAndShowStatus(){
    const due = checkReminders();
    if(!due.length){ setStatusT('reminderNoneDue', null, 'ok'); return; }
    openRemindersModal(due);
  }
```

Add the new i18n keys to all six `STRINGS` blocks (next to
`toolbarCheckInbox`/`dragdropNoFilesWaiting`-style entries):

- `en`: `toolbarCheckReminders: '🔔 Check reminders', reminderNoneDue: 'No reminders due.',`
- `es`: `toolbarCheckReminders: '🔔 Ver recordatorios', reminderNoneDue: 'No hay recordatorios pendientes.',`
- `fr`: `toolbarCheckReminders: '🔔 Vérifier les rappels', reminderNoneDue: 'Aucun rappel à traiter.',`
- `de`: `toolbarCheckReminders: '🔔 Erinnerungen prüfen', reminderNoneDue: 'Keine fälligen Erinnerungen.',`
- `zh-Hans`: `toolbarCheckReminders: '🔔 检查提醒', reminderNoneDue: '没有到期的提醒。',`
- `zh-Hant`: `toolbarCheckReminders: '🔔 檢查提醒', reminderNoneDue: '沒有到期的提醒。',`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: every scenario (1 through 6) prints `True`/expected values,
`JS ERRORS: []`.

- [ ] **Step 5: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `PASS`.

- [ ] **Step 6: Run the full existing suite**

Run: `cd tests && for f in test_*.py; do python3 "$f" > /tmp/task6_$f.log 2>&1; echo "EXIT:$? for $f"; done`
Expected: 64/64 exit 0 (63 pre-existing scripts plus `test_reminders.py`).

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Wire up the two reminder-check trigger points

Library open (afterDbReady()) surfaces the modal automatically when
something's due, silently otherwise. A new always-visible 'Check
reminders' toolbar button mirrors 'Check inbox' exactly, reporting
'No reminders due.' when a manual click finds nothing -- both explicit
triggers, no polling, matching this app's existing 'no silent writes'
principle applied to a read-only check instead."
```

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md` (new architecture note), `tests/CLAUDE.md` (new
  paragraph describing `test_reminders.py`'s coverage)

**Interfaces:**
- Consumes: the finished behavior from Tasks 1-6 (this task only
  documents it — no code changes).

- [ ] **Step 1: Read the existing notes first**

Read `CLAUDE.md`'s existing notes for "Amount, Currency, and Payment
method" and "Field descriptions" in full — both are the closest
precedent for a new field-type-shaped feature's own architecture note
(dense, "what and why" prose, cross-referencing the exact functions
involved). Read `tests/CLAUDE.md`'s own "How this was tested" section in
full, particularly its closing "This list itself can go stale" paragraph
and the most recently added feature's own entry, to match voice and
placement exactly.

- [ ] **Step 2: Add the CLAUDE.md architecture note**

Insert a new bullet in `CLAUDE.md`'s "Architecture notes" section (find a
sensible spot — e.g. right after the "Field descriptions" note, since
both concern the generic custom-fields system), covering: `reminder` as a
fifth `fields.type` value that reuses `date`'s render/format code
verbatim; that any field of this type on any document is automatically a
reminder source, with no hardcoded field name; the `reminder_lookahead_days`
setting and its 30-day default; the `reminder_snoozes` table and its
compound `(document_id, field_id)` key, since one document can carry more
than one reminder-type field; the "what counts as due" rule (lookahead
window, archived/deleted exclusion, active-snooze exclusion); and the two
explicit trigger points (library open, "Check reminders" button) with no
live badge and no background polling, matching this app's `checkInbox()`
precedent for the same reasoning.

- [ ] **Step 3: Add the tests/CLAUDE.md coverage paragraph**

In `tests/CLAUDE.md`'s "How this was tested" section, find the end of the
existing feature list (its most recently added entry, currently the
right-click context menu's own paragraph, immediately before "This list
itself can go stale"). Add a new clause describing `test_reminders.py`'s
coverage: creating a `reminder`-type field inline and confirming it
behaves identically to `date` in rendering/storage/formatting, including
the Column-capability-checkbox-offered-but-not-Autocomplete detail; the
`reminder_lookahead_days` setting's default/persistence/reopen behavior;
the `reminder_snoozes` table's loading and its compound-key `INSERT OR
REPLACE` dedupe (the one genuinely new piece of `stub_studio2.js`
machinery this feature needed); `checkReminders()`'s full "what counts as
due" rule exercised via a 9-document scenario (due today, overdue,
due-within-window, outside-window, archived, deleted, actively-snoozed,
expired-snooze, and a two-reminder-field document); the modal's row
rendering, all four snooze choices persisting and removing their own row,
the modal auto-closing once everything's snoozed away, and clicking a row
following the exact same select/render/closeModal/openDetail sequence
`saveEditedDocument()`'s own success path already uses; and both trigger
points (automatic on library open, the "Check reminders" button,
including its "No reminders due." empty-case status message).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "Document the reminder-type custom fields feature"
```

---

## Self-Review

**1. Spec coverage** — every section of
`docs/superpowers/specs/2026-08-30-reminder-fields-design.md` maps to a
task: the field type itself and its identical-to-`date` treatment (Task
1); the lookahead setting (Task 2); the snooze table (Task 3); the "what
counts as due" rule (Task 4); the modal and snooze UI (Task 5); the two
explicit trigger points (Task 6); documentation (Task 7). Out-of-scope
items from the spec (push notifications/background timers, editing a
reminder's date from within the modal, recurring reminders, a live nav
badge, reminders on archived/deleted documents) are not implemented by
any task — the last of these is explicitly enforced by `checkReminders()`'s
own `if(d.deleted || d.archived) continue;` guard in Task 4.

**2. Placeholder scan** — no TBD/TODO; every step shows exact before/
after code, exact translated strings for all six languages (including
the two hand-checked `zh-Hant` conversions, verified against this file's
own existing `字段名称`/`字段名稱` pair rather than guessed), and real
test assertions rather than descriptions of what to test. An earlier
draft of Task 3's Step 1 had the test written before the debug hook it
depends on existed, requiring a later step to go back and rewrite it —
fixed during this review pass so Step 1's test is correct as first
written, with the hook itself folded directly into Step 3's
implementation. Task 6's Scenario 6 similarly had a real logic bug in an
earlier draft (mutating the database via `db.run()` *after* a reload
doesn't affect what a *subsequent* reload's own seed data contains) —
fixed by computing "today" once in Python and embedding it directly in
the seed data itself, which also removed the previous two-reload
workaround entirely.

**3. Type/name consistency** — `checkReminders()`'s return shape
(`{documentId, fieldId, fieldName, date, docTitle}`) is defined once in
Task 4 and consumed identically by Task 5's `renderReminderRowHtml()`/
`wireReminderRows()` and Task 6's `checkRemindersAndShowStatus()`/
`afterDbReady()`. `reminderSnoozes`'s key shape (`` `${documentId}:${fieldId}` ``)
is established in Task 3's `loadReminderSnoozes()` and used identically
by Task 4's `checkReminders()` and Task 5's `snoozeReminder()`.
`addDaysToIsoDate()`/`reminderDueLabel()` are defined once in Task 4 and
reused by Task 5's row rendering and Task 6's snooze-duration math (via
`wireReminderRows()`, itself part of Task 5) — no duplicate
implementations anywhere.

**4. A real ordering dependency worth restating**: Task 3's
`loadReminderSnoozes()` must run before Task 4's `checkReminders()` can
correctly exclude actively-snoozed reminders — both are called from
`loadDocumentsFromDb()`/module scope, so this is naturally satisfied by
load order (Task 3's call site is added inside `loadDocumentsFromDb()`
itself), but an implementer resuming from Task 4 onward should confirm
`reminderSnoozes` is actually populated by the time `checkReminders()`
runs, not just that the function exists.
