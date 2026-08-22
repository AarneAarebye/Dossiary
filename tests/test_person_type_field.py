import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Covers creating and using a brand new Person-type custom field (e.g. "Author") --
# the actual point of unifying People into the generic fields system: any number of
# independent, multi-valued person-list fields can now coexist, not just the one
# hardcoded People slot. See migratePeopleToGenericField()/renderPersonFieldHtml() in
# CLAUDE.md for the underlying mechanism.

TYPE_FIELD_ROWS = [
    {"document_type": "Book", "field_name": "People", "position": 0},
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
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Create a new "Author" field of type Person, inline from the capture form ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Book')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        await page.fill('#f-new-field-name', 'Author')
        await page.select_option('#f-new-field-type', 'person')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(150)

        author_input = page.locator('[data-dynamic-field="Author"] input')
        author_present = await author_input.count()
        print("Author field appears immediately after creation:", author_present)
        placeholder = await author_input.get_attribute('placeholder')
        print("Author input has a person-style placeholder:", placeholder)
        # wireCommaAutocomplete() removes the native list= attribute and replaces it
        # with its own comma-aware suggestion dropdown -- see test_comma_autocomplete.py
        # for real coverage of that mechanism, including on this exact Author field.
        list_attr = await author_input.get_attribute('list')
        assert list_attr is None, f"Author input should have its native list= attribute removed (comma-aware autocomplete replaces it), got {list_attr!r}"
        print("Author input's native list= attribute is removed (replaced by comma-aware autocomplete):", list_attr)

        # People (already configured for Book) should be present and untouched by adding Author.
        people_present = await page.locator('[data-dynamic-field="People"] input').count()
        print("People field still present after adding Author:", people_present)

        await page.fill('[data-dynamic-field="People"] input', 'Arne')
        await author_input.fill('Tolkien, Christopher Tolkien')
        await page.fill('#f-title', 'The Silmarillion')
        with open('book1.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 book1")
        await page.set_input_files('#file-input', 'book1.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # === Verify persisted state: Author and People are independent, correctly-keyed
        # document_field_people rows -- not merged, not cross-contaminated ===
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        author_field = next(f for f in persisted['fields'] if f['name'] == 'Author')
        people_field = next(f for f in persisted['fields'] if f['name'] == 'People')
        print("Author field type:", author_field['type'])
        author_links = [r for r in persisted['document_field_people'] if r['field_id'] == author_field['id']]
        people_links = [r for r in persisted['document_field_people'] if r['field_id'] == people_field['id']]
        print("Author has 2 linked people:", len(author_links) == 2)
        print("People has 1 linked person:", len(people_links) == 1)
        names_by_id = {p['id']: p['name'] for p in persisted['people']}
        author_names = sorted(names_by_id[r['person_id']] for r in author_links)
        print("Author names:", author_names)
        assert author_names == ['Christopher Tolkien', 'Tolkien']

        # === Detail view shows Author as its own pills section, separate from People ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        # .modal-section h3 is CSS text-transform:uppercase, so inner_text() reports
        # "AUTHOR" even though the actual DOM/source text is "Author" -- same quirk
        # test_people.py's own "People" section check already lives with.
        modal_text = await page.locator('#detail-panel-body').inner_text()
        print("detail shows Author section:", 'AUTHOR' in modal_text)
        print("detail shows both Author names:", 'Tolkien' in modal_text and 'Christopher Tolkien' in modal_text)
        print("detail shows Arne under People:", 'Arne' in modal_text)

        # === Search finds a document by its Author, not just People ===
        await page.fill('#search', 'Christopher')
        await page.wait_for_timeout(200)
        rows_for_author_search = await page.locator('#doc-tbody tr').count()
        print("searching an Author name finds the document (should be 1):", rows_for_author_search)
        await page.fill('#search', '')
        await page.wait_for_timeout(150)

        # === A second document's Author field autocompletes from the same person-list,
        # even though "Tolkien" only ever appeared as an Author, never as People ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Book')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        options = await page.locator('#person-list option').evaluate_all('opts => opts.map(o => o.value)')
        print("person-list datalist includes an Author-only name:", 'Tolkien' in options)

        print("JS ERRORS so far:", errors)
        await browser.close()

asyncio.run(main())
