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

        # === Scenario 2: Review modal lists both files; add one individually ===
        await page.click('#inbox-review-btn')
        await page.wait_for_timeout(150)
        row_count = await page.locator('#inbox-list .file-preview').count()
        print("inbox modal row count:", row_count)

        # The modal shows which folder it's actually reading from -- plain text, not a
        # link, since the File System Access API exposes no absolute path and there's
        # no way to open a native file manager from a browser tab.
        modal_text = await page.locator('.modal').inner_text()
        print("modal shows the library's folder name:", 'EmptyLibrary/inbox/' in modal_text)

        await page.click('.inbox-add-one-btn[data-name="scan001.pdf"]')
        await page.wait_for_timeout(300)
        row_count_after = await page.locator('#inbox-list .file-preview').count()
        print("inbox modal row count after adding one:", row_count_after)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # The saved document should carry only the file + a filename-derived title --
        # nothing else assumed -- and land with source 'scan-inbox'.
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1 = persisted['documents'][0]
        print("doc1:", {k: doc1[k] for k in ['id', 'title', 'category', 'document_type', 'date', 'source', 'file_path']})
        print("inbox-added doc gets a real original_file_path (should not be None):", doc1.get('original_file_path'))
        print("inbox-added doc searchable_pdf_built (should be 0):", doc1.get('searchable_pdf_built'))

        inbox_after_one = await page.evaluate("""
            (async () => {
                const inbox = await window.__TEST_ROOT.getDirectoryHandle('inbox');
                const names = [];
                for await (const [name] of inbox.entries()) names.push(name);
                return names;
            })()
        """)
        print("inbox/ contents after adding scan001.pdf:", inbox_after_one)

        files_after_one = await page.evaluate("""
            (async () => {
                const files = await window.__TEST_ROOT.getDirectoryHandle('files');
                const names = [];
                for await (const [name] of files.entries()) names.push(name);
                return names;
            })()
        """)
        print("files/ contents after adding scan001.pdf:", files_after_one)

        # An inbox-added document lands flagged for review (needs_review=1, see
        # addInboxFile()), so it shows in the review queue, not the main table, until
        # someone clicks Done -- see CLAUDE.md's review-queue note.
        main_rows_before_done = await page.locator('#doc-tbody tr').count()
        print("main table rows before Done (should be 0, doc lives in the review queue):", main_rows_before_done)
        queue_row_count = await page.locator('.review-queue-row[data-id="1"]').count()
        print("review queue shows the inbox-added doc:", queue_row_count)

        await page.click('.review-queue-row[data-id="1"] .review-done-btn')
        await page.wait_for_timeout(200)

        # Once reviewed, it moves into the main table and shows the inbox-added pill.
        pill_text = await page.locator('tr[data-id="1"] .pill.captured').inner_text()
        print("table pill for inbox-added doc after Done:", pill_text)

        # === Scenario 3: "Add all with defaults" clears the rest and the banner disappears ===
        await page.click('#inbox-review-btn')
        await page.wait_for_timeout(150)
        await page.click('#inbox-add-all-btn')
        await page.wait_for_timeout(300)
        modal_gone = await page.locator('#modal-backdrop').count()
        print("modal closed after add-all emptied the inbox:", modal_gone == 0)

        banner_visible_after = await page.locator('#inbox-banner').is_visible()
        print("banner visible after inbox emptied:", banner_visible_after)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("total documents after add-all:", len(persisted2['documents']))
        print("sources:", sorted(d['source'] for d in persisted2['documents']))

        # === Scenario 4: reopening the (now-empty) library keeps the banner hidden ===
        # #reload-btn's own click handler calls resetAll() then openLibrary() -- the stub's
        # showDirectoryPicker keeps returning the same __TEST_ROOT, and library.sqlite
        # already exists on it now, so this re-loads straight in without #init-btn.
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        banner_on_reopen = await page.locator('#inbox-banner').is_visible()
        print("banner visible on reopening an already-emptied library:", banner_on_reopen)

        # === Scenario 5: a file staged (e.g. by scan_watch.py) *after* the library was
        # already open doesn't show up on its own -- checkInbox() only runs once, right
        # after the library opens (see afterDbReady()) -- but the always-visible
        # "Check inbox" toolbar button lets someone notice it without fully reopening
        # the library ===
        await page.evaluate("window.__addInboxFile(window.__TEST_ROOT, 'late_arrival.pdf');")
        banner_still_hidden = await page.locator('#inbox-banner').is_visible()
        print("banner still hidden right after a late file is staged (no auto-poll):", not banner_still_hidden)

        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(200)
        late_row_count = await page.locator('#inbox-list .file-preview').count()
        print("'Check inbox' opens the modal showing the late-arriving file:", late_row_count)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        banner_visible_after_check = await page.locator('#inbox-banner').is_visible()
        print("banner now reflects it too, after the manual check:", banner_visible_after_check)

        print("JS errors:", errors)
        await browser.close()

asyncio.run(main())
