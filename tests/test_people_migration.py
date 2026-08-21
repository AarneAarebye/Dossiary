import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# An "old-shape" library, exactly what a library predating
# migratePeopleToGenericField() looks like: people/document_people populated
# directly (as this app itself used to write, and as migrate_to_new_library.py in
# the sibling repo still does), no `fields` row for 'People' at all, and
# document_type_fields already using the literal 'People' sentinel string the way
# it always has -- see CLAUDE.md's note on why that string needs no migration of
# its own, only the fields/document_field_people promotion does.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Old Letter", "category": "Mail", "subcategory": None,
            "document_type": "Letter", "payment_method": None, "amount": None, "currency": None,
            "date": "2019-03-01", "import_date": "2019-03-01T09:00:00Z", "notes": None,
            "ocr_text": None, "ocr_language": None, "file_path": "files/1_old.pdf",
            "original_file_path": None, "created_at": "2019-03-01T09:00:00Z",
            "source": "migrated", "source_legacy_id": 7, "thumbnail_path": None,
        },
    ],
    "people": [{"id": 1, "name": "Arne"}, {"id": 2, "name": "Jana"}],
    "document_people": [
        {"document_id": 1, "person_id": 1},
        {"document_id": 1, "person_id": 2},
    ],
    "document_type_fields": [
        {"document_type": "Letter", "field_name": "People", "position": 0},
    ],
    "fields": [],
    "document_field_values": [],
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
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)

        # === 'People' promoted to a real fields row, type person ===
        people_field = next((f for f in persisted['fields'] if f['name'] == 'People'), None)
        print("People field created:", people_field is not None)
        print("People field type (should be person):", people_field['type'] if people_field else None)
        assert people_field is not None and people_field['type'] == 'person'

        # === document_field_people backfilled from the old document_people rows,
        # under this field's id ===
        field_id = people_field['id']
        links = [r for r in persisted['document_field_people'] if r['document_id'] == 1 and r['field_id'] == field_id]
        print("document_field_people backfilled (should be 2 links):", len(links))
        assert len(links) == 2

        # === Old document_people left untouched, vestigial (never dropped) ===
        print("old document_people still present (vestigial):", persisted['document_people'])
        assert len(persisted['document_people']) == 2

        # === document_type_fields' pre-existing 'People' sentinel needed no migration
        # of its own -- it already matches the newly-real field by name ===
        print("document_type_fields unchanged:", persisted['document_type_fields'])
        assert len(persisted['document_type_fields']) == 1

        # === Table row shows both people correctly ===
        row1 = await page.locator('tr[data-id="1"]').inner_html()
        print("row shows Arne pill:", 'Arne' in row1)
        print("row shows Jana pill:", 'Jana' in row1)

        # === Edit form shows People pre-filled from the migrated data ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        person_prefill = await page.locator('#dynamic-fields-e [data-dynamic-field="People"] input').input_value()
        print("edit form People pre-filled from migrated data:", person_prefill)
        assert set(n.strip() for n in person_prefill.split(',')) == {'Arne', 'Jana'}
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Idempotency: reopening the same (now-migrated) library doesn't create a
        # duplicate 'People' field or duplicate document_field_people rows ===
        await page.click('#reload-btn')
        await page.wait_for_timeout(400)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        people_fields_after = [f for f in persisted2['fields'] if f['name'] == 'People']
        print("exactly one People field after reopen:", len(people_fields_after))
        assert len(people_fields_after) == 1
        links_after = [r for r in persisted2['document_field_people'] if r['field_id'] == field_id]
        print("document_field_people count stable after reopen (should still be 2):", len(links_after))
        assert len(links_after) == 2

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
