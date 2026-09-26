# Storage stats — Design

**Status:** Approved, ready for implementation planning.

## Problem

Every document now permanently uses roughly double the disk space it used
to, because `writeOriginalToSubfolder()` unconditionally preserves a raw
original file alongside the "active" copy (a processed searchable PDF when
one was built, otherwise a plain duplicate of the same bytes) — see the
"Preserving an original file on ingestion" note in `CLAUDE.md`. There is
currently no way for a person to see how much disk space their library
folder is actually using, let alone how much of that is this doubling
overhead versus genuinely distinct content, or files sitting on disk that
nothing in the library even points to anymore.

## Scope

- A new toolbar button, **"💾 Storage stats"**, opening its own modal —
  deliberately not folded into the existing "🔍 Library check" modal,
  since this is a read-only overview, not a "detect a problem, offer to
  fix it" check the way that modal's other sections all are.
- Computes real disk usage by walking the actual `files/`, `thumbnails/`,
  and `inbox/` folders (`for await (const [name, handle] of
  dirHandle.entries())`, the same pattern `checkInbox()` already uses) and
  reading each file's real size via `getFile().size` — not by trusting
  whatever `allDocs` happens to track, since that would silently miss any
  file nothing in the database points to.
- Shows a grand total, a per-folder breakdown (`files/`/`thumbnails/`/
  `inbox/`/`library.sqlite`), and — within `files/` specifically — an
  active/original/untracked split, directly answering the question that
  motivated this feature.
- Runs the walk immediately when the modal opens (the click on the
  toolbar button is itself the explicit trigger), showing a busy/spinner
  state while it's in progress.

Out of scope: any per-document size breakdown, sorting, or "biggest
documents" list; any delete/cleanup action for untracked files (this
feature only shows they exist — a future feature could add cleanup, but
that's not this one); caching or persisting the computed totals across
modal opens (always recomputed fresh, matching every sibling
maintenance-feature check's own "no persisted state" convention except
duplicate detection's own file-hash backfill, which this doesn't need
since summing `.size` never requires reading a file's actual bytes).

## Architecture

**The walk is a real, on-demand folder traversal, not a summary of
tracked metadata.** `computeStorageStats()` walks `filesDirHandle`
recursively (`files/` contains one subfolder per document with a
preserved original, `files/<id>_<baseName>/<originalName>`, plus each
document's own active file sitting directly in `files/` itself as
`<id>_<baseName><ext>`), `thumbnailsDirHandle`, and `inboxDirHandle` (when
it exists — a library that's never received an inbox file has no `inbox/`
folder to walk, which is not an error), summing every file's real
`getFile().size`. `library.sqlite`'s own size is added to the grand total
separately, since it isn't part of any of the three folders above.

**Every file under `files/` is classified into exactly one of three
buckets** by comparing its own relative path against every document's
`file_path`/`original_file_path` in `allDocs` — **including documents in
the Waste bin**, since a soft-deleted document's files are never touched
on disk (per the Waste bin's own "nothing on disk is ever touched"
design) and are still real, physically present, space-consuming files:

- **Active** — matches some document's `file_path`.
- **Original** — matches some document's `original_file_path`.
- **Untracked** — matches neither. This is a genuine, useful side effect
  of walking the real folder rather than trusting the database: a file
  under `files/` that no document row points to at all. This feature
  doesn't offer any way to remove it (out of scope, see above) — it only
  makes it visible, which nothing else in this app currently can.

`thumbnails/` gets the same two-way split (active/untracked, matched
against `thumbnail_path` — there's no "original" concept for a generated
preview). `inbox/` isn't split further at all — every file staged there is
equally "not yet added," so its own folder total is the only number shown
for it.

**Rendering.** A new modal (its own toolbar button and open function,
independent of `openLibraryCheckModal()`) shows a spinner while
`computeStorageStats()` runs, then the grand total, the four-way folder
breakdown, and the `files/` active/original/untracked split — every
number formatted with a human-readable, auto-scaling unit (KB/MB/GB),
generalizing the existing `pickedFileSizeKb`-style formatting this app
already uses for a picked file's size during capture rather than a new,
unrelated formatter. If "Untracked" (in either `files/` or `thumbnails/`)
is non-zero, it's called out distinctly rather than silently folded into
a bucket-less total, since it's the one number here likely to surprise
someone.

## Error handling

A missing `inbox/` folder (a library that's never received a staged file)
is treated as zero, not an error, matching `checkInbox()`'s own existing
"a missing folder just means nothing to add" precedent. Any other
per-file read failure encountered mid-walk (a file becoming unreadable
between being listed and having its size read) is skipped for that one
file rather than aborting the whole computation, the same "don't let one
bad file take down an aggregate operation" reasoning `backfillFileHash()`
already uses elsewhere in this app.

## Testing

A new `tests/test_storage_stats.py`: capture a few documents of known
byte sizes, including at least one that builds a searchable PDF (so its
`file_path` and `original_file_path` are genuinely different-sized real
files, not just two copies of the same bytes); stage a file directly in
`inbox/`; write one extra file directly into `files/` via
`window.__TEST_ROOT` that no document's `file_path`/`original_file_path`
points to. Then open the Storage stats modal and confirm: the grand total
equals the real, independently-computed sum of every file's actual byte
size; the four-way folder breakdown sums to the grand total; the
active/original/untracked split within `files/` correctly attributes each
known file, with the deliberately untracked one landing in "Untracked"
and nothing else wrongly landing there; a document moved to the Waste bin
still has its files counted (not silently dropped); and the modal shows a
busy state at least momentarily before resolving to final numbers.
