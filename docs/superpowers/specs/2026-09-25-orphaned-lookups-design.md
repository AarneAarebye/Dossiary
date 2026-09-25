# Orphaned tags/people cleanup — Design

**Status:** Approved, ready for implementation planning.

## Problem

Dossiary has always left orphaned `tags`/`people` rows in place forever — a
tag removed from every document that used it, or a person's name that no
longer appears anywhere, stays in the database indefinitely. This was a
deliberate choice (see `CLAUDE.md`'s existing "harmless unused lookup
entries, still useful for datalist autocomplete" reasoning), but a
long-lived library can accumulate a real number of these over time, and
there's no way to see or remove them today.

## Scope

- Detect any `tags`/`people` row not referenced by any non-deleted
  document — a document sitting in the Waste bin doesn't count as "using"
  its tags/people, so a tag/person referenced only by a Waste-bin document
  is treated as orphaned.
- A person is checked against *every* person-type field a document might
  carry (People, Author, Collaborator, ...), not just the built-in People
  field — the same name is the same `people` row across all of them.
- Fold this into the existing "🔍 Library check" modal as two more
  sections, "Orphaned tags" and "Orphaned people", appended after the
  existing broken-file-links section — matching the precedent set by
  duplicate detection and broken file links rather than adding a fourth
  near-identical toolbar button.
- A real, new "Delete" action per orphaned row, plus a "Delete all
  orphaned" bulk action per section — without this the feature would only
  ever show a list with nothing to do about it, since no UI anywhere in
  this app can currently delete a tag or person row.
- Both the per-row Delete and the bulk Delete all require a native
  `confirm()` before acting — this is the first genuinely irreversible
  action this maintenance-feature family has added (duplicate detection
  and broken-file-links never destroy data), and deliberately the first
  `confirm()` dialog anywhere in this app's own UI.

Out of scope: any general tag/person *management* screen (renaming,
merging, viewing usage counts for tags/people that are still in use); any
change to how tags/people are created, deduplicated, or displayed
elsewhere in the app.

## Architecture

**Detection is entirely in-memory, needs no new database query, and
requires no persisted state or backfill** — every document object in
`allDocs` already carries `d.tags` (an array of tag name strings) and
`d.personFieldValues` (a map of `{fieldName: [names]}` covering every
person-type field on that document), both loaded at library-open time for
display purposes already. `computeOrphanedTags(docs)` and
`computeOrphanedPeople(docs)` each build a `Set` of every name actually in
use across the non-deleted documents in `docs` (`d.tags` flattened for
tags; `Object.values(d.personFieldValues || {}).flat()` flattened for
people), then filter the existing `tagNameToId`/`personNameToId` maps
(already loaded, already the full roster of every tag/person row) down to
the names *not* in that set. Both run fresh on every "Library check" open,
the same "cheap enough to just recompute" reasoning `computeBrokenFileLinks()`
already uses — no hashing, no file I/O, just a couple of `Set` lookups over
data already in memory.

**Rendering.** Two new sections in `renderLibraryCheckResults()` (which
already takes `exactGroups`, `metadataGroups`, `brokenLinks` — this adds
`orphanedTags`, `orphanedPeople`), each omitted entirely when empty, same
as every existing section. Unlike every row rendered in this modal so
far, an orphaned-tag/person row doesn't represent a *document* — there's
nothing to click through to a detail panel for — so these rows get their
own markup, not `.duplicate-row`: just the name and a "Delete" button,
non-clickable. Each section's own header carries a "Delete all orphaned"
button next to the section label, shown only when that section has at
least one row.

**Deletion.** `deleteOrphanedTag(name)`: `DELETE FROM tags WHERE id = ?`
plus a cascade `DELETE FROM document_tags WHERE tag_id = ?` (cleans up any
stale join rows — by construction, any remaining ones can only belong to
Waste-bin documents, since a live reference would have kept the tag out of
the orphaned list), removes the name from the in-memory `tagNameToId` map,
and refreshes the tag autocomplete datalist so it stops being suggested
immediately. `deleteOrphanedPerson(name)` is the same shape against
`people`/`document_field_people`/`personNameToId`/the person datalist.
A single per-row Delete persists immediately (`persistDb()`) — one row,
one write, nothing to batch. "Delete all orphaned" is a real bulk action
in the same sense as this app's existing bulk-action buttons (Archive/
Delete/Flag-for-review), so it follows their same established convention:
one shared `confirm()` covering every row in that section (not one
confirm per row), every `DELETE` queued first, and exactly one
`persistDb()`/re-render at the end — not one persist per row.

**A real, accepted consequence of treating Waste-bin-only references as
orphaned:** if a tag/person is deleted while its only reference was on a
document sitting in the Waste bin, and that document is later restored,
the restored document will silently no longer show that tag/person — the
join row pointing at the now-gone id is harmless dead weight, but the name
itself is permanently gone. This is a direct, deliberate consequence of
the scoping decision above, not a bug to guard against.

## Error handling

Both `confirm()` dialogs are the only gate — declining either one is a
complete no-op, nothing is read or written. A person renaming/re-adding a
tag or person elsewhere while this modal happens to be open isn't a
concern in practice, since the modal blocks interaction with the rest of
the page the same way every other modal in this app already does.

## Testing

A new `tests/test_orphaned_lookups.py`: a tag/person still used by a
non-deleted document is never flagged; a tag/person used only by a
document that's been moved to the Waste bin *is* flagged; a person used
via a non-People person-type field (e.g. a custom "Author" field) is
correctly recognized as in-use and not flagged; per-row Delete removes
just that row and persists it; "Delete all orphaned" clears every row in
that section in one action; a deleted tag/person disappears from its
autocomplete datalist immediately; declining either `confirm()` dialog
leaves everything unchanged; and restoring a Waste-bin document whose tag
was deleted while orphaned comes back without that tag, rather than
crashing or showing a stale reference.
