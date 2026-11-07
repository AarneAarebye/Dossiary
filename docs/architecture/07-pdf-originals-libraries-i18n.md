# Dossiary architecture notes: Searchable PDF, originals, make searchable, new and recent libraries, UI languages

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

- **Searchable PDF generation** (JPEG/PNG images, and — as of the
  2026-09-22 amendment below — scanned PDFs too): `runOcr()` requests
  Tesseract's `{blocks: true}` output specifically — the default
  `recognize()` call only returns plain text, not per-word bounding boxes.
  `flattenOcrWords()` flattens the `blocks -> paragraphs -> lines -> words`
  tree. `buildSearchablePdf()` then uses jsPDF to place the source image as
  a full-page background with each word rendered as invisible
  (`renderingMode: 'invisible'`) text positioned at its bounding box — the
  same technique tools like `ocrmypdf` use. Two jsPDF unit gotchas that are
  easy to reintroduce as bugs if this code is touched:
  - jsPDF's `unit: 'px'` does **not** default to a 1:1 pixel mapping; the
    `hotfixes: ['px_scaling']` constructor option is required to make 1 unit
    equal 1 real image pixel, matching the coordinates `addImage()` and
    Tesseract's `bbox` both use. Without it, all text lands in the wrong
    place.
  - `setFontSize()` **always** takes points, regardless of the document's
    configured unit. Word heights from Tesseract are in pixels, so they're
    converted via `wordHeightPx * 0.75` (96 CSS px per inch ÷ 72 pt per
    inch) before being passed to `setFontSize()`.
  - Horizontal scaling to exactly match each word's bbox width is
    deliberately not attempted (would need jsPDF's transform-matrix text
    API); only x/y position and approximate font size are set. This was a
    deliberate scope cut for robustness, not an oversight — don't add
    matrix-based scaling without a way to visually verify it, since it
    can't be checked in this project's offline test setup (see below).
  - When a searchable PDF is built, the *processed* file is the generated
    PDF (`file_path`), and the *original* upload is preserved untouched in
    a subfolder next to it (`original_file_path`) — mirroring the layout
    `migrate_to_new_library.py` produces for migrated documents and that
    Mariner Paperless itself used. See "Preserving an original file on
    ingestion" below for what happens when a searchable PDF *isn't* built.
  **PDF capture OCR (2026-09-22 amendment)**: the capture form's "Make searchable" (formerly "Run OCR")
  button and language selector, previously hard-disabled for any non-image
  upload, now also work for PDFs — an opt-in click before Save, at parity
  with images, not an automatic zero-click process. Clicking it on a PDF
  first checks every page for real, pre-existing text via pdf.js's
  `page.getTextContent()`; if any page has substantial real text, the whole
  document is treated as already-searchable and OCR is skipped entirely —
  the file saves completely untouched, since rebuilding an already-digital
  PDF through the rasterize-and-overlay technique below would only degrade
  it for no benefit. Otherwise, every page is rendered via
  `renderPdfPageToCanvas()` (the same helper `runOcrForEdit()` already
  uses) and OCR'd individually with `{blocks: true}` — unlike
  `runOcrForEdit()`'s own PDF path, which only needs plain text, capture-time
  OCR also needs each page's word-position data, since it feeds the
  searchable-PDF rebuild at Save. **Rendered pages go to jsPDF as JPEG
  (quality 0.9), never PNG** (`ocrPdfPagesWithWords()`, shared with "Make
  searchable"): jsPDF stores a PNG as a predictor-compressed image, and
  Chrome's PDF viewer showed a large one -- a 72-ppi Image Capture scan
  rendered at scale 2 to 4288x6282 -- as coloured noise, though other
  readers decoded it fine; it was also ~6x the size. `buildSearchablePdf()` itself was
  generalized from a single-page function to `buildSearchablePdf(pages)`,
  taking an array of `{dataUrl, imageFormat, dims, words}` entries and
  looping `addPage()` for entries after the first — every existing
  image-capture call site now passes a single-element array, reusing the
  exact same per-page placement logic and the same two jsPDF unit gotchas
  documented above, rather than a second parallel implementation. The
  resulting rebuilt PDF is, necessarily, a rasterized copy of the original
  scanned pages (an image background per page, same as the image-capture
  case) — there is no code path anywhere in this app for merging a new text
  layer into an existing PDF's own vector/text content, which is exactly
  why the already-has-real-text check above exists: to make sure this
  rasterize-and-rebuild path is only ever taken for PDFs that didn't have
  real content worth preserving in the first place. See
  `docs/superpowers/specs/2026-09-22-pdf-capture-ocr-design.md` for the
  full design.
- **Preserving an original file on ingestion** (`writeOriginalToSubfolder()`,
  called unconditionally from both `saveNewDocument()` and `addInboxFile()`)
  reverses what used to be true only for the searchable-PDF path above:
  every new document, regardless of file type or whether OCR ever runs,
  gets its raw, untouched bytes written into `files/<id>_<baseName>/` and
  `original_file_path` set to that — before any processing happens.
  `file_path` keeps meaning the same *concept* it always has — whatever's
  currently active (the searchable PDF when one was built, otherwise a
  plain copy of the same content) — but its *naming scheme* changed for
  `saveNewDocument()`'s plain-save branch specifically: the active copy is
  now named `<id>_<baseName><ext>`, using the same title-or-filename-derived
  `baseName` computed once and reused for the original's subfolder, rather
  than being purely filename-derived as it was before this feature (`ext`
  is extracted directly from the raw uploaded filename, not re-run through
  `safeFilename()`, since `baseName` already went through it). This is a
  real, user-visible change — documents captured after this ships are named
  differently than ones captured before. `addInboxFile()` was always
  filename-derived (no title field exists at Inbox-add time) and still is;
  only the capture form's plain-save path changed. LibraryLifeboat-migrated
  documents are untouched by this — their `original_file_path` reflects
  Mariner's own historical layout via `migrate_to_new_library.py`, not this
  app's own ingestion.
  **This means `original_file_path IS NOT NULL` can no longer be read as
  "this document went through searchable-PDF processing"** — a new
  `searchable_pdf_built` column (`documents.searchable_pdf_built`, `0`/`1`)
  is the explicit signal for that now, set to `1` only in
  `saveNewDocument()`'s searchable-PDF branch, `0` everywhere else
  (including every Inbox add, since Inbox never runs OCR automatically).
  A one-time backfill migration (`migrateSearchablePdfBuiltFlag()`, same
  settings-row-tracked-once pattern as `migrateTextFieldsAutocompleteDefault()`
  below) sets `searchable_pdf_built = 1` for existing documents where
  `original_file_path IS NOT NULL AND source = 'captured'` — the same
  predicate that uniquely identified the old rule — deliberately excluding
  `source = 'migrated'` documents, whose `original_file_path` predates and
  is unrelated to this app's own OCR pipeline. Every new document now
  permanently uses roughly double the disk space (an original plus an
  active copy, even when nothing is ever processed) — an accepted
  tradeoff, not an oversight. `searchable_pdf_built` is loaded into
  `allDocs` (as a boolean) and gates the "Make searchable" action below.
- **"Make searchable"** (`makeDocumentSearchable()`,
  `openMakeSearchableModal()`, the panel-only `'make-searchable'` action in
  `buildDetailActions()`) builds a searchable PDF for an already-saved
  document -- the same OCR-plus-invisible-text-layer rebuild capture does
  when OCR runs before Save, after the fact. Offered only for a non-deleted
  document whose active file ends in `.pdf`/`.jpg`/`.jpeg`/`.png` and whose
  `searchable_pdf_built` is still `0`; panel-only (like "Regenerate
  preview"), since it's a long, progress-reporting run rather than a
  one-shot context-menu action. A small dialog picks the OCR language
  (defaulting to the document's own `ocr_language`, else Auto) and blocks
  Escape/backdrop/close while running (`makeSearchableRunning`, checked by
  `onModalKeydown()` alongside the Library check backfill flag). It shares
  its OCR steps with capture: `pdfHasRealText()` (a PDF with real text is
  left completely untouched and reported as such -- same reason capture
  skips it) and `ocrPdfPagesWithWords()` were pulled out of `runOcr()`, and
  `ocrLanguageOptionsHtml()` now builds all three OCR language dropdowns.
  **The untouched original is always kept**, by one of two rules:
  - The document has its own preserved original (everything this app
    captured or added via Inbox): the active *copy* is replaced -- a PDF is
    overwritten in place, an image gets a new `<stem>.pdf` next to it. The
    superseded image copy is removed only when its bytes hash-match
    `file_hash` (which is computed on the original), so a copy that
    somehow differs from the original is never deleted.
  - No original, or the original's file is missing on disk: the current
    file *becomes* `original_file_path` and the searchable PDF is written
    next to it as `<stem>.pdf` (image) or `<stem>_searchable.pdf` (PDF) --
    never overwriting what might be the only copy.
  `file_hash` needs no update under either rule: it's derived from the
  original, which never changes. Existing non-empty `ocr_text` is kept
  (it may have been corrected by hand), otherwise the fresh OCR text and
  language are stored. The sidecar is rewritten under the new file stem
  (best-effort) and the old one removed when the stem changed -- it's
  derived output, not user data.
  **Bulk "Make searchable"** (`#bulk-make-searchable-btn` in the
  bulk-action bar's More menu -- see the page tools note) opens the same dialog: `openMakeSearchableModal(ids)`
  takes a list, filters it through `canMakeSearchable(d)` (the one
  eligibility rule, shared with the panel action), and a single remaining
  id takes the original single-document path and messages. The button only
  shows when at least one selected document is eligible (never in the
  Waste bin), and the dialog says how many it will process. Documents run
  one after another, each persisted as it finishes (`makeDocumentSearchable()`
  already calls `persistDb()` per document -- a long batch is exactly where
  a closed tab or crash should keep what's done, the same reasoning as the
  Library check backfill's periodic saves). "Stop after this document"
  lets the current one finish. The summary counts made searchable /
  already had text / could not be processed / not processed (stopped),
  phrased as "Label: N" so no singular/plural key pairs are needed, and
  lists each failed document with its reason. A failed document stays
  eligible, so the bulk button remains for a retry.
  **Failures say which file and why**: `withFileOp(op, path, fn)` wraps a
  file read or write and rethrows with `fileOp`/`filePath`/`errorName`
  attached, and `fileErrorText(e, fallbackKey)` turns that into plain words
  -- a read-only file (Chrome's `NoModificationAllowedError`, e.g. a file
  locked in Finder) gets "Could not save "<library>/<path>": the file is
  read-only" plus how to unlock it, a missing file points at Library check's
  re-link, anything else names the path and the browser's message. It used
  to be "OCR failed: Failed to execute 'createWritable'...", although OCR
  had worked and only saving failed. Make searchable, Edit pages and
  Combine use it. **"OCR found no text" isn't a failure**: OCR ran and
  recognized nothing (blank page, photo, handwriting, wrong language). A
  single run shows it in the neutral status colour; the bulk summary counts
  it on its own ("No text found: N. Try another OCR language."), lists those
  documents apart from real failures (`#make-searchable-notext-list`), and
  they stay eligible for a retry.
  **`has_text_layer`** (`documents.has_text_layer`, `0`/`1`, added via
  `SCHEMA_MIGRATIONS`) records a PDF found to already contain real text --
  by capture-time OCR (`pendingPdfHasText`) or by "Make searchable" -- so
  `canMakeSearchable()` stops offering it. Kept separate from
  `searchable_pdf_built` on purpose: that flag means "this app built the
  file", this one "the file was searchable as it came". Without it, every
  digital PDF (a downloaded bill) would count as not searchable forever.
  **"Not searchable yet" in Library check** (`renderNotSearchableSection()`
  filling `#not-searchable-slot`, last in the list since it's not a
  problem, just what OCR hasn't reached) shows two counts, from
  `notSearchableBuckets()`: PDFs **not checked for text yet**, and
  documents that **need OCR** (images, which never have a text layer, and
  PDFs checked without one -- `text_checked` = 1, `has_text_layer` = 0),
  **leaving out any document that already has OCR text** (typed in by hand
  or from an earlier OCR run): search and the sidecar read `ocr_text`, not
  the file, so it's findable already. Reported after a person typed the
  text of a document OCR couldn't read and Library check kept listing it.
  The panel still offers "Make searchable" for such a document.
  The split exists because a single "not searchable" count was reported as
  wildly wrong: a Mariner-migrated library arrived with ~1,340 documents
  counted, since none of its PDFs (most of which already carry a text
  layer from Mariner/ScanSnap) had ever been opened to look. Whether a PDF
  has text is only knowable by opening it -- Mariner's stored OCR text
  lives apart from the file. **"Check for text"** (`runTextLayerCheck()`)
  opens each unchecked PDF with pdf.js and runs `pdfHasRealText()`, no
  OCR, shaped like the duplicate backfill for the same iCloud reason: 4
  files at a time, a chained save every 25, a Stop that lets in-flight
  files finish (then a note saying how far it got), and the modal's close
  controls gated on `findDuplicatesBackfillRunning` while it runs. A file
  that can't be read stays unchecked, so the next run retries it. Each
  count comes with its own actions: "Check for text" for the first; "Show
  in table" (the same Reports drill-down the duplicate groups use, back
  link returning to Library check) and "Make all searchable" (the bulk
  dialog, for the needs-OCR bucket only -- not a way to start OCR on
  hundreds of unchecked PDFs by accident) for the second. "Make
  searchable" also records `text_checked` when it finds no text.
  **A found text layer also becomes searchable text**: `recordPdfTextLayer()`
  (the one place that records a check, used by "Check for text", "Make
  searchable", and the duplicate backfill) copies the PDF's own text
  (`pdfExtractText()`) into `ocr_text` when that's empty, and the caller
  refreshes the sidecar -- the app's search and Spotlight only ever see
  `ocr_text`, so before this a digital PDF (or a Mariner PDF whose text
  never reached the database) wasn't findable by its contents at all.
  Existing `ocr_text` is never replaced. A third count, **"Text not in
  search yet"** (`notSearchableBuckets().textMissing`: non-deleted PDFs with
  `has_text_layer` = 1 but empty `ocr_text`), catches PDFs checked before
  the text was copied over (v1.30.1); "Check for text" includes them in the
  same pass, and since `recordPdfTextLayer()` copies into any empty
  `ocr_text`, no separate code path was needed. Capture does the same: a PDF found
  to have text fills the empty OCR text box. **The duplicate backfill
  checks for text from the same read** (`backfillFileHash()`): when the
  file it hashes is the document's active PDF (no separate original, as for
  every Mariner-migrated document), it opens those bytes with pdf.js too,
  so on iCloud Drive a file downloads once for both checks; a document
  hashed from a separate original is left for "Check for text". It's the
  one place to find these documents without a toolbar filter, which would
  have reopened the toolbar-wrap calibration problem described near the
  top of this file.
- **Sidecar `.txt` files** (`buildSidecarText()` / `writeSidecarFile()`) are
  written next to every captured document's primary file, containing the
  fields that only live in `library.sqlite` (category, tags, notes, OCR
  text, etc.) so Spotlight/Finder search can find them — Spotlight has no
  visibility into a SQLite file's rows otherwise, and there is no way to
  register a real Spotlight importer from a browser context. If the
  metadata fields captured in `saveNewDocument()` change, update
  `buildSidecarText()`'s field list to match — it's easy for these to drift
  out of sync since nothing enforces they stay identical. The sidecar's
  base filename always matches the primary file's stem (without extension),
  never the original's — so it's discoverable sitting right next to what a
  person would actually open. `migrate_to_new_library.py` in the sibling
  repo does the equivalent thing in Python (`build_sidecar_text()`) for
  migrated documents; keep both in sync if the sidecar format changes,
  since a person migrating and then capturing should get consistent files.
- **New libraries are `<Name>.dossiary` folders** (`createLibraryFolder()`,
  `libraryFolderName()`, `showNewLibraryForm()`, the `#new-library-form`
  on the init-state screen). When a picked folder has no `library.sqlite`,
  the screen offers a name (default `newLibraryDefaultName`, "My
  Documents") with a live preview of the folder it will create, and
  **Create library in this folder** makes `<Name>.dossiary` inside the
  picked folder and runs `initNewLibrary()` there (`rootDirHandle` is
  switched to the new folder first, so recent libraries record it). The
  same naming LibraryLifeboat's migration uses, so a library folder is
  recognisable. It's a convention only: a browser app can't register a
  package type, and opening never requires the extension. A name already
  ending in `.dossiary` (any case) isn't doubled; names with `/ \ : * ? "
  < > |` or a leading dot are refused; an existing folder of that name is
  never reused. **"Use this folder as the library" (`#init-btn`, the old
  "Initialize a new library here") still sets up the picked folder itself**
  and becomes the main action -- the name form hidden -- when that folder
  already ends in `.dossiary`. A language switch on this screen swaps an
  untouched default name and rebuilds the preview (`setLang()`).
  **"Copy the setup of"** (`#copy-setup-select`, `renderCopySetupOptions()`,
  `readSetupSourceOrShowError()`, `copySetupFrom()`) starts either path
  with another library's setup: its `fields` (ids kept, since
  `visible_columns`, `sort_key` and Smart Collection rules refer to
  `field-<id>`/`field:<id>`), `document_type_fields`, `field_descriptions`,
  smart `collections`, and every `settings` row except
  `SETUP_SETTINGS_NOT_COPIED` (`last_backup_at`) -- the migration markers
  included, so `migrateTextFieldsAutocompleteDefault()` doesn't switch a
  copied field's deliberately-off autocomplete back on. Never documents,
  tags, people or manual collections. The source comes from Recent
  libraries or "Another library folder…" (`showDirectoryPicker({mode:
  'read'})`), and is read into a separate in-memory sql.js database, never
  written. It's read *before* the new folder is created, so an unreadable
  source (no permission, no `library.sqlite`) is reported in
  `#copy-setup-error` and leaves nothing half-made. `copySetupFrom()` runs
  in `initNewLibrary(setup)` right after `SCHEMA` and before the field
  migrations, which find the copied built-in fields by name and add only
  what's missing. Columns are listed explicitly (`SELECT id, name, ... FROM
  fields`, not `SELECT *`), per the sql.js convention above and so the test
  stub's `FakeDatabase` can serve it; a table an older source lacks is
  skipped. The status line adds `statusSetupCopiedFrom`
  (`setupCopiedFromName`, read by `afterDbReady()`).
- **Recent libraries** (`renderRecentLibraries()`, `recordRecentLibrary()`,
  `reconnectRecentLibrary()`, `#recent-libraries` on the empty-state screen)
  reverses what an earlier version of this note called an unavoidable
  browser limitation. `FileSystemDirectoryHandle` objects are structured-
  cloneable, so they can be stored directly in IndexedDB (database
  `dossiary-app-db`, object store `recentLibraries`) and later
  re-authorized with a single click via `handle.requestPermission()` — no
  fresh `showDirectoryPicker()` dialog needed, just a user gesture. This is
  still FSA's own handle object being persisted, not a `localStorage`-style
  workaround around FSA. `afterDbReady()` (the single point both
  `loadDb()` and `initNewLibrary()` funnel through) calls
  `recordRecentLibrary(rootDirHandle)` as a fire-and-forget best-effort
  call, same pattern as its neighboring `checkInbox()` call — a failure to
  record history should never block a library from actually opening.
  Dedup uses `handle.isSameEntry()` (folder *identity*, not name — a
  folder can be renamed, and two different folders can share a name), not
  a string comparison; a re-opened library updates its existing entry's
  `lastOpenedAt` rather than creating a duplicate row. Capped at 5 entries,
  oldest evicted first. On by default (matches Finder/Explorer "Recent
  Files" conventions) — a person on a shared computer who doesn't want a
  library remembered removes it via the row's own ✕; there's no separate
  opt-out setting. **One real caveat worth being explicit about**: all
  `file://` pages share a single IndexedDB origin, so this isn't isolated
  to Dossiary the way it would be if this app were served from a real
  origin — any other local HTML file a person happens to open in the same
  browser can enumerate `indexedDB.databases()`, read `dossiary-app-db`'s
  stored records back (live `FileSystemDirectoryHandle` objects included),
  and call `requestPermission()` on them itself. The native OS/browser
  permission prompt — which still names the real folder — is the only
  remaining gate at that point, not origin isolation; there's no way to
  scope `file://` storage per-page, and this is empirically confirmed
  behavior in real Chromium, not a hypothetical. `openLibrary()`'s original body (given a granted
  handle, check for `library.sqlite` and proceed) is now the shared
  `proceedWithRootDirHandle(handle)` helper, called both from the fresh-
  picker path and from a successful reconnect — so there's exactly one
  place that knows what "given a folder handle, open it" means. Tested via
  `tests/test_recent_libraries.py`; `tests/stub_studio2.js` needed a
  from-scratch in-memory `indexedDB` fake for this (storing values by
  reference, not a real structured-clone round-trip) since a real
  browser's IndexedDB would silently strip our fake `FileSystemDirectoryHandle`
  class down to a plain data object, unlike what happens to a *real* handle.
- **Library details in Recent libraries.** Each `recentLibraries` entry also
  caches the library's `title` and `description`, so the list can show them
  without opening the library; `recordRecentLibrary(handle, details)`
  refreshes it when a library opens (and sets `lastOpenedAt`), and
  `updateRecentLibraryDetails()` refreshes it when `saveLibraryDetails()`
  succeeds (leaving `lastOpenedAt` alone). The ✎
  pencil on an entry reconnects that library (permission click) and, only if
  `proceedWithRootDirHandle()` returns `true` (it now returns `true`/`false`
  for opened/not opened), runs `opts.afterOpen`, which opens the Library
  details dialog. `saveLibraryDetails()` changes in-memory state, the header
  (`libraryHeaderName()`) and the cache only after the settings were
  persisted; on a failed or refused write the status line says why ("Save
  failed" when `persistDb()` throws, its own message when it returns
  `false`, the close-the-dialog-first notice when `ensureCurrentVersion()`
  refuses) and the header, the in-memory values and the list entry stay as
  they were (the settings rows are restored unless a synced reload swapped
  the database meanwhile). Tested via `tests/test_library_details.py`.
- **UI language support (started as English/German, later generalized to
  seven languages — English, German, Spanish, French, Chinese Simplified,
  Chinese Traditional, Armenian)** is a flat per-language dictionary (`STRINGS.en` /
  `STRINGS.de` / `STRINGS.es` / `STRINGS.fr` / `STRINGS['zh-Hans']` /
  `STRINGS['zh-Hant']` / `STRINGS.hy`, ~930 keys each), a lookup helper (`t(key,
  params)`), and one whole-page re-translate pass (`applyI18n()`) — not a
  full i18n library, ICU message format, or per-string `.po`/`.json` files;
  the app's single-file constraint (see "What this project is") rules out
  pulling in a real i18n framework, and a handful of hardcoded languages
  don't need one. `t()` falls back `STRINGS[currentLang][key] ?? STRINGS.en[key] ??
  key` — an unknown/missing key renders as its own literal key string
  rather than throwing or going blank, so a typo'd or forgotten key is
  loud and visible in the UI instead of silently disappearing. `params` is
  a plain `{needle: value}` object, substituted via repeated
  `replaceAll('{needle}', value)` calls — no positional/plural ICU
  grammar, deliberately (see the singular/plural note below for how
  count-dependent strings are handled instead).
  **Static markup vs. dynamically-built markup use two different
  mechanisms, split along the same line the rest of this app already
  splits on** (compare the Configurable columns/dynamic filters notes
  above, or `renderDynamicTableHead()`): HTML that exists in the page's
  own source — labels, buttons, modal headings that are always present in
  the DOM, just hidden/shown — carries a `data-i18n`(`-placeholder`|
  `-title`|`-aria-label`) attribute naming its key, and `applyI18n()`
  walks all four attribute kinds once (`textContent`, `.placeholder`,
  `.title`, `aria-label` respectively) to fill them in. Anything rebuilt
  from scratch in JS on every render — table rows, the dynamic-fields
  container, status-line messages, the recent-libraries list, modal
  bodies assembled via template strings — has no stable DOM node for an
  attribute to survive on, so those call `t()` directly inline wherever
  the template string is built, re-evaluated fresh every time that code
  runs anyway. Neither mechanism is "more correct" than the other; using
  attributes for content that gets discarded and rebuilt on every
  `render()` call would be silently inert (the attribute would exist for
  a few milliseconds before the element carrying it is thrown away), and
  inline `t()` calls for genuinely static markup would just be more code
  than a declarative attribute for no benefit.
  **A handful of elements landed on the wrong side of this split in the
  original translation pass and were corrected in a later final-review
  fix round**: the modal close button's `aria-label`, the capture/edit
  forms' built-in (non-dynamic) field clear buttons' `title`/`aria-label`,
  and the file/thumbnail preview `<img alt>` all live inside `modalRoot`
  template strings rebuilt fresh on every modal open — `applyI18n()` is
  only ever called at page-init and from `setLang()` (and, per the toggle-
  guard note above, `setLang()` now never runs while a modal is open at
  all), so a `data-i18n-aria-label`/`data-i18n-title` attribute on one of
  these would never actually get resolved; the fix was inline `t()` calls
  at template-build time, matching what the detail modal's own close
  button and the dynamic per-field clear buttons already did correctly
  from the start. All of them **reuse existing keys** rather than minting
  near-duplicates — `detailCloseAriaLabel` (despite its name, a generic
  "Close" label, not detail-modal-specific) for every modal's close
  button, and `fieldClearTitle`/`fieldClearAriaLabel` (the same pair
  `renderGenericFieldHtml()`'s dynamic fields already use) for the 8
  built-in clear buttons, substituting each field's own existing label key
  (`captureDocTypeLabel`/`editCategoryLabel`/etc., or `tableColTags` for
  the two Tags clear buttons, which have no dedicated plain-"Tags" label
  key of their own) as `{name}`. `FIELD_DEFS`' own `label` values (feeding
  the Columns menu and the Reports breakdown dropdown) got the same
  reuse-not-duplicate treatment: each entry gained a `labelKey` pointing
  at the exact same `tableColCategory`-family keys the static `<th>`
  headers already carry as `data-i18n`, rather than new `columnLabel*`
  keys with identical English/German text. `dynamicColumnDefs()` entries
  (real user-typed field names, e.g. "Organization") deliberately have no
  `labelKey` at all and must never get one — `fieldDefLabel(f)` (shared by
  both display sites) falls back to the raw `label` for those. Because the
  Columns menu is only otherwise rebuilt at library-open time and from
  Field Settings' own field-list-changed call sites — neither of which
  fires on a language toggle — `renderColumnsMenu()` was added to
  `setLang()`'s own follow-up-calls list (see above) so these labels
  retranslate live, the same reasoning that already justified
  `populateFilters()`'s presence there.
  **Persistence is `localStorage` (`dossiary_lang` key), not the
  per-library `settings` table every other per-library preference in this
  app uses** (`nav_style`, `default_currency`, sort order, column
  visibility, ...) — a deliberate exception, not an oversight: the
  empty-state "Open or create a library…" screen (`#empty-state`) has to render
  in the right language *before* any library folder has been picked, so
  there's no `library.sqlite` open yet for a `settings` row to live in.
  `localStorage` is the one piece of persisted app state that predates
  and outlives any single library, the same reason `dossiary-app-db`
  (IndexedDB, see the Recent libraries note just above) was chosen for
  recent-library history rather than a `settings` row — both need to
  exist before/across library selection, not scoped to one library.
  **Language choice auto-detects once, then a manual toggle permanently
  overrides it**: `loadLang()` only consults `navigator.language`/
  `navigator.languages` (checking whether any reported locale starts with
  `de`) when `localStorage.getItem('dossiary_lang')` has never been set;
  the moment someone clicks `#lang-toggle` (now `#lang-select`) once, `saveLang()` writes an
  explicit `'en'`/`'de'` value that short-circuits the browser-locale
  check on every future load, even if the browser's own locale disagrees.
  This mirrors the general "an explicit person action beats a computed
  guess" pattern already used elsewhere in this app (compare the Date/
  Currency `.field-guess` pattern — both are dismissible defaults, not
  permanent inferences), just at the whole-UI-language level instead of a
  single form field. `setLang()` (the toggle's click handler) has its own
  small set of hand-rolled follow-up calls — `applyI18n()`, then
  conditionally `renderStats()`/`populateFilters()`/`renderColumnsMenu()`/
  `render()` (library open, `subLabel.textContent = rootDirHandle.name` set
  separately by those same call sites) or `subLabel.textContent =
  t('emptyTitle')` plus `renderRecentLibraries()` (empty-state) — because
  none of those functions/assignments is invoked from inside `render()`'s
  own "always run this" chain (see the Collections nav section's own note
  above for the general pattern of "which dynamic container rebuilds on
  which trigger" in this codebase); without them, filter-dropdown option
  text, the Columns menu's own built-in-field checkbox labels, the
  empty-state screen's subtitle, and the recent-libraries list would each
  keep showing whichever language they were last rendered in until the
  next unrelated document mutation (or, for `#sub-label` specifically, the
  next `resetAll()`/library-open) forced a rebuild. `#sub-label` itself
  deliberately carries no `data-i18n="emptyTitle"` attribute — it's reused
  for the folder name once a library is open, and `applyI18n()`'s own
  blind textContent walk would clobber that name the next time language is
  toggled while a library happens to be open; setting it explicitly here,
  gated on "no library open", avoids that collision the same way the
  Amount/Currency header-line and conditional-field notes elsewhere in
  this file avoid overreaching a general mechanism into a case it doesn't
  fit. **"A library is open" means `rootDirHandle && db`, not
  `rootDirHandle` alone** (`setLang()`'s `libraryOpen`): while the
  init-state ("no library.sqlite found — Initialize?") prompt is showing,
  a folder is already picked but no database is loaded, and keying on
  `rootDirHandle` alone rendered an empty document table and stats under
  that prompt on a language change and left `#sub-label` untranslated
  (found while recapturing the User Guide screenshots).
  **A mouse click on `#lang-toggle` (now `#lang-select`) is already blocked by a modal's own
  backdrop while a modal is open, but keyboard Tab-through can still reach
  and activate it** (Enter/Space fires a real `click` event without any of
  the backdrop's spatial hit-testing) — and no modal's content re-renders
  in place when that happens, since none of `setLang()`'s follow-up calls
  above touch `modalRoot`. Re-rendering the open modal to fix that isn't
  safe in general: capture/edit would discard whatever's already been
  typed into the form, the exact same in-progress-work hazard
  `applyDynamicFieldsForType()`'s own note above documents for switching
  document types mid-edit, and there's no reliable way to tell which
  modal is open or safely rebuild it in place from `setLang()` alone. The
  resolution is a **toggle guard, not a re-render**: `#lang-toggle` (now `#lang-select`)'s
  click handler returns early — no language change, `saveLang()` never
  called — whenever `modalRoot.innerHTML !== ''` (the same "is a modal
  open" signal `closeModal()`'s own `modalRoot.innerHTML = ''` implies),
  making the toggle inert for the keyboard path too, matching what a
  mouse user already experiences via the backdrop rather than attempting
  a re-render that would be safe for some modals and destructive for
  others. **The persistent detail panel doesn't need an equivalent guard**
  — `setLang()` calls `openDetail(selectedDocId)` (when set) unconditionally
  after `render()`, with no modal-open check at all, because the panel is
  read-only display content, not an in-progress form; unlike capture/edit,
  there's nothing typed-but-unsaved for a re-render to discard.
  **`loadLang()`/`saveLang()` wrap their `localStorage` calls in their own
  try/catch, independently of each other** — `localStorage` access can
  throw (blocked by browser privacy settings, enterprise policy, private-
  browsing quota edge cases), and `let currentLang = loadLang()` runs at
  module-init time, before `#open-btn` or anything else in the app is
  wired up; an uncaught throw here would abort the entire top-level IIFE,
  not just language detection, taking the whole app down before it ever
  renders. A blocked read falls through to the existing
  `navigator.language` auto-detect (skipping only the stored-preference
  check, not detection itself); a blocked write fails silently, so the
  language still works correctly for the rest of that session, purely
  in-memory — it just won't survive a reload, same as if the browser had
  never stored a preference at all.
  **Count-dependent strings use an explicit singular/plural key pair per
  language** (e.g. `sharedPageCountSingular`/`sharedPageCountPlural`,
  `dragdropAddedToReviewQueueSingular`/`...Plural`), picked by the same
  `count === 1 ? t('xSingular', {count}) : t('xPlural', {count})` ternary
  the English-only code already used before translation — not a real
  ICU/CLDR plural-rules engine (which would need a real dependency this
  single-file app doesn't have, and would be overkill for a two-language,
  binary-plural app in the first place; German, like English, only
  distinguishes singular from "everything else," so the same ternary that
  was already correct for English needed no restructuring, just a second
  language's worth of correctly-inflected phrasing supplied for both
  branches).
  **Tested by a deliberate two-file split, one dynamic and one static**:
  `tests/test_i18n.py` is a real Playwright suite exercising actual toggle
  behavior across the app — default/auto-detected/manually-overridden
  language on load and across a reload, date formatting following UI
  language rather than OS locale, and translated content across the nav,
  toolbar, table, detail modal, capture/edit forms, Field Settings, Manage
  Collections, Reports, the Libraries/licenses modal, and drag-and-drop —
  the same kind of real-browser-driven coverage every other feature in
  this suite gets. A later final-whole-branch-review fix round added
  Scenarios 18-22, each targeting a gap the review found via manual/live
  testing rather than a failing automated check: 18 blocks
  `window.localStorage` entirely (`getItem`/`setItem` both throwing) and
  confirms the app still renders and `#open-btn` is still wired, rather
  than the whole top-level IIFE having silently aborted at
  `loadLang()`/`saveLang()`; 19 confirms `#sub-label` retranslates live on
  the empty-state screen, not just the neighboring recent-libraries list
  Scenario 7 already covers; 20 confirms `FIELD_DEFS`' new `labelKey`
  wiring (Columns menu, Reports breakdown dropdown, tolerant of the
  migration-added "Payment method" dynamic column riding along
  untranslated) and the `#ocr-lang`/`#e-ocr-lang` `<option>` lists in both
  forms; 21 confirms `#lang-toggle` (now `#lang-select`) is a genuine no-op while a modal is
  open (dispatched via `force=True`, since a real un-forced click already
  correctly times out against the backdrop — the same protection this fix
  doesn't touch) and works again once the modal closes; 22 sweeps the
  remaining minor gaps (modal close-button `aria-label`s across 5 modals,
  the 8 built-in clear buttons' `title`/`aria-label`, the file-preview
  `<img alt>`, and the footer's "Libraries" link) in one pass over freshly
  rebuilt forms and modals. `tests/test_i18n_coverage.py` is a different
  kind of check entirely: a plain Python script (no Playwright, no
  browser) that greps `dossiary.html` for every `data-i18n*` attribute
  value and every `t('key')`/`t("key")` call, and asserts each referenced
  key exists in *every* supported language's own `STRINGS` block (looped
  over `SUPPORTED_LANGS` itself, not a hardcoded language pair — see the
  "Generalized from two languages to six" note just below), and that each
  language's key set matches `STRINGS.en`'s exactly, not just "referenced
  key present" — a static safety net against the one mistake
  `test_i18n.py`'s scenario-by-scenario clicking can't exhaustively rule
  out (a key added to English but never given a translation in some other
  language, or vice versa, anywhere in this ~930-key, hand-maintained
  dictionary that no single Playwright run touches every corner of).
  Its own key-extraction regex needed to be **more careful than a naive
  "key starts a line" pattern**: `STRINGS.en`/`STRINGS.de` pack several
  `key: 'value',` pairs onto one source line throughout (matching this
  file's existing dense, wrapped style elsewhere, e.g. `FIELD_DEFS`), so a
  key is only recognized when it's immediately preceded by `{`, `,`, or a
  line start *and* immediately followed by `:` plus a quote — otherwise
  either most keys sharing a line with another key go undetected, or text
  sitting inside a string *value* that happens to end in `word:` right
  before that value's own closing quote (e.g. the literal English value
  `'Important:'`) gets misread as a second, bogus key. The `t()` call-site
  regex has the same kind of trap: matching bare `t\(` catches any
  function call whose name simply ends in the letter "t" followed by a
  quoted argument (`createElement('div')`, `getContext('2d')`,
  `dispatchEvent(new Event('change'))`, `closest('th...')`, all real calls
  elsewhere in this file) — a leading `\b` word-boundary before the `t`
  is what keeps the match scoped to the actual `t()` helper. Both were
  real false-positive floods hit and fixed while building this check, not
  hypothetical — worth remembering if this regex is ever extended, since
  the failure mode (a flood of *fake* missing-key reports burying any
  *real* one) is the opposite of the usual silent-gap risk this kind of
  check exists to catch.
  **Generalized from two languages to six, later seven** (`SUPPORTED_LANGS = ['en', 'de',
  'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']`, plus `NATIVE_LANG_NAMES` — each code's
  own name for itself, `简体中文`/`繁體中文` etc., deliberately never run
  through `t()`, since a language's name for itself in its own script is
  what belongs in a language picker no matter which language is currently
  active — `LANG_AUTODETECT`, and `DATE_LOCALE`) once Spanish, French, and
  both Chinese scripts were added on top of the original English/German
  implementation described above. None of the dictionary/lookup-helper/
  `applyI18n()` shape above had to change to support this: `STRINGS` simply
  grew from two top-level keys to six, then seven (~930 keys apiece now,
  not ~260), and
  `t()`'s own `STRINGS[currentLang][key] ?? STRINGS.en[key] ?? key`
  fallback chain already generalizes for free, since it was never
  hardcoded to specifically `en`/`de` in the first place.
  `tests/test_i18n_coverage.py` loops over `SUPPORTED_LANGS` the same
  way now, rather than a hardcoded `STRINGS.en`/`STRINGS.de` pair — going
  from two languages to six changed that check's loop bound, not its
  underlying logic.
  **Armenian (`hy`) is the seventh language**, translated independently
  (not derived from another block) and shipped in v1.49.0 before a native
  speaker's review; corrections from that review page follow in an update. It auto-detects from a bare `hy` or any
  `hy-*` locale, formats dates with `hy-AM`, and adds Tesseract's `hye` to
  the OCR language lists (`ocrLangArmenian`). `test_i18n_coverage.py` also
  checks that every translation keeps exactly English's `{placeholders}`.
  **The old `EN | DE` two-state `#lang-toggle` button was replaced by a
  `<select id="lang-select">`** listing all seven languages via
  `NATIVE_LANG_NAMES`, since a two-state toggle has no way to generalize
  past two options. `setLang(lang)` itself didn't change — same
  signature, same conditional follow-up calls described above — only the
  control invoking it did, from a click handler alternating between two
  hardcoded values to a `change` handler reading `event.target.value`.
  This forced a real fix to the existing modal-open guard, not just a
  handler rewire: the old button's guard could get away with simply
  skipping `setLang()` and doing nothing else while a modal was open,
  because a *button* has no displayed state of its own to desync from
  `currentLang` — nothing on screen changes until the click handler
  actually runs. A native `<select>` is a strictly harder case: choosing a
  new option visually commits that option as the control's own displayed
  value *immediately* and *synchronously* — mouse or keyboard — before any
  `change` handler even runs, and nothing can intercept that part. So
  `#lang-select`'s guard has to do more than the old button's guard did:
  when a modal is open, it actively resets `e.target.value = currentLang`
  back to the still-active language, on top of skipping `setLang()` —
  otherwise the dropdown would sit there visibly showing a language the
  app never actually switched to, silently lying about the current state
  until the next real change goes through. The keyboard-Tab-through hazard
  and the reasoning for why re-rendering the open modal in place isn't a
  safe alternative (both described above for the old button) carry over
  unchanged to the new control.
  **Chinese does not inflect for grammatical number**, so the existing
  singular/plural key-pair convention (`sharedPageCountSingular`/
  `...Plural`, picked by the same `count === 1 ? t('xSingular', {count}) :
  t('xPlural', {count})` ternary described above) needed no new no-plural
  code path for `zh-Hans`/`zh-Hant` — both simply carry *identical* text in
  both slots of every existing pair. This is the same "only distinguishes
  singular from everything else" reasoning already noted above for German,
  taken one step further: Chinese doesn't distinguish grammatical number at
  all, so its two slots just happen to always agree.
  **Chinese needs real region disambiguation that German/Spanish/French
  don't**, because `navigator.language`/`navigator.languages` report a
  region code (`zh-CN`, `zh-TW`, ...) or occasionally an explicit script
  subtag (`zh-Hans`, `zh-Hant`), not something that reliably indicates
  simplified vs. traditional on its own the way a bare `de`/`es`/`fr`
  prefix check already does for those. `LANG_AUTODETECT` (an ordered array
  of `{code, test}` rules, first match wins) resolves this: a `CN`/`SG`/
  `MY` region or explicit `Hans` script → `zh-Hans`; a `TW`/`HK`/`MO`
  region or explicit `Hant` script → `zh-Hant`; a bare `zh` with no
  recognizable region or script at all defaults to `zh-Hans` (more widely
  read globally — the same "best guess, dismissible by the existing
  manual-override-wins rule" spirit as every other auto-detect default in
  this app, e.g. the Date/Currency `.field-guess` pattern noted elsewhere
  in this file). **`loadLang()` is locale-major, not rule-major**: it
  iterates the user's own `navigator.languages` array in order (outermost
  loop), and for each locale string in turn checks it against every
  `LANG_AUTODETECT` rule (innermost loop), returning on the first rule
  that matches — so the user's own preference order decides ties between
  languages, and no `LANG_AUTODETECT` rule can shadow another rule against
  a *different* locale string earlier in the user's own list. (An earlier
  version of `loadLang()` was rule-major instead — checking each rule
  against the *whole* array before moving to the next rule — which broke
  in two ways: `navigator.languages = ['zh-TW', 'zh']` could pick
  `zh-Hans` over `zh-Hant` depending on which rule happened to be listed
  first, and, worse, a browser reporting `['en-US', 'zh-CN', 'zh']` — an
  ordinary machine with Chinese added as a secondary input language —
  auto-detected Chinese over the user's own first-listed English, since
  there was no explicit `en` rule participating in the same matching loop
  at all, only an implicit final fallback. Both were real, fixed
  regressions, not hypothetical.) `zh-Hant`'s rule is still listed before
  `zh-Hans`'s purely for readability now — the two rules test disjoint
  locale strings (a `TW`/`HK`/`MO` region or explicit `Hant` script vs.
  bare `zh`/`CN`/`SG`/`MY`/`Hans`), so within a single locale string
  there's no shadowing risk left to order around either way. This was
  verified two ways, not just asserted: a direct code trace during
  review, and `tests/test_i18n.py`'s own Scenario 27 (`navigator.languages
  = ['zh-TW', 'zh']` still correctly lands on Chinese Traditional, not
  Simplified) plus the new Scenario 28 (`['en-US', 'zh-CN', 'zh']`
  correctly lands on English, not Chinese).
  **`STRINGS['zh-Hant']` is derived programmatically from the finished
  `STRINGS['zh-Hans']` block, not translated independently a second time**
  — using `opencc-python-reimplemented`'s `s2t` (Simplified→Traditional)
  conversion profile, the same OpenCC engine Wikipedia and other major
  projects use for this exact conversion, run once at authoring time as a
  local script whose *output* (the literal `STRINGS['zh-Hant']` object)
  was committed to `dossiary.html` as plain text — a one-time authoring
  tool, never a runtime dependency; the app itself has no OpenCC
  dependency, and nothing about its zero-dependency, single-file nature
  changed. Simplified and Traditional Chinese are the same language with
  two different character sets, not two different languages, which is
  what makes derivation the right call specifically here — nothing else in
  `SUPPORTED_LANGS` has an equivalent relationship; Spanish and French were
  each translated independently, the ordinary way. Converting is both
  faster than a second from-scratch translation pass and, more
  importantly, *guarantees* the two scripts stay in lockstep — no risk of
  `zh-Hans` and `zh-Hant` drifting to say subtly different things for the
  same key over time, the way two independently-maintained translations
  could. The accepted tradeoff is that `zh-Hant`'s wording is exactly
  `zh-Hans`'s wording rendered in a different script, with no room for
  Traditional-specific phrasing choices (e.g. regional vocabulary
  differences between Taiwan and mainland usage) that an independent
  translation might have made — judged acceptable for this app's UI
  strings, which lean short and functional rather than idiomatic prose.
  `USER_GUIDE.zh-Hant.md` (see the User Guide vs. README note above) was
  derived the same way, for the same lockstep-consistency reason, from the
  finished `USER_GUIDE.zh-Hans.md` prose — with its embedded image paths
  corrected afterward by hand (from `docs/user-guide/zh-Hans/` to
  `docs/user-guide/zh-Hant/`, since converting prose doesn't touch
  relative image links correctly on its own) and its own
  independently-captured screenshot set, **not** shared with the
  Simplified guide's own screenshots — the running app renders different
  characters in each language state, so a screenshot captured under
  `zh-Hans` would show the wrong script if reused under `zh-Hant`.
