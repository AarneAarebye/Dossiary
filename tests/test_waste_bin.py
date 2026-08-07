import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: an ordinary, active document.
# Doc 2: flagged for review, not archived, not deleted -- shows in the review queue.
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
        # rather than erroring, and shows normally ===
        row3_visible = await page.locator('tr[data-id="3"]').count()
        print("pre-deleted-column doc shows normally (should be 1):", row3_visible)

        # === Scenario 2: deleting doc 1 from its detail view removes it from the main
        # table and puts it in the waste bin; no modal auto-opens ===
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
        print("doc 1 no longer in the main table:", '1' not in main_row_ids)

        # Even with "Show archived" checked, a deleted (non-archived) document stays
        # hidden from the main table -- deleted is the strongest of the three flags.
        await page.check('#show-archived-toggle')
        await page.wait_for_timeout(150)
        main_row_ids_archived_shown = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 still absent with 'Show archived' checked:", '1' not in main_row_ids_archived_shown)
        await page.uncheck('#show-archived-toggle')
        await page.wait_for_timeout(150)

        # === Scenario 4: the waste bin lists the deleted document, and there is no
        # "empty bin" action anywhere in it ===
        await page.click('#waste-bin-btn')
        await page.wait_for_timeout(200)
        bin_row_ids = await page.locator('#waste-bin-list .review-queue-row').evaluate_all('els => els.map(e => e.dataset.id)')
        print("waste bin shows doc 1:", bin_row_ids)
        empty_bin_btn_count = await page.locator('button:has-text("Empty")').count()
        print("no 'Empty bin' button exists:", empty_bin_btn_count == 0)

        # === Scenario 5: restoring directly from the waste bin's own Restore button
        # works without opening the detail modal, and the row disappears from the list ===
        await page.click('.waste-bin-restore-btn[data-id="1"]')
        await page.wait_for_timeout(200)
        modal_still_open = await page.locator('#modal-backdrop').count()
        print("waste bin modal stays open after Restore (list refreshes in place):", modal_still_open == 1)
        bin_row_ids_after_restore = await page.locator('#waste-bin-list .review-queue-row').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 no longer listed in the waste bin:", '1' not in bin_row_ids_after_restore)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        main_row_ids_after_restore = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 back in the main table after restoring:", '1' in main_row_ids_after_restore)

        # === Scenario 6: deleting a flagged (needs_review) document removes it from
        # the review queue too, not just the main table -- deleted trumps needs_review
        # the same way it trumps archived ===
        # Doc 2 is needs_review=1, so it lives in the review queue, not a main-table
        # row -- click its queue row (same pattern renderReviewQueue() itself wires).
        await page.click('.review-queue-row[data-id="2"] .file-preview')
        await page.wait_for_timeout(200)
        queue_review_label_before = await page.locator('#review-toggle-btn').inner_text()
        print("doc 2 starts flagged (Done label):", queue_review_label_before)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        queue_row_ids = await page.locator('.review-queue-row').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 2 no longer in the review queue after deletion:", '2' not in queue_row_ids)
        review_queue_visible = await page.locator('#review-queue').is_visible()
        print("review queue hidden entirely now (was its only entry):", not review_queue_visible)

        await page.click('#waste-bin-btn')
        await page.wait_for_timeout(200)
        bin_row_ids2 = await page.locator('#waste-bin-list .review-queue-row').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 2 shows in the waste bin instead:", '2' in bin_row_ids2)

        # Clicking the row itself (not the Restore button) opens the full detail view.
        await page.click('.review-queue-row[data-id="2"] .file-preview')
        await page.wait_for_timeout(200)
        detail_title = await page.locator('.modal h2').first.inner_text()
        print("clicking a waste bin row opens its detail view:", detail_title)
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
        # Restoring doc 2 doesn't touch needs_review -- it goes right back to the
        # review queue, not the main table, since that flag was never cleared.
        print("doc 2 is still flagged for review after restoring (flags are independent):", doc2['needs_review'])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
