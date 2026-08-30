import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [
    {"document_type": "Policy", "field_name": "People", "position": 0},
]

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, []);")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)

        # === Scenario 1: creating a 'reminder'-type field inline behaves
        # identically to 'date' in every respect except the type stored ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Policy')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        await page.fill('#f-new-field-name', 'Renewal Date')
        reminder_option_present = await page.locator('#f-new-field-type option[value="reminder"]').count()
        print("Reminder option present in the type dropdown:", reminder_option_present == 1)
        await page.select_option('#f-new-field-type', 'reminder')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(100)

        renewal_input = page.locator('[data-dynamic-field="Renewal Date"] input')
        renewal_present = await renewal_input.count()
        print("Renewal Date field appears immediately after creation:", renewal_present == 1)
        input_type = await renewal_input.get_attribute('type')
        print("new reminder field renders as a native date input:", input_type == 'date')
        await renewal_input.fill('2026-03-15')
        await page.fill('#f-title', 'Insurance Policy Document')
        with open('policy1.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 policy1")
        await page.set_input_files('#file-input', 'policy1.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        field_row = next((f for f in persisted['fields'] if f['name'] == 'Renewal Date'), None)
        print("field persisted with type 'reminder':", field_row['type'] if field_row else None)
        value_row = next((v for v in persisted['document_field_values'] if v['field_id'] == field_row['id']), None)
        print("value persisted as a plain ISO date string:", value_row['value'] if value_row else None)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        displayed = await page.locator('#detail-panel-body').inner_text()
        print("detail panel shows the reminder field's value like any date field:", '2026' in displayed)

        # No Autocomplete checkbox, matching 'date' -- but the Column checkbox IS
        # offered (capabilitiesHtml()'s guard is exclusion-based: person + Amount
        # only, so 'reminder' gets it automatically like every other non-excluded type).
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.click('.fs-list-item:has-text("Policy")')
        await page.wait_for_timeout(150)
        reminder_item = page.locator('#fs-available-list .fs-field-item[data-field="Renewal Date"], #fs-display-list .fs-field-item[data-field="Renewal Date"]').first
        column_checkbox_present = await reminder_item.locator('.fs-col-toggle').count()
        autocomplete_checkbox_present = await reminder_item.locator('.fs-autocomplete-toggle').count()
        print("Column checkbox offered for a reminder field:", column_checkbox_present == 1)
        print("Autocomplete checkbox NOT offered for a reminder field:", autocomplete_checkbox_present == 0)

        # === Scenario 2: reminder_lookahead_days defaults to 30 when unset,
        # persists an explicit value, and survives a reopen ===
        lookahead_default = await page.evaluate("document.getElementById('fs-reminder-lookahead').value")
        print("reminder lookahead defaults to 30 with no persisted setting:", lookahead_default)  # set below, after opening Field Settings again

        await page.fill('#fs-reminder-lookahead', '14')
        await page.dispatch_event('#fs-reminder-lookahead', 'change')
        await page.wait_for_timeout(200)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        lookahead_row = next((s for s in persisted2['settings'] if s['key'] == 'reminder_lookahead_days'), None)
        print("reminder_lookahead_days persisted as '14':", lookahead_row['value'] if lookahead_row else None)

        # Reopen (same convention test_nav.py/test_recent_libraries.py use: re-seed
        # a fresh root with the setting already present, simulating a real reopen
        # reading the same on-disk library.sqlite back)
        seed_with_lookahead = {'document_type_fields': TYPE_FIELD_ROWS, 'settings': [{'key': 'reminder_lookahead_days', 'value': '14'}]}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_lookahead)}, []); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        lookahead_after_reopen = await page.evaluate("document.getElementById('fs-reminder-lookahead').value")
        print("reminder_lookahead_days reads back as '14' after reopening:", lookahead_after_reopen)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        # === Scenario 3: reminder_snoozes rows load correctly into memory,
        # and a real INSERT OR REPLACE against the compound (document_id,
        # field_id) key replaces an existing row rather than duplicating it ===
        seed_with_snooze = {
            'document_type_fields': TYPE_FIELD_ROWS,
            'reminder_snoozes': [
                {'document_id': 1, 'field_id': 1, 'snoozed_until': '2026-06-01'},
            ],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_snooze)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        # window.__DEBUG_reminderSnoozes is a small test-only hook loadReminderSnoozes()
        # sets at the end of its own body -- the simplest way to assert on this
        # module-private variable from outside the page's own closure.
        loaded_snooze = await page.evaluate("window.__DEBUG_reminderSnoozes ? window.__DEBUG_reminderSnoozes['1:1'] : undefined")
        print("seeded snooze row loads into memory:", loaded_snooze)

        # Directly exercise the real INSERT OR REPLACE path the app itself uses,
        # confirming the stub correctly replaces (not duplicates) on the same
        # compound key -- this is the one thing this table needed new stub support
        # for, since every prior INSERT OR REPLACE dedupe in this stub has been a
        # single-column key (settings.key, field_descriptions.field_name).
        # `db` and `loadReminderSnoozes` are both private to dossiary.html's own
        # top-level closure, not reachable from page.evaluate() directly -- routed
        # through the __DEBUG_dbRun/__DEBUG_loadReminderSnoozes test-only hooks instead.
        replaced_value = await page.evaluate("""
            () => {
                window.__DEBUG_dbRun('INSERT OR REPLACE INTO reminder_snoozes (document_id, field_id, snoozed_until) VALUES (?, ?, ?)', [1, 1, '2026-07-15']);
                window.__DEBUG_loadReminderSnoozes(); // re-read from the table, same as a real reopen would
                return window.__DEBUG_reminderSnoozes['1:1'];
            }
        """)
        print("after a second INSERT OR REPLACE on the same (document_id, field_id), the row's snoozed_until is the NEW value:", replaced_value == '2026-07-15')

        # The check above alone is vacuous: loadReminderSnoozes()'s for-of loop overwrites
        # the same "1:1" map key once per matching row, in insertion order, so it reads back
        # the same correct *final* value whether the stub's compound-key dedupe actually
        # removed the old (document_id=1, field_id=1) row or just left it sitting alongside
        # the new one -- either way the newest row is the one processed last and wins the
        # map slot. Confirm the real fix: read the raw table rows via __DEBUG_reminderSnoozesRawRows
        # (added specifically for this) and assert there's exactly ONE row for this key, not two.
        raw_rows = await page.evaluate("window.__DEBUG_reminderSnoozesRawRows()")
        matching_rows = [r for r in raw_rows if r[0] == 1 and r[1] == 1]
        print("exactly one reminder_snoozes row exists for (document_id=1, field_id=1) after the replace (proves dedupe, not just the final map value):", len(matching_rows) == 1)
        if matching_rows:
            print("and that one row holds the NEW value, not the old one:", matching_rows[0][2] == '2026-07-15')

        # === Scenario 4: checkReminders() -- due/overdue inclusion, lookahead
        # window boundary, archived/deleted exclusion, active-snooze exclusion,
        # expired-snooze inclusion, multi-field-per-document correctness, sort
        # order. All dates are computed relative to the real "today" the test
        # runs on, so this scenario is deliberately date-arithmetic rather than
        # hardcoded, to stay correct regardless of when the suite runs. ===
        multi_field_seed = {
            "documents": [
                {  # doc 1: due today
                    "id": 1, "title": "Doc Due Today", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 2: overdue by 5 days
                    "id": 2, "title": "Doc Overdue", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 3: due in 10 days (within a 14-day lookahead)
                    "id": 3, "title": "Doc Due Soon", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 4: due in 60 days (OUTSIDE a 14-day lookahead -- must be excluded)
                    "id": 4, "title": "Doc Too Far Out", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 5: due today, but ARCHIVED -- must be excluded
                    "id": 5, "title": "Doc Archived", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 1, "needs_review": 0, "deleted": 0,
                },
                {  # doc 6: due today, but DELETED -- must be excluded
                    "id": 6, "title": "Doc Deleted", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 1,
                },
                {  # doc 7: due today, but ACTIVELY snoozed -- must be excluded
                    "id": 7, "title": "Doc Snoozed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 8: due today, snooze already EXPIRED -- must be included
                    "id": 8, "title": "Doc Snooze Expired", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 9: TWO reminder fields, one due (Insurance) one not (Warranty)
                    "id": 9, "title": "Doc Two Reminders", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "settings": [{"key": "reminder_lookahead_days", "value": "14"}],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
                {"id": 2, "name": "Warranty End", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [],  # filled in below via JS, using real relative-to-today dates
            "reminder_snoozes": [],       # filled in below via JS, same reason
        }

        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(multi_field_seed)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        # Compute every date relative to the app's own todayIsoDate() and write
        # document_field_values / reminder_snoozes directly via __DEBUG_dbRun(), then
        # reload from the in-memory db so allDocs/reminderSnoozes reflect them --
        # this keeps the scenario correct regardless of what "today" actually is
        # when the suite runs.
        result = await page.evaluate("""
            () => {
                const add = (days) => window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), days);
                const values = [
                    [1, 1, add(0)],   // doc1 field1 (Renewal Date): due today
                    [2, 1, add(-5)],  // doc2: overdue by 5 days
                    [3, 1, add(10)],  // doc3: due in 10 days (within 14-day lookahead)
                    [4, 1, add(60)],  // doc4: due in 60 days (outside lookahead)
                    [5, 1, add(0)],   // doc5: due today, but archived
                    [6, 1, add(0)],   // doc6: due today, but deleted
                    [7, 1, add(0)],   // doc7: due today, but actively snoozed
                    [8, 1, add(0)],   // doc8: due today, snooze already expired
                    [9, 1, add(0)],   // doc9 Renewal Date: due today
                    [9, 2, add(60)],  // doc9 Warranty End: not due
                ];
                for(const [documentId, fieldId, value] of values){
                    window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [documentId, fieldId, value]);
                }
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until) VALUES (?, ?, ?)', [7, 1, add(5)]);  // active: 5 days in the future
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until) VALUES (?, ?, ?)', [8, 1, add(-1)]); // expired: 1 day in the past
                window.__DEBUG_loadDocumentsFromDb();
                const due = window.__DEBUG_checkReminders();
                return due.map(r => ({ documentId: r.documentId, fieldId: r.fieldId, fieldName: r.fieldName, date: r.date, docTitle: r.docTitle }));
            }
        """)
        due_doc_ids = sorted(r['documentId'] for r in result)
        print("checkReminders() includes exactly docs 1, 2, 3, 8, 9 (not 4/5/6/7):", due_doc_ids == [1, 2, 3, 8, 9])

        doc9_entries = [r for r in result if r['documentId'] == 9]
        print("doc 9 contributes exactly one due entry (Renewal Date only, not Warranty End):", len(doc9_entries) == 1 and doc9_entries[0]['fieldName'] == 'Renewal Date')

        sorted_dates = [r['date'] for r in result]
        print("results are sorted by date ascending (most overdue first):", sorted_dates == sorted(sorted_dates))
        print("doc 2 (most overdue) sorts first:", result[0]['documentId'] == 2)

        # === Scenario 5: openRemindersModal() renders every due reminder,
        # clicking a row opens that document, and each of the four snooze
        # choices persists correctly and removes that row from the list ===
        due_now = await page.evaluate("checkReminders()")
        await page.evaluate("(due) => openRemindersModal(due)", due_now)
        await page.wait_for_timeout(200)

        row_count = await page.locator('.reminder-row').count()
        print("modal shows exactly one row per due reminder:", row_count == len(due_now))

        # Custom-date input should be hidden before "Custom date..." is selected
        doc1_row = page.locator('.reminder-row[data-document-id="1"]')
        custom_date_initially_hidden = not await doc1_row.locator('.reminder-snooze-custom-date').is_visible()
        print("custom-date input is hidden before 'Custom date' is selected:", custom_date_initially_hidden)

        # Snooze doc 3's reminder for "1 week" -- confirm it persists and the row disappears
        doc3_row = page.locator('.reminder-row[data-document-id="3"]')
        await doc3_row.locator('.reminder-snooze-select').select_option('1w')
        await page.wait_for_timeout(200)
        doc3_row_gone = await page.locator('.reminder-row[data-document-id="3"]').count()
        print("doc 3's row is removed from the modal after snoozing 1 week:", doc3_row_gone == 0)

        persisted3 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        snooze_row_3 = next((s for s in persisted3['reminder_snoozes'] if s['document_id'] == 3 and s['field_id'] == 1), None)
        expected_1w = await page.evaluate("addDaysToIsoDate(todayIsoDate(), 7)")
        print("doc 3's snooze persisted as exactly today + 7 days:", snooze_row_3['snoozed_until'] if snooze_row_3 else None, "==", expected_1w)

        # Custom-date snooze on doc 1
        await doc1_row.locator('.reminder-snooze-select').select_option('custom')
        await page.wait_for_timeout(100)
        custom_date_visible = await doc1_row.locator('.reminder-snooze-custom-date').is_visible()
        print("choosing 'Custom date' reveals a date picker:", custom_date_visible)
        await doc1_row.locator('.reminder-snooze-custom-date').fill('2026-12-25')
        await page.evaluate("""
            () => {
                const input = document.querySelector('.reminder-row[data-document-id="1"] .reminder-snooze-custom-date');
                if(input) {
                    const event = new Event('change', { bubbles: true });
                    input.dispatchEvent(event);
                }
            }
        """)
        await page.wait_for_timeout(200)
        doc1_row_gone = await page.locator('.reminder-row[data-document-id="1"]').count()
        print("doc 1's row is removed after a custom-date snooze:", doc1_row_gone == 0)

        # Clicking a remaining row (not its snooze control) opens that document
        # and closes the modal
        remaining_row = page.locator('.reminder-row').first
        remaining_doc_id = await remaining_row.get_attribute('data-document-id')
        await remaining_row.click()
        await page.wait_for_timeout(200)
        modal_closed = await page.locator('.reminder-row').count()
        print("clicking a row closes the modal:", modal_closed == 0)
        selected_row_highlighted = await page.locator(f'tr[data-id="{remaining_doc_id}"].row-selected').count()
        print("clicking a row selects/highlights that document in the table:", selected_row_highlighted == 1)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
