import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

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

        # Seed an empty library with two files already waiting in inbox/, mirroring what
        # a watched-folder helper like scan_watch.py would have deposited before the
        # library was ever opened.
        await page.evaluate("""
            () => {
                window.__TEST_ROOT = window.__makeEmptyRoot();
                window.__addInboxFile(window.__TEST_ROOT, 'scan001.pdf');
                window.__addInboxFile(window.__TEST_ROOT, 'scan002.jpg');
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: banner shows the pending count as soon as the library opens ===
        banner_visible = await page.locator('#inbox-banner').is_visible()
        banner_text = await page.locator('#inbox-banner-text').inner_text()
        print("banner visible after open:", banner_visible)
        print("banner text:", banner_text)

        # === Scenario 2: clicking the banner's "Add all" button adds both staged files
        # directly -- no modal ever appears -- lands on the Inbox nav view, and reports
        # the folder + count on the status line ===
        await page.click('#inbox-add-all-btn')
        await page.wait_for_timeout(400)

        modal_present = await page.locator('#modal-backdrop').count()
        print("no modal appeared after Add all:", modal_present == 0)

        current_view_is_inbox = await page.locator('#nav-item-inbox.active').count()
        print("landed on the Inbox nav view:", current_view_is_inbox == 1)

        status_text = await page.locator('#status').inner_text()
        print("status line after Add all:", status_text)
        print("status line names the folder:", 'EmptyLibrary/inbox/' in status_text)
        print("status line names the count:", '2' in status_text)

        banner_visible_after = await page.locator('#inbox-banner').is_visible()
        print("banner hidden once inbox emptied:", not banner_visible_after)

        # The saved documents should carry only the file + a filename-derived title --
        # nothing else assumed -- and land with source 'scan-inbox'.
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("total documents after Add all:", len(persisted['documents']))
        print("sources:", sorted(d['source'] for d in persisted['documents']))
        doc1 = next(d for d in persisted['documents'] if d['id'] == 1)
        print("doc1:", {k: doc1[k] for k in ['id', 'title', 'category', 'document_type', 'date', 'source', 'file_path']})
        print("inbox-added doc gets a real original_file_path (should not be None):", doc1.get('original_file_path'))
        print("inbox-added doc searchable_pdf_built (should be 0):", doc1.get('searchable_pdf_built'))

        inbox_after_all = await page.evaluate("""
            (async () => {
                const inbox = await window.__TEST_ROOT.getDirectoryHandle('inbox');
                const names = [];
                for await (const [name] of inbox.entries()) names.push(name);
                return names;
            })()
        """)
        print("inbox/ contents after Add all (should be empty):", inbox_after_all)

        files_after_all = await page.evaluate("""
            (async () => {
                const files = await window.__TEST_ROOT.getDirectoryHandle('files');
                const names = [];
                for await (const [name] of files.entries()) names.push(name);
                return names;
            })()
        """)
        print("files/ contents after Add all:", sorted(files_after_all))

        # Both land flagged for review (needs_review=1, see addInboxFile()), so both
        # show in the Inbox nav view, not All Documents, until someone clicks Done --
        # see CLAUDE.md's nav architecture note.
        main_rows_before_done = await page.locator('#doc-tbody tr').count()
        print("All Documents rows before Done (should be 0, both live in Inbox):", main_rows_before_done)
        inbox_row_count = await page.locator('#doc-tbody tr').count()  # already on the Inbox view from above
        print("Inbox view shows both inbox-added docs:", inbox_row_count)

        # Done-ing one of them moves it into All Documents with the inbox-added pill;
        # the other stays in the Inbox queue -- exercises the existing, unchanged
        # toggleNeedsReview() flow, not new code from this change.
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#review-toggle-btn')
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        pill_text = await page.locator('tr[data-id="1"] .pill.captured').inner_text()
        print("table pill for inbox-added doc after Done:", pill_text)

        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        remaining_row_count = await page.locator('tr[data-id="2"]').count()
        print("the other inbox-added doc is still in the Inbox queue:", remaining_row_count)

        # === Scenario 3: reopening the (now-empty) library keeps the banner hidden ===
        # #reload-btn's own click handler calls resetAll() then openLibrary() -- the stub's
        # showDirectoryPicker keeps returning the same __TEST_ROOT, and library.sqlite
        # already exists on it now, so this re-loads straight in without #init-btn.
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        banner_on_reopen = await page.locator('#inbox-banner').is_visible()
        print("banner visible on reopening an already-emptied library:", banner_on_reopen)

        # === Scenario 4: a file staged (e.g. by scan_watch.py) *after* the library was
        # already open doesn't show up on its own -- checkInbox() only runs once, right
        # after the library opens (see afterDbReady()) -- but the always-visible "Check
        # inbox" toolbar button lets someone notice and add it directly, without opening
        # any modal ===
        await page.evaluate("window.__addInboxFile(window.__TEST_ROOT, 'late_arrival.pdf');")
        banner_still_hidden = await page.locator('#inbox-banner').is_visible()
        print("banner still hidden right after a late file is staged (no auto-poll):", not banner_still_hidden)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(400)

        modal_present_after_check = await page.locator('#modal-backdrop').count()
        print("no modal appeared after Check inbox:", modal_present_after_check == 0)

        current_view_is_inbox_after_check = await page.locator('#nav-item-inbox.active').count()
        print("Check inbox landed on the Inbox nav view:", current_view_is_inbox_after_check == 1)

        status_after_check = await page.locator('#status').inner_text()
        print("status line after Check inbox found the late file:", status_after_check)

        late_doc_row = await page.locator('tr[data-id="3"]').count()
        print("late-arriving file was added directly:", late_doc_row == 1)

        # === Scenario 5: clicking "Check inbox" when nothing is staged reports that on
        # the status line and does not navigate anywhere ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(300)

        status_when_empty = await page.locator('#status').inner_text()
        print("status line when inbox is empty:", status_when_empty)

        stayed_on_all = await page.locator('#nav-item-all.active').count()
        print("stayed on All Documents (no navigation for a no-op):", stayed_on_all == 1)

        print("JS errors:", errors)
        await browser.close()

asyncio.run(main())
