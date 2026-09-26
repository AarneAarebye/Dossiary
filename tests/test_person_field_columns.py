import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Person-type fields other than People (e.g. "Author") as optional table
# columns and filters: shown as pills, filtered by "includes this name" (and
# "not set"), sortable, reportable, and savable as a Smart Collection.
def doc(i, title):
    return {
        "id": i, "title": title, "category": None, "document_type": "Book",
        "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_doc.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }

SEED = {
    "documents": [doc(1, "Silmarillion"), doc(2, "Hobbit"), doc(3, "Anonymous Pamphlet"), doc(4, "Letters")],
    "tags": [], "document_tags": [],
    "fields": [{"id": 1, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0}],
    "people": [{"id": 1, "name": "Tolkien"}, {"id": 2, "name": "Christopher"}, {"id": 3, "name": "Carpenter"}],
    "document_field_people": [
        {"document_id": 1, "field_id": 1, "person_id": 1},
        {"document_id": 1, "field_id": 1, "person_id": 2},
        {"document_id": 2, "field_id": 1, "person_id": 1},
        {"document_id": 4, "field_id": 1, "person_id": 3},
    ],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        async def visible_ids():
            return await page.locator('#doc-tbody tr').evaluate_all("rs => rs.map(r => +r.dataset.id)")

        # === Scenario 1: Field Settings offers Column for Author, not for People ===
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        author_toggle = page.locator('.fs-list-item[data-field="Author"] .fs-col-toggle')
        print("Author (person field) gets a Column checkbox:", await author_toggle.count() >= 1)
        print("...but no Autocomplete checkbox:", await page.locator('.fs-list-item[data-field="Author"] .fs-autocomplete-toggle').count() == 0)
        print("People keeps no Column checkbox (it has its own fixed column):", await page.locator('.fs-list-item[data-field="People"] .fs-col-toggle').count() == 0)
        await author_toggle.first.check()
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 2: the column shows names as pills once turned on ===
        col_id = 'field-1'
        print("Author appears in the Columns menu:", await page.locator(f'#col-toggle-{col_id}').count() == 1)
        await page.click('#columns-btn')
        await page.locator(f'#col-toggle-{col_id}').check()
        await page.click('#search')
        await page.wait_for_timeout(200)
        print("Author column header visible:", await page.locator(f'th[data-field="{col_id}"]').is_visible())
        pills = await page.locator(f'#doc-tbody tr[data-id="1"] td[data-field="{col_id}"] .pill').all_inner_texts()
        print("Row shows every author as a pill:", pills == ['Tolkien', 'Christopher'], pills)
        empty = await page.inner_text(f'#doc-tbody tr[data-id="3"] td[data-field="{col_id}"]')
        print("Row without authors shows the no-value dash:", empty.strip() == '—', repr(empty))

        # === Scenario 3: filter by one name, and by "not set" ===
        sel = f'#dyn-filter-{col_id}'
        options = await page.locator(f'{sel} option').evaluate_all("os => os.map(o => o.value)")
        print("Filter lists each distinct name once:", sorted(options[2:]) == ['Carpenter', 'Christopher', 'Tolkien'], options)
        await page.select_option(sel, 'Tolkien')
        await page.wait_for_timeout(200)
        print("Filtering by Tolkien shows both of his documents:", sorted(await visible_ids()) == [1, 2], await visible_ids())
        await page.select_option(sel, '__unset__')
        await page.wait_for_timeout(200)
        print("'Not set' shows only the document without authors:", await visible_ids() == [3], await visible_ids())

        # === Scenario 4: a Smart Collection saved from that filter keeps working ===
        await page.select_option(sel, 'Tolkien')
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.wait_for_timeout(150)
        await page.fill('#smart-collection-name-input', 'By Tolkien')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(200)
        await page.select_option(sel, '')
        await page.wait_for_timeout(150)
        await page.locator('.nav-item[data-view^="collection-"]', has_text='By Tolkien').click()
        await page.wait_for_timeout(250)
        print("Smart Collection by author matches the same documents:", sorted(await visible_ids()) == [1, 2], await visible_ids())
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)

        # === Scenario 5: sorting by the column ===
        await page.click(f'th[data-field="{col_id}"]')
        await page.wait_for_timeout(200)
        ids = await visible_ids()
        print("Sorting ascending orders by the joined names (empty first):", ids == [3, 4, 2, 1], ids)

        # === Scenario 6: Reports can break totals down by author ===
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(200)
        opts = await page.locator('#report-breakdown-field option').evaluate_all("os => os.map(o => o.value)")
        print("Reports offers Author as a breakdown:", col_id in opts, opts)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
