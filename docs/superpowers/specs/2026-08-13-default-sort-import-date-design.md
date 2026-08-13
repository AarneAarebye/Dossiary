# Default sort: persisted, defaulting to Import date (newest first)

## Context

The document table's sort is currently module-level session state
(`let sortKey = 'date'; let sortDir = 'desc';`) — always starting at
`date` descending on every page load, never saved anywhere, and reset
implicitly (never restored) on every library switch since nothing writes
it back except the in-memory variables themselves. `date` is the
document's own **content** date (an invoice or letter date), not when it
was added to the library, and it's deliberately left blank for
Inbox-imported documents until reviewed (see `sortDocs()`'s own null
handling, `av = a.date || ''`) — so under the current default, newly
imported but not-yet-reviewed documents sort to the very bottom of the
list rather than being visible near the top.

This changes the default to `import_date` (always set, sorts correctly as
an ISO string with no null-handling needed) and makes the choice a real,
per-library persisted preference — so whatever a person last sorted by is
what they see on their next reopen, the same way `nav_style` already
works.

## What's changing

**Two new `settings` keys**, `sort_key` and `sort_dir`, mirroring
`nav_style`'s existing `key`/`value` pattern exactly (two flat keys, not
one packed JSON value, matching this app's established convention of
one setting per concern):

```js
function loadSortState(){
  const keyRows = queryAll("SELECT value FROM settings WHERE key = 'sort_key'").rows;
  const dirRows = queryAll("SELECT value FROM settings WHERE key = 'sort_dir'").rows;
  sortKey = keyRows.length ? keyRows[0][0] : 'import_date';
  sortDir = (dirRows.length && dirRows[0][0] === 'asc') ? 'asc' : 'desc';
}

async function saveSortState(key, dir){
  sortKey = key;
  sortDir = dir;
  db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('sort_key', ?)", [key]);
  db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('sort_dir', ?)", [dir]);
  await persistDb();
}
```

`loadSortState()` is called once per library open, from
`loadDocumentsFromDb()`, alongside the existing `loadNavStyle()` call — a
fresh library (no `sort_key`/`sort_dir` rows yet) and an existing library
that predates this feature both fall through to the same default
(`import_date`, `desc`), identical in spirit to how `default_document_type`
and `default_currency` behave when unset.

No `SCHEMA_MIGRATIONS` entry needed — `settings` is already a generic
key/value table (`CREATE TABLE IF NOT EXISTS`), and adding new keys to it
is purely additive, the same as every other settings-backed feature in
this app (`nav_style`, `collections_nav_expanded`, `default_document_type`,
`default_currency`).

**Column-header click handler** (`el('doc-thead-row')`'s delegated click
listener) changes from:

```js
if(sortKey === key){ sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }
else{ sortKey = key; sortDir = key === 'date' ? 'desc' : 'asc'; }
render();
```

to:

```js
let newKey = sortKey, newDir = sortDir;
if(sortKey === key){ newDir = sortDir === 'asc' ? 'desc' : 'asc'; }
else{ newKey = key; newDir = (key === 'date' || key === 'import_date') ? 'desc' : 'asc'; }
saveSortState(newKey, newDir);
render();
```

Two behavior changes bundled here, both approved: (1) clicking "Imported"
for the first time now defaults to descending (newest-import-first),
matching "Date"'s existing special case, rather than the generic
ascending-by-default every other column uses; (2) every sort change —
clicking any column header, in any direction — now persists via
`saveSortState()`, not just updates in-memory state.

**No special handling on library switch.** `navStyle` isn't reset inside
`resetAll()` either; the next library open's own `loadDocumentsFromDb()` →
`loadSortState()` call naturally re-reads (or defaults for) that specific
library's own saved preference. Whatever sort was active for the
previously-open library simply gets overwritten by the newly-opened
library's own state, the same way `navStyle` already behaves.

## Non-goals

- No new UI for choosing the default sort outside the existing
  click-a-column-header mechanism — there's no separate "default sort"
  dropdown or settings-modal control being added.
- No change to `sortDocs()`'s comparison logic itself (`date`'s
  null-handling, `amount`'s numeric parsing, `field-*`'s dynamic-field
  handling, or the generic string-compare fallback `import_date` already
  uses correctly) — only which key/direction is active by default and
  whether that choice persists.
- No change to which columns are sortable — `import_date`'s `<th
  data-key="import_date">` already exists and is already fully wired
  through the same delegated click listener; this doesn't add a new
  sortable column, it changes what happens when the app opens and what
  happens after any click.

## Testing

Needs coverage for: a fresh library opening with `import_date`/`desc` as
the active sort (the "Imported" column header carries the `.active`
class, and rows appear newest-imported-first); clicking "Date" still
works and persists that new choice (reopening the library keeps the
`date`-sorted state, not reverting to `import_date`); clicking "Imported"
for the first time (when some other column is currently active) lands on
descending, not ascending; an old-shape library seeded with no
`sort_key`/`sort_dir` rows at all reads back using the new default rather
than erroring or defaulting to something else — the same "pre-existing
document/setting reads back correctly" pattern already used for
`archived`/`deleted`/`needs_review` and for `nav_style`'s own tests.
