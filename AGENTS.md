# AGENTS.md

Guidance for coding agents (Claude Code and others) when working in this repository.

## What this project is

A single-file, local-first, browser-based document archive app
(`dossiary.html`). No server, no backend, no build step, no
third-party install — open the file in Chrome or Edge and it reads/writes a
folder you choose directly, via the File System Access API. Data lives in a
SQLite database (`library.sqlite`, read/written via sql.js — SQLite compiled
to WebAssembly) plus a `files/` folder, both inside the library folder the
person picks.

This project is a spinoff of
[`LibraryLifeboat`](https://github.com/AarneAarebye/LibraryLifeboat):
that repo's `migrate_to_new_library.py` produces the `library.sqlite` schema
this app expects, as a one-time conversion from a discontinued Mariner
Paperless library. But this app itself has no Mariner-specific logic or
dependency — don't reintroduce Core Data / `.paperless` package assumptions
here. If a change would only make sense for Mariner-migrated data, it
probably belongs in the other repo instead.

## Repository layout

```
dossiary.html            The entire app (single file: HTML + CSS + JS)
scan_watch.py            Standalone watched-folder helper -- see its own note below
packaging/macos/         Dossiary.app launcher (AppleScript) and its build
                          script, build-launcher.sh -- see the spec
                          docs/superpowers/specs/2026-10-15-applications-folder-layout-design.md
README.md                Usage docs, schema, and known limitations
README.de.md             German translation of README.md
USER_GUIDE.md            Non-technical beginner guide, linked from README.md
USER_GUIDE.de.md         German translation of USER_GUIDE.md
USER_GUIDE.es.md         Spanish translation of USER_GUIDE.md
USER_GUIDE.fr.md         French translation of USER_GUIDE.md
USER_GUIDE.zh-Hans.md    Simplified Chinese translation of USER_GUIDE.md
USER_GUIDE.zh-Hant.md    Traditional Chinese translation of USER_GUIDE.md,
                          derived from USER_GUIDE.zh-Hans.md via OpenCC
USER_GUIDE.hy.md         Armenian translation of USER_GUIDE.md
docs/user-guide/         Screenshots for each USER_GUIDE.<lang>.md, one
                          subfolder per language (en/, de/, es/, fr/,
                          zh-Hans/, zh-Hant/, hy/), plus capture.py and the
                          fabricated demo/ images it captures from -- see
                          that section's own note below
MIGRATION.md             Migrating from Mariner Paperless, linked from README.md
MIGRATION.de.md          German translation of MIGRATION.md
AGENTS.md                This file (tool-agnostic agent guidance)
CLAUDE.md                Imports AGENTS.md
CONTRIBUTING.md          Human-contributor guide (tests, conventions, PR expectations)
LICENSE                  MIT
.gitignore               Excludes personal library data from commits
tests/                   Playwright regression suite (109 scripts) + shared
                          browser-API stub — see "How this was tested" below
```

There's intentionally no `package.json`, bundler, or build step for the app
itself. Keep `dossiary.html` that way — the whole point is "download
one file, open it, it works." External libraries (sql.js, Tesseract.js) are
loaded from CDN at runtime via `<script src>`, not vendored or bundled.
`scan_watch.py` is the one deliberate exception to "single file" in this
repo: it's a separate, optional, stdlib-only companion script that never
gets loaded by the app and has no effect if you never run it — see its own
architecture note below for why it exists outside `dossiary.html`
rather than being folded into it.

## User Guide vs. README

`USER_GUIDE.md`/`USER_GUIDE.de.md` exist because `README.md`/`README.de.md`
are, deliberately, written for people who want to understand the
internals (schema, architecture, testing, known limitations) — not for
someone who just wants to start using the app. That's the right audience
for the README (a technical document for a technical project), but it
left no on-ramp for a non-technical first-time user, so the User Guide
was added as a separate, narrower document rather than trying to soften
the README's own tone in place. The two READMEs gained a one-line pointer
near the top rather than being restructured, so neither document's own
scope changed.

The User Guide's scope is deliberately narrow: a first-time user starting
from physical paper with no existing digital archive, covering the core
capture/find/Inbox loop plus a brief, screenshot-light tour of
Collections/Reports/Archive/custom fields — not a Mariner Paperless
migration guide (that stays `MIGRATION.md`'s job, linked from the User
Guide's own "Where to go next" section) and not a replacement for the
README's own feature-by-feature depth.

**Screenshots are static PNGs under `docs/user-guide/en/` and
`docs/user-guide/de/`, each guide showing its own language's UI** (the
German guide's screenshots show the German-toggled app, not reused
English images) — captured from a small, fabricated demo library (a
synthetic invoice, letter, and receipt, generated as plain images with no
real personal data) driven through the actual app via browser automation,
toggling Dossiary's own in-app language control between passes rather
than needing two separate app builds. `file://` pages can't be scripted
by the browser-automation tooling used to capture them (a security
boundary of the automation layer itself, not something particular to
this app), so capture was done by serving the repo directory over
`python3 -m http.server` and driving `http://localhost:<port>/dossiary.html`
instead — the File System Access API works identically over a `localhost`
origin, which counts as a secure context the same way `file://` does, so
this required no code changes to test against. The native
"choose a folder" picker can't be automated by design (same reasoning as
this file's own "no direct scanner integration" note — a browser
extension has no path to script a native OS dialog); a person had to
click through it once per capture session, after which everything else
was scripted. These screenshots are manually refreshed if the UI changes
meaningfully — same maintenance model as any other static doc image in
this repo, no visual-regression tooling involved.

**Practical notes from the v1.27 recapture (Claude in Chrome, all six
languages in one session)**, worth reusing next time: serve a scratch
folder holding a copy of `dossiary.html` *plus* the demo images on one
localhost origin, so in-page JavaScript can `fetch()` a demo image and
hand it to `#file-input` via `DataTransfer` (the browser tool can't drive
a native file chooser either); inject `translate="no"`/`<meta
name="google" content="notranslate">` after each page load, or Chrome's
own page translator kicks in once the page language changes and mangles
the UI (it rewrote "DOSSIERS" to "FILES" and the language menu's native
names); hide `.scanline` so the sweeping line doesn't cross controls;
blank `#status` for shots whose last status message doesn't retranslate;
and switch language via `#lang-select`'s `change` event between shots,
reopening any modal afterward, since the language switch is blocked while
a modal is open. **The English guide has 12 images, the six translated
guides 9, with their own numbering** (`02-table`, `03-capture-blank`, …,
`09-reports` — no empty-folder, library-ready, or collections images),
so a capture has to be saved under each guide's own filenames, not
English's.

**Since v1.37 the capture is a script: `docs/user-guide/capture.py`**
(Playwright for Python, headless, no browser extension and no person
clicking a picker). It serves the repo on `localhost:8833` (bound to
127.0.0.1 only: on all interfaces the macOS firewall silently dropped the
connections), blocks the scan-helper ports 8765/8766 so a scanix500
running on the machine can't change the toolbar in the shots, and replaces
only `showDirectoryPicker()`, which returns a `Documents` folder in the
origin-private file system (OPFS) -- a real `FileSystemDirectoryHandle`,
so the real app code runs unchanged against real sql.js, Tesseract.js and
pdf.js from the CDN. Each language gets a fresh browser context (its
`localStorage` language preset, a matching `locale` so date inputs format
the same way), creates "<My Documents>.dossiary" through the real
new-library form, adds Amount/Currency to the three demo types via
`__DEBUG_dbRun()` and reopens the library, captures the three fabricated
demo documents from `docs/user-guide/demo/` with real OCR, stages the
inbox scan by writing into OPFS, and saves every shot under that guide's
own filenames. `python3 docs/user-guide/capture.py all` rewrites all 66
images; pass `en,de` to limit languages, or an output folder to review
first. Bump `APP_VERSION` before capturing for a release, since the
footer shows it.

**This same per-language screenshot pattern extended to four more guides**
once Spanish, French, and both Chinese scripts joined English/German as UI
languages — `USER_GUIDE.es.md`, `USER_GUIDE.fr.md`, `USER_GUIDE.zh-Hans.md`,
and `USER_GUIDE.zh-Hant.md`, each showing its own language's UI under its
own `docs/user-guide/<lang>/` folder, captured the same server-and-toggle
way described above. The two Chinese guides in particular get fully
independent screenshot sets rather than sharing one — see the OpenCC-
derivation note under "UI language support" further below for why a
`zh-Hans` screenshot can't stand in for `zh-Hant`, or vice versa, the way
it safely could between, say, two regional variants of the same script.

**The footer's own "User Guide" link (`#user-guide-link`,
`updateUserGuideLink()`) resolves to a per-language file via a second,
deliberately separate array — `USER_GUIDE_LANGS`, currently `['de', 'es',
'fr', 'zh-Hans', 'zh-Hant', 'hy']`** — not `SUPPORTED_LANGS` itself.
`userGuideUrl()` appends `.${currentLang}` to the linked filename only
when `currentLang` is in `USER_GUIDE_LANGS`; otherwise the link points at
plain `USER_GUIDE.md` (English, suffix-less, matching the file-naming
convention every other translated doc in this repo already uses —
`README.de.md`, `MIGRATION.de.md`, etc.). The two arrays are kept
separate on purpose: `SUPPORTED_LANGS` is "languages the *app's UI* can
render in," `USER_GUIDE_LANGS` is "languages that additionally have their
*own guide file* to link to" — a UI language could in principle ship
before its guide does (or a guide could theoretically lag behind, if one
were ever retired or delayed), and the fallback exists specifically to
keep the footer link never broken in that gap, rather than assuming the
two lists always match. With all four new guides landing in the same
project that added their languages, there's no currently-live language
that actually falls into the fallback case today — but the fallback
branch is still real, exercised code (`tests/test_i18n.py`'s own coverage
of the footer link), not dead weight to prune, since a future language
added with its guide following in a later change would hit it again.

## Versioning

See the `cutting-a-release` skill (`.claude/skills/cutting-a-release/SKILL.md`)
for the version-sync convention between `dossiary.html`/`scan_watch.py` and
this repo's git tags.

## Architecture notes

The detailed notes (what each part does, why it was built that way, the traps found along the way) live in
`docs/architecture/`, one file per area. They are not loaded automatically: read the file for the area you are
about to change. Add a new note to the matching file, not here. The list under each file gives the notes in it.

### [`docs/architecture/01-page-basics.md`](docs/architecture/01-page-basics.md): Page basics: HTML skeleton, layout, CSS, footer libraries

  - `<!DOCTYPE html>` and `<meta charset="UTF-8">` at the very top are load-bearing, not boilerplate
  - The status line retranslates on a language change via a remembered *builder*, not a key
  - `.table-wrap` is a deliberate, bounded scroll container
  - `OPEN_SOURCE_LIBRARIES`

### [`docs/architecture/02-data-and-fields.md`](docs/architecture/02-data-and-fields.md): Data layer and fields: File System Access, sql.js, ids and uids, tags, people, custom fields, previews, forms

  - File System Access API
  - sql.js
  - IDs are assigned in JS, not via `AUTOINCREMENT`/`last_insert_rowid()`.
  - Stable uids
  - Tag deduplication
  - People is a real, generic `fields` row now (`type: 'person'`), not a hardcoded sentinel
  - `subcategory` is a flat, independent field, not nested under `category`
  - Custom fields (`fields` + `document_field_values`) are fully generic — not a fixed set of hardcoded columns.
  - Document previews
  - Dynamic per-type fields
  - The capture form's date field is preset to today (`todayIsoDate()`,
  - Keyboard shortcuts
  - Suggested values from OCR text
  - Autofill from earlier documents
  - `.field input[type=date]{ color-scheme:dark; }`
  - `wireClearButton(inputId, clearBtnId)`
  - Document Type is deliberately positioned right after the file/OCR section, styled via `.field-prominent`, i...
  - Field settings modal
  - "Set up fields for this type…" in the capture and Edit forms
  - Creating a brand new custom field happens inline in the capture/edit forms
  - `migrateTextFieldsAutocompleteDefault()`
  - Amount, Currency, and Payment method used to be "sentinel" dynamic
  - The one-time backfill (`migrateSentinelFieldsToGeneric()`) was the first in-app data migration this codebas...
  - `migratePeopleToGenericField()` followed the same precedent shortly
  - `default_currency` (a `settings` row, exactly like `default_document_type`

### [`docs/architecture/03-detail-and-edit.md`](docs/architecture/03-detail-and-edit.md): Detail view, editing, archive, review queue, waste bin

  - The detail view's header (`openDetail()`'s `modal-meta` block) shows
  - The detail view also shows `File`/`Original` lines with each file's path
  - `applyDynamicFieldsForType()`'s `isEdit` parameter controls whether "orphaned" fields render
  - A real debugging lesson from building this feature, worth remembering for future large refactors
  - Not every test file was using the shared `stub_studio2.js`.
  - `runOcrForEdit()` is deliberately separate from `runOcr()`, not a shared function with a flag.
  - Editing
  - Archiving
  - Review queue
  - Waste bin

### [`docs/architecture/04-navigation-reports-columns.md`](docs/architecture/04-navigation-reports-columns.md): Navigation, reports, collections, detail panel, columns, tools, sorting, schema upgrades

  - Top-level navigation
  - Reports
  - Collections
  - The detail view is a persistent side panel (`#detail-panel`), not a modal
  - Configurable columns/filters
  - The "🛠 Tools" toolbar dropdown
  - Every filter dropdown built by `populateFilters()`
  - Persisted default sort order
  - Per-field capability checkboxes

### [`docs/architecture/05-ocr-inbox-scanning.md`](docs/architecture/05-ocr-inbox-scanning.md): OCR, scanning hints, Inbox, drag and drop, scan_watch.py, the scan dialog

  - Schema upgrades for already-existing libraries.
  - OCR now runs on both images and PDFs
  - OCR language options
  - No direct scanner integration in the app itself
  - The scan-hint text is OS-aware
  - Inbox
  - Drag-and-drop
  - scan_watch.py
  - Scanning: the scan dialog and its helpers

### [`docs/architecture/06-sync-and-libraries.md`](docs/architecture/06-sync-and-libraries.md): Dossiary Sync: devices dialog, delete library, share library, saving without a lease

  - iPhone & other devices
  - Delete library
  - Share this library and Get it
  - Saving in a synced library (no editing lease)

### [`docs/architecture/07-pdf-originals-libraries-i18n.md`](docs/architecture/07-pdf-originals-libraries-i18n.md): Searchable PDF, originals, make searchable, new and recent libraries, UI languages

  - Searchable PDF generation
  - Preserving an original file on ingestion
  - "Make searchable"
  - Sidecar `.txt` files
  - New libraries are `<Name>.dossiary` folders
  - Recent libraries
  - UI language support (started as English/German, later generalized to

### [`docs/architecture/08-fields-bulk-checks-grid.md`](docs/architecture/08-fields-bulk-checks-grid.md): Field descriptions and reminders, bulk edit, duplicate and library checks, grid view, splits

  - Field descriptions
  - Renaming a custom field
  - Reminder-type custom fields
  - The default-reminder context menu
  - Comma-aware autocomplete for multi-valued fields
  - Bulk edit
  - Duplicate detection
  - The "Find duplicates" modal was renamed to "Library check" (`#library-check-btn`, `openLibraryCheckModal()`)
  - Orphaned tags/people cleanup
  - Unused custom fields
  - Grid view
  - Line-item splits
  - Calendar view
  - Page tools
  - Smart Collection rules and editor
  - Rename or merge values
  - Back up library
  - Export selected documents
  - Export as library
  - Import a folder
  - Share
  - Storage stats

## How this was tested

See `tests/CLAUDE.md` for the full per-feature test-coverage narrative and
testing conventions (the shared stub harness, `stub_studio2.js` discipline,
how to run the suite) — it loads automatically whenever Claude works with
files under `tests/`.

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
  sibling repo's `document_ledger.html`, since people may use both.
