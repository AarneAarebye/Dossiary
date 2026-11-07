# Test coverage narrative, part 3 of 4: Tools menu, export, sharing, reports, collections, autofill and calendar

Split out of `tests/CLAUDE.md`. This part continues mid-sentence from part 2; the whole narrative was one long paragraph in `tests/CLAUDE.md` and is kept word for word.

Index: `tests/CLAUDE.md`.

or both were deleted from the stub filesystem behind the app's back each
get their own row with exactly the right File/Original indicators; a
document with a `NULL` `original_file_path` and a deleted document with
broken paths are both correctly never flagged; clicking "Re-link…" leaves
the modal open and the table selection unchanged (the
`.broken-link-indicators` wrapper's `stopPropagation` really does keep the
row's own click-to-detail-panel handler from firing -- confirmed
non-vacuous by temporarily removing it); a cancelled picker being a no-op
that also removes its hidden input, and a stale leftover input from an
older browser being swept up by the next attempt (both confirmed
non-vacuous by temporarily reverting the cleanup); re-linking writing the
picked bytes to the exact stored path and removing just that indicator
(or the whole row); `file_hash` recomputed only when the repaired path is
the hash-deriving one (`original_file_path`, or `file_path` for a document
with no original) and left untouched otherwise; and a simulated write
failure leaving the indicator and Re-link button in place with an inline
error and `file_hash` unchanged. Every real re-link goes through
Playwright's `expect_file_chooser()`, not `set_input_files()` on the input
directly -- headless Chromium auto-dismisses an unanswered picker, firing
`cancel`, which now removes the input before `set_input_files()` could
find it), the Library check modal's orphaned tags/people sections
(`test_orphaned_lookups.py` -- a tag or person still referenced by a
non-deleted document is never flagged; one referenced only by a Waste-bin
document is flagged; a person referenced only via a non-People
person-type field (Author) is still correctly recognized as in-use; a
per-row Delete, behind its own `confirm()`, removes just that row and
cascades into the join table; declining that `confirm()` leaves
everything unchanged; "Delete all orphaned" clears every row in a
section in one action behind its own single `confirm()` (plural wording
for 2+ rows; for exactly one row, the singular wording, and declining that
bulk `confirm()` leaves the row and its persisted `tags` row intact); a deleted
tag/person disappears from its autocomplete datalist immediately; and
restoring a Waste-bin document whose tag was deleted while orphaned
brings it back without that tag), the Library check modal's unused-fields
section (`test_unused_fields.py` -- exactly the custom fields no
non-deleted document has a value for are listed, whether set up for no
type, set up for a type (noted "Set up for: Receipt"), or only used by
Waste-bin documents (noted, for a text and a person-type field alike);
a used field and every auto-created field (People/Amount/Currency/Payment
method/Reminder) never listed; declining the `confirm()` deletes nothing;
a single Delete removing the field row, its description, its table
column, and resetting a sort on that column to Imported; "Delete all
unused" confirming with the count and the name of the affected Smart
Collection, then removing the rest -- per-type setup, a Waste-bin
document's value and people, and only the deleted field's filter from
that Smart Collection's criteria -- while the used field's value stays;
and reopening the check listing nothing), fixes found while recapturing
the User Guide screenshots (`test_ui_polish.py` -- `<html translate="no">`
and the notranslate meta present; the composite Inbox-add status message
retranslating on a language switch; a deliberately slowed `getFile()`
proving a superseded `openDetail()` can't write a no-longer-selected
document back into the panel after a switch to a view that doesn't show
it; a hidden-column dynamic filter staying hidden after filters are
rebuilt on the Reports view; nav count badges and "Save as Smart
Collection" staying inside the 220px sidebar in Spanish; and a long,
space-free file path wrapping inside the detail panel -- every check
confirmed to fail against the pre-fix code), the "🛠 Tools" toolbar
dropdown (`test_tools_menu.py` -- "Switch library" sitting in the header
on the same line as the library's name, returning to the start screen's
recent-libraries list without opening the folder picker by itself, and
hidden on the start screen; daily actions visible on the toolbar and the four
occasional ones hidden until Tools opens; items in order; choosing Library check or Manage fields
running it and closing the menu; Escape closing it and returning focus to
`#tools-btn`; an outside click and a second click on Tools closing it;
`aria-expanded` tracking open/closed; opening Tools closing Columns and
vice versa; and the button and items translating with the UI language --
every other test that used one of the moved buttons now clicks
`#tools-btn` first, and `test_footer_pin.py`'s 320px-width check also
confirms the Tools menu opens fully visible, not clipped by the
scrollable mobile toolbar), creating a new library (`test_new_library.py`
-- the no-library screen's name form with its default name and folder
preview, creating as the main action; a name with a slash refused, an
existing `Taken.dossiary` never reused, typing updating the preview and
clearing the error; Enter creating `Family Papers.dossiary` with the
library inside it and nothing in the picked folder, the new library open
under that name; an existing `.DOSSIARY` ending not doubled; a picked
`Prepared.dossiary` folder hiding the form and making "Use this folder as
the library" the main action, which sets the library up in it; and the
untouched default name and preview following a switch to German),
Share (`test_share.py` -- in this Chromium, which can't share files: the
fallback with Export and a prepared mailto listing the documents; with a
fake `navigator.share`/`canShare`: files read before Share is offered, an
unreadable one listed, nothing shared before the click, files named like
exported copies with PDF details, the confirmation; the panel's Share…, a
dismissed sheet staying quiet, a refused one reported, a single document
shared with its title; German labels), details in exported PDFs (`test_export.py`'s later checks -- by default the
copy carries title, subject and keywords with its pages untouched; with the
option off the copy is byte-identical; a PDF pdf-lib can't open copied
unchanged and reported), hiding toolbar buttons (`test_toolbar_buttons.py` -- all shown by default;
the dialog listing the five optional buttons ticked and never Add document
or Tools; unticking hiding them at once and saving the setting; Details
staying hidden after Reports sets its display; the choice surviving a
reopen; ticking one again; German labels), line-item splits (`test_splits.py` -- the Edit form's split toggle; a
line with a comma decimal and a note, the summary of what's split and what
stays; the line saved, shown in the panel and the sidecar; a split-only
category in the Category filter and matching it; a Smart Collection
"Category is"/"is not" rule seeing the line; Reports by Category counting
the line under its own category with the grand total unchanged, its
drill-down, and other breakdowns ignoring it; reopening Edit showing the
saved line; lines over the Amount and a line without an amount flagged and
not saved; a category rename reaching the line; removing every line; the
German summary; and in the capture form: too much refused before any file
is written, the summary, the line saved with the new document and shown in
its panel; `stub_studio2.js` knows the `document_splits` table), the calendar view (`test_calendar_view.py` -- the switch's third button
replacing the table; opening on the newest document's month with its
count; Sunday-first in English, March 1st 2026 the first cell; a date
stored with a time still landing on its day; outside days empty;
undated documents below; previous month and Today (marking today); a
chip selecting with its details, K moving to the previous chip, the
context menu, dragging a chip onto a collection; the search narrowing
the chips; the view remembered after reopening; German month name,
Monday first, March 1st the seventh cell, translated labels; back to
List), collection folders (`test_collection_folders.py` -- the plain list
without folders and no folder picker yet; creating folders (button and
Enter), the folder picker per collection, assignments saved, per-folder
counts; the nav grouping collections under their folders with unfiled
ones last; folding remembered across reopening; a folded folder opening
while dragging over it, taking the drop, and folding again; renaming, and
deleting a folder keeping its collections unfiled; a library copying this
setup getting the folders; German labels), dragging documents onto a collection (`test_drag_to_collection.py` --
real HTML5 drag-and-drop via Playwright: an unchecked row added alone, a
checked row carrying the whole checked selection, a document already there
reported and not added twice, a smart collection not taking the drop, no
file-drop overlay or import during any of it, no highlight left behind, a
grid tile drop, a collapsed Collections section opening for the drag and
closing afterwards, nothing draggable in the Waste bin, and the German
message; `stub_studio2.js`'s `INSERT OR IGNORE INTO collection_documents`
now skips an existing pair like the real primary key does), the Reports pie chart (`test_report_pie.py` -- 10 positive values giving
7 own slices plus "Other" with the right total and share, each of the 7
largest rows' swatch matching its slice and the rest sharing Other's
colour, a negative row without a swatch plus the chart's note, the pie
beside the table and labelled, a single-value currency drawn as a circle,
no pie for a currency with nothing positive or for the multi-valued Tags
breakdown, a slice and "Other" drilling down to the right documents,
Enter on a focused slice, and German labels -- read via `textContent`,
since SVG `<title>` isn't an HTMLElement for `inner_text`), copying another library's setup into a new one (`test_copy_setup.py` --
from a recent library: custom field copied with its id and its
switched-off autocomplete, no built-in field duplicated, document types'
field order, field descriptions, the smart but not the manual collection,
settings but not `last_backup_at`, no documents/tags/people, the status
line naming the source, the copied column and smart collection showing,
and the source's `library.sqlite` byte-for-byte unchanged; "Another
library folder…" adding and selecting the picked folder, used with "Use
this folder as the library"; a picked folder without `library.sqlite`
reported with no `.dossiary` folder created; a cancelled picker keeping
the earlier choice; the options retranslating to German; and "Nothing"
giving a plain library), Library check's unused preview files
(`test_unused_previews.py` -- an old PNG and a preview in a subfolder
listed with their total size, a Waste-bin document's preview and the
current JPEG not listed, `.DS_Store` ignored; declining the confirmation
deleting nothing, confirming deleting exactly the two, the result shown in
place, and the next check finding nothing), the grid view (`test_grid_view.py` -- Grid
by default for a library that never chose a view (the test sets
`window.__STUB_KEEP_DEFAULT_VIEW`, since the shared stub otherwise starts
every library in List so the rest of the suite can drive the table),
choosing List showing the table and being saved, the count line's text
unchanged; Grid showing one tile per
listed document in the table's order (Waste bin excluded), the table
hidden, the choice saved, and the count row still exactly as tall as the
count line alone; a stored preview shown, a placeholder with the file kind
for none, "Preview missing" for a stored path whose file is gone, tiles
taller than the old 140px panel preview; click selecting and showing
details, J moving to the next tile, right-click opening the document menu,
tile checkboxes driving the bulk bar; the size slider widening tiles and
being saved; "Create missing previews (2)" making and saving both
previews as real JPEG bytes (`thumbnails/<id>.jpg`), marked full size,
showing them and disappearing; "Recreate older previews (4)" recreating
two tiny previews and one whose file is missing, keeping a 600x800 one
untouched (only marked), the button disappearing, the status line's
counts, and the old preview file left on disk; reopening keeping grid and size;
German labels; back to List; no switch in Reports. Pass a path to save a
screenshot), page tools (`test_page_tools.py` -- "Edit
pages…" offered for a PDF in the panel, not for an image nor in the
right-click menu; one card per page, Save disabled until something changes,
rotation shown on the thumbnail, a removed page dimmed, the summary counting
pages and documents; rotate + reorder + remove + split writing the edited
copy in place next to an untouched original and a new split document with
the remaining pages in the new order, its title, category, tags, people,
amount, collection membership, hash and sidecar; a document without an
original keeping its file as the original and getting `<stem>_edited.pdf`,
text layer recorded, OCR text kept; an image added from a file as the last
page (answered through `expect_file_chooser()`); removing every page
refused; the bulk bar's More menu opening/closing (aria-expanded, Escape,
outside click, choosing an item) and the bar staying one line; Combine
hidden for one document, reorderable, a read-only file named in the Edit pages error with the dialog left open for
another try; the kept image document getting the
combined PDF next to its original with the hash-matching image copy
removed, OCR text joined, the other document binned with its files intact;
pdf-lib in the Libraries modal; German labels. The shared stub gained a
fake pdf-lib (`window.PDFLib`) whose "PDFs" are `%PDF-FAKELIB` plus a JSON
page list `{src, page, rotation, text}`, and the fake pdf.js reads that
list for page count and per-page text, so a test can check exactly which
pages ended up where. Real pdf-lib 1.17.1 was also checked by hand in a
browser: rotation, reordering and an image page come out right), Smart
Collection rules and editor
(`test_smart_collections.py` -- every rule kind evaluated directly through
`window.__DEBUG_smartMatchIds`: text is/is not/contains/empty
(case-insensitive), tags and person includes/excludes/empty, checkbox
checked/unchecked/not set, Amount is/at least/at most/between/empty, any
text, archived/in-review status, dates on/before/between/empty and
relative ones (last 30 days, this month, this year, last year, expected
values computed from today so the test doesn't age), all vs. any, and no
rules matching every non-deleted document; an old toolbar-snapshot
collection opening in the editor as the equivalent rules with a live count,
editing and saving it as rules and the collection view following; a new
collection refusing a missing name or empty value, relative-date and
value-less status rules, two boxes for "between", removing a rule, the
count switching between all and any; the toolbar's "Save as Smart
Collection" storing rules; a category rename updating rule values; a field
deletion removing only its rule; the editor in German), rename or merge values (`test_manage_values.py`
-- values listed with counts, the Waste bin included; merging two
categories after confirming, with a Smart Collection's category following;
a cancelled merge changing nothing; merging a document type, dropping the
old type's field setup, keeping the target's, and moving the default type
and a Smart Collection's type filter; merging two tags that differ only in
case without duplicate links; renaming a person in place, then merging
them; renaming a Payment method value with its Smart Collection filter; an
empty name refused; Escape cancelling without closing; the sidecar and the
category filter updated), backup (`test_backup.py` -- the "no backup
yet" reminder on the open status line; a folder inside the library
refused; a dated folder with every library file byte for byte, a fresh
`library.sqlite`, `.DS_Store` skipped, `dossiary.html` (the faked
jsDelivr download, replacing the library's own older copy) and
`How to open.txt` naming the backup folder; offline with nothing stored,
the backup completing without them and saying so; a second backup getting its own
"(2)" folder; no reminder right after a backup; an overdue one depending
on the configured days, retranslating on a language switch, and 0
switching it off; the dialog unclosable mid-copy and Stop removing the
incomplete copy), export (`test_export.py` -- a folder inside
the library refused; files named by date and title with clashes numbered
(including one already in the destination, left untouched) and unsafe
characters replaced; the copies byte-identical; a missing file reported
by name; `index.csv` with a row per exported file, quoting, amount/
currency/tags/custom-field columns, `,` in English and `;` in German, and
omitted when unticked; `files/` unchanged -- the stub's folder picker takes
a one-shot `window.__NEXT_PICKED_DIR`, and its directory handles gained
`resolve()`), folder import (`test_import_collection.py` -- the "Import a folder or earlier export" titles and the add-to-a-collection step for a folder with an `index.csv`: new or existing manual collection, only listed files, a skipped duplicate with a row added, no empty collection, a failed save kept in the summary; `test_import_folder.py` -- a round trip:
export two documents in German (`;`, German headers) plus a loose file,
import into an empty library; a folder inside the library refused; title,
date, kept import date, category, subcategory, type, notes, Amount/
Currency, tags, People and a custom field restored and the documents
filed, the new type given the fields it used; the loose file flagged for
review; hidden files ignored; the sidecar carrying the details; the
folder unchanged; a second import skipping all three as duplicates; an
empty folder reported; a folder without `index.csv` adding every file for
review), export as library (`test_export_library.py` -- the new
library's database built through `window.__DEBUG_buildExportLibrary`:
only the exported documents with ids kept and their tags, people, custom
values, splits and snoozes; "only what's used" keeping just the fields
with values plus the built-ins, their types' setup, their descriptions,
settings minus `last_backup_at`/`scan_bridge_url`/`scan_last_settings`,
and a manual collection holding only exported documents; "everything"
adding every field, Smart Collections and folders; no duplicate marks or
OCR jobs; then the dialog: its defaults and hints, a folder inside the
library refused, Copy writing files, originals, previews, fresh sidecars
and `library.sqlite` at the same paths with this library unchanged, an
existing folder name refused, Escape blocked and Stop removing the
incomplete library, Move with one file missing leaving that document out
and in this library while the other goes to the Waste bin, and "Open it"
switching to the new library, bundles with Dossiary (`test_export_bundle.py` -- bundle names; the
download from jsDelivr at the running version (faked with `page.route`,
`access-control-allow-origin: *`), another version's download ignored,
offline with nothing stored, a copy chosen in the dialog, the stored copy
used silently, an outdated stored copy asking and declining/accepting;
`How to open.txt` in English, and German followed by English; then the
dialog: Library only unchanged and never fetching; a folder bundle's layout,
downloaded `dossiary.html`, instructions, summary, Open it and Recent
libraries entry; an existing bundle folder or zip refused; offline → Choose
dossiary.html (a non-Dossiary file refused, the chosen one stored and used on
the next click, and later without asking); an outdated stored copy declined
writing nothing; zip only read back with Python's `zipfile` (entries,
contents, CRCs, the zipped database, no folder, no Open it, no Recent
libraries entry); Both with identical folder and zip contents; the email
note and a ZIP64 zip with Armenian/Chinese names via
`__DEBUG_setZipLimits`; Stop removing a partial zip; Move only after the
zip is written; German labels), the zip writer itself
(`test_zip_writer.py` -- CRC32's check value, entries/contents/CRCs/stored/
UTF-8 flag read back with Python's `zipfile`, ZIP64 records with lowered
limits, an empty zip), and the stub's writable streams appending like the
real API (`test_stub_writable.py`)), autofill from earlier documents
(`test_autofill.py` -- a known title, typed with odd spacing and case,
replacing capture's untouched default type from the most recent match and
filling Category/Subcategory/Payment method/Currency as guesses naming the
source; a typed category left alone; a Waste-bin document never used; a
review-queue document's Edit form filling and saving the kept guesses; no
autofill when editing a reviewed document), keyboard shortcuts
(`test_keyboard_shortcuts.py` -- J/K/arrows moving the selection and the
panel, clamped at the top; D clearing the review flag and selecting the
next document; E opening Edit; Ctrl+Shift+Enter saving and marking Done
from inside a field, Ctrl+Enter saving only; no effect while typing in the
search box or with the ? list open; D leaving a reviewed document alone;
Enter opening the file exactly once; the list translating -- note that a
Playwright `evaluate()` string ending in an arrow function gets *called*,
so wrap setup code in `() => { ... }`), suggested values from OCR text
(`test_ocr_suggestions.py` -- the parser case by case through
`window.__DEBUG_suggestFromOcrText` (German and English totals, the total
on the line after its label, both thousands styles, month names,
impossible dates skipped, no amount without a total line, an ambiguous
slash date following the UI language); a review-queue document's Edit
form suggesting date/amount/currency as guesses with notes, an edited
guess losing its mark, guesses returning after a type change without
touching a typed date, kept guesses saved; no guesses for a reviewed
document or over an existing date; and capture's OCR replacing the
"today" preset -- the stub's OCR text is overridable via
`window.__STUB_OCR_TEXT`), the Storage stats modal
(`test_storage_stats.py` -- the real-folder walk correctly sums
`files/`/`thumbnails/`/`inbox/`/`library.sqlite` against an
independently-computed expectation, not just the app's own arithmetic; a
document whose searchable PDF was built has genuinely different-sized
active and original files, both correctly attributed; a deliberately
untracked file lands in the Untracked bucket and nowhere else; a document
moved to the Waste bin still has its files counted; the modal shows a
busy state before resolving to final numbers; each folder's split renders
as sub-rows directly under that folder's own row, with thumbnails/'s
Untracked row correctly absent when zero; and `formatBytes()`'s unit
boundaries, including the just-below-a-boundary rounding edge), "Make
searchable" (`test_make_searchable.py` -- offered only for a not-yet-built
PDF/JPEG/PNG and only in the panel, not the context menu; an image with a
preserved original gets a new `.pdf` active file, OCR text/language
stored, the hash-identical PNG copy removed and the sidecar refreshed; a
legacy PDF with no original keeps its file as the new original, gets a
`_searchable.pdf` next to it and keeps hand-corrected OCR text; a PDF with
real text is reported and left untouched; a copy that doesn't match the
original's hash stays on disk; a missing original is never overwritten in
place; and the dialog can't be closed mid-run via Escape, backdrop,
