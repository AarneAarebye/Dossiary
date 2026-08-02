import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio
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
            if 'sql-wasm.js' in url or 'tesseract' in url or 'pdf.js' in url or 'jspdf' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)

        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        # Scenario: open an EMPTY folder -> should show "initialize new library" prompt
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        init_visible = await page.locator("#init-state").is_visible()
        print("init-state visible for empty folder:", init_visible)

        await page.click("#init-btn")
        await page.wait_for_timeout(300)
        status = await page.locator("#status").inner_text()
        row_count = await page.locator("#doc-tbody tr").count()
        print("status after init:", status)
        print("row count after init (should be 0):", row_count)

        # Now add first document to a brand-new library, verify id starts at 1
        await page.click('#add-btn')
        await page.wait_for_timeout(100)

        import base64
        pdf_bytes = b"%PDF-1.4 fake pdf content"
        with open('tiny.pdf', 'wb') as f:
            f.write(pdf_bytes)
        await page.set_input_files('#file-input', 'tiny.pdf')
        await page.wait_for_timeout(150)

        ocr_btn_disabled = await page.locator('#run-ocr-btn').is_disabled()
        preview_text = await page.locator('#file-preview-area').inner_text()
        print("OCR button disabled for PDF:", ocr_btn_disabled)
        print("preview mentions OCR-not-available note:", 'OCR not available for PDFs' in preview_text)

        await page.fill('#f-title', 'First New Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)
        status2 = await page.locator("#status").inner_text()
        print("status after first save on new library:", status2)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
