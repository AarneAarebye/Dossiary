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

async def measure(page, label, min_gap):
    """min_gap: the smallest acceptable gap in px. 0 means "no overlap
    allowed" (the normal case); a negative value documents a known, bounded,
    accepted overlap (only used for the single structurally-unavoidable
    320px+bulk-bar corner) so the test still catches it getting WORSE."""
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

        # === Desktop viewport (1280x720): tight calibration expected in all
        # four nav-style x bulk-bar-visible combinations -- min_gap=-2 (i.e.
        # essentially exact, no overlap, matching Task 1's own verification) ===
        await open_seeded_library(page, 1280, 720, 'tabs')
        await measure(page, "desktop 1280x720, nav=tabs, bulkbar=hidden", min_gap=-2)

        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        await measure(page, "desktop 1280x720, nav=tabs, bulkbar=VISIBLE", min_gap=-2)
        await page.click('#bulk-clear-selection-btn')
        await page.wait_for_timeout(150)

        await page.click('#nav-style-toggle')
        await page.wait_for_timeout(200)
        await measure(page, "desktop 1280x720, nav=sidebar, bulkbar=hidden", min_gap=-2)

        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        await measure(page, "desktop 1280x720, nav=sidebar, bulkbar=VISIBLE", min_gap=-2)

        print("JS ERRORS (desktop viewport):", errors)
        await browser.close()

    # === Mobile breakpoint (max-width: 640px): the mobile calibration uses a
    # single worst-case (320px-width) constant per combination, so the gap is
    # tight only at 320px and grows to a deliberate safety margin at wider
    # mobile widths -- min_gap=-2 (no overlap) everywhere EXCEPT the one
    # documented, structurally-unavoidable corner (320px + bulk bar visible,
    # both nav styles), where a small bounded overlap is accepted (see
    # CLAUDE.md's .table-wrap note) but must not silently get worse. ===
    async with async_playwright() as p:
        browser2 = await p.chromium.launch()
        page2 = await browser2.new_page()
        errors2 = []
        page2.on("pageerror", lambda exc: errors2.append(str(exc)))

        await open_seeded_library(page2, 320, 800, 'tabs')
        await measure(page2, "mobile 320x800, nav=tabs, bulkbar=hidden", min_gap=-2)
        await page2.check('tr[data-id="1"] .row-select-checkbox')
        await page2.wait_for_timeout(150)
        await measure(page2, "mobile 320x800, nav=tabs, bulkbar=VISIBLE (known bounded overlap)", min_gap=-30)
        await page2.click('#bulk-clear-selection-btn')
        await page2.wait_for_timeout(150)

        await page2.click('#nav-style-toggle')
        await page2.wait_for_timeout(200)
        await measure(page2, "mobile 320x800, nav=sidebar, bulkbar=hidden", min_gap=-2)
        await page2.check('tr[data-id="1"] .row-select-checkbox')
        await page2.wait_for_timeout(150)
        await measure(page2, "mobile 320x800, nav=sidebar, bulkbar=VISIBLE (known bounded overlap)", min_gap=-55)

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

asyncio.run(main())
