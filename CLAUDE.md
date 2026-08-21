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
USER_GUIDE.es.md         Spanish translation of USER_GUIDE.md
USER_GUIDE.fr.md         French translation of USER_GUIDE.md
USER_GUIDE.zh-Hans.md    Simplified Chinese translation of USER_GUIDE.md
USER_GUIDE.zh-Hant.md    Traditional Chinese translation of USER_GUIDE.md,
                          derived from USER_GUIDE.zh-Hans.md via OpenCC
docs/user-guide/         Screenshots for each USER_GUIDE.<lang>.md, one
                          subfolder per language (en/, de/, es/, fr/,
                          zh-Hans/, zh-Hant/) -- see that section's own
                          note below for how they were captured
MIGRATION.md             Migrating from Mariner Paperless, linked from README.md
MIGRATION.de.md          German translation of MIGRATION.md
CLAUDE.md                This file
CONTRIBUTING.md          Human-contributor guide (tests, conventions, PR expectations)
LICENSE                  MIT
.gitignore               Excludes personal library data from commits
tests/                   Playwright regression suite (63 scripts) + shared
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
'fr', 'zh-Hans', 'zh-Hant']`** — not `SUPPORTED_LANGS` itself.
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
  + `max-height:calc(100vh - Xpx)`, `X` now nav-style- and footer-dependent —
  see below), not just "the table with horizontal scroll" it looks like at a
  glance. This exists specifically so `thead th`'s `position:sticky; top:0;`
  has something correct to stick to. The original version only had
  `overflow-x:auto` (no `overflow-y` set at all) — which looks harmless, but
  per the CSS Overflow spec, if one axis is anything other than `visible` and
  the other is left as `visible`, the browser silently forces the `visible`
  one to compute as `auto` too. That turned `.table-wrap` into an unintended
  vertical scroll container, which broke the sticky header — it stuck to the
  top of `.table-wrap`'s own (never-scrolling, since the *page* was
  scrolling instead) box rather than the viewport, so it just scrolled away
  like nothing was sticky at all. Setting `overflow-y: visible` explicitly
  does **not** fix this — the spec doesn't allow "one visible, one not" as a
  computed combination, so the browser overrides it back to `auto`
  regardless of what's literally written. The actual fix was to stop
  fighting that rule and lean into it: make `.table-wrap` an intentional,
  bounded scroll container for both axes, so sticky has exactly one clear,
  correctly-scrolling ancestor. **`X` is `410` by default (top-tab nav),
  `370` with `.nav-style-sidebar`, `484` with `.bulk-bar-visible`, and `444`
  with both** (see the "Top-level nav" and "Collections" notes below for the
  nav-style/bulk-bar dimensions) — the bulk-action bar adds its own
  **74px** on desktop (`484 - 410 = 74`, `444 - 370 = 74`) and **102px** on
  mobile (`494 - 392 = 102`, `518 - 416 = 102`) whenever any row is
  selected, regardless of nav style — derivable directly from the constants
  quoted here and in the mobile note below, not a separately-measured
  figure. **These four desktop numbers were bumped a second time (from
  `364`/`370`/`438`/`444`) by the Amount-range/Currency-filter branch**,
  and the relationship between the tabs and sidebar pair is no longer the
  simple "tab strip sits above `.table-wrap`, adding real height; sidebar
  sits beside it, adding none" story the original numbers told. That
  branch's new toolbar controls can push `.toolbar` onto an extra wrapped
  row at certain viewport widths, and which widths trigger that differs
  between the two nav styles (tabs' toolbar spans the full content width;
  sidebar's is squeezed narrower by the sidebar itself, so it wraps at
  different breakpoints) — so each nav style's pair of constants is now
  independently calibrated to its own worst-case width across a
  700-1600px sweep (`getBoundingClientRect()` on `#table-wrap` and
  `footer`, same 60-document seed and methodology as always), not derived
  from the other by a fixed structural offset. It happened that tabs'
  worst case (an extra wrapped row appearing only around 1000-1100px,
  absent at other tabs widths) needed a bigger bump than sidebar's did
  this round, landing tabs' numbers above sidebar's again — but that's
  incidental to where each style's own toolbar happens to wrap this time,
  not a re-assertion of the old structural rule; a future toolbar change
  could easily flip it back. Sidebar mode is left with roughly `46px` of
  known, accepted dead space at viewport widths `≥1440px` (its own
  worst-case width is narrower than that, so the constant that closes the
  worst case necessarily overshoots at the wide end) — deliberately not
  tightened further, per the "accept extra gap, never accept overlap"
  principle repeated throughout this note: the potential savings were
  small relative to the risk of reopening a real overlap at a
  narrower width. **Since the
  footer became fixed, permanently-visible chrome (`position: fixed; bottom:
  0;`, see the footer's own note elsewhere in this file), all four numbers
  above also include its rendered height (62px at normal widths)** — the
  footer now consumes part of this budget exactly the way the header/nav/
  toolbar/bulk-bar already did. **At the app's one mobile breakpoint
  (`max-width: 640px`) there are four further `.table-wrap` max-height
  overrides scoped to that media query, and their constants (`392`/`416`/
  `494`/`518`) are NOT simply the four desktop base numbers plus a mobile
  footer-height delta** — an earlier attempt at this calibration made
  exactly that mistake (reusing `302`/`262`/`376`/`336` plus a ~97px footer
  delta, giving `399`/`359`/`473`/`433`) and it was wrong, because it never
  re-measured how much taller the header/toolbar/nav chrome itself renders
  at mobile widths. The correct `392`/`416`/`494`/`518` were measured
  as the actual combined "everything above `.table-wrap`, plus the mobile
  footer's own height" total, directly via `getBoundingClientRect()`, not
  derived from the desktop numbers at all. These four also use the
  **worst-case (320px-width) measurement across the whole 320–640px
  breakpoint range** — both the chrome height and the footer's own height
  shrink as the viewport widens within that range, so a single constant
  picked from the narrowest, tallest-chrome end of the range means growing
  extra room (not overlap) toward the wider end of it — the same "accept
  extra gap, never accept overlap" principle already established above for
  the nav-style/bulk-bar desktop numbers. **Re-measured after the toolbar
  was capped to a single horizontally-scrollable row** (see that fix's own
  note just below): at 640px width (the wide end of the mobile range)
  `.table-wrap` now renders at 408px tall with the tabs nav / 384px tall
  with the sidebar nav (60-doc seed, 800px-tall viewport, both measured via
  `getBoundingClientRect()`) — several rows' worth of real table, not the
  ~58px/one-row sliver an earlier version of this note described against
  the old, pre-toolbar-fix constants. The extra room toward the wide end of
  the range is real and intentional (per the "accept extra gap, never
  accept overlap" principle above), but no longer the "close to unusable"
  problem it once was; the toolbar fix substantially improved this
  specific consequence as a side effect, not just moved the number
  slightly. A real intermediate breakpoint (or a continuous/`clamp()`-based
  constant) would still shrink that extra room further, but it's no longer
  a correctness or usability gap worth tracking as one. Worth keeping in
  proportion, though: the File System Access API this whole app depends on
  (see that note further below) isn't available on iOS Safari or Chrome
  for Android, so this mobile breakpoint mostly matters for someone
  narrowing a desktop browser window, not an actual phone.
  **`.table-wrap` also has its own mobile `padding-bottom` (`32px`), and
  CSS padding can't be compressed below its declared value by `max-height`**
  — a box whose `max-height` computes smaller than its own padding sum
  still renders at (at least) that padding sum, never the smaller
  `max-height` value (confirmed directly: a minimal `overflow:auto;
  padding-bottom:32px; max-height:6px` box renders at `32px`, not `6px`).
  This mattered concretely for the `.bulk-bar-visible` mobile variants, so
  `#main-layout.bulk-bar-visible .table-wrap` and
  `#main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap`'s mobile
  rules also set `padding-bottom: 0` (overriding the general mobile
  `32px`), removing that floor so the box can actually shrink all the way
  down to whatever `max-height` says.
  **The mobile calibration used to have one further, genuinely unavoidable
  wrinkle at the single narrowest, shortest corner (320px width, ~800px-or-
  shorter viewport height, bulk-action bar visible)**: the header+toolbar+
  nav+bulk-bar chrome *by itself*, before `.table-wrap` rendered anything
  at all, used to be taller (measured `723px` tabs / `747px` sidebar at
  320px width) than the room left once the fixed footer reserved its own
  space in a viewport that short, producing a small, structural overlap no
  `.table-wrap` CSS alone could fix. **This corner was closed outright**
  by capping `.toolbar` to a single horizontally-scrollable row
  (`flex-wrap:nowrap` plus `flex-shrink:0` on its children — see the
  `.toolbar` CSS and its own comment in `dossiary.html`'s mobile media
  query) rather than by further `.table-wrap` tuning: `.toolbar` wrapping
  onto many rows at narrow widths, not the bulk-action bar, was the real
  driver of the old worst-case mobile chrome height, and pinning it to one
  row shrank that chrome enough that the corner no longer occurs — verified
  empirically (see below) at `gap=0.0px`, not overlapping, across all four
  nav-style × bulk-bar combinations at 320px width. Worth keeping as
  institutional memory in case a future change to the toolbar's contents
  (e.g. adding enough new buttons that even a single scrollable row grows
  taller than expected) reintroduces tall chrome here and this needs
  revisiting. **The real trade-off of this fix**: at narrow widths, toolbar
  controls are no longer all visible at once the way they were when the
  row wrapped onto several lines — they're still reachable, but only via
  horizontal scroll, with no visible scroll affordance on platforms that
  use overlay scrollbars (e.g. macOS), so a person may not immediately
  realize there's more toolbar to scroll to.
  All of these numbers were verified empirically
  (`getBoundingClientRect()` on `#table-wrap` and `footer`, confirming
  `#table-wrap`'s rendered bottom edge lands exactly at the *footer's* top
  edge in every case where there's actually enough room for it to) — worth
  restating since that same class of check has already caught real drift
  more than once: the *sidebar* nav-style's inherited value silently going
  stale (real value `256`, not the `230` a straight "no extra height, so
  reuse the old number unchanged" assumption would have kept) from
  unrelated header/toolbar changes made well before the nav existed; this
  file's own `295`/`256` figures, quoted in an earlier version of this
  note, having drifted from the code's actual `302`/`262` by the time the
  footer-pinning feature touched this area; and the mobile constants
  described just above being derived from the wrong base entirely on the
  first attempt at this same feature, only caught by re-measuring rather
  than trusting the earlier arithmetic. If you ever adjust the
  header/toolbar/nav/footer layout, recalibrate the same way — verify
  empirically, e.g. checking `getBoundingClientRect()` on `thead th`
  before/after a large internal scroll stays roughly constant, or that
  `#table-wrap`'s own bottom edge lands at the fixed footer's top edge —
  rather than assuming a nearby value, or an old comment's value, is still
  correct.
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
  documents SET archived = ?` from the detail panel's Archive/Unarchive
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
  values and the empirical-verification story, including why the two
  styles' constants are each independently calibrated to their own
  worst-case toolbar-wrapping width rather than related by a fixed
  structural offset.
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
  time from a document's own detail-panel action buttons ("Add to Collection"
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
  the detail-panel single-document action buttons use — no special
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
- **The detail view is a persistent side panel (`#detail-panel`), not a
  modal** — `openDetail(id)` keeps its name (it still means "show this
  document's detail content") but now renders into `#detail-panel-body`
  instead of `#modal-root`, and drops the backdrop/close-button/Escape
  chrome that made it a modal (a panel isn't dismissed, it's collapsed).
  This replaced a full-screen modal that hid the table entirely while
  open, matching legacy Mariner Paperless's own persistent "Details" side
  panel instead. **`selectedDocId`** (module-level, distinct from
  `selectedDocIds`, the multi-select `Set` bulk actions use) tracks which
  single row the panel is showing, `null` meaning nothing selected — the
  panel then shows a plain empty-state message rather than blank content.
  Row click sets it, applies a `.row-selected` highlight to that `<tr>`,
  and calls `openDetail(id)`; `render()`'s own rebuild of `tbody` on every
  call means the highlight has to be reapplied after each rebuild (a
  `tbody.querySelector('tr[data-id=...]')` lookup right after the rows are
  rendered), and `render()` also invalidates `selectedDocId` back to
  `null` — refreshing the panel to its empty state — whenever the
  currently-selected document falls out of the active view's filtered/
  sorted set (deleted, archived out of view, or excluded by a filter/
  search change). **`openDetail(id)` itself is the authoritative setter of
  `selectedDocId`**, not just a content-rendering function — it sets
  `selectedDocId = d ? d.id : null` from whatever document it actually
  finds (or fails to find), right after its own `allDocs.find()` lookup.
  This means `render()`'s own invalidation above doesn't always have the
  last word: several action handlers (e.g. `toggleArchived()`) call
  `render()` first — which zeroes `selectedDocId` if the acted-on document
  fell out of the current filtered/sorted view — and then call
  `openDetail(id)` again afterward with that same original id purely to
  refresh the panel's displayed content. Because `openDetail()` re-asserts
  `selectedDocId` unconditionally, that trailing call re-selects the
  document too, re-highlighting its row if one still exists and leaving
  the panel showing its content even if the row doesn't (e.g. it just got
  archived out of the currently-visible view). This is intentional —
  quick "undo" reachability right after an action, not a bug — not an
  invalidation loophole to close. **Clicking a row never auto-expands a collapsed
  panel** — selection, highlighting, and content-refresh all happen
  unconditionally on every row click, but panel *visibility* is
  controlled only by the toolbar's own `#detail-panel-toggle-btn`,
  deliberately: if a row click also expanded the panel, the panel's own
  collapsed-by-default setting (see below) would stop mitigating anything
  — it would spring open on literally the first row click anyone ever
  makes.
  **The panel's expanded/collapsed state is a per-library `settings` row**
  (`detail_panel_expanded`), following `nav_style`'s exact
  `loadNavStyle()`/`saveNavStyle()`/`applyNavStyle()` pattern
  (`loadDetailPanelExpanded()`/`saveDetailPanelExpanded()`/
  `applyDetailPanelExpanded()`, toggling a `detail-panel-expanded` class on
  `#main-layout`) — except the default is collapsed (`false`) rather than
  one of two named states, since defaulting to expanded would undercut the
  entire reason this shipped collapsed-by-default: an always-visible panel
  costs real horizontal table width, and the person who raised this
  feature (comparing it to Mariner's own panel) explicitly worried about
  losing that space. Below the app's one mobile breakpoint
  (`max-width:640px`), the panel force-collapses regardless of the saved
  preference — `#main-layout.detail-panel-expanded .detail-panel{
  display:none; }` inside the media query, matched in selector specificity
  to the base `#main-layout.detail-panel-expanded .detail-panel{
  display:flex; }` rule it overrides (a lower-specificity `.detail-panel{
  display:none; }` there would lose to the more specific rule and fail to
  collapse anything) — a true side panel doesn't fit a phone-width
  viewport any better than a full sidebar nav does (see that note's own
  mobile-collapse precedent above). The toggle button itself is hidden
  (not disabled) in Reports view, since that view renders its own
  aggregate content rather than the shared document table — there's no
  row for the panel to ever reflect there, same "hidden when the control
  is inert for this view" pattern already used for "Show archived".
  **The panel deliberately reuses `.table-wrap`'s own four `max-height`
  calibration constants (410/370/484/444, plus their nav-style/bulk-bar
  combinations) for its own `max-height`, rather than introducing new
  ones** — the panel is a flex sibling of `.table-wrap` inside a new
  `.table-detail-row` wrapper, sitting at exactly the same vertical offset
  under exactly the same header/toolbar/nav/bulk-bar/footer chrome, so the
  same "how much vertical room is left below that chrome" figure applies
  to both; the reasoning is sound and was spot-checked the same empirical
  way as everything else in this section at authoring time
  (`getBoundingClientRect()`, confirming the panel's own bottom edge lands
  at the fixed footer's top edge with no overlap), not assumed just
  because the numbers happened to match structurally — but, unlike
  `.table-wrap` itself, this has **no automated regression test guarding
  it**: `tests/test_footer_pin.py` is the file that actually enforces this
  class of check on an ongoing basis, and it was never extended to also
  measure the panel's own bottom edge. A future layout change could
  silently drift the panel out of alignment with the footer without any
  test failing to catch it — don't read this note as claiming coverage
  that doesn't exist. This is
  purely a **horizontal** layout change — the panel sits *beside* the
  table, not above or below it — so none of `.table-wrap`'s own four
  constants needed to move; reusing them for a same-height sibling is not
  the same thing as touching them.
  **Two call sites that used to rely on an implicit trick no longer can.**
  Before this change, `openEditForm()`'s Cancel button and
  `saveEditedDocument()`'s success path both called `openDetail(id)`,
  which — since the detail view and the edit form shared the same
  `#modal-root` — implicitly closed the edit modal *and* reopened detail
  content in one call, just by overwriting the same container. With the
  panel and the edit modal now separate, simultaneously-existing elements,
  that implicit behavior is gone: **Cancel** now just calls `closeModal()`
  and does nothing else — the panel, if open, already shows whatever
  document Edit was opened from, and Cancel deliberately does not force a
  collapsed panel open or re-render content that didn't change. **Save**'s
  success path now does two explicit things the old single call used to
  do for free: `closeModal()` to dismiss the edit modal, and
  `selectedDocId = id` (before the `render()` call that reapplies row
  highlighting) so the just-saved document becomes the new panel
  selection — this specifically covers editing reached via the row-level
  `.row-edit-btn` shortcut (see its own note above), which bypasses row
  selection entirely on the way in, so without this the panel would still
  be pointing at whatever (if anything) was selected before, not the
  document that was just edited.
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
- **Every filter dropdown built by `populateFilters()`** (Category, Type,
  People, and any dynamic custom-field filter) also carries a "— Not set —"
  option, right after "All X," so a document missing that field entirely
  can be filtered to directly. It's driven by a dedicated sentinel,
  `FILTER_UNSET` (`'__unset__'`), deliberately distinct from the plain
  empty string `populateFilters()`'s own "All X" option already uses to
  mean "this filter isn't active" — reusing the empty string for both
  would make "not set" indistinguishable from "no filter selected."
  `matchesCriteria()` — the single predicate both the live toolbar and
  saved Smart Collection criteria already share (see the Collections note
  above) — is the only place that interprets the sentinel, so this works
  everywhere filtering already composes (the toolbar, Smart Collections,
  Reports' own filter composition) with no separate code path: a scalar
  field (category/type) checks `!!d.category`, the multi-valued People
  field checks `(d.people||[]).length > 0`, and a dynamic field checks
  `actual !== undefined` against `d.customFields`. That last check is
  deliberately `!== undefined`, not a falsy check — a checkbox field
  explicitly saved as unchecked is stored as the string `'0'`, which is
  real, meaningful data, not "unset," matching
  `readDynamicFieldValues()`'s own existing rule for the save path (an
  unchecked box is meaningful data, not "empty"); only a field with no
  saved value at all should match "— Not set —".
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
  see the People note above for why) or for `'Amount'` by name (its flags
  are deliberately kept off — see the sentinel-fields note above — so an
  editable checkbox that visibly did nothing would just be confusing).
  Currency is no longer excluded here — it's a completely ordinary field
  for capability purposes now, same as Payment method, and gets these
  checkboxes like any other text field.
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
- **UI language support (started as English/German, later generalized to
  six languages — English, German, Spanish, French, Chinese Simplified,
  Chinese Traditional)** is a flat per-language dictionary (`STRINGS.en` /
  `STRINGS.de` / `STRINGS.es` / `STRINGS.fr` / `STRINGS['zh-Hans']` /
  `STRINGS['zh-Hant']`, 278 keys each), a lookup helper (`t(key,
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
  key exists in *every* supported language's own `STRINGS` block (looped
  over `SUPPORTED_LANGS` itself, not a hardcoded language pair — see the
  "Generalized from two languages to six" note just below), and that each
  language's key set matches `STRINGS.en`'s exactly, not just "referenced
  key present" — a static safety net against the one mistake
  `test_i18n.py`'s scenario-by-scenario clicking can't exhaustively rule
  out (a key added to English but never given a translation in some other
  language, or vice versa, anywhere in this ~270-key, hand-maintained
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
  **Generalized from two languages to six** (`SUPPORTED_LANGS = ['en', 'de',
  'es', 'fr', 'zh-Hans', 'zh-Hant']`, plus `NATIVE_LANG_NAMES` — each code's
  own name for itself, `简体中文`/`繁體中文` etc., deliberately never run
  through `t()`, since a language's name for itself in its own script is
  what belongs in a language picker no matter which language is currently
  active — `LANG_AUTODETECT`, and `DATE_LOCALE`) once Spanish, French, and
  both Chinese scripts were added on top of the original English/German
  implementation described above. None of the dictionary/lookup-helper/
  `applyI18n()` shape above had to change to support this: `STRINGS` simply
  grew from two top-level keys to six (278 keys apiece now, not ~260), and
  `t()`'s own `STRINGS[currentLang][key] ?? STRINGS.en[key] ?? key`
  fallback chain already generalizes for free, since it was never
  hardcoded to specifically `en`/`de` in the first place.
  `tests/test_i18n_coverage.py` loops over `SUPPORTED_LANGS` the same
  way now, rather than a hardcoded `STRINGS.en`/`STRINGS.de` pair — going
  from two languages to six changed that check's loop bound, not its
  underlying logic.
  **The old `EN | DE` two-state `#lang-toggle` button was replaced by a
  `<select id="lang-select">`** listing all six languages via
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
- **Field descriptions** (`field_descriptions`, `loadFieldDescriptions()`/
  `saveFieldDescription()`, the "Field Descriptions" section in Field
  Settings — `.fs-descriptions`, `renderFieldDescriptionsList()`) let a
  person attach a short, optional hint to any field — the five built-ins
  (Category, Subcategory, Document Type, Date, Tags) plus every generic
  custom field — shown as a `.field-hint` line under the field's label in
  both the capture and edit forms. **`field_descriptions` is keyed by
  `field_name TEXT PRIMARY KEY`, not `fields.id`**, deliberately — the
  five built-ins have no `fields`-table row at all (they're real `<input>`s
  hardcoded into the capture/edit form markup, not part of the generic
  fields system — see the Custom fields note above), so a `fields.id`
  foreign key simply couldn't reach them. Keying by name instead covers
  both groups — built-ins and generic custom fields — with one uniform
  table and one uniform `fieldDescriptions[name]` lookup, rather than a
  built-in-only mechanism plus a second, `fields.id`-keyed one for custom
  fields. **`FIELD_DESCRIPTION_BUILTIN_NAMES`** (`['Category',
  'Subcategory', 'Document Type', 'Date', 'Tags']`) is a hardcoded array
  for the same reason it can't be derived from anything: unlike
  `dynamicColumnDefs()` or `getUsedDocumentTypes()`, there's no table row
  or other in-memory list that already enumerates "fields with a real form
  input but no `fields` row" — Amount, Currency, and Payment method used
  to be in that category too, but aren't anymore (see the sentinel-fields
  note above), so this array is exactly, and only, the five names left
  over after that migration. **A custom field can share a built-in's exact
  name** (e.g. a Mariner-migrated library with a custom "Date" field, since
  the sibling migration script copies field names generically with no
  reserved-word check) — `renderFieldDescriptionsList()` filters
  `fieldDefs` against `FIELD_DESCRIPTION_BUILTIN_NAMES` before appending
  the custom-fields tail, so the built-in always wins the single shared
  row and the list never shows the same name twice; `addInlineCustomField()`'s
  own reserved-name list was deliberately left alone rather than extended
  to also block this collision, since doing so would change behavior for
  existing libraries that already have such a field, a bigger change than
  this feature warranted.
  **`renderFieldDescriptionsList()` is deliberately NOT re-rendered when
  the selected document type changes in Field Settings**, unlike
  `renderFieldSettingsFieldColumns()` (the Fields/Display Fields columns,
  which are genuinely scoped to `fsSelectedType`) — a description belongs
  to the field itself, independent of which type(s) it happens to be
  attached to, the same "property of the field, not of its relationship to
  `fsSelectedType`" reasoning the Per-field capability checkboxes note
  above already established for `show_as_column`/`autocomplete`. The list
  is built once per modal open and stays correct regardless of which type
  is subsequently selected in the other two columns.
  **The save-on-blur handler has no revert-on-empty guard**, unlike the
  Collections rename input it's modeled on (the Manage Collections modal's
  own rename input resets back to the collection's real name on an empty
  blur, rather than saving a blank one — see `tests/CLAUDE.md`'s Collections
  entry) — because an empty description is a
  valid, meaningful value here (it just means "show no hint for this
  field"), not an error state to reject the way an empty collection name
  would be. Blurring an emptied input saves the empty string via the same
  `INSERT OR REPLACE` path as any other value, and the corresponding
  `.field-hint` line correctly disappears from the capture/edit forms.
  **Description text is never run through `t()`** — like a field's own
  name, it's free-form content someone typed for their own library, not
  app chrome; running it through the translation lookup would be wrong
  twice over — it isn't one of this app's ~278 known UI strings in the
  first place, so `t()`'s fallback would just echo it back unchanged, and
  passing it through `t(key, params)` at all would risk a literal `{...}`
  substring in someone's own description being misread as a substitution
  placeholder (`test_field_descriptions.py`'s own Scenario 9 checks
  exactly this: a description containing a literal `{label}` renders
  verbatim). **Document Type is the one built-in field that already had
  its own permanent `.field-hint` line before this feature** (the "Not in
  the list? Type a new one — it'll be created." autocomplete hint) — its
  new description hint is a SECOND, separate `.field-hint` div appended
  after the existing one, not a replacement; a configured description
  shows both, stacked, and a field with no description set continues
  showing just the original hint exactly as before.
- **Comma-aware autocomplete for multi-valued fields** (`wireCommaAutocomplete()`)
  fixes a real limitation of native `<input list="...">`: the browser only
  ever matches suggestions against the *whole* input value, never a
  substring of it, so a comma-separated field (People/Author/Collaborator/
  any other person-type field, and Tags) only ever offered suggestions for
  the *first* entry typed — after "Birgit, " and starting a second name,
  nothing suggested, since no datalist option's value literally starts
  with "Birgit, A". `wireCommaAutocomplete(input, datalistId)` replaces the
  native mechanism by hand: on every keystroke it takes the text after the
  last comma, filters the given datalist's own `<option>` values by it
  (case-insensitive substring, excluding names already used earlier in the
  same input), and renders a small clickable/keyboard-navigable suggestion
  list (`.comma-autocomplete-dropdown`) positioned under the input via the
  existing `.field-with-clear` wrapper's `position:relative` — the same
  wrapper every comma-separated field already had for its clear button, so
  no new markup was needed there. The native `list` attribute is removed
  once this takes over (`input.removeAttribute('list')`), so the browser's
  own broken-for-this-case popup never appears alongside the real one.
  Selecting a suggestion (click, or Enter on a keyboard-highlighted item)
  replaces just the current segment and appends `", "` so typing the next
  entry can continue immediately. Wired from three places: the generic
  `applyDynamicFieldsForType()` rebuild pass (covers every person-type
  field, People included, the same way its clear-button rewiring already
  does), `addInlineCustomField()`'s own insert path (a newly-created
  person-type field, appended without a full container rebuild), and two
  one-off calls for `#f-tags`/`#e-tags` (Tags isn't part of the dynamic
  fields system at all, same as its clear button). A
  `dataset.commaAutocompleteWired` guard makes the function idempotent,
  though in practice every one of these three call sites only ever wires a
  freshly-rendered element, so the guard is defensive rather than
  load-bearing.

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
