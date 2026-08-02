import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url:
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
        await page.wait_for_timeout(200)

        # Toggle payment_method ON, tags OFF
        await page.click('#columns-btn')
        await page.wait_for_timeout(150)
        await page.check('#col-toggle-payment_method')
        await page.wait_for_timeout(150)
        await page.uncheck('#col-toggle-tags')
        await page.wait_for_timeout(150)

        # Simulate closing and reopening the SAME library folder (same __TEST_ROOT handle,
        # since it's a real in-memory fake filesystem the "settings" are actually persisted to)
        await page.click('#reload-btn')
        await page.wait_for_timeout(400)

        payment_visible = await page.locator('th[data-field="payment_method"]').is_visible()
        tags_visible = await page.locator('th[data-field="tags"]').is_visible()
        print("payment_method column visible after reopen (should be True):", payment_visible)
        print("tags column visible after reopen (should be False):", tags_visible)

        # also check the columns menu checkboxes themselves reflect restored state
        await page.click('#columns-btn')
        await page.wait_for_timeout(150)
        payment_checked = await page.locator('#col-toggle-payment_method').is_checked()
        tags_checked = await page.locator('#col-toggle-tags').is_checked()
        print("payment_method checkbox checked:", payment_checked)
        print("tags checkbox checked (should be False):", tags_checked)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
