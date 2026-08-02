import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

FIELD_ROWS = [
    {"id": 1, "name": "Organization", "type": "text"},
    {"id": 2, "name": "Year", "type": "number"},
    {"id": 3, "name": "Date From", "type": "date"},
    {"id": 4, "name": "Paid", "type": "checkbox"},
]
TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Organization", "position": 0},
    {"document_type": "Invoice", "field_name": "Year", "position": 1},
    {"document_type": "Invoice", "field_name": "Date From", "position": 2},
    {"document_type": "Invoice", "field_name": "Paid", "position": 3},
    {"document_type": "Invoice", "field_name": "People", "position": 4},
]

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

        # === Capture a document of type "Invoice" -> all 4 generic fields + People should render ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('genfield.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 genfield")
        await page.set_input_files('#file-input', 'genfield.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Genfield Doc')
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)

        # verify correct input types rendered
        org_input_type = await page.locator('#f-field-1').get_attribute('type')
        year_input_type = await page.locator('#f-field-2').get_attribute('type')
        date_input_type = await page.locator('#f-field-3').get_attribute('type')
        paid_input_type = await page.locator('#f-field-4').get_attribute('type')
        print("input types (text, number, date, checkbox):", org_input_type, year_input_type, date_input_type, paid_input_type)

        # fill values -- Organization intentionally contains "&" to confirm it's NOT split
        await page.fill('#f-field-1', 'Dres. Ernestus & Cop, Sandhausen')
        await page.fill('#f-field-2', '2018')
        await page.fill('#f-field-3', '2018-05-01')
        await page.check('#f-field-4')
        await page.fill('#f-person', 'Arne')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        dfv = persisted['document_field_values']
        fields_by_id = {f['id']: f['name'] for f in persisted['fields']}
        print("document_field_values:", [(fields_by_id[r['field_id']], r['value']) for r in dfv])

        org_value = next(r['value'] for r in dfv if fields_by_id[r['field_id']] == 'Organization')
        print("Organization value NOT split (should contain full name with &):", org_value)

        # Table rows never show generic custom field values unless the field is
        # flagged show_as_column=1 in Field Settings (Organization here isn't) --
        # only the detail view (checked below) shows every custom field.
        row_text = await page.locator('tr[data-id="1"]').inner_text()
        print("row shows organization name (should be False -- not flagged as a column):", 'Dres. Ernestus & Cop, Sandhausen' in row_text)

        # detail modal shows formatted values (checkbox -> Yes, date -> readable)
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        modal_text = await page.locator('.modal').inner_text()
        print("modal shows Organization:", 'Organization' in modal_text and 'Ernestus' in modal_text)
        print("modal shows Paid as Yes:", 'Yes' in modal_text)
        print("modal shows formatted date (not raw ISO):", '2018' in modal_text and 'T00:00' not in modal_text)

        # search by generic field value
        await page.click('#modal-close-btn')
        await page.fill('#search', 'Sandhausen')
        await page.wait_for_timeout(150)
        search_rows = await page.locator('#doc-tbody tr').count()
        print("rows found searching generic field value 'Sandhausen':", search_rows)
        await page.fill('#search', '')

        # === Edit: change Organization and uncheck Paid ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)

        org_prefill = await page.locator('#e-field-1').input_value()
        paid_checked = await page.locator('#e-field-4').is_checked()
        print("edit form pre-filled organization:", org_prefill)
        print("edit form pre-filled Paid checkbox:", paid_checked)

        await page.fill('#e-field-1', 'New Organization Name')
        await page.uncheck('#e-field-4')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        dfv2 = {fields_by_id[r['field_id']]: r['value'] for r in persisted2['document_field_values']}
        print("after edit - Organization:", dfv2.get('Organization'))
        print("after edit - Paid (should be '0'):", dfv2.get('Paid'))
        print("document_field_values count after edit (should be 4, not accumulating dupes):", len(persisted2['document_field_values']))

        # sidecar reflects generic fields
        sidecar = await page.evaluate("""
            (async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await filesDir.getFileHandle('1_genfield.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        print("sidecar has updated Organization:", 'New Organization Name' in sidecar)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
