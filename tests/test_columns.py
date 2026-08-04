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
        await page.wait_for_timeout(200)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('coldoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 coldoc")
        await page.set_input_files('#file-input', 'coldoc.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Column Test Doc')
        await page.fill('#f-category', 'TestCat')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # Payment method is a plain generic field now (see
        # migrateSentinelFieldsToGeneric()), pre-seeded with show_as_column=1/
        # autocomplete=1 on every library -- its column/filter id is dynamic
        # ("field-<id>"), not the fixed "payment_method" this test used to assume.
        persisted0 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        payment_field_id = next(f['id'] for f in persisted0['fields'] if f['name'] == 'Payment method')
        col_id = f'field-{payment_field_id}'

        # Default state: Payment method column and filter should be HIDDEN
        # (dynamicColumnDefs() gives every show_as_column field defaultVisible: false)
        payment_th_visible = await page.locator(f'th[data-field="{col_id}"]').is_visible()
        payment_filter_visible = await page.locator(f'span[data-field="{col_id}"]').count() > 0 and await page.locator(f'span[data-field="{col_id}"]').is_visible()
        category_th_visible = await page.locator('th[data-field="category"]').is_visible()
        print("Payment method column visible by default (should be False):", payment_th_visible)
        print("Payment method filter visible by default (should be False):", payment_filter_visible)
        print("category column visible by default (should be True):", category_th_visible)

        # Open columns menu, toggle Payment method ON, Category OFF
        await page.click('#columns-btn')
        await page.wait_for_timeout(150)
        menu_visible = await page.locator('#columns-menu').is_visible()
        print("columns menu opens:", menu_visible)

        await page.check(f'#col-toggle-{col_id}')
        await page.wait_for_timeout(150)
        await page.uncheck('#col-toggle-category')
        await page.wait_for_timeout(150)

        payment_th_visible2 = await page.locator(f'th[data-field="{col_id}"]').is_visible()
        payment_filter_visible2 = await page.locator(f'span[data-field="{col_id}"]').is_visible()
        category_th_visible2 = await page.locator('th[data-field="category"]').is_visible()
        print("Payment method column visible after toggle ON:", payment_th_visible2)
        print("Payment method filter visible after toggle ON:", payment_filter_visible2)
        print("category column visible after toggle OFF:", category_th_visible2)

        # check payment filter dropdown exists and works
        payment_options = await page.locator(f'#dyn-filter-{col_id} option').all_inner_texts()
        print("payment filter options:", payment_options)

        # Verify persisted to settings table
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("persisted settings table:", persisted['settings'])

        # Close menu by clicking outside, then reopen library fresh (simulate reload) to verify persistence
        await page.click('body', position={'x': 10, 'y': 10})
        await page.wait_for_timeout(100)
        menu_closed = not await page.locator('#columns-menu').is_visible()
        print("menu closes on outside click:", menu_closed)

        print("JS ERRORS:", errors)
        await browser.close()

        # Second browser session: reopen the SAME persisted library and verify settings survive
        browser2 = await async_playwright().start()

asyncio.run(main())
