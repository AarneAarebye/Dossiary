import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: Category "Travel" -- matches the smart collection's saved criteria below.
# Doc 2: Category "Food" -- does NOT match the smart collection's criteria, and is
#        NOT a member of the manual collection either.
# Doc 3: Category "Travel" -- also matches the smart collection's criteria, proving
#        it's a live filter (multiple documents can match), and is separately also a
#        member of the manual collection (proving the two mechanisms are independent).
SEED = {
    "documents": [
        {
            "id": 1, "title": "Flight Receipt", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Grocery Receipt", "category": "Food", "document_type": "Receipt",
            "date": "2026-03-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-03-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Hotel Receipt", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-03-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "collections": [
        {"id": 1, "name": "Manual Trip Folder", "kind": "manual", "criteria": None},
        {"id": 2, "name": "Travel Category", "kind": "smart", "criteria": json.dumps({"q": "", "category": "Travel", "type": "", "person": "", "dynamic": []})},
    ],
    "collection_documents": [
        {"collection_id": 1, "document_id": 3},
    ],
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

        # === Scenario 1: the Collections nav section exists, expanded by default,
        # listing both seeded collections alphabetically ===
        section_count = await page.locator('#nav-collections-section').count()
        print("Collections nav section exists:", section_count == 1)
        collection_nav_labels = await page.locator('.nav-item[data-view^="collection-"] .nav-item-label').all_inner_texts()
        print("Collection nav items, alphabetical:", collection_nav_labels)

        # === Scenario 2: clicking the manual collection shows only its member
        # document (doc 3), regardless of category ===
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        manual_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Manual collection shows only doc 3:", manual_row_ids)

        # === Scenario 3: clicking the smart collection live-filters by its saved
        # criteria (Category = Travel) -- docs 1 and 3, not doc 2 ===
        await page.click('#nav-item-collection-2')
        await page.wait_for_timeout(150)
        smart_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Smart collection shows docs 1 and 3 (Category=Travel), not doc 2:", smart_row_ids)

        # === Scenario 4: the toolbar's own filters still compose on top of a
        # collection's scope, same as every other view -- searching within the smart
        # collection for "Hotel" narrows it to just doc 3 ===
        await page.fill('#search', 'Hotel')
        await page.wait_for_timeout(150)
        smart_search_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Search composes with the smart collection's own scope:", smart_search_ids)
        await page.click('#search-clear')
        await page.wait_for_timeout(150)

        # === Scenario 5: switching back to All Documents still shows every
        # non-archived/non-deleted/non-needs-review document, unaffected by having
        # just been in a collection ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        all_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents shows all 3 docs:", sorted(all_row_ids))

        # === Scenario 6: Collections section expand/collapse persists via settings,
        # the same way nav_style already does ===
        collections_section_class = await page.locator('#nav-collections-section').get_attribute('class')
        print("Collections section starts expanded (no 'collapsed' class):", 'collapsed' not in (collections_section_class or ''))

        await page.click('#nav-collections-toggle')
        await page.wait_for_timeout(150)
        collections_section_class_after = await page.locator('#nav-collections-section').get_attribute('class')
        print("Collections section collapsed after clicking the toggle:", 'collapsed' in (collections_section_class_after or ''))

        settings_after = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).settings;
            })()
        """)
        collapsed_setting = next((s for s in settings_after if s['key'] == 'collections_nav_expanded'), None)
        print("collections_nav_expanded persisted as '0':", collapsed_setting['value'] if collapsed_setting else None)

        # === Scenario 7: countLine shows correct denominator for collection views (not "undefined") ===
        # Re-expand collections section if it's still collapsed
        collections_section_class = await page.locator('#nav-collections-section').get_attribute('class')
        if 'collapsed' in (collections_section_class or ''):
            await page.click('#nav-collections-toggle')
            await page.wait_for_timeout(150)

        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        count_line_text = await page.locator('#count-line').text_content()
        print("countLine for manual collection has valid denominator (not 'undefined'):", 'undefined' not in (count_line_text or ''))
        print("countLine text for manual collection:", count_line_text)

        await page.click('#nav-item-collection-2')
        await page.wait_for_timeout(150)
        count_line_text_smart = await page.locator('#count-line').text_content()
        print("countLine for smart collection has valid denominator (not 'undefined'):", 'undefined' not in (count_line_text_smart or ''))

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 8: verify nav layout doesn't break sticky header height calibration (tabs mode) ===
        # Re-expand collections section if it's still collapsed
        collections_section_class = await page.locator('#nav-collections-section').get_attribute('class')
        if 'collapsed' in (collections_section_class or ''):
            await page.click('#nav-collections-toggle')
            await page.wait_for_timeout(150)

        table_wrap_rect = await page.evaluate("""
            () => {
                const el = document.querySelector('#table-wrap');
                const rect = el.getBoundingClientRect();
                return { top: rect.top, bottom: rect.bottom, height: rect.height };
            }
        """)
        viewport_height = await page.evaluate("() => window.innerHeight")
        table_bottom_distance = viewport_height - table_wrap_rect['bottom']
        print("Table-wrap bottom lands near viewport bottom (tabs mode):", abs(table_bottom_distance) <= 2, f"(distance: {table_bottom_distance}px)")

        # === Scenario 9: verify nav layout works correctly in sidebar mode ===
        await page.click('#nav-style-toggle')
        await page.wait_for_timeout(150)

        table_wrap_rect_sidebar = await page.evaluate("""
            () => {
                const el = document.querySelector('#table-wrap');
                const rect = el.getBoundingClientRect();
                return { top: rect.top, bottom: rect.bottom, height: rect.height };
            }
        """)
        table_bottom_distance_sidebar = viewport_height - table_wrap_rect_sidebar['bottom']
        print("Table-wrap bottom lands near viewport bottom (sidebar mode):", abs(table_bottom_distance_sidebar) <= 2, f"(distance: {table_bottom_distance_sidebar}px)")

        # Verify collections section is still visible and functional in sidebar mode
        sidebar_collections = await page.locator('#nav-collections-section').count()
        print("Collections section still visible in sidebar mode:", sidebar_collections == 1)

        # === Scenario 7: "Save as Smart Collection" is visible only in All
        # Documents, not inside a collection's own view ===
        save_smart_btn_in_all = await page.locator('#save-smart-collection-btn').is_visible()
        print("Save-as-Smart-Collection button visible in All Documents:", save_smart_btn_in_all)
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        save_smart_btn_in_collection = await page.locator('#save-smart-collection-btn').is_visible()
        print("Save-as-Smart-Collection button hidden inside a collection view:", not save_smart_btn_in_collection)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 8: setting a category filter and saving creates a new Smart
        # Collection that live-filters the same way the seeded one does ===
        await page.select_option('#category-filter', 'Food')
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.wait_for_timeout(150)
        await page.fill('#smart-collection-name-input', 'Food Category')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(200)
        await page.select_option('#category-filter', '')
        await page.wait_for_timeout(150)

        new_collection_labels = await page.locator('.nav-item[data-view^="collection-"] .nav-item-label').all_inner_texts()
        print("New Smart Collection appears in the nav:", 'Food Category' in new_collection_labels)

        new_smart_nav_btn = page.locator('.nav-item[data-view^="collection-"]', has_text='Food Category')
        await new_smart_nav_btn.click()
        await page.wait_for_timeout(150)
        new_smart_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("New Smart Collection shows only doc 2 (Category=Food):", new_smart_row_ids)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
