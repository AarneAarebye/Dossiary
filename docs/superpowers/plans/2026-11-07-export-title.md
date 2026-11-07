# Export title and description Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The export dialog gets an optional title and description (prefilled from the library's own), saved in `export-details.json` next to `index.csv`; the import panel shows them for a folder with an `index.csv`.

**Architecture:** `openExportModal()` writes the file after `index.csv`. `openImportModal()` skips the file in its scan, reads it, and hands the texts to `askImportCollection()`, which shows them and pre-fills the new-collection name.

**Tech Stack:** `dossiary.html` (single file, vanilla JS), Playwright for Python tests with `tests/stub_studio2.js`.

**Spec:** `docs/superpowers/specs/2026-11-07-export-title-design.md` (read it; it is binding).

**Prerequisite:** the library-details plan (`2026-11-07-library-details.md`) is finished: `libraryTitle`, `libraryDescription` and `cleanLibraryText(value, max)` exist (limits `LIBRARY_TITLE_MAX = 60`, `LIBRARY_DESCRIPTION_MAX = 300`). The folder import's collection step (`askImportCollection(folderName, matchedCount)`, v1.59.0) exists. Note `libraryDisplayName(folderName)` is an older, unrelated function (the new header function is `libraryHeaderName()`).

## Global Constraints

- Single file: all code goes into `dossiary.html`; no build step.
- Every new string exists in all 7 languages (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`, `hy`); `tests/test_i18n_coverage.py` must pass. `hy` uses `key: "value"` with double quotes; the others use single quotes, so avoid apostrophes or use the typographic ’. Armenian is unreviewed: say so in the report.
- Texts inserted into HTML go through `escapeHtml()`; texts shown through `t('key', {…})`.
- The export file name is exactly `export-details.json`; content `{"format":1,"title":…,"description":…}`; written only when `index.csv` was written under the name `index.csv` and at least one text is non-empty.
- The library's own settings are never changed by an export.
- The folder import only reads the folder; `export-details.json` is never imported as a document.
- Run tests from `tests/` with `/usr/local/bin/python3` (the one with Playwright). Commit messages end with the two attribution lines given by the session.

---

### Task 1: Export dialog writes the file

**Files:**
- Modify: `dossiary.html` (`openExportModal()` near line 9307; the 7 `STRINGS` blocks)
- Test: `tests/test_export_details.py` (create)

**Interfaces:**
- Consumes: `libraryTitle`, `libraryDescription`, `cleanLibraryText`, `LIBRARY_TITLE_MAX`, `LIBRARY_DESCRIPTION_MAX`, `uniqueFileNameIn`, `buildExportCsv`.
- Produces: dialog ids `#export-title`, `#export-description`; the file `export-details.json`; constant `EXPORT_DETAILS_FILE = 'export-details.json'`.

Strings (translate the same meaning in the other six languages, matching each block's vocabulary):

| key | English |
|---|---|
| `exportTitleLabel` | `Title (optional)` |
| `exportDescriptionLabel` | `Description (optional)` |
| `exportDetailsFileHint` | `Saved next to index.csv and shown when the folder is imported. The library itself is not changed.` |
| `importAboutExport` | `About this export` |

(The last is used in Task 2; add all four here.)

- [ ] **Step 1: Write the failing test.** Create `tests/test_export_details.py` with the header, route handler and stub setup of `tests/test_import_folder.py`/`tests/test_library_details.py`, a seeded library with `library_title`/`library_description` settings, and helpers `library(page)` and `folder_files(page)` (reads `window.__FOLDER` entries and file texts via `evaluate`). Scenarios (print `"<claim>:", <bool>`):
  1. Select documents, open the export dialog: `#export-title` and `#export-description` hold the library's texts; with a library without them both are empty.
  2. Change the texts (`Annual\nreview  2025`, a description with spaces and a line break), export into an empty `__FOLDER`: `export-details.json` exists with `format == 1`, the cleaned title/description; the library's `settings` rows are unchanged.
  3. Both fields cleared: no `export-details.json`. "Include index.csv" unchecked: both fields disabled, no file. A destination that already holds an `index.csv`: the new index is numbered and no details file is written.
  4. A 100-character title is cut to 60 in the file.
  Finish with `print("No page errors:", not errors, errors)`.
- [ ] **Step 2:** Run `cd tests && /usr/local/bin/python3 test_export_details.py`. Expected: scenario 1 fails (no `#export-title`).
- [ ] **Step 3: Implement.**
  - Add the 4 strings to all 7 blocks.
  - In the export dialog markup, after the two toggles:
```js
          <div class="field">
            <label for="export-title">${t('exportTitleLabel')}</label>
            <input type="text" id="export-title" maxlength="${LIBRARY_TITLE_MAX}" value="${escapeHtml(libraryTitle)}" />
          </div>
          <div class="field">
            <label for="export-description">${t('exportDescriptionLabel')}</label>
            <textarea id="export-description" rows="3" maxlength="${LIBRARY_DESCRIPTION_MAX}">${escapeHtml(libraryDescription)}</textarea>
            <div class="field-hint">${t('exportDetailsFileHint')}</div>
          </div>
```
    (check `.field` / `.field-hint` are the classes the Library details dialog and others use; follow whatever Task 1 of the library-details plan used.)
  - Keep the fields in step with the index toggle:
```js
    const syncExportDetailsFields = () => {
      const on = el('export-index-toggle').checked;
      el('export-title').disabled = el('export-description').disabled = !on;
    };
    el('export-index-toggle').addEventListener('change', syncExportDetailsFields);
```
    and include `el('export-title').disabled = el('export-description').disabled = true;` in the line that disables controls when the run starts.
  - Read the texts before the run (after the picker, next to `withIndex`): 
```js
      const detailsTitle = cleanLibraryText(el('export-title').value, LIBRARY_TITLE_MAX);
      const detailsDescription = cleanLibraryText(el('export-description').value, LIBRARY_DESCRIPTION_MAX);
```
  - After the `index.csv` write inside the `if(withIndex && exported.length){ … }` block:
```js
          if(indexName === 'index.csv' && (detailsTitle || detailsDescription)){
            const dw = await (await dest.getFileHandle(EXPORT_DETAILS_FILE, { create: true })).createWritable();
            await dw.write(JSON.stringify({ format: 1, title: detailsTitle, description: detailsDescription }, null, 2));
            await dw.close();
          }
```
    with `const EXPORT_DETAILS_FILE = 'export-details.json';` declared near the other export constants. Make sure the details file's name is also added to the `taken` set logic only if needed (it is not in `uniqueFileNameIn`'s use; an exported document can never be named `export-details.json` unless a document file has that name: check `exportFileName()` and, if a document could collide, add the name to `taken` before the files loop so such a document is numbered instead).
- [ ] **Step 4:** Run `/usr/local/bin/python3 test_export_details.py` (all `True`), `test_i18n_coverage.py`, and every existing export test (`ls test_*export*.py`), `test_import_folder.py`, `test_import_collection.py`. Expected: pass. Screenshot the export dialog at 1440 and 390 px width and tidy spacing with existing classes only.
- [ ] **Step 5: Commit.** `git add dossiary.html tests && git commit -m "feat: optional title and description in the export dialog"`

---

### Task 2: The import shows them

**Files:**
- Modify: `dossiary.html` (`openImportModal()` file scan near line 9636, `askImportCollection()`)
- Test: `tests/test_export_details.py`

**Interfaces:**
- Consumes: Task 1 (`EXPORT_DETAILS_FILE`, the file format, string `importAboutExport`), `cleanLibraryText`, existing `askImportCollection(folderName, matchedCount)`.
- Produces: `askImportCollection(folderName, matchedCount, about)` where `about` is `{title, description}` or `null`; `async readExportDetails(handle) -> {title, description} | null`.

- [ ] **Step 1: Write the failing tests** (extend `tests/test_export_details.py`; spec scenarios 4–8). Build folders with the same `make_folder` helper style as `test_import_collection.py` (files plus `index.csv` plus an optional `export-details.json`), or reuse the Task 1 export output. Scenarios: (4) export from the library (as in Task 1), then import the folder into an empty library: `#import-options` shows "About this export", the title and the description as text; a title like `<b>x</b>` is shown literally (`inner_html` contains `&lt;b&gt;`); after importing, the documents are exactly the exported files (no extra document for the json). (5) index.csv but no details file; a malformed `export-details.json` (`{nope`); a file with empty texts: no "About this export" block and the import works as before. (6) a folder with a details file but no `index.csv`: the import runs at once and the json is not imported (document count = number of real files). (7) "A new collection" starts with the export title; without one, with the folder name. (8) a hand-made file with a 200-character title shows it cut to 60.
- [ ] **Step 2:** Run it. Expected: scenarios 4–8 fail.
- [ ] **Step 3: Implement.**
  - Helper, near `parseCsv()`:
```js
  // The title and description an export wrote next to its index.csv, or null
  // when there is no usable file. Never throws: a bad file is just ignored.
  async function readExportDetails(handle){
    try{
      const data = JSON.parse(await (await handle.getFile()).text());
      if(!data || typeof data !== 'object') return null;
      const title = cleanLibraryText(data.title, LIBRARY_TITLE_MAX);
      const description = cleanLibraryText(data.description, LIBRARY_DESCRIPTION_MAX);
      return (title || description) ? { title, description } : null;
    }catch(e){ return null; }
  }
```
  - In the folder scan loop, next to the `index.csv` special case, add `if(name.toLowerCase() === EXPORT_DETAILS_FILE){ detailsHandle = handle; continue; }` (declare `let detailsHandle = null;` beside `indexHandle`). After the index is read, `const about = (index && detailsHandle) ? await readExportDetails(detailsHandle) : null;`. Make sure the "no files to import" check still sees only real files (the json is skipped, so a folder holding only the json and an index counts as empty exactly as one holding only an index does).
  - Pass `about` to `askImportCollection(src.name, matchedCount, about)`. In its markup, before the count line, when `about`:
```js
      ${about ? `<div class="import-about">
        <div class="doc-sub">${escapeHtml(t('importAboutExport'))}</div>
        ${about.title ? `<div class="doc-title">${escapeHtml(about.title)}</div>` : ''}
        ${about.description ? `<p>${escapeHtml(about.description)}</p>` : ''}
      </div>` : ''}
```
    and make "A new collection" the default choice (`#import-coll-new` checked, `#import-coll-name` enabled, the dropdown disabled, the run button's enabled state computed by the existing `update()`), with the name from a new helper:
```js
  // "{export title or folder name} · 2026-11-07 14:32", local time.
  function importCollectionDefaultName(about, folderName, now = new Date()){
    const p = (n) => String(n).padStart(2, '0');
    const stamp = `${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())} ${p(now.getHours())}:${p(now.getMinutes())}`;
    return `${(about && about.title) || folderName} · ${stamp}`;
  }
```
    Only files listed in `index.csv` join the collection (the existing `memberIds` rule): do not change it. Update `tests/test_import_collection.py`: its scenario 2 asserted `#import-coll-none` as the default; it must now expect `#import-coll-new` checked with the date-stamped name, and the run in that scenario must click "No collection" first where it expects no collection to be created. Check every other scenario there for the same assumption.
- [ ] **Step 4:** Run `/usr/local/bin/python3 test_export_details.py`, `test_import_folder.py`, `test_import_collection.py`, `test_i18n_coverage.py`. Expected: pass, no page errors. Screenshot the import panel with and without the block at 1440 and 390 px.
- [ ] **Step 5: Commit.** `git add dossiary.html tests && git commit -m "feat: show an export's title and description when importing it"`

---

### Task 3: Docs, version, full suite

**Files:**
- Modify: `dossiary.html` (`APP_VERSION` → the next minor after the current value, for example `'1.61.0'` if it is `'1.60.0'`), `scan_watch.py` (`__version__`), `tests/test_scan_watch_version.py` (all three together; see `.claude/skills/cutting-a-release/SKILL.md`), `README.md` and `README.de.md` (the Export and "Import a folder or earlier export" bullets), `docs/architecture/08-fields-bulk-checks-grid.md` ("Export selected documents" and "Import a folder": `export-details.json`, `readExportDetails`, the skip in the scan, the known cost with older versions), `AGENTS.md` (test count), `tests/CLAUDE.md` and `tests/coverage/` (list `test_export_details.py` as `test_import_collection.py` is listed)

- [ ] **Step 1:** Update the docs and the three version places; do not tag, push or release. Count the scripts in `tests/` for the new total.
- [ ] **Step 2:** Run the whole suite as `tests/CLAUDE.md` describes, checking each script's exit status. Report any failure with its output; re-run an unrelated failure once and say so.
- [ ] **Step 3: Commit.** `git add -A` (leave the untracked `start_last_claude` alone) `&& git commit -m "docs: export title and description (<version>)"`.
