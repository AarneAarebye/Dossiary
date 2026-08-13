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
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('impdoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 impdoc")
        await page.set_input_files('#file-input', 'impdoc.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Import Date Test')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # default: import_date column should be VISIBLE (now that it's the default sort and needs a visible header)
        col_visible = await page.locator('th[data-field="import_date"]').is_visible()
        print("import_date column visible by default (should be True):", col_visible)

        # The column starts visible now (it's the default sort and needs a visible
        # header -- see above), so the Columns-menu checkbox starts checked too.
        # Exercise the toggle in both directions -- uncheck (hide), then re-check
        # (show) -- rather than a single check() that would now be a no-op.
        await page.click('#columns-btn')
        await page.wait_for_timeout(150)
        checkbox_exists = await page.locator('#col-toggle-import_date').count()
        print("Imported checkbox exists in columns menu:", checkbox_exists)
        await page.uncheck('#col-toggle-import_date')
        await page.wait_for_timeout(150)
        col_visible_after_uncheck = await page.locator('th[data-field="import_date"]').is_visible()
        print("import_date column hidden after unchecking:", not col_visible_after_uncheck)

        await page.check('#col-toggle-import_date')
        await page.wait_for_timeout(150)

        col_visible2 = await page.locator('th[data-field="import_date"]').is_visible()
        cell_visible = await page.locator('td[data-field="import_date"]').first.is_visible()
        print("import_date column visible after re-checking:", col_visible2)
        print("import_date cell visible after re-checking:", cell_visible)

        cell_text = await page.locator('td[data-field="import_date"]').first.inner_text()
        print("import_date cell text (should be a real date, not —):", cell_text)

        await page.click('body', position={'x': 10, 'y': 10})  # close columns dropdown first
        await page.wait_for_timeout(100)
        # sort by import_date column
        await page.click('th[data-key="import_date"]')
        await page.wait_for_timeout(150)
        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
