import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, datetime
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

        # check preset value matches today
        date_value = await page.locator('#f-date').input_value()
        today = datetime.date.today().isoformat()
        print(f"preset date value: {date_value} (expected {today}): {date_value == today}")

        # check guess flag classes/hint present initially
        has_guess_class = await page.locator('#f-date').evaluate("el => el.classList.contains('field-guess')")
        hint_visible = await page.locator('#f-date-hint').is_visible()
        print("has guess styling initially:", has_guess_class)
        print("hint visible initially:", hint_visible)

        # simulate user touching/changing the field
        await page.fill('#f-date', '2020-05-15')
        await page.wait_for_timeout(100)

        has_guess_class_after = await page.locator('#f-date').evaluate("el => el.classList.contains('field-guess')")
        hint_visible_after = await page.locator('#f-date-hint').is_visible()
        print("has guess styling after edit:", has_guess_class_after)
        print("hint visible after edit:", hint_visible_after)

        # confirm the (now user-edited) date actually saves correctly
        with open('datepreset.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 datepreset")
        await page.set_input_files('#file-input', 'datepreset.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Date Test')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("saved date value:", persisted['documents'][0]['date'])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
