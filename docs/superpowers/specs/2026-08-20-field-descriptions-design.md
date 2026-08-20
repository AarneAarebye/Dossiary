# Field descriptions

## Context

Dossiary's custom fields (`fields` table) and built-in fields alike are
identified by name alone, with no room to explain what a field means.
This came up concretely with "Organization" and "Organization To" —
migrated straight through from Mariner Paperless's own `ZCUSTOMITEM.ZNAME`
values (`migrate_to_new_library.py` in the sibling `LibraryLifeboat` repo
copies custom field names generically, never inventing or hardcoding
these two specifically) — which despite the name can hold either an
organization's name or a person's, since they're plain free-text fields
recording whoever sent or will receive the document. Renaming them
doesn't resolve the ambiguity for whoever is filling out the form; a
short explanatory hint does, and generalizes to any field that could use
one (Category vs. Subcategory, a custom "Reimbursable" checkbox, etc.).

Dossiary has no field-rename capability at all today (Field Settings
manages attachment-to-type and the show_as_column/autocomplete
capability flags, never a field's own name), so this is additive, not a
migration of existing data.

## Approach

### Data model

One new table, added to the `SCHEMA` string (dossiary.html:1923-1962) —
`CREATE TABLE IF NOT EXISTS field_descriptions ( field_name TEXT PRIMARY
KEY, description TEXT );`. No `SCHEMA_MIGRATIONS` entry is needed:
`CREATE TABLE IF NOT EXISTS` already handles both a brand new library and
an existing one missing the table, the same way `collections`/
`collection_documents` were added.

`field_name` is a flat string key, not a foreign key to `fields.id` —
deliberately, so the same mechanism covers both custom fields (`fields`
rows, keyed by `fields.name`) and the five built-in fields that have a
real form input but no `fields` row at all: Category, Subcategory,
Document Type, Date, Tags (confirmed via the actual form markup —
`#f-category`/`#f-subcategory`/`#f-type`/`#f-date`/`#f-tags` at
dossiary.html:5266-5320, and their `#e-*` edit-form counterparts at
dossiary.html:4686-4732). Migrating those five into the generic `fields`
system just to give them a description column would be a far larger,
unrelated architectural change — they stay dedicated `documents` columns
with their own hardcoded rendering, exactly as today. Import Date is
deliberately excluded from the whole feature — it's never an editable
form field (see CLAUDE.md's own note on why it needs no field or guess at
all), so a hint under its label has nowhere to attach.

Loaded once per library open into an in-memory map,
`fieldDescriptions = {}` (`field_name -> description`), via a new
`loadFieldDescriptions()` function called from `loadDocumentsFromDb()`
alongside the existing `loadFieldDefs()`/`loadNavStyle()` calls. Saved via
a new `saveFieldDescription(fieldName, description)` function doing a
plain `INSERT OR REPLACE INTO field_descriptions (field_name,
description) VALUES (?, ?)`, the same upsert pattern every other
key-value write in this app already uses. An empty string is a valid
stored value (no special delete-the-row handling) — display logic simply
skips rendering a hint when the description is falsy.

Like field names themselves, description text is free-form,
user-authored content and must never be run through `t()` — only the
static chrome around it (the new section's heading, etc.) needs
translation.

### Field Settings UI

A new section in the Field Settings modal (`openFieldSettingsModal()`,
dossiary.html:4981-5032), placed after the existing `.fs-columns`
three-column area (Doc Types / Fields / Display Fields) and before the
modal's Done button — not folded into any of those three, since a
description belongs to the field itself, independent of which document
type happens to be selected (the same reasoning that already keeps the
Column/Autocomplete capability checkboxes, `capabilitiesHtml()`, reachable
regardless of `fsSelectedType`). A new `renderFieldDescriptionsList()`
function, called once from `openFieldSettingsModal()` (unlike
`renderFieldSettingsFieldColumns()`, it doesn't need to re-run when the
selected type changes, since it isn't type-scoped).

The section is a flat list, one row per field, in a fixed order: the five
built-ins first (Category, Subcategory, Document Type, Date, Tags, in
that order), then every `fieldDefs` entry in its existing order — each
row showing the field's name (read-only label) and a text input
pre-filled with its current description (blank if unset). Saved on blur,
mirroring the existing rename-on-blur pattern already used for
Collections (`commitRename()`/`.manage-collection-rename-input`,
dossiary.html:5744-5771) — type, click away, it's saved, no separate Save
button needed for this list.

### Showing it in the forms

A small, always-on hint line under the field's label — reusing the
already-existing `.field-hint` CSS class (dossiary.html:376: dim,
italic, `font-size:10.5px`), not `.field-guess-hint` (amber-colored,
reserved for dismissible guesses like the Date/Currency defaults — a
description isn't a guess, so it shouldn't look like one). `.field-hint`
is already used exactly this way for Document Type's own static
explanatory line (`captureDocTypeHint`, dossiary.html:5268; see
`.field-hint{ font-style:italic; ... }`) — this feature generalizes that
existing pattern rather than inventing a new one.

Both the capture and edit forms are rebuilt from a template string on
every open (confirmed: `f-type`/`f-date`/etc.'s values are already
interpolated from live JS state on each render, not static markup), so
each of the five built-ins' `<div class="field">...</div>` blocks gains
one conditional line:
`${fieldDescriptions['Category'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Category'])}</div>` : ''}`
(and equivalently for Subcategory/Document Type/Date/Tags, in both the
`f-*` capture template and the `e-*` edit template) — rendering nothing
at all when no description is set, same as every other optional hint in
this app.

For generic fields, `renderGenericFieldHtml()` (dossiary.html:3299-3341)
and `renderPersonFieldHtml()` (dossiary.html:3257-3270) each gain the
same conditional `.field-hint` line, keyed by `field.name`, covering both
branches of `renderGenericFieldHtml()` (the checkbox branch and the
text/number/date branch) so every field type gets identical treatment.
Since these two functions already receive everything else needed to
render a field, no new parameter is required — they read directly from
the module-level `fieldDescriptions` map, the same way `renderGenericFieldHtml()`
already reads module-level `defaultCurrency`.

## Out of scope

- No rename capability for any field (built-in or custom) — this spec is
  purely additive; "Organization"/"Organization To" keep their existing
  names, clarified by a description instead.
- No change to `migrate_to_new_library.py` in the sibling `LibraryLifeboat`
  repo. Field descriptions are a purely Dossiary-side, per-library
  concept (stored in `library.sqlite`, not in Mariner's own data model),
  and Mariner has no equivalent concept to migrate from — a freshly
  migrated library simply starts with no descriptions set, same as a
  brand new one.
- No description shown in the read-only detail view (`openDetail()`) —
  this is about helping someone *fill out* a field correctly, not about
  redisplaying already-saved data; out of scope unless a real need
  surfaces later.
- No character limit or validation on description text beyond what a
  plain `<input type="text">` already implies.

## Critical files

- `dossiary.html`:
  - `SCHEMA` (~line 1923) — new `field_descriptions` table.
  - New `loadFieldDescriptions()` function, called from
    `loadDocumentsFromDb()` alongside `loadFieldDefs()`.
  - New `saveFieldDescription(fieldName, description)` function.
  - `openFieldSettingsModal()` (~line 4981) — new section markup after
    `.fs-columns`, before the Done button.
  - New `renderFieldDescriptionsList()` function, called once from
    `openFieldSettingsModal()`.
  - `renderGenericFieldHtml()` (~line 3299) — conditional `.field-hint`
    line in both the checkbox and text/number/date branches.
  - `renderPersonFieldHtml()` (~line 3257) — conditional `.field-hint`
    line.
  - The capture form's template (containing `#f-category`/`#f-subcategory`/
    `#f-type`/`#f-date`/`#f-tags`, ~lines 5266-5320) and the edit form's
    template (`#e-category`/`#e-subcategory`/`#e-type`/`#e-date`/`#e-tags`,
    ~lines 4686-4732) — one conditional `.field-hint` line added per
    built-in field, in each template.
  - `STRINGS` — new keys for the Field Settings section's own chrome
    (heading, any placeholder text) across all six language blocks.

## Testing

A new Playwright test file, following this suite's established shape,
covering:
- The `field_descriptions` table is created for both a brand new library
  and an existing (pre-this-feature) seeded library.
- Field Settings' new section lists all five built-ins plus every seeded
  custom field, in the documented order; typing a description and
  blurring persists it (`INSERT OR REPLACE`, verified via the persisted
  JSON); reopening the modal shows the saved value.
- Setting a description for a built-in field (e.g. Category) shows the
  hint line under that field's label in both the capture and edit forms;
  leaving it unset shows no hint line at all.
- Setting a description for a generic field of each type (text, number,
  date, checkbox, person) shows the hint line correctly in both forms.
- Description text is never run through `t()` — a description containing
  characters that would look like an i18n key if mistranslated (e.g. a
  literal `{label}`) renders verbatim.
- `tests/test_i18n_coverage.py` passes unmodified once the new static
  keys are added to all six language blocks.
