# One subfolder per export, and importing several exports

Date: 2026-11-08. Scope: the page (`dossiary.html`) only. Builds on the export title (spec `2026-11-07-export-title-design.md`) and the folder import collection step (`2026-11-07-import-folder-collection-design.md`).

## Problem

Exporting into a folder that already held an export produced `index (2).csv` and no `export-details.json` for it. The import reads only `index.csv`, so it imported `index (2).csv` as an ordinary document into the Inbox. Several exports in one place are not supported.

## Decisions (agreed 2026-11-08)

- **One subfolder per export.** The folder the person picks is the parent. Export always creates a new subfolder in it and writes everything there.
- **Import** reads one export folder as today, or, from a folder that holds several export subfolders, lists them and imports the ticked ones, each into its own collection.

## Export

- Subfolder name: `{title} · YYYY-MM-DD HH-MM` when the export has a title (the cleaned Title field), otherwise `Export YYYY-MM-DD HH-MM`. Local time. Characters not allowed in folder names (`/ \ : * ? " < > |` and control characters) become `-`; the result is trimmed and cut at 100 characters before the date part is added. A name that already exists gets ` (2)`, ` (3)`. Created with `getDirectoryHandle(name, {create:true})` after checking it does not exist.
- Documents, `index.csv` and `export-details.json` go into the subfolder. The names inside are the plain ones: `index.csv` and `export-details.json` are never numbered away. A document named like either gets the existing numbering (the reserved names stay in `taken`).
- "Include index.csv" off: the subfolder is still made and holds the files; no index, no details file.
- Nothing exported (all failed): the empty subfolder is removed (best effort, errors ignored).
- The inside-library check still applies to the picked parent. The done message names the subfolder: `exportDone` with `folder` = the subfolder's name (parent not shown).

## Import

After the folder is chosen:

1. **The folder has its own `index.csv`** (a single export folder, or an older flat export): behaviour exactly as today. Additionally any `index (N).csv` and `export-details (N).json` in it (N = digits) are neither imported as documents nor read; if at least one was skipped, the options panel / status shows "Skipped N extra index files from other exports." (new string).
2. **No `index.csv`, but one or more direct subfolders that each contain an `index.csv`:** the options panel shows "This folder holds N exports" with one row per export: a checkbox (ticked), its title (or the subfolder name), its description (plain text, escaped, one line with ellipsis), and "N files listed" (rows of its index whose file is present). Subfolders without an `index.csv`, and hidden folders (name starts with `.`), are not listed. Top-level files of the parent are ignored in this mode. Only direct subfolders are looked at.
3. **Neither:** plain folder import as today.

Collection choice in mode 2 (one choice for the whole run):
- **A new collection per export (default):** each export's collection is named as today (`{title or subfolder name} · YYYY-MM-DD HH:MM`, made unique with ` (2)`, ` (3)` against existing collections and the other names of this run). There is no single editable name field in this mode; the names are shown as a read-only list under the radio.
- **No collection.**
- **One existing collection for all.**
Import button disabled while no export is ticked, or while "existing" has no selection.

Running: exports are imported one after the other with the existing per-folder routine (same duplicate handling, details from the index, Inbox for unlisted files, collection step per export). The progress line names the export ("Export 2 of 3: …"); the summary adds up counts and lists the exports with their own counts (`Added`, `Skipped`, etc.) and the collection each went to. A failure in one export is shown and the next export still runs. The Person-flow hold and the busy/close locks cover the whole run, not each export.

Nothing changes for exports made by earlier versions beyond item 1 above.

## Code changes

- `exportSubfolderName(title, now)`, `sanitizeFolderName(name)`: small pure helpers (testable).
- `openExportModal()`: create the subfolder before the loop, use it as the write target (`dest`) for files, index and details; remove the empty subfolder on total failure; the done message uses the subfolder name. The 1.61.1 details-write error handling stays.
- `openImportModal()`: scan classification (own index / export subfolders / plain); the per-folder import body moves into a function `importOneFolder(src, files, index, about, choice, hooks)` that the single-folder path calls once and the multi-export path calls per ticked export; summary aggregation.
- `askImportExports(exports, existingCollections)`: the list panel (promise-based like `askImportCollection`), ids `#import-exports-list`, `.import-export-row`, `#import-export-check-<n>`, reusing the collection radios (`#import-coll-none/-existing/-new`).
- Index-name matcher: `/^index \(\d+\)\.csv$/i`, `/^export-details \(\d+\)\.json$/i`, used in the file scan for mode 1.
- New strings (7 languages en, es, fr, de, zh-Hans, zh-Hant, hy; Armenian unreviewed): `importExportsFound` ("This folder holds {count} exports."), `importExportFiles` ("{count} files listed"), `importExportFilesOne`, `importExportsNewPerExport` ("A new collection for each export"), `importExtraIndexSkipped` ("Skipped {count} extra index files from other exports."), `importExportProgress` ("Export {n} of {total}: {name}"), `importExportsSummaryHeading`, `exportDoneInSubfolder` if `exportDone` cannot carry the subfolder wording unchanged.
- Version: the next minor after the header-title release (1.63.0 if that is 1.62.0); README (+ German), architecture note 08, AGENTS.md, tests index, coverage doc.

## Known cost

An older Dossiary importing a parent folder made by this version sees only subfolders and reports that there are no files; the person picks the export subfolder instead. The Mac app and iPhone/iPad have no folder import.

## Tests

New `tests/test_export_subfolders.py` (Playwright, stubs as in `test_export_details.py` / `test_import_collection.py`):
1. Export creates `{title} · date` / `Export date` subfolder with files, `index.csv`, `export-details.json` inside; the parent holds only the subfolder; forbidden characters are replaced; a second export in the same minute gets ` (2)`.
2. Index off: subfolder with files only. All files failing: no subfolder left.
3. Two exports in one parent, then import of the parent: list shows both with title, description and file counts; both ticked; result is two collections, each holding only its export's documents; counts add up.
4. Untick one: only the other is imported. Nothing ticked: Import disabled.
5. "No collection" and "One existing collection" apply to all ticked exports.
6. A subfolder without `index.csv` and a hidden folder are not listed; top-level files of the parent are ignored in this mode; parent with neither index nor export subfolders imports as a plain folder.
7. A folder with `index.csv` plus `index (2).csv` and `export-details (2).json`: imports as today, the two extra files are not documents, the note shows.
8. A failing export (stub one document as unreadable) does not stop the next export; summary shows both.
9. `sanitizeFolderName` / `exportSubfolderName` cases via `page.evaluate`: long titles cut, empty after cleaning falls back to "Export".

Existing tests adapted: `test_export.py`, `test_export_details.py`, `test_import_folder.py`, `test_import_collection.py` (exports now land in a subfolder). `test_i18n_coverage.py` keeps passing.

## Out of scope

Merging exports into one collection; reading exports nested deeper than one level; renaming existing exports; Mac app and iPhone/iPad.
