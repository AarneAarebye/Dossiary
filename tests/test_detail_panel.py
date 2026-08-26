import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import tempfile

def _write_patched_app_with_preview_enabled():
    """Writes a copy of dossiary.html with SHOW_DOCUMENT_PREVIEW flipped to
    true, so this file's "every panel action still works" coverage
    (including Regenerate preview) keeps exercising the real pipeline even
    though it now defaults to off (see dossiary.html's own
    SHOW_DOCUMENT_PREVIEW comment). Returns the temp file's path; caller
    is responsible for deleting it."""
    with open(APP_PATH) as f:
        html = f.read()
    target = "const SHOW_DOCUMENT_PREVIEW = false;"
    replacement = "const SHOW_DOCUMENT_PREVIEW = true;"
    assert target in html, "SHOW_DOCUMENT_PREVIEW declaration not found -- did its exact text change in dossiary.html?"
    patched = html.replace(target, replacement)
    fd, path = tempfile.mkstemp(suffix='.html', dir=_os2.path.dirname(APP_PATH))
    with _os2.fdopen(fd, 'w') as f:
        f.write(patched)
    return path

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
        patched_app_path = _write_patched_app_with_preview_enabled()
        await page.goto(f"file://{patched_app_path}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: panel starts EXPANDED by default (no saved setting),
        # an explicit '0' opt-out still collapses it, and an explicit '1' still
        # keeps it expanded, all surviving a reopen ===
        print("panel starts expanded with no saved setting:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))

        # Reopen with an explicit '0' -- the deliberate opt-out must still work
        # even though the no-row-at-all default flipped to expanded. See
        # test_nav.py's own nav_style Scenario 7 for the established "simulate a
        # reopen via re-seeding + #reload-btn" convention this mirrors; a real
        # page.reload() doesn't work here since it destroys the stub's in-memory
        # library state entirely.
        seed_with_collapsed = dict(SEED)
        seed_with_collapsed['settings'] = [{'key': 'detail_panel_expanded', 'value': '0'}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_collapsed)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        print("explicit '0' still collapses the panel:", not await page.locator('#main-layout.detail-panel-expanded').count())

        # Toggling it from here persists '1' -- the existing toggle/persistence
        # mechanics are otherwise completely unchanged by the default flip.
        await page.click('#detail-panel-toggle-btn')
        await page.wait_for_timeout(150)
        settings_after_toggle = await read_settings(page)
        expanded_row = next((s for s in settings_after_toggle if s['key'] == 'detail_panel_expanded'), None)
        print("toggling from collapsed persists '1':", expanded_row['value'] if expanded_row else None)

        # Reopen once more with that explicit '1' -- still expanded, and this is
        # the state every later scenario in this file expects the panel to be in.
        seed_with_expanded = dict(SEED)
        seed_with_expanded['settings'] = [{'key': 'detail_panel_expanded', 'value': '1'}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_expanded)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        print("explicit '1' persists as expanded across reopen:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))

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

        # .row-edit-btn only renders below the 640px mobile breakpoint now (see
        # "Hide the row-level Edit shortcut except below the mobile breakpoint")
        # -- it's hidden entirely at this file's default desktop viewport, so
        # both remaining uses of it below (Scenarios 5-6) need a mobile width.
        await page.set_viewport_size({"width": 375, "height": 800})
        await page.wait_for_timeout(150)

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

        # Back to desktop width, so Scenario 8's own mobile-viewport transition
        # below is a meaningful before/after check rather than vacuous (it
        # would otherwise already be at 375px by the time it gets there).
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.wait_for_timeout(150)

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

        # Back to desktop width -- Scenario 8 left the viewport at 375x800 for
        # its own mobile check and never restored it, so without this,
        # Scenario 10's double-click coverage (below) would only ever run at
        # mobile width, never desktop.
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.wait_for_timeout(150)

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

        # double-clicking the select checkbox must not open the file -- the
        # checkbox's own stopPropagation() covers click but not dblclick, so
        # this needs its own explicit guard in the dblclick handler
        checkbox_dblclick_opened_nothing = False
        try:
            async with page.expect_event('popup', timeout=1000):
                await page.dblclick('tr[data-id="4"] .select-col')
        except Exception:
            checkbox_dblclick_opened_nothing = True
        print("double-clicking the select checkbox does not open the file:", checkbox_dblclick_opened_nothing)

        _os.remove('detailpaneldblclick.pdf')

        # === Scenario 11: right-click selects the row and opens a context
        # menu, whether or not the panel is currently expanded ===
        await page.click('#detail-panel-toggle-btn')  # collapse it, so this genuinely exercises "regardless of panel state"
        await page.wait_for_timeout(150)
        panel_collapsed_before_right_click = not await page.locator('#main-layout.detail-panel-expanded').count()
        print("panel collapsed ahead of Scenario 11:", panel_collapsed_before_right_click)

        await page.click('tr[data-id="2"]', button='right')
        await page.wait_for_timeout(200)
        row2_selected_via_right_click = await page.locator('tr[data-id="2"].row-selected').count()
        print("right-click selects/highlights the row:", row2_selected_via_right_click == 1)
        menu_visible = await page.locator('.row-context-menu:visible').count()
        print("right-click opens the context menu:", menu_visible == 1)

        # === Scenario 12: the context menu's action set matches the panel's
        # own, minus Regenerate preview, plus Detail ===
        menu_item_texts = await page.locator('.row-context-menu .row-context-menu-item').all_inner_texts()
        print("Regenerate preview never appears in the context menu:", not any('preview' in t.lower() for t in menu_item_texts))
        print("Detail item is present:", any('Details' in t for t in menu_item_texts))
        print("Edit is present:", any(t == 'Edit' for t in menu_item_texts))
        print("Archive is present:", any(t == 'Archive' for t in menu_item_texts))
        print("Delete is present:", any(t == 'Delete' for t in menu_item_texts))

        # === Scenario 13: "Detail" toggles the panel without changing
        # selection; selecting a different row afterward doesn't itself
        # change panel visibility ===
        await page.click('.row-context-menu .row-context-menu-item:has-text("Show Details")')
        await page.wait_for_timeout(150)
        panel_expanded_after_detail_click = bool(await page.locator('#main-layout.detail-panel-expanded').count())
        print("Detail expands the panel:", panel_expanded_after_detail_click)
        still_row2_selected = await page.locator('tr[data-id="2"].row-selected').count()
        print("Detail does not change which document is selected:", still_row2_selected == 1)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(150)
        panel_still_expanded_after_other_selection = bool(await page.locator('#main-layout.detail-panel-expanded').count())
        print("selecting a different row afterward doesn't change panel visibility:", panel_still_expanded_after_other_selection)

        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(200)
        await page.click('.row-context-menu .row-context-menu-item:has-text("Hide Details")')
        await page.wait_for_timeout(150)
        panel_collapsed_after_second_detail_click = not await page.locator('#main-layout.detail-panel-expanded').count()
        print("Detail collapses the panel on a second invocation:", panel_collapsed_after_second_detail_click)

        # === Scenario 14: a representative action (Archive) actually does
        # the same thing from the context menu as it does from the panel ===
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(200)
        await page.click('.row-context-menu .row-context-menu-item:has-text("Archive")')
        await page.wait_for_timeout(200)
        await page.click('#detail-panel-toggle-btn')  # expand to check the panel's own button label
        await page.wait_for_timeout(150)
        archived_via_context_menu = await page.locator('#archive-toggle-btn').inner_text()
        print("Archive from the context menu actually archives the document:", 'Unarchive' in archived_via_context_menu)
        await page.click('#archive-toggle-btn')  # unarchive again
        await page.wait_for_timeout(200)

        # === Scenario 15: no context menu on .select-col/.row-edit-col, or
        # in Reports view ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        dialog_fired = []
        page.on('dialog', lambda dialog: (dialog_fired.append(dialog.message), asyncio.ensure_future(dialog.dismiss())))
        await page.click('tr[data-id="1"] .select-col', button='right')
        await page.wait_for_timeout(200)
        no_menu_on_checkbox = await page.locator('.row-context-menu:visible').count()
        print("no context menu when right-clicking the select checkbox:", no_menu_on_checkbox == 0)

        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        # #doc-tbody's <tr> elements from the last non-Reports render are NOT
        # cleared out when switching into Reports -- render() returns early
        # for currentView === 'reports', before the code that rebuilds tbody
        # rows, so they simply sit hidden underneath (tableWrap itself gets
        # display:none). Check visibility, not raw existence, to correctly
        # capture "nothing to right-click" rather than "no <tr> elements".
        no_rows_in_reports = await page.locator('#doc-tbody tr:visible').count()
        print("Reports view has no rows to right-click in the first place:", no_rows_in_reports == 0)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 16: "Add to Collection" from the context menu closes
        # the menu and opens the collection picker cleanly, positioned near
        # the click rather than collapsed to (0,0) ===
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(200)
        await page.click('.row-context-menu .row-context-menu-item:has-text("Add to collection")')
        await page.wait_for_timeout(150)
        context_menu_gone = await page.locator('.row-context-menu:visible').count()
        print("context menu closes when Add to Collection is clicked:", context_menu_gone == 0)
        picker_visible = await page.locator('.bulk-collection-menu:visible').count()
        print("collection picker opens:", picker_visible == 1)
        # Plain `.bulk-collection-menu` also matches the toolbar's own permanent,
        # always-present-but-display:none #bulk-collection-menu div -- a strict-mode
        # violation with two matches. :visible disambiguates to the one this click
        # actually created.
        picker_top = await page.locator('.bulk-collection-menu:visible').evaluate('el => parseFloat(el.style.top)')
        # picker_top > 0 alone is vacuous: the picker's own positioning code is
        # `rect.bottom + window.scrollY + 6`, so even a fully collapsed (all-zero)
        # rect -- which is exactly what a detached-from-the-DOM e.target would
        # produce if onClick ran AFTER the menu was removed -- still yields
        # 0 + 0 + 6 = 6, and 6 > 0 is still True. A real click-relative position
        # on this row (well down the page, at a desktop viewport) lands far above
        # that ~6px floor, so a threshold well above it (but still comfortably
        # below any plausible real position) actually distinguishes "positioned
        # near the click" from "collapsed to zero".
        print("collection picker is positioned near the click, not collapsed to (0,0):", picker_top > 50)
        await page.click('#nav-item-all')  # dismiss the picker by clicking elsewhere
        await page.wait_for_timeout(150)

        # === Scenario 17: the context menu clamps vertically so every item
        # stays fully on-screen and clickable, even when right-clicking a row
        # near the bottom of the table -- reproducing the exact "Delete is
        # unreachable" overflow the final whole-branch review caught (verified
        # empirically at 1280x800, 1280x1000, 1440x900, and 1280x720; every
        # one overflowed before the fix). Needs a seed large enough that a low
        # row is genuinely below the fold, not the 3-document SEED above --
        # matching the "seed enough documents to make the geometry check
        # non-vacuous" convention test_footer_pin.py/test_collections.py's own
        # Scenario 30 already use for similar viewport-geometry checks.
        many_docs_seed = {
            "documents": [
                {
                    "id": i, "title": f"Doc {i}", "category": "Finance", "document_type": "Invoice",
                    "date": f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None,
                    "created_at": f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
                    "archived": 0, "needs_review": 0, "deleted": 0,
                }
                for i in range(1, 26)
            ],
            "tags": [], "document_tags": [],
            # A manual collection is included so "Add to collection" renders too --
            # without it the menu only has 5 items, which happens to still fit
            # this particular row/viewport combination even unclamped (confirmed
            # while building this scenario: 5 items landed with the last item's
            # own bottom exactly AT the viewport edge, only the menu's own
            # padding poked past it) and would make this scenario vacuous. With
            # "Add to collection" as a 6th item, the unclamped menu genuinely
            # pushes the last item's bottom to 831px against an 800px-tall
            # viewport -- confirmed by temporarily reverting the clamp in
            # showRowContextMenu() and re-running this scenario, which then
            # correctly reports False.
            "collections": [{"id": 1, "name": "My Collection", "kind": "manual", "criteria": None}],
            "collection_documents": [],
        }
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(many_docs_seed)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        last_row = page.locator('#doc-tbody tr').last
        await last_row.scroll_into_view_if_needed()
        await last_row.click(button='right')
        await page.wait_for_timeout(200)
        menu_item_rects = await page.locator('.row-context-menu .row-context-menu-item:visible').evaluate_all(
            "els => els.map(e => e.getBoundingClientRect().bottom)"
        )
        viewport_height = 800
        # A half-pixel tolerance absorbs float rounding from getBoundingClientRect()
        # without masking a real overflow -- a genuinely off-screen item overflows
        # by several pixels' worth of button height, not a rounding error.
        all_items_within_viewport = len(menu_item_rects) > 0 and all(b <= viewport_height + 0.5 for b in menu_item_rects)
        print("every context menu item (including the last one) is fully within the viewport:", all_items_within_viewport)
        await page.click('#nav-item-all')  # dismiss the menu
        await page.wait_for_timeout(150)

        # === Scenario 18: right-clicking elsewhere on the page closes an
        # already-open context menu, instead of leaving it open underneath
        # the browser's own native context menu -- the dismissal listener
        # used to only cover 'click', not 'contextmenu' ===
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        menu_open = await page.locator('.row-context-menu').count()
        print("context menu open after right-clicking a row:", menu_open == 1)
        await page.click('header', button='right')
        await page.wait_for_timeout(150)
        menu_closed_after_elsewhere = await page.locator('.row-context-menu').count()
        print("context menu closes after right-clicking elsewhere on the page:", menu_closed_after_elsewhere == 0)

        # Right-clicking a DIFFERENT row must still replace the menu with a
        # fresh one for that row, not just close it -- confirms the new
        # 'contextmenu' dismissal listener doesn't fight with
        # showRowContextMenu()'s own existing old-menu removal.
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="2"]', button='right')
        await page.wait_for_timeout(150)
        menu_count_after_row_switch = await page.locator('.row-context-menu').count()
        print("exactly one menu remains after right-clicking a different row:", menu_count_after_row_switch == 1)
        await page.click('#nav-item-all')  # dismiss
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()
        _os2.remove(patched_app_path)

asyncio.run(main())
