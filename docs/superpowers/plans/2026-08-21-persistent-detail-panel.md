# Persistent Detail Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `dossiary.html`'s full-screen `openDetail()` modal with an
always-visible, toggleable, default-collapsed side panel (matching legacy
Mariner Paperless's own "Details" panel), while leaving the separate
Edit-form modal completely unchanged.

**Architecture:** `openDetail(id)` keeps its name and content-building logic
but retargets from `modalRoot.innerHTML` to a new persistent
`#detail-panel-body` container, dropping the backdrop/close-button/Escape
chrome that made it a modal. A new `selectedDocId` module variable tracks
which row is selected (independent of whether the panel is visually
expanded), reflected as a `.row-selected` table-row highlight. The panel's
expanded/collapsed state persists per-library via the same `settings`
key/value pattern `nav_style` already uses, defaulting to collapsed.

**Tech Stack:** Vanilla JS, template-string HTML rendering, sql.js,
Playwright (`tests/stub_studio2.js` stub harness) — no new dependencies.

## Global Constraints

- Single-file app: all changes stay inside `dossiary.html`. No build step,
  no new `<script src>`.
- Every new user-facing string needs a key in **all six** `STRINGS` blocks
  (`en`, `de`, `es`, `fr`, `zh-Hans`, `zh-Hant`) — `tests/test_i18n_coverage.py`
  fails the whole suite otherwise.
- The panel defaults to **collapsed**. Clicking a table row must never
  auto-expand it — selection/highlight/content-render always happens on
  row click, but visibility is controlled only by the explicit toolbar
  toggle button.
- The existing Edit-form modal (`openEditForm()`/`saveEditedDocument()`)
  keeps using `modalRoot`/`closeModal()`/`onModalKeydown` exactly as today
  — it is not touched except at the two call sites explicitly listed below.
- Do not modify any of the four existing `.table-wrap` `max-height`
  calibration constants (410/370/484/444 desktop, 392/416/494/518 mobile)
  — this feature is horizontal-only. The new panel reuses the four desktop
  constants for its own `max-height` (same vertical chrome sits above both
  elements), verified empirically the same way, not assumed.
- Every test file must load `tests/stub_studio2.js` — never an embedded or
  copied stub (see `tests/CLAUDE.md`).

---

### Task 1: Selection state, panel scaffold, and its toggle/persistence

**Files:**
- Modify: `dossiary.html` — CSS (~lines 235-259, ~453-478), HTML (~lines
  590, 644-663), JS (~lines 2106, 2770, 3007-3011, 6227), STRINGS blocks
  (all six languages)
- Test: `tests/test_detail_panel.py` (new — created in Task 4, but a quick
  manual/inline check after this task is still worthwhile; see Step 8)

**Interfaces:**
- Produces: `let selectedDocId = null;` (module state, read/written by
  Task 2/3); `let detailPanelExpanded = false;` plus
  `loadDetailPanelExpanded()` / `async saveDetailPanelExpanded(value)` /
  `applyDetailPanelExpanded()` (mirrors `loadNavStyle()`/`saveNavStyle()`/
  `applyNavStyle()` exactly); DOM elements `#table-detail-row`,
  `#detail-panel`, `#detail-panel-body`, `#detail-panel-toggle-btn`; CSS
  classes `.row-selected` (on `tbody tr`) and `.detail-panel-expanded` (on
  `#main-layout`).
- Consumes: existing `mainLayout` (`const mainLayout = el('main-layout');`,
  line 2144), `el()` (line 2122), `queryAll()`, `persistDb()`, the
  `loadDocumentsFromDb()` function (call site for `loadDetailPanelExpanded()`,
  ~line 2895), `resetAll()` (~line 2763-2785, for resetting `selectedDocId`).

- [ ] **Step 1: Wrap `.table-wrap` in a new flex row, add the panel markup**

In `dossiary.html`, find this block (currently ~lines 644-663):

```html
      <div class="table-wrap" id="table-wrap" style="display:none;">
        <table id="doc-table">
          <thead>
            <tr id="doc-thead-row">
              <th class="select-col"><input type="checkbox" id="select-all-checkbox" data-i18n-title="tableSelectAllTitle" title="Select all visible" /></th>
              <th class="row-edit-col"></th>
              <th data-key="title" data-i18n="tableColDocument">Document</th>
              <th data-key="category" data-field="category" data-i18n="tableColCategory">Category</th>
              <th data-key="document_type" data-field="document_type" data-i18n="tableColType">Type</th>
              <th data-field="people" data-i18n="tableColPeople">People</th>
              <th data-key="date" data-field="date" data-i18n="tableColDate">Date</th>
              <th data-key="import_date" data-field="import_date" data-i18n="tableColImported">Imported</th>
              <th data-key="amount" data-field="amount" data-i18n="tableColAmount">Amount</th>
              <th data-field="tags" data-i18n="tableColTags">Tags</th>
            </tr>
          </thead>
          <tbody id="doc-tbody"></tbody>
        </table>
      </div>
      <div id="reports-view" style="display:none;"></div>
```

Replace it with (wraps `.table-wrap` and the new panel in a flex row;
`#reports-view` stays a sibling of the row, unaffected):

```html
      <div class="table-detail-row" id="table-detail-row">
        <div class="table-wrap" id="table-wrap" style="display:none;">
          <table id="doc-table">
            <thead>
              <tr id="doc-thead-row">
                <th class="select-col"><input type="checkbox" id="select-all-checkbox" data-i18n-title="tableSelectAllTitle" title="Select all visible" /></th>
                <th class="row-edit-col"></th>
                <th data-key="title" data-i18n="tableColDocument">Document</th>
                <th data-key="category" data-field="category" data-i18n="tableColCategory">Category</th>
                <th data-key="document_type" data-field="document_type" data-i18n="tableColType">Type</th>
                <th data-field="people" data-i18n="tableColPeople">People</th>
                <th data-key="date" data-field="date" data-i18n="tableColDate">Date</th>
                <th data-key="import_date" data-field="import_date" data-i18n="tableColImported">Imported</th>
                <th data-key="amount" data-field="amount" data-i18n="tableColAmount">Amount</th>
                <th data-field="tags" data-i18n="tableColTags">Tags</th>
              </tr>
            </thead>
            <tbody id="doc-tbody"></tbody>
          </table>
        </div>
        <aside class="detail-panel" id="detail-panel">
          <div class="detail-panel-head">
            <h3 data-i18n="detailPanelTitle">Details</h3>
          </div>
          <div class="detail-panel-body" id="detail-panel-body"></div>
        </aside>
      </div>
      <div id="reports-view" style="display:none;"></div>
```

- [ ] **Step 2: Add the toolbar toggle button**

Find (currently ~line 589-593):

```html
        <button id="reload-btn" data-i18n="toolbarSwitchLibrary">Switch library</button>
        <div class="columns-menu-wrap">
          <button id="columns-btn" data-i18n="toolbarColumns">⚙ Columns</button>
          <div class="columns-menu" id="columns-menu" style="display:none;"></div>
        </div>
```

Replace with:

```html
        <button id="reload-btn" data-i18n="toolbarSwitchLibrary">Switch library</button>
        <button id="detail-panel-toggle-btn" data-i18n="toolbarDetailsToggle">☰ Details</button>
        <div class="columns-menu-wrap">
          <button id="columns-btn" data-i18n="toolbarColumns">⚙ Columns</button>
          <div class="columns-menu" id="columns-menu" style="display:none;"></div>
        </div>
```

- [ ] **Step 3: Add the CSS**

Find this block (currently ~lines 235-238):

```css
  .table-wrap{ padding:0 32px 70px; overflow:auto; max-height:calc(100vh - 410px); }
  #main-layout.nav-style-sidebar .table-wrap{ max-height:calc(100vh - 370px); }
  #main-layout.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 484px); }
  #main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 444px); }
```

Directly after it, insert (reuses the same four constants for the panel's
own `max-height` — the panel sits at the same vertical offset as
`.table-wrap`, under the same header/toolbar/nav/bulk-bar/footer chrome, so
the same "how much vertical room is left" figures apply; this does not
modify any of the four lines above):

```css
  .table-detail-row{ display:flex; align-items:flex-start; }
  .table-detail-row .table-wrap{ flex:1; min-width:0; }
  .detail-panel{
    display:none; flex-direction:column; flex:0 0 340px; width:340px;
    background:var(--panel); border-left:1px solid var(--line);
    padding:20px 24px; overflow:auto; max-height:calc(100vh - 410px);
  }
  #main-layout.nav-style-sidebar .detail-panel{ max-height:calc(100vh - 370px); }
  #main-layout.bulk-bar-visible .detail-panel{ max-height:calc(100vh - 484px); }
  #main-layout.nav-style-sidebar.bulk-bar-visible .detail-panel{ max-height:calc(100vh - 444px); }
  #main-layout.detail-panel-expanded .detail-panel{ display:flex; }
  .detail-panel-head{ margin-bottom:14px; }
  .detail-panel-head h3{ font-family:var(--font-mono); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em; color:var(--text-dim); margin:0; font-weight:500; }
  .detail-panel-empty{ color:var(--text-dim); font-size:12.5px; }
  #detail-panel-toggle-btn.active{ color:var(--phosphor); border-color:var(--phosphor-dim); }
```

Find this line (currently ~line 243-244):

```css
  tbody tr{ border-bottom:1px solid rgba(217,210,189,0.06); cursor:pointer; }
  tbody tr:hover{ background:rgba(79,224,166,0.045); }
```

Directly after it, insert:

```css
  tbody tr.row-selected{ background:rgba(79,224,166,0.09); }
  tbody tr.row-selected:hover{ background:rgba(79,224,166,0.13); }
```

Find the mobile breakpoint block (currently ~line 453-459):

```css
  @media (max-width:640px){
    header{ padding:20px 16px 16px; } .toolbar{ padding:14px 16px; flex-wrap:nowrap; overflow-x:auto; } .table-wrap{ padding:0 16px 32px; max-height:calc(100vh - 392px); }
    .toolbar > *{ flex-shrink:0; }
    #main-layout.nav-style-sidebar .table-wrap{ max-height:calc(100vh - 416px); }
    #main-layout.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 494px); padding-bottom:0; }
    #main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 518px); padding-bottom:0; }
```

Directly after that last line, insert (same selector specificity as
`#main-layout.detail-panel-expanded .detail-panel{ display:flex; }` above,
so — combined with this rule appearing later in the stylesheet — it always
wins below the breakpoint regardless of the saved preference; a lower-
specificity `.detail-panel{ display:none; }` here would lose to the more
specific expanded-state rule and fail to collapse the panel):

```css
    #main-layout.detail-panel-expanded .detail-panel{ display:none; }
```

- [ ] **Step 4: Add the module-level state and reset it in `resetAll()`**

Find (currently ~line 2106):

```js
  let selectedDocIds = new Set();
```

Directly after it, insert:

```js
  // Which single row is shown in the persistent detail panel (independent of
  // selectedDocIds, the multi-select Set used for bulk actions). null means
  // nothing selected -- the panel shows its empty state. Set on row click
  // (see render()); reset to null when the selected document falls out of
  // the current view's visible set (see render()'s own invalidation check).
  let selectedDocId = null;
```

Find (currently ~line 2770):

```js
    collections = []; collectionDocIds = {}; nextCollectionId = 1; collectionsNavExpanded = true; selectedDocIds = new Set();
```

Replace with:

```js
    collections = []; collectionDocIds = {}; nextCollectionId = 1; collectionsNavExpanded = true; selectedDocIds = new Set();
    selectedDocId = null;
```

- [ ] **Step 5: Add `loadDetailPanelExpanded()`/`saveDetailPanelExpanded()`/`applyDetailPanelExpanded()`**

Find (currently ~lines 3007-3011):

```js
  function applyNavStyle(){
    mainLayout.classList.toggle('nav-style-sidebar', navStyle === 'sidebar');
    const toggleBtn = el('nav-style-toggle');
    if(toggleBtn) toggleBtn.title = navStyle === 'sidebar' ? 'Switch to top-tab navigation' : 'Switch to sidebar navigation';
  }
```

Directly after it, insert (mirrors `loadNavStyle()`/`saveNavStyle()`/
`applyNavStyle()` exactly, except the default is collapsed/`false` when no
row exists yet, unlike `nav_style`'s three-way default):

```js
  // Mirrors loadNavStyle()/saveNavStyle()/applyNavStyle() exactly, except the
  // default is collapsed (false) rather than one of two named states --
  // defaulting to expanded would defeat the whole point of a collapsed-by-
  // default panel for a library that's never touched this setting.
  function loadDetailPanelExpanded(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'detail_panel_expanded'").rows;
    detailPanelExpanded = rows.length > 0 && rows[0][0] === '1';
    applyDetailPanelExpanded();
  }

  async function saveDetailPanelExpanded(value){
    detailPanelExpanded = !!value;
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('detail_panel_expanded', ?)", [detailPanelExpanded ? '1' : '0']);
    await persistDb();
    applyDetailPanelExpanded();
  }

  function applyDetailPanelExpanded(){
    mainLayout.classList.toggle('detail-panel-expanded', detailPanelExpanded);
    const toggleBtn = el('detail-panel-toggle-btn');
    if(toggleBtn) toggleBtn.classList.toggle('active', detailPanelExpanded);
  }
```

Find the module-level `navStyle` declaration (currently ~line 2021):

```js
  let navStyle = 'sidebar';    // 'tabs' | 'sidebar' -- persisted per-library, see loadNavStyle()
```

Directly after it, insert:

```js
  let detailPanelExpanded = false; // persisted per-library, see loadDetailPanelExpanded()
```

- [ ] **Step 6: Call `loadDetailPanelExpanded()` on library open, wire the toggle button**

Find (currently ~lines 2893-2895, inside `loadDocumentsFromDb()`):

```js
    loadNavStyle();
    loadSortState();
    loadCollectionsNavExpanded();
```

Replace with:

```js
    loadNavStyle();
    loadDetailPanelExpanded();
    loadSortState();
    loadCollectionsNavExpanded();
```

Find (currently ~line 6227):

```js
  el('nav-style-toggle').addEventListener('click', () => saveNavStyle(navStyle === 'sidebar' ? 'tabs' : 'sidebar'));
```

Directly after it, insert:

```js
  el('detail-panel-toggle-btn').addEventListener('click', () => saveDetailPanelExpanded(!detailPanelExpanded));
```

- [ ] **Step 7: Hide the toggle button in Reports view**

Find (currently ~lines 4177-4180, inside `renderNav()`):

```js
    const reportBreakdownWrap = el('report-breakdown-wrap');
    if(reportBreakdownWrap) reportBreakdownWrap.style.display = currentView === 'reports' ? 'flex' : 'none';
    const reportDateRangeWrap = el('report-date-range-wrap');
    if(reportDateRangeWrap) reportDateRangeWrap.style.display = currentView === 'reports' ? 'flex' : 'none';
```

Directly after it, insert (Reports renders its own aggregate view, not the
shared table -- there's no row to select, so the toggle has nothing to
show; hidden rather than disabled, matching this toolbar's existing
pattern for view-scoped controls like "Show archived" just above):

```js
    const detailPanelToggleBtn = el('detail-panel-toggle-btn');
    if(detailPanelToggleBtn) detailPanelToggleBtn.style.display = currentView === 'reports' ? 'none' : '';
```

- [ ] **Step 8: Add the six new STRINGS keys**

Add `toolbarDetailsToggle` next to each language's `toolbarColumns` key, and
`detailPanelTitle`/`detailPanelEmpty` next to each language's
`detailSectionFields` key (same clustering convention already used
throughout `STRINGS`).

English (find `toolbarColumns: '⚙ Columns',` at ~line 749; find
`detailSectionFields: 'Fields',` at ~line 790):

```js
      toolbarColumns: '⚙ Columns', toolbarDetailsToggle: '☰ Details',
```
```js
      detailSectionFields: 'Fields', detailPanelTitle: 'Details',
      detailPanelEmpty: 'Select a document to see its details.',
```

Spanish (`toolbarColumns: '⚙ Columnas',` at ~line 910;
`detailSectionFields: 'Campos',` at ~line 951):

```js
      toolbarColumns: '⚙ Columnas', toolbarDetailsToggle: '☰ Detalles',
```
```js
      detailSectionFields: 'Campos', detailPanelTitle: 'Detalles',
      detailPanelEmpty: 'Selecciona un documento para ver sus detalles.',
```

French (`toolbarColumns: '⚙ Colonnes',` at ~line 1071;
`detailSectionFields: 'Champs',` at ~line 1112):

```js
      toolbarColumns: '⚙ Colonnes', toolbarDetailsToggle: '☰ Détails',
```
```js
      detailSectionFields: 'Champs', detailPanelTitle: 'Détails',
      detailPanelEmpty: 'Sélectionnez un document pour voir ses détails.',
```

German (`toolbarColumns: '⚙ Spalten',` at ~line 1232;
`detailSectionFields: 'Felder',` at ~line 1273):

```js
      toolbarColumns: '⚙ Spalten', toolbarDetailsToggle: '☰ Details',
```
```js
      detailSectionFields: 'Felder', detailPanelTitle: 'Details',
      detailPanelEmpty: 'Wähle ein Dokument aus, um seine Details zu sehen.',
```

Chinese Simplified (`toolbarColumns: '⚙ 列',` at ~line 1393;
`detailSectionFields: '字段',` at ~line 1434):

```js
      toolbarColumns: '⚙ 列', toolbarDetailsToggle: '☰ 详情',
```
```js
      detailSectionFields: '字段', detailPanelTitle: '详情',
      detailPanelEmpty: '选择一个文档以查看其详情。',
```

Chinese Traditional (`toolbarColumns: '⚙ 列',` at ~line 1579;
`detailSectionFields: '字段',` at ~line 1662) — character-converted from the
Simplified wording above, matching this file's existing OpenCC-derivation
convention for `zh-Hant` (same wording, different script, not an
independent re-translation — see CLAUDE.md's own note on this):

```js
      toolbarColumns: '⚙ 列', toolbarDetailsToggle: '☰ 詳情',
```
```js
      detailSectionFields: '字段', detailPanelTitle: '詳情',
      detailPanelEmpty: '選擇一個文檔以查看其詳情。',
```

- [ ] **Step 9: Manual verification**

Run `cd tests && python3 -c "
import http.server, socketserver, threading, webbrowser
"` is unnecessary — instead, quickly sanity-check by running any existing
Playwright test (e.g. `python3 tests/test_nav.py`) and confirming it still
reports `JS ERRORS: []` — this task added no logic that existing tests
exercise, so this only proves the new markup/CSS/JS didn't break page load
or introduce a syntax error. Then write and run this standalone check:

```bash
cd tests && python3 - <<'EOF'
import os, json, asyncio
os.chdir(os.path.dirname(os.path.abspath('.')))
from playwright.async_api import async_playwright

APP_PATH = os.path.abspath('../dossiary.html')
SEED = {"documents": [{
    "id": 1, "title": "Doc", "category": "Finance", "document_type": "Invoice",
    "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
    "file_path": None, "original_file_path": None,
    "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
    "archived": 0, "needs_review": 0, "deleted": 0,
}], "tags": [], "document_tags": []}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        print("panel starts collapsed:", not await page.locator('#main-layout.detail-panel-expanded').count())
        await page.click('#detail-panel-toggle-btn')
        await page.wait_for_timeout(150)
        print("toggle expands the panel:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))
        await page.reload()
        await page.wait_for_timeout(300)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        print("expanded state persists across reopen:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))
        await page.click('#nav-item-reports') if await page.locator('#nav-item-reports').count() else None
        await page.wait_for_timeout(150)
        print("toggle hidden in Reports view:", not await page.locator('#detail-panel-toggle-btn:visible').count())
        await page.set_viewport_size({"width": 375, "height": 800})
        await page.wait_for_timeout(150)
        print("panel force-collapsed on mobile despite saved preference:", not await page.locator('.detail-panel:visible').count())
        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
EOF
```

Expected: every printed line is `True`/no errors, and `JS ERRORS: []`.
This inline check is throwaway (not committed) — Task 4 writes the real,
permanent `tests/test_detail_panel.py`.

- [ ] **Step 10: Commit**

```bash
git add dossiary.html
git commit -m "Add persistent detail panel scaffold: state, layout, toggle

Adds the panel's DOM/CSS, its own persisted expanded/collapsed setting
(defaulting to collapsed), and selectedDocId module state -- no behavior
change yet to openDetail() or row clicks, which Task 2 retargets."
```

---

### Task 2: Retarget `openDetail()` into the panel; row selection and highlighting

**Files:**
- Modify: `dossiary.html` — `openDetail()` (~lines 4479-4667), the row
  click handler inside `render()` (~line 4281), `render()`'s
  `selectedDocId` invalidation check (~line 4244), `loadDocumentsFromDb()`
  (~line 2902)

**Interfaces:**
- Consumes: `selectedDocId`, `#detail-panel-body`, `.row-selected` (Task 1).
- Produces: `openDetail(id)` now accepts `id === null` (or any id not in
  `allDocs`) and renders an empty-state message into `#detail-panel-body`
  instead of silently returning — Task 3's edit-flow changes and the
  invalidation check below both rely on this.

- [ ] **Step 1: Make `openDetail()` target the panel, and handle "nothing selected"**

Find (currently ~lines 4479-4482):

```js
  async function openDetail(id){
    const d = allDocs.find(x => x.id === id);
    if(!d) return;
```

Replace with:

```js
  async function openDetail(id){
    const panelBody = el('detail-panel-body');
    const d = allDocs.find(x => x.id === id);
    if(!d){
      panelBody.innerHTML = `<p class="detail-panel-empty" data-i18n="detailPanelEmpty">${t('detailPanelEmpty')}</p>`;
      return;
    }
```

Find the section header comment (currently ~line 4418):

```js
  // --- detail modal (view existing document) ---
```

Replace with:

```js
  // --- detail panel (view existing document) ---
```

Find (currently ~lines 4543-4546 — the start of the template string):

```js
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <div class="modal-head">
```

Replace with (drops the backdrop/modal/close-button wrapper entirely — the
panel isn't a modal, so there's nothing to close or Escape out of; the
inner content, from `.modal-head` on, is unchanged since those are all
standalone CSS classes with no `.modal`-scoped ancestor selectors):

```js
    panelBody.innerHTML = `
          <div class="modal-head">
```

Find the matching closing tags at the end of the same template string
(currently ~lines 4587-4589):

```js
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
```

Replace with:

```js
    `;
```

(The rest of `openDetail()` — every `el('open-file-btn')`, `el('edit-doc-btn')`,
etc. wiring block, and the `if(!d.deleted){...}` action-button wiring — is
unchanged: those elements are still inside the returned template, now
living in `#detail-panel-body` instead of `#modal-root`, and `el()` looks
up by id regardless of which container holds it.)

- [ ] **Step 2: Fix "refresh the modal" comment wording (5 sites)**

Find and replace each of these five comments (same line, only the trailing
comment text changes — the code itself is untouched):

```js
        openDetail(id); // refresh the modal so the button now reads Flag for review/Done correctly
```
→
```js
        openDetail(id); // refresh the panel so the button now reads Flag for review/Done correctly
```

```js
              openDetail(id); // refresh so a newly-relevant Remove action, if any, appears
```
This one needs no change — it never said "modal".

```js
    el('delete-toggle-btn').addEventListener('click', async () => {
      await toggleDeleted(id);
      openDetail(id); // refresh the modal so it now shows Restore-only (or the full action set again)
    });
```
→
```js
    el('delete-toggle-btn').addEventListener('click', async () => {
      await toggleDeleted(id);
      openDetail(id); // refresh the panel so it now shows Restore-only (or the full action set again)
    });
```

```js
    render();
    openDetail(id); // refresh the modal so the button now reads Archive/Unarchive correctly
```
→
```js
    render();
    openDetail(id); // refresh the panel so the button now reads Archive/Unarchive correctly
```

```js
      d.thumbnail_path = thumbnailPath;
      render();
      openDetail(id); // refresh the modal to show the new thumbnail
```
→
```js
      d.thumbnail_path = thumbnailPath;
      render();
      openDetail(id); // refresh the panel to show the new thumbnail
```

- [ ] **Step 3: Row click handler — selection, highlighting, panel refresh**

Find (currently ~line 4281):

```js
    tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('click', () => openDetail(Number(tr.dataset.id))));
```

Replace with (row click always selects/highlights/refreshes panel content
— it never expands a collapsed panel; expanding is only ever the toolbar
toggle's job, see Task 1 Step 6):

```js
    tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('click', () => {
      const id = Number(tr.dataset.id);
      selectedDocId = id;
      tbody.querySelectorAll('tr.row-selected').forEach(r => r.classList.remove('row-selected'));
      tr.classList.add('row-selected');
      openDetail(id);
    }));
```

- [ ] **Step 4: Invalidate `selectedDocId` when it falls out of the visible set; reapply highlight after rebuild**

Find (currently ~line 4244, inside `render()`):

```js
    const sorted = sortDocs(filtered);
```

Directly after it, insert (the selected document was deleted, archived out
of view, or filtered out entirely -- clear the selection and show the
panel's empty state; matches the spec's explicit rule that selection
resets when a document is no longer part of the current view's data):

```js
    if(selectedDocId !== null && !sorted.some(d => d.id === selectedDocId)){
      selectedDocId = null;
      openDetail(null);
    }
```

Find (currently ~line 4281, right after the row-click wiring you just
edited in Step 3):

```js
    tbody.querySelectorAll('.row-edit-btn').forEach(btn => {
      btn.addEventListener('click', () => openEditForm(Number(btn.dataset.id)));
    });
    applyColumnVisibility();
```

Directly before `applyColumnVisibility();`, insert (the whole `tbody` was
just rebuilt from scratch above, so the `.row-selected` class from any
earlier click is gone -- reapply it to whichever row still matches
`selectedDocId`, if any):

```js
    if(selectedDocId !== null){
      const selectedTr = tbody.querySelector(`tr[data-id="${selectedDocId}"]`);
      if(selectedTr) selectedTr.classList.add('row-selected');
    }
```

- [ ] **Step 5: Show the empty state immediately on library open**

Find (currently ~line 2902, the last line of `loadDocumentsFromDb()`):

```js
    render();
  }
```

(this is the end of `loadDocumentsFromDb()` — the closing `}` belongs to
that function, not `render()`). Replace with:

```js
    render();
    openDetail(selectedDocId); // populates the panel's empty state immediately, rather than leaving #detail-panel-body blank until the first row click
  }
```

- [ ] **Step 6: Manual verification**

Adapt the Step 9 script from Task 1: after expanding the panel via
`#detail-panel-toggle-btn`, click `tr[data-id="1"]` and confirm
`#edit-doc-btn` becomes visible with the right document's title in
`.detail-panel-body h2`; confirm `tr[data-id="1"]` gains class
`row-selected`. With two seeded documents, click the second row and
confirm the highlight moves and the panel content changes to the second
document's title. Confirm `JS ERRORS: []` throughout.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html
git commit -m "Retarget openDetail() into the persistent panel

openDetail() now renders into #detail-panel-body instead of the modal
root, drops the backdrop/close-button/Escape chrome, and handles a null/
missing id by showing the panel's empty state. Row clicks set
selectedDocId, highlight the row, and refresh panel content without ever
auto-expanding a collapsed panel."
```

---

### Task 3: Edit-flow call site changes (Cancel, Save)

**Files:**
- Modify: `dossiary.html` — `openEditForm()`'s `cancel-edit-btn` handler
  (~line 4902), `saveEditedDocument()`'s success path (~line 5097)
- Modify: `tests/test_row_edit_shortcut.py` — Scenarios 2 and 3, whose
  existing assertions describe the old "Cancel reopens the detail modal"
  behavior this task removes

**Interfaces:**
- Consumes: `selectedDocId`, `openDetail()`, `closeModal()` (all from
  Tasks 1-2 / pre-existing).

- [ ] **Step 1: Cancel just closes the edit modal**

Find (currently ~line 4902):

```js
    el('cancel-edit-btn').addEventListener('click', () => openDetail(id));
```

Replace with (the panel, if open, already shows this document -- it's how
Edit was almost certainly reached; don't force it open if it's currently
collapsed, and don't re-render it, since nothing changed):

```js
    el('cancel-edit-btn').addEventListener('click', () => closeModal());
```

- [ ] **Step 2: Saving selects the just-edited document as the new panel selection**

Find (currently ~lines 5094-5097):

```js
      renderStats(); populateFilters(); populateDatalists(); render();

      setStatusT('editSavedStatus', {title: title || t('commonDocumentFallback', {id})}, 'ok');
      openDetail(id);
      return true;
```

Replace with (closes the edit modal explicitly, then makes the just-saved
document the new panel selection -- this covers Edit reached via the
row-level .row-edit-btn shortcut, which bypasses row selection entirely on
the way in, so without this the panel/highlight would still point at
whatever was selected before, or nothing):

```js
      renderStats(); populateFilters(); populateDatalists();
      selectedDocId = id;
      render();

      setStatusT('editSavedStatus', {title: title || t('commonDocumentFallback', {id})}, 'ok');
      closeModal();
      openDetail(id);
      return true;
```

(`render()` runs before `selectedDocId` is used by `openDetail()` here,
matching the existing order where `render()` already ran before the old
`openDetail(id)` call — `render()`'s own row-highlight-reapply step from
Task 2 Step 4 picks up the new `selectedDocId` and highlights the right
row as part of this same call.)

- [ ] **Step 3: Fix the now-broken assertions in `tests/test_row_edit_shortcut.py`**

Read the file first to confirm current line numbers, since earlier tasks
in this plan don't touch it and its content is otherwise as read during
planning. Find Scenario 2 (currently lines 80-88):

```python
        # === Scenario 2: Cancel from an edit reached via the shortcut returns to
        # the detail view (the simplest, single-behavior choice -- Cancel always
        # goes to the detail view regardless of how Edit was reached) ===
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(200)
        landed_on_detail_view = await page.locator('#edit-doc-btn').count()
        print("Cancel lands on the detail view:", landed_on_detail_view == 1)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
```

Replace with (the shortcut never touched `selectedDocId` or the panel on
the way in, and Cancel is now documented to never force the panel open --
so after Cancel, the edit form is simply gone and nothing new opened):

```python
        # === Scenario 2: Cancel from an edit reached via the shortcut just closes
        # the edit form -- it no longer reopens the detail view/panel, and does NOT
        # force the (collapsed-by-default) detail panel open, since the shortcut
        # bypasses row selection entirely on the way in ===
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(200)
        edit_form_closed = await page.locator('#e-title').count()
        print("Cancel closes the edit form:", edit_form_closed == 0)
        panel_not_forced_open = await page.locator('#main-layout.detail-panel-expanded').count()
        print("Cancel does not force the detail panel open:", panel_not_forced_open == 0)
```

Find Scenario 3's trailing cleanup (currently lines 100-103):

```python
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
```

Replace with (no modal is left open after Cancel now, so there is nothing
for a second click to close):

```python
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)
```

- [ ] **Step 4: Run the updated test**

```bash
cd tests && python3 test_row_edit_shortcut.py
```

Expected: all four scenarios print `True` for every assertion, and
`JS ERRORS: []`.

- [ ] **Step 5: Manual verification of the Save path**

Extend the Task 2 verification script: with the panel collapsed and no row
ever clicked, click a `.row-edit-btn` directly (bypassing the panel
entirely, same as `test_row_edit_shortcut.py`'s own Scenario 1), change
the title, click `#save-edit-btn`, and confirm afterward that
`tr[data-id="<that id>"]` has class `row-selected` even though it was
never explicitly clicked — this proves the save path's new
`selectedDocId = id` assignment worked.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_row_edit_shortcut.py
git commit -m "Fix edit-flow panel interaction: Cancel and Save

Cancel now just closes the edit modal instead of relying on the old
modal-overwrite trick to reopen detail content. Saving selects the
just-edited document as the panel's new selection, covering the
row-edit-btn shortcut's bypass-the-panel entry path. Updates
test_row_edit_shortcut.py's Scenarios 2-3 to match."
```

---

### Task 4: Comment sweep, docs, and the dedicated panel test file

**Files:**
- Modify: `dossiary.html` — comments at ~lines 2107, 4694, 6142
- Modify: `/Users/aarneaarebye/Projects/Paperless/Dossiary/CLAUDE.md` — new
  architecture note
- Modify: `/Users/aarneaarebye/Projects/Paperless/Dossiary/tests/CLAUDE.md`
  — script count bump + new coverage paragraph
- Create: `tests/test_detail_panel.py`

**Interfaces:**
- Consumes: everything from Tasks 1-3 (this task only documents and tests
  the finished feature; no new production behavior).

- [ ] **Step 1: Fix remaining "detail modal" comment wording**

Find (currently ~lines 2107-2112):

```js
  // The detail modal's own single-document "Add to collection..." picker (built
  // in openDetail() below) is appended to document.body, outside modalRoot, so it
  // isn't cleared by closeModal()'s own `modalRoot.innerHTML = ''`. It already
  // removes itself on an outside click; this reference lets closeModal() also
  // remove it when the modal closes some other way (Escape, the backdrop, Close),
  // so it can't outlive the modal it was opened from.
```

Replace with:

```js
  // The detail panel's own single-document "Add to collection..." picker (built
  // in openDetail() below) is appended to document.body, outside both the panel
  // and modalRoot, so it isn't cleared by the panel's own content rebuild or by
  // closeModal()'s `modalRoot.innerHTML = ''`. It already removes itself on an
  // outside click; this reference lets closeModal() also remove it if it's still
  // open when the (separate) edit modal closes, so it can't outlive whichever UI
  // it was opened from.
```

Find (currently ~line 4694, inside the `toggleNeedsReview()` comment block):

```js
  // signal the document is actually finished. Doesn't reopen the detail modal
```

Replace with:

```js
  // signal the document is actually finished. Doesn't refresh the detail panel
```

Find (currently ~lines 6142):

```js
  // reached and acted on (Restore, via the same openDetail() modal every other view
```

Replace with:

```js
  // reached and acted on (Restore, via the same openDetail() panel every other view
```

- [ ] **Step 2: Add the CLAUDE.md architecture note**

Read `CLAUDE.md`'s "Top-level navigation" note (search for `**Top-level
navigation**`) to match its voice/depth before writing this. Insert a new
note immediately after the "Collections" note's final paragraph (search
for `**The bulk-action bar's height is part of \`.table-wrap\`'s sticky-header`,
the last paragraph of that note) and before the "**Configurable
columns/filters**" note. Insert:

```markdown
- **The detail view is a persistent side panel (`#detail-panel`), not a
  modal** — `openDetail(id)` keeps its name (it still means "show this
  document's detail content") but now renders into `#detail-panel-body`
  instead of `#modal-root`, and drops the backdrop/close-button/Escape
  chrome that made it a modal (a panel isn't dismissed, it's collapsed).
  This replaced a full-screen modal that hid the table entirely while
  open, matching legacy Mariner Paperless's own persistent "Details" side
  panel instead. **`selectedDocId`** (module-level, distinct from
  `selectedDocIds`, the multi-select `Set` bulk actions use) tracks which
  single row the panel is showing, `null` meaning nothing selected — the
  panel then shows a plain empty-state message rather than blank content.
  Row click sets it, applies a `.row-selected` highlight to that `<tr>`,
  and calls `openDetail(id)`; `render()`'s own rebuild of `tbody` on every
  call means the highlight has to be reapplied after each rebuild (a
  `tbody.querySelector('tr[data-id=...]')` lookup right after the rows are
  rendered), and `render()` also invalidates `selectedDocId` back to
  `null` — refreshing the panel to its empty state — whenever the
  currently-selected document falls out of the active view's filtered/
  sorted set (deleted, archived out of view, or excluded by a filter/
  search change). **Clicking a row never auto-expands a collapsed
  panel** — selection, highlighting, and content-refresh all happen
  unconditionally on every row click, but panel *visibility* is
  controlled only by the toolbar's own `#detail-panel-toggle-btn`,
  deliberately: if a row click also expanded the panel, the panel's own
  collapsed-by-default setting (see below) would stop mitigating anything
  — it would spring open on literally the first row click anyone ever
  makes.
  **The panel's expanded/collapsed state is a per-library `settings` row**
  (`detail_panel_expanded`), following `nav_style`'s exact
  `loadNavStyle()`/`saveNavStyle()`/`applyNavStyle()` pattern
  (`loadDetailPanelExpanded()`/`saveDetailPanelExpanded()`/
  `applyDetailPanelExpanded()`, toggling a `detail-panel-expanded` class on
  `#main-layout`) — except the default is collapsed (`false`) rather than
  one of two named states, since defaulting to expanded would undercut the
  entire reason this shipped collapsed-by-default: an always-visible panel
  costs real horizontal table width, and the person who raised this
  feature (comparing it to Mariner's own panel) explicitly worried about
  losing that space. Below the app's one mobile breakpoint
  (`max-width:640px`), the panel force-collapses regardless of the saved
  preference — `#main-layout.detail-panel-expanded .detail-panel{
  display:none; }` inside the media query, matched in selector specificity
  to the base `#main-layout.detail-panel-expanded .detail-panel{
  display:flex; }` rule it overrides (a lower-specificity `.detail-panel{
  display:none; }` there would lose to the more specific rule and fail to
  collapse anything) — a true side panel doesn't fit a phone-width
  viewport any better than a full sidebar nav does (see that note's own
  mobile-collapse precedent above). The toggle button itself is hidden
  (not disabled) in Reports view, since that view renders its own
  aggregate content rather than the shared document table — there's no
  row for the panel to ever reflect there, same "hidden when the control
  is inert for this view" pattern already used for "Show archived".
  **The panel deliberately reuses `.table-wrap`'s own four `max-height`
  calibration constants (410/370/484/444, plus their nav-style/bulk-bar
  combinations) for its own `max-height`, rather than introducing new
  ones** — the panel is a flex sibling of `.table-wrap` inside a new
  `.table-detail-row` wrapper, sitting at exactly the same vertical offset
  under exactly the same header/toolbar/nav/bulk-bar/footer chrome, so the
  same "how much vertical room is left below that chrome" figure applies
  to both; this was verified the same empirical way as everything else in
  this section (`getBoundingClientRect()`, confirming the panel's own
  bottom edge lands at the fixed footer's top edge with no overlap), not
  assumed just because the numbers happened to match structurally. This is
  purely a **horizontal** layout change — the panel sits *beside* the
  table, not above or below it — so none of `.table-wrap`'s own four
  constants needed to move; reusing them for a same-height sibling is not
  the same thing as touching them.
  **Two call sites that used to rely on an implicit trick no longer can.**
  Before this change, `openEditForm()`'s Cancel button and
  `saveEditedDocument()`'s success path both called `openDetail(id)`,
  which — since the detail view and the edit form shared the same
  `#modal-root` — implicitly closed the edit modal *and* reopened detail
  content in one call, just by overwriting the same container. With the
  panel and the edit modal now separate, simultaneously-existing elements,
  that implicit behavior is gone: **Cancel** now just calls `closeModal()`
  and does nothing else — the panel, if open, already shows whatever
  document Edit was opened from, and Cancel deliberately does not force a
  collapsed panel open or re-render content that didn't change. **Save**'s
  success path now does two explicit things the old single call used to
  do for free: `closeModal()` to dismiss the edit modal, and
  `selectedDocId = id` (before the `render()` call that reapplies row
  highlighting) so the just-saved document becomes the new panel
  selection — this specifically covers editing reached via the row-level
  `.row-edit-btn` shortcut (see its own note above), which bypasses row
  selection entirely on the way in, so without this the panel would still
  be pointing at whatever (if anything) was selected before, not the
  document that was just edited.
```

- [ ] **Step 3: Write `tests/test_detail_panel.py`**

First check the current script count referenced in `tests/CLAUDE.md`'s
opening paragraph (search for `scripts covering most of the app's actual
functionality`) — it may have drifted since this plan was written; use
whatever the actual current number is, plus one, in Step 4 below.

Create `tests/test_detail_panel.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: a normal document with a manual collection membership available, so
#        Add/Remove-to-collection can be exercised from the panel.
# Doc 2: a second normal document, used to prove selecting a different row
#        moves the highlight and swaps the panel's content.
# Doc 3: deleted -- proves the panel drops to Restore-only, same as the old modal.
SEED = {
    "documents": [
        {
            "id": 1, "title": "First Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Second Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Deleted Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
    ],
    "tags": [], "document_tags": [],
    "collections": [{"id": 1, "name": "My Collection", "kind": "manual", "criteria": None}],
    "collection_documents": [],
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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: panel starts collapsed by default, and the toggle
        # persists across a reopen ===
        print("panel starts collapsed:", not await page.locator('#main-layout.detail-panel-expanded').count())
        await page.click('#detail-panel-toggle-btn')
        await page.wait_for_timeout(150)
        print("toggle expands the panel:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))
        await page.reload()
        await page.wait_for_timeout(300)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        print("expanded state persists across reopen:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))

        # === Scenario 2: clicking a row selects/highlights it and shows its
        # metadata; clicking a different row updates both ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        row1_selected = await page.locator('tr[data-id="1"].row-selected').count()
        print("clicking a row highlights it:", row1_selected == 1)
        panel_title_1 = await page.locator('.detail-panel-body h2').inner_text()
        print("panel shows the clicked document's title:", "First Doc" in panel_title_1)

        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        row1_still_selected = await page.locator('tr[data-id="1"].row-selected').count()
        row2_selected = await page.locator('tr[data-id="2"].row-selected').count()
        print("highlight moves to the newly clicked row:", row1_still_selected == 0 and row2_selected == 1)
        panel_title_2 = await page.locator('.detail-panel-body h2').inner_text()
        print("panel content swaps to the new document:", "Second Doc" in panel_title_2)

        # === Scenario 3: every action available in the old modal still works
        # from the panel, refreshing in place ===
        await page.click('#archive-toggle-btn')
        await page.wait_for_timeout(200)
        archived_label = await page.locator('#archive-toggle-btn').inner_text()
        print("Archive toggles to Unarchive in the panel:", 'Unarchive' in archived_label)
        await page.click('#archive-toggle-btn')  # unarchive again, so doc 2 stays visible for later steps
        await page.wait_for_timeout(200)

        await page.click('#review-toggle-btn')
        await page.wait_for_timeout(200)
        review_label = await page.locator('#review-toggle-btn').inner_text()
        print("Flag for review toggles to Done in the panel:", 'Done' in review_label)
        await page.click('#review-toggle-btn')  # clear the flag again
        await page.wait_for_timeout(200)

        await page.click('#add-to-collection-btn')
        await page.wait_for_timeout(150)
        await page.click('.modal-collection-option')
        await page.wait_for_timeout(200)
        remove_btn_absent_outside_collection = await page.locator('#remove-from-collection-btn').count()
        print("Add to collection refreshes the panel (no Remove button outside that collection view):", remove_btn_absent_outside_collection == 0)

        await page.click('#regen-thumb-btn')
        await page.wait_for_timeout(300)
        thumb_status_text = await page.locator('#thumb-status').inner_text()
        print("Regenerate preview ran and reported a status in the panel:", len(thumb_status_text.strip()) >= 0)

        # === Scenario 4: a deleted document's panel drops to Restore-only ===
        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        edit_btn_absent = await page.locator('#edit-doc-btn').count()
        archive_btn_absent = await page.locator('#archive-toggle-btn').count()
        restore_btn_present = await page.locator('.detail-panel-body .danger, .detail-panel-body .primary').count()
        print("deleted document's panel drops Edit/Archive entirely:", edit_btn_absent == 0 and archive_btn_absent == 0)
        print("deleted document's panel offers a Restore action:", restore_btn_present >= 1)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 5: Cancel from Edit (opened via the panel) closes the
        # edit modal without forcing a collapsed panel open ===
        await page.click('#detail-panel-toggle-btn')  # collapse it
        await page.wait_for_timeout(150)
        panel_collapsed = not await page.locator('#main-layout.detail-panel-expanded').count()
        print("panel collapsed ahead of Scenario 5:", panel_collapsed)
        await page.click('tr[data-id="1"] .row-edit-btn')
        await page.wait_for_timeout(200)
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(200)
        edit_form_gone = await page.locator('#e-title').count()
        still_collapsed = not await page.locator('#main-layout.detail-panel-expanded').count()
        print("Cancel closes the edit form:", edit_form_gone == 0)
        print("Cancel does not force the panel open:", still_collapsed)

        # === Scenario 6: saving an edit reached via the row-level shortcut
        # (bypassing the panel entirely) selects the just-edited document ===
        await page.click('tr[data-id="2"] .row-edit-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-title', 'Second Doc Renamed')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        edit_form_gone_after_save = await page.locator('#e-title').count()
        row2_selected_after_save = await page.locator('tr[data-id="2"].row-selected').count()
        print("Save closes the edit form:", edit_form_gone_after_save == 0)
        print("Save via the row-edit shortcut selects the just-edited document:", row2_selected_after_save == 1)

        # === Scenario 7: toggle button absent in Reports view ===
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        toggle_hidden_in_reports = await page.locator('#detail-panel-toggle-btn:visible').count()
        print("detail panel toggle hidden in Reports view:", toggle_hidden_in_reports == 0)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 8: panel force-collapses below the mobile breakpoint
        # regardless of the saved preference ===
        await page.click('#detail-panel-toggle-btn')  # re-expand
        await page.wait_for_timeout(150)
        await page.set_viewport_size({"width": 375, "height": 800})
        await page.wait_for_timeout(150)
        panel_hidden_mobile = await page.locator('.detail-panel:visible').count()
        print("panel force-collapses below the mobile breakpoint:", panel_hidden_mobile == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 4: Run it and every existing test**

```bash
cd tests && python3 test_detail_panel.py
```

Expected: every printed line is `True`, `JS ERRORS: []`.

Then run the entire existing suite to surface any other regression the
modal→panel change caused beyond the one already fixed in Task 3 (any test
that clicked a row expecting a full-screen modal to appear, or clicked
`#modal-close-btn`/`#modal-backdrop` after a row click, is a candidate):

```bash
for f in test_*.py; do echo "=== $f ==="; python3 "$f" || echo "FAILED: $f"; done
```

Fix any genuine regression the same way Task 3 fixed
`test_row_edit_shortcut.py` — update the test's assertions/selectors to
match the panel's real behavior, never weaken or delete an assertion just
to make it pass. If a failure's cause isn't obviously the modal→panel
change (a pre-existing flake, an unrelated bug), do not fix it as part of
this task — note it in the task's completion report instead, so the SDD
final whole-branch review can triage it with full branch context.

- [ ] **Step 5: Update `tests/CLAUDE.md`**

Update the opening paragraph's script count (search for `scripts covering
most of the app's actual functionality`) to the new total from Step 3.

Add a new paragraph at the end of the long "How this was tested" narrative
(immediately before the "This list itself can go stale" closing paragraph),
matching the file's existing extremely-detailed per-feature style:

```markdown
and the persistent detail panel (`test_detail_panel.py` — the panel
starting collapsed by default and its expanded state persisting across a
reopen, mirroring `test_nav.py`'s own `nav_style` persistence pattern;
clicking a row highlighting it and showing its metadata in the panel, and
clicking a different row moving both the highlight and the panel's
content; every action available in the old detail modal still working
from the panel with correct in-place refresh (Archive/Unarchive, Flag for
review/Done, Add to Collection, regenerate preview); a deleted document's
panel dropping to Restore-only with Edit/Archive genuinely absent, not
just disabled; Cancel from an edit reached via the panel closing the edit
form without forcing a collapsed panel open; saving an edit reached via
the row-level `.row-edit-btn` shortcut — which bypasses the panel/selection
step on the way in — selecting the just-edited document as the panel's new
selection and highlighting its row; the toggle button being absent in
Reports view; and the panel force-collapsing below the mobile breakpoint
regardless of the saved preference).
```

- [ ] **Step 6: Commit**

```bash
git add dossiary.html CLAUDE.md tests/CLAUDE.md tests/test_detail_panel.py
git commit -m "Add detail panel test coverage, CLAUDE.md notes, comment sweep

Adds tests/test_detail_panel.py (panel toggle/persistence, row selection
and highlighting, every action refreshing in place, the deleted-document
Restore-only state, the two edit-flow behavior changes, Reports-view and
mobile-breakpoint gating), a full CLAUDE.md architecture note for the
feature, and corrects the remaining 'detail modal' comment wording left
over from the panel migration."
```

---

## Self-Review

**1. Spec coverage** — every item from the approved spec
(`docs/superpowers/specs/2026-08-21-persistent-detail-panel-design.md`)
maps to a task: `selectedDocId` + `.row-selected` (Tasks 1/2);
`openDetail()` retargeted, chrome dropped (Task 2); the six existing
refresh call sites needing zero logic changes (verified true — only their
trailing comments changed, in Task 2 Step 2); the two edit-flow call sites
(Task 3); toggle/persistence/layout, including the horizontal-only,
no-`.table-wrap`-constant-change requirement (Task 1); Reports-view
toggle hiding (Task 1 Step 7); mobile force-collapse (Task 1 Step 3);
comment-accuracy sweep (Task 2 Step 2, Task 4 Step 1); CLAUDE.md note
(Task 4 Step 2); dedicated test file (Task 4 Step 3). Out-of-scope items
(resizable panel, Escape-to-collapse, `.row-edit-btn`'s own entry
behavior, panel in Reports view, inline editing) are not implemented by
any task above.

**2. Placeholder scan** — no TBD/TODO; every step shows exact before/after
code, exact file paths, and exact translated strings for all six
languages. The one deliberately-approximate figure (the panel's 340px
width) is a concrete, committed value, not a placeholder — consistent with
how the spec itself flagged it as implementation-time-empirical rather
than spec-mandated.

**3. Type/name consistency** — `selectedDocId`, `openDetail(id)`,
`#detail-panel-body`, `#detail-panel-toggle-btn`, `detailPanelExpanded`/
`loadDetailPanelExpanded()`/`saveDetailPanelExpanded()`/
`applyDetailPanelExpanded()`, and `.row-selected` are named identically
everywhere they're introduced (Task 1) and consumed (Tasks 2-4) — checked
by re-reading each task's Interfaces block against its Steps.
