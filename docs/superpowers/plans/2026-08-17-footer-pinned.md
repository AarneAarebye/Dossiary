# Pin the Footer to the Viewport Bottom Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `dossiary.html`'s footer (language switcher, User Guide,
Libraries, version/license/GitHub links) permanently visible at the bottom
of the viewport instead of reachable only by scrolling past the document
table, without ever overlapping the table.

**Architecture:** `<footer>` switches from normal document flow to
`position: fixed; bottom: 0;`, becoming permanent page chrome the same way
the header/nav/toolbar already are at the top. `.table-wrap`'s existing
`max-height: calc(100vh - Npx)` formula (already nav-style- and
bulk-bar-visibility-dependent) gets the footer's own empirically measured
height added to each of its four constants, plus a new mobile-breakpoint
override, so the table's own scroll region always ends exactly at the
footer's top edge.

**Tech Stack:** Plain CSS (no new dependencies), Playwright for the
regression test (existing `tests/stub_studio2.js` fake-browser-API stub).

## Global Constraints

- Single-file app — no new files except the one new test file; no build
  step, no CDN dependency changes.
- No changes to the footer's content, links, or the language `<select>`'s
  own behavior — positioning only.
- No changes to modal/dropdown stacking order — the footer's `z-index`
  must sit above `thead th`'s sticky header (`z-index: 10`) and below every
  dropdown menu and modal (`z-index: 30` and up), so an open modal or
  dropdown continues to render on top of the footer exactly as today.
- `.table-wrap`'s recalibration must use empirically measured pixel values
  (not guesses), per this repo's own established convention for this exact
  kind of calibration (see the `.table-wrap` note in `CLAUDE.md`).
- The existing 57-script Playwright suite must still pass unmodified after
  these changes (no functional/JS behavior is changing, only CSS
  positioning).

---

### Task 1: Pin the footer and recalibrate `.table-wrap`

**Files:**
- Modify: `dossiary.html:414-417` (the `footer{...}` CSS rule)
- Modify: `dossiary.html:217-220` (the four `.table-wrap` max-height rules)
- Modify: `dossiary.html:422-436` (the `@media (max-width:640px){...}`
  block — add mobile-breakpoint `.table-wrap` max-height overrides)
- Modify: `CLAUDE.md` (the `.table-wrap` calibration note, currently around
  lines 172-206)

**Interfaces:**
- Produces: a fixed-position `footer` element with `z-index: 15` and an
  explicit `background: var(--ink)`; four recalibrated `.table-wrap`
  max-height constants (`364px`/`324px`/`438px`/`398px` in place of the
  current `302px`/`262px`/`376px`/`336px`); four new mobile-breakpoint
  `.table-wrap` max-height overrides (`399px`/`359px`/`473px`/`433px`).
  Task 2's test asserts against these exact selectors and values.

The exact pixel constants below were measured empirically in a real
Chromium browser before this plan was written, using the same
`getBoundingClientRect()` method this codebase's own `.table-wrap`
calibration note already establishes — they are not estimates. At a
1280×720 viewport (the same viewport the existing sticky-header
calibration test in `tests/test_collections.py` uses), the footer's
rendered height is **62px**. At the app's one existing mobile breakpoint
(`max-width: 640px`), footer content wraps across more than one line, and
its height varies with the exact width — 71px at 600-640px width, up to
**97px** at 320px width (a common minimum phone width, and the narrowest
width measured). Using the *largest* observed mobile height (97px) as the
mobile constant is deliberate: undershooting would let the footer overlap
scrolled table content at narrower widths (a real bug), while
overshooting only leaves a few extra pixels of harmless blank space above
the footer at the wider end of the mobile range (600-640px) — the safe
direction to round in.

- [ ] **Step 1: Pin the footer with `position: fixed`**

Edit `dossiary.html`, replacing:

```css
  footer{
    padding: 18px 32px 22px; border-top: 1px solid var(--line);
    font-family: var(--font-mono); font-size: 11px; color: var(--text-dim); text-align: center;
  }
```

with:

```css
  footer{
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 15;
    padding: 18px 32px 22px; border-top: 1px solid var(--line);
    font-family: var(--font-mono); font-size: 11px; color: var(--text-dim); text-align: center;
    background: var(--ink);
  }
```

The explicit `background: var(--ink)` is required now that the footer can
have scrolled table rows underneath it (it never could before, since it
always sat below all table content in the page's normal flow) — this
mirrors `thead th`'s own `position:sticky; ...; background:var(--ink);`
rule a few lines earlier in the file, which solves the identical problem
for the sticky column headers.

The `z-index: 15` sits above `thead th`'s sticky header (`z-index: 10`,
so the footer never renders underneath a table row that happens to be
mid-scroll) and below every dropdown menu (`z-index: 30`+) and modal
`.backdrop` (`z-index: 50`), so opening a dropdown or modal still covers
the footer exactly as it does today.

- [ ] **Step 2: Recalibrate the desktop `.table-wrap` max-height constants**

Edit `dossiary.html`, replacing:

```css
  .table-wrap{ padding:0 32px 40px; overflow:auto; max-height:calc(100vh - 302px); }
  #main-layout.nav-style-sidebar .table-wrap{ max-height:calc(100vh - 262px); }
  #main-layout.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 376px); }
  #main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 336px); }
```

with:

```css
  .table-wrap{ padding:0 32px 40px; overflow:auto; max-height:calc(100vh - 364px); }
  #main-layout.nav-style-sidebar .table-wrap{ max-height:calc(100vh - 324px); }
  #main-layout.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 438px); }
  #main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 398px); }
```

Each constant is the existing value plus the footer's measured desktop
height (62px): `302+62=364`, `262+62=324`, `376+62=438`, `336+62=398`.

- [ ] **Step 3: Add mobile-breakpoint `.table-wrap` max-height overrides**

Edit `dossiary.html`, replacing the mobile media query's first line:

```css
  @media (max-width:640px){
    header{ padding:20px 16px 16px; } .toolbar{ padding:14px 16px; } .table-wrap{ padding:0 16px 32px; }
    .stats{ display:none; } .modal{ padding:20px 16px 22px; } .field-row{ flex-direction:column; }
    footer{ padding:16px 16px 20px; } .inbox-banner{ margin:0 16px 14px; flex-direction:column; align-items:flex-start; }
    .app-nav{ padding:0 16px; overflow-x:auto; }
```

with:

```css
  @media (max-width:640px){
    header{ padding:20px 16px 16px; } .toolbar{ padding:14px 16px; } .table-wrap{ padding:0 16px 32px; max-height:calc(100vh - 399px); }
    #main-layout.nav-style-sidebar .table-wrap{ max-height:calc(100vh - 359px); }
    #main-layout.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 473px); }
    #main-layout.nav-style-sidebar.bulk-bar-visible .table-wrap{ max-height:calc(100vh - 433px); }
    .stats{ display:none; } .modal{ padding:20px 16px 22px; } .field-row{ flex-direction:column; }
    footer{ padding:16px 16px 20px; } .inbox-banner{ margin:0 16px 14px; flex-direction:column; align-items:flex-start; }
    .app-nav{ padding:0 16px; overflow-x:auto; }
```

Each mobile constant is the *same* base chrome height used above (`302`/
`262`/`376`/`336` — deliberately not the already-recalibrated desktop
totals, to avoid double-counting the footer) plus the footer's measured
worst-case mobile height (97px): `302+97=399`, `262+97=359`,
`376+97=473`, `336+97=433`. These four rules appear later in the
stylesheet than Step 2's desktop rules and share the exact same selectors,
so they win by source order inside the media query — the identical
cascade mechanism the existing `.table-wrap{ padding:0 16px 32px; }`
mobile override already relies on.

- [ ] **Step 4: Verify manually in a real browser**

Run this throwaway script (not committed — it's superseded by Task 2's
permanent test) from the `tests/` directory to confirm the recalibration
holds with no gap and no overlap, at both a desktop and a mobile-breakpoint
viewport:

```bash
cd tests && python3 -c "
import asyncio, json
from playwright.async_api import async_playwright

APP_PATH = '../dossiary.html'

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

async def check(width, height):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': width, 'height': height})
        await route_stub(page)
        await page.goto(f'file://{APP_PATH}')
        await page.wait_for_timeout(200)
        docs = [{'id': i, 'title': f'Doc {i}', 'category':'Travel','document_type':'Receipt','date':f'2026-03-{(i%28)+1:02d}T00:00:00+00:00','notes':None,'ocr_text':None,'ocr_language':None,'file_path':f'files/{i}_a.pdf','original_file_path':None,'created_at':'2026-03-01T00:00:00+00:00','source':'captured','source_legacy_id':None,'archived':0,'needs_review':0,'deleted':0} for i in range(1,61)]
        SEED = {'documents': docs, 'tags': [], 'document_tags': []}
        await page.evaluate(f'window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});')
        await page.click('#open-btn')
        await page.wait_for_timeout(400)
        info = await page.evaluate(\"\"\"
            () => {
                const tw = document.querySelector('#table-wrap').getBoundingClientRect();
                const f = document.querySelector('footer').getBoundingClientRect();
                const twEl = document.querySelector('#table-wrap');
                return { twBottom: tw.bottom, fTop: f.top, fBottom: f.bottom, viewportHeight: window.innerHeight, binding: twEl.scrollHeight > twEl.clientHeight + 1 };
            }
        \"\"\")
        gap = info['fTop'] - info['twBottom']
        print(f'{width}x{height}: binding={info[\"binding\"]} gap(table-wrap bottom -> footer top)={gap:.1f}px footer fully in viewport={info[\"fBottom\"] <= info[\"viewportHeight\"] + 1}')
        await browser.close()

asyncio.run(check(1280, 720))
asyncio.run(check(375, 800))
"
```

Expected: for both viewports, `binding=True` (the 60-document seed
genuinely overflows `.table-wrap`, so the measurement is meaningful — the
same non-diagnostic-gap lesson `tests/test_collections.py`'s own Scenario
30 comment documents), `gap` within about 2px of `0` (no overlap, no
large empty band), and `footer fully in viewport=True` (the footer needs
no scrolling to reach, at either width).

- [ ] **Step 5: Update the `CLAUDE.md` `.table-wrap` calibration note**

Edit `CLAUDE.md`, replacing:

```markdown
- **`.table-wrap` is a deliberate, bounded scroll container** (`overflow:auto`
  + `max-height:calc(100vh - Xpx)`, `X` now nav-style-dependent — see below),
  not just "the table with horizontal scroll" it looks like at a glance. This
  exists specifically so `thead th`'s `position:sticky; top:0;` has something
  correct to stick to. The original version only had `overflow-x:auto` (no
  `overflow-y` set at all) — which looks harmless, but per the CSS Overflow
  spec, if one axis is anything other than `visible` and the other is left as
  `visible`, the browser silently forces the `visible` one to compute as
  `auto` too. That turned `.table-wrap` into an unintended vertical scroll
  container, which broke the sticky header — it stuck to the top of
  `.table-wrap`'s own (never-scrolling, since the *page* was scrolling
  instead) box rather than the viewport, so it just scrolled away like
  nothing was sticky at all. Setting `overflow-y: visible` explicitly does
  **not** fix this — the spec doesn't allow "one visible, one not" as a
  computed combination, so the browser overrides it back to `auto`
  regardless of what's literally written. The actual fix was to stop
  fighting that rule and lean into it: make `.table-wrap` an intentional,
  bounded scroll container for both axes, so sticky has exactly one clear,
  correctly-scrolling ancestor. **`X` is `295` by default (top-tab nav) and
  `256` when `#main-layout` has the `.nav-style-sidebar` class** (see the
  "Top-level nav" note below) — the tab strip sits *above* `.table-wrap` in
  the tabs layout, adding real height to the stack, while the sidebar sits
  *beside* it, contributing none. Both numbers were verified empirically
  (`getBoundingClientRect()` on `#table-wrap` itself, confirming its
  rendered bottom edge lands exactly at the viewport bottom) while building
  the nav feature — worth restating since that same check caught the
  *sidebar* case's inherited value having already silently drifted stale
  (real value `256`, not the `230` a straight "no extra height, so reuse the
  old number unchanged" assumption would have kept) from unrelated
  header/toolbar changes made elsewhere, well before the nav existed. If you
  ever adjust the header/toolbar/nav layout, recalibrate the same way —
  verify empirically, e.g. checking `getBoundingClientRect()` on `thead th`
  before/after a large internal scroll stays roughly constant, or that
  `#table-wrap`'s own bottom edge lands at the viewport bottom — rather than
  assuming a nearby value, or an old comment's value, is still correct.
```

with:

```markdown
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
  correctly-scrolling ancestor. **`X` is `364` by default (top-tab nav),
  `324` with `.nav-style-sidebar`, `438` with `.bulk-bar-visible`, and `398`
  with both** (see the "Top-level nav" and "Collections" notes below for the
  nav-style/bulk-bar dimensions) — the tab strip sits *above* `.table-wrap`
  in the tabs layout, adding real height to the stack, while the sidebar
  sits *beside* it, contributing none; the bulk-action bar adds its own
  ~114px whenever any row is selected, regardless of nav style. **Since the
  footer became fixed, permanently-visible chrome (`position: fixed; bottom:
  0;`, see the footer's own note elsewhere in this file), all four numbers
  above also include its rendered height (62px at normal widths)** — the
  footer now consumes part of this budget exactly the way the header/nav/
  toolbar/bulk-bar already did, and at the app's one mobile breakpoint
  (`max-width: 640px`, where the footer wraps across more lines and can run
  up to 97px tall) there are four further `.table-wrap` max-height overrides
  scoped to that media query, using the same four base numbers (`302`/`262`/
  `376`/`336` — i.e. *without* the desktop footer height already baked in)
  plus that larger mobile footer height instead. All of these numbers were
  verified empirically (`getBoundingClientRect()` on `#table-wrap` and
  `footer`, confirming `#table-wrap`'s rendered bottom edge lands exactly at
  the *footer's* top edge — no longer literally "the viewport bottom" now
  that the footer occupies the last stretch of it) — worth restating since
  that same class of check has already caught real drift twice: once when
  the *sidebar* nav-style's inherited value had silently gone stale (real
  value `256`, not the `230` a straight "no extra height, so reuse the old
  number unchanged" assumption would have kept) from unrelated
  header/toolbar changes made well before the nav existed, and again when
  this file's own `295`/`256` figures, quoted in this very note, had drifted
  from the code's actual `302`/`262` by the time the footer-pinning feature
  touched this area — a small, real example of exactly the staleness this
  note already warns about below. If you ever adjust the header/toolbar/nav/
  footer layout, recalibrate the same way — verify empirically, e.g.
  checking `getBoundingClientRect()` on `thead th` before/after a large
  internal scroll stays roughly constant, or that `#table-wrap`'s own bottom
  edge lands at the fixed footer's top edge — rather than assuming a nearby
  value, or an old comment's value, is still correct.
```

- [ ] **Step 6: Commit**

```bash
git add dossiary.html CLAUDE.md
git commit -m "$(cat <<'EOF'
Pin the footer to the viewport bottom

The footer (language switcher, User Guide, Libraries, version/license/
GitHub links) used to be reachable only by scrolling past the document
table, which with a large library never felt necessary, so it went
unused. Making it position:fixed chrome, like the header/nav/toolbar
already are, keeps it permanently visible; .table-wrap's max-height is
recalibrated (desktop and the existing 640px mobile breakpoint) so the
table's own scroll region never overlaps it.
EOF
)"
```

---

### Task 2: Add a permanent regression test for the footer/table-wrap calibration

**Files:**
- Create: `tests/test_footer_pin.py`
- Modify: `CLAUDE.md` (the repo-layout script count and the "How this was
  tested" section)

**Interfaces:**
- Consumes: the exact selectors and constants Task 1 produced — `footer`
  (now `position: fixed`, `z-index: 15`), `#table-wrap` (max-height
  `364px`/`324px`/`438px`/`398px` desktop, `399px`/`359px`/`473px`/`433px`
  at `max-width: 640px`), and `#nav-style-toggle` /
  `.row-select-checkbox` / `#bulk-clear-selection-btn` for driving the
  nav-style and bulk-bar-visible states (same controls
  `tests/test_collections.py`'s own Scenario 30 already uses for this
  exact purpose).

- [ ] **Step 1: Write the test file**

Create `tests/test_footer_pin.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# 60 documents is comfortably enough to overflow .table-wrap at any of the
# viewports below -- see tests/test_collections.py's own Scenario 30 comment
# for why a small 3-4 document seed would never make the max-height
# constraint actually binding, silently passing regardless of whether the
# CSS constants are right or wrong.
def make_seed():
    docs = [
        {
            "id": i, "title": f"Document {i}", "category": "Travel" if i % 2 == 0 else "Food",
            "document_type": "Receipt", "date": f"2026-03-{(i % 28) + 1:02d}T00:00:00+00:00",
            "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": f"files/{i}_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        }
        for i in range(1, 61)
    ]
    return {"documents": docs, "tags": [], "document_tags": []}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    stub_js = open('stub_studio2.js').read()
    await page.add_init_script(stub_js)

async def open_seeded_library(page, width, height):
    await page.set_viewport_size({'width': width, 'height': height})
    await route_stub(page)
    await page.goto(f"file://{APP_PATH}")
    await page.wait_for_timeout(200)
    await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(make_seed())});")
    await page.click("#open-btn")
    await page.wait_for_timeout(400)

async def measure(page, label):
    info = await page.evaluate("""
        () => {
            const twEl = document.querySelector('#table-wrap');
            const tw = twEl.getBoundingClientRect();
            const f = document.querySelector('footer').getBoundingClientRect();
            return {
                twBottom: tw.bottom, fTop: f.top, fBottom: f.bottom,
                viewportHeight: window.innerHeight,
                binding: twEl.scrollHeight > twEl.clientHeight + 1,
            };
        }
    """)
    gap = info['fTop'] - info['twBottom']
    assert info['binding'], f"[{label}] .table-wrap's max-height constraint isn't actually binding -- seed too small to test calibration"
    assert abs(gap) <= 2, f"[{label}] expected #table-wrap's bottom edge within 2px of the footer's top edge, got a {gap:.1f}px gap"
    assert info['fBottom'] <= info['viewportHeight'] + 1, f"[{label}] footer's bottom edge ({info['fBottom']:.1f}) extends past the viewport ({info['viewportHeight']}) -- it should be fully visible with no scrolling"
    print(f"[{label}] table-wrap bottom lands within 2px of footer top (gap={gap:.1f}px), footer fully in viewport: PASS")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        # === Scenario 1-4: desktop viewport (1280x720, matching the existing
        # sticky-header calibration test), across all four combinations of nav
        # style (tabs/sidebar) x bulk-action-bar visibility (hidden/visible) ===
        await open_seeded_library(page, 1280, 720)

        await measure(page, "desktop, nav style A (tabs), bulk bar hidden")

        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        await measure(page, "desktop, nav style A (tabs), bulk bar VISIBLE")
        await page.click('#bulk-clear-selection-btn')
        await page.wait_for_timeout(150)

        await page.click('#nav-style-toggle')
        await page.wait_for_timeout(200)
        await measure(page, "desktop, nav style B (sidebar), bulk bar hidden")

        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        await measure(page, "desktop, nav style B (sidebar), bulk bar VISIBLE")
        await page.click('#bulk-clear-selection-btn')
        await page.wait_for_timeout(150)

        print("JS ERRORS (desktop viewport):", errors)
        await browser.close()

    # === Scenario 5: the app's one mobile breakpoint (max-width: 640px),
    # where the footer wraps across more than one line and needs its own,
    # separately-calibrated .table-wrap max-height override -- a fresh page,
    # since switching viewport size mid-session on the desktop page above
    # would leave stale nav-style/bulk-bar state behind ===
    async with async_playwright() as p:
        browser2 = await p.chromium.launch()
        page2 = await browser2.new_page()
        errors2 = []
        page2.on("pageerror", lambda exc: errors2.append(str(exc)))
        await open_seeded_library(page2, 375, 800)
        await measure(page2, "mobile (375x800), nav style A (tabs), bulk bar hidden")
        print("JS ERRORS (mobile viewport):", errors2)
        await browser2.close()

asyncio.run(main())
```

- [ ] **Step 2: Run the test and confirm it passes**

Run: `cd tests && python3 test_footer_pin.py`
Expected: five `PASS` lines (one per scenario), `JS ERRORS: []` twice, exit
code 0, no `Traceback`.

- [ ] **Step 3: Confirm the test actually catches a real regression**

Temporarily re-widen one constant to prove the test isn't vacuously
passing — edit `dossiary.html`'s base `.table-wrap` rule from
`max-height:calc(100vh - 364px)` to `max-height:calc(100vh - 300px)` (a
plausible-looking but wrong value), run `python3 test_footer_pin.py` again,
and confirm it now fails with the "gap" assertion (the table now overlaps
the footer by roughly 64px). Then revert that temporary edit before
continuing — `git diff dossiary.html` should show no changes once reverted.

- [ ] **Step 4: Update `CLAUDE.md`'s repo-layout script count**

Edit `CLAUDE.md`, replacing:

```markdown
tests/                   Playwright regression suite (57 scripts) + shared
```

with:

```markdown
tests/                   Playwright regression suite (58 scripts) + shared
```

- [ ] **Step 5: Update `CLAUDE.md`'s "How this was tested" section**

Edit `CLAUDE.md`, replacing:

```markdown
There's a real, runnable Playwright regression suite in `tests/` — **57
scripts covering most of the app's actual functionality** (56 of them
Playwright-driven; the 57th, `test_i18n_coverage.py`, is a plain static
check with no browser involved — see its own description below): capture, edit,
```

with:

```markdown
There's a real, runnable Playwright regression suite in `tests/` — **58
scripts covering most of the app's actual functionality** (57 of them
Playwright-driven; one, `test_i18n_coverage.py`, is a plain static
check with no browser involved — see its own description below): capture, edit,
```

Then edit `CLAUDE.md` again, replacing:

```markdown
temporarily renaming one `STRINGS.de` key and confirming the script
failed with that exact key reported missing, then reverting), and search
across all of the above. This
```

with:

```markdown
temporarily renaming one `STRINGS.de` key and confirming the script
failed with that exact key reported missing, then reverting), and search
across all of the above. Also the fixed-footer/`.table-wrap` calibration
itself (`test_footer_pin.py` — a 60-document seed, the same
non-diagnostic-gap-avoiding size `test_collections.py`'s own Scenario 30
uses, confirming `#table-wrap`'s bottom edge lands within 2px of the
footer's top edge across all four nav-style x bulk-bar-visible
combinations at a 1280x720 desktop viewport, plus the app's one mobile
breakpoint at 375x800 — and that the footer itself is always fully within
the viewport, needing no scroll to reach, verified by temporarily
widening one of the recalibrated constants and confirming the test then
fails). This
```

- [ ] **Step 6: Run the full suite to confirm nothing else regressed**

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

Expected: `TOTAL: 58  FAILED: []`.

- [ ] **Step 7: Commit**

```bash
git add tests/test_footer_pin.py CLAUDE.md
git commit -m "$(cat <<'EOF'
Add a regression test for the pinned-footer/.table-wrap calibration

Confirms #table-wrap's bottom edge always lands within 2px of the fixed
footer's top edge -- no overlap, no large empty gap -- across every
nav-style x bulk-bar-visible combination, at both the desktop viewport
and the app's one mobile breakpoint, and that the footer itself is
always fully visible without scrolling.
EOF
)"
```
