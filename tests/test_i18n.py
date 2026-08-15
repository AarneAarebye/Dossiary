import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json
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

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
