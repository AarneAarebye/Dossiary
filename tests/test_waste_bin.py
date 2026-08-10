import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: an ordinary, active document.
# Doc 2: flagged for review, not archived, not deleted -- shows in the Inbox nav view.
# Doc 3: pre-`deleted`-column document (the key is omitted entirely, simulating a
#        library from before this feature existed) -- should read back as not-deleted,
#        same tolerance already proven for `archived` in test_archive.py.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Active Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2020-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_invoice.pdf", "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Queued Doc", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_scan.pdf", "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "scan-inbox", "source_legacy_id": None,
            "archived": 0, "needs_review": 1, "deleted": 0,
        },
        {
            "id": 3, "title": "Predates Deleted Column", "category": "Medical", "document_type": "Invoice",
            "date": "2019-05-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "migrated", "source_legacy_id": 9,
            "archived": 0, "needs_review": 0,
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

        # === Scenario 1: a pre-`deleted`-column document reads back as not-deleted
        # rather than erroring, and shows normally in All Documents ===
        row3_visible = await page.locator('tr[data-id="3"]').count()
        print("pre-deleted-column doc shows normally (should be 1):", row3_visible)

        # === Scenario 2: deleting doc 1 from its detail view removes it from All
        # Documents; the modal refreshes in place rather than closing ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        delete_btn_label = await page.locator('#delete-toggle-btn').inner_text()
        print("active doc's detail button label:", delete_btn_label)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(200)

        # === Scenario 3: a deleted document's detail view shows ONLY Restore -- no
        # Edit/Archive/Flag-for-review/Delete buttons ===
        restore_btn_label = await page.locator('#delete-toggle-btn').inner_text()
        print("deleted doc's detail button now reads:", restore_btn_label)
        edit_btn_count = await page.locator('#edit-doc-btn').count()
        archive_btn_count = await page.locator('#archive-toggle-btn').count()
        review_btn_count = await page.locator('#review-toggle-btn').count()
        print("Edit button hidden while deleted:", edit_btn_count == 0)
        print("Archive button hidden while deleted:", archive_btn_count == 0)
        print("Review-toggle button hidden while deleted:", review_btn_count == 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        main_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 no longer in All Documents:", '1' not in main_row_ids)

        # Even with "Show archived" checked, a deleted (non-archived) document stays
        # hidden from All Documents -- deleted is the strongest of the three flags.
        await page.check('#show-archived-toggle')
        await page.wait_for_timeout(150)
        main_row_ids_archived_shown = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 still absent with 'Show archived' checked:", '1' not in main_row_ids_archived_shown)
        await page.uncheck('#show-archived-toggle')
        await page.wait_for_timeout(150)

        # === Scenario 4: the Waste bin nav view lists the deleted document (in the
        # same real table every other view uses), and there is no "empty bin" action
        # anywhere in this app ===
        await page.click('#nav-item-trash')
        await page.wait_for_timeout(200)
        bin_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Waste bin shows doc 1:", bin_row_ids)
        empty_bin_btn_count = await page.locator('button:has-text("Empty")').count()
        print("no 'Empty bin' button exists:", empty_bin_btn_count == 0)

        # === Scenario 5: restoring from the detail view (reached by clicking the row
        # in the Waste bin nav view) refreshes the modal in place, and the row
        # disappears from Waste bin ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(200)
        modal_still_open = await page.locator('#modal-backdrop').count()
        print("modal stays open after Restore (refreshes in place):", modal_still_open == 1)
        restore_label_after = await page.locator('#delete-toggle-btn').inner_text()
        print("button now reads Delete again (full action set restored):", restore_label_after)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        bin_row_ids_after_restore = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 no longer listed in Waste bin:", '1' not in bin_row_ids_after_restore)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        main_row_ids_after_restore = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 back in All Documents after restoring:", '1' in main_row_ids_after_restore)

        # === Scenario 6: deleting a flagged (needs_review) document removes it from
        # Inbox too, not just All Documents -- deleted trumps needs_review the same
        # way it trumps archived ===
        # Doc 2 is needs_review=1, so it lives in the Inbox nav view, not All
        # Documents -- switch there and click its row.
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        queue_review_label_before = await page.locator('#review-toggle-btn').inner_text()
        print("doc 2 starts flagged (Done label):", queue_review_label_before)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        inbox_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 2 no longer in Inbox after deletion:", '2' not in inbox_row_ids)
        inbox_count_now = await page.locator('#nav-count-inbox').inner_text()
        print("Inbox badge now 0 (was its only entry):", inbox_count_now)

        await page.click('#nav-item-trash')
        await page.wait_for_timeout(200)
        bin_row_ids2 = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 2 shows in Waste bin instead:", '2' in bin_row_ids2)

        # Clicking the row itself opens the full detail view, same as any other view.
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        detail_title = await page.locator('.modal h2').first.inner_text()
        print("clicking a Waste bin row opens its detail view:", detail_title)
        restore_from_detail_label = await page.locator('#delete-toggle-btn').inner_text()
        print("its detail view also only offers Restore:", restore_from_detail_label)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(200)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc2 = next(d for d in persisted['documents'] if d['id'] == 2)
        print("doc 2 persisted as not-deleted after restoring from its own detail view:", doc2['deleted'])
        # Restoring doc 2 doesn't touch needs_review -- it goes right back to Inbox,
        # not All Documents, since that flag was never cleared.
        print("doc 2 is still flagged for review after restoring (flags are independent):", doc2['needs_review'])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
