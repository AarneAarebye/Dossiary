# Pin the footer to the viewport bottom

## Context

`dossiary.html`'s `<footer>` (version, language switcher, MIT License,
GitHub link, Libraries/licenses link, User Guide link) currently sits in
normal document flow, immediately after `#main-layout` closes. `.table-wrap`
above it is already a deliberate, bounded scroll container
(`max-height: calc(100vh - Npx)`, four variants depending on nav style and
whether the bulk-action bar is visible — see the architecture notes in
`CLAUDE.md`), so the footer sits at a roughly fixed distance below the fold
regardless of how many documents are in the table.

The user (who has 1,300+ documents in their library) reported the footer is
"hard to reach." Clarified through discussion: it's not that scrolling
fails to reveal it — scroll chaining from the table's own inner scroll
region up to the page does work — it's that with a long table, the page
never *feels* like there's anything below it, so the footer is effectively
forgotten and never used, even though every item in it (language switcher,
User Guide link, Libraries/licenses modal, version/GitHub/copyright) is
something the user reaches for during normal use, not just once at setup.

## Approach

Pin the whole footer to the bottom of the viewport with
`position: fixed; bottom: 0; left: 0; right: 0;`, making it permanent page
chrome — the same role the header/nav/toolbar already play at the top —
rather than something reachable only by scrolling past the table. Content,
links, and the language `<select>` are unchanged; only its positioning
changes.

Two alternatives were considered and rejected:
- **Duplicating** the language switcher/User Guide link into the toolbar or
  nav, leaving the real footer untouched at the bottom: rejected because the
  user uses the *whole* footer (including the version/license/GitHub bits),
  which would still require scrolling, and duplicated controls add clutter.
- **A pinned "expand" button/tab** that reveals the footer as a popover on
  click: rejected as unnecessary complexity — it introduces a new
  interaction pattern this app doesn't otherwise use, for a footer that's
  small enough to just pin outright.

### `.table-wrap` recalibration

Because the footer becomes fixed, permanently-visible chrome, it now
consumes part of the vertical budget the same way the header/nav/toolbar
already do. Each of the four existing `.table-wrap` max-height constants
(`302px` base, `262px` sidebar-nav, `376px` bulk-bar-visible, `336px`
sidebar+bulk-bar-visible — see `dossiary.html`'s CSS, and the
`.table-wrap`-calibration note in `CLAUDE.md`) gets the footer's own
rendered height added to it, following the exact same empirical
verification method that note already establishes: measure via
`getBoundingClientRect()` in a real browser rather than assuming a number,
confirming `#table-wrap`'s bottom edge lands exactly at the fixed footer's
top edge (no overlap, no gap) — not "the old number plus a nearby-looking
constant."

The footer's rendered height must be checked at both the normal desktop
width and the existing `@media (max-width: 640px)` breakpoint (where the
footer's own padding already shrinks, and — with six language options in
the dropdown plus five links — content may wrap to more than one line on
very narrow viewports). If the two heights differ meaningfully, the mobile
breakpoint needs its own `.table-wrap` max-height override; today there is
none, since the footer wasn't part of the calculation at all.

### Stacking order

The footer gets a modest `z-index` — above the table's sticky column
headers (`z-index: 10`) so it always renders above table content if any
transient overlap occurs, but below every dropdown menu and modal
(`z-index: 30` and up) so an open modal continues to fully cover it exactly
as it does today (the modal `.backdrop` is already `position: fixed;
inset: 0`, independent of page scroll position, so this is a) already true
before this change and b) unaffected by the footer's own repositioning).

## Critical files

- `dossiary.html`:
  - `footer{...}` CSS rule — add `position: fixed; bottom: 0; left: 0;
    right: 0;` and a `z-index` between `10` and `30`.
  - The four `.table-wrap` / `#main-layout.nav-style-sidebar .table-wrap` /
    `#main-layout.bulk-bar-visible .table-wrap` /
    `#main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap`
    max-height rules — add the footer's measured height to each existing
    constant.
  - The `@media (max-width: 640px)` footer padding rule — check whether a
    narrower, wrapped footer needs its own `.table-wrap` max-height
    override at that breakpoint.
- `CLAUDE.md` — the `.table-wrap` calibration note needs updating to
  describe the footer as part of the reserved vertical budget now, the same
  way it already documents the header/nav/toolbar/bulk-bar's contributions.

No JavaScript changes are anticipated — the footer's content, its language
`<select>`, and every link/handler on it are unaffected; this is purely a
CSS repositioning plus a recalibration of an already-existing formula.

## Testing

No functional or JS behavior changes are expected, so the existing
57-script Playwright suite should pass unmodified with no test-file edits.

Add empirical verification for the new calibration, following the same
method the existing sticky-header tests already use (see
`tests/test_collections.py`'s Scenario 29-30 large-seed calibration check
referenced in `CLAUDE.md`): seed enough documents that `.table-wrap`'s own
scroll is genuinely binding (`scrollHeight > clientHeight`, asserted before
trusting any position measurement — the exact lesson that check's own
history already documents), then assert via `getBoundingClientRect()` that
`#table-wrap`'s bottom edge lands exactly at the fixed footer's top edge —
across all four nav-style × bulk-bar-visible combinations, and at the
`max-width: 640px` breakpoint if it turns out to need its own override.
Also confirm the footer itself is visible (in the viewport, not clipped)
without any page scroll, both at page load and after scrolling the table's
own inner region to its end.

## Out of scope

- No change to the footer's content, links, or the language switcher's own
  behavior.
- No change to modal/dropdown behavior or their existing stacking order —
  only the footer's own z-index is newly introduced.
- No visual redesign of the footer itself (colors, spacing, wording) —
  positioning only.
