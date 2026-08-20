# tests/ — testing conventions and coverage

Guidance for Claude when working under this repo's `tests/` directory. Loads only when Claude touches files here — the parent repo's `../CLAUDE.md` covers everything else about Dossiary.

## How this was tested (useful context for future changes)

There's a real, runnable Playwright regression suite in `tests/` — **59
scripts covering most of the app's actual functionality** (58 of them
Playwright-driven; one, `test_i18n_coverage.py`, is a plain static
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
no stored preference yet; selecting a language from the `<select
id="lang-select">` dropdown overriding that and persisting across a
reload even though the browser's own locale still says German; date
formatting following the UI language choice rather than OS locale;
translated content across the nav, toolbar, stats bar, table
headers/rows, detail modal, capture and edit forms (including the shared
inline add-field validation message and reused OCR strings), Field
Settings, Manage Collections, Reports, the Libraries/licenses modal, and
the drag-and-drop overlay; the recent-libraries list and empty-state
screen re-translating live on toggle, not just on next load; two
regressions caught by inspecting raw `innerHTML` rather than
`inner_text()` alone — a duplicated "Important:"/"Wichtig:" label and a
nested `<b><b>...</b></b>` from double-wrapping a substituted name); and,
once the app grew from two supported languages to six, auto-detection for
each of the other four (Scenarios 24-27 — Spanish from an `es-ES` locale,
French from `fr-FR`, Chinese Simplified from `zh-CN` and from a bare `zh`
locale with no region, and Chinese Traditional from `zh-TW`, specifically
confirmed to win over Chinese Simplified's own bare-`zh` catch-all rather
than being shadowed by it) plus a dedicated regression scenario (28) for
the case that motivated making `loadLang()` locale-major instead of
rule-major — `navigator.languages = ['en-US', 'zh-CN', 'zh']` (English
first, Chinese as a secondary input language) correctly resolving to
English rather than Chinese — which doubles as a check of `#lang-select`'s
full option list, not just its currently-selected value: exactly the six
expected language codes, with native names (e.g. `简体中文`) rendering
correctly. Also a static i18n key-coverage check (`test_i18n_coverage.py` — no Playwright,
just a grep-based Python script confirming every `data-i18n`/
`data-i18n-placeholder`/`data-i18n-title`/`data-i18n-aria-label`
attribute value and every `t('key')` call argument in `dossiary.html`
exists in every one of the six languages' own `STRINGS` block — looped
over `SUPPORTED_LANGS` itself (parsed straight out of `dossiary.html`,
not hardcoded), so a language added to the dropdown without a matching
`STRINGS` block fails this check loudly instead of silently crashing the
app for whoever gets auto-detected or manually switched into it — and
that each language's key set matches `STRINGS.en`'s exactly, not just
"referenced key present"; verified during development to actually catch a
real regression, not just trivially pass, by
temporarily renaming one `STRINGS.de` key and confirming the script
failed with that exact key reported missing, then reverting), and search
across all of the above. Also the fixed-footer/`.table-wrap` calibration
itself (`test_footer_pin.py` — a 60-document seed, the same
non-diagnostic-gap-avoiding size `test_collections.py`'s own Scenario 30
uses, confirming `#table-wrap`'s bottom edge lands with no overlap against
the fixed footer's top edge across all four nav-style x bulk-bar-visible
combinations at a 1280x720 desktop viewport, plus the app's one mobile
breakpoint at 320x800 (both nav styles, bulk bar hidden and visible),
375x800 (tabs, bulk bar hidden and visible), and 640x800 (sidebar, bulk
bar hidden and visible) — and that the footer itself is always fully
within the viewport, needing no scroll to reach. **All scenarios now
assert the same tight `min_gap=-2` tolerance, including at 320px width
with the bulk bar visible** — an earlier version of this suite had to
carve out a bounded-ceiling exception for that one corner (both nav
styles), since it had a small, real, structurally unavoidable overlap;
capping `.toolbar` to a single horizontally-scrollable row (the fix this
whole test file's own filename-adjacent feature landed) closed that
corner outright by shrinking the mobile chrome height enough that it no
longer occurs, so the exception was removed once the corner was
confirmed closed (`gap=0.0px` at that combination, same as every other
scenario). Vacuousness was confirmed by temporarily re-widening the base
desktop constant and confirming the test then fails with a large,
clearly-wrong gap. The same file also asserts (not just prints) that the
narrow-width toolbar genuinely overflows horizontally with every expected
control still present in the DOM (`toolbar_info`), and that the Columns
dropdown, opened at 320px width, is fully contained within the viewport
rather than clipped to a sliver by `.toolbar`'s own `overflow-x:auto`
forcing `overflow-y` to compute as `auto` too (`columns_menu_info`) — the
one real regression a final review of the toolbar-scroll branch found,
caught by no other test in the suite since every other scenario that
opens the Columns menu runs at desktop viewport width, where `.toolbar`
never becomes an overflow container in the first place), and the "not set"
filter option (`test_not_set_filter.py` — the option appears in every
filter dropdown (Category, Type, People, and dynamic custom fields); each
field type's "not set" filter narrows to exactly the right documents with
no saved value; a checkbox field explicitly saved as unchecked (`'0'`) is
correctly excluded as real data, not "unset"; and a Smart Collection saved
with a "not set" filter active reproduces the same filtering from its own
saved criteria, proving the shared `matchesCriteria()` path works for both
live toolbar and persisted Smart Collection filters), Currency opting into
the generic column/filter/autocomplete/sort system and the new Amount range
filter (`test_amount_currency_filter.py` — Currency's own Column capability
checkbox appearing in Field Settings while Amount's still doesn't; the
Currency column appearing in the Columns menu as `field-3`, hidden by
default, showing real per-row values once toggled on, and sorting correctly
via the existing generic `sortKey.startsWith('field-')` mechanism with zero
new sort code; the Currency filter dropdown listing distinct values plus
"— Not set —" and narrowing correctly for both; a Smart Collection saved
with a Currency filter active reproducing the same filtering from its own
saved criteria; Reports' breakdown-field dropdown correctly excluding
Currency, since it's already the report's own top-level grouping; the
Amount min/max range filter narrowing correctly for min-only, max-only,
both together, and an empty-result min>max case, with a document that has
no Amount at all correctly excluded from every range comparison since NaN
never satisfies a `>=`/`<=` comparison; "Amount not set" matching only a
document with no saved Amount value at all, critically not one whose
Amount is explicitly saved as `0` (real data, not "unset"); the min/max
inputs disabling while "not set" is checked and re-enabling once it's
unchecked; typing into an enabled min input leaving "not set" unchecked;
the Currency filter and Amount "not set" composing correctly with plain
AND, with no dedicated combo code, proving `matchesCriteria()`'s existing
composition already covers it; a Smart Collection saved with an Amount
range filter active reproducing the same filtering from its own saved
criteria, mirroring the Currency Smart Collection scenario's structure;
`resetAll()` clearing the Amount filter's min/max/"not set" state when
switching libraries via the real `#reload-btn` ("Switch library") code
path, reproducing the exact reported bug — a leaked "not set" filter would
otherwise silently hide every document in the newly-opened library; and,
as a second, independent scenario in the same file, the
`migrateCurrencyColumnDefault()` backfill migration correctly flipping
Currency's `show_as_column`/`autocomplete` from `0`/`0` to `1`/`1` for a
library that already ran the old `migrateSentinelFieldsToGeneric()` before
this feature existed, and — the idempotency property — NOT re-flipping it
if a person already manually turned it back off after an earlier run of
this same backfill), and field descriptions (`test_field_descriptions.py` —
the `field_descriptions` table existing for both a seeded/reopened library
and a brand new one taken through `initNewLibrary()`; the Field Settings
"Field Descriptions" list ordering the five built-ins first, in order, then
every custom field, including the auto-created sentinel fields (Payment
method, Amount, Currency, People); typing a description and blurring
persisting it, and the saved value reappearing on reopening Field Settings;
the description hint appearing under the right field's label, correctly
scoped to that one field, in **both** the capture and edit forms, for a
built-in (Category), a custom text field (Organization), and one of each
other generic field type (checkbox, number, date, person) — proving
`renderGenericFieldHtml()`'s checkbox and text/number/date branches and
`renderPersonFieldHtml()` all got the same treatment; a field with no
description set showing no hint at all (Subcategory); Document Type's
pre-existing autocomplete hint and its new description hint both rendering,
stacked, in both forms, rather than one replacing the other; and description
text containing a literal `{label}` rendering completely verbatim rather
than being run through `t()`'s substitution). This
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
  clause (used by the settings lookup). The Amount/Currency column-and-filter
  branch extended `run()`'s `UPDATE` handling further: a compound
  `WHERE col1 = ? AND col2 = ?` clause (checked before the pre-existing
  single-condition pattern, so it isn't accidentally matched by the
  looser one first), and literal (non-`?`) values inside the `SET`
  clause itself — e.g. `UPDATE fields SET show_as_column = 1,
  autocomplete = 1 WHERE name = ? AND type = ?`, which
  `migrateCurrencyColumnDefault()` sends as a literal-valued backfill
  rather than binding `1`/`1` as params. If a future change sends the app's
  first `UPDATE`/`DELETE`/`SELECT` with a shape the stub doesn't recognize
  yet, extend the stub's regex matching rather than working around it —
  the whole point is exercising the app's real SQL strings. The field-
  descriptions branch registered a new `field_descriptions` table in the
  `FakeDatabase`'s table lists (both the seeded-load and empty-init paths),
  and gave it the same `INSERT OR REPLACE` dedupe treatment `settings`
  already had — real `field_descriptions.field_name` is a `TEXT PRIMARY
  KEY`, so without a matching dedupe branch in the stub, saving two
  different descriptions for the same field name would leave both rows in
  the fake table instead of replacing the first, silently diverging from
  the real schema's own uniqueness guarantee.
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