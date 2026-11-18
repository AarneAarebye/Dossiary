import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# A plain custom field, deliberately NOT Payment method/Amount/Currency, to prove
# the show_as_column/autocomplete system genuinely generalizes -- any field can opt
# in via Field Settings, not just the ones migrateSentinelFieldsToGeneric() seeds.
FIELD_ROWS = [{"id": 1, "name": "Status", "type": "text"}]
# "Report" is configured with People (not Status) just so it counts as a "used
# type" for Field Settings without also pre-attaching Status -- Status needs to
# stay in the "available" Fields list (not already-configured) for its Column/
# Autocomplete checkboxes to be reachable in the first place.
TYPE_FIELD_ROWS = [{"document_type": "Report", "field_name": "People", "position": 0}]

async def read_db(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, {json.dumps(FIELD_ROWS)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
        await page.wait_for_timeout(150)
        toggle = '.fs-list-item[data-field="Status"] .fs-col-toggle'
        print("People has no Column checkbox:", await page.locator('.fs-list-item[data-field="People"] .fs-col-toggle').count() == 0)

        db0 = await read_db(page)
        vc0 = [r for r in db0['settings'] if r['key'] == 'visible_columns']
        print("no Status column before ticking:", await page.locator('th[data-field="field-1"]').count() == 0)
        print("visible_columns has no field-1 before ticking:", not vc0 or 'field-1' not in vc0[0]['value'])

        await page.check(toggle)
        await page.wait_for_timeout(200)
        print("ticking shows the column in the table:", await page.locator('th[data-field="field-1"]').is_visible())
        db1 = await read_db(page)
        vc1 = json.loads(next(r for r in db1['settings'] if r['key'] == 'visible_columns')['value'])
        print("visible_columns saved with field-1:", 'field-1' in vc1)
        print("visible_columns keeps the default columns:", all(c in vc1 for c in ['category', 'people', 'date', 'amount']))
        print("show_as_column saved in the same write:", next(f for f in db1['fields'] if f['name'] == 'Status')['show_as_column'] == 1)

        await page.uncheck(toggle)
        await page.wait_for_timeout(200)
        print("unticking removes the column from the table:", await page.locator('th[data-field="field-1"]').count() == 0)
        db2 = await read_db(page)
        vc2 = json.loads(next(r for r in db2['settings'] if r['key'] == 'visible_columns')['value'])
        print("visible_columns saved without field-1:", 'field-1' not in vc2)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
