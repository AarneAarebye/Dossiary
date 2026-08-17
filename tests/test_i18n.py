import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json, base64
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # === Scenario 1: default language with no navigator.language override
        # matches existing English strings (regression guard) ===
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        title_text = await page.locator('#empty-state h2').inner_text()
        print("Scenario 1 -- default (no locale signal) shows English:", title_text == "No library open")
        await page.close()

        # === Scenario 2: navigator.language = de-DE with no stored preference
        # yet results in German on first load ===
        page2 = await browser.new_page()
        await page2.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'de-DE' });
            Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de'] });
        """)
        await page2.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page2.add_init_script(stub_js)
        await page2.goto(f"file://{APP_PATH}")
        await page2.wait_for_timeout(200)
        title_text_de = await page2.locator('#empty-state h2').inner_text()
        print("Scenario 2 -- de-DE browser locale auto-detects German:", title_text_de == "Keine Bibliothek geöffnet")

        # === Scenario 3: clicking the toggle switches the empty-state title,
        # and the choice persists across reload, overriding navigator.language ===
        await page2.click('#lang-toggle')
        await page2.wait_for_timeout(100)
        title_after_toggle = await page2.locator('#empty-state h2').inner_text()
        print("Scenario 3 -- toggle switches to English:", title_after_toggle == "No library open")
        await page2.reload()
        await page2.wait_for_timeout(200)
        title_after_reload = await page2.locator('#empty-state h2').inner_text()
        print("Scenario 3 -- manual choice persists across reload (overrides de-DE browser locale):", title_after_reload == "No library open")

        # === Scenario 4: date formatting follows the UI language, not just the
        # browser's OS locale (page2 is currently in English after Scenario 3's
        # toggle click -- switch back to German and open a seeded document's
        # detail view to check the date format) ===
        await page2.click('#lang-toggle')
        await page2.wait_for_timeout(100)
        SEED = {"documents": [{
            "id": 1, "title": "Test Doc", "category": "Finance", "document_type": "Invoice",
            "date": "2026-03-05T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-05T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        }], "tags": [], "document_tags": []}
        await page2.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page2.click("#open-btn")
        await page2.wait_for_timeout(300)
        await page2.click('tr[data-id="1"]')
        await page2.wait_for_timeout(200)
        meta_text = await page2.locator('.modal-meta').inner_text()
        print("Scenario 4 -- German UI language produces German-formatted date (contains 'März'):", 'März' in meta_text)

        # === Scenario 5: nav, toolbar, and stats switch to German ===
        page3 = await browser.new_page()
        await page3.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page3.add_init_script(stub_js)
        await page3.goto(f"file://{APP_PATH}")
        await page3.wait_for_timeout(200)
        await page3.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page3.click("#open-btn")
        await page3.wait_for_timeout(300)
        await page3.click('#lang-toggle')
        await page3.wait_for_timeout(150)
        nav_all_text = await page3.locator('#nav-item-all .nav-item-label').inner_text()
        add_btn_text = await page3.locator('#add-btn').inner_text()
        stats_text = await page3.locator('#stats').inner_text()
        category_filter_text = await page3.locator('#category-filter option[value=""]').inner_text()
        print("Scenario 5 -- nav item translated:", nav_all_text == "Alle Dokumente")
        print("Scenario 5 -- toolbar button translated:", "Dokument hinzufügen" in add_btn_text)
        print("Scenario 5 -- stats bar translated:", "Dokumente" in stats_text)
        print("Scenario 5 -- category filter default option translated:", category_filter_text == "Alle Kategorien")

        # === Scenario 6: empty-state body, init-state (no library.sqlite),
        # and library-open status messages translate ===
        page4 = await browser.new_page()
        await page4.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'de-DE' });
            Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de'] });
        """)
        await page4.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page4.add_init_script(stub_js)
        await page4.goto(f"file://{APP_PATH}")
        await page4.wait_for_timeout(200)
        open_btn_text = await page4.locator('#open-btn').inner_text()
        print("Scenario 6 -- empty-state open button translated:", open_btn_text == "Bibliotheksordner öffnen")
        # The static "Important:"/"Wichtig:" <b> label and the translated
        # emptyHintImportant span sit side by side in the markup -- an earlier
        # version of emptyHintImportant's own STRINGS value redundantly
        # repeated the label text ("Wichtig: Öffne diese Datei..."), which
        # rendered as "Wichtig: Wichtig: ..." and wasn't caught by inner_text()
        # equality checks elsewhere in this file (they collapse markup, not
        # duplicated plain text). Assert the label appears exactly once.
        hint_text = await page4.locator('#empty-state .hint').inner_text()
        print("Scenario 6 -- empty-state hint's 'Wichtig:' label is not duplicated:", hint_text.count('Wichtig:') == 1)
        await page4.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();") # empty folder, no library.sqlite
        await page4.click("#open-btn")
        await page4.wait_for_timeout(300)
        init_title = await page4.locator('#init-state h2').inner_text()
        print("Scenario 6 -- init-state (no library.sqlite) translated:", init_title == "Leerer Ordner")
        init_message_text = await page4.locator('#init-message').inner_text()
        print("Scenario 6 -- init-message names the folder (German wrapper text):", "EmptyLibrary" in init_message_text and "Keine" in init_message_text)
        # initMessageWithName's own STRINGS value already wraps {name} in
        # <b>...</b> -- the call site must not ALSO wrap the substituted value
        # in <b>...</b>, which would produce redundant nested <b><b>...</b></b>
        # (invisible to an inner_text() check, since browsers collapse nested
        # bold tags visually; only inspecting the actual innerHTML catches it).
        init_message_html = await page4.locator('#init-message').inner_html()
        print("Scenario 6 -- init-message has no nested <b><b> tags:", '<b><b>' not in init_message_html and '<b></b>' not in init_message_html)

        # === Scenario 7: recent-libraries list (on the empty-state screen) is
        # rebuilt via t() calls baked into a template string, not data-i18n
        # attributes -- confirm the language toggle re-renders it live, not
        # just on next page load. Open a seeded library (recording a recent-
        # libraries entry), then use the "Switch library" button with
        # __TEST_ROOT cleared (the same simulated-cancel pattern
        # test_recent_libraries.py uses) to land back on the empty-state
        # screen with the recent-libraries list populated ===
        page5 = await browser.new_page()
        await page5.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page5.add_init_script(stub_js)
        await page5.goto(f"file://{APP_PATH}")
        await page5.wait_for_timeout(200)
        EMPTY_SEED = {"documents": [], "tags": [], "document_tags": []}
        await page5.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'LibraryA';" % json.dumps(EMPTY_SEED))
        await page5.click("#open-btn")
        await page5.wait_for_timeout(300)
        await page5.evaluate("window.__TEST_ROOT = null;")  # simulate cancelling the picker on "Switch library"
        await page5.click("#reload-btn")
        await page5.wait_for_timeout(200)
        # #recent-libraries h3 is CSS text-transform:uppercase, so inner_text()
        # reports "RECENT LIBRARIES" even though the actual DOM/source text is
        # "Recent libraries" -- same quirk test_person_type_field.py's own
        # ".modal-section h3" check already lives with.
        recent_heading_before = await page5.locator('#recent-libraries h3').inner_text()
        print("Scenario 7 -- recent-libraries heading starts English:", recent_heading_before == "RECENT LIBRARIES")
        await page5.click('#lang-toggle')
        await page5.wait_for_timeout(150)
        recent_heading_after = await page5.locator('#recent-libraries h3').inner_text()
        print("Scenario 7 -- recent-libraries heading retranslates live on toggle (not just next load):", recent_heading_after == "ZULETZT GEÖFFNETE BIBLIOTHEKEN")
        recent_status_after = await page5.locator('[id^="recent-lib-status-"]').inner_text()
        print("Scenario 7 -- recent-libraries 'Last opened' line retranslates live:", "Zuletzt geöffnet:" in recent_status_after)

        # === Scenario 8: table headers and row content translate (reuses
        # page3 from Scenario 5, already open with the seeded library and
        # toggled to German) ===
        # thead th is CSS text-transform:uppercase, so inner_text() reports
        # "DOKUMENT" even though the actual DOM/source text is "Dokument" --
        # same quirk the Scenario 7 recent-libraries heading check already
        # lives with.
        col_header_text = await page3.locator('th[data-key="title"]').inner_text()
        print("Scenario 8 -- table column header translated:", col_header_text == "DOKUMENT")
        row_edit_title = await page3.locator('tr[data-id="1"] .row-edit-btn').get_attribute('title')
        print("Scenario 8 -- row-edit button title translated:", row_edit_title == "Bearbeiten")
        count_line_text = await page3.locator('#count-line').inner_text()
        print("Scenario 8 -- showing-count line translated:", "von" in count_line_text and "Dokumenten" in count_line_text)

        # === Scenario 9: detail modal translates (reuses page3, still German,
        # detail modal not yet open there -- click a row) ===
        await page3.click('tr[data-id="1"]')
        await page3.wait_for_timeout(200)
        edit_btn_text = await page3.locator('#edit-doc-btn').inner_text()
        print("Scenario 9 -- detail modal Edit button translated:", edit_btn_text == "Bearbeiten")
        # .modal-section h3 is CSS text-transform:uppercase, so inner_text()
        # reports e.g. "PERSONEN" even though the actual DOM/source text is
        # "Personen" -- same quirk the Scenario 7/8 uppercase-header checks
        # already live with. Which heading renders first depends on whether
        # this seeded doc has any non-Amount/Currency/Payment-method custom
        # field values (it doesn't), so People/Tags are the plausible ones,
        # not Fields.
        fields_heading = await page3.locator('.modal-section h3').first.inner_text()
        print("Scenario 9 -- detail modal section heading translated:", fields_heading in ("FELDER", "PERSONEN"))
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 10: shared field-rendering validation messages
        # translate (reuses page3, still German) -- renderPersonFieldHtml()/
        # renderGenericFieldHtml()/addInlineCustomField() are shared by both
        # the capture and edit forms; exercised here via the capture form's
        # own "+ Add a custom field" flow. The toggle/mini-form only become
        # visible once a document type is entered (updateAddFieldVisibility()),
        # so a type is filled in first -- leaving the new field's name blank
        # then reaches the "Enter a field name" validation message ===
        await page3.click('#add-btn')
        await page3.wait_for_timeout(200)
        await page3.fill('#f-type', 'Invoice')
        await page3.locator('#f-type').blur()
        await page3.wait_for_timeout(100)
        await page3.click('#f-add-field-toggle')
        await page3.wait_for_timeout(100)
        await page3.click('#f-new-field-btn')  # no name entered
        await page3.wait_for_timeout(100)
        validation_text = await page3.locator('#f-new-field-status').inner_text()
        print("Scenario 10 -- inline add-field validation message translated:", validation_text == "Gib einen Feldnamen ein.")
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 11: capture form ("Add document" modal), scan hint, and
        # capture-time OCR flow translate (reuses page3, still German, capture
        # modal not open there since Scenario 10 closed it) ===
        await page3.click('#add-btn')
        await page3.wait_for_timeout(200)
        modal_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 11 -- capture modal heading translated:", modal_heading == "Dokument hinzufügen")
        save_btn_text = await page3.locator('#save-doc-btn').inner_text()
        print("Scenario 11 -- capture save button translated:", save_btn_text == "Dokument speichern")
        file_drop_text = await page3.locator('#file-drop').inner_text()
        print("Scenario 11 -- file-drop label translated:", "Klicken, um eine Datei auszuwählen" in file_drop_text)
        # scanHintHtml() is only wired up as visible-toggle content; click the
        # toggle to reveal it, then check the German intro/body/outro compose
        # correctly (this also exercises detectOS()'s branching -- whichever
        # branch fires, the surrounding intro/outro text is always present).
        await page3.click('#scan-hint-toggle')
        await page3.wait_for_timeout(100)
        scan_hint_text = await page3.locator('#scan-hint').inner_text()
        print("Scenario 11 -- scan-hint intro/outro translated:", "Diese App kann deinen Scanner nicht direkt öffnen" in scan_hint_text and "Klicken, um eine Datei auszuwählen" in scan_hint_text)
        # .field label is CSS text-transform:uppercase, so inner_text() reports
        # "DOKUMENTTYP" even though the actual DOM/source text is "Dokumenttyp"
        # -- same quirk the Scenario 7/8/9 uppercase-header checks already live
        # with.
        doc_type_label_text = await page3.locator('label[for="f-type"]').inner_text()
        print("Scenario 11 -- document type label translated:", doc_type_label_text == "DOKUMENTTYP")
        tags_label_text = await page3.locator('label[for="f-tags"]').inner_text()
        print("Scenario 11 -- tags label translated:", tags_label_text == "TAGS (DURCH KOMMA GETRENNT)")
        await page3.click('#cancel-doc-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 12: edit form ("Edit document" modal), its Save flow,
        # and edit-time OCR button/status translate, including reused
        # capture-form keys (reuses page3, still German, capture modal
        # already closed by Scenario 11's Cancel click) ===
        await page3.click('tr[data-id="1"]')
        await page3.wait_for_timeout(200)
        await page3.click('#edit-doc-btn')
        await page3.wait_for_timeout(200)
        edit_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 12 -- edit modal heading translated:", edit_heading == "Dokument bearbeiten")
        save_changes_text = await page3.locator('#save-edit-btn').inner_text()
        print("Scenario 12 -- edit save-changes button translated:", save_changes_text == "Änderungen speichern")
        # .field label is CSS text-transform:uppercase, so inner_text() reports
        # "DOKUMENTTYP" even though the actual DOM/source text is "Dokumenttyp"
        # -- same quirk the Scenario 7/8/9/11 uppercase-header checks already
        # live with.
        edit_doc_type_label = await page3.locator('label[for="e-type"]').inner_text()
        print("Scenario 12 -- edit document type label translated:", edit_doc_type_label == "DOKUMENTTYP")
        # Task 8's own reviewer found that wireAddFieldControls()'s dynamic
        # toggle re-labeling was already translated (shared with capture), but
        # the edit form's own STATIC "+ Add a custom field" button markup was
        # still hardcoded English -- confirm that gap is now closed. The
        # seeded doc has document_type "Invoice" set, so updateAddFieldVisibility('e')
        # has already made the wrap visible by this point.
        add_field_toggle_text = await page3.locator('#e-add-field-toggle').inner_text()
        print("Scenario 12 -- edit add-field toggle (static markup) translated:", add_field_toggle_text == "+ Benutzerdefiniertes Feld hinzufügen")
        run_ocr_text = await page3.locator('#e-run-ocr-btn').inner_text()
        print("Scenario 12 -- edit Run OCR button (reused capture key) translated:", run_ocr_text == "OCR ausführen")
        # This seeded doc's file_path has no backing file in the fake
        # filesystem (__makeSeededRoot only creates library.sqlite + an empty
        # files/ dir), so clicking Run OCR here would only exercise the
        # already-covered ocrFailedStatus error path, not the new
        # ocrDone/ocrLoadingPdf/ocrRecognizingPage/editOcrPdfDone keys --
        # test_edit_ocr.py's own doc-with-a-real-file scenarios are a more
        # reliable place to exercise that success path if ever needed; here
        # we only confirm the German label/status wiring is in place.
        await page3.click('#cancel-edit-btn')
        await page3.wait_for_timeout(150)
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 13: Field Settings modal translates (reuses page3,
        # still German; no modal open at this point since Scenario 12 closed
        # both the edit form via Cancel and the detail view via modal-close-btn) ===
        await page3.click('#manage-fields-btn')
        await page3.wait_for_timeout(200)
        fs_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 13 -- Field Settings heading translated:", fs_heading == "Feldeinstellungen")
        # .fs-col h3 is CSS text-transform:uppercase (see line ~152), so
        # inner_text() reports "DOKUMENTTYPEN" even though the actual
        # DOM/source text is "Dokumenttypen" -- same quirk the Scenario
        # 7/8/9/11/12 uppercase-header checks already live with.
        col_heading = await page3.locator('.fs-col h3').first.inner_text()
        print("Scenario 13 -- Field Settings column heading translated:", col_heading == "DOKUMENTTYPEN")
        await page3.click('#fs-done-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 14: Manage Collections modal translates (reuses page3,
        # still German; no modal open at this point since Scenario 13 closed
        # the Field Settings modal) ===
        await page3.click('#manage-collections-btn')
        await page3.wait_for_timeout(200)
        mc_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 14 -- Manage Collections heading translated:", mc_heading == "Sammlungen verwalten")
        await page3.click('#mc-done-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 15: Reports view translates (reuses page3, still German;
        # no modal open at this point since Scenario 14 closed the Manage
        # Collections modal) ===
        await page3.click('#nav-item-reports')
        await page3.wait_for_timeout(200)
        print_btn_text = await page3.locator('#reports-print-btn').inner_text()
        print("Scenario 15 -- Reports print button translated:", print_btn_text == "🖨 Drucken")

        # === Scenario 16: Libraries/licenses modal translates ===
        await page3.click('#libraries-link')
        await page3.wait_for_timeout(200)
        lib_heading = await page3.locator('.modal h2').inner_text()
        print("Scenario 16 -- Libraries modal heading translated:", lib_heading == "Open-Source-Bibliotheken")
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 17: drag-and-drop overlay text translates ===
        overlay_text = await page3.locator('.drop-overlay-box').inner_text()
        print("Scenario 17 -- drop overlay text translated:", overlay_text == "Zum Prüfen ablegen")

        # === Scenario 18: localStorage access blocked (privacy settings, enterprise
        # policy, etc.) must not crash the whole app -- loadLang()/saveLang() run at
        # module-init time, before #open-btn's own click handler is wired up, so an
        # uncaught throw here would abort the entire top-level IIFE, not just language
        # detection. Replace window.localStorage with an object whose getItem/setItem
        # both throw (the same shape a real blocked-storage browser exposes), confirm
        # the page still renders and #open-btn still works, and confirm the auto-detect
        # fallback (navigator.language) and the manual toggle both still work in-memory
        # despite every persistence call failing silently underneath them ===
        page6 = await browser.new_page()
        errors6 = []
        page6.on("pageerror", lambda exc: errors6.append(str(exc)))
        await page6.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'de-DE' });
            Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de'] });
            Object.defineProperty(window, 'localStorage', {
                configurable: true,
                value: {
                    getItem: () => { throw new DOMException('blocked', 'SecurityError'); },
                    setItem: () => { throw new DOMException('blocked', 'SecurityError'); },
                },
            });
        """)
        await page6.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page6.add_init_script(stub_js)
        await page6.goto(f"file://{APP_PATH}")
        await page6.wait_for_timeout(200)
        title_text_blocked = await page6.locator('#empty-state h2').inner_text()
        print("Scenario 18 -- blocked localStorage doesn't abort init; page still renders, falling back to de-DE auto-detect:", title_text_blocked == "Keine Bibliothek geöffnet")
        print("Scenario 18 -- no uncaught JS errors from the blocked localStorage calls:", errors6 == [])
        # #open-btn's click handler must still be wired -- if the top-level IIFE had
        # actually aborted, this click would silently do nothing instead of opening
        # the (fake) picked folder.
        await page6.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s);" % json.dumps({"documents": [], "tags": [], "document_tags": []}))
        await page6.click("#open-btn")
        await page6.wait_for_timeout(300)
        opened_ok = await page6.locator('#toolbar').is_visible()
        print("Scenario 18 -- open-btn's click handler still wired (library opens) despite blocked localStorage:", opened_ok)
        # Toggling language with localStorage blocked must not throw either -- saveLang()
        # fails silently, but the in-memory language still switches for this session.
        await page6.click('#lang-toggle')
        await page6.wait_for_timeout(150)
        nav_all_text_toggled = await page6.locator('#nav-item-all .nav-item-label').inner_text()
        print("Scenario 18 -- toggling language still works in-memory despite blocked localStorage (no throw):", nav_all_text_toggled == "All Documents")
        print("Scenario 18 -- still no uncaught JS errors after the toggle:", errors6 == [])

        # === Scenario 19: #sub-label (the empty-state screen's own subtitle) retranslates
        # live on toggle, not just the recent-libraries list Scenario 7 already checks --
        # setLang()'s empty-state branch used to call only renderRecentLibraries(), leaving
        # #sub-label (visible on that exact same screen) stuck in whatever language it was
        # last set in. Reuses page5's DOM state exactly as Scenario 7 left it -- German,
        # empty-state screen, right after that scenario's own #lang-toggle click -- so this
        # assertion needs no fresh interaction of its own to be meaningful ===
        sub_label_after_toggle = await page5.locator('#sub-label').inner_text()
        print("Scenario 19 -- empty-state sub-label retranslates live on toggle (not just the recent-libraries list):", sub_label_after_toggle == "Keine Bibliothek geöffnet")

        # === Scenario 20: FIELD_DEFS-derived labels (Columns menu, Reports breakdown
        # dropdown) and the static OCR-language <option> lists (capture + edit forms)
        # translate -- two separate plan gaps the final review found (FIELD_DEFS itself
        # hardcoded English `label`s with no labelKey at all, and #ocr-lang/#e-ocr-lang
        # were never wired to t() in either form), checked together since both are plain
        # option-text lookups. Back to the All Documents view first (page3 has been on
        # Reports since Scenario 15, where the table rows Scenario 20's own edit-form
        # check needs aren't rendered) -- still German ===
        await page3.click('#nav-item-all')
        await page3.wait_for_timeout(150)
        await page3.click('#columns-btn')
        await page3.wait_for_timeout(150)
        columns_menu_text = await page3.locator('#columns-menu').inner_text()
        print("Scenario 20 -- Columns menu's built-in field labels translated:", "Kategorie" in columns_menu_text and "Datum" in columns_menu_text and "Tags" in columns_menu_text)
        await page3.click('#columns-btn')
        await page3.wait_for_timeout(100)
        # The seeded library's migrateSentinelFieldsToGeneric() backfill also creates a
        # 'Payment method' field flagged show_as_column, which dynamicColumnDefs() (real
        # user data, deliberately never translated -- see FIELD_DEFS's own comment) tacks
        # on after the three fixed, translatable entries -- so check just the fixed
        # prefix rather than exact list equality.
        breakdown_options = await page3.locator('#report-breakdown-field option').all_inner_texts()
        print("Scenario 20 -- Reports breakdown dropdown's fixed options translated:", breakdown_options[:3] == ["Kategorie", "Typ", "Personen"])

        ocr_lang_de = ["Automatisch (Deutsch + Englisch)", "Nur Deutsch", "Nur Englisch", "Nur Französisch",
                        "Nur Spanisch", "Nur Chinesisch (Vereinfacht)", "Nur Chinesisch (Traditionell / Kantonesisch)"]
        await page3.click('#add-btn')
        await page3.wait_for_timeout(200)
        capture_ocr_lang_options = await page3.locator('#ocr-lang option').all_inner_texts()
        print("Scenario 20 -- capture-form OCR language dropdown options translated:", capture_ocr_lang_options == ocr_lang_de)
        await page3.click('#cancel-doc-btn')
        await page3.wait_for_timeout(150)
        await page3.click('tr[data-id="1"]')
        await page3.wait_for_timeout(200)
        await page3.click('#edit-doc-btn')
        await page3.wait_for_timeout(200)
        edit_ocr_lang_options = await page3.locator('#e-ocr-lang option').all_inner_texts()
        print("Scenario 20 -- edit-form OCR language dropdown options translated:", edit_ocr_lang_options == ocr_lang_de)
        await page3.click('#cancel-edit-btn')
        await page3.wait_for_timeout(150)
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 21: #lang-toggle is inert while a modal is open -- a mouse click
        # is already blocked by the modal's own backdrop, but keyboard Tab-through can
        # still reach and activate the button (Enter/Space fires a real click event the
        # same as a mouse click would), and re-rendering an open modal in place isn't
        # safe (would discard in-progress capture/edit work). Confirm the click while a
        # modal's open is a genuine no-op -- no language change, modal content
        # untouched -- and that the toggle isn't permanently broken, only inert while a
        # modal happens to be open (reuses page3, still German, no modal open after
        # Scenario 20's own cleanup) ===
        await page3.click('#add-btn')
        await page3.wait_for_timeout(200)
        toggle_label_before_guard = await page3.locator('#lang-toggle').inner_text()
        modal_heading_before_guard = await page3.locator('.modal h2').inner_text()
        # A plain click() here would just time out -- the backdrop genuinely intercepts
        # pointer events for a real mouse click (Playwright confirms the same thing a
        # human mouse user would hit), which is exactly the existing protection this
        # fix doesn't need to touch. force=True skips that hit-testing and dispatches
        # the click event directly on the button, the same way a keyboard Enter/Space
        # activation would (no hit-testing involved either) -- this is the actual gap
        # the click handler's own guard exists to close.
        await page3.click('#lang-toggle', force=True)
        await page3.wait_for_timeout(150)
        toggle_label_after_guard = await page3.locator('#lang-toggle').inner_text()
        modal_heading_after_guard = await page3.locator('.modal h2').inner_text()
        print("Scenario 21 -- lang-toggle click while a modal is open is a no-op (toggle label unchanged):", toggle_label_before_guard == toggle_label_after_guard == "EN")
        print("Scenario 21 -- the open modal's own language is untouched by the blocked toggle:", modal_heading_before_guard == modal_heading_after_guard == "Dokument hinzufügen")
        await page3.click('#cancel-doc-btn')
        await page3.wait_for_timeout(150)
        # Once the modal is closed, the toggle works normally again -- confirming this
        # is a scoped-to-open-modal guard, not a general regression in the button.
        await page3.click('#lang-toggle')
        await page3.wait_for_timeout(150)
        toggle_label_after_close = await page3.locator('#lang-toggle').inner_text()
        print("Scenario 21 -- lang-toggle works again once the modal is closed:", toggle_label_after_close == "DE")
        # Switch back to German so the reused-page3 scenarios below see what they expect.
        await page3.click('#lang-toggle')
        await page3.wait_for_timeout(150)

        # === Scenario 22: the remaining minor-severity gaps from the final review --
        # thumbnail/file-preview alt text, the 5 modal close-button aria-labels that
        # still hardcoded "Close" instead of reusing detailCloseAriaLabel (Libraries,
        # edit, Field Settings, capture, Manage Collections), the 8 built-in (non-
        # dynamic) field clear buttons' title/aria-label, and the footer's "Libraries"
        # link text. All four are the same class of "still-hardcoded-English" gap,
        # checked together in one pass (reuses page3, back to German after Scenario
        # 21's own toggle probe) ===
        footer_libraries_text = await page3.locator('#libraries-link').inner_text()
        print("Scenario 22 -- footer Libraries link translated:", footer_libraries_text == "Bibliotheken")

        await page3.click('#libraries-link')
        await page3.wait_for_timeout(200)
        lib_close_aria = await page3.locator('#modal-close-btn').get_attribute('aria-label')
        print("Scenario 22 -- Libraries modal close button aria-label translated:", lib_close_aria == "Schließen")
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)

        await page3.click('#manage-fields-btn')
        await page3.wait_for_timeout(200)
        fs_close_aria = await page3.locator('#modal-close-btn').get_attribute('aria-label')
        print("Scenario 22 -- Field Settings modal close button aria-label translated:", fs_close_aria == "Schließen")
        await page3.click('#fs-done-btn')
        await page3.wait_for_timeout(150)

        await page3.click('#manage-collections-btn')
        await page3.wait_for_timeout(200)
        mc_close_aria = await page3.locator('#modal-close-btn').get_attribute('aria-label')
        print("Scenario 22 -- Manage Collections modal close button aria-label translated:", mc_close_aria == "Schließen")
        await page3.click('#mc-done-btn')
        await page3.wait_for_timeout(150)

        await page3.click('#add-btn')
        await page3.wait_for_timeout(200)
        capture_close_aria = await page3.locator('#modal-close-btn').get_attribute('aria-label')
        print("Scenario 22 -- capture modal close button aria-label translated:", capture_close_aria == "Schließen")
        f_type_clear_title = await page3.locator('#f-type-clear').get_attribute('title')
        f_type_clear_aria = await page3.locator('#f-type-clear').get_attribute('aria-label')
        print("Scenario 22 -- capture Document Type clear button translated:", f_type_clear_title == "Leeren" and f_type_clear_aria == "Dokumenttyp leeren")
        f_category_clear_aria = await page3.locator('#f-category-clear').get_attribute('aria-label')
        print("Scenario 22 -- capture Category clear button translated:", f_category_clear_aria == "Kategorie leeren")
        f_subcategory_clear_aria = await page3.locator('#f-subcategory-clear').get_attribute('aria-label')
        print("Scenario 22 -- capture Subcategory clear button translated:", f_subcategory_clear_aria == "Unterkategorie leeren")
        f_tags_clear_aria = await page3.locator('#f-tags-clear').get_attribute('aria-label')
        print("Scenario 22 -- capture Tags clear button translated:", f_tags_clear_aria == "Tags leeren")
        # The file-picker preview <img alt> only renders once a file is actually picked --
        # write a real (tiny) PNG to disk and pick it, same pattern test_copy_path.py uses.
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('i18nfixpreview.png', 'wb') as f:
            f.write(png_bytes)
        await page3.set_input_files('#file-input', 'i18nfixpreview.png')
        await page3.wait_for_timeout(150)
        preview_alt = await page3.locator('#file-preview-area img').get_attribute('alt')
        print("Scenario 22 -- capture file-preview alt text translated:", preview_alt == "Dokumentvorschau")
        await page3.click('#cancel-doc-btn')
        await page3.wait_for_timeout(150)

        await page3.click('tr[data-id="1"]')
        await page3.wait_for_timeout(200)
        await page3.click('#edit-doc-btn')
        await page3.wait_for_timeout(200)
        edit_close_aria = await page3.locator('#modal-close-btn').get_attribute('aria-label')
        print("Scenario 22 -- edit modal close button aria-label translated:", edit_close_aria == "Schließen")
        e_type_clear_aria = await page3.locator('#e-type-clear').get_attribute('aria-label')
        print("Scenario 22 -- edit Document Type clear button translated:", e_type_clear_aria == "Dokumenttyp leeren")
        e_category_clear_aria = await page3.locator('#e-category-clear').get_attribute('aria-label')
        print("Scenario 22 -- edit Category clear button translated:", e_category_clear_aria == "Kategorie leeren")
        e_subcategory_clear_aria = await page3.locator('#e-subcategory-clear').get_attribute('aria-label')
        print("Scenario 22 -- edit Subcategory clear button translated:", e_subcategory_clear_aria == "Unterkategorie leeren")
        e_tags_clear_aria = await page3.locator('#e-tags-clear').get_attribute('aria-label')
        print("Scenario 22 -- edit Tags clear button translated:", e_tags_clear_aria == "Tags leeren")
        await page3.click('#cancel-edit-btn')
        await page3.wait_for_timeout(150)
        await page3.click('#modal-close-btn')
        await page3.wait_for_timeout(150)

        # === Scenario 23: footer "User Guide" link opens the right language's guide,
        # in a new tab, and updates live when the language is toggled (reuses page3,
        # currently German from Scenario 22's own setup) ===
        user_guide_target = await page3.locator('#user-guide-link').get_attribute('target')
        print("Scenario 23 -- User Guide link opens in a new tab:", user_guide_target == "_blank")
        user_guide_href_de = await page3.locator('#user-guide-link').get_attribute('href')
        print("Scenario 23 -- User Guide link points at the German guide while UI is German:",
              user_guide_href_de.endswith('/USER_GUIDE.de.md'))
        user_guide_text_de = await page3.locator('#user-guide-link').inner_text()
        print("Scenario 23 -- User Guide link text translated:", user_guide_text_de == "Benutzerhandbuch")

        await page3.click('#lang-toggle')
        await page3.wait_for_timeout(150)
        user_guide_href_en = await page3.locator('#user-guide-link').get_attribute('href')
        print("Scenario 23 -- User Guide link updates to the English guide after toggling to English:",
              user_guide_href_en.endswith('/USER_GUIDE.md') and not user_guide_href_en.endswith('/USER_GUIDE.de.md'))
        user_guide_text_en = await page3.locator('#user-guide-link').inner_text()
        print("Scenario 23 -- User Guide link text back to English:", user_guide_text_en == "User Guide")

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
