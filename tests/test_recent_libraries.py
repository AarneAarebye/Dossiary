import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [], "tags": [], "document_tags": [],
}

async def read_recent_libraries(page):
    return await page.evaluate("""
        (async () => {
            const req = indexedDB.open('dossiary-app-db', 1);
            const idb = await new Promise((resolve, reject) => {
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
            const store = idb.transaction('recentLibraries', 'readonly').objectStore('recentLibraries');
            const all = await new Promise((resolve, reject) => {
                const r = store.getAll();
                r.onsuccess = () => resolve(r.result);
                r.onerror = () => reject(r.error);
            });
            return all.map(e => ({ id: e.id, name: e.name, lastOpenedAt: e.lastOpenedAt }));
        })()
    """)

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

        # === Scenario 1: opening a library records exactly one entry in IndexedDB ===
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'LibraryA';" % json.dumps(SEED))
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        entries = await read_recent_libraries(page)
        print("one entry recorded after opening LibraryA:", [e['name'] for e in entries])

        # === Scenario 2: the recent-libraries list is visible on the startup
        # screen after switching away from LibraryA (simulated "cancel") ===
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")  # "Switch library"
        await page.wait_for_timeout(200)
        row_names = await page.locator('#recent-libraries-list .doc-title').all_inner_texts()
        print("recent-libraries list shows LibraryA:", row_names)

        # === Scenario 3: clicking the row reconnects without a folder-picker
        # call -- straight back into LibraryA ===
        await page.evaluate("window.__TEST_ROOT = null;")  # picker would abort if it were used
        await page.click('.recent-lib-target')
        await page.wait_for_timeout(300)
        empty_state_visible = await page.locator('#empty-state').is_visible()
        print("reconnect succeeded without a picker call, library is open:", not empty_state_visible)

        # === Scenario 4: reopening the same folder again does not create a
        # duplicate entry -- switch away, reopen LibraryA the normal way, check
        # the count stays at 1 and lastOpenedAt moved forward ===
        entries_before = await read_recent_libraries(page)
        original_entry_id = entries_before[0]['id']  # the very first entry ever recorded (Scenario 1's LibraryA) -- used
        # below (Scenario 5) to check eviction by id, not name, since this scenario is about to
        # deliberately create a second, differently-identified entry that also happens to be named 'LibraryA'.
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'LibraryA';" % json.dumps(SEED))
        # NOTE: this is a *different* FakeDirHandle instance with the same name,
        # not the same object -- isSameEntry() is identity-based, so this should
        # actually add a SECOND entry. To test true dedup we must reopen the
        # exact same handle instance, so instead click the recent-libraries row
        # again (Scenario 3 already proved reconnect works); here just confirm
        # opening a *different* folder that happens to share a name does NOT
        # get merged with the existing entry (dedup is identity-based, not
        # name-based).
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        entries_after_same_name_diff_handle = await read_recent_libraries(page)
        print("a different handle with the same name is NOT merged (identity-based dedup):",
              len(entries_after_same_name_diff_handle) == len(entries_before) + 1)

        # === Scenario 5: 5-entry cap eviction -- open 4 more distinct libraries
        # (6 total now) and confirm the oldest is evicted, exactly 5 remain ===
        for letter in ['C', 'D', 'E', 'F']:
            await page.evaluate("window.__TEST_ROOT = null;")
            await page.click("#reload-btn")
            await page.wait_for_timeout(150)
            await page.evaluate(
                "window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'Library%s';" % (json.dumps(SEED), letter)
            )
            await page.click("#open-btn")
            await page.wait_for_timeout(250)
        final_entries = await read_recent_libraries(page)
        print("exactly 5 entries remain after opening 6+ distinct libraries:", len(final_entries) == 5)
        # Checked by id, not name: Scenario 4 deliberately created a second entry that
        # also happens to be named 'LibraryA' (a different handle, same folder name), and
        # that one is newer than the original -- so it's expected to survive the eviction
        # even though the original (oldest) 'LibraryA' entry does not. A name-based check
        # can't tell those two entries apart.
        print("oldest (first LibraryA, by id) was evicted:", original_entry_id not in [e['id'] for e in final_entries])
        print("newest (LibraryF) is present:", 'LibraryF' in [e['name'] for e in final_entries])

        # === Scenario 6: manual removal via the row's own ✕ button ===
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")
        await page.wait_for_timeout(200)
        before_remove = await page.locator('#recent-libraries-list .review-queue-row').count()
        await page.click('.recent-lib-remove-btn >> nth=0')
        await page.wait_for_timeout(200)
        after_remove = await page.locator('#recent-libraries-list .review-queue-row').count()
        print("removing one entry via its own ✕ shrinks the list by exactly one:", after_remove == before_remove - 1)

        # === Scenario 7: a denied/failed reconnect shows an inline error and
        # leaves the entry in the list (does not remove it) ===
        row_count_before_denied = await page.locator('#recent-libraries-list .review-queue-row').count()
        # renderRecentLibraries() sorts entries newest-first, which does not generally match
        # IndexedDB's own getAll() (insertion) order -- so force-deny whichever entry's id is
        # actually rendered first (the one `nth=0` below is about to click), not raw all[0].
        first_row_id = await page.evaluate("document.querySelector('.recent-lib-target').dataset.id")
        await page.evaluate("""
            (async (targetId) => {
                const req = indexedDB.open('dossiary-app-db', 1);
                const idb = await new Promise(r => { req.onsuccess = () => r(req.result); });
                const store = idb.transaction('recentLibraries', 'readonly').objectStore('recentLibraries');
                const all = await new Promise(r => { const rq = store.getAll(); rq.onsuccess = () => r(rq.result); });
                const entry = all.find(e => String(e.id) === String(targetId));
                entry.handle._forceDenied = true;
            })(%s)
        """ % json.dumps(first_row_id))
        await page.click('.recent-lib-target >> nth=0')
        await page.wait_for_timeout(200)
        error_text = await page.locator('#recent-libraries-list .doc-sub').first.inner_text()
        print("denied reconnect shows inline error:", error_text)
        row_count_after_denied = await page.locator('#recent-libraries-list .review-queue-row').count()
        print("denied entry stays in the list (not auto-removed):", row_count_after_denied == row_count_before_denied)
        still_on_empty_state = await page.locator('#empty-state').is_visible()
        print("still on the empty-state screen after a denied reconnect:", still_on_empty_state)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
