import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# A plain custom field, deliberately NOT Payment method/Amount/Currency, to prove
# the show_as_column/autocomplete system genuinely generalizes -- any field can opt
# in via Field Settings, not just the ones migrateSentinelFieldsToGeneric() seeds.
FIELD_ROWS = [{"id": 1, "name": "Status", "type": "text"}]
# "Report" is configured with People (not Status) just so it counts as a "used
# type" for Field Settings without also pre-attaching Status -- Status needs to
# stay in the "available" Fields list (not already-configured) for its Column/
# Autocomplete checkboxes to be reachable in the first place.
TYPE_FIELD_ROWS = [{"document_type": "Report", "field_name": "People", "position": 0}]

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, {json.dumps(FIELD_ROWS)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Column/Autocomplete checkboxes offered for a real generic field, unchecked
        # by default (Status wasn't flagged in the seed) ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(150)
        col_checked_before = await page.locator('.fs-list-item[data-field="Status"] .fs-col-toggle').is_checked()
        ac_checked_before = await page.locator('.fs-list-item[data-field="Status"] .fs-autocomplete-toggle').is_checked()
        print("Column checkbox present, unchecked by default:", col_checked_before)
        print("Autocomplete checkbox present (text field), unchecked by default:", ac_checked_before)

        # Amount/Currency don't get these checkboxes at all -- deliberately inert
        # (see formatAmount()'s note); neither is configured for "Report" either, so
        # both are in this same available-fields list to compare against.
        amount_toggle_count = await page.locator('.fs-list-item[data-field="Amount"] .fs-col-toggle').count()
        currency_toggle_count = await page.locator('.fs-list-item[data-field="Currency"] .fs-col-toggle').count()
        print("Amount has no Column checkbox (deliberately inert, see formatAmount()):", amount_toggle_count == 0)
        print("Currency has no Column checkbox (deliberately inert):", currency_toggle_count == 0)

        # Turn both capabilities on for Status.
        await page.check('.fs-list-item[data-field="Status"] .fs-col-toggle')
        await page.wait_for_timeout(150)
        await page.check('.fs-list-item[data-field="Status"] .fs-autocomplete-toggle')
        await page.wait_for_timeout(150)
        # Now actually attach Status to Report's display fields so it shows up in
        # the capture form -- toggling Column/Autocomplete is independent of that.
        await page.click('.fs-list-item[data-field="Status"] .fs-add')
        await page.wait_for_timeout(150)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        persisted0 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        status_field = next(f for f in persisted0['fields'] if f['name'] == 'Status')
        print("Status flags persisted (show_as_column=1, autocomplete=1):", status_field['show_as_column'], status_field['autocomplete'])
        col_id = f"field-{status_field['id']}"

        # === Capture two documents with different Status values ===
        for title, status in [("Report A", "Approved"), ("Report B", "Pending")]:
            await page.click('#add-btn')
            await page.wait_for_timeout(100)
            await page.fill('#f-type', 'Report')
            await page.locator('#f-type').blur()
            await page.wait_for_timeout(150)
            # autocomplete=1 now -- the input should carry a generated datalist.
            list_attr = await page.locator(f'[data-dynamic-field="Status"] input').get_attribute('list')
            print(f"Status input has autocomplete list attr ({title}):", list_attr)
            await page.fill('[data-dynamic-field="Status"] input', status)
            await page.fill('#f-title', title)
            fname = f"{title.replace(' ', '_')}.pdf"
            with open(fname, 'wb') as f:
                f.write(b"%PDF-1.4 x")
            await page.set_input_files('#file-input', fname)
            await page.wait_for_timeout(100)
            await page.click('#save-doc-btn')
            await page.wait_for_timeout(300)

        # === Column: hidden by default (dynamicColumnDefs() -> defaultVisible:false),
        # visible once toggled in the Columns menu ===
        th_visible_before = await page.locator(f'th[data-field="{col_id}"]').is_visible()
        print("Status column hidden by default:", not th_visible_before)
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        await page.check(f'#col-toggle-{col_id}')
        await page.wait_for_timeout(150)
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        th_visible_after = await page.locator(f'th[data-field="{col_id}"]').is_visible()
        print("Status column visible after toggling on:", th_visible_after)

        cell_values = await page.locator(f'#doc-tbody td[data-field="{col_id}"]').all_inner_texts()
        print("Status column shows the right values:", sorted(cell_values))

        # === Filter: dynamic dropdown built from real distinct values ===
        filter_options = await page.locator(f'#dyn-filter-{col_id} option').all_inner_texts()
        print("Status filter options:", filter_options)
        await page.select_option(f'#dyn-filter-{col_id}', 'Approved')
        await page.wait_for_timeout(150)
        count_text = await page.locator('#count-line').inner_text()
        print("count line after filtering by Approved:", count_text)
        await page.select_option(f'#dyn-filter-{col_id}', '')
        await page.wait_for_timeout(150)

        # === Sort: click the header, values should sort alphabetically ===
        await page.click(f'th[data-key="{col_id}"]')
        await page.wait_for_timeout(150)
        sorted_values = await page.locator(f'#doc-tbody td[data-field="{col_id}"]').all_inner_texts()
        print("Status column values after ascending sort (Approved, Pending):", sorted_values)

        # === Turning Column back off removes it from the table/filters again ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(150)
        await page.uncheck('.fs-list-item[data-field="Status"] .fs-col-toggle')
        await page.wait_for_timeout(150)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)
        th_gone = await page.locator(f'th[data-field="{col_id}"]').count()
        filter_gone = await page.locator(f'#dyn-filter-{col_id}').count()
        print("Status column removed from thead after unflagging:", th_gone == 0)
        print("Status filter removed from toolbar after unflagging:", filter_gone == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
