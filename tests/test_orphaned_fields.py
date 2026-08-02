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
    {"document_type": "Certificate", "field_name": "Year", "position": 0},  # NOT Organization
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

        # Capture an Invoice with Organization filled in
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)

        # Capture form should NOT show orphaned fields (no existing values anyway)
        org_count_capture = await page.locator('[data-dynamic-field="Organization"]').count()
        print("Organization present in capture form for Invoice (should be 1, normally configured):", org_count_capture)
        orphaned_hint_capture = await page.locator('.field-orphaned-hint').count()
        print("orphaned hints in capture form (should be 0):", orphaned_hint_capture)

        await page.fill('#f-field-1', 'Acme Corp')
        await page.fill('#f-title', 'Invoice With Org')
        with open('orphandoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 orphandoc")
        await page.set_input_files('#file-input', 'orphandoc.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # Now edit this document and reclassify to Certificate (which does NOT have Organization configured)
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)

        await page.fill('#e-type', 'Certificate')
        await page.locator('#e-type').blur()
        await page.wait_for_timeout(150)

        # Organization should STILL show, but marked as orphaned
        org_field = page.locator('[data-dynamic-field="Organization"]')
        org_count_edit = await org_field.count()
        print("Organization present in edit form after reclassify to Certificate (should be 1, orphaned):", org_count_edit)
        has_orphaned_class = await org_field.evaluate("el => el.classList.contains('field-orphaned')")
        print("Organization field has 'field-orphaned' class:", has_orphaned_class)
        org_value = await page.locator('#e-field-1').input_value()
        print("Organization value preserved and shown:", org_value)
        hint_text = await page.locator('[data-dynamic-field="Organization"] .field-orphaned-hint').inner_text()
        print("orphaned hint text present:", len(hint_text) > 0)

        # Year (configured for Certificate) should show normally, NOT marked orphaned
        year_field = page.locator('[data-dynamic-field="Year"]')
        year_has_orphaned_class = await year_field.evaluate("el => el.classList.contains('field-orphaned')")
        print("Year field (normally configured) has orphaned class (should be False):", year_has_orphaned_class)

        # Edit the orphaned Organization value and save -- should persist the change
        await page.fill('#e-field-1', 'Updated Corp Name')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        fields_by_id = {f['id']: f['name'] for f in persisted['fields']}
        dfv = {fields_by_id[r['field_id']]: r['value'] for r in persisted['document_field_values']}
        print("Organization value after editing orphaned field:", dfv.get('Organization'))
        print("document_type after save:", persisted['documents'][0]['document_type'])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
