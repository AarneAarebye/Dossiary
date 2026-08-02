import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Amount", "position": 0},
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

        # === Currency renders alongside Amount, sharing its per-type visibility ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        currency_count_none = await page.locator('#f-currency').count()
        print("currency input present with no type selected (should be 0):", currency_count_none)

        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        currency_count_invoice = await page.locator('#f-currency').count()
        print("currency input present for Invoice type (should be 1):", currency_count_invoice)

        # === No default_currency configured yet -- no guess, plain blank field ===
        currency_value_no_default = await page.locator('#f-currency').input_value()
        currency_is_guess_no_default = 'field-guess' in (await page.locator('#f-currency').get_attribute('class') or '')
        print("currency blank with no default_currency configured:", currency_value_no_default == '')
        print("currency NOT flagged as a guess with no default_currency configured:", not currency_is_guess_no_default)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Configure a default_currency via Field Settings, mirroring
        # default_document_type's own settings-backed pattern ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(150)
        await page.fill('#fs-default-currency', 'USD')
        await page.locator('#fs-default-currency').blur()
        await page.wait_for_timeout(150)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        settings_after = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).settings;
            })()
        """)
        default_currency_setting = next((s['value'] for s in settings_after if s['key'] == 'default_currency'), None)
        print("default_currency persisted to settings:", default_currency_setting)

        # === Now a fresh capture pre-fills Currency as a dismissible guess ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        currency_prefill_value = await page.locator('#f-currency').input_value()
        currency_prefill_is_guess = 'field-guess' in (await page.locator('#f-currency').get_attribute('class') or '')
        hint_visible = await page.locator('#f-currency-hint').is_visible()
        print("currency pre-filled from default_currency setting:", currency_prefill_value)
        print("currency flagged as a guess:", currency_prefill_is_guess)
        print("guess hint visible:", hint_visible)

        # Touching the field (typing) clears the guess flag, same as Date's pattern.
        await page.locator('#f-currency').type('X')
        guess_cleared = 'field-guess' in (await page.locator('#f-currency').get_attribute('class') or '')
        hint_hidden_after_touch = await page.locator('#f-currency-hint').is_visible()
        print("guess flag cleared after typing:", not guess_cleared)
        print("hint hidden after typing:", not hint_hidden_after_touch)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Back to the main capture-and-save flow for the rest of this test ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('#f-amount', '75.00')
        await page.fill('#f-currency', 'EUR')
        await page.fill('#f-title', 'Currency Doc')
        with open('curdoc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 curdoc")
        await page.set_input_files('#file-input', 'curdoc.pdf')
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
        print("saved amount:", doc1['amount'])
        print("saved currency:", doc1['currency'])

        # === Table and detail view show amount + currency together ===
        table_amount_cell = await page.locator('tr[data-id="1"] td.amount').inner_text()
        print("table amount cell:", table_amount_cell)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        modal_text = await page.locator('.modal').inner_text()
        print("detail view shows '75.00 EUR':", '75.00 EUR' in modal_text)
        await page.click('#modal-close-btn')

        # === Sidecar text includes the currency ===
        sidecar_text = await page.evaluate("""
            (async () => {
                const files = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await files.getFileHandle('1_curdoc.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        print("sidecar mentions 'Amount: 75 EUR':", 'Amount: 75 EUR' in sidecar_text)

        # === Edit: change currency via clear button + retype ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        currency_prefill = await page.locator('#e-currency').input_value()
        print("edit form currency pre-filled:", currency_prefill)
        await page.click('#e-currency-clear')
        currency_after_clear = await page.locator('#e-currency').input_value()
        print("currency cleared via clear button:", currency_after_clear == '')
        await page.fill('#e-currency', 'USD')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("currency updated to USD:", persisted2['documents'][0]['currency'])
        # saveEditedDocument() ends by opening the detail view, not closing the modal.
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === CRITICAL: reclassifying to a type without Amount configured doesn't
        # remove the field outright while it still holds real data -- it becomes
        # "orphaned" (per CLAUDE.md: shown, marked, still editable) rather than
        # silently disappearing. This is the same orphaned-field treatment Amount
        # already had; Currency rides along with it since they share one block. ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-type', 'Certificate')
        await page.locator('#e-type').blur()
        await page.wait_for_timeout(150)
        amount_block_orphaned = await page.locator('[data-dynamic-field="Amount"].field-orphaned').count()
        currency_still_editable = await page.locator('#e-currency').input_value()
        print("Amount+Currency block marked orphaned after reclassify to Certificate:", amount_block_orphaned == 1)
        print("currency still editable in the orphaned block:", currency_still_editable)
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted3 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1_after = persisted3['documents'][0]
        print("amount PRESERVED after reclassify+save (should still be 75.0):", doc1_after['amount'])
        print("currency PRESERVED after reclassify+save (should still be USD):", doc1_after['currency'])
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # Reclassify back to Invoice -- the preserved value should reappear in the form.
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-type', 'Invoice')
        await page.locator('#e-type').blur()
        await page.wait_for_timeout(150)
        currency_reappeared = await page.locator('#e-currency').input_value()
        no_longer_orphaned = await page.locator('[data-dynamic-field="Amount"].field-orphaned').count()
        print("currency reappears after reclassifying back to Invoice:", currency_reappeared)
        print("no longer marked orphaned once Invoice is selected again:", no_longer_orphaned == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
