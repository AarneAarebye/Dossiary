# Export title and description, shown at import

Date: 2026-11-07. Scope: the page (`dossiary.html`) only. Depends on the library title and description (spec `2026-11-07-library-details-design.md`, plan `2026-11-07-library-details.md`), which must be built first: the export dialog starts with the library's own texts.

## Problem

An export is a folder of files plus `index.csv`. Nothing in it says what the export is, so when it comes back through "Import a folder or earlier export", the person sees only a folder name.

## Decisions (agreed 2026-11-07)

- **Export:** the dialog gets an optional **Title** and an optional **Description**.
- **Prefill:** both start with the library's own title and description (Library details). They can be changed or cleared for this export; the library itself is not changed.
- **Stored in a small file next to `index.csv`**, not in `index.csv` (that file stays a plain table of documents for older versions and other tools).
- **Import:** when the folder has an `index.csv` (the step after choosing the folder that already exists), the panel also shows the export's title and description if the folder has them.

## The file

`export-details.json` in the export folder:

```json
{ "format": 1, "title": "Birgit’s papers", "description": "Everything about the house and car" }
```

- Written only when `index.csv` is written under its own name (`index.csv`, not a renamed copy) and at least one of the two texts is non-empty. Otherwise no file.
- Texts are cleaned like the library's: whitespace and line breaks collapse to one space, trimmed, title at most 60 characters, description at most 300 (`cleanLibraryText()`).
- Any other keys are ignored on reading; `format` is for the future and not checked beyond being a number or absent.
- An existing `export-details.json` in the destination is overwritten when a new export writes one, and left alone when it does not. An existing `index.csv` already gets a numbered name (`uniqueFileNameIn`): in that case no details file is written, because an import would not read that index either.
- It contains no personal data beyond the two texts the person typed.

## Behaviour

**Export dialog** (`openExportModal()`): two fields below the existing toggles, Title (single line, `maxlength` 60) and Description (textarea, `maxlength` 300), prefilled from `libraryTitle`/`libraryDescription`, with the hint "Saved next to index.csv and shown when the folder is imported. The library itself is not changed." Both are disabled together with "Include index.csv" when that toggle is off (no index, no details), and during the run.

**Import** (`openImportModal()`):
- `export-details.json` is read in the same folder scan as `index.csv` and never imported as a document (it is skipped from the file list, like `index.csv`), also when there is no `index.csv`.
- With a readable `index.csv` and a details file with at least one non-empty text, the options panel starts with an "About this export" block: the title in bold, the description under it, both as plain text (escaped).
- No `index.csv`, an unreadable `index.csv`, a missing, empty or malformed details file: no block, no error, nothing else changes.
- **A collection for the batch is now the default.** The collection choice starts on "A new collection" (it started on "No collection" in 1.59.0), with the name pre-filled as `{export title, or the folder name} · {YYYY-MM-DD HH:MM}` in local time, e.g. `Birgit’s papers · 2026-11-07 14:32`. The name stays editable, and "No collection" and "An existing collection" are one click away. Only the files listed in `index.csv` join (added documents and the existing documents behind skipped duplicates); files without a row go to the Inbox and are not added. No collection is created when nothing qualifies. The existing name-taken rule applies to the pre-filled name (the minute in the name makes a clash unlikely; if it happens the note shows and the person edits the name).

## Code changes

- `askImportCollection()`: default choice `new`, name via a small helper `importCollectionDefaultName(about, folderName, now)`; the existing radio/validation logic is unchanged.

- `openExportModal()`: the fields, the disabled logic, reading them at start, writing the file after `index.csv`.
- New `readExportDetails(dirHandle)`-style helper used by the import (returns `{title, description}` or `null`), `cleanLibraryText()` reused.
- `openImportModal()`: skip the details file in the scan, read it, pass it to `askImportCollection()` which renders the block and the collection-name prefill.
- New strings (7 languages, Armenian unreviewed): `exportTitleLabel` ("Title (optional)"), `exportDescriptionLabel` ("Description (optional)"), `exportDetailsFileHint`, `importAboutExport` ("About this export").
- Version: the next number after the library-details release (1.61.0 if that was 1.60.0), README (+ German), architecture note 08 (Export selected documents, Import a folder), AGENTS.md, tests index.

## Known cost

An older Dossiary version importing a folder made by this version has no idea about `export-details.json` and adds it to the Inbox as a document (of type "other file"). The person can delete it. This only affects older versions of the page.

## Tests

New `tests/test_export_details.py` (Playwright, stubs as in `test_import_folder.py` / `test_library_details.py`):
1. The export dialog starts with the library's title and description; with none set the fields are empty.
2. Export with edited texts writes `export-details.json` with the cleaned values and `format: 1`; the library's own settings are unchanged.
3. Both texts empty: no file. "Include index.csv" unchecked: fields disabled, no file. An existing `index.csv` in the destination (so the new one is numbered): no file.
4. Import of that folder: the panel shows "About this export", the title and the description; HTML in them is shown as text; `export-details.json` is not added as a document (document count is the exported files only).
5. A folder with `index.csv` but no details file, one with a malformed file, one with a file whose texts are empty: no block, import works as before.
6. A folder with a details file but no `index.csv`: imports at once, the details file is not imported as a document.
7. "A new collection" pre-fills with the export title; without a title with the folder name.
8. A title over 60 characters in a hand-made file is cut at display.

`test_import_folder.py`, `test_import_collection.py`, the export tests and `test_i18n_coverage.py` keep passing.

## Out of scope

The Mac app and iPhone/iPad (no export or folder import there); "Export as library" (a different flow); a title for Share; storing the texts anywhere else.
