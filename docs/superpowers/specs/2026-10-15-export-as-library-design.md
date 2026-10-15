# Export as library

Date: 2026-10-15

## Goal

Turn the selected documents into a new, ready-to-open `<Name>.dossiary`
library: to hand documents to someone (copy) or to split a library in two
(move). It fills the gap between the features that exist today: Back up
library copies everything, Export copies files plus an `index.csv` (which
Import a folder can read back), and "Copy the setup of" copies setup without
documents.

## Entry point

"Export as library…" (`#bulk-export-library-btn`) in the bulk-action bar's
More ▾ menu, next to Export… and Share…, acting on the checked documents.
Hidden in the Waste bin, like the rest of that menu. A whole collection or
search result is exported by opening it and ticking select-all.

## Dialog (`openExportLibraryModal(ids)`)

- **Name**: default "<this library's name> (export)", with the live folder
  preview, validation and `.dossiary` handling of the new-library form
  (`libraryFolderName()`; names with `/ \ : * ? " < > |` or a leading dot
  refused; a name already ending in `.dossiary` isn't doubled).
- **Location**: chosen when **Export library** is clicked
  (`showDirectoryPicker({mode: 'readwrite'})`), as in Export and Back up
  library; the hint under the name says the folder is created in the folder
  chosen next. The library itself or a folder inside it is refused
  (`isInsideLibrary()`). An existing folder of the chosen name is never
  reused; the dialog says so and asks for another name.
- **Documents**: Copy (default) / Move. Move's note: "The documents go to the
  Waste bin here once the new library has been written. Restoring them from
  the Waste bin undoes it."
- **Setup**: "Only what these documents use" (default) / "Everything from
  this library".
- A line with the document count and their files' total size (from
  `File.size` of the active files and originals, read when the dialog
  opens; a file that can't be read isn't counted).
- When any selected document has a pending background-OCR row
  (`isOcrPendingDoc()`): "N documents are still being made searchable; they
  are exported as they are now."
- **Export library** starts it; progress "N of M documents"; **Stop**. While
  it runs, Escape, backdrop and close are blocked, as in Back up library.

When done: a summary (exported, left out because a file couldn't be read --
each listed with its reason via `fileErrorText()`, moved to the Waste bin
when Move), the new folder's name, an **Open it** button (switches to the
new library through the same path as a recent library), and the new
library is recorded in Recent libraries (`recordRecentLibrary()`).

## What the new library contains

The new database is a separate in-memory sql.js database created with
`SCHEMA`; the open library stays open and is only read until a Move's last
step.

**Documents**: every exported document's `documents` row with all its
columns, **keeping its id**, so every stored path (`files/<id>_…`,
`thumbnails/<id>.jpg`) is valid unchanged in the new folder. Status columns
(needs_review, archived, searchable flags, `file_hash`, `thumbnail_hd`) are
kept as they are. Deleted documents can't be selected, so none are
exported.

**Per-document data**, limited to the exported ids: `document_field_values`,
`document_field_people` and the `people` rows they use, `document_tags` and
the `tags` rows they use, `document_splits`, `reminder_snoozes`. Ids are
kept.

**Collections**: manual collections holding at least one exported document,
with only those documents in `collection_documents`; collection folders that
hold an exported collection.

**Setup, "only what these documents use"** (default):
- `fields` that hold a value (or person) on an exported document, plus the
  built-in fields the migrations would recreate anyway (People, Amount,
  Currency, Payment method, Reminder);
- `document_type_fields` rows for the document types of exported documents,
  limited to the copied fields;
- `field_descriptions` for the copied fields and the built-in names
  (Category, Subcategory, Document Type, Date, Tags);
- `settings`, except the ones listed below;
- no Smart Collections.

**Setup, "everything"**: what "Copy the setup of" copies today
(`copySetupFrom()`, generalized to take a target database): all fields,
document type fields, field descriptions, Smart Collections with their
folders, and `settings` except the ones listed below.

**Never copied**: the settings `last_backup_at`, `scan_bridge_url` and
`scan_last_settings` (this library's history and this computer's scanner);
`not_duplicate_groups` (judgements about this library); `ocr_jobs`
(pending background OCR belongs to this library's runner). Field ids in
`visible_columns`/`sort_key` that point at a field not copied are harmless:
`loadColumnSettings()` drops unknown ids and `loadSortState()` falls back.

**Files**, for each exported document: `file_path`, `original_file_path`
and `thumbnail_path` copied to the same relative paths; the sidecar `.txt`
written fresh from the document's in-memory state (`buildSidecarText()`),
next to the active file. An empty `inbox/` is created, as for any new
library.

## Order and safety

1. Create `<Name>.dossiary` in the chosen folder.
2. Copy files, 4 documents at a time (iCloud downloads overlap, as in
   Back up library). A document whose active file or original can't be read
   is left out entirely and listed; a missing preview or sidecar write is
   ignored (best-effort, as everywhere else).
3. Build the database from the documents that made it, then write
   `library.sqlite` -- last, so a folder without it never looks like a
   finished library.
   If no document could be read, no library is made (the folder is
   removed) and the dialog says so.
4. Stop, or any failure before step 3 completes, removes the new folder
   (`removeEntry(..., {recursive: true})`, as Back up library does). The open
   library is untouched up to here.
5. Move only, after step 3 succeeded: the exported documents (not the ones
   left out) go to the Waste bin with one `persistDb()`, the same way bulk
   Delete does (`bulkSetDeleted()`). Their files stay in place. If that save
   fails, their Waste-bin flag is undone in memory and the summary says so:
   the new library is complete, and the documents are still in this library
   too.

Nothing is ever deleted from this library's folder.

## Testing

`tests/test_export_library.py`, Playwright with the shared stub, in the
style of `test_backup.py`/`test_export.py`:
- Copy, "only what's used": the new folder has `library.sqlite`, the files,
  originals, previews and sidecars at the same paths; its documents keep ids
  and details, tags, people, custom values and splits; only used fields and
  their type setup; a manual collection with only the exported documents;
  no Smart Collections; scanner settings and `last_backup_at` absent; the
  source library is unchanged.
- Copy, "everything": all fields and Smart Collections present.
- Move: the exported documents are in the source's Waste bin, their files
  still on disk.
- A document with a missing file is left out and listed; with Move it stays
  out of the Waste bin.
- Stop removes the new folder; refusing the library's own folder; an
  existing folder name is refused.
- The new library opens (its `library.sqlite` loaded through the normal
  open path) and shows the exported documents.
- Strings in all six languages (`test_i18n_coverage.py`).

## Out of scope

- Exporting from the detail panel for a single document (select it and use
  the bulk menu).
- Re-numbering documents in the new library.
- Merging an exported library into another existing library (Import a
  folder covers files plus details).
