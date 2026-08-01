# Document Studio

A local-first, browser-based document archive: capture, OCR, tag, and browse
your own documents — no server, no account, no upload. Everything lives in
one SQLite database and a folder of files on your own disk, opened and
written directly by the browser.

## Why

Most document-management tools want your files in their cloud. Document
Studio is the opposite: it's a single HTML file that reads and writes a
folder you choose, using the browser's
[File System Access API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API)
and [sql.js](https://github.com/sql-js/sql.js) (SQLite compiled to
WebAssembly) — nothing is ever uploaded anywhere. Point it at a folder,
and that folder *is* your archive.

It also has no native-code dependency of any kind, so it runs identically on
Apple Silicon or Intel, macOS/Windows/Linux — anywhere a modern Chromium
browser runs — indefinitely, with no risk of the "Intel-only app stops
working" problem that motivated this project in the first place.

## Features

- **Browse** — sortable, searchable, filterable list of every document in
  the library, with category/type filters. Search matches title, category,
  document type, notes, tags, and OCR text.
- **Capture** — add a new document (PDF or image), with client-side OCR
  (German, English, or both) via [Tesseract.js](https://github.com/naptha/tesseract.js)
  running entirely in your browser. For JPEG/PNG images, this also builds a
  **searchable PDF** — the image with an invisible, selectable text layer
  positioned over each recognized word (the same "sandwich" technique tools
  like `ocrmypdf` use) — while the original image is preserved untouched in
  a subfolder next to it, mirroring how Mariner Paperless itself laid out
  processed vs. original files.
- **Spotlight/Finder search** — every captured document also gets a plain
  `.txt` sidecar file (title, category, tags, notes, OCR text, custom
  field values) written next to it, so macOS's built-in file search can
  find documents by fields that otherwise only live inside
  `library.sqlite`. This isn't a real Spotlight *integration* (not
  possible from a browser — see Limitations below); it's just an ordinary
  text file that happens to get indexed like any other.
- **Custom fields, fully generic** — text, number, date, and checkbox
  fields (Organization, Year, Date From, Paid, Reimbursable — whatever
  your library uses) are all modeled the same way, backfilled from
  Mariner's own field definitions and values. Not a fixed set of
  hardcoded fields.
- **Tag & organize** — category, subcategory, document type, payment
  method, amount, date, notes, people, custom fields, and free-form tags
  per document — a document can relate to more than one person, filterable
  the same way tags are
- **Open originals** — one click to open the actual file from disk
- **Edit** — click any document, then "Edit" to update its metadata (title,
  category, subcategory, type, payment method, amount, date, people, tags,
  custom field values, notes, OCR text) after the fact. This only ever
  changes `library.sqlite` — the underlying file on disk is never touched
  or replaced.
- **Configurable columns & filters** — the "⚙ Columns" button in the
  toolbar lets you show/hide table columns (Category, Type, Payment method,
  People, Date, Imported, Amount, Tags); each one that supports filtering
  shows or hides its matching filter dropdown at the same time. The choice
  is saved in `library.sqlite` itself, so it travels with the library
  folder rather than being tied to one browser or device. (Custom fields
  as table columns/filters is planned but not built yet — see Limitations.)
- **Document previews** — every document can show a small preview image in
  its detail view. Migrated documents get Mariner's own thumbnail, copied
  over directly by `migrate_to_new_library.py`. Newly captured documents
  get one generated automatically (an image gets downscaled directly; a
  PDF gets its first page rendered via [pdf.js](https://mozilla.github.io/pdf.js/)).
  A "Generate preview" / "Regenerate preview" button in the detail view
  lets you create one on demand for any document that's missing one, or
  refresh an existing one.
- **Dynamic fields per document type** — capture/edit forms only show the
  custom fields (and People) actually configured for whatever document
  type you've picked, in the configured order, mirroring how Mariner
  Paperless itself decided which fields to display per type. An
  unconfigured document type (a brand new type, or a library where this
  wasn't tracked) shows none of its custom fields at all — matching
  Mariner's own behavior, where fields have to be explicitly assigned to
  a type before they show up.
- **Date defaults to today when capturing** — since that's right for a
  freshly-received document but wrong for a backlog of older mail, it's
  visually flagged (amber-tinted, with a "double-check this" note) until
  you actually touch the field, so an unreviewed guess doesn't quietly
  pass for a real value.

## Getting started

1. Open `document_studio.html` directly in **Chrome or Edge** (double-click
   it, or drag it into a browser window — don't use an embedded preview
   pane; folder write access requires a real top-level page).
2. Click **"Open library folder"** and choose a folder. If it's empty,
   you'll be offered to initialize a new library there. If it already has a
   `library.sqlite` (e.g. from a migration — see below), it opens straight
   into your existing documents.
3. Click **"＋ Add document"** to capture something new.

### Migrating from Mariner Paperless

If you're coming from the discontinued Mariner Paperless app, use
[`migrate_to_new_library.py`](https://github.com/AarneAarebye/MarinerPaperlessExporter)
first — it's a one-time conversion script that reads a `.paperless` library
and produces a `library.sqlite` + `files/` folder in the schema Document
Studio expects. Point Document Studio at that output folder afterward.

## Database schema

```
documents
    id                  INTEGER PRIMARY KEY
    title               TEXT
    category            TEXT
    subcategory         TEXT     -- independent of category, NOT a child of it (see note below)
    document_type       TEXT
    payment_method      TEXT     -- nullable, only meaningful for receipts/invoices
    amount              REAL     -- nullable
    date                TEXT     -- ISO 8601, the document's own date (e.g. invoice date)
    import_date         TEXT     -- ISO 8601, when the document was scanned/captured/imported
                                  -- (for migrated documents, this comes from Mariner's own
                                  -- import date; for captured documents, it equals created_at)
    notes               TEXT
    ocr_text            TEXT
    ocr_language        TEXT     -- 'deu' / 'eng' / 'eng+deu' / NULL
    file_path           TEXT     -- relative to library root, e.g. "files/3_invoice.pdf"
    original_file_path  TEXT     -- relative to library root, nullable
    created_at          TEXT     -- ISO 8601, when the record was created
    source              TEXT     -- 'migrated' or 'captured'
    source_legacy_id    INTEGER  -- traceability only, for migrated documents
    thumbnail_path      TEXT     -- relative to library root, nullable

tags
    id    INTEGER PRIMARY KEY
    name  TEXT UNIQUE

document_tags
    document_id  INTEGER
    tag_id       INTEGER
    PRIMARY KEY (document_id, tag_id)

people
    id    INTEGER PRIMARY KEY
    name  TEXT UNIQUE

document_people
    document_id  INTEGER
    person_id    INTEGER
    PRIMARY KEY (document_id, person_id)

settings
    key    TEXT PRIMARY KEY
    value  TEXT

fields
    id    INTEGER PRIMARY KEY
    name  TEXT UNIQUE
    type  TEXT      -- 'text', 'number', 'date', or 'checkbox'

document_field_values
    document_id  INTEGER
    field_id     INTEGER
    value        TEXT     -- always stored as text; interpreted per fields.type when read
    PRIMARY KEY (document_id, field_id)

document_type_fields
    document_type  TEXT
    field_name     TEXT      -- a name from `fields`, OR the literal 'People' as a sentinel
                              -- for the special multi-valued people/document_people system
    position       INTEGER   -- display order within this document type
    PRIMARY KEY (document_type, field_name)
```

`settings` is a small key-value table for app preferences that should
travel with the library rather than live in browser storage — currently
just `visible_columns` (a JSON array of which table columns and their
matching filters are shown).

**Custom fields are fully generic** (`fields` + `document_field_values`) —
Organization, Year, Date From, Paid, whatever your library actually uses.
Each field has a type (`text`/`number`/`date`/`checkbox`) that determines
how it's rendered and how its stored (always-text) value gets interpreted.
Populated by `migrate_to_new_library.py` from Mariner's own field
definitions and real values; Document Studio reads and writes this table
as documents are captured/edited, but doesn't yet have a UI for *defining*
new fields itself — see Limitations.

`document_type_fields` drives the capture/edit forms' dynamic field
behavior (see "Dynamic fields per document type" above): for a document
type present in this table, only the listed fields — plus People, via the
`'People'` sentinel — show, in the given order. A type absent from this
table shows **none** of its custom fields at all, matching Mariner's own
behavior (fields must be explicitly assigned to a type before they
display). Populated by `migrate_to_new_library.py`, which decodes
Mariner's own per-type display-field configuration.

"People" works exactly like tags: a document can relate to more than one
person (a joint bill, a shared appointment, etc.), so it's a many-to-many
relationship, not a single field. For migrated documents, this is backfilled
from Mariner's "Person" custom field — which sometimes held multiple names
joined with "&" (e.g. "Arne & Jana") — split into individual people so that
filtering by one name finds every document they're part of, not just ones
where they're the *only* name.

`subcategory` is despite its name **not** nested under `category` — that's
how Mariner's own schema worked (no foreign key between the two tables),
and it holds in the data too: the same subcategory name shows up under
different categories on different documents (e.g. "Dentist" appears under
both "Medical" and "Health"). It's carried over as-is: a second, independent
classification field.

Unlike People, **most custom fields are plain values, not split on "&".**
Person is genuinely multi-valued in practice ("Arne & Jana" means two
people); most other fields aren't — a real "Organization" value can
legitimately contain "&" as part of one name (e.g. "Dres. Ernestus & Cop,
Sandhausen", a German medical practice partnership; "Stadtwerke Walldorf
GmbH & Co. KG"), and splitting on it would corrupt the name rather than
separate genuinely distinct values.

## Limitations

- **No real Spotlight/Core Spotlight integration.** A browser-based app has
  no access to `CSSearchableIndex` or the ability to register a Spotlight
  importer — both require native code installed at the system level. The
  `.txt` sidecar files get *incidental* Spotlight benefit (since Spotlight
  indexes any plain text file's content), but this is a workaround, not a
  true integration, and it doesn't cover PDFs without a text layer.
- **Re-select the folder each session.** Browsers don't allow persisting
  direct file-system access across page reloads, so you'll pick the folder
  again each time you open the app. This is a browser constraint, not
  something Document Studio can work around.
- **OCR and searchable PDFs work on JPEG/PNG images, not PDF uploads.**
  Tesseract.js recognizes images directly; turning a PDF into a searchable
  PDF would require first rendering its pages to images client-side (e.g.
  via pdf.js), which isn't implemented yet. Uploading a PDF still works —
  it's just saved as-is, with any OCR text added manually to the notes
  field instead. Other image formats (WEBP, GIF, TIFF) are OCR'd for
  extracted text but not turned into a searchable PDF, since jsPDF's image
  embedding is only used here with JPEG/PNG.
- **Searchable PDF text positioning is best-effort.** Word bounding boxes
  come directly from Tesseract; horizontal stretching to exactly match each
  word's width isn't attempted (only position and approximate font size
  are), so the invisible text layer may not align pixel-for-pixel with the
  visible word underneath on close inspection — it should still select and
  search correctly.
- **Preview generation only covers images and PDFs.** Other file types
  (if you ever capture something else) won't get a preview — "Generate
  preview" will just report it can't handle that format.
- **No UI yet for managing document types, fields, or which fields show
  per type.** `fields` and `document_type_fields` are fully readable and
  writable by the app when capturing/editing documents, but there's no
  settings screen (yet) for *defining* a new field, renaming one, or
  changing which fields a document type shows — that all currently
  requires editing the database directly, or re-running the migration
  script. A settings screen mirroring this is planned.
- **Custom fields aren't table columns/filters yet.** They show correctly
  in the capture/edit forms and the detail view, but the main document
  list only has columns for the fixed fields (Category, Type, Payment
  method, People, Date, Amount, Tags) — not yet for arbitrary custom
  fields like Organization or Year. They are, however, included in search.
- **Requires Chrome or Edge.** Safari and Firefox don't support the write
  side of the File System Access API as of writing.
- **Needs network on first load** (to fetch the sql.js, Tesseract.js,
  jsPDF, and pdf.js WebAssembly/JS bundles from their CDNs) even though
  your documents never
  leave your machine.

## License

MIT — see [LICENSE](LICENSE).
