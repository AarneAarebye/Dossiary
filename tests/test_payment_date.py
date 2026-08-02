import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

FIELD_ROWS = [{"id": 1, "name": "Payment Date", "type": "date"}]
TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Payment Date", "position": 0},
    {"document_type": "Invoice", "field_name": "Payment method", "position": 1},
    {"document_type": "Invoice", "field_name": "Amount", "position": 2},
]

# Payment method/Amount are plain generic fields now (see
# migrateSentinelFieldsToGeneric()) -- their values live in document_field_values,
# joined against `fields` by name, not documents.amount/payment_method directly.
def get_field_value(persisted, doc_id, field_name):
    field = next((f for f in persisted['fields'] if f['name'] == field_name), None)
    if not field:
        return None
    row = next((v for v in persisted['document_field_values'] if v['document_id'] == doc_id and v['field_id'] == field['id']), None)
    return row['value'] if row else None

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, {json.dumps(FIELD_ROWS)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # Capture with Payment Date + Payment method + Amount all showing together
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)

        pd_type = await page.locator('#f-field-1').get_attribute('type')
        print("Payment Date input type:", pd_type)
        order = await page.evaluate("Array.from(document.getElementById('dynamic-fields-f').children).map(el => el.dataset.dynamicField)")
        # Currency shows up too even though this seed's TYPE_FIELD_ROWS never
        # mentions it: migrateSentinelFieldsToGeneric() treats any pre-existing
        # "Amount" document_type_fields row (real library or, as here, a synthetic
        # seed shaped like one) as needing a Currency row added alongside it, to
        # preserve the old implicit "Currency always rides along with Amount"
        # behavior for libraries that already had Amount configured before this field
        # existed independently.
        print("Field order in form (should be Payment Date, Payment method, Amount, Currency):", order)

        await page.fill('#f-field-1', '2024-03-15')
        await page.fill('[data-dynamic-field="Payment method"] input', 'Credit Card')
        await page.fill('[data-dynamic-field="Amount"] input', '89.00')
        await page.fill('#f-title', 'Payment Date Test')
        with open('pdtest.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 pdtest")
        await page.set_input_files('#file-input', 'pdtest.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        dfv = persisted['document_field_values']
        pd_value = next((r['value'] for r in dfv if r['field_id'] == 1), None)
        print("saved Payment Date value:", pd_value)
        print("saved amount:", get_field_value(persisted, persisted['documents'][0]['id'], 'Amount'))
        print("saved payment_method:", get_field_value(persisted, persisted['documents'][0]['id'], 'Payment method'))

        # Detail view: formatted date, not raw
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        modal_text = await page.locator('.modal').inner_text()
        print("modal shows Payment Date label:", 'Payment Date' in modal_text)
        print("modal shows formatted date (not raw ISO):", '2024' in modal_text and 'T00:00' not in modal_text)

        # Edit: pre-fill check
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        pd_prefill = await page.locator('#e-field-1').input_value()
        print("edit form Payment Date pre-filled:", pd_prefill)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
