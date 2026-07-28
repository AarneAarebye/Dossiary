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
  the library, with category/type filters
- **Capture** — add a new document (PDF or image), with client-side OCR
  (German, English, or both) via [Tesseract.js](https://github.com/naptha/tesseract.js)
  running entirely in your browser
- **Tag & organize** — category, document type, payment method, amount,
  date, notes, and free-form tags per document
- **Open originals** — one click to open the actual file from disk

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
    document_type       TEXT
    payment_method      TEXT     -- nullable, only meaningful for receipts/invoices
    amount              REAL     -- nullable
    date                TEXT     -- ISO 8601
    notes               TEXT
    ocr_text            TEXT
    ocr_language        TEXT     -- 'deu' / 'eng' / 'eng+deu' / NULL
    file_path           TEXT     -- relative to library root, e.g. "files/3_invoice.pdf"
    original_file_path  TEXT     -- relative to library root, nullable
    created_at          TEXT     -- ISO 8601, when the record was created
    source              TEXT     -- 'migrated' or 'captured'
    source_legacy_id    INTEGER  -- traceability only, for migrated documents

tags
    id    INTEGER PRIMARY KEY
    name  TEXT UNIQUE

document_tags
    document_id  INTEGER
    tag_id       INTEGER
    PRIMARY KEY (document_id, tag_id)
```

## Limitations

- **Re-select the folder each session.** Browsers don't allow persisting
  direct file-system access across page reloads, so you'll pick the folder
  again each time you open the app. This is a browser constraint, not
  something Document Studio can work around.
- **OCR works on images, not PDFs.** Tesseract.js recognizes images
  directly; OCR-ing a PDF would require first rendering it to an image
  client-side, which isn't implemented yet. PDFs can still be captured —
  just add notes manually instead of relying on OCR.
- **No thumbnails yet** for newly captured documents.
- **Requires Chrome or Edge.** Safari and Firefox don't support the write
  side of the File System Access API as of writing.
- **Needs network on first load** (to fetch the sql.js and Tesseract.js
  WebAssembly bundles from their CDNs) even though your documents never
  leave your machine.

## License

MIT — see [LICENSE](LICENSE).
