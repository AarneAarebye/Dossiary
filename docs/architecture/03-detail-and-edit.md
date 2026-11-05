# Dossiary architecture notes: Detail view, editing, archive, review queue, waste bin

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

- **The detail view's header (`openDetail()`'s `modal-meta` block) shows
  Payment and Amount conditionally, not as always-present placeholder
  lines.** Computed just before the template string
  (`amountForHeader`/`hasAmountForHeader`/`paymentMethodForHeader`, read
  from `d.customFields` since both are plain generic fields now — see the
  sentinel-fields note above): `<b>Amount</b>` only appends onto the Date
  line when `hasAmountForHeader` is true; the whole `<b>Payment</b>` line
  only renders when `paymentMethodForHeader` is truthy. This intentionally
  differs from Category/Type/Date/Imported/ID, which always show (with a
  `—` placeholder when empty) — those aren't newly-optional per-type
  fields the way Amount/Payment are, so an empty placeholder there is
  still informative, whereas an empty Payment/Amount line would just be
  noise for a document whose type doesn't use them. The generic "Fields"
  section further down explicitly excludes `'Amount'`/`'Currency'`/
  `'Payment method'` from its own `Object.entries(d.customFields)` loop
  (they'd otherwise now show up there too, duplicating the header line).
- **The detail view also shows `File`/`Original` lines with each file's
  path**, prefixed with `rootDirHandle.name` — the same "as far as it can
  go" pattern as the Inbox status message's own folder label (see the Inbox
  note below): there's no browser API to reveal a file in the OS's file
  manager (Finder/Explorer/whatever Linux distro is running) or expose its
  absolute filesystem path, so a person who wants to find it manually gets
  the next best thing, a path they can navigate to themselves. `File` shows
  whenever `d.file_path` is set (effectively always, for anything with a
  file at all); `Original` shows whenever `d.original_file_path` is set —
  see "Preserving an original file on ingestion" below, this is now true
  for essentially every document captured or added via Inbox by this app
  (not just ones that went through searchable-PDF processing), since
  `writeOriginalToSubfolder()` preserves a raw original unconditionally.
  A document with no distinct original at all (e.g. a migrated document
  whose Mariner-sourced record never had one) simply has
  `original_file_path` left `NULL`, and the line doesn't render.
  Each line also gets a small
  **"Copy" button** (`copyPathToClipboard()`) next to the path, wired only
  when that path exists — unlike revealing a file in the OS's file manager
  or reading an absolute filesystem path (impossible from a browser tab,
  see above), the
  Clipboard API (`navigator.clipboard.writeText()`) has no such
  restriction from a regular page context, so this is a real, working
  affordance rather than another "as far as it can go" compromise.
  `fileFullPath`/`originalFullPath` are computed once and used for both
  the displayed text and the copied value, so they can't drift apart. The
  button shows "Copied!" for 1.5s (`.copy-path-btn.copied`, phosphor-green)
  before reverting to "Copy" — purely a UI nicety, not persisted anywhere.
  **Each line also shows its file's size** (`formatBytes()`, the same
  formatter Storage stats uses, in a `.path-size` span after the path's
  own Copy button -- Copy belongs to the path, so it stays right next to it) -- `File.size` from the same `getFile()` lookup
  `openDetail()` already makes for the PDF page count, plus one more for
  the original; a metadata read, not a content read. A path that's set
  but doesn't resolve shows `detailFileMissing` ("missing", `.path-missing`,
  red) instead -- the same condition Library check's broken-links section
  flags. Shown for both lines, not just the original, because the
  interesting comparison is usually active copy vs. original (a
  searchable PDF can be much larger or smaller than the scan it came
  from). Panel only -- a table column would mean a file lookup per row.
- **`applyDynamicFieldsForType()`'s `isEdit` parameter controls whether
  "orphaned" fields render** — a field with a real value in
  `d.customFields`/`d.personFieldValues` that isn't in the current type's
  `document_type_fields` configuration (removed from that type's setup
  after the fact, or the document was reclassified to a type that never
  had it). Only the edit form passes `isEdit=true`; capture never has
  pre-existing values to orphan in the first place, so passing it there
  would be a no-op at best and confusing if it weren't. Orphaned fields
  are appended after the normally-configured ones and rendered with the
  same functions (`renderPersonFieldHtml()` / `renderGenericFieldHtml()`,
  each now taking a trailing `orphaned` boolean) so they behave identically
  once on screen — same input types, same `data-field-id`/`data-dynamic-field`
  attributes, same save-time handling — the only difference is the
  `.field-orphaned` class and the `.field-orphaned-hint` note. Person-type
  fields (People included, now that it's a real field — see its own note
  above) get their own orphaned-detection loop over `existingPersonFieldValues`,
  parallel to but separate from the `existingValues`/`d.customFields` loop
  every other field type uses, since a person-type field's "does it have
  real data" check is "does its name array have entries", not "is its
  string value non-blank." **This is
  deliberate: an orphaned field needs to be exactly as editable/clearable
  as a configured one**, not a special read-only or half-functional
  state, since the entire point is giving someone the chance to actually
  fix or clear the data, not just see that it exists. This falls out of
  the existing save logic (`getShownFieldIds()`'s generic `[data-field-id]`
  query) for free, precisely because orphaned fields use the same
  rendering and the same DOM attributes as configured ones — don't add
  separate handling for them in the save path; if saving ever needs to
  special-case orphaned fields, something about this design has gone
  wrong. Re-selecting a type mid-edit re-evaluates which fields are
  orphaned against the *original* document's persisted values (`d.*`),
  not whatever's currently typed into the form — switching types back
  and forth during a single edit session doesn't lose track of what the
  document actually has.
- **A real debugging lesson from building this feature, worth remembering
  for future large refactors**: an earlier, incomplete attempt at this
  exact feature had left dead scaffolding in the file (a duplicate
  `defaultDocumentType` declaration, an unused `document_types` table, a
  `knownDocumentTypes` loader, a stray call to a function that no longer
  existed). The stray call caused `loadDocumentsFromDb()` to throw and
  silently abort partway through — breaking the columns menu and, for
  libraries loaded via `loadDb()` rather than a fresh `initNewLibrary()`,
  breaking the initial `render()` call too. **This did not show up in
  `pageerror`/`console` listeners in every test**, and a manual
  step-by-step reproduction of the *same* actions succeeded — because the
  manual repro didn't happen to trigger the one code path (loading an
  existing/seeded library, or opening the columns menu) that touched the
  broken line. The lesson: after deleting a function or variable during a
  refactor, grep the whole file for its name before trusting that syntax
  validation + a few manual clicks means it's fine — a stray reference
  can silently break a code path that isn't the one you happened to test
  by hand, and passing tests that route through a different, less-current
  stub file can mask it further (see the next note).
- **Not every test file was using the shared `stub_studio2.js`.**
  `test_studio.py` (the oldest test in this suite) had its own fully
  embedded, increasingly-stale copy of the fake File System Access API,
  missing tables added to the schema long after it was written. It's
  since been switched to use `stub_studio2.js` like every other test.
  If a new test file ever gets created by copying an old one, check it's
  reading `stub_studio2.js` rather than embedding its own stub — a
  second stale copy would silently stop testing against current behavior
  the same way this one did.
- **`runOcrForEdit()` is deliberately separate from `runOcr()`, not a
  shared function with a flag.** `runOcr()` (capture) operates on
  `pendingFile`, a not-yet-saved in-memory File, and requests
  `{blocks:true}` output because its result may get baked into a
  searchable PDF on save (see `buildSearchablePdf()`). `runOcrForEdit()`
  (now reached from the Edit form's "Make searchable" only for a document that
  is already searchable; otherwise the button queues background OCR, see the
  Background OCR note) operates on a document's actual saved file (resolved fresh via
  `resolveFileHandle(d.file_path)`), only refreshes `e-ocr-text`, and
  deliberately does **not** request word-position data or touch
  `file_path`/rebuild any PDF — consistent with editing being
  metadata-only (see the "Editing" note above). **Both `runOcrForEdit()`
  and `runOcr()` handle PDFs now** (see the "Searchable PDF generation"
  note's own 2026-09-22 PDF capture OCR amendment for `runOcr()`'s own PDF
  path) — the real remaining difference between them isn't PDF support
  itself, it's what each one does with the result: `runOcr()` requests the
  per-word position data and can rebuild the file into a searchable PDF at
  Save, `runOcrForEdit()` stays plain-text/metadata-only, exactly as the
  paragraph above already describes. `runOcrForEdit()`'s own PDF handling
  renders every page via `renderPdfPageToCanvas()` (a higher-resolution
  sibling of `generateThumbnail()`'s PDF path; OCR accuracy degrades badly
  at thumbnail resolution, so this is intentionally a separate function
  with its own `scale` parameter, not a shared one with a size flag),
  called once per page in a loop (`for(let pageNum = 1; pageNum <=
  pdf.numPages; pageNum++)`), with each page's recognized text joined
  together — not just the first page, see the "How this was tested"
  section's note on multi-page PDF OCR — and passes each resulting
  canvas straight to Tesseract, which accepts canvas elements directly
  as an image source. Capture-mode OCR was later extended to support PDFs
  too (the 2026-09-22 amendment referenced above), and it does exactly
  what this note used to only suggest doing: it reuses this same
  `renderPdfPageToCanvas()` helper rather than duplicating the pdf.js
  rendering logic a third time.
- **Editing** (`openEditForm()` / `saveEditedDocument()`) updates metadata
  only — `title` through `ocr_text` via a plain `UPDATE`, and tags/people
  via delete-then-reinsert of that document's links (not a diff), reusing
  the same find-or-create pattern as capture. It never touches `file_path`,
  `original_file_path`, `created_at`, `import_date`, `source`, or
  `source_legacy_id` — there's no file-replacement feature, deliberately
  out of scope so far. After saving, the sidecar `.txt` is rewritten via
  `sidecarBaseNameFromFilePath()`, which derives the base filename from the
  existing `file_path` rather than storing it separately — if the
  file-naming scheme in `saveNewDocument()` ever changes, this derivation
  needs to change with it, or edited documents will silently write their
  sidecar to the wrong name. Orphaned `tags`/`people` rows (a tag or person
  removed from every document that used it) are left in place rather than
  pruned — they're harmless unused lookup entries and still useful for
  datalist autocomplete; don't add *automatic* cleanup logic for this
  without a reason. The one sanctioned way to remove them is the explicit,
  `confirm()`-gated "Orphaned tags"/"Orphaned people" sections of the
  Library check modal (see that note further below) — a person-triggered
  action, never something saving an edit does on its own.
  **Every table row has a hover-revealed `.row-edit-btn` (✎)** next to its
  checkbox (`.row-edit-col`, a narrow column added specifically for it — see
  `applyColumnVisibility()`'s sibling `data-field` columns, this one has no
  `data-field` and is never hideable via the Columns menu) that jumps
  straight to `openEditForm()`, skipping `openDetail()` entirely — a
  same-view shortcut for the common case of wanting to edit right away,
  without a separate click through the detail view first. Present in every
  nav view uniformly (not just Inbox, where the idea originally came from —
  editing directly is generically useful regardless of a document's review
  state; and, since the panel follow-up, only below the 640px breakpoint —
  see the detail-panel note below), **except deleted documents**, where it's
  absent entirely, matching
  the detail view's own precedent of dropping Edit (not just disabling it)
  for anything already in the Waste bin. The button's own `<td>` carries
  `onclick="event.stopPropagation()"`, the same pattern the select-checkbox
  column already uses, so clicking it doesn't also fire the row's own
  click-to-`openDetail()` handler. **Cancel from an edit reached this way
  still lands on the detail view**, not back on the table — a deliberate,
  simplest-option choice: `openEditForm()`/`saveEditedDocument()` don't
  track how the form was opened, so Cancel keeps its one existing behavior
  (always `openDetail(id)`) regardless of entry point, rather than adding
  new state just to make Cancel's destination conditional.
- **Archiving** (`documents.archived`, `toggleArchived()`, the "Show
  archived" toolbar checkbox) is a reversible "no longer needed" flag, not
  deletion — **this app has no *permanent* delete feature at all** (see the
  Waste bin note below for the one, still-non-destructive, exception), and
  archiving isn't a step toward adding one; it exists specifically so a
  document a person doesn't want cluttering their view anymore doesn't have
  to be destroyed to get out of the way. An archived document is hidden
  from the All Documents nav view by default — `matchesView()` (see the
  "Top-level navigation" note below) checks `d.archived && !showArchived`
  for the `'all'` view, before any category/search filter, so an archived
  document can't leak into a match by accident — until someone checks
  "Show archived" in the toolbar (only shown for the `'all'` view — see
  below), at which point it reappears with a small `archived` pill next to
  its title (same spot as the existing "new"/"from inbox" pills). Nothing
  else about the document changes; toggling it is a single `UPDATE
  documents SET archived = ?` from the detail panel's Archive/Unarchive
  button, mirroring `regenerateThumbnail()`'s own update-in-memory →
  persist → `render()` → re-open-the-modal pattern. Deliberately a
  dedicated `documents` column, not a generic custom checkbox field — the
  generic fields system (see below) has no concept of "hidden from the
  view by default," only optional columns/filters that are always visible
  once configured, which doesn't fit what an archive needs to do.
  **The "📦 Archive" nav view** (`#nav-item-archive`, `data-view="archive"`,
  `matchesView()`'s `'archive'` branch: `!!d.archived`, after the shared
  deleted check) lists every archived document, flagged for review or not,
  with its own badge. Added because the badges didn't add up: an archived
  document counted in none of All Documents / Inbox / Waste bin, so a
  library of 1,355 showed 1333 + 7 + 14. Now All + Inbox + Archive + Waste
  bin equals the total (with "Show archived" off, which is only offered in
  All Documents). The bulk-action bar's Archive button reads Unarchive in
  this view and clears the flag (`bulkSetArchived(ids, currentView !==
  'archive')`). "Show archived" stays, for searching active and archived
  documents together.
- **Review queue** (`documents.needs_review`, `toggleNeedsReview()`, the
  Inbox nav item — `#nav-item-inbox`, `data-view="inbox"`) is a second,
  independent staging flag, built as a direct structural mirror of
  `archived` above — same `documents` column pattern, same `SCHEMA`/
  `SCHEMA_MIGRATIONS` treatment, same detail-panel toggle-button pattern
  (`review-toggle-btn`, "Flag for review" / "Done") — but serving a
  different purpose: not "no longer needed," but "not yet reviewed." This
  is the second stage of a two-stage lifecycle for inbox-imported
  documents — see the Inbox note further below for the first stage (raw
  files sitting in the `inbox/` folder, before they're documents at all;
  that feature's own "📥 Check inbox" button is deliberately unrelated to
  this Inbox *nav item*, down to the icon choice — see the "Top-level
  navigation" note for why 🚩, not 📥, was picked for this one, precisely
  to avoid the two being conflated). `addInboxFile()` sets `needs_review =
  1` on every document it creates, since an inbox-imported document
  deliberately has category, type, date, etc. left `NULL` rather than
  guessed (seeing "not listed at the top of the table" for an inbox import
  with no date was the original bug report that led to this feature — the
  fix isn't to guess a date, it's to put unreviewed documents somewhere a
  person actually notices them). Any document can be flagged, not just
  inbox-imported ones — the "Flag for review" button in the detail panel
  works on anything, mirroring the "mark all documents as needs_review"
  scope the person who requested this feature specifically asked for.
  **Only the explicit Done action clears the flag — saving an edit never
  does**, even though `openEditForm()` is reachable directly from a row's
  own detail view; this was a deliberate design call (not a limitation)
  specifically so someone doing an intermediate save on a document they're
  not fully done reviewing yet doesn't lose their place in the queue. A
  flagged document is excluded from the `'all'` nav view by `matchesView()`
  and shown instead when `currentView === 'inbox'`, via the same real
  `<table>` every other view renders through — see the "Top-level
  navigation" note below for how view membership, badge counts, and
  rendering all work; this note only covers `needs_review`'s own semantics
  and its interaction with `archived`.
  **`toggleNeedsReview()` has two call sites**: the detail panel's own
  toggle button (`async () => { await toggleNeedsReview(id); openDetail(id);
  }`, which refreshes in place), and the edit form's own "Save & Done"
  button (see its own note below, which closes the modal entirely instead)
  — the function itself doesn't need to guard against being invoked with
  no modal open either way, since both callers already handle their own
  post-toggle UI update. (An earlier version of this note said "a single
  call site now," true when the old review-queue UI's standalone Done
  button went away — no longer accurate once "Save & Done" added a second,
  legitimate one.)
  **"Save & Done" (`#save-done-btn`, only rendered inside `openEditForm()`
  when `d.needs_review` is true — same condition the detail view's own
  button already uses to decide "Flag for review" vs "Done")** lets someone
  finish a review in one click instead of two separate actions (Edit →
  Save changes → back to detail → Done) — and, unlike the standalone
  "Done" button (which reopens the detail view in place), it closes the
  modal entirely on success, revealing whatever table was already showing
  underneath (typically the Inbox queue, since `toggleNeedsReview()`'s own
  `render()` has already removed the now-finished document from it by the
  time the modal closes) — deliberately no forced navigation to the Inbox
  view specifically, so someone reviewing from a Collection view or
  elsewhere isn't yanked away from it. It does not weaken the "only an
  explicit action clears the flag, never an implicit save" rule above —
  it's a second, distinct explicit action a person chooses instead of
  plain "Save changes," not saving silently clearing the flag as a side
  effect; plain "Save changes" still never touches `needs_review`, exactly
  as before. Critically, it only clears the flag if the save actually
  succeeded: `saveEditedDocument()` used to swallow its own errors
  internally with no way for a caller to tell success from failure (every
  existing call site just fired it and moved on) — it now `return`s
  `true`/`false` from its existing success/catch paths, and "Save & Done"'s
  own handler checks that before calling `toggleNeedsReview()`, so a failed
  save leaves the document exactly as a failed plain "Save changes" already
  did: still flagged, still in the edit form, with the same error message.
  **`needs_review` and `archived` are fully independent flags, with zero
  automatic interaction in either direction** — flagging a document for
  review doesn't touch `archived`, and archiving one doesn't touch
  `needs_review`; per the explicit design call this was built to ("Archived
  is archived. If one wants to edit it, it would have to be brought back
  from archive."), un-archiving is the only sanctioned way back to an
  archived document, flagged or not. This has one real consequence worth
  being deliberate about: the `'inbox'` view's own `matchesView()` branch
  excludes archived documents — the queue is specifically for documents
  someone should be actively working through, and an archived one isn't
  that — so a document that's *both* archived and flagged would be
  reachable from **neither** the `'all'` view nor the `'inbox'` view if the
  `'all'` view's own exclusion of flagged documents were as unconditional
  as it first looks. The `!d.archived` carve-out in `matchesView()`'s
  `'all'`-view exclusion of `needs_review` documents is what prevents
  that: an archived+flagged document is governed by the archived check
  alone once "Show archived" is on, same as any other archived document,
  so un-archiving (the one sanctioned way back) still actually works
  instead of leading to a document nothing can reach. Don't simplify that
  condition without re-deriving this — it looks redundant with the
  `'inbox'` branch's own archived exclusion at a glance, but the two
  branches are guarding different views (`'inbox'` vs. `'all'`) and only
  one of them has the archived carve-out.
- **Waste bin** (`documents.deleted`, `toggleDeleted()`, the Waste bin nav
  item — `#nav-item-trash`, `data-view="trash"`) is a third independent
  staging flag, added on explicit request to give "delete" a real UI
  affordance without actually adding permanent deletion to an app that
  otherwise never destroys a person's data. It's a soft delete only —
  toggling it just flips the column, exactly like `archived`/`needs_review`;
  nothing on disk (`files/`, `thumbnails/`, the sidecar `.txt`) is ever
  touched, and **there is deliberately no "empty bin" action anywhere in
  this app** — the waste bin is the permanent, sole home for a deleted
  document, not a staging area with its own expiry.
  **`deleted` is the strongest of the three flags**, unlike the
  `archived`/`needs_review` relationship above, which is genuinely
  symmetric (each has its own carve-out for the other). A deleted document
  is unconditionally excluded from the `'all'` view — `matchesView()`
  checks `d.deleted` first, before any other view's logic, so it stays
  hidden from `'all'` **even with "Show archived" checked** — and from the
  `'inbox'` view too, regardless of `needs_review`. This is a deliberate
  asymmetry from the archived+needs_review case: there, "Show archived"
  had to be preserved as the one sanctioned way back to a document,
  because nothing else could reach it. Deletion doesn't need that same
  escape hatch, because it gets its own dedicated one instead — the
  `'trash'` nav view itself — so there's no equivalent risk of a document
  becoming unreachable from everywhere.
  `openDetail()` reflects this by degree, not just visibility: a deleted
  document's action bar drops Edit/Regenerate preview/Archive/Flag for
  review entirely (not shown disabled — genuinely absent from the DOM) and
  offers only Restore, since none of those other actions mean anything for
  a document that isn't reachable anywhere they'd matter until it's
  restored. `toggleDeleted()`, like `toggleNeedsReview()` above, now has a
  single call site — the detail panel's own button — and always refreshes
  in place; restoring from a `'trash'`-view row works by opening that
  row's detail view (the same `openDetail()` every other view's rows use)
  and clicking Restore there, rather than a dedicated inline restore
  button. The `'trash'` view is reached the same way as `'inbox'` or
  `'all'` — a click on its nav item, not a separate modal — see the
  "Top-level navigation" note below for why all three views were unified
  onto one shared table rather than each keeping its own bespoke
  rendering, as this feature and the review queue originally did. (A
  fourth nav view, Reports, was added later — see its own note below —
  but it deliberately renders its own aggregate view rather than sharing
  this table, so it isn't part of the three unified here.)
