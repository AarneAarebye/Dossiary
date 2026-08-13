import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Content date (`date`) and import date (`import_date`) deliberately run in
# DIFFERENT relative orders across these three documents, so a test can prove
# which field is actually driving the active sort, not just that some sort
# happened to change the row order:
#   date desc order:        doc 3, doc 2, doc 1  (2026-01-03, -02, -01)
#   import_date desc order: doc 1, doc 3, doc 2  (2026-03-03, -02, -01)
SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc One", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-01T00:00:00+00:00", "import_date": "2026-03-03T00:00:00+00:00",
            "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Doc Two", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-02T00:00:00+00:00", "import_date": "2026-03-01T00:00:00+00:00",
            "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-01-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Doc Three", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-03T00:00:00+00:00", "import_date": "2026-03-02T00:00:00+00:00",
            "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
}

async def read_settings(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text()).settings;
        })()
    """)

async def row_order(page):
    return await page.evaluate("""
        () => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)
    """)

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: a library with no sort_key/sort_dir settings rows (this one
        # was never seeded with any) opens sorted by Import date, newest first -- the
        # new default -- not the old 'date' descending default ===
        imported_th_active = await page.locator('th[data-key="import_date"]').get_attribute('class')
        print("Imported column header is active by default:", 'active' in (imported_th_active or ''))
        order_on_open = await row_order(page)
        print("rows open in import_date-desc order (doc1, doc3, doc2):", order_on_open)

        # === Scenario 2: clicking "Date" switches the sort and persists the choice ===
        await page.click('th[data-key="date"]')
        await page.wait_for_timeout(150)
        order_after_date_click = await row_order(page)
        print("rows reorder to date-desc order (doc3, doc2, doc1) after clicking Date:", order_after_date_click)
        settings_after_date_click = await read_settings(page)
        sort_key_row = next((s for s in settings_after_date_click if s['key'] == 'sort_key'), None)
        sort_dir_row = next((s for s in settings_after_date_click if s['key'] == 'sort_dir'), None)
        print("sort_key persisted as 'date':", sort_key_row['value'] if sort_key_row else None)
        print("sort_dir persisted as 'desc':", sort_dir_row['value'] if sort_dir_row else None)

        # === Scenario 3: clicking "Imported" while some other column is active defaults
        # to descending (newest-imported-first), not the generic ascending-by-default
        # every other non-Date column uses ===
        # Start fresh to avoid state leakage from earlier scenarios
        await browser.close()
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await page.route('**/*', route_handler)
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        # Seed with date as current sort (simulating end of Scenario 2)
        seed_for_s3 = dict(SEED)
        seed_for_s3['settings'] = [
            {'key': 'sort_key', 'value': 'date'},
            {'key': 'sort_dir', 'value': 'desc'},
        ]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_for_s3)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        # The "Imported" column is now visible by default, so just click it
        # (no need to show it via Columns menu)
        await page.click('th[data-key="import_date"]')
        await page.wait_for_timeout(150)
        order_after_imported_click = await row_order(page)
        print("rows reorder to import_date-desc order (doc1, doc3, doc2) on first click of Imported:", order_after_imported_click)
        settings_after_imported_click = await read_settings(page)
        sort_dir_row2 = next((s for s in settings_after_imported_click if s['key'] == 'sort_dir'), None)
        print("sort_dir persisted as 'desc' after first click of Imported:", sort_dir_row2['value'] if sort_dir_row2 else None)

        # === Scenario 4: reopening the library reads back persisted sort state
        # from Scenario 3 -- this is a real round-trip test: Scenario 3 persisted
        # 'import_date'/'desc' to the same root (and that root is still in memory),
        # so reloading it should read that persisted state back and re-sort the table ===
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        import_date_th_active_after_reopen = await page.locator('th[data-key="import_date"]').get_attribute('class')
        print("Imported column header is active after reopening (preserving Scenario 3's sort):", 'active' in (import_date_th_active_after_reopen or ''))
        order_after_reopen = await row_order(page)
        print("rows still in import_date-desc order (doc1, doc3, doc2) after reopening:", order_after_reopen)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
