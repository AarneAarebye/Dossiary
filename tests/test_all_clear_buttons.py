import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "People", "position": 0},
    {"document_type": "Invoice", "field_name": "Payment method", "position": 1},
    {"document_type": "Invoice", "field_name": "Amount", "position": 2},
]

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, []);")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Capture form: fill every field, then clear each one ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('#f-category', 'Medical')
        await page.fill('#f-subcategory', 'Dentist')
        await page.fill('#f-payment', 'Credit Card')
        await page.fill('#f-amount', '42.50')
        await page.fill('#f-tags', 'urgent, receipt')
        await page.fill('#f-person', 'Arne, Jana')

        fields = ['category', 'subcategory', 'payment', 'amount', 'tags', 'person']
        for field in fields:
            btn_id = f'#f-{field}-clear'
            visible = await page.locator(btn_id).is_visible()
            print(f"f-{field}-clear visible before clearing:", visible)

        for field in fields:
            await page.click(f'#f-{field}-clear')
            await page.wait_for_timeout(80)
            value = await page.locator(f'#f-{field}').input_value()
            print(f"f-{field} value after clear (should be empty):", repr(value))

        print("JS ERRORS so far:", errors)

        # === Edit form: same check on a real saved document ===
        with open('clearall.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 clearall")
        await page.set_input_files('#file-input', 'clearall.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Clear All Test')
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('#f-category', 'Medical')
        await page.fill('#f-amount', '99.99')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)

        edit_fields = ['category', 'subcategory', 'payment', 'amount', 'tags']
        for field in edit_fields:
            btn_id = f'#e-{field}-clear'
            visible = await page.locator(btn_id).is_visible()
            print(f"e-{field}-clear visible:", visible)
            await page.click(btn_id)
            await page.wait_for_timeout(80)
            value = await page.locator(f'#e-{field}').input_value()
            print(f"e-{field} value after clear (should be empty):", repr(value))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
