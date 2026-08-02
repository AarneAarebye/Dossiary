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
        with open('subdoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 subdoc")
        await page.set_input_files('#file-input', 'subdoc.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Dentist Bill')
        await page.fill('#f-category', 'Medical')
        await page.fill('#f-subcategory', 'Dentist')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # check table row shows subcategory as sub-line
        row_html = await page.locator('tr[data-id="1"]').inner_html()
        print("row shows category:", 'Medical' in row_html)
        print("row shows subcategory:", 'Dentist' in row_html)

        # check persisted DB
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("persisted document:", persisted['documents'][0])

        # check detail modal
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        modal_text = await page.locator('.modal').inner_text()
        print("modal shows category/subcategory:", 'Medical / Dentist' in modal_text)

        # check sidecar
        sidecar = await page.evaluate("""
            (async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await filesDir.getFileHandle('1_subdoc.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        print("sidecar has Subcategory line:", 'Subcategory: Dentist' in sidecar)

        # search by subcategory alone should find it
        await page.fill('#search', 'Dentist')
        await page.wait_for_timeout(150)
        rows = await page.locator('#doc-tbody tr').count()
        print("rows found searching 'Dentist':", rows)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
