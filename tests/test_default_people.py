import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

# Field Settings > New documents > "Fill in People with the person adding the document" (1.69.0): the checkbox stores
# settings.default_people = 'adder' (empty when switched off). Only Dossiary for Mac and the iOS app know the person
# adding a document, so the page's own capture still leaves People empty.

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [{"document_type": "Report", "field_name": "People", "position": 0}]

async def read_db(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)

def setting(db, key):
    rows = [r for r in db.get('settings', []) if r['key'] == key]
    return rows[0]['value'] if rows else None

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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, []);")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        async def open_settings():
            await page.click('#tools-btn'); await page.click('#manage-fields-btn')
            await page.wait_for_timeout(150)

        async def close_settings():
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(150)

        await open_settings()
        box = '#fs-default-people'
        print("the checkbox is in New documents:", await page.locator(f'.fs-group:has(#fs-default-currency) {box}').count() == 1)
        print("off in a library without the setting:", not await page.is_checked(box))
        hint = await page.locator(f'.field:has({box}) .field-hint').inner_text()
        print("the hint says this browser leaves People empty:", "leaves People empty" in hint)

        await page.check(box)
        await page.wait_for_timeout(200)
        db1 = await read_db(page)
        print("ticking stores default_people = adder:", setting(db1, 'default_people') == 'adder')

        await close_settings(); await open_settings()
        print("still ticked when Field Settings opens again:", await page.is_checked(box))

        await page.uncheck(box)
        await page.wait_for_timeout(200)
        db2 = await read_db(page)
        print("unticking stores an empty value:", setting(db2, 'default_people') == '')
        await close_settings()

        # A value the page doesn't know (a later version's) reads as off.
        await page.evaluate("""(() => { db.run("UPDATE settings SET value = 'Arne' WHERE key = 'default_people'"); loadDefaultPeople(); })()""")
        await open_settings()
        print("another value reads as off:", not await page.is_checked(box))

        print("no JS errors:", errors == [])
        if errors: print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
