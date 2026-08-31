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
def make_seed(nav_style):
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
    return {"documents": docs, "tags": [], "document_tags": [], "settings": [{"key": "nav_style", "value": nav_style}]}

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

async def open_seeded_library(page, width, height, nav_style):
    await page.set_viewport_size({'width': width, 'height': height})
    await route_stub(page)
    await page.goto(f"file://{APP_PATH}")
    await page.wait_for_timeout(200)
    await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(make_seed(nav_style))});")
    await page.click("#open-btn")
    await page.wait_for_timeout(400)

async def measure_last_row_not_clipped(page, label):
    """Real last-row-visibility check for the 641-1280px desktop width band,
    which the container-bottom-vs-footer-top proxy measure() uses above is
    blind to: a large .table-wrap padding-bottom can absorb the difference
    between the max-height budget and what actually fits, so twBottom could
    sit comfortably above the footer's top edge while the last real <tr>
    (the content that actually matters to a person) is still clipped behind
    it. Scrolls both #table-wrap's own inner region and the page to their
    respective ends before measuring, since either one being un-scrolled
    could hide a real overlap."""
    await page.evaluate("""
        () => {
            const tw = document.querySelector('#table-wrap');
            tw.scrollTop = tw.scrollHeight;
            window.scrollTo(0, document.body.scrollHeight);
        }
    """)
    await page.wait_for_timeout(100)
    info = await page.evaluate("""
        () => {
            const tw = document.querySelector('#table-wrap');
            tw.scrollTop = tw.scrollHeight;
            window.scrollTo(0, document.body.scrollHeight);
            const rows = document.querySelectorAll('#doc-tbody tr');
            const lastRow = rows[rows.length - 1];
            const lr = lastRow.getBoundingClientRect();
            const f = document.querySelector('footer').getBoundingClientRect();
            return { lastRowBottom: lr.bottom, footerTop: f.top, rowCount: rows.length };
        }
    """)
    clip = info['lastRowBottom'] - info['footerTop']
    assert info['rowCount'] > 0, f"[{label}] no table rows found -- seed/render didn't happen as expected"
    assert clip <= 2, f"[{label}] last table row is clipped behind the fixed footer by {clip:.1f}px (last row bottom {info['lastRowBottom']:.1f}, footer top {info['footerTop']:.1f})"
    print(f"[{label}] last row clip={clip:.1f}px (<=2px accepted): PASS")

async def measure(page, label, min_gap):
    """min_gap: the smallest acceptable gap in px, applied uniformly across
    all scenarios in this file. -2 allows for ~2px tolerance to account for
    sub-pixel rendering precision, matching the "no real overlap" expectation
    throughout."""
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
    assert gap >= min_gap, f"[{label}] expected #table-wrap's bottom edge no more than {-min_gap:.0f}px below the footer's top edge, got a {gap:.1f}px gap (more overlap than the accepted bound)"
    assert info['fBottom'] <= info['viewportHeight'] + 1, f"[{label}] footer's bottom edge ({info['fBottom']:.1f}) extends past the viewport ({info['viewportHeight']}) -- it should be fully visible with no scrolling"
    print(f"[{label}] gap={gap:.1f}px (min accepted {min_gap}px): PASS")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        # === Desktop viewport sweep (720px-tall viewport), across several
        # widths -- not just 1280px. A final whole-branch review of the
        # Amount-range/Currency-filter branch found that a single calibrated
        # width isn't enough: that branch's new toolbar controls can push
        # .toolbar onto an extra wrapped row at certain widths only, and
        # which widths trigger that differs by nav style (tabs' toolbar
        # spans the full width; sidebar's is squeezed narrower), so a
        # regression can appear at an untested width even while 1280px alone
        # keeps passing. 1000/1100px is where tabs mode regressed (an extra
        # wrapped row not present at 1280px, now closed by recalibrating
        # tabs' own constants); 1440px is where sidebar mode's own
        # recalibration (see CLAUDE.md's sticky-header calibration note)
        # leaves deliberate, accepted dead space rather than overlap.
        # Both nav styles share the same underlying padding-absorption
        # effect at narrow-enough widths: the box-edge measure() proxy
        # reports a large apparent overlap there even though the real last
        # table row isn't clipped, because .table-wrap's own padding-bottom
        # absorbs the difference (the same known effect the 641-1280px
        # in-between-band section below already accounts for). Each nav
        # style clears that effect at a different width, verified with a
        # finer 700-1100px sweep at this exact 720px viewport height:
        # tabs' proxy becomes reliable at 900px (boxGap goes from a false
        # -52/-67px at 700-850px to a real, trustworthy 16px at 900px);
        # sidebar's real clip stays tight (-3.5px) from 700-850px, then
        # relaxes sharply to -40.5px at 900px and further at 1000/1100px
        # (an earlier version of this comment guessed 900px as sidebar's
        # own worst case, which was wrong -- 900px already has 40px+ of
        # unused margin there, real coverage but not a sensitive one,
        # since a future regression smaller than that margin would slip
        # through undetected). So: 800px is included specifically to keep
        # sidebar's *actual* tightest point covered by a real, sensitive
        # check, and both nav styles fall back to the real
        # last-row-visibility check below their own reliability threshold
        # (900px for tabs, 1280px for sidebar) rather than the proxy. ===
        for width in [800, 1000, 1100, 1280, 1440]:
            await open_seeded_library(page, width, 720, 'tabs')
            tabs_tight = width >= 900
            if tabs_tight:
                await measure(page, f"desktop {width}x720, nav=tabs, bulkbar=hidden", min_gap=-2)
            else:
                await measure_last_row_not_clipped(page, f"desktop {width}x720, nav=tabs, bulkbar=hidden")

            await page.check('tr[data-id="1"] .row-select-checkbox')
            await page.wait_for_timeout(150)
            if tabs_tight:
                await measure(page, f"desktop {width}x720, nav=tabs, bulkbar=VISIBLE", min_gap=-2)
            else:
                await measure_last_row_not_clipped(page, f"desktop {width}x720, nav=tabs, bulkbar=VISIBLE")
            await page.click('#bulk-clear-selection-btn')
            await page.wait_for_timeout(150)

            await page.click('#nav-style-toggle')
            await page.wait_for_timeout(200)
            sidebar_tight = width >= 1280
            if sidebar_tight:
                await measure(page, f"desktop {width}x720, nav=sidebar, bulkbar=hidden", min_gap=-2)
            else:
                await measure_last_row_not_clipped(page, f"desktop {width}x720, nav=sidebar, bulkbar=hidden")

            await page.check('tr[data-id="1"] .row-select-checkbox')
            await page.wait_for_timeout(150)
            if sidebar_tight:
                await measure(page, f"desktop {width}x720, nav=sidebar, bulkbar=VISIBLE", min_gap=-2)
            else:
                await measure_last_row_not_clipped(page, f"desktop {width}x720, nav=sidebar, bulkbar=VISIBLE")
            await page.click('#bulk-clear-selection-btn')
            await page.wait_for_timeout(150)

        print("JS ERRORS (desktop viewport sweep):", errors)
        await browser.close()

    # === Mobile breakpoint (max-width: 640px): the mobile calibration uses a
    # single worst-case (320px-width) constant per combination, so the gap is
    # tight only at 320px and grows to a deliberate safety margin at wider
    # mobile widths. The 320px+bulk-bar corner was once a known, structurally-
    # unavoidable overlap, but Task 1 fixed it by capping .toolbar to a single
    # horizontally-scrollable row, reducing chrome height enough to eliminate it.
    # All scenarios now expect tight, uniform min_gap=-2 everywhere. ===
    async with async_playwright() as p:
        browser2 = await p.chromium.launch()
        page2 = await browser2.new_page()
        errors2 = []
        page2.on("pageerror", lambda exc: errors2.append(str(exc)))

        await open_seeded_library(page2, 320, 800, 'tabs')
        await measure(page2, "mobile 320x800, nav=tabs, bulkbar=hidden", min_gap=-2)
        await page2.check('tr[data-id="1"] .row-select-checkbox')
        await page2.wait_for_timeout(150)
        await measure(page2, "mobile 320x800, nav=tabs, bulkbar=VISIBLE", min_gap=-2)
        await page2.click('#bulk-clear-selection-btn')
        await page2.wait_for_timeout(150)

        await page2.click('#nav-style-toggle')
        await page2.wait_for_timeout(200)
        await measure(page2, "mobile 320x800, nav=sidebar, bulkbar=hidden", min_gap=-2)
        await page2.check('tr[data-id="1"] .row-select-checkbox')
        await page2.wait_for_timeout(150)
        await measure(page2, "mobile 320x800, nav=sidebar, bulkbar=VISIBLE", min_gap=-2)

        # === Toolbar reachability at the narrowest supported width: every
        # control must still be reachable via horizontal scroll, not silently
        # clipped or unreachable, now that .toolbar no longer wraps onto many
        # rows at narrow widths. ===
        toolbar_info = await page2.evaluate("""
            () => {
                const tb = document.querySelector('.toolbar');
                const ids = ['search', 'category-filter', 'type-filter', 'person-filter',
                             'show-archived-toggle', 'manage-fields-btn', 'manage-collections-btn',
                             'inbox-check-btn', 'check-reminders-btn', 'add-btn', 'reload-btn', 'columns-btn'];
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
        assert toolbar_info['missingControls'] == [], f"Toolbar is missing expected controls: {toolbar_info['missingControls']}"
        assert toolbar_info['overflowsHorizontally'], f"Toolbar should overflow horizontally (scrollWidth={toolbar_info['scrollWidth']} vs clientWidth={toolbar_info['clientWidth']}) but doesn't -- children may be compressing instead of the row genuinely overflowing"

        # === Columns dropdown must actually be visible in the viewport when opened,
        # not just present in the DOM -- .toolbar{overflow-x:auto} at narrow widths
        # forces overflow-y to compute as auto too (the same CSS Overflow spec quirk
        # this file's own .table-wrap note documents), which used to clip
        # .columns-menu (position:absolute inside .toolbar) to a ~12px sliver. ===
        columns_menu_info = await page2.evaluate("""
            () => {
                document.getElementById('columns-btn').click();
                const menu = document.getElementById('columns-menu');
                const rect = menu.getBoundingClientRect();
                return {
                    display: menu.style.display,
                    top: rect.top, bottom: rect.bottom, height: rect.height,
                    viewportHeight: window.innerHeight,
                    fullyVisible: rect.top >= 0 && rect.bottom <= window.innerHeight,
                };
            }
        """)
        print(f"[columns menu, 320px width] opens and is fully visible in the viewport (not clipped by .toolbar's own overflow): {columns_menu_info['fullyVisible']}")
        assert columns_menu_info['display'] == 'block', "Columns menu should be open after clicking the button"
        assert columns_menu_info['fullyVisible'], f"Columns menu clipped: top={columns_menu_info['top']:.1f} bottom={columns_menu_info['bottom']:.1f} viewportHeight={columns_menu_info['viewportHeight']}"

        print("JS ERRORS (320px mobile viewport):", errors2)
        await browser2.close()

    async with async_playwright() as p:
        browser3 = await p.chromium.launch()
        page3 = await browser3.new_page()
        errors3 = []
        page3.on("pageerror", lambda exc: errors3.append(str(exc)))

        await open_seeded_library(page3, 375, 800, 'tabs')
        await measure(page3, "mobile 375x800, nav=tabs, bulkbar=hidden", min_gap=-2)
        await page3.check('tr[data-id="1"] .row-select-checkbox')
        await page3.wait_for_timeout(150)
        await measure(page3, "mobile 375x800, nav=tabs, bulkbar=VISIBLE", min_gap=-2)

        print("JS ERRORS (375px mobile viewport):", errors3)
        await browser3.close()

    async with async_playwright() as p:
        browser4 = await p.chromium.launch()
        page4 = await browser4.new_page()
        errors4 = []
        page4.on("pageerror", lambda exc: errors4.append(str(exc)))

        await open_seeded_library(page4, 640, 800, 'sidebar')
        await measure(page4, "mobile 640x800, nav=sidebar, bulkbar=hidden", min_gap=-2)
        await page4.check('tr[data-id="1"] .row-select-checkbox')
        await page4.wait_for_timeout(150)
        await measure(page4, "mobile 640x800, nav=sidebar, bulkbar=VISIBLE", min_gap=-2)

        print("JS ERRORS (640px mobile viewport):", errors4)
        await browser4.close()

    # === Desktop in-between width band (641-1280px, 800px viewport height):
    # a final whole-branch review found this band was never covered by the
    # scenarios above -- .toolbar wraps across more rows at these
    # in-between widths than at the 1280px-calibrated width, so
    # .table-wrap's recalibrated max-height allowed more content than
    # actually fit above the fixed footer, clipping the real last table row
    # (up to 27px at 700-800px, 14px at 900px) even though the
    # container-bottom-vs-footer-top proxy measure() uses above looked fine
    # (a large .table-wrap padding-bottom was absorbing the difference).
    # The fix was raising .table-wrap's padding-bottom from 40px to 70px
    # (box-sizing:border-box means max-height's math already includes
    # padding, so this doesn't change the calibrated max-height constants or
    # the 1280px-width behavior -- confirmed via measure() below still
    # reading a 0px gap there -- it just reserves more of the already-
    # budgeted space as padding instead of potential content). This uses
    # the real last-row-visibility check (measure_last_row_not_clipped),
    # not the proxy, specifically because the proxy is blind to this exact
    # failure mode. ===
    async with async_playwright() as p:
        browser5 = await p.chromium.launch()
        errors5 = []
        for nav_style in ['tabs', 'sidebar']:
            for width in [641, 700, 800, 900, 1000, 1100, 1280]:
                page5 = await browser5.new_page()
                page5.on("pageerror", lambda exc: errors5.append(str(exc)))
                await open_seeded_library(page5, width, 800, nav_style)
                await measure_last_row_not_clipped(page5, f"in-between band {width}x800, nav={nav_style}")
                await page5.close()

        # 1280px is the calibrated desktop width -- confirm the padding-bottom
        # change didn't disturb its own exact-0px-gap calibration.
        page5b = await browser5.new_page()
        page5b.on("pageerror", lambda exc: errors5.append(str(exc)))
        await open_seeded_library(page5b, 1280, 800, 'tabs')
        await measure(page5b, "in-between band regression check: 1280x800, nav=tabs, bulkbar=hidden", min_gap=-2)
        await page5b.close()

        print("JS ERRORS (641-1280px in-between width band):", errors5)
        await browser5.close()

asyncio.run(main())
