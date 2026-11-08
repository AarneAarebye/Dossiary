# One subfolder per export, multi-export import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Every export lands in its own new subfolder of the chosen folder; the import can list several export subfolders and import the ticked ones, each into its own collection; stray `index (N).csv` files are never imported as documents.

**Architecture:** Spec: `docs/superpowers/specs/2026-11-08-export-subfolder-design.md` (read it fully first; it is the requirements). Export: create the subfolder, then the existing loop writes into it. Import: classify the picked folder (own `index.csv` / export subfolders / plain), move the per-folder import body of `openImportModal()` into `importOneFolder(...)` so the single-folder path calls it once and the multi-export path once per ticked export, plus a list panel `askImportExports(...)`.

**Tech Stack:** Vanilla JS single-file page `dossiary.html`, File System Access API, Playwright (Python) in `tests/`, run with `/usr/local/bin/python3` from `tests/`, stubs in `tests/stub_studio2.js` (extend the stub only if a needed directory behaviour is missing; keep other tests passing).

## Global Constraints

- Subfolder names: `{title} · YYYY-MM-DD HH-MM` with a title, else `Export YYYY-MM-DD HH-MM`; forbidden `/ \ : * ? " < > |` and control characters become `-`; title part trimmed and cut at 100 characters; name clash gets ` (2)`, ` (3)`.
- Inside the subfolder `index.csv` and `export-details.json` keep their plain names; documents named like them are still numbered (`taken` keeps both reserved names).
- Import regexes: `/^index \(\d+\)\.csv$/i` and `/^export-details \(\d+\)\.json$/i`.
- Collection names for imports stay `{export title or folder/subfolder name} · YYYY-MM-DD HH:MM`, made unique with ` (2)`, ` (3)` (against existing collections and the other names in the same run).
- Multi-export mode looks only at direct, non-hidden subfolders that contain an `index.csv`; top-level files of the parent are ignored in that mode.
- Strings in all 7 language blocks (en, es, fr, de, zh-Hans, zh-Hant, hy; Armenian unreviewed; zh-Hant by hand); `tests/test_i18n_coverage.py` passes. English text short and plain.
- Do not push, tag or release. Commit per task, messages end with:
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_0117epTz6pLGF3vCWxi4JMsL`.
- The full suite (every `tests/test_*.py`) passes at the end of every task.

---

### Task 1: Export writes into a new subfolder

**Files:**
- Modify: `dossiary.html` (`openExportModal`, new helpers near `EXPORT_DETAILS_FILE`)
- Create: `tests/test_export_subfolders.py` (scenarios 1, 2, 9 of the spec)
- Modify (adapt): `tests/test_export.py`, `tests/test_export_details.py`, `tests/test_import_folder.py` and any other test that exports and then reads the picked folder directly (grep `export-start-btn`)

**Interfaces:**
- Produces: `sanitizeFolderName(name) -> string`, `exportSubfolderName(title, now = new Date()) -> string`, `uniqueSubfolderIn(parentHandle, baseName) -> Promise<FileSystemDirectoryHandle>` (creates and returns the directory, numbering on clash).

- [ ] **Step 1:** Add the helpers (spec "Export"). `sanitizeFolderName`: replace forbidden characters with `-`, collapse whitespace, trim, cut at 100. `exportSubfolderName`: `(title ? sanitize(title) + ' · ' : 'Export ') + YYYY-MM-DD HH-MM` (local time, zero padded); a title that is empty after sanitising falls back to `Export `.
- [ ] **Step 2:** In `openExportModal()` start handler, after the inside-library check and before the loop, create the subfolder with `uniqueSubfolderIn(dest, exportSubfolderName(detailsTitle, new Date()))` and use it as the write target for documents, `uniqueFileNameIn`, `index.csv` and `export-details.json` (keep `dest` for the inside-library check; the done message uses the subfolder's `name` as `folder`). If nothing was exported, `removeEntry(subfolderName, {recursive:true})` on the parent in a try/catch that ignores errors. Keep the 1.61.1 behaviour (`taken.add(EXPORT_DETAILS_FILE)`, details write failure handling).
- [ ] **Step 3:** Write `tests/test_export_subfolders.py` scenarios 1, 2, 9 (names, forbidden characters, same-minute clash, index off, all-failed removes the subfolder, helper edge cases via `page.evaluate`). Adapt the existing tests that read exported files so they look inside the single new subfolder (a small shared helper in the test is fine). Run the adapted tests, then the full suite.
- [ ] **Step 4: Commit** `feat: export writes into its own subfolder`.

### Task 2: Import — classify the folder, refactor, skip extra index files

**Files:**
- Modify: `dossiary.html` (`openImportModal`)
- Modify: `tests/test_export_subfolders.py` (scenario 7), adapt `tests/test_import_folder.py` / `tests/test_import_collection.py` only if needed

**Interfaces:**
- Produces: `importOneFolder(src, files, index, about, choice, ctx) -> Promise<{added, withDetails, skipped, failed, unmatchedRows, collectionLine, memberIds...}>` containing exactly the per-folder body that is now inline in the start handler (the loop over files, details from index, duplicate handling, Inbox for unlisted files, collection step). `ctx` carries what is shared (`statusEl`, `newTypes`, progress prefix, hold). Pure refactor for the single-folder path: behaviour and all existing import tests unchanged.

- [ ] **Step 1:** Extract `importOneFolder` from the start handler without changing behaviour; the single-folder path calls it once. Run `test_import_folder.py`, `test_import_collection.py`, `test_export_details.py` — all still pass before going on.
- [ ] **Step 2:** In the scan, skip (never import, never read) names matching the two regexes; count them. When the count is > 0 show the new string `importExtraIndexSkipped` ({count}) in the import summary/status area (add the string in 7 languages).
- [ ] **Step 3:** Add the scan classification as a function `classifyImportFolder(src)` returning `{kind: 'single'|'exports'|'plain', ...}`: `single` when the folder has `index.csv`; `exports` when it has none but ≥1 direct non-hidden subfolder with an `index.csv` (return `[{name, dirHandle, index, about, fileCount}]` using the same `readImportIndex`/`readExportDetails` and counting listed rows whose file exists in that subfolder); else `plain`. For now `exports` is not acted on (Task 3); `single` and `plain` run as today.
- [ ] **Step 4:** Test scenario 7 (index.csv + `index (2).csv` + `export-details (2).json`: imports as today, extra files not documents, note shown). Full suite.
- [ ] **Step 5: Commit** `refactor: import per-folder body, skip extra index files`.

### Task 3: Import several exports

**Files:**
- Modify: `dossiary.html` (`openImportModal`, new `askImportExports`, STRINGS)
- Modify: `tests/test_export_subfolders.py` (scenarios 3, 4, 5, 6, 8)

**Interfaces:**
- Consumes: `classifyImportFolder`, `importOneFolder`, `importCollectionDefaultName`, `askImportCollection` patterns (promise-based panel in `#import-options`).
- Produces: `askImportExports(exports, existingCollections) -> Promise<{selected: [exportIndex...], mode: 'new-per-export'|'none'|'existing', id?}>`.

- [ ] **Step 1:** Add the strings `importExportsFound`, `importExportFiles`, `importExportFilesOne`, `importExportsNewPerExport`, `importExportProgress`, `importExportsSummaryHeading` (7 languages). `askImportExports` renders: heading, one row per export (checkbox ticked, title or subfolder name in bold, description plain text escaped with ellipsis, file count line), then the collection radios (new per export = default with a read-only list of the computed names, none, existing + select). Import button disabled with nothing ticked or with "existing" and no selection. Reuse the radio ids `#import-coll-none/-existing/-new`-style naming where practical, export rows get `.import-export-row` and `#import-export-check-<n>`.
- [ ] **Step 2:** In the start handler, for `kind === 'exports'` call `askImportExports`, then run `importOneFolder` for each selected export in order with a per-export collection decision (name uniqueness against existing collections and earlier names of this run), one `beginPersonFlowHold()` and one busy/close lock for the whole run, progress text `importExportProgress`. A thrown error in one export is recorded for that export and the loop continues. Final summary: heading, totals, then one block per export with its counts and its collection.
- [ ] **Step 3:** Tests scenarios 3, 4, 5, 6, 8 from the spec (two exports in one parent via two real export runs or hand-built stub directories; two collections each containing only their own documents; untick; none/existing apply to all; non-index subfolder and hidden folder not listed, top-level files ignored, plain folder unchanged; one failing export does not stop the other).
- [ ] **Step 4:** Full suite. **Commit** `feat: import several exports from one folder`.

### Task 4: Docs and version

**Files:**
- Modify: `dossiary.html` (`APP_VERSION`), `scan_watch.py` (`__version__`), `tests/test_scan_watch_version.py`, `README.md`, `README.de.md`, `docs/architecture/08-*.md`, `AGENTS.md` (script count), `tests/CLAUDE.md`, `tests/coverage/03-tools-export-share-reports-collections.md`

- [ ] **Step 1:** Version: the minor after the current `APP_VERSION` (the header-title release is 1.62.0, so 1.63.0; check the file first). Sync the three places.
- [ ] **Step 2:** README (+ German): export creates a subfolder; import lists several exports. Architecture note 08: new flow, the classification rules, the old-version cost. AGENTS.md and the two tests docs: new script, scenarios, adapted tests.
- [ ] **Step 3:** Full suite, all pass. **Commit** `chore: version, docs for export subfolders`.
