import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

async def read_settings(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text()).settings;
        })()
    """)

# Doc 1: a normal document with a manual collection membership available, so
#        Add/Remove-to-collection can be exercised from the panel.
# Doc 2: a second normal document, used to prove selecting a different row
#        moves the highlight and swaps the panel's content.
# Doc 3: deleted -- proves the panel drops to Restore-only, same as the old modal.
SEED = {
    "documents": [
        {
            "id": 1, "title": "First Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Second Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Deleted Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-01-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
    ],
    "tags": [], "document_tags": [],
    "collections": [{"id": 1, "name": "My Collection", "kind": "manual", "criteria": None}],
    "collection_documents": [],
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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: panel starts collapsed by default, and the toggle
        # persists across a reopen ===
        print("panel starts collapsed:", not await page.locator('#main-layout.detail-panel-expanded').count())
        await page.click('#detail-panel-toggle-btn')
        await page.wait_for_timeout(150)
        print("toggle expands the panel:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))
        settings_after_toggle = await read_settings(page)
        expanded_row = next((s for s in settings_after_toggle if s['key'] == 'detail_panel_expanded'), None)
        print("detail_panel_expanded persisted as '1':", expanded_row['value'] if expanded_row else None)

        # Reopen the library via "Switch library" -- a real reopen would read the
        # still-persisted detail_panel_expanded setting back from the same on-disk
        # library.sqlite; here that's simulated by re-seeding a fresh root with
        # detail_panel_expanded already set, matching this suite's existing
        # convention for "does a preference survive a reopen" checks
        # (test_nav.py's own nav_style Scenario 7 does the same). A real
        # page.reload() doesn't work for this: it destroys the stub's in-memory
        # library state entirely, so a freshly re-seeded root after a genuine
        # reload has no way to reflect what a previous session wrote to disk --
        # #reload-btn (the toolbar's own "Switch library") re-reads from
        # window.__TEST_ROOT without tearing down the page's JS context.
        seed_with_expanded = dict(SEED)
        seed_with_expanded['settings'] = [{'key': 'detail_panel_expanded', 'value': '1'}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_expanded)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        print("expanded state persists across reopen:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))

        # === Scenario 2: clicking a row selects/highlights it and shows its
        # metadata; clicking a different row updates both ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        row1_selected = await page.locator('tr[data-id="1"].row-selected').count()
        print("clicking a row highlights it:", row1_selected == 1)
        panel_title_1 = await page.locator('.detail-panel-body h2').inner_text()
        print("panel shows the clicked document's title:", "First Doc" in panel_title_1)

        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        row1_still_selected = await page.locator('tr[data-id="1"].row-selected').count()
        row2_selected = await page.locator('tr[data-id="2"].row-selected').count()
        print("highlight moves to the newly clicked row:", row1_still_selected == 0 and row2_selected == 1)
        panel_title_2 = await page.locator('.detail-panel-body h2').inner_text()
        print("panel content swaps to the new document:", "Second Doc" in panel_title_2)

        # === Scenario 3: every action available in the old modal still works
        # from the panel, refreshing in place ===
        await page.click('#archive-toggle-btn')
        await page.wait_for_timeout(200)
        archived_label = await page.locator('#archive-toggle-btn').inner_text()
        print("Archive toggles to Unarchive in the panel:", 'Unarchive' in archived_label)
        await page.click('#archive-toggle-btn')  # unarchive again, so doc 2 stays visible for later steps
        await page.wait_for_timeout(200)

        await page.click('#review-toggle-btn')
        await page.wait_for_timeout(200)
        review_label = await page.locator('#review-toggle-btn').inner_text()
        print("Flag for review toggles to Done in the panel:", 'Done' in review_label)
        await page.click('#review-toggle-btn')  # clear the flag again
        await page.wait_for_timeout(200)

        await page.click('#add-to-collection-btn')
        await page.wait_for_timeout(150)
        await page.click('.modal-collection-option')
        await page.wait_for_timeout(200)
        remove_btn_absent_outside_collection = await page.locator('#remove-from-collection-btn').count()
        print("Add to collection refreshes the panel (no Remove button outside that collection view):", remove_btn_absent_outside_collection == 0)

        # Actually exercise the collection-membership side, not just the
        # tautological "not shown here" check above: switch into the collection's
        # own nav view and confirm the document is really there, with a working
        # Remove button once viewed from inside it.
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        doc_present_in_collection_view = await page.locator('tr[data-id="2"]').count()
        print("the added document appears in its own collection's nav view:", doc_present_in_collection_view == 1)
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        remove_btn_present_in_collection_view = await page.locator('#remove-from-collection-btn').count()
        print("Remove from collection button appears once viewing from inside that collection:", remove_btn_present_in_collection_view == 1)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        await page.click('#regen-thumb-btn')
        await page.wait_for_timeout(300)
        thumb_status_text = await page.locator('#thumb-status').inner_text()
        print("Regenerate preview reports the expected error (seed docs have no file_path):", "Could not generate preview" in thumb_status_text and "no file" in thumb_status_text.lower())

        # === Scenario 4: a deleted document's panel drops to Restore-only ===
        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        edit_btn_absent = await page.locator('#edit-doc-btn').count()
        archive_btn_absent = await page.locator('#archive-toggle-btn').count()
        restore_btn_present = await page.locator('.detail-panel-body .danger, .detail-panel-body .primary').count()
        print("deleted document's panel drops Edit/Archive entirely:", edit_btn_absent == 0 and archive_btn_absent == 0)
        print("deleted document's panel offers a Restore action:", restore_btn_present >= 1)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 5: Cancel from Edit (reached via the row-level
        # .row-edit-btn shortcut, which bypasses the panel/selection step
        # entirely on the way in) closes the edit modal without forcing a
        # collapsed panel open ===
        await page.click('#detail-panel-toggle-btn')  # collapse it
        await page.wait_for_timeout(150)
        panel_collapsed = not await page.locator('#main-layout.detail-panel-expanded').count()
        print("panel collapsed ahead of Scenario 5:", panel_collapsed)

        # A genuine bare row click (not .row-edit-btn, which has its own
        # stopPropagation() and never exercises this path at all) must never
        # auto-expand a collapsed panel -- the single most load-bearing design
        # rule in this whole feature. Selection, highlighting, and content
        # refresh must still happen unconditionally even while collapsed.
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        still_collapsed_after_row_click = not await page.locator('#main-layout.detail-panel-expanded').count()
        row1_highlighted_while_collapsed = await page.locator('tr[data-id="1"].row-selected').count()
        panel_title_while_collapsed = await page.locator('.detail-panel-body h2').inner_text()
        print("row click never auto-expands a collapsed panel:", still_collapsed_after_row_click)
        print("row click still highlights/selects while collapsed:", row1_highlighted_while_collapsed == 1)
        print("row click still refreshes panel content while collapsed:", "First Doc" in panel_title_while_collapsed)

        await page.click('tr[data-id="1"] .row-edit-btn')
        await page.wait_for_timeout(200)
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(200)
        edit_form_gone = await page.locator('#e-title').count()
        still_collapsed = not await page.locator('#main-layout.detail-panel-expanded').count()
        print("Cancel closes the edit form:", edit_form_gone == 0)
        print("Cancel does not force the panel open:", still_collapsed)

        # === Scenario 6: saving an edit reached via the row-level shortcut
        # (bypassing the panel entirely) selects the just-edited document ===
        await page.click('tr[data-id="2"] .row-edit-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-title', 'Second Doc Renamed')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        edit_form_gone_after_save = await page.locator('#e-title').count()
        row2_selected_after_save = await page.locator('tr[data-id="2"].row-selected').count()
        print("Save closes the edit form:", edit_form_gone_after_save == 0)
        print("Save via the row-edit shortcut selects the just-edited document:", row2_selected_after_save == 1)

        # === Scenario 7: toggle button absent in Reports view, and the panel
        # itself has no presence there either -- not just the toggle button
        # hidden while the panel stays stuck open (and uncollapsible, since the
        # only control that could close it is the very button that's hidden)
        # underneath. Expand the panel first so switching to Reports is a
        # meaningful check, not vacuously true because it was already collapsed. ===
        await page.click('#detail-panel-toggle-btn')  # expand it
        await page.wait_for_timeout(150)
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        toggle_hidden_in_reports = await page.locator('#detail-panel-toggle-btn:visible').count()
        panel_hidden_in_reports = await page.locator('.detail-panel:visible').count()
        print("detail panel toggle hidden in Reports view:", toggle_hidden_in_reports == 0)
        print("detail panel itself has no presence in Reports view:", panel_hidden_in_reports == 0)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.click('#detail-panel-toggle-btn')  # collapse it again, restoring the state Scenario 8 expects below
        await page.wait_for_timeout(150)

        # === Scenario 8: panel force-collapses below the mobile breakpoint
        # regardless of the saved preference ===
        await page.click('#detail-panel-toggle-btn')  # re-expand
        await page.wait_for_timeout(150)
        await page.set_viewport_size({"width": 375, "height": 800})
        await page.wait_for_timeout(150)
        panel_hidden_mobile = await page.locator('.detail-panel:visible').count()
        print("panel force-collapses below the mobile breakpoint:", panel_hidden_mobile == 0)

        # === Scenario 9: selectedDocId invalidation resets the panel to its
        # empty state (and drops the row highlight) once the currently-selected
        # document falls out of the active filtered view -- previously
        # zero automated coverage. Uses the search box against the two
        # already-seeded documents (no new seed data needed) rather than a
        # view switch, since a view switch's own exclusion behavior is already
        # exercised structurally by Scenario 4's trash/all transition. ===
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        row1_selected_before_search = await page.locator('tr[data-id="1"].row-selected').count()
        print("Scenario 9 setup: doc 1 selected before filtering:", row1_selected_before_search == 1)

        await page.fill('#search', 'Second Doc Renamed')
        await page.wait_for_timeout(200)
        row1_absent_from_filtered_view = await page.locator('tr[data-id="1"]').count()
        print("doc 1 excluded from the filtered view by the search text:", row1_absent_from_filtered_view == 0)
        panel_reset_to_empty = await page.locator('.detail-panel-empty').count()
        no_row_highlighted_after_invalidation = await page.locator('tr.row-selected').count()
        print("panel resets to its empty state once the selected doc falls out of view:", panel_reset_to_empty == 1)
        print("no row remains highlighted after invalidation:", no_row_highlighted_after_invalidation == 0)
        await page.fill('#search', '')
        await page.wait_for_timeout(200)

        # === Scenario 10: double-clicking a row opens its file; a document with
        # no file_path is a silent no-op; a single click never opens anything ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Doc With File')
        with open('detailpaneldblclick.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 detailpaneldblclick")
        await page.set_input_files('#file-input', 'detailpaneldblclick.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # single click on the new row must not open anything
        # (this Playwright version's expect_event __aexit__ itself awaits the
        # event's value, so the TimeoutError from a not-fired "popup" surfaces
        # right at the `async with` block's own exit -- the whole block needs
        # to be wrapped in try/except, not just a bare `.value` await after it,
        # or the expected-timeout case would crash the script instead of being
        # caught, as first observed running this scenario)
        single_click_opened_nothing = False
        try:
            async with page.expect_event('popup', timeout=1000):
                await page.click('tr[data-id="4"]')
                await page.wait_for_timeout(300)
        except Exception:
            single_click_opened_nothing = True
        print("single click does not open the file:", single_click_opened_nothing)

        # double click opens the file in a new tab
        async with page.expect_event('popup', timeout=3000) as popup_info:
            await page.dblclick('tr[data-id="4"]')
        popup = await popup_info.value
        print("double-click opens the file in a new tab:", popup is not None)
        await popup.close()

        # a document with no file_path is a silent no-op on double-click -- no
        # popup opens
        no_file_dblclick_no_popup = False
        try:
            async with page.expect_event('popup', timeout=1000):
                await page.dblclick('tr[data-id="1"]')
        except Exception:
            no_file_dblclick_no_popup = True
        print("double-click on a document with no file_path opens nothing:", no_file_dblclick_no_popup)

        _os.remove('detailpaneldblclick.pdf')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
