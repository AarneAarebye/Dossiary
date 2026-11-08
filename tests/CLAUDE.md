# tests/ — testing conventions and coverage

Guidance for Claude when working under this repo's `tests/` directory. Loads only when Claude touches files here — the parent repo's `../CLAUDE.md` covers everything else about Dossiary.

## How this was tested (useful context for future changes)

**Every printed check reads `True` on pass.** A `: False` in any script's
output is a regression, never an intended value -- a check that expects
something absent or hidden is phrased so (`"column hidden by default:",
not visible`), and a raw non-boolean value gets a comparison in front of
it. Sixteen scripts used to print `False` for expected outcomes ("(should
be False)" labels, raw `is_checked()` results), which made a full run
unreadable; they were all rewritten, so a full run now prints no `False`
at all. Keep it that way for new checks.

**Test coverage narrative.** The per-feature account of what the 114 scripts cover was one 95 KB paragraph here. It now lives in four parts under `tests/coverage/`, word for word and in the original order; the parts are not loaded automatically, so read the one for the area you are changing (search them for a script name such as `test_reminders.py`):

- [`coverage/01-capture-ocr-fields-inbox-nav.md`](coverage/01-capture-ocr-fields-inbox-nav.md): Capture, OCR, previews, custom fields, inbox, navigation and libraries (lines 16-446 of the old file).
- [`coverage/02-detail-reminders-bulk-duplicates.md`](coverage/02-detail-reminders-bulk-duplicates.md): Detail panel, reminders, bulk edit, duplicate detection and broken links (lines 447-765 of the old file).
- [`coverage/03-tools-export-share-reports-collections.md`](coverage/03-tools-export-share-reports-collections.md): Tools menu, export, sharing, reports, collections, autofill and calendar (lines 766-1090 of the old file).
- [`coverage/04-scan-devices-library-sync.md`](coverage/04-scan-devices-library-sync.md): Scan dialog, devices, deleting and sharing libraries, leases and page counts (lines 1091-1322 of the old file).
**The older scripts, by name.** The narrative (now in `coverage/`) grew feature by
feature and describes most of the early tests only by what they cover,
never by file name. This list maps each of them to what it checks:

- **Capture and edit basics**
  - `test_studio.py` -- the oldest test: opens a seeded library (rows,
    open-file button, image OCR) and adds a new document.
  - `test_studio2.py` -- a new library from an empty folder: the
    init-state screen, the first save, PDF OCR enabled with no stale "not
    available" note, and a plain PDF save getting a real
    `original_file_path` with `searchable_pdf_built` 0.
  - `test_edit.py` -- the Edit button, saving title/category/subcategory/
    people/tags, and the table row, panel and persisted rows
    (`documents`, `people`, `document_field_people`, `tags`) afterwards.
  - `test_edit_cancel.py` -- Cancel discards the edit: the panel and row
    keep the original title.
  - `test_subcategory.py` -- subcategory shown in the row, the panel and
    the sidecar, persisted, and found by search.
  - `test_date_preset.py` -- the capture date's "today" guess: amber
    styling and hint, both cleared on the first edit, the value saved; and
    "today" being the local day, not the UTC one (just after midnight in
    Berlin, in the evening in Los Angeles, via a fixed clock and timezone).
  - `test_date_picker_color_scheme.py` -- both date inputs have
    `color-scheme: dark`, so the picker icon is visible.
  - `test_extensionless_file.py` -- a file with no extension saves through
    both capture and Inbox, without its active copy colliding with the
    original's subfolder (`TypeMismatchError`).
  - `test_sidecar_and_search.py` -- the sidecar's content, OCR text found
    by search (and gibberish not), and the search box's clear button
    restoring the rows and focus.
  - `test_scan_hint_and_ocr_languages.py` -- the scan-hint toggle, and the
    OCR language options in both forms.
  - `test_scan_hint_os_detection.py` -- `detectOS()`/`scanHintHtml()`:
    Image Capture/Preview on macOS, Windows Scan on Windows, the generic
    text on Linux or with no OS signal.
- **Clear buttons**
  - `test_clear_button.py` -- clearing Document Type empties it, removes
    its dynamic fields and returns focus, in both forms.
  - `test_all_clear_buttons.py` -- every built-in field's clear button in
    both forms empties its input.
- **People and custom fields**
  - `test_people.py` -- People as a person-type field:
    `document_field_people` links, `document_people` left untouched, name
    pills in the row, the People filter.
  - `test_generic_fields.py` -- text/number/date/checkbox inputs, values
    in `document_field_values`, an `&` in a value never split, Yes/No and
    formatted dates in the panel, search over field values.
  - `test_dynamic_fields.py` -- which fields each document type shows, in
    `document_type_fields` order; none for no type or an unknown type;
    fields removed when switching type (by design).
  - `test_add_field_inline.py` -- "+ Add a custom field": hidden until a
    type is entered, the toggle, the Amount hint, built-in and duplicate
    names refused, the new field saved and attached to the type, and
    values already typed into other fields surviving the insert, in
    capture and Edit.
  - `test_field_settings.py` -- the Field Settings dialog: document
    types, available vs. displayed fields, adding a field to a type and
    persisting it.
  - `test_fields_from_form.py` -- "Set up fields for this type…" in both
    forms: Field Settings opening above the form with its type selected (a
    brand-new type too), Done/Escape/backdrop/✕ closing only that layer, the
    added fields appearing with typed values (title, field values, a ticked
    checkbox) kept, an orphaned field keeping its typed value, the new type's
    setup saved; the default-currency guess following a changed default
    while a typed currency stays; Escape in a rename cancelling only the
    rename; the Tools entry unchanged; the German label. Confirmed
    non-vacuous by disabling the restore step.
  - `test_remove_type_setup.py` -- Field Settings' "Remove field setup":
    shown only for a selected type no document uses that has fields, its
    texts; pressing it drops the type from the list at once, deselects it
    and deletes only its `document_type_fields` rows (other types, fields
    and values untouched); removing the last field of an unused type drops
    it the same way while a used type stays listed; a brand-new type typed
    into the capture form stays listed and selected with no fields, and its
    setup can be removed too. Confirmed non-vacuous by keeping the empty
    key on the last field's removal.
  - `test_field_autocomplete_default.py` -- the one-time migration
    switching autocomplete on for existing text fields (and its marker),
    new text fields defaulting to it, number fields not, and switching it
    off sticking.
  - `test_orphaned_fields.py` -- a value in a field no longer set up for
    the document's type shows in Edit with the orphaned hint, editable;
    capture never shows orphaned fields.
  - `test_orphaned_clear.py` -- clearing an orphaned field and saving
    removes its value.
- **Amount, Currency and Payment method**
  - `test_sentinel_field_migration.py` -- an old-shape library: the three
    `fields` rows created with the right flags, values backfilled from the
    old `documents` columns, and Currency added beside Amount in
    `document_type_fields`.
  - `test_amount_payment_dynamic.py` -- Amount and Payment method appear
    only for types set up with them.
  - `test_currency.py` -- Currency as its own per-type field, and the
    `default_currency` guess in capture (persisted, flagged, cleared).
  - `test_edit_currency_guess.py` -- the Edit-form Currency guess, only
    for a document with a real, non-zero Amount and no Currency.
  - `test_payment_date.py` -- a Payment Date custom field ordered among
    Payment method/Amount/Currency, saved, formatted in the panel, and
    pre-filled in Edit.
  - `test_header_amount_payment.py` -- the panel's Payment line and Amount
    label appear only when the document has them; Date always shows.
- **Table and columns**
  - `test_columns.py` -- Payment method's column and filter hidden by
    default, Category shown, and the Columns menu toggling both.
  - `test_columns_persist.py` -- column choices surviving a reopen.
  - `test_generic_column_system.py` -- any custom field (not just the
    seeded ones) opting into a column and autocomplete from Field
    Settings; Amount gets no Column checkbox, Currency does.
  - `test_import_collection.py` -- "Import a folder or earlier export": the
    new titles, and the collection step for a folder with an `index.csv`
    (the choice starting on "A new collection" named after the folder with
    date and time, made unique if taken; none, new or existing manual
    collection; only listed files; a skipped duplicate with a row added; no
    empty collection; failure kept in the summary).
  - `test_export_details.py` (adapted in 1.63.0: it reads the export's subfolder) -- the export dialog's Title and Description:
    prefilled from the library's own, the 60/300 limits and hint, both
    disabled with the index off (no details file), empty texts writing no
    `export-details.json`, edited texts cleaned and written as
    `{"format": 1, ...}` with the library's settings unchanged, a document
    named `index` numbered `index (2).csv` while the real `index.csv` keeps
    its name, a document named `export-details` numbered while the details
    file keeps its name, also with both texts empty; HTML special characters
    kept as text in the prefill and the file; a details file written when
    there are texts and none when both are empty; a round trip exporting
    documents named `index.csv` and `export-details.json` and importing the
    export folder, both coming back as documents with their details and no
    extra-index note, while an unlisted `index (3).csv` added to that folder
    is still skipped with the note; a failing write of the details file (read-only handle) still exporting the
    documents and `index.csv` with the done text plus the failure sentence; and the import side: a real export round-tripped showing
    "About this export" (title as text, not HTML), the new collection
    named after the title and holding exactly the exported files, a bad,
    non-string or empty details file ignored, a folder without `index.csv`
    importing at once with the json never a document, a description alone,
    the folder name as fallback, and over-long texts cut; no page errors.
  - `test_export_subfolders.py` -- one subfolder per export and importing
    several exports: an export creating `{title} · YYYY-MM-DD HH-MM` (or
    `Export …`) holding the files, `index.csv` and `export-details.json` while
    the picked folder holds only that subfolder, with its name in the done
    message; a same-minute clash numbered " (2)"; a failing subfolder
    creation showing the error and handing the dialog back; forbidden
    characters becoming `-`; index off giving files only; every file failing
    leaving no subfolder (message naming the picked folder);
    `sanitizeFolderName` / `exportSubfolderName` cases (long titles cut,
    empty after cleaning falls back to "Export"); a folder with `index.csv`
    plus `index (2).csv` and `export-details (2).json` importing as before,
    the extras not documents, the note shown; `classifyImportFolder` (single,
    plain, exports; hidden, index-less and unusable-index subfolders left out;
    file counts and details title); a parent with two exports (also two real
    exports made one after the other) listing both with title, description
    (as text) and file counts, ticked, a new collection per export with
    read-only names, one summary block each; unticking one, nothing ticked
    disabling Import; "No collection" and "One existing collection" applying
    to all ticked; top-level files of the parent ignored and a parent with no
    export subfolders imported as a plain folder; a document type new at the
    start counted as new in every export; a failing file and a failing export
    not stopping the next one (red status, dialog closable).
  - `test_library_details.py` -- Library details: the Tools entry and
    dialog (empty fields, folder-name hint, maxlength, Cancel/Escape); title
    and description saved in `settings` and shown in the header (description
    as tooltip); whitespace collapse, the 60/300 limits, a blank title
    falling back to the folder name; seeded details at open; no stale title
    after switching library; Recent libraries rows (title, description line,
    "{folder} · Last opened"); the pencil reconnecting once and then opening
    the dialog; a failed save changing nothing; a save updating the entry
    without touching `lastOpenedAt`; a denied reconnect or a non-library
    folder opening no dialog; the German Tools entry; the header name as a
    button (role, tabindex, `aria-haspopup`, pointer cursor) opening the
    dialog with the current values by click, Enter and Space, still a button
    after saving from it, and not reopening over an open dialog, over
    another dialog or during a long operation; the empty-state text with no
    button semantics, opening nothing by click or Enter, also after a
    language change. Confirmed non-vacuous by dropping each guard.
  - `test_import_date_column.py` -- the Imported column: visible by
    default, in the Columns menu, toggled off and on, showing a real date.
  - `test_sticky_header.py` -- with many rows, the table header stays at
    the top while scrolling and has an opaque background.
- **Archive and Inbox folder**
  - `test_archive.py` -- "Show archived" off by default, the count line,
    the archived pill, Archive/Unarchive, and a document from before the
    `archived` column reading as not archived.
  - `test_inbox_folder_creation.py` -- `inbox/` created for a new library
    and for an existing one that lacked it, with no banner for the empty
    folder.

**Running it**: `cd tests && python3 test_<name>.py` (each is a standalone
script, not a pytest suite — no test runner or config needed beyond
Python 3 and Playwright's Chromium). Ships with **zero real user data** —
every test seeds its own synthetic library state — deliberately, even
though a real Mariner-migrated `.paperless` library was used for ad-hoc
verification during development (e.g. confirming Payment Date's real
per-type configuration, or running an end-to-end migration through
`migrate_gui.py`/`migrate_web.py` in the sibling repo); that real data
was never checked into this suite and shouldn't be — see the `.gitignore`
entries for `tests/*.sqlite`/`tests/*.documentwalletsql` if a real fixture
ever gets added locally for similar ad-hoc checks.

Real `sql.js` and `Tesseract.js` can't be fetched in a fully offline/sandboxed
dev environment, and `showDirectoryPicker` requires a real native OS dialog
that can't be scripted. The approach used throughout:

- Stub `window.initSqlJs` with a small generic `FakeDatabase` class
  (`tests/stub_studio2.js` — shared by every test file; see the note
  below on why that matters) that parses/serializes its whole state as
  JSON (instead of real SQLite bytes) and implements just enough of
  `run()`/`exec()`/`export()` — via regex parsing of the actual SQL
  strings the app sends — to exercise real
  `INSERT`/`UPDATE`/`DELETE`/`SELECT ... WHERE` logic without a real
  SQLite engine. This needed real extending as the app grew past pure
  inserts: `run()` handles `UPDATE ... SET ... WHERE col = ?` and
  `DELETE FROM ... WHERE col = ?` (used by editing), and `INSERT OR
  REPLACE` semantics (used by settings) in addition to the original
  `INSERT OR IGNORE`; `exec()` handles a single `WHERE col = 'literal'`
  clause (used by the settings lookup). The Amount/Currency column-and-filter
  branch extended `run()`'s `UPDATE` handling further: a compound
  `WHERE col1 = ? AND col2 = ?` clause (checked before the pre-existing
  single-condition pattern, so it isn't accidentally matched by the
  looser one first), and literal (non-`?`) values inside the `SET`
  clause itself — e.g. `UPDATE fields SET show_as_column = 1,
  autocomplete = 1 WHERE name = ? AND type = ?`, which
  `migrateCurrencyColumnDefault()` sends as a literal-valued backfill
  rather than binding `1`/`1` as params. If a future change sends the app's
  first `UPDATE`/`DELETE`/`SELECT` with a shape the stub doesn't recognize
  yet, extend the stub's regex matching rather than working around it —
  the whole point is exercising the app's real SQL strings. The field-
  descriptions branch registered a new `field_descriptions` table in the
  `FakeDatabase`'s table lists (both the seeded-load and empty-init paths),
  and gave it the same `INSERT OR REPLACE` dedupe treatment `settings`
  already had — real `field_descriptions.field_name` is a `TEXT PRIMARY
  KEY`, so without a matching dedupe branch in the stub, saving two
  different descriptions for the same field name would leave both rows in
  the fake table instead of replacing the first, silently diverging from
  the real schema's own uniqueness guarantee.
- Stub `window.showDirectoryPicker` and the `FileSystemDirectoryHandle` /
  `FileSystemFileHandle` interfaces with an in-memory `Map`-based fake
  filesystem, so `getFileHandle`/`getDirectoryHandle`/`createWritable`/
  `getFile` behave like the real API's contract (including throwing
  `NotFoundError` when a file doesn't exist and `create` wasn't passed).
- Stub `window.Tesseract.createWorker`/`recognize`/`terminate` to return
  canned text and a realistic word/bbox tree (mimicking the `{blocks: true}`
  output shape) instead of running real OCR.
- Stub `window.jspdf.jsPDF` with a fake class that records every
  constructor option, `addImage`/`setFontSize`/`text` call, and `output()`
  invocation, so the searchable-PDF code path's *logic* (correct
  coordinates, correct options, correct call sequencing) can be verified
  without a real PDF renderer.
- Stub `window.pdfjsLib` similarly, for the PDF-page-rendering path used
  by both thumbnail generation and edit-time OCR on PDFs.
- Drive the actual UI with Playwright — real clicks, real form fills, real
  assertions against rendered DOM state and the persisted (fake) database
  bytes after save, not just unit-testing isolated functions.

This validates the app's own logic thoroughly but does **not** validate
that real `sql.js`/`Tesseract.js`/the real browser dialog behave exactly as
assumed — that still needs an actual browser test after nontrivial changes,
same as the sibling repo's live viewer. This is especially true for the
searchable-PDF feature: the stub confirms jsPDF is *called* correctly, but
not that the resulting PDF actually renders with correctly positioned,
selectable text in a real PDF viewer — verify that visually after any
change to `buildSearchablePdf()`.

**Every test file must use `tests/stub_studio2.js`, never its own
embedded copy.** This bit twice, for real, not hypothetically: two
different test files independently accumulated their own increasingly
stale embedded/misnamed stub (one had a fully duplicated, outdated
`FakeDatabase`; another just pointed at a leftover file with an
almost-but-not-quite-right name), and both silently kept "passing" while
testing against weaker, out-of-date behavior instead of the app's actual
current requirements. If you create a new test file, copy the
`stub_studio2.js`-loading boilerplate from an existing one rather than
writing new stub-loading code from scratch, and if you ever see a test
reading anything other than `stub_studio2.js`, that's a bug to fix, not a
one-off worth leaving alone.

**A second, newer cross-cutting convention exists alongside that one:
`_write_patched_app_with_preview_enabled()`, currently hand-duplicated
identically across three files rather than factored into a shared module.**
`SHOW_DOCUMENT_PREVIEW` (see that flag's own note in the parent repo's
`../CLAUDE.md`) defaults to hiding the persistent detail panel's thumbnail
slot and its Generate/Regenerate button, so `test_thumbnails.py`,
`test_regenerate.py`, and `test_detail_panel.py` each need a way to keep
exercising the real, underlying preview pipeline — thumbnail generation and
regeneration, and every panel/context-menu action that touches it — at full
strength, rather than only ever seeing it hidden; none of the three exist
to test the toggle's own default behavior itself, that's
`test_thumbnails.py`'s own Scenario 3 job alone, run against the real,
unpatched app. Each of the three files carries its own copy of the helper —
identical in what it does, differing only in each file's own docstring
explaining why that particular file needs it: it reads `dossiary.html`,
replaces the literal `const SHOW_DOCUMENT_PREVIEW = false;` with `= true;`,
writes the patched HTML to a temp file next to `dossiary.html`
(`tempfile.mkstemp(..., dir=...)`, so relative asset paths still resolve
the same way they did against the real file), and returns that path for the
test to `page.goto()` instead of `APP_PATH` — the caller is responsible for
`os.remove()`-ing it once done. This suite has no shared Python helper
module — every test file here is a fully standalone script, the same
situation the `stub_studio2.js` note above exists to address on the
JS-stub side — so, like that note's own guidance, if you ever add a fourth
test file that needs this same technique, copy
`_write_patched_app_with_preview_enabled()` verbatim from one of these
three rather than writing a new one from scratch.
Stable uids (`test_stable_uids.py`): `__DEBUG_derivedUid()` against Python's
`uuid.uuid5` in the same namespace (so the JavaScript UUID v5 is pinned to the
standard); an old seeded library with rows in all eight uid tables and no uid
getting every derived value, built-in fields added on open included, and the
`stable_uids_migrated` marker; two fresh copies of one seed agreeing; a reopen
changing nothing and restoring a cleared uid to the same value; a new library
running it too. Every creation path is covered by one generic check at the
end of the tests that run it (`test_studio.py`, `test_edit.py`,
`test_add_field_inline.py`, `test_person_type_field.py`, `test_splits.py`,
`test_drag_drop.py`, `test_inbox.py`, `test_import_folder.py`,
`test_page_tools.py`, `test_collections.py`, `test_collection_folders.py`,
`test_smart_collections.py`, `test_reminders.py`): every row in the eight
tables has a uid, which a path inserting without one fails (confirmed by
dropping the tag INSERT's uid); `test_studio.py` also checks the captured
document and its new tag are v4. `test_export_library.py` checks exported
documents, tags, people and fields keep their uids, `test_copy_setup.py` a
copied field's, and `test_import_folder.py` that imported documents get new
v4 ones. `test_splits.py` needs the git-ignored `tiny.pdf` fixture,
which a fresh worktree lacks -- copy it from the main checkout.
