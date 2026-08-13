# Default Sort (Import Date) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the document table's sort a real, per-library persisted preference (mirroring `nav_style`), defaulting to `import_date` descending instead of the current session-only `date` descending default.

**Architecture:** Two new `settings` keys (`sort_key`, `sort_dir`) with `loadSortState()`/`saveSortState()` functions mirroring `loadNavStyle()`/`saveNavStyle()` exactly. The existing column-header click handler is extended to call `saveSortState()` on every change, and to default "Imported" to descending on first click (matching "Date"'s existing special case).

**Tech Stack:** Vanilla JS in `dossiary.html` (no build step, no framework). Tests are standalone Playwright/Python scripts in `tests/`.

## Global Constraints

- Single file (`dossiary.html`) — no build step, no new `<script src>` dependencies.
- No schema change — `settings` is already a generic key/value table (`CREATE TABLE IF NOT EXISTS`), so no `SCHEMA_MIGRATIONS` entry is needed for these two new keys, same as `nav_style`/`collections_nav_expanded`/`default_document_type`/`default_currency`.
- No change to `sortDocs()`'s comparison logic itself (its `date`/`amount`/`field-*`/generic-fallback branches are all unchanged) — only which key/direction is active by default and whether the choice persists.
- No new sortable column — `<th data-key="import_date">` already exists and is already wired through the existing delegated click listener.
- An old-shape library with no `sort_key`/`sort_dir` rows must read back using the new defaults (`import_date`/`desc`), not error.

---

## Task 1: Persisted default sort, defaulting to Import date descending

**Files:**
- Modify: `dossiary.html:769-770` (module-level `sortKey`/`sortDir` initial values)
- Modify: `dossiary.html:1423` (`loadDocumentsFromDb()` — add `loadSortState()` call)
- Modify: `dossiary.html:1494` area (insert `loadSortState()`/`saveSortState()` right after `loadNavStyle()`/before `applyNavStyle()`)
- Modify: `dossiary.html:2759-2766` (column-header click handler)
- Test: `tests/test_default_sort.py` (new file)

**Interfaces:**
- Consumes: `queryAll(sql)` (returns `{columns, rows}`, pre-existing, unchanged), `db.run(sql, params)` (pre-existing), `persistDb()` (pre-existing), `render()` (pre-existing), `sortKey`/`sortDir` (existing module-level `let`s).
- Produces: `loadSortState()` — no parameters, no return value, sets module-level `sortKey`/`sortDir` from `settings` (or defaults). `saveSortState(key, dir)` — `async`, sets module-level `sortKey`/`sortDir`, persists both to `settings`, no return value. No later task depends on these (this is the only task in this plan).

- [ ] **Step 1: Write the new test file**

Create `tests/test_default_sort.py`. Three documents with deliberately different relative orderings between `date` and `import_date`, so the test can prove which field is actually driving the sort (not just that "some" sort happened):

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Content date (`date`) and import date (`import_date`) deliberately run in
# DIFFERENT relative orders across these three documents, so a test can prove
# which field is actually driving the active sort, not just that some sort
# happened to change the row order:
#   date desc order:        doc 3, doc 2, doc 1  (2026-01-03, -02, -01)
#   import_date desc order: doc 1, doc 3, doc 2  (2026-03-03, -02, -01)
SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc One", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-01T00:00:00+00:00", "import_date": "2026-03-03T00:00:00+00:00",
            "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Doc Two", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-02T00:00:00+00:00", "import_date": "2026-03-01T00:00:00+00:00",
            "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-01-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Doc Three", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-03T00:00:00+00:00", "import_date": "2026-03-02T00:00:00+00:00",
            "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
}

async def read_settings(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text()).settings;
        })()
    """)

async def row_order(page):
    return await page.evaluate("""
        () => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)
    """)

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: a library with no sort_key/sort_dir settings rows (this one
        # was never seeded with any) opens sorted by Import date, newest first -- the
        # new default -- not the old 'date' descending default ===
        imported_th_active = await page.locator('th[data-key="import_date"]').get_attribute('class')
        print("Imported column header is active by default:", 'active' in (imported_th_active or ''))
        order_on_open = await row_order(page)
        print("rows open in import_date-desc order (doc1, doc3, doc2):", order_on_open)

        # === Scenario 2: clicking "Date" switches the sort and persists the choice ===
        await page.click('th[data-key="date"]')
        await page.wait_for_timeout(150)
        order_after_date_click = await row_order(page)
        print("rows reorder to date-desc order (doc3, doc2, doc1) after clicking Date:", order_after_date_click)
        settings_after_date_click = await read_settings(page)
        sort_key_row = next((s for s in settings_after_date_click if s['key'] == 'sort_key'), None)
        sort_dir_row = next((s for s in settings_after_date_click if s['key'] == 'sort_dir'), None)
        print("sort_key persisted as 'date':", sort_key_row['value'] if sort_key_row else None)
        print("sort_dir persisted as 'desc':", sort_dir_row['value'] if sort_dir_row else None)

        # === Scenario 3: clicking "Imported" while some other column is active defaults
        # to descending (newest-imported-first), not the generic ascending-by-default
        # every other non-Date column uses ===
        await page.click('th[data-key="import_date"]')
        await page.wait_for_timeout(150)
        order_after_imported_click = await row_order(page)
        print("rows reorder to import_date-desc order (doc1, doc3, doc2) on first click of Imported:", order_after_imported_click)
        settings_after_imported_click = await read_settings(page)
        sort_dir_row2 = next((s for s in settings_after_imported_click if s['key'] == 'sort_dir'), None)
        print("sort_dir persisted as 'desc' after first click of Imported:", sort_dir_row2['value'] if sort_dir_row2 else None)

        # === Scenario 4: reopening the library keeps the persisted sort -- 'date' desc
        # was the last explicit choice recorded on disk before this reopen (clicking
        # Imported above changed the LIVE in-memory state further, but this step
        # simulates a real reopen by re-seeding a fresh root with 'date'/'desc'
        # explicitly persisted, proving a real reopen reads settings back rather than
        # reverting to the import_date/desc default) ===
        seed_with_sort = dict(SEED)
        seed_with_sort['settings'] = [
            {'key': 'sort_key', 'value': 'date'},
            {'key': 'sort_dir', 'value': 'desc'},
        ]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_sort)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        date_th_active_after_reopen = await page.locator('th[data-key="date"]').get_attribute('class')
        print("Date column header is active after reopening with 'date'/'desc' persisted:", 'active' in (date_th_active_after_reopen or ''))
        order_after_reopen = await row_order(page)
        print("rows still in date-desc order (doc3, doc2, doc1) after reopening:", order_after_reopen)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run the test to verify it fails against the current (unmodified) app**

Run: `cd tests && python3 test_default_sort.py`

Expected: FAIL/incorrect output — the table opens sorted by `date` descending (the current default), not `import_date`, so `order_on_open` will print `['3', '2', '1']` instead of the expected `['1', '3', '2']`, and `imported_th_active` will show no `active` class. Clicking headers won't produce any `sort_key`/`sort_dir` settings rows at all, since nothing persists sort state yet. Confirm the run does not cleanly print the full expected sequence — this is the "red" step.

- [ ] **Step 3: Update the module-level initial values**

Find (`dossiary.html`, currently around lines 769-770):

```js
  let sortKey = 'date';
  let sortDir = 'desc';
```

Replace with:

```js
  let sortKey = 'import_date'; // overwritten by loadSortState() on every library open -- this is just the pre-library-open starting value
  let sortDir = 'desc';
```

- [ ] **Step 4: Add `loadSortState()`/`saveSortState()`**

Find (`dossiary.html`, currently around lines 1494-1498):

```js
  function loadNavStyle(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'nav_style'").rows;
    navStyle = (rows.length && rows[0][0] === 'tabs') ? 'tabs' : 'sidebar';
    applyNavStyle();
  }
```

Replace with (inserts the two new functions right after `loadNavStyle()`):

```js
  function loadNavStyle(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'nav_style'").rows;
    navStyle = (rows.length && rows[0][0] === 'tabs') ? 'tabs' : 'sidebar';
    applyNavStyle();
  }

  // Mirrors loadNavStyle()/saveNavStyle() exactly. Defaults to import_date/desc
  // when no sort_key/sort_dir rows exist yet -- covers both a fresh library and
  // an existing library that predates this feature, same as default_document_type/
  // default_currency's own unset-defaults-quietly behavior. import_date is always
  // set (unlike date, which Inbox-imported documents leave NULL until reviewed --
  // see sortDocs()'s own date-branch null handling), so it needs no special
  // fallback here the way date's own comparator does.
  function loadSortState(){
    const keyRows = queryAll("SELECT value FROM settings WHERE key = 'sort_key'").rows;
    const dirRows = queryAll("SELECT value FROM settings WHERE key = 'sort_dir'").rows;
    sortKey = keyRows.length ? keyRows[0][0] : 'import_date';
    sortDir = (dirRows.length && dirRows[0][0] === 'asc') ? 'asc' : 'desc';
  }

  async function saveSortState(key, dir){
    sortKey = key;
    sortDir = dir;
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('sort_key', ?)", [key]);
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('sort_dir', ?)", [dir]);
    await persistDb();
  }
```

- [ ] **Step 5: Call `loadSortState()` from `loadDocumentsFromDb()`**

Find (`dossiary.html`, currently around line 1423):

```js
    loadNavStyle();
```

Replace with:

```js
    loadNavStyle();
    loadSortState();
```

- [ ] **Step 6: Update the column-header click handler**

Find (`dossiary.html`, currently around lines 2759-2766):

```js
  el('doc-thead-row').addEventListener('click', (e) => {
    const th = e.target.closest('th[data-key]');
    if(!th) return;
    const key = th.dataset.key;
    if(sortKey === key){ sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }
    else{ sortKey = key; sortDir = key === 'date' ? 'desc' : 'asc'; }
    render();
  });
```

Replace with:

```js
  el('doc-thead-row').addEventListener('click', (e) => {
    const th = e.target.closest('th[data-key]');
    if(!th) return;
    const key = th.dataset.key;
    let newKey = sortKey, newDir = sortDir;
    if(sortKey === key){ newDir = sortDir === 'asc' ? 'desc' : 'asc'; }
    else{ newKey = key; newDir = (key === 'date' || key === 'import_date') ? 'desc' : 'asc'; }
    saveSortState(newKey, newDir);
    render();
  });
```

- [ ] **Step 7: Run the test again to verify it passes**

Run: `cd tests && python3 test_default_sort.py`

Expected: every printed line reflects success — `Imported column header is active by default: True`, `rows open in import_date-desc order (doc1, doc3, doc2): ['1', '3', '2']`, `rows reorder to date-desc order (doc3, doc2, doc1) after clicking Date: ['3', '2', '1']`, `sort_key persisted as 'date': date`, `sort_dir persisted as 'desc': desc`, `rows reorder to import_date-desc order (doc1, doc3, doc2) on first click of Imported: ['1', '3', '2']`, `sort_dir persisted as 'desc' after first click of Imported: desc`, `Date column header is active after reopening with 'date'/'desc' persisted: True`, `rows still in date-desc order (doc3, doc2, doc1) after reopening: ['3', '2', '1']`, and `JS ERRORS: []`.

- [ ] **Step 8: Run the full regression suite**

```bash
cd tests
for f in test_*.py; do python3 "$f" > /tmp/out_$f.txt 2>&1 || echo "FAILED: $f"; done
```

Expected: no `FAILED:` lines (53 test files total after this — `test_default_sort.py` is new). Pay particular attention to any existing test that clicks a column header or asserts on row order without expecting the new persist-on-click behavior — if any such test fails, read its actual output before assuming the new code is wrong; it may be a test that never seeded `sort_key`/`sort_dir` and is now correctly seeing the new `import_date` default instead of the old `date` default for the first time.

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_default_sort.py
git commit -m "Persist the document table's sort preference, defaulting to Import date (newest first)"
```

---

## Self-Review

**Spec coverage:**
- Two new `settings` keys with `loadSortState()`/`saveSortState()` mirroring `nav_style`'s pattern — Steps 3-4, covered.
- `loadSortState()` called once per library open, alongside `loadNavStyle()` — Step 5, covered.
- Column-header click handler: "Imported" defaults to descending on first click; every sort change persists — Step 6, covered.
- No special handling needed on library switch (matches how `navStyle` isn't reset in `resetAll()` either) — nothing in this plan touches `resetAll()`, matching the spec's explicit statement that no such handling is needed.
- No schema migration — confirmed, this plan only adds `INSERT OR REPLACE` calls against the existing `settings` table, no `SCHEMA_MIGRATIONS` entry.
- No change to `sortDocs()`'s comparison logic — confirmed, nothing in this plan touches that function.
- Old-shape library (no `sort_key`/`sort_dir` rows) reads back using the new defaults rather than erroring — `loadSortState()`'s `keyRows.length ? ... : 'import_date'` fallback covers this exactly, and Scenario 1 in the test (a library seeded with zero settings rows) exercises it directly.

**Placeholder scan:** No TBD/TODO, no "add appropriate error handling," no "similar to Task N" (single task), no undefined references — every code block is the actual, complete text to write or the actual current text to find.

**Type consistency:** `loadSortState()` takes no parameters and returns nothing; `saveSortState(key, dir)` takes two strings and returns nothing (async). Both are called with the same names/shapes at their two call sites (Step 5 and Step 6) as defined in Step 4.
