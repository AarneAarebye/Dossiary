import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, base64, json
from playwright.async_api import async_playwright

# Suggested values from OCR text: a likely date, amount and currency offered
# as amber guesses in the Edit form (review-queue documents only) and after
# running OCR in the capture/Edit forms. A guess only fills an empty field or
# replaces another guess, and is cleared on first edit.
INVOICE_DE = """Stadtwerke Musterstadt
Rechnung Nr. 4711
Datum: 15.02.2026
Leistungszeitraum 01.01.2026 - 31.01.2026
Nettobetrag 61,76 EUR
Gesamtbetrag 73,50 EUR
Zahlbar bis 01.03.2026"""

def doc(i, title, **extra):
    d = {
        "id": i, "title": title, "category": None, "document_type": "Receipt",
        "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "scan-inbox", "source_legacy_id": None,
        "archived": 0, "needs_review": 1, "deleted": 0,
    }
    d.update(extra)
    return d

SEED = {
    "documents": [
        doc(1, "Utility bill", ocr_text=INVOICE_DE),
        doc(2, "Reviewed already", ocr_text=INVOICE_DE, needs_review=0),
        doc(3, "Has a date", ocr_text=INVOICE_DE, date="2026-01-10T00:00:00+00:00"),
        doc(4, "Earlier doc in euro symbols", needs_review=0),
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 3, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [{"document_id": 4, "field_id": 2, "value": "EUR"}],
    "document_type_fields": [
        {"document_type": "Receipt", "field_name": "Amount", "position": 0},
        {"document_type": "Receipt", "field_name": "Currency", "position": 1},
    ],
}

PARSER_CASES = [
    ("German invoice: first date, total amount, EUR", INVOICE_DE, {"date": "2026-02-15", "amount": "73.50", "currency": "EUR"}),
    ("Total on the line after its label, thousands separator",
     "INVOICE\nDate: 2026-03-04\nTOTAL DUE\n$1,234.56\nThank you", {"date": "2026-03-04", "amount": "1234.56", "currency": "USD"}),
    ("German thousands and decimal comma", "Summe: 1.234,56 €", {"date": None, "amount": "1234.56", "currency": "EUR"}),
    ("Month names (German)", "Berlin, den 3. März 2026\nBetrag 12,00", {"date": "2026-03-03", "amount": "12.00", "currency": None}),
    ("Month names (English, month first)", "March 12, 2026\nAmount due: £40.00", {"date": "2026-03-12", "amount": "40.00", "currency": "GBP"}),
    ("Largest of several totals wins", "Subtotal 10,00\nTotal 11,90\nTotal paid 11,90", {"date": None, "amount": "11.90", "currency": None}),
    ("No total line -> no amount guessed", "Price 9,99\nQty 2", {"date": None, "amount": None, "currency": None}),
    ("Impossible dates are skipped", "31.02.2026 then 01.03.2026", {"date": "2026-03-01", "amount": None, "currency": None}),
    ("Slash date with day > 12 is day-first", "14/03/2026", {"date": "2026-03-14", "amount": None, "currency": None}),
    ("Nothing useful", "Hello World", {"date": None, "amount": None, "currency": None}),
]

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    await page.add_init_script(open('stub_studio2.js').read())

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        # === Scenario 1: the parser, case by case ===
        for label, text, expected in PARSER_CASES:
            got = await page.evaluate("(t) => window.__DEBUG_suggestFromOcrText(t)", text)
            print(f"Parser -- {label}:", got == expected, got)
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(100)
        us = await page.evaluate("(t) => window.__DEBUG_suggestFromOcrText(t)", "03/04/2026")
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(100)
        eu = await page.evaluate("(t) => window.__DEBUG_suggestFromOcrText(t)", "03/04/2026")
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(100)
        print("Ambiguous slash date follows the UI language (en: month first, de: day first):",
              us['date'] == '2026-03-04' and eu['date'] == '2026-04-03', us['date'], eu['date'])

        # === Scenario 2: the Edit form of a review-queue document shows guesses ===
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(200)
        await page.click('#doc-tbody tr[data-id="1"] td:nth-child(3)')
        await page.wait_for_timeout(250)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        date_in = page.locator('#e-date')
        amount_in = page.locator('#dynamic-fields-e [data-dynamic-field="Amount"] input')
        currency_in = page.locator('#dynamic-fields-e [data-dynamic-field="Currency"] input')
        print("Date suggested from the text:", await date_in.input_value() == '2026-02-15')
        print("Amount suggested from the total line:", await amount_in.input_value() == '73.50')
        print("Currency suggested in the library's own style:", await currency_in.input_value() == 'EUR')
        print("All three marked as guesses:", all([await x.evaluate("e => e.classList.contains('field-guess')") for x in (date_in, amount_in, currency_in)]))
        print("...with the 'please check' note:", await page.locator('.ocr-guess-hint:visible').count() == 3)
        await date_in.fill('2026-02-16')
        await page.wait_for_timeout(100)
        print("Editing a guess clears its mark and note:", not await date_in.evaluate("e => e.classList.contains('field-guess')")
              and await page.locator('.ocr-guess-hint:visible').count() == 2)

        # === Scenario 3: changing the type rebuilds fields and re-suggests ===
        await page.fill('#e-type', 'Other')
        await page.dispatch_event('#e-type', 'change')
        await page.wait_for_timeout(150)
        await page.fill('#e-type', 'Receipt')
        await page.dispatch_event('#e-type', 'change')
        await page.wait_for_timeout(150)
        print("Guesses come back after the fields are rebuilt:", await amount_in.input_value() == '73.50')
        print("...but the date the person typed is kept:", await date_in.input_value() == '2026-02-16')

        # === Scenario 4: kept guesses are saved like typed values ===
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(400)
        state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        d1 = next(d for d in state['documents'] if d['id'] == 1)
        vals = {v['field_id']: v['value'] for v in state.get('document_field_values', []) if v['document_id'] == 1}
        print("Saved: the edited date and the kept amount/currency:", (d1.get('date') or '').startswith('2026-02-16') and vals.get(1) == '73.50' and vals.get(2) == 'EUR', d1.get('date'), vals)

        # === Scenario 5: no guesses outside the review queue, never over a real value ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)
        await page.click('#doc-tbody tr[data-id="2"] td:nth-child(3)')
        await page.wait_for_timeout(250)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        print("A reviewed document's Edit form gets no guesses:", await page.locator('#e-date').input_value() == '' and await page.locator('.ocr-guess-hint:visible').count() == 0)
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(200)
        await page.click('#doc-tbody tr[data-id="3"] td:nth-child(3)')
        await page.wait_for_timeout(250)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        print("An existing date is never replaced:", await page.locator('#e-date').input_value() == '2026-01-10'
              and not await page.locator('#e-date').evaluate("e => e.classList.contains('field-guess')"))
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)

        # === Scenario 6: capture -- running OCR replaces the "today" guess ===
        await page.evaluate(f"window.__STUB_OCR_TEXT = {json.dumps(INVOICE_DE)};")
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
        with open('ocr_suggest.png', 'wb') as fh:
            fh.write(png)
        await page.set_input_files('#file-input', 'ocr_suggest.png')
        await page.wait_for_timeout(200)
        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(500)
        print("Capture: OCR's date replaces the preset today:", await page.locator('#f-date').input_value() == '2026-02-15')
        print("...still marked as a guess, with the OCR note instead of the 'today' note:",
              await page.locator('#f-date').evaluate("e => e.classList.contains('field-guess')")
              and await page.locator('#f-date-hint').is_hidden()
              and await page.locator('.ocr-guess-hint:visible').count() >= 1)
        await page.evaluate("window.__STUB_OCR_TEXT = null;")
        _os.remove('ocr_suggest.png')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
