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

        # These three are "already searchable" (a text layer found): the Edit form's
        # button keeps reading their text on the spot, via runOcrForEdit().
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET has_text_layer = 1 WHERE id = ?', [1]); window.__DEBUG_dbRun('UPDATE documents SET has_text_layer = 1 WHERE id = ?', [2]);")
        await page.evaluate("window.__DEBUG_loadDocumentsFromDb()")
        await page.wait_for_timeout(200)

        # --- Edit doc 1 (image), run OCR ---
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        run_ocr_visible = await page.locator('#e-run-ocr-btn').is_visible()
        print("Make searchable button visible in edit form:", run_ocr_visible)

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

        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET has_text_layer = 1 WHERE id = ?', [3]); window.__DEBUG_loadDocumentsFromDb()")
        await page.wait_for_timeout(200)
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

        print("already-searchable docs added no ocr_jobs row:", await page.evaluate("window.__DEBUG_ocrJobRows().length") == 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Doc 4: a scanned PDF without text -- the button now queues background OCR.
        # scan_auto_ocr is off here (the stub's default): the button must work anyway. ===
        await page.evaluate("window.__DEBUG_holdOcrJobs(true)")
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('editocr_pdf4.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 editocr scanned")
        await page.set_input_files('#file-input', 'editocr_pdf4.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Scanned Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)
        await page.click('tr[data-id="4"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        print("edit button reads 'Make searchable':", (await page.inner_text('#e-run-ocr-btn')).strip() == 'Make searchable')
        await page.select_option('#e-ocr-lang', 'deu')
        await page.click('#e-run-ocr-btn')
        await page.wait_for_timeout(300)
        rows = await page.evaluate("window.__DEBUG_ocrJobRows()")
        print("queued one edit row:", len(rows) == 1 and rows[0]['document_id'] == 4 and rows[0]['job_id'] is None and rows[0]['requested_by'] == 'edit')
        print("row carries the form's language:", rows[0]['ocr_language'] == 'deu')
        print("OCR text box disabled:", await page.locator('#e-ocr-text').is_disabled())
        print("queued note shown:", 'Being made searchable in the background' in await page.inner_text('#e-ocr-status'))
        print("table row shows the pending pill:", 'Making searchable…' in await page.inner_text('tr[data-id="4"]'))

        # Saving with the row pending keeps ocr_text and saves the other fields.
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET ocr_text = ? WHERE id = ?', ['typed earlier', 4]); window.__DEBUG_loadDocumentsFromDb()")
        await page.wait_for_timeout(100)
        await page.fill('#e-title', 'Scanned Doc renamed')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        persisted = await page.evaluate("""(async () => { const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite'); return JSON.parse(await (await fh.getFile()).text()); })()""")
        doc4 = [d for d in persisted['documents'] if d['id'] == 4][0]
        print("save kept ocr_text and saved the title:", doc4['ocr_text'] == 'typed earlier' and doc4['title'] == 'Scanned Doc renamed')

        # Reopening the form while the row is pending shows the box locked.
        await page.click('tr[data-id="4"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        print("reopened: box disabled with the note:", await page.locator('#e-ocr-text').is_disabled() and 'Being made searchable' in await page.inner_text('#e-ocr-status'))
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # A pass makes it searchable, with the setting off.
        await page.evaluate("window.__DEBUG_runOcrJobPass()")
        for _ in range(40):
            await page.wait_for_timeout(100)
            if await page.evaluate("window.__DEBUG_ocrFallbackIdle()") and not await page.evaluate("window.__DEBUG_ocrJobRows().length"):
                break
        persisted = await page.evaluate("""(async () => { const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite'); return JSON.parse(await (await fh.getFile()).text()); })()""")
        doc4 = [d for d in persisted['documents'] if d['id'] == 4][0]
        print("pass made it searchable and removed the row:", doc4['searchable_pdf_built'] == 1 and await page.evaluate("window.__DEBUG_ocrJobRows().length") == 0)

        # === Doc 5/6: the job finishing while the Edit form stays open; an inactive scan row ===
        for n, title in ((5, 'Open Form Doc'), (6, 'Scan Row Doc')):
            await page.click('#add-btn')
            await page.wait_for_timeout(100)
            with open(f'editocr_pdf{n}.pdf', 'wb') as f:
                f.write(f"%PDF-1.4 editocr {n}".encode())
            await page.set_input_files('#file-input', f'editocr_pdf{n}.pdf')
            await page.wait_for_timeout(100)
            await page.fill('#f-title', title)
            await page.click('#save-doc-btn')
            await page.wait_for_timeout(300)
        await page.click('tr[data-id="5"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.click('#e-run-ocr-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("window.__DEBUG_runOcrJobPass()")
        for _ in range(40):
            await page.wait_for_timeout(100)
            if await page.evaluate("window.__DEBUG_ocrFallbackIdle()") and not await page.evaluate("window.__DEBUG_ocrJobRows().length"):
                break
        await page.wait_for_timeout(200)
        box = page.locator('#e-ocr-text')
        print("finished while open: box shows the recognized text:", (await box.input_value()).startswith('Hello World'))
        print("finished while open: box and button enabled, note cleared:", await box.is_enabled() and await page.locator('#e-run-ocr-btn').is_enabled() and (await page.inner_text('#e-ocr-status')).strip() == '')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        persisted = await page.evaluate("""(async () => { const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite'); return JSON.parse(await (await fh.getFile()).text()); })()""")
        doc5 = [d for d in persisted['documents'] if d['id'] == 5][0]
        print("save after the job finished keeps the recognized text:", (doc5['ocr_text'] or '').startswith('Hello World'))

        # A scan fallback row with the setting off is not active: no lock.
        await page.evaluate("window.__DEBUG_dbRun('INSERT OR REPLACE INTO ocr_jobs (document_id, helper_url, job_id, file_hash, created_at, ocr_language, requested_by) VALUES (?, ?, ?, ?, ?, ?, ?)', [6, null, null, null, 'x', null, 'scan'])")
        await page.click('tr[data-id="6"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        print("inactive scan row does not lock the box:", await page.locator('#e-ocr-text').is_enabled() and await page.locator('#e-run-ocr-btn').is_enabled())
        await page.fill('#e-ocr-text', 'typed by hand')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        persisted = await page.evaluate("""(async () => { const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite'); return JSON.parse(await (await fh.getFile()).text()); })()""")
        print("save with an inactive scan row stores the typed text:", [d for d in persisted['documents'] if d['id'] == 6][0]['ocr_text'] == 'typed by hand')

        # The capture form's button carries the new name too (English and German).
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        print("capture button reads 'Make searchable':", (await page.inner_text('#run-ocr-btn')).strip() == 'Make searchable')
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        print("capture button reads 'Durchsuchbar machen' in German:", (await page.inner_text('#run-ocr-btn')).strip() == 'Durchsuchbar machen')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
