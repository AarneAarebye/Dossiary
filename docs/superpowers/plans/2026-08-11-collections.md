# Collections / Smart Collections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add manual and smart Collections to Dossiary, reachable from an expandable "Collections" nav section — hand-curated document lists and saved-filter views that re-evaluate live, both filterable further by the existing toolbar.

**Architecture:** Everything lives in the existing single-file `dossiary.html` — two new additive tables (`collections`, `collection_documents`), a `collection-<id>` value for `currentView`/`matchesView()` alongside the existing `'all'`/`'inbox'`/`'trash'`/`'reports'`, a shared `matchesCriteria()` predicate reused by both the live toolbar filters and saved Smart Collections, a new checkbox-based multi-select mechanism on the document table for bulk-adding to manual collections, and a Field-Settings-style management modal.

**Tech Stack:** Vanilla JS (no framework), sql.js (already loaded), Playwright + the shared `tests/stub_studio2.js` fake-browser-API stub for testing.

## Global Constraints

- Single file: all production changes go in `dossiary.html`. No build step, no new `<script src>` dependency.
- No nested folders — collections are a flat list under the Collections nav section.
- No dedicated criteria-builder UI — a Smart Collection's criteria is exactly whatever the toolbar's filters are set to when you save it (search/category/type/person/dynamic fields, all ANDed — the same shape `currentFilters()` already returns).
- No in-place Smart Collection criteria editing — changing what one matches means deleting it and creating a new one.
- Smart collections store **no** `collection_documents` rows — membership is always computed live from `criteria`.
- The "Save as Smart Collection" control is visible only in the `'all'` view.
- A document can be manually added to a collection only if that collection's `kind` is `'manual'` — smart collections are never a valid target for the bulk-add/detail-modal "Add to collection" actions.
- Every new test file must load `tests/stub_studio2.js` (never an embedded copy) — this is an existing, strictly-enforced convention in this repo (see `CLAUDE.md`'s "How this was tested" section).
- Follow this repo's existing test style exactly: one standalone Python script per feature (not per task), `print()`-based observation (no `assert` on behavior — only used for hard setup failures), driven with real Playwright clicks/fills against the real DOM, seeded via `window.__makeSeededRoot(SEED)`.
- `tests/test_collections.py` is one evolving file across every task that touches it — each task extends the same `SEED` dict and appends new scenarios before the final `print("JS ERRORS:", errors)` line, never creating a new file per task.
- IDs are assigned in JS, never via `AUTOINCREMENT` — this app's existing, universal pattern (`nextDocId`/`nextTagId`/`nextFieldId`, each initialized from `MAX(id)+1` on library open, incremented locally, the explicit id passed into each `INSERT`). New collections follow the identical `nextCollectionId` pattern.

---

### Task 1: Schema, state, nav rendering, and view routing (manual + smart)

**Files:**
- Modify: `dossiary.html` (SCHEMA ~line 483-515, state consts ~line 552-610, `resetAll()` ~line 1138-1156, `loadDocumentsFromDb()` ~line 1166-1262, nav markup ~line 356-377, CSS, `matchesView()` ~line 2231-2263, `setView()`, `renderNav()`)
- Create: `tests/test_collections.py`

**Interfaces:**
- Consumes: `matchesView(d, view, showArchived)`, `setView(view)`, `renderNav()`, `queryAll(sql)`, `escapeHtml()`, `el()`, existing `settings`-table `key`/`value` load/save pattern (see `loadNavStyle()`/`saveNavStyle()`), `document.querySelectorAll('.nav-item[data-view]')` click-wiring loop (already generic, picks up new nav items automatically).
- Produces: `let collections = [];`, `let collectionDocIds = {};`, `let nextCollectionId = 1;`, `function loadCollections()`, `function matchesCriteria(d, criteria)`, a `'collection-<id>'` value accepted by `matchesView()`/`setView()`. Later tasks read all of these; Task 2 reuses `matchesCriteria()` inside `applyFilters()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_collections.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: Category "Travel" -- matches the smart collection's saved criteria below.
# Doc 2: Category "Food" -- does NOT match the smart collection's criteria, and is
#        NOT a member of the manual collection either.
# Doc 3: Category "Travel" -- also matches the smart collection's criteria, proving
#        it's a live filter (multiple documents can match), and is separately also a
#        member of the manual collection (proving the two mechanisms are independent).
SEED = {
    "documents": [
        {
            "id": 1, "title": "Flight Receipt", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Grocery Receipt", "category": "Food", "document_type": "Receipt",
            "date": "2026-03-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-03-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Hotel Receipt", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-03-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "collections": [
        {"id": 1, "name": "Manual Trip Folder", "kind": "manual", "criteria": None},
        {"id": 2, "name": "Travel Category", "kind": "smart", "criteria": json.dumps({"q": "", "category": "Travel", "type": "", "person": "", "dynamic": []})},
    ],
    "collection_documents": [
        {"collection_id": 1, "document_id": 3},
    ],
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

        # === Scenario 1: the Collections nav section exists, expanded by default,
        # listing both seeded collections alphabetically ===
        section_count = await page.locator('#nav-collections-section').count()
        print("Collections nav section exists:", section_count == 1)
        collection_nav_labels = await page.locator('.nav-item[data-view^="collection-"] .nav-item-label').all_inner_texts()
        print("Collection nav items, alphabetical:", collection_nav_labels)

        # === Scenario 2: clicking the manual collection shows only its member
        # document (doc 3), regardless of category ===
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        manual_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Manual collection shows only doc 3:", manual_row_ids)

        # === Scenario 3: clicking the smart collection live-filters by its saved
        # criteria (Category = Travel) -- docs 1 and 3, not doc 2 ===
        await page.click('#nav-item-collection-2')
        await page.wait_for_timeout(150)
        smart_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Smart collection shows docs 1 and 3 (Category=Travel), not doc 2:", smart_row_ids)

        # === Scenario 4: the toolbar's own filters still compose on top of a
        # collection's scope, same as every other view -- searching within the smart
        # collection for "Hotel" narrows it to just doc 3 ===
        await page.fill('#search', 'Hotel')
        await page.wait_for_timeout(150)
        smart_search_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Search composes with the smart collection's own scope:", smart_search_ids)
        await page.click('#search-clear')
        await page.wait_for_timeout(150)

        # === Scenario 5: switching back to All Documents still shows every
        # non-archived/non-deleted/non-needs-review document, unaffected by having
        # just been in a collection ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        all_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents shows all 3 docs:", sorted(all_row_ids))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_collections.py`

Expected: fails early — `#nav-collections-section` doesn't exist yet, so `Collections nav section exists: False`, and the subsequent locator calls return empty results or the click on `#nav-item-collection-1` times out (element not found).

- [ ] **Step 3: Add the schema**

In `dossiary.html`, inside the `SCHEMA` template literal (~line 483-515), add these two `CREATE TABLE` statements alongside the existing ones (order doesn't matter, but placing them after `document_field_values` keeps new tables grouped at the end):

```sql
    CREATE TABLE IF NOT EXISTS collections (
      id INTEGER PRIMARY KEY, name TEXT, kind TEXT,
      criteria TEXT
    );
    CREATE TABLE IF NOT EXISTS collection_documents (
      collection_id INTEGER, document_id INTEGER, PRIMARY KEY (collection_id, document_id)
    );
```

**No `SCHEMA_MIGRATIONS` entry is needed for these two tables.** Confirmed by reading the actual call sites: `db.run(SCHEMA)` already runs unconditionally on every library open — both fresh (`initNewLibrary()`) and existing (`loadDb()`, right before `applySchemaMigrations()`) — and `CREATE TABLE IF NOT EXISTS` is a no-op when the table already exists, so adding these two statements directly to `SCHEMA` is sufficient by itself. `SCHEMA_MIGRATIONS` exists specifically for `ALTER TABLE ... ADD COLUMN` on tables that already exist (new columns on an existing table aren't covered by `CREATE TABLE IF NOT EXISTS`) — it is not needed for brand new tables.

- [ ] **Step 4: Add module-level state**

Near the other `let`-declared state (alongside `let fieldDefs = [];`/`let nextFieldId = 1;`, ~line 604):

```js
  let collections = [];        // [{id, name, kind, criteria}, ...] from the `collections` table
  let collectionDocIds = {};   // { <collectionId>: Set<documentId> } -- manual collections only;
                                // a smart collection has no entry here at all, see loadCollections()
  let nextCollectionId = 1;    // same pattern as nextDocId/nextTagId/nextFieldId -- initialized from
                                // MAX(id)+1 on library open, incremented locally, explicit id passed
                                // into each INSERT (this app assigns ids in JS, never via AUTOINCREMENT)
```

- [ ] **Step 5: Reset the new state in `resetAll()`**

In `resetAll()` (~line 1138), add alongside the existing `fieldDefs = []; ...` line:

```js
    collections = []; collectionDocIds = {}; nextCollectionId = 1;
```

- [ ] **Step 6: Add `loadCollections()` and call it from `loadDocumentsFromDb()`**

Add this function right after `loadFieldDefs()` (~line 1387):

```js
  function loadCollections(){
    const { rows } = queryAll('SELECT id, name, kind, criteria FROM collections');
    collections = rows.map(([id, name, kind, criteria]) => ({ id, name, kind, criteria }));
    let maxCollectionId = 0;
    for(const c of collections) maxCollectionId = Math.max(maxCollectionId, c.id);
    nextCollectionId = maxCollectionId + 1;

    collectionDocIds = {};
    const links = queryAll('SELECT collection_id, document_id FROM collection_documents');
    for(const [collectionId, documentId] of links.rows){
      (collectionDocIds[collectionId] = collectionDocIds[collectionId] || new Set()).add(documentId);
    }
  }
```

In `loadDocumentsFromDb()`, add a call to `loadCollections();` right after the existing `loadFieldDefs();` call (~line 1204).

- [ ] **Step 7: Add `matchesCriteria()`**

Add this pure function right after `currentFilters()` (search for `function currentFilters(){`, it's just before `matchesView()`):

```js
  // Applies a saved (or live) filter snapshot to one document -- the shape `criteria`
  // takes is exactly currentFilters()'s own return shape, so the same object can come
  // from either the live toolbar or a Smart Collection's stored criteria. Factored out
  // so both use identical predicate logic; see applyFilters() (Task 2) for the live
  // side, and matchesView()'s 'collection-<id>' branch below for the saved side.
  function matchesCriteria(d, criteria){
    const { q, category, type, person, dynamic } = criteria;
    if(category && d.category !== category) return false;
    if(type && d.document_type !== type) return false;
    if(person && !(d.people||[]).includes(person)) return false;
    for(const f of dynamic){
      if((d.customFields || {})[f.label] !== f.value) return false;
    }
    if(q){
      const personFieldNames = Object.values(d.personFieldValues || {}).map(names => (names || []).join(' '));
      const hay = [d.title, d.category, d.subcategory, d.document_type, d.notes, d.ocr_text, ...Object.values(d.customFields || {}), ...personFieldNames, (d.tags||[]).join(' ')].filter(Boolean).join(' ').toLowerCase();
      if(!hay.includes(q)) return false;
    }
    return true;
  }
```

- [ ] **Step 8: Extend `matchesView()`**

Find `matchesView(d, view, showArchived)`. Add a new branch right after the existing `if(view === 'reports') return true;` line, before the `'all'`-view fallthrough logic:

```js
    // A collection view -- 'collection-<id>'. Manual membership comes from
    // collectionDocIds (built once per library open by loadCollections()); smart
    // membership is computed live against the collection's saved criteria, via the
    // exact same matchesCriteria() the live toolbar filters use in applyFilters().
    // Same as every other view, deleted documents are already excluded by the
    // shared `if(d.deleted) return false;` check above this point.
    if(view.startsWith('collection-')){
      const id = Number(view.slice('collection-'.length));
      const collection = collections.find(c => c.id === id);
      if(!collection) return false;
      if(collection.kind === 'manual') return collectionDocIds[id] ? collectionDocIds[id].has(d.id) : false;
      return matchesCriteria(d, JSON.parse(collection.criteria));
    }
```

- [ ] **Step 9: Extend `setView()`**

Find `setView(view)`. Its current guard rejects anything outside the four fixed views — extend it to also accept any `collection-<id>` view:

```js
  function setView(view){
    if(view !== 'all' && view !== 'inbox' && view !== 'trash' && view !== 'reports' && !view.startsWith('collection-')) return;
    if(currentView === view) return;
    currentView = view;
    render();
  }
```

- [ ] **Step 10: Add the Collections nav section markup**

In `dossiary.html`, inside `<nav class="app-nav" id="app-nav">`, insert this right after `#nav-item-reports`'s closing `</button>` and before `#nav-style-toggle`:

```html
      <div class="nav-collections-section" id="nav-collections-section">
        <button type="button" class="nav-collections-header" id="nav-collections-toggle">
          <span class="nav-item-icon">📚</span>
          <span class="nav-item-label">Collections</span>
          <span class="nav-collections-chevron" id="nav-collections-chevron">▾</span>
        </button>
        <div class="nav-collections-list" id="nav-collections-list"></div>
      </div>
```

`#nav-collections-list` is rebuilt from scratch on every `renderNav()` call (Step 12 below), the same "delete-then-reinsert" pattern this app already uses for other dynamically-rebuilt containers (`renderDynamicTableHead()`, `dynamicFiltersEl.innerHTML = ...` in `populateFilters()`).

- [ ] **Step 11: Add the Collections section CSS**

Near the other `.nav-item`/`.app-nav` rules:

```css
  .nav-collections-section{ display:flex; flex-direction:column; }
  .nav-collections-header{
    display:flex; align-items:center; gap:8px; padding:11px 16px; border:none; background:transparent;
    color:var(--text-dim); font-family:var(--font-mono); font-size:12px; letter-spacing:0.03em; cursor:pointer;
  }
  .nav-collections-header:hover{ color:var(--phosphor); }
  .nav-collections-chevron{ margin-left:auto; font-size:10px; transition:transform 0.15s; }
  .nav-collections-section.collapsed .nav-collections-chevron{ transform:rotate(-90deg); }
  .nav-collections-section.collapsed .nav-collections-list{ display:none; }
  .nav-collections-list .nav-item{ padding-left:32px; }
  #main-layout.nav-style-sidebar .nav-collections-list .nav-item{ padding-left:40px; }
```

(`.nav-item` inside `.nav-collections-list` reuses the app's existing `.nav-item` rule wholesale — same active/hover states, same icon/label layout — only the extra left padding here is new, to visually nest it under the "Collections" header.)

- [ ] **Step 12: Extend `renderNav()`**

Find `renderNav()`. Add this block (order relative to the existing badge/active-class logic doesn't matter, but placing it at the end keeps the diff minimal):

```js
    // Collections nav section -- rebuilt from scratch every render() call, same
    // "delete-then-reinsert" pattern this app already uses for other dynamic
    // containers (dynamicColumnDefs()'s <th>s, populateFilters()'s dynamic-filters).
    const sortedCollections = [...collections].sort((a, b) => a.name.localeCompare(b.name));
    const collectionsList = el('nav-collections-list');
    if(collectionsList){
      collectionsList.innerHTML = sortedCollections.map(c => `
        <button type="button" class="nav-item" id="nav-item-collection-${c.id}" data-view="collection-${c.id}">
          <span class="nav-item-icon">${c.kind === 'smart' ? '☆' : '📁'}</span>
          <span class="nav-item-label">${escapeHtml(c.name)}</span>
        </button>
      `).join('');
      collectionsList.querySelectorAll('.nav-item[data-view]').forEach(btn => {
        btn.addEventListener('click', () => setView(btn.dataset.view));
      });
      collectionsList.querySelectorAll('.nav-item[data-view]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === currentView);
      });
    }
```

This wiring is intentionally separate from the existing bottom-of-script
`document.querySelectorAll('.nav-item[data-view]').forEach(btn => { btn.addEventListener('click', ...) });`
line, which only runs once at page load and therefore never sees these
dynamically-inserted buttons — collection nav items need their own
re-wiring every time `#nav-collections-list` is rebuilt, the same reason
`dynamicFiltersEl`'s `<select>`s are re-wired inside `populateFilters()`
itself rather than relying on the one-time bottom-of-script pass.

- [ ] **Step 13: Add `collections_nav_expanded` load/save, mirroring `nav_style` exactly**

Per the approved spec, the Collections section's expand/collapse state
persists via a `settings` row, the same `loadNavStyle()`/`saveNavStyle()`/
`applyNavStyle()` pattern (`dossiary.html:1332-1349`) already establishes
for the nav-style toggle. Add a matching trio right after those three
functions:

```js
  let collectionsNavExpanded = true;

  function loadCollectionsNavExpanded(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'collections_nav_expanded'").rows;
    collectionsNavExpanded = !(rows.length && rows[0][0] === '0');
    applyCollectionsNavExpanded();
  }

  async function saveCollectionsNavExpanded(value){
    collectionsNavExpanded = !!value;
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('collections_nav_expanded', ?)", [collectionsNavExpanded ? '1' : '0']);
    await persistDb();
    applyCollectionsNavExpanded();
  }

  function applyCollectionsNavExpanded(){
    const section = el('nav-collections-section');
    if(section) section.classList.toggle('collapsed', !collectionsNavExpanded);
  }
```

Reset `collectionsNavExpanded = true;` in `resetAll()` alongside the other
new state (Step 5 above), and call `loadCollectionsNavExpanded();` in
`loadDocumentsFromDb()` alongside the existing `loadNavStyle();` call.

- [ ] **Step 14: Wire the expand/collapse toggle**

Near the bottom-of-script wiring block (alongside `el('nav-style-toggle').addEventListener(...)`):

```js
  el('nav-collections-toggle').addEventListener('click', () => {
    saveCollectionsNavExpanded(!collectionsNavExpanded);
  });
```

- [ ] **Step 15: Extend the test to cover persistence**

Add this scenario to `tests/test_collections.py`, right after Scenario 5 (still before the final `print("JS ERRORS:", errors)` line):

```python
        # === Scenario 6: Collections section expand/collapse persists via settings,
        # the same way nav_style already does ===
        collections_section_class = await page.locator('#nav-collections-section').get_attribute('class')
        print("Collections section starts expanded (no 'collapsed' class):", 'collapsed' not in (collections_section_class or ''))

        await page.click('#nav-collections-toggle')
        await page.wait_for_timeout(150)
        collections_section_class_after = await page.locator('#nav-collections-section').get_attribute('class')
        print("Collections section collapsed after clicking the toggle:", 'collapsed' in (collections_section_class_after or ''))

        settings_after = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).settings;
            })()
        """)
        collapsed_setting = next((s for s in settings_after if s['key'] == 'collections_nav_expanded'), None)
        print("collections_nav_expanded persisted as '0':", collapsed_setting['value'] if collapsed_setting else None)
```

- [ ] **Step 16: Run test to verify it passes**

Run: `cd tests && python3 test_collections.py`

Expected output (all lines correct, `JS ERRORS: []`):
```
Collections nav section exists: True
Collection nav items, alphabetical: ['Manual Trip Folder', 'Travel Category']
Manual collection shows only doc 3: ['3']
Smart collection shows docs 1 and 3 (Category=Travel), not doc 2: ['1', '3']
Search composes with the smart collection's own scope: ['3']
All Documents shows all 3 docs: ['1', '2', '3']
Collections section starts expanded (no 'collapsed' class): True
Collections section collapsed after clicking the toggle: True
collections_nav_expanded persisted as '0': 0
JS ERRORS: []
```

- [ ] **Step 17: Commit**

```bash
git add dossiary.html tests/test_collections.py
git commit -m "Add Collections schema, nav section, and manual/smart view routing"
```

---

### Task 2: Smart Collection creation via "Save as Smart Collection"

**Files:**
- Modify: `dossiary.html` (toolbar markup ~line 380-408, `applyFilters()`, CSS)
- Test: `tests/test_collections.py` (extended, not replaced)

**Interfaces:**
- Consumes: `matchesCriteria(d, criteria)` (Task 1), `currentFilters()`, `collections`/`nextCollectionId` (Task 1), `queryAll`, `persistDb()` (this app's existing save-to-disk function, `dossiary.html:1272`), `loadCollections()`, `render()`.
- Produces: a working "Save as Smart Collection" toolbar control; `applyFilters()` refactored to call `matchesCriteria()` instead of its own inline copy of the same checks. Task 5 (Manage Collections modal) reads `collections` populated by this flow the same way it reads manually-created ones.

- [ ] **Step 1: Write the failing test additions**

Append these scenarios to `tests/test_collections.py`, before the final `print("JS ERRORS:", errors)` line:

```python
        # === Scenario 7: "Save as Smart Collection" is visible only in All
        # Documents, not inside a collection's own view ===
        save_smart_btn_in_all = await page.locator('#save-smart-collection-btn').is_visible()
        print("Save-as-Smart-Collection button visible in All Documents:", save_smart_btn_in_all)
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        save_smart_btn_in_collection = await page.locator('#save-smart-collection-btn').is_visible()
        print("Save-as-Smart-Collection button hidden inside a collection view:", not save_smart_btn_in_collection)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 8: setting a category filter and saving creates a new Smart
        # Collection that live-filters the same way the seeded one does ===
        await page.select_option('#category-filter', 'Food')
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.wait_for_timeout(150)
        await page.fill('#smart-collection-name-input', 'Food Category')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(200)
        await page.select_option('#category-filter', '')
        await page.wait_for_timeout(150)

        new_collection_labels = await page.locator('.nav-item[data-view^="collection-"] .nav-item-label').all_inner_texts()
        print("New Smart Collection appears in the nav:", 'Food Category' in new_collection_labels)

        new_smart_nav_btn = page.locator('.nav-item[data-view^="collection-"]', has_text='Food Category')
        await new_smart_nav_btn.click()
        await page.wait_for_timeout(150)
        new_smart_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("New Smart Collection shows only doc 2 (Category=Food):", new_smart_row_ids)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_collections.py`

Expected: fails at `Save-as-Smart-Collection button visible in All Documents: False` (element doesn't exist yet), and subsequent steps throw or return empty.

- [ ] **Step 3: Add the toolbar button and name-input UI**

In the toolbar, right after `#report-date-range-wrap` (~line 399) and before the `.columns-menu-wrap` div:

```html
        <button type="button" id="save-smart-collection-btn" style="display:none;">☆ Save as Smart Collection</button>
        <span class="add-field-form" id="smart-collection-name-form" style="display:none;">
          <input type="text" id="smart-collection-name-input" placeholder="Collection name" />
          <button type="button" id="smart-collection-name-save-btn">Save</button>
          <button type="button" id="smart-collection-name-cancel-btn">Cancel</button>
        </span>
```

Reuses the existing `.add-field-form` class wholesale (already styled — a small inline flex row with a text input and buttons, the exact pattern `addInlineCustomField()`'s own name-input form already uses; no new CSS needed for this part). No `window.prompt()` anywhere in this app, and this doesn't introduce the first one.

- [ ] **Step 4: Wire visibility to `currentView`**

In `renderNav()` (already modified in Task 1), add one more line:

```js
    const saveSmartBtn = el('save-smart-collection-btn');
    if(saveSmartBtn) saveSmartBtn.style.display = currentView === 'all' ? 'inline-block' : 'none';
```

If the name-input form happens to be open when the view changes away from `'all'`, hide it too (add right after the line above):

```js
    if(currentView !== 'all'){
      const nameForm = el('smart-collection-name-form');
      if(nameForm) nameForm.style.display = 'none';
    }
```

- [ ] **Step 5: Wire the button/form interactions**

Near the bottom-of-script wiring block:

```js
  el('save-smart-collection-btn').addEventListener('click', () => {
    el('save-smart-collection-btn').style.display = 'none';
    el('smart-collection-name-form').style.display = 'inline-flex';
    el('smart-collection-name-input').value = '';
    el('smart-collection-name-input').focus();
  });
  el('smart-collection-name-cancel-btn').addEventListener('click', () => {
    el('smart-collection-name-form').style.display = 'none';
    el('save-smart-collection-btn').style.display = 'inline-block';
  });
  el('smart-collection-name-input').addEventListener('keydown', (e) => { if(e.key === 'Enter') saveSmartCollection(); });
  el('smart-collection-name-save-btn').addEventListener('click', saveSmartCollection);

  async function saveSmartCollection(){
    const name = el('smart-collection-name-input').value.trim();
    if(!name) return;
    const id = nextCollectionId++;
    const criteria = JSON.stringify(currentFilters());
    db.run('INSERT INTO collections (id, name, kind, criteria) VALUES (?, ?, ?, ?)', [id, name, 'smart', criteria]);
    await persistDb();
    loadCollections();
    el('smart-collection-name-form').style.display = 'none';
    el('save-smart-collection-btn').style.display = 'inline-block';
    render();
  }
```

`persistDb()` (confirmed at `dossiary.html:1272`) is the app's real, single save-to-disk function — exports the in-memory database and writes it to `dbFileHandle`. The `await persistDb();` call above is the literal, correct call, not illustrative.

- [ ] **Step 6: Refactor `applyFilters()` to reuse `matchesCriteria()`**

Find `applyFilters(docs)`. Its body currently re-implements category/type/person/dynamic/search checks inline. Replace that inline logic with a call to `matchesCriteria()`:

```js
  function applyFilters(docs){
    const filters = currentFilters();
    return docs.filter(d => {
      if(!matchesView(d, currentView, filters.showArchived)) return false;
      if(currentView === 'reports'){
        const { dateFrom, dateTo } = currentReportDateRange();
        if(dateFrom && (!d.date || d.date.slice(0, 10) < dateFrom)) return false;
        if(dateTo && (!d.date || d.date.slice(0, 10) > dateTo)) return false;
      }
      return matchesCriteria(d, filters);
    });
  }
```

`currentFilters()`'s return shape (`{ q, category, type, person, showArchived, dynamic }`) already has every field `matchesCriteria()` reads (`q`, `category`, `type`, `person`, `dynamic`) plus the one extra (`showArchived`) that `matchesCriteria()` simply ignores since it doesn't destructure it — no adapter needed, direct pass-through.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd tests && python3 test_collections.py`

Expected new lines (all Task 1 scenarios still print their previously-correct values):
```
Save-as-Smart-Collection button visible in All Documents: True
Save-as-Smart-Collection button hidden inside a collection view: True
New Smart Collection appears in the nav: True
New Smart Collection shows only doc 2 (Category=Food): ['2']
JS ERRORS: []
```

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_collections.py
git commit -m "Add Save-as-Smart-Collection flow and refactor applyFilters() onto matchesCriteria()"
```

---

### Task 3: Multi-select checkboxes and bulk-add to a manual collection

**Files:**
- Modify: `dossiary.html` (table markup ~line 440-454, `render()` ~line 2370-2413, CSS)
- Test: `tests/test_collections.py` (extended)

**Interfaces:**
- Consumes: `collections`, `collectionDocIds` (Task 1), `db.run`/`persistDb`, `render()`.
- Produces: `let selectedDocIds = new Set();`; `function addDocumentsToCollection(collectionId, docIds)` (shared, async — inserts `collection_documents` rows, persists, reloads, re-renders); `function createManualCollection(name)` (shared, async — inserts a `collections` row with `kind: 'manual'`, `criteria: null`). Task 4 (detail modal) and Task 5 (Manage Collections modal's own "+ New") both call these same two functions rather than duplicating their logic.

- [ ] **Step 1: Write the failing test additions**

Append to `tests/test_collections.py`, before the final `print("JS ERRORS:", errors)` line:

```python
        # === Scenario 9: checkbox column exists, selecting rows shows the bulk bar ===
        checkbox_count = await page.locator('.row-select-checkbox').count()
        print("Row checkboxes present, one per visible row:", checkbox_count == 3)

        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        bulk_bar_visible = await page.locator('#bulk-action-bar').is_visible()
        bulk_bar_text = await page.locator('#bulk-action-count').inner_text()
        print("Bulk action bar visible with 2 selected:", bulk_bar_visible, bulk_bar_text)

        # Clicking a checkbox must not also open the detail modal (row click delegation).
        modal_open_after_check = await page.locator('#modal-backdrop').count()
        print("Checking a row's checkbox does not open its detail modal:", modal_open_after_check == 0)

        # === Scenario 10: bulk "Add to collection" adds both selected docs to the
        # existing manual collection (which already had doc 3) ===
        await page.click('#bulk-add-to-collection-btn')
        await page.wait_for_timeout(150)
        await page.click('.bulk-collection-option[data-collection-id="1"]')
        await page.wait_for_timeout(200)

        selection_cleared = await page.locator('#bulk-action-bar').is_visible()
        print("Selection cleared (bulk bar hidden) after adding:", not selection_cleared)

        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        manual_row_ids_after = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Manual collection now has docs 1, 2, and 3:", sorted(manual_row_ids_after))
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 11: selection clears when switching views ===
        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        await page.click('#nav-item-collection-2')
        await page.wait_for_timeout(150)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        bulk_bar_after_view_switch = await page.locator('#bulk-action-bar').is_visible()
        print("Selection cleared after switching views:", not bulk_bar_after_view_switch)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_collections.py`

Expected: fails at `Row checkboxes present, one per visible row: False` (no checkbox column yet).

- [ ] **Step 3: Add the checkbox column to the table**

In the `<thead>` (~line 443), add a new first `<th>`:

```html
              <th class="select-col"><input type="checkbox" id="select-all-checkbox" title="Select all visible" /></th>
```

In `render()`'s row-building template (~line 2391), add a new first `<td>`:

```js
        <td class="select-col" onclick="event.stopPropagation()"><input type="checkbox" class="row-select-checkbox" data-id="${d.id}" ${selectedDocIds.has(d.id) ? 'checked' : ''} /></td>
```

The inline `onclick="event.stopPropagation()"` on the `<td>` is deliberate and necessary: `tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('click', () => openDetail(...)))` fires on any click within the row, including the checkbox — without stopping propagation here, checking a box would also pop open that document's detail modal.

- [ ] **Step 4: Add `selectedDocIds` state and its own render/reset wiring**

Near the other `let`-declared state (alongside `collections`/`collectionDocIds` from Task 1):

```js
  let selectedDocIds = new Set();
```

In `resetAll()`, add:
```js
    selectedDocIds = new Set();
```

In `setView(view)` (Task 1's version), clear the selection on every successful view switch — add it right after `currentView = view;`:
```js
    selectedDocIds = new Set();
```

- [ ] **Step 5: Wire checkbox interactions and the bulk-action bar into `render()`**

At the end of `render()` (after the existing `applyColumnVisibility();` line), add:

```js
    document.querySelectorAll('.row-select-checkbox').forEach(cb => {
      cb.addEventListener('change', () => {
        const id = Number(cb.dataset.id);
        if(cb.checked) selectedDocIds.add(id); else selectedDocIds.delete(id);
        renderBulkActionBar();
        const selectAll = el('select-all-checkbox');
        if(selectAll) selectAll.checked = sorted.length > 0 && sorted.every(d => selectedDocIds.has(d.id));
      });
    });
    const selectAllCheckbox = el('select-all-checkbox');
    if(selectAllCheckbox){
      selectAllCheckbox.checked = sorted.length > 0 && sorted.every(d => selectedDocIds.has(d.id));
      selectAllCheckbox.onchange = () => {
        if(selectAllCheckbox.checked){ sorted.forEach(d => selectedDocIds.add(d.id)); }
        else { sorted.forEach(d => selectedDocIds.delete(d.id)); }
        render();
      };
    }
    renderBulkActionBar();
```

(`selectAllCheckbox.onchange = ...` is used instead of `addEventListener` deliberately here, mirroring this file's existing convention for elements re-wired on every render — assigning `.onchange` replaces any prior handler outright rather than accumulating duplicate listeners across repeated `render()` calls, which `addEventListener` would do without an explicit remove.)

Add `renderBulkActionBar()` right after `render()`:

```js
  function renderBulkActionBar(){
    const bar = el('bulk-action-bar');
    if(!bar) return;
    if(selectedDocIds.size === 0){ bar.style.display = 'none'; return; }
    bar.style.display = 'flex';
    el('bulk-action-count').textContent = `${selectedDocIds.size} selected`;
  }
```

- [ ] **Step 6: Add the bulk-action bar markup and CSS**

Right after `.count-line` (~line 439, just before `.table-wrap`):

```html
      <div class="bulk-action-bar" id="bulk-action-bar" style="display:none;">
        <span id="bulk-action-count"></span>
        <div class="bulk-collection-menu-wrap">
          <button type="button" id="bulk-add-to-collection-btn">Add to collection ▾</button>
          <div class="bulk-collection-menu" id="bulk-collection-menu" style="display:none;"></div>
        </div>
        <span class="add-field-form" id="bulk-new-collection-form" style="display:none;">
          <input type="text" id="bulk-new-collection-input" placeholder="New collection name" />
          <button type="button" id="bulk-new-collection-save-btn">Create &amp; add</button>
          <button type="button" id="bulk-new-collection-cancel-btn">Cancel</button>
        </span>
        <button type="button" id="bulk-clear-selection-btn">Clear selection</button>
      </div>
```

`#bulk-new-collection-form` reuses the same `.add-field-form` class as Task 2's `#smart-collection-name-form` — already styled, no new CSS needed for it — and stays hidden until "+ New collection…" is picked from the dropdown menu below.

CSS, near `.inbox-banner`:

```css
  .bulk-action-bar{
    margin:0 32px 14px; padding:12px 16px; border:1px solid var(--phosphor-dim); border-radius:var(--radius);
    background:rgba(79,224,166,0.06); display:flex; align-items:center; gap:12px;
    font-family:var(--font-mono); font-size:12.5px; color:var(--phosphor);
  }
  .bulk-collection-menu-wrap{ position:relative; }
  .bulk-collection-menu{
    position:absolute; top:calc(100% + 6px); left:0; background:var(--panel); border:1px solid var(--line);
    border-radius:var(--radius); padding:6px; z-index:40; min-width:200px; box-shadow:0 8px 24px rgba(0,0,0,0.4);
  }
  .bulk-collection-option{ display:block; width:100%; text-align:left; padding:8px 10px; background:transparent; border:none; color:var(--text); font-family:var(--font-mono); font-size:12.5px; cursor:pointer; border-radius:var(--radius); }
  .bulk-collection-option:hover{ background:rgba(79,224,166,0.1); color:var(--phosphor); }
  .select-col{ width:32px; text-align:center; padding:11px 8px !important; }
```

(`.select-col`'s `!important` overrides the generic `tbody td{ padding:11px 14px; }` rule for this one narrower column — the only `!important` in this task, scoped narrowly like the app's existing `@media print` precedent.)

- [ ] **Step 7: Add the shared `addDocumentsToCollection()`/`createManualCollection()` functions and wire the bulk-add dropdown**

Add these two functions near `saveSmartCollection()` (Task 2):

```js
  // Shared by the bulk-select "Add to collection" action (this task) and the detail
  // modal's single-document "Add to collection..." action (Task 4) -- the one place
  // that writes collection_documents rows, so both call sites stay identical.
  async function addDocumentsToCollection(collectionId, docIds){
    for(const docId of docIds){
      db.run('INSERT OR IGNORE INTO collection_documents (collection_id, document_id) VALUES (?, ?)', [collectionId, docId]);
    }
    await persistDb();
    loadCollections();
    render();
  }

  // Shared by this task's bulk-bar "+ New collection..." option and Task 5's Manage
  // Collections modal "+ New collection" button -- the one place that creates an
  // empty manual collection.
  async function createManualCollection(name){
    const id = nextCollectionId++;
    db.run('INSERT INTO collections (id, name, kind, criteria) VALUES (?, ?, ?, ?)', [id, name, 'manual', null]);
    await persistDb();
    loadCollections();
    render();
    return id;
  }
```

Wire the bulk dropdown (near the other bottom-of-script wiring, after `el('save-smart-collection-btn')...`):

```js
  el('bulk-add-to-collection-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    const menu = el('bulk-collection-menu');
    const manualCollections = collections.filter(c => c.kind === 'manual');
    menu.innerHTML = manualCollections.map(c => `<button type="button" class="bulk-collection-option" data-collection-id="${c.id}">${escapeHtml(c.name)}</button>`).join('')
      + `<button type="button" class="bulk-collection-option" id="bulk-new-collection-option">+ New collection…</button>`;
    menu.querySelectorAll('.bulk-collection-option[data-collection-id]').forEach(btn => {
      btn.addEventListener('click', async () => {
        await addDocumentsToCollection(Number(btn.dataset.collectionId), [...selectedDocIds]);
        selectedDocIds = new Set();
        menu.style.display = 'none';
      });
    });
    el('bulk-new-collection-option').addEventListener('click', () => {
      menu.style.display = 'none';
      el('bulk-new-collection-form').style.display = 'inline-flex';
      el('bulk-new-collection-input').value = '';
      el('bulk-new-collection-input').focus();
    });
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
  });
  document.addEventListener('click', (e) => {
    const wrap = document.querySelector('.bulk-collection-menu-wrap');
    if(wrap && !wrap.contains(e.target)) el('bulk-collection-menu').style.display = 'none';
  });

  // No window.prompt() anywhere in this app (see Global Constraints) -- "+ New
  // collection..." opens the inline #bulk-new-collection-form instead, the same
  // .add-field-form pattern Task 2's #smart-collection-name-form already uses.
  async function createAndAddToNewCollection(){
    const name = el('bulk-new-collection-input').value.trim();
    if(!name) return;
    const newId = await createManualCollection(name); // already persists + re-renders
    await addDocumentsToCollection(newId, [...selectedDocIds]); // already persists + re-renders
    selectedDocIds = new Set();
    el('bulk-new-collection-form').style.display = 'none';
  }
  el('bulk-new-collection-input').addEventListener('keydown', (e) => { if(e.key === 'Enter') createAndAddToNewCollection(); });
  el('bulk-new-collection-save-btn').addEventListener('click', createAndAddToNewCollection);
  el('bulk-new-collection-cancel-btn').addEventListener('click', () => { el('bulk-new-collection-form').style.display = 'none'; });
  el('bulk-clear-selection-btn').addEventListener('click', () => { selectedDocIds = new Set(); render(); });
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd tests && python3 test_collections.py`

Expected new lines (all Task 1-2 scenarios still print their previously-correct values):
```
Row checkboxes present, one per visible row: True
Bulk action bar visible with 2 selected: True 2 selected
Checking a row's checkbox does not open its detail modal: True
Selection cleared (bulk bar hidden) after adding: True
Manual collection now has docs 1, 2, and 3: ['1', '2', '3']
Selection cleared after switching views: True
JS ERRORS: []
```

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_collections.py
git commit -m "Add multi-select checkboxes and bulk-add to manual collections"
```

---

### Task 4: Detail modal Add/Remove-from-collection actions

**Files:**
- Modify: `dossiary.html` (`openDetail()`, CSS)
- Test: `tests/test_collections.py` (extended)

**Interfaces:**
- Consumes: `addDocumentsToCollection(collectionId, docIds)`, `createManualCollection(name)` (Task 3), `collections`, `collectionDocIds`, `currentView` — all from earlier tasks.
- Produces: two new detail-modal actions. Nothing later depends on new exports from this task; it's a pure consumer of Task 3's shared functions.

- [ ] **Step 1: Write the failing test additions**

Append to `tests/test_collections.py`, before the final `print("JS ERRORS:", errors)` line:

```python
        # === Scenario 12: detail modal "Add to collection..." action, single document ===
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        add_to_collection_btn_count = await page.locator('#add-to-collection-btn').count()
        print("Detail modal has an Add-to-collection action:", add_to_collection_btn_count == 1)
        await page.click('#add-to-collection-btn')
        await page.wait_for_timeout(150)
        await page.click('.modal-collection-option[data-collection-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        manual_after_modal_add = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Manual collection includes doc 2 after adding from its detail view:", sorted(manual_after_modal_add))

        # === Scenario 13: detail modal "Remove from this collection" appears only
        # when viewing a document from inside a manual collection's own view, and
        # correctly removes it ===
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        remove_btn_count = await page.locator('#remove-from-collection-btn').count()
        print("Remove-from-collection action shown when viewing from inside the collection:", remove_btn_count == 1)
        await page.click('#remove-from-collection-btn')
        await page.wait_for_timeout(200)

        manual_after_remove = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Doc 2 removed from the manual collection:", sorted(manual_after_remove))
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # Opening a document from All Documents (not from inside a collection) never
        # shows the remove action, even if that document happens to belong to a
        # manual collection (doc 3 has been a member since the SEED).
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        remove_btn_from_all = await page.locator('#remove-from-collection-btn').count()
        print("Remove-from-collection hidden when viewing from All Documents:", remove_btn_from_all == 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_collections.py`

Expected: fails at `Detail modal has an Add-to-collection action: False`.

- [ ] **Step 3: Add the actions to `openDetail()`**

Find `openDetail(id)`. In the `actions` array construction, inside the `if(!d.deleted){ ... }` block, add (placement alongside the existing Archive/Flag for review buttons, before Delete):

```js
      const manualCollections = collections.filter(c => c.kind === 'manual');
      if(manualCollections.length) actions.push(`<button id="add-to-collection-btn">Add to collection…</button>`);
      if(currentView.startsWith('collection-')){
        const viewedCollection = collections.find(c => c.id === Number(currentView.slice('collection-'.length)));
        if(viewedCollection && viewedCollection.kind === 'manual') actions.push(`<button id="remove-from-collection-btn">Remove from this collection</button>`);
      }
```

(`manualCollections.length` guards against showing an "Add to collection…" button that opens an empty, useless menu when no manual collection exists yet — consistent with this app's existing pattern of omitting an action entirely rather than showing a disabled/no-op one, e.g. how `#open-original-btn` only renders when `d.original_file_path` is set.)

At the end of `openDetail()`, in the `if(!d.deleted){ ... }` wiring block (alongside the existing `el('archive-toggle-btn').addEventListener(...)` etc.), add:

```js
      if(el('add-to-collection-btn')){
        el('add-to-collection-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          const menu = document.createElement('div');
          menu.className = 'bulk-collection-menu';
          menu.style.cssText = 'position:absolute; z-index:50;';
          const rect = e.target.getBoundingClientRect();
          menu.style.top = (rect.bottom + window.scrollY + 6) + 'px';
          menu.style.left = rect.left + 'px';
          menu.innerHTML = manualCollections.map(c => `<button type="button" class="modal-collection-option" data-collection-id="${c.id}">${escapeHtml(c.name)}</button>`).join('');
          document.body.appendChild(menu);
          menu.querySelectorAll('.modal-collection-option').forEach(btn => {
            btn.addEventListener('click', async () => {
              await addDocumentsToCollection(Number(btn.dataset.collectionId), [id]);
              menu.remove();
              openDetail(id); // refresh so a newly-relevant Remove action, if any, appears
            });
          });
          const removeMenu = (evt) => { if(!menu.contains(evt.target)){ menu.remove(); document.removeEventListener('click', removeMenu); } };
          setTimeout(() => document.addEventListener('click', removeMenu), 0);
        });
      }
      if(el('remove-from-collection-btn')){
        el('remove-from-collection-btn').addEventListener('click', async () => {
          const collectionId = Number(currentView.slice('collection-'.length));
          db.run('DELETE FROM collection_documents WHERE collection_id = ? AND document_id = ?', [collectionId, id]);
          await persistDb();
          loadCollections();
          closeModal();
          render();
        });
      }
```

The `add-to-collection-btn` handler builds its dropdown menu directly (`document.createElement`/`appendChild`) rather than reusing `#bulk-collection-menu`'s fixed DOM position, since the detail modal can be scrolled and the button's position varies — positioning a fresh, absolutely-positioned menu relative to the clicked button's own `getBoundingClientRect()` is simpler here than trying to make one shared menu element work correctly from two different layout contexts (the toolbar's bulk bar vs. a modal action button).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_collections.py`

Expected new lines (all Task 1-3 scenarios still print their previously-correct values):
```
Detail modal has an Add-to-collection action: True
Manual collection includes doc 2 after adding from its detail view: ['2', '3']
Remove-from-collection action shown when viewing from inside the collection: True
Doc 2 removed from the manual collection: ['3']
Remove-from-collection hidden when viewing from All Documents: True
JS ERRORS: []
```

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_collections.py
git commit -m "Add detail-modal Add-to-collection / Remove-from-collection actions"
```

---

### Task 5: Manage Collections modal

**Files:**
- Modify: `dossiary.html` (toolbar markup, new modal-opening function, CSS)
- Test: `tests/test_collections.py` (extended)

**Interfaces:**
- Consumes: `collections`, `collectionDocIds`, `matchesCriteria` (Task 1), `createManualCollection(name)` (Task 3), `allDocs`, `render()`.
- Produces: `function openManageCollectionsModal()`. Nothing later depends on this task; it's the last feature task before docs.

- [ ] **Step 1: Write the failing test additions**

Append to `tests/test_collections.py`, before the final `print("JS ERRORS:", errors)` line:

```python
        # === Scenario 14: Manage Collections modal lists every collection with the
        # right kind and document count ===
        await page.click('#manage-collections-btn')
        await page.wait_for_timeout(150)
        collection_rows = await page.locator('.manage-collection-row').count()
        print("Manage Collections modal lists all collections:", collection_rows)
        row_names = await page.locator('.manage-collection-row .manage-collection-name').all_inner_texts()
        print("Row names:", sorted(row_names))
        travel_count = await page.locator('.manage-collection-row', has_text='Travel Category').locator('.manage-collection-count').inner_text()
        print("Smart Collection's live count reflects current matching docs:", travel_count)

        # === Scenario 15: renaming a collection ===
        manual_row = page.locator('.manage-collection-row', has_text='Manual Trip Folder')
        await manual_row.locator('.manage-collection-rename-input').fill('Trip Docs')
        await manual_row.locator('.manage-collection-rename-input').press('Enter')
        await page.wait_for_timeout(200)
        renamed_label = await page.locator('#nav-collections-list .nav-item-label', has_text='Trip Docs').count()
        print("Rename reflected in the nav:", renamed_label == 1)

        # === Scenario 16: "+ New collection" creates an empty manual collection ===
        await page.fill('#manage-new-collection-input', 'Empty Folder')
        await page.click('#manage-new-collection-btn')
        await page.wait_for_timeout(200)
        new_row_count = await page.locator('.manage-collection-row', has_text='Empty Folder').count()
        print("New empty manual collection created:", new_row_count == 1)

        # === Scenario 17: deleting a collection removes it from the nav without
        # touching its member documents ===
        await page.locator('.manage-collection-row', has_text='Empty Folder').locator('.manage-collection-delete-btn').click()
        await page.wait_for_timeout(200)
        deleted_row_count = await page.locator('.manage-collection-row', has_text='Empty Folder').count()
        print("Deleted collection gone from the modal:", deleted_row_count == 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        deleted_nav_count = await page.locator('#nav-collections-list .nav-item-label', has_text='Empty Folder').count()
        print("Deleted collection gone from the nav:", deleted_nav_count == 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_collections.py`

Expected: fails at `#manage-collections-btn` not found (click throws).

- [ ] **Step 3: Add the toolbar button**

In the toolbar, alongside `#manage-fields-btn` (~line 404):

```html
        <button id="manage-collections-btn">⚙ Manage collections</button>
```

- [ ] **Step 4: Add `openManageCollectionsModal()` and `renderManageCollectionsList()`**

Add these near `openFieldSettingsModal()`:

```js
  function openManageCollectionsModal(){
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal wide" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="Close">✕</button>
          <h2>Manage collections</h2>
          <div id="manage-collections-list"></div>
          <div class="add-field-form" style="margin-top:16px;">
            <input type="text" id="manage-new-collection-input" placeholder="New collection name" />
            <button type="button" id="manage-new-collection-btn">+ New collection</button>
          </div>
          <div class="modal-actions" style="margin-top:16px;">
            <button id="manage-collections-done-btn">Done</button>
          </div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('manage-collections-done-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
    el('manage-new-collection-input').addEventListener('keydown', (e) => { if(e.key === 'Enter') el('manage-new-collection-btn').click(); });
    el('manage-new-collection-btn').addEventListener('click', async () => {
      const name = el('manage-new-collection-input').value.trim();
      if(!name) return;
      await createManualCollection(name);
      renderManageCollectionsList();
    });
    renderManageCollectionsList();
  }

  // documentCount for a smart collection is computed live against allDocs (matching
  // the same criteria evaluation matchesView()'s 'collection-<id>' branch uses),
  // never stored -- for a manual collection it's just the collection_documents row
  // count already loaded into collectionDocIds.
  function renderManageCollectionsList(){
    const listEl = el('manage-collections-list');
    if(!listEl) return;
    const sorted = [...collections].sort((a, b) => a.name.localeCompare(b.name));
    listEl.innerHTML = sorted.map(c => {
      const count = c.kind === 'manual'
        ? (collectionDocIds[c.id] ? collectionDocIds[c.id].size : 0)
        : allDocs.filter(d => matchesCriteria(d, JSON.parse(c.criteria))).length;
      return `
        <div class="manage-collection-row" data-collection-id="${c.id}">
          <span class="manage-collection-kind">${c.kind === 'smart' ? '☆' : '📁'}</span>
          <input type="text" class="manage-collection-rename-input" value="${escapeHtml(c.name)}" />
          <span class="manage-collection-name" style="display:none;">${escapeHtml(c.name)}</span>
          <span class="manage-collection-count">${count}</span>
          <button type="button" class="manage-collection-delete-btn">Delete</button>
        </div>
      `;
    }).join('');
    listEl.querySelectorAll('.manage-collection-row').forEach(rowEl => {
      const id = Number(rowEl.dataset.collectionId);
      const renameInput = rowEl.querySelector('.manage-collection-rename-input');
      const commitRename = async () => {
        const name = renameInput.value.trim();
        if(!name) return;
        db.run('UPDATE collections SET name = ? WHERE id = ?', [name, id]);
        await persistDb();
        loadCollections();
        renderManageCollectionsList();
        render();
      };
      renameInput.addEventListener('keydown', (e) => { if(e.key === 'Enter') commitRename(); });
      renameInput.addEventListener('blur', commitRename);
      rowEl.querySelector('.manage-collection-delete-btn').addEventListener('click', async () => {
        db.run('DELETE FROM collections WHERE id = ?', [id]);
        db.run('DELETE FROM collection_documents WHERE collection_id = ?', [id]);
        await persistDb();
        loadCollections();
        renderManageCollectionsList();
        render();
      });
    });
  }
```

**Note on the hidden `.manage-collection-name` span:** the test scenario reads collection names via `.manage-collection-name` (a stable, non-input element, easier to assert against than an `<input>`'s `.value`) while the actual UI edits the name via the visible `.manage-collection-rename-input`. Both stay in sync because `renderManageCollectionsList()` rebuilds both from the same `c.name` on every call, including right after a rename commits.

- [ ] **Step 5: Wire the toolbar button**

Near the other toolbar button wiring:

```js
  el('manage-collections-btn').addEventListener('click', openManageCollectionsModal);
```

- [ ] **Step 6: Add CSS**

Near `.fs-list`/`.fs-list-item` (Field Settings' own list styling) or a reasonable equivalent spot:

```css
  .manage-collection-row{ display:flex; align-items:center; gap:10px; padding:8px 0; border-bottom:1px solid var(--line); }
  .manage-collection-kind{ font-size:13px; }
  .manage-collection-rename-input{ flex:1; background:var(--ink-2); border:1px solid var(--line); border-radius:var(--radius); padding:6px 8px; color:var(--text); font-family:var(--font-sans); font-size:13px; }
  .manage-collection-count{ font-family:var(--font-mono); font-size:11px; color:var(--text-dim); min-width:24px; text-align:right; }
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd tests && python3 test_collections.py`

Expected new lines. **Note the count is 3, not 2** — Task 2's Scenario 8 created a third collection ("Food Category," a smart collection for Category=Food) that nothing in Tasks 2-4 ever deletes, so it's still present here alongside the two from the original SEED:
```
Manage Collections modal lists all collections: 3
Row names: ['Food Category', 'Manual Trip Folder', 'Travel Category']
Smart Collection's live count reflects current matching docs: 2
Rename reflected in the nav: True
New empty manual collection created: True
Deleted collection gone from the modal: True
Deleted collection gone from the nav: True
JS ERRORS: []
```

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_collections.py
git commit -m "Add Manage Collections modal (rename, delete, create manual collections)"
```

---

### Task 6: Documentation and full regression

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `README.de.md`, `CONTRIBUTING.md` (if it states a script count)

**Interfaces:**
- Consumes: nothing new — this task only documents what Tasks 1-5 built.
- Produces: nothing consumed by later tasks (this is the last task).

- [ ] **Step 1: Add a CLAUDE.md architecture note**

Add a new bullet in `CLAUDE.md`'s architecture-notes section, immediately after the existing "Reports" note, following that note's density and style. Cover: the `collections`/`collection_documents` schema and why smart collections store no membership rows; `matchesCriteria()`'s extraction and its symmetry with `currentFilters()` (both used by `applyFilters()` for the live toolbar and by `matchesView()`'s `'collection-<id>'` branch for saved Smart Collections); the Collections nav section's expand/collapse; the deliberate manual-vs-smart creation-flow split (Manage Collections modal's "+ New" for manual, the toolbar's "Save as Smart Collection" for smart, and why a smart collection is never creatable from the modal); the multi-select checkbox column and why selection resets on view switch and library close; and the shared `addDocumentsToCollection()`/`createManualCollection()` functions used by both the bulk-add bar and the detail modal's own single-document action.

- [ ] **Step 2: Update the test-suite description paragraph and script count**

In `CLAUDE.md`'s "How this was tested" section: verify the current script count with `ls tests/test_*.py | wc -l` (don't assume a number) and update it in both `CLAUDE.md` and `CONTRIBUTING.md` if it changed. Add a clause describing `test_collections.py`'s coverage to the long feature-coverage paragraph, following its existing style — covering manual and smart collection view routing and live re-evaluation, the toolbar filters composing on top of a collection's own scope, Smart Collection creation via "Save as Smart Collection" (and its visibility scoped to All Documents only), multi-select + bulk add (including that checking a box doesn't also open the detail modal, and that selection clears on view switch), the detail modal's Add/Remove-from-collection actions (and that Remove only appears when viewing from inside that specific manual collection), and the Manage Collections modal's rename/delete/create-empty-manual-collection flows.

- [ ] **Step 3: Update README.md and README.de.md**

In `README.md`'s `## Features` section, add a bullet near the Reports entry:

```markdown
- **Collections** — organize documents into your own named groupings, reachable from an expandable Collections section in the nav. Manual collections are hand-picked lists (select documents in the table or add them from a document's own detail view); Smart Collections save your current search/category/type/person/field filters as a live view that keeps matching new documents automatically.
```

Add the equivalent German translation to `README.de.md` in the matching spot, following that file's existing translation conventions (UI labels like "Collections"/"Category"/"Type" stay in English, matching every other feature bullet).

- [ ] **Step 4: Run the full test suite**

Run every `test_*.py` file (not just `test_collections.py`) and confirm every file passes — `JS ERRORS: []` (or equivalent) in every file that prints it, no `Traceback`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md README.de.md CONTRIBUTING.md
git commit -m "Document Collections/Smart Collections in CLAUDE.md and both READMEs"
```
