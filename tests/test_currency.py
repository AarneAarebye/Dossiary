import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Currency needs its own document_type_fields entry now, same as any other generic
# field (see migrateSentinelFieldsToGeneric()'s note) -- it no longer rides along
# with Amount implicitly. Only the table/detail-view *display* stays paired.
TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Amount", "position": 0},
    {"document_type": "Invoice", "field_name": "Currency", "position": 1},
    {"document_type": "Certificate", "field_name": "People", "position": 0},
]

def get_field_value(persisted, doc_id, field_name):
    field = next((f for f in persisted['fields'] if f['name'] == field_name), None)
    if not field:
        return None
    row = next((v for v in persisted['document_field_values'] if v['document_id'] == doc_id and v['field_id'] == field['id']), None)
    return row['value'] if row else None

CUR_INPUT = '[data-dynamic-field="Currency"] input'
CUR_CLEAR = '[data-dynamic-field="Currency"] .clear-btn'
CUR_HINT = '[data-dynamic-field="Currency"] .field-guess-hint'
AMT_INPUT = '[data-dynamic-field="Amount"] input'

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

        # === Currency renders alongside Amount for a type that configures both ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        currency_count_none = await page.locator(CUR_INPUT).count()
        print("currency input present with no type selected (should be 0):", currency_count_none)

        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        currency_count_invoice = await page.locator(CUR_INPUT).count()
        print("currency input present for Invoice type (should be 1):", currency_count_invoice)

        # === No default_currency configured yet -- no guess, plain blank field ===
        currency_value_no_default = await page.locator(CUR_INPUT).input_value()
        currency_is_guess_no_default = 'field-guess' in (await page.locator(CUR_INPUT).get_attribute('class') or '')
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
        currency_prefill_value = await page.locator(CUR_INPUT).input_value()
        currency_prefill_is_guess = 'field-guess' in (await page.locator(CUR_INPUT).get_attribute('class') or '')
        hint_visible = await page.locator(CUR_HINT).is_visible()
        print("currency pre-filled from default_currency setting:", currency_prefill_value)
        print("currency flagged as a guess:", currency_prefill_is_guess)
        print("guess hint visible:", hint_visible)

        # Touching the field (typing) clears the guess flag, same as Date's pattern.
        await page.locator(CUR_INPUT).type('X')
        guess_cleared = 'field-guess' in (await page.locator(CUR_INPUT).get_attribute('class') or '')
        hint_hidden_after_touch = await page.locator(CUR_HINT).is_visible()
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
        await page.fill(AMT_INPUT, '75.00')
        await page.fill(CUR_INPUT, 'EUR')
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
        print("saved amount:", get_field_value(persisted, doc1['id'], 'Amount'))
        print("saved currency:", get_field_value(persisted, doc1['id'], 'Currency'))

        # === Table and detail view show amount + currency together ===
        table_amount_cell = await page.locator('tr[data-id="1"] td.amount').inner_text()
        print("table amount cell:", table_amount_cell)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        panel_text = await page.locator('#detail-panel-body').inner_text()
        print("detail view shows '75.00 EUR':", '75.00 EUR' in panel_text)

        # === Sidecar text includes the currency ===
        sidecar_text = await page.evaluate("""
            (async () => {
                const files = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await files.getFileHandle('1_Currency Doc.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        # Amount is stored as raw text now (whatever was typed, "75.00"), not a
        # parsed JS number the way documents.amount used to be -- so the sidecar
        # shows exactly what was typed, no more/less precision than that.
        print("sidecar mentions 'Amount: 75.00 EUR':", 'Amount: 75.00 EUR' in sidecar_text)

        # === Edit: change currency via clear button + retype ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        currency_prefill = await page.locator(CUR_INPUT).input_value()
        print("edit form currency pre-filled:", currency_prefill)
        await page.click(CUR_CLEAR)
        currency_after_clear = await page.locator(CUR_INPUT).input_value()
        print("currency cleared via clear button:", currency_after_clear == '')
        await page.fill(CUR_INPUT, 'USD')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("currency updated to USD:", get_field_value(persisted2, doc1['id'], 'Currency'))
        # saveEditedDocument() now closes the edit modal explicitly on success and
        # updates the (already-open) panel in place -- no separate close click needed.

        # === CRITICAL: reclassifying to a type without Amount/Currency configured
        # doesn't remove either field outright while it still holds real data -- each
        # independently becomes "orphaned" (per CLAUDE.md: shown, marked, still
        # editable) rather than silently disappearing. Amount and Currency are two
        # separate generic fields now, so this is checked for each independently
        # (only their table/detail-view *display* stays paired). ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-type', 'Certificate')
        await page.locator('#e-type').blur()
        await page.wait_for_timeout(150)
        amount_orphaned = await page.locator('[data-dynamic-field="Amount"].field-orphaned').count()
        currency_orphaned = await page.locator('[data-dynamic-field="Currency"].field-orphaned').count()
        currency_still_editable = await page.locator(CUR_INPUT).input_value()
        print("Amount marked orphaned after reclassify to Certificate:", amount_orphaned == 1)
        print("Currency marked orphaned after reclassify to Certificate:", currency_orphaned == 1)
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
        print("amount PRESERVED after reclassify+save (should still be 75.0):", get_field_value(persisted3, doc1_after['id'], 'Amount'))
        print("currency PRESERVED after reclassify+save (should still be USD):", get_field_value(persisted3, doc1_after['id'], 'Currency'))

        # Reclassify back to Invoice -- the preserved value should reappear in the form.
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-type', 'Invoice')
        await page.locator('#e-type').blur()
        await page.wait_for_timeout(150)
        currency_reappeared = await page.locator(CUR_INPUT).input_value()
        no_longer_orphaned = await page.locator('[data-dynamic-field="Currency"].field-orphaned').count()
        print("currency reappears after reclassifying back to Invoice:", currency_reappeared)
        print("no longer marked orphaned once Invoice is selected again:", no_longer_orphaned == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
