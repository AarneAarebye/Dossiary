# Amount/Currency Column and Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let people filter documents by Currency (dropdown, including "not
set") and by an Amount range (min/max, including "not set") in the main
toolbar, and give Currency its own toggleable table column — without
touching the existing combined "123.45 EUR" Amount column or detail-view
line.

**Architecture:** Currency is a plain generic `fields` row already
(`type: 'text'`) that's excluded by name from the app's existing generic
column/filter/autocomplete system (`dynamicColumnDefs()`/
`populateFilters()`/`matchesCriteria()`/`capabilitiesHtml()`) — removing
that exclusion and flipping its default `show_as_column`/`autocomplete`
to `1`/`1` (for new libraries directly, for existing libraries via a new
one-time backfill migration) gives it a real column, filter dropdown, and
"not set" support entirely through code that already exists and is
already tested. Amount (`type: 'number'`) never gets a filter dropdown
from that system regardless (no dropdown of distinct numbers), so it gets
a brand-new min/max range filter plus a "not set" checkbox, wired directly
into `currentFilters()`/`matchesCriteria()` — the same shared predicate
every other filter, Smart Collection, and Reports view composition already
flows through, so no dedicated combo code is needed for the two filters to
work together.

**Tech Stack:** Vanilla JS, single-file `dossiary.html`, sql.js, no build
step. Tests: standalone Playwright scripts under `tests/`, driven against
`tests/stub_studio2.js`'s fake File System Access API / SQLite.

## Global Constraints

- Single-file app — all changes go in `dossiary.html`, no new files except
  the test file.
- `db.exec(sql)` for parameter-free reads, `db.run(sql, params)` with `?`
  placeholders for writes — no new query patterns.
- Every new user-facing string needs a translation in all six `STRINGS`
  blocks: `en`, `de`, `es`, `fr`, `zh-Hans`, `zh-Hant` — enforced by
  `tests/test_i18n_coverage.py`, which must pass unmodified once keys are
  added.
- A one-time data migration for existing libraries must be tracked via its
  own dedicated `settings` row (never an implicit data-shape check) so it
  never silently re-enables something a person deliberately turned back
  off afterward — see `migrateTextFieldsAutocompleteDefault()` for the
  established pattern.
- Every new test file must load `tests/stub_studio2.js` — never an
  embedded/duplicated stub.
- Reference spec: `docs/superpowers/specs/2026-08-19-amount-currency-column-filter-design.md`.

---

### Task 1: Currency opts into the generic column/filter/autocomplete system

**Files:**
- Modify: `dossiary.html` — `migrateSentinelFieldsToGeneric()` (~line
  2963-2970), `capabilitiesHtml()` (~line 4971-4973),
  `reportBreakdownFields()` (~line 3657-3660), plus two new call sites for
  a new migration function.
- Create: `tests/test_amount_currency_filter.py`

**Interfaces:**
- Consumes: nothing from later tasks.
- Produces: `migrateCurrencyColumnDefault()` — a new module-level
  function, called from both `initNewLibrary()` and `loadDb()` (same call
  sites as `migrateTextFieldsAutocompleteDefault()`). Task 2 does not call
  this function directly but relies on Currency already being a
  `show_as_column: 1, autocomplete: 1` field by the time its own toolbar
  code runs. `tests/test_amount_currency_filter.py` — Task 2 appends to
  this same file (does not create a new one); it must exist with the
  structure shown below (imports, `SEED`, `route_stub`/`visible_ids`/
  `option_label` helpers, `main()`'s `async with` block still open) before
  Task 2 starts.

- [ ] **Step 1: Flip Currency's default `show_as_column`/`autocomplete` for new libraries**

In `dossiary.html`, find `migrateSentinelFieldsToGeneric()`:

```js
    const sentinelDefs = [
      { name: 'Payment method', type: 'text', showAsColumn: 1, autocomplete: 1 },
      { name: 'Amount', type: 'number', showAsColumn: 0, autocomplete: 0 },
      { name: 'Currency', type: 'text', showAsColumn: 0, autocomplete: 0 },
    ];
```

Change the Currency line only (Amount's stays `0, 0` — it's still
excluded from this system entirely, see Task 2):

```js
    const sentinelDefs = [
      { name: 'Payment method', type: 'text', showAsColumn: 1, autocomplete: 1 },
      { name: 'Amount', type: 'number', showAsColumn: 0, autocomplete: 0 },
      { name: 'Currency', type: 'text', showAsColumn: 1, autocomplete: 1 },
    ];
```

This function runs on every library open, including a brand new one
(`initNewLibrary()` calls it same as `loadDb()`), and for a new library
its own idempotency check (`if(fieldNameToId['Payment method'] !==
undefined) return;`) finds nothing yet, so it proceeds and creates
Currency's field row fresh from this literal. No other change is needed
for new libraries.

- [ ] **Step 2: Add the one-time backfill migration for existing libraries**

Directly below `migrateTextFieldsAutocompleteDefault()` (~line 3081) in
`dossiary.html`, add:

```js
  // One-time backfill for existing libraries: Currency used to be excluded
  // from the generic column/filter/autocomplete system entirely (see
  // migrateSentinelFieldsToGeneric() above) -- this flips it on for any
  // library that already ran that migration under the old defaults.
  // Tracked via its own settings row, same reasoning as
  // migrateTextFieldsAutocompleteDefault() just above: there's no way to
  // tell "never touched" apart from "a person deliberately turned it back
  // off in Field Settings" just by looking at the fields table, since both
  // look identical (show_as_column = 0). Running this unconditionally on
  // every open would silently re-enable a field someone had intentionally
  // turned back off; the explicit marker is what makes it safe to call
  // unconditionally instead.
  function migrateCurrencyColumnDefault(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'currency_column_default_migrated'").rows;
    if(rows.length) return; // already run once for this library
    db.run("UPDATE fields SET show_as_column = 1, autocomplete = 1 WHERE name = ? AND type = ?", ['Currency', 'text']);
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('currency_column_default_migrated', ?)", ['1']);
  }
```

The `AND type = ?` guard mirrors `capabilitiesHtml()`'s own
name-plus-context carefulness — it's here defensively, in case a library
somehow has a non-text field literally named "Currency" (e.g. a person's
own custom field predating the sentinel migration), though in practice
`migrateSentinelFieldsToGeneric()`'s own idempotency check
(`fieldNameToId['Currency'] !== undefined`) already prevents that from
ever being created as anything but `type: 'text'`.

- [ ] **Step 3: Wire the new migration into both call sites**

In `dossiary.html`, find (~line 2588):

```js
      migrateTextFieldsAutocompleteDefault(); // no-op here (no text fields exist yet beyond the sentinels above), but marks this library as migrated
      migrateSearchablePdfBuiltFlag(); // no-op here (no documents exist yet), but marks this library as migrated
```

Change to:

```js
      migrateTextFieldsAutocompleteDefault(); // no-op here (no text fields exist yet beyond the sentinels above), but marks this library as migrated
      migrateCurrencyColumnDefault(); // no-op here (Currency was already created show_as_column=1 above), but marks this library as migrated
      migrateSearchablePdfBuiltFlag(); // no-op here (no documents exist yet), but marks this library as migrated
```

And find (~line 2613):

```js
    migrateTextFieldsAutocompleteDefault(); // one-time; no-op if this library was already migrated
    migrateSearchablePdfBuiltFlag(); // one-time; no-op if this library was already migrated
```

Change to:

```js
    migrateTextFieldsAutocompleteDefault(); // one-time; no-op if this library was already migrated
    migrateCurrencyColumnDefault(); // one-time; no-op if this library was already migrated
    migrateSearchablePdfBuiltFlag(); // one-time; no-op if this library was already migrated
```

- [ ] **Step 4: Let Currency's Field Settings capability checkboxes render**

In `dossiary.html`, find `capabilitiesHtml()` (~line 4971-4973):

```js
    function capabilitiesHtml(fieldName){
      const fieldDef = fieldDefs.find(f => f.name === fieldName);
      if(!fieldDef || fieldDef.type === 'person' || fieldName === 'Amount' || fieldName === 'Currency') return '';
```

Remove the `|| fieldName === 'Currency'` arm (Amount's exclusion stays —
it still never participates in this system):

```js
    function capabilitiesHtml(fieldName){
      const fieldDef = fieldDefs.find(f => f.name === fieldName);
      if(!fieldDef || fieldDef.type === 'person' || fieldName === 'Amount') return '';
```

- [ ] **Step 5: Exclude Currency from the Reports breakdown-field options**

In `dossiary.html`, find `reportBreakdownFields()` (~line 3657-3660):

```js
  function reportBreakdownFields(){
    const fixed = FIELD_DEFS.filter(f => ['category', 'document_type', 'people'].includes(f.id));
    return [...fixed, ...dynamicColumnDefs()];
  }
```

Change to filter Currency out of the dynamic spread by name — Reports
already groups totals by Currency at the top level
(`computeReportGroups()`), so offering it again as a breakdown-within-a-
currency-group dimension would be redundant:

```js
  function reportBreakdownFields(){
    const fixed = FIELD_DEFS.filter(f => ['category', 'document_type', 'people'].includes(f.id));
    // Currency is deliberately excluded here (joining Date/Amount/Tags,
    // already excluded from dynamicColumnDefs()'s own callers for their own
    // reasons) -- Reports already groups totals by Currency at the top
    // level, so offering it again as a breakdown-within-a-currency-group
    // dimension would be redundant.
    return [...fixed, ...dynamicColumnDefs().filter(f => f.label !== 'Currency')];
  }
```

- [ ] **Step 6: Manual verification — new library**

Serve the repo (`python3 -m http.server` from the repo root) and open
`dossiary.html` in Chrome against a brand new library folder. Confirm:
Columns menu lists "Currency" (unchecked by default); Field Settings shows
Column/Autocomplete checkboxes for Currency (both checked) but none for
Amount; the toolbar's dynamic-filters area shows a Currency dropdown once
at least one document has a Currency value and the Currency column is
toggled visible (matching how Payment method's own dynamic filter
already only builds once a document has a value — this is pre-existing
`populateFilters()` behavior, unchanged here).

- [ ] **Step 7: Write the test file (Currency scenarios)**

Create `tests/test_amount_currency_filter.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

FILTER_UNSET = '__unset__'

# Doc 1: Amount 100, Currency EUR.
# Doc 2: Amount 250, Currency USD.
# Doc 3: Amount 500, Currency EUR.
# Doc 4: no Amount, no Currency saved at all (never had a
#        document_field_values row for either field).
# Doc 5: Amount explicitly saved as 0, Currency EUR -- real saved data,
#        must NOT match Amount's "not set" filter.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc 1 (100 EUR)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Doc 2 (250 USD)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-03-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Doc 3 (500 EUR)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-03-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 4, "title": "Doc 4 (no amount, no currency)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-04T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-03-04T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 5, "title": "Doc 5 (amount explicitly 0, EUR)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-05T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/5_e.pdf", "original_file_path": None,
            "created_at": "2026-03-05T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 2, "value": "100"},
        {"document_id": 1, "field_id": 3, "value": "EUR"},
        {"document_id": 2, "field_id": 2, "value": "250"},
        {"document_id": 2, "field_id": 3, "value": "USD"},
        {"document_id": 3, "field_id": 2, "value": "500"},
        {"document_id": 3, "field_id": 3, "value": "EUR"},
        {"document_id": 5, "field_id": 2, "value": "0"},
        {"document_id": 5, "field_id": 3, "value": "EUR"},
    ],
}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    stub_js = open('stub_studio2.js').read()
    await page.add_init_script(stub_js)

async def visible_ids(page):
    return sorted(await page.evaluate(
        "() => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)"
    ))

async def option_label(page, select_id, value):
    return await page.evaluate(f"""
        () => {{
            const opts = Array.from(document.querySelector('{select_id}').options);
            const opt = opts.find(o => o.value === '{value}');
            return opt ? opt.textContent : null;
        }}
    """)

async def read_db(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Scenario 1: Currency's own capability checkboxes render in Field
        # Settings (unlike Amount's, which stay hidden), confirming the
        # capabilitiesHtml() exclusion was removed for Currency only ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        currency_col_checkbox = page.locator('.fs-list-item[data-field="Currency"] .fs-col-toggle')
        amount_col_checkbox = page.locator('.fs-list-item[data-field="Amount"] .fs-col-toggle')
        currency_checkbox_count = await currency_col_checkbox.count()
        amount_checkbox_count = await amount_col_checkbox.count()
        assert currency_checkbox_count == 1, "Currency should have a Column capability checkbox in Field Settings"
        assert amount_checkbox_count == 0, "Amount should still have NO capability checkboxes in Field Settings"
        print("Currency has a Column checkbox, Amount does not:", currency_checkbox_count, amount_checkbox_count)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 2: Currency column appears in the Columns menu, hidden
        # by default, and toggling it on shows the right per-row values ===
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        currency_toggle = page.locator('#columns-menu input[type=checkbox]', has=page.locator('xpath=following-sibling::*[contains(text(), "Currency")]'))
        # Simpler: locate by the field's column id directly, same convention
        # test_generic_column_system.py already uses for dynamic fields.
        currency_col_toggle = page.locator('#col-toggle-field-3')
        assert await currency_col_toggle.count() == 1, "Currency should appear in the Columns menu as field-3"
        assert not await currency_col_toggle.is_checked(), "Currency column should be hidden by default"
        await page.check('#col-toggle-field-3')
        await page.wait_for_timeout(150)
        await page.click('#columns-btn')  # close the menu
        await page.wait_for_timeout(100)
        currency_cell_texts = await page.evaluate(
            "() => Array.from(document.querySelectorAll('#doc-tbody tr td[data-field=\\'field-3\\']')).map(td => td.textContent.trim())"
        )
        print("Currency column cell values (rows in DOM order):", currency_cell_texts)
        assert 'EUR' in currency_cell_texts and 'USD' in currency_cell_texts, f"Currency column should show real values, got {currency_cell_texts}"

        # Sorting by the new Currency column works -- proves it flows through
        # the existing generic sortKey.startsWith('field-') mechanism
        # (sortDocs()) with zero new sort code, same as any other
        # show_as_column text field.
        await page.click('th[data-key="field-3"]')
        await page.wait_for_timeout(150)
        ids_after_first_click = await page.evaluate(
            "() => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)"
        )
        await page.click('th[data-key="field-3"]')  # click again to flip direction
        await page.wait_for_timeout(150)
        ids_after_second_click = await page.evaluate(
            "() => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)"
        )
        assert ids_after_first_click != ids_after_second_click, \
            f"Clicking the Currency header a second time should reverse sort order, got {ids_after_first_click} both times"
        print("Sorting by the Currency column works (order flips on second click):", ids_after_first_click, "->", ids_after_second_click)

        # === Scenario 3: Currency filter dropdown lists distinct values plus
        # "not set", and selecting a value narrows correctly ===
        eur_label = await option_label(page, '#dyn-filter-field-3', 'EUR')
        assert eur_label == 'EUR', f"Currency filter should list EUR as an option, got {eur_label!r}"
        not_set_label = await option_label(page, '#dyn-filter-field-3', FILTER_UNSET)
        assert not_set_label is not None, "Currency filter is missing a '__unset__'-valued option"
        print("Currency filter has EUR and a 'Not set' option:", eur_label, not_set_label)

        await page.select_option('#dyn-filter-field-3', 'EUR')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '3', '5'], f"Currency=EUR should show docs 1, 3, 5, got {ids}"
        print("Currency=EUR filter shows docs 1, 3, 5:", ids)

        await page.select_option('#dyn-filter-field-3', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['4'], f"Currency 'not set' should show only doc 4, got {ids}"
        print("Currency 'not set' filter shows only doc 4:", ids)

        # === Scenario 4: a Smart Collection saved with a Currency filter
        # active reproduces the same filtering on its own saved criteria ===
        await page.select_option('#dyn-filter-field-3', 'EUR')
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.wait_for_timeout(150)
        await page.fill('#smart-collection-name-input', 'EUR Only')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(200)
        await page.select_option('#dyn-filter-field-3', '')
        await page.wait_for_timeout(150)

        smart_collection_nav = page.locator('.nav-item[data-view^="collection-"]', has_text='EUR Only')
        await smart_collection_nav.click()
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '3', '5'], f"'EUR Only' Smart Collection should show docs 1, 3, 5, got {ids}"
        print("Smart Collection saved with a Currency filter correctly reproduces it:", ids)

        # === Scenario 5: Reports' breakdown-field dropdown does NOT list
        # Currency as an option (it's already the top-level grouping) ===
        await page.click('.nav-item[data-view="reports"]')
        await page.wait_for_timeout(200)
        breakdown_options = await page.evaluate(
            "() => Array.from(document.querySelector('#report-breakdown-field').options).map(o => o.textContent)"
        )
        assert 'Currency' not in breakdown_options, f"Currency should not be a Reports breakdown option, got {breakdown_options}"
        print("Reports breakdown dropdown correctly excludes Currency:", breakdown_options)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 8: Run the test**

Run: `cd tests && /usr/local/bin/python3 test_amount_currency_filter.py`
(substitute whichever `python3` on this machine has Playwright installed
and its Chromium browser downloaded — check with `python3 -m pip show
playwright` first if unsure which interpreter to use.)

Expected: every `assert` passes, `JS ERRORS: []`, script exits 0.

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_amount_currency_filter.py
git commit -m "Let Currency opt into the generic column/filter/autocomplete system"
```

---

### Task 2: Amount range filter, "not set" checkbox, and i18n

**Files:**
- Modify: `dossiary.html` — toolbar markup (~line 540), CSS (~line 367-369),
  DOM element consts (~line 2084-2085), `currentFilters()` (~line 3776-3781),
  `matchesCriteria()` (~line 3788-3815), the static wiring block (~line
  4123-4130), and all six `STRINGS` blocks.
- Modify: `tests/test_amount_currency_filter.py` (append new scenarios to
  the file Task 1 created).

**Interfaces:**
- Consumes: Task 1's `SEED`/helper functions in
  `tests/test_amount_currency_filter.py` (this task's steps append to
  `main()` before `print("JS ERRORS:", errors)` and `await browser.close()`
  — do not duplicate the file's boilerplate). Consumes Currency already
  being `show_as_column: 1` (Task 1) so the combined-filter scenario below
  has a working Currency filter to compose with.
- Produces: nothing further consumed by any later task — this is the last
  task in the plan.

- [ ] **Step 1: Add the toolbar markup**

In `dossiary.html`, find (~line 540):

```html
        <span id="dynamic-filters"></span>
        <label class="show-archived-toggle" id="show-archived-wrap">
          <input type="checkbox" id="show-archived-toggle" /> <span data-i18n="toolbarShowArchived">Show archived</span>
        </label>
```

Insert the new controls between them:

```html
        <span id="dynamic-filters"></span>
        <span class="amount-filter-range" id="amount-filter-range-wrap">
          <input type="number" id="amount-filter-min" step="0.01" data-i18n-title="toolbarAmountMinTitle" data-i18n-placeholder="toolbarAmountMinTitle" title="Min amount" placeholder="Min amount" />
          <span>–</span>
          <input type="number" id="amount-filter-max" step="0.01" data-i18n-title="toolbarAmountMaxTitle" data-i18n-placeholder="toolbarAmountMaxTitle" title="Max amount" placeholder="Max amount" />
        </span>
        <label class="show-archived-toggle" id="amount-filter-unset-wrap">
          <input type="checkbox" id="amount-filter-unset" /> <span data-i18n="toolbarAmountUnsetLabel">Amount not set</span>
        </label>
        <label class="show-archived-toggle" id="show-archived-wrap">
          <input type="checkbox" id="show-archived-toggle" /> <span data-i18n="toolbarShowArchived">Show archived</span>
        </label>
```

The "not set" checkbox reuses the existing `.show-archived-toggle` CSS
class directly (same flex/gap/mono-font styling already defined for it) —
no new CSS needed for that piece, only for the number-input pair below.

- [ ] **Step 2: Add CSS for the range inputs**

In `dossiary.html`, find (~line 367-369):

```css
  .report-date-range{ display:flex; align-items:center; gap:6px; }
  .report-date-range input[type=date]{ color-scheme:dark; background:var(--ink-2); border:1px solid var(--line); color:var(--text); font-family:var(--font-mono); font-size:12px; padding:7px 9px; border-radius:var(--radius); }
  .report-date-range span{ color:var(--text-dim); font-family:var(--font-mono); font-size:12px; }
```

Add a parallel block directly below it:

```css
  .amount-filter-range{ display:flex; align-items:center; gap:6px; }
  .amount-filter-range input[type=number]{ width:90px; background:var(--ink-2); border:1px solid var(--line); color:var(--text); font-family:var(--font-mono); font-size:12px; padding:7px 9px; border-radius:var(--radius); }
  .amount-filter-range input[type=number]:disabled{ opacity:0.4; }
  .amount-filter-range span{ color:var(--text-dim); font-family:var(--font-mono); font-size:12px; }
```

- [ ] **Step 3: Cache the new DOM elements**

In `dossiary.html`, find (~line 2084-2085):

```js
  const reportDateFrom = el('report-date-from');
  const reportDateTo = el('report-date-to');
```

Add directly below:

```js
  const reportDateFrom = el('report-date-from');
  const reportDateTo = el('report-date-to');
  const amountFilterMin = el('amount-filter-min');
  const amountFilterMax = el('amount-filter-max');
  const amountFilterUnset = el('amount-filter-unset');
```

- [ ] **Step 4: Extend `currentFilters()`**

In `dossiary.html`, find `currentFilters()` (~line 3776-3781):

```js
  function currentFilters(){
    const dynamic = [...document.querySelectorAll('#dynamic-filters select')]
      .map(sel => ({ label: sel.dataset.fieldLabel, value: sel.value }))
      .filter(f => f.value);
    return { q: (searchInput.value || '').trim().toLowerCase(), category: categoryFilter.value, type: typeFilter.value, person: personFilter.value, showArchived: showArchivedToggle.checked, dynamic };
  }
```

Change to:

```js
  function currentFilters(){
    const dynamic = [...document.querySelectorAll('#dynamic-filters select')]
      .map(sel => ({ label: sel.dataset.fieldLabel, value: sel.value }))
      .filter(f => f.value);
    return {
      q: (searchInput.value || '').trim().toLowerCase(), category: categoryFilter.value, type: typeFilter.value,
      person: personFilter.value, showArchived: showArchivedToggle.checked, dynamic,
      amountMin: amountFilterMin.value, amountMax: amountFilterMax.value, amountUnset: amountFilterUnset.checked,
    };
  }
```

- [ ] **Step 5: Extend `matchesCriteria()`**

In `dossiary.html`, find `matchesCriteria()` (~line 3788-3808):

```js
  function matchesCriteria(d, criteria){
    const { q, category, type, person, dynamic } = criteria;
    if(category){
      if(category === FILTER_UNSET ? !!d.category : d.category !== category) return false;
    }
    if(type){
      if(type === FILTER_UNSET ? !!d.document_type : d.document_type !== type) return false;
    }
    if(person){
      if(person === FILTER_UNSET ? (d.people||[]).length > 0 : !(d.people||[]).includes(person)) return false;
    }
    for(const f of dynamic){
```

Change to:

```js
  function matchesCriteria(d, criteria){
    const { q, category, type, person, dynamic, amountMin, amountMax, amountUnset } = criteria;
    if(category){
      if(category === FILTER_UNSET ? !!d.category : d.category !== category) return false;
    }
    if(type){
      if(type === FILTER_UNSET ? !!d.document_type : d.document_type !== type) return false;
    }
    if(person){
      if(person === FILTER_UNSET ? (d.people||[]).length > 0 : !(d.people||[]).includes(person)) return false;
    }
    // amountMin/amountMax/amountUnset may be entirely absent on criteria
    // saved by a Smart Collection created before this filter existed --
    // normalize to the same "inactive" defaults currentFilters() itself
    // always supplies now, so an old saved collection's behavior is
    // unchanged rather than suddenly excluding every document with no
    // Amount value.
    const amtUnset = !!amountUnset;
    const amtMin = amountMin || '';
    const amtMax = amountMax || '';
    if(amtUnset){
      // Deliberately checking the raw stored value, NOT formatAmount()'s
      // "0 or NaN displays as --" rule -- a document with Amount explicitly
      // saved as 0 has real, meaningful saved data (same
      // checkbox-'0'-is-not-unset distinction the dynamic-fields loop just
      // below already enforces for every other field); only a document
      // with no document_field_values row for Amount at all counts as
      // "not set."
      if((d.customFields || {})['Amount'] !== undefined) return false;
    } else if(amtMin !== '' || amtMax !== ''){
      const raw = (d.customFields || {})['Amount'];
      const amt = raw != null && raw !== '' ? parseFloat(raw) : NaN;
      if(isNaN(amt)) return false;
      if(amtMin !== '' && amt < parseFloat(amtMin)) return false;
      if(amtMax !== '' && amt > parseFloat(amtMax)) return false;
    }
    for(const f of dynamic){
```

(The rest of the function, from the `dynamic` loop onward, is unchanged.)

- [ ] **Step 6: Wire the new controls**

In `dossiary.html`, find (~line 4128-4130):

```js
  showArchivedToggle.addEventListener('change', render);
  reportDateFrom.addEventListener('change', render);
  reportDateTo.addEventListener('change', render);
```

Add directly below:

```js
  showArchivedToggle.addEventListener('change', render);
  reportDateFrom.addEventListener('change', render);
  reportDateTo.addEventListener('change', render);
  // "Not set" and the min/max range are mutually exclusive states -- a
  // document can't simultaneously have no Amount and have one within a
  // range -- so typing into either number input unchecks "not set" (and
  // re-enables both inputs), and checking "not set" clears and disables
  // both.
  amountFilterMin.addEventListener('input', () => { amountFilterUnset.checked = false; render(); });
  amountFilterMax.addEventListener('input', () => { amountFilterUnset.checked = false; render(); });
  amountFilterUnset.addEventListener('change', () => {
    amountFilterMin.disabled = amountFilterMax.disabled = amountFilterUnset.checked;
    if(amountFilterUnset.checked){ amountFilterMin.value = ''; amountFilterMax.value = ''; }
    render();
  });
```

- [ ] **Step 7: Add the three new i18n keys to all six `STRINGS` blocks**

In `dossiary.html`, each language block has a line ending in
`toolbarToDateTitle: '...'` (English at ~line 712, Spanish ~871, French
~1030, German ~1189, Chinese Simplified ~1348). For those five, add the
three new keys directly after that line, packed onto their own line
matching the surrounding style:

English (~line 712):
```js
      toolbarFromDateTitle: 'From date', toolbarToDateTitle: 'To date',
      toolbarAmountMinTitle: 'Min amount', toolbarAmountMaxTitle: 'Max amount', toolbarAmountUnsetLabel: 'Amount not set',
```

Spanish (~line 871):
```js
      toolbarFromDateTitle: 'Desde fecha', toolbarToDateTitle: 'Hasta fecha',
      toolbarAmountMinTitle: 'Importe mín.', toolbarAmountMaxTitle: 'Importe máx.', toolbarAmountUnsetLabel: 'Importe sin definir',
```

French (~line 1030):
```js
      toolbarFromDateTitle: 'Date de début', toolbarToDateTitle: 'Date de fin',
      toolbarAmountMinTitle: 'Montant min.', toolbarAmountMaxTitle: 'Montant max.', toolbarAmountUnsetLabel: 'Montant non défini',
```

German (~line 1189):
```js
      toolbarFromDateTitle: 'Von Datum', toolbarToDateTitle: 'Bis Datum',
      toolbarAmountMinTitle: 'Betrag min.', toolbarAmountMaxTitle: 'Betrag max.', toolbarAmountUnsetLabel: 'Betrag nicht gesetzt',
```

Chinese Simplified (~line 1348):
```js
      toolbarFromDateTitle: '起始日期', toolbarToDateTitle: '结束日期',
      toolbarAmountMinTitle: '最小金额', toolbarAmountMaxTitle: '最大金额', toolbarAmountUnsetLabel: '金额未设置',
```

Chinese Traditional (`zh-Hant`, ~line 1526-1527) uses one key per line
(matching its own existing style, since it's derived from `zh-Hans` via
OpenCC rather than packed like the other five blocks):

```js
      toolbarFromDateTitle: '起始日期',
      toolbarToDateTitle: '結束日期',
      toolbarAmountMinTitle: '最小金額',
      toolbarAmountMaxTitle: '最大金額',
      toolbarAmountUnsetLabel: '金額未設置',
```

Currency's own "All Currencies" option needs no new key at all — it
flows through the existing dynamic filter template
(`populateFilters()`, unchanged by this task), which already reuses
`toolbarAllDynamic` with `{label}`, exactly like Payment method's filter
already does today.

- [ ] **Step 8: Run the i18n coverage check**

Run: `cd tests && /usr/local/bin/python3 test_i18n_coverage.py`
Expected: passes with all six languages reporting exact key parity (273 +
3 = 276 keys per language) — no test-file changes needed there, this is a
static grep-based check that discovers new `data-i18n*`/`t('key')`
references automatically.

- [ ] **Step 9: Manual verification**

Open the app against a library with documents that have a spread of
Amount values (some set, some not, one explicitly `0`). Confirm: typing a
min narrows the table to Amount ≥ min; typing a max narrows to Amount ≤
max; typing both narrows to the range; checking "Amount not set" greys
out and clears both number inputs and shows only documents with no saved
Amount; typing into either number input while "not set" is checked
unchecks it and re-enables both inputs.

- [ ] **Step 10: Append the Amount + combined test scenarios**

Open `tests/test_amount_currency_filter.py` (created in Task 1). Insert
the following scenarios directly before the existing:

```python
        print("JS ERRORS:", errors)
        await browser.close()
```

lines at the end of `main()`, i.e. immediately after Task 1's Scenario 5
block:

```python
        # === Scenario 6: Amount range filter -- min only, max only, both,
        # and an empty-result min>max case. Filters composed here on top of
        # docs 1/2/3/5 (100/250/500/0, doc 4 has no Amount at all and is
        # correctly excluded from every range comparison below since NaN
        # never satisfies a >= / <= comparison) ===
        await page.click('.nav-item[data-view="all"]')
        await page.wait_for_timeout(150)

        await page.fill('#amount-filter-min', '200')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2', '3'], f"Amount min=200 should show docs 2, 3, got {ids}"
        print("Amount min=200 shows docs 2, 3:", ids)

        await page.fill('#amount-filter-min', '')
        await page.fill('#amount-filter-max', '200')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '5'], f"Amount max=200 should show docs 1, 5 (0 and 100), got {ids}"
        print("Amount max=200 shows docs 1, 5:", ids)

        await page.fill('#amount-filter-min', '100')
        await page.fill('#amount-filter-max', '300')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '2'], f"Amount 100-300 should show docs 1, 2, got {ids}"
        print("Amount range 100-300 shows docs 1, 2:", ids)

        await page.fill('#amount-filter-min', '300')
        await page.fill('#amount-filter-max', '100')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == [], f"Amount min>max should show zero results, got {ids}"
        print("Amount min=300/max=100 (min>max) correctly shows zero results:", ids)

        await page.fill('#amount-filter-min', '')
        await page.fill('#amount-filter-max', '')
        await page.wait_for_timeout(150)

        # === Scenario 7: "Amount not set" matches only doc 4 -- critically
        # NOT doc 5, whose Amount is explicitly saved as 0 (real data) ===
        await page.check('#amount-filter-unset')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['4'], f"Amount 'not set' should show only doc 4 (not doc 5, whose Amount=0 is real data), got {ids}"
        print("Amount 'not set' filter shows only doc 4, correctly excluding doc 5's explicit 0:", ids)

        min_disabled = await page.locator('#amount-filter-min').is_disabled()
        max_disabled = await page.locator('#amount-filter-max').is_disabled()
        assert min_disabled and max_disabled, "Min/max inputs should be disabled while 'not set' is checked"
        print("Min/max inputs disabled while 'not set' is checked:", min_disabled, max_disabled)

        # === Scenario 8: typing into a number input unchecks "not set" and
        # re-enables both inputs ===
        await page.evaluate("() => { document.getElementById('amount-filter-min').disabled = false; }")
        await page.fill('#amount-filter-min', '100')
        await page.wait_for_timeout(150)
        unset_checked = await page.locator('#amount-filter-unset').is_checked()
        assert not unset_checked, "'Not set' should uncheck itself once a min/max value is typed"
        max_disabled_after = await page.locator('#amount-filter-max').is_disabled()
        assert not max_disabled_after, "Max input should be re-enabled once 'not set' unchecks itself"
        print("Typing into min unchecks 'not set' and re-enables max:", unset_checked, max_disabled_after)
        await page.fill('#amount-filter-min', '')
        await page.wait_for_timeout(150)

        # === Scenario 9: Currency filter AND Amount "not set" compose
        # correctly with plain AND -- no dedicated combo code exists, this
        # proves matchesCriteria()'s existing composition already covers it ===
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        await page.click('#columns-btn')  # Currency column already toggled on in Scenario 2; just closing any stray open menu state
        await page.wait_for_timeout(100)
        await page.select_option('#dyn-filter-field-3', 'EUR')
        await page.check('#amount-filter-unset')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == [], f"Currency=EUR AND Amount not set should show zero results (doc 4 has no Currency saved either), got {ids}"
        print("Currency=EUR AND Amount-not-set correctly composes to zero results:", ids)
        await page.select_option('#dyn-filter-field-3', '')
        await page.uncheck('#amount-filter-unset')
        await page.wait_for_timeout(150)
```

Note on Scenario 9's expected result: doc 4 is the only document with no
Amount, but it also has no Currency saved at all, so it fails the
`Currency=EUR` half of the AND — the assertion is deliberately `== []`,
not a document that happens to satisfy both, since this SEED has no such
document. This still proves the composition works (a real combined match
is exercised structurally by `matchesCriteria()`'s shared code path,
already covered independently by Scenario 6/7's own passing assertions
against the same predicate) without needing a sixth seeded document.

- [ ] **Step 11: Append the backfill-migration idempotency scenario**

Playwright can't run two independently-seeded libraries in one `page`
session without a reload that would lose Task 1/2's live filter state, so
this scenario uses its own dedicated `main()`-style block. Append this as
a **second, independent script** at the very end of
`tests/test_amount_currency_filter.py`, after `asyncio.run(main())`:

```python
# === Second, independent scenario: the backfill migration
# (migrateCurrencyColumnDefault()) correctly flips Currency's
# show_as_column/autocomplete from 0/0 to 1/1 for a library that already
# ran the OLD migrateSentinelFieldsToGeneric() before this feature existed
# -- and, critically, does NOT re-flip it if a person already manually
# turned it back off in Field Settings after an earlier run of this same
# backfill (idempotency, same property migrateTextFieldsAutocompleteDefault()'s
# own test already covers for its own migration) ===
BACKFILL_SEED = {
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 0, "autocomplete": 0},
    ],
}

ALREADY_MIGRATED_BUT_MANUALLY_OFF_SEED = {
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 0, "autocomplete": 0},
    ],
    "settings": [
        {"key": "currency_column_default_migrated", "value": "1"},
    ],
}

async def read_db(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)

async def backfill_main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        errors = []

        # --- Case A: pre-migration shape, no marker row yet -- gets flipped ---
        # Reuses route_stub(), defined earlier in this same file for main()'s
        # own page -- no need to duplicate the routing/stub-loading logic here.
        page = await browser.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(BACKFILL_SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)
        persisted = await read_db(page)
        currency_field = next(f for f in persisted['fields'] if f['name'] == 'Currency')
        assert currency_field['show_as_column'] == 1 and currency_field['autocomplete'] == 1, \
            f"Currency should be backfilled to show_as_column=1, autocomplete=1, got {currency_field}"
        marker = next((s for s in persisted['settings'] if s['key'] == 'currency_column_default_migrated'), None)
        assert marker is not None and marker['value'] == '1', "Migration marker should be persisted after the backfill runs"
        print("Case A: pre-migration Currency field correctly backfilled to show_as_column=1, autocomplete=1:", currency_field)
        await page.close()

        # --- Case B: already migrated once, then manually turned back off --
        # a reopen must NOT silently re-enable it ---
        page2 = await browser.new_page()
        page2.on("pageerror", lambda exc: errors.append(str(exc)))
        await route_stub(page2)
        await page2.goto(f"file://{APP_PATH}")
        await page2.wait_for_timeout(200)
        await page2.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(ALREADY_MIGRATED_BUT_MANUALLY_OFF_SEED)});")
        await page2.click("#open-btn")
        await page2.wait_for_timeout(400)
        persisted2 = await read_db(page2)
        currency_field2 = next(f for f in persisted2['fields'] if f['name'] == 'Currency')
        assert currency_field2['show_as_column'] == 0, \
            f"A library already past the migration marker, with Currency manually turned back off, should stay off, got {currency_field2}"
        print("Case B: manually-turned-off Currency stays off across reopen (migration marker already present):", currency_field2)
        await page2.close()

        print("JS ERRORS (backfill scenarios):", errors)
        await browser.close()

asyncio.run(backfill_main())
```

- [ ] **Step 12: Run the full test file**

Run: `cd tests && /usr/local/bin/python3 test_amount_currency_filter.py`
Expected: every `assert` in both `main()` and `backfill_main()` passes,
both `JS ERRORS` prints are `[]`, script exits 0.

- [ ] **Step 13: Run the full existing suite to confirm no regressions**

Run:
```bash
cd tests
for f in test_*.py; do /usr/local/bin/python3 "$f" || echo "FAILED: $f"; done
```
Expected: no `FAILED:` lines. This project's own `CLAUDE.md` for `tests/`
notes each script is standalone (no shared runner needed) — this loop is
just a convenient way to run all of them in sequence.

- [ ] **Step 14: Commit**

```bash
git add dossiary.html tests/test_amount_currency_filter.py
git commit -m "Add Amount range filter and 'not set' checkbox to the toolbar"
```
