# CLAUDE.md

Guidance for Claude (or Claude Code) when working in this repository.

## What this project is

A single-file, local-first, browser-based document archive app
(`document_studio.html`). No server, no backend, no build step, no
third-party install — open the file in Chrome or Edge and it reads/writes a
folder you choose directly, via the File System Access API. Data lives in a
SQLite database (`library.sqlite`, read/written via sql.js — SQLite compiled
to WebAssembly) plus a `files/` folder, both inside the library folder the
person picks.

This project is a spinoff of
[`MarinerPaperlessExporter`](https://github.com/AarneAarebye/MarinerPaperlessExporter):
that repo's `migrate_to_new_library.py` produces the `library.sqlite` schema
this app expects, as a one-time conversion from a discontinued Mariner
Paperless library. But this app itself has no Mariner-specific logic or
dependency — don't reintroduce Core Data / `.paperless` package assumptions
here. If a change would only make sense for Mariner-migrated data, it
probably belongs in the other repo instead.

## Repository layout

```
document_studio.html   The entire app (single file: HTML + CSS + JS)
README.md               Usage docs, schema, and known limitations
LICENSE                 MIT
.gitignore              Excludes personal library data from commits
```

There's intentionally no `package.json`, bundler, or build step. Keep it
that way — the whole point is "download one file, open it, it works."
External libraries (sql.js, Tesseract.js) are loaded from CDN at runtime via
`<script src>`, not vendored or bundled.

## Architecture notes

- **File System Access API** (`showDirectoryPicker({mode: 'readwrite'})`)
  gives a `FileSystemDirectoryHandle` for the chosen library folder. This
  only works in a real top-level page — it's blocked inside cross-origin
  iframes (e.g. an embedded chat preview pane), which is why the README
  explicitly tells people to open the file directly rather than view it in
  an embedded frame. Don't "fix" a report of this failing by changing app
  code; it's a browser security restriction, not a bug, and the fix is
  "open the file outside the iframe."
- **sql.js** is used with two calling conventions, kept consistent
  throughout: `db.exec(sql)` for parameter-free `SELECT ... FROM <table>`
  reads (no `WHERE` clauses are used anywhere — the whole table is read
  into JS and filtered/sorted client-side), and `db.run(sql, params)` with
  `?` placeholders for all `INSERT`s. Don't introduce `db.prepare()`/bind
  patterns or parameterized `SELECT`s without a reason; the simpler
  convention has been deliberately kept uniform.
- **IDs are assigned in JS, not via `AUTOINCREMENT`/`last_insert_rowid()`.**
  `nextDocId`/`nextTagId` counters are initialized from `MAX(id)+1` when a
  library is opened, then incremented locally on each insert, and the
  explicit id is passed into the `INSERT` statement. This mirrors
  `migrate_to_new_library.py`'s approach in the sibling repo — keep both
  consistent if either changes, since a person could reasonably use both
  tools against the same library lineage.
- **Tag deduplication** happens via an in-memory `tagNameToId` map built at
  load time and updated on every new tag insert — not a `SELECT ... WHERE
  name = ?` round-trip per tag. This assumes single-writer, single-tab
  usage (true for this app's design); don't add multi-tab sync assumptions
  without addressing that this map can go stale across tabs.
- **OCR (Tesseract.js) only runs on images, not PDFs.** Recognizing a PDF
  would require rendering its first page to a canvas client-side (e.g. via
  pdf.js) before handing it to Tesseract — not implemented. The UI disables
  the OCR button and explains this for PDF uploads; don't silently attempt
  OCR on a PDF file object, it will not work as expected.
- **No persistence of the folder handle across page reloads.** A person
  re-selects the library folder every session. This is a deliberate,
  accepted limitation (see README), not something to silently work around
  with `localStorage`/`indexedDB` — browser storage APIs beyond what the
  File System Access API itself provides are out of scope here.

## How this was tested (useful context for future changes)

Real `sql.js` and `Tesseract.js` can't be fetched in a fully offline/sandboxed
dev environment, and `showDirectoryPicker` requires a real native OS dialog
that can't be scripted. The approach used during development:

- Stub `window.initSqlJs` with a small generic `FakeDatabase` class that
  parses/serializes its whole state as JSON (instead of real SQLite bytes)
  and implements just enough of `run()`/`exec()`/`export()` — via regex
  parsing of the actual SQL strings the app sends — to exercise real INSERT
  and SELECT logic without a real SQLite engine.
- Stub `window.showDirectoryPicker` and the `FileSystemDirectoryHandle` /
  `FileSystemFileHandle` interfaces with an in-memory `Map`-based fake
  filesystem, so `getFileHandle`/`getDirectoryHandle`/`createWritable`/
  `getFile` behave like the real API's contract (including throwing
  `NotFoundError` when a file doesn't exist and `create` wasn't passed).
- Stub `window.Tesseract.createWorker`/`recognize`/`terminate` to return
  canned text instead of running real OCR.
- Drive the UI with Playwright: open a seeded "migrated" library, add a new
  document (verifying OCR-button gating for images vs. PDFs, tag reuse vs.
  creation, and the persisted `library.sqlite` bytes after save), and
  initialize a brand-new empty library from scratch.

This validates the app's own logic thoroughly but does **not** validate
that real `sql.js`/`Tesseract.js`/the real browser dialog behave exactly as
assumed — that still needs an actual browser test after nontrivial changes,
same as the sibling repo's live viewer.

## Working conventions

- This app touches other people's personal documents (financial, medical,
  identity documents, etc.). Every file operation should be either an
  explicit read of something the person picked, or an explicit write they
  triggered (e.g. "Save document") — never anything automatic, silent, or
  triggered by data from outside the person's own input.
- Keep the single-file structure. If this grows enough to want separate
  files, that's worth discussing first — it changes the "just open the
  file" promise this app is built around.
- Preserve the visual language (dark "ink" background, phosphor-green
  accents, amber for capture/new-document actions) for consistency with the
  sibling repo's `document_archive.html`, since people may use both.
