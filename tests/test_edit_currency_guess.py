import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Covers the Edit-form Currency guess: unlike every other field, Currency is allowed
# to guess in Edit too, but only when the document has a real, non-zero Amount and no
# Currency saved -- e.g. a document captured before a default currency was ever
# configured. See CLAUDE.md's renderGenericFieldHtml() note for the full rationale.
TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Amount", "position": 0},
    {"document_type": "Invoice", "field_name": "Currency", "position": 1},
]

def get_field_value(persisted, doc_id, field_name):
    field = next((f for f in persisted['fields'] if f['name'] == field_name), None)
    if not field:
        return None
    row = next((v for v in persisted['document_field_values'] if v['document_id'] == doc_id and v['field_id'] == field['id']), None)
    return row['value'] if row else None

CUR_INPUT = '[data-dynamic-field="Currency"] input'
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

        # === Capture three documents with NO default_currency configured yet, so none
        # of them get a Currency value -- mirrors documents captured before a default
        # currency ever existed for this library. ===
        async def capture(title, amount_value, filename):
            await page.click('#add-btn')
            await page.wait_for_timeout(100)
            await page.fill('#f-type', 'Invoice')
            await page.locator('#f-type').blur()
            await page.wait_for_timeout(150)
            if amount_value is not None:
                await page.fill(AMT_INPUT, amount_value)
            await page.fill('#f-title', title)
            with open(filename, 'wb') as f:
                f.write(b"%PDF-1.4 guesstest")
            await page.set_input_files('#file-input', filename)
            await page.wait_for_timeout(100)
            await page.click('#save-doc-btn')
            await page.wait_for_timeout(300)

        await capture('Has Amount', '120.00', 'guessdoc1.pdf')   # doc 1: real, non-zero amount
        await capture('No Amount', None, 'guessdoc2.pdf')        # doc 2: amount left blank entirely
        await capture('Zero Amount', '0', 'guessdoc3.pdf')       # doc 3: amount explicitly typed as 0

        persisted0 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("doc1 saved amount (should be 120.00):", get_field_value(persisted0, 1, 'Amount'))
        print("doc1 saved currency (should be None, no default configured yet):", get_field_value(persisted0, 1, 'Currency'))
        print("doc2 saved amount (should be None, left blank):", get_field_value(persisted0, 2, 'Amount'))
        print("doc3 saved amount (should be '0'):", get_field_value(persisted0, 3, 'Amount'))

        # === Now configure a default_currency, same as test_currency.py's pattern ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(150)
        await page.fill('#fs-default-currency', 'EUR')
        await page.locator('#fs-default-currency').blur()
        await page.wait_for_timeout(150)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        # === Doc 1 (real non-zero Amount, no Currency): Edit should now guess EUR ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        doc1_cur_value = await page.locator(CUR_INPUT).input_value()
        doc1_is_guess = 'field-guess' in (await page.locator(CUR_INPUT).get_attribute('class') or '')
        doc1_hint_visible = await page.locator(CUR_HINT).is_visible()
        print("doc1 (has amount) edit Currency pre-filled with default:", doc1_cur_value)
        print("doc1 (has amount) edit Currency flagged as a guess:", doc1_is_guess)
        print("doc1 (has amount) edit guess hint visible:", doc1_hint_visible)

        # Touching it clears the guess flag, same dismiss-on-touch behavior every
        # other guess field already has.
        await page.locator(CUR_INPUT).type('X')
        doc1_guess_cleared = 'field-guess' not in (await page.locator(CUR_INPUT).get_attribute('class') or '')
        doc1_hint_hidden_after_touch = not await page.locator(CUR_HINT).is_visible()
        print("doc1 guess flag cleared after typing:", doc1_guess_cleared)
        print("doc1 guess hint hidden after typing:", doc1_hint_hidden_after_touch)
        await page.click('#modal-close-btn')  # discard this edit (Cancel), doc1 currency stays unset
        await page.wait_for_timeout(150)

        # === Re-open doc1's edit form fresh and accept the guess by saving untouched,
        # confirming it becomes a real persisted value exactly like the capture-time
        # guess already does. ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted1 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("doc1 currency persisted after accepting the edit-time guess:", get_field_value(persisted1, 1, 'Currency'))
        # Save already closed the edit modal on success (see saveEditedDocument()'s
        # explicit closeModal() call) -- no separate close click needed here.

        # === Re-opening doc1's edit again: Currency now has a REAL saved value, so it
        # must NOT be re-flagged as a guess (a saved value is truth, not a guess). ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        doc1_reopen_value = await page.locator(CUR_INPUT).input_value()
        doc1_reopen_is_guess = 'field-guess' in (await page.locator(CUR_INPUT).get_attribute('class') or '')
        print("doc1 currency on reopen (should be EUR, real value):", doc1_reopen_value)
        print("doc1 currency NOT flagged as a guess once it's a real saved value:", not doc1_reopen_is_guess)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Doc 2 (no Amount at all): Edit must NOT guess -- a blank Currency here is
        # still the document's real, unaltered state. ===
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        doc2_cur_value = await page.locator(CUR_INPUT).input_value()
        doc2_is_guess = 'field-guess' in (await page.locator(CUR_INPUT).get_attribute('class') or '')
        print("doc2 (no amount) edit Currency stays blank:", doc2_cur_value == '')
        print("doc2 (no amount) edit Currency NOT flagged as a guess:", not doc2_is_guess)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Doc 3 (Amount explicitly '0'): same as no amount at all, per
        # formatAmount()'s own "amount === 0 means nothing to show" treatment --
        # must NOT guess either. ===
        await page.click('tr[data-id="3"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        doc3_cur_value = await page.locator(CUR_INPUT).input_value()
        doc3_is_guess = 'field-guess' in (await page.locator(CUR_INPUT).get_attribute('class') or '')
        print("doc3 (zero amount) edit Currency stays blank:", doc3_cur_value == '')
        print("doc3 (zero amount) edit Currency NOT flagged as a guess:", not doc3_is_guess)

        print("JS ERRORS:", errors)
        for fn in ('guessdoc1.pdf', 'guessdoc2.pdf', 'guessdoc3.pdf'):
            if _os.path.exists(fn):
                _os.remove(fn)
        await browser.close()

asyncio.run(main())
