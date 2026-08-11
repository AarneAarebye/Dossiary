# Reports View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 4th top-level nav view, "Reports," that totals Dossiary's documents by a chosen breakdown dimension (Category/Type/People/any custom field), grouped by currency, with a date-range filter and a print-friendly layout.

**Architecture:** Everything lives in the existing single-file `dossiary.html` — a new `.nav-item`/`data-view="reports"` plugs into the existing `currentView`/`matchesView()`/`renderNav()`/`setView()` machinery the same way `'all'`/`'inbox'`/`'trash'` already do; `render()` gains a branch that, for `currentView === 'reports'`, hides the document table and renders grouped totals into a new `#reports-view` container instead. No schema changes, no new dependencies, no server.

**Tech Stack:** Vanilla JS (no framework), sql.js (unused by this feature — read-only over already-loaded `allDocs`), Playwright + the shared `tests/stub_studio2.js` fake-browser-API stub for testing.

## Global Constraints

- Single file: all production changes go in `dossiary.html`. No build step, no new `<script src>` dependency.
- Reports **always** includes archived and needs-review documents; only `deleted` (Waste bin) is excluded — per the approved spec's `matchesView()` design, this is not configurable.
- Amount totals are **grouped by Currency and never summed across different currency labels.**
- The breakdown dropdown's field list is exactly `{category, document_type, people}` (from `FIELD_DEFS`) plus `dynamicColumnDefs()` — **not** `date`, `import_date`, `amount`, or `tags`.
- A document with more than one value for a multi-valued breakdown field (People, or a custom person-type field) contributes its full Amount to **every** value's row — rows may not sum to the currency's own grand total, and the UI must say so.
- Every new test file must load `tests/stub_studio2.js` (never an embedded copy) — this is an existing, strictly-enforced convention in this repo (see `CLAUDE.md`'s "How this was tested" section).
- Follow this repo's existing test style exactly: one standalone Python script per feature (not per task), `print()`-based observation (no `assert` on behavior — only used for hard setup failures), driven with real Playwright clicks/fills against the real DOM, seeded via `window.__makeSeededRoot(SEED)`.
- **`tests/test_reports.py` is one evolving file across all four tasks that touch it** — each task extends the same `SEED` dict and appends new scenarios before the final `print("JS ERRORS:", errors)` line; it does not create a new file per task. The full, final document set (used from Task 3 onward) is:

  | id | state | category | type | date | currency | amount | people |
  |----|-------|----------|------|------|----------|--------|--------|
  | 1 | active | Travel | Receipt | 2026-03-01 | EUR | 45.00 | Alice, Bob |
  | 2 | archived | Travel | Receipt | 2026-02-01 | EUR | 30.00 | Alice |
  | 3 | deleted | Travel | Receipt | 2026-01-01 | — | — | — |
  | 4 | needs-review | Medical | Receipt | 2026-01-15 | EUR | 10.00 | — |
  | 5 | archived | Food | Receipt | 2026-03-05 | USD | 20.00 | — |
  | 6 | archived | Food | Receipt | 2025-06-01 | *(none)* | 15.00 | — |
  | 7 | archived | Travel | Receipt | *(none)* | EUR | 5.00 | — |

  Docs 5-7 are `archived` (not plain `active`) so they stay out of the default All Documents view without changing what All Documents itself shows (only doc 1 is ever visible there — see Task 1's Scenario 4) — Reports includes them regardless, since Reports always includes archived documents. Docs 1-4 are added in Task 1; docs 5-6 in Task 2; doc 7 in Task 3.

---

### Task 1: Reports nav item, view scoping, and render() skeleton

**Files:**
- Modify: `dossiary.html` (markup ~line 335-341, CSS ~line 40-58, consts ~line 581-590, `matchesView()` ~line 2044-2070, `setView()` ~line 2161-2166, `render()` ~line 2168-2199, `resetAll()` ~line 1090-1105) — line numbers are approximate; search by the function/element names given, since earlier edits in this task shift later line numbers within the same task.
- Create: `tests/test_reports.py`

**Interfaces:**
- Consumes: `matchesView(d, view, showArchived)`, `setView(view)`, `renderNav()`, `render()`, `resetAll()`, `applyFilters(docs)`, `allDocs` (all pre-existing).
- Produces: a `'reports'` value accepted by `currentView`/`setView()`/`matchesView()`; a `#reports-view` DOM container (currently `<p id="reports-doc-count">`, replaced by Task 2's real report tables); `const reportsView = el('reports-view');`. Later tasks read `reportsView` and extend `render()`'s existing `if(currentView === 'reports')` branch.

- [ ] **Step 1: Write the failing test**

Create `tests/test_reports.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: ordinary, active -- always in scope for Reports and the only document that
#        ever shows in the All Documents default view across every scenario below.
# Doc 2: archived -- Reports includes archived documents by default (unlike All
#        Documents, which hides them until "Show archived" is checked).
# Doc 3: deleted (Waste bin) -- Reports excludes deleted documents, same as every
#        other view.
# Doc 4: flagged for review (Inbox view) -- Reports includes needs-review documents
#        by default too, same reasoning as archived. Given a different Category
#        (Medical, not Travel) so later breakdown-by-category scenarios can tell it
#        apart from docs 1/2.
# Docs 5-7 are added in Tasks 2/3 for currency/date-range scenarios.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Active Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Archived Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-02-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-02-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Deleted Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
        {
            "id": 4, "title": "Needs Review Doc", "category": "Medical", "document_type": "Receipt",
            "date": "2026-01-15T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-01-15T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 1, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: the Reports nav item exists and is reachable ===
        reports_nav_count = await page.locator('#nav-item-reports').count()
        print("Reports nav item exists:", reports_nav_count == 1)

        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        reports_active = await page.locator('#nav-item-reports').get_attribute('class')
        print("Reports nav item becomes active on click:", 'active' in (reports_active or ''))

        # === Scenario 2: switching to Reports hides the document table/count line ===
        table_visible = await page.locator('#table-wrap').is_visible()
        count_line_visible = await page.locator('#count-line').is_visible()
        reports_view_visible = await page.locator('#reports-view').is_visible()
        print("Table hidden in Reports view:", not table_visible)
        print("Count line hidden in Reports view:", not count_line_visible)
        print("#reports-view visible:", reports_view_visible)

        # === Scenario 3: Reports scope includes archived and needs-review, excludes
        # deleted -- 3 of the 4 seeded documents (doc 1 active, doc 2 archived, doc 4
        # needs-review) should be in scope; doc 3 (deleted) should not ===
        doc_count_text = await page.locator('#reports-doc-count').inner_text()
        print("Reports doc-count text:", doc_count_text)

        # === Scenario 4: switching back to All Documents restores the table, and
        # Show archived reflects that view's own independent state (unaffected by
        # having just been in Reports). Only doc 1 is ever plain active/non-archived/
        # non-needs-review/non-deleted in this SEED, so this assertion stays valid
        # even after Tasks 2-3 add more documents (5-7 are all archived). ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        table_visible_after = await page.locator('#table-wrap').is_visible()
        reports_view_visible_after = await page.locator('#reports-view').is_visible()
        print("Table visible again in All Documents:", table_visible_after)
        print("#reports-view hidden again:", not reports_view_visible_after)
        all_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents still shows only doc 1 (rest are archived/needs-review/deleted):", all_row_ids)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reports.py`

Expected: fails early — `#nav-item-reports` doesn't exist yet, so `Reports nav item exists: False` and the subsequent click times out / throws (Playwright will raise a `TimeoutError` on `page.click('#nav-item-reports')` since the element isn't in the DOM). That failure is the confirmation this test is exercising code that doesn't exist yet.

- [ ] **Step 3: Add the nav item markup**

In `dossiary.html`, inside `<nav class="app-nav" id="app-nav" ...>`, insert a new button after `#nav-item-trash`'s closing `</button>` and before `#nav-style-toggle`:

```html
      <button type="button" class="nav-item" id="nav-item-reports" data-view="reports">
        <span class="nav-item-icon">📊</span>
        <span class="nav-item-label">Reports</span>
      </button>
```

No `.nav-item-count` span — Reports has no badge (there's no single meaningful count for a totals view the way there is for the other three). `.nav-item{ display:flex; align-items:center; gap:8px; ... }` (existing CSS, ~line 40) has no fixed-children-count assumption, so omitting the count span is safe and needs no CSS change.

The existing wiring at the bottom of the script (`document.querySelectorAll('.nav-item[data-view]').forEach(btn => { btn.addEventListener('click', () => setView(btn.dataset.view)); });`, ~line 3704) already picks up this new button automatically — no change needed there.

- [ ] **Step 4: Add the `#reports-view` container**

In `dossiary.html`, inside `#content-col`, right after `.table-wrap`'s closing `</div>` (immediately before `#content-col`'s own closing `</div>`):

```html
      <div id="reports-view" style="display:none;"></div>
```

Add the matching const near the other content-area consts (right after `const countLine = el('count-line');`, ~line 581):

```js
  const reportsView = el('reports-view');
```

- [ ] **Step 5: Extend `matchesView()`**

In `dossiary.html`, find `matchesView(d, view, showArchived)` (~line 2044). Add a new branch after the existing `if(view === 'inbox') return ...;` line and its comment block, before the `'all'`-view fallthrough logic (`if(d.archived && !showArchived) return false;`):

```js
    // Reports always includes archived and needs-review documents -- a report is
    // about real financial history, not about what's currently cluttering the
    // browse view. Only `deleted` (Waste bin) is excluded, via the shared
    // `if(d.deleted) return false;` check above -- this branch runs only once
    // that's already ruled out.
    if(view === 'reports') return true;
```

- [ ] **Step 6: Extend `setView()`**

In `dossiary.html`, find `setView(view)` (~line 2161):

```js
  function setView(view){
    if(view !== 'all' && view !== 'inbox' && view !== 'trash' && view !== 'reports') return;
    if(currentView === view) return;
    currentView = view;
    render();
  }
```

- [ ] **Step 7: Extend `render()` with the Reports skeleton branch**

In `dossiary.html`, find `render()` (~line 2168). Insert a branch immediately after computing `filtered`/`sorted`, before the existing `countLine.style.display = 'block';` line:

```js
  function render(){
    renderNav();
    const filtered = applyFilters(allDocs);
    const sorted = sortDocs(filtered);
    if(currentView === 'reports'){
      tableWrap.style.display = 'none';
      countLine.style.display = 'none';
      reportsView.style.display = 'block';
      reportsView.innerHTML = `<p id="reports-doc-count">${filtered.length} document${filtered.length === 1 ? '' : 's'} in scope</p>`;
      return;
    }
    reportsView.style.display = 'none';
    tableWrap.style.display = 'block';
    countLine.style.display = 'block';
    countLine.textContent = `Showing ${sorted.length} of ${navCounts[currentView]} documents`;
    // ...unchanged from here down (dynDefs, tbody.innerHTML, etc.)
```

This placeholder (`#reports-doc-count`) is deliberately temporary — Task 2 replaces this `innerHTML` assignment with the real grouped-report rendering. Building it this way now proves the scoping/filtering pipeline (`matchesView`'s new branch, `applyFilters`, hiding/showing the right containers) works correctly before any report-specific rendering logic exists, and gives Task 2 a known-good `filtered` array to build on.

- [ ] **Step 8: Extend `resetAll()`**

In `dossiary.html`, find `resetAll()` (~line 1090). Add `reportsView.style.display = 'none';` alongside the existing `tableWrap.style.display = 'none'; countLine.style.display = 'none';` line:

```js
    toolbar.style.display = 'none'; tableWrap.style.display = 'none'; countLine.style.display = 'none';
    reportsView.style.display = 'none';
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd tests && python3 test_reports.py`

Expected output (all lines correct, `JS ERRORS: []`):
```
Reports nav item exists: True
Reports nav item becomes active on click: True
Table hidden in Reports view: True
Count line hidden in Reports view: True
#reports-view visible: True
Reports doc-count text: 3 documents in scope
Table visible again in All Documents: True
#reports-view hidden again: True
All Documents still shows only doc 1 (rest are archived/needs-review/deleted): ['1']
JS ERRORS: []
```

- [ ] **Step 10: Commit**

```bash
git add dossiary.html tests/test_reports.py
git commit -m "Add Reports nav item with view scoping (archived included, deleted excluded)"
```

---

### Task 2: Breakdown dropdown and grouped report rendering

**Files:**
- Modify: `dossiary.html` (toolbar markup ~line 353-355, `populateFilters()` ~line 1945-1962, CSS, `render()`'s reports branch from Task 1, new functions placed near `formatAmount()` ~line 2009)
- Test: `tests/test_reports.py` (extended, not replaced)

**Interfaces:**
- Consumes: `dynamicColumnDefs()`, `FIELD_DEFS`, `fieldDefs`, `d.customFields`, `d.personFieldValues`, `d.people`, `d.category`, `d.document_type`, `escapeHtml()`, `formatAmount()`'s existing `isNaN`/`=== 0` convention (mirrored, not called directly), `reportsView` (from Task 1), the `filtered` array `render()` already computes.
- Produces: `reportBreakdownFields()` → `[{id, label}, ...]`; `reportBreakdownFieldInfo(fieldId)` → `{ label, multiValued, getValues(d) }` or `null`; `numericAmount(d)` → `number | null`; `computeReportGroups(docs, fieldId)` → `[{ currency, rows: [{label, count, total}], grandTotal, documentCount, multiValued, breakdownLabel }, ...]`; `renderReportsView(docs)` (writes into `reportsView.innerHTML`, called from `render()`'s reports branch in place of Task 1's placeholder). Task 3 reads `renderReportsView` unchanged; Task 4 reads the DOM it produces to attach the print button.

- [ ] **Step 1: Write the failing test additions**

First, extend the `SEED` dict already defined at the top of `tests/test_reports.py` (from Task 1) with custom-field data and two more documents. The exact schema (confirmed from `dossiary.html`'s `SCHEMA` constant) is `fields(id, name, type, show_as_column, autocomplete)`, `document_field_values(document_id, field_id, value)`, `people(id, name)`, `document_field_people(document_id, field_id, person_id)` — `stub_studio2.js`'s `__makeSeededRoot` accepts all four directly, same shape as the real tables (confirmed by reading `stub_studio2.js`'s own `this.tables` initialization, which lists all four alongside `documents`/`tags`).

Replace the `"tags": [], "document_tags": [],` line and the two documents already in `SEED["documents"]` stay as-is — only add these keys and these two new documents:

```python
SEED = {
    "documents": [
        # ...docs 1-4 unchanged from Task 1...
        {
            "id": 5, "title": "USD Food Receipt", "category": "Food", "document_type": "Receipt",
            "date": "2026-03-05T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/5_e.pdf", "original_file_path": None,
            "created_at": "2026-03-05T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 6, "title": "No-Currency Food Receipt", "category": "Food", "document_type": "Receipt",
            "date": "2025-06-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/6_f.pdf", "original_file_path": None,
            "created_at": "2025-06-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Currency", "type": "text", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 1, "value": "45.00"},
        {"document_id": 1, "field_id": 2, "value": "EUR"},
        {"document_id": 2, "field_id": 1, "value": "30.00"},
        {"document_id": 2, "field_id": 2, "value": "EUR"},
        {"document_id": 4, "field_id": 1, "value": "10.00"},
        {"document_id": 4, "field_id": 2, "value": "EUR"},
        {"document_id": 5, "field_id": 1, "value": "20.00"},
        {"document_id": 5, "field_id": 2, "value": "USD"},
        {"document_id": 6, "field_id": 1, "value": "15.00"},
        # doc 6 deliberately has NO field_id=2 (Currency) row -- blank currency
    ],
    "people": [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ],
    "document_field_people": [
        {"document_id": 1, "field_id": 3, "person_id": 1},  # doc 1: Alice
        {"document_id": 1, "field_id": 3, "person_id": 2},  # doc 1: Bob (multi-valued)
        {"document_id": 2, "field_id": 3, "person_id": 1},  # doc 2: Alice
    ],
}
```

(docs 1-4 are unchanged from Task 1 — only add docs 5-6 to the existing `"documents"` list, and add the four new top-level keys.)

Then append these scenarios before the final `print("JS ERRORS:", errors)` block (keep the browser/page open, don't restructure the existing scenarios):

```python
        # === Scenario 5: breakdown dropdown exists and defaults to Category ===
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        breakdown_count = await page.locator('#report-breakdown-field').count()
        print("Breakdown dropdown exists:", breakdown_count == 1)
        breakdown_options = await page.locator('#report-breakdown-field option').all_inner_texts()
        print("Breakdown dropdown options:", breakdown_options)

        # === Scenario 6: currency grouping -- EUR (docs 1,2,4), USD (doc 5), and "No
        # currency set" (doc 6) are three separate groups, in that order (sorted by
        # currency label; "No currency set" sorts last since its internal grouping
        # key starts with underscores) ===
        group_headings = await page.locator('.report-currency-group h3').all_inner_texts()
        print("Currency group headings:", group_headings)

        # === Scenario 7: Category breakdown within the EUR group -- docs 1/2 share
        # Category "Travel" (count 2, total 75.00), doc 4 is "Medical" (count 1,
        # total 10.00); the group's own Grand total (85.00, count 3) is computed
        # independently, not by summing the rows (which happen to match here since
        # Category is single-valued) ===
        eur_group = page.locator('.report-currency-group').first
        cat_row_labels = await eur_group.locator('.report-table tbody td:nth-child(1)').all_inner_texts()
        cat_row_counts = await eur_group.locator('.report-table tbody td:nth-child(2)').all_inner_texts()
        cat_row_totals = await eur_group.locator('.report-table tbody td:nth-child(3)').all_inner_texts()
        cat_grand_total_row = await eur_group.locator('.report-table tfoot td').all_inner_texts()
        print("EUR group Category rows (label, count, total):", list(zip(cat_row_labels, cat_row_counts, cat_row_totals)))
        print("EUR group Grand total row:", cat_grand_total_row)
        cat_caption_count = await eur_group.locator('.report-caption').count()
        print("No multi-valued caption for Category breakdown:", cat_caption_count == 0)

        # === Scenario 8: People breakdown within the EUR group -- doc 1 has both
        # Alice and Bob, so it contributes its 45.00 to BOTH rows; doc 2 (Alice only)
        # contributes 30.00 to Alice; doc 4 has no People at all, landing in "(none)".
        # Row totals (75+45+10=130) intentionally exceed the group's real Grand total
        # (85.00) -- this is the documented multi-valued-breakdown behavior, and the
        # caption must appear to explain it. Switching the dropdown here, without
        # leaving the Reports view, also proves the report recomputes on dropdown
        # change alone. ===
        await page.select_option('#report-breakdown-field', 'people')
        await page.wait_for_timeout(150)
        eur_group = page.locator('.report-currency-group').first
        people_row_labels = await eur_group.locator('.report-table tbody td:nth-child(1)').all_inner_texts()
        people_row_counts = await eur_group.locator('.report-table tbody td:nth-child(2)').all_inner_texts()
        people_row_totals = await eur_group.locator('.report-table tbody td:nth-child(3)').all_inner_texts()
        people_grand_total_row = await eur_group.locator('.report-table tfoot td').all_inner_texts()
        people_caption_count = await eur_group.locator('.report-caption').count()
        print("EUR group People rows (label, count, total):", list(zip(people_row_labels, people_row_counts, people_row_totals)))
        print("EUR group Grand total row (independent, still 85.00/3):", people_grand_total_row)
        print("Multi-valued caption shown for People breakdown:", people_caption_count > 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reports.py`

Expected: fails at `Breakdown dropdown exists: False` (element doesn't exist yet), and the subsequent locator calls return empty lists/throw on `select_option`.

- [ ] **Step 3: Add the breakdown dropdown markup**

In `dossiary.html`, inside `.toolbar`, add a new wrapped `<select>` right after the `#show-archived-wrap` label (so it's grouped with the other view-specific toolbar controls):

```html
        <span class="filter-wrap" id="report-breakdown-wrap" style="display:none;">
          <select id="report-breakdown-field"></select>
        </span>
```

- [ ] **Step 4: Toggle its visibility from `renderNav()`**

In `dossiary.html`, find `renderNav()` (~line 2135). Add a line alongside the existing `showArchivedWrap` visibility line:

```js
    if(showArchivedWrap) showArchivedWrap.style.display = currentView === 'all' ? 'flex' : 'none';
    const reportBreakdownWrap = el('report-breakdown-wrap');
    if(reportBreakdownWrap) reportBreakdownWrap.style.display = currentView === 'reports' ? 'flex' : 'none';
```

- [ ] **Step 5: Populate the breakdown dropdown from `populateFilters()`**

In `dossiary.html`, find `populateFilters()` (~line 1945). Add this block at the end of the function, before its closing `}`:

```js
    // Report breakdown dropdown -- Category/Type/People plus any custom field
    // flagged show_as_column (same source dynamicColumnDefs() already uses for
    // table columns/filters). Deliberately excludes date/import_date/amount/tags
    // from FIELD_DEFS -- see reportBreakdownFields()'s own comment.
    const breakdownSelect = el('report-breakdown-field');
    if(breakdownSelect){
      const previousValue = breakdownSelect.value;
      const options = reportBreakdownFields();
      breakdownSelect.innerHTML = options.map(f => `<option value="${f.id}">${escapeHtml(f.label)}</option>`).join('');
      breakdownSelect.value = options.some(f => f.id === previousValue) ? previousValue : (options[0] ? options[0].id : '');
    }
```

- [ ] **Step 6: Add `reportBreakdownFields()`, `reportBreakdownFieldInfo()`, `numericAmount()`, and `computeReportGroups()`**

In `dossiary.html`, add these new functions right after `formatAmount()` (~line 2016):

```js
  // Category/Type/People are always offered as breakdown dimensions; any other
  // show_as_column field (including Payment method, already flagged show_as_column
  // by migrateSentinelFieldsToGeneric()) comes from dynamicColumnDefs(), the same
  // mechanism table columns/filters already use. Deliberately excludes date/
  // import_date (near-unique per document, not a meaningful grouping key -- the
  // Reports date-range filter handles time-scoping instead), amount (the value
  // being summed, not something to group by), and tags (multi-valued like People,
  // but out of scope for v1).
  function reportBreakdownFields(){
    const fixed = FIELD_DEFS.filter(f => ['category', 'document_type', 'people'].includes(f.id));
    return [...fixed, ...dynamicColumnDefs()];
  }

  // Resolves a breakdown field id (from reportBreakdownFields()) to how to read its
  // value(s) off a document. getValues() always returns an array -- a single-value
  // field returns a one-element array (possibly [null]), a multi-valued field
  // (People, or a custom person-type field) returns every name, or [null] if empty.
  function reportBreakdownFieldInfo(fieldId){
    if(fieldId === 'category') return { label: 'Category', multiValued: false, getValues: d => [d.category || null] };
    if(fieldId === 'document_type') return { label: 'Type', multiValued: false, getValues: d => [d.document_type || null] };
    if(fieldId === 'people') return { label: 'People', multiValued: true, getValues: d => (d.people && d.people.length) ? d.people : [null] };
    if(fieldId.startsWith('field-')){
      const id = Number(fieldId.slice('field-'.length));
      const def = fieldDefs.find(f => f.id === id);
      if(!def) return null;
      if(def.type === 'person'){
        return { label: def.name, multiValued: true, getValues: d => {
          const names = (d.personFieldValues || {})[def.name];
          return (names && names.length) ? names : [null];
        }};
      }
      return { label: def.name, multiValued: false, getValues: d => [(d.customFields || {})[def.name] || null] };
    }
    return null;
  }

  // A document's Amount as a real number for summing, or null if it has none --
  // mirrors formatAmount()'s own isNaN/=== 0 treatment of "no real amount" as
  // excluded, not counted as 0, so a document without an Amount doesn't silently
  // drag a group's total toward zero while still counting toward its Count.
  function numericAmount(d){
    const raw = (d.customFields || {})['Amount'];
    const n = raw != null && raw !== '' ? parseFloat(raw) : NaN;
    return (isNaN(n) || n === 0) ? null : n;
  }

  // Groups `docs` by Currency first (never summing across different currency
  // labels), then by the chosen breakdown field's value(s) within each currency
  // group. Each currency group's grandTotal/documentCount are computed
  // independently over every document in that currency group -- NOT by summing
  // the rows below -- so they stay correct even when the breakdown field is
  // multi-valued and its own rows over-count (a document with two People contributes
  // its Amount to both rows, but only once to the group's real total).
  function computeReportGroups(docs, fieldId){
    const info = reportBreakdownFieldInfo(fieldId);
    if(!info) return [];
    const byCurrency = {};
    for(const d of docs){
      const currency = (d.customFields || {})['Currency'] || null;
      const key = currency || '__no_currency__';
      (byCurrency[key] = byCurrency[key] || { currency, docs: [] }).docs.push(d);
    }
    return Object.keys(byCurrency).sort().map(key => {
      const group = byCurrency[key];
      const rows = {};
      for(const d of group.docs){
        const amount = numericAmount(d);
        for(const rawValue of info.getValues(d)){
          const label = (rawValue == null || rawValue === '') ? '(none)' : rawValue;
          const row = (rows[label] = rows[label] || { label, count: 0, total: 0 });
          row.count += 1;
          if(amount != null) row.total += amount;
        }
      }
      const rowList = Object.values(rows).sort((a, b) => (b.total - a.total) || a.label.localeCompare(b.label));
      const grandTotal = group.docs.reduce((sum, d) => { const a = numericAmount(d); return sum + (a != null ? a : 0); }, 0);
      return {
        currency: group.currency, rows: rowList, grandTotal,
        documentCount: group.docs.length, multiValued: info.multiValued, breakdownLabel: info.label,
      };
    });
  }
```

- [ ] **Step 7: Add `renderReportsView()` and wire it into `render()`**

In `dossiary.html`, add this function right after `computeReportGroups()`:

```js
  // Builds the grouped totals HTML into #reports-view, replacing whatever it
  // currently contains. Called from render()'s `currentView === 'reports'` branch.
  function renderReportsView(docs){
    const breakdownSelect = el('report-breakdown-field');
    const fieldId = breakdownSelect ? breakdownSelect.value : 'category';
    const groups = computeReportGroups(docs, fieldId);
    reportsView.innerHTML = groups.length ? groups.map(g => `
      <div class="report-currency-group">
        <h3>${g.currency ? escapeHtml(g.currency) : 'No currency set'}</h3>
        ${g.multiValued ? `<p class="report-caption">Documents with more than one ${escapeHtml(g.breakdownLabel)} are counted once per name, so this breakdown's row totals may not add up to the Grand total below.</p>` : ''}
        <table class="report-table">
          <thead><tr><th>${escapeHtml(g.breakdownLabel)}</th><th>Count</th><th>Total</th></tr></thead>
          <tbody>
            ${g.rows.map(r => `<tr><td>${escapeHtml(r.label)}</td><td>${r.count}</td><td>${r.total.toFixed(2)}</td></tr>`).join('')}
          </tbody>
          <tfoot><tr><td>Grand total</td><td>${g.documentCount}</td><td>${g.grandTotal.toFixed(2)}</td></tr></tfoot>
        </table>
      </div>
    `).join('') : '<p id="reports-empty">No documents match the current filters.</p>';
  }
```

Now replace Task 1's placeholder line in `render()`'s reports branch:

```js
    if(currentView === 'reports'){
      tableWrap.style.display = 'none';
      countLine.style.display = 'none';
      reportsView.style.display = 'block';
      renderReportsView(filtered);
      return;
    }
```

(This removes the `#reports-doc-count` placeholder entirely — Task 1's own test assertion on it will be superseded; see Step 8 below.)

- [ ] **Step 8: Update Task 1's now-obsolete assertion**

In `tests/test_reports.py`, remove Scenario 3's `doc_count_text`/`print("Reports doc-count text:", ...)` lines (the element no longer exists) — the same property (3 documents in scope) is now verified more thoroughly by Scenario 7's row/grand-total checks.

- [ ] **Step 9: Add CSS for the report tables**

In `dossiary.html`'s `<style>` block, add near the existing `.table-wrap`/table rules (~line 144-159):

```css
  #reports-view{ padding:0 32px 40px; }
  .report-currency-group{ margin-bottom:32px; }
  .report-currency-group h3{ font-family:var(--font-mono); font-size:13px; color:var(--phosphor); margin:0 0 8px; }
  .report-caption{ font-family:var(--font-mono); font-size:11.5px; color:var(--text-dim); margin:0 0 10px; }
  .report-table tfoot td{ font-weight:600; border-top:2px solid var(--line); padding:11px 14px; }
  #reports-empty{ font-family:var(--font-mono); font-size:13px; color:var(--text-dim); padding:0 32px; }
```

(`table{}`, `thead th{}`, `tbody tr{}`, `tbody td{}`, and `select{}` are all already unscoped/generic in this stylesheet, so `.report-table` and `#report-breakdown-field` inherit the app's existing table and form-control styling automatically, with zero new rules needed for them.)

- [ ] **Step 10: Run test to verify it passes**

Run: `cd tests && python3 test_reports.py`

Expected new lines (all others from Task 1 still print their previously-correct values, minus the removed doc-count line):
```
Breakdown dropdown exists: True
Breakdown dropdown options: ['Category', 'Type', 'People']
Currency group headings: ['EUR', 'USD', 'No currency set']
EUR group Category rows (label, count, total): [('Travel', '2', '75.00'), ('Medical', '1', '10.00')]
EUR group Grand total row: ['Grand total', '3', '85.00']
No multi-valued caption for Category breakdown: True
EUR group People rows (label, count, total): [('Alice', '2', '75.00'), ('Bob', '1', '45.00'), ('(none)', '1', '10.00')]
EUR group Grand total row (independent, still 85.00/3): ['Grand total', '3', '85.00']
Multi-valued caption shown for People breakdown: True
JS ERRORS: []
```

- [ ] **Step 11: Commit**

```bash
git add dossiary.html tests/test_reports.py
git commit -m "Add breakdown dropdown and grouped currency/category/people totals to Reports"
```

---

### Task 3: Date-range filter

**Files:**
- Modify: `dossiary.html` (toolbar markup, `renderNav()`, `applyFilters()` ~line 2071-2090)
- Test: `tests/test_reports.py` (extended)

**Interfaces:**
- Consumes: `applyFilters(docs)`, `currentView`, `render` event wiring pattern (`categoryFilter.addEventListener('change', render);` etc.), `d.date`.
- Produces: `currentReportDateRange()` → `{ dateFrom: string, dateTo: string }` (empty strings when unset); a new condition inside `applyFilters()` active only for `currentView === 'reports'`.

- [ ] **Step 1: Write the failing test additions**

First, add one more document to `SEED["documents"]` (after doc 6): doc 7, active-but-archived like docs 5-6, sharing Category "Travel"/Currency "EUR" with docs 1-2 but with **no `date`** — this is what proves a document with no date gets excluded once a date-range bound is active, and included again once it's cleared:

```python
        {
            "id": 7, "title": "No-Date Travel Receipt", "category": "Travel", "document_type": "Receipt",
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/7_g.pdf", "original_file_path": None,
            "created_at": "2026-01-20T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
```

Add its Amount/Currency to `SEED["document_field_values"]`:

```python
        {"document_id": 7, "field_id": 1, "value": "5.00"},
        {"document_id": 7, "field_id": 2, "value": "EUR"},
```

Then append this scenario before the final `print("JS ERRORS:", errors)` block:

```python
        # === Scenario 9: date-range filter narrows Reports totals -- with the
        # dropdown reset to Category (Scenario 8 left it on People), filtering to
        # 2026 excludes doc 6 (dated 2025) and doc 7 (no date at all), leaving only
        # the EUR and USD currency groups; clearing the range restores all three ===
        await page.select_option('#report-breakdown-field', 'category')
        await page.wait_for_timeout(150)

        date_from_count = await page.locator('#report-date-from').count()
        date_to_count = await page.locator('#report-date-to').count()
        print("Date range inputs exist:", date_from_count == 1 and date_to_count == 1)

        await page.fill('#report-date-from', '2026-01-01')
        await page.fill('#report-date-to', '2026-12-31')
        await page.wait_for_timeout(150)
        group_headings_filtered = await page.locator('.report-currency-group h3').all_inner_texts()
        print("Currency groups with 2026 date range (doc 6's 2025 date and doc 7's blank date both excluded):", group_headings_filtered)

        await page.fill('#report-date-from', '')
        await page.fill('#report-date-to', '')
        await page.wait_for_timeout(150)
        group_headings_unfiltered = await page.locator('.report-currency-group h3').all_inner_texts()
        print("Currency groups with no date range (doc 6 and doc 7 included again):", group_headings_unfiltered)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reports.py`

Expected: `Date range inputs exist: False`, and `page.fill('#report-date-from', ...)` throws (element not found).

- [ ] **Step 3: Add the date-range markup**

In `dossiary.html`'s toolbar, right after `#report-breakdown-wrap`:

```html
        <span class="report-date-range" id="report-date-range-wrap" style="display:none;">
          <input type="date" id="report-date-from" title="From date" />
          <span>–</span>
          <input type="date" id="report-date-to" title="To date" />
        </span>
```

Add matching CSS near `.field input[type=date]{ color-scheme:dark; }` (~line 227) so the date pickers render correctly in dark mode, same reasoning as every other date input in this app:

```css
  .report-date-range{ display:flex; align-items:center; gap:6px; }
  .report-date-range input[type=date]{ color-scheme:dark; background:var(--ink-2); border:1px solid var(--line); color:var(--text); font-family:var(--font-mono); font-size:12px; padding:7px 9px; border-radius:var(--radius); }
  .report-date-range span{ color:var(--text-dim); font-family:var(--font-mono); font-size:12px; }
```

- [ ] **Step 4: Toggle visibility from `renderNav()`**

Alongside the `report-breakdown-wrap` line added in Task 2:

```js
    const reportDateRangeWrap = el('report-date-range-wrap');
    if(reportDateRangeWrap) reportDateRangeWrap.style.display = currentView === 'reports' ? 'flex' : 'none';
```

- [ ] **Step 5: Add `currentReportDateRange()` and extend `applyFilters()`**

In `dossiary.html`, add near `formatDate()` (~line 1993):

```js
  function currentReportDateRange(){
    const from = el('report-date-from');
    const to = el('report-date-to');
    return { dateFrom: from ? from.value : '', dateTo: to ? to.value : '' };
  }
```

In `applyFilters()` (~line 2071), add a condition right after the existing `matchesView()` check:

```js
  function applyFilters(docs){
    const { q, category, type, person, showArchived, dynamic } = currentFilters();
    return docs.filter(d => {
      if(!matchesView(d, currentView, showArchived)) return false;
      if(currentView === 'reports'){
        const { dateFrom, dateTo } = currentReportDateRange();
        if(dateFrom && (!d.date || d.date < dateFrom)) return false;
        if(dateTo && (!d.date || d.date > dateTo)) return false;
      }
      if(category && d.category !== category) return false;
      // ...unchanged from here down
```

- [ ] **Step 6: Wire the inputs to re-render on change**

Near the existing `categoryFilter.addEventListener('change', render);` block (~line 2201-2206):

```js
  el('report-date-from').addEventListener('change', render);
  el('report-date-to').addEventListener('change', render);
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd tests && python3 test_reports.py`

Expected new lines:
```
Date range inputs exist: True
Currency groups with 2026 date range (doc 6's 2025 date and doc 7's blank date both excluded): ['EUR', 'USD']
Currency groups with no date range (doc 6 and doc 7 included again): ['EUR', 'USD', 'No currency set']
```
All prior scenarios still print their previously-correct values; `JS ERRORS: []`.

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_reports.py
git commit -m "Add date-range filter to the Reports view"
```

---

### Task 4: Print layout

**Files:**
- Modify: `dossiary.html` (CSS, `renderReportsView()`)
- Test: `tests/test_reports.py` (extended)

**Interfaces:**
- Consumes: `renderReportsView(docs)` (from Task 2), `#reports-view`, `#app-nav`, `.toolbar`.
- Produces: a `#reports-print-btn` button inside `#reports-view`'s rendered content, wired to call `window.print()`; a `@media print` stylesheet block.

- [ ] **Step 1: Write the failing test additions**

Append to `tests/test_reports.py` (before the final `print`/`browser.close()` lines). This stubs `window.print` before checking the button calls it, since a real print dialog can't be driven in this offline test environment — same spirit as this suite's existing Tesseract/jsPDF/pdf.js stubs, just inline here since it's the only test needing it:

```python
        # === Scenario 10: Print button exists and calls window.print() ===
        await page.evaluate("window.__printCalled = false; window.print = () => { window.__printCalled = true; };")
        print_btn_count = await page.locator('#reports-print-btn').count()
        print("Print button exists:", print_btn_count == 1)
        await page.click('#reports-print-btn')
        print_called = await page.evaluate("window.__printCalled")
        print("window.print() called on click:", print_called)

        # === Scenario 11: nav/toolbar are hidden under print media ===
        await page.emulate_media(media="print")
        nav_display = await page.locator('#app-nav').evaluate("el => getComputedStyle(el).display")
        toolbar_display = await page.locator('.toolbar').evaluate("el => getComputedStyle(el).display")
        print("Nav hidden under print media:", nav_display == 'none')
        print("Toolbar hidden under print media:", toolbar_display == 'none')
        await page.emulate_media(media="screen")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reports.py`

Expected: `Print button exists: False`, click throws (element not found); `Nav hidden under print media: False` (no `@media print` rule exists yet).

- [ ] **Step 3: Add the print button to `renderReportsView()`**

In `dossiary.html`, modify `renderReportsView()` (from Task 2) to prepend a print button and wire it each render (the whole container is rebuilt every call, so re-wiring on each call is correct and matches this app's existing pattern for dynamically-rebuilt containers):

```js
  function renderReportsView(docs){
    const breakdownSelect = el('report-breakdown-field');
    const fieldId = breakdownSelect ? breakdownSelect.value : 'category';
    const groups = computeReportGroups(docs, fieldId);
    const groupsHtml = groups.length ? groups.map(g => `
      <div class="report-currency-group">
        <h3>${g.currency ? escapeHtml(g.currency) : 'No currency set'}</h3>
        ${g.multiValued ? `<p class="report-caption">Documents with more than one ${escapeHtml(g.breakdownLabel)} are counted once per name, so this breakdown's row totals may not add up to the Grand total below.</p>` : ''}
        <table class="report-table">
          <thead><tr><th>${escapeHtml(g.breakdownLabel)}</th><th>Count</th><th>Total</th></tr></thead>
          <tbody>
            ${g.rows.map(r => `<tr><td>${escapeHtml(r.label)}</td><td>${r.count}</td><td>${r.total.toFixed(2)}</td></tr>`).join('')}
          </tbody>
          <tfoot><tr><td>Grand total</td><td>${g.documentCount}</td><td>${g.grandTotal.toFixed(2)}</td></tr></tfoot>
        </table>
      </div>
    `).join('') : '<p id="reports-empty">No documents match the current filters.</p>';
    reportsView.innerHTML = `<button type="button" id="reports-print-btn" class="report-print-btn">🖨 Print</button>` + groupsHtml;
    el('reports-print-btn').addEventListener('click', () => window.print());
  }
```

- [ ] **Step 4: Add the `@media print` stylesheet block**

At the end of `dossiary.html`'s `<style>` block:

```css
  @media print{
    #app-nav, .toolbar, .inbox-banner, footer, #reports-print-btn{ display:none !important; }
  }
```

`!important` is used here deliberately and only here — print media needs to override whatever inline/computed `display` these elements currently have on screen (e.g. `.toolbar`'s inline `style="display:none"` before a library is even open would already be `none`, but `#app-nav`'s is `flex` once a library is open, set both inline and via later JS, so a plain unqualified rule could lose the cascade battle depending on specificity at print time). No other rule in this stylesheet uses `!important`; keep it scoped to this one block.

- [ ] **Step 5: Add a small style for the print button**

Alongside the other Task 2 CSS additions:

```css
  .report-print-btn{ background:var(--ink-2); border:1px solid var(--line); color:var(--text); font-family:var(--font-mono); font-size:12px; padding:8px 14px; border-radius:var(--radius); cursor:pointer; margin-bottom:16px; }
  .report-print-btn:hover{ color:var(--phosphor); border-color:var(--phosphor-dim); }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd tests && python3 test_reports.py`

Expected new lines:
```
Print button exists: True
window.print() called on click: True
Nav hidden under print media: True
Toolbar hidden under print media: True
```
All prior scenarios unchanged; `JS ERRORS: []`.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_reports.py
git commit -m "Add print-friendly layout to the Reports view"
```

---

### Task 5: Documentation and full regression

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `README.de.md`

**Interfaces:**
- Consumes: nothing new — this task only documents what Tasks 1-4 built.
- Produces: nothing consumed by later tasks (this is the last task).

- [ ] **Step 1: Add a CLAUDE.md architecture note**

Add a new bullet in `CLAUDE.md`'s architecture-notes section, immediately after the existing "Top-level navigation" note (the same section documenting `#main-layout`/`#app-nav`/`matchesView()`/`renderNav()`), following that note's density and style:

```markdown
- **Reports** (`#nav-item-reports`, `data-view="reports"`, `reportBreakdownFields()`,
  `reportBreakdownFieldInfo()`, `computeReportGroups()`, `renderReportsView()`) is a
  4th top-level nav view alongside All Documents/Inbox/Waste bin, added after
  reading Mariner Paperless's own User Guide and finding no equivalent to its
  Reports/Expense feature anywhere in this app. **`matchesView()`'s `'reports'`
  branch always includes archived and needs-review documents** -- a report is
  about real financial history, not about what's currently decluttered out of
  the browse view; only `deleted` (Waste bin) documents are excluded, same as
  every other view. Totals are grouped by Currency first and never summed
  across different currency labels (`customFields['Currency']`, blank treated
  as its own "No currency set" group) -- Dossiary never assumes a
  single-currency library. Within each currency group, documents are further
  grouped by a chosen breakdown field (`#report-breakdown-field`, populated
  from `reportBreakdownFields()`: Category/Type/People from `FIELD_DEFS`, plus
  any custom field flagged `show_as_column` via the same `dynamicColumnDefs()`
  table columns/filters already use -- deliberately excludes `date`/
  `import_date` (near-unique per document, not a meaningful grouping key),
  `amount` (the value being summed, not a grouping key), and `tags` (multi-
  valued like People, but out of scope for v1). **A document with more than
  one value for a multi-valued breakdown field (People, or a custom
  person-type field) contributes its full Amount to every value's row** --
  `renderReportsView()` shows an explicit caption when this applies, since
  row totals then legitimately don't sum to the currency group's own Grand
  total; that Grand total (`computeReportGroups()`'s `grandTotal`/
  `documentCount`) is deliberately computed independently over every document
  in the currency group, not by summing the rows above it, so it stays a
  reliable "true total" regardless. A separate, Reports-only date-range
  filter (`#report-date-from`/`#report-date-to`, `currentReportDateRange()`)
  filters on the document's own `date` field (its content date, not
  `import_date`) -- `applyFilters()` only applies this filter when
  `currentView === 'reports'`; the existing search/category/type/dynamic-field
  filters continue to apply unchanged in this view too. No new dependency, no
  schema change -- this is a pure read/aggregate view over `allDocs`. Printing
  (`#reports-print-btn` → `window.print()`) is the first `@media print`
  stylesheet in this app, hiding `#app-nav`/`.toolbar`/etc.; the browser's own
  print dialog already offers "Save as PDF" on every platform this app
  targets, so no separate PDF-generation path was needed.
```

- [ ] **Step 2: Update the test-suite description paragraph**

In `CLAUDE.md`'s "How this was tested" section, update the script count (check the current count with `ls tests/test_*.py | wc -l` and update the stated number in both `CLAUDE.md` and `CONTRIBUTING.md` if it changed from what's currently written there), and add a clause describing `test_reports.py`'s coverage to the long feature-coverage paragraph, following its existing style:

```markdown
the Reports view (`test_reports.py` -- the nav item and view-scoping
(archived and needs-review included, deleted excluded, matching the
"Top-level navigation" note's own `matchesView()` design); currency
grouping across three distinct groups including a blank-Currency "No
currency set" group; category/type breakdown totals and their independently-
computed Grand total; the multi-valued People-breakdown row-inflation
caveat and its on-screen caption, switched to without leaving the Reports
view; the date-range filter narrowing totals by the document's own Date
field and correctly excluding a document with no date set once a bound is
active; and the print button/`@media print` layout hiding the nav and
toolbar),
```

- [ ] **Step 3: Update README.md and README.de.md**

In `README.md`'s `## Features` section, add a short bullet near the other nav-related entries (Archiving/Waste bin/Inbox), matching that list's existing one-paragraph-per-feature style:

```markdown
- **Reports** — a 4th nav view totals your documents by Category, Type,
  People, or any custom field, grouped by currency so amounts in different
  currencies are never added together, with a date-range filter and a
  print-friendly layout for tax season or expense reimbursement.
```

Add the equivalent German translation to `README.de.md` in the matching spot (`## Funktionen`), following that file's existing translation conventions (UI labels like "Reports"/"Category"/"Type"/"People" stay in English, matching how every other feature bullet in that file already handles literal UI text).

- [ ] **Step 4: Run the full test suite**

Run: `cd tests && for f in test_*.py; do echo "=== $f ==="; python3 "$f" 2>&1 | tail -5; done`

(Or use whatever background-friendly runner pattern this session already uses for the full suite — the point is running every `test_*.py` file, not just `test_reports.py`.)

Expected: every file passes, `JS ERRORS: []` (or equivalent) in every file that prints it, no `Traceback`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md README.de.md
git commit -m "Document the Reports view in CLAUDE.md and both READMEs"
```
