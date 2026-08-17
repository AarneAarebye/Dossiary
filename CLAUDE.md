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
[`LibraryLifeboat`](https://github.com/AarneAarebye/LibraryLifeboat)
(formerly MarinerPaperlessTools):
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
README.md                Usage docs, schema, and known limitations
README.de.md             German translation of README.md
USER_GUIDE.md            Non-technical beginner guide, linked from README.md
USER_GUIDE.de.md         German translation of USER_GUIDE.md
docs/user-guide/         Screenshots for USER_GUIDE.md (en/) and
                          USER_GUIDE.de.md (de/) -- see that section's own
                          note below for how they were captured
MIGRATION.md             Migrating from Mariner Paperless, linked from README.md
MIGRATION.de.md          German translation of MIGRATION.md
CLAUDE.md                This file
CONTRIBUTING.md          Human-contributor guide (tests, conventions, PR expectations)
LICENSE                  MIT
.gitignore               Excludes personal library data from commits
tests/                   Playwright regression suite (55 scripts) + shared
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

## Versioning

`dossiary.html` and `scan_watch.py` share one version number (`1.8.3` as of
this writing), kept manually in sync with this repo's git tag on each
release — no build step or shared version file to do this automatically.
`dossiary.html` has its own `APP_VERSION` constant (the very first line
inside the top-level IIFE), shown in the footer next to the copyright line
via `#app-version-label`, set once during the same static-wiring pass as
the Libraries-link click handler — deliberately not gated behind a library
being open, since the version should be visible regardless of app state.
`scan_watch.py` has its own separate `__version__`, exposed the standard
way via `argparse`'s `--version` flag. When cutting a release, bump both
constants together with the tag — nothing currently checks that they agree
with each other or with the tag, or with `LibraryLifeboat`'s own version
(the sibling repo's `migrate_to_new_library.py` produces the schema this
app expects, so a large version skew between the two is worth noticing,
though the two repos don't currently enforce or check compatibility by
version number — only by the schema itself matching).

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
  + `max-height:calc(100vh - Xpx)`, `X` now nav-style-dependent — see below),
  not just "the table with horizontal scroll" it looks like at a glance. This
  exists specifically so `thead th`'s `position:sticky; top:0;` has something
  correct to stick to. The original version only had `overflow-x:auto` (no
  `overflow-y` set at all) — which looks harmless, but per the CSS Overflow
  spec, if one axis is anything other than `visible` and the other is left as
  `visible`, the browser silently forces the `visible` one to compute as
  `auto` too. That turned `.table-wrap` into an unintended vertical scroll
  container, which broke the sticky header — it stuck to the top of
  `.table-wrap`'s own (never-scrolling, since the *page* was scrolling
  instead) box rather than the viewport, so it just scrolled away like
  nothing was sticky at all. Setting `overflow-y: visible` explicitly does
  **not** fix this — the spec doesn't allow "one visible, one not" as a
  computed combination, so the browser overrides it back to `auto`
  regardless of what's literally written. The actual fix was to stop
  fighting that rule and lean into it: make `.table-wrap` an intentional,
  bounded scroll container for both axes, so sticky has exactly one clear,
  correctly-scrolling ancestor. **`X` is `295` by default (top-tab nav) and
  `256` when `#main-layout` has the `.nav-style-sidebar` class** (see the
  "Top-level nav" note below) — the tab strip sits *above* `.table-wrap` in
  the tabs layout, adding real height to the stack, while the sidebar sits
  *beside* it, contributing none. Both numbers were verified empirically
  (`getBoundingClientRect()` on `#table-wrap` itself, confirming its
  rendered bottom edge lands exactly at the viewport bottom) while building
  the nav feature — worth restating since that same check caught the
  *sidebar* case's inherited value having already silently drifted stale
  (real value `256`, not the `230` a straight "no extra height, so reuse the
  old number unchanged" assumption would have kept) from unrelated
  header/toolbar changes made elsewhere, well before the nav existed. If you
  ever adjust the header/toolbar/nav layout, recalibrate the same way —
  verify empirically, e.g. checking `getBoundingClientRect()` on `thead th`
  before/after a large internal scroll stays roughly constant, or that
  `#table-wrap`'s own bottom edge lands at the viewport bottom — rather than
  assuming a nearby value, or an old comment's value, is still correct.
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
  anywhere else in the form-handling code. Person-type fields deliberately
  don't participate in the `show_as_column`/`autocomplete` capability
  system (Field Settings' checkboxes exclude `type === 'person'`, same
  spirit as the narrow Amount/Currency exception below) — People keeps its
  own permanently-fixed table column and filter dropdown exactly as
  before, and giving a multi-valued field a single-string table cell or a
  useful filter dropdown is a real, separate feature that wasn't in scope
  when this generalization landed; a new person-type field like Author
  simply doesn't get a column or filter yet.
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
  operates on a document's actual saved file (resolved fresh via
  `resolveFileHandle(d.file_path)`), only refreshes `e-ocr-text`, and
  deliberately does **not** request word-position data or touch
  `file_path`/rebuild any PDF — consistent with editing being
  metadata-only (see the "Editing" note above). **`runOcrForEdit()`
  handles PDFs, `runOcr()` doesn't** — it renders every page via
  `renderPdfPageToCanvas()` (a higher-resolution sibling of
  `generateThumbnail()`'s PDF path; OCR accuracy degrades badly at
  thumbnail resolution, so this is intentionally a separate function
  with its own `scale` parameter, not a shared one with a size flag),
  called once per page in a loop (`for(let pageNum = 1; pageNum <=
  pdf.numPages; pageNum++)`), with each page's recognized text joined
  together — not just the first page, see the "How this was tested"
  section's note on multi-page PDF OCR — and passes each resulting
  canvas straight to Tesseract, which accepts canvas elements directly
  as an image source. If capture-mode OCR is ever extended to support
  PDFs too, reuse `renderPdfPageToCanvas()` rather than duplicating the
  pdf.js rendering logic a third time.
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
  **Every table row has a hover-revealed `.row-edit-btn` (✎)** next to its
  checkbox (`.row-edit-col`, a narrow column added specifically for it — see
  `applyColumnVisibility()`'s sibling `data-field` columns, this one has no
  `data-field` and is never hideable via the Columns menu) that jumps
  straight to `openEditForm()`, skipping `openDetail()` entirely — a
  same-view shortcut for the common case of wanting to edit right away,
  without a separate click through the detail view first. Present in every
  nav view uniformly (not just Inbox, where the idea originally came from —
  editing directly is generically useful regardless of a document's review
  state), **except deleted documents**, where it's absent entirely, matching
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
  documents SET archived = ?` from the detail modal's Archive/Unarchive
  button, mirroring `regenerateThumbnail()`'s own update-in-memory →
  persist → `render()` → re-open-the-modal pattern. Deliberately a
  dedicated `documents` column, not a generic custom checkbox field — the
  generic fields system (see below) has no concept of "hidden from the
  view by default," only optional columns/filters that are always visible
  once configured, which doesn't fit what an archive needs to do.
- **Review queue** (`documents.needs_review`, `toggleNeedsReview()`, the
  Inbox nav item — `#nav-item-inbox`, `data-view="inbox"`) is a second,
  independent staging flag, built as a direct structural mirror of
  `archived` above — same `documents` column pattern, same `SCHEMA`/
  `SCHEMA_MIGRATIONS` treatment, same detail-modal toggle-button pattern
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
  inbox-imported ones — the "Flag for review" button in the detail modal
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
  **`toggleNeedsReview()` has two call sites**: the detail modal's own
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
  single call site — the detail modal's own button — and always refreshes
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
- **Top-level navigation** (`#main-layout`, `#app-nav`, `.nav-item`,
  `currentView`, `matchesView()`, `renderNav()`, `setView()`) unifies
  All Documents/Inbox/Waste bin — previously an always-visible Review
  Queue banner above the table plus a separately-modal Waste Bin reached
  via its own toolbar button — into one persistent nav switching between
  three views of the exact same real `<table>` (same columns, sorting,
  search, category/type/dynamic filters), directly modeled on Mariner
  Paperless's own "Everything"/"Inbox" sidebar. Clicking a row in any view
  opens the same `openDetail()` modal used everywhere else, which already
  renders the correct action set per document state (see the Archiving/
  Review queue/Waste bin notes above) — this is why unifying onto one
  table needed no new per-row action buttons at all, unlike the old
  review-queue rows' own inline Edit/Done buttons or the waste-bin modal's
  own inline Restore button, both now gone.
  **`matchesView(d, view, showArchived)`** is the single function
  encoding view membership, extracted from what used to be `applyFilters()`'s
  own inline logic: `'trash'` → `!!d.deleted`; `'inbox'` → (after excluding
  deleted) `!!d.needs_review && !d.archived`; `'all'` → (after excluding
  deleted) the pre-existing default-table rules, `archived && !showArchived`
  excluded and `needs_review && !archived` excluded. `applyFilters()` now
  reads `if(!matchesView(d, currentView, showArchived)) return false;`
  before its unchanged category/type/person/dynamic/search filters — so
  those filters compose correctly with whichever view is active for free,
  which the old separate Review Queue/Waste Bin renderers never supported
  (neither had its own search or category filtering at all).
  **`currentView`** (`'all'` | `'inbox'` | `'trash'`) is session-only,
  never persisted — always starts `'all'` on every library open, via
  `resetAll()`. Switching views does **not** reset search text, filter
  selects, or "Show archived" — only the document set changes.
  **`renderNav()` replaces `renderReviewQueue()` in `render()`'s "always
  call this first" slot** (`render()`'s first statement, so every existing
  call site — initial load, post-edit, post-inbox-add, post-toggle — picks
  it up automatically): it computes `navCounts` (one `matchesView()` filter
  pass per view, against the *current* `showArchivedToggle` state),
  updates each `.nav-item`'s badge and `.active` class, and shows/hides
  `showArchivedWrap` (`currentView === 'all'` only — "Show archived" only
  means anything for the `'all'` view; `'inbox'` already excludes archived
  unconditionally, and `'trash'`'s `deleted` flag trumps `archived`
  regardless, so showing the checkbox in those views would just be inert
  UI). Badges reflect **view membership only**, not the live search/filter
  text — recomputing per keystroke would make navigation counts flicker
  while typing, and the existing `countLine` ("Showing X of Y", its
  denominator now `navCounts[currentView]` rather than `allDocs.length`)
  already covers the filtered-count case. `setView(view)` sets
  `currentView` and calls `render()`; wired from each `.nav-item[data-view]`'s
  click handler.
  **Visual style is a persisted, user-configurable setting**
  (`navStyle`, `'tabs'` | `'sidebar'`, default `'sidebar'`), toggled via a
  `#nav-style-toggle` button living inside the nav itself — no general
  settings-modal infrastructure exists in this app, so the control sits
  spatially attached to what it controls, the same reasoning behind where
  `default_document_type`/`default_currency` live in Field Settings.
  `loadNavStyle()`/`saveNavStyle()`/`applyNavStyle()` follow the exact
  existing `settings`-table `key`/`value` pattern used by
  `loadDefaultCurrency()`/`saveDefaultCurrency()` — `applyNavStyle()`
  just toggles a `nav-style-sidebar` class on `#main-layout`; one shared
  markup structure and one CSS class flips between a horizontal tab strip
  and a vertical sidebar, not two divergent markups. `loadNavStyle()` is
  called from `loadDocumentsFromDb()` alongside `loadDefaultCurrency()`.
  **Icons were chosen to avoid a real collision**: All Documents is 📁,
  Waste bin is 🗑 (already used elsewhere in the app), and Inbox is
  deliberately **🚩**, not 📥 — 📥 is already the separate, pre-existing
  "Check inbox" toolbar button for raw staged files (see the Inbox note
  below), and reusing it here would visually conflate two unrelated
  features; 🚩 instead matches the existing "Flag for review" button label
  already used for this exact `needs_review` concept.
  **`.table-wrap`'s sticky-header max-height calibration is nav-style-
  dependent** — see that note near the top of this file for the current
  values and the empirical-verification story; the tabs nav sits *above*
  the table (adding real height to the stack) while the sidebar nav sits
  *beside* it (adding none), so the two styles need different constants.
- **Reports** (`#nav-item-reports`, `data-view="reports"`, `reportBreakdownFields()`,
  `reportBreakdownFieldInfo()`, `computeReportGroups()`, `renderReportsView()`) is a
  4th top-level nav view alongside All Documents/Inbox/Waste bin, giving totals
  for tax prep and expense reimbursement workflows Dossiary previously had no way
  to support. **`matchesView()`'s `'reports'` branch always includes archived and
  needs-review documents** — a report is about real financial history, not about
  what's currently decluttered out of the browse view; only `deleted` (Waste bin)
  documents are excluded, same as every other view. Totals are grouped by Currency
  first and never summed across different currency labels
  (`customFields['Currency']`, blank treated as its own "No currency set" group) —
  Dossiary never assumes a single-currency library. Within each currency group,
  documents are further grouped by a chosen breakdown field (`#report-breakdown-field`,
  populated from `reportBreakdownFields()`: Category/Type/People from `FIELD_DEFS`,
  plus any custom field flagged `show_as_column` via the same `dynamicColumnDefs()`
  table columns/filters already use — deliberately excludes `date`/`import_date`
  (near-unique per document, not a meaningful grouping key), `amount` (the value
  being summed, not a grouping key), and `tags` (multi-valued like People, but
  out of scope for v1). **A document with more than one value for a multi-valued
  breakdown field (People, or a custom person-type field) contributes its full
  Amount to every value's row** — `renderReportsView()` shows an explicit caption
  when this applies, since row totals then legitimately don't sum to the currency
  group's own Grand total; that Grand total (`computeReportGroups()`'s `grandTotal`/
  `documentCount`) is deliberately computed independently over every document in
  the currency group, not by summing the rows above it, so it stays a reliable
  "true total" regardless. A separate, Reports-only date-range filter
  (`#report-date-from`/`#report-date-to`, `currentReportDateRange()`) filters on
  the document's own `date` field (its content date, not `import_date`) —
  `applyFilters()` only applies this filter when `currentView === 'reports'`; the
  existing search/category/type/dynamic-field filters continue to apply unchanged
  in this view too. No new dependency, no schema change — this is a pure
  read/aggregate view over `allDocs`. Printing (`#reports-print-btn` →
  `window.print()`) is the first `@media print` stylesheet in this app, hiding
  `#app-nav`/`.toolbar`/etc.; the browser's own print dialog already offers "Save
  as PDF" on every platform this app targets, so no separate PDF-generation path
  was needed.
- **Collections** (`collections` + `collection_documents` tables,
  `openManageCollectionsModal()`, `createManualCollection()`,
  `addDocumentsToCollection()`) are user-created document groupings, manually
  curated or automatically matching your current search/filter state as a
  live view. The schema stores only two tables: `collections` (name, `kind`,
  criteria JSON for smart collections) and `collection_documents` (the
  manual join for non-smart collections). Smart collections store no rows in
  `collection_documents` — instead, `matchesCriteria()` re-evaluates their
  filter criteria against each document on every `render()` call, the same
  criteria grammar `currentFilters()` extracts from the toolbar (Category,
  Type, Person dropdowns, dynamic-field filters, search text), so a smart
  collection always stays synchronized with new documents without any
  background sync logic. Manual collections are static rosters you build by
  selecting documents in the table and clicking "Add to Collection" (via the
  bulk-action toolbar that appears when checkboxes are checked), or one at a
  time from a document's own detail-modal action buttons ("Add to Collection"
  picks which one; "Remove from Collection" appears only when viewing from
  inside a specific manual collection). Removing a document from a collection
  and deleting a collection are both inline `DELETE FROM` statements in their
  respective click handlers, not named functions; deleting the collection
  currently being viewed (via its own nav item) falls back `currentView` to
  `'all'` first, so the person isn't left in a now-nonexistent view with
  nothing highlighted. The Collections nav section
  expands and collapses via a toggle button (`#nav-collections-toggle` →
  `saveCollectionsNavExpanded()`), defaulting to **expanded**
  (`collectionsNavExpanded = true` unconditionally at startup and in `resetAll()`)
  and staying expanded until the user explicitly collapses it, with that choice
  then persisted via the `collections_nav_expanded` setting; the list itself
  (`#nav-collections-list`) is rebuilt on **every `render()` call** (it lives
  inside `renderNav()`, called from `render()`'s "always call this first" slot —
  see the Top-level navigation note above), not just when a collection is
  created, deleted, or renamed — the same delete-then-reinsert-from-scratch
  pattern this app already uses for other dynamic containers, though those
  rebuild on their own separate triggers rather than every `render()` call
  (`renderDynamicTableHead()`'s `<th>`s rebuild when the columns menu
  changes, `populateFilters()`'s dynamic filters rebuild from their own
  explicit call sites — neither is invoked from inside `render()` itself).
  Smart collections
  are created only via the "☆ Save as Smart Collection" button
  (visible only in the All Documents view) — the Manage Collections modal's
  "+ New collection" creates manual collections only, never smart ones: a
  Smart Collection is only ever created by capturing a real, live filter
  snapshot at the moment "Save as Smart Collection" is clicked (its criteria
  coming straight from `currentFilters()`), and the Manage Collections modal
  has no filter state of its own to capture — a smart collection created
  there would have no criteria, which has no meaning for a collection whose
  entire membership is defined by its criteria. **"Save as Smart Collection"
  lives in the Collections nav section itself, not `.toolbar`** — moved there
  to fix a real toolbar-wrap regression (two new buttons pushed `.toolbar`
  from 2 rows to 3, landing `#reload-btn` directly under the open Columns
  dropdown); "⚙ Manage collections" stayed in the toolbar, since removing
  just the one button was already enough to restore the original 2-row
  layout. Multi-select
  checkboxes (`#select-all-checkbox`, per-row checkboxes with class
  `row-select-checkbox` and `data-id="${d.id}"`) reset whenever you switch views
  (`setView()` clears `selectedDocIds` and re-renders the table) or close the
  library — the selection state never persists across sessions and is scoped to a
  single view, so switching to a Smart Collection and back to All Documents doesn't
  retain your old All Documents selection. Creating a new manual collection
  and adding its first documents happen as one action via the same
  `addDocumentsToCollection()` and `createManualCollection()` functions that
  the detail-modal single-document action buttons use — no special
  code-path difference between a bulk add and a single add.
  **Bulk archive/delete/flag-for-review actions** (`bulkSetArchived()`,
  `bulkSetDeleted()`, `bulkSetNeedsReview()`, `renderBulkActionBar()`)
  extend the bulk-action bar with view-aware buttons for applying state
  changes to multiple documents at once. Button visibility and labels are
  context-sensitive: the Waste bin view shows only "Restore"; the Inbox
  view relabels "Flag for review" to "Done" (unflag); every other view
  (All Documents, Collections, Reports) shows Archive, Delete, and "Flag
  for review" alongside the existing "Add to collection" — but Reports
  view shows neither checkboxes nor a bulk bar at all. All three functions
  use **unconditional-set semantics** (not per-document toggle): "Archive
  selected" always sets `archived=1` for every selected document regardless
  of its current state, enabling correct behavior for mixed-state selections
  (e.g., selecting both archived and unarchived documents from a Collection
  view and clicking Archive leaves both archived, not toggling the already-
  archived one back to unarchived). Crucially, all database UPDATEs are
  queued first (`forEach`), then persisted and rendered exactly once via a
  single `persistDb()` / `render()` call, not per-document — unlike looping
  the single-document toggle functions, this avoids wasteful
  re-serialization of the entire SQLite database for bulk operations on
  multiple documents.
  **A collection view (`matchesView()`'s `'collection-<id>'` branch, both
  manual and smart) deliberately includes archived and needs-review
  documents** — the same choice, and the same reasoning, as the Reports view
  above: a collection is a saved/curated view (a manually-built roster, or a
  saved filter snapshot), conceptually closer to a report than to the
  day-to-day `'all'` browse view, so a document someone explicitly added to
  a collection — or that matches a Smart Collection's saved criteria —
  shouldn't silently vanish from that collection just because it got
  archived or flagged for review elsewhere. Only `deleted` (Waste bin) is
  excluded, via the same shared check every other view uses.
  **The bulk-action bar's height is part of `.table-wrap`'s sticky-header
  calibration too** — see that note near the top of this file. Selecting any
  row shows `#bulk-action-bar` (~74px of real page height above
  `.table-wrap`), so `renderBulkActionBar()` toggles a `.bulk-bar-visible`
  class on `#main-layout` and the CSS has dedicated `max-height` rules for
  all four combinations of nav style × bulk-bar visibility — don't assume
  the two nav-style constants alone are enough; selecting documents (this
  feature's own core workflow) is exactly the case that needs the other two.
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
- **Persisted default sort order** (`sortKey`, `sortDir`, `loadSortState()`,
  `saveSortState()`) mirrors the `nav_style`/`default_currency` pattern exactly:
  a per-library setting stored in the `settings` table, loaded once on library
  open via `loadDocumentsFromDb()`, and persisted back on every column-header
  click via the click handler's fire-and-forget call to `saveSortState()` —
  the async `persistDb()` happens in the background without blocking `render()`.
  **Defaults to `import_date` descending (newest-imported-first), not `date`
  descending**, because `date` (a document's own content date, e.g. invoice date)
  can be `NULL` for Inbox-imported documents until they're reviewed — sorting
  by a field that's `NULL` for a significant portion of a library would bury
  unreviewed documents in raw insertion order at the bottom of the table,
  making a review queue invisible. `import_date` (when the library imported the
  file) is always populated. **The "Imported" column is visible by default**
  specifically so this sort choice has a visible, highlighted header on first
  open — without seeing `th[data-key="import_date"]` highlighted in
  phosphor-green, a person has no way to know the table is already sorted. If
  the person never opens the Columns menu, they never disable this column, so
  the header stays visible and the sort stays legible. Clicking the header
  toggles direction (ascending on subsequent clicks); clicking a different
  column header sets that column as the new sort and defaults `date`/`import_date`
  to descending, all other columns to ascending — matching the existing click
  logic for those two special-case columns. `loadSortState()` validates the
  persisted `sort_key` against every currently-sortable column — `'title'`
  (sortable but deliberately absent from `FIELD_DEFS`, see that field's own
  note above), the rest of `FIELD_DEFS`, and `dynamicColumnDefs()`'s own ids
  (already in `'field-<id>'` form — don't re-prefix them, that was a real bug
  caught in review: re-prefixing produces `'field-field-<id>'`, which never
  matches anything, silently discarding every custom-field sort on reopen) —
  falling back to `import_date` for a stale or removed key, the same
  graceful-degradation convention `loadColumnSettings()` already uses.
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
  ever reach them. Not offered for any person-type field (People, Author,
  Collaborator, ... — `capabilitiesHtml()` excludes `type === 'person'`,
  see the People note above for why) or for `'Amount'`/`'Currency'` by
  name (their flags are deliberately kept off — see the sentinel-fields
  note above — so an editable checkbox that visibly did nothing would just
  be confusing).
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
  slow OCR pass per file). This mirrors `saveNewDocument()`'s file-copy/
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
    Mariner Paperless itself used. See "Preserving an original file on
    ingestion" below for what happens when a searchable PDF *isn't* built.
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
  tradeoff, not an oversight. `searchable_pdf_built` is not yet loaded
  into the in-memory `allDocs` model or read by any UI — nothing consumes
  it yet; it exists for a planned future "build a searchable PDF after the
  fact" action to gate on.
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
- **UI language support (English/German)** is a flat two-language dictionary
  (`STRINGS.en` / `STRINGS.de`, ~260 keys each), a lookup helper (`t(key,
  params)`), and one whole-page re-translate pass (`applyI18n()`) — not a
  full i18n library, ICU message format, or per-string `.po`/`.json` files;
  the app's single-file constraint (see "What this project is") rules out
  pulling in a real i18n framework, and two hardcoded languages don't need
  one. `t()` falls back `STRINGS[currentLang][key] ?? STRINGS.en[key] ??
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
  empty-state "Open library folder" screen (`#empty-state`) has to render
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
  the moment someone clicks `#lang-toggle` once, `saveLang()` writes an
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
  gated on `!rootDirHandle`, avoids that collision the same way the
  Amount/Currency header-line and conditional-field notes elsewhere in
  this file avoid overreaching a general mechanism into a case it doesn't
  fit.
  **A mouse click on `#lang-toggle` is already blocked by a modal's own
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
  resolution is a **toggle guard, not a re-render**: `#lang-toggle`'s
  click handler returns early — no language change, `saveLang()` never
  called — whenever `modalRoot.innerHTML !== ''` (the same "is a modal
  open" signal `closeModal()`'s own `modalRoot.innerHTML = ''` implies),
  making the toggle inert for the keyboard path too, matching what a
  mouse user already experiences via the backdrop rather than attempting
  a re-render that would be safe for some modals and destructive for
  others.
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
  forms; 21 confirms `#lang-toggle` is a genuine no-op while a modal is
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
  key exists in *both* `STRINGS.en` and `STRINGS.de` — a static safety net
  against the one mistake `test_i18n.py`'s scenario-by-scenario clicking
  can't exhaustively rule out (a key added to English but never given a
  German translation, or vice versa, anywhere in this ~270-key,
  hand-maintained dictionary that no single Playwright run touches every
  corner of).
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

## How this was tested (useful context for future changes)

There's a real, runnable Playwright regression suite in `tests/` — **57
scripts covering most of the app's actual functionality** (56 of them
Playwright-driven; the 57th, `test_i18n_coverage.py`, is a plain static
check with no browser involved — see its own description below): capture, edit,
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
content, the Inbox add flow (`test_inbox.py` — banner visibility, the
banner's "Add all" button adding both staged files directly to Inbox with
no modal appearing, landing on the Inbox nav view, reporting the folder
path + count on the status line, the banner hiding once empty, the
toolbar's "Check inbox" button surfacing a file staged after library open
(which the one-time-at-open `checkInbox()` call alone would miss) and
adding it directly the same way, "Check inbox" with nothing staged
reporting "No files waiting" without navigating, and a partial-failure
scenario (1 succeeds, 1 fails) reporting accurately on the status line
with both success and error indicators),
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
review queue (`test_review_queue.py` — an inbox-imported document landing
flagged and reachable via the Inbox nav view rather than All Documents;
Done clearing the flag from the detail modal; any document, not just
inbox-imported ones, being manually flaggable from the detail view; an
intermediate save via Edit *not* clearing the flag, only the explicit
Done action does; and the archived+needs_review independence property,
including the one subtle case that actually matters — a document that's
both stays out of the Inbox view but is still reachable, and toggleable,
via "Show archived" in the All Documents view, per `matchesView()`'s
`!d.archived` carve-out described in the review-queue architecture note
above; "Save & Done" being present only when editing a currently-flagged
document and absent for an unflagged one; and clicking it both saving the
edited title and clearing the flag in one action, verified against
persisted state, not just the DOM), the waste bin (`test_waste_bin.py` — a pre-`deleted`-column
document reading back as not-deleted rather than erroring; deleting an
active document hiding it from All Documents even with "Show archived"
checked; its detail view dropping down to a Restore-only action set with
Edit/Archive/Flag for review/Delete all genuinely absent from the DOM,
not just disabled; restoring both from a Waste bin row's detail view and
from within the modal after re-opening it there; deleting a flagged
document removing it from the Inbox view too, not just All Documents;
that no "Empty bin" button exists anywhere; and that restoring a document
doesn't touch its independent `needs_review` state, so a restored,
still-flagged document goes straight back to the Inbox view rather than
All Documents), the unified top-level nav itself (`test_nav.py` — the old
`#waste-bin-btn`/`#review-queue` markup genuinely gone; the separate,
unrelated "Check inbox" staged-files button/modal still present and
distinct from the new Inbox nav item; category and search filters
composing correctly with the Inbox and Waste bin views, not just All
Documents, which the old separate Review Queue/Waste Bin renderers never
supported; nav badge counts correct on load and live after a mutation;
the `nav_style` setting persisting `'sidebar'` across a reopen), the Date
field's
`color-scheme: dark` fix (asserted via `getComputedStyle` in
both the capture and edit forms, not just eyeballed), the Edit-form
Currency guess (an existing document with a real non-zero Amount and no
Currency saved gets guessed and flagged once a default currency is
configured; a document with no Amount, or Amount explicitly `0`, does
not; the guess is dismissed on touch same as everywhere else; and once
accepted and saved, the real value is never re-flagged as a guess on
reopen), `inbox/` actually getting created (for a brand new library, and
for an existing library that predates this fix, with the inbox banner
correctly staying hidden for the freshly-created, still-empty folder),
the scan-hint text's OS-specific wording (macOS, Windows, Linux, and the
no-signal-at-all fallback, each verified via an overridden
`navigator.userAgentData`/`navigator.platform` rather than trusting
whatever OS the test happens to run on), the footer's app-version label
(folded into `test_libraries_modal.py`, which already exercises that
part of the page), `scan_watch.py --version`'s output (its own
standalone, non-Playwright script since it's a plain subprocess check),
the detail view's `File`/`Original` path lines (folded into
`test_searchable_pdf.py`, since that's the one scenario that produces
both a processed file and a separate original to show), the path lines'
"Copy" buttons (`test_copy_path.py` — button presence per doc type, the
"Copied!"/reset label cycle, and that each button copies its own path
independently rather than a stale or shared value), People's generalization
into a real person-type field (`test_person_type_field.py` — creating a
brand new "Author" field inline, an existing People field staying present
and unaffected, independent `document_field_people` links per field rather
than a merged/shared list, the detail view's own pills section for a
non-People person-type field, searching by an Author-only name, and the
`person-list` datalist autocompleting a name that's only ever appeared as
an Author, never as People; `test_people_migration.py` — an old-shape
seeded library, `document_people` populated directly with no `fields` row
for `'People'` yet, correctly promoted on open, its `document_type_fields`
sentinel row needing no migration of its own, the old `document_people`
table left untouched, and idempotency across a reopen), the recent-libraries
startup list (`test_recent_libraries.py` — an entry recorded on open, dedup
by folder identity rather than name, the 5-entry cap evicting the oldest,
one-click reconnect without a fresh folder-picker call, manual removal, and
a denied/failed reconnect leaving its entry in place with an inline error),
the `searchable_pdf_built` backfill migration (`test_searchable_pdf_built_migration.py`
— a `captured` document with a pre-existing original correctly backfilled
to `1`, a `migrated` document's unrelated original correctly left alone, a
`scan-inbox` document with no original left alone, and stability across a
reopen), the Reports view (`test_reports.py` — the nav item and view-scoping
(archived and needs-review included, deleted excluded, matching the
"Top-level navigation" note's own `matchesView()` design); currency
grouping across three distinct groups including a blank-Currency "No
currency set" group; category/type breakdown totals and their independently-
computed Grand total; the multi-valued People-breakdown row-inflation
caveat and its on-screen caption, switched to without leaving the Reports
view; the date-range filter narrowing totals by the document's own Date
field and correctly excluding a document with no date set once a bound is
active; and the print button/`@media print` layout hiding the nav and
toolbar), Collections (`test_collections.py` — manual and smart collection
view routing and live re-evaluation of Smart Collection criteria whenever
filters change; toolbar filters composing correctly on top of a
collection's own scope; "Save as Smart Collection" visibility (scoped to
All Documents only, **hidden** — not disabled — everywhere else, checked
across the Inbox/Waste bin/Reports views too, not just one example
collection view); multi-select + bulk add (including that checking
a checkbox doesn't also open the detail modal, and that selected checkboxes
clear on view switch), the detail modal's Add-to-Collection and
Remove-from-Collection action buttons (Remove appearing only when viewing
from inside that specific manual collection), the Manage Collections
modal's rename/delete/create-empty-manual-collection flows (including that
an empty rename resets the input back to the real name instead of leaving
it blank), the Collections nav section's expand/collapse toggle, an
archived document that's a collection member still showing up in that
collection's view (manual and smart collections deliberately include
archived/needs-review documents — see this note's own Collections entry
above), deleting the collection currently being viewed falling back to All
Documents rather than leaving a phantom view, bulk archive/delete/flag-for-review
actions (`test_collections.py` Scenarios 25-28b — the four view-aware action
buttons visible/hidden/relabeled correctly per nav view (All/Collection/Inbox/
Trash); unconditional-set semantics on mixed-state selections archived both
already-archived and previously-unarchived docs; bulk flag-for-review setting
needs_review on multiple docs; Inbox relabeling the button to "Done" and
bulk-Done clearing the flag; bulk delete hiding docs from All Documents and
moving to Waste bin; bulk restore clearing the deleted flag; each action
clearing selection and persisting exactly once), and a dedicated
large-document-seed (60+) check of `.table-wrap`'s sticky-header height
calibration across all four combinations of nav style × bulk-action-bar
visibility (Scenarios 29a-29c — no checkboxes in Reports view; nav badge
counts updating after bulk actions; bulk delete from Collection view
preserving collection membership on restore; Scenario 30 measures calibration
constants), replacing an earlier version of this same check that used only
3-4 seeded documents — too few to ever make the `max-height` constraint
actually binding, so it could report success regardless of whether the CSS
constants were actually correct; the current version explicitly asserts
`scrollHeight > clientHeight` first, to prove the constraint is binding
before trusting the bottom-edge measurement that follows it), persisted
default sort preference (`test_default_sort.py` — table opens sorted by
`import_date` desc by default when no sort settings exist; clicking Date
persists the sort choice; clicking Imported (a descending-by-default column
like Date) persists desc rather than defaulting to asc; reopening reads
back and applies persisted sort state), drag-and-drop (`test_drag_drop.py`
— the overlay staying hidden and a drop no-oping with no library open; the
overlay showing on `dragenter` and hiding after a `drop`, using real
`DragEvent`/`DataTransfer` objects dispatched on `document`, not a stub,
since both are standard browser APIs already available in a real
Chromium page; a single dropped file landing as a `source: 'dropped'`
needs-review document with the status line naming it and the view
jumping to Inbox; a multi-file drop adding one document per file in a
single batched persist; and an empty drop — no files in the
`DataTransfer` — being a real no-op, no navigation and no document
created), the row-level edit shortcut (`test_row_edit_shortcut.py` — the
hover-revealed button opening the Edit form directly rather than the
detail view, with no lingering detail-view element proving
`event.stopPropagation()` genuinely stopped the row's own click handler
from also firing; the same behavior holding in the Inbox view too, not
just All Documents; Cancel from an edit reached this way landing on the
detail view; and the button being entirely absent — not just hidden — for
a deleted document in the Waste bin), UI language support
(`test_i18n.py` — default English with no locale signal; auto-detecting
German from `navigator.language`/`navigator.languages` on first load with
no stored preference yet; a manual toggle click overriding that and
persisting across a reload even though the browser's own locale still
says German; date formatting following the UI language choice rather than
OS locale; translated content across the nav, toolbar, stats bar, table
headers/rows, detail modal, capture and edit forms (including the shared
inline add-field validation message and reused OCR strings), Field
Settings, Manage Collections, Reports, the Libraries/licenses modal, and
the drag-and-drop overlay; the recent-libraries list and empty-state
screen re-translating live on toggle, not just on next load; and two
regressions caught by inspecting raw `innerHTML` rather than
`inner_text()` alone — a duplicated "Important:"/"Wichtig:" label and a
nested `<b><b>...</b></b>` from double-wrapping a substituted name), and a
static i18n key-coverage check (`test_i18n_coverage.py` — no Playwright,
just a grep-based Python script confirming every `data-i18n`/
`data-i18n-placeholder`/`data-i18n-title`/`data-i18n-aria-label`
attribute value and every `t('key')` call argument in `dossiary.html`
exists in both `STRINGS.en` and `STRINGS.de`; verified during development
to actually catch a real regression, not just trivially pass, by
temporarily renaming one `STRINGS.de` key and confirming the script
failed with that exact key reported missing, then reverting), and search
across all of the above. This
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
