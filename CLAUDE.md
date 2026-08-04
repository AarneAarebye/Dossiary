# CLAUDE.md

Guidance for Claude (or Claude Code) when working in this repository.

## What this project is

A single-file, local-first, browser-based document archive app
(`dossiary.html`). No server, no backend, no build step, no
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
dossiary.html            The entire app (single file: HTML + CSS + JS)
scan_watch.py            Standalone watched-folder helper -- see its own note below
README.md               Usage docs, schema, and known limitations
CLAUDE.md                This file
CONTRIBUTING.md          Human-contributor guide (tests, conventions, PR expectations)
LICENSE                  MIT
.gitignore               Excludes personal library data from commits
tests/                   Playwright regression suite (38 scripts) + shared
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
  readable date rather than the raw ISO string). `fields` also has
  `show_as_column`/`autocomplete` capability flags (0/1) — see the
  generalized column/filter/sort/autocomplete system and per-field
  capability checkboxes described further below.
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
- **`.field input[type=date]{ color-scheme:dark; }`** exists for the same
  reason the DOCTYPE/quirks-mode note above does — an obscure default that
  "works fine" until someone actually looks closely. Without it, Chrome/
  Edge render the native calendar-picker icon (and the picker popup itself)
  using their light-mode default styling, since the browser has no way to
  know this page is dark themed otherwise — nothing else in this file sets
  `color-scheme` anywhere. The result is a dark-gray icon sitting directly
  on the date field's own dark `--ink-2` background: technically present,
  but close to invisible, reported as "the Date pickers are barely
  visible." `color-scheme: dark` tells the browser to draw its native
  form-control chrome (this icon, and the day-grid/month/year picker that
  opens from it) in dark mode instead, which is enough on its own — no
  `::-webkit-calendar-picker-indicator` filter hack needed. Scoped to
  `input[type=date]` specifically, not applied page-wide via `:root`; this
  app's dark theme is already handled by explicit CSS custom properties
  everywhere else, so a global `color-scheme: dark` would only be doing
  something for the handful of native browser controls (this icon, plus
  scrollbars) that don't already read from `--ink`/`--text` — narrower is
  safer than reaching for a page-wide flip that has no other purpose here.
- **`wireClearButton(inputId, clearBtnId)`** is a small, generic helper,
  wired to Category, Subcategory, Document Type, Payment method, People,
  Tags, Amount, and the toolbar's own search box in both forms (`f-*`/`e-*`
  + matching `*-clear` button) — clears an input and refocuses it,
  dispatching both a real `input` **and** `change` event, so whatever
  listener is already on the input fires exactly as it would from a manual
  edit regardless of which of the two it happens to listen for (Document
  Type's `applyDynamicFieldsForType()` listens for `change`; the search box
  listens for `input`, so results update live while typing, not just on
  blur — dispatching only one or the other would leave one of these two
  silently stale after a clear). Works the same for plain fields with no
  such listener (Amount, Category) — the dispatched events are just a
  no-op there. The search box's clear button (`#search-clear`, wrapped in
  the same `.field-with-clear`/`.clear-btn` markup as any other field, via
  a dedicated `.search-wrap` class carrying the toolbar's own
  `flex:1 1 240px` sizing since `.field-with-clear` itself has none) is
  wired with a plain one-off `wireClearButton('search', 'search-clear')`
  call — unlike the per-document-field ones, it isn't rebuilt per type
  change, so it doesn't need the People field's re-wire-after-rebuild
  treatment. **The People field is a special case**:
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
  for that type, not a diff). **Still deliberately doesn't create new
  custom fields itself** — only toggles/reorders existing `fields` rows.
  Field *creation* lives in the capture/edit forms instead (see
  `addInlineCustomField()` below) — a version that created fields here
  too was tried and deliberately reverted in favor of that, since it
  didn't fix the actual reported gap (an empty library has no document
  type to select here either, so this dialog's Fields column is stuck
  behind the same "select a type" gate no matter what). `default_document_type`
  (in `settings`) pre-fills `f-type` and immediately shows that type's
  configured fields when "Add document" opens
  (`applyDynamicFieldsForType('f', defaultDocumentType || '')` instead of
  always starting blank).
- **Creating a brand new custom field happens inline in the capture/edit
  forms** (`addInlineCustomField()`, `updateAddFieldVisibility()`,
  `wireAddFieldControls()`) — a "+ Add a custom field" toggle below the
  dynamic-fields container, hidden until a document type is entered (same
  gating as every other dynamic field: a custom field is always attached
  to *some* type). This is the one place in the app that creates a
  `fields` row from scratch outside of `migrate_to_new_library.py`, and it
  does so in the same motion as attaching it to whichever type is
  currently entered — unlike Field Settings' add-to-type flow (which
  operates on fields that already exist), creating and attaching aren't
  separate steps here, since the whole reason to reach for this instead
  of Field Settings is "I'm filling out this type right now and need a
  field for it." Type choices are Text/Number/Date/Checkbox only —
  deliberately no "Currency" option; a field needing a monetary value
  should use the built-in Amount field (with its own linked Currency, see
  below) instead of a second, disconnected custom field, and the mini-form
  shows a hint saying exactly that. A name collision with an existing
  field (or one of the built-in sentinel names) is rejected with a message
  pointing at Field Settings rather than silently attaching the existing
  field or creating a confusing duplicate — Field Settings' own Fields
  column already lists every existing field with a "+" for exactly that
  case, so duplicating that logic here wasn't worth it for what should be
  a rare collision. **Critical correctness property, tested explicitly**:
  adding a field appends only the new field's own input via
  `insertAdjacentHTML` — it deliberately does NOT call
  `applyDynamicFieldsForType()` to refresh the whole container, which
  would wipe out anything already typed into the *other* dynamic fields on
  the same in-progress document (capture has no saved values to fall back
  to at all; edit's rebuild always re-reads the original persisted
  `d.customFields`, discarding in-session edits, not what's currently on
  screen). Don't "simplify" this back to a full re-render without
  preserving that distinction. **A new Text-type field created this way
  defaults to `autocomplete: 1`** (`const autocomplete = type === 'text' ? 1
  : 0;` right before the `INSERT`) — it immediately gets the same
  suggestions-dropdown behavior Category/Type/Payment method already have
  (see `renderGenericFieldHtml()`/`populateDatalists()`), matching the
  built-in fields' UX without an extra trip to Field Settings. Number/Date/
  Checkbox fields get no such default — see
  `migrateTextFieldsAutocompleteDefault()` below for why a distinct-values
  dropdown doesn't suit those types.
- **`migrateTextFieldsAutocompleteDefault()`** (called from both
  `initNewLibrary()` and `loadDb()`, right after
  `migrateSentinelFieldsToGeneric()`) is a one-time-per-library backfill
  that flips `autocomplete` on for every already-existing Text-type field,
  so a library created before this default existed gets the same
  suggestions-dropdown UX a brand new custom text field gets automatically
  now (see the note above). Deliberately Text-only, for the same reason
  Amount/Date table columns never got filter dropdowns — a dropdown of
  distinct values doesn't suit Number/Date, and Checkbox is already a
  plain yes/no. **Tracked via an explicit `settings` row**
  (`text_autocomplete_default_migrated`), not an implicit data-shape check
  like `migrateSentinelFieldsToGeneric()` uses (`fieldNameToId['Payment
  method'] !== undefined`) — unlike that migration, there's no reliable way
  to tell "this field's autocomplete was never touched" apart from "a
  person deliberately switched it back off in Field Settings" just by
  looking at the `fields` table, since both look identical (`autocomplete =
  0`). Running this unconditionally on every open would silently re-enable
  a field someone had intentionally turned off; the explicit marker is what
  makes it safe to call unconditionally instead.
- **Amount, Currency, and Payment method used to be "sentinel" dynamic
  fields with dedicated `documents` columns (`amount`/`currency`/
  `payment_method`) and bespoke rendering — they're all plain rows in
  `fields` now** (`migrateSentinelFieldsToGeneric()`, run once per library
  open, idempotent by checking whether a `'Payment method'` row already
  exists). This was a real architectural shift, not just a rename: the old
  design made sense when this schema descended from Mariner's own
  receipt-centric `ZRECEIPT` table (`payment_method`/`amount` came straight
  from `ZRECEIPT.ZPAYMENTMETHOD`/`ZAMOUNT`, never through Mariner's generic
  `ZCUSTOMITEM` system — confirmed directly in `migrate_to_new_library.py`),
  but Dossiary itself isn't receipt-specific, so hardcoding them
  stopped making sense. **Payment method is now a completely ordinary
  field** — `renderPaymentFieldHtml()` is gone; it flows through
  `renderGenericFieldHtml()` and `applyDynamicFieldsForType()`'s generic
  per-field loop exactly like "Organization" would, with `show_as_column:1,
  autocomplete:1` set by the migration so it keeps its table column/filter/
  autocomplete (see the generalized column system below) without any
  Payment-method-specific code anywhere. **Amount and Currency keep one
  deliberate, narrow exception**: `show_as_column:0, autocomplete:0` (they
  opt OUT of the generic column system), because their *table column and
  detail-view line* stay intentionally combined into one "123.45 EUR"
  display (`formatAmount()`, reading `d.customFields['Amount']`/`['Currency']`,
  `parseFloat`'d since `document_field_values.value` is always text) rather
  than becoming two independent columns. Their capture/edit form inputs,
  however, are NOT specially paired anymore — each is a normal, independently-
  positioned `renderGenericFieldHtml()` field with its own clear button;
  the old side-by-side `.field-row` layout from `renderAmountFieldHtml()`
  is gone. Two narrow exceptions specifically for the field named
  `'Currency'` remain inside `renderGenericFieldHtml()` itself: it reuses
  the long-standing `currency-list` datalist (rather than the generic
  per-field `field-${id}-list` mechanism), and it still pre-fills from
  `defaultCurrency` as a dismissible guess on capture (amber `.field-guess`
  + hint, cleared on first `input`/`change`) — both are single `field.name
  === 'Currency'` checks, not the general mechanism. **The value-preservation
  correctness property is now free**: since all three fields flow through
  the same `readDynamicFieldValues()`/`document_field_values` save loop and
  `applyDynamicFieldsForType()`'s generic orphaned-field handling as any
  other custom field, "reclassifying to a type where a field isn't
  configured doesn't discard its value" falls out of existing, already-
  tested generic-field code — no more `el('e-amount') ? ... : d.amount`-
  style fallback needed anywhere.
- **The one-time backfill (`migrateSentinelFieldsToGeneric()`) is the
  first in-app data migration this codebase has ever had** (every prior
  `SCHEMA_MIGRATIONS` entry was purely additive — `ALTER TABLE ... ADD
  COLUMN`, no data movement). Called from both `initNewLibrary()` (so a
  brand new library starts with Payment method/Amount/Currency pre-defined,
  exactly as they were always implicitly available before — nothing to
  backfill, just the field definitions) and `loadDb()` (so an existing
  library's real `documents.payment_method`/`amount`/`currency` values get
  copied into `document_field_values`). **Critical backward-compatibility
  step**: for every existing `document_type_fields` row where `field_name
  = 'Amount'`, it also inserts one for `field_name = 'Currency'` at the
  same type if not already present — Currency previously had no
  independent per-type configuration at all (it rode along with Amount
  implicitly), so without this, every already-migrated library would
  suddenly lose the ability to *edit* Currency for types that could edit
  it before (display would still work, since display doesn't consult
  `document_type_fields` — only the edit/capture forms do). The old
  `documents.payment_method`/`amount`/`currency` columns are deliberately
  **never dropped or cleared** after backfilling — left as permanently
  unused, vestigial columns, matching this app's additive-only migration
  philosophy and avoiding any risk of silent data loss if a backfill step
  ever no-ops on some edge case. The sibling `migrate_to_new_library.py`
  was deliberately left untouched (still writes directly to the old
  columns) — this backfill runs on every library open regardless of how
  the old-shape data got there, so a fresh Mariner migration gets promoted
  to the generic system on first open in Dossiary exactly the same
  as a library that's had Dossiary's own old sentinel-field code
  write to it directly.
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
  guess treatment itself (`renderGenericFieldHtml()`'s `isCurrencyGuess =
  isCurrency && !existingValue && !!defaultCurrency && (prefix === 'f' ||
  (prefix === 'e' && amountFilled))`, where `isCurrency = field.name ===
  'Currency'`) mirrors the Date field's today-default exactly: `.field-guess`
  amber styling + a dismissible `.field-guess-hint`, cleared on the first
  `input` or `change` event on the currency input (both, since — unlike Date —
  Currency has its own clear button, whose `wireClearButton()` dispatches a
  `change` event that must also count as "touched"). **Edit guesses too, but
  only in one narrow case**: the document has a real, non-zero Amount already
  saved and no Currency saved — typically a document captured before a
  default currency was ever configured, or whose capture-time guess got
  cleared. `amountFilled` is computed once per `applyDynamicFieldsForType()`
  call from the document's own persisted `Amount` value (`existingValues['Amount']`,
  mirroring `formatAmount()`'s own `amount != 0` check almost exactly — `'0'`
  typed explicitly counts as "no real amount," same as blank), independent of
  whether Amount itself is currently configured/orphaned for the type being
  edited, and threaded through to both the normally-configured and orphaned
  `renderGenericFieldHtml()` call sites so an orphaned Currency field can
  still guess correctly. **Any other blank Currency in edit — no Amount
  saved at all, or Amount is `0`/blank — still never guesses**: that blank
  is the document's real, saved state, not something to paper over. This was
  a deliberate, explicit reversal of an earlier version of this same note
  ("Edit never guesses under any circumstances") — the earlier blanket rule
  turned out to be stricter than actually useful once real usage surfaced
  amount-only documents predating `default_currency`'s existence; the
  amount-gated version keeps the original "don't paper over real blank
  state" intent while actually closing that gap.
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
- **`applyDynamicFieldsForType()`'s `isEdit` parameter controls whether
  "orphaned" fields render** — a field with a real value in
  `d.customFields`/`d.people` that isn't in the current type's
  `document_type_fields` configuration (removed from that type's setup
  after the fact, or the document was reclassified to a type that never
  had it). Only the edit form passes `isEdit=true`; capture never has
  pre-existing values to orphan in the first place, so passing it there
  would be a no-op at best and confusing if it weren't. Orphaned fields
  are appended after the normally-configured ones and rendered with the
  same functions (`renderPeopleFieldHtml()` / `renderGenericFieldHtml()`,
  each now taking a trailing `orphaned` boolean — Payment method, Amount,
  and Currency are just entries in `d.customFields` now, so they fall into
  this one generic loop automatically rather than needing their own
  dedicated branches the way they used to) so they behave identically once
  on screen — same input types, same `data-field-id`/`data-dynamic-field`
  attributes, same save-time handling — the only difference is the
  `.field-orphaned` class and the `.field-orphaned-hint` note. **This is
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
- **Archiving** (`documents.archived`, `toggleArchived()`, the "Show
  archived" toolbar checkbox) is a reversible "no longer needed" flag, not
  deletion — **this app has no delete feature at all**, and archiving isn't
  a step toward adding one; it exists specifically so a document a person
  doesn't want cluttering their view anymore doesn't have to be destroyed to
  get out of the way. An archived document is hidden from the default
  table/search view — `applyFilters()` checks `d.archived && !showArchived`
  first, before every other filter, so an archived document can't leak into
  a category/search match by accident — until someone checks "Show
  archived" in the toolbar, at which point it reappears with a small
  `archived` pill next to its title (same spot as the existing "new"/"from
  inbox" pills). Nothing else about the document changes; toggling it is a
  single `UPDATE documents SET archived = ?` from the detail modal's
  Archive/Unarchive button, mirroring `regenerateThumbnail()`'s own
  update-in-memory → persist → `render()` → re-open-the-modal pattern.
  Deliberately a dedicated `documents` column, not a generic custom
  checkbox field — the generic fields system (see below) has no concept of
  "hidden from the view by default," only optional columns/filters that are
  always visible once configured, which doesn't fit what an archive needs
  to do.
- **Configurable columns/filters** (`FIELD_DEFS`, `visibleColumns`,
  `renderColumnsMenu()`, `applyColumnVisibility()`) work by toggling
  `display` on any element carrying a matching `data-field="<id>"`
  attribute — table headers, table cells (added fresh in every `render()`
  call, so `applyColumnVisibility()` runs again at the end of `render()`
  to reapply to the new cells), and the `<span class="filter-wrap">`
  wrapping each filter `<select>`. `FIELD_DEFS` only holds the fixed,
  built-in columns (Category, Type, People, Date, Imported, Amount, Tags)
  now — Payment method was removed from it and, since it's a plain
  `fields` row with `show_as_column:1`, flows through `dynamicColumnDefs()`
  instead: any field with `show_as_column` set gets appended as a dynamic
  tail after the fixed ones, id `field-${id}`, everywhere `FIELD_DEFS` is
  consulted (`[...FIELD_DEFS, ...dynamicColumnDefs()]` in
  `loadColumnSettings()`/`renderColumnsMenu()`). `applyColumnVisibility()`
  needed **no changes** to support this — it was already fully generic
  (`[data-field]` query), which is exactly why the split works. Dynamic
  `<th>`s are (re)built by `renderDynamicTableHead()` (called from
  `renderColumnsMenu()`) by removing any previous `[data-dynamic-column]`
  headers and appending fresh ones; there's deliberately **no per-header
  click wiring** for these — sort-on-click is delegated once, on
  `#doc-thead-row` itself (`e.target.closest('th[data-key]')`), specifically
  so newly-appended dynamic headers sort correctly without needing to be
  individually wired at creation time. `populateFilters()` similarly
  rebuilds an entire `<span id="dynamic-filters">` container every call
  (dynamic filters only for `show_as_column` fields where `hasFilter` is
  true — i.e. `type === 'text' || type === 'checkbox'`; Number/Date fields
  get a column but no filter dropdown, same reasoning as Date/Amount never
  having had one: a dropdown listing every distinct number/date isn't
  useful), and `currentFilters()`/`applyFilters()` read whatever dynamic
  `<select>`s currently exist via `document.querySelectorAll('#dynamic-filters select')`
  rather than named consts, so no code changes are needed as fields are
  flagged/unflagged. `sortDocs()` has a `sortKey.startsWith('field-')`
  branch: numeric compare for `type==='number'` fields, case-insensitive
  string compare otherwise. `populateDatalists()` follows the identical
  pattern for `autocomplete:1` text fields, rebuilding
  `<div id="dynamic-datalists">` with one `<datalist id="field-${id}-list">`
  per field; `renderGenericFieldHtml()` adds the matching `list=` attribute
  when `field.autocomplete` is set. If you add a new *fixed* (non-field-
  table) configurable column, you still need all three pieces the old note
  described: an entry in `FIELD_DEFS`, a `data-field` on the `<th>` (and
  matching `<td>`), and — if it has a filter — a `data-field`-wrapped
  `<span>` in the toolbar; missing any one means the toggle silently does
  nothing for that piece. The preference itself is stored in
  `library.sqlite`'s `settings` table (`INSERT OR REPLACE`, not the
  `ON CONFLICT ... DO UPDATE` upsert syntax — deliberately, since upsert
  support depends on the SQLite version sql.js happens to bundle, and
  `INSERT OR REPLACE` has been supported forever), not browser storage —
  keep it that way so the preference travels with the library folder.
- **Per-field capability checkboxes** (`toggleFieldCapability()`,
  `capabilitiesHtml()`/`wireCapabilities()` shared helpers inside
  `renderFieldSettingsFieldColumns()`) let a person flip a field's
  `show_as_column`/`autocomplete` flags directly in Field Settings — two
  small checkboxes ("Column", and "Autocomplete" for text-type fields
  only) rendered next to the field's name. **Deliberately shown in BOTH
  the Fields (available) and Display Fields (already-attached-to-this-type)
  columns**, via the same shared `capabilitiesHtml()`/`wireCapabilities()`
  helpers rather than only the Fields column — `show_as_column`/
  `autocomplete` are properties of the field itself, independent of
  `fsSelectedType`, so a field already attached to whichever type happens
  to be selected still needs a reachable way to toggle its own flags; the
  first version of this only rendered checkboxes in the Fields column and
  a field attached to every type in the library would have had no way to
  ever reach them. Not offered for `'People'` (not a `fields` row) or for
  `'Amount'`/`'Currency'` by name (their flags are deliberately kept off —
  see the sentinel-fields note above — so an editable checkbox that
  visibly did nothing would just be confusing).
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
  "Refresh" button is clicked, or the toolbar's always-visible **"📥 Check
  inbox" button** (`#inbox-check-btn`) is clicked, which calls `checkInbox()`
  then immediately opens the modal. That toolbar button exists specifically
  because the "Refresh" button and the banner's own "Review" button are only
  reachable from inside/via the banner — which only reflects whatever
  `checkInbox()` found the one time it runs automatically, at library-open.
  Without a toolbar entry point, a file a watched-folder helper (e.g.
  `scan_watch.py`) stages *after* someone already has the library open in
  their browser (the normal way people actually use it — leaving the tab
  open while scanning throughout the day) would have no visible way to be
  noticed short of fully reopening the library. This is still a single
  explicit click, not automatic polling — same "no silent writes" principle
  as everything else in this section, just a second, always-available door
  to the same `checkInbox()` call the banner already made once. Turning a staged file into an actual document
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

There's a real, runnable Playwright regression suite in `tests/` — **38
scripts covering most of the app's actual functionality**: capture, edit,
tags, people, subcategory, columns/filters (including persistence), OCR
(images and PDFs, both capture-time and edit-time, across every language
option, including edit-time OCR against every page of a multi-page PDF,
not just the first), PDF page count display (capture/edit/detail, and its
correct absence for image documents), searchable PDF generation,
thumbnails/previews (generation and regeneration), generic custom fields
(all four types), dynamic per-type field show/hide/reorder, Field Settings
(add/remove/reorder fields per type, default document type, the per-field
Column/Autocomplete capability checkboxes), creating a brand new custom
field inline from the capture/edit forms (visibility gating, reserved-name
and duplicate-name rejection, attaching to the current type, and — the
critical property — that it doesn't disturb values already typed into
other fields on the same in-progress document), the generalized custom-
field column/filter/sort/autocomplete system end-to-end on a fresh field
(not just Payment method), the `migrateSentinelFieldsToGeneric()` backfill
itself (an old-shape seeded library — `documents.payment_method`/`amount`/
`currency` populated, no `fields` rows for any of the three — correctly
promoted on open, including the `document_type_fields` Currency backfill
and idempotency across a reopen), Payment method/Amount/Currency now
flowing through the same generic-field machinery as any custom field
(including the value-preservation-when-hidden correctness property, which
now comes for free from the pre-existing generic mechanism rather than
needing its own fallback code), Payment Date as a genuine migrated custom
field, the detail view's conditional header, orphaned-field display and
editability in the Edit dialog, every clear button, the sticky table
header, the scan-hint toggle, the Libraries/licenses modal, sidecar file
content, the Inbox review flow (banner visibility, add-one and
add-all-with-defaults, the file moving from `inbox/` into `files/`, the
banner disappearing once empty, and the toolbar's "Check inbox" button
surfacing a file staged after the library was already open, which the
automatic once-at-open `checkInbox()` call alone would miss),
`migrateTextFieldsAutocompleteDefault()`
(a pre-existing text field's autocomplete flipped on by the one-time
backfill, a newly-created inline text field defaulting to it immediately
with no backfill needed, a newly-created inline number field correctly
*not* getting it, and — the critical idempotency property — a field
someone manually switches back off in Field Settings staying off across a
reopen of the same already-migrated library), archiving (hidden from the
default table/search view, reappearing with its pill once "Show archived"
is checked, a pre-`archived`-column document reading back as not-archived
rather than erroring, and archiving/unarchiving actually persisting), the
Date field's `color-scheme: dark` fix (asserted via `getComputedStyle` in
both the capture and edit forms, not just eyeballed), the Edit-form
Currency guess (an existing document with a real non-zero Amount and no
Currency saved gets guessed and flagged once a default currency is
configured; a document with no Amount, or Amount explicitly `0`, does
not; the guess is dismissed on touch same as everywhere else; and once
accepted and saved, the real value is never re-flagged as a guess on
reopen), and search across all of the above. This
list itself can go stale — if you add a test, or a feature loses its test,
update this paragraph in the same change; don't let this description
silently drift the way it once did (an earlier version of this section
described only two basic scenarios, long after the suite had grown well
past that).
Separately, and worth remembering: a single commit whose message described
itself as a trivial doc-only rename ("Update references to renamed
MarinerPaperlessTools repo") turned out, on closer inspection, to have
silently reverted **four** already-shipped, already-documented features at
once — the scan-hint toggle, the extra OCR languages, edit-time OCR's
multi-page support (back to first-page-only), and the PDF page count
feature entirely, deleting `tests/test_page_count.py` and 32 lines of
`tests/test_edit_ocr.py` along with it. It was built from a base that
predated the commits that added those features, and none of it showed up
as a conflict. The lesson: a commit message describing a small, obviously-
safe-sounding change (a rename, a reference update) is not a reliable
signal of its actual diff size or risk — if something regresses that a
commit's message gives no reason to suspect it touched, check that commit's
actual diff rather than trusting the message, especially for any commit
touching `dossiary.html` alongside doc files.

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
  sibling repo's `document_ledger.html`, since people may use both.
