import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [
        {
            "id": 1, "title": "Insurance Policy", "category": "Finance", "document_type": "Policy",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [], "settings": [],
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)

        # === Scenario 1: the 'Reminder' field is auto-created for a fresh library
        # open, idempotently -- reopening doesn't duplicate or otherwise disturb it ===
        field_row = await page.evaluate("window.__DEBUG_findFieldByName('Reminder')")
        print("'Reminder' field auto-created with type 'reminder':", field_row is not None and field_row['type'] == 'reminder')

        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        field_row_after_reopen = await page.evaluate("window.__DEBUG_findFieldByName('Reminder')")
        print("re-opening the same library doesn't duplicate the field (same id):", field_row_after_reopen is not None and field_row_after_reopen['id'] == field_row['id'])

        # === Scenario 2: 'Reminder' is rejected as a name when creating a custom
        # field inline, matching the existing reserved-name behavior ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Policy')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        await page.fill('#f-new-field-name', 'Reminder')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(100)
        validation_text = await page.locator('#f-new-field-status').inner_text()
        print("'Reminder' is rejected as a reserved custom-field name:", 'reserved' in validation_text.lower() or 'Reminder' in validation_text)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 3: setDefaultReminder()/clearDefaultReminder() write/remove
        # the value correctly, in memory and persisted, and it participates in
        # checkReminders() exactly like any other reminder-type field ===
        result = await page.evaluate("""
            (async () => {
                await window.__DEBUG_setDefaultReminder(1, window.__DEBUG_todayIsoDate());
                const due = window.__DEBUG_checkReminders();
                const includesDoc1 = due.some(r => r.documentId === 1 && r.fieldName === 'Reminder');
                return { includesDoc1 };
            })()
        """)
        print("a default reminder due today is included by checkReminders():", result['includesDoc1'])

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        reminder_field_id = field_row['id']
        saved_value = next((v['value'] for v in persisted['document_field_values'] if v['document_id'] == 1 and v['field_id'] == reminder_field_id), None)
        print("the value is actually persisted to document_field_values:", saved_value is not None)

        await page.evaluate("window.__DEBUG_clearDefaultReminder(1)")
        await page.wait_for_timeout(100)
        result2 = await page.evaluate("""
            () => {
                const due = window.__DEBUG_checkReminders();
                const stillIncluded = due.some(r => r.documentId === 1 && r.fieldName === 'Reminder');
                return { stillIncluded };
            }
        """)
        print("clearDefaultReminder() and checkReminders() no longer includes it:", not result2['stillIncluded'])

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        saved_value_after_clear = next((v for v in persisted2['document_field_values'] if v['document_id'] == 1 and v['field_id'] == reminder_field_id), None)
        print("and the persisted row is actually gone, not just blanked:", saved_value_after_clear is None)

        # === Scenario 4: a document with a default reminder value shows it as an
        # orphaned, editable field in the Edit form, regardless of its type, since
        # 'Reminder' is never attached to document_type_fields ===
        await page.evaluate("window.__DEBUG_setDefaultReminder(1, window.__DEBUG_todayIsoDate())")
        await page.wait_for_timeout(100)
        await page.click(f'tr[data-id="1"]')
        await page.wait_for_timeout(150)
        await page.click('#edit-doc-btn')  # the detail panel's own Edit button, wired via actionIdByKey['edit'] = 'edit-doc-btn' in openDetail()
        await page.wait_for_timeout(150)
        orphaned_reminder = page.locator('[data-dynamic-field="Reminder"].field-orphaned')
        print("the Reminder field shows as an orphaned, editable field in Edit:", await orphaned_reminder.count() == 1)
        orphaned_input = orphaned_reminder.locator('input')
        orphaned_value = await orphaned_input.input_value()
        print("with the correct saved value pre-filled:", orphaned_value == await page.evaluate("window.__DEBUG_todayIsoDate()"))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
