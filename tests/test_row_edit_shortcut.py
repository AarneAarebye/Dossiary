import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: a normal document in All Documents.
# Doc 2: flagged for review -- shows in the Inbox nav view, proving the shortcut
#        isn't view-specific (per the design decision: every row, every view).
# Doc 3: deleted -- shows in the Waste bin, where the shortcut should be entirely
#        absent, matching the detail view's own precedent of dropping Edit for
#        anything already in the bin.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Regular Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Flagged Doc", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-01-02T00:00:00+00:00", "source": "scan-inbox", "source_legacy_id": None,
            "archived": 0, "needs_review": 1, "deleted": 0,
        },
        {
            "id": 3, "title": "Deleted Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
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

        # === Scenario 1: clicking the row-edit shortcut on a normal document (All
        # Documents view) opens the Edit form directly, not the detail view, and
        # doesn't also trigger the row's own click-to-detail handler (proving
        # event.stopPropagation() on the cell actually works) ===
        edit_btn_count = await page.locator('tr[data-id="1"] .row-edit-btn').count()
        print("edit shortcut button present on a normal row:", edit_btn_count == 1)

        await page.click('tr[data-id="1"] .row-edit-btn')
        await page.wait_for_timeout(200)
        edit_title_field_visible = await page.locator('#e-title').is_visible()
        print("Edit form opened directly:", edit_title_field_visible)
        detail_only_element_present = await page.locator('#edit-doc-btn').count()
        print("detail view was never opened underneath (no lingering detail-only element):", detail_only_element_present == 0)

        # === Scenario 2: Cancel from an edit reached via the shortcut just closes
        # the edit form -- it no longer reopens the detail view/panel, and does NOT
        # force the (collapsed-by-default) detail panel open, since the shortcut
        # bypasses row selection entirely on the way in ===
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(200)
        edit_form_closed = await page.locator('#e-title').count()
        print("Cancel closes the edit form:", edit_form_closed == 0)
        panel_not_forced_open = await page.locator('#main-layout.detail-panel-expanded').count()
        print("Cancel does not force the detail panel open:", panel_not_forced_open == 0)

        # === Scenario 3: the shortcut works the same way in the Inbox view too --
        # not scoped to any one nav view ===
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        edit_btn_in_inbox = await page.locator('tr[data-id="2"] .row-edit-btn').count()
        print("edit shortcut button present in the Inbox view:", edit_btn_in_inbox == 1)
        await page.click('tr[data-id="2"] .row-edit-btn')
        await page.wait_for_timeout(200)
        edit_opened_from_inbox = await page.locator('#e-title').is_visible()
        print("Edit form opened directly from the Inbox view:", edit_opened_from_inbox)
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)

        # === Scenario 4: the shortcut is entirely absent for a deleted document in
        # the Waste bin -- matching the detail view's own precedent of dropping
        # Edit for anything already in the bin, not just disabling it ===
        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        edit_btn_in_trash = await page.locator('tr[data-id="3"] .row-edit-btn').count()
        print("edit shortcut button absent for a deleted document:", edit_btn_in_trash == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
