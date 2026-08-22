# Panel follow-up: row interactions and defaults

## Context

The persistent detail panel (see
`docs/superpowers/specs/2026-08-21-persistent-detail-panel-design.md`) just
merged to `main`. Using it surfaced four small redundancies worth cleaning
up now that the panel — not a modal — is the permanent home for a
document's actions:

1. The row-level hover "✎" Edit shortcut (`.row-edit-btn`) duplicates the
   panel's own Edit button once the panel is reliably reachable.
2. Clicking a row only selects it today; there's no direct way to open
   the underlying file from the table itself.
3. Once opening a file from the table exists, the panel's own "Open
   file" button may be redundant.
4. The panel currently defaults to **collapsed** — deliberately, to
   protect table width — but with less duplicated chrome, defaulting to
   **expanded** now reads as more complete than defaulting to hidden.

This spec resolves all four together, since #1 and #4 interact directly
(removing the row shortcut only makes sense once the panel — carrying the
same action — is reliably visible), and #2/#3 turned out to interact too
(see Approach).

## Approach

### Row interaction: single click unchanged, double-click opens the file

Single click keeps its exact current behavior — select the row, apply
`.row-selected`, refresh `#detail-panel-body` via `openDetail(id)`. Nothing
about that changes.

A new `dblclick` listener on each `<tr>` opens that document's file, reusing
the exact logic the panel's own "Open file" button already uses
(`resolveFileHandle(d.file_path)` → `fh.getFile()` →
`window.open(URL.createObjectURL(file), '_blank')`), guarded the same way
(`if(d.file_path)`). Browsers fire two ordinary `click` events before a
`dblclick`, so by the time the double-click fires, the existing single-click
handler has already selected the row and refreshed the panel twice over —
the `dblclick` handler only needs to add the file-open step, not repeat
selection. A document with no `file_path` (e.g. an Inbox-imported document
never given a file) simply does nothing extra on double-click — no error,
no dialog, the same silent no-op the panel's own conditionally-rendered
"Open file" button already represents for such a document.

This resolved a real design question during brainstorming: an earlier
option considered making *single* click open the file, but that collapses
"quickly select rows to compare metadata" and "open a file" into one
ambiguous gesture. Double-click is the same convention file managers
already use (single selects, double opens) and keeps both actions clean.

### "Open file" stays in the panel

Double-click isn't a discoverable gesture by itself — someone who's never
tried it has no reason to know it exists. The panel's "Open file" (and
"Open original file") buttons remain exactly as they are today: the
reliable, visible way to open a file, with double-click as a shortcut for
anyone who already knows it. No change to that button's code at all.

### `.row-edit-btn` removed at normal widths, kept only below the mobile breakpoint

At normal widths, the button becomes fully redundant now that the panel
defaults to expanded (see below) and Edit is one click away in it — so it
disappears there. It's kept **only** inside the existing
`@media (max-width:640px)` block, because that's the one situation where
the panel is structurally unreachable: `#main-layout.detail-panel-expanded
.detail-panel{ display:none; }` inside that same media query force-hides
the panel unconditionally, regardless of the toggle — so without a
fallback, Edit would be completely unreachable from the table below that
width. (Per the original panel spec, this breakpoint mostly matters for
someone narrowing a desktop browser window, not an actual phone — the File
System Access API this whole app depends on isn't available on mobile
browsers — but the fallback still needs to exist for that case.)

Concretely: `.row-edit-btn`'s existing `opacity:0` / hover-reveal rules
move from the base stylesheet into the `@media (max-width:640px)` block,
with a new base rule (`.row-edit-btn{ display:none; }`, outside the media
query) hiding it entirely above that width. Its column
(`.row-edit-col`, the `<th>`/`<td>` pair) also collapses to zero width
above 640px for the same reason (`.row-edit-col{ display:none; }` outside
the media query, restored inside it) — reclaiming that column's width is a
small, free bonus now that the button itself is gone there, and this
column was never part of the `visibleColumns`/Columns-menu system to begin
with (per CLAUDE.md's own note: "never hideable via the Columns menu"), so
this is a plain CSS-only toggle, not a new mechanism.

No JS/markup changes needed beyond this — the button's row-level rendering
(`d.deleted ? '' : ...`) and click-wiring stay exactly as they are; only
its *visibility* becomes viewport-width-dependent, layered on top of the
existing deleted-document exclusion.

### Panel defaults to expanded

`loadDetailPanelExpanded()`'s no-setting-row fallback flips from `false` to
`true`:

```js
detailPanelExpanded = rows.length === 0 || rows[0][0] !== '0';
```

(An explicit `'0'` row still means collapsed — someone who deliberately
toggles it closed keeps that preference across reopens, exactly as
today — only the *no-preference-saved-at-all* case changes.) Every other
mechanic — the `settings`-table persistence pattern, the toolbar toggle,
the mobile force-collapse override, and Reports view hiding the panel
entirely — is unchanged.

This is a pure default flip with no real migration concern: the panel
feature has not yet been pushed past this local `main` branch, so there is
no shipped library anywhere with a persisted `detail_panel_expanded` row to
reconcile.

## Out of scope

- Any change to what the panel *shows* or its action buttons beyond
  keeping "Open file"/"Open original file" as-is.
- Any change to `.row-edit-btn`'s own behavior once clicked (still jumps
  straight to `openEditForm()`, skipping the panel/selection step) — only
  its width-gated visibility changes.
- Resizing, keyboard shortcuts, or any other panel mechanic not already
  covered by the original panel spec.

## Critical files

- `dossiary.html`:
  - New `dblclick` listener alongside the existing `click` listener in the
    row-wiring pass inside `render()` (~line 4383), opening `d.file_path`
    the same way `open-file-btn`'s handler does (~line 4721).
  - `.row-edit-btn`/`.row-edit-col` CSS (~lines 322-328): base rules
    change to `display:none`; the existing hover-reveal opacity rules
    move inside `@media (max-width:640px)` (~line 477).
  - `loadDetailPanelExpanded()` (~line 3081): flip the no-row fallback
    from `false` to `true`.
  - CLAUDE.md: update the "detail view is a persistent side panel"
    architecture note to describe the new default, the double-click
    file-open behavior, and the width-gated row-edit-btn — this repo's
    established documentation discipline treats every non-obvious
    behavior change as needing its own note.

## Testing

Extend the existing Playwright suite (`tests/test_detail_panel.py` and
`tests/test_row_edit_shortcut.py`, following this repo's established
per-file conventions):

- Double-clicking a row with a file opens it (assert a new tab/window
  request was made, mirroring however the existing "Open file" button
  scenario already asserts this).
- Double-clicking a row with no `file_path` is a silent no-op — no error,
  no new tab.
- Single click still only selects/highlights/refreshes the panel, with no
  file-open side effect (regression guard against the double-click
  handler accidentally firing on a single click).
- `.row-edit-btn` is absent at a normal desktop viewport width, for a
  non-deleted document, where it was previously present.
- `.row-edit-btn` is still present and clickable at a viewport width under
  640px, for the same document.
- The panel starts expanded by default when no `detail_panel_expanded`
  setting row exists; still starts collapsed when one exists with value
  `'0'`; still starts expanded when one exists with value `'1'`.
