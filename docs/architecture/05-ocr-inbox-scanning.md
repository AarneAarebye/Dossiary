# Dossiary architecture notes: OCR, scanning hints, Inbox, drag and drop, scan_watch.py, the scan dialog

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

- **Schema upgrades for already-existing libraries.** `SCHEMA` uses
  `CREATE TABLE IF NOT EXISTS`, which is a no-op for a table that already
  exists — it does **not** retroactively add new columns to someone's
  existing `library.sqlite`. Any column added after the initial release
  needs a corresponding entry in `SCHEMA_MIGRATIONS` (an `ALTER TABLE ...
  ADD COLUMN ...` string), applied via `applySchemaMigrations()` right
  after opening an existing library, with the failure path (column already
  exists) silently ignored. `loadDb()` also immediately persists the
  upgraded schema back to disk rather than leaving the upgrade only in
  memory -- except in a synced library (see the saving note, "Saving in a synced
  library"), where it stays in memory until the next real save. If you add a new column, add the migration in the same change —
  don't just add it to `SCHEMA` and assume everyone's starting fresh;
  people have real libraries with real captured documents already.
- **OCR now runs on both images and PDFs** — see the 2026-09-22 PDF capture
  OCR amendment under "Searchable PDF generation" further below for the PDF
  path's own details (page-by-page rendering via `renderPdfPageToCanvas()`,
  the already-has-real-text skip check, and the multi-page searchable-PDF
  rebuild). This used to be images-only, with the OCR button hard-disabled
  for any PDF upload; don't reintroduce that restriction or assume a PDF
  file object silently fails OCR — it doesn't anymore.
- **OCR language options** (`#ocr-lang` in capture, `#e-ocr-lang` in edit —
  kept in sync, same option list in both) are just language codes passed to
  `Tesseract.createWorker(lang.split('+'))`; Tesseract.js resolves each code
  to a `.traineddata` file it downloads on demand, so adding a language is
  purely an `<option>` addition, no worker/recognition logic changes. `Auto`
  (`eng+deu`) recognizes against both trained models in one pass — deliberately
  **not** expanded to include French/Spanish/Chinese too, since combining more
  languages into one `recognize()` call means downloading and running against
  every model in the combo on every scan; the other languages are
  single-language-only options instead. `chi_tra` (Traditional Chinese) is
  labeled "Chinese (Traditional / Cantonese)" — verified directly against the
  `tesseract-ocr/tessdata`/`tessdata_fast` repos that there is **no** separate
  Cantonese (`yue`) trained model to add; Cantonese text uses the same
  traditional-character script `chi_tra` already covers. Don't add a `yue`
  option from memory/assumption — it would silently fail to download.
- **No direct scanner integration in the app itself** (`#scan-hint-toggle` /
  `#scan-hint` in the capture form only, not edit — editing never adds a new
  source file, see below). A browser has no API to control scanner hardware
  or launch a native app like Image Capture — this is a hard web-platform
  boundary, not something to "fix" by trying to shell out or invoke a URL
  scheme. The toggle only reveals static instructions (use Image Capture or
  Preview's Import from Scanner, save the result, then use the existing
  "click to choose a file" control) — it doesn't touch the filesystem itself,
  so it reuses `handlePickedFile()` with zero new file-handling code. For a
  more automated path, see the Inbox feature and `scan_watch.py` below — that
  helper is a separate native process, not something loaded into this page,
  precisely because a browser tab can't watch a folder in the background the
  way it does.
- **The scan-hint text is OS-aware** (`detectOS()`, `scanHintHtml()`) —
  it used to hardcode macOS instructions (Image Capture / Preview)
  unconditionally, which is simply wrong advice for anyone running Chrome or
  Edge on Windows, even though the app itself works there just as well (no
  native-code dependency at all — see "What this project is" above).
  `detectOS()` checks `navigator.userAgentData.platform` first (a clean,
  non-deprecated string on every Chromium build, and this app already
  requires Chrome/Edge), falling back to `navigator.platform`/
  `navigator.userAgent` substring matching for any Chromium build that
  hasn't rolled that API out yet. Returns `'macOS'`/`'Windows'`/`'Linux'`,
  or `''` if neither signal says anything recognizable — `scanHintHtml()`
  treats `''` and `'Linux'` the same way, a generic "use your scanner's own
  software" fallback, deliberately **not** guessing at a specific Linux
  scanning app (e.g. `simple-scan`) by name, since which one (if any) is
  installed varies far more on Linux than the reliably-present Image
  Capture/Windows Scan on their respective platforms. Computed once per
  `openCaptureModal()` call (OS doesn't change mid-session, so there's no
  need for this to be reactive) and interpolated directly into the
  `#scan-hint` template — the toggle-visibility wiring itself
  (`#scan-hint-toggle`'s click listener) is unchanged.
- **Inbox** (`checkInbox()`, `addInboxFile()`, `addAllInboxFiles()`,
  `addAllInboxFilesAndShowStatus()`, the `#inbox-banner` element) reads a
  library's `inbox/` folder (a sibling of `library.sqlite` and `files/` at
  the library root) and adds everything currently staged there directly,
  with no per-file review step — mirroring legacy Mariner Paperless's own
  ScanSnap watch-folder integration (a scanned file showing up already
  filed, with the rest of the metadata left for later cleanup), but
  deliberately split into two pieces rather than a single background
  auto-import, for two reasons documented in more detail in "Working
  conventions" below: (1) this app is meant to be the library's sole
  writer to `library.sqlite` — it loads the whole database into memory
  and only writes it back out on an explicit save, so a second process
  inserting rows directly risks silently losing work to whichever side
  saved last; (2) every write is supposed to come from an explicit click,
  never from data that just showed up on disk. So `inbox/` is populated by
  something else entirely outside this file (see `scan_watch.py` below,
  though nothing stops a person from just dragging a file into that folder
  by hand — **the folder itself is created for you** by both
  `initNewLibrary()` and `openLibrary()`'s existing-library path, right
  alongside the equivalent `files/` call; a real gap reported against an
  earlier version of this app, since `checkInbox()`'s own `getDirectoryHandle('inbox',
  { create: false })` deliberately never creates it — that's correct for
  *checking* (a missing folder just means "nothing to add, not an
  error"), but nothing else ever brought it into existence either, so a
  person couldn't actually drag a file in by hand, or point
  `scan_watch.py`'s `--drop-folder` at it directly, without first manually
  creating it in Finder/Explorer/their file manager. Creating an empty
  folder here doesn't conflict with the "no silent writes" principle
  below — no data is written, it's the same "ensure the expected
  structure exists" role `files/`'s own `{ create: true }` already plays)
  and this app never watches or polls it — `checkInbox()` only runs once,
  right after `afterDbReady()`, or when the toolbar's always-visible
  **"📥 Check inbox" button** (`#inbox-check-btn`) is clicked. That toolbar
  button exists specifically because the automatic once-at-open call is
  the *only* other thing that ever triggers a scan — a file a
  watched-folder helper (e.g. `scan_watch.py`) stages *after* someone
  already has the library open in their browser (the normal way people
  actually use it — leaving the tab open while scanning throughout the
  day) would have no visible way to be noticed short of fully reopening
  the library. This is still a single explicit click, not automatic
  polling — same "no silent writes" principle as everything else in this
  section.

  **Both entry points add everything staged, immediately, with no
  intermediate review step** — clicking `#inbox-check-btn` (after its own
  fresh `checkInbox()` scan) or the banner's own `#inbox-add-all-btn`
  ("Add all") both call the same `addAllInboxFilesAndShowStatus()`, which
  adds every currently-staged file via `addAllInboxFiles()`/`addInboxFile()`,
  and reports what happened on the status line
  (`"Added N document(s) to the review queue from <folder>/inbox/."`, with
  an error indicator and partial-failure message if any files failed to add).
  If at least one file was actually added, it also jumps to the 🚩 Inbox nav
  view so the newly needs-review-flagged documents are immediately visible
  (subject to any active search/filter text that might hide them, same as
  any other view — see the Top-level navigation note for how filters
  compose); a `checkInbox()` scan that finds nothing staged, or where every
  staged file fails to add, reports the appropriate status message instead
  without navigating anywhere — there's nothing new to look at in either
  case.
  This intentionally removed what used to be a review modal
  (`openInboxModal()`, listing each staged file with its own "Add" button
  plus an "Add all with defaults" button) — that extra confirmation step
  existed specifically so nothing got written without a person looking at
  it first, but now that the Waste bin (see its own note above) gives
  every write a safe, fully reversible undo path, it stopped pulling its
  weight: the click on "Check inbox" or "Add all" is already the explicit
  gesture that satisfies principle (2) above, a second confirming click on
  top of it was redundant. An inbox-added document gets
  `source = 'scan-inbox'` (distinct from `'captured'` and `'migrated'`)
  and only two things set beyond the file itself: a filename-derived
  title, and `document_type` prefilled from `default_document_type` if
  one's configured (same intent as the capture form's own default-type
  prefill) — category, subcategory, payment method, amount, date, and
  notes are all left `NULL` rather than guessed, and no OCR runs
  automatically (that stays an explicit action from the Edit dialog's
  existing `runOcrForEdit()`, so a bulk add doesn't silently kick off a
  slow OCR pass per file). **A PDF's own text layer is read, though**:
  `createReviewDocumentFromFile()` opens an added PDF with pdf.js from the
  bytes already in hand and runs `recordPdfTextLayer()`, so a scan a helper
  already OCR'd (scanix500 runs ocrmypdf) or a digital PDF arrives with its
  `ocr_text` filled and `text_checked`/`has_text_layer` set -- searchable
  and in its sidecar at once. Before this, every scanned PDF landed with
  empty OCR text until Library check's "Check for text" ran. Best-effort:
  a PDF pdf.js can't open is left unchecked. This mirrors `saveNewDocument()`'s file-copy/
  thumbnail/sidecar logic closely but isn't a shared function with it,
  since the two have different inputs (a form's DOM fields vs. nothing but
  a filename) and different defaults for nearly every column. The folder
  being read from is surfaced in the status-line message itself now
  (`${rootDirHandle.name}/inbox/`, plain text, not a link — the File
  System Access API exposes no absolute filesystem path for a
  `FileSystemDirectoryHandle`, only its own name, and there's no API to
  launch a native file manager from a browser tab, so this is
  deliberately as far as it can go) rather than a dedicated modal line,
  since there's no modal anymore; still useful to confirm at a glance that
  `scan_watch.py --library` is pointed at the folder you expect,
  especially with more than one library folder in play.
- **Drag-and-drop** (`createReviewDocumentFromFile()`, `addDroppedFiles()`,
  the `dragenter`/`dragover`/`dragleave`/`drop` listeners on `document`,
  `#drop-overlay`) is a third way to add a needs-review document, alongside
  capture and Inbox — drop one or more files anywhere on the page (while a
  library is open) and each becomes its own document with the exact same
  defaults Inbox uses: filename-derived title, `document_type` prefilled
  from `default_document_type` if configured, `needs_review = 1`, no OCR.
  The per-file creation logic (id reservation, file copy, original
  preservation, thumbnail, sidecar, `INSERT`, `allDocs` push) used to live
  entirely inside `addInboxFile()`; it's now `createReviewDocumentFromFile
  (file, source)`, a shared helper both `addInboxFile()` (passing
  `'scan-inbox'`) and `addDroppedFiles()` (passing `'dropped'`) call —
  `source` is the one thing that differs between an Inbox-staged file and a
  dropped one, and keeping it a real, distinct value (not reusing
  `'scan-inbox'`) keeps the two origins distinguishable in the data, the
  same reasoning `source` already gets applied for elsewhere (`'captured'`
  vs `'migrated'` vs `'scan-inbox'`). `addInboxFile()` itself is now a thin
  wrapper: call the shared helper, then do its own Inbox-specific cleanup
  (`inboxDirHandle.removeEntry()`, `pendingInboxFiles` filtering,
  `updateInboxBanner()`) that a dropped file has no equivalent of. A
  multi-file drop adds every file in one pass, `persistDb()`/`render()`
  reserved for the very end rather than once per file, for the same reason
  the bulk-action functions (see their own note above) skip a per-document
  round-trip. On any success it jumps to the 🚩 Inbox nav view, mirroring
  `addAllInboxFilesAndShowStatus()`; a drop that adds nothing (an empty
  drop, or every file failing) reports on the status line without
  navigating anywhere. **`#drop-overlay` is `pointer-events:none`** —
  deliberately, so it's purely visual and never itself becomes the
  `dragleave`/`drop` target instead of the real page underneath it, which
  is also why the show/hide logic uses a counter (`dragCounter`) rather
  than a plain boolean: `dragenter`/`dragleave` fire on every element
  boundary a dragged item crosses, including descendants, so naively
  showing on enter and hiding on leave flickers the overlay off every time
  the drag passes over a child element — counting enters against leaves
  and only hiding at zero is the standard fix. The whole feature is gated
  on `rootDirHandle` being set (a library open) — dragging over the
  empty-state screen is a deliberate no-op, not an error, since there's
  nowhere to save the file yet.
- **scan_watch.py** is the other half of Inbox, and is intentionally *not*
  part of `dossiary.html` — a stdlib-only Python script (no
  dependency to `pip install`), run separately, that watches a folder your
  scan software saves into (e.g. ScanSnap Home's own "save to folder"
  destination) and moves each file into a library's `inbox/` folder once its
  mtime has held steady for `--settle-seconds`, purely as a filesystem move.
  It never opens `library.sqlite`, assigns a document ID, or sets any
  metadata — see the Inbox note above for why that split matters. Its
  "stable" check is deliberately stateless across polls (just `now -
  mtime >= settle_seconds`, re-checked fresh every pass) rather than
  comparing against a previous poll's reading — that was a real bug caught
  while building this: an earlier version tracked "unchanged since last
  poll" in an in-memory dict, which meant a single `--once` invocation could
  never stage anything, since every fresh process starts with an empty dict
  and therefore always treats every file as newly-seen on its first (and
  only) pass.
- **Scanning: the scan dialog and its helpers** (`openScanDialog()`,
  `discoverScanHelpers()`, `startScanFromDialog()`; spec
  `docs/superpowers/specs/2026-10-09-system-scanner-helper-design.md`,
  section 2; wire format in dossiary-scan-helper's `PROTOCOL.md`). A browser
  can't reach a scanner (see "No direct scanner integration" above), so a
  small helper app on the computer does the scanning and Dossiary talks to
  it over `fetch()`: scanix500 on `localhost:8765` (version 2 since
  scanix500 0.4.0, its iX500 listed as `sane:ix500` with its real settings;
  a scanix500 before 0.4.0 speaks version 1 and gets one fixed "ScanSnap
  iX500" entry, `V1_SCANNER`) and dossiary-scan-helper on `localhost:8766`
  (version 2: `GET /scanners`, JSON `POST /scan`). The Field Settings address (`scan_bridge_url`) is
  probed too, for a helper on another port. **Only loopback addresses
  count** (`normalizeHelperUrl()`: `http://localhost`, `http://127.0.0.1` or
  `http://[::1]`, optional port 1-65535; anything else is `null`): helpers
  listen on 127.0.0.1 only, and a pairing token and scanned pages travel
  over plain HTTP, so an address on another machine -- typed in Field
  Settings, or copied with a library's setup -- is never contacted, and the
  dialog's "Look again" refuses it. **Discovery**
  (`probeScanHelper()`, `loadHelperScanners()`) uses a 3 s `/health`
  timeout; a health with `protocol: 2` is version 2, one with
  `service: 'scanix500-bridge'` version 1, anything else is ignored.
  **📷 Scan opens the dialog**: every found scanner (a duplicated name gets
  its helper in brackets), and only the settings the chosen one supports --
  source, two-sided (only a duplex feeder), color, resolution, and the
  extras Dossiary knows (`splitOnBlank`, `skipBlankPages`; unknown ones are
  never shown or sent). Without remembered settings for the chosen scanner,
  two-sided and skip blank pages start ticked where offered -- what
  scanix500 always did before the dialog (the protocol's own defaults are
  both off). The last scanner and settings are remembered per
  library (`scan_last_settings`); a gone scanner falls back to the first.
  **The scan request has no timeout** (a feeder batch can take minutes);
  while it runs the dialog's button reads "Scanning…", the dialog and the
  status line count the time up ("Scanning… 1:12", with a note that big
  batches and OCR take minutes -- the request gives no progress, so this is
  what keeps a long scan from looking stuck; real step-by-step progress would
  need a protocol endpoint), and Escape, backdrop and close are blocked
  (`scanDialogRunning`). Results, in either wire
  format (`decodeScanFiles()`), go through `writeScanFilesToInbox()` →
  `checkInbox()` → `addAllInboxFilesAndShowStatus()`, like any staged file;
  a `partial` result does the same, then shows the helper's message. A
  failure keeps the dialog open with the helper's message. **The files are
  written before the dialog closes**: a version 2 helper keeps no copy, so
  if `inbox/` can't be written the dialog stays open with
  `fileErrorText()`'s message naming the file and the reason, and nothing
  is lost that a second scan can't redo. Remembering the settings
  (`saveLastScanSettings()`) is best-effort -- a read-only `library.sqlite`
  doesn't stop the scan -- and any other error ends as a "Scan failed"
  message, never a status line stuck on "Scanning…". A pairing token is
  stored as soon as `/pair` answers, even if the dialog was redrawn
  meanwhile (another helper's pairing, a 401), since the code is used up by
  then.
  **Photos (2026-10-24)** (spec
  `docs/superpowers/specs/2026-10-24-scan-dialog-photos-design.md`): a
  scanner that lists `formats` (pdf/jpeg/png) and `areas`
  (full/a4/a5/a6/10x15/13x18) gets a Format and a Paper size select (shown
  when there is more than one value; ids `scan-dialog-format`/`-area`,
  wrappers `-field`). Both are hidden with the feeder as source: images only
  come from the flatbed (the helpers refuse them from a feeder), so the
  request says `pdf` and carries no `area`. Black & white is not offered
  with JPEG. For the standard areas `scanResolutionsFor()` hides resolutions
  over the helpers' 100-megapixel limit (`SCAN_MAX_PIXELS`, inclusive;
  `scanPixelCount()` = round(w/25.4*dpi)*round(h/25.4*dpi), sizes in
  `SCAN_AREA_MM`); `full` has no known size, so nothing is filtered and a
  helper's 422 message is shown. The request has `area` for a flatbed scan
  on a scanner with areas, and `ocr` only for PDFs; a scanned image has no
  `ocrJob`, so `queueScanOcr()` queues it for Dossiary's own OCR when
  `scan_auto_ocr` is on, and it ends as a searchable PDF with the image kept
  as the original. `scan_last_settings` gains `format` only for a
  scanner that lists more than one format, and `area` whenever the scanner
  lists any area (`readScanDialogSettings()`), so older saved objects and
  helpers without the fields are unchanged.
  **Background OCR (2026-10-11)**: when `scan_auto_ocr` is on (default;
  Field Settings, with `scan_ocr_language`, default Auto = eng+deu), a scan
  asks a helper that offers `ocr` to make the pages searchable
  (`ocr: true`, `ocrLanguages` the setting's codes the scanner supports) and
  returns at once; each file's `ocrJob` goes into `ocr_jobs (document_id,
  helper_url, job_id, file_hash, created_at)` by `queueScanOcr()`. `job_id`
  NULL means "waiting for Dossiary's own OCR": a scan with no `ocrJob` and no
  text layer of its own. The runner (`startOcrJobRunner()`, a 3 s timer, one
  `runOcrJobPass()` at a time, one fallback OCR at a time) starts after a
  scan and when a library opens with rows, and stops in `resetAll()` or when
  the last row goes. A pass polls `GET /ocr/<job>`: 202 keeps waiting; 200
  swaps the searchable PDF in through `replaceActiveFile()` (the original is
  kept) -- but only if the active file still has the job's `file_hash`,
  otherwise "Edit pages…"/"Combine…" changed it and the result is discarded
  for the fallback. Fallback triggers: 404/500, a bad answer, a failed swap,
  and a helper unreachable (network error or 401) for 10 minutes
  (`ocrUnreachableSince` is in memory, so polling never rewrites
  `library.sqlite`; that is why there is no `last_reached_at` column). The
  fallback is `makeDocumentSearchable()` with the row's `ocr_language` (else
  the setting's language), run only while the setting is on -- for scan rows;
  the pill "Making searchable…" (`ocrPendingDocIds`) marks pending documents
  in table, grid and panel. **The Edit form's "Make searchable" button
  (`#e-run-ocr-btn`, formerly "Run OCR") queues a row too**
  (`queueEditOcr()`: `job_id` NULL, `requested_by = 'edit'`, `ocr_language`
  = the form's language; `ocr_jobs` gained both columns, with
  `SCHEMA_MIGRATIONS` entries; scan rows are `requested_by = 'scan'`).
  `isActiveOcrRow()`: an `'edit'` row runs and shows whatever the scan
  setting says, since it was asked for; the setting governs scans only.
  The form locks the OCR text box with `editOcrQueuedNote` (also when
  reopened while a row exists) and `saveEditedDocument()` keeps the saved
  `ocr_text` while a row is pending, so the stale box can't erase what the
  job writes. A document that is already searchable (`canMakeSearchable()`
  false) keeps the instant `runOcrForEdit()` read. A deleted document's row
  is dropped (panel/bulk Delete, and by a pass for raw updates like
  Combine's). Every await checks `rootDirHandle` is still the starting
  library, and the fallback passes `isStale` into `makeDocumentSearchable()`
  so a library switch writes nothing. **Why this doesn't break "every write
  is an explicit action"**: the work starts from an explicit Scan or Make
  searchable click, the scan part is governed by a setting, it only touches
  files that scan created or the document that was clicked, the original is
  always kept, and a queued Edit job resumes after reopening the library.
  A helper swap leaves `searchable_pdf_built` 0 on purpose (that flag means
  Dossiary built the file); `has_text_layer` marks it searchable. **Guards**:
  `performScanRequest()` remembers the library root before its awaits and
  neither queues nor continues if it changed (`queueScanOcr()` takes the root
  too and returns 0 on a mismatch, since the ids belong to the old library);
  `canEditPages()`, `canCombine()` and `canMakeSearchable()` refuse a
  document with an active `ocr_jobs` row (`isOcrPendingDoc()`, which also
  consults the table, since the in-memory set can lag a freshly queued row),
  because the job's later result would rebuild from the old pages and undo
  the edit -- the fallback itself uses `canMakeSearchableBase()`;
  `saveEditedDocument()` with the OCR box locked leaves `ocr_text` out of the
  UPDATE and the in-memory copy, so a job finishing during Save's awaits
  isn't overwritten; the fallback's `persistDb()` is try/catch'd (read-only
  `library.sqlite`). Spec
  `docs/superpowers/specs/2026-10-11-background-scan-ocr-design.md`, wire
  format in dossiary-scan-helper's `PROTOCOL.md`. **Pairing**:
  `Origin: null` can't tell this `file://` page from a sandboxed iframe on
  any website, so each browser pairs once per helper: a helper whose
  `/health` says `paired: false` shows a code field in the dialog
  (`submitInlinePairing()`, `POST /pair` `{code, client: 'Dossiary'}`), and
  the token is kept in `localStorage` (`dossiary_scan_tokens`, keyed by the
  helper's address -- per browser, not per library). `Authorization:
  Bearer <token>` is only sent when there is a token: a pre-0.3.0
  scanix500 (no `paired` field, counts as paired) rejects the preflight for
  that header. A 401 drops the token and brings the code field back.
  **One Scan button since v1.51** -- the separate 📸 Scan Multi button
  (the dialog with split on blank pages ticked, shown only while a scanner
  could split) was merged into the dialog's own checkbox: it differed from
  Scan only in that one tick. The option reads "Split the stack at blank
  sheets" (a whole blank sheet, not a blank page, is the separator), and
  its always-visible hint (`#scan-split-hint`) starts with "Scan Multi:"
  for former Mariner Paperless users (the hint doesn't name Paperless); "Skip blank pages" has its own hint
  (`#scan-skip-hint`, the blank backs of one-sided letters). Ticking split also ticks
  "Skip blank pages" (untickable again), because in scanix500
  (`blank_filter.py`) a sheet blank on every side is the separator and is
  dropped, while other blank pages -- the blank backs of one-sided
  letters -- are kept unless skip is on; split alone is rarely what anyone
  wants. A scanner offering both gets a folded "What do these options
  do?" table of the four combinations (`#scan-options-help-toggle`,
  `#scan-options-help`; its CSS overrides the document table's global
  `table`/`thead th` rules, whose `min-width:800px` and sticky header
  would otherwise leak in). While split is ticked the start button reads "Scan and split"
  (`syncScanStartLabel()`/`scanStartLabel()`), since split is remembered
  with the scanner's settings and quietly turns one stack into several
  documents. A library whose `hidden_toolbar_buttons` still lists
  `scan-multi` is unaffected (unknown keys are ignored). With Scan Multi's
  availability check gone, opening a library no longer contacts any scan
  helper; discovery happens only when the dialog opens. **Nothing found** explains what to
  install, links dossiary-scan-helper's releases and scanix500, and offers
  the address field with "Look again". **Tests**: the shared stub fails
  every request to another localhost origin, so no test reaches a real
  helper on the machine; `tests/test_scan_dialog.py` fakes helpers per
  scenario, and `tests/manual_scan_reference_helper.py` checks against the
  real reference helper by hand.
