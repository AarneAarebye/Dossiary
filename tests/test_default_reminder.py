import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [
        {
            "id": 1, "title": "Insurance Policy", "category": "Finance", "document_type": "Policy",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [], "settings": [],
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)

        # === Scenario 1: the 'Reminder' field is auto-created for a fresh library
        # open, idempotently -- reopening doesn't duplicate or otherwise disturb it ===
        field_row = await page.evaluate("window.__DEBUG_findFieldByName('Reminder')")
        print("'Reminder' field auto-created with type 'reminder':", field_row is not None and field_row['type'] == 'reminder')

        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        field_row_after_reopen = await page.evaluate("window.__DEBUG_findFieldByName('Reminder')")
        print("re-opening the same library doesn't duplicate the field (same id):", field_row_after_reopen is not None and field_row_after_reopen['id'] == field_row['id'])

        # === Scenario 2: 'Reminder' is rejected as a name when creating a custom
        # field inline, matching the existing reserved-name behavior ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Policy')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        await page.fill('#f-new-field-name', 'Reminder')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(100)
        validation_text = await page.locator('#f-new-field-status').inner_text()
        print("'Reminder' is rejected as a reserved custom-field name:", 'reserved' in validation_text.lower() or 'Reminder' in validation_text)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 3: setDefaultReminder()/clearDefaultReminder() write/remove
        # the value correctly, in memory and persisted, and it participates in
        # checkReminders() exactly like any other reminder-type field ===
        result = await page.evaluate("""
            (async () => {
                await window.__DEBUG_setDefaultReminder(1, window.__DEBUG_todayIsoDate());
                const inMemory = window.__DEBUG_getCustomFieldValue(1, 'Reminder');
                const due = window.__DEBUG_checkReminders();
                const includesDoc1 = due.some(r => r.documentId === 1 && r.fieldName === 'Reminder');
                return { inMemory, includesDoc1 };
            })()
        """)
        print("setDefaultReminder() updates the document's in-memory customFields:", bool(result['inMemory']))
        print("a default reminder due today is included by checkReminders():", result['includesDoc1'])

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        reminder_field_id = field_row['id']
        saved_value = next((v['value'] for v in persisted['document_field_values'] if v['document_id'] == 1 and v['field_id'] == reminder_field_id), None)
        print("the value is actually persisted to document_field_values:", saved_value is not None)

        await page.evaluate("window.__DEBUG_clearDefaultReminder(1)")
        await page.wait_for_timeout(100)
        result2 = await page.evaluate("""
            () => {
                const inMemory = window.__DEBUG_getCustomFieldValue(1, 'Reminder');
                const due = window.__DEBUG_checkReminders();
                const stillIncluded = due.some(r => r.documentId === 1 && r.fieldName === 'Reminder');
                return { inMemory, stillIncluded };
            }
        """)
        print("clearDefaultReminder() removes it from in-memory customFields:", not result2['inMemory'])
        print("and checkReminders() no longer includes it:", not result2['stillIncluded'])

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        saved_value_after_clear = next((v for v in persisted2['document_field_values'] if v['document_id'] == 1 and v['field_id'] == reminder_field_id), None)
        print("and the persisted row is actually gone, not just blanked:", saved_value_after_clear is None)

        # === Scenario 4: a document with a default reminder value shows it as an
        # orphaned, editable field in the Edit form, regardless of its type, since
        # 'Reminder' is never attached to document_type_fields ===
        await page.evaluate("window.__DEBUG_setDefaultReminder(1, window.__DEBUG_todayIsoDate())")
        await page.wait_for_timeout(100)
        await page.click(f'tr[data-id="1"]')
        await page.wait_for_timeout(150)
        await page.click('#edit-doc-btn')  # the detail panel's own Edit button, wired via actionIdByKey['edit'] = 'edit-doc-btn' in openDetail()
        await page.wait_for_timeout(150)
        orphaned_reminder = page.locator('[data-dynamic-field="Reminder"].field-orphaned')
        print("the Reminder field shows as an orphaned, editable field in Edit:", await orphaned_reminder.count() == 1)
        orphaned_input = orphaned_reminder.locator('input')
        orphaned_value = await orphaned_input.input_value()
        print("with the correct saved value pre-filled:", orphaned_value == await page.evaluate("window.__DEBUG_todayIsoDate()"))
        await page.click('#modal-close-btn')  # close the Edit form left open by Scenario 4, so it doesn't block the row right-clicks below
        await page.wait_for_timeout(150)

        # === Scenario 5: the context menu shows "Add reminder" for a document with
        # no default reminder, and the flyout offers Today/Tomorrow/Next week/Custom
        # date but not Clear reminder ===
        await page.evaluate("window.__DEBUG_clearDefaultReminder(1)")
        await page.wait_for_timeout(100)
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        add_reminder_item = page.locator('.row-context-menu-item', has_text='Add reminder')
        print("context menu shows 'Add reminder' when none is set:", await add_reminder_item.count() == 1)
        await add_reminder_item.click()
        await page.wait_for_timeout(150)

        # The row context menu's own generic closeMenu() should have removed the
        # .row-context-menu itself, but NOT the flyout it just opened -- the same
        # "separate DOM element, tracked separately" property Add to Collection's
        # own picker already relies on.
        context_menu_gone = await page.locator('.row-context-menu').count() == 0
        flyout_present = await page.locator('.reminder-flyout').count() == 1
        print("the row context menu closes but the flyout it opened stays open:", context_menu_gone and flyout_present)

        flyout_options = await page.locator('.reminder-flyout-option').all_inner_texts()
        has_today = any('Today' in o for o in flyout_options)
        has_tomorrow = any('Tomorrow' in o for o in flyout_options)
        has_next_week = any('Next week' in o for o in flyout_options)
        has_custom = any('Custom date' in o for o in flyout_options)
        has_clear = any('Clear reminder' in o for o in flyout_options)
        print("flyout offers Today/Tomorrow/Next week/Custom date:", has_today and has_tomorrow and has_next_week and has_custom)
        print("but not Clear reminder, since none is set yet:", not has_clear)

        # === Scenario 6: choosing "Today" sets it immediately and updates the
        # context menu's label on the next right-click ===
        await page.locator('.reminder-flyout-option', has_text='Today').click()
        await page.wait_for_timeout(150)
        flyout_gone = await page.locator('.reminder-flyout').count() == 0
        print("choosing a preset closes the flyout:", flyout_gone)

        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        reminder_set_item = page.locator('.row-context-menu-item', has_text='Reminder:')
        print("the menu item now reads 'Reminder: <date>':", await reminder_set_item.count() == 1)

        # === Scenario 7: Custom date reveals a hidden date input with a min of
        # tomorrow, matching the reminders modal's own already-established pattern ===
        await reminder_set_item.click()  # reopens the flyout (now to CHANGE the existing reminder)
        await page.wait_for_timeout(150)
        custom_date_input = page.locator('.reminder-flyout-custom-date')
        custom_date_visible_before = await custom_date_input.is_visible()
        print("the custom-date input starts hidden:", not custom_date_visible_before)
        await page.locator('.reminder-flyout-option', has_text='Custom date').click()
        await page.wait_for_timeout(100)
        custom_date_visible_after = await custom_date_input.is_visible()
        print("choosing 'Custom date…' reveals it:", custom_date_visible_after)
        min_attr = await custom_date_input.get_attribute('min')
        expected_min = await page.evaluate("window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), 1)")
        print("its min attribute is tomorrow:", min_attr == expected_min)
        color_scheme = await custom_date_input.evaluate("el => getComputedStyle(el).colorScheme")
        print("and it's styled for dark mode:", color_scheme == 'dark')

        # Playwright's fill() on a native <input type="date"> already dispatches a
        # real 'change' event as part of setting the value, which our handler
        # picks up immediately -- no separate dispatch_event('change') needed (and
        # calling one would time out anyway, since the flyout/input are already
        # gone by the time it'd run).
        await custom_date_input.fill('2026-12-25')
        await page.wait_for_timeout(150)
        flyout_gone_after_custom = await page.locator('.reminder-flyout').count() == 0
        print("confirming a custom date closes the flyout:", flyout_gone_after_custom)

        # === Scenario 8: Clear reminder removes it and the label reverts ===
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        await page.locator('.row-context-menu-item', has_text='Reminder:').click()
        await page.wait_for_timeout(150)
        await page.locator('.reminder-flyout-option', has_text='Clear reminder').click()
        await page.wait_for_timeout(150)

        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        add_reminder_again = page.locator('.row-context-menu-item', has_text='Add reminder')
        print("after clearing, the menu item reverts to 'Add reminder':", await add_reminder_again.count() == 1)
        await page.click('tr[data-id="1"]', button='right')  # close the reopened menu

        # === Scenario 9: setting a reminder via the flyout produces state
        # checkReminders() correctly includes, an end-to-end confirmation that the
        # UI-triggered write matches Task 1's own function-level behavior ===
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        await page.locator('.row-context-menu-item', has_text='Add reminder').click()
        await page.wait_for_timeout(150)
        await page.locator('.reminder-flyout-option', has_text='Today').click()
        await page.wait_for_timeout(150)
        due_after_ui_set = await page.evaluate("window.__DEBUG_checkReminders().some(r => r.documentId === 1 && r.fieldName === 'Reminder')")
        print("a reminder set via the flyout is picked up by checkReminders():", due_after_ui_set)

        # === Scenario 10: buildDetailActions() is shared with the detail panel --
        # the same action, and its flyout, must also work from there, not just the
        # row context menu, confirming the actionIdByKey entry added in Step 3 ===
        await page.evaluate("window.__DEBUG_clearDefaultReminder(1)")
        await page.wait_for_timeout(100)
        await page.click('tr[data-id="1"]')  # left-click selects the row and opens the panel
        await page.wait_for_timeout(150)
        panel_btn = page.locator('#default-reminder-btn')
        panel_btn_text = await panel_btn.inner_text()
        print("the detail panel shows a real 'Add reminder' button, not id=\"undefined\":", 'Add reminder' in panel_btn_text)
        await panel_btn.click()
        await page.wait_for_timeout(150)
        await page.locator('.reminder-flyout-option', has_text='Tomorrow').click()
        await page.wait_for_timeout(150)
        panel_btn_after = page.locator('#default-reminder-btn')
        panel_btn_text_after = await panel_btn_after.inner_text()
        print("choosing a preset from the panel button updates its own label too:", 'Reminder:' in panel_btn_text_after)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
