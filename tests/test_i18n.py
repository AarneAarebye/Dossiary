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
        print("Scenario 5 -- nav item translated:", nav_all_text == "Alle Dokumente")
        print("Scenario 5 -- toolbar button translated:", "Dokument hinzufügen" in add_btn_text)
        print("Scenario 5 -- stats bar translated:", "Dokumente" in stats_text)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
