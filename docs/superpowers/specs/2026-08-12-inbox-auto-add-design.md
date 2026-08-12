# Inbox: skip the review modal, auto-add straight to the review queue

## Context

Today, both ways of triggering an Inbox check open a review modal
(`openInboxModal()`) that lists every staged file in `inbox/` and requires
a further click — either "Add" on an individual file, or "Add all with
defaults" — before anything is written to the library. This extra step
exists specifically because CLAUDE.md's Inbox note documents a deliberate
principle: every write to `library.sqlite` must come from an explicit,
in-the-moment user click, never from data that just showed up on disk.

Now that the Waste bin gives every write a safe, fully reversible undo
path, that extra confirmation step is no longer pulling its weight for
this specific case. The two clicks that already exist — the toolbar's
"📥 Check inbox" button, and the inbox banner's own action button — are
already explicit user gestures; using either of them as the trigger to
add everything found, with no modal in between, still satisfies "every
write is explicitly triggered," it just removes a redundant confirmation
click.

## What's changing

Both existing entry points stop opening the review modal and instead
immediately add every currently-staged file, using exactly the same
per-file logic and defaults `addInboxFile()`/`addAllInboxFiles()` already
apply today (filename-derived title, `document_type` prefilled from
`default_document_type` if configured, `needs_review = 1`,
`source = 'scan-inbox'`, no OCR). Nothing about *what* gets written
changes — only when the write happens (immediately on click, not after a
second confirming click) and that the modal is gone.

### Toolbar "📥 Check inbox" button (`#inbox-check-btn`)

Current: click → `checkInbox()` (fresh scan) → `openInboxModal()`.

New: click → `checkInbox()` (fresh scan, unchanged — this part never
writes) → if any files were found, add all of them, navigate to the 🚩
Inbox nav view, and show a status message summarizing the count (e.g.
"Added 3 documents to the review queue from the inbox."). If nothing was
found, show a status message ("No files waiting in inbox.") and stay on
the current view — no navigation for a no-op.

### Inbox banner (`#inbox-banner`, its button `#inbox-review-btn`)

The banner itself keeps behaving exactly as it does today: it's populated
by the one automatic `checkInbox()` call in `afterDbReady()` right after a
library opens, and that automatic scan still never writes anything — only
a real click writes. What changes is what the banner's button does and is
called: today it's labeled "Review" and opens the modal; going forward it
adds everything the banner is already showing, navigates to the Inbox nav
view, and shows the same kind of status message the toolbar button shows.
Its label changes from "Review" to "Add all", reflecting the new,
un-mediated action. The banner disappears once its files are added, same
as it does today once the inbox is empty.

### Removed

`openInboxModal()`, its markup (the modal's `<h2>Inbox</h2>` dialog, the
`#inbox-list` file-preview list, the per-file `.inbox-add-one-btn`
buttons, the `#inbox-add-all-btn` button, and the modal's own
`#inbox-refresh-btn`), and `renderInboxList()` all become unreachable and
are deleted as dead code, per this codebase's stated convention of not
leaving half-used code around once nothing calls it.

`addInboxFile()`'s and `addAllInboxFiles()`'s own logic is **not**
rewritten — they already guard every modal-DOM reference
(`el('inbox-status')`, `el('inbox-list')`) with a null check, so they
degrade harmlessly with the modal gone. `addAllInboxFiles()`'s one
modal-specific line (`if(!pendingInboxFiles.length) closeModal();`, run
after the loop) is removed since there's no modal to close.

## Data flow / architecture

No schema change, no new dependency. `checkInbox()`'s own contract is
unchanged: it is still the only thing that reads `inbox/`, still never
writes, and still only runs automatically once (right after a library
opens) or on an explicit click of `#inbox-check-btn` — the toolbar
button's whole reason for existing (per CLAUDE.md's own note) was letting
someone notice a file staged *after* the library was already open without
fully reopening it; that reasoning is unchanged, it just now also
triggers the add in the same click rather than requiring a second one.

## Error handling

`addInboxFile()`'s existing per-file try/catch (rolls back the reserved
`nextDocId` and reports a failure via the modal's status element if one
exists) is untouched. Since the modal element is gone, a per-file failure
during a bulk add from either new entry point falls back to whatever the
app-wide `setStatus()` call inside `addInboxFile()` already shows (it's
called unconditionally alongside the modal-only status update) — no new
error-handling path is needed, this already works today whenever the
modal happens to be absent from the DOM for any reason.

## Testing

`tests/test_inbox.py` needs a real rewrite, not just a patch, since its
Scenario 2 and Scenario 3 exercise the modal directly (`#inbox-review-btn`
opening it, `.inbox-add-one-btn`, `#inbox-add-all-btn`,
`#modal-close-btn`, `#inbox-refresh-btn`) and Scenario 5 clicks
`#inbox-check-btn` expecting it to open the modal. The rewritten file
needs to cover:

- Banner still shows the pending count as soon as the library opens
  (unchanged from today's Scenario 1).
- Clicking the banner's button adds every staged file directly (no modal
  ever appears), lands on the 🚩 Inbox nav view, and the added
  document(s) carry the same fields as today (filename-derived title,
  `source = 'scan-inbox'`, `needs_review = 1`, a real
  `original_file_path`, `searchable_pdf_built = 0`) — folding in what
  today's Scenario 2's persisted-document assertions check.
- The staged file is moved out of `inbox/` and into `files/` (today's
  Scenario 2's directory-listing assertions).
- The banner disappears once its files are added (today's Scenario 3's
  banner-visibility assertion, reached without the modal).
- Reopening an already-emptied library keeps the banner hidden (today's
  Scenario 4, unchanged).
- A file staged after the library is already open doesn't surface on its
  own (no auto-poll) — clicking `#inbox-check-btn` finds it, adds it
  directly, and lands on the Inbox nav view (today's Scenario 5, minus
  the modal-opening assertion).
- New: clicking `#inbox-check-btn` when `inbox/` is empty shows the
  "nothing waiting" status message and does not navigate away from the
  current view.
- New (or folded into the above): after an inbox-added document is
  flagged `needs_review`, the existing Done flow (already covered by
  today's Scenario 2's second half) still works unchanged — this is
  exercising already-existing `toggleNeedsReview()` behavior, not new
  code, so a light touch here is enough.

`tests/test_inbox_folder_creation.py` doesn't reference the modal or
either button and needs no changes.

## Non-goals

- No change to how `inbox/` gets populated (`scan_watch.py`, manual
  drag-and-drop) — this is purely about what happens once files are
  already staged there.
- No change to `addInboxFile()`'s per-file defaults (still no OCR, still
  category/date/etc. left blank, still `default_document_type` prefill).
- No per-file selective add — since the whole point is removing the
  review step, there's no longer a way to add only *some* of the staged
  files from either entry point; anyone who adds something unwanted can
  waste-bin it afterward.
