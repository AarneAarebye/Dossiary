import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: a normal, already-reviewed document -- shows in All Documents.
# Doc 2: flagged for review, not archived -- shows in the Inbox nav view instead of
#        All Documents.
# Doc 3: flagged for review AND archived -- independent flags (per design), so it's
#        excluded from the Inbox view (which excludes archived docs) and only
#        reachable via "Show archived" in All Documents, same as any other archived doc.
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

        # === Scenario 1: Inbox nav badge shows only the non-archived flagged doc;
        # All Documents shows only the fully-reviewed doc; the archived+flagged doc
        # is in neither place until "Show archived" is checked ===
        inbox_count = await page.locator('#nav-count-inbox').inner_text()
        print("Inbox badge (should say 1):", inbox_count)
        all_count = await page.locator('#nav-count-all').inner_text()
        print("All Documents badge (should say 1):", all_count)

        main_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents shows only doc 1 by default:", main_row_ids)

        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        inbox_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Inbox view contains only doc 2:", inbox_row_ids)
        show_archived_visible_in_inbox = await page.locator('#show-archived-wrap').is_visible()
        print("'Show archived' hidden while in Inbox view:", not show_archived_visible_in_inbox)

        # === Scenario 2: checking 'Show archived' back on All Documents surfaces
        # doc 3 (archived overrides the Inbox-only routing for a flagged doc), but
        # doc 2 still doesn't appear there -- it's still only reachable via Inbox ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.check('#show-archived-toggle')
        await page.wait_for_timeout(150)
        main_row_ids_archived_shown = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents with 'Show archived' checked shows doc 1 and 3, not 2:", main_row_ids_archived_shown)
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        inbox_row_ids_still = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Inbox still shows only doc 2 (archived flagged doc never joins it):", inbox_row_ids_still)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.uncheck('#show-archived-toggle')
        await page.wait_for_timeout(150)

        # === Scenario 3: clicking a row in Inbox opens the same detail modal as any
        # other view; its 'Done' button clears needs_review, and the document then
        # moves to All Documents ===
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        doc2_review_label = await page.locator('#review-toggle-btn').inner_text()
        print("doc 2's detail button label from Inbox (should be Done):", doc2_review_label)
        await page.click('#review-toggle-btn')
        await page.wait_for_timeout(200)
        # The detail panel refreshes its content in place (no modal to close at all
        # for panel content) -- confirm the button itself is still present with its
        # new label, proving openDetail() re-rendered rather than clearing the panel.
        panel_refreshed_after_done = await page.locator('#review-toggle-btn').count()
        print("panel refreshes in place after Done (button still present):", panel_refreshed_after_done == 1)
        inbox_count_after_done = await page.locator('#nav-count-inbox').inner_text()
        print("Inbox badge now 0:", inbox_count_after_done)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        main_row_ids_after_done = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 2 now in All Documents:", '2' in main_row_ids_after_done)

        # === Scenario 4: any document can be manually flagged from the detail view,
        # not just inbox-imported ones -- flagging doc 1 removes it from All
        # Documents and adds it to Inbox ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        review_btn_label = await page.locator('#review-toggle-btn').inner_text()
        print("unflagged doc's detail button label:", review_btn_label)
        await page.click('#review-toggle-btn')
        await page.wait_for_timeout(200)
        review_btn_label_after = await page.locator('#review-toggle-btn').inner_text()
        print("button label after flagging (panel refreshes in place):", review_btn_label_after)

        main_row_ids_after_flag = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 no longer in All Documents after being flagged:", '1' not in main_row_ids_after_flag)
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        inbox_row_ids_after_flag = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 now in Inbox:", '1' in inbox_row_ids_after_flag)

        # === Scenario 5: saving an intermediate edit on a flagged document does NOT
        # clear needs_review -- only the explicit Done action does (per design: some
        # people do intermediate saves before a document is actually ready) ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        edit_modal_open = await page.locator('#modal-backdrop').count()
        print("clicking Edit from the detail view (reached via Inbox) opens the edit form:", edit_modal_open == 1)
        await page.fill('#e-title', 'Reviewed Invoice (touched)')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        # saveEditedDocument() now closes the edit modal explicitly on success and
        # sets selectedDocId so the (already-open) panel shows the just-saved
        # document -- no separate close click needed.

        inbox_row_ids_after_save = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 still in Inbox after an intermediate save:", '1' in inbox_row_ids_after_save)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        main_row_ids_after_save = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 still absent from All Documents after that save:", '1' not in main_row_ids_after_save)

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

        # === Scenario 7: "Save & Done" (only rendered on a currently-flagged
        # document) saves the edit AND clears needs_review in one click -- doc 1
        # is still flagged here (Scenario 4 flagged it, Scenario 5's intermediate
        # save deliberately left it flagged) ===
        await page.uncheck('#show-archived-toggle')
        await page.wait_for_timeout(150)
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        save_done_visible_flagged = await page.locator('#save-done-btn').count()
        print("'Save & Done' button present when editing a flagged document:", save_done_visible_flagged == 1)

        await page.fill('#e-title', 'Reviewed Invoice (finished)')
        await page.click('#save-done-btn')
        await page.wait_for_timeout(300)
        # Unlike the standalone "Done" button (which reopens the detail view in
        # place), "Save & Done" closes everything and returns straight to the
        # table that was already showing underneath -- no extra click needed to
        # dismiss a dialog before moving to the next item in the queue.
        modal_open_after_save_done = await page.locator('#modal-backdrop').count()
        print("modal fully closed after Save & Done:", modal_open_after_save_done == 0)

        inbox_row_ids_after_save_done = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("still on the Inbox view (no forced navigation), doc 1 now gone from it:", '1' not in inbox_row_ids_after_save_done)
        still_on_inbox_view = await page.locator('#nav-item-inbox.active').count()
        print("Inbox nav item still the active view:", still_on_inbox_view == 1)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        main_row_ids_after_save_done = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("doc 1 now in All Documents:", '1' in main_row_ids_after_save_done)

        persisted_after_save_done = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1_after = next(d for d in persisted_after_save_done['documents'] if d['id'] == 1)
        print("doc 1's title reflects the Save & Done edit:", doc1_after['title'])
        print("doc 1's needs_review persisted as cleared:", doc1_after['needs_review'])

        # === Scenario 8: "Save & Done" is absent entirely for an unflagged
        # document (doc 2, Done-d back in Scenario 3) -- only plain "Save
        # changes" makes sense there ===
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        save_done_visible_unflagged = await page.locator('#save-done-btn').count()
        print("'Save & Done' button absent when editing an unflagged document:", save_done_visible_unflagged == 0)
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
