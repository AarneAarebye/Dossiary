import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

# People is a plain person-type `fields` row now (see migratePeopleToGenericField()),
# not a hardcoded sentinel -- its input lives at the same [data-dynamic-field="People"]
# input selector any other dynamic field would use, not a fixed #f-person/#e-person id.
PEOPLE_INPUT_F = '[data-dynamic-field="People"] input'
PEOPLE_INPUT_E = '#dynamic-fields-e [data-dynamic-field="People"] input'

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
        type_field_rows = [{'document_type': 'General', 'field_name': 'People', 'position': 0}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({type_field_rows!r}, []);")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

        # Document 1: two people
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('doc1.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 doc1")
        await page.set_input_files('#file-input', 'doc1.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Family Letter')
        await page.fill('#f-type', 'General')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill(PEOPLE_INPUT_F, 'Arne, Jana')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # Document 2: one overlapping person (Arne, should be REUSED not duplicated) + one new
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('doc2.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 doc2")
        await page.set_input_files('#file-input', 'doc2.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Solo Doc')
        await page.fill('#f-type', 'General')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill(PEOPLE_INPUT_F, 'Arne')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # check persisted state: exactly 2 people (Arne, Jana), not 3, and the People
        # field's own document_field_people rows (not the vestigial document_people
        # table -- see CLAUDE.md's migratePeopleToGenericField() note) reflect them.
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("people table:", persisted['people'])
        people_field = next(f for f in persisted['fields'] if f['name'] == 'People')
        print("People field type (should be person):", people_field['type'])
        print("document_field_people links:", persisted['document_field_people'])
        print("document_people is untouched/empty (vestigial, never written by the app):", persisted['document_people'])
        assert len(persisted['people']) == 2, f"expected 2 people, got {persisted['people']}"
        assert all(row['field_id'] == people_field['id'] for row in persisted['document_field_people'])

        # check table rendering shows pills for both people on row 1
        row1_html = await page.locator('tr[data-id="1"]').inner_html()
        print("row 1 shows Arne pill:", 'Arne' in row1_html)
        print("row 1 shows Jana pill:", 'Jana' in row1_html)

        # check person filter dropdown has exactly Arne and Jana (deduped, not 'Arne, Jana' as one option)
        filter_options = await page.locator('#person-filter option').all_inner_texts()
        print("person filter options:", filter_options)

        # filter by "Arne" -- should show BOTH documents (since Arne appears in both)
        await page.select_option('#person-filter', 'Arne')
        await page.wait_for_timeout(150)
        rows_for_arne = await page.locator('#doc-tbody tr').count()
        print("rows when filtering by Arne (should be 2):", rows_for_arne)

        # filter by "Jana" -- should show only 1 document
        await page.select_option('#person-filter', 'Jana')
        await page.wait_for_timeout(150)
        rows_for_jana = await page.locator('#doc-tbody tr').count()
        print("rows when filtering by Jana (should be 1):", rows_for_jana)

        # reset filter, open detail modal for doc 1, check People section shows both pills
        await page.select_option('#person-filter', '')
        await page.wait_for_timeout(100)
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        modal_text = await page.locator('#detail-panel-body').inner_text()
        print("modal shows 'People' section:", 'People' in modal_text)
        print("modal shows both names:", 'Arne' in modal_text and 'Jana' in modal_text)

        # check sidecar for doc1
        sidecar = await page.evaluate("""
            (async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await filesDir.getFileHandle('1_Family Letter.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        print("--- sidecar for doc1 ---")
        print(sidecar)

        # === Edit: clear People via the clear button, confirm it saves as empty ===
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        people_value_before_edit = await page.locator(PEOPLE_INPUT_E).input_value()
        print("edit form pre-fills People:", people_value_before_edit)
        await page.click('[data-dynamic-field="People"] .clear-btn')
        await page.fill(PEOPLE_INPUT_E, 'Arne, Ben')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("people table after edit (should now include Ben, still 3 total):", persisted2['people'])
        assert len(persisted2['people']) == 3, f"expected 3 people after adding Ben, got {persisted2['people']}"

        print("JS ERRORS:", errors)
        for fn in ('doc1.pdf', 'doc2.pdf'):
            if _os.path.exists(fn):
                _os.remove(fn)
        await browser.close()

asyncio.run(main())
