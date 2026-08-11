import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: ordinary, active -- always in scope for Reports and the only document that
#        ever shows in the All Documents default view across every scenario below.
# Doc 2: archived -- Reports includes archived documents by default (unlike All
#        Documents, which hides them until "Show archived" is checked).
# Doc 3: deleted (Waste bin) -- Reports excludes deleted documents, same as every
#        other view.
# Doc 4: flagged for review (Inbox view) -- Reports includes needs-review documents
#        by default too, same reasoning as archived. Given a different Category
#        (Medical, not Travel) so later breakdown-by-category scenarios can tell it
#        apart from docs 1/2.
# Docs 5-7 are added in Tasks 2/3 for currency/date-range scenarios.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Active Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Archived Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-02-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-02-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Deleted Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
        {
            "id": 4, "title": "Needs Review Doc", "category": "Medical", "document_type": "Receipt",
            "date": "2026-01-15T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-01-15T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 1, "deleted": 0,
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

        # === Scenario 1: the Reports nav item exists and is reachable ===
        reports_nav_count = await page.locator('#nav-item-reports').count()
        print("Reports nav item exists:", reports_nav_count == 1)

        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        reports_active = await page.locator('#nav-item-reports').get_attribute('class')
        print("Reports nav item becomes active on click:", 'active' in (reports_active or ''))

        # === Scenario 2: switching to Reports hides the document table/count line ===
        table_visible = await page.locator('#table-wrap').is_visible()
        count_line_visible = await page.locator('#count-line').is_visible()
        reports_view_visible = await page.locator('#reports-view').is_visible()
        print("Table hidden in Reports view:", not table_visible)
        print("Count line hidden in Reports view:", not count_line_visible)
        print("#reports-view visible:", reports_view_visible)

        # === Scenario 3: Reports scope includes archived and needs-review, excludes
        # deleted -- 3 of the 4 seeded documents (doc 1 active, doc 2 archived, doc 4
        # needs-review) should be in scope; doc 3 (deleted) should not ===
        doc_count_text = await page.locator('#reports-doc-count').inner_text()
        print("Reports doc-count text:", doc_count_text)

        # === Scenario 4: switching back to All Documents restores the table, and
        # Show archived reflects that view's own independent state (unaffected by
        # having just been in Reports). Only doc 1 is ever plain active/non-archived/
        # non-needs-review/non-deleted in this SEED, so this assertion stays valid
        # even after Tasks 2-3 add more documents (5-7 are all archived). ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        table_visible_after = await page.locator('#table-wrap').is_visible()
        reports_view_visible_after = await page.locator('#reports-view').is_visible()
        print("Table visible again in All Documents:", table_visible_after)
        print("#reports-view hidden again:", not reports_view_visible_after)
        all_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents still shows only doc 1 (rest are archived/needs-review/deleted):", all_row_ids)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
