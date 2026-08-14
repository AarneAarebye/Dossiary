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

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
