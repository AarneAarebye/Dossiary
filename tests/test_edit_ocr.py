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
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

        # === Doc 1: an IMAGE document ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('editocr_img.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'editocr_img.png')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Image Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # === Doc 2: a PDF document ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('editocr_pdf.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 editocr")
        await page.set_input_files('#file-input', 'editocr_pdf.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'PDF Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # --- Edit doc 1 (image), run OCR ---
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        run_ocr_visible = await page.locator('#e-run-ocr-btn').is_visible()
        print("Run OCR button visible in edit form:", run_ocr_visible)

        await page.click('#e-run-ocr-btn')
        await page.wait_for_timeout(400)
        ocr_text_1 = await page.locator('#e-ocr-text').input_value()
        ocr_status_1 = await page.locator('#e-ocr-status').inner_text()
        print("OCR text after running on image doc:", repr(ocr_text_1))
        print("OCR status:", ocr_status_1)

        # Save and confirm it persists
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1 = [d for d in persisted['documents'] if d['id'] == 1][0]
        print("persisted ocr_text for image doc:", doc1['ocr_text'])
        # Save already closed the edit modal on success -- no separate close click needed.

        # --- Edit doc 2 (PDF), run OCR -- exercises the pdf.js render path ---
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.click('#e-run-ocr-btn')
        await page.wait_for_timeout(400)
        ocr_text_2 = await page.locator('#e-ocr-text').input_value()
        ocr_status_2 = await page.locator('#e-ocr-status').inner_text()
        print("OCR text after running on PDF doc:", repr(ocr_text_2))
        print("OCR status (PDF path):", ocr_status_2)

        pdfjs_calls = await page.evaluate("window.__STUB_LOG.filter(l => l.includes('pdfjsLib'))")
        print("pdfjsLib was invoked for PDF OCR:", len(pdfjs_calls) > 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Doc 3: a multi-page PDF -- regression test for a real bug report where
        # edit-time OCR silently only recognized the first page of a scanned PDF ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('editocr_pdf3.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 editocr multipage")
        await page.set_input_files('#file-input', 'editocr_pdf3.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Multi-page PDF Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.evaluate("window.__STUB_PDF_NUM_PAGES = 3;")
        await page.evaluate("window.__STUB_LOG.length = 0;")
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.click('#e-run-ocr-btn')
        await page.wait_for_timeout(400)
        ocr_text_3 = await page.locator('#e-ocr-text').input_value()
        ocr_status_3 = await page.locator('#e-ocr-status').inner_text()
        recognize_calls = await page.evaluate("window.__STUB_LOG.filter(l => l.startsWith('recognize called')).length")
        print("OCR text after running on 3-page PDF doc:", repr(ocr_text_3))
        print("OCR status (multi-page PDF path):", ocr_status_3)
        print("recognize() call count for 3-page PDF:", recognize_calls)
        assert ocr_text_3 == 'Hello World\n\nHello World\n\nHello World', f"expected text from all 3 pages, got {ocr_text_3!r}"
        assert recognize_calls == 3, f"expected recognize() to run once per page (3), got {recognize_calls}"
        assert '3 page' in ocr_status_3, f"expected status to mention 3 pages, got {ocr_status_3!r}"

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
