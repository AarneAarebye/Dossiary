import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import re
import asyncio, json
from playwright.async_api import async_playwright

# Import a folder or earlier export: titles and strings (Task 1); the
# collection step is added to this file by later tasks.
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({documents: [], fields: []});")
        await page.click("#open-btn"); await page.wait_for_timeout(500)
        await page.click('#tools-btn')
        print("The Tools entry names earlier exports:", 'earlier export' in await page.inner_text('#import-folder-btn'))
        await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
        print("The dialog title names earlier exports:", 'earlier export' in await page.inner_text('.modal h2'))
        print("No page errors:", not errors, errors)

asyncio.run(main())
