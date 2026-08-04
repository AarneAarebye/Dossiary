import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, base64
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
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
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        # === Doc 1: a 5-page PDF -- page count should show in capture, detail, and edit ===
        await page.evaluate("window.__STUB_PDF_NUM_PAGES = 5;")
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('pagecount5.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 fivepage")
        await page.set_input_files('#file-input', 'pagecount5.pdf')
        await page.wait_for_timeout(300)
        capture_page_count = await page.locator('#f-page-count').inner_text()
        print("Capture form page count note:", repr(capture_page_count))

        await page.fill('#f-title', 'Five Page Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(300)
        detail_text = await page.locator('.modal-meta').inner_text()
        print("Detail view shows 'Pages' label:", 'Pages' in detail_text)
        print("Detail view shows '5':", '5' in detail_text)

        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        edit_page_count = await page.locator('#e-page-count').inner_text()
        print("Edit dialog page count note:", repr(edit_page_count))
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Doc 2: an IMAGE document -- should show no page count anywhere ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('pagecountimg.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'pagecountimg.png')
        await page.wait_for_timeout(300)
        await page.fill('#f-title', 'Image Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(300)
        detail_text_2 = await page.locator('.modal-meta').inner_text()
        print("Image doc detail view shows no 'Pages' label:", 'Pages' not in detail_text_2)

        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        edit_page_count_2 = await page.locator('#e-page-count').inner_text()
        print("Image doc edit dialog page count note (should be empty):", repr(edit_page_count_2))

        assert capture_page_count.strip() == '5 pages', f"expected '5 pages' in capture form, got {capture_page_count!r}"
        assert 'Pages' in detail_text and '5' in detail_text, "expected detail view to show Pages: 5"
        assert edit_page_count.strip() == '5 pages', f"expected '5 pages' in edit dialog, got {edit_page_count!r}"
        assert 'Pages' not in detail_text_2, "image doc detail view should not show a Pages line"
        assert edit_page_count_2.strip() == '', f"image doc edit dialog should show no page count, got {edit_page_count_2!r}"

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
