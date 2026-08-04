import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

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
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url:
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
        import base64
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('scan2.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'scan2.png')
        await page.wait_for_timeout(100)
        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(200)

        await page.fill('#f-title', 'Insurance Letter')
        await page.fill('#f-category', 'Insurance')
        await page.fill('#f-tags', 'urgent, health')
        await page.fill('#f-notes', 'call back by friday')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # read the sidecar file content directly
        sidecar_content = await page.evaluate("""
            (async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await filesDir.getFileHandle('1_Insurance Letter.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        print("--- sidecar file content ---")
        print(sidecar_content)

        # now test that searching by OCR text (only) finds the document in the UI
        await page.fill('#search', 'Hello World')  # this is the fake OCR text from the stub
        await page.wait_for_timeout(150)
        rows_ocr_search = await page.locator('#doc-tbody tr').count()
        print("rows found searching OCR text 'Hello World':", rows_ocr_search)

        await page.fill('#search', 'nonexistent gibberish text')
        await page.wait_for_timeout(150)
        rows_no_match = await page.locator('#doc-tbody tr').count()
        print("rows found searching gibberish (should be 0):", rows_no_match)

        # === Search box's own clear ("x") button empties it AND re-filters
        # immediately -- wireClearButton() dispatches 'input' now (not just
        # 'change'), since that's the event the search box's own listener uses ===
        await page.click('#search-clear')
        await page.wait_for_timeout(150)
        search_value_after_clear = await page.input_value('#search')
        rows_after_clear = await page.locator('#doc-tbody tr').count()
        focused_after_clear = await page.evaluate('document.activeElement.id')
        print("search value after clicking clear (should be empty):", repr(search_value_after_clear))
        print("rows restored after clearing search (should be 1):", rows_after_clear)
        print("focus returned to the search input:", focused_after_clear == 'search')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
