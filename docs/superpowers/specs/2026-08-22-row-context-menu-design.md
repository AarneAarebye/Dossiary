# Row context menu

## Context

The persistent detail panel (see the two prior specs under
`docs/superpowers/specs/2026-08-21-persistent-detail-panel-design.md` and
`docs/superpowers/specs/2026-08-22-panel-followup-row-interactions-design.md`)
already puts every document action — Open file, Open original file, Edit,
Regenerate preview, Archive/Unarchive, Flag for review/Done, Add/Remove
Collection, Delete/Restore — behind selecting a row and looking at the
panel. This adds a second, faster path to most of those same actions: a
right-click context menu on the row itself, so someone doesn't need the
panel expanded (or to look away from the table) to archive, flag, edit, or
delete a document.

## Approach

### Right-click selects, then opens a menu

A new `contextmenu` listener on each `<tr>`, alongside the existing
`click`/`dblclick` listeners (`dossiary.html` ~lines 4385-4410), calls
`event.preventDefault()` to suppress the browser's native menu, then does
exactly what the existing `click` listener does — sets `selectedDocId`,
applies `.row-selected`, calls `openDetail(id)` to refresh the panel's
content — before opening the new floating menu at the cursor position.
Right-clicking a different row than what's currently selected moves the
highlight there immediately, matching standard desktop-app convention
(Finder, Windows Explorer, Gmail), so every menu item below unambiguously
applies to the now-visibly-selected row. `.select-col`/`.row-edit-col`
already opt their cells out of `click` and `dblclick` via
`onclick="event.stopPropagation()"`; the `dblclick` listener's own comment
already documents that `stopPropagation()` on `click` doesn't cover other
event types, so the new `contextmenu` listener needs the identical
`e.target.closest('.select-col, .row-edit-col')` guard the `dblclick`
listener already uses, not a fresh mechanism.

### Shared action-building logic

`openDetail()` (`dossiary.html` ~line 4612) currently builds its
`actions` array (~lines 4638-4660) as HTML strings with hardcoded element
ids (`id="edit-doc-btn"`, `id="archive-toggle-btn"`, ...), then wires each
one's `click` handler separately later in the same function (~lines
4761-4813). Those ids only work because exactly one copy of each button
exists in the DOM at a time (inside the panel). A context menu item can't
reuse those same ids without colliding, so the actual reusable unit isn't
the rendered HTML — it's the *decision logic* (which actions apply to this
document, in this view, right now) and each action's *handler* (what
happens on click).

This spec's one real refactor: extract that decision logic into a function
returning a plain list of action descriptors — key, label, style variant
(`primary`/`danger`/plain), and a handler closure — for a given document
`id`. `openDetail()` calls it to build the panel's buttons (rendering each
descriptor as a `<button id="...">` exactly as today, then wiring
`element.addEventListener('click', descriptor.onClick)` instead of the
current per-id wiring block); the new context-menu builder calls the exact
same function to build its own menu items, rendering each descriptor as a
menu row instead of a button, wired to the same `onClick`. Neither caller
needs to know how the other renders — they just consume the same list.
This guarantees the menu can never drift out of sync with the panel's own
conditional logic (deleted-document Restore-only, Add/Remove Collection's
view-dependent visibility, etc.) the way two independently-maintained
lists eventually would.

The one handler needing special care during extraction is "Add to
Collection" — it opens its own floating collection-picker
(`openDocCollectionMenu`, `dossiary.html` ~line 2172), positioned relative
to whichever element was actually clicked (`e.target.getBoundingClientRect()`).
That positioning logic already reads its anchor from the click event
rather than assuming a specific button id, so it needs no special-casing
between the panel and the context menu — each caller's own click event
naturally supplies the right anchor.

Per the approved scope: the context menu shows every action the panel
would show for this document **except Regenerate preview** — including
Open file/Open original file, despite double-click already covering file-
opening; the redundancy was confirmed acceptable rather than treated as a
reason to drop it.

### The "Detail" item

A new item, always present, listed first in the menu — not part of the
shared action list above, since it doesn't act on the document's own data,
it controls the panel's visibility. Right-click has already selected the
row and refreshed the panel's content by the time the menu opens, so
"Detail" only needs to toggle `detailPanelExpanded` — the same call the
toolbar's own `#detail-panel-toggle-btn` already makes
(`saveDetailPanelExpanded(!detailPanelExpanded)`, `dossiary.html` ~line
3089). Its label reflects the current state ("Show Details" when
collapsed, "Hide Details" when expanded), mirroring the toolbar button's
own title-attribute convention. Clicking a *different* row's "Detail"
later doesn't collapse the panel by itself — only this menu item, chosen
explicitly, toggles expand/collapse; switching which document is selected
(via left-click, right-click, or double-click elsewhere) never touches the
panel's own visibility, exactly matching the existing "row click never
auto-expands" rule this app already established for the panel.

### Menu rendering, positioning, and dismissal

Reuses the same floating-menu technique already used three times in this
file (`openDocCollectionMenu`'s own collection picker, the bulk-action
bar's collection menu, the Columns menu): a `<div>` appended to
`document.body`, `position:fixed` (matching the click's viewport
coordinates, not `position:absolute` plus scroll offsets, since a
`contextmenu` event's `clientX`/`clientY` are already viewport-relative),
dismissed by a `document`-level click listener that removes the menu when
the click lands outside it — the same `removeMenu` pattern
`add-to-collection-btn`'s own handler already implements. Visually reuses
the same dark-background/phosphor-green-hover styling already established
for this app's other floating menus, rather than introducing a new visual
language.

No presence in Reports view — there's no table, no rows, nothing to
right-click. Waste bin rows don't need special-casing in the new code at
all: the shared action-building function already reduces a deleted
document down to Restore-only, so the context menu inherits that for
free.

Clicking any item closes the context menu immediately, before that item's
own handler runs — including "Add to Collection," whose own follow-up
collection-picker then opens fresh against a clean page rather than
stacking on top of the still-open context menu. This is a deliberate
difference from the panel's own "Add to Collection" button, which has no
reason to close anything since the panel itself is permanent, not a
transient overlay.

## Out of scope

- Multi-row / bulk actions via right-click — checkboxes and the existing
  bulk-action bar already cover selecting and acting on several documents
  at once; this feature is single-row only.
- A keyboard-triggered context menu (Shift+F10 / the Menu key) — mouse
  right-click only for this pass.
- Any change to the panel's own buttons, to Regenerate preview itself, or
  to any other action's actual behavior once triggered — this spec only
  adds a second entry point to actions that already exist.

## Critical files

- `dossiary.html`:
  - New `contextmenu` listener in the row-wiring pass inside `render()`
    (~line 4385, alongside the existing `click`/`dblclick` listeners) —
    selects the row (same logic as `click`), then builds and shows the
    context menu.
  - `openDetail()` (~lines 4638-4660, 4761-4813) — the action-array/
    handler-wiring logic here gets extracted into a shared function; the
    rest of `openDetail()` (thumbnail, metadata, Fields/People/Tags
    sections) is untouched.
  - New shared action-building function, called by both `openDetail()`
    and the new context-menu builder.
  - New context-menu-building function (rendering + positioning +
    dismissal), following the existing `openDocCollectionMenu`/Columns-
    menu floating-menu pattern.
  - `saveDetailPanelExpanded()` (~line 3089) — consumed, not modified, by
    the new "Detail" menu item.
  - New CSS for the context menu's own item styling, reusing existing
    floating-menu color/hover rules rather than introducing new ones.
  - New i18n keys for "Detail"'s two label states ("Show Details"/"Hide
    Details") across all six supported languages, following this app's
    established `STRINGS`-block convention.

## Testing

A new Playwright test file (or an extension of `tests/test_detail_panel.py`,
whichever reads more naturally once scoped in the implementation plan),
following this repo's established `stub_studio2.js` conventions, covering:
- Right-clicking a row selects/highlights it and refreshes the panel's
  content, the same as a left click, whether or not the panel is
  currently expanded.
- The menu's action set matches the panel's own for a normal document, a
  deleted document (Restore-only), and a document viewed from inside a
  manual collection (Remove from Collection present) versus outside one
  (absent) — mirroring the equivalent existing panel-behavior tests.
- Regenerate preview is never present in the context menu.
- Each menu action, once clicked, does the same thing its panel
  equivalent does (spot-check a representative few — Edit, Archive,
  Delete — rather than re-testing every action's own already-covered
  behavior from scratch).
- "Detail" toggles the panel's expanded/collapsed state without changing
  which document is selected; selecting a different row afterward (by any
  method) does not itself change the panel's visibility.
- The native browser context menu is genuinely suppressed (the custom
  menu appears instead).
- No context menu appears when right-clicking `.select-col`/`.row-edit-col`
  cells, or anywhere in Reports view.
