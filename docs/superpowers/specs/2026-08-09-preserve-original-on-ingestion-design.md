# Preserve original file on ingestion — design

Date: 2026-08-09
Status: approved, ready for implementation plan

## Context

This is sub-project 1 of a two-part change. It was scoped out mid-design
of sub-project 2 ("build a searchable PDF after the fact for an existing
document"), when a `/btw` side-question asked whether every document
should get a preserved original from the moment it's added, rather than
only documents that happen to go through capture-time searchable-PDF
processing. Verified against the current code: today, `original_file_path`
is populated *only* when `saveNewDocument()`'s `canBuildSearchablePdf`
branch runs (a JPEG/PNG captured with OCR run before Save) — Inbox adds
and plain PDF/un-OCR'd-image captures never get a second "original"
location at all, only `file_path`.

Doing this first makes sub-project 2 simpler for any document added after
it ships (the original is already safely separate, so retroactively
building a searchable PDF just needs to overwrite `file_path`, not move
anything). It does **not** simplify sub-project 2 for documents already in
a library today — those still need sub-project 2's own safe move-then-
replace handling, since this change only affects documents added after it
ships.

## Goal

Every document added via the capture form (`saveNewDocument()`) or the
Inbox (`addInboxFile()`) — regardless of file type, regardless of whether
OCR ever runs — gets its raw, untouched bytes preserved at
`original_file_path` from the moment it's added, before any manipulation.
`file_path` keeps its current meaning exactly: "whatever's currently
active" — the searchable PDF when one was built, otherwise a plain copy of
the same content.

## Non-goals

- **LibraryLifeboat-migrated documents are explicitly out of scope.**
  `migrate_to_new_library.py` already produces its own original/processed
  layout, copied from Mariner's own historical data — unrelated to this
  change, and not to be touched.
- Sub-project 2 (the retroactive "Build searchable PDF" action) is a
  separate spec, brainstormed and written up afterward.
- No change to `file_path`'s own meaning or naming conventions — only to
  whether a sibling original also gets written.
- No thumbnail regeneration logic changes.
- No attempt to detect whether a migrated PDF already secretly contains a
  real text layer from its Mariner origin — out of scope, see the schema
  section below.

## Schema change

New column on `documents`:

```sql
searchable_pdf_built INTEGER DEFAULT 0
```

Added to the base `SCHEMA` (fresh libraries) and as a `SCHEMA_MIGRATIONS`
entry (`ALTER TABLE documents ADD COLUMN searchable_pdf_built INTEGER DEFAULT 0`)
for existing ones, following this codebase's standard additive-only
migration pattern.

**Why this column is needed now, when it wasn't before:** today,
`original_file_path IS NOT NULL` implicitly means "this document went
through searchable-PDF processing," because that was the *only* code path
that ever set it. Once `original_file_path` is set unconditionally for
every new document, that implication breaks — a document can have a
perfectly good `original_file_path` and still have `file_path` pointing at
an unprocessed plain copy. `searchable_pdf_built` is the new, explicit
signal for "has Dossiary's own OCR+jsPDF pipeline actually built the file
currently at `file_path`."

## One-time backfill migration

Mirrors `migrateTextFieldsAutocompleteDefault()`'s pattern exactly: tracked
via an explicit `settings` row (e.g. `searchable_pdf_built_backfill_migrated`)
so it runs exactly once, ever — **not** on every library open, unlike some
of this app's other backfills. This is load-bearing: after this change
ships, `original_file_path IS NOT NULL` will be true for ordinary,
never-processed new documents too, so re-running a naive version of this
query on every open would incorrectly flip `searchable_pdf_built` to `1`
for documents that were never actually processed.

The one-time backfill itself:

```sql
UPDATE documents SET searchable_pdf_built = 1
WHERE original_file_path IS NOT NULL AND source = 'captured'
```

`source = 'captured'` is the same predicate that already, uniquely,
identifies "went through `saveNewDocument()`'s searchable-PDF branch" in
the current codebase — no `scan-inbox` document could have
`original_file_path` set under the old code (`addInboxFile()` always wrote
`NULL`), and `migrated` documents are deliberately excluded per the
Non-goals section above (their `original_file_path` predates and is
unrelated to this app's own OCR pipeline).

## Ingestion changes

**Shared helper** (new, small, reused by both ingestion paths — the one
piece of logic that's genuinely identical between them; `saveNewDocument()`
and `addInboxFile()` otherwise stay separate, matching this codebase's
existing documented choice not to unify them, since they have different
inputs and different defaults for nearly every column):

```js
// Writes `file`'s raw bytes into files/<id>_<baseName>/<originalName>,
// returning the relative path to store as original_file_path. Called
// before any processing, from both saveNewDocument() and addInboxFile(),
// so every new document's untouched original is preserved from the moment
// it's added, regardless of file type or whether it's ever OCR'd.
async function writeOriginalToSubfolder(id, baseName, file){
  const subfolderName = `${id}_${baseName}`;
  const subfolderHandle = await filesDirHandle.getDirectoryHandle(subfolderName, { create: true });
  const originalName = safeFilename(file.name, 'original');
  const originalHandle = await subfolderHandle.getFileHandle(originalName, { create: true });
  const writable = await originalHandle.createWritable();
  await writable.write(await file.arrayBuffer());
  await writable.close();
  return `files/${subfolderName}/${originalName}`;
}
```

**`saveNewDocument()`:** both branches (the existing `canBuildSearchablePdf`
branch and its `else`) call `writeOriginalToSubfolder(id, baseName, pendingFile)`
and set `originalFilePathForDb` from its result, unconditionally — replacing
the current `else` branch's `originalFilePathForDb = null`. The searchable-PDF
branch's own existing subfolder-writing code (today duplicated inline) is
replaced by a call to the same shared helper, so there's exactly one
implementation of "write an original into its subfolder." `searchable_pdf_built`
is set to `1` when the searchable-PDF branch runs, `0` otherwise.

**`addInboxFile()`:** gains the same call — `baseName` derived the same way
`saveNewDocument()`'s non-searchable branch already derives it (from the
file's own name via `safeFilename()`, since Inbox adds have no title field
at add time). `original_file_path` is set from the helper's result instead
of the current hardcoded `null`. `searchable_pdf_built` stays `0` — Inbox
never runs OCR automatically, so a freshly-added Inbox document is
definitionally unprocessed.

`file_path` itself is unaffected in both functions — same naming, same
content, same "processed if processed, otherwise a plain copy" meaning as
today.

## Visible consequences (stated explicitly, not just implied)

- Every new document (Inbox or capture, any file type) permanently uses
  roughly double the disk space — the tradeoff this design accepts.
- The detail view's `Original`/`Open original file` UI — today rare — will
  appear for essentially every new document going forward.
- `writeOriginalToSubfolder()`'s directory-per-document layout means
  `files/` gains one subfolder per new document, not just per
  searchable-PDF document as today.

## Testing

Existing tests with assertions that assume `original_file_path` stays
`null` outside the searchable-PDF path need updating, not just new tests
added — at minimum `tests/test_inbox.py` and the plain-save scenarios in
`tests/test_studio.py`/`tests/test_studio2.py`. A new scenario (in an
existing or new test file) should cover: a plain PDF capture and a plain
Inbox add both now get a real `original_file_path` with
`searchable_pdf_built = 0`; the existing searchable-PDF capture scenario
(`tests/test_searchable_pdf.py`) still gets `searchable_pdf_built = 1`; and
the one-time backfill itself — a pre-existing-shape seeded library
(`original_file_path` populated the old way for a `captured` document, a
`migrated` document with its own unrelated `original_file_path`, and a
`scan-inbox` document with none) reads back with the correct
`searchable_pdf_built` values after open, and stays correct across a
second reopen (idempotency of the one-time marker).

## Documentation

`CLAUDE.md`'s sidecar/migration notes and the searchable-PDF architecture
note need updating to describe: the new `searchable_pdf_built` column and
why it exists now, the one-time backfill and its `source = 'captured'`
predicate, and that `original_file_path` no longer implies "searchable PDF
built" on its own. `README.md`/`README.de.md`'s schema section should
mention the new column.
