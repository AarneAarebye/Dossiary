import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Payment method", "position": 0},
    {"document_type": "Invoice", "field_name": "Amount", "position": 1},
    {"document_type": "Certificate", "field_name": "People", "position": 0},
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
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

        # === Doc 1: Certificate type, no amount/payment at all ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Certificate')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Certificate Doc')
        with open('nopay.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 nopay")
        await page.set_input_files('#file-input', 'nopay.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        modal_text1 = await page.locator('#detail-panel-body').inner_text()
        print("--- Doc without amount/payment ---")
        print("shows Payment b-tag (should be False):", '<b>Payment</b>' in modal_text1 or 'Payment ' in modal_text1)
        print("shows 'Amount' label (should be False):", 'Amount' in modal_text1)
        print("shows 'Date' label (should be True, always shown):", 'Date' in modal_text1)

        # === Doc 2: Invoice type, WITH amount/payment filled in ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'With Payment Doc')
        await page.fill('[data-dynamic-field="Payment method"] input', 'PayPal')
        await page.fill('[data-dynamic-field="Amount"] input', '75.00')
        with open('haspay.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 haspay")
        await page.set_input_files('#file-input', 'haspay.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        modal_text2 = await page.locator('#detail-panel-body').inner_text()
        print("--- Doc with amount/payment ---")
        print("shows 'Payment' label (should be True):", 'Payment' in modal_text2)
        print("shows 'PayPal' value:", 'PayPal' in modal_text2)
        print("shows 'Amount' label (should be True):", 'Amount' in modal_text2)
        print("shows '75.00' value:", '75.00' in modal_text2)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
