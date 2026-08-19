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

# A second, independent library ("library B") used by Scenario 11 below to
# reproduce the exact resetAll() bug report: neither of its two documents
# has any Amount/Currency field values at all, so if the Amount range
# filter's state (min/max/"not set") leaked across a library switch instead
# of being cleared by resetAll(), both documents would wrongly stay hidden
# after reopening this library.
LIBRARY_B_SEED = {
    "documents": [
        {
            "id": 1, "title": "Library B Doc 1", "category": "Misc", "document_type": "Note",
            "date": "2026-04-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-04-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Library B Doc 2", "category": "Misc", "document_type": "Note",
            "date": "2026-04-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-04-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
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

        # === Scenario 6: Amount range filter -- min only, max only, both,
        # and an empty-result min>max case. Filters composed here on top of
        # docs 1/2/3/5 (100/250/500/0, doc 4 has no Amount at all and is
        # correctly excluded from every range comparison below since NaN
        # never satisfies a >= / <= comparison) ===
        await page.click('.nav-item[data-view="all"]')
        await page.wait_for_timeout(150)

        await page.fill('#amount-filter-min', '200')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2', '3'], f"Amount min=200 should show docs 2, 3, got {ids}"
        print("Amount min=200 shows docs 2, 3:", ids)

        await page.fill('#amount-filter-min', '')
        await page.fill('#amount-filter-max', '200')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '5'], f"Amount max=200 should show docs 1, 5 (0 and 100), got {ids}"
        print("Amount max=200 shows docs 1, 5:", ids)

        await page.fill('#amount-filter-min', '100')
        await page.fill('#amount-filter-max', '300')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '2'], f"Amount 100-300 should show docs 1, 2, got {ids}"
        print("Amount range 100-300 shows docs 1, 2:", ids)

        await page.fill('#amount-filter-min', '300')
        await page.fill('#amount-filter-max', '100')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == [], f"Amount min>max should show zero results, got {ids}"
        print("Amount min=300/max=100 (min>max) correctly shows zero results:", ids)

        await page.fill('#amount-filter-min', '')
        await page.fill('#amount-filter-max', '')
        await page.wait_for_timeout(150)

        # === Scenario 7: "Amount not set" matches only doc 4 -- critically
        # NOT doc 5, whose Amount is explicitly saved as 0 (real data) ===
        await page.check('#amount-filter-unset')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['4'], f"Amount 'not set' should show only doc 4 (not doc 5, whose Amount=0 is real data), got {ids}"
        print("Amount 'not set' filter shows only doc 4, correctly excluding doc 5's explicit 0:", ids)

        min_disabled = await page.locator('#amount-filter-min').is_disabled()
        max_disabled = await page.locator('#amount-filter-max').is_disabled()
        assert min_disabled and max_disabled, "Min/max inputs should be disabled while 'not set' is checked"
        print("Min/max inputs disabled while 'not set' is checked:", min_disabled, max_disabled)

        # === Scenario 8: unchecking "not set" re-enables both inputs (its own
        # change handler), and typing into the now-enabled min input leaves
        # "not set" unchecked -- a disabled input can't be typed into in a
        # real browser at all, so there's no real-world path where typing
        # happens while the checkbox is still checked; this only exercises
        # the reachable case ===
        await page.uncheck('#amount-filter-unset')
        await page.wait_for_timeout(150)
        min_enabled = not await page.locator('#amount-filter-min').is_disabled()
        max_enabled = not await page.locator('#amount-filter-max').is_disabled()
        assert min_enabled and max_enabled, "Unchecking 'not set' should re-enable both inputs"
        print("Unchecking 'not set' re-enables both inputs:", min_enabled, max_enabled)

        await page.fill('#amount-filter-min', '100')
        await page.wait_for_timeout(150)
        unset_checked = await page.locator('#amount-filter-unset').is_checked()
        assert not unset_checked, "'Not set' should stay unchecked after typing into an enabled input"
        print("Typing into an enabled min input leaves 'not set' unchecked:", unset_checked)
        await page.fill('#amount-filter-min', '')
        await page.wait_for_timeout(150)

        # === Scenario 9: Currency filter AND Amount "not set" compose
        # correctly with plain AND -- no dedicated combo code exists, this
        # proves matchesCriteria()'s existing composition already covers it ===
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        await page.click('#columns-btn')  # Currency column already toggled on in Scenario 2; just closing any stray open menu state
        await page.wait_for_timeout(100)
        await page.select_option('#dyn-filter-field-3', 'EUR')
        await page.check('#amount-filter-unset')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == [], f"Currency=EUR AND Amount not set should show zero results (doc 4 has no Currency saved either), got {ids}"
        print("Currency=EUR AND Amount-not-set correctly composes to zero results:", ids)
        await page.select_option('#dyn-filter-field-3', '')
        await page.uncheck('#amount-filter-unset')
        await page.wait_for_timeout(150)

        # === Scenario 10: a Smart Collection saved with an Amount range
        # filter active reproduces the same filtering from its own saved
        # criteria on reopen -- mirrors Scenario 4's Currency Smart
        # Collection structure exactly, but for #amount-filter-min/
        # #amount-filter-max instead of the Currency dropdown ===
        await page.fill('#amount-filter-min', '100')
        await page.fill('#amount-filter-max', '300')
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.wait_for_timeout(150)
        await page.fill('#smart-collection-name-input', '100-300')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(200)
        await page.fill('#amount-filter-min', '')
        await page.fill('#amount-filter-max', '')
        await page.wait_for_timeout(150)

        amount_smart_collection_nav = page.locator('.nav-item[data-view^="collection-"]', has_text='100-300')
        await amount_smart_collection_nav.click()
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['1', '2'], f"'100-300' Smart Collection should show docs 1, 2, got {ids}"
        print("Smart Collection saved with an Amount range filter correctly reproduces it:", ids)

        # === Scenario 11: resetAll() clears the Amount filter's state (min,
        # max, "not set") when switching libraries -- reproduces the exact
        # reported bug: checking "Amount not set" in library A, then
        # switching to library B, used to leave the checkbox checked and
        # both inputs disabled, silently hiding every document in library B
        # (whose documents have no Amount value at all, so they'd all match
        # a leaked "not set" filter). #reload-btn ("Switch library") is the
        # real code path that calls resetAll() then openLibrary() -- the
        # same path a person actually uses to switch libraries -- and the
        # stub's showDirectoryPicker() returns whatever window.__TEST_ROOT
        # currently points at, so reassigning it here to a fresh, second
        # seeded root genuinely simulates picking a different folder. ===
        await page.click('.nav-item[data-view="all"]')
        await page.wait_for_timeout(150)
        await page.check('#amount-filter-unset')
        await page.wait_for_timeout(150)
        ids_before_switch = await visible_ids(page)
        assert ids_before_switch == ['4'], f"sanity check before switching libraries: expected only doc 4, got {ids_before_switch}"

        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(LIBRARY_B_SEED)});")
        await page.click('#reload-btn')
        await page.wait_for_timeout(400)

        min_value = await page.locator('#amount-filter-min').input_value()
        max_value = await page.locator('#amount-filter-max').input_value()
        unset_checked_after_switch = await page.locator('#amount-filter-unset').is_checked()
        min_disabled_after_switch = await page.locator('#amount-filter-min').is_disabled()
        max_disabled_after_switch = await page.locator('#amount-filter-max').is_disabled()
        assert min_value == '' and max_value == '', f"Amount min/max should be cleared after switching libraries, got min={min_value!r} max={max_value!r}"
        assert not unset_checked_after_switch, "'Amount not set' should be unchecked after switching libraries"
        assert not min_disabled_after_switch and not max_disabled_after_switch, "Amount min/max inputs should be re-enabled after switching libraries"
        print("Amount filter state (min, max, 'not set', disabled) is fully cleared after switching libraries:",
              min_value, max_value, unset_checked_after_switch, min_disabled_after_switch, max_disabled_after_switch)

        ids_after_switch = await visible_ids(page)
        assert ids_after_switch == ['1', '2'], f"Both library B documents should be visible after switching (filter cleared, not leaked), got {ids_after_switch}"
        print("Both library B documents are visible after switching libraries (Amount filter didn't leak):", ids_after_switch)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())

# === Second, independent scenario: the backfill migration
# (migrateCurrencyColumnDefault()) correctly flips Currency's
# show_as_column/autocomplete from 0/0 to 1/1 for a library that already
# ran the OLD migrateSentinelFieldsToGeneric() before this feature existed
# -- and, critically, does NOT re-flip it if a person already manually
# turned it back off in Field Settings after an earlier run of this same
# backfill (idempotency, same property migrateTextFieldsAutocompleteDefault()'s
# own test already covers for its own migration) ===
BACKFILL_SEED = {
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 0, "autocomplete": 0},
    ],
}

ALREADY_MIGRATED_BUT_MANUALLY_OFF_SEED = {
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 0, "autocomplete": 0},
    ],
    "settings": [
        {"key": "currency_column_default_migrated", "value": "1"},
    ],
}

async def read_db(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)

async def backfill_main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        errors = []

        # --- Case A: pre-migration shape, no marker row yet -- gets flipped ---
        # Reuses route_stub(), defined earlier in this same file for main()'s
        # own page -- no need to duplicate the routing/stub-loading logic here.
        page = await browser.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(BACKFILL_SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)
        persisted = await read_db(page)
        currency_field = next(f for f in persisted['fields'] if f['name'] == 'Currency')
        assert currency_field['show_as_column'] == 1 and currency_field['autocomplete'] == 1, \
            f"Currency should be backfilled to show_as_column=1, autocomplete=1, got {currency_field}"
        marker = next((s for s in persisted['settings'] if s['key'] == 'currency_column_default_migrated'), None)
        assert marker is not None and marker['value'] == '1', "Migration marker should be persisted after the backfill runs"
        print("Case A: pre-migration Currency field correctly backfilled to show_as_column=1, autocomplete=1:", currency_field)
        await page.close()

        # --- Case B: already migrated once, then manually turned back off --
        # a reopen must NOT silently re-enable it ---
        page2 = await browser.new_page()
        page2.on("pageerror", lambda exc: errors.append(str(exc)))
        await route_stub(page2)
        await page2.goto(f"file://{APP_PATH}")
        await page2.wait_for_timeout(200)
        await page2.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(ALREADY_MIGRATED_BUT_MANUALLY_OFF_SEED)});")
        await page2.click("#open-btn")
        await page2.wait_for_timeout(400)
        persisted2 = await read_db(page2)
        currency_field2 = next(f for f in persisted2['fields'] if f['name'] == 'Currency')
        assert currency_field2['show_as_column'] == 0, \
            f"A library already past the migration marker, with Currency manually turned back off, should stay off, got {currency_field2}"
        print("Case B: manually-turned-off Currency stays off across reopen (migration marker already present):", currency_field2)
        await page2.close()

        print("JS ERRORS (backfill scenarios):", errors)
        await browser.close()

asyncio.run(backfill_main())
