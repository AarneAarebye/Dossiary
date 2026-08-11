# Collections / Smart Collections — design

Date: 2026-08-11
Status: approved, ready for implementation plan

## Context

This is sub-project 2 of two independent candidates identified during a
feature-gap analysis against Mariner Paperless (Dossiary's predecessor).
Sub-project 1 (Reports) shipped in v1.5.0. Collections is the natural
sequel: the top-level nav (All Documents/Inbox/Waste bin/Reports) already
gives fixed, built-in ways to slice a library; Collections adds
user-defined ones — both hand-curated lists ("2026 Home Renovation") and
saved live filters ("Travel receipts, this year").

## Goal

Two kinds of user-defined groupings, both reachable from an expandable
"Collections" section in the top-level nav, alongside the existing four
fixed views:

- **Manual Collections** — an explicit, hand-picked list of documents.
- **Smart Collections** — a saved snapshot of the toolbar's filters
  (search/category/type/person/dynamic fields) that re-evaluates live
  against the current library every time you open it.

## Non-goals

- **No nested folders.** Every collection sits directly in one flat list
  under the Collections nav section — no folders-of-collections, unlike
  Mariner's own model. Not clearly load-bearing even in the manual's own
  examples; can be added later without disrupting this design.
- **No dedicated criteria-builder UI.** A Smart Collection's criteria is
  exactly whatever the toolbar's filters are set to at the moment you save
  it — no separate screen with operators (contains/greater-than/date
  range) or AND/OR combination logic. If that turns out to matter later,
  it's a separate, additive feature.
- **No in-place Smart Collection criteria editing.** Changing what a Smart
  Collection matches means deleting it and creating a new one with the
  toolbar set differently — not an "edit criteria" flow that reloads a
  saved snapshot back into the toolbar for adjustment.
- **No cross-collection bulk actions** beyond "add selected to a
  collection" — no bulk delete/archive/tag from the new checkbox
  selection mechanism; that's out of scope for this project.
- **No collection reordering UI.** Collections list in a fixed order
  (creation order, or alphabetical — see the nav section below); no
  drag-to-reorder.

## Data model

Two new tables, following this app's existing junction-table conventions
(e.g. `document_field_people`):

```sql
CREATE TABLE IF NOT EXISTS collections (
  id INTEGER PRIMARY KEY, name TEXT, kind TEXT, -- 'manual' | 'smart'
  criteria TEXT -- JSON snapshot of toolbar filters; NULL for manual collections
);
CREATE TABLE IF NOT EXISTS collection_documents (
  collection_id INTEGER, document_id INTEGER, PRIMARY KEY (collection_id, document_id)
);
```

Added to the base `SCHEMA` (fresh libraries) and as two `SCHEMA_MIGRATIONS`
entries for existing ones, following this codebase's standard
additive-only migration pattern (`CREATE TABLE IF NOT EXISTS`, tried and
any "already exists" failure silently ignored).

`collection_documents` is used **only** for manual collections — a smart
collection's membership is never materialized as rows; it's computed live
every render from its `criteria` JSON, the same way the toolbar's live
filters are computed live from `currentFilters()` today.

`criteria` JSON shape (mirrors `currentFilters()`'s own return shape
exactly, so building and consuming it is symmetric):
```json
{ "q": "travel", "category": "Travel", "type": "", "person": "",
  "dynamic": [{ "label": "Reimbursable", "value": "1" }] }
```

## New module-level state

Two new variables, loaded once per library open (`loadDocumentsFromDb()`,
alongside where `fieldDefs`/`typeFieldOrder` already load) and reset in
`resetAll()` on library close, following the exact pattern those two
already establish:

```js
let collections = [];        // [{id, name, kind, criteria}, ...] from the `collections` table
let collectionDocIds = {};   // { <collectionId>: Set<documentId> }, built from collection_documents --
                              // manual collections only; a smart collection has no entry here at all
let nextCollectionId = 1;    // same pattern as nextDocId/nextTagId -- initialized from MAX(id)+1 on
                              // library open, incremented locally, explicit id passed into each INSERT
                              // (this app assigns ids in JS throughout, never via AUTOINCREMENT)
```

## Nav integration

A new, non-selectable **"📚 Collections"** header row in `#app-nav`,
placed after the existing `#nav-item-reports` and before
`#nav-style-toggle` — same position a 5th `.nav-item` would occupy, but
this row is a section toggle, not a view itself (clicking it never calls
`setView()`). It has its own expand/collapse chevron and toggles the
visibility of a dynamically-rendered list of `.nav-item`s directly below
it, one per row in `collections`, each `data-view="collection-<id>"`,
reusing the exact same `.nav-item` markup/CSS every other view already
uses (icon, label, no count badge — same reasoning as Reports having none:
a document count isn't the obviously-meaningful number for every
collection the way it is for Inbox/Waste bin). Collections list
alphabetically by name. Expand/collapse state is a `settings` row
(`collections_nav_expanded`, `'1'`/`'0'`), persisted the same way
`nav_style` already is, defaulting to expanded.

`matchesView()` (`dossiary.html:2231`) gains a branch, placed alongside
the existing `'reports'` branch:

```js
if(view.startsWith('collection-')){
  const id = Number(view.slice('collection-'.length));
  const collection = collections.find(c => c.id === id);
  if(!collection) return false;
  if(collection.kind === 'manual') return collectionDocIds[id] ? collectionDocIds[id].has(d.id) : false;
  return matchesCriteria(d, JSON.parse(collection.criteria));
}
```

Same as every other view, the toolbar's live filters (search/category/
type/person/dynamic) still apply on top once you're inside a collection —
`applyFilters()` needs no change beyond `matchesView()` already handling
the routing, since it already runs the shared filter logic after the
per-view membership check regardless of which view that check was for.

## Smart Collections — create via "save current filters"

A **"☆ Save as Smart Collection"** button in the toolbar, visible only in
the `'all'` view (the toolbar's filters aren't necessarily meaningful
snapshotted from Inbox/Waste bin/Reports/another collection — this button
follows the same visibility-by-view pattern `showArchivedWrap`/the Reports
date-range wrap already use). Clicking it calls `currentFilters()`
(`dossiary.html:2219`) to snapshot the toolbar's exact current state,
prompts for a name (reusing the plain `prompt()`-free small-modal pattern
this app already uses elsewhere for short text input — see how tags/
custom-field creation prompt for a name), and inserts a `collections` row
with `kind: 'smart'` and `criteria` set to the JSON-stringified snapshot.

**`matchesCriteria(d, criteria)`** is a new function, factored out of
`applyFilters()`'s existing category/type/person/dynamic-field/search body
(`dossiary.html:2273-2284`) so the exact same predicate logic drives both
the live toolbar filters and a saved Smart Collection's evaluation — no
duplicated filter logic anywhere:

```js
function matchesCriteria(d, criteria){
  const { q, category, type, person, dynamic } = criteria;
  if(category && d.category !== category) return false;
  if(type && d.document_type !== type) return false;
  if(person && !(d.people||[]).includes(person)) return false;
  for(const f of dynamic){
    if((d.customFields || {})[f.label] !== f.value) return false;
  }
  if(q){
    const personFieldNames = Object.values(d.personFieldValues || {}).map(names => (names || []).join(' '));
    const hay = [d.title, d.category, d.subcategory, d.document_type, d.notes, d.ocr_text, ...Object.values(d.customFields || {}), ...personFieldNames, (d.tags||[]).join(' ')].filter(Boolean).join(' ').toLowerCase();
    if(!hay.includes(q)) return false;
  }
  return true;
}
```

`applyFilters()`'s own body (`dossiary.html:2264-2284`) is refactored to
call `matchesCriteria(d, currentFilters())` for its post-view-check
filtering, rather than re-implementing the same five checks inline —
`currentFilters()`'s return shape already matches `matchesCriteria()`'s
expected `criteria` argument shape exactly (both were designed from the
same object shape, see Data model above), so this is a direct call, no
adapter needed.

## Manual Collections — multi-select + bulk add

The document table gains a new leftmost checkbox column (`<th>`/`<td>`,
following the existing `data-field` column-visibility conventions where
relevant, though this column is not one of the toggleable ones — it's
always present) plus a "select all visible" checkbox in the header row.
Selection is new session-only state, `let selectedDocIds = new Set();`,
reset by `resetAll()` (library close/switch) and by `setView()` (switching
views clears the selection, since "3 selected" from a different view's
document set would be confusing to carry over).

Once `selectedDocIds.size > 0`, a small bulk-action bar appears above the
table (e.g. `"3 selected · Add to collection ▾ · Clear selection"`),
built the same way the existing `.inbox-banner` conditionally appears —
shown/hidden via `style.display`, not always present in the DOM. "Add to
collection ▾" opens a small dropdown/menu listing every **manual**
collection (smart collections aren't a valid target — you can't manually
add a document to a live-computed filter) plus a "+ New collection…"
option; picking one inserts `collection_documents` rows for every
selected id not already present (`INSERT OR IGNORE`, matching this app's
existing dedup convention), then clears the selection.

The detail modal (`openDetail()`) also gains a one-document **"Add to
collection…"** action, listing the same manual-collection picker,
following the exact existing action-button pattern Archive/Flag for
review/Delete already use. When a document is opened *from inside* a
manual collection's view specifically (i.e. `currentView` is
`collection-<id>` and that collection is manual), the modal additionally
shows a **"Remove from this collection"** action, removing just that one
`collection_documents` row and refreshing.

## Manage Collections modal

A **"⚙ Manage collections"** toolbar button (placed alongside the existing
`⚙ Columns`/`⚙ Manage fields` buttons, `dossiary.html:401-404`) opens a
modal styled like the existing Field Settings modal: one row per
collection (name, kind badge, document count — for smart collections,
the live count from evaluating `matchesCriteria()` against `allDocs`; for
manual, `collection_documents` row count), an inline rename control, a
delete button per row, and a **"+ New collection"** button that creates
an empty **manual** collection (prompts for a name only) — smart
collections are exclusively created via the toolbar's "Save as Smart
Collection" flow described above, never from this modal, since a smart
collection with no criteria has no meaning. Deleting a collection removes
its `collections` row and (for manual ones) its `collection_documents`
rows; documents themselves are never touched, same "collections organize,
they don't own" principle Mariner's own model uses and this app's
existing tags/categories already follow.

## Visible consequences

- Two new tables, but no change to any existing table's schema — the
  usual additive-only migration story, no data migration needed for
  existing libraries (they simply start with zero collections).
- The document table's row height/layout gains one new column
  permanently (the checkbox), visible in every view, not just when
  something's selected — worth confirming this reads as "always there,
  quiet until used" rather than clutter, same tradeoff Mariner's own
  Report view's checkbox column makes.
- `renderNav()` grows a third dynamically-rendered nav section (after the
  4 fixed items and, previously, the Reports view's own controls) —
  worth checking the sidebar-style nav's vertical space doesn't get
  cramped with several collections plus the existing 4 fixed items,
  especially combined with `.table-wrap`'s empirically-calibrated
  max-height (see CLAUDE.md's own note on why that number needs
  re-verification whenever the nav's height changes).

## Testing

New `tests/test_collections.py`, following this suite's established
print-based-observation convention, covering at minimum: creating a
manual collection via the modal and confirming it appears in the nav;
multi-select checkboxes + bulk "add to collection" inserting the right
`collection_documents` rows; the detail modal's "Add to collection"/
"Remove from this collection" actions; creating a Smart Collection by
setting toolbar filters and clicking "Save as Smart Collection," then
confirming its saved criteria correctly re-filters `allDocs` when
reopened (including after a document that would now match is added, and
one that no longer matches is edited out — proving it's live, not a
snapshot of documents); renaming and deleting both kinds via the modal;
toolbar filters still composing on top of a collection's own scope,
matching every other view; selection state clearing on view switch and
library close; and the "Save as Smart Collection" button's visibility
being scoped to the `'all'` view only.

## Documentation

`CLAUDE.md` gains a new architecture note (following the density/style of
the existing "Top-level navigation" and "Reports" notes) describing:
`collections`/`collection_documents`' schema and why smart collections
store no membership rows; the `matchesCriteria()` extraction and its
symmetry with `currentFilters()`; the nav section's expand/collapse
persistence; the multi-select/bulk-add mechanism and why selection resets
on view switch; and the deliberate manual-vs-smart creation-flow split
(modal for manual, toolbar button for smart). `README.md`/`README.de.md`'s
feature list gains a short entry alongside the existing nav-related
entries.
