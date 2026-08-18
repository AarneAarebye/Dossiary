# Make the toolbar horizontally scrollable at narrow widths

## Context

Investigating the documented, accepted "320px width + bulk-action bar
visible + short viewport" overlap corner (see `CLAUDE.md`'s `.table-wrap`
calibration note) found that its real root cause isn't the bulk-action bar
— that only contributes 88px. It's `.toolbar` itself: at 320px viewport
width, `.toolbar`'s `flex-wrap: wrap` stacks its ~9 controls (search box,
Category/Type/Person filters, "Show archived," Manage fields/collections,
Check inbox, Add document, Switch library, Columns) across many rows,
measuring **395px tall** — more than half of the total chrome height above
the fixed footer. This was already true before the footer was pinned; it
only became a visible overlap once something got permanently anchored to
the bottom of the viewport for that chrome to run into.

The current mobile `.table-wrap` calibration (see that same `CLAUDE.md`
note) works around this by using the worst-case measurement across the
whole 320-640px mobile range as its constant, and by explicitly accepting
a small, documented, regression-guarded overlap at the single worst corner
(320px + bulk-bar visible) rather than pretending it doesn't exist. This
spec addresses the actual root cause instead, which should let that
accepted-limitation language be removed rather than just managed.

## Approach

Change `.toolbar`'s narrow-width behavior from wrapping onto many rows to
staying a single, horizontally-scrollable row:

```css
@media (max-width:640px){
  .toolbar{ flex-wrap:nowrap; overflow-x:auto; }
}
```

This caps `.toolbar`'s height to roughly one row's worth of controls at
any width from 320px up to the 640px breakpoint boundary, instead of
395px at the narrow end. Every control stays reachable — swipe/scroll
horizontally to reach ones off-screen — rather than being hidden or
moved into a new disclosure UI, which was explicitly ruled out as more
than this fix's scope calls for.

Two other alternatives were considered and rejected during brainstorming:
collapsing secondary controls behind a "Filters & more" disclosure
(meaningfully more code — new markup, toggle state, new i18n strings —
for a problem that's really just "the row is too tall"), and hiding the
least-essential controls entirely below a width threshold (loses real
functionality rather than just reflowing it).

### Recalibration this triggers

The four existing mobile `.table-wrap` max-height constants (`718`/`742`/
`820`/`844`) and `#reports-view`'s mobile bottom padding (`140px`) were
both derived treating the old tall, wrapping toolbar as the width range's
worst case. Once the toolbar is capped to one row, actual chrome height
should stop varying much with width at all (a single-row toolbar doesn't
grow much just because the viewport narrowed) — likely collapsing the
"320px is always the worst case across the range" derivation into
something simpler, though this needs to be confirmed empirically rather
than assumed. All four `.table-wrap` constants and `#reports-view`'s
mobile padding get re-measured the same way the existing calibration was
originally derived (`getBoundingClientRect()` on the real elements in a
real browser, per the method already established and repeatedly restated
in `CLAUDE.md`'s `.table-wrap` note) and updated to whatever the new,
correct values are — not assumed from the old numbers.

If re-measurement confirms the 320px+bulk-bar overlap corner is now
genuinely closed (0px gap, not just a smaller one), `CLAUDE.md`'s
`.table-wrap` note gets its "genuinely unavoidable wrinkle" section
removed (it will no longer be true), and `tests/test_footer_pin.py`'s two
bounded-overlap exceptions (`min_gap=-30` for 320px+tabs+bulkbar,
`min_gap=-55` for 320px+sidebar+bulkbar) collapse back to the same tight
`min_gap=-2` every other scenario in that file already uses. If
re-measurement finds the corner is smaller but not fully closed, the
bounded exceptions stay, updated to the new, smaller measured values,
and `CLAUDE.md`'s note is updated to describe the new numbers rather than
removed outright — the fix should be evaluated honestly against what it
actually achieves, not assumed to fully solve the problem before
verifying.

## Critical files

- `dossiary.html`:
  - `.toolbar`'s existing `@media (max-width:640px)` rule — add the
    `flex-wrap:nowrap; overflow-x:auto;` override.
  - The four `.table-wrap` mobile max-height constants and
    `#reports-view`'s mobile padding, inside the same media query —
    re-measured and updated.
  - The in-file CSS comment above `.table-wrap`'s desktop rules (already
    updated once during the footer-pinning work to mention the mobile
    overrides) — update again if the derivation story changes.
- `CLAUDE.md` — the `.table-wrap` calibration note: update the mobile
  constants, and either remove or update the "genuinely unavoidable
  wrinkle" section describing the 320px+bulk-bar corner depending on
  what re-measurement finds.
- `tests/test_footer_pin.py` — the two bounded-overlap exceptions,
  updated or removed depending on what re-measurement finds.

## Verification

- Re-measure `.table-wrap`'s chrome height (header+nav+toolbar+bulk-bar)
  across the 320-640px range, both nav styles, bulk bar hidden and
  visible, the same way the existing calibration was derived — confirm
  whether chrome height is now roughly constant across that range (as
  expected) or still varies meaningfully, and derive the correct
  constants from what's actually measured.
- Confirm the 320px+bulk-bar corner's actual overlap (0px, or a smaller
  but nonzero number) via direct measurement, not assumption.
- In a real browser, confirm every toolbar control (search, all filters,
  Show archived, every button, Columns menu) is still reachable via
  horizontal scroll at 320px, 375px, and 640px widths, and that nothing
  is silently clipped or unreachable.
- Run the existing 58-script suite to confirm no regressions, and update
  `tests/test_footer_pin.py`'s assertions to match whatever the
  corrected calibration turns out to be.
- Spot-check that no existing test assumes `.toolbar`'s controls wrap
  onto multiple visible rows at a narrow viewport width (a quick grep for
  narrow-viewport toolbar interactions in the test suite) before
  trusting the change doesn't break anything already covered.
