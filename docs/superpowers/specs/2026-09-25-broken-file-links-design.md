# Broken file links — Design

**Status:** Approved, ready for implementation planning.

## Problem

A document's `file_path`/`original_file_path` can stop resolving if the
underlying file is moved, renamed, or deleted outside the app — Dossiary
has no way to notice this proactively. Today the only way to discover it
is to click "Open file"/"Open original" from the detail panel and get a
generic `alert()` error. There's no way to see, at a glance, which
documents in a library have gone stale this way, and no way to fix one
short of manually restoring the exact file at the exact expected path
outside the app.

## Scope

- Detect any non-deleted document whose `file_path` and/or
  `original_file_path` is set but fails to resolve to a real file.
- Fold this check into the just-shipped "Find duplicates" modal rather
  than adding a 6th toolbar button — the modal and its toolbar button are
  renamed to the more general "Library check" (`#library-check-btn`,
  `openLibraryCheckModal()`), and now renders up to three sections in one
  pass: exact-hash duplicate groups, Title+Date duplicate groups, and a
  new broken-file-links section. Task 4's existing DOM ids, i18n keys, and
  test scenarios for the old "Find duplicates" name are updated as part of
  this same work.
- A "re-link" action per broken path: pick a replacement file via a native
  file picker, and write its bytes directly into the exact path already
  stored in the database — no path or database row changes, since the
  path itself was already correct; only the missing file at it is
  restored.
- If the re-linked path is the one `file_hash` was derived from
  (`original_file_path`, or `file_path` for a document with no preserved
  original — the same fallback rule duplicate detection's own hashing
  already uses), recompute and persist `file_hash` from the replacement
  bytes, so future duplicate scans reflect the document's real current
  content.

Out of scope: `thumbnail_path` (cosmetic, already has its own fix via
"Generate preview"); any general file-replacement feature for a document
whose file is *not* broken (this stays narrowly "restore what's missing
at the path that's already there," not a new way to swap a working
document's file); any new toolbar button.

## Architecture

**The check itself needs no persisted state and no lazy backfill.** Unlike
duplicate detection's SHA-256 hashing (expensive enough to justify a
one-time-per-library backfill), an existence check is cheap — it never
reads a file's bytes, just calls `resolveFileHandle(path, false)` and
catches whatever it throws (any error, not narrowly `NotFoundError` —
matching this app's existing generic file-error handling elsewhere, e.g.
`buildDetailActions()`'s own `alert(t('detailOpenFileError', {error:
e.message}))`). It runs fresh every time the modal opens, over every
non-deleted document (archived and needs-review documents included, same
"tells the truth about the whole non-deleted library" reasoning
duplicate detection's own checks already use). A document whose path is
`NULL` was simply never given one and is not flagged — only a *set* path
that fails to resolve counts as broken.

**The modal itself is renamed and restructured.** `#find-duplicates-btn` →
`#library-check-btn` ("🔍 Find duplicates" → "🔍 Library check," same
icon), `openFindDuplicatesModal()` → `openLibraryCheckModal()`, and its
own i18n keys (`toolbarFindDuplicates`, `duplicatesModalTitle`, etc.)
renamed to match. The modal now computes three result sets on open —
`computeExactHashDuplicateGroups()`, `computeMetadataDuplicateGroups()`
(both unchanged from duplicate detection), and a new
`computeBrokenFileLinks(docs)` — and renders a labeled section per result
set, omitting any section with nothing to show rather than displaying an
empty heading. The existing lazy `file_hash` backfill (needed for the
duplicate-grouping sections) is unaffected by this change and still runs
first when needed; the new broken-links check doesn't participate in that
backfill at all, since it has no cost to defer.

**Each broken document renders as its own row**, independent from the
duplicate-group rows above it, showing the document's name and a "File"
and/or "Original" indicator for whichever of its two paths actually
failed to resolve — a document with only one broken path shows only that
one. Each indicator carries its own "Re-link…" control. Clicking it opens
a plain `<input type="file">` picker, with the same
`accept="application/pdf,image/*"` restriction the capture form's own
file input already uses (the same mechanism, not a new one — no File
System Access directory picker needed, since this is writing into a path
already inside the already-open library, not choosing a new top-level
location). Once a file is picked, its bytes are written into the exact stored path via
`resolveFileHandle(path, true)` (creating what's missing) — the picked
file's own name is irrelevant, since the stored path doesn't change, only
the bytes now sitting at it.

**Hash correctness after a re-link.** If the just-repaired path is the one
`file_hash` was derived from — `original_file_path` when the document has
one, otherwise `file_path` — the hash is recomputed from the replacement
bytes via the existing `computeFileHash()` helper and persisted (a single
`UPDATE documents SET file_hash = ? WHERE id = ?`, mirroring
`backfillFileHash()`'s own write pattern). Re-linking the *other* path
(e.g. `file_path` on a document that also has its own
`original_file_path`) leaves `file_hash` untouched, since it was never
derived from that path in the first place. Without this, a document's
hash would silently describe bytes that no longer exist anywhere the
moment a real (non-identical) replacement file is supplied, producing
misleading results in future duplicate scans.

After a successful re-link, that specific broken indicator is removed
from the row in place (or the whole row is removed if it was the
document's only broken indicator) — no full re-scan of the other two
sections is needed, since nothing about duplicate grouping changed.

## Error handling

A failed re-link write (permission revoked mid-session, disk full) is
caught and shown inline on that same row — the indicator stays showing
broken, so nothing silently looks fixed when it isn't. Cancelling the
native file-picker dialog without choosing anything is a no-op, matching
how the capture form's own file input already behaves. Because the
broken-link check has no persisted state, there's no equivalent of
duplicate detection's own "first open pays a one-time cost" — every
"Library check" open re-checks fresh and equally cheaply.

## Testing

A new `tests/test_broken_links.py`: a document with a genuinely missing
`file_path` is flagged; one with a missing `original_file_path` is
flagged; one with both missing shows both indicators independently on one
row; a document with a `NULL` path (never had one) is correctly *not*
flagged; a deleted document is excluded from the check entirely even if
its own paths are broken; re-linking `file_path` writes the picked bytes
to the exact original stored path and makes that indicator disappear;
re-linking the hash-deriving path (`original_file_path`, or `file_path`
on a document with none) recomputes and persists `file_hash` from the new
bytes, while re-linking the *other* path leaves the document's existing
`file_hash` completely untouched; and a failed write during re-link
leaves the row still showing broken with an inline error rather than
silently appearing fixed.

Task 4's existing 8 scenarios in `tests/test_duplicate_detection.py` are
updated in the same change for the renamed button id
(`#library-check-btn`), modal-opening function
(`window.__DEBUG_openLibraryCheckModal`), and i18n keys — none should be
left referencing the old "Find duplicates" names once this ships.
