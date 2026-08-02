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
[`MarinerPaperlessTools`](https://github.com/AarneAarebye/MarinerPaperlessTools):
that repo's `migrate_to_new_library.py` produces the `library.sqlite` schema
this app expects, as a one-time conversion from a discontinued Mariner
Paperless library. But this app itself has no Mariner-specific logic or
dependency — don't reintroduce Core Data / `.paperless` package assumptions
here. If a change would only make sense for Mariner-migrated data, it
probably belongs in the other repo instead.

## Repository layout

```
document_studio.html   The entire app (single file: HTML + CSS + JS)
scan_watch.py            Standalone watched-folder helper -- see its own note below
README.md               Usage docs, schema, and known limitations
CLAUDE.md                This file
LICENSE                  MIT
.gitignore               Excludes personal library data from commits
tests/                   Playwright regression suite (30 scripts) + shared
                          browser-API stub — see "How this was tested" below
```

There's intentionally no `package.json`, bundler, or build step for the app
itself. Keep `document_studio.html` that way — the whole point is "download
one file, open it, it works." External libraries (sql.js, Tesseract.js) are
loaded from CDN at runtime via `<script src>`, not vendored or bundled.
`scan_watch.py` is the one deliberate exception to "single file" in this
repo: it's a separate, optional, stdlib-only companion script that never
gets loaded by the app and has no effect if you never run it — see its own
architecture note below for why it exists outside `document_studio.html`
rather than being folded into it.

## Architecture notes

- **`<!DOCTYPE html>` and `<meta charset="UTF-8">` at the very top are
  load-bearing, not boilerplate** — don't remove them thinking they're
  unnecessary for a file that isn't a "real" full HTML document. Without
  the DOCTYPE, the browser renders in quirks mode, which has an obscure
  legacy behavior where `<table>` elements don't inherit `color` from
  ancestors — this made every table cell render invisible (black text on
  the dark background) until it was diagnosed and fixed. Without the
  charset declaration, special characters (the footer's `©`/`·`, the
  `＋`/`✕` used elsewhere in the UI) rely on browser encoding-sniffing
  instead of a guarantee. Both bugs are the kind that "work fine" in quick
  testing and then fail unpredictably for someone else — keep both lines.
- **`.table-wrap` is a deliberate, bounded scroll container** (`overflow:auto`
  + `max-height:calc(100vh - 230px)`), not just "the table with horizontal
  scroll" it looks like at a glance. This exists specifically so `thead
  th`'s `position:sticky; top:0;` has something correct to stick to. The
  original version only had `overflow-x:auto` (no `overflow-y` set at
  all) — which looks harmless, but per the CSS Overflow spec, if one axis
  is anything other than `visible` and the other is left as `visible`,
  the browser silently forces the `visible` one to compute as `auto` too.
  That turned `.table-wrap` into an unintended vertical scroll container,
  which broke the sticky header — it stuck to the top of `.table-wrap`'s
  own (never-scrolling, since the *page* was scrolling instead) box
  rather than the viewport, so it just scrolled away like nothing was
  sticky at all. Setting `overflow-y: visible` explicitly does **not**
  fix this — the spec doesn't allow "one visible, one not" as a computed
  combination, so the browser overrides it back to `auto` regardless of
  what's literally written. The actual fix was to stop fighting that
  rule and lean into it: make `.table-wrap` an intentional, bounded
  scroll container for both axes, so sticky has exactly one clear,
  correctly-scrolling ancestor. If you ever need to adjust the header/
  toolbar layout, `230px` is calibrated against their current combined
  height — recalibrate it (verify empirically, e.g. checking
  `getBoundingClientRect()` on `thead th` before/after a large internal
  scroll stays roughly constant) rather than assuming a nearby value is
  still correct.
- **`OPEN_SOURCE_LIBRARIES`** (the array backing the footer's "Libraries"
  link/modal) lists exactly the CDN dependencies this file actually loads
  (`ensureTesseract()`, `ensureJsPdf()`, `ensurePdfJs()`, plus sql.js
  loaded unconditionally for the database itself) — keep it in sync if a
  dependency is added, removed, or swapped. The license for each was
  verified directly against its own repo's `LICENSE` file when this was
  written (sql.js MIT, Tesseract.js Apache-2.0, jsPDF MIT, pdf.js
  Apache-2.0), not assumed from general familiarity — if any of these
  ever change their license, or a new dependency gets added, verify the
  same way rather than guessing; this is exactly the kind of detail
  that's easy to get subtly wrong from memory.
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
- **People are structured exactly like tags** (`people` + `document_people`
  many-to-many, `personNameToId` map, comma-separated input in the capture
  form) — a document can relate to more than one person. Don't regress this
  to a single `person TEXT` column on `documents`; an earlier version of
  this app did that, and it was wrong: Mariner's own source data has
  multi-person values (e.g. "Arne & Jana"), and a single string field makes
  "find everything about Arne" impossible for any document he shares with
  someone else. If touching this, keep `migrate_to_new_library.py` in the
  sibling repo in sync — it does the equivalent split-on-`&` migration in
  Python.
- **`subcategory` is a flat, independent field, not nested under
  `category`** — despite the name, and despite what a naive redesign might
  assume. This matches Mariner's own schema (`ZSUBCATEGORY` has no foreign
  key to `ZCATEGORY`) and the real data (the same subcategory name appears
  under different categories on different documents). Don't build a
  category → subcategory cascading dropdown or similar hierarchy UI on the
  assumption that one is scoped to the other; it isn't, in the source data
  or here.
- **Custom fields (`fields` + `document_field_values`) are fully generic —
  not a fixed set of hardcoded columns.** This replaced an earlier design
  that had dedicated `organization`/`organization_to` columns on
  `documents`; that approach didn't scale once it became clear Mariner
  libraries can have 15+ real custom fields (Organization, Year, Date
  From, Paid, Reimbursable, ...), not just those two. `fields.type` is one
  of `'text'`/`'number'`/`'date'`/`'checkbox'`, confirmed empirically
  against real `ZCUSTOMRECEIPTITEM` data (see `migrate_to_new_library.py`'s
  own notes for how) — `renderGenericFieldHtml()` picks the input type
  from this, and `formatCustomFieldValue()` formats stored values for
  display accordingly (checkbox `'1'`/`'0'` → `Yes`/`No`, date → a
  readable date rather than the raw ISO string).
  **Do not apply people-style `&`-splitting to generic field values.**
  `people` is genuinely multi-valued in Mariner's own data (`"Arne &
  Jana"` means two people); most other fields aren't — real values like
  `"Dres. Ernestus & Cop, Sandhausen"` legitimately contain `&` as part of
  one name, and splitting would corrupt them. If a future field needs
  backfilling, check its actual `&`-containing values against real data
  before assuming either pattern.
- **Document previews** (`generateThumbnail()`, `writeThumbnail()`,
  `regenerateThumbnail()`) are stored as PNG files in a `thumbnails/`
  folder at the library root (`thumbnails/<id>.png`), not as BLOBs in
  `library.sqlite` — deliberately, to keep the database small and mirror
  the `files/`/`thumbnails/` split Mariner itself used. `migrate_to_new_library.py`
  populates `thumbnail_path` by copying Mariner's own `ZTHUMBNAILPATH` file
  directly during migration — it does **not** render anything client-side
  for migrated documents, and this app doesn't either unless someone
  explicitly clicks "Generate"/"Regenerate" preview. Don't add automatic
  bulk preview generation on library open; across several libraries with
  potentially thousands of documents each, silently rendering every
  missing preview on open would be slow and surprising. `generateThumbnail()`
  handles two input types only: `image/*` (direct canvas downscale) and
  `application/pdf` (first page rendered via pdf.js) — anything else
  returns `null`, which is an expected, non-error outcome, not something
  to add more format branches for without being asked. The pdf.js main
  library and its worker script **must be the exact same pinned CDN
  version** (`PDFJS_VERSION`) — pdf.js throws a hard error if they
  mismatch, so don't update one without the other.
- **Dynamic per-type fields** (`typeFieldOrder`, `loadTypeFieldOrder()`,
  `applyDynamicFieldsForType()`, `renderGenericFieldHtml()`,
  `renderPeopleFieldHtml()`) fully rebuild the capture/edit forms'
  `dynamic-fields-f`/`dynamic-fields-e` container's HTML from scratch
  whenever the document type changes, based on `document_type_fields` — a
  table this app only *reads*, never writes; `migrate_to_new_library.py`
  is the sole writer, populated by decoding Mariner's own
  `ZDATATYPE.ZFIELDORDERARRAY` (see that script's own notes for the
  decoding details). A document type **absent** from `document_type_fields`
  (a brand new type, or one from a library where this wasn't tracked)
  shows **none** of its custom fields or People — this deliberately
  matches Mariner's own behavior (a type shows nothing until fields are
  explicitly assigned to it), and is not a bug to "fix" with a
  show-everything fallback; an earlier version of this feature did exactly
  that (with a fixed 3-field set) and it was changed on purpose once the
  field set became fully generic and type-dependent.
  **Known, accepted limitation:** because the container is rebuilt from
  scratch (not just shown/hidden) on every type change, switching document
  types mid-capture does **not** preserve anything already typed into
  fields that get removed — this is a real regression from the old fixed
  3-field version (which could hide-without-losing since there were only
  ever 3 possible elements), traded off deliberately for supporting an
  arbitrary, type-dependent field set. Don't "fix" this without a real
  reason to invest in cross-rebuild value preservation; it wasn't judged
  worth the complexity for how the app is actually used (pick a type near
  the start of a capture, not partway through). The **edit** form doesn't
  have this problem in the same way — `saveEditedDocument()` always reads
  `d.customFields` (the document's actual persisted values) fresh on every
  type-change re-render, not values typed during the current edit session,
  so switching types back and forth during an edit correctly restores
  previously-saved values for fields that reappear.
  Saving reads the rendered form via `readDynamicFieldValues()` (skips
  blank text/number/date fields, but always includes checkboxes — an
  unchecked box is meaningful data, not "empty") and `getShownFieldIds()`
  (every field currently rendered, regardless of value, needed so editing
  correctly clears a field the person emptied out — `readDynamicFieldValues()`
  alone can't tell "never had a value" apart from "just cleared it").
  `readDynamicPeopleValue()` reads the People input specifically, which —
  like every other dynamic field — may not exist in the DOM at all if
  'People' isn't configured for the current type.
- **The capture form's date field is preset to today (`todayIsoDate()`),
  but only in the capture form** — not the edit form, which correctly
  pre-fills with the document's own existing date, a real value, not a
  guess. The preset is intentionally visually flagged (`.field-guess`
  class + `#f-date-hint`), cleared on the field's first `input` event,
  because `date` is the document's own content date (e.g. an invoice
  date), which is very often *not* today for anything that isn't
  freshly-received mail — unlike `import_date`, which genuinely is "now"
  and doesn't need a field or a guess at all. Don't extend this
  preset-and-flag pattern to `import_date` (it's already correct without
  one) or remove the visual flag thinking it's unnecessary friction — an
  unflagged default here would be a silently wrong date more often than
  a right one, for anyone working through a backlog of older documents.
- **`wireClearButton(inputId, clearBtnId)`** is a small, generic helper,
  wired to Category, Subcategory, Document Type, Payment method, People,
  Tags, and Amount in both forms (`f-*`/`e-*` + matching `*-clear`
  button) — clears an input and refocuses it, dispatching a real `change`
  event so whatever listener is already on the input (Document Type's
  `applyDynamicFieldsForType()` being the one that actually depends on
  this) fires exactly as it would from a manual edit. Works the same for
  plain fields with no such listener (Amount, Category) — the dispatched
  event is just a no-op there. **The People field is a special case**:
  since it's rendered dynamically inside `renderPeopleFieldHtml()`
  (rebuilt from scratch on every document-type change, not a fixed DOM
  element), its clear button has to be re-wired every time that HTML is
  rebuilt — done at the end of `applyDynamicFieldsForType()`, guarded by
  checking the People input actually exists first (it may not, if People
  isn't configured for the current type). If more dynamic per-type
  fields ever get clear buttons too, follow that same re-wire-after-rebuild
  pattern rather than assuming a one-time wire-up at form-open is enough.
- **Document Type is deliberately positioned right after the file/OCR
  section, styled via `.field-prominent`, in both forms** — not with
  Category, and not further down the form. This is intentional: it's the
  one field `applyDynamicFieldsForType()` actually depends on, so putting
  it early means the form's shape (which custom fields appear) is
  established before someone's deep into filling out the rest, rather
  than fields suddenly appearing below content they've already entered.
  If you reorder the form again, keep Document Type near the top — this
  was a deliberate UX fix, not an arbitrary ordering.
- **Field settings modal** (`openFieldSettingsModal()`, `manage-fields-btn`
  in the toolbar) manages `document_type_fields` directly, mirroring
  Mariner's own Document Types / Fields / Display Fields screen: pick a
  type (`getUsedDocumentTypes()` — union of types actually on a document
  and types already in `typeFieldOrder`, deliberately *not* every type
  that could theoretically exist), add/remove/reorder its fields
  (`addFieldToType()`/`removeFieldFromType()`/`moveFieldInType()`, each
  saving immediately via `persistTypeFieldOrder()` — delete-then-reinsert
  for that type, not a diff). **Deliberately doesn't create new custom
  fields** — only toggles/reorders existing `fields` rows; if that's ever
  wanted, it's new scope, not an extension of this dialog's existing
  behavior. `default_document_type` (in `settings`) pre-fills `f-type`
  and immediately shows that type's configured fields when "Add document"
  opens (`applyDynamicFieldsForType('f', defaultDocumentType || '')`
  instead of always starting blank).
- **Amount and Payment method are sentinel dynamic fields, exactly like
  People** (`renderAmountFieldHtml()`, `renderPaymentFieldHtml()`) —
  toggleable/reorderable per type via `document_type_fields` the same as
  any generic field or People, but their values still live in
  `documents.amount`/`documents.payment_method` (the typed columns they
  already had — `amount` is `REAL`), **not** in the generic
  `document_field_values` table. There was no reason to move that storage
  just to make them configurable; only the *visibility* needed to become
  dynamic. Mariner itself treated both as mandatory, always-shown fields
  with no per-type on/off signal to migrate (they're built into `ZRECEIPT`
  directly, not part of the `ZCUSTOMITEM`/`ZFIELDORDERARRAY` system the
  way named custom fields are) — `migrate_to_new_library.py` compensates
  by enabling both for every document type actually used by a migrated
  document, so nothing goes missing on migration; a person can then turn
  either off per type via this dialog if some type genuinely doesn't need
  it. **Critical correctness property, tested explicitly**: reclassifying
  a document to a type where Amount/Payment aren't configured must not
  discard the value already saved just because the input isn't currently
  rendered — `saveEditedDocument()` falls back to the document's existing
  `d.amount`/`d.payment_method` when `el('e-amount')`/`el('e-payment')`
  return `null` (field not in the DOM), rather than defaulting to blank/
  null the way a genuinely-cleared field would. Don't simplify this to
  "missing field means null" without preserving that distinction.
- **Currency (`documents.currency`) is a companion to Amount, not its own
  sentinel field.** `renderAmountFieldHtml()` renders both the Amount and
  Currency inputs together, inside one `.field` wrapper carrying a single
  `data-dynamic-field="Amount"` — so Currency has no independent entry in
  `document_type_fields` and can't be toggled on/off separately in Field
  Settings; it always shows/hides in lockstep with Amount, including
  through the same orphaned-field path (a document with a real, non-zero
  amount still shows the whole Amount+Currency block, marked
  `.field-orphaned`, even after being reclassified to a type that doesn't
  configure Amount — see the orphaned-fields note below; this is why
  `saveEditedDocument()`'s `el('e-currency') ? ... : d.currency` fallback
  is a genuine second line of defense, not the only thing keeping the
  value from being lost). Stored as free text (like Payment method), not a
  fixed dropdown — real libraries mix symbols ("€", "$") and ISO codes
  ("USD", "CHF"), and a fixed enum would force an artificial choice.
  `formatAmount()` displays it suffixed after the number ("123.45 EUR"),
  uniformly regardless of whether the value is a symbol or a code, since
  free text gives no reliable signal for prefix-vs-suffix placement per
  currency — don't try to special-case known symbols to prefix them
  without a real reason to invest in that. Sorting the Amount table column
  (`sortDocs()`) still sorts by the raw `amount` number only; there's no
  currency-aware conversion, which is an accepted simplification for a
  personal archive rather than an accounting tool.
- **`default_currency` (a `settings` row, exactly like `default_document_type`
  — `loadDefaultCurrency()`/`saveDefaultCurrency()`, configured via the same
  Field Settings modal) pre-fills new captures' Currency field as a
  dismissible guess, but stays unset until someone configures one.** Don't
  hardcode a literal currency (e.g. `'€'`) as the fallback instead of this
  setting, even though it might seem like a harmless convenience default —
  this app is a general-purpose, single-file, downloadable tool that
  anyone can grab, not code scoped to one person's library, so a fixed
  default would be silently wrong for anyone whose library isn't in that
  one currency, with no way to change it short of editing source. The
  guess treatment itself (`renderAmountFieldHtml()`'s `isGuess = prefix
  === 'f' && !existingCurrency && !!defaultCurrency`) mirrors the Date
  field's today-default exactly: `.field-guess` amber styling + a
  dismissible `.field-guess-hint`, cleared on the first `input` or
  `change` event on the currency input (both, since — unlike Date —
  Currency has its own clear button, whose `wireClearButton()` dispatches
  a `change` event that must also count as "touched"). Edit never guesses
  under any circumstances, configured default or not: a blank Currency
  there is the document's real, saved state, not something to paper over.
- **The detail view's header (`openDetail()`'s `modal-meta` block) shows
  Payment and Amount conditionally, not as always-present placeholder
  lines.** `<b>Amount</b>` only appends onto the Date line when
  `d.amount != null && d.amount !== 0`; the whole `<b>Payment</b>` line
  only renders when `d.payment_method` is truthy. This intentionally
  differs from Category/Type/Date/Imported/ID, which always show (with a
  `—` placeholder when empty) — those aren't newly-optional per-type
  fields the way Amount/Payment are, so an empty placeholder there is
  still informative, whereas an empty Payment/Amount line would just be
  noise for a document whose type doesn't use them. If more fields
  become sentinel/configurable like these two, apply the same
  has-a-value-or-don't-show-it treatment rather than defaulting to an
  always-shown placeholder line.
- **`applyDynamicFieldsForType()`'s `isEdit` parameter controls whether
  "orphaned" fields render** — a field with a real value in
  `d.customFields`/`d.people`/`d.amount`/`d.payment_method` that isn't in
  the current type's `document_type_fields` configuration (removed from
  that type's setup after the fact, or the document was reclassified to a
  type that never had it). Only the edit form passes `isEdit=true`;
  capture never has pre-existing values to orphan in the first place, so
  passing it there would be a no-op at best and confusing if it weren't.
  Orphaned fields are appended after the normally-configured ones and
  rendered with the same functions (`renderPeopleFieldHtml()` /
  `renderAmountFieldHtml()` / `renderPaymentFieldHtml()` /
  `renderGenericFieldHtml()`, each now taking a trailing `orphaned`
  boolean) so they behave identically once on screen — same input types,
  same `data-field-id`/`data-dynamic-field` attributes, same save-time
  handling — the only difference is the `.field-orphaned` class and the
  `.field-orphaned-hint` note. **This is deliberate: an orphaned field
  needs to be exactly as editable/clearable as a configured one**, not a
  special read-only or half-functional state, since the entire point is
  giving someone the chance to actually fix or clear the data, not just
  see that it exists. This falls out of the existing save logic
  (`getShownFieldIds()`, the `d.amount`/`d.payment_method` fallback in
  `saveEditedDocument()`) for free, precisely because orphaned fields use
  the same rendering and the same DOM attributes as configured ones —
  don't add separate handling for them in the save path; if saving ever
  needs to special-case orphaned fields, something about this design has
  gone wrong. Re-selecting a type mid-edit re-evaluates which fields are
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
  operates on a document's actual saved file (resolved fresh via
  `resolveFileHandle(d.file_path)`), only refreshes `e-ocr-text`, and
  deliberately does **not** request word-position data or touch
  `file_path`/rebuild any PDF — consistent with editing being
  metadata-only (see the "Editing" note above). **`runOcrForEdit()`
  handles PDFs, `runOcr()` doesn't** — it renders the first page via
  `renderPdfFirstPageToCanvas()` (a higher-resolution sibling of
  `generateThumbnail()`'s PDF path; OCR accuracy degrades badly at
  thumbnail resolution, so this is intentionally a separate function
  with its own `scale` parameter, not a shared one with a size flag) and
  passes the resulting canvas straight to Tesseract, which accepts canvas
  elements directly as an image source. If capture-mode OCR is ever
  extended to support PDFs too, reuse `renderPdfFirstPageToCanvas()`
  rather than duplicating the pdf.js rendering logic a third time.
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
  datalist autocomplete; don't add cleanup logic for this without a reason.
- **Configurable columns/filters** (`FIELD_DEFS`, `visibleColumns`,
  `renderColumnsMenu()`, `applyColumnVisibility()`) work by toggling
  `display` on any element carrying a matching `data-field="<id>"`
  attribute — table headers, table cells (added fresh in every `render()`
  call, so `applyColumnVisibility()` runs again at the end of `render()`
  to reapply to the new cells), and the `<span class="filter-wrap">`
  wrapping each filter `<select>`. If you add a new configurable field,
  you need **all three**: an entry in `FIELD_DEFS`, a `data-field` on the
  `<th>` (and matching `<td>` in `render()`'s row template), and — if it
  has a filter — a `data-field`-wrapped `<span>` around its `<select>` in
  the toolbar. Missing any one of these means the toggle silently does
  nothing for that piece. The preference itself is stored in
  `library.sqlite`'s `settings` table (`INSERT OR REPLACE`, not the
  `ON CONFLICT ... DO UPDATE` upsert syntax — deliberately, since upsert
  support depends on the SQLite version sql.js happens to bundle, and
  `INSERT OR REPLACE` has been supported forever), not browser storage —
  keep it that way so the preference travels with the library folder.
- **Schema upgrades for already-existing libraries.** `SCHEMA` uses
  `CREATE TABLE IF NOT EXISTS`, which is a no-op for a table that already
  exists — it does **not** retroactively add new columns to someone's
  existing `library.sqlite`. Any column added after the initial release
  needs a corresponding entry in `SCHEMA_MIGRATIONS` (an `ALTER TABLE ...
  ADD COLUMN ...` string), applied via `applySchemaMigrations()` right
  after opening an existing library, with the failure path (column already
  exists) silently ignored. `loadDb()` also immediately persists the
  upgraded schema back to disk rather than leaving the upgrade only in
  memory. If you add a new column, add the migration in the same change —
  don't just add it to `SCHEMA` and assume everyone's starting fresh;
  people have real libraries with real captured documents already.
- **OCR (Tesseract.js) only runs on images, not PDFs.** Recognizing a PDF
  would require first rendering its first page to a canvas client-side (e.g.
  via pdf.js) before handing it to Tesseract — not implemented. The UI
  disables the OCR button and explains this for PDF uploads; don't silently
  attempt OCR on a PDF file object, it will not work as expected.
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
- **Inbox** (`checkInbox()`, `openInboxModal()`, `addInboxFile()`,
  `addAllInboxFiles()`, the `#inbox-banner` element) reads a library's
  `inbox/` folder (a sibling of `library.sqlite` and `files/` at the library
  root) and offers one-click "add with defaults" for whatever's in it —
  mirroring legacy Mariner Paperless's own ScanSnap watch-folder integration
  (a scanned file showing up already filed, with the rest of the metadata
  left for later cleanup), but deliberately split into two pieces rather than
  a single background auto-import, for two reasons documented in more detail
  in "Working conventions" below: (1) this app is meant to be the library's
  sole writer to `library.sqlite` — it loads the whole database into memory
  and only writes it back out on an explicit save, so a second process
  inserting rows directly risks silently losing work to whichever side saved
  last; (2) every write is supposed to come from an explicit click, never
  from data that just showed up on disk. So `inbox/` is populated by
  something else entirely outside this file (see `scan_watch.py` below,
  though nothing stops a person from just dragging a file into that folder
  by hand) and this app never watches or polls it — `checkInbox()` only runs
  once, right after `afterDbReady()`, and again when the Inbox modal's
  "Refresh" button is clicked. Turning a staged file into an actual document
  always requires a click on "Add" or "Add all with defaults" inside this
  tab. An inbox-added document gets `source = 'scan-inbox'` (distinct from
  `'captured'` and `'migrated'`) and only two things set beyond the file
  itself: a filename-derived title, and `document_type` prefilled from
  `default_document_type` if one's configured (same intent as the capture
  form's own default-type prefill) — category, subcategory, payment method,
  amount, date, and notes are all left `NULL` rather than guessed, and no OCR
  runs automatically (that stays an explicit action from the Edit dialog's
  existing `runOcrForEdit()`, so a bulk "Add all" doesn't silently kick off a
  slow OCR pass per file). This mirrors `saveNewDocument()`'s file-copy/
  thumbnail/sidecar logic closely but isn't a shared function with it, since
  the two have different inputs (a form's DOM fields vs. nothing but a
  filename) and different defaults for nearly every column.
- **scan_watch.py** is the other half of Inbox, and is intentionally *not*
  part of `document_studio.html` — a stdlib-only Python script (no
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
- **Searchable PDF generation** (JPEG/PNG only): `runOcr()` requests
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
    Mariner Paperless itself used. When a searchable PDF *isn't* built
    (PDF upload, or an image format other than JPEG/PNG), the picked file
    is saved directly as `file_path` with `original_file_path` left `NULL`
    — there's no meaningfully separate "original" in that case.
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
- **No persistence of the folder handle across page reloads.** A person
  re-selects the library folder every session. This is a deliberate,
  accepted limitation (see README), not something to silently work around
  with `localStorage`/`indexedDB` — browser storage APIs beyond what the
  File System Access API itself provides are out of scope here.

## How this was tested (useful context for future changes)

There's a real, runnable Playwright regression suite in `tests/` — **30
scripts covering most of the app's actual functionality**: capture, edit,
tags, people, subcategory, columns/filters (including persistence), OCR
(images and PDFs, both capture-time and edit-time, across every language
option), searchable PDF generation, thumbnails/previews (generation and
regeneration), generic custom fields (all four types), dynamic per-type
field show/hide/reorder, Field Settings (add/remove/reorder fields per
type, default document type), Amount/Payment as configurable sentinel
fields (including the value-preservation-when-hidden correctness
property), Currency as Amount's companion field (shared visibility,
orphaned-together behavior, display formatting), Payment Date as a
genuine migrated custom field, the detail view's conditional header,
orphaned-field display and editability in the Edit dialog, every clear
button, the sticky table header, the scan-hint toggle, the Libraries/
licenses modal, sidecar file content, the Inbox review flow (banner
visibility, add-one and add-all-with-defaults, the file moving from
`inbox/` into `files/`, the banner disappearing once empty), and search
across all of the above. This list itself can go
stale — if you add a test, or a feature loses its test, update this
paragraph in the same change; don't let this description silently drift
the way it once did (an earlier version of this section described only
two basic scenarios, long after the suite had grown well past that — and,
separately, a stray revert once silently deleted two already-shipped,
already-documented features — the scan-hint toggle and the extra OCR
languages — with nothing catching it because neither had a test; that's
exactly the gap `test_scan_hint_and_ocr_languages.py` closes).

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
  clause (used by the settings lookup). If a future change sends the app's
  first `UPDATE`/`DELETE`/`SELECT` with a shape the stub doesn't recognize
  yet, extend the stub's regex matching rather than working around it —
  the whole point is exercising the app's real SQL strings.
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
