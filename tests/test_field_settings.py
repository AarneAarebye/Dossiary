import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

FIELD_ROWS = [
    {"id": 1, "name": "Organization", "type": "text"},
    {"id": 2, "name": "Year", "type": "number"},
]
TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Organization", "position": 0},
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

        # Capture a document of type "Invoice" so it's a "used" type
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('fsdoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 fsdoc")
        await page.set_input_files('#file-input', 'fsdoc.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'FS Test Doc')
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # === Open Field Settings ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        type_list_text = await page.locator('#fs-type-list').inner_text()
        print("Document Types list shows Invoice:", 'Invoice' in type_list_text)

        # Invoice should be auto-selected (first/only type); check columns
        available_text = await page.locator('#fs-available-list').inner_text()
        display_text = await page.locator('#fs-display-list').inner_text()
        print("Available fields shows Year (not yet shown for Invoice):", 'Year' in available_text)
        print("Available fields shows People:", 'People' in available_text)
        print("Display fields shows Organization (already configured):", 'Organization' in display_text)

        # Add "Year" to Display Fields
        await page.click('[data-field="Year"] .fs-add')
        await page.wait_for_timeout(150)
        display_text2 = await page.locator('#fs-display-list').inner_text()
        print("Display fields now shows Year after adding:", 'Year' in display_text2)

        # Verify persisted
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        invoice_fields = sorted([r['field_name'] for r in persisted['document_type_fields'] if r['document_type'] == 'Invoice'])
        print("persisted fields for Invoice:", invoice_fields)

        # Reorder: move Year up (should now be position 0, before Organization)
        await page.click('[data-field="Year"] .fs-up')
        await page.wait_for_timeout(150)
        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        invoice_rows = sorted([r for r in persisted2['document_type_fields'] if r['document_type'] == 'Invoice'], key=lambda r: r['position'])
        print("order after moving Year up:", [(r['field_name'], r['position']) for r in invoice_rows])

        # Remove Organization
        await page.click('[data-field="Organization"] .fs-remove')
        await page.wait_for_timeout(150)
        persisted3 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        invoice_fields3 = sorted([r['field_name'] for r in persisted3['document_type_fields'] if r['document_type'] == 'Invoice'])
        print("persisted fields for Invoice after removing Organization:", invoice_fields3)

        # === Set default document type ===
        await page.select_option('#fs-default-type', 'Invoice')
        await page.wait_for_timeout(150)
        persisted4 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        default_setting = [r for r in persisted4['settings'] if r['key'] == 'default_document_type']
        print("persisted default_document_type setting:", default_setting)

        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        # Open Add Document -- should now be pre-filled with "Invoice" and show Year field
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        prefilled_type = await page.locator('#f-type').input_value()
        print("Add Document form pre-filled type:", prefilled_type)
        year_field_present = await page.locator('[data-dynamic-field="Year"]').count()
        print("Year field auto-shown on open (from default type):", year_field_present)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
