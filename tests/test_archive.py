import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 3 is pre-archived. Doc 1 deliberately omits the `archived` key entirely,
# simulating a document that predates the archived column (the SCHEMA_MIGRATIONS
# ALTER TABLE default -- should read back as "not archived", not error).
SEED = {
    "documents": [
        {
            "id": 1, "title": "Active Doc One", "category": "Medical", "document_type": "Invoice",
            "date": "2020-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "migrated", "source_legacy_id": 1,
        },
        {
            "id": 2, "title": "Active Doc Two", "category": "Finance", "document_type": "Receipt",
            "date": "2020-02-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "migrated", "source_legacy_id": 2, "archived": 0,
        },
        {
            "id": 3, "title": "Old Unneeded Doc", "category": "Medical", "document_type": "Invoice",
            "date": "2020-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "migrated", "source_legacy_id": 3, "archived": 1,
        },
    ],
    "tags": [], "document_tags": [],
}

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
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

        # === Archived doc hidden by default; pre-archived-column doc reads as
        # not-archived rather than erroring ===
        show_archived_checked_default = await page.locator('#show-archived-toggle').is_checked()
        row_count_default = await page.locator('#doc-tbody tr').count()
        count_line_default = await page.locator('#count-line').inner_text()
        print("'Show archived' unchecked by default:", not show_archived_checked_default)
        print("row count with archived hidden (should be 2):", row_count_default)
        print("count line (should say 2 of 3):", count_line_default)

        # === Checking "Show archived" reveals it, with an archived pill ===
        await page.check('#show-archived-toggle')
        await page.wait_for_timeout(150)
        row_count_shown = await page.locator('#doc-tbody tr').count()
        archived_pill_count = await page.locator('tr[data-id="3"] .pill.archived').count()
        print("row count with 'Show archived' checked (should be 3):", row_count_shown)
        print("archived doc shows an 'archived' pill:", archived_pill_count == 1)

        # === Detail modal offers Unarchive for an archived doc, and it works ===
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        archive_btn_label = await page.locator('#archive-toggle-btn').inner_text()
        print("archived doc's detail button label:", archive_btn_label)
        await page.click('#archive-toggle-btn')
        await page.wait_for_timeout(200)
        archive_btn_label_after = await page.locator('#archive-toggle-btn').inner_text()
        print("button label after unarchiving:", archive_btn_label_after)

        # Still checked "Show archived", but now nothing is archived
        row_count_after_unarchive = await page.locator('#doc-tbody tr').count()
        pill_count_after_unarchive = await page.locator('.pill.archived').count()
        print("row count after unarchiving (should be 3):", row_count_after_unarchive)
        print("no archived pills remain:", pill_count_after_unarchive == 0)

        # === Archiving an active doc hides it once "Show archived" is unchecked,
        # and search doesn't surface it either ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#archive-toggle-btn')
        await page.wait_for_timeout(200)

        await page.uncheck('#show-archived-toggle')
        await page.wait_for_timeout(150)
        row_count_final = await page.locator('#doc-tbody tr').count()
        print("row count with doc 1 newly archived, 'Show archived' off (should be 2):", row_count_final)

        await page.fill('#search', 'Active Doc One')
        await page.wait_for_timeout(200)
        search_hides_archived = await page.locator('#doc-tbody tr').count()
        print("searching an archived doc's own title finds nothing while hidden:", search_hides_archived == 0)

        await page.check('#show-archived-toggle')
        await page.wait_for_timeout(200)
        search_with_archived_shown = await page.locator('#doc-tbody tr').count()
        print("same search finds it once 'Show archived' is checked:", search_with_archived_shown == 1)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1 = next(d for d in persisted['documents'] if d['id'] == 1)
        doc3 = next(d for d in persisted['documents'] if d['id'] == 3)
        print("doc 1 persisted as archived:", doc1['archived'])
        print("doc 3 persisted as unarchived:", doc3['archived'])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
