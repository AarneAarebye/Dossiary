# UI Language Support (English/German) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate every piece of Dossiary's own fixed UI text (nav, toolbar, table, forms, modals, status messages, empty-state screens) into German, switchable at any time via a footer toggle, with auto-detection from the browser's language on first load.

**Architecture:** A single `STRINGS = {en:{...}, de:{...}}` dictionary plus a `t(key, params)` lookup function. Static HTML gets `data-i18n`/`data-i18n-placeholder`/`data-i18n-title` attributes, applied by `applyI18n()`. Dynamically-rendered JS (table rows, modals, status messages) calls `t()` inline. Language choice lives in `localStorage` (not the per-library `settings` table), since the empty-state screen needs translating before any library/database exists.

**Tech Stack:** Vanilla JS, no build step, no new dependencies — same as the rest of `dossiary.html`. Tests use the existing Playwright + `stub_studio2.js` conventions in `tests/`.

## Global Constraints

- No new dependencies, no build step, no bundler — `dossiary.html` stays one file.
- User data (category/tag/field names, titles, notes, OCR text) is **never** translated — only Dossiary's own fixed chrome.
- Language choice persists in `localStorage` under key `dossiary_lang`, independent of any library's `settings` table.
- Missing/untranslated keys fall back to English, then to the raw key string — never blank.
- No ICU/pluralization library. Count-dependent strings use a **singular/plural key pair** picked by a ternary at the call site (matching the ternary logic already present in the current English-only code) — each language supplies its own grammatically correct singular and plural phrasing independently. This is a deliberate refinement over the original spec's "single invariant form" suggestion: the code already branches on count today, so wrapping each existing branch in `t()` costs nothing extra and produces correct German grammar (e.g. `Seite`/`Seiten`, not an invented invariant form).
- All work happens directly on `dossiary.html` (no new files except the test file and this plan's docs).

---

## Task 1: Infrastructure — `STRINGS`, `t()`, `applyI18n()`, language toggle, persistence

**Files:**
- Modify: `dossiary.html` (footer markup ~line 620, module-level constants ~line 638, static-wiring pass ~line 1227-1233, date-formatting call site ~line 2313)
- Create: `tests/test_i18n.py`

**Interfaces:**
- Produces: `STRINGS` (object, `{en: {...}, de: {...}}`), `t(key, params)` (function, returns string), `applyI18n()` (function, no args, walks `[data-i18n]`/`[data-i18n-placeholder]`/`[data-i18n-title]`), `currentLang` (module-level `let`, `'en'`|`'de'`), `setLang(lang)` (function), `loadLang()`/`saveLang(lang)` (functions backing `localStorage`).
- Consumes: nothing new (this is the foundation every later task builds on).

This task defines the `STRINGS` object's shape, the lookup/apply machinery, and its first handful of shared entries (`common*`, `emptyTitle`). Every later task grows the same `STRINGS.en`/`STRINGS.de` objects with the keys its own area needs, in the same commit that wires them up via `data-i18n*` attributes or `t()` calls — translation and wiring are never split across separate commits, so the dictionary and its usages can never drift out of sync mid-task. Where a later task's strings are identical in wording to an earlier task's (e.g. "Cancel", "Run OCR", a page-count phrase), it reuses that existing key instead of duplicating it — each task's own section below says explicitly which keys it reuses versus which it adds new.

- [ ] **Step 1: Write the failing test**

Create `tests/test_i18n.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # === Scenario 1: default language with no navigator.language override
        # matches existing English strings (regression guard) ===
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        title_text = await page.locator('#empty-state h2').inner_text()
        print("Scenario 1 -- default (no locale signal) shows English:", title_text == "No library open")
        await page.close()

        # === Scenario 2: navigator.language = de-DE with no stored preference
        # yet results in German on first load ===
        page2 = await browser.new_page()
        await page2.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'de-DE' });
            Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de'] });
        """)
        await page2.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page2.add_init_script(stub_js)
        await page2.goto(f"file://{APP_PATH}")
        await page2.wait_for_timeout(200)
        title_text_de = await page2.locator('#empty-state h2').inner_text()
        print("Scenario 2 -- de-DE browser locale auto-detects German:", title_text_de == "Keine Bibliothek geöffnet")

        # === Scenario 3: clicking the toggle switches the empty-state title,
        # and the choice persists across reload, overriding navigator.language ===
        await page2.click('#lang-toggle')
        await page2.wait_for_timeout(100)
        title_after_toggle = await page2.locator('#empty-state h2').inner_text()
        print("Scenario 3 -- toggle switches to English:", title_after_toggle == "No library open")
        await page2.reload()
        await page2.wait_for_timeout(200)
        title_after_reload = await page2.locator('#empty-state h2').inner_text()
        print("Scenario 3 -- manual choice persists across reload (overrides de-DE browser locale):", title_after_reload == "No library open")

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL — `#lang-toggle` doesn't exist yet, `#empty-state h2` text is always "No library open" regardless of locale.

- [ ] **Step 3: Add `STRINGS`, `t()`, `applyI18n()`, language state/persistence**

Add near the top of the `<script>` block in `dossiary.html`, immediately after the `APP_VERSION` line (~line 638):

```js
  // --- i18n ---
  // See CLAUDE.md's UI language note for the full rationale. Summary: STRINGS is
  // a flat, two-language dictionary; t() looks a key up in the current language,
  // falling back to English then to the raw key so a missing/untranslated key
  // never renders blank. data-i18n* attributes cover fixed markup (applyI18n()
  // walks them); anything built fresh in JS (table rows, modals, status
  // messages) calls t() directly in its own template string. Language choice is
  // in localStorage, not the per-library `settings` table -- the empty-state
  // "Open library folder" screen has to translate before any library/database
  // exists, so a per-library setting can't be the only mechanism.
  const STRINGS = {
    en: {
      commonCancel: 'Cancel', commonSave: 'Save', commonDone: 'Done', commonDelete: 'Delete',
      commonAdd: 'Add', commonClear: 'Clear', commonRemove: 'Remove', commonNone: '— None —',
      commonDocumentFallback: 'Document #{id}', commonYes: 'Yes', commonNo: 'No',
      langToggleTitle: 'Switch language',
    },
    de: {
      commonCancel: 'Abbrechen', commonSave: 'Speichern', commonDone: 'Fertig', commonDelete: 'Löschen',
      commonAdd: 'Hinzufügen', commonClear: 'Leeren', commonRemove: 'Entfernen', commonNone: '— Keine —',
      commonDocumentFallback: 'Dokument Nr. {id}', commonYes: 'Ja', commonNo: 'Nein',
      langToggleTitle: 'Sprache wechseln',
    },
  };

  function t(key, params){
    let str = STRINGS[currentLang][key] ?? STRINGS.en[key] ?? key;
    if(params){
      for(const [k, v] of Object.entries(params)) str = str.replaceAll(`{${k}}`, v);
    }
    return str;
  }

  function applyI18n(){
    document.querySelectorAll('[data-i18n]').forEach(elm => { elm.textContent = t(elm.dataset.i18n); });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(elm => { elm.placeholder = t(elm.dataset.i18nPlaceholder); });
    document.querySelectorAll('[data-i18n-title]').forEach(elm => { elm.title = t(elm.dataset.i18nTitle); });
  }

  function loadLang(){
    const stored = localStorage.getItem('dossiary_lang');
    if(stored === 'en' || stored === 'de') return stored;
    const langs = navigator.languages || [navigator.language || ''];
    return langs.some(l => l.toLowerCase().startsWith('de')) ? 'de' : 'en';
  }
  function saveLang(lang){ localStorage.setItem('dossiary_lang', lang); }

  let currentLang = loadLang();

  function setLang(lang){
    currentLang = lang;
    saveLang(lang);
    applyI18n();
    if(rootDirHandle){ render(); }
  }
```

`rootDirHandle` is declared later in the file (~line 710) but this function isn't *called* until after the whole script has parsed, so the forward reference is fine — same pattern already used elsewhere in this file (e.g. `resetAll()` referencing `el()`-wrapped DOM lookups defined below it).

Add the footer toggle markup in `dossiary.html`, right after the existing `app-version-label` span (~line 621):

```html
    © 2026 Aarne Aarebye · <span id="app-version-label"></span> ·
    <button type="button" id="lang-toggle" data-i18n-title="langToggleTitle"></button> ·
    MIT License ·
```

Add its own small style rule next to the other footer rules (~line 419, after `footer a:hover`):

```css
  #lang-toggle{ font-family:var(--font-mono); font-size:11px; padding:2px 6px; border:1px solid var(--line); border-radius:var(--radius); background:transparent; color:var(--text-dim); cursor:pointer; }
  #lang-toggle:hover{ color:var(--phosphor); border-color:var(--phosphor-dim); }
```

Wire it and call `applyI18n()` once during the existing static-wiring pass, right after the `app-version-label` line (~line 1232):

```js
  el('app-version-label').textContent = `v${APP_VERSION}`;
  el('lang-toggle').textContent = currentLang === 'de' ? 'EN' : 'DE'; // shows the language you'd SWITCH TO
  el('lang-toggle').addEventListener('click', () => {
    setLang(currentLang === 'de' ? 'en' : 'de');
    el('lang-toggle').textContent = currentLang === 'de' ? 'EN' : 'DE';
  });
  applyI18n();
```

Give the empty-state heading its first `data-i18n` attribute, proving the whole pipeline end-to-end on the pre-library screen (~line 551):

```html
      <div id="empty-state" class="empty">
        <h2 data-i18n="emptyTitle">No library open</h2>
```

Add the two keys this needs to both `STRINGS.en` and `STRINGS.de`:

```js
    // in STRINGS.en, alongside the common* keys:
      emptyTitle: 'No library open',
    // in STRINGS.de:
      emptyTitle: 'Keine Bibliothek geöffnet',
```

Finally, update `resetAll()`'s matching literal (~line 1335) to use the same key so the two stay in sync:

```js
    subLabel.textContent = 'No library open'; statsEl.innerHTML = ''; setStatus('');
```
becomes:
```js
    subLabel.textContent = t('emptyTitle'); statsEl.innerHTML = ''; setStatus('');
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS — all three scenarios print `True`, no JS errors.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Add STRINGS/t()/applyI18n() i18n infrastructure and footer language toggle"
```

---

## Task 2: Locale-aware date formatting

**Files:**
- Modify: `dossiary.html:2313`

**Interfaces:**
- Consumes: `currentLang` (from Task 1)
- Produces: nothing new for later tasks — this is a self-contained one-line behavioral change.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`, before `print("JS ERRORS:", errors)` at the end of `main()` (this task reuses the browser/page from Scenario 2/3, already in German):

```python
        # === Scenario 4: date formatting follows the UI language, not just the
        # browser's OS locale (page2 is currently in English after Scenario 3's
        # toggle click -- switch back to German and open a seeded document's
        # detail view to check the date format) ===
        await page2.click('#lang-toggle')
        await page2.wait_for_timeout(100)
        SEED = {"documents": [{
            "id": 1, "title": "Test Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-03-05T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-05T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        }], "tags": [], "document_tags": []}
        await page2.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page2.click("#open-btn")
        await page2.wait_for_timeout(300)
        await page2.click('tr[data-id="1"]')
        await page2.wait_for_timeout(200)
        meta_text = await page2.locator('.modal-meta').inner_text()
        print("Scenario 4 -- German UI language produces German-formatted date (contains 'März'):", 'März' in meta_text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL — the date renders in English month formatting (`Mar 5, 2026`) regardless of `currentLang`.

- [ ] **Step 3: Change the date-formatting call site**

In `dossiary.html:2313`, change:

```js
    return d.toLocaleDateString(undefined, { year:'numeric', month:'short', day:'2-digit' });
```
to:
```js
    return d.toLocaleDateString(currentLang === 'de' ? 'de-DE' : 'en-US', { year:'numeric', month:'short', day:'2-digit' });
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Make date formatting follow the selected UI language, not just OS locale"
```

---

## Task 3: Nav, toolbar, inbox banner, bulk action bar

**Files:**
- Modify: `dossiary.html` (static markup ~lines 464-589, `renderStats()` ~2230-2234, `populateFilters()` ~2245-2277, `renderBulkActionBar()` ~2772-2796, `renderNav()`/collections nav items)

**Interfaces:**
- Consumes: `t()`, `applyI18n()` (Task 1)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append a new scenario to `tests/test_i18n.py` (new page, seeded library, switch to German, check nav/toolbar/stats text):

```python
        # === Scenario 5: nav, toolbar, and stats switch to German ===
        page3 = await browser.new_page()
        await page3.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page3.add_init_script(stub_js)
        await page3.goto(f"file://{APP_PATH}")
        await page3.wait_for_timeout(200)
        await page3.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page3.click("#open-btn")
        await page3.wait_for_timeout(300)
        await page3.click('#lang-toggle')
        await page3.wait_for_timeout(150)
        nav_all_text = await page3.locator('#nav-item-all .nav-item-label').inner_text()
        add_btn_text = await page3.locator('#add-btn').inner_text()
        stats_text = await page3.locator('#stats').inner_text()
        print("Scenario 5 -- nav item translated:", nav_all_text == "Alle Dokumente")
        print("Scenario 5 -- toolbar button translated:", "Dokument hinzufügen" in add_btn_text)
        print("Scenario 5 -- stats bar translated:", "Dokumente" in stats_text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL — nav/toolbar/stats stay in English after the toggle.

- [ ] **Step 3: Add keys and wire the nav/toolbar/inbox-banner/bulk-bar markup**

Add to `STRINGS.en`/`STRINGS.de` (Task 1's dictionary object — insert alongside the existing keys):

```js
    // STRINGS.en additions:
      navAllDocuments: 'All Documents', navInbox: 'Inbox', navWasteBin: 'Waste bin', navReports: 'Reports',
      navCollections: 'Collections', navSaveSmartCollection: '☆ Save as Smart Collection',
      navSmartCollectionNamePlaceholder: 'Collection name', navStyleToggleTitle: 'Switch to top-tab navigation',
      navStyleToggleAriaLabel: 'Switch navigation layout',
      toolbarSearchPlaceholder: 'Search title, category, notes, tags, OCR text…',
      toolbarSearchClearAriaLabel: 'Clear search', toolbarAllCategories: 'All categories',
      toolbarAllTypes: 'All types', toolbarAllPeople: 'All people', toolbarAllDynamic: 'All {label}',
      toolbarShowArchived: 'Show archived', toolbarBreakdownByTitle: 'Break down by',
      toolbarFromDateTitle: 'From date', toolbarToDateTitle: 'To date',
      toolbarManageFields: '⚙ Manage fields', toolbarManageCollections: '⚙ Manage collections',
      toolbarCheckInbox: '📥 Check inbox', toolbarAddDocument: '＋ Add document',
      toolbarSwitchLibrary: 'Switch library', toolbarColumns: '⚙ Columns',
      inboxBannerAddAll: 'Add all',
      bulkAddToCollection: 'Add to collection ▾', bulkNewCollectionPlaceholder: 'New collection name',
      bulkCreateAndAdd: 'Create & add', bulkArchive: 'Archive', bulkFlagForReview: 'Flag for review',
      bulkRestore: 'Restore', bulkClearSelection: 'Clear selection', bulkSelectedCount: '{count} selected',
      bulkNewCollectionMenuItem: '+ New collection…',
      statsDocuments: 'documents', statsCategories: 'categories', statsCapturedHere: 'captured here',
    // STRINGS.de additions:
      navAllDocuments: 'Alle Dokumente', navInbox: 'Posteingang', navWasteBin: 'Papierkorb', navReports: 'Berichte',
      navCollections: 'Sammlungen', navSaveSmartCollection: '☆ Als intelligente Sammlung speichern',
      navSmartCollectionNamePlaceholder: 'Sammlungsname', navStyleToggleTitle: 'Zur Reiternavigation wechseln',
      navStyleToggleAriaLabel: 'Navigationslayout wechseln',
      toolbarSearchPlaceholder: 'Titel, Kategorie, Notizen, Tags, OCR-Text durchsuchen…',
      toolbarSearchClearAriaLabel: 'Suche leeren', toolbarAllCategories: 'Alle Kategorien',
      toolbarAllTypes: 'Alle Typen', toolbarAllPeople: 'Alle Personen', toolbarAllDynamic: 'Alle {label}',
      toolbarShowArchived: 'Archivierte anzeigen', toolbarBreakdownByTitle: 'Aufschlüsseln nach',
      toolbarFromDateTitle: 'Von Datum', toolbarToDateTitle: 'Bis Datum',
      toolbarManageFields: '⚙ Felder verwalten', toolbarManageCollections: '⚙ Sammlungen verwalten',
      toolbarCheckInbox: '📥 Posteingang prüfen', toolbarAddDocument: '＋ Dokument hinzufügen',
      toolbarSwitchLibrary: 'Bibliothek wechseln', toolbarColumns: '⚙ Spalten',
      inboxBannerAddAll: 'Alle hinzufügen',
      bulkAddToCollection: 'Zu Sammlung hinzufügen ▾', bulkNewCollectionPlaceholder: 'Neuer Sammlungsname',
      bulkCreateAndAdd: 'Erstellen & hinzufügen', bulkArchive: 'Archivieren', bulkFlagForReview: 'Zur Prüfung markieren',
      bulkRestore: 'Wiederherstellen', bulkClearSelection: 'Auswahl aufheben', bulkSelectedCount: '{count} ausgewählt',
      bulkNewCollectionMenuItem: '+ Neue Sammlung…',
      statsDocuments: 'Dokumente', statsCategories: 'Kategorien', statsCapturedHere: 'hier erfasst',
```

Note `bulkDone`/`bulkDelete` were already defined in Task 1 (`commonDone`/`commonDelete`) — reuse those instead of duplicating: `renderBulkActionBar()`'s Delete button and the Inbox-view "Done" relabel use `t('commonDelete')`/`t('commonDone')`.

Apply `data-i18n`/`data-i18n-placeholder`/`data-i18n-title` attributes to the static nav/toolbar/inbox-banner/bulk-bar markup (~lines 464-589), e.g.:

```html
<span class="nav-item-label" data-i18n="navAllDocuments">All Documents</span>
...
<span class="nav-item-label" data-i18n="navInbox">Inbox</span>
...
<span class="nav-item-label" data-i18n="navWasteBin">Waste bin</span>
...
<span class="nav-item-label" data-i18n="navReports">Reports</span>
...
<span class="nav-item-label" data-i18n="navCollections">Collections</span>
...
<button type="button" id="save-smart-collection-btn" class="nav-save-smart-btn" style="display:none;" data-i18n="navSaveSmartCollection">☆ Save as Smart Collection</button>
...
<input type="text" id="smart-collection-name-input" data-i18n-placeholder="navSmartCollectionNamePlaceholder" placeholder="Collection name" />
<button type="button" id="smart-collection-name-save-btn" data-i18n="commonSave">Save</button>
<button type="button" id="smart-collection-name-cancel-btn" data-i18n="commonCancel">Cancel</button>
...
<button type="button" class="nav-style-toggle" id="nav-style-toggle" data-i18n-title="navStyleToggleTitle" title="Switch to top-tab navigation" aria-label="Switch navigation layout">⇄</button>
```

apply the same `data-i18n-title="navStyleToggleAriaLabel"` treatment is not possible for `aria-label` since `applyI18n()` (Task 1) only handles `textContent`/`placeholder`/`title`. Add a fourth attribute kind now, since this is the first `aria-label` this project needs to translate — extend `applyI18n()` (in `dossiary.html`, the function added in Task 1) with one more block:

```js
  function applyI18n(){
    document.querySelectorAll('[data-i18n]').forEach(elm => { elm.textContent = t(elm.dataset.i18n); });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(elm => { elm.placeholder = t(elm.dataset.i18nPlaceholder); });
    document.querySelectorAll('[data-i18n-title]').forEach(elm => { elm.title = t(elm.dataset.i18nTitle); });
    document.querySelectorAll('[data-i18n-aria-label]').forEach(elm => { elm.setAttribute('aria-label', t(elm.dataset.i18nAriaLabel)); });
  }
```

then:

```html
<button type="button" class="nav-style-toggle" id="nav-style-toggle" data-i18n-title="navStyleToggleTitle" data-i18n-aria-label="navStyleToggleAriaLabel" title="Switch to top-tab navigation" aria-label="Switch navigation layout">⇄</button>
```

Continue the same pattern for the rest of the toolbar/inbox-banner/bulk-bar static markup:

```html
<input class="search" id="search" type="text" data-i18n-placeholder="toolbarSearchPlaceholder" placeholder="Search title, category, notes, tags, OCR text…" />
<button type="button" class="clear-btn" id="search-clear" data-i18n-title="commonClear" data-i18n-aria-label="toolbarSearchClearAriaLabel" title="Clear" aria-label="Clear search">✕</button>
<span class="filter-wrap" data-field="category"><select id="category-filter"><option value="" data-i18n="toolbarAllCategories">All categories</option></select></span>
<span class="filter-wrap" data-field="document_type"><select id="type-filter"><option value="" data-i18n="toolbarAllTypes">All types</option></select></span>
<span class="filter-wrap" data-field="people"><select id="person-filter"><option value="" data-i18n="toolbarAllPeople">All people</option></select></span>
<label class="show-archived-toggle" id="show-archived-wrap">
  <input type="checkbox" id="show-archived-toggle" /> <span data-i18n="toolbarShowArchived">Show archived</span>
</label>
<select id="report-breakdown-field" data-i18n-title="toolbarBreakdownByTitle" title="Break down by"></select>
<input type="date" id="report-date-from" data-i18n-title="toolbarFromDateTitle" title="From date" />
<input type="date" id="report-date-to" data-i18n-title="toolbarToDateTitle" title="To date" />
<button id="manage-fields-btn" data-i18n="toolbarManageFields">⚙ Manage fields</button>
<button id="manage-collections-btn" data-i18n="toolbarManageCollections">⚙ Manage collections</button>
<button id="inbox-check-btn" data-i18n="toolbarCheckInbox">📥 Check inbox</button>
<button class="accent" id="add-btn" data-i18n="toolbarAddDocument">＋ Add document</button>
<button id="reload-btn" data-i18n="toolbarSwitchLibrary">Switch library</button>
<button id="columns-btn" data-i18n="toolbarColumns">⚙ Columns</button>
...
<button class="accent" id="inbox-add-all-btn" data-i18n="inboxBannerAddAll">Add all</button>
...
<button type="button" id="bulk-add-to-collection-btn" data-i18n="bulkAddToCollection">Add to collection ▾</button>
<input type="text" id="bulk-new-collection-input" data-i18n-placeholder="bulkNewCollectionPlaceholder" placeholder="New collection name" />
<button type="button" id="bulk-new-collection-save-btn" data-i18n="bulkCreateAndAdd">Create &amp; add</button>
<button type="button" id="bulk-new-collection-cancel-btn" data-i18n="commonCancel">Cancel</button>
<button type="button" id="bulk-archive-btn" data-i18n="bulkArchive">Archive</button>
<button type="button" id="bulk-delete-btn" data-i18n="commonDelete">Delete</button>
<button type="button" id="bulk-review-btn" data-i18n="bulkFlagForReview">Flag for review</button>
<button type="button" id="bulk-restore-btn" style="display:none;" data-i18n="bulkRestore">Restore</button>
<button type="button" id="bulk-clear-selection-btn" data-i18n="bulkClearSelection">Clear selection</button>
```

Note the `<label class="show-archived-toggle">` change wraps the text in a `<span>` since the label also contains the checkbox `<input>` — `applyI18n()`'s `textContent =` assignment would otherwise wipe out the checkbox element itself if applied directly to the `<label>`.

Update `renderStats()` (~2230-2234) to use `t()` instead of hardcoded text:

```js
    `<div class="stat"><b>${allDocs.length}</b>${t('statsDocuments')}</div>` /* was: literal 'documents' */
    `<div class="stat"><b>${cats.size}</b>${t('statsCategories')}</div>` /* was: literal 'categories' */
    `<div class="stat"><b>${captured}</b>${t('statsCapturedHere')}</div>` /* was: literal 'captured here' */
```

Update `populateFilters()` (~2245-2277) dynamic-field "All {label}" option:

```js
    // was: `<option value="">All ${escapeHtml(f.label.toLowerCase())}</option>`
    `<option value="">${t('toolbarAllDynamic', {label: escapeHtml(f.label.toLowerCase())})}</option>`
```

Update `renderBulkActionBar()` (~2772-2796):

```js
    // was: `${selectedDocIds.size} selected`
    t('bulkSelectedCount', {count: selectedDocIds.size})
    // was: currentView === 'inbox' ? 'Done' : 'Flag for review'
    currentView === 'inbox' ? t('commonDone') : t('bulkFlagForReview')
```

Update the bulk "+ New collection…" menu item and any other inline-JS-rendered nav/collections strings the same way, using `t('bulkNewCollectionMenuItem')`.

Add `applyI18n()` and re-render calls to the toggle handler already wired in Task 1 — no change needed there since `setLang()` already calls `applyI18n()` and `render()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate nav, toolbar, inbox banner, and bulk action bar"
```

---

## Task 4: Empty-state, init-state, recent libraries, library open/init status messages

**Files:**
- Modify: `dossiary.html` (~lines 550-569 static markup, `openLibrary()`/`proceedWithRootDirHandle()`/`initNewLibrary()`/`loadDb()`/`afterDbReady()`/`resetAll()` ~lines 1235-1337, `renderRecentLibraries()`/`reconnectRecentLibrary()` ~lines 1170-1223)

**Interfaces:**
- Consumes: `t()` (Task 1)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
        # === Scenario 6: empty-state body, init-state (no library.sqlite),
        # and library-open status messages translate ===
        page4 = await browser.new_page()
        await page4.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'de-DE' });
        """)
        await page4.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page4.add_init_script(stub_js)
        await page4.goto(f"file://{APP_PATH}")
        await page4.wait_for_timeout(200)
        open_btn_text = await page4.locator('#open-btn').inner_text()
        print("Scenario 6 -- empty-state open button translated:", open_btn_text == "Bibliotheksordner öffnen")
        await page4.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();") # empty folder, no library.sqlite
        await page4.click("#open-btn")
        await page4.wait_for_timeout(300)
        init_title = await page4.locator('#init-state h2').inner_text()
        print("Scenario 6 -- init-state (no library.sqlite) translated:", init_title == "Leerer Ordner")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, wire markup, replace `setStatus()` literals**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      emptyBody: 'Open a Dossiary library folder, or start a brand new one here. Everything happens locally in your browser — nothing is uploaded.',
      emptyOpenButton: 'Open library folder',
      emptyHintBrowser: "Needs Chrome or Edge (the File System Access API isn't supported in Safari/Firefox).",
      emptyHintWriteAccess: 'This app needs write access to save new documents, so pick "Edit"/allow when your browser asks.',
      emptyHintImportant: 'Important: open this file directly in your browser (not inside a chat preview pane) — folder write access is blocked inside embedded frames.',
      initTitle: 'Empty folder', initMessageDefault: 'No <code>library.sqlite</code> found in that folder.',
      initMessageWithName: 'No <code>library.sqlite</code> found in "<b>{name}</b>".',
      initButton: 'Initialize a new library here', initPickAgain: 'Choose a different folder',
      recentLibrariesHeading: 'Recent libraries', recentLibrariesLastOpened: 'Last opened {date}',
      recentLibrariesRemoveTitle: 'Remove', recentLibrariesRemoveAriaLabel: 'Remove {name} from recent libraries',
      recentLibrariesReopenDenied: "Couldn't reopen — access was denied.",
      recentLibrariesReopenFailed: "Couldn't reopen — folder may have moved or access was denied.",
      statusNoFsaSupport: 'Your browser does not support the File System Access API. Use Chrome or Edge.',
      statusOpeningFolderPicker: 'Opening folder picker…', statusFolderSelectionCancelled: 'Folder selection cancelled.',
      statusCouldNotOpenFolder: 'Could not open that folder: {error}', statusCheckingForLibrary: 'Checking for library.sqlite…',
      statusSettingUpSqlite: 'Setting up SQLite engine…', statusInitializedNewLibrary: 'Initialized a new empty library.',
      statusCouldNotInitLibrary: 'Could not initialize a new library: {error}',
      statusLoadingSqliteEngine: 'Loading SQLite engine…', statusReadingLibrary: 'Reading library.sqlite…',
      statusOpenedLibrary: 'Opened {count} documents from {name}.',
    // STRINGS.de additions:
      emptyBody: 'Öffne einen Dossiary-Bibliotheksordner oder starte hier eine ganz neue Bibliothek. Alles geschieht lokal in deinem Browser — nichts wird hochgeladen.',
      emptyOpenButton: 'Bibliotheksordner öffnen',
      emptyHintBrowser: 'Erfordert Chrome oder Edge (die File System Access API wird in Safari/Firefox nicht unterstützt).',
      emptyHintWriteAccess: 'Diese App benötigt Schreibzugriff, um neue Dokumente zu speichern — wähle "Bearbeiten"/Erlauben, wenn dein Browser danach fragt.',
      emptyHintImportant: 'Wichtig: Öffne diese Datei direkt in deinem Browser (nicht in einer eingebetteten Chat-Vorschau) — Schreibzugriff auf Ordner ist in eingebetteten Frames blockiert.',
      initTitle: 'Leerer Ordner', initMessageDefault: 'Keine <code>library.sqlite</code> in diesem Ordner gefunden.',
      initMessageWithName: 'Keine <code>library.sqlite</code> in "<b>{name}</b>" gefunden.',
      initButton: 'Neue Bibliothek hier anlegen', initPickAgain: 'Anderen Ordner wählen',
      recentLibrariesHeading: 'Zuletzt geöffnete Bibliotheken', recentLibrariesLastOpened: 'Zuletzt geöffnet: {date}',
      recentLibrariesRemoveTitle: 'Entfernen', recentLibrariesRemoveAriaLabel: '{name} aus zuletzt geöffneten Bibliotheken entfernen',
      recentLibrariesReopenDenied: 'Konnte nicht erneut geöffnet werden — Zugriff wurde verweigert.',
      recentLibrariesReopenFailed: 'Konnte nicht erneut geöffnet werden — Ordner wurde möglicherweise verschoben oder Zugriff wurde verweigert.',
      statusNoFsaSupport: 'Dein Browser unterstützt die File System Access API nicht. Verwende Chrome oder Edge.',
      statusOpeningFolderPicker: 'Ordnerauswahl wird geöffnet…', statusFolderSelectionCancelled: 'Ordnerauswahl abgebrochen.',
      statusCouldNotOpenFolder: 'Ordner konnte nicht geöffnet werden: {error}', statusCheckingForLibrary: 'Suche nach library.sqlite…',
      statusSettingUpSqlite: 'SQLite-Engine wird eingerichtet…', statusInitializedNewLibrary: 'Neue, leere Bibliothek angelegt.',
      statusCouldNotInitLibrary: 'Neue Bibliothek konnte nicht angelegt werden: {error}',
      statusLoadingSqliteEngine: 'SQLite-Engine wird geladen…', statusReadingLibrary: 'library.sqlite wird gelesen…',
      statusOpenedLibrary: '{count} Dokumente aus {name} geöffnet.',
```

Wire the static markup (~lines 550-569):

```html
      <div id="empty-state" class="empty">
        <h2 data-i18n="emptyTitle">No library open</h2>
        <p data-i18n="emptyBody">Open a Dossiary library folder, or start a brand new one here.
           Everything happens locally in your browser — nothing is uploaded.</p>
        <div id="recent-libraries" style="display:none;"></div>
        <button class="primary" id="open-btn" data-i18n="emptyOpenButton">Open library folder</button>
        <div class="hint">
          <span data-i18n="emptyHintBrowser">Needs Chrome or Edge (the File System Access API isn't supported in Safari/Firefox).</span><br/>
          <span data-i18n="emptyHintWriteAccess">This app needs write access to save new documents, so pick <b>"Edit"</b>/allow when your browser asks.</span><br/><br/>
          <b style="color:var(--text)">Important:</b> <span data-i18n="emptyHintImportant">open this file directly in your browser (not inside a chat
          preview pane) — folder write access is blocked inside embedded frames.</span>
        </div>
      </div>

      <div id="init-state" class="empty" style="display:none;">
        <h2 data-i18n="initTitle">Empty folder</h2>
        <p id="init-message" data-i18n="initMessageDefault">No <code>library.sqlite</code> found in that folder.</p>
        <button class="primary" id="init-btn" data-i18n="initButton">Initialize a new library here</button>
        <button id="pick-again-btn" data-i18n="initPickAgain">Choose a different folder</button>
      </div>
```

The `emptyHintBrowser`/`emptyHintWriteAccess`/`emptyHintImportant` keys keep their embedded `<b>`/bold text as literal HTML inside the translated string itself (matching the "Important:" bold prefix, which stays a separate untranslated static `<b>` label since it's short and consistent — only the sentence after it is wrapped). Since `applyI18n()` sets `textContent`, not `innerHTML`, any `<b>` tags embedded inside a `STRINGS` value would render as literal text, not markup — so `emptyHintWriteAccess`'s translated value keeps `"Edit"` as plain quoted text rather than `<b>"Edit"</b>` (the bold styling on that one word is dropped; this is an acceptable, minor visual simplification, not a functional regression — the sentence reads identically either way).

Replace the hardcoded `setStatus()`/`el(...).textContent` literals in `openLibrary()`, `proceedWithRootDirHandle()`, `initNewLibrary()`, `loadDb()`, `afterDbReady()` (~lines 1235-1316):

```js
  async function openLibrary(){
    if(typeof window.showDirectoryPicker !== 'function'){
      setStatus(t('statusNoFsaSupport'), 'err');
      return;
    }
    try{
      setStatus(t('statusOpeningFolderPicker'));
      const handle = await window.showDirectoryPicker({ mode: 'readwrite' });
      await proceedWithRootDirHandle(handle);
    }catch(e){
      if(e.name === 'AbortError'){ setStatus(t('statusFolderSelectionCancelled')); }
      else{ setStatus(t('statusCouldNotOpenFolder', {error: e.message}), 'err'); }
    }
  }

  async function proceedWithRootDirHandle(handle){
    rootDirHandle = handle;
    setStatus(t('statusCheckingForLibrary'));
    try{
      dbFileHandle = await rootDirHandle.getFileHandle('library.sqlite', { create: false });
      filesDirHandle = await rootDirHandle.getDirectoryHandle('files', { create: true });
      await rootDirHandle.getDirectoryHandle('inbox', { create: true });
      await loadDb();
    }catch(e){
      emptyState.style.display = 'none';
      initState.style.display = 'block';
      el('init-message').innerHTML = t('initMessageWithName', {name: `<b>${escapeHtml(rootDirHandle.name)}</b>`});
      setStatus('');
    }
  }

  async function initNewLibrary(){
    try{
      setStatus(t('statusSettingUpSqlite'));
      // ... unchanged body ...
      setStatus(t('statusInitializedNewLibrary'), 'ok');
      afterDbReady();
    }catch(e){
      setStatus(t('statusCouldNotInitLibrary', {error: e.message}), 'err');
    }
  }

  async function loadDb(){
    setStatus(t('statusLoadingSqliteEngine'));
    await ensureSqlJs();
    setStatus(t('statusReadingLibrary'));
    // ... unchanged body ...
    afterDbReady();
  }

  function afterDbReady(){
    emptyState.style.display = 'none';
    initState.style.display = 'none';
    loadDocumentsFromDb();
    setStatus(t('statusOpenedLibrary', {count: allDocs.length, name: rootDirHandle.name}), 'ok');
    checkInbox();
    recordRecentLibrary(rootDirHandle);
  }
```

Note `initMessageWithName`'s `{name}` substitution here deliberately passes an already-`<b>`-wrapped HTML fragment as the interpolated value (matching the original code's `innerHTML` usage at this one call site — every other `t()` usage in this plan sets `textContent`/`.value`/attribute, where this HTML-embedding trick would be wrong; this is the one deliberate exception since `initMessage` is set via `.innerHTML`, not through `applyI18n()`'s attribute-walk).

Update `renderRecentLibraries()` (~1185-1223):

```js
    container.innerHTML = `
      <h3>${t('recentLibrariesHeading')}</h3>
      <div id="recent-libraries-list">
        ${entries.map(entry => `
          <div class="review-queue-row" data-id="${entry.id}">
            <div class="file-preview recent-lib-target" data-id="${entry.id}">
              <div class="file-icon">DIR</div>
              <div style="flex:1;">
                <div class="doc-title">${escapeHtml(entry.name)}</div>
                <div class="doc-sub" id="recent-lib-status-${entry.id}">${t('recentLibrariesLastOpened', {date: formatDate(entry.lastOpenedAt)})}</div>
              </div>
            </div>
            <div class="review-queue-actions">
              <button type="button" class="recent-lib-remove-btn" data-id="${entry.id}" title="${t('recentLibrariesRemoveTitle')}" aria-label="${t('recentLibrariesRemoveAriaLabel', {name: escapeHtml(entry.name)})}">✕</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
```

Update `reconnectRecentLibrary()` (~1170-1183):

```js
      if(perm !== 'granted'){
        if(statusLine) statusLine.textContent = t('recentLibrariesReopenDenied');
        return;
      }
      await proceedWithRootDirHandle(handle);
    }catch(e){
      if(statusLine) statusLine.textContent = t('recentLibrariesReopenFailed');
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate empty-state, init-state, recent libraries, and library-open status messages"
```

---

## Task 5: Main table — headers, pills, showing-count, row-edit button

**Files:**
- Modify: `dossiary.html` (static table headers ~lines 594-608, `render()` ~2674-2762)

**Interfaces:**
- Consumes: `t()` (Task 1)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py` (reusing `page3` from Task 3's scenario, already open with the seeded library and toggled to German):

```python
        # === Scenario 7: table headers and row content translate ===
        col_header_text = await page3.locator('th[data-key="title"]').inner_text()
        print("Scenario 7 -- table column header translated:", col_header_text == "Dokument")
        row_edit_title = await page3.locator('tr[data-id="1"] .row-edit-btn').get_attribute('title')
        print("Scenario 7 -- row-edit button title translated:", row_edit_title == "Bearbeiten")
        count_line_text = await page3.locator('#count-line').inner_text()
        print("Scenario 7 -- showing-count line translated:", "von" in count_line_text and "Dokumenten" in count_line_text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, wire table headers, update `render()`**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      tableColDocument: 'Document', tableColCategory: 'Category', tableColType: 'Type', tableColPeople: 'People',
      tableColDate: 'Date', tableColImported: 'Imported', tableColAmount: 'Amount', tableColTags: 'Tags',
      tableSelectAllTitle: 'Select all visible', tableRowEditTitle: 'Edit',
      tablePillNew: 'new', tablePillFromInbox: 'from inbox', tablePillArchived: 'archived',
      tableShowingCount: 'Showing {shown} of {total} documents', tableNoValue: '—',
    // STRINGS.de additions:
      tableColDocument: 'Dokument', tableColCategory: 'Kategorie', tableColType: 'Typ', tableColPeople: 'Personen',
      tableColDate: 'Datum', tableColImported: 'Importiert', tableColAmount: 'Betrag', tableColTags: 'Tags',
      tableSelectAllTitle: 'Alle sichtbaren auswählen', tableRowEditTitle: 'Bearbeiten',
      tablePillNew: 'neu', tablePillFromInbox: 'aus Posteingang', tablePillArchived: 'archiviert',
      tableShowingCount: '{shown} von {total} Dokumenten angezeigt', tableNoValue: '—',
```

Wire the static table headers (~594-608):

```html
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
```

Update `render()` (~2674-2762) — since `applyI18n()`'s DOM-walk only runs once per `setLang()` call and the table body is *rebuilt* on every `render()` (not just shown/hidden), the row-template's own strings need direct `t()` calls, not `data-i18n`, same as every other dynamically-rendered area:

```js
    // was: `Showing ${sorted.length} of ${denominator} documents`
    t('tableShowingCount', {shown: sorted.length, total: denominator})
    // row-edit button, was: title="Edit"
    `<button class="row-edit-btn" data-id="${d.id}" title="${t('tableRowEditTitle')}">✎</button>`
    // pills, was: 'new' / 'from inbox' / 'archived'
    d.source === 'scan-inbox' ? t('tablePillFromInbox') : t('tablePillNew')
    d.archived ? `<span class="pill archived">${t('tablePillArchived')}</span>` : ''
    // fallback dashes, was: literal '—' at each of the 5 call sites (category/type/people/tags cells)
    t('tableNoValue')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate main table headers, pills, and showing-count line"
```

---

## Task 6: Detail modal

**Files:**
- Modify: `dossiary.html` (`openDetail()` ~2894-3082, `regenerateThumbnail()` ~3176-3209, `copyPathToClipboard()` ~2886-2890)

**Interfaces:**
- Consumes: `t()` (Task 1), `commonDocumentFallback` (Task 1)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py` (reusing `page3`, still German, detail modal not yet open there — click a row):

```python
        # === Scenario 8: detail modal translates ===
        await page3.click('tr[data-id="1"]')
        await page3.wait_for_timeout(200)
        edit_btn_text = await page3.locator('#edit-doc-btn').inner_text()
        print("Scenario 8 -- detail modal Edit button translated:", edit_btn_text == "Bearbeiten")
        fields_heading = await page3.locator('.modal-section h3').first.inner_text()
        print("Scenario 8 -- detail modal section heading translated:", fields_heading in ("Kategorie", "Felder", "Personen"))
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)
```

(The exact first `h3` text depends on which sections render for this seeded doc's type — the assertion checks it's one of the plausible German headings rather than a single exact string, since the seeded doc's configured fields aren't controlled by this test.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update `openDetail()`/`regenerateThumbnail()`/`copyPathToClipboard()`**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      detailOpenFile: 'Open file', detailOpenOriginal: 'Open original file', detailEdit: 'Edit',
      detailRegeneratePreview: 'Regenerate preview', detailGeneratePreview: 'Generate preview',
      detailUnarchive: 'Unarchive', detailArchive: 'Archive',
      detailAddToCollection: 'Add to collection…', detailRemoveFromCollection: 'Remove from this collection',
      detailNoPreviewYet: 'No preview yet', detailPreviewMissing: 'Preview file missing',
      detailCloseAriaLabel: 'Close', detailLabelCategory: 'Category', detailLabelType: 'Type', detailLabelDate: 'Date',
      detailLabelAmount: 'Amount', detailLabelPayment: 'Payment', detailLabelPages: 'Pages',
      detailLabelImported: 'Imported', detailLabelId: 'ID', detailLabelSource: 'Source',
      detailLabelFile: 'File', detailLabelOriginal: 'Original', detailCopyButton: 'Copy', detailCopiedButton: 'Copied!',
      detailNoFileRecorded: 'No file recorded for this document', detailSectionFields: 'Fields',
      detailSectionPeople: 'People', detailSectionTags: 'Tags', detailSectionNotes: 'Notes',
      detailSectionOcrText: 'OCR text', detailCopyClipboardError: 'Could not copy to clipboard: {error}',
      detailOpenFileError: 'Could not open file: {error}', detailGeneratingPreview: 'Generating preview…',
      detailNoFileForPreview: 'This document has no file to generate a preview from.',
      detailUnsupportedPreviewType: "Can't generate a preview from this file type ({type}).",
      detailPreviewGenerationFailed: 'Could not generate preview: {error}',
    // STRINGS.de additions:
      detailOpenFile: 'Datei öffnen', detailOpenOriginal: 'Originaldatei öffnen', detailEdit: 'Bearbeiten',
      detailRegeneratePreview: 'Vorschau neu erzeugen', detailGeneratePreview: 'Vorschau erzeugen',
      detailUnarchive: 'Aus Archiv holen', detailArchive: 'Archivieren',
      detailAddToCollection: 'Zu Sammlung hinzufügen…', detailRemoveFromCollection: 'Aus dieser Sammlung entfernen',
      detailNoPreviewYet: 'Noch keine Vorschau', detailPreviewMissing: 'Vorschaudatei fehlt',
      detailCloseAriaLabel: 'Schließen', detailLabelCategory: 'Kategorie', detailLabelType: 'Typ', detailLabelDate: 'Datum',
      detailLabelAmount: 'Betrag', detailLabelPayment: 'Zahlung', detailLabelPages: 'Seiten',
      detailLabelImported: 'Importiert', detailLabelId: 'ID', detailLabelSource: 'Quelle',
      detailLabelFile: 'Datei', detailLabelOriginal: 'Original', detailCopyButton: 'Kopieren', detailCopiedButton: 'Kopiert!',
      detailNoFileRecorded: 'Für dieses Dokument ist keine Datei hinterlegt', detailSectionFields: 'Felder',
      detailSectionPeople: 'Personen', detailSectionTags: 'Tags', detailSectionNotes: 'Notizen',
      detailSectionOcrText: 'OCR-Text', detailCopyClipboardError: 'Konnte nicht in die Zwischenablage kopieren: {error}',
      detailOpenFileError: 'Datei konnte nicht geöffnet werden: {error}', detailGeneratingPreview: 'Vorschau wird erzeugt…',
      detailNoFileForPreview: 'Für dieses Dokument gibt es keine Datei, aus der eine Vorschau erzeugt werden könnte.',
      detailUnsupportedPreviewType: 'Aus diesem Dateityp ({type}) kann keine Vorschau erzeugt werden.',
      detailPreviewGenerationFailed: 'Vorschau konnte nicht erzeugt werden: {error}',
```

`openDetail()` builds its HTML fresh on every open (like the table row template), so replace each literal with a `t()` call at its exact call site — e.g.:

```js
    // was: 'Open file'
    t('detailOpenFile')
    // was: 'Open original file'
    t('detailOpenOriginal')
    // was: 'Edit'
    t('detailEdit')
    // was: `${d.thumbnail_path ? 'Regenerate' : 'Generate'} preview`
    d.thumbnail_path ? t('detailRegeneratePreview') : t('detailGeneratePreview')
    // was: d.archived ? 'Unarchive' : 'Archive'
    d.archived ? t('detailUnarchive') : t('detailArchive')
    // was: d.needs_review ? 'Done' : 'Flag for review'  (reuse Task 1/3's commonDone/bulkFlagForReview)
    d.needs_review ? t('commonDone') : t('bulkFlagForReview')
    // was: 'Add to collection…'
    t('detailAddToCollection')
    // was: 'Remove from this collection'
    t('detailRemoveFromCollection')
    // was: 'Delete'  (reuse commonDelete)
    t('commonDelete')
    // was: 'Restore'  (reuse bulkRestore)
    t('bulkRestore')
    // was: 'No preview yet' / 'Preview file missing'
    t('detailNoPreviewYet') / t('detailPreviewMissing')
    // was: aria-label="Close"
    t('detailCloseAriaLabel')
    // was: bold labels 'Category'/'Type'/'Date'/'Amount'/'Payment'/'Pages'/'Imported'/'ID'/'Source'/'File'/'Original'
    t('detailLabelCategory') / t('detailLabelType') / t('detailLabelDate') / t('detailLabelAmount') /
    t('detailLabelPayment') / t('detailLabelPages') / t('detailLabelImported') / t('detailLabelId') /
    t('detailLabelSource') / t('detailLabelFile') / t('detailLabelOriginal')
    // was: 'Copy'  (the copy-to-clipboard buttons)
    t('detailCopyButton')
    // was: 'No file recorded for this document'
    t('detailNoFileRecorded')
    // was: 'Fields' / 'People' / 'Tags' / 'Notes' / 'OCR text'  (section <h3> headings)
    t('detailSectionFields') / t('detailSectionPeople') / t('detailSectionTags') / t('detailSectionNotes') / t('detailSectionOcrText')
    // was: '—' fallback for empty People/Tags  (reuse Task 5's tableNoValue)
    t('tableNoValue')
```

`copyPathToClipboard()` (~2886-2890):

```js
    // was: btn.textContent = 'Copied!'
    btn.textContent = t('detailCopiedButton');
    // was: alert('Could not copy to clipboard: ' + e.message)
    alert(t('detailCopyClipboardError', {error: e.message}));
```

The two "Could not open file" `alert()` call sites (~3015, 3024):

```js
    // was: alert('Could not open file: ' + e.message)
    alert(t('detailOpenFileError', {error: e.message}));
```

`regenerateThumbnail()` (~3176-3209):

```js
    // was: setStatus('Generating preview…', 'busy')  (spinner)
    setStatus(t('detailGeneratingPreview'), 'busy');
    // was: throw new Error('This document has no file to generate a preview from.')
    throw new Error(t('detailNoFileForPreview'));
    // was: `Can't generate a preview from this file type (${file.type || 'unknown'}).`
    t('detailUnsupportedPreviewType', {type: file.type || 'unknown'})
    // was: 'Could not generate preview: ' + e.message
    t('detailPreviewGenerationFailed', {error: e.message})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate the detail view modal"
```

---

## Task 7: Shared dynamic field rendering (person/generic field helpers, inline add-field validation)

**Files:**
- Modify: `dossiary.html` (`renderPersonFieldHtml()`/`renderGenericFieldHtml()` ~lines 1891-1967, `addInlineCustomField()` ~lines 2088-2126)

**Interfaces:**
- Consumes: `t()` (Task 1)
- Produces: `fieldClearTitle`, `fieldClearAriaLabel`, `fieldOrphanedHint`, `fieldCurrencyGuessHint`, `fieldPersonLabelSuffix`, `fieldPersonPlaceholder`, `fieldValidation*` keys — consumed by Task 8 (capture form) and Task 9 (edit form), since both forms call these same shared rendering functions.

This task is deliberately sequenced before Tasks 8/9: the capture and edit forms both render their dynamic per-type fields through these shared functions, so translating the shared functions first means Tasks 8/9 only need to handle the form-chrome strings that are *not* already covered here.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py` — this needs a document type with a configured person-type field to exercise `renderPersonFieldHtml()`'s orphaned-hint path; extend the `SEED` used by Task 6's scenario with a `document_type_fields`/`fields` row, or (simpler, matching existing test conventions in `tests/test_person_type_field.py`) open the capture form and check the generic "+ Add a custom field" validation message directly, which doesn't need extra seed data:

```python
        # === Scenario 9: shared field-rendering validation messages translate ===
        await page3.click('#add-btn')
        await page3.wait_for_timeout(200)
        await page3.click('#add-field-toggle')
        await page3.wait_for_timeout(100)
        await page3.click('#add-field-save-btn') # no type selected, no name entered yet
        await page3.wait_for_timeout(100)
        validation_text = await page3.locator('#add-field-status').inner_text()
        print("Scenario 9 -- inline add-field validation message translated:", validation_text in ("Wähle zuerst einen Dokumenttyp aus.", "Gib einen Feldnamen ein."))
        await page3.click('#cancel-btn')
        await page3.wait_for_timeout(150)
```

(Exact button/element IDs for the add-field toggle/save button should be confirmed against the actual rendered form during implementation — this plan's earlier reconnaissance read the form's *template strings*, not their live rendered `id`s in every case; if an ID differs from what's shown here, use the real one, the assertion intent stays the same: the validation status text is in German.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update the shared rendering functions**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      fieldPersonLabelSuffix: '{name} (comma-separated)', fieldPersonPlaceholder: 'e.g. Arne, Jana',
      fieldClearTitle: 'Clear', fieldClearAriaLabel: 'Clear {name}',
      fieldOrphanedHint: 'Not shown for this document type — edit or clear it here if needed',
      fieldCurrencyGuessHint: 'Defaulted to {currency} — change if this document uses a different currency',
      fieldValidationPickDocType: 'Pick a document type first.', fieldValidationEnterName: 'Enter a field name.',
      fieldValidationReservedName: '"{name}" is a built-in field — use ⚙ Manage fields to add it for this type.',
      fieldValidationDuplicateName: '"{name}" already exists — use ⚙ Manage fields to add it to this type.',
    // STRINGS.de additions:
      fieldPersonLabelSuffix: '{name} (durch Komma getrennt)', fieldPersonPlaceholder: 'z. B. Arne, Jana',
      fieldClearTitle: 'Leeren', fieldClearAriaLabel: '{name} leeren',
      fieldOrphanedHint: 'Für diesen Dokumenttyp nicht angezeigt — hier bei Bedarf bearbeiten oder leeren',
      fieldCurrencyGuessHint: 'Auf {currency} voreingestellt — ändern, falls dieses Dokument eine andere Währung verwendet',
      fieldValidationPickDocType: 'Wähle zuerst einen Dokumenttyp aus.', fieldValidationEnterName: 'Gib einen Feldnamen ein.',
      fieldValidationReservedName: '"{name}" ist ein eingebautes Feld — nutze ⚙ Felder verwalten, um es für diesen Typ hinzuzufügen.',
      fieldValidationDuplicateName: '"{name}" existiert bereits — nutze ⚙ Felder verwalten, um es zu diesem Typ hinzuzufügen.',
```

`renderPersonFieldHtml()`/`renderGenericFieldHtml()` (~1891-1967) — replace each literal at its exact call site:

```js
    // was: `${escapeHtml(field.name)} (comma-separated)`
    t('fieldPersonLabelSuffix', {name: escapeHtml(field.name)})
    // was: placeholder="e.g. Arne, Jana"
    t('fieldPersonPlaceholder')
    // was: title="Clear" / aria-label={`Clear ${escapeHtml(field.name)}`}
    t('fieldClearTitle') / t('fieldClearAriaLabel', {name: escapeHtml(field.name)})
    // was: 'Not shown for this document type — edit or clear it here if needed'  (4 call sites, same literal)
    t('fieldOrphanedHint')
    // was: `Defaulted to ${escapeHtml(defaultCurrency)} — change if this document uses a different currency`
    t('fieldCurrencyGuessHint', {currency: escapeHtml(defaultCurrency)})
```

`addInlineCustomField()` (~2088-2126):

```js
    // was: 'Pick a document type first.'
    t('fieldValidationPickDocType')
    // was: 'Enter a field name.'
    t('fieldValidationEnterName')
    // was: `"${name}" is a built-in field — use ⚙ Manage fields to add it for this type.`
    t('fieldValidationReservedName', {name})
    // was: `"${name}" already exists — use ⚙ Manage fields to add it to this type.`
    t('fieldValidationDuplicateName', {name})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate shared dynamic field rendering and inline add-field validation"
```

---

## Task 8: Capture form ("Add document") + scan hint + capture-time OCR flow

**Files:**
- Modify: `dossiary.html` (`openCaptureModal()` ~3771-3916, `scanHintHtml()` ~3758-3769, `handlePickedFile()` ~3918-3947, `runOcr()` ~3949-3978, `saveNewDocument()` ~4077-4233)

**Interfaces:**
- Consumes: `t()` (Task 1), field-rendering keys (Task 7), `commonDocumentFallback`/`commonCancel`/`commonAdd` (Task 1)
- Produces: `ocrLoadingEngine`, `ocrRecognizing`, `statusSaving`, `statusSaveFailed` — consumed by Task 9 (edit form shares these exact phrases).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
        # === Scenario 10: capture form translates ===
        await page3.click('#add-btn')
        await page3.wait_for_timeout(200)
        modal_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 10 -- capture modal heading translated:", modal_heading == "Dokument hinzufügen")
        save_btn_text = await page3.locator('#save-btn').inner_text()
        print("Scenario 10 -- capture save button translated:", save_btn_text == "Dokument speichern")
        await page3.click('#cancel-btn')
        await page3.wait_for_timeout(150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update the capture form and its OCR/save flow**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      captureTitle: 'Add document', captureFileDropLabel: 'Click to choose a file (PDF or image)',
      captureScanToggle: 'Need to scan a paper document first?',
      captureOcrTextLabel: 'Extracted / notes text (editable)', captureOcrTextPlaceholder: 'Runs after OCR, or type/paste manually',
      captureRunOcr: 'Run OCR', captureDocTypeLabel: 'Document type',
      captureDocTypePlaceholder: 'Pick this first — it determines which fields show below',
      captureDocTypeHint: "Not in the list? Type a new one — it'll be created.",
      captureTitleLabel: 'Title', captureDateLabel: 'Date',
      captureDateGuessHint: "Defaulted to today — check this is the document's actual date",
      captureCategoryLabel: 'Category', captureSubcategoryLabel: 'Subcategory',
      captureSubcategoryPlaceholder: 'Independent of category, not a child of it',
      captureAddFieldToggleCollapsed: '+ Add a custom field', captureAddFieldToggleExpanded: '− Add a custom field',
      captureAddFieldNamePlaceholder: 'Field name', captureAddFieldTypeText: 'Text', captureAddFieldTypeNumber: 'Number',
      captureAddFieldTypeDate: 'Date', captureAddFieldTypeCheckbox: 'Checkbox', captureAddFieldTypePerson: 'Person',
      captureAddFieldAmountHint: 'Need a monetary value? Use the built-in Amount field (with its own Currency) instead.',
      captureTagsLabel: 'Tags (comma-separated)', captureTagsPlaceholder: 'e.g. medical, insurance',
      captureNotesLabel: 'Notes', captureSaveButton: 'Save document',
      scanHintIntro: "This app can't open your scanner directly — browsers aren't allowed to control hardware or launch other apps. Instead: ",
      scanHintOutro: ' Then come back and use "Click to choose a file" above to pick that scan.',
      scanHintMac: 'open <b>Image Capture</b> (⌘Space, type "Image Capture") or Preview\'s <b>File → Import from Scanner</b>, scan the document, and save it somewhere you\'ll find it (e.g. the Desktop).',
      scanHintWindows: 'open the <b>Windows Scan</b> app (search "Scan" in the Start menu) or your scanner\'s own software, scan the document, and save it somewhere you\'ll find it (e.g. Documents or the Desktop).',
      scanHintOther: "use your scanner's own software to scan the document and save it somewhere you'll find it.",
      pickedOcrPdfNote: 'Running OCR will build a searchable PDF (image + invisible text layer); the original stays alongside it.',
      pickedOcrOtherImageNote: 'OCR text will be extracted, but a searchable PDF can only be built from JPEG/PNG — this file will be saved as-is.',
      pickedOcrNotAvailablePdf: ' · OCR not available for PDFs yet, add notes manually',
      pickedFileSizeKb: '{size} KB', sharedPageCountSingular: '{count} page', sharedPageCountPlural: '{count} pages',
      ocrLoadingEngine: 'Loading OCR engine…', ocrRecognizing: 'Recognizing text…',
      captureOcrDoneWordsSingular: 'Done — {count} word positioned for a searchable PDF.',
      captureOcrDoneWordsPlural: 'Done — {count} words positioned for a searchable PDF.',
      captureOcrDoneNoWords: 'Done, but no words with position data were found.',
      ocrFailedStatus: 'OCR failed: {error}', statusSaving: 'Saving…',
      captureSavedStatus: 'Saved "{title}" as #{id}.', statusSaveFailed: 'Save failed: {error}',
    // STRINGS.de additions:
      captureTitle: 'Dokument hinzufügen', captureFileDropLabel: 'Klicken, um eine Datei auszuwählen (PDF oder Bild)',
      captureScanToggle: 'Musst du zuerst ein Papierdokument scannen?',
      captureOcrTextLabel: 'Erkannter Text / Notizen (bearbeitbar)', captureOcrTextPlaceholder: 'Wird nach OCR ausgefüllt, oder manuell eintippen/einfügen',
      captureRunOcr: 'OCR ausführen', captureDocTypeLabel: 'Dokumenttyp',
      captureDocTypePlaceholder: 'Zuerst auswählen — bestimmt, welche Felder unten angezeigt werden',
      captureDocTypeHint: 'Nicht in der Liste? Einfach einen neuen Typ eintippen — er wird angelegt.',
      captureTitleLabel: 'Titel', captureDateLabel: 'Datum',
      captureDateGuessHint: 'Auf heute voreingestellt — prüfe, ob dies das tatsächliche Datum des Dokuments ist',
      captureCategoryLabel: 'Kategorie', captureSubcategoryLabel: 'Unterkategorie',
      captureSubcategoryPlaceholder: 'Unabhängig von der Kategorie, keine Unterordnung',
      captureAddFieldToggleCollapsed: '+ Benutzerdefiniertes Feld hinzufügen', captureAddFieldToggleExpanded: '− Benutzerdefiniertes Feld hinzufügen',
      captureAddFieldNamePlaceholder: 'Feldname', captureAddFieldTypeText: 'Text', captureAddFieldTypeNumber: 'Zahl',
      captureAddFieldTypeDate: 'Datum', captureAddFieldTypeCheckbox: 'Kontrollkästchen', captureAddFieldTypePerson: 'Person',
      captureAddFieldAmountHint: 'Brauchst du einen Geldbetrag? Nutze stattdessen das eingebaute Feld "Betrag" (mit eigener Währung).',
      captureTagsLabel: 'Tags (durch Komma getrennt)', captureTagsPlaceholder: 'z. B. medizinisch, Versicherung',
      captureNotesLabel: 'Notizen', captureSaveButton: 'Dokument speichern',
      scanHintIntro: 'Diese App kann deinen Scanner nicht direkt öffnen — Browser dürfen keine Hardware steuern oder andere Programme starten. Stattdessen: ',
      scanHintOutro: ' Komm danach zurück und wähle den Scan oben über "Klicken, um eine Datei auszuwählen" aus.',
      scanHintMac: 'öffne <b>Digitale Bilder</b> (⌘Leertaste, "Digitale Bilder" eintippen) oder in der Vorschau <b>Ablage → Vom Scanner importieren</b>, scanne das Dokument und speichere es an einem Ort, den du wiederfindest (z. B. den Schreibtisch).',
      scanHintWindows: 'öffne die App <b>Windows-Scannen</b> (im Startmenü nach "Scannen" suchen) oder die eigene Software deines Scanners, scanne das Dokument und speichere es an einem Ort, den du wiederfindest (z. B. Dokumente oder den Schreibtisch).',
      scanHintOther: 'nutze die eigene Software deines Scanners, um das Dokument zu scannen und es an einem Ort zu speichern, den du wiederfindest.',
      pickedOcrPdfNote: 'Beim Ausführen von OCR wird ein durchsuchbares PDF erzeugt (Bild + unsichtbare Textebene); das Original bleibt daneben erhalten.',
      pickedOcrOtherImageNote: 'Der OCR-Text wird extrahiert, aber ein durchsuchbares PDF kann nur aus JPEG/PNG erzeugt werden — diese Datei wird unverändert gespeichert.',
      pickedOcrNotAvailablePdf: ' · OCR für PDFs noch nicht verfügbar, Notizen manuell eintragen',
      pickedFileSizeKb: '{size} KB', sharedPageCountSingular: '{count} Seite', sharedPageCountPlural: '{count} Seiten',
      ocrLoadingEngine: 'OCR-Engine wird geladen…', ocrRecognizing: 'Text wird erkannt…',
      captureOcrDoneWordsSingular: 'Fertig — {count} Wort für ein durchsuchbares PDF positioniert.',
      captureOcrDoneWordsPlural: 'Fertig — {count} Wörter für ein durchsuchbares PDF positioniert.',
      captureOcrDoneNoWords: 'Fertig, aber es wurden keine Wörter mit Positionsdaten gefunden.',
      ocrFailedStatus: 'OCR fehlgeschlagen: {error}', statusSaving: 'Wird gespeichert…',
      captureSavedStatus: '"{title}" als #{id} gespeichert.', statusSaveFailed: 'Speichern fehlgeschlagen: {error}',
```

`openCaptureModal()` (~3771-3916) — replace each literal at its call site with the corresponding `t()`/`t(..., params)` call (heading, file-drop label, scan-toggle, OCR text label/placeholder, Run OCR button, Document type label/placeholder/hint, Title/Date labels, date-guess hint, Category/Subcategory labels/placeholder, add-field toggle/placeholder/type options/hint, Tags label/placeholder, Notes label, Save/Cancel buttons — Cancel reuses `t('commonCancel')` from Task 1):

```js
    t('captureTitle'); t('captureFileDropLabel'); t('captureScanToggle'); t('captureOcrTextLabel');
    t('captureOcrTextPlaceholder'); t('captureRunOcr'); t('captureDocTypeLabel'); t('captureDocTypePlaceholder');
    t('captureDocTypeHint'); t('captureTitleLabel'); t('captureDateLabel'); t('captureDateGuessHint');
    t('captureCategoryLabel'); t('captureSubcategoryLabel'); t('captureSubcategoryPlaceholder');
    // was: isExpanded ? '− Add a custom field' : '+ Add a custom field'
    isExpanded ? t('captureAddFieldToggleExpanded') : t('captureAddFieldToggleCollapsed')
    t('captureAddFieldNamePlaceholder');
    // was: <option value="text">Text</option> etc.
    `<option value="text">${t('captureAddFieldTypeText')}</option><option value="number">${t('captureAddFieldTypeNumber')}</option><option value="date">${t('captureAddFieldTypeDate')}</option><option value="checkbox">${t('captureAddFieldTypeCheckbox')}</option><option value="person">${t('captureAddFieldTypePerson')}</option>`
    // was: 'Add'  (reuse commonAdd)
    t('commonAdd')
    t('captureAddFieldAmountHint'); t('captureTagsLabel'); t('captureTagsPlaceholder'); t('captureNotesLabel');
    t('captureSaveButton');
    // was: 'Cancel'  (reuse commonCancel)
    t('commonCancel')
```

`scanHintHtml()` (~3758-3769):

```js
    // was the OS-branching function's return value construction:
    const intro = t('scanHintIntro');
    const outro = t('scanHintOutro');
    const body = os === 'macOS' ? t('scanHintMac') : os === 'Windows' ? t('scanHintWindows') : t('scanHintOther');
    return `${intro}${body}${outro}`;
```

(the existing function's control flow choosing macOS/Windows/other stays exactly as-is — only the three returned string literals become `t()` calls.)

`handlePickedFile()` (~3918-3947):

```js
    // was: 'Running OCR will build a searchable PDF (image + invisible text layer); the original stays alongside it.'
    t('pickedOcrPdfNote')
    // was: 'OCR text will be extracted, but a searchable PDF can only be built from JPEG/PNG — this file will be saved as-is.'
    t('pickedOcrOtherImageNote')
    // was: ' · OCR not available for PDFs yet, add notes manually'
    t('pickedOcrNotAvailablePdf')
    // was: `${(file.size/1024).toFixed(0)} KB`
    t('pickedFileSizeKb', {size: (file.size/1024).toFixed(0)})
    // was: `${count} page${count === 1 ? '' : 's'}`
    count === 1 ? t('sharedPageCountSingular', {count}) : t('sharedPageCountPlural', {count})
```

`runOcr()` (~3949-3978):

```js
    t('ocrLoadingEngine'); t('ocrRecognizing');
    // was: `Done — ${pendingOcrWords.length} words positioned for a searchable PDF.`
    pendingOcrWords.length === 1
      ? t('captureOcrDoneWordsSingular', {count: pendingOcrWords.length})
      : t('captureOcrDoneWordsPlural', {count: pendingOcrWords.length})
    t('captureOcrDoneNoWords');
    // was: 'OCR failed: ' + e.message
    t('ocrFailedStatus', {error: e.message})
```

`saveNewDocument()` (~4077-4233):

```js
    // was: setStatus('Saving…', 'busy')
    setStatus(t('statusSaving'), 'busy');
    // was: setStatus(`Saved "${title || 'Document #' + id}" as #${id}.`, 'ok')
    setStatus(t('captureSavedStatus', {title: title || t('commonDocumentFallback', {id}), id}), 'ok');
    // was: 'Save failed: ' + e.message
    setStatus(t('statusSaveFailed', {error: e.message}), 'err');
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate the capture form, scan hint, and capture-time OCR flow"
```

---

## Task 9: Edit form + edit-time OCR flow

**Files:**
- Modify: `dossiary.html` (`openEditForm()` ~3213-3366, `saveEditedDocument()` ~3377-3511, `runOcrForEdit()` ~4006-4051)

**Interfaces:**
- Consumes: `t()`, field-rendering keys (Task 7), `ocrLoadingEngine`/`ocrRecognizing`/`ocrFailedStatus`/`statusSaving`/`statusSaveFailed`/`sharedPageCountSingular`/`sharedPageCountPlural`/`commonCancel`/`commonDone`/`commonDocumentFallback` (Tasks 1/8)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
        # === Scenario 11: edit form translates, including reused capture-form keys ===
        await page3.click('tr[data-id="1"]')
        await page3.wait_for_timeout(200)
        await page3.click('#edit-doc-btn')
        await page3.wait_for_timeout(200)
        edit_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 11 -- edit modal heading translated:", edit_heading == "Dokument bearbeiten")
        save_changes_text = await page3.locator('#save-btn').inner_text()
        print("Scenario 11 -- edit save-changes button translated:", save_changes_text == "Änderungen speichern")
        await page3.click('#cancel-edit-btn')
        await page3.wait_for_timeout(150)
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update the edit form and its OCR/save flow**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      editTitle: 'Edit document', editDocTypeLabel: 'Document type', editDocTypePlaceholder: 'Determines which fields show below',
      editDocTypeHint: "Not in the list? Type a new one — it'll be created.", editTitleLabel: 'Title', editDateLabel: 'Date',
      editCategoryLabel: 'Category', editSubcategoryLabel: 'Subcategory',
      editSubcategoryPlaceholder: 'Independent of category, not a child of it',
      editOcrTextLabel: 'OCR / extracted text', editSaveAndDone: 'Save & Done', editSaveChanges: 'Save changes',
      editSavedStatus: 'Saved changes to "{title}".',
      ocrDone: 'Done.', ocrLoadingPdf: 'Loading PDF…', ocrRecognizingPage: 'Recognizing page {page} of {total}…',
      editOcrPdfDoneSingular: 'Done — {count} page recognized.', editOcrPdfDonePlural: 'Done — {count} pages recognized.',
      editOcrUnsupportedType: "Can't run OCR on this file type ({type}).",
    // STRINGS.de additions:
      editTitle: 'Dokument bearbeiten', editDocTypeLabel: 'Dokumenttyp', editDocTypePlaceholder: 'Bestimmt, welche Felder unten angezeigt werden',
      editDocTypeHint: 'Nicht in der Liste? Einfach einen neuen Typ eintippen — er wird angelegt.', editTitleLabel: 'Titel', editDateLabel: 'Datum',
      editCategoryLabel: 'Kategorie', editSubcategoryLabel: 'Unterkategorie',
      editSubcategoryPlaceholder: 'Unabhängig von der Kategorie, keine Unterordnung',
      editOcrTextLabel: 'OCR / erkannter Text', editSaveAndDone: 'Speichern & Fertig', editSaveChanges: 'Änderungen speichern',
      editSavedStatus: 'Änderungen an "{title}" gespeichert.',
      ocrDone: 'Fertig.', ocrLoadingPdf: 'PDF wird geladen…', ocrRecognizingPage: 'Seite {page} von {total} wird erkannt…',
      editOcrPdfDoneSingular: 'Fertig — {count} Seite erkannt.', editOcrPdfDonePlural: 'Fertig — {count} Seiten erkannt.',
      editOcrUnsupportedType: 'OCR ist für diesen Dateityp ({type}) nicht möglich.',
```

`openEditForm()` (~3213-3366) — replace each literal (heading, Document type label/placeholder/hint, Title/Date/Category/Subcategory labels/placeholder, add-field controls reuse Task 8's `capture*` keys verbatim since it's the same shared template, Tags/Notes labels reuse Task 8's `capture*` keys, OCR text label, Run OCR button reuses `t('captureRunOcr')`, Save & Done / Save changes / Cancel):

```js
    t('editTitle'); t('editDocTypeLabel'); t('editDocTypePlaceholder'); t('editDocTypeHint');
    t('editTitleLabel'); t('editDateLabel'); t('editCategoryLabel'); t('editSubcategoryLabel'); t('editSubcategoryPlaceholder');
    // add-field controls: reuse t('captureAddFieldToggleCollapsed')/Expanded, t('captureAddFieldNamePlaceholder'),
    // the same type-option markup as Task 8, t('commonAdd'), t('captureAddFieldAmountHint')
    t('captureTagsLabel'); t('captureTagsPlaceholder'); t('captureNotesLabel');
    t('editOcrTextLabel');
    t('captureRunOcr'); // "Run OCR" -- identical wording, shared key
    // was: d.needs_review ? '<button class="primary" id="save-done-btn">Save &amp; Done</button>' : ''
    d.needs_review ? `<button class="primary" id="save-done-btn">${t('editSaveAndDone')}</button>` : ''
    t('editSaveChanges');
    t('commonCancel'); // reuse
```

Page-count display (~3354-3365), identical pattern to Task 8's `handlePickedFile()`:

```js
    // was: `${count} page${count === 1 ? '' : 's'}`
    count === 1 ? t('sharedPageCountSingular', {count}) : t('sharedPageCountPlural', {count})
```

`saveEditedDocument()` (~3377-3511):

```js
    setStatus(t('statusSaving'), 'busy'); // reused from Task 8
    // was: setStatus(`Saved changes to "${title || 'Document #' + id}".`, 'ok')
    setStatus(t('editSavedStatus', {title: title || t('commonDocumentFallback', {id})}), 'ok');
    setStatus(t('statusSaveFailed', {error: e.message}), 'err'); // reused from Task 8
```

`runOcrForEdit()` (~4006-4051):

```js
    t('ocrLoadingEngine'); t('ocrRecognizing'); // reused from Task 8
    t('ocrDone'); t('ocrLoadingPdf');
    // was: `Recognizing page ${pageNum} of ${pdf.numPages}…`
    t('ocrRecognizingPage', {page: pageNum, total: pdf.numPages})
    // was: `Done — ${pdf.numPages} page${pdf.numPages === 1 ? '' : 's'} recognized.`
    pdf.numPages === 1
      ? t('editOcrPdfDoneSingular', {count: pdf.numPages})
      : t('editOcrPdfDonePlural', {count: pdf.numPages})
    // was: `Can't run OCR on this file type (${file.type || 'unknown'}).`
    t('editOcrUnsupportedType', {type: file.type || 'unknown'})
    t('ocrFailedStatus', {error: e.message}); // reused from Task 8
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate the edit form and edit-time OCR flow"
```

---

## Task 10: Field Settings modal

**Files:**
- Modify: `dossiary.html` (`openFieldSettingsModal()` and helpers ~3521-3735)

**Interfaces:**
- Consumes: `t()`, `commonDone`/`commonNone` (Task 1)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
        # === Scenario 12: Field Settings modal translates ===
        await page3.click('#manage-fields-btn')
        await page3.wait_for_timeout(200)
        fs_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 12 -- Field Settings heading translated:", fs_heading == "Feldeinstellungen")
        col_heading = await page3.locator('.fs-col h3').first.inner_text()
        print("Scenario 12 -- Field Settings column heading translated:", col_heading == "Dokumenttypen")
        await page3.click('#fs-done-btn')
        await page3.wait_for_timeout(150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update the modal**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      fieldSettingsTitle: 'Field settings',
      fieldSettingsDefaultDocTypeLabel: 'Default document type (pre-fills "Add document")',
      fieldSettingsDefaultCurrencyLabel: 'Default currency (guessed on new captures, e.g. EUR)',
      fieldSettingsColDocTypes: 'Document Types', fieldSettingsColFields: 'Fields', fieldSettingsColDisplayFields: 'Display Fields',
      fieldSettingsNoDocTypes: 'No document types in use yet. Type one into the Add/Edit document form first.',
      fieldSettingsSelectDocType: 'Select a document type.', fieldSettingsColumnCheckbox: 'Column',
      fieldSettingsAutocompleteCheckbox: 'Autocomplete', fieldSettingsAddToDisplayTitle: 'Add to Display Fields',
      fieldSettingsAllFieldsShown: 'All fields are already shown for this type.',
      fieldSettingsMoveUpTitle: 'Move up', fieldSettingsMoveDownTitle: 'Move down', fieldSettingsRemoveTitle: 'Remove',
      fieldSettingsNoFieldsShown: 'No fields shown for this type yet — add some from the left.',
    // STRINGS.de additions:
      fieldSettingsTitle: 'Feldeinstellungen',
      fieldSettingsDefaultDocTypeLabel: 'Standard-Dokumenttyp (füllt "Dokument hinzufügen" vor)',
      fieldSettingsDefaultCurrencyLabel: 'Standardwährung (wird bei neuen Erfassungen vorgeschlagen, z. B. EUR)',
      fieldSettingsColDocTypes: 'Dokumenttypen', fieldSettingsColFields: 'Felder', fieldSettingsColDisplayFields: 'Anzeigefelder',
      fieldSettingsNoDocTypes: 'Noch keine Dokumenttypen in Verwendung. Gib zuerst einen im Formular "Dokument hinzufügen/bearbeiten" ein.',
      fieldSettingsSelectDocType: 'Wähle einen Dokumenttyp aus.', fieldSettingsColumnCheckbox: 'Spalte',
      fieldSettingsAutocompleteCheckbox: 'Autovervollständigung', fieldSettingsAddToDisplayTitle: 'Zu Anzeigefeldern hinzufügen',
      fieldSettingsAllFieldsShown: 'Für diesen Typ werden bereits alle Felder angezeigt.',
      fieldSettingsMoveUpTitle: 'Nach oben', fieldSettingsMoveDownTitle: 'Nach unten', fieldSettingsRemoveTitle: 'Entfernen',
      fieldSettingsNoFieldsShown: 'Für diesen Typ werden noch keine Felder angezeigt — füge links welche hinzu.',
```

Replace each literal in `openFieldSettingsModal()`/its render helpers (~3521-3735) with the corresponding `t()` call, and the two `— None —` default-select options with `t('commonNone')`, and the modal's Done button with `t('commonDone')`:

```js
    t('fieldSettingsTitle'); t('fieldSettingsDefaultDocTypeLabel'); t('commonNone');
    t('fieldSettingsDefaultCurrencyLabel'); t('commonNone');
    t('fieldSettingsColDocTypes'); t('fieldSettingsColFields'); t('fieldSettingsColDisplayFields');
    t('commonDone'); t('fieldSettingsNoDocTypes'); t('fieldSettingsSelectDocType');
    t('fieldSettingsColumnCheckbox'); t('fieldSettingsAutocompleteCheckbox'); t('fieldSettingsAddToDisplayTitle');
    t('fieldSettingsAllFieldsShown'); t('fieldSettingsMoveUpTitle'); t('fieldSettingsMoveDownTitle');
    t('fieldSettingsRemoveTitle'); t('fieldSettingsNoFieldsShown');
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate the Field Settings modal"
```

---

## Task 11: Manage Collections modal

**Files:**
- Modify: `dossiary.html` (`openManageCollectionsModal()`/`renderManageCollectionsList()` ~4237-4329)

**Interfaces:**
- Consumes: `t()`, `commonDone`/`commonDelete` (Task 1), `bulkNewCollectionMenuItem` (Task 3, already covers the bulk-bar's own menu item — this task covers the *modal*'s distinct "+ New collection" button, worded slightly differently)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
        # === Scenario 13: Manage Collections modal translates ===
        await page3.click('#manage-collections-btn')
        await page3.wait_for_timeout(200)
        mc_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 13 -- Manage Collections heading translated:", mc_heading == "Sammlungen verwalten")
        await page3.click('#mc-done-btn')
        await page3.wait_for_timeout(150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update the modal**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      collectionsTitle: 'Manage collections', collectionsNewNamePlaceholder: 'New collection name',
      collectionsNewButton: '+ New collection',
    // STRINGS.de additions:
      collectionsTitle: 'Sammlungen verwalten', collectionsNewNamePlaceholder: 'Neuer Sammlungsname',
      collectionsNewButton: '+ Neue Sammlung',
```

Replace each literal (heading, new-collection-name placeholder, "+ New collection" button, per-collection "Delete" button reusing `t('commonDelete')`, modal's own Done button reusing `t('commonDone')`):

```js
    t('collectionsTitle'); t('collectionsNewNamePlaceholder'); t('collectionsNewButton');
    t('commonDone'); t('commonDelete');
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate the Manage Collections modal"
```

---

## Task 12: Reports view

**Files:**
- Modify: `dossiary.html` (`renderReportsView()`/`reportBreakdownFieldInfo()`/`computeReportGroups()`/`formatCustomFieldValue()` ~2355-2456)

**Interfaces:**
- Consumes: `t()` (Task 1)
- Produces: `commonYes`/`commonNo` already exist (Task 1) — this task is the first to actually *use* them, in `formatCustomFieldValue()`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
        # === Scenario 14: Reports view translates ===
        await page3.click('#nav-item-reports')
        await page3.wait_for_timeout(200)
        print_btn_text = await page3.locator('#reports-print-btn').inner_text()
        print("Scenario 14 -- Reports print button translated:", print_btn_text == "🖨 Drucken")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update Reports rendering**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      reportsNone: '(none)', reportsNoCurrencySet: 'No currency set',
      reportsMultiValueCaption: "Documents with more than one {label} are counted once per name, so this breakdown's row totals may not add up to the Grand total below.",
      reportsColCount: 'Count', reportsColTotal: 'Total', reportsGrandTotal: 'Grand total',
      reportsNoDocuments: 'No documents match the current filters.', reportsPrintButton: '🖨 Print',
      reportsBreakdownCategory: 'Category', reportsBreakdownType: 'Type', reportsBreakdownPeople: 'People',
    // STRINGS.de additions:
      reportsNone: '(keine)', reportsNoCurrencySet: 'Keine Währung angegeben',
      reportsMultiValueCaption: 'Dokumente mit mehr als einem/einer {label} werden pro Name einmal gezählt, daher stimmen die Zeilensummen dieser Aufschlüsselung möglicherweise nicht mit der Gesamtsumme unten überein.',
      reportsColCount: 'Anzahl', reportsColTotal: 'Summe', reportsGrandTotal: 'Gesamtsumme',
      reportsNoDocuments: 'Keine Dokumente entsprechen den aktuellen Filtern.', reportsPrintButton: '🖨 Drucken',
      reportsBreakdownCategory: 'Kategorie', reportsBreakdownType: 'Typ', reportsBreakdownPeople: 'Personen',
```

Replace each literal:

```js
    // reportBreakdownFieldInfo() (~2355-2357): was 'Category'/'Type'/'People'
    t('reportsBreakdownCategory'); t('reportsBreakdownType'); t('reportsBreakdownPeople');
    // computeReportGroups()/renderReportsView() (~2412-2446):
    t('reportsNone'); // was '(none)'
    // was: g.currency ? escapeHtml(g.currency) : 'No currency set'
    g.currency ? escapeHtml(g.currency) : t('reportsNoCurrencySet')
    // was: `Documents with more than one ${escapeHtml(g.breakdownLabel)} are counted once per name, ...`
    t('reportsMultiValueCaption', {label: escapeHtml(g.breakdownLabel)})
    t('reportsColCount'); t('reportsColTotal'); t('reportsGrandTotal'); t('reportsNoDocuments'); t('reportsPrintButton');
    // formatCustomFieldValue() (~2456): checkbox Yes/No
    value === '1' ? t('commonYes') : t('commonNo')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate the Reports view"
```

---

## Task 13: Libraries/licenses modal

**Files:**
- Modify: `dossiary.html` (`openLibrariesModal()` ~2843-2876)

**Interfaces:**
- Consumes: `t()` (Task 1)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
        # === Scenario 15: Libraries/licenses modal translates ===
        await page3.click('#libraries-link')
        await page3.wait_for_timeout(200)
        lib_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 15 -- Libraries modal heading translated:", lib_heading == "Open-Source-Bibliotheken")
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update the modal**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      librariesTitle: 'Open source libraries',
      librariesIntro: 'Loaded from a CDN at runtime, only when a feature that needs it is actually used. None of it ever sees your documents except locally, in your own browser.',
      librariesUseSqlJs: 'Reading/writing library.sqlite (SQLite compiled to WebAssembly)',
      librariesUseTesseract: 'OCR text extraction',
      librariesUseJsPdf: 'Building the searchable PDF layer for captured images',
      librariesUsePdfJs: 'Rendering PDF pages (first page for previews, every page for edit-time OCR)',
    // STRINGS.de additions:
      librariesTitle: 'Open-Source-Bibliotheken',
      librariesIntro: 'Wird zur Laufzeit von einem CDN geladen, nur wenn eine Funktion sie tatsächlich benötigt. Keine davon bekommt deine Dokumente jemals zu sehen — außer lokal, in deinem eigenen Browser.',
      librariesUseSqlJs: 'Lesen/Schreiben von library.sqlite (SQLite, kompiliert zu WebAssembly)',
      librariesUseTesseract: 'OCR-Texterkennung',
      librariesUseJsPdf: 'Erzeugen der durchsuchbaren PDF-Ebene für erfasste Bilder',
      librariesUsePdfJs: 'Rendern von PDF-Seiten (erste Seite für Vorschauen, jede Seite für OCR beim Bearbeiten)',
```

Replace each literal in `openLibrariesModal()` — the heading, intro paragraph, and each of the four `OPEN_SOURCE_LIBRARIES` entries' `use` description (library names themselves — sql.js, Tesseract.js, jsPDF, pdf.js — and license names like "MIT"/"Apache-2.0" stay as-is, they're proper nouns, not translated):

```js
    t('librariesTitle'); t('librariesIntro');
    t('librariesUseSqlJs'); t('librariesUseTesseract'); t('librariesUseJsPdf'); t('librariesUsePdfJs');
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate the Libraries/licenses modal"
```

---

## Task 14: Drag-and-drop and Inbox-add status messages

**Files:**
- Modify: `dossiary.html` (`updateInboxBanner()`, `addInboxFile()`, `addDroppedFiles()`, `addAllInboxFilesAndShowStatus()` ~4362-4525, drop-overlay static markup ~line 617)

**Interfaces:**
- Consumes: `t()`, `commonDocumentFallback` (Task 1)
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_i18n.py`:

```python
        # === Scenario 16: drag-and-drop overlay text translates ===
        overlay_text = await page3.locator('.drop-overlay-box').inner_text()
        print("Scenario 16 -- drop overlay text translated:", overlay_text == "Zum Prüfen ablegen")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n.py`
Expected: FAIL.

- [ ] **Step 3: Add keys, update the static overlay markup and status messages**

Add to `STRINGS.en`/`STRINGS.de`:

```js
    // STRINGS.en additions:
      dragdropOverlayText: 'Drop to add for review',
      dragdropInboxBannerWaitingSingular: '{count} document waiting in the inbox folder.',
      dragdropInboxBannerWaitingPlural: '{count} documents waiting in the inbox folder.',
      dragdropAddedFromInboxStatus: 'Added "{title}" as #{id} from the inbox.',
      dragdropAddFailedStatus: 'Failed to add "{name}": {error}',
      dragdropDropFailedSingle: 'Could not add the dropped file.',
      dragdropDropFailedMulti: 'Could not add any of the {count} dropped files.',
      dragdropAddedSingleForReview: 'Added "{title}" as #{id} for review.',
      dragdropAddedMultiForReview: 'Added {count} documents for review.',
      dragdropPartialFailureSingular: ' {count} file could not be added.',
      dragdropPartialFailurePlural: ' {count} files could not be added.',
      dragdropNoFilesWaiting: 'No files waiting in {folder}.',
      dragdropCouldNotAddAnyOfCountSingular: 'Could not add any of the {count} file in {folder}.',
      dragdropCouldNotAddAnyOfCountPlural: 'Could not add any of the {count} files in {folder}.',
      dragdropAddedToReviewQueueSingular: 'Added {count} document to the review queue from {folder}.',
      dragdropAddedToReviewQueuePlural: 'Added {count} documents to the review queue from {folder}.',
      dragdropPartialFailureStillThereSingular: ' {count} file could not be added and is still there.',
      dragdropPartialFailureStillTherePlural: ' {count} files could not be added and are still there.',
    // STRINGS.de additions:
      dragdropOverlayText: 'Zum Prüfen ablegen',
      dragdropInboxBannerWaitingSingular: '{count} Dokument wartet im Posteingangsordner.',
      dragdropInboxBannerWaitingPlural: '{count} Dokumente warten im Posteingangsordner.',
      dragdropAddedFromInboxStatus: '"{title}" als #{id} aus dem Posteingang hinzugefügt.',
      dragdropAddFailedStatus: '"{name}" konnte nicht hinzugefügt werden: {error}',
      dragdropDropFailedSingle: 'Die abgelegte Datei konnte nicht hinzugefügt werden.',
      dragdropDropFailedMulti: 'Keine der {count} abgelegten Dateien konnte hinzugefügt werden.',
      dragdropAddedSingleForReview: '"{title}" als #{id} zur Prüfung hinzugefügt.',
      dragdropAddedMultiForReview: '{count} Dokumente zur Prüfung hinzugefügt.',
      dragdropPartialFailureSingular: ' {count} Datei konnte nicht hinzugefügt werden.',
      dragdropPartialFailurePlural: ' {count} Dateien konnten nicht hinzugefügt werden.',
      dragdropNoFilesWaiting: 'Keine Dateien warten in {folder}.',
      dragdropCouldNotAddAnyOfCountSingular: 'Konnte keine der {count} Datei in {folder} hinzufügen.',
      dragdropCouldNotAddAnyOfCountPlural: 'Konnte keine der {count} Dateien in {folder} hinzufügen.',
      dragdropAddedToReviewQueueSingular: '{count} Dokument aus {folder} zur Prüfung hinzugefügt.',
      dragdropAddedToReviewQueuePlural: '{count} Dokumente aus {folder} zur Prüfung hinzugefügt.',
      dragdropPartialFailureStillThereSingular: ' {count} Datei konnte nicht hinzugefügt werden und ist noch dort.',
      dragdropPartialFailureStillTherePlural: ' {count} Dateien konnten nicht hinzugefügt werden und sind noch dort.',
```

Update the drop-overlay static markup (~line 617):

```html
  <div id="drop-overlay" class="drop-overlay" style="display:none;">
    <div class="drop-overlay-box" data-i18n="dragdropOverlayText">Drop to add for review</div>
  </div>
```

`updateInboxBanner()` (~4362):

```js
    // was: `${pendingInboxFiles.length} document${pendingInboxFiles.length === 1 ? '' : 's'} waiting in the inbox folder.`
    pendingInboxFiles.length === 1
      ? t('dragdropInboxBannerWaitingSingular', {count: pendingInboxFiles.length})
      : t('dragdropInboxBannerWaitingPlural', {count: pendingInboxFiles.length})
```

`addInboxFile()` (~4451, 4453):

```js
    // was: setStatus(`Added "${title || 'Document #' + id}" as #${id} from the inbox.`, 'ok')
    setStatus(t('dragdropAddedFromInboxStatus', {title: title || t('commonDocumentFallback', {id}), id}), 'ok');
    // was: setStatus(`Failed to add "${name}": ${e.message}`, 'err')
    setStatus(t('dragdropAddFailedStatus', {name, error: e.message}), 'err');
```

`addDroppedFiles()` (~4483-4491):

```js
    // was: setStatus(`Could not add ${failed === 1 ? 'the dropped file' : `any of the ${failed} dropped files`}.`, 'err')
    setStatus(failed === 1 ? t('dragdropDropFailedSingle') : t('dragdropDropFailedMulti', {count: failed}), 'err');
    // was: `Added "${lastTitle || 'Document #' + lastId}" as #${lastId} for review.`
    t('dragdropAddedSingleForReview', {title: lastTitle || t('commonDocumentFallback', {id: lastId}), id: lastId})
    // was: `Added ${added} documents for review.`
    t('dragdropAddedMultiForReview', {count: added})
    // was: ` ${failed} file${failed === 1 ? '' : 's'} could not be added.`
    failed === 1 ? t('dragdropPartialFailureSingular', {count: failed}) : t('dragdropPartialFailurePlural', {count: failed})
```

`addAllInboxFilesAndShowStatus()` (~4512-4525):

```js
    // was: setStatus(`No files waiting in ${folderLabel}.`, 'ok')
    setStatus(t('dragdropNoFilesWaiting', {folder: folderLabel}), 'ok');
    // was: setStatus(`Could not add any of the ${count} file${count === 1 ? '' : 's'} in ${folderLabel}.`, 'err')
    setStatus(
      count === 1
        ? t('dragdropCouldNotAddAnyOfCountSingular', {count, folder: folderLabel})
        : t('dragdropCouldNotAddAnyOfCountPlural', {count, folder: folderLabel}),
      'err'
    );
    // was: setStatus(`Added ${added} document${added === 1 ? '' : 's'} to the review queue from ${folderLabel}.` +
    //      (failed ? ` ${failed} file${failed === 1 ? '' : 's'} could not be added and ${failed === 1 ? 'is' : 'are'} still there.` : ''),
    //      failed ? 'err' : 'ok')
    const addedPart = added === 1
      ? t('dragdropAddedToReviewQueueSingular', {count: added, folder: folderLabel})
      : t('dragdropAddedToReviewQueuePlural', {count: added, folder: folderLabel});
    const failedPart = failed
      ? (failed === 1
          ? t('dragdropPartialFailureStillThereSingular', {count: failed})
          : t('dragdropPartialFailureStillTherePlural', {count: failed}))
      : '';
    setStatus(addedPart + failedPart, failed ? 'err' : 'ok');
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Translate drag-and-drop overlay and Inbox-add status messages"
```

---

## Task 15: Static key-coverage check + CLAUDE.md documentation

**Files:**
- Create: `tests/test_i18n_coverage.py`
- Modify: `CLAUDE.md`, `README.md`/`README.de.md` (footnote mention only, see below)

**Interfaces:**
- Consumes: the complete `STRINGS` dictionary (all prior tasks)
- Produces: nothing — this is the terminal verification task.

- [ ] **Step 1: Write the failing test**

Create `tests/test_i18n_coverage.py` — a plain Python script (no Playwright/browser needed) that greps `dossiary.html` for every `data-i18n*` attribute value and every `t('...')`/`t("...")` call's key argument, and confirms each one exists in both `STRINGS.en` and `STRINGS.de`:

```python
import os, re, json, subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.abspath(os.path.join('..', 'dossiary.html'))
html = open(APP_PATH, encoding='utf-8').read()

# Extract the STRINGS object's two language blocks by locating "const STRINGS = {"
# and the matching top-level "en:" / "de:" object bodies, then pulling every
# `key:` identifier out of each with a regex -- deliberately not a real JS
# parser (no such dependency in this repo), just enough structure-awareness
# to avoid false matches inside string values that happen to contain a colon.
strings_match = re.search(r'const STRINGS = \{(.*?)\n  \};', html, re.DOTALL)
assert strings_match, "Could not locate STRINGS object in dossiary.html"
strings_body = strings_match.group(1)

en_match = re.search(r'en:\s*\{(.*?)\n    \},\s*\n    de:', strings_body, re.DOTALL)
de_match = re.search(r'de:\s*\{(.*?)\n    \},', strings_body, re.DOTALL)
assert en_match and de_match, "Could not split STRINGS into en/de blocks"

key_re = re.compile(r'^\s*(\w+):', re.MULTILINE)
en_keys = set(key_re.findall(en_match.group(1)))
de_keys = set(key_re.findall(de_match.group(1)))

print(f"STRINGS.en has {len(en_keys)} keys, STRINGS.de has {len(de_keys)} keys")

# Every referenced key -- from data-i18n*="key" attributes and t('key'...)/t("key"...) calls
attr_keys = set(re.findall(r'data-i18n(?:-placeholder|-title|-aria-label)?="([a-zA-Z0-9]+)"', html))
call_keys = set(re.findall(r"t\(\s*['\"]([a-zA-Z0-9]+)['\"]", html))
referenced_keys = attr_keys | call_keys

missing_from_en = referenced_keys - en_keys
missing_from_de = referenced_keys - de_keys
unused_en_only = en_keys - referenced_keys  # defined but never referenced -- not a failure, just reported

print("Keys referenced in markup/code but missing from STRINGS.en:", sorted(missing_from_en))
print("Keys referenced in markup/code but missing from STRINGS.de:", sorted(missing_from_de))
print("Keys defined in STRINGS but never referenced (informational only):", sorted(unused_en_only))

assert not missing_from_en, f"{len(missing_from_en)} key(s) missing from STRINGS.en"
assert not missing_from_de, f"{len(missing_from_de)} key(s) missing from STRINGS.de"
print("PASS")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_i18n_coverage.py`

Expected at this point in the plan (Tasks 1-14 already complete by the time this task runs): PASS already, since every prior task added its keys to both languages in the same commit that referenced them — there should be no gap to find. This step's real purpose is catching a *regression*: temporarily comment out one `STRINGS.de` entry (e.g. rename `emptyTitle` to `emptyTitleX` in the `de` block only) and confirm the script correctly reports it as missing and fails, then revert the temporary change. This proves the check actually catches what it's designed to catch, rather than trivially passing regardless of input.

- [ ] **Step 3: Fix any real gaps the check finds**

If Step 2's real (non-sabotaged) run reports genuine missing keys, add them to `STRINGS.en`/`STRINGS.de` now, matching the translation conventions established in Tasks 1-14.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: PASS, with the sabotage from Step 2 reverted.

- [ ] **Step 5: Document in CLAUDE.md and commit**

Add a new architecture note to `CLAUDE.md`, following the file's established style (explaining *why*, not just *what* — see existing notes like the nav-style or sort-persistence ones for the pattern). Content to cover:

- `STRINGS`/`t()`/`applyI18n()` and the `data-i18n`/`data-i18n-placeholder`/`data-i18n-title`/`data-i18n-aria-label` attribute convention, with the static-vs-dynamic-markup split (attributes for parse-time HTML, inline `t()` calls for anything rebuilt in JS on every render).
- Why persistence is `localStorage` (`dossiary_lang` key), not the per-library `settings` table — the empty-state screen has to translate before any library/database exists.
- The auto-detect-then-manual-override behavior (`navigator.language` checked only when no stored preference exists yet; any manual toggle click permanently overrides it from then on).
- The singular/plural key-pair convention for count-dependent strings (no ICU library — each language supplies its own grammatically correct singular/plural phrasing, picked by the same ternary the English-only code already had).
- The `tests/test_i18n.py` + `tests/test_i18n_coverage.py` split — one Playwright suite exercising real toggle behavior across every UI area, one plain-Python static check guaranteeing no `data-i18n`/`t()` reference ever points at a key missing from either language.
- Update the "How this was tested" section's test-suite script count and add a short description of what `test_i18n.py`/`test_i18n_coverage.py` cover, following the existing paragraph's format.

Also add one line to `README.md`/`README.de.md` (wherever this repo documents user-facing features, e.g. near any existing UI-feature list) noting the in-app English/German toggle exists — a one-sentence mention, not a new section; skip this step if no existing README section is a natural fit (check the file's current structure before assuming where it goes, rather than inventing a new section).

```bash
git add dossiary.html tests/test_i18n_coverage.py CLAUDE.md README.md README.de.md
git commit -m "Add static i18n key-coverage check and document the language-support architecture"
```

---

## Post-plan verification

After Task 15, run the full existing test suite (not just the new i18n tests) to confirm nothing regressed:

```bash
cd tests && for f in test_*.py; do echo "=== $f ==="; python3 "$f"; done
```

Every file should print `PASS` (or, for files using the print-based-observation convention without an explicit `PASS` marker, no `Traceback` and every printed assertion line reading `True`) with an empty `JS ERRORS: []` list, matching this repo's established verification convention.

Also do a real-browser spot check (not just the Playwright stub suite) per CLAUDE.md's standing note that the stub setup validates the app's own logic but not real `sql.js`/`Tesseract.js`/browser-dialog behavior: open `dossiary.html` directly in Chrome or Edge, toggle to German, and visually confirm the nav/toolbar/a few forms render legibly (no text overflow/wrapping regressions from longer German phrases — German UI strings are often meaningfully longer than their English equivalents, e.g. `toolbarAddDocument`'s "＋ Dokument hinzufügen" vs "＋ Add document", which this plan's Playwright-only testing cannot visually catch).
