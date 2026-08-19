import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

FILTER_UNSET = '__unset__'

# Doc 1: Amount 100, Currency EUR.
# Doc 2: Amount 250, Currency USD.
# Doc 3: Amount 500, Currency EUR.
# Doc 4: no Amount, no Currency saved at all (never had a
#        document_field_values row for either field).
# Doc 5: Amount explicitly saved as 0, Currency EUR -- real saved data,
#        must NOT match Amount's "not set" filter.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc 1 (100 EUR)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Doc 2 (250 USD)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-03-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Doc 3 (500 EUR)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-03-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 4, "title": "Doc 4 (no amount, no currency)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-04T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-03-04T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 5, "title": "Doc 5 (amount explicitly 0, EUR)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-05T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/5_e.pdf", "original_file_path": None,
            "created_at": "2026-03-05T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 2, "value": "100"},
        {"document_id": 1, "field_id": 3, "value": "EUR"},
        {"document_id": 2, "field_id": 2, "value": "250"},
        {"document_id": 2, "field_id": 3, "value": "USD"},
        {"document_id": 3, "field_id": 2, "value": "500"},
        {"document_id": 3, "field_id": 3, "value": "EUR"},
        {"document_id": 5, "field_id": 2, "value": "0"},
        {"document_id": 5, "field_id": 3, "value": "EUR"},
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

        # === Scenario 1: Currency's own capability checkboxes render in Field
        # Settings (unlike Amount's, which stay hidden), confirming the
        # capabilitiesHtml() exclusion was removed for Currency only ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        currency_col_checkbox = page.locator('.fs-list-item[data-field="Currency"] .fs-col-toggle')
        amount_col_checkbox = page.locator('.fs-list-item[data-field="Amount"] .fs-col-toggle')
        currency_checkbox_count = await currency_col_checkbox.count()
        amount_checkbox_count = await amount_col_checkbox.count()
        assert currency_checkbox_count == 1, "Currency should have a Column capability checkbox in Field Settings"
        assert amount_checkbox_count == 0, "Amount should still have NO capability checkboxes in Field Settings"
        print("Currency has a Column checkbox, Amount does not:", currency_checkbox_count, amount_checkbox_count)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 2: Currency column appears in the Columns menu, hidden
        # by default, and toggling it on shows the right per-row values ===
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        currency_toggle = page.locator('#columns-menu input[type=checkbox]', has=page.locator('xpath=following-sibling::*[contains(text(), "Currency")]'))
        # Simpler: locate by the field's column id directly, same convention
        # test_generic_column_system.py already uses for dynamic fields.
        currency_col_toggle = page.locator('#col-toggle-field-3')
        assert await currency_col_toggle.count() == 1, "Currency should appear in the Columns menu as field-3"
        assert not await currency_col_toggle.is_checked(), "Currency column should be hidden by default"
        await page.check('#col-toggle-field-3')
        await page.wait_for_timeout(150)
        await page.click('#columns-btn')  # close the menu
        await page.wait_for_timeout(100)
        currency_cell_texts = await page.evaluate(
            "() => Array.from(document.querySelectorAll('#doc-tbody tr td[data-field=\\'field-3\\']')).map(td => td.textContent.trim())"
        )
        print("Currency column cell values (rows in DOM order):", currency_cell_texts)
        assert 'EUR' in currency_cell_texts and 'USD' in currency_cell_texts, f"Currency column should show real values, got {currency_cell_texts}"

        # Sorting by the new Currency column works -- proves it flows through
        # the existing generic sortKey.startsWith('field-') mechanism
        # (sortDocs()) with zero new sort code, same as any other
        # show_as_column text field.
        await page.click('th[data-key="field-3"]')
        await page.wait_for_timeout(150)
        ids_after_first_click = await page.evaluate(
            "() => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)"
        )
        await page.click('th[data-key="field-3"]')  # click again to flip direction
        await page.wait_for_timeout(150)
        ids_after_second_click = await page.evaluate(
            "() => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)"
        )
        assert ids_after_first_click != ids_after_second_click, \
            f"Clicking the Currency header a second time should reverse sort order, got {ids_after_first_click} both times"
        print("Sorting by the Currency column works (order flips on second click):", ids_after_first_click, "->", ids_after_second_click)

        # === Scenario 3: Currency filter dropdown lists distinct values plus
        # "not set", and selecting a value narrows correctly ===
        eur_label = await option_label(page, '#dyn-filter-field-3', 'EUR')
        assert eur_label == 'EUR', f"Currency filter should list EUR as an option, got {eur_label!r}"
        not_set_label = await option_label(page, '#dyn-filter-field-3', FILTER_UNSET)
        assert not_set_label is not None, "Currency filter is missing a '__unset__'-valued option"
        print("Currency filter has EUR and a 'Not set' option:", eur_label, not_set_label)

        await page.select_option('#dyn-filter-field-3', 'EUR')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '3', '5'], f"Currency=EUR should show docs 1, 3, 5, got {ids}"
        print("Currency=EUR filter shows docs 1, 3, 5:", ids)

        await page.select_option('#dyn-filter-field-3', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['4'], f"Currency 'not set' should show only doc 4, got {ids}"
        print("Currency 'not set' filter shows only doc 4:", ids)

        # === Scenario 4: a Smart Collection saved with a Currency filter
        # active reproduces the same filtering on its own saved criteria ===
        await page.select_option('#dyn-filter-field-3', 'EUR')
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.wait_for_timeout(150)
        await page.fill('#smart-collection-name-input', 'EUR Only')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(200)
        await page.select_option('#dyn-filter-field-3', '')
        await page.wait_for_timeout(150)

        smart_collection_nav = page.locator('.nav-item[data-view^="collection-"]', has_text='EUR Only')
        await smart_collection_nav.click()
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '3', '5'], f"'EUR Only' Smart Collection should show docs 1, 3, 5, got {ids}"
        print("Smart Collection saved with a Currency filter correctly reproduces it:", ids)

        # === Scenario 5: Reports' breakdown-field dropdown does NOT list
        # Currency as an option (it's already the top-level grouping) ===
        await page.click('.nav-item[data-view="reports"]')
        await page.wait_for_timeout(200)
        breakdown_options = await page.evaluate(
            "() => Array.from(document.querySelector('#report-breakdown-field').options).map(o => o.textContent)"
        )
        assert 'Currency' not in breakdown_options, f"Currency should not be a Reports breakdown option, got {breakdown_options}"
        print("Reports breakdown dropdown correctly excludes Currency:", breakdown_options)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
