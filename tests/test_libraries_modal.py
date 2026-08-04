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
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        # Should work even with NO library open at all
        link_visible = await page.locator('#libraries-link').is_visible()
        print("Libraries link visible with no library open:", link_visible)

        await page.click('#libraries-link')
        await page.wait_for_timeout(150)
        modal_text = await page.locator('.modal').inner_text()
        print("modal shows sql.js:", 'sql.js' in modal_text)
        print("modal shows Tesseract.js:", 'Tesseract.js' in modal_text)
        print("modal shows jsPDF:", 'jsPDF' in modal_text)
        print("modal shows pdf.js:", 'pdf.js' in modal_text)
        print("modal shows MIT:", 'MIT' in modal_text)
        print("modal shows Apache-2.0:", 'Apache-2.0' in modal_text)

        link_href = await page.locator('.modal a[href*="sql-js"]').get_attribute('href')
        print("sql.js link href:", link_href)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)
        modal_closed = await page.locator('.modal').count()
        print("modal closes correctly:", modal_closed == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
