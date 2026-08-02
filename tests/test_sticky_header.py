import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Seed a library with many documents so the list is genuinely scrollable
SEED = {
    "documents": [
        {
            "id": i, "title": f"Document {i}", "category": "Medical", "document_type": "Invoice",
            "payment_method": None, "amount": None, "date": "2020-01-01T00:00:00+00:00",
            "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": f"files/{i}_doc.pdf", "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "migrated", "source_legacy_id": i
        }
        for i in range(1, 61)
    ],
    "tags": [], "document_tags": [],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 700})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)

        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        row_count = await page.locator('#doc-tbody tr').count()
        print("total rows loaded:", row_count)

        # Check header position before scrolling
        header_top_before = await page.evaluate("document.querySelector('thead th').getBoundingClientRect().top")
        print("header top before scroll:", header_top_before)

        # Scroll the page down significantly
        await page.evaluate("document.getElementById('table-wrap').scrollTop = 1500")
        await page.wait_for_timeout(200)

        header_top_after = await page.evaluate("document.querySelector('thead th').getBoundingClientRect().top")
        print("header top after scrolling 1500px (should still be near 0, not far negative):", header_top_after)

        # Confirm the header is actually visible in the viewport (not scrolled off-screen)
        header_visible = await page.locator('thead th').first.is_visible()
        print("header still visible after scroll:", header_visible)

        # Confirm a far-down row scrolled correctly out of initial view (sanity check the scroll actually happened)
        last_row_top = await page.evaluate("document.querySelector('tr[data-id=\"60\"]').getBoundingClientRect().top")
        print("last row position after scroll (should be reasonable, not way off):", last_row_top)

        # Confirm the header still has a background (not transparent, so content doesn't show through)
        header_bg = await page.evaluate("getComputedStyle(document.querySelector('thead th')).backgroundColor")
        print("header background color (should not be transparent):", header_bg)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
