# Toolbar Horizontal Scroll at Narrow Widths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cap `.toolbar` to a single, horizontally-scrollable row at narrow
viewport widths instead of letting it wrap onto many rows, fixing the real
root cause of the documented "320px width + bulk-action bar visible" footer
overlap corner.

**Architecture:** A two-part CSS change inside the existing
`@media (max-width:640px)` block — `flex-wrap:nowrap; overflow-x:auto;` on
`.toolbar` itself, plus `flex-shrink:0` on its direct children (without
this second part, children still compress and their button text wraps
internally instead of the row genuinely overflowing — see Task 1's own
note on this). This shrinks mobile chrome height enough that the four
mobile `.table-wrap` max-height constants and the accepted overlap
exception in `CLAUDE.md`/`tests/test_footer_pin.py` all get recalibrated
to reflect the corner being closed.

**Tech Stack:** Plain CSS (no new dependencies), Playwright for the
existing regression test (`tests/test_footer_pin.py`, using
`tests/stub_studio2.js`).

## Global Constraints

- Every toolbar control (search box, all filters, "Show archived," every
  button, the Columns menu) must remain reachable via horizontal scroll at
  narrow widths — nothing may become permanently hidden or unreachable.
- `.table-wrap`'s recalibration must use empirically measured pixel
  values (not guesses), per this repo's own established convention (see
  the `.table-wrap` note in `CLAUDE.md`).
- No changes to the toolbar's content, controls, or their behavior —
  layout/scrolling only.
- The existing 58-script Playwright suite must all still pass.

---

### Task 1: Cap the toolbar to one scrollable row and recalibrate mobile `.table-wrap`

**Files:**
- Modify: `dossiary.html:419-423` (the `@media (max-width:640px)` block's
  `.toolbar` and `.table-wrap` rules)
- Modify: `dossiary.html:190-270`-ish (the in-file CSS comment above
  `.table-wrap`'s desktop rules — the same comment block already updated
  twice during the footer-pinning work)
- Modify: `CLAUDE.md` (the `.table-wrap` calibration note)

**Interfaces:**
- Produces: `.toolbar{flex-wrap:nowrap; overflow-x:auto;}` and
  `.toolbar > *{flex-shrink:0;}` inside the mobile media query; four
  recalibrated mobile `.table-wrap` max-height constants (`392px`/
  `416px`/`494px`/`518px` in place of the current `718px`/`742px`/`820px`/
  `844px`). Task 2's test updates rely on these exact new values and on
  the corner being confirmed closed.

The exact pixel constants below were measured empirically in a real
Chromium browser before this plan was written, using the same
`getBoundingClientRect()` method this codebase's own `.table-wrap`
calibration note already establishes, with the proposed CSS fix injected
via a style tag (not yet applied to the file) — they are not estimates.

- [ ] **Step 1: Apply the toolbar CSS fix**

Edit `dossiary.html`, replacing the first line of the mobile media query:

```css
  @media (max-width:640px){
    header{ padding:20px 16px 16px; } .toolbar{ padding:14px 16px; } .table-wrap{ padding:0 16px 32px; max-height:calc(100vh - 718px); }
```

with:

```css
  @media (max-width:640px){
    header{ padding:20px 16px 16px; } .toolbar{ padding:14px 16px; flex-wrap:nowrap; overflow-x:auto; } .table-wrap{ padding:0 16px 32px; max-height:calc(100vh - 392px); }
    .toolbar > *{ flex-shrink:0; }
```

**Why `flex-shrink:0` is required, not optional**: `flex-wrap:nowrap` alone
does NOT stop the toolbar's children from shrinking below their natural
width — flex items default to `flex-shrink:1`, so the browser compresses
them to fit instead of letting the row genuinely overflow. Buttons like
"⚙ Manage fields" and "📥 Check inbox" don't have `white-space:nowrap` set,
so a compressed button's text wraps onto two lines internally, and the
toolbar ends up just as tall as before (measured 97px, barely better than
doing nothing) even though `overflow-x:auto` and `flex-wrap:nowrap` are
both correctly applied. `flex-shrink:0` forces every child to keep its
natural width, so the row genuinely overflows horizontally (scrollable)
instead of squeezing vertically — measured toolbar height drops to 69px
with both rules together, versus 97px with `flex-wrap`/`overflow-x` alone.

- [ ] **Step 2: Recalibrate the remaining three mobile `.table-wrap` constants**

Edit `dossiary.html`, replacing:

```css
    #main-layout.nav-style-sidebar .table-wrap{ max-height:calc(100vh - 742px); }
    #main-layout.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 820px); padding-bottom:0; }
    #main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 844px); padding-bottom:0; }
```

with:

```css
    #main-layout.nav-style-sidebar .table-wrap{ max-height:calc(100vh - 416px); }
    #main-layout.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 494px); padding-bottom:0; }
    #main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 518px); padding-bottom:0; }
```

Each new constant is `chrome-top + footer-height` measured at 320px width
(the same worst-case-across-320-640px-range derivation the existing
mobile constants already use) — `392` (tabs, idle), `416` (sidebar,
idle), `494` (tabs, bulk-bar visible), `518` (sidebar, bulk-bar visible).
The `padding-bottom:0` overrides on the two bulk-bar-visible rules stay
unchanged — they're still correct (removing the mobile `32px`
padding-bottom floor), just no longer strictly load-bearing now that
there's much more slack; leave them as-is rather than reverting them,
since removing them would add risk for no benefit.

- [ ] **Step 3: Verify empirically — the corner should now be fully closed**

Run this from `tests/`:

```bash
cd tests && python3 -c "
import asyncio, json, os
from playwright.async_api import async_playwright

APP_PATH = os.path.abspath('../dossiary.html')

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body='/* stubbed */', content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    stub_js = open('stub_studio2.js').read()
    await page.add_init_script(stub_js)

async def check(width, nav_style, bulkbar):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': width, 'height': 800})
        await route_stub(page)
        await page.goto(f'file://{APP_PATH}')
        await page.wait_for_timeout(200)
        docs = [{'id': i, 'title': f'Doc {i}', 'category':'Travel','document_type':'Receipt','date':f'2026-03-{(i%28)+1:02d}T00:00:00+00:00','notes':None,'ocr_text':None,'ocr_language':None,'file_path':f'files/{i}_a.pdf','original_file_path':None,'created_at':'2026-03-01T00:00:00+00:00','source':'captured','source_legacy_id':None,'archived':0,'needs_review':0,'deleted':0} for i in range(1,61)]
        SEED = {'documents': docs, 'tags': [], 'document_tags': [], 'settings': [{'key':'nav_style','value':nav_style}]}
        await page.evaluate(f'window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});')
        await page.click('#open-btn')
        await page.wait_for_timeout(400)
        if bulkbar:
            await page.check('tr[data-id=\"1\"] .row-select-checkbox')
            await page.wait_for_timeout(150)
        info = await page.evaluate('''
            () => {
                const tw = document.querySelector('#table-wrap').getBoundingClientRect();
                const f = document.querySelector('footer').getBoundingClientRect();
                return { twBottom: tw.bottom, fTop: f.top };
            }
        ''')
        gap = info['fTop'] - info['twBottom']
        print(f'width={width} nav={nav_style} bulkbar={bulkbar}: gap={gap:.1f}px', 'OVERLAP!!' if gap < -2 else 'ok')
        await browser.close()

for w in [320, 375, 640]:
    check_args = [(w, 'tabs', False), (w, 'sidebar', False), (w, 'tabs', True), (w, 'sidebar', True)]
    for args in check_args:
        asyncio.run(check(*args))
"
```

Expected: every line prints `ok` (`gap >= -2px`), including the
previously-overlapping `320px width, bulk-bar visible` lines for both nav
styles — confirm these now show `gap` at or near `0.0px` (tight, since
320px is the calibration point), not a negative number. If any line still
shows `OVERLAP!!`, do not proceed to Task 2 — something in the
measurement or the applied CSS doesn't match what this plan assumed, and
needs investigating before touching the docs/tests that assume the corner
is closed.

- [ ] **Step 4: Confirm `#reports-view`'s mobile padding still clears the footer (no change expected)**

`#reports-view`'s own required clearance (`dossiary.html:443`,
`padding:0 16px 140px;`) was always derived from the footer's own height
plus a margin — it's a page-flow element, not part of the chrome stack
`.table-wrap` measures, so it shouldn't need to change just because the
toolbar above it got shorter. Confirm this rather than assuming it: run
`tests/test_reports.py` (or open the Reports view manually at 320×800
with a 60-document seed, scroll to the end, and confirm the Grand total
row isn't clipped behind the footer). If it turns out `140px` needs
adjusting for some reason not anticipated here, adjust it and note why in
your task report — don't silently leave a real gap uncovered.

- [ ] **Step 5: Manually confirm every toolbar control is reachable via horizontal scroll**

In a real browser (or via a Playwright script), at 320px, 375px, and
640px widths, confirm: the search box, all three built-in filters
(Category/Type/People), "Show archived," and every button (Manage
fields, Manage collections, Check inbox, Add document, Switch library,
Columns) are all present, not clipped, and reachable by scrolling
`.toolbar` horizontally (e.g. `element.scrollIntoView()` or dragging the
scrollbar) — none should be permanently hidden or inaccessible.

- [ ] **Step 6: Update the in-file CSS comment above `.table-wrap`'s desktop rules**

This comment (already updated twice during the footer-pinning work) still
describes the mobile constants as `718`/`742`/`820`/`844` and describes
the 320px+bulk-bar corner as a "genuinely unavoidable wrinkle." Update it
to state the new `392`/`416`/`494`/`518` constants, and note that the
toolbar's own narrow-width wrapping (not the bulk-action bar) was the
real driver of the old worst-case numbers — now that `.toolbar` is capped
to one row via `flex-wrap:nowrap`/`flex-shrink:0`, chrome height no
longer varies nearly as dramatically across the 320-640px range. Leave
the general "worst-case-320px-width, accept extra gap not overlap"
derivation philosophy in place — it's still the correct approach, just
operating on much smaller numbers now.

- [ ] **Step 7: Update `CLAUDE.md`'s `.table-wrap` calibration note**

Find and update the same figures in `CLAUDE.md`'s `.table-wrap` note:
replace `718`/`742`/`820`/`844` with `392`/`416`/`494`/`518` everywhere
they appear, and **remove** the "One further, genuinely unavoidable
wrinkle... 320px width, ~800px-or-shorter viewport height, bulk-action
bar visible" paragraph (and its residual-overlap numbers, `723px`/`747px`
chrome, `-20px`/`-44px` overlap) — Step 3's verification should confirm
this limitation no longer exists, so the note describing it as permanent
and unfixable would now be actively wrong, which this file's own stated
standard treats as worse than simply not mentioning a resolved issue.
Add a brief note instead: this corner was closed by capping `.toolbar` to
one row (see the toolbar's own CSS/comment), not by further `.table-wrap`
tuning — worth keeping as institutional memory in case a future change to
the toolbar's contents reintroduces tall wrapping and this needs
revisiting.

- [ ] **Step 8: Commit**

```bash
git add dossiary.html CLAUDE.md
git commit -m "$(cat <<'EOF'
Cap the toolbar to one scrollable row at narrow widths

.toolbar wrapping onto many rows at narrow viewport widths (395px tall
at 320px width) was the real driver behind the mobile .table-wrap
calibration's worst-case numbers -- including the documented,
previously-unfixable 320px+bulk-bar footer overlap corner. Capping it
to a single horizontally-scrollable row (flex-wrap:nowrap plus
flex-shrink:0 on its children, without which children just compress
and wrap their own text instead of the row genuinely overflowing)
shrinks mobile chrome enough to close that corner outright, so the
four mobile .table-wrap constants drop from 718/742/820/844 to
392/416/494/518.
EOF
)"
```

---

### Task 2: Tighten the regression test's bounded-overlap exceptions and add toolbar-reachability coverage

**Files:**
- Modify: `tests/test_footer_pin.py`

**Interfaces:**
- Consumes: Task 1's new mobile `.table-wrap` constants (`392px`/`416px`/
  `494px`/`518px`) and the confirmation that the 320px+bulk-bar corner is
  fully closed.

- [ ] **Step 1: Collapse the two bounded-overlap exceptions back to the tight check**

Edit `tests/test_footer_pin.py`, replacing:

```python
        await measure(page2, "mobile 320x800, nav=tabs, bulkbar=VISIBLE (known bounded overlap)", min_gap=-30)
```

with:

```python
        await measure(page2, "mobile 320x800, nav=tabs, bulkbar=VISIBLE", min_gap=-2)
```

and replacing:

```python
        await measure(page2, "mobile 320x800, nav=sidebar, bulkbar=VISIBLE (known bounded overlap)", min_gap=-55)
```

with:

```python
        await measure(page2, "mobile 320x800, nav=sidebar, bulkbar=VISIBLE", min_gap=-2)
```

These two scenarios now use the exact same `min_gap=-2` tolerance every
other scenario in this file already uses — the special-cased bounded
exceptions existed only because of the now-closed corner, and keeping
them around with a looser bound than necessary would silently mask a
real regression if `.table-wrap`'s calibration ever drifted back toward
overlapping again.

- [ ] **Step 2: Add a toolbar-reachability scenario**

Add a new scenario to `tests/test_footer_pin.py`, after the existing
mobile scenarios (find the end of the `async with async_playwright() as
p:` block covering the 320×800 mobile viewport, right before its
`await browser2.close()` — or add a new `async with` block after it,
matching this file's existing pattern of one browser context per group
of related viewport checks):

```python
        # === Toolbar reachability at the narrowest supported width: every
        # control must still be reachable via horizontal scroll, not silently
        # clipped or unreachable, now that .toolbar no longer wraps onto many
        # rows at narrow widths. ===
        toolbar_info = await page2.evaluate("""
            () => {
                const tb = document.querySelector('.toolbar');
                const ids = ['search', 'category-filter', 'type-filter', 'person-filter',
                             'show-archived-toggle', 'manage-fields-btn', 'manage-collections-btn',
                             'inbox-check-btn', 'add-btn', 'reload-btn', 'columns-btn'];
                const missing = ids.filter(id => !document.getElementById(id));
                return {
                    scrollWidth: tb.scrollWidth,
                    clientWidth: tb.clientWidth,
                    overflowsHorizontally: tb.scrollWidth > tb.clientWidth + 1,
                    missingControls: missing,
                };
            }
        """)
        print(f"[toolbar reachability, 320px width] all expected controls present (none missing): {toolbar_info['missingControls'] == []}")
        print(f"[toolbar reachability, 320px width] toolbar genuinely overflows horizontally (scrollWidth={toolbar_info['scrollWidth']} > clientWidth={toolbar_info['clientWidth']}): {toolbar_info['overflowsHorizontally']}")
```

This confirms two things the CSS fix depends on: every control that was
there before is still present in the DOM (nothing got hidden), and the
toolbar's `scrollWidth` genuinely exceeds its `clientWidth` — proof the
row is overflowing horizontally (reachable via scroll) rather than having
silently shrunk its children to fit (the exact bug Task 1's Step 1 found
and fixed with `flex-shrink:0`; without that rule, `scrollWidth` and
`clientWidth` would be much closer together even though the row still
looks "capped").

- [ ] **Step 3: Run the test file and confirm everything passes**

Run: `cd tests && python3 test_footer_pin.py`
Expected: all scenarios print PASS/True, no `OVERLAP` or overlap-related
failures, the two new toolbar-reachability lines both print `True`, exit
code 0.

- [ ] **Step 4: Run the full suite to confirm nothing else regressed**

Run:

```bash
cd tests && python3 -c "
import subprocess, glob
failed = []
files = sorted(glob.glob('test_*.py'))
for f in files:
    p = subprocess.run(['python3', f], capture_output=True, text=True, timeout=180)
    if p.returncode != 0 or 'Traceback' in p.stdout or 'Traceback' in p.stderr:
        failed.append(f)
        print(f'FAILED: {f}')
print(f'TOTAL: {len(files)}  FAILED: {failed}')
"
```

Expected: `TOTAL: 58  FAILED: []` (this task modifies an existing test
file, it doesn't add a new one, so the total count doesn't change).

- [ ] **Step 5: Commit**

```bash
git add tests/test_footer_pin.py
git commit -m "$(cat <<'EOF'
Tighten test_footer_pin.py now that the mobile bulk-bar corner is closed

The two 320px+bulk-bar-visible scenarios used a loosened min_gap
(-30/-55) to accept the documented, then-unfixable overlap. With the
toolbar capped to one row (see the prior commit), that corner closes
outright, so both scenarios now use the same tight -2px tolerance as
everything else in this file -- a looser bound left in place would
silently mask a real future regression. Also adds a scenario confirming
every toolbar control is still present and the row genuinely overflows
horizontally (scrollWidth > clientWidth) rather than having silently
shrunk its children to fit.
EOF
)"
```
