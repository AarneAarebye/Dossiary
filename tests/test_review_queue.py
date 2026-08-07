import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: a normal, already-reviewed document -- shows in the main table.
# Doc 2: flagged for review, not archived -- shows in the review queue instead of
#        the main table.
# Doc 3: flagged for review AND archived -- independent flags (per design), so it's
#        excluded from the queue (which excludes archived docs) and only reachable
#        via "Show archived" in the main table, same as any other archived doc.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Reviewed Invoice", "category": "Finance", "document_type": "Invoice",
            "date": "2020-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_invoice.pdf", "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0,
        },
        {
            "id": 2, "title": "Unreviewed Scan", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_scan.pdf", "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "scan-inbox", "source_legacy_id": None,
            "archived": 0, "needs_review": 1,
        },
        {
            "id": 3, "title": "Old Flagged Doc", "category": "Medical", "document_type": "Invoice",
            "date": "2019-05-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-07-28T08:19:45+00:00", "source": "migrated", "source_legacy_id": 9,
            "archived": 1, "needs_review": 1,
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

        # === Scenario 1: queue shows only the non-archived flagged doc; main table
        # shows only the fully-reviewed doc; the archived+flagged doc is in neither
        # place until "Show archived" is checked ===
        queue_visible = await page.locator('#review-queue').is_visible()
        queue_heading = await page.locator('#review-queue-heading').inner_text()
        print("queue visible on load:", queue_visible)
        print("queue heading (should say 1):", queue_heading)
        queue_row_ids = await page.locator('.review-queue-row').evaluate_all('els => els.map(e => e.dataset.id)')
        print("queue contains only doc 2:", queue_row_ids)

        main_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("main table shows only doc 1 by default:", main_row_ids)

        # === Scenario 2: checking 'Show archived' surfaces doc 3 in the main table
        # (archived overrides the queue-only routing for a flagged doc), but doc 2
        # still doesn't appear there -- it's still only reachable via the queue ===
        await page.check('#show-archived-toggle')
        await page.wait_for_timeout(150)
        main_row_ids_archived_shown = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("main table with 'Show archived' checked shows doc 1 and 3, not 2:", main_row_ids_archived_shown)
        queue_row_ids_still = await page.locator('.review-queue-row').evaluate_all('els => els.map(e => e.dataset.id)')
        print("queue still shows only doc 2 (archived flagged doc never joins it):", queue_row_ids_still)
        await page.uncheck('#show-archived-toggle')
        await page.wait_for_timeout(150)

        # === Scenario 3: the queue row's own 'Done' button clears needs_review without
        # opening the detail modal, and the document then appears in the main table ===
        await page.click('.review-queue-row[data-id="2"] .review-done-btn')
        await page.wait_for_timeout(200)
        modal_open_after_done = await page.locator('#modal-backdrop').count()
        print("no modal opened by the queue's own Done button:", modal_open_after_done == 0)
        queue_visible_after_done = await page.locator('#review-queue').is_visible()
        print("queue hidden once empty:", not queue_visible_after_done)
        main_row_ids_after_done = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 2 now in the main table:", '2' in main_row_ids_after_done)

        # === Scenario 4: any document can be manually flagged from the detail view,
        # not just inbox-imported ones -- flagging doc 1 removes it from the main
        # table and adds it to the queue ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        review_btn_label = await page.locator('#review-toggle-btn').inner_text()
        print("unflagged doc's detail button label:", review_btn_label)
        await page.click('#review-toggle-btn')
        await page.wait_for_timeout(200)
        review_btn_label_after = await page.locator('#review-toggle-btn').inner_text()
        print("button label after flagging (modal refreshes in place):", review_btn_label_after)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        main_row_ids_after_flag = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 no longer in main table after being flagged:", '1' not in main_row_ids_after_flag)
        queue_row_ids_after_flag = await page.locator('.review-queue-row').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 now in the queue:", '1' in queue_row_ids_after_flag)

        # === Scenario 5: saving an intermediate edit on a flagged document does NOT
        # clear needs_review -- only the explicit Done action does (per design: some
        # people do intermediate saves before a document is actually ready) ===
        await page.click('.review-queue-row[data-id="1"] .review-edit-btn')
        await page.wait_for_timeout(200)
        edit_modal_open = await page.locator('#modal-backdrop').count()
        print("queue row's Edit button opens the edit form:", edit_modal_open == 1)
        await page.fill('#e-title', 'Reviewed Invoice (touched)')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        # saveEditedDocument() reopens the detail view (not the edit form) on success,
        # rather than closing the modal outright -- close it before continuing.
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        queue_row_ids_after_save = await page.locator('.review-queue-row').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 still in the queue after an intermediate save:", '1' in queue_row_ids_after_save)
        main_row_ids_after_save = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 still absent from the main table after that save:", '1' not in main_row_ids_after_save)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1 = next(d for d in persisted['documents'] if d['id'] == 1)
        print("doc 1 title updated by the save:", doc1['title'])
        print("doc 1 still flagged in persisted state:", doc1['needs_review'])

        # === Scenario 6: archiving and flagging are fully independent -- archiving
        # the still-flagged doc 3 from its detail view doesn't touch needs_review,
        # and un-flagging doc 1 from its detail view doesn't touch archived ===
        await page.check('#show-archived-toggle')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        doc3_review_label = await page.locator('#review-toggle-btn').inner_text()
        doc3_archive_label = await page.locator('#archive-toggle-btn').inner_text()
        print("archived+flagged doc's review button (should be Done):", doc3_review_label)
        print("archived+flagged doc's archive button (should be Unarchive):", doc3_archive_label)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
