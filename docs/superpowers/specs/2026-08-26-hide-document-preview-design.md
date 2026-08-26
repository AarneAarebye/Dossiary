# Hide the detail panel's document preview

## Context

The persistent detail panel (`openDetail()`, `dossiary.html`) shows a small
(110x140px) thumbnail image — or a dashed placeholder box when none exists
yet — at the top-left of its content, next to the title/metadata column
(`.modal-head`). A "Generate preview"/"Regenerate preview" action in the
panel's action bar (`regen-thumb-btn`, built by `buildDetailActions()`,
already marked `panelOnly: true` so it never appears in the row context
menu) produces that image on demand.

Until there's a carousel/gallery-style view that could make a preview
image genuinely useful (e.g. flipping through a multi-page document), the
single static thumbnail mostly just costs horizontal space in the panel
for a preview a person can get more useful info from by clicking "Open
file" anyway. This spec hides the preview image and its Generate/
Regenerate action, while keeping the underlying thumbnail-generation code
fully intact and easy to re-enable later.

## Approach

### A single named toggle, not scattered comments

A new top-level constant, `SHOW_DOCUMENT_PREVIEW = false` (declared near
`APP_VERSION`, with a comment explaining what it gates and why it's off),
is the one thing that needs to change to reactivate this feature.
Literally commenting out the display code was considered and rejected:
the thumbnail HTML isn't a standalone statement, it's built into a
`thumbHtml` variable interpolated inline inside `openDetail()`'s one large
template-literal string (`` `${thumbHtml}` ``) — there's no clean way to
`/* */`-wrap something living inside a template literal without either
breaking the string or leaving orphaned dead code around it. A single
boolean flag reactivates with a one-word edit in one place, rather than
hunting for comment markers across the two separate call sites this
touches.

### What the flag gates

Two places in `dossiary.html`:

- `openDetail()`'s thumbnail-fetch-and-render block — the code that
  computes `thumbHtml`, covering all three cases it currently handles
  (a real `<img>` when `d.thumbnail_path` resolves, "no preview yet" when
  there's no `thumbnail_path`, and "preview missing" when the stored path
  fails to resolve). When the flag is off, none of this renders — not
  even the dashed empty-state placeholder box. Rendering an empty
  placeholder instead of the real thumbnail would still cost the same
  110x140px of space, defeating the entire point of this change. The
  panel's `.modal-head` (`display:flex; gap:20px;`) already collapses
  correctly to just its metadata child when the thumbnail child is
  omitted entirely — flex `gap` only applies between actual children, so
  there's no orphaned gap left behind.
- `buildDetailActions()`'s `regen-thumb` descriptor — simply not appended
  to the returned array when the flag is off, rather than appended and
  then filtered out downstream. Since this descriptor is already marked
  `panelOnly: true`, the row context menu (`showRowContextMenu()`) never
  consumed it in the first place; this is the only place that needs to
  change for the button to disappear.

### What's deliberately untouched

Thumbnail *generation* on capture and Inbox-add (`generateThumbnail()`,
`writeThumbnail()`, called from `saveNewDocument()`,
`createReviewDocumentFromFile()`) keeps running exactly as it does today,
regardless of `SHOW_DOCUMENT_PREVIEW`. `thumbnail_path` stays populated
for every newly captured document the entire time the preview is hidden,
so reactivating the feature later needs no backfill pass — every
document captured while the toggle is off already has a real thumbnail
file sitting in `thumbnails/`, ready to display the moment the flag flips
back to `true`.

## Out of scope

- Any change to thumbnail generation itself, its storage format, or the
  `thumbnails/` folder layout.
- A carousel/gallery view, or any other future consumer of the thumbnail
  image — this spec only hides the one existing consumer.
- A user-facing setting to toggle this (Field Settings or otherwise) —
  this is a hardcoded, developer-facing toggle for a feature being
  deliberately shelved, not a per-library preference.
- Removing the `thumbnail_path` column, `regenerateThumbnail()`, or any
  other code the display block or the action depend on — everything
  needed to fully restore the feature must still exist and work, gated
  only by the one flag.

## Critical files

- `dossiary.html`:
  - New `SHOW_DOCUMENT_PREVIEW` constant near `APP_VERSION`.
  - `openDetail()`'s `thumbHtml`-building block, gated by the new
    constant.
  - `buildDetailActions()`'s `regen-thumb` descriptor, gated by the new
    constant.
  - CLAUDE.md: a note next to the existing thumbnail/preview
    documentation explaining the toggle, its location, and that
    generation itself keeps running underneath.
- `tests/test_thumbnails.py`, `tests/test_regenerate.py`: both click
  "Regenerate preview" and assert on `.modal-thumb`/`.modal-thumb-empty`,
  which won't exist with the flag off by default. Both need to keep
  proving the underlying generate/regenerate/display pipeline still
  works end-to-end (not just get deleted, which would let that code
  silently bit-rot while the feature is off) — the plan should specify a
  concrete mechanism for running them against a copy of `dossiary.html`
  with the constant patched to `true`, consistent with how this suite
  already stubs/intercepts other parts of the page rather than needing a
  test-only hook baked into production code.

## Testing

- With the default (flag off) configuration: opening the detail panel
  for a document that has a real thumbnail on disk shows neither the
  `<img>` nor an empty placeholder box, and no "Generate preview"/
  "Regenerate preview" button appears in the action bar — genuinely
  absent from the DOM, not merely hidden via CSS, matching this app's
  existing convention for conditionally-omitted actions (e.g. the Waste
  bin's trimmed action set).
- With the flag patched to `true` for that one test run: the existing
  `test_thumbnails.py`/`test_regenerate.py` coverage (image and PDF
  thumbnail generation on capture, the empty-state placeholder, clicking
  Generate/Regenerate and seeing the real image appear, the button's
  label switching between "Generate preview" and "Regenerate preview")
  continues to pass unchanged, proving the underlying feature still works
  correctly and hasn't decayed while hidden.
- A document captured while the flag is off still gets a real
  `thumbnail_path` written and a real file in `thumbnails/` — confirmed
  directly against the persisted database/filesystem state, not just
  that the panel doesn't show it.
