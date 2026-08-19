import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: everything set (Category, Type, People, Status text field, Paid
#        checkbox checked) -- the baseline "nothing should match a 'not
#        set' filter" document.
# Doc 2: Category is blank -- the only document that should match the
#        Category "not set" filter.
# Doc 3: Type is blank, People has no one linked, Status was never saved,
#        and Paid was never saved either (no document_field_values row at
#        all for either custom field) -- the document every OTHER "not
#        set" filter (Type/People/Status/Paid) should match.
# Doc 4: Paid is explicitly saved as unchecked ('0') -- must NOT appear
#        under Paid's "not set" filter, since '0' is real saved data, not
#        a missing value. Category/Type/People/Status are all set on this
#        one so only the Paid check is actually being exercised.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc 1 (everything set)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Doc 2 (no category)", "category": None, "document_type": "Receipt",
            "date": "2026-03-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-03-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Doc 3 (no type, no people, no custom fields)", "category": "Travel", "document_type": None,
            "date": "2026-03-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-03-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 4, "title": "Doc 4 (Paid explicitly unchecked)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-04T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-03-04T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Status", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Paid", "type": "checkbox", "show_as_column": 1, "autocomplete": 0},
        {"id": 3, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 1, "value": "Open"},
        {"document_id": 1, "field_id": 2, "value": "1"},
        {"document_id": 4, "field_id": 1, "value": "Open"},
        {"document_id": 4, "field_id": 2, "value": "0"},
    ],
    "people": [
        {"id": 1, "name": "Alice"},
    ],
    "document_field_people": [
        {"document_id": 1, "field_id": 3, "person_id": 1},
        {"document_id": 4, "field_id": 3, "person_id": 1},
    ],
}

FILTER_UNSET = '__unset__'

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

async def visible_ids(page):
    return sorted(await page.evaluate(
        "() => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)"
    ))

async def option_label(page, select_id, value):
    return await page.evaluate(f"""
        () => {{
            const opts = Array.from(document.querySelector('{select_id}').options);
            const opt = opts.find(o => o.value === '{value}');
            return opt ? opt.textContent : null;
        }}
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

        # Dynamic custom-field filters (Status, Paid) only render into the
        # DOM behind a data-field-wrapped <span> that applyColumnVisibility()
        # hides unless that field's own COLUMN is toggled visible -- a
        # completely separate on/off switch from the filter dropdown itself
        # (dynamicColumnDefs() defaults every custom field's column to
        # defaultVisible:false, per dossiary.html's own dynamicColumnDefs()).
        # Toggle both on once, via the same Columns-menu checkbox flow
        # test_generic_column_system.py's own tests already use, before any
        # scenario below tries to interact with either dynamic filter.
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        await page.check('#col-toggle-field-1')  # Status
        await page.check('#col-toggle-field-2')  # Paid
        await page.wait_for_timeout(150)
        await page.click('#columns-btn')  # close the menu
        await page.wait_for_timeout(100)

        # === Scenario 1: the "not set" option exists, with the exact
        # expected value, in every filter dropdown (built-in and dynamic) ===
        category_label = await option_label(page, '#category-filter', FILTER_UNSET)
        assert category_label is not None, "Category filter is missing a '__unset__'-valued option"
        print(f"Category filter has a 'Not set' option: {category_label!r}")

        type_label = await option_label(page, '#type-filter', FILTER_UNSET)
        assert type_label is not None, "Type filter is missing a '__unset__'-valued option"
        print(f"Type filter has a 'Not set' option: {type_label!r}")

        person_label = await option_label(page, '#person-filter', FILTER_UNSET)
        assert person_label is not None, "Person filter is missing a '__unset__'-valued option"
        print(f"Person filter has a 'Not set' option: {person_label!r}")

        status_label = await option_label(page, '#dyn-filter-field-1', FILTER_UNSET)
        assert status_label is not None, "Status (dynamic text field) filter is missing a '__unset__'-valued option"
        print(f"Status filter has a 'Not set' option: {status_label!r}")

        paid_label = await option_label(page, '#dyn-filter-field-2', FILTER_UNSET)
        assert paid_label is not None, "Paid (dynamic checkbox field) filter is missing a '__unset__'-valued option"
        print(f"Paid filter has a 'Not set' option: {paid_label!r}")

        # === Scenario 2: Category "not set" matches only doc 2 ===
        await page.select_option('#category-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2'], f"Category 'not set' should show only doc 2, got {ids}"
        print("Category 'not set' filter shows only doc 2:", ids)
        await page.select_option('#category-filter', '')
        await page.wait_for_timeout(150)

        # === Scenario 3: Type "not set" matches only doc 3 ===
        await page.select_option('#type-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['3'], f"Type 'not set' should show only doc 3, got {ids}"
        print("Type 'not set' filter shows only doc 3:", ids)
        await page.select_option('#type-filter', '')
        await page.wait_for_timeout(150)

        # === Scenario 4: People "not set" matches only doc 3 (docs 1 and 4
        # both have Alice linked; doc 2 also has no People value seeded, so
        # confirm it's included too since this scenario isn't scoped by
        # Category) ===
        await page.select_option('#person-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2', '3'], f"People 'not set' should show docs 2 and 3, got {ids}"
        print("People 'not set' filter shows docs 2 and 3:", ids)
        await page.select_option('#person-filter', '')
        await page.wait_for_timeout(150)

        # === Scenario 5: Status (dynamic text field) "not set" matches
        # only doc 3 (docs 1 and 4 have it saved; doc 2 also has no Status
        # value seeded) ===
        await page.select_option('#dyn-filter-field-1', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2', '3'], f"Status 'not set' should show docs 2 and 3, got {ids}"
        print("Status 'not set' filter shows docs 2 and 3:", ids)
        await page.select_option('#dyn-filter-field-1', '')
        await page.wait_for_timeout(150)

        # === Scenario 6: Paid (dynamic checkbox field) "not set" matches
        # docs 2 and 3 -- critically, NOT doc 4, whose Paid is explicitly
        # '0' (unchecked), which is real saved data, not "unset" ===
        await page.select_option('#dyn-filter-field-2', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2', '3'], f"Paid 'not set' should show docs 2 and 3 (not doc 4, whose Paid=0 is real data), got {ids}"
        print("Paid 'not set' filter shows docs 2 and 3, correctly excluding doc 4's explicit '0':", ids)
        await page.select_option('#dyn-filter-field-2', '')
        await page.wait_for_timeout(150)

        # === Scenario 7: a Smart Collection saved with a "not set" filter
        # active reproduces the same filtering on its own saved criteria --
        # proving the shared matchesCriteria() path works for saved
        # criteria, not just the live toolbar select ===
        await page.select_option('#category-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.wait_for_timeout(150)
        await page.fill('#smart-collection-name-input', 'No Category')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(200)
        await page.select_option('#category-filter', '')
        await page.wait_for_timeout(150)

        smart_collection_nav = page.locator('.nav-item[data-view^="collection-"]', has_text='No Category')
        await smart_collection_nav.click()
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2'], f"'No Category' Smart Collection should show only doc 2, got {ids}"
        print("Smart Collection saved with a 'not set' filter correctly reproduces the same filtering:", ids)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
