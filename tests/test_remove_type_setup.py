import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

# Field Settings' "Remove field setup" button and its sibling fix: a type no
# document uses can lose its whole setup in one click, and removing such a
# type's last field drops it from the type list straight away. Fields and
# values are never touched; a type typed into the form that opened the dialog
# (fsExtraType) stays listed while it has no fields.

import asyncio, json
from playwright.async_api import async_playwright

FIELD_ROWS = [
    {"id": 1, "name": "Organization", "type": "text"},
    {"id": 2, "name": "Year", "type": "number"},
]
TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Organization", "position": 0},
    {"document_type": "Retired", "field_name": "Organization", "position": 0},
    {"document_type": "Retired", "field_name": "Year", "position": 1},
    {"document_type": "Solo", "field_name": "Year", "position": 0},
]


async def read_db(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)


def rows_for(db, type_name):
    return sorted((r['position'], r['field_name']) for r in db['document_type_fields'] if r['document_type'] == type_name)


async def listed_types(page):
    return [s.strip() for s in await page.locator('#fs-type-list .fs-list-item').all_inner_texts()]


async def active_type(page):
    loc = page.locator('#fs-type-list .fs-list-item.active')
    return (await loc.inner_text()).strip() if await loc.count() else None


async def select_type(page, name):
    await page.click(f'#fs-type-list .fs-list-item[data-type="{name}"]')
    await page.wait_for_timeout(100)


async def remove_btn_count(page):
    return await page.locator('#fs-remove-setup-btn').count()


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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, {json.dumps(FIELD_ROWS)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # One document of type Invoice, with an Organization value, so Invoice is used.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('rmsetup.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 rmsetup")
        await page.set_input_files('#file-input', 'rmsetup.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Remove Setup Doc')
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.locator('[data-dynamic-field="Organization"] input').fill('ACME')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)
        db0 = await read_db(page)
        values_before = sorted(json.dumps(r, sort_keys=True) for r in db0['document_field_values'])
        print("seeded document saved with a field value:", len(values_before) == 1)

        # === Scenario 1: the button shows only for an unused type with fields ===
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        print("all three types listed:", await listed_types(page) == ['Invoice', 'Retired', 'Solo'])
        await select_type(page, 'Invoice')
        print("used type: no Remove field setup button:", await remove_btn_count(page) == 0)
        await select_type(page, 'Retired')
        print("unused type with fields: button shown:", await remove_btn_count(page) == 1)
        print("button text:", (await page.locator('#fs-remove-setup-btn').inner_text()).strip() == 'Remove field setup')
        hint = (await page.locator('#fs-type-actions .field-hint').inner_text()).strip()
        print("hint text:", hint == 'Only available for a document type with no documents. Fields and values are kept.')

        # === Scenario 2: pressing it removes the setup, nothing else ===
        await page.click('#fs-remove-setup-btn')
        await page.wait_for_timeout(200)
        print("Retired gone from the list at once:", await listed_types(page) == ['Invoice', 'Solo'])
        print("no type selected afterwards:", await active_type(page) is None)
        print("columns ask to select a type:", 'Select a document type' in await page.locator('#fs-display-list').inner_text())
        print("button gone:", await remove_btn_count(page) == 0)
        db1 = await read_db(page)
        print("Retired rows deleted:", rows_for(db1, 'Retired') == [])
        print("Invoice and Solo rows untouched:", rows_for(db1, 'Invoice') == [(0, 'Organization')] and rows_for(db1, 'Solo') == [(0, 'Year')])
        print("both fields kept:", sorted(f['name'] for f in db1['fields'] if f['name'] in ('Organization', 'Year')) == ['Organization', 'Year'])
        print("field values kept:", sorted(json.dumps(r, sort_keys=True) for r in db1['document_field_values']) == values_before)

        # === Scenario 3: removing the last field of an unused type drops it too ===
        await select_type(page, 'Solo')
        await page.click('#fs-display-list [data-field="Year"] .fs-remove')
        await page.wait_for_timeout(200)
        print("Solo gone from the list after its last field:", await listed_types(page) == ['Invoice'])
        print("no type selected after that:", await active_type(page) is None)
        db2 = await read_db(page)
        print("Solo rows deleted:", rows_for(db2, 'Solo') == [])

        # A used type keeps its place when its last field goes.
        await select_type(page, 'Invoice')
        await page.click('#fs-display-list [data-field="Organization"] .fs-remove')
        await page.wait_for_timeout(200)
        print("used type stays listed and selected:", await listed_types(page) == ['Invoice'] and await active_type(page) == 'Invoice')
        print("used type with no fields: no button:", await remove_btn_count(page) == 0)
        db3 = await read_db(page)
        print("Invoice rows now empty:", rows_for(db3, 'Invoice') == [])
        await page.click('#fs-available-list [data-field="Organization"] .fs-add')
        await page.wait_for_timeout(150)
        print("used type with a field again: still no button:", await remove_btn_count(page) == 0)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        # Reopening lists only the used type.
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        print("reopened: only Invoice listed:", await listed_types(page) == ['Invoice'])
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        # === Scenario 4: a brand-new type typed into the capture form ===
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        await page.fill('#f-title', 'Draft')
        await page.fill('#f-type', 'Brandnew')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(100)
        await page.click('#f-type-fields-btn')
        await page.wait_for_timeout(200)
        print("new type listed and selected:", 'Brandnew' in await listed_types(page) and await active_type(page) == 'Brandnew')
        print("new type without fields: no button:", await remove_btn_count(page) == 0)
        await page.click('#fs-available-list [data-field="Year"] .fs-add')
        await page.wait_for_timeout(150)
        print("new type with a field: button shown:", await remove_btn_count(page) == 1)
        await page.click('#fs-display-list [data-field="Year"] .fs-remove')
        await page.wait_for_timeout(200)
        print("new type stays listed and selected after its last field goes:",
              'Brandnew' in await listed_types(page) and await active_type(page) == 'Brandnew')
        print("its fields column still usable:", await page.locator('#fs-available-list [data-field="Year"] .fs-add').count() == 1)
        db4 = await read_db(page)
        print("no Brandnew rows left:", rows_for(db4, 'Brandnew') == [])
        await page.click('#fs-available-list [data-field="Year"] .fs-add')
        await page.wait_for_timeout(150)
        db5 = await read_db(page)
        print("field added again to the new type:", rows_for(db5, 'Brandnew') == [(0, 'Year')])
        await page.click('#fs-remove-setup-btn')
        await page.wait_for_timeout(200)
        print("new type gone after Remove field setup:", 'Brandnew' not in await listed_types(page))
        print("no type selected after removing the new type's setup:", await active_type(page) is None)
        db6 = await read_db(page)
        print("Brandnew rows deleted:", rows_for(db6, 'Brandnew') == [])
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(200)
        print("capture form still open with its typed title:", await page.locator('#f-title').input_value() == 'Draft')

        print("no JS errors:", errors == [], errors if errors else '')
        await browser.close()
    try:
        _os.remove('rmsetup.pdf')
    except OSError:
        pass

asyncio.run(main())
