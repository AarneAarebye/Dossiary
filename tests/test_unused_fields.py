import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Library check's "Unused fields" section: a custom field no non-deleted
# document has a value for is listed -- whether it's set up for no type at all,
# set up for some type (noted, since it may be deliberately prepared), or only
# still used by Waste-bin documents (noted too). Deleting removes the field and
# everything referring to it, including a Smart Collection's filter on it.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Live Doc", "category": None, "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Binned Doc", "category": None, "document_type": "Receipt",
            "date": "2026-03-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-03-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
    ],
    "tags": [], "document_tags": [],
    "people": [{"id": 1, "name": "Jana"}],
    "fields": [
        {"id": 1, "name": "Organization", "type": "text", "show_as_column": 0, "autocomplete": 1},  # used -- never listed
        {"id": 2, "name": "Legacy", "type": "text", "show_as_column": 1, "autocomplete": 0},        # A: no values, no type
        {"id": 3, "name": "Prepared", "type": "text", "show_as_column": 0, "autocomplete": 0},      # B: set up for Receipt, no values
        {"id": 4, "name": "Old Only", "type": "text", "show_as_column": 0, "autocomplete": 0},      # C: value only on a binned doc
        {"id": 5, "name": "Ghost Author", "type": "person", "show_as_column": 0, "autocomplete": 0},  # C: people only on a binned doc
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 1, "value": "Acme"},
        {"document_id": 2, "field_id": 4, "value": "stale"},
    ],
    "document_field_people": [{"document_id": 2, "field_id": 5, "person_id": 1}],
    "document_type_fields": [
        {"document_type": "Receipt", "field_name": "Organization", "position": 0},
        {"document_type": "Receipt", "field_name": "Prepared", "position": 1},
    ],
    "field_descriptions": [{"field_name": "Legacy", "description": "from Mariner"}],
    "settings": [{"key": "sort_key", "value": "field-2"}, {"key": "sort_dir", "value": "asc"}],
    "collections": [
        {"id": 1, "name": "Old stuff", "kind": "smart",
         "criteria": json.dumps({"q": "", "category": "", "type": "", "person": "", "showArchived": False,
                                 "dynamic": [{"label": "Old Only", "value": "stale"}, {"label": "Organization", "value": "Acme"}],
                                 "amountMin": "", "amountMax": "", "amountUnset": False})},
    ],
}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    await page.add_init_script(open('stub_studio2.js').read())

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
        dialogs = []
        dialog_mode = {'accept': True}
        async def on_dialog(d):
            dialogs.append(d.message)
            if dialog_mode['accept']: await d.accept()
            else: await d.dismiss()
        page.on("dialog", lambda d: asyncio.ensure_future(on_dialog(d)))
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Scenario 1: which fields are listed, with the right notes ===
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(400)
        section = page.locator('#unused-fields-section')
        print("Unused fields section is shown:", await section.count() == 1)
        names = await section.locator('.unused-field-row .doc-title').all_inner_texts()
        print("Exactly the unused custom fields are listed (A, B and C kinds):", sorted(names) == ['Ghost Author', 'Legacy', 'Old Only', 'Prepared'], names)
        print("A used field (Organization) is not listed:", 'Organization' not in names)
        print("Auto-created fields (People/Amount/Currency/Payment method/Reminder) are never listed:",
              not any(n in names for n in ['People', 'Amount', 'Currency', 'Payment method', 'Reminder']))
        note = lambda name: section.locator('.unused-field-row').filter(has_text=name).locator('.unused-field-notes')
        print("A field set up for a type says so:", await note('Prepared').inner_text() == 'Set up for: Receipt')
        print("A field only used by Waste-bin documents says so:",
              await note('Old Only').inner_text() == 'Only used by documents in the Waste bin'
              and await note('Ghost Author').inner_text() == 'Only used by documents in the Waste bin')
        print("A field with neither gets no note:", await note('Legacy').count() == 0)

        # === Scenario 2: cancelling the confirmation deletes nothing ===
        dialog_mode['accept'] = False
        await section.locator('.unused-field-row').filter(has_text='Legacy').locator('.unused-field-delete-btn').click()
        await page.wait_for_timeout(300)
        db0 = await read_db(page)
        print("Cancelling the confirmation keeps the field:", any(f['name'] == 'Legacy' for f in db0['fields']) and await section.locator('.unused-field-row').count() == 4)

        dialog_mode['accept'] = True

        # === Scenario 3: deleting one field removes it and everything about it ===
        dialogs.clear()
        await section.locator('.unused-field-row').filter(has_text='Legacy').locator('.unused-field-delete-btn').click()
        await page.wait_for_timeout(400)
        print("Confirmation names the field:", any('"Legacy"' in m for m in dialogs), dialogs)
        db1 = await read_db(page)
        print("Legacy's field row is gone:", not any(f['name'] == 'Legacy' for f in db1['fields']))
        print("...and its description:", not any(r['field_name'] == 'Legacy' for r in db1['field_descriptions']))
        sort_key = next((r['value'] for r in db1['settings'] if r['key'] == 'sort_key'), None)
        print("Sort on the deleted field's column falls back to Imported:", sort_key == 'import_date', sort_key)
        print("Its row disappears from the modal, others remain:", await section.locator('.unused-field-row').count() == 3)
        headers = await page.locator('#doc-thead-row th').all_inner_texts()
        print("Its table column is gone:", not any('Legacy' in h for h in headers))

        # === Scenario 4: "Delete all unused" removes the rest, naming the Smart Collection ===
        dialogs.clear()
        await section.locator('.unused-fields-delete-all-btn').click()
        await page.wait_for_timeout(400)
        print("Bulk confirmation counts the fields and names the affected Smart Collection:",
              any('3 unused fields' in m and 'Old stuff' in m for m in dialogs), dialogs)
        db2 = await read_db(page)
        remaining = sorted(f['name'] for f in db2['fields'])
        print("Only used and auto-created fields remain:", not any(n in remaining for n in ['Prepared', 'Old Only', 'Ghost Author']) and 'Organization' in remaining, remaining)
        print("Per-type setup for the deleted field is gone:", [r['field_name'] for r in db2['document_type_fields']] == ['Organization'] or all(r['field_name'] != 'Prepared' for r in db2['document_type_fields']))
        print("Waste-bin document's value for a deleted field is gone:", not any(r['field_id'] == 4 for r in db2['document_field_values']))
        print("...and its people for a deleted person-type field:", not any(r['field_id'] == 5 for r in db2['document_field_people']))
        print("The used field's value is untouched:", any(r['field_id'] == 1 and r['value'] == 'Acme' for r in db2['document_field_values']))
        criteria = json.loads(db2['collections'][0]['criteria'])
        print("Smart Collection keeps its other filter, loses only the deleted field's:", criteria['dynamic'] == [{"label": "Organization", "value": "Acme"}], criteria['dynamic'])
        in_memory = await page.evaluate("window.__DEBUG_getCustomFieldValue(2, 'Old Only')")
        print("Deleted field's value is gone from the in-memory document too:", in_memory is None, in_memory)
        print("Section disappears once everything is deleted:", await page.locator('#unused-fields-section').count() == 0)

        # === Scenario 5: reopening shows no unused fields ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(400)
        print("Reopening Library check lists no unused fields:", await page.locator('#unused-fields-section').count() == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
