import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# An "old-shape" library, exactly what a library predating
# migrateSentinelFieldsToGeneric() looks like: documents.payment_method/amount/
# currency populated directly (as migrate_to_new_library.py itself still does, and
# as dossiary.html itself used to before this app-side migration existed),
# no `fields` rows for any of the three, and Amount configured for the type but
# Currency not (Currency never had an independent document_type_fields entry).
SEED = {
    "documents": [
        {
            "id": 1, "title": "Old Invoice", "category": "Bills", "subcategory": None,
            "document_type": "Invoice", "payment_method": "Visa", "amount": 50.5, "currency": "EUR",
            "date": "2020-01-15", "import_date": "2020-01-15T09:00:00Z", "notes": None,
            "ocr_text": None, "ocr_language": None, "file_path": "files/1_old.pdf",
            "original_file_path": None, "created_at": "2020-01-15T09:00:00Z",
            "source": "migrated", "source_legacy_id": 42, "thumbnail_path": None,
        },
    ],
    "document_type_fields": [
        {"document_type": "Invoice", "field_name": "Amount", "position": 0},
    ],
    "fields": [],
    "document_field_values": [],
}

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)

        # === fields table backfilled with all three, correct types/capabilities ===
        by_name = {f['name']: f for f in persisted['fields']}
        print("fields created:", sorted(by_name.keys()))
        print("Payment method: type=text, show_as_column=1, autocomplete=1:",
              by_name.get('Payment method', {}).get('type'), by_name.get('Payment method', {}).get('show_as_column'), by_name.get('Payment method', {}).get('autocomplete'))
        print("Amount: type=number, show_as_column=0:", by_name.get('Amount', {}).get('type'), by_name.get('Amount', {}).get('show_as_column'))
        print("Currency: type=text, show_as_column=0:", by_name.get('Currency', {}).get('type'), by_name.get('Currency', {}).get('show_as_column'))

        # === document_field_values backfilled from the old columns ===
        def value_for(field_name):
            field = by_name[field_name]
            row = next((v for v in persisted['document_field_values'] if v['document_id'] == 1 and v['field_id'] == field['id']), None)
            return row['value'] if row else None
        print("backfilled Payment method value:", value_for('Payment method'))
        print("backfilled Amount value:", value_for('Amount'))
        print("backfilled Currency value:", value_for('Currency'))

        # === document_type_fields gets a Currency row wherever Amount was configured,
        # preserving the old implicit "Currency always shows with Amount" behavior ===
        invoice_fields = sorted(r['field_name'] for r in persisted['document_type_fields'] if r['document_type'] == 'Invoice')
        print("Invoice's document_type_fields now includes Currency alongside Amount:", invoice_fields)

        # === Old documents.payment_method/amount/currency columns are left in place,
        # untouched -- vestigial, but not destroyed ===
        old_doc = persisted['documents'][0]
        print("old payment_method column still present (vestigial):", old_doc.get('payment_method'))
        print("old amount column still present (vestigial):", old_doc.get('amount'))

        # === Table shows the backfilled data correctly, combined ===
        table_amount_cell = await page.locator('tr[data-id="1"] td.amount').inner_text()
        print("table amount cell shows backfilled data:", table_amount_cell)

        # === Edit form shows Payment method (now show_as_column/autocomplete, but
        # still rendered as an ordinary dynamic field) with its backfilled value ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        payment_prefill = await page.locator('[data-dynamic-field="Payment method"] input').input_value()
        print("edit form Payment method pre-filled from backfilled data:", payment_prefill)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Idempotency: reopening the same (now-migrated) library doesn't create
        # duplicate fields or duplicate document_field_values rows ===
        await page.click('#reload-btn')
        await page.wait_for_timeout(400)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("fields count stable after reopen (should be 3):", len(persisted2['fields']))
        print("document_field_values count stable after reopen (should be 3):", len(persisted2['document_field_values']))
        print("document_type_fields count stable after reopen (should be 2):", len(persisted2['document_type_fields']))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
