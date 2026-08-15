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
        await page4.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();") # empty folder, no library.sqlite
        await page4.click("#open-btn")
        await page4.wait_for_timeout(300)
        init_title = await page4.locator('#init-state h2').inner_text()
        print("Scenario 6 -- init-state (no library.sqlite) translated:", init_title == "Leerer Ordner")
        init_message_text = await page4.locator('#init-message').inner_text()
        print("Scenario 6 -- init-message names the folder (German wrapper text):", "EmptyLibrary" in init_message_text and "Keine" in init_message_text)

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

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
