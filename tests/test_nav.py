import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1/2: both in All Documents, different categories -- lets us prove a category
#          filter narrows within a view rather than just within the whole library.
# Doc 3: flagged for review (Inbox view), title contains "Invoice" like doc 1 --
#        lets us prove search composes with the Inbox view's own document set.
# Doc 4: deleted (Waste bin view), title contains "Invoice" too -- same idea for
#        Waste bin.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Old Invoice", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Grocery Receipt", "category": "Personal", "document_type": "Receipt",
            "date": "2026-01-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-01-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Pending Invoice", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-03T00:00:00+00:00", "source": "scan-inbox", "source_legacy_id": None,
            "archived": 0, "needs_review": 1, "deleted": 0,
        },
        {
            "id": 4, "title": "Old Invoice Copy", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-04T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-01-04T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
    ],
    "tags": [], "document_tags": [],
}

async def read_settings(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text()).settings;
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: the old review-queue/waste-bin UI is genuinely gone ===
        waste_bin_btn_count = await page.locator('#waste-bin-btn').count()
        review_queue_count = await page.locator('#review-queue').count()
        print("#waste-bin-btn no longer exists:", waste_bin_btn_count == 0)
        print("#review-queue no longer exists:", review_queue_count == 0)

        # === Scenario 2: the separate, unrelated "Check inbox" (raw staged files)
        # feature still works and isn't conflated with the new Inbox nav item ===
        inbox_check_count = await page.locator('#inbox-check-btn').count()
        print("#inbox-check-btn still present:", inbox_check_count == 1)
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(200)
        staged_modal_heading = await page.locator('.modal h2').first.inner_text()
        print("Check inbox opens the staged-files Inbox modal, not the nav view:", staged_modal_heading)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 3: category filter composes with the Inbox nav view -- doc 3
        # is the only Inbox document, and it has no category, so filtering by
        # "Finance" should hide it even though it's otherwise in scope ===
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        inbox_before_filter = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Inbox view before filtering:", inbox_before_filter)
        # populateFilters() only lists categories/types that exist among allDocs, so
        # "Finance" is available even though it doesn't appear on any Inbox document.
        await page.select_option('#category-filter', 'Finance')
        await page.wait_for_timeout(150)
        inbox_after_filter = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Inbox view filtered by an unrelated category shows nothing:", inbox_after_filter)
        await page.select_option('#category-filter', '')
        await page.wait_for_timeout(150)

        # === Scenario 4: search composes with the Waste bin nav view -- both All
        # Documents docs 1/4 contain "Invoice", but only doc 4 is in Waste bin ===
        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        await page.fill('#search', 'Invoice')
        await page.wait_for_timeout(150)
        trash_search_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Waste bin filtered by search 'Invoice' shows only doc 4, not doc 1:", trash_search_ids)
        await page.click('#search-clear')
        await page.wait_for_timeout(150)

        # === Scenario 5: search also composes with All Documents (sanity check the
        # same mechanism still works on the default view) ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.fill('#search', 'Invoice')
        await page.wait_for_timeout(150)
        all_search_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents filtered by search 'Invoice' shows only doc 1:", all_search_ids)
        await page.click('#search-clear')
        await page.wait_for_timeout(150)

        # === Scenario 6: badge counts are correct on load and stay live after a
        # mutation (archiving doc 2 doesn't change any nav badge, since archived
        # docs without needs_review/deleted still count toward All Documents only
        # once "Show archived" independently reveals them -- but the count itself,
        # per renderNav()'s own definition, reflects matchesView() with the CURRENT
        # showArchivedToggle state, so archiving doc 2 while unchecked should drop
        # the All Documents count by one) ===
        all_count_initial = await page.locator('#nav-count-all').inner_text()
        inbox_count_initial = await page.locator('#nav-count-inbox').inner_text()
        trash_count_initial = await page.locator('#nav-count-trash').inner_text()
        print("initial badges (all, inbox, trash):", all_count_initial, inbox_count_initial, trash_count_initial)

        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        await page.click('#archive-toggle-btn')
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        all_count_after_archive = await page.locator('#nav-count-all').inner_text()
        print("All Documents badge drops by one after archiving doc 2 (Show archived unchecked):", all_count_after_archive)

        # === Scenario 7: nav_style setting persists across a reopen ===
        await page.click('#nav-style-toggle')
        await page.wait_for_timeout(200)
        main_layout_class = await page.get_attribute('#main-layout', 'class')
        print("main-layout gets nav-style-sidebar class after toggling:", main_layout_class)
        settings_after_toggle = await read_settings(page)
        nav_style_row = next((s for s in settings_after_toggle if s['key'] == 'nav_style'), None)
        print("nav_style persisted as 'sidebar':", nav_style_row['value'] if nav_style_row else None)

        # Reopen the library via "Switch library" -- a real reopen would read the
        # still-persisted nav_style setting back from the same on-disk
        # library.sqlite; here that's simulated by re-seeding a fresh root with
        # nav_style already set, matching this suite's existing convention for
        # "does a preference survive a reopen" checks (test_recent_libraries.py
        # and others do the same). window.__TEST_ROOT must be updated BEFORE
        # clicking #reload-btn, since that click's handler calls openLibrary()
        # (and therefore the stubbed showDirectoryPicker()) synchronously.
        seed_with_style = dict(SEED)
        seed_with_style['settings'] = [{'key': 'nav_style', 'value': 'sidebar'}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_style)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        main_layout_class_after_reopen = await page.get_attribute('#main-layout', 'class')
        print("nav-style-sidebar class survives reopen:", main_layout_class_after_reopen)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
