# Persistent detail panel

## Context

Legacy Mariner Paperless (the app this repo descended from) shows a
document's metadata in a persistent, collapsible side panel next to the
document table — click a different row, the panel's content updates live;
the table itself never leaves the screen. Dossiary's current equivalent,
`openDetail()`, is a full-screen **modal**: clicking a row opens an
overlay with the document's metadata, action buttons, and file paths, and
the table underneath is completely inaccessible until the modal closes.

This replaces the modal with a persistent panel matching Mariner's own
UX — defaulting to **collapsed**, given the real horizontal-space cost a
permanent panel adds on top of this app's already-tight `.table-wrap`/
toolbar layout (see CLAUDE.md's own extensive calibration notes). Editing
stays exactly as it is today — a separate modal, entirely untouched by
this spec — this is purely about how the *read-only* view is presented.

## Approach

### A new "selected row" concept

Nothing in Dossiary currently tracks "which row is the user looking at" as
persistent UI state — the modal made that unnecessary, since only one
document's detail could ever be on screen at a time and closing it left no
trace. A persistent panel needs this concept for real: a new module-level
`let selectedDocId = null`, set whenever a row is clicked, and reflected
visually as a highlighted table row (a new CSS class, e.g. `.row-selected`,
applied via the existing `render()`/table-rebuild pass the same way
`.row-select-checkbox`'s own state already gets reapplied on every
render — distinct from that existing bulk-select checkbox mechanism, which
tracks a *different*, multi-document selection for bulk actions).
`selectedDocId` resets to `null` (panel shows its empty state — a simple
"Select a document to see its details" message, mirroring the tone of
this app's other empty states) when the selected document is deleted, or
is filtered/scrolled out of the current view's data entirely — checked
wherever `render()` already recomputes the visible row set.

**Clicking a row never auto-expands a collapsed panel.** Row click always
sets `selectedDocId` and re-renders the panel's content and the table's
highlight, regardless of whether the panel is currently expanded or
collapsed — this is cheap, and means the panel is already showing the
right document the moment someone *does* open it. But if it auto-expanded
the panel too, the collapsed default would stop mitigating anything: the
panel would spring open on the very first row click any time someone uses
the app, which is exactly the horizontal-space cost this design is meant
to avoid by default. Expanding the panel is only ever the explicit toggle
button's job.

### `openDetail()` retargeted, not rewritten

The function keeps its name and almost all of its existing logic — it
already fully rebuilds a container's `innerHTML` from scratch on every
call (`modalRoot.innerHTML = ...`, dossiary.html:4543-4589) and already
has a well-established "call `openDetail(id)` again to refresh" pattern
used after every action (archive toggle, flag toggle, delete toggle,
regenerate thumbnail, add/remove from a collection — six call sites,
dossiary.html:4620/4639/4665/4682/4788/5097). That pattern is exactly
what a persistent panel needs too, so the *content-building* half of the
function (the `actions`/`thumbHtml`/`pageCount`/header/Fields-section
logic) carries over essentially unchanged. What changes is the *container*
and the modal-specific chrome around it:

- Target a new persistent element instead of `modalRoot` — the panel's
  own body element.
- Drop the modal wrapper entirely: no `.backdrop`/`#modal-backdrop`, no
  `role="dialog" aria-modal="true"`, no `.modal-close` button. A
  `role="complementary"` landmark on the panel itself is a reasonable
  accessibility substitute, not a hard requirement for this pass.
- Drop `document.addEventListener('keydown', onModalKeydown)` — there's
  nothing to Escape-close; the panel isn't a modal. (Whether Escape should
  instead *collapse* the panel is a nice-to-have, explicitly out of scope
  for this pass — see below.)
- The six existing "refresh" call sites keep working with zero logic
  changes — they just now re-render into the panel instead of
  `modalRoot`, exactly as intended.

Two call sites need real behavior changes, not just a retarget, because
they currently rely on the modal-overwrite trick (calling `openDetail(id)`
implicitly replaces whatever the edit form's modal was showing, since both
write to the same `modalRoot`) — with the panel and the edit modal now
being two separate, simultaneously-existing elements, that trick no longer
applies:

- **`cancel-edit-btn`** (dossiary.html:4902, inside `openEditForm()`):
  today, `() => openDetail(id)` both closes the edit modal *and* reopens
  the detail modal in one call, since it's the same root element. With the
  panel, Cancel should just close the edit modal (`closeModal()`) — the
  panel, if open, already shows this document (it's how Edit was almost
  certainly reached), so nothing needs to be re-rendered. If the panel is
  currently collapsed, Cancel does **not** auto-expand it — collapsing was
  a deliberate choice, and an edit that changed nothing shouldn't override
  it.
- **`saveEditedDocument()`'s success path** (dossiary.html:5097): today,
  the trailing `openDetail(id)` call closes the edit modal and opens the
  detail modal showing the just-saved data, again via the shared-root
  trick. With the panel, this becomes two explicit steps: `closeModal()`
  (dismiss the edit modal) plus setting `selectedDocId = id` and
  re-rendering the panel — covering the case where Edit was reached via
  the row-level `.row-edit-btn` shortcut (which "skip[s] `openDetail()`
  entirely," per its own existing documentation) rather than from the
  panel itself, so the just-edited document becomes the selected one and
  shows in the panel (if open) and highlighted in the table either way.

### Toggle, persistence, and layout

A toolbar button (alongside "⚙ Columns") toggles the panel, labeled e.g.
"☰ Details." State persists per library via the same `settings`-table
key/value pattern as `nav_style` (`loadDetailPanelExpanded()`/
`saveDetailPanelExpanded()`), **defaulting to collapsed** for a library
that's never set the preference — the explicit mitigation for the
horizontal-space concern this spec opened with.

Layout: the table and the panel become flex siblings inside a new
wrapping row element, with `.table-wrap` given `flex:1` (so it keeps
consuming whatever width the panel isn't using) and the panel a fixed
width (a specific px value to be picked empirically during
implementation, in the same "measure against a real seeded viewport"
spirit as every other layout number in this app — no default width is
assumed here). This is a purely **horizontal** change and does not touch
`.table-wrap`'s existing `max-height` calibration (the vertical axis) at
all — the panel sits beside the table, not above or below it, so none of
CLAUDE.md's hard-won height-calibration constants need to move. Below the
existing mobile breakpoint, the panel force-collapses regardless of the
saved preference, matching the same "accept extra gap, never accept
overlap" principle already used for every other narrow-viewport
accommodation in this app.

Reports view renders its own aggregate view rather than sharing the
document table (per its own existing design), so there's no "row" for the
panel to reflect there — the toggle button hides in that view, matching
how "Show archived" is already conditionally shown only where it's
meaningful.

### Comment-accuracy sweep

Numerous existing comments across `dossiary.html` refer to `openDetail()`
by name as "the detail modal" or describe an action as reopening "the
modal" (the six refresh call sites, plus at least one cross-reference in
the Waste bin architecture note, dossiary.html:6142, and the
`openDocCollectionMenu` comment at dossiary.html:2108). None of these need
the function *renamed*, but every one describing it as a modal needs its
wording corrected to "panel" — the same discipline this repo has already
applied after prior semantic shifts (e.g. the Currency capability-checkbox
comment sweep during the Amount/Currency filter branch).

## Out of scope

- **Editing stays exactly as it is** — a separate modal, `openEditForm()`,
  completely untouched beyond the two call-site changes described above.
  No live/inline editing in the panel, matching Mariner's own screenshot.
- **No resizable/draggable panel width** — a fixed width for this pass;
  YAGNI until an actual need for a different width surfaces.
- **No Escape-to-collapse keyboard shortcut** — a reasonable future
  nicety, not required here; the panel isn't a modal, so nothing needs a
  dismiss gesture to remain usable.
- **No change to the row-level `.row-edit-btn` hover shortcut's own
  behavior** — it still jumps straight to the edit form, skipping the
  panel/selection step on the way in; only what happens *after* saving
  (described above) changes.
- **No panel presence in Reports view** — that view has no document rows
  to select in the first place.

## Critical files

- `dossiary.html`:
  - New module-level `let selectedDocId = null;` and a `.row-selected`
    highlighting pass, wired into the existing table-rebuild logic.
  - New panel container markup (a fixed-width sibling of `.table-wrap`
    inside a new flex-row wrapper) and its own empty-state content.
  - `openDetail()` (~line 4479-4667) — retarget from `modalRoot` to the
    new panel container; drop backdrop/close-button/`onModalKeydown`
    wiring; the six existing internal "refresh" call sites need no logic
    changes.
  - The table row click handler (~line 4281) — sets `selectedDocId` and
    calls the retargeted `openDetail()`, instead of opening a modal.
  - `openEditForm()`'s `cancel-edit-btn` handler (~line 4902) and
    `saveEditedDocument()`'s success path (~line 5097) — the two behavior
    changes described above.
  - New `loadDetailPanelExpanded()`/`saveDetailPanelExpanded()` functions,
    following `nav_style`'s existing pattern exactly.
  - New toolbar toggle button, hidden in Reports view.
  - New CSS: the flex-row wrapper, the panel's fixed width, the mobile
    breakpoint's forced-collapse override, `.row-selected`.
  - Comment sweep: every existing reference to `openDetail()` as "the
    detail modal" corrected to describe the panel instead (dossiary.html
    ~4620, ~4639, ~4665, ~4682, ~4788, ~2108, ~6142, and any others a
    `grep -n "detail modal\|reopen the modal"` turns up).
- `CLAUDE.md`: a new architecture note, matching this repo's established
  practice for every comparable feature this session, covering the
  `selectedDocId` concept, why the panel doesn't affect `.table-wrap`'s
  height calibration, and the two edit-flow call-site changes.

## Testing

A new Playwright test file, following this suite's established shape,
covering:
- The panel starts collapsed by default for a library that's never set
  the preference; toggling it persists across a reopen (same pattern
  `test_nav.py` already uses for `nav_style`).
- Clicking a row selects it (visible `.row-selected` highlight) and shows
  its metadata in the panel; clicking a different row updates the panel's
  content and moves the highlight, without navigating away from the table.
- Every action available in today's modal (Archive/Unarchive, Delete/
  Restore, Flag for review/Done, Add/Remove from Collection, Edit,
  regenerate preview, Copy path buttons) still works from the panel, with
  the panel's content correctly refreshing in place after each — a
  regression check against the six existing "refresh" call sites.
- A deleted document's panel content collapses to Restore-only, exactly
  as today's modal does.
- Opening Edit from the panel, clicking Cancel, closes the edit modal and
  leaves the panel showing the (unchanged) document — without forcing the
  panel open if it had been collapsed.
- Opening Edit via the row-level `.row-edit-btn` shortcut (bypassing the
  panel), saving a change, closes the edit modal and shows the just-edited
  document as the new selection (panel content, if open, and table
  highlight) — the specific case the save-path behavior change addresses.
- The panel forces closed below the mobile breakpoint regardless of the
  saved "expanded" preference.
- The panel's toggle button is absent in Reports view.
