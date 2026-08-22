import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

FIELD_ROWS = [
    {"id": 1, "name": "Existing", "type": "text"},
]
TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Existing", "position": 0},
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

        # === "+ Add a custom field" is hidden until a document type is entered --
        # exactly the empty-library gap this feature exists to close ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        wrap_visible_no_type = await page.locator('#f-add-field-wrap').is_visible()
        print("add-field control hidden with no type selected:", not wrap_visible_no_type)

        # A brand new type nobody's configured before (the "empty library" case) --
        # typed straight into the form, same as Document Type itself already works.
        await page.fill('#f-type', 'Warranty')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        wrap_visible_new_type = await page.locator('#f-add-field-wrap').is_visible()
        print("add-field control visible once a type is entered:", wrap_visible_new_type)

        toggle_label_before = await page.locator('#f-add-field-toggle').inner_text()
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        form_visible = await page.locator('#f-new-field-form').is_visible()
        currency_hint_visible = await page.locator('#f-new-field-currency-hint').is_visible()
        toggle_label_after = await page.locator('#f-add-field-toggle').inner_text()
        print("mini-form visible after clicking toggle:", form_visible)
        print("currency hint visible pointing at built-in Amount:", currency_hint_visible)
        print("toggle label before/after (should switch + to −):", toggle_label_before, '/', toggle_label_after)

        # Clicking again collapses it back, restoring the "+" label.
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        form_visible_after_collapse = await page.locator('#f-new-field-form').is_visible()
        toggle_label_collapsed = await page.locator('#f-add-field-toggle').inner_text()
        print("mini-form hidden after clicking toggle again:", not form_visible_after_collapse)
        print("toggle label back to +:", toggle_label_collapsed)

        await page.click('#f-add-field-toggle')  # re-open for the rest of the scenario
        await page.wait_for_timeout(100)

        # Reserved/built-in name is rejected.
        await page.fill('#f-new-field-name', 'Amount')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(100)
        reserved_status = await page.locator('#f-new-field-status').inner_text()
        print("rejects a built-in field name:", 'built-in' in reserved_status)

        # Create a genuinely new field ("Warranty Expiry", type date) for this type.
        await page.fill('#f-new-field-name', 'Warranty Expiry')
        await page.select_option('#f-new-field-type', 'date')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(150)
        new_field_present = await page.locator('[data-dynamic-field="Warranty Expiry"]').count()
        print("new field appears in the form immediately:", new_field_present == 1)
        # Payment method/Amount/Currency are pre-seeded fields now (see
        # migrateSentinelFieldsToGeneric()), so a freshly-created field's id isn't
        # a small fixed number anymore -- located by data-dynamic-field instead.
        new_field_input_type = await page.locator('[data-dynamic-field="Warranty Expiry"] input').get_attribute('type')
        print("new field rendered with the chosen type (date):", new_field_input_type)

        # Duplicate-name collision points at Field Settings instead of silently
        # creating a second field or attaching the existing one behind your back.
        await page.fill('#f-new-field-name', 'Warranty Expiry')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(100)
        dup_status = await page.locator('#f-new-field-status').inner_text()
        print("duplicate name points at Field Settings:", 'Manage fields' in dup_status)

        await page.fill('[data-dynamic-field="Warranty Expiry"] input', '2027-01-01')
        await page.fill('#f-title', 'Warranty Doc')
        with open('inlinefield.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 inlinefield")
        await page.set_input_files('#file-input', 'inlinefield.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        warranty_field = next(f for f in persisted['fields'] if f['name'] == 'Warranty Expiry')
        print("fields table has the new field:", warranty_field)
        print("document_type_fields attaches it to Warranty:", [r for r in persisted['document_type_fields'] if r['document_type'] == 'Warranty'])
        print("saved value:", [v for v in persisted['document_field_values'] if v['field_id'] == warranty_field['id']])

        # === Adding an inline field does NOT wipe out values already typed into
        # other, pre-existing dynamic fields on the same in-progress document ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('#f-field-1', 'Pre-existing value')
        await page.click('#f-add-field-toggle')
        await page.fill('#f-new-field-name', 'Second Field')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(150)
        preserved_value = await page.locator('#f-field-1').input_value()
        print("earlier field's typed value survives adding a new field:", preserved_value == 'Pre-existing value')
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Same in the Edit dialog, and its own in-session edits survive too ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        edit_wrap_visible = await page.locator('#e-add-field-wrap').is_visible()
        print("edit form shows add-field control for a document with a type:", edit_wrap_visible)
        await page.fill('[data-dynamic-field="Warranty Expiry"] input', '2028-06-15')  # change the existing Warranty Expiry value in-session
        await page.click('#e-add-field-toggle')
        await page.fill('#e-new-field-name', 'Notes Detail')
        await page.click('#e-new-field-btn')
        await page.wait_for_timeout(150)
        edit_new_field_present = await page.locator('[data-dynamic-field="Notes Detail"]').count()
        edit_preserved_value = await page.locator('[data-dynamic-field="Warranty Expiry"] input').input_value()
        print("new field appears in edit form:", edit_new_field_present == 1)
        print("in-session edit to existing field survives adding a new field:", edit_preserved_value == '2028-06-15')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
