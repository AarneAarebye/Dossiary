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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, []);")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

        # === Unconfigured type: Amount/Payment should NOT render at all ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        amount_count_none = await page.locator('[data-dynamic-field="Amount"]').count()
        payment_count_none = await page.locator('[data-dynamic-field="Payment method"]').count()
        print("Amount present with no type selected (should be 0):", amount_count_none)
        print("Payment present with no type selected (should be 0):", payment_count_none)

        # === Certificate: configured for People only, NOT Amount/Payment ===
        await page.fill('#f-type', 'Certificate')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        amount_count_cert = await page.locator('[data-dynamic-field="Amount"]').count()
        payment_count_cert = await page.locator('[data-dynamic-field="Payment method"]').count()
        people_count_cert = await page.locator('[data-dynamic-field="People"]').count()
        print("--- Type = Certificate (People only) ---")
        print("Amount present (should be 0):", amount_count_cert)
        print("Payment present (should be 0):", payment_count_cert)
        print("People present (should be 1):", people_count_cert)

        # === Invoice: configured for Payment method + Amount ===
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        amount_input_type = await page.locator('[data-dynamic-field="Amount"] input').get_attribute('type')
        payment_input_type = await page.locator('[data-dynamic-field="Payment method"] input').get_attribute('type')
        print("--- Type = Invoice ---")
        print("Amount input type attribute:", amount_input_type)
        print("Payment method input type attribute:", payment_input_type)

        await page.fill('[data-dynamic-field="Amount"] input', '150.75')
        await page.fill('[data-dynamic-field="Payment method"] input', 'Bank Transfer')
        await page.fill('#f-title', 'Invoice Doc')
        with open('apdoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 apdoc")
        await page.set_input_files('#file-input', 'apdoc.pdf')
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
        doc1 = persisted['documents'][0]
        print("saved amount:", get_field_value(persisted, doc1['id'], 'Amount'))
        print("saved payment_method:", get_field_value(persisted, doc1['id'], 'Payment method'))

        # === CRITICAL: editing and reclassifying to a type WITHOUT Amount/Payment
        # should PRESERVE the existing values, not clear them ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        amount_prefill = await page.locator('[data-dynamic-field="Amount"] input').input_value()
        print("edit form amount pre-filled:", amount_prefill)

        # reclassify to Certificate (no Amount/Payment configured)
        await page.fill('#e-type', 'Certificate')
        await page.locator('#e-type').blur()
        await page.wait_for_timeout(150)
        # NOT actually removed from the DOM: since this document has a real, non-zero
        # amount, applyDynamicFieldsForType()'s orphaned-field handling (isEdit=true)
        # re-appends it marked .field-orphaned instead of dropping it -- see
        # test_orphaned_fields.py for that behavior in detail. It stays present and
        # editable here specifically so the value below isn't just preserved blindly
        # but actually visible for review.
        amount_block_orphaned = await page.locator('[data-dynamic-field="Amount"].field-orphaned').count()
        print("Amount field marked orphaned (not removed) after reclassify:", amount_block_orphaned == 1)

        # Save WITHOUT amount/payment fields present -- must NOT wipe the stored values
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1_after = persisted2['documents'][0]
        print("amount PRESERVED after reclassify+save (should still be 150.75):", get_field_value(persisted2, doc1_after['id'], 'Amount'))
        print("payment_method PRESERVED after reclassify+save (should still be Bank Transfer):", get_field_value(persisted2, doc1_after['id'], 'Payment method'))
        print("document_type correctly changed:", doc1_after['document_type'])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
