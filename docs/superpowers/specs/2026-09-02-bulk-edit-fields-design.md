# Bulk edit fields for selected documents

## Context

Multi-select (`selectedDocIds`, the row checkboxes) currently only feeds
the bulk-action bar's unconditional-set actions — Archive, Delete, Flag
for review, Add to collection (see
`docs/superpowers/specs/2026-08-12-bulk-archive-delete-review-design.md`)
— and the single-row right-click context menu
(`docs/superpowers/specs/2026-08-22-row-context-menu-design.md`) only ever
acts on one document. There is no way today to set the same Category,
Document Type, custom field value, etc. across several documents at once
— someone with, say, 12 Inbox-imported utility bills has to open each one
individually and retype the same Category/Type.

This adds a bulk-edit form reachable two ways, that lets you set values
for one or many fields and apply them to every currently-selected
document in one save.

## Approach

### Entry points

Both open the same `openBulkEditForm(ids)`, passed `[...selectedDocIds]`:

- A new, minimal right-click context menu on **checked** rows: right-
  clicking a row that's part of the current 2+-document selection shows a
  menu with exactly one item, **"Edit"** — it deliberately doesn't
  duplicate Archive/Delete/Flag for review, which already live in the
  bulk-action bar. Right-clicking a row that *isn't* checked keeps
  today's existing single-document context menu unchanged, even while
  other rows are checked elsewhere — the two menus are mutually
  exclusive per row, decided by that row's own checked state, not by
  whether a selection exists at all.
- A new **"Edit"** button in `#bulk-action-bar`, alongside the existing
  Archive/Delete/Flag-for-review/Add-to-collection buttons, following
  that feature's own per-view visibility rules (hidden in Waste bin,
  same as Archive/Add-to-collection already are there).

### Field list: union across selected documents, computed once

Bulk edit aims for parity with the single-document Edit form's fields —
Document Type, Category, Subcategory, Date, Notes, Tags, every
person-type field (People, Author, Collaborator, …), and every generic
custom field — with two deliberate exclusions (see "Excluded fields"
below).

Selected documents can span different Document Types, each with its own
`document_type_fields` configuration. `openBulkEditForm()` computes the
field list once, when the form opens, as a **union**: every field
configured for *any* selected document's type, plus any field *any*
selected document currently holds a value for (covering a field that was
later removed from its type's configuration, or a document reclassified
away from a type that used it). The list is **not** recomputed if the
form's own Document Type input is changed mid-edit — recomputing live
would need to reconcile against the original per-document union in a way
that adds real complexity for a rare case (changing Document Type as part
of the same bulk edit that's also setting other fields); simpler to fix
the field list for the life of the form.

A field present in *every* selected document's type renders normally.
Reusing existing convention, one that's present for only *some* — either
configured for a subset of the selected types, or held as data outside any
configured type — renders with the same `.field-orphaned` class/hint the
single-document Edit form already uses for a field no longer configured
for a document's current type. Here it signals "this field doesn't belong
to every selected document's type, but applying it here still writes it
for all of them" rather than "this document has stale data" — same visual
treatment, adjacent but distinct meaning, worth calling out explicitly in
the implementation so the hint text used here doesn't just clone the
edit-form's wording.

Every field starts genuinely blank/unset — bulk edit never pre-fills a
field from any one selected document's current value (there's no single
correct document to pull it from, and pre-filling from an arbitrary one
would look like a shown, editable "current value" it isn't). This also
means the Date-defaults-to-today and Currency-defaults-to-`default_currency`
dismissible-guess treatments the capture/edit forms use are **not** applied
here — a bulk-set value should always be a deliberate choice, not
something to notice-and-clear across many documents at once.

### The "Apply" toggle: how a field opts in

Every **replace-semantics** field (see below) gets its own "Apply to all"
checkbox, unchecked by default, immediately to the left of the field's
own input. Only checked fields get written to any document; unchecked
fields are left completely untouched everywhere. This is required rather
than optional polish: "blank" already carries different meaning per field
type in this app (an unchecked checkbox field is real, meaningful data —
see `readDynamicFieldValues()`'s existing "unchecked box is not empty"
rule — not an "unset" signal the way a blank text field can be), so there
is no value-based way to distinguish "leave this alone" from "clear this
to blank" that works uniformly across text/number/date/checkbox/reminder
fields. The explicit toggle is the one mechanism that works the same way
for all of them. A checkbox-type field therefore shows *two* checkboxes
side by side — "Apply to all" and the field's own Yes/No value — which is
slightly busier than other field rows but unambiguous.

Saving with every "Apply" box unchecked and no Tags/People typed is a
no-op — safe default, nothing changes, matching this app's general
"nothing happens without an explicit action" principle.

### Replace vs. additive fields

**Replace semantics** (Apply checkbox + input, as above): Document Type,
Category, Subcategory, Date, Notes, and every generic custom field
(text/number/date/checkbox/reminder — this covers Amount, Currency, and
Payment method too, which are ordinary generic fields now per the
sentinel-fields migration; nothing field-type-specific needed for them
here). Checking the box and leaving the value blank is a valid, explicit
"clear this field on every selected document" — not disallowed, since
that's a real and sometimes-wanted outcome (e.g. bulk-clearing a
mistakenly-set field).

**Additive semantics, no Apply checkbox needed**: Tags, and every
person-type field. Typed names/tags are added to each selected document's
existing list via the same find-or-create pattern capture/edit already
use; nothing already on a document is ever removed by a bulk edit. A
blank Tags/People input is unambiguously "nothing to add" — no toggle
needed, unlike the replace-semantics fields above. This extends the
additive behavior requested for Tags to every person-type field (People,
Author, Collaborator, …), since they're the same comma-separated
multi-valued shape and "replace every selected document's People list
with the exact same names" would almost never be the intended outcome of
a bulk edit.

### Mixed-value indicator

For every field in the union, `openBulkEditForm()` also compares the
selected documents' *current* values for that field (already available —
`allDocs` already holds each selected document's full data, no extra
query needed). A field is **mixed** when the selected documents don't all
agree: for a scalar replace field, any two selected documents having a
different value (blank/unset counts as one shared value for this
comparison, so "all blank" or "all exactly `'Finance'`" is *not* mixed,
but "some `'Finance'`, some blank" *is*); for an additive field, the
selected documents' tag/person-name sets aren't all identical as sets
(order doesn't matter). A field where every selected document already
agrees gets no indicator at all — nothing to warn about.

A mixed field shows a small hint line under it, worded differently by
semantics, since the two behave differently on save:

- **Additive fields** (Tags, person-type fields): *"Documents in this
  selection currently have different {field} — what you enter here is
  added on top of each document's own existing values; nothing is
  removed."* Purely informational — there's no overwrite risk to warn
  about, just a clarification of the (non-obvious, replace-by-default-
  everywhere-else-in-this-app) additive behavior.
- **Replace-semantics fields** (Document Type, Category, Subcategory,
  Date, Notes, every generic field): *"Documents in this selection
  currently have different {field} values — checking Apply will
  overwrite ALL of them with the value you enter."* A real warning: this
  is the one place a bulk edit can silently discard divergent existing
  data, so it's called out before, not after, checking Apply.

This is independent of, and can co-occur with, the `.field-orphaned`
styling above — a field can be both "not configured for every selected
document's type" and "mixed" (or orphaned-but-uniform, or
configured-everywhere-but-mixed); the two indicators answer different
questions (does this field apply everywhere vs. do the selected
documents already agree on it) and both can be true or false
independently.

### Excluded fields

**Title** and the **OCR-text box** are not part of the bulk-edit form,
deliberately narrower than literal field-for-field parity with the
single-document Edit form:
- Title is meant to be unique per document; setting every selected
  document's title to the identical string has no sensible use case and
  would actively harm the table's own scannability.
- OCR text is per-file extracted content tied to that document's own
  file, not really "metadata" in the sense the rest of this form edits —
  bulk-overwriting it with the same text across documents with different
  underlying files doesn't correspond to anything real.

### Save

On Save, for each checked replace-semantics field and each non-blank
additive field, the same per-document write primitives
`saveEditedDocument()`/`bulkSetArchived()` already use are applied across
every selected id — `UPDATE documents SET <col> = ?` for the scalar
columns (Document Type/Category/Subcategory/Date/Notes), delete-then-
insert into `document_field_values` for generic fields, find-or-create
plus additive link insert (skipping a link that already exists) for
Tags/person-type fields — batched into exactly one `persistDb()` and one
`render()` call at the end, following the exact reasoning
`bulkSetArchived()`'s own spec already documents: looping individual
single-document save functions would re-serialize the whole SQLite
database once per selected document, which bulk actions exist specifically
to avoid.

`archived`, `deleted`, and `needs_review` are never touched by a bulk
edit — those already have their own dedicated bulk actions, and this
feature's scope is field values only, mirroring how the single-document
Edit form's own "Save changes" (not "Save & Done") never touches
`needs_review` either.

Selection (`selectedDocIds`) is **not** cleared after a bulk edit save —
unlike `bulkSetArchived()`/`bulkSetDeleted()`/`bulkSetNeedsReview()`,
which clear it because their whole point is moving documents out of the
current view. Editing field values doesn't remove a document from view,
so keeping the selection lets someone chain a further bulk action (e.g.
bulk-edit Category, then bulk-flag the same selection for review)
without re-checking every row.

No confirmation dialog before applying — consistent with every other
bulk action and every single-document save in this app, none of which use
a `confirm()`-style interruption; the per-field Apply checkboxes are
already the explicit, deliberate opt-in this form needs.

## UI

A new modal (`#modal-root`, same shell as `openEditForm()`), titled
something like "Edit N documents" (count from `ids.length`). No
file/thumbnail/OCR section — bulk edit is metadata-only, same as the
single-document Edit form already is. Field order mirrors the
single-document form's own layout: Document Type (prominent, first) →
Category → Subcategory → Date → Tags → People (and other person-type
fields) → Notes → the computed union of remaining generic custom fields
(configured fields first, in the order their originating types list
them, followed by any data-only orphaned additions) → Save changes /
Cancel.

No layout/CSS-calibration impact — this is a transient modal like
`openEditForm()`, not new persistent chrome, so none of the
`.table-wrap`/detail-panel sticky-header `max-height` constants documented
elsewhere in this codebase need to change.

## Non-goals

- No bulk edit of `archived`/`deleted`/`needs_review` — already covered
  by the existing bulk-action bar.
- No live re-computation of the field union if Document Type is changed
  inside the bulk-edit form itself (see above).
- No confirmation dialog.
- No keyboard-triggered variant of the new context menu (matches the
  existing single-row context menu's own scope).
- No change to the single-document Edit form, `saveEditedDocument()`, or
  any existing bulk-action function — this is new, additive
  functionality alongside them.

## Critical files

- `dossiary.html`:
  - New `openBulkEditForm(ids)` — builds and renders the modal, including
    the field-union computation described above.
  - New `saveBulkEdit(ids)` — reads every field's Apply-checkbox/input
    state and writes as described above.
  - New context-menu builder for the checked-rows case, following the
    existing floating-menu pattern (`openDocCollectionMenu`, the Columns
    menu, the single-row context menu) — reuses that same visual language
    rather than inventing a new one.
  - `renderBulkActionBar()` — new "Edit" button alongside the existing
    Archive/Delete/Flag-for-review/Add-to-collection buttons, with the
    same view-based visibility handling those already have.
  - The existing row `contextmenu` listener (wired in `render()`'s
    row-wiring pass) — needs a branch on whether the right-clicked row is
    in `selectedDocIds` and `selectedDocIds.size >= 2`, dispatching to the
    new bulk menu instead of the existing single-document one.
  - New i18n keys across all six `STRINGS` blocks: the bulk context-menu
    "Edit" label (may be able to reuse an existing generic key — confirm
    during planning), the bulk-action-bar button label, the modal title
    (`{count}`-parameterized, singular/plural pair), each "Apply to all"
    checkbox's label/aria-label, the two mixed-value hint variants
    (`{field}`-parameterized, one for additive fields and one for
    replace-semantics fields), and a post-save status message
    (`{count}`-parameterized, singular/plural pair) — `zh-Hant` derived
    from the finished `zh-Hans` wording via OpenCC, matching this repo's
    established convention.

## Testing

A new Playwright test file (`tests/test_bulk_edit.py`, following this
repo's one-file-per-feature convention for comparably-sized additions —
see `tests/CLAUDE.md`), covering at minimum:
- Right-clicking a checked row (2+ selected) shows the bulk "Edit" item
  only, not the single-document menu; right-clicking an unchecked row
  shows the single-document menu unchanged, even with others checked.
- The bulk-action bar's new "Edit" button opens the same form, respecting
  the same per-view visibility rules as the other bulk buttons.
- The field union: seed documents of two different types with
  non-overlapping configured fields, select one of each, confirm the
  form shows both types' configured fields (each with `.field-orphaned`
  styling since neither is common to both) plus every scalar field.
- A replace-semantics field with its Apply box left unchecked is
  untouched on every selected document after save, regardless of what's
  typed into its input.
- A replace-semantics field with Apply checked and a blank value clears
  it on every selected document.
- A checkbox-type field's "Apply to all" and its own value checkbox are
  independent — Apply unchecked leaves existing values alone regardless
  of the value checkbox's own state.
- Tags and a person-type field: typed values are added to each selected
  document's existing list without removing what was already there;
  leaving the input blank changes nothing.
- Mixed-value indicator: a replace-semantics field seeded with differing
  values across the selection shows the overwrite-warning hint; the same
  field seeded with identical values (or all blank) across the selection
  shows no hint at all. An additive field seeded with differing tag/
  person sets shows the "added on top" hint; identical sets show no hint.
- Saving with nothing checked and nothing typed is a genuine no-op (no
  `persistDb()`-visible change).
- Selection survives a bulk-edit save (still checked afterward), unlike
  the existing bulk archive/delete/flag actions.
- `persistDb()`/`render()` are each triggered once per bulk-edit save, not
  once per selected document (verify via end-state correctness across a
  handful of seeded documents, matching this suite's existing convention
  rather than spying on call counts).
