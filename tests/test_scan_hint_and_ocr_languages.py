import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

EXPECTED_LANG_VALUES = ['eng+deu', 'deu', 'eng', 'fra', 'spa', 'chi_sim', 'chi_tra']

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
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(300)
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

        # === Capture form: scan-hint toggle ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        hint_hidden_initially = await page.locator('#scan-hint').is_visible()
        print("scan-hint hidden before clicking toggle:", not hint_hidden_initially)
        await page.click('#scan-hint-toggle')
        hint_visible_after_click = await page.locator('#scan-hint').is_visible()
        print("scan-hint visible after clicking toggle:", hint_visible_after_click)
        await page.click('#scan-hint-toggle')
        hint_hidden_again = await page.locator('#scan-hint').is_visible()
        print("scan-hint hidden after clicking toggle again:", not hint_hidden_again)

        # === Capture form: OCR language options ===
        capture_lang_values = await page.locator('#ocr-lang option').evaluate_all('opts => opts.map(o => o.value)')
        print("capture #ocr-lang values match expected:", capture_lang_values == EXPECTED_LANG_VALUES, capture_lang_values)

        # Save a document so we can open Edit and check its language select too.
        with open('langdoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 langdoc")
        await page.set_input_files('#file-input', 'langdoc.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Lang Test Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        edit_lang_values = await page.locator('#e-ocr-lang option').evaluate_all('opts => opts.map(o => o.value)')
        print("edit #e-ocr-lang values match expected:", edit_lang_values == EXPECTED_LANG_VALUES, edit_lang_values)

        print("JS errors:", errors)
        _os.remove('langdoc.pdf')
        await browser.close()

asyncio.run(main())
