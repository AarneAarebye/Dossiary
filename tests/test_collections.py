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
        # Doc 4: a member of the manual collection, but archived -- pins the
        # deliberate decision (see matchesView()'s 'collection-<id>' branch and its
        # CLAUDE.md note) that collection views include archived/needs-review
        # documents, unlike the 'all' view's default behavior.
        {
            "id": 4, "title": "Archived Warranty", "category": "Home", "document_type": "Receipt",
            "date": "2026-03-04T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-03-04T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "collections": [
        {"id": 1, "name": "Manual Trip Folder", "kind": "manual", "criteria": None},
        {"id": 2, "name": "Travel Category", "kind": "smart", "criteria": json.dumps({"q": "", "category": "Travel", "type": "", "person": "", "dynamic": []})},
    ],
    "collection_documents": [
        {"collection_id": 1, "document_id": 3},
        {"collection_id": 1, "document_id": 4},
    ],
}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    stub_js = open('stub_studio2.js').read()
    await page.add_init_script(stub_js)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)

        await route_stub(page)
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
        # documents (doc 3 and doc 4), regardless of category ===
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        manual_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Manual collection shows docs 3 and 4:", sorted(manual_row_ids))

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
        # just been in a collection (doc 4 is archived, so it's excluded here) ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        all_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents shows docs 1, 2, 3 (doc 4 archived, hidden by default):", sorted(all_row_ids))

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

        # === Scenario 8: Collections nav section still renders and is reachable
        # after switching nav style (sidebar <-> tabs) -- the *sticky-header height
        # calibration* that this toggle affects is covered separately, with a
        # document seed large enough to actually make it diagnostic (a small seed
        # never overflows .table-wrap's max-height, so a check against one can't
        # tell a correct constant from a wrong one) -- see the dedicated scenario
        # near the end of this file ===
        await page.click('#nav-style-toggle')
        await page.wait_for_timeout(150)
        collections_after_toggle = await page.locator('#nav-collections-section').count()
        print("Collections section still visible after switching nav style:", collections_after_toggle == 1)

        # === Scenario 9: "Save as Smart Collection" is visible only in All
        # Documents -- not inside a collection's own view, nor in Inbox, Waste bin,
        # or Reports. The app's own visibility check has no per-view branching (a
        # single `currentView === 'all'` comparison), so this exercises all of
        # those views, not just one example collection view. Also lives in the
        # Collections nav section now, not .toolbar -- see CLAUDE.md's Collections
        # note on why (a toolbar-wrap regression, fixed by moving it here). ===
        save_smart_btn_in_all = await page.locator('#save-smart-collection-btn').is_visible()
        print("Save-as-Smart-Collection button visible in All Documents:", save_smart_btn_in_all)
        for view_selector, view_label in [
            ('#nav-item-collection-1', 'a manual collection view'),
            ('#nav-item-inbox', 'Inbox'),
            ('#nav-item-trash', 'Waste bin'),
            ('#nav-item-reports', 'Reports'),
        ]:
            await page.click(view_selector)
            await page.wait_for_timeout(150)
            visible = await page.locator('#save-smart-collection-btn').is_visible()
            print(f"Save-as-Smart-Collection button hidden inside {view_label}:", not visible)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 10: setting a category filter and saving creates a new Smart
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

        # === Scenario 11: checkbox column exists, selecting rows shows the bulk bar ===
        checkbox_count = await page.locator('.row-select-checkbox').count()
        print("Row checkboxes present, one per visible row:", checkbox_count == 3)  # doc 4 is archived, hidden by default

        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        bulk_bar_visible = await page.locator('#bulk-action-bar').is_visible()
        bulk_bar_text = await page.locator('#bulk-action-count').inner_text()
        print("Bulk action bar visible with 2 selected:", bulk_bar_visible, bulk_bar_text)

        # Clicking a checkbox must not also open the detail modal (row click delegation).
        modal_open_after_check = await page.locator('#modal-backdrop').count()
        print("Checking a row's checkbox does not open its detail modal:", modal_open_after_check == 0)

        # === Scenario 12: bulk "Add to collection" adds both selected docs to the
        # existing manual collection (which already had docs 3 and 4) ===
        await page.click('#bulk-add-to-collection-btn')
        await page.wait_for_timeout(150)
        await page.click('.bulk-collection-option[data-collection-id="1"]')
        await page.wait_for_timeout(200)

        selection_cleared = await page.locator('#bulk-action-bar').is_visible()
        print("Selection cleared (bulk bar hidden) after adding:", not selection_cleared)

        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        manual_row_ids_after = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Manual collection now has docs 1, 2, 3, and 4:", sorted(manual_row_ids_after))
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 13: selection clears when switching views ===
        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        await page.click('#nav-item-collection-2')
        await page.wait_for_timeout(150)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        bulk_bar_after_view_switch = await page.locator('#bulk-action-bar').is_visible()
        print("Selection cleared after switching views:", not bulk_bar_after_view_switch)

        # === Scenario 14: "+ New collection…" flow works end-to-end (tests the inline
        # form for creating a new manual collection on-the-fly during bulk-add) ===
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.check('tr[data-id="3"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        await page.click('#bulk-add-to-collection-btn')
        await page.wait_for_timeout(150)
        await page.click('#bulk-new-collection-option')
        await page.wait_for_timeout(150)
        await page.fill('#bulk-new-collection-input', 'My New Collection')
        await page.click('#bulk-new-collection-save-btn')
        await page.wait_for_timeout(200)

        # New collection should appear in the nav
        new_coll_nav_labels = await page.locator('.nav-item[data-view^="collection-"] .nav-item-label').all_inner_texts()
        print("New collection 'My New Collection' appears in nav:", 'My New Collection' in new_coll_nav_labels)

        # Click into the new collection and verify it has docs 2 and 3
        new_coll_nav_btn = page.locator('.nav-item[data-view^="collection-"]', has_text='My New Collection')
        await new_coll_nav_btn.click()
        await page.wait_for_timeout(150)
        new_coll_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("New collection contains docs 2 and 3:", sorted(new_coll_row_ids))

        # Go back to All Documents and verify bulk bar is hidden and checkboxes are unchecked
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        bulk_bar_hidden_after_new_coll = await page.locator('#bulk-action-bar').is_visible()
        print("Bulk bar hidden after creating and adding to new collection:", not bulk_bar_hidden_after_new_coll)
        checked_count_after_new_coll = await page.locator('.row-select-checkbox:checked').count()
        print("No checkboxes remain checked after new collection creation:", checked_count_after_new_coll == 0)

        # === Scenario 15: select-all checkbox works ===
        select_all_checkbox = page.locator('#select-all-checkbox')
        await select_all_checkbox.check()
        await page.wait_for_timeout(150)

        # All visible row checkboxes should be checked
        all_checked_count = await page.locator('.row-select-checkbox:checked').count()
        all_total_count = await page.locator('.row-select-checkbox').count()
        print("Select-all checks all visible checkboxes:", all_checked_count == all_total_count)

        # Bulk bar should show correct count
        bulk_bar_text_all = await page.locator('#bulk-action-count').inner_text()
        print("Bulk bar shows correct count after select-all:", f"{all_total_count} selected" in bulk_bar_text_all)

        # Uncheck select-all
        await select_all_checkbox.uncheck()
        await page.wait_for_timeout(150)

        # Bulk bar should disappear
        bulk_bar_hidden_after_uncheck = await page.locator('#bulk-action-bar').is_visible()
        print("Bulk bar hidden after unchecking select-all:", not bulk_bar_hidden_after_uncheck)

        # === Scenario 16: detail modal "Add to collection..." action, single document ===
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        add_to_collection_btn_count = await page.locator('#add-to-collection-btn').count()
        print("Detail modal has an Add-to-collection action:", add_to_collection_btn_count == 1)
        await page.click('#add-to-collection-btn')
        await page.wait_for_timeout(150)
        await page.click('.modal-collection-option[data-collection-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        manual_after_modal_add = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Manual collection includes doc 2 after adding from its detail view:", sorted(manual_after_modal_add))

        # === Scenario 17: detail modal "Remove from this collection" appears only
        # when viewing a document from inside a manual collection's own view, and
        # correctly removes it ===
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        remove_btn_count = await page.locator('#remove-from-collection-btn').count()
        print("Remove-from-collection action shown when viewing from inside the collection:", remove_btn_count == 1)
        await page.click('#remove-from-collection-btn')
        await page.wait_for_timeout(200)

        manual_after_remove = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Doc 2 removed from the manual collection:", sorted(manual_after_remove))
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # Opening a document from All Documents (not from inside a collection) never
        # shows the remove action, even if that document happens to belong to a
        # manual collection (doc 3 has been a member since the SEED).
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        remove_btn_from_all = await page.locator('#remove-from-collection-btn').count()
        print("Remove-from-collection hidden when viewing from All Documents:", remove_btn_from_all == 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 18: Remove-from-collection hidden when viewing from inside a
        # smart collection's view, even though doc 3 is a member of a manual collection
        # (doc 3 matches the smart "Travel Category" collection's criteria) ===
        await page.click('#nav-item-collection-2')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        remove_btn_from_smart = await page.locator('#remove-from-collection-btn').count()
        print("Remove-from-collection hidden when viewing from inside a smart collection:", remove_btn_from_smart == 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 19: Manage Collections modal lists every collection with the
        # right kind and document count ===
        await page.click('#manage-collections-btn')
        await page.wait_for_timeout(150)
        collection_rows = await page.locator('.manage-collection-row').count()
        print("Manage Collections modal lists all collections:", collection_rows)
        row_names = await page.locator('.manage-collection-row .manage-collection-name').all_inner_texts()
        print("Row names:", sorted(row_names))
        travel_count = await page.locator('.manage-collection-row', has_text='Travel Category').locator('.manage-collection-count').inner_text()
        print("Smart Collection's live count reflects current matching docs:", travel_count)

        # === Scenario 20: renaming a collection; an empty rename resets the input
        # back to the real name instead of leaving it blank ===
        manual_row = page.locator('.manage-collection-row', has_text='Manual Trip Folder')
        await manual_row.locator('.manage-collection-rename-input').fill('Trip Docs')
        await manual_row.locator('.manage-collection-rename-input').press('Enter')
        await page.wait_for_timeout(200)
        renamed_label = await page.locator('#nav-collections-list .nav-item-label', has_text='Trip Docs').count()
        print("Rename reflected in the nav:", renamed_label == 1)

        renamed_row = page.locator('.manage-collection-row', has_text='Trip Docs')
        await renamed_row.locator('.manage-collection-rename-input').fill('')
        await renamed_row.locator('.manage-collection-rename-input').press('Enter')
        await page.wait_for_timeout(200)
        reset_value = await renamed_row.locator('.manage-collection-rename-input').input_value()
        print("Empty rename resets the input back to the real name (not left blank):", reset_value == 'Trip Docs')
        still_named_in_nav = await page.locator('#nav-collections-list .nav-item-label', has_text='Trip Docs').count()
        print("Collection is still named 'Trip Docs' in the nav after the empty-rename attempt:", still_named_in_nav == 1)

        # === Scenario 21: "+ New collection" creates an empty manual collection ===
        await page.fill('#manage-new-collection-input', 'Empty Folder')
        await page.click('#manage-new-collection-btn')
        await page.wait_for_timeout(200)
        new_row_count = await page.locator('.manage-collection-row', has_text='Empty Folder').count()
        print("New empty manual collection created:", new_row_count == 1)

        # === Scenario 22: deleting a collection removes it from the nav without
        # touching its member documents ===
        await page.locator('.manage-collection-row', has_text='Empty Folder').locator('.manage-collection-delete-btn').click()
        await page.wait_for_timeout(200)
        deleted_row_count = await page.locator('.manage-collection-row', has_text='Empty Folder').count()
        print("Deleted collection gone from the modal:", deleted_row_count == 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        deleted_nav_count = await page.locator('#nav-collections-list .nav-item-label', has_text='Empty Folder').count()
        print("Deleted collection gone from the nav:", deleted_nav_count == 0)

        # === Scenario 23: an archived document that's a collection member still
        # shows up in that collection's view -- pins the deliberate decision (see
        # matchesView()'s 'collection-<id>' branch and CLAUDE.md's own note) that
        # collection views include archived/needs-review documents, unlike the
        # 'all' view's default behavior. Doc 4 (archived=1) is a member of the
        # manual "Trip Docs" collection per the SEED. ===
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        manual_row_ids_with_archived = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("Archived doc 4 still shows up inside its manual collection:", '4' in manual_row_ids_with_archived)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        archived_hidden_from_all = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("...but doc 4 is still hidden from All Documents by default (confirms it's really archived):", '4' not in archived_hidden_from_all)

        # === Scenario 24: deleting the collection currently being viewed falls back
        # to All Documents instead of leaving a phantom view with nothing selected ===
        await page.click('#nav-item-collection-2')  # "Travel Category" smart collection
        await page.wait_for_timeout(150)
        await page.click('#manage-collections-btn')
        await page.wait_for_timeout(150)
        await page.locator('.manage-collection-row', has_text='Travel Category').locator('.manage-collection-delete-btn').click()
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        all_nav_active = await page.locator('#nav-item-all').get_attribute('class')
        print("Deleting the currently-viewed collection falls back to All Documents (nav-item-all active):", 'active' in (all_nav_active or ''))
        count_line_after_delete = await page.locator('#count-line').text_content()
        print("countLine no longer stuck on the deleted collection's denominator:", 'undefined' not in (count_line_after_delete or ''))

        print("JS ERRORS:", errors)
        await browser.close()

    # === Scenario 25: sticky-header height calibration, across all four
    # combinations of nav style (tabs/sidebar) x bulk-action-bar visibility (hidden/
    # visible) -- a SEPARATE, larger-seeded page, because the earlier scenarios'
    # 3-4 document seed never makes .table-wrap's max-height actually binding (its
    # content is shorter than the max-height, so its rendered bottom edge floats far
    # above the viewport bottom regardless of whether the CSS constant is right or
    # wrong -- exactly the "non-diagnostic" gap a prior review of this feature
    # flagged). 60 documents is comfortably enough to overflow at 1280x720; each
    # state's own scrollHeight > clientHeight check below proves the constraint is
    # actually binding before trusting the bottom-edge measurement that follows it. ===
    async with async_playwright() as p:
        browser2 = await p.chromium.launch()
        page2 = await browser2.new_page(viewport={'width': 1280, 'height': 720})
        errors2 = []
        page2.on("pageerror", lambda exc: errors2.append(str(exc)))

        await route_stub(page2)
        await page2.goto(f"file://{APP_PATH}")
        await page2.wait_for_timeout(200)

        big_docs = [
            {
                "id": i, "title": f"Document {i}", "category": "Travel" if i % 2 == 0 else "Food",
                "document_type": "Receipt", "date": f"2026-03-{(i % 28) + 1:02d}T00:00:00+00:00",
                "notes": None, "ocr_text": None, "ocr_language": None,
                "file_path": f"files/{i}_a.pdf", "original_file_path": None,
                "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
                "archived": 0, "needs_review": 0, "deleted": 0,
            }
            for i in range(1, 61)
        ]
        BIG_SEED = {"documents": big_docs, "tags": [], "document_tags": [], "collections": [], "collection_documents": []}
        await page2.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(BIG_SEED)});")
        await page2.click("#open-btn")
        await page2.wait_for_timeout(400)

        async def measure_calibration(label):
            info = await page2.evaluate("""
                () => {
                    const el = document.querySelector('#table-wrap');
                    const rect = el.getBoundingClientRect();
                    return {
                        bottom: rect.bottom, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight,
                        viewportHeight: window.innerHeight,
                    };
                }
            """)
            distance = info['viewportHeight'] - info['bottom']
            binding = info['scrollHeight'] > info['clientHeight'] + 1
            print(f"[{label}] max-height constraint actually binding (scrollHeight > clientHeight):", binding)
            print(f"[{label}] table-wrap bottom lands within 2px of viewport bottom:", abs(distance) <= 2, f"(distance: {distance:.1f}px)")

        # State A: default nav style, bulk bar hidden
        await measure_calibration("nav style A, bulk bar hidden")

        # State B: default nav style, bulk bar visible
        await page2.check('tr[data-id="1"] .row-select-checkbox')
        await page2.check('tr[data-id="2"] .row-select-checkbox')
        await page2.wait_for_timeout(150)
        await measure_calibration("nav style A, bulk bar VISIBLE")
        await page2.click('#bulk-clear-selection-btn')
        await page2.wait_for_timeout(150)

        # Switch nav style
        await page2.click('#nav-style-toggle')
        await page2.wait_for_timeout(200)

        # State C: other nav style, bulk bar hidden
        await measure_calibration("nav style B, bulk bar hidden")

        # State D: other nav style, bulk bar visible
        await page2.check('tr[data-id="1"] .row-select-checkbox')
        await page2.check('tr[data-id="2"] .row-select-checkbox')
        await page2.wait_for_timeout(150)
        await measure_calibration("nav style B, bulk bar VISIBLE")

        print("JS ERRORS (calibration page):", errors2)
        await browser2.close()

asyncio.run(main())
