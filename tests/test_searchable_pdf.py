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

        await page.click('#add-btn')
        await page.wait_for_timeout(100)

        # a tiny real PNG so isImage + type checks pass, and Image() can load it for dimensions
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('scan.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'scan.png')
        await page.wait_for_timeout(150)

        preview_text = await page.locator('#file-preview-area').inner_text()
        print("preview mentions searchable PDF:", 'searchable PDF' in preview_text)

        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(300)
        ocr_status = await page.locator('#ocr-status').inner_text()
        print("OCR status:", ocr_status)

        await page.fill('#f-title', 'Scanned Letter')
        await page.fill('#f-category', 'Mail')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        status = await page.locator('#status').inner_text()
        print("save status:", status)

        jspdf_calls = await page.evaluate("window.__JSPDF_CALLS")
        print("jsPDF construct opts:", [c for c in jspdf_calls if c['type'] == 'construct'])
        print("jsPDF addImage calls:", [c for c in jspdf_calls if c['type'] == 'addImage'])
        print("jsPDF text call count:", sum(1 for c in jspdf_calls if c['type'] == 'text'))
        print("jsPDF text calls:", [c for c in jspdf_calls if c['type'] == 'text'])

        # verify the resulting DB record has both file_path (processed) and original_file_path (subfolder)
        db_state = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("documents[0]:", db_state['documents'][0])
        print("searchable_pdf_built (should be 1):", db_state['documents'][0].get('searchable_pdf_built'))

        # verify actual files on the fake filesystem
        files_listing = await page.evaluate("""
            (async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const names = [];
                for (const [name, handle] of filesDir._children) {
                    names.push(name + (handle.kind === 'directory' ? '/' : ''));
                    if (handle.kind === 'directory') {
                        for (const [subname] of handle._children) names.push(name + '/' + subname);
                    }
                }
                return names;
            })()
        """)
        print("files/ listing:", files_listing)

        # Detail view shows both the processed file's and the original's path, prefixed
        # with the library folder name (since File System Access API handles expose no
        # absolute path) -- see CLAUDE.md's note on this pattern in the Inbox section.
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        modal_meta_text = await page.locator('.modal-meta').inner_text()
        print("modal shows File path:", 'File' in modal_meta_text and 'EmptyLibrary/files/1_Scanned Letter.pdf' in modal_meta_text)
        print("modal shows Original path:", 'Original' in modal_meta_text and 'EmptyLibrary/files/1_Scanned Letter/scan.png' in modal_meta_text)

        # === Scenario: a PDF that already has real, selectable text -- OCR is
        # skipped entirely, and the file saves completely untouched ===
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = true;")
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('already_text.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 already has text")
        await page.set_input_files('#file-input', 'already_text.pdf')
        await page.wait_for_timeout(150)

        run_ocr_enabled_for_pdf = not await page.locator('#run-ocr-btn').is_disabled()
        print("Run OCR button is enabled for a PDF upload:", run_ocr_enabled_for_pdf)

        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(300)
        already_text_status = await page.locator('#ocr-status').inner_text()
        print("status for a PDF that already has real text:", already_text_status)

        await page.fill('#f-title', 'Already Searchable PDF')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        db_state_2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc2 = [d for d in db_state_2['documents'] if d['id'] == 2][0]
        print("already-searchable PDF was NOT rebuilt (searchable_pdf_built should be 0):", doc2.get('searchable_pdf_built'))
        print("already-searchable PDF's ocr_text is empty (OCR never ran):", not doc2.get('ocr_text'))

        # === Scenario: a scanned (no real text) multi-page PDF gets OCR'd page by
        # page and rebuilt into a multi-page searchable PDF ===
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = false;")
        await page.evaluate("window.__STUB_PDF_NUM_PAGES = 3;")
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('scanned_multipage.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 scanned multipage")
        await page.set_input_files('#file-input', 'scanned_multipage.pdf')
        await page.wait_for_timeout(150)

        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(500)
        multipage_status = await page.locator('#ocr-status').inner_text()
        print("status after OCR'ing a 3-page scanned PDF:", multipage_status)
        multipage_ocr_text = await page.locator('#f-ocr-text').input_value()
        print("OCR text combines all 3 pages:", multipage_ocr_text.count('Hello World') == 3)

        # Reset the jsPDF call log so the upcoming per-page addImage count reflects only
        # this document's own save, not also the single-page document saved earlier above.
        await page.evaluate("window.__JSPDF_CALLS = [];")
        await page.fill('#f-title', 'Scanned Multipage PDF')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        jspdf_calls_multipage = await page.evaluate("window.__JSPDF_CALLS")
        addimage_calls = [c for c in jspdf_calls_multipage if c['type'] == 'addImage']
        addpage_present = any(c['type'] == 'construct' for c in jspdf_calls_multipage)
        print("jsPDF got one addImage call per page (3):", len(addimage_calls) == 3)

        db_state_3 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc3 = [d for d in db_state_3['documents'] if d['id'] == 3][0]
        print("scanned multi-page PDF was rebuilt (searchable_pdf_built should be 1):", doc3.get('searchable_pdf_built'))
        print("scanned multi-page PDF's ocr_text was populated:", bool(doc3.get('ocr_text')))

        # === Scenario: a scanned single-page PDF with no OCR run at all still
        # saves normally, with the OCR button available but never clicked ===
        await page.evaluate("window.__STUB_PDF_NUM_PAGES = 1;")
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('unocred.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 never ocred")
        await page.set_input_files('#file-input', 'unocred.pdf')
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Never OCRd PDF')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        db_state_4 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc4 = [d for d in db_state_4['documents'] if d['id'] == 4][0]
        print("a PDF saved without ever clicking Run OCR is not rebuilt:", doc4.get('searchable_pdf_built') == 0)
        print("a PDF saved without ever clicking Run OCR has no ocr_text:", not doc4.get('ocr_text'))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
