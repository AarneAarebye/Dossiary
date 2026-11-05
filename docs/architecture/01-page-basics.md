# Dossiary architecture notes: Page basics: HTML skeleton, layout, CSS, footer libraries

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

- **`<!DOCTYPE html>` and `<meta charset="UTF-8">` at the very top are
  load-bearing, not boilerplate** — don't remove them thinking they're
  unnecessary for a file that isn't a "real" full HTML document. Without
  the DOCTYPE, the browser renders in quirks mode, which has an obscure
  legacy behavior where `<table>` elements don't inherit `color` from
  ancestors — this made every table cell render invisible (black text on
  the dark background) until it was diagnosed and fixed. Without the
  charset declaration, special characters (the footer's `©`/`·`, the
  `＋`/`✕` used elsewhere in the UI) rely on browser encoding-sniffing
  instead of a guarantee. Both bugs are the kind that "work fine" in quick
  testing and then fail unpredictably for someone else — keep both lines.
  **`<html translate="no">` and `<meta name="google" content="notranslate">`
  right after them are load-bearing too**: the app translates itself, and
  without them Chrome's own page translator kicks in as soon as the UI
  language changes and machine-translates the page on top of it
  ("DOSSIERS" became "FILES", the language menu's native names became
  "German"/"Spanish").
- **The status line retranslates on a language change via a remembered
  *builder*, not a key** (`setStatusLive(build, kind)`, `lastStatusBuild`;
  `setStatusT(key, params, kind)` is the one-key shorthand). Composite
  messages -- several `t()` results joined, like the Inbox/drag-and-drop
  "Added N documents… N skipped as duplicates…" reports -- pass their own
  builder closure so they retranslate too; they used to go through plain
  `setStatus()` and stayed in the old language. Plain `setStatus()` is now
  only for clearing the line.
- **`.table-wrap` is a deliberate, bounded scroll container** (`overflow:auto`
  + `max-height:calc(100vh - Xpx)`, `X` now nav-style- and footer-dependent —
  see below), not just "the table with horizontal scroll" it looks like at a
  glance. This exists specifically so `thead th`'s `position:sticky; top:0;`
  has something correct to stick to. The original version only had
  `overflow-x:auto` (no `overflow-y` set at all) — which looks harmless, but
  per the CSS Overflow spec, if one axis is anything other than `visible` and
  the other is left as `visible`, the browser silently forces the `visible`
  one to compute as `auto` too. That turned `.table-wrap` into an unintended
  vertical scroll container, which broke the sticky header — it stuck to the
  top of `.table-wrap`'s own (never-scrolling, since the *page* was
  scrolling instead) box rather than the viewport, so it just scrolled away
  like nothing was sticky at all. Setting `overflow-y: visible` explicitly
  does **not** fix this — the spec doesn't allow "one visible, one not" as a
  computed combination, so the browser overrides it back to `auto`
  regardless of what's literally written. The actual fix was to stop
  fighting that rule and lean into it: make `.table-wrap` an intentional,
  bounded scroll container for both axes, so sticky has exactly one clear,
  correctly-scrolling ancestor. **`X` is `414` by default (top-tab nav),
  `374` with `.nav-style-sidebar`, `488` with `.bulk-bar-visible`, and `448`
  with both** (see the "Top-level nav" and "Collections" notes below for the
  nav-style/bulk-bar dimensions) — the bulk-action bar adds its own
  **74px** on desktop (`488 - 414 = 74`, `448 - 374 = 74`) and **102px** on
  mobile (`494 - 392 = 102`, `518 - 416 = 102`) whenever any row is
  selected, regardless of nav style — derivable directly from the constants
  quoted here and in the mobile note below, not a separately-measured
  figure. **These four desktop numbers were bumped a second time (from
  `364`/`370`/`438`/`444` to `410`/`370`/`484`/`444`) by the Amount-range/
  Currency-filter branch**,
  and the relationship between the tabs and sidebar pair is no longer the
  simple "tab strip sits above `.table-wrap`, adding real height; sidebar
  sits beside it, adding none" story the original numbers told. That
  branch's new toolbar controls can push `.toolbar` onto an extra wrapped
  row at certain viewport widths, and which widths trigger that differs
  between the two nav styles (tabs' toolbar spans the full content width;
  sidebar's is squeezed narrower by the sidebar itself, so it wraps at
  different breakpoints) — so each nav style's pair of constants is now
  independently calibrated to its own worst-case width across a
  700-1600px sweep (`getBoundingClientRect()` on `#table-wrap` and
  `footer`, same 60-document seed and methodology as always), not derived
  from the other by a fixed structural offset. It happened that tabs'
  worst case (an extra wrapped row appearing only around 1000-1100px,
  absent at other tabs widths) needed a bigger bump than sidebar's did
  this round, landing tabs' numbers above sidebar's again — but that's
  incidental to where each style's own toolbar happens to wrap this time,
  not a re-assertion of the old structural rule; a future toolbar change
  could easily flip it back. **These four desktop numbers were bumped a
  third time (from `410`/`370`/`484`/`444` to the current
  `414`/`374`/`488`/`448` — a uniform +4px across all four) by the
  reminders feature's own toolbar button**: Task 6's new "🔔 Check
  reminders" button (see the reminder-type custom fields note further
  below) pushed `.toolbar` onto an extra wrapped row at two more
  nav-style-specific desktop widths (~1050-1100px for tabs, ~1280-1350px
  for sidebar), breaking the sticky-header calibration by exactly 2px at
  each — the same class of regression the Amount-range/Currency-filter
  branch caused above, just from one more toolbar button crossing the
  same wrapping threshold. Re-verified the same empirical way as every
  prior bump: worst-case gap for every nav-style/bulk-bar combination went
  from `-3.0px` (a real overlap) back to `+1.0px` (just past the `-2px`
  accepted bound, not a large overshoot). Sidebar mode is left with
  roughly `50px` of
  known, accepted dead space at viewport widths `≥1440px` (up from the
  `46px` this note previously quoted, by the same uniform +4px this
  round's bump added — the underlying worst-case width didn't move, so
  the overshoot at the wide end grew by exactly the same amount as the
  constant itself did) — its own
  worst-case width is narrower than that, so the constant that closes the
  worst case necessarily overshoots at the wide end — deliberately not
  tightened further, per the "accept extra gap, never accept overlap"
  principle repeated throughout this note: the potential savings were
  small relative to the risk of reopening a real overlap at a
  narrower width. **A fourth bump was tried, then reverted, over the
  Scan/Scan Multi toolbar buttons — worth recording in full, since it's
  the one case in this note's history where the "just bump the constants"
  playbook turned out to be the wrong fix.** Those two new buttons (see
  the scanix500 HTTP-bridge spec under `docs/superpowers/`) pushed
  `.toolbar` onto an extra wrapped row across a noticeably wider
  tabs-mode desktop band than any prior bump — `test_footer_pin.py`'s own
  fixed 720px-viewport sweep (800/1000/1100/1280/1440px) reported a real
  `AssertionError` at exactly 1000px (`nav=tabs`, both bulk-bar states,
  gap `-43.0px`, far past the accepted `-2px` bound). A first pass
  applied the same uniform-bump playbook every prior round in this note
  used (`414`/`374`/`488`/`448` → `456`/`416`/`530`/`490`, +42px across
  all four, chasing a finer-swept worst case of `-45.0px`) and it did
  make the suite pass — but a follow-up check using
  `measure_last_row_not_clipped()` (the real, content-based check this
  file's own "in-between width band" section already relies on, rather
  than the coarser `measure()` box-edge proxy) across the *entire*
  700-1600px range, both nav styles, both bulk-bar states, found the real
  last table row was **never** actually clipped behind the footer
  anywhere in that sweep, even against the *original*, never-bumped
  constants. The `-43px`/`-45px` `measure()` was reporting was the same
  "`.table-wrap`'s own generous `70px` padding-bottom absorbs the
  difference" artifact this note's "in-between width band" section
  already documents — just larger this time because the two new buttons
  widened the width band where the toolbar wraps onto extra rows, pushing
  that band out past the `900px` width `test_footer_pin.py`'s own
  `tabs_tight` flag assumed was safely past the artifact zone. **The real
  fix was correcting that stale threshold, not spending table height on a
  CSS bump the actual content never needed.** A fresh 700-1600px sweep
  (20px steps) against the original, un-bumped constants found the
  box-edge proxy's own gap only turns reliably non-negative starting at
  1020px for tabs (sidebar's own transition, 1240px, hadn't moved past
  its existing 1280px threshold at all) — `test_footer_pin.py`'s
  `tabs_tight` flag was moved from `width >= 900` to `width >= 1050`
  (~30px of margin above the measured 1020px transition; `sidebar_tight`
  left unchanged at `1280`), the CSS bump was reverted back to
  `414`/`374`/`488`/`448`, and the full sweep re-verified green against
  *both* changes together — including the 1000px-tabs case that
  originally failed, which the corrected threshold now correctly routes
  through the real-content check instead of the stale proxy. **One
  genuine implementation slip surfaced while reverting the bump, worth
  keeping as institutional memory**: a blind find-and-replace on the
  pixel values (`456`→`414`, `416`→`374`, `530`→`488`, `490`→`448`)
  silently corrupted the *mobile* breakpoint's own, entirely unrelated
  `416px` constant (`nav-style-sidebar`'s mobile `bulkbar=hidden` value,
  never touched by the desktop bump in the first place) purely because it
  happened to share a literal numeric value with one of the desktop
  constants being reverted — caught immediately by a resulting mobile
  320px test failure that had no business appearing from a desktop-only
  change, fixed by hand, and confirmed independently correct once the
  full 67-file suite went green again. The lesson: even a numeric,
  seemingly mechanical revert needs to be scoped to the right selectors,
  not just the right numbers — two CSS rules can share a literal value by
  pure coincidence. `test_collections.py`'s own Scenario 30 calibration
  check and `test_detail_panel.py`'s full suite (the panel reuses these
  same four constants — see its own paragraph further below) were
  re-verified passing against the final, reverted-and-corrected state,
  not just `test_footer_pin.py` alone. **The same thing happened again
  with the "💾 Storage stats" toolbar button, and got the same fix**: it
  widened the wrap band once more, so `test_footer_pin.py` failed at
  1100px (tabs) and `test_collections.py`'s Scenario 30 at 1280px
  (sidebar), both at the proxy's `-48px`. A fresh 700-1600px sweep (20px
  steps, both nav styles, both bulk-bar states) found the real last row
  never clipped anywhere (`<= -4px`), while the proxy only turns reliable
  from 1160px (tabs) / 1380px (sidebar) — so `tabs_tight` moved
  `1050`→`1190`, `sidebar_tight` `1280`→`1410`, Scenario 30 now runs at
  1440x720 instead of 1280x720, and the four CSS constants stayed
  untouched. The "🛠 Tools" dropdown (see its own note below) and the
  header's "⇄ Switch library" link moved five occasional-use buttons off
  the toolbar, which shortened it by a row at
  most desktop widths -- new occasional actions belong in that menu, not
  on the toolbar. Expect this to recur with every new toolbar button; re-run
  that sweep rather than bumping the constants. **Since the
  footer became fixed, permanently-visible chrome (`position: fixed; bottom:
  0;`, see the footer's own note elsewhere in this file), all four numbers
  above also include its rendered height (62px at normal widths)** — the
  footer now consumes part of this budget exactly the way the header/nav/
  toolbar/bulk-bar already did. **At the app's one mobile breakpoint
  (`max-width: 640px`) there are four further `.table-wrap` max-height
  overrides scoped to that media query, and their constants (`392`/`416`/
  `494`/`518`) are NOT simply the four desktop base numbers plus a mobile
  footer-height delta** — an earlier attempt at this calibration made
  exactly that mistake (reusing `302`/`262`/`376`/`336` plus a ~97px footer
  delta, giving `399`/`359`/`473`/`433`) and it was wrong, because it never
  re-measured how much taller the header/toolbar/nav chrome itself renders
  at mobile widths. The correct `392`/`416`/`494`/`518` were measured
  as the actual combined "everything above `.table-wrap`, plus the mobile
  footer's own height" total, directly via `getBoundingClientRect()`, not
  derived from the desktop numbers at all. These four also use the
  **worst-case (320px-width) measurement across the whole 320–640px
  breakpoint range** — both the chrome height and the footer's own height
  shrink as the viewport widens within that range, so a single constant
  picked from the narrowest, tallest-chrome end of the range means growing
  extra room (not overlap) toward the wider end of it — the same "accept
  extra gap, never accept overlap" principle already established above for
  the nav-style/bulk-bar desktop numbers. **Re-measured after the toolbar
  was capped to a single horizontally-scrollable row** (see that fix's own
  note just below): at 640px width (the wide end of the mobile range)
  `.table-wrap` now renders at 408px tall with the tabs nav / 384px tall
  with the sidebar nav (60-doc seed, 800px-tall viewport, both measured via
  `getBoundingClientRect()`) — several rows' worth of real table, not the
  ~58px/one-row sliver an earlier version of this note described against
  the old, pre-toolbar-fix constants. The extra room toward the wide end of
  the range is real and intentional (per the "accept extra gap, never
  accept overlap" principle above), but no longer the "close to unusable"
  problem it once was; the toolbar fix substantially improved this
  specific consequence as a side effect, not just moved the number
  slightly. A real intermediate breakpoint (or a continuous/`clamp()`-based
  constant) would still shrink that extra room further, but it's no longer
  a correctness or usability gap worth tracking as one. Worth keeping in
  proportion, though: the File System Access API this whole app depends on
  (see that note further below) isn't available on iOS Safari or Chrome
  for Android, so this mobile breakpoint mostly matters for someone
  narrowing a desktop browser window, not an actual phone.
  **`.table-wrap` also has its own mobile `padding-bottom` (`32px`), and
  CSS padding can't be compressed below its declared value by `max-height`**
  — a box whose `max-height` computes smaller than its own padding sum
  still renders at (at least) that padding sum, never the smaller
  `max-height` value (confirmed directly: a minimal `overflow:auto;
  padding-bottom:32px; max-height:6px` box renders at `32px`, not `6px`).
  This mattered concretely for the `.bulk-bar-visible` mobile variants, so
  `#main-layout.bulk-bar-visible .table-wrap` and
  `#main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap`'s mobile
  rules also set `padding-bottom: 0` (overriding the general mobile
  `32px`), removing that floor so the box can actually shrink all the way
  down to whatever `max-height` says.
  **The mobile calibration used to have one further, genuinely unavoidable
  wrinkle at the single narrowest, shortest corner (320px width, ~800px-or-
  shorter viewport height, bulk-action bar visible)**: the header+toolbar+
  nav+bulk-bar chrome *by itself*, before `.table-wrap` rendered anything
  at all, used to be taller (measured `723px` tabs / `747px` sidebar at
  320px width) than the room left once the fixed footer reserved its own
  space in a viewport that short, producing a small, structural overlap no
  `.table-wrap` CSS alone could fix. **This corner was closed outright**
  by capping `.toolbar` to a single horizontally-scrollable row
  (`flex-wrap:nowrap` plus `flex-shrink:0` on its children — see the
  `.toolbar` CSS and its own comment in `dossiary.html`'s mobile media
  query) rather than by further `.table-wrap` tuning: `.toolbar` wrapping
  onto many rows at narrow widths, not the bulk-action bar, was the real
  driver of the old worst-case mobile chrome height, and pinning it to one
  row shrank that chrome enough that the corner no longer occurs — verified
  empirically (see below) at `gap=0.0px`, not overlapping, across all four
  nav-style × bulk-bar combinations at 320px width. Worth keeping as
  institutional memory in case a future change to the toolbar's contents
  (e.g. adding enough new buttons that even a single scrollable row grows
  taller than expected) reintroduces tall chrome here and this needs
  revisiting. **The real trade-off of this fix**: at narrow widths, toolbar
  controls are no longer all visible at once the way they were when the
  row wrapped onto several lines — they're still reachable, but only via
  horizontal scroll, with no visible scroll affordance on platforms that
  use overlay scrollbars (e.g. macOS), so a person may not immediately
  realize there's more toolbar to scroll to.
  All of these numbers were verified empirically
  (`getBoundingClientRect()` on `#table-wrap` and `footer`, confirming
  `#table-wrap`'s rendered bottom edge lands exactly at the *footer's* top
  edge in every case where there's actually enough room for it to) — worth
  restating since that same class of check has already caught real drift
  more than once: the *sidebar* nav-style's inherited value silently going
  stale (real value `256`, not the `230` a straight "no extra height, so
  reuse the old number unchanged" assumption would have kept) from
  unrelated header/toolbar changes made well before the nav existed; this
  file's own `295`/`256` figures, quoted in an earlier version of this
  note, having drifted from the code's actual `302`/`262` by the time the
  footer-pinning feature touched this area; and the mobile constants
  described just above being derived from the wrong base entirely on the
  first attempt at this same feature, only caught by re-measuring rather
  than trusting the earlier arithmetic. If you ever adjust the
  header/toolbar/nav/footer layout, recalibrate the same way — verify
  empirically, e.g. checking `getBoundingClientRect()` on `thead th`
  before/after a large internal scroll stays roughly constant, or that
  `#table-wrap`'s own bottom edge lands at the fixed footer's top edge —
  rather than assuming a nearby value, or an old comment's value, is still
  correct.
- **`OPEN_SOURCE_LIBRARIES`** (the array backing the footer's "Libraries"
  link/modal) lists exactly the CDN dependencies this file actually loads
  (`ensureTesseract()`, `ensureJsPdf()`, `ensurePdfJs()`, `ensurePdfLib()`,
  `ensureQrCode()`,
  plus sql.js loaded unconditionally for the database itself) — keep it in sync if a
  dependency is added, removed, or swapped. The license for each was
  verified directly against its own repo's `LICENSE` file when this was
  written (sql.js MIT, Tesseract.js Apache-2.0, jsPDF MIT, pdf.js
  Apache-2.0, pdf-lib MIT -- checked against Hopding/pdf-lib's LICENSE.md,
  qrcode-generator MIT -- checked against kazuhikoarase/qrcode-generator's
  LICENSE), not assumed from general familiarity — if any of these
  ever change their license, or a new dependency gets added, verify the
  same way rather than guessing; this is exactly the kind of detail
  that's easy to get subtly wrong from memory.
