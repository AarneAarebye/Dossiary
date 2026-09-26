import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Renaming a custom field in Field Settings: everything keyed by the field's
# *name* must move with it -- fields.name, document_type_fields, field
# descriptions, Smart Collection criteria, and every document's in-memory
# customFields/personFieldValues -- while name-dependent built-ins stay locked.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Invoice Acme", "category": "Bills", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Letter Other", "category": "Bills", "document_type": "Receipt",
            "date": "2026-03-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-03-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "people": [{"id": 1, "name": "Jana"}],
    "fields": [
        {"id": 1, "name": "Organization", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Year", "type": "number", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 1, "value": "Acme GmbH"},
        {"document_id": 2, "field_id": 1, "value": "Someone Else"},
    ],
    "document_field_people": [{"document_id": 1, "field_id": 2, "person_id": 1}],
    "document_type_fields": [
        {"document_type": "Receipt", "field_name": "Organization", "position": 0},
        {"document_type": "Receipt", "field_name": "Author", "position": 1},
    ],
    "field_descriptions": [{"field_name": "Organization", "description": "Who sent it"}],
    "collections": [
        {"id": 1, "name": "Acme docs", "kind": "smart",
         "criteria": json.dumps({"q": "", "category": "", "type": "", "person": "", "showArchived": False,
                                 "dynamic": [{"label": "Organization", "value": "Acme GmbH"}],
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

def row_for(page_desc_item_name):
    return f'.fs-description-item[data-field-name="{page_desc_item_name}"]'

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Scenario 1: rename buttons only on renameable custom fields ===
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        has_btn = lambda name: page.locator(f'{row_for(name)} .fs-rename').count()
        print("Organization/Author/Year each get a rename button:",
              await has_btn('Organization') == 1 and await has_btn('Author') == 1 and await has_btn('Year') == 1)
        locked = [await has_btn(n) for n in ['People', 'Amount', 'Currency', 'Payment method', 'Category', 'Date']]
        print("Built-ins and name-dependent fields (People/Amount/Currency/Payment method/Category/Date) get none:", locked == [0] * 6, locked)

        # === Scenario 2: invalid names are rejected with a reason, nothing changes ===
        async def try_rename(old, new, key='Enter'):
            await page.click(f'{row_for(old)} .fs-rename')
            await page.fill(f'{row_for(old)} .fs-rename-input', new)
            await page.press(f'{row_for(old)} .fs-rename-input', key)
            await page.wait_for_timeout(200)

        await try_rename('Organization', 'Year')
        status = await page.locator(f'{row_for("Organization")} .fs-rename-status').inner_text()
        print("Renaming to an existing field's name is rejected:", 'already exists' in status, repr(status))
        await page.fill(f'{row_for("Organization")} .fs-rename-input', 'Amount')
        await page.press(f'{row_for("Organization")} .fs-rename-input', 'Enter')
        await page.wait_for_timeout(200)
        status = await page.locator(f'{row_for("Organization")} .fs-rename-status').inner_text()
        print("Renaming to a built-in name is rejected:", 'built-in' in status, repr(status))
        await page.fill(f'{row_for("Organization")} .fs-rename-input', '   ')
        await page.press(f'{row_for("Organization")} .fs-rename-input', 'Enter')
        await page.wait_for_timeout(200)
        status = await page.locator(f'{row_for("Organization")} .fs-rename-status').inner_text()
        print("Renaming to a blank name is rejected:", status == 'Enter a field name.', repr(status))

        # Escape cancels without closing the Field Settings modal.
        await page.press(f'{row_for("Organization")} .fs-rename-input', 'Escape')
        await page.wait_for_timeout(200)
        print("Escape cancels the rename but leaves Field Settings open:",
              await page.locator('#fs-descriptions-list').count() == 1 and await page.locator(f'{row_for("Organization")} .fs-rename-input').count() == 0)
        db_before = await read_db(page)
        print("Nothing was renamed by the rejected/cancelled attempts:", any(f['name'] == 'Organization' for f in db_before['fields']))

        # === Scenario 3: a valid rename carries every name-keyed reference ===
        await try_rename('Organization', 'Correspondent')
        print("Row now shows the new name:", await page.locator(row_for('Correspondent')).count() == 1 and await page.locator(row_for('Organization')).count() == 0)
        db_after = await read_db(page)
        field1 = next(f for f in db_after['fields'] if f['id'] == 1)
        print("fields.name updated, id unchanged:", field1['name'] == 'Correspondent')
        dtf_names = sorted(r['field_name'] for r in db_after['document_type_fields'])
        print("document_type_fields updated:", dtf_names == ['Author', 'Correspondent'], dtf_names)
        desc = {r['field_name']: r['description'] for r in db_after['field_descriptions']}
        print("Field description moved to the new name:", desc.get('Correspondent') == 'Who sent it' and 'Organization' not in desc, desc)
        criteria = json.loads(db_after['collections'][0]['criteria'])
        print("Smart Collection criteria now reference the new name:", criteria['dynamic'] == [{"label": "Correspondent", "value": "Acme GmbH"}], criteria['dynamic'])
        custom = await page.evaluate("window.__DEBUG_getCustomFieldValue(1, 'Correspondent')")
        old_custom = await page.evaluate("window.__DEBUG_getCustomFieldValue(1, 'Organization')")
        print("In-memory document values follow the rename:", custom == 'Acme GmbH' and old_custom is None, custom, old_custom)

        # Field Settings' per-type columns show the new name once a type is selected.
        await page.click('#fs-type-list .fs-list-item[data-type="Receipt"]')
        await page.wait_for_timeout(150)
        print("Display Fields column lists the new name:", await page.locator('#fs-display-list .fs-field-item[data-field="Correspondent"]').count() == 1)

        # === Scenario 4: a person-type field renames too, values intact ===
        await try_rename('Author', 'Writer')
        db_after2 = await read_db(page)
        print("Person-type field renamed in the database:", any(f['id'] == 2 and f['name'] == 'Writer' for f in db_after2['fields']))
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 5: the rest of the app sees the new name ===
        header_texts = await page.locator('#doc-thead-row th').all_inner_texts()
        print("Table column header shows the new name:", any('Correspondent' in h for h in header_texts), header_texts)
        await page.click('#nav-collections-list .nav-item >> text=Acme docs')
        await page.wait_for_timeout(200)
        rows = await page.locator('#doc-tbody tr[data-id]').evaluate_all("rows => rows.map(r => Number(r.dataset.id))")
        print("Smart Collection still matches after the rename:", rows == [1], rows)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.click('#doc-tbody tr[data-id="1"]')
        await page.wait_for_timeout(200)
        panel = await page.locator('#detail-panel-body').inner_text()
        print("Detail panel shows the value under the new name:", 'Correspondent' in panel and 'Acme GmbH' in panel and 'Organization' not in panel)
        print("...and the renamed person-type field keeps its people:", 'WRITER' in panel.upper() and 'Jana' in panel and 'AUTHOR' not in panel.upper())

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
