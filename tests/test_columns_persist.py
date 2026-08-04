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

        # Payment method is a plain generic field now (see
        # migrateSentinelFieldsToGeneric()), pre-seeded on every library -- its
        # column id is dynamic ("field-<id>"), not the fixed "payment_method" this
        # test used to assume.
        persisted0 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        payment_field_id = next(f['id'] for f in persisted0['fields'] if f['name'] == 'Payment method')
        col_id = f'field-{payment_field_id}'

        # Toggle Payment method ON, tags OFF
        await page.click('#columns-btn')
        await page.wait_for_timeout(150)
        await page.check(f'#col-toggle-{col_id}')
        await page.wait_for_timeout(150)
        await page.uncheck('#col-toggle-tags')
        await page.wait_for_timeout(150)

        # Simulate closing and reopening the SAME library folder (same __TEST_ROOT handle,
        # since it's a real in-memory fake filesystem the "settings" are actually persisted to)
        await page.click('#reload-btn')
        await page.wait_for_timeout(400)

        payment_visible = await page.locator(f'th[data-field="{col_id}"]').is_visible()
        tags_visible = await page.locator('th[data-field="tags"]').is_visible()
        print("Payment method column visible after reopen (should be True):", payment_visible)
        print("tags column visible after reopen (should be False):", tags_visible)

        # also check the columns menu checkboxes themselves reflect restored state
        await page.click('#columns-btn')
        await page.wait_for_timeout(150)
        payment_checked = await page.locator(f'#col-toggle-{col_id}').is_checked()
        tags_checked = await page.locator('#col-toggle-tags').is_checked()
        print("Payment method checkbox checked:", payment_checked)
        print("tags checkbox checked (should be False):", tags_checked)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
