import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

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

        # === Capture form: Date input should render with a visible (light-on-dark) picker icon ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        capture_color_scheme = await page.locator('#f-date').evaluate("el => getComputedStyle(el).colorScheme")
        print("capture #f-date color-scheme (should be dark):", capture_color_scheme)
        assert capture_color_scheme == 'dark', f"expected dark, got {capture_color_scheme!r}"

        with open('datepicker.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 datepicker")
        await page.set_input_files('#file-input', 'datepicker.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Date Picker Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # === Edit form: same fix must apply there too ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        edit_color_scheme = await page.locator('#e-date').evaluate("el => getComputedStyle(el).colorScheme")
        print("edit #e-date color-scheme (should be dark):", edit_color_scheme)
        assert edit_color_scheme == 'dark', f"expected dark, got {edit_color_scheme!r}"

        print("JS ERRORS:", errors)
        _os.remove('datepicker.pdf')
        await browser.close()

asyncio.run(main())
