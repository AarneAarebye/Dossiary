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
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

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
        inbox_row_count = await page.locator('#doc-tbody tr').count()  # still on Inbox view from Add all
        print("Inbox view shows both inbox-added docs:", inbox_row_count)

        # Done-ing one of them moves it into All Documents with the inbox-added pill;
        # the other stays in the Inbox queue -- exercises the existing, unchanged
        # toggleNeedsReview() flow, not new code from this change.
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#review-toggle-btn')
        await page.wait_for_timeout(200)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        pill_text = await page.locator('tr[data-id="1"] .pill.captured').inner_text()
        print("table pill for inbox-added doc after Done:", pill_text)

        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        remaining_row_count = await page.locator('tr[data-id="2"]').count()
        print("the other inbox-added doc is still in the Inbox queue:", remaining_row_count)

        # === Scenario 2b: partial failure (1 succeeds, 1 fails) reports accurately ===
        # Verify that if a file is genuinely unreadable (permission revoked, disk error,
        # etc.) -- failing before any write happens, not just failing to be removed from
        # inbox/ after it was already saved -- the status message correctly reports the
        # partial failure (1 added, 1 couldn't be added) rather than falsely claiming
        # both were added successfully. Runs in its own fresh library so its doc ids
        # don't collide with Scenario 2's.
        await page.evaluate("""
            () => {
                window.__TEST_ROOT = window.__makeEmptyRoot();
                window.__addInboxFile(window.__TEST_ROOT, 'partial1.pdf');
                window.__addInboxFile(window.__TEST_ROOT, 'partial2.jpg');
            }
        """)
        await page.click('#reload-btn')
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(300)

        # After library opens, checkInbox() runs automatically and discovers both files
        banner_text_before = await page.locator('#inbox-banner-text').inner_text()
        print("banner shows 2 files staged:", '2' in banner_text_before)

        # Make partial2.jpg genuinely unreadable -- addInboxFile() calls entry.handle.getFile()
        # before it writes anything, so this fails the add *before* any document is
        # created, unlike removing the entry from inbox/ (which the add flow doesn't
        # consult until after it's already persisted the document, and so wouldn't
        # actually make the add itself fail).
        await page.evaluate("""
            async () => {
                const inbox = await window.__TEST_ROOT.getDirectoryHandle('inbox');
                const handle = inbox._children.get('partial2.jpg');
                handle.getFile = async () => { const e = new Error('gone'); e.name = 'NotFoundError'; throw e; };
            }
        """)

        # Click the banner's add button; 1 will succeed, 1 will genuinely fail
        await page.click('#inbox-add-all-btn')
        await page.wait_for_timeout(400)

        status_partial = await page.locator('#status').inner_text()
        print("status after partial failure (1 success, 1 fail):", status_partial)
        print("status correctly reports 1 added:", '1' in status_partial and 'added' in status_partial.lower() and 'document' in status_partial.lower())
        print("status correctly reports 1 failed:", '1' in status_partial and 'could not be added' in status_partial.lower())
        print("status shows error (not false success):", 'err' in await page.locator('#status').get_attribute("class"))

        # Only the file that actually succeeded became a real, persisted document --
        # the message's "1 failed" claim is only meaningful if that's actually true.
        persisted_partial = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("only 1 document actually persisted despite staging 2:", len(persisted_partial['documents']))

        inbox_row_count_partial = await page.locator('#doc-tbody tr').count()
        print("Inbox view shows only the 1 doc that actually succeeded:", inbox_row_count_partial)

        # Clean up the permanently-broken file so it doesn't interfere with Scenario 3's
        # "banner hidden on an empty inbox" check below.
        await page.evaluate("""
            async () => {
                const inbox = await window.__TEST_ROOT.getDirectoryHandle('inbox');
                inbox._children.delete('partial2.jpg');
            }
        """)

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

        late_doc_row = await page.locator('tr[data-id="2"]').count()
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
