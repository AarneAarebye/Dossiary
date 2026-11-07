# Import a folder: title and "add to a collection" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the folder import so it names earlier exports, and let a folder with an `index.csv` put its imported documents into a new or existing manual collection.

**Architecture:** `openImportModal()` in `dossiary.html` gets a promise-based options panel (`askImportCollection()`) that runs only when an `index.csv` was read. The import loop collects the ids of documents that had an index row (added documents and the existing documents behind skipped duplicates); after the loop the existing helpers `createManualCollection()` and `addDocumentsToCollection()` write the collection.

**Tech Stack:** `dossiary.html` (single file, vanilla JS, sql.js), Playwright for Python tests with `tests/stub_studio2.js`.

**Spec:** `docs/superpowers/specs/2026-11-07-import-folder-collection-design.md` (read it; it is binding).

## Global Constraints

- Single file: all code goes into `dossiary.html`; no build step, no new files besides tests and docs.
- No `window.prompt()`/`alert()`; use inline panels (as the bulk-bar "New collection" form does).
- Every new string exists in all 7 languages (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`, `hy`); `tests/test_i18n_coverage.py` must pass. The `hy` block uses `key: "value"` with double quotes; the others use single quotes on long one-line blocks. Armenian is not reviewed: say so in the report.
- User-visible text uses `t('key')`, with `escapeHtml()` for names inserted into HTML.
- The folder is only read; files without an index row go to the Inbox exactly as today.
- Run tests from `tests/`: `python3 test_x.py`; the whole suite with the repo's usual runner (see `tests/CLAUDE.md`).
- Commit messages end with the two attribution lines given by the session.

---

### Task 1: Titles and strings

**Files:**
- Modify: `dossiary.html` (the 7 `STRINGS` blocks: lines near 1189, 1424, 1659, 1894, 2129, 2364, and the `hy` block near 2810)
- Test: `tests/test_import_collection.py` (created here, extended in Task 2)

**Interfaces:**
- Produces: string keys `importIndexFound` (`{count}`), `importAddLabel`, `importAddNone`, `importAddExisting`, `importAddNew`, `importNewNamePlaceholder`, `importNameTaken`, `importRunBtn`, `importCountCollection` (`{name}`, `{count}`), `importCollectionFailed`; changed `toolbarImportFolder`, `importModalTitle`.

English texts (translate the same meaning in the other six languages, matching each block's style; keep the 📂 in `toolbarImportFolder`):

| key | English |
|---|---|
| `toolbarImportFolder` | `📂 Import a folder or earlier export…` |
| `importModalTitle` | `Import a folder or earlier export` |
| `importIndexFound` | `{count} files in this folder are listed in index.csv.` |
| `importAddLabel` | `Add the imported documents to a collection` |
| `importAddNone` | `No collection` |
| `importAddExisting` | `An existing collection` |
| `importAddNew` | `A new collection` |
| `importNewNamePlaceholder` | `Collection name` |
| `importNameTaken` | `A collection with this name already exists. Choose it under “An existing collection”.` |
| `importRunBtn` | `Import` |
| `importCountCollection` | `Added to the collection “{name}”: {count}` |
| `importCollectionFailed` | `The documents were imported, but the collection could not be saved.` |

- [ ] **Step 1: Write the failing test.** Create `tests/test_import_collection.py` with the same header as `tests/test_import_folder.py` (lines 1–9: the `chdir`, `APP_PATH`, imports), the route handler and `add_init_script(open('stub_studio2.js').read())`, then:

```python
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.route('**/*', route_handler)          # same handler as test_import_folder.py
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({documents: [], fields: []});")
        await page.click("#open-btn"); await page.wait_for_timeout(500)
        await page.click('#tools-btn')
        print("The Tools entry names earlier exports:", 'earlier export' in await page.inner_text('#import-folder-btn'))
        await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
        print("The dialog title names earlier exports:", 'earlier export' in await page.inner_text('.modal h2'))
        print("No page errors:", not errors, errors)

asyncio.run(main())
```

- [ ] **Step 2:** Run `cd tests && python3 test_import_collection.py`. Expected: the first two lines print `False`.
- [ ] **Step 3:** Add all 12 keys to all 7 `STRINGS` blocks (changing the two existing keys in place).
- [ ] **Step 4:** Run `python3 test_import_collection.py` (all `True`), `python3 test_i18n_coverage.py`, `python3 test_import_folder.py`. Expected: all pass. If `test_import_folder.py` checks the old title text, update that assertion to the new one.
- [ ] **Step 5: Commit.** `git add dossiary.html tests && git commit -m "feat: name earlier exports in the folder import title"`

---

### Task 2: The collection step

**Files:**
- Modify: `dossiary.html` — `createReviewDocumentFromFile()` (near line 15262, the `skippedDuplicate` return), `openImportModal()` (near line 9454)
- Test: `tests/test_import_collection.py`

**Interfaces:**
- Consumes: Task 1 string keys; `collections` (array of `{id, name, kind}`), `createManualCollection(name) -> id|null`, `addDocumentsToCollection(id, docIds) -> bool`, `escapeHtml`, `t`.
- Produces: `askImportCollection(folderName, matchedCount) -> Promise<{mode:'none'}|{mode:'existing',id:number}|{mode:'new',name:string}>`; `createReviewDocumentFromFile()` duplicate result gains `duplicateOfId`.

- [ ] **Step 1: Write the failing tests.** Extend the test file. Build the folder in the test (no export step):

```python
async def make_folder(page, name, files, index_rows):
    """files: {filename: text}; index_rows: list of (filename, title). Writes index.csv when index_rows is not None."""
    await page.evaluate("""async ([name, files, rows]) => {
        const dir = window.__makeEmptyRoot(); dir.name = name;
        const put = async (n, c) => { const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); };
        for(const [n, c] of Object.entries(files)) await put(n, c);
        if(rows !== null) await put('index.csv', 'File,Title\\n' + rows.map(r => r[0] + ',' + r[1]).join('\\n') + '\\n');
        window.__FOLDER = dir;
    }""", [name, files, index_rows])

async def library(page):
    return await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")

async def open_import(page):
    await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)

async def pick(page):
    await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__FOLDER; }")
    await page.click('#import-start-btn'); await page.wait_for_timeout(400)
```

Scenarios (each prints `"<claim>:" , <bool>`; `library(page)` returns the stub's JSON tables, so check `rows['collections']` and `rows['collection_documents']`, `rows['documents']`):

1. **Plain folder**: `make_folder(page, 'Plain', {'a.pdf': '%PDF-1.4 a'}, None)`; `open_import`, `pick`, wait 1000 ms. Expect `#import-options` not visible and `#import-summary` contains `Added: 1`.
2. **Folder with index, "No collection" default**: files `b.pdf`, `c.pdf`, `loose.pdf`; index rows for `b.pdf` and `c.pdf`. After `pick`: `#import-options` visible, text contains `2 files in this folder are listed in index.csv.`, `#import-coll-none` is checked, `#import-coll-existing` is disabled (no manual collection yet). Click `#import-run-btn`, wait 1200 ms: `Added: 3`, and `collections` is empty.
3. **New collection**: new folder `Taxes 2025` with `d.pdf`, `e.pdf`, `loose2.pdf`, index rows for the first two. After `pick`: `#import-coll-name` has value `Taxes 2025`, "Import" enabled after `check('#import-coll-new')`. Click `#import-run-btn`. Expect one manual collection named `Taxes 2025`, `collection_documents` holding exactly the two documents titled by the index rows (the third, titled `loose2`, is absent), and the summary contains `Added to the collection “Taxes 2025”: 2`.
4. **Existing collection and duplicates**: same folder `Taxes 2025` again but with a new file `f.pdf` (index rows `d.pdf`, `f.pdf`). `open_import`, `pick`, check `#import-coll-existing`, `select_option('#import-coll-select', label='Taxes 2025')`, run. Expect `d.pdf` skipped as a duplicate yet still a member, `f.pdf` newly added and a member: `collection_documents` for that collection holds 3 documents; summary contains `Added to the collection “Taxes 2025”: 2`.
5. **Taken name**: new folder with an index; check `#import-coll-new`, fill `#import-coll-name` with `taxes 2025` (different case): `#import-run-btn` is disabled and `#import-coll-warn` contains `already exists`.
6. **Nothing qualifies**: folder `Empty rows` with `g.pdf` and an `index.csv` listing only `other.pdf`; choose "A new collection" named `Ghost`, run: the library has no collection `Ghost`; the summary has no `Added to the collection` line.
7. **Cancel**: with the panel showing, click `#import-cancel-btn`: the modal closes and the document count is unchanged.

Finish with `print("No page errors:", not errors, errors)`.

- [ ] **Step 2:** Run it. Expected: scenarios 2–7 fail (no `#import-options`).
- [ ] **Step 3: Implement.**

(a) In `createReviewDocumentFromFile()` change the duplicate return to
```js
        return { id: null, title: null, skippedDuplicate: true, duplicateOfId: duplicateMatch.id };
```

(b) In `openImportModal()`'s template add, directly after `<div class="status" id="import-status"></div>`:
```js
          <div id="import-options" style="display:none;"></div>
```

(c) Add before `openImportModal()`:
```js
  // Asks where the documents of an index.csv folder should go. Resolves when
  // "Import" is clicked; if the dialog is closed instead, it never resolves.
  function askImportCollection(folderName, matchedCount){
    return new Promise(resolve => {
      const manual = collections.filter(c => c.kind === 'manual').sort((a, b) => a.name.localeCompare(b.name));
      const box = el('import-options');
      box.style.display = '';
      box.innerHTML = `
        <p>${escapeHtml(t('importIndexFound', {count: matchedCount}))}</p>
        <fieldset class="import-collection-choice">
          <legend>${escapeHtml(t('importAddLabel'))}</legend>
          <label><input type="radio" name="import-coll" id="import-coll-none" checked> ${escapeHtml(t('importAddNone'))}</label>
          <label><input type="radio" name="import-coll" id="import-coll-existing"${manual.length ? '' : ' disabled'}> ${escapeHtml(t('importAddExisting'))}</label>
          <select id="import-coll-select">${manual.map(c => `<option value="${c.id}">${escapeHtml(c.name)}</option>`).join('')}</select>
          <label><input type="radio" name="import-coll" id="import-coll-new"> ${escapeHtml(t('importAddNew'))}</label>
          <input type="text" id="import-coll-name" value="${escapeHtml(folderName)}" placeholder="${escapeHtml(t('importNewNamePlaceholder'))}" />
        </fieldset>
        <div class="status err" id="import-coll-warn" style="display:none;">${escapeHtml(t('importNameTaken'))}</div>
        <div class="modal-actions"><button class="primary" id="import-run-btn">${escapeHtml(t('importRunBtn'))}</button></div>`;
      const mode = () => el('import-coll-new').checked ? 'new' : el('import-coll-existing').checked ? 'existing' : 'none';
      const update = () => {
        const m = mode();
        el('import-coll-select').disabled = m !== 'existing';
        el('import-coll-name').disabled = m !== 'new';
        const name = el('import-coll-name').value.trim();
        const taken = m === 'new' && manual.some(c => c.name.trim().toLowerCase() === name.toLowerCase());
        el('import-coll-warn').style.display = taken ? '' : 'none';
        el('import-run-btn').disabled = (m === 'new' && (!name || taken)) || (m === 'existing' && !el('import-coll-select').value);
      };
      box.addEventListener('input', update);
      box.addEventListener('change', update);
      update();
      el('import-run-btn').addEventListener('click', () => {
        const m = mode();
        box.style.display = 'none';
        if(m === 'existing') resolve({ mode: 'existing', id: Number(el('import-coll-select').value) });
        else if(m === 'new') resolve({ mode: 'new', name: el('import-coll-name').value.trim() });
        else resolve({ mode: 'none' });
      });
    });
  }
```

(d) In the start-button handler, after the `index`/`indexError` parsing and before `const startBtn = ...`, insert:
```js
      let choice = null;
      if(index){
        el('import-start-btn').style.display = 'none';
        choice = await askImportCollection(src.name, files.filter(f => index.has(f.name.toLowerCase())).length);
      }
```
(`startBtn.style.display = 'none'` is already set after the run; keep it.)

(e) Declare `const memberIds = [];` next to `const failed = [];`. In the loop, replace
```js
            if(result.skippedDuplicate){ skipped++; continue; }
            added++;
            if(rec) withDetails++;
```
with
```js
            if(result.skippedDuplicate){
              skipped++;
              if(rec && result.duplicateOfId != null) memberIds.push(result.duplicateOfId);
              continue;
            }
            added++;
            if(rec){ withDetails++; memberIds.push(result.id); }
```

(f) After the `if(added){ renderStats(); ... }` block and the `lines` construction (after the `importCountUnmatched` line is pushed, before `keptFolders` is reported), add:
```js
      let collectionFailed = false;
      if(choice && choice.mode !== 'none' && memberIds.length){
        const cid = choice.mode === 'existing' ? choice.id : await createManualCollection(choice.name);
        const ok = cid != null && await addDocumentsToCollection(cid, memberIds);
        const c = ok ? collections.find(x => x.id === cid) : null;
        if(c) lines.push(t('importCountCollection', {name: c.name, count: memberIds.length}));
        else{ collectionFailed = true; lines.push(t('importCollectionFailed')); }
      }
```
and add `|| collectionFailed` to the condition that sets the status class to `err`.

- [ ] **Step 4:** Run `python3 test_import_collection.py` (all `True`), `python3 test_import_folder.py`, `python3 test_i18n_coverage.py`, `python3 test_import_date_column.py`. Expected: all pass, no page errors. Also open the dialog once in a headed or screenshot run and check the panel looks tidy at 1440 and 390 px width (`page.screenshot`), fixing spacing with existing CSS classes only.
- [ ] **Step 5: Commit.** `git add dossiary.html tests && git commit -m "feat: add imported documents to a collection"`

---

### Task 3: Docs, version, full suite

**Files:**
- Modify: `dossiary.html` (`APP_VERSION` → `'1.59.0'`), `README.md` (the "Import a folder" bullet near line 259), `README.de.md` (matching bullet), `docs/architecture/08-fields-bulk-checks-grid.md` (the "Import a folder" note near line 1173), `AGENTS.md` (the tests count "110 scripts" → 111), `tests/coverage/` index entry for `test_import_collection.py` (follow how `test_import_folder.py` is listed; see `tests/CLAUDE.md`)

- [ ] **Step 1:** README: rename the bullet to **Import a folder or earlier export**, and add: "If the folder has an `index.csv`, you can also add the imported documents to a new or an existing collection; only the files listed in `index.csv` are added." Mirror it in German. Update the architecture note: `askImportCollection()`, `memberIds`, `duplicateOfId`, no empty collection.
- [ ] **Step 2:** Bump `APP_VERSION`. Check the cutting-a-release skill (`.claude/skills/cutting-a-release/SKILL.md`) for other places that must stay in sync, but do not tag or release.
- [ ] **Step 3:** Run the whole suite as `tests/CLAUDE.md` describes. Expected: every script passes (check each script's own exit status, not a grep for the word "False").
- [ ] **Step 4: Commit.** `git add -A && git commit -m "docs: import a folder or earlier export, add to a collection (1.59.0)"`. Do not push or release.
