# Bulk archive, delete, and flag-for-review

## Context

The bulk-action bar (`#bulk-action-bar`, shown whenever any row checkbox is
checked) currently offers exactly one action: "Add to collection ▾" (plus
"Clear selection"). Archiving, deleting, and flagging/un-flagging a
document for review are all single-document-only actions today, reachable
solely from a document's own detail view (`openDetail()`'s action
buttons). This adds bulk equivalents of all three, following the same
selection mechanism the existing bulk-add-to-collection feature already
uses (`selectedDocIds`, a `Set` of document ids).

`renderBulkActionBar()` currently has no view-awareness at all — it's
purely a function of `selectedDocIds.size`, so "Add to collection" is
technically shown even when viewing the Waste bin (`currentView ===
'trash'`), even though a deleted document's own detail view already drops
that button entirely (`openDetail()` gates the whole action set, "Add to
collection" included, behind `if(!d.deleted)`, showing only Restore for a
deleted document). This is a small existing inconsistency; the work below
fixes it as a natural side effect of making the bar view-aware for the new
actions.

## What's changing

`renderBulkActionBar()` becomes view-aware, matching `openDetail()`'s
existing per-state action-set precedent exactly rather than inventing a
new pattern:

- **`currentView === 'trash'`**: only **Restore selected**. "Add to
  collection" is dropped here too (matching the single-document view).
- **`currentView === 'inbox'`**: Add to collection, **Archive selected**,
  **Delete selected**, **Done** (marks every selected document reviewed —
  labeled "Done" rather than "Flag for review", since everything visible
  in this view is already flagged).
- **Every other view** (`'all'`, `'reports'` — moot, no selection UI
  exists there — and `'collection-<id>'`): Add to collection, Archive
  selected, Delete selected, **Flag for review selected**.

**Bulk actions are unconditional sets, not per-document toggles.**
"Archive selected" always sets `archived = 1` for every selected document
regardless of each one's current value (same for "Flag for review
selected" → `needs_review = 1`, "Done" → `needs_review = 0`, "Restore
selected" → `deleted = 0`). This avoids ambiguous outcomes from a mixed
selection (e.g. a Collection view, which deliberately includes archived
and needs-review documents per its own design, could easily have a
selection where some documents are already archived and some aren't) —
"Archive selected" always means "make sure all of these are archived,"
never "flip whichever ones weren't."

**No confirmation dialog for any bulk action**, including delete —
consistent with every existing single-document toggle in this app (all of
which apply instantly with no modal), and with the same reasoning that
just justified removing the Inbox review modal: the Waste bin already
gives every write a fully reversible undo path, so a confirmation step
would be redundant friction rather than a real safety improvement.

### New functions

Three new functions, one per flag, each doing a single batched update
rather than reusing the existing single-document
`toggleArchived()`/`toggleDeleted()`/`toggleNeedsReview()` in a loop —
looping those would call `persistDb()` (which re-serializes and rewrites
the *entire* SQLite database) once per selected document, which is wasteful
for what bulk-select exists specifically to handle: potentially many
documents at once. Each new function does its `UPDATE` calls first, then
exactly one `persistDb()` and one `render()`:

```js
async function bulkSetArchived(ids, value){
  ids.forEach(id => db.run('UPDATE documents SET archived = ? WHERE id = ?', [value ? 1 : 0, id]));
  ids.forEach(id => { const d = allDocs.find(x => x.id === id); if(d) d.archived = value; });
  await persistDb();
  selectedDocIds = new Set();
  render();
}
```

(`bulkSetDeleted(ids, value)` and `bulkSetNeedsReview(ids, value)` follow
the identical shape, just targeting their own column.) Each `UPDATE` is
still a single parameterized `db.run('UPDATE ... WHERE id = ?', [...])`
call per id — matching this codebase's established convention (confirmed
against `toggleArchived()`'s own single-document `UPDATE`, and against
`tests/stub_studio2.js`'s fake SQL engine, which only understands a single
`WHERE col = ?` equality, not `WHERE id IN (...)`) — the batching win is in
deferring `persistDb()`/`render()` to once at the end, not in the SQL
shape itself.

Clearing `selectedDocIds` and re-rendering after every bulk action matches
the existing bulk-add-to-collection behavior exactly (selection doesn't
survive past a bulk action today, and this doesn't change that).

## UI

Four new buttons added to `#bulk-action-bar`'s markup (alongside the
existing "Add to collection ▾" and "Clear selection"), each `hidden`/shown
based on `currentView` inside `renderBulkActionBar()`:

- `#bulk-archive-btn` — "Archive selected"
- `#bulk-delete-btn` — "Delete selected"
- `#bulk-review-btn` — label text swaps between "Flag for review selected"
  and "Done" depending on `currentView === 'inbox'`
- `#bulk-restore-btn` — "Restore selected" (Waste bin only)

Each button's click handler calls its matching bulk function with
`[...selectedDocIds]` and the fixed target value described above.

## Non-goals

- No bulk "Remove from collection" — the user's request was specifically
  archive/delete/flag-for-review; a bulk remove-from-collection action
  wasn't asked for and isn't included here, though it would follow the
  same pattern if wanted later.
- No confirmation dialog for any bulk action, including delete (see
  above).
- No change to the existing single-document toggle functions
  (`toggleArchived()`, `toggleDeleted()`, `toggleNeedsReview()`) — they
  keep their current per-document-toggle behavior for the detail view's
  own buttons, untouched.
- No schema change, no new dependency.

## Testing

`tests/test_collections.py` gets new scenarios appended (it already has
the bulk-select/bulk-action-bar seed and setup this needs — reusing that
is simpler than duplicating it in a new file). Coverage needed: each
button's visibility per view (present/absent
matching the table above), bulk archive/delete/flag/restore actually
updating every selected document's flag correctly, the "unconditional
set" behavior on a genuinely mixed-state selection (at least one already
in the target state, at least one not, confirming the result is uniform
afterward), selection clearing after a bulk action, and that
`persistDb()`/`render()` are each triggered once per bulk action, not once
per document (verifiable by seeding a handful of documents and confirming
the outcome is correct — an explicit call-count assertion isn't necessary
given this suite doesn't spy on internal calls elsewhere, correctness of
the end state is the existing convention).
