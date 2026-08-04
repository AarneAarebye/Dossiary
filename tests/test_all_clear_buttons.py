import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "People", "position": 0},
    {"document_type": "Invoice", "field_name": "Payment method", "position": 1},
    {"document_type": "Invoice", "field_name": "Amount", "position": 2},
]

# Payment method/Amount are plain generic fields now (see
# migrateSentinelFieldsToGeneric()), so they no longer have fixed #f-payment/
# #f-amount ids -- located by their data-dynamic-field attribute instead, same as
# any other custom field.
FIELDS = [
    ('category', '#f-category', '#f-category-clear'),
    ('subcategory', '#f-subcategory', '#f-subcategory-clear'),
    ('payment', '[data-dynamic-field="Payment method"] input', '[data-dynamic-field="Payment method"] .clear-btn'),
    ('amount', '[data-dynamic-field="Amount"] input', '[data-dynamic-field="Amount"] .clear-btn'),
    ('tags', '#f-tags', '#f-tags-clear'),
    ('person', '#f-person', '#f-person-clear'),
]
EDIT_FIELDS = [
    ('category', '#e-category', '#e-category-clear'),
    ('subcategory', '#e-subcategory', '#e-subcategory-clear'),
    ('payment', '[data-dynamic-field="Payment method"] input', '[data-dynamic-field="Payment method"] .clear-btn'),
    ('amount', '[data-dynamic-field="Amount"] input', '[data-dynamic-field="Amount"] .clear-btn'),
    ('tags', '#e-tags', '#e-tags-clear'),
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
        await page.fill('[data-dynamic-field="Payment method"] input', 'Credit Card')
        await page.fill('[data-dynamic-field="Amount"] input', '42.50')
        await page.fill('#f-tags', 'urgent, receipt')
        await page.fill('#f-person', 'Arne, Jana')

        for name, input_sel, clear_sel in FIELDS:
            visible = await page.locator(clear_sel).is_visible()
            print(f"f-{name}-clear visible before clearing:", visible)

        for name, input_sel, clear_sel in FIELDS:
            await page.click(clear_sel)
            await page.wait_for_timeout(80)
            value = await page.locator(input_sel).input_value()
            print(f"f-{name} value after clear (should be empty):", repr(value))

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
        await page.fill('[data-dynamic-field="Amount"] input', '99.99')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)

        for name, input_sel, clear_sel in EDIT_FIELDS:
            visible = await page.locator(clear_sel).is_visible()
            print(f"e-{name}-clear visible:", visible)
            await page.click(clear_sel)
            await page.wait_for_timeout(80)
            value = await page.locator(input_sel).input_value()
            print(f"e-{name} value after clear (should be empty):", repr(value))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
