# Duplicate detection — Design

**Status:** Approved, ready for implementation planning.

## Problem

Dossiary has no way to notice that a document has been added twice — either
as the exact same file (a re-scan accidentally imported a second time, or
the same file staged into `inbox/` more than once) or as two clearly
related entries (the same title and date captured twice, from two
different scans of the same paper). Right now the only way to find these is
to notice by eye while browsing.

## Scope

- **Two kinds of duplicate**: an exact match on the file's own bytes
  (near-certain), and a "likely duplicate" heuristic match on Title + Date
  (same real-world document, different files).
- **Three places this runs**:
  - The capture form warns, non-blocking, the moment a file is picked, if
    its bytes exactly match an already-hashed document.
  - Inbox and drag-and-drop bulk adds silently skip (with explicit
    reporting) a staged file whose bytes exactly match an existing
    document, rather than creating a second document for it.
  - A new "Find duplicates" toolbar button opens a modal listing every
    duplicate group in the library — both exact-file and Title+Date
    matches — for the person to review and resolve using the app's
    existing detail-panel actions.
- **Out of scope**: near-duplicate detection by OCR-text similarity
  (re-scans of the same paper with different file bytes and no matching
  metadata); any bespoke delete/merge action beyond what the detail panel
  already offers; touching `migrate_to_new_library.py` or LibraryLifeboat's
  own schema.

## Architecture

**`documents.file_hash`** (new nullable `TEXT` column, `SCHEMA_MIGRATIONS`)
stores a lowercase hex SHA-256 digest, computed by a small shared helper —
`computeFileHash(file)`: `file.arrayBuffer()` → `crypto.subtle.digest('SHA-256',
buffer)` → hex string.

**The hash is computed on the original uploaded bytes, not the active
`file_path`.** `buildSearchablePdf()` can rasterize-and-rebuild a captured
file during OCR, and two byte-identical source scans processed through that
pipeline at different moments can produce slightly different output bytes
(embedded timestamps and similar). Hashing the *processed* file would
silently defeat exact-duplicate detection for exactly the case it exists to
catch. Since `writeOriginalToSubfolder()` already unconditionally preserves
every new document's raw upload, the hash is computed on that same original,
at the same moment it's written to disk. A document with no preserved
original — a LibraryLifeboat-migrated document, predating this app's own
ingestion pipeline — falls back to hashing `file_path` instead: a weaker,
explicitly accepted signal for that one population, not a reason to touch
the sibling migration script.

New documents (capture, Inbox, drag-and-drop) get their hash computed and
stored at creation time — one file, already being read at that moment
anyway. Existing documents start with `file_hash = NULL` and are backfilled
lazily: the first time "Find duplicates" is opened, it reads and hashes
every not-yet-hashed document's file once, with a progress indicator (the
same "no cap, just show progress" treatment the PDF capture OCR feature
already uses), persisting each hash as it's computed so every later scan
and every capture-time check is instant. Until that first backfill runs,
the capture-time warning can only catch matches against documents that
already happen to have a hash — a real, stated limitation, not hidden
behavior.

### Capture-time warning

The moment a file is picked (`handlePickedFile()`), its hash is computed
immediately and checked against every document's `file_hash` currently in
`allDocs`. On a match, an inline, dismissible warning appears directly in
the capture form — the same `.field-guess`-style banner treatment already
used elsewhere in this form, not a second modal — naming the matched
document with a link to open its detail panel. It is purely informational:
Save stays enabled, nothing is blocked. This checks the exact-hash case
only, never the Title+Date heuristic — form fields may still be blank at
the moment a file is picked, so a heuristic warning that early would just
be noise.

### Inbox / drag-and-drop bulk adds

`createReviewDocumentFromFile(file, source)` — the one shared helper both
`addInboxFile()` and `addDroppedFiles()` already call — computes the file's
hash first. A match against an existing document's `file_hash` means: no
document is created for it, its staged copy is removed from `inbox/`
(mirroring the cleanup a normal successful add already does — an identical
copy already lives safely in `files/`, so nothing unique is lost), and it's
counted toward a new "N skipped as duplicates" clause on the status line,
alongside the existing "Added N document(s)..." report. A non-matching file
in the same batch is added exactly as today, with its own hash computed and
stored. This is a genuine behavior change — Inbox has never silently
not-added a staged file before — and the explicit status-line reporting is
what keeps it from being *silent*, per this app's own "no silent writes"
working convention: nothing about this omits information from the person,
it just avoids creating a redundant document.

### "Find duplicates" modal

A new toolbar button (`🔍 Find duplicates`, alongside the existing
`🔔 Check reminders`/`📥 Check inbox` — the same family of explicit,
on-demand maintenance actions) opens a modal structured like the Reminders
modal. If any document is missing a hash, the backfill pass described above
runs first, with a progress indicator. Then the in-memory `allDocs` is
grouped two ways: exact `file_hash` matches, and normalized (trimmed,
case-insensitive) Title+Date matches — a document with a blank Title or
blank Date is excluded from the Title+Date pass entirely, since matching
against an empty string would produce meaningless mass-groupings. Each
group renders as one row listing its documents, tagged "Exact file match"
or "Likely duplicate (title + date)". Clicking a document in a group closes
the modal, selects that document, and opens its detail panel — the same
click-through pattern the Reminders modal's own rows already use — where
the existing Archive/Delete/Edit actions do the actual resolving; this
feature adds no bespoke delete or merge action of its own.

Deleted documents are excluded from every grouping pass (they're not "in
the library" anymore, same reasoning `matchesView()` already applies
everywhere else); archived and needs-review documents are included, same
"tells the truth about the whole non-deleted library" reasoning Reports and
Collections already use.

## Error handling

A `file_hash` collision between two genuinely different documents is
astronomically unlikely with SHA-256 and isn't designed around. Editing a
document never touches its hash — editing is metadata-only, per this app's
existing architecture, and there's no file-replacement feature for it to
interact with. If the backfill pass hits a document whose file has gone
missing from disk outside the app (`resolveFileHandle` throwing
`NotFoundError`), that one document is skipped for this pass — not a new
error path, since this app doesn't treat a missing file as a hard error
anywhere else either — and the rest of the library still gets hashed.

## Testing

New Playwright scenarios in `tests/test_duplicate_detection.py`: an
exact-hash match detected between two seeded documents with identical file
bytes; a Title+Date match between two documents with different files but
matching title and date, and confirmation that a Title-only match (same
title, different date) is correctly *not* flagged; the capture-time warning
appearing immediately on file pick for a byte-identical file, remaining
non-blocking (Save still succeeds when clicked anyway); an Inbox bulk-add
batch where one staged file is an exact duplicate (skipped, removed from
`inbox/`, counted on the status line) and a second staged file in the same
batch is genuinely new (added normally, with its own hash stored); the lazy
backfill computing and persisting hashes for existing unhashed documents on
the first "Find duplicates" open, and a second open not re-hashing them; a
deleted document excluded from every grouping pass; and clicking a document
within a duplicate group closing the modal and opening its detail panel.
