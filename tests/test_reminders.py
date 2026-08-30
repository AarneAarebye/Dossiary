import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [
    {"document_type": "Policy", "field_name": "People", "position": 0},
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, []);")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)

        # === Scenario 1: creating a 'reminder'-type field inline behaves
        # identically to 'date' in every respect except the type stored ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Policy')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        await page.fill('#f-new-field-name', 'Renewal Date')
        reminder_option_present = await page.locator('#f-new-field-type option[value="reminder"]').count()
        print("Reminder option present in the type dropdown:", reminder_option_present == 1)
        await page.select_option('#f-new-field-type', 'reminder')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(100)

        renewal_input = page.locator('[data-dynamic-field="Renewal Date"] input')
        renewal_present = await renewal_input.count()
        print("Renewal Date field appears immediately after creation:", renewal_present == 1)
        input_type = await renewal_input.get_attribute('type')
        print("new reminder field renders as a native date input:", input_type == 'date')
        await renewal_input.fill('2026-03-15')
        await page.fill('#f-title', 'Insurance Policy Document')
        with open('policy1.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 policy1")
        await page.set_input_files('#file-input', 'policy1.pdf')
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
        field_row = next((f for f in persisted['fields'] if f['name'] == 'Renewal Date'), None)
        print("field persisted with type 'reminder':", field_row['type'] if field_row else None)
        value_row = next((v for v in persisted['document_field_values'] if v['field_id'] == field_row['id']), None)
        print("value persisted as a plain ISO date string:", value_row['value'] if value_row else None)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        displayed = await page.locator('#detail-panel-body').inner_text()
        print("detail panel shows the reminder field's value like any date field:", '2026' in displayed)

        # No Autocomplete checkbox, matching 'date' -- but the Column checkbox IS
        # offered (capabilitiesHtml()'s guard is exclusion-based: person + Amount
        # only, so 'reminder' gets it automatically like every other non-excluded type).
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.click('.fs-list-item:has-text("Policy")')
        await page.wait_for_timeout(150)
        reminder_item = page.locator('#fs-available-list .fs-field-item[data-field="Renewal Date"], #fs-display-list .fs-field-item[data-field="Renewal Date"]').first
        column_checkbox_present = await reminder_item.locator('.fs-col-toggle').count()
        autocomplete_checkbox_present = await reminder_item.locator('.fs-autocomplete-toggle').count()
        print("Column checkbox offered for a reminder field:", column_checkbox_present == 1)
        print("Autocomplete checkbox NOT offered for a reminder field:", autocomplete_checkbox_present == 0)

        # === Scenario 2: reminder_lookahead_days defaults to 30 when unset,
        # persists an explicit value, and survives a reopen ===
        lookahead_default = await page.evaluate("document.getElementById('fs-reminder-lookahead').value")
        print("reminder lookahead defaults to 30 with no persisted setting:", lookahead_default)  # set below, after opening Field Settings again

        await page.fill('#fs-reminder-lookahead', '14')
        await page.dispatch_event('#fs-reminder-lookahead', 'change')
        await page.wait_for_timeout(200)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        lookahead_row = next((s for s in persisted2['settings'] if s['key'] == 'reminder_lookahead_days'), None)
        print("reminder_lookahead_days persisted as '14':", lookahead_row['value'] if lookahead_row else None)

        # Reopen (same convention test_nav.py/test_recent_libraries.py use: re-seed
        # a fresh root with the setting already present, simulating a real reopen
        # reading the same on-disk library.sqlite back)
        seed_with_lookahead = {'document_type_fields': TYPE_FIELD_ROWS, 'settings': [{'key': 'reminder_lookahead_days', 'value': '14'}]}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_lookahead)}, []); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        lookahead_after_reopen = await page.evaluate("document.getElementById('fs-reminder-lookahead').value")
        print("reminder_lookahead_days reads back as '14' after reopening:", lookahead_after_reopen)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
