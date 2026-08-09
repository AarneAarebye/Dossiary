import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

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

        # Create a document with initial tags/people/category
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('editdoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 editdoc")
        await page.set_input_files('#file-input', 'editdoc.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Original Title')
        await page.fill('#f-category', 'OldCategory')
        await page.fill('#f-subcategory', 'OldSub')
        await page.fill('#f-type', 'General')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('[data-dynamic-field="People"] input', 'Arne, Jana')
        await page.fill('#f-tags', 'oldtag1, oldtag2')
        await page.fill('#f-notes', 'original notes')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # Open detail, click Edit
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        edit_btn_present = await page.locator('#edit-doc-btn').count()
        print("Edit button present:", edit_btn_present)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)

        # Check form pre-filled with existing values
        title_val = await page.locator('#e-title').input_value()
        category_val = await page.locator('#e-category').input_value()
        subcategory_val = await page.locator('#e-subcategory').input_value()
        person_val = await page.locator('#dynamic-fields-e [data-dynamic-field="People"] input').input_value()
        tags_val = await page.locator('#e-tags').input_value()
        notes_val = await page.locator('#e-notes').input_value()
        print(f"Pre-filled: title={title_val!r} category={category_val!r} subcategory={subcategory_val!r}")
        print(f"  person={person_val!r} tags={tags_val!r} notes={notes_val!r}")

        # Edit: change category, remove Jana (keep Arne, add Lydia), remove oldtag2 (keep oldtag1, add newtag)
        await page.fill('#e-title', 'Updated Title')
        await page.fill('#e-category', 'NewCategory')
        await page.fill('#e-subcategory', 'NewSub')
        await page.fill('#dynamic-fields-e [data-dynamic-field="People"] input', 'Arne, Lydia')
        await page.fill('#e-tags', 'oldtag1, newtag')
        await page.fill('#e-notes', 'updated notes')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        # Should return to detail view showing updated values
        modal_text = await page.locator('.modal').inner_text()
        print("--- detail view after save ---")
        print(modal_text)

        # Verify persisted DB state
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("--- persisted documents ---")
        print(persisted['documents'][0])
        print("--- persisted people ---", persisted['people'])
        print("--- persisted document_field_people ---", persisted['document_field_people'])
        print("--- persisted tags ---", persisted['tags'])
        print("--- persisted document_tags ---", persisted['document_tags'])

        # Verify sidecar rewritten
        sidecar = await page.evaluate("""
            (async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await filesDir.getFileHandle('1_Original Title.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        print("--- sidecar after edit ---")
        print(sidecar)

        # Verify table row re-rendered with new values
        row_html = await page.locator('tr[data-id="1"]').inner_html()
        print("row shows Updated Title:", 'Updated Title' in row_html)
        print("row shows NewCategory:", 'NewCategory' in row_html)
        print("row shows NewSub:", 'NewSub' in row_html)
        print("row shows Lydia:", 'Lydia' in row_html)
        print("row shows Jana (should be False):", 'Jana' in row_html)
        print("row shows newtag:", 'newtag' in row_html)
        print("row shows oldtag2 (should be False):", 'oldtag2' in row_html)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
