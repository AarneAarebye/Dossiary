import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, datetime
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
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        print("after a second INSERT OR REPLACE on the same (document_id, field_id), the row's snoozed_until is the NEW value:", replaced_value['snoozedUntil'] == '2026-07-15')

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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        due_now = await page.evaluate("window.__DEBUG_checkReminders()")
        await page.evaluate("(due) => window.__DEBUG_openRemindersModal(due)", due_now)
        await page.wait_for_timeout(200)

        row_count = await page.locator('.reminder-row').count()
        print("modal shows exactly one row per due reminder:", row_count == len(due_now))

        # Custom-date input should be hidden before "Custom date..." is selected
        doc1_row = page.locator('.reminder-row[data-document-id="1"]')
        custom_date_initially_hidden = not await doc1_row.locator('.reminder-snooze-custom-date').is_visible()
        print("custom-date input is hidden before 'Custom date' is selected:", custom_date_initially_hidden)

        # The custom-date input is the only date input in the app that used to be
        # missing color-scheme:dark (finding 1) -- confirm it's now fixed, same
        # assertion style as tests/test_date_picker_color_scheme.py uses for #f-date/#e-date.
        custom_date_color_scheme = await doc1_row.locator('.reminder-snooze-custom-date').evaluate("el => getComputedStyle(el).colorScheme")
        print("custom-date input's color-scheme is dark:", custom_date_color_scheme == 'dark')

        # The custom-date input has no lower bound by default (finding 4) -- confirm its
        # `min` attribute is set to tomorrow's date, so the native picker won't offer
        # today-or-earlier as a choice.
        custom_date_min = await doc1_row.locator('.reminder-snooze-custom-date').get_attribute('min')
        expected_min = await page.evaluate("window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), 1)")
        print("custom-date input's min attribute is tomorrow's date:", custom_date_min == expected_min)

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
        expected_1w = await page.evaluate("window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), 7)")
        print("doc 3's snooze persisted as exactly today + 7 days:", snooze_row_3['snoozed_until'] if snooze_row_3 else None, "==", expected_1w)

        # Custom-date snooze on doc 1
        await doc1_row.locator('.reminder-snooze-select').select_option('custom')
        await page.wait_for_timeout(100)
        custom_date_visible = await doc1_row.locator('.reminder-snooze-custom-date').is_visible()
        print("choosing 'Custom date' reveals a date picker:", custom_date_visible)

        # Defensive check (finding 4): a manually-typed past-or-today value can bypass
        # a native date input's own `min` attribute enforcement in some browsers, so the
        # JS-level check in wireReminderRows()'s change handler needs to reject it too --
        # simulated directly via page.evaluate() setting .value and dispatching a real
        # 'change' event, since Playwright's own .fill() may itself be blocked by `min`
        # before ever reaching the app's handler.
        past_date = await page.evaluate("window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), -30)")
        await page.evaluate("""
            (pastDate) => {
                const input = document.querySelector('.reminder-row[data-document-id="1"] .reminder-snooze-custom-date');
                input.value = pastDate;
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
        """, past_date)
        await page.wait_for_timeout(200)
        doc1_row_survives_past_date = await page.locator('.reminder-row[data-document-id="1"]').count()
        print("a manually-set past date is rejected by the JS-level defensive check (row stays, no snooze written):", doc1_row_survives_past_date == 1)

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
        # Click the row's own title text, not the row element's bounding-box center --
        # Task 3's two new Dismiss/Delete buttons widened the row's right-hand
        # `.reminder-snooze` control span enough that a plain center-click on the row
        # itself can now land inside that span (which stops propagation) instead of
        # the row's own click-to-open handler.
        await remaining_row.locator('.reminder-row-title').click()
        await page.wait_for_timeout(200)
        modal_closed = await page.locator('.reminder-row').count()
        print("clicking a row closes the modal:", modal_closed == 0)
        selected_row_highlighted = await page.locator(f'tr[data-id="{remaining_doc_id}"].row-selected').count()
        print("clicking a row selects/highlights that document in the table:", selected_row_highlighted == 1)

        # === Scenario 6: the automatic library-open check surfaces the modal
        # only when something is due, and stays silent otherwise; the manual
        # "Check reminders" button reports "No reminders due." when nothing
        # is due, and opens the modal when something is ===
        today_iso = datetime.date.today().isoformat()
        due_seed = {
            "documents": [
                {
                    "id": 1, "title": "Doc With Reminder", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [{"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0}],
            "document_field_values": [{"document_id": 1, "field_id": 1, "value": today_iso}],
        }
        empty_seed = {
            "documents": [
                {
                    "id": 1, "title": "Doc Without Reminder", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [], "document_field_values": [],
        }

        # A genuinely fresh library open (the real afterDbReady() flow) with a due
        # reminder already present in the seed data -- not a mid-session mutation --
        # should surface the modal automatically, with no manual action.
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(due_seed)}); window.__TEST_ROOT.name = 'DueLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        modal_shown_automatically = await page.locator('.reminder-row').count()
        print("library open with a due reminder shows the reminders modal automatically:", modal_shown_automatically > 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # Manual button, something due
        check_btn_present = await page.locator('#check-reminders-btn').count()
        print("Check reminders toolbar button is present:", check_btn_present == 1)
        await page.click('#check-reminders-btn')
        await page.wait_for_timeout(200)
        modal_shown_by_button = await page.locator('.reminder-row').count()
        print("clicking Check reminders opens the modal when something is due:", modal_shown_by_button > 0)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # Manual button, nothing due (fresh library with no reminder field)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(empty_seed)}); window.__TEST_ROOT.name = 'EmptyLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        no_modal_on_open = await page.locator('.reminder-row').count()
        print("library open with nothing due shows no modal:", no_modal_on_open == 0)
        await page.click('#check-reminders-btn')
        await page.wait_for_timeout(200)
        status_text = await page.locator('#status').inner_text()
        print("Check reminders with nothing due reports the empty-case status message:", 'no reminders' in status_text.lower())

        # === Scenario 7: reminder_snoozes.dismissed loads into the new
        # {snoozedUntil, dismissed} shape, and checkReminders() excludes a
        # dismissed field unconditionally -- even one that's overdue with no
        # snoozed_until at all, and even one whose snooze row also carries a
        # stale future snoozed_until (dismissed must win regardless) ===
        dismiss_seed = {
            "documents": [
                {
                    "id": 1, "title": "Doc Dismissed No Snooze", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 2, "title": "Doc Dismissed With Stale Future Snooze", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 3, "title": "Doc Not Dismissed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 4: two reminder fields on the SAME document -- one dismissed
                   # (Renewal Date), one left alone (Warranty End) -- proves dismissal is
                   # scoped per-field, not per-document
                    "id": 4, "title": "Doc Two Fields One Dismissed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
                {"id": 2, "name": "Warranty End", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(dismiss_seed)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        result7 = await page.evaluate("""
            () => {
                const add = (days) => window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), days);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, add(-5)]);  // overdue
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [2, 1, add(0)]);   // due today
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [3, 1, add(0)]);   // due today, never touched
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [4, 1, add(0)]);   // doc4 Renewal Date: due today, will be dismissed below
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [4, 2, add(0)]);   // doc4 Warranty End: due today, left alone
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [1, 1, null, 1]);
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [2, 1, add(30), 1]);
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [4, 1, null, 1]);
                window.__DEBUG_loadDocumentsFromDb();
                const loaded1 = window.__DEBUG_reminderSnoozes['1:1'];
                const loaded2 = window.__DEBUG_reminderSnoozes['2:1'];
                const due = window.__DEBUG_checkReminders();
                return { loaded1, loaded2, dueIds: due.map(r => r.documentId), doc4Fields: due.filter(r => r.documentId === 4).map(r => r.fieldName) };
            }
        """)
        print("dismissed row (no snooze) loads into memory as {snoozedUntil: null, dismissed: true}:", result7['loaded1'] == {'snoozedUntil': None, 'dismissed': True})
        print("dismissed row (with a stale future snoozed_until) still loads dismissed=true:", result7['loaded2']['dismissed'] == True)
        print("checkReminders() excludes both dismissed docs 1 and 2, includes docs 3 and 4:", sorted(result7['dueIds']) == [3, 4])
        print("doc 4 contributes only Warranty End (Renewal Date dismissed, per-field not per-document):", result7['doc4Fields'] == ['Warranty End'])

        # Editing doc 1's dismissed field to a brand-new date does NOT un-dismiss it --
        # dismissal is scoped to (document_id, field_id), never to the specific value
        # that was due at the time it was dismissed.
        result7b = await page.evaluate("""
            () => {
                const add = (days) => window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), days);
                window.__DEBUG_dbRun('DELETE FROM document_field_values WHERE document_id = ? AND field_id = ?', [1, 1]);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, add(-1)]);
                window.__DEBUG_loadDocumentsFromDb();
                return window.__DEBUG_checkReminders().map(r => r.documentId);
            }
        """)
        print("doc 1 stays excluded after its dismissed field's value is changed to a brand-new date:", 1 not in result7b)

        # === Scenario 8: dismissReminder()/reenableReminder()/clearReminderFieldValue()
        # each write the correct persisted state and update reminderSnoozes/allDocs
        # in memory, exercised directly via their __DEBUG_ hooks (no UI yet -- Task 3
        # wires the real buttons) ===
        # The seeded value just needs to be some already-passed/due date -- computed
        # relative to today (like Scenario 7's own dates), not hardcoded, so this
        # scenario's own assertion below stays correct regardless of which real day
        # the suite runs on. (A hardcoded literal here once caused a real bug: once
        # real time passed it, it became overdue, which made checkReminders()'s
        # documented auto-surface-on-open behavior pop the Reminders modal on a
        # later scenario's own reload, blocking its first click.)
        seed8_reminder_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
        seed8 = {
            "documents": [
                {
                    "id": 1, "title": "Doc For Dismiss", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [
                {"document_id": 1, "field_id": 1, "value": seed8_reminder_date},
            ],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed8)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        async def read_db():
            return await page.evaluate("""
                (async () => {
                    const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                    const f = await fh.getFile();
                    return JSON.parse(await f.text());
                })()
            """)

        # dismissReminder
        await page.evaluate("window.__DEBUG_dismissReminder(1, 1)")
        await page.wait_for_timeout(150)
        persisted = await read_db()
        snooze_row = next((s for s in persisted['reminder_snoozes'] if s['document_id'] == 1 and s['field_id'] == 1), None)
        print("dismissReminder() persists dismissed=1:", snooze_row is not None and snooze_row['dismissed'] == 1)
        in_memory_dismissed = await page.evaluate("window.__DEBUG_reminderSnoozes['1:1']")
        print("dismissReminder() updates in-memory reminderSnoozes:", in_memory_dismissed == {'snoozedUntil': None, 'dismissed': True})
        still_has_value = await page.evaluate("window.__DEBUG_getCustomFieldValue(1, 'Renewal Date')")
        print("dismissReminder() does NOT touch the field's own stored value:", still_has_value == seed8_reminder_date)

        # reenableReminder
        await page.evaluate("window.__DEBUG_reenableReminder(1, 1)")
        await page.wait_for_timeout(150)
        persisted = await read_db()
        snooze_row_after = next((s for s in persisted['reminder_snoozes'] if s['document_id'] == 1 and s['field_id'] == 1), None)
        print("reenableReminder() deletes the reminder_snoozes row entirely:", snooze_row_after is None)
        in_memory_after = await page.evaluate("window.__DEBUG_reminderSnoozes['1:1']")
        print("reenableReminder() removes the in-memory entry too:", in_memory_after is None)

        # clearReminderFieldValue
        await page.evaluate("window.__DEBUG_clearReminderFieldValue(1, 1)")
        await page.wait_for_timeout(150)
        persisted = await read_db()
        value_row = next((v for v in persisted['document_field_values'] if v['document_id'] == 1 and v['field_id'] == 1), None)
        print("clearReminderFieldValue() deletes the document_field_values row:", value_row is None)
        in_memory_value = await page.evaluate("window.__DEBUG_getCustomFieldValue(1, 'Renewal Date')")
        print("clearReminderFieldValue() clears the in-memory customFields entry too:", in_memory_value is None)

        # === Scenario 9: the Reminders modal's Dismiss and Delete buttons work
        # end to end -- clicking either removes that row, persists the correct
        # change, and the modal auto-closes once every row is gone via a mix of
        # Dismiss/Delete/Snooze (not just Snooze alone, which Scenario 5 already
        # covers) ===
        seed9 = {
            "documents": [
                {
                    "id": 1, "title": "Doc To Dismiss", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 2, "title": "Doc To Delete", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 3, "title": "Doc To Snooze", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
                {"id": 2, "name": "Warranty End", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [],
            "reminder_snoozes": [],
        }
        # Scenario 8's own seeded reminder value is deliberately overdue (computed
        # relative to today, not hardcoded -- see that scenario's own comment),
        # which makes its own library-open auto-open the Reminders modal
        # (afterDbReady() -> checkReminders()) -- harmless to that scenario's own
        # __DEBUG_-driven assertions, but it leaves a modal backdrop sitting open
        # that would otherwise block Scenario 9's own first UI click below. Close
        # anything left open defensively so this scenario doesn't flake depending
        # on which day it happens to run.
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(100)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed9)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                const today = window.__DEBUG_todayIsoDate();
                const add = (days) => window.__DEBUG_addDaysToIsoDate(today, days);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, today]);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [2, 2, add(60)]); // doc 2's OTHER reminder field, deliberately outside the lookahead window (so it never shows its own modal row) -- must survive deleting field 1's value below
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [2, 1, today]);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [3, 1, today]);
                window.__DEBUG_loadDocumentsFromDb();
            }
        """)
        due9 = await page.evaluate("window.__DEBUG_checkReminders()")
        await page.evaluate("(due) => window.__DEBUG_openRemindersModal(due)", due9)
        await page.wait_for_timeout(200)

        buttons_present = await page.locator('.reminder-row[data-document-id="1"] .reminder-dismiss-btn').count()
        delete_present = await page.locator('.reminder-row[data-document-id="1"] .reminder-delete-btn').count()
        print("each row shows both a Dismiss and a Delete button:", buttons_present == 1 and delete_present == 1)
        delete_is_danger = await page.locator('.reminder-row[data-document-id="1"] .reminder-delete-btn').get_attribute('class')
        print("the Delete button carries the app's .danger styling:", 'danger' in (delete_is_danger or ''))

        async def read_db():
            return await page.evaluate("""
                (async () => {
                    const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                    const f = await fh.getFile();
                    return JSON.parse(await f.text());
                })()
            """)

        # Dismiss doc 1
        await page.click('.reminder-row[data-document-id="1"] .reminder-dismiss-btn')
        await page.wait_for_timeout(200)
        doc1_gone = await page.locator('.reminder-row[data-document-id="1"]').count()
        print("clicking Dismiss removes doc 1's row:", doc1_gone == 0)
        persisted = await read_db()
        doc1_snooze = next((s for s in persisted['reminder_snoozes'] if s['document_id'] == 1 and s['field_id'] == 1), None)
        print("Dismiss persists dismissed=1 for doc 1:", doc1_snooze is not None and doc1_snooze['dismissed'] == 1)
        doc1_value = next((v for v in persisted['document_field_values'] if v['document_id'] == 1 and v['field_id'] == 1), None)
        print("Dismiss does NOT clear doc 1's stored value:", doc1_value is not None)

        # Delete doc 2
        await page.click('.reminder-row[data-document-id="2"] .reminder-delete-btn')
        await page.wait_for_timeout(200)
        doc2_gone = await page.locator('.reminder-row[data-document-id="2"]').count()
        print("clicking Delete removes doc 2's row:", doc2_gone == 0)
        persisted = await read_db()
        doc2_value = next((v for v in persisted['document_field_values'] if v['document_id'] == 2 and v['field_id'] == 1), None)
        print("Delete clears doc 2's stored value entirely:", doc2_value is None)
        doc2_other_field_value = next((v for v in persisted['document_field_values'] if v['document_id'] == 2 and v['field_id'] == 2), None)
        print("Delete leaves doc 2's OTHER reminder field (Warranty End) untouched:", doc2_other_field_value is not None)

        # Snooze doc 3, then confirm the modal auto-closes once all three are gone
        await page.locator('.reminder-row[data-document-id="3"] .reminder-snooze-select').select_option('1w')
        await page.wait_for_timeout(200)
        modal_closed = await page.locator('.reminder-row').count()
        print("modal auto-closes once every row has been cleared via a mix of Dismiss/Delete/Snooze:", modal_closed == 0)

        # === Scenario 10: a dismissed reminder-type field shows the
        # "Reminders are dismissed" hint in the Edit form, an otherwise-identical
        # non-dismissed one doesn't, and clicking Re-enable clears the dismissal
        # (both the hint disappearing and checkReminders() including the field
        # again) ===
        seed10 = {
            "documents": [
                {
                    "id": 1, "title": "Doc With Dismissed Field", "category": None, "document_type": "Policy",
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
                {"id": 2, "name": "Warranty End", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_type_fields": [
                {"document_type": "Policy", "field_name": "Renewal Date", "position": 0},
                {"document_type": "Policy", "field_name": "Warranty End", "position": 1},
            ],
            # Filled in below via JS, using real dates relative to today -- same reason
            # Scenario 4's own seed does this rather than hardcoding literal dates: a
            # hardcoded date drifts into "not due" (excluded by the lookahead window)
            # or "overdue" depending purely on which real day the suite happens to run,
            # which would make the final checkReminders()-inclusion assertion below
            # flaky rather than deterministic.
            "document_field_values": [],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed10)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        renewal_value = await page.evaluate("""
            () => {
                const today = window.__DEBUG_todayIsoDate();
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, today]);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 2, today]);
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [1, 1, null, 1]);
                window.__DEBUG_loadDocumentsFromDb();
                return today;
            }
        """)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)

        renewal_hint = await page.locator('[data-dynamic-field="Renewal Date"] .reminder-reenable-btn').count()
        warranty_hint = await page.locator('[data-dynamic-field="Warranty End"] .reminder-reenable-btn').count()
        print("the dismissed field (Renewal Date) shows the Re-enable hint:", renewal_hint == 1)
        print("the non-dismissed field (Warranty End) does not show it:", warranty_hint == 0)

        # Capture form never shows this hint -- there's no document yet to check.
        # By the time the capture form's own markup replaces modalRoot's content,
        # the edit form (and its hint) is already gone -- no modal-specific
        # selector scoping is needed, just confirm the hint's class is absent
        # from the page entirely while the capture form is open.
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        await page.fill('#f-type', 'Policy')
        await page.wait_for_timeout(200)
        # Blur #f-type (and dismiss its native datalist suggestion popup, which
        # otherwise swallows the very next real mouse click in Chromium) before
        # interacting with anything else in the modal.
        await page.keyboard.press('Tab')
        await page.wait_for_timeout(100)
        capture_hint_count = await page.locator('.reminder-reenable-btn').count()
        print("the capture form never shows a Re-enable hint (no document exists yet):", capture_hint_count == 0)
        await page.click('#cancel-doc-btn')
        await page.wait_for_timeout(150)

        # Re-enable from the edit form
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)

        # Type an unsaved change into a DIFFERENT field on the same form before
        # clicking Re-enable -- Re-enable has no legitimate reason to touch any
        # field's rendered value except making its own hint disappear (it should
        # do a targeted DOM removal, not a full applyDynamicFieldsForType()
        # re-render from the document's originally-persisted values, which would
        # silently discard this unsaved edit -- the same class of bug
        # addInlineCustomField() already documents avoiding for itself). This
        # must be another field INSIDE the dynamic-fields-e container (like
        # Warranty End, #e-field-2) rather than a built-in field like Category --
        # built-ins live in the edit form's static markup outside that container
        # and are never touched by applyDynamicFieldsForType() at all, which
        # would make the assertion pass vacuously even with the bug present.
        await page.fill('#e-field-2', '2026-12-25')

        await page.click('[data-dynamic-field="Renewal Date"] .reminder-reenable-btn')
        await page.wait_for_timeout(200)
        hint_gone = await page.locator('[data-dynamic-field="Renewal Date"] .reminder-reenable-btn').count()
        print("clicking Re-enable removes the hint immediately:", hint_gone == 0)

        still_shows_value = await page.locator('#e-field-1').input_value()
        print("Re-enabling does not touch the field's own value:", still_shows_value == renewal_value)

        warranty_after_reenable = await page.locator('#e-field-2').input_value()
        print("Re-enabling does not discard an unsaved edit in a DIFFERENT dynamic field:", warranty_after_reenable == '2026-12-25')

        due_after_reenable = await page.evaluate("window.__DEBUG_checkReminders()")
        renewal_due_again = any(r['documentId'] == 1 and r['fieldName'] == 'Renewal Date' for r in due_after_reenable)
        print("checkReminders() includes Renewal Date again after Re-enable:", renewal_due_again)

        # === Scenario 11: snoozeReminder()'s own defensive `dismissed = 0` write
        # actually clears a prior dismissal -- untested until now, since no existing
        # scenario snoozes a field that's currently dismissed. A dismissed field
        # never shows a row in the Reminders modal in the first place (by design --
        # there's no Snooze control to click on one), so this is driven via the
        # __DEBUG_snoozeReminder hook to call the real function directly rather than
        # a UI click, the same reasoning __DEBUG_dismissReminder/__DEBUG_reenableReminder/
        # __DEBUG_clearReminderFieldValue above are already driven that way. Deliberately
        # exercises the real snoozeReminder() function itself (not a hand-copied
        # duplicate of its own INSERT OR REPLACE via __DEBUG_dbRun), so this actually
        # proves the app's own code path, not just the stub's dedupe behavior --
        # Scenario 3 already covers that separately. ===
        # Scenario 10 leaves the edit form open -- close it first so it doesn't
        # block this scenario's own #reload-btn click below.
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)
        seed11 = {
            "documents": [
                {
                    "id": 1, "title": "Doc Dismissed Then Snoozed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed11)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        result11 = await page.evaluate("""
            async () => {
                const add = (days) => window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), days);
                // Seed doc 1's field as currently dismissed, matching Scenario 3's own
                // pattern of writing reminder_snoozes directly via __DEBUG_dbRun.
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [1, 1, null, 1]);
                window.__DEBUG_loadDocumentsFromDb();
                const before = window.__DEBUG_reminderSnoozes['1:1'];
                const newSnoozeUntil = add(7);
                // The real snoozeReminder() call -- not a duplicate INSERT.
                await window.__DEBUG_snoozeReminder(1, 1, newSnoozeUntil);
                const after = window.__DEBUG_reminderSnoozes['1:1'];
                return { before, after, newSnoozeUntil };
            }
        """)
        print("field starts dismissed:", result11['before'] == {'snoozedUntil': None, 'dismissed': True})
        print("snoozeReminder() clears dismissed in memory:", result11['after']['dismissed'] == False)
        print("snoozeReminder() sets the new snoozedUntil in memory:", result11['after']['snoozedUntil'] == result11['newSnoozeUntil'])
        persisted11 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        persisted_row = next((s for s in persisted11['reminder_snoozes'] if s['document_id'] == 1 and s['field_id'] == 1), None)
        print("snoozeReminder() persists dismissed=0, not a stale dismissed=1:", persisted_row is not None and persisted_row['dismissed'] == 0)
        print("snoozeReminder() persists the new snoozed_until:", persisted_row is not None and persisted_row['snoozed_until'] == result11['newSnoozeUntil'])

        # === Scenario 12: clearing a reminder-type field's value also removes any
        # lingering reminder_snoozes row for that exact (document_id, field_id) pair
        # -- not just that document_field_values/customFields get cleared (already
        # covered by Scenario 8/10 above). Exercises BOTH call paths:
        # clearReminderFieldValue() directly (the Reminders modal's own Delete
        # button), and clearDefaultReminder() (the row context-menu flyout's "Clear
        # reminder"), which now delegates to it. The real end-to-end proof is the
        # last step of each half: setting a brand-new value on the same field
        # afterward and confirming checkReminders() actually includes it again --
        # i.e. the field is NOT silently still excluded as if still dismissed,
        # which is the exact bug this fix exists to prevent. ===
        seed12 = {
            "documents": [
                {
                    "id": 1, "title": "Doc Custom Field Cleared While Dismissed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 2, "title": "Doc Default Reminder Cleared While Dismissed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed12)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        # -- Half A: clearReminderFieldValue() (custom field, Reminders modal's Delete) --
        result12a = await page.evaluate("""
            () => {
                const today = window.__DEBUG_todayIsoDate();
                // A real stored value, plus a dismissal on top of it.
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, today]);
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [1, 1, null, 1]);
                window.__DEBUG_loadDocumentsFromDb();
                // Raw rows are plain [document_id, field_id, snoozed_until, dismissed]
                // arrays (see queryAll()), not objects -- index, don't use dot access.
                const rowExistsBefore = window.__DEBUG_reminderSnoozesRawRows().some(r => r[0] === 1 && r[1] === 1);
                return { rowExistsBefore };
            }
        """)
        print("Half A: doc 1's reminder_snoozes row exists before clearing:", result12a['rowExistsBefore'])
        await page.evaluate("window.__DEBUG_clearReminderFieldValue(1, 1)")
        await page.wait_for_timeout(150)
        result12a2 = await page.evaluate("""
            () => {
                const rowGone = !window.__DEBUG_reminderSnoozesRawRows().some(r => r[0] === 1 && r[1] === 1);
                return { rowGone };
            }
        """)
        print("clearReminderFieldValue() deletes the reminder_snoozes row entirely (not just dismissed -> 0):", result12a2['rowGone'])
        # Set a brand-new value afterward -- the real end-to-end proof that it isn't
        # silently born already-dismissed.
        due12a = await page.evaluate("""
            () => {
                const today = window.__DEBUG_todayIsoDate();
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, today]);
                window.__DEBUG_loadDocumentsFromDb();
                return window.__DEBUG_checkReminders();
            }
        """)
        print("checkReminders() includes doc 1's Renewal Date again after a brand-new value:", any(r['documentId'] == 1 and r['fieldName'] == 'Renewal Date' for r in due12a))

        # -- Half B: clearDefaultReminder() (the reserved 'Reminder' field, the row
        # context-menu flyout's "Clear reminder") --
        reminder_field_id = await page.evaluate("window.__DEBUG_findFieldByName('Reminder').id")
        await page.evaluate(f"""
            () => {{
                const fieldId = {reminder_field_id};
                const today = window.__DEBUG_todayIsoDate();
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [2, fieldId, today]);
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [2, fieldId, null, 1]);
                window.__DEBUG_loadDocumentsFromDb();
            }}
        """)
        row_exists_before_b = await page.evaluate(f"window.__DEBUG_reminderSnoozesRawRows().some(r => r[0] === 2 && r[1] === {reminder_field_id})")
        print("Half B: doc 2's reminder_snoozes row exists before clearing:", row_exists_before_b)
        await page.evaluate("window.__DEBUG_clearDefaultReminder(2)")
        await page.wait_for_timeout(150)
        row_gone_b = await page.evaluate(f"!window.__DEBUG_reminderSnoozesRawRows().some(r => r[0] === 2 && r[1] === {reminder_field_id})")
        print("clearDefaultReminder() (delegating to clearReminderFieldValue()) also deletes the reminder_snoozes row entirely:", row_gone_b)
        due12b = await page.evaluate(f"""
            () => {{
                const fieldId = {reminder_field_id};
                const today = window.__DEBUG_todayIsoDate();
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [2, fieldId, today]);
                window.__DEBUG_loadDocumentsFromDb();
                return window.__DEBUG_checkReminders();
            }}
        """)
        print("checkReminders() includes doc 2's Reminder field again after a brand-new value:", any(r['documentId'] == 2 and r['fieldName'] == 'Reminder' for r in due12b))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
