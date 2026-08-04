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
        with open('canceldoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 canceldoc")
        await page.set_input_files('#file-input', 'canceldoc.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Keep This Title')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-title', 'Should Not Be Saved')
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(200)

        modal_text = await page.locator('.modal').inner_text()
        print("shows original title after cancel:", 'Keep This Title' in modal_text)
        print("shows discarded edit (should be False):", 'Should Not Be Saved' in modal_text)

        row_html = await page.locator('tr[data-id="1"]').inner_html()
        print("row still shows original title:", 'Keep This Title' in row_html)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
