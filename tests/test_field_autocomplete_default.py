import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# A library that pre-dates migrateTextFieldsAutocompleteDefault() -- a real text
# field that was never touched in Field Settings, so autocomplete is still 0.
SEED = {
    "fields": [
        {"id": 1, "name": "Existing Text", "type": "text", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_type_fields": [
        {"document_type": "Invoice", "field_name": "Existing Text", "position": 0},
    ],
}

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        async def read_db():
            return await page.evaluate("""
                (async () => {
                    const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                    const f = await fh.getFile();
                    return JSON.parse(await f.text());
                })()
            """)

        # === Opening an existing library retroactively flips Autocomplete on for
        # every already-existing text-type field (migrateTextFieldsAutocompleteDefault()) ===
        persisted = await read_db()
        existing_field = next(f for f in persisted['fields'] if f['name'] == 'Existing Text')
        print("pre-existing text field's autocomplete flipped on by migration (should be 1):", existing_field['autocomplete'])
        migration_marker = next((s for s in persisted['settings'] if s['key'] == 'text_autocomplete_default_migrated'), None)
        print("migration marker persisted:", migration_marker)

        # The form input actually carries the generated datalist attribute now.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        list_attr = await page.locator('[data-dynamic-field="Existing Text"] input').get_attribute('list')
        print("pre-existing text field's input has a datalist attr:", list_attr)

        # === A newly-created inline TEXT field defaults to Autocomplete on ===
        await page.click('#f-add-field-toggle')
        await page.fill('#f-new-field-name', 'New Text Field')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(150)

        # === A newly-created inline NUMBER field does NOT get Autocomplete ===
        # (mini-form stays open after adding a field -- no need to re-toggle it)
        await page.fill('#f-new-field-name', 'New Number Field')
        await page.select_option('#f-new-field-type', 'number')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        persisted2 = await read_db()
        new_text_field = next(f for f in persisted2['fields'] if f['name'] == 'New Text Field')
        new_number_field = next(f for f in persisted2['fields'] if f['name'] == 'New Number Field')
        print("new inline TEXT field defaults to autocomplete=1:", new_text_field['autocomplete'])
        print("new inline NUMBER field does not get autocomplete (should be 0):", new_number_field['autocomplete'])

        # === Manually turning Autocomplete back off for a field in Field Settings
        # is respected -- reopening the (already-migrated) library must not silently
        # flip it back on ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.uncheck('.fs-list-item[data-field="Existing Text"] .fs-autocomplete-toggle')
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        persisted3 = await read_db()
        turned_off_field = next(f for f in persisted3['fields'] if f['name'] == 'Existing Text')
        print("manually turning autocomplete off persists (should be 0):", turned_off_field['autocomplete'])

        await page.click('#reload-btn')
        await page.wait_for_timeout(400)

        persisted4 = await read_db()
        after_reopen_field = next(f for f in persisted4['fields'] if f['name'] == 'Existing Text')
        print("manual override survives reopening the already-migrated library (should stay 0):", after_reopen_field['autocomplete'])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
