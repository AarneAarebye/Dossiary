import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc 1", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Organization", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 2, "name": "Organization To", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 3, "name": "Paid", "type": "checkbox", "show_as_column": 0, "autocomplete": 0},
        {"id": 4, "name": "Year", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 5, "name": "Date From", "type": "date", "show_as_column": 0, "autocomplete": 0},
        {"id": 6, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_type_fields": [
        {"document_type": "Receipt", "field_name": "Organization", "position": 0},
        {"document_type": "Receipt", "field_name": "Organization To", "position": 1},
        {"document_type": "Receipt", "field_name": "Paid", "position": 2},
        {"document_type": "Receipt", "field_name": "Year", "position": 3},
        {"document_type": "Receipt", "field_name": "Date From", "position": 4},
        {"document_type": "Receipt", "field_name": "Author", "position": 5},
    ],
    "field_descriptions": [],
}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    stub_js = open('stub_studio2.js').read()
    await page.add_init_script(stub_js)

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
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Scenario 1: field_descriptions table exists and starts empty ===
        persisted = await read_db(page)
        assert 'field_descriptions' in persisted, "field_descriptions table should exist after opening a library"
        print("field_descriptions table exists:", 'field_descriptions' in persisted)

        # === Scenario 2: Field Settings lists the five built-ins first, in order,
        # then every custom field (Organization, Organization To, Paid, Year, Date From, Author)
        # and the auto-created fields (Payment method, Amount, Currency, People) ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        names = await page.evaluate(
            "() => Array.from(document.querySelectorAll('#fs-descriptions-list .fs-description-item')).map(el => el.dataset.fieldName)"
        )
        # The five built-ins, plus the seeded fields, plus auto-created sentinel fields, plus the auto-created default Reminder field
        expected = ['Category', 'Subcategory', 'Document Type', 'Date', 'Tags',
                    'Organization', 'Organization To', 'Paid', 'Year', 'Date From', 'Author',
                    'Payment method', 'Amount', 'Currency', 'People', 'Reminder']
        assert names == expected, \
            f"unexpected field order, expected {expected}, got {names}"
        print("Field Descriptions lists built-ins then custom fields, in order:", names)

        # === Scenario 3: typing a description and blurring persists it ===
        org_input = page.locator('.fs-description-item[data-field-name="Organization"] .fs-description-input')
        await org_input.fill('Sender or origin of this document -- can be a person or organization')
        await page.locator('.fs-description-item[data-field-name="Organization To"] .fs-description-input').click()
        await page.wait_for_timeout(150)

        persisted2 = await read_db(page)
        saved = next((r for r in persisted2['field_descriptions'] if r['field_name'] == 'Organization'), None)
        assert saved is not None and saved['description'] == 'Sender or origin of this document -- can be a person or organization', \
            f"description not persisted correctly, got {saved}"
        print("Description persisted via blur:", saved)

        # === Scenario 4: reopening Field Settings shows the saved value ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        reopened_value = await page.locator('.fs-description-item[data-field-name="Organization"] .fs-description-input').input_value()
        assert reopened_value == 'Sender or origin of this document -- can be a person or organization', \
            f"reopened value mismatch, got {reopened_value!r}"
        print("Reopening Field Settings shows the saved description:", reopened_value)

        # === Scenario 5: setting a description for a built-in (Category) and a
        # custom field (Organization) shows the hint under each label in the
        # capture form; a field with no description shows no hint at all ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.locator('.fs-description-item[data-field-name="Category"] .fs-description-input').fill('Where this document belongs, e.g. Travel or Medical')
        await page.locator('.fs-description-item[data-field-name="Tags"] .fs-description-input').click()
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        await page.fill('#f-type', 'Receipt')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)

        category_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'f-category\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert category_hints == ['Where this document belongs, e.g. Travel or Medical'], f"Category hint missing or wrong, got {category_hints}"
        print("Category shows its description hint in the capture form:", category_hints)

        org_field = page.locator('[data-dynamic-field="Organization"]')
        org_hints = await org_field.locator('.field-hint').all_text_contents()
        assert org_hints == ['Sender or origin of this document -- can be a person or organization'], f"Organization hint missing or wrong, got {org_hints}"
        print("Organization (custom field) shows its description hint in the capture form:", org_hints)

        subcategory_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'f-subcategory\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert subcategory_hints == [], f"Subcategory should show no hint (no description set), got {subcategory_hints}"
        print("Subcategory shows no hint when no description is set:", subcategory_hints)

        # === Scenario 6: Document Type shows BOTH its existing built-in hint and
        # the new description hint, stacked, when a description is set for it ===
        # (Paid's description is set here too, early, purely so Scenario 7 below
        # -- which opens the edit form on the seeded document -- has a non-text
        # generic field description already saved to check; Scenario 8 re-fills
        # it with the same final text later when it exercises every other
        # generic field type in the capture form.)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.locator('.fs-description-item[data-field-name="Document Type"] .fs-description-input').fill('What kind of document this is')
        await page.locator('.fs-description-item[data-field-name="Paid"] .fs-description-input').fill('Whether this was already paid')
        await page.locator('.fs-description-item[data-field-name="Date"] .fs-description-input').click()
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        type_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'f-type\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert len(type_hints) == 2, f"Document Type should show two stacked hints (built-in + description), got {type_hints}"
        assert type_hints[1] == 'What kind of document this is', f"second Document Type hint should be the description, got {type_hints}"
        print("Document Type shows both its built-in hint and the new description hint, stacked:", type_hints)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 7: the same hints show correctly in the edit form too --
        # Category (a built-in), a non-text generic field type (the "Paid"
        # checkbox), and Document Type's own two-stacked-hints case, all
        # checked against the edit form, not just capture ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(300)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        edit_category_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'e-category\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert edit_category_hints == ['Where this document belongs, e.g. Travel or Medical'], f"edit-form Category hint missing or wrong, got {edit_category_hints}"
        print("Category shows its description hint in the edit form too:", edit_category_hints)

        edit_paid_hints = await page.locator('[data-dynamic-field="Paid"]').locator('.field-hint').all_text_contents()
        assert edit_paid_hints == ['Whether this was already paid'], f"edit-form Paid (checkbox) hint missing or wrong, got {edit_paid_hints}"
        print("Paid (a non-text generic field type) shows its description hint in the edit form too:", edit_paid_hints)

        edit_type_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'e-type\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert len(edit_type_hints) == 2, f"edit-form Document Type should show two stacked hints (built-in + description), got {edit_type_hints}"
        assert edit_type_hints[1] == 'What kind of document this is', f"second edit-form Document Type hint should be the description, got {edit_type_hints}"
        print("Document Type shows both stacked hints in the edit form too:", edit_type_hints)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 8: a generic field of every type (checkbox, number, date,
        # person -- text is already covered by Organization in Scenario 5) shows
        # its description hint correctly, proving renderGenericFieldHtml()'s
        # checkbox branch, its text/number/date branch, and renderPersonFieldHtml()
        # all got the same treatment ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.locator('.fs-description-item[data-field-name="Paid"] .fs-description-input').fill('Whether this was already paid')
        await page.locator('.fs-description-item[data-field-name="Year"] .fs-description-input').fill('The tax year this applies to')
        await page.locator('.fs-description-item[data-field-name="Date From"] .fs-description-input').fill('Start of the period this covers')
        await page.locator('.fs-description-item[data-field-name="Author"] .fs-description-input').fill('Who wrote or created this document')
        await page.locator('.fs-description-item[data-field-name="Category"] .fs-description-input').click()  # blur the last input
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        await page.fill('#f-type', 'Receipt')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)

        for field_name, expected in [
            ('Paid', 'Whether this was already paid'),
            ('Year', 'The tax year this applies to'),
            ('Date From', 'Start of the period this covers'),
            ('Author', 'Who wrote or created this document'),
        ]:
            hints = await page.locator(f'[data-dynamic-field="{field_name}"]').locator('.field-hint').all_text_contents()
            assert hints == [expected], f"{field_name} hint missing or wrong, got {hints}"
            print(f"{field_name} shows its description hint in the capture form:", hints)

        # === Scenario 9: description text is never run through t() -- a
        # description containing a literal "{label}" (which would be silently
        # substituted or replaced if it were passed to t() with a params object,
        # the way translated strings are) renders completely verbatim ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        literal_text = 'Not a real placeholder: {label} stays exactly as typed'
        await page.locator('.fs-description-item[data-field-name="Organization To"] .fs-description-input').fill(literal_text)
        await page.locator('.fs-description-item[data-field-name="Category"] .fs-description-input').click()
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        await page.fill('#f-type', 'Receipt')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        org_to_hints = await page.locator('[data-dynamic-field="Organization To"]').locator('.field-hint').all_text_contents()
        assert org_to_hints == [literal_text], f"literal-braces description was altered, got {org_to_hints}"
        print("Description containing a literal '{label}' renders verbatim, not run through t():", org_to_hints)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 10: field_descriptions table also exists for a brand new
        # library (initNewLibrary(), not just an existing/seeded one reopened
        # via loadDb()) -- same assertion shape as Scenario 1, against a fresh
        # empty folder taken through the "initialize new library" prompt ===
        new_page = await browser.new_page()
        await route_stub(new_page)
        await new_page.goto(f"file://{APP_PATH}")
        await new_page.wait_for_timeout(200)
        await new_page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await new_page.click("#open-btn")
        await new_page.wait_for_timeout(200)
        await new_page.click("#init-btn")
        await new_page.wait_for_timeout(200)
        new_lib_persisted = await read_db(new_page)
        assert 'field_descriptions' in new_lib_persisted, "field_descriptions table should exist for a brand new library too"
        print("field_descriptions table exists for a brand new library:", 'field_descriptions' in new_lib_persisted)
        await new_page.close()

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
