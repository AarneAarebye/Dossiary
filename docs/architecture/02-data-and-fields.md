# Dossiary architecture notes: Data layer and fields: File System Access, sql.js, ids and uids, tags, people, custom fields, previews, forms

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

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
- **Stable uids** (`uid TEXT` on `documents`, `tags`, `people`, `fields`,
  `collections`, `collection_folders`, `document_splits`, `reminder_snoozes`;
  `derivedUid()`, `newUid()`, `migrateStableUids()`; spec
  `docs/superpowers/specs/2026-10-22-stable-uids-design.md`) give every record
  an identity that survives two Macs editing copies of one library, where the
  integer ids above collide. Existing rows get a UUID v5 of `<table>:<key>`
  (`documents:12`, `document_splits:12:0`, `reminder_snoozes:12:7`) in
  `DOSSIARY_UID_NAMESPACE`, so every copy computes the same value; new rows
  get `crypto.randomUUID()` (`newUid()`) in every INSERT -- except the built-in
  fields the migrations add, which get their derived uid, and reminder snoozes,
  always derived since the (document, field) pair is their identity. Export as
  library and "Copy the setup of" keep a row's uid (`withUid()` selects it only
  when the source has the column). `migrateStableUids()` runs on every open, after
  the other migrations, filling any missing uid with its derived value --
  also a row an older Dossiary on another Mac wrote without one -- and sets
  the `stable_uids_migrated` marker. **The namespace never changes**: a new
  one would give every existing row a different id. Integer ids stay the
  keys everything references; nothing looks rows up by uid yet. Saving the
  Edit form rewrites a document's split lines but keeps each kept position's
  uid. Accepted gap: an *older* Dossiary that deletes a tag/person and reuses
  its integer id leaves a row the next open derives the old uid for -- only
  this version's own inserts are guaranteed distinct.
- **Tag deduplication** happens via an in-memory `tagNameToId` map built at
  load time and updated on every new tag insert — not a `SELECT ... WHERE
  name = ?` round-trip per tag. This assumes single-writer, single-tab
  usage (true for this app's design); don't add multi-tab sync assumptions
  without addressing that this map can go stale across tabs.
- **People is a real, generic `fields` row now (`type: 'person'`), not a
  hardcoded sentinel** — `migratePeopleToGenericField()` promoted it the
  same way `migrateSentinelFieldsToGeneric()` promoted Payment method/
  Amount/Currency (see that note below), and for the same underlying
  reason: what used to be a special case turned out to generalize cleanly
  once there was a real second use for it — specifically, wanting
  independent multi-valued person-list fields beyond just "People" (e.g.
  "Author", "Collaborator"). A document can relate to more than one person
  **per person-type field**, backed by `document_field_people
  (document_id, field_id, person_id)` — a per-field generalization of the
  old singleton `document_people (document_id, person_id)`, which is now
  vestigial (see the migration note below for why it's kept, never
  dropped). `personNameToId`/the `people` table itself are unchanged and
  still shared globally across every person-type field — "Arne" as an
  Author and "Arne" in People are the same person, so autocomplete and
  search both work across all of them, not just whichever field a name
  first appeared in. Comma-separated input, found-or-created by name on
  save, same as it always worked for the one People field — multi-valued
  "&"-splitting (e.g. "Arne & Jana") only ever happened once, historically,
  in `migrate_to_new_library.py`'s own Python-side migration; this app's UI
  has only ever used commas. Don't regress any of this to a single
  `person TEXT` column on `documents`; an earlier version of this app did
  that for People specifically, and it was wrong for the same reason it
  would be wrong for Author or Collaborator now: Mariner's own source data
  has multi-person values, and a single string field makes "find every
  document Arne is part of" impossible for anything he shares with someone
  else. `renderPersonFieldHtml()` (generalized from a People-only
  `renderPeopleFieldHtml()`) follows `renderGenericFieldHtml()`'s id/
  data-attribute conventions exactly (`${prefix}-field-${field.id}`,
  `data-field-id`), so the generic clear-button wiring, `getShownFieldIds()`,
  and orphaned-field marking in `applyDynamicFieldsForType()` all apply to
  a person-type field automatically, with zero special-casing needed
  anywhere else in the form-handling code. People keeps its own
  permanently-fixed table column and filter dropdown exactly as before (it
  gets no Column checkbox, and `dynamicColumnDefs()` skips it by name even
  if its flag were set). **Every other person-type field (Author,
  Collaborator, ...) can be a table column and filter** via the ordinary
  `show_as_column` flag -- Field Settings offers it the Column checkbox
  (never Autocomplete, which stays text-only). `dynamicColumnDefs()` carries
  each field's `type`, so the table cell renders its names as pills, the
  filter lists each distinct name once (`personNamesFor(d, name)`, the one
  reader of `d.personFieldValues`), and `matchesCriteria()` treats a
  person-type dynamic filter as "includes this name", with "— Not set —"
  meaning no names at all -- the same semantics as the fixed People filter.
  The type is resolved by field name from `fieldDefs` there, since saved
  Smart Collection criteria store only `{label, value}`, so an author
  filter saved as a Smart Collection keeps working. Sorting compares the
  joined names; Reports already had a multi-valued breakdown path for
  person-type fields, which now simply gets reached once the column is on.
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
  handles three input types: `image/*` (direct canvas downscale),
  `application/pdf` (first page rendered via pdf.js) and RTF
  (`isRtfFile()`: type `text/rtf` or `application/rtf`, or a `.rtf`
  name) — anything else returns `null`, which is an expected, non-error
  outcome, not something to add more format branches for without being
  asked. RTF was added on request (most documents in Mariner-migrated
  libraries are RTF): `rtfFirstPageCanvas()` loads rtf.js (three bundles,
  pinned to `RTFJS_VERSION`, loaded in WMFJS, EMFJS, RTFJS order), draws
  the first A4 page in a hidden box and snapshots it through an SVG
  `foreignObject`; files over 2 MB, renders over 10 s and unreadable RTF
  return `null`. The design is
  `docs/superpowers/specs/2026-11-13-rtf-previews-design.md`. The pdf.js main
  library and its worker script **must be the exact same pinned CDN
  version** (`PDFJS_VERSION`) — pdf.js throws a hard error if they
  mismatch, so don't update one without the other.
  **The detail panel's own display of this preview is currently hidden
  behind `SHOW_DOCUMENT_PREVIEW` (`const`, declared right after
  `APP_VERSION`), a hardcoded developer-facing toggle, not a user-facing
  setting.** Off until there's a carousel/gallery-style view that would
  make a single static thumbnail worth its 110x140px of panel space
  again — see the `docs/superpowers/specs/2026-08-26-hide-document-preview-design.md`
  spec for the full reasoning. It gates exactly two things: the block in
  `openDetail()` that builds `thumbHtml` (when off, `thumbHtml` is `''`,
  not even the "no preview yet" empty-state placeholder, since that would
  still cost the same panel space), and the `regen-thumb` action
  descriptor in `buildDetailActions()` (when off, it's never added to the
  actions array, so "Generate preview"/"Regenerate preview" doesn't
  appear in the panel — it was already `panelOnly: true`, so it was never
  reachable from the row context menu regardless). Generation itself —
  `generateThumbnail()`/`writeThumbnail()` on capture and Inbox-add — is
  completely untouched by this flag and keeps running exactly as before,
  so `thumbnail_path` stays populated for every document captured while
  the toggle is off; reactivating the feature later needs no backfill,
  just flipping the constant back to `true`.
- **Dynamic per-type fields** (`typeFieldOrder`, `loadTypeFieldOrder()`,
  `applyDynamicFieldsForType()`, `renderGenericFieldHtml()`,
  `renderPersonFieldHtml()`) fully rebuild the capture/edit forms'
  `dynamic-fields-f`/`dynamic-fields-e` container's HTML from scratch
  whenever the document type changes, based on `document_type_fields` — a
  table this app only *reads*, never writes; `migrate_to_new_library.py`
  is the sole writer, populated by decoding Mariner's own
  `ZDATATYPE.ZFIELDORDERARRAY` (see that script's own notes for the
  decoding details). A document type **absent** from `document_type_fields`
  (a brand new type, or one from a library where this wasn't tracked)
  shows **none** of its custom fields, People included (People is a
  plain custom field now — see its own note above) — this deliberately
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
  unchecked box is meaningful data, not "empty"; also skips any
  person-type field, deferring to `readPersonFieldValues()` instead, since
  those are multi-valued rather than a single string) and `getShownFieldIds()`
  (every field currently rendered, regardless of value or type, needed so
  editing correctly clears a field the person emptied out —
  `readDynamicFieldValues()` alone can't tell "never had a value" apart
  from "just cleared it", and person-type fields need the same treatment).
  `readPersonFieldValues()` reads every rendered person-type field (People,
  Author, Collaborator, ...) as `[{fieldId, names}]` — generalized from a
  People-only `readDynamicPeopleValue()` the same way `renderPersonFieldHtml()`
  generalized from `renderPeopleFieldHtml()`. Like any other dynamic field,
  a given person-type field may not exist in the DOM at all if it isn't
  configured for the current type.
- **The capture form's date field is preset to today (`todayIsoDate()`,
  the local day -- it used the UTC day until v1.49, so just after midnight
  in Europe it pre-filled yesterday), but only in the capture form** — not the edit form, which correctly
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
- **Keyboard shortcuts** (`KEYBOARD_SHORTCUTS`, `openShortcutsModal()`,
  `markDoneAndAdvance()`, one `document` keydown listener) are aimed at
  working through the review queue: J/K or ↓/↑ move the selection (via the
  row's own click handler, so selection/highlight/panel stay one code
  path), Enter/O opens the file (the panel's own `open-file` action from
  `buildDetailActions()`), E edits, D is Done-and-next (only for a document
  still in review -- in the Inbox the finished one leaves the list, so
  "next" is whatever took its place), ? shows the list. Table keys never
  fire with a dialog open, in the Reports view, with a modifier held, or
  when focus is in a field, button or link (those keep their own
  Enter/Space). The Edit form adds Ctrl/⌘+Enter (Save) and
  Ctrl/⌘+Shift+Enter (Save & Done), which do work from inside its fields.
  The list lives behind "?" rather than a footer link, since the footer's
  height is part of `.table-wrap`'s max-height budget.
- **Suggested values from OCR text** (`suggestFromOcrText()`,
  `applyGuess()`, `applyOcrSuggestions()`) offer a likely date, amount
  and currency, read from a document's OCR text, as guesses with the same
  amber `.field-guess` look as the date preset above (plus an
  `.ocr-guess-hint` note), cleared on first edit. **When**: in the Edit form
  only for review-queue (`needs_review`) documents -- where fields are
  expected to be empty; an ordinary edit never quietly gains values -- and
  re-applied after a type change rebuilds the dynamic fields; and right
  after OCR runs, in both capture and Edit. **Never over a real value**: a
  guess only fills an empty field or replaces another guess (capture's
  "today", the default-currency guess, whose note it hides). Kept guesses
  save like typed values, the same as the date preset. **Deliberately
  conservative parsing**: the first plausible date in the text (ISO,
  `dd.mm.yyyy`/`yy`, `dd/mm/yyyy` -- day-first unless a part is > 12 or the
  UI language is English -- and de/en/fr/es/hy month names (Armenian also in its official
  `2026 թ. հոկտեմբերի 17` order), impossible dates
  skipped); an amount only from a line naming a total ("Gesamt", "Summe",
  "Total", "Betrag", "Amount due", "Ընդամենը", ... or the line after it, since OCR
  often splits label and figure), the largest such figure, with
  `1.234,56`/`1,234.56` both understood; the currency from that figure or
  the text, written the way the library already writes it (`€` vs `EUR`,
  `currencyInLibraryStyle()`). No sender/organization: too unreliable from
  free text. `window.__DEBUG_suggestFromOcrText` exposes the parser to
  `tests/test_ocr_suggestions.py`.
- **Autofill from earlier documents** (`findEarlierDocByTitle()`,
  `applyHistoryAutofill()`), Mariner Paperless's own "Auto fill receipt
  information from previous files": changing the Title to one an earlier,
  non-deleted document has (compared trimmed and case-insensitively, the
  way a merchant or sender name repeats) fills the empty fields from the
  most recently imported match -- Document Type first, via a real `change`
  event so the type's fields exist, then Category, Subcategory, Payment
  method and Currency -- each marked as a guess naming the source
  (`autofillHint`). Only fields that genuinely repeat per sender: never
  amounts, dates, notes or tags. Same scope rule as the OCR suggestions:
  always in capture (where the untouched default document type counts as
  replaceable), and in Edit only for review-queue documents. Both features
  share `applyGuess()`/`markGuess()`; a capture type change re-applies the
  OCR suggestions its rebuild would otherwise drop.
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
  change, so it doesn't need the re-wire-after-rebuild treatment every
  dynamic field does. **Every dynamic per-type field's clear button — text/
  number/date/checkbox fields and person-type fields (People, Author,
  Collaborator, ...) alike — gets re-wired the same generic way**: since
  `dynamic-fields-f`/`dynamic-fields-e`'s whole HTML is rebuilt from
  scratch on every document-type change (not fixed DOM elements), a single
  `container.querySelectorAll('.clear-btn')` pass at the end of
  `applyDynamicFieldsForType()` re-wires whatever's currently rendered,
  regardless of field type — there's no per-field-type special-casing
  needed here at all, and in particular no dedicated People-only re-wiring
  path (an earlier version of this note described one; it was already
  inaccurate even before People was generalized into a real field — the
  generic pass has covered People the same as everything else for a
  while). A field simply isn't in that `querySelectorAll` result at all if
  it isn't currently rendered (not configured for the selected type), same
  as any other dynamic field.
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
  for that type, not a diff). A type no document uses (`documentTypeInUse()`:
  every document in `allDocs`, Waste bin included, type names trimmed) that
  still has fields gets **Remove field setup** under the type list
  (`renderFieldSettingsTypeActions()`, `removeTypeFieldSetup()`): it deletes
  the type's `typeFieldOrder` key and rows, deselects it, and touches no field
  or value, so there is no confirmation. Removing such a type's last field
  with ✕ deletes the key too, so the type leaves the list at once instead of
  lingering as `typeFieldOrder[type] = []` until the next reload; a type typed
  into the form underneath (`fsExtraType`) stays listed and selected anyway,
  since `fieldSettingsTypes()` adds it regardless of `typeFieldOrder`. **Still deliberately doesn't create new
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
- **"Set up fields for this type…" in the capture and Edit forms**
  (`#f-type-fields-btn`/`#e-type-fields-btn`, under Document Type) opens
  Field Settings *above* the form rather than replacing it:
  `openFieldSettingsModal({selectType, onClose})` renders into a second
  layer, `#modal-root-over` (`modalOverRoot`), with its own
  `fs-modal-backdrop`/`fs-modal-close-btn` ids since the form underneath
  keeps `modal-backdrop`/`modal-close-btn`. The typed type is preselected and
  listed even when no document has it yet (`fsExtraType`,
  `fieldSettingsTypes()`), which the Tools-menu entry can't do for a
  brand-new type. Escape is caught in the capture phase
  (`stackedFieldSettingsKeydown`) so it closes only this layer (a field
  rename input still handles its own Escape first); `closeModal()` clears
  the layer without rebuilding anything. Closing runs the form's own
  rebuild through `rebuildDynamicFieldsKeepingInput()`: it snapshots every
  dynamic input by field id, rebuilds, and puts typed values back -- a guess
  stays a guess with its note, except the default-currency guess, which
  takes the rebuild's value since the default may just have changed. A field
  the new setup drops disappears (Edit still shows it as orphaned if the
  document has a saved value, with the typed value). Opened from the Tools
  menu, Field Settings behaves exactly as before.
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
  field for it." Type choices are Text/Number/Date/Checkbox/Person —
  deliberately no "Currency" option; a field needing a monetary value
  should use the built-in Amount field (with its own linked Currency, see
  below) instead of a second, disconnected custom field, and the mini-form
  shows a hint saying exactly that. A name collision with an existing
  field (or one of the built-in field names — People, Amount, Payment
  method) is rejected with a message pointing at Field Settings rather
  than silently attaching the existing field or creating a confusing
  duplicate — Field Settings' own Fields column already lists every
  existing field with a "+" for exactly that case, so duplicating that
  logic here wasn't worth it for what should be a rare collision.
  Dispatches to `renderPersonFieldHtml()` instead of
  `renderGenericFieldHtml()` when the chosen type is Person, same as
  `applyDynamicFieldsForType()`'s own dispatch. **Critical correctness
  property, tested explicitly**:
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
  Payment-method-specific code anywhere. **Amount alone keeps one
  deliberate, narrow exception**: `show_as_column:0, autocomplete:0` (it
  opts OUT of the generic column system), because its *table column and
  detail-view line* stay intentionally combined with Currency into one
  "123.45 EUR" display (`formatAmount()`, reading
  `d.customFields['Amount']`/`['Currency']`, `parseFloat`'d since
  `document_field_values.value` is always text) rather than becoming its
  own independent column. **Currency itself has since opted INTO the
  generic column system** (`show_as_column:1, autocomplete:1`, same as
  Payment method) — it gets its own optional table column, filter
  dropdown, and autocomplete datalist, entirely independent of the
  combined Amount/Currency display above, which keeps working unchanged
  regardless of whether Currency's own column happens to be toggled on.
  Both capture/edit form inputs are NOT specially paired — each is a normal,
  independently-positioned `renderGenericFieldHtml()` field with its own
  clear button; the old side-by-side `.field-row` layout from
  `renderAmountFieldHtml()` is gone. Two narrow exceptions specifically for
  the field named `'Currency'` remain inside `renderGenericFieldHtml()`
  itself: it reuses the long-standing `currency-list` datalist (rather than
  the generic per-field `field-${id}-list` mechanism, which still also
  gets generated for it as a harmless unused side effect of opting into
  the generic column system), and it still pre-fills from `defaultCurrency`
  as a dismissible guess on capture (amber `.field-guess` + hint, cleared
  on first `input`/`change`) — both are single `field.name === 'Currency'`
  checks, not the general mechanism. **The value-preservation
  correctness property is now free**: since all three fields flow through
  the same `readDynamicFieldValues()`/`document_field_values` save loop and
  `applyDynamicFieldsForType()`'s generic orphaned-field handling as any
  other custom field, "reclassifying to a type where a field isn't
  configured doesn't discard its value" falls out of existing, already-
  tested generic-field code — no more `el('e-amount') ? ... : d.amount`-
  style fallback needed anywhere.
- **The one-time backfill (`migrateSentinelFieldsToGeneric()`) was the
  first in-app data migration this codebase ever had** (every prior
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
- **`migratePeopleToGenericField()` followed the same precedent shortly
  after, promoting the 'People' sentinel into a real `fields` row
  (`type: 'person'`)** — the second in-app data migration this codebase
  has had, structured the same way (idempotent, checked via
  `fieldNameToId['People'] !== undefined`, called from both
  `initNewLibrary()` and `loadDb()`) but simpler in one respect and
  trickier in another. Simpler: unlike Amount/Currency, `document_type_fields`
  needed **no** migration of its own — its `field_name` column already
  stored the literal string `'People'` as a sentinel even before this
  change, and that string keeps matching unchanged now that `'People'` is
  a real field name instead of a special-cased one, so the generic
  per-field lookup in `applyDynamicFieldsForType()` just starts resolving
  it correctly the moment the old `if(fieldName === 'People')` branch is
  gone. Trickier: this promotes a many-to-many relationship, not a
  single-valued column, so the backfill copies `document_people`'s rows
  into a new, per-field `document_field_people (document_id, field_id,
  person_id)` table under the new field's id, rather than copying a
  scalar value into `document_field_values`. `document_people` itself is
  left in place afterward, unused — vestigial, same additive-only
  philosophy as the old `documents.payment_method`/`amount`/`currency`
  columns, never dropped in case a backfill step ever no-ops on some edge
  case. Idempotency relies on `'People'` already being a name
  `addInlineCustomField()` has always refused to let anyone create a
  same-named custom field with, even before this migration existed — so
  there's no need to guard against `fieldNameToId['People']` already
  pointing at some unrelated, wrong-typed field from before this feature
  existed; that was never possible.
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
