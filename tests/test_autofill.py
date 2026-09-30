import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Autofill from earlier documents: entering a title that matches an earlier
# document's fills the empty Document Type, Category, Subcategory, Payment
# method and Currency from the most recently imported match, as guesses.
def doc(i, title, **extra):
    d = {
        "id": i, "title": title, "category": None, "subcategory": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "import_date": "2026-03-01T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }
    d.update(extra)
    return d

SEED = {
    "documents": [
        doc(1, "Stadtwerke", category="Old category", document_type="Invoice", import_date="2025-01-01T00:00:00+00:00"),
        doc(2, "Stadtwerke", category="Home", subcategory="Utilities", document_type="Invoice", import_date="2026-02-01T00:00:00+00:00"),
        doc(3, "Deleted Shop", category="Should not be used", deleted=1),
        doc(4, "scan_20260321_0001", needs_review=1),
        doc(5, "Reviewed doc"),
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 2, "field_id": 1, "value": "Bank transfer"},
        {"document_id": 2, "field_id": 3, "value": "EUR"},
    ],
    "document_type_fields": [
        {"document_type": "Invoice", "field_name": "Payment method", "position": 0},
        {"document_type": "Invoice", "field_name": "Currency", "position": 1},
        {"document_type": "Receipt", "field_name": "Amount", "position": 0},
    ],
    "settings": [{"key": "default_document_type", "value": "Receipt"}],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        async def is_guess(sel):
            return await page.locator(sel).evaluate("e => e.classList.contains('field-guess')")

        # === Scenario 1: capture -- a known title fills the empty fields ===
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        print("Capture starts with the default type (Receipt):", await page.input_value('#f-type') == 'Receipt')
        await page.fill('#f-title', ' stadtwerke ')
        await page.dispatch_event('#f-title', 'change')
        await page.wait_for_timeout(200)
        pm = '#dynamic-fields-f [data-dynamic-field="Payment method"] input'
        cur = '#dynamic-fields-f [data-dynamic-field="Currency"] input'
        print("Type replaces the untouched default, from the most recent match:", await page.input_value('#f-type') == 'Invoice')
        print("...so the Invoice fields appear:", await page.locator(pm).count() == 1)
        print("Category and Subcategory from the most recent match, not the older one:",
              await page.input_value('#f-category') == 'Home' and await page.input_value('#f-subcategory') == 'Utilities')
        print("Payment method and Currency filled:", await page.input_value(pm) == 'Bank transfer' and await page.input_value(cur) == 'EUR')
        print("All marked as guesses:", all([await is_guess(s) for s in ['#f-type', '#f-category', '#f-subcategory', pm, cur]]))
        hints = await page.locator('.ocr-guess-hint:visible').all_inner_texts()
        print("...with a note naming the source:", len(hints) == 5 and all('Stadtwerke' in h for h in hints), hints[:1])
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 2: what the person already entered is never replaced ===
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        await page.fill('#f-category', 'My own')
        await page.fill('#f-title', 'Stadtwerke')
        await page.dispatch_event('#f-title', 'change')
        await page.wait_for_timeout(200)
        print("A category the person typed stays:", await page.input_value('#f-category') == 'My own' and not await is_guess('#f-category'))
        print("...while empty fields are still filled:", await page.input_value('#f-subcategory') == 'Utilities')
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 3: no match, or only a deleted match, fills nothing ===
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        await page.fill('#f-title', 'Deleted Shop')
        await page.dispatch_event('#f-title', 'change')
        await page.wait_for_timeout(200)
        print("A document in the Waste bin is never used as a source:", await page.input_value('#f-category') == '' and await page.input_value('#f-type') == 'Receipt')
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 4: Edit form of a review-queue document ===
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(200)
        await page.click('#doc-tbody tr[data-id="4"] td:nth-child(3)')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        await page.fill('#e-title', 'Stadtwerke')
        await page.dispatch_event('#e-title', 'change')
        await page.wait_for_timeout(200)
        epm = '#dynamic-fields-e [data-dynamic-field="Payment method"] input'
        print("Edit (review queue): renaming to a known title fills the fields:",
              await page.input_value('#e-type') == 'Invoice' and await page.input_value('#e-category') == 'Home' and await page.input_value(epm) == 'Bank transfer')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(400)
        state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        d4 = next(d for d in state['documents'] if d['id'] == 4)
        vals = {v['field_id']: v['value'] for v in state.get('document_field_values', []) if v['document_id'] == 4}
        print("Kept guesses are saved:", d4['document_type'] == 'Invoice' and d4['category'] == 'Home' and vals.get(1) == 'Bank transfer', vals)

        # === Scenario 5: no autofill when editing an already-reviewed document ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)
        await page.click('#doc-tbody tr[data-id="5"] td:nth-child(3)')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        await page.fill('#e-title', 'Stadtwerke')
        await page.dispatch_event('#e-title', 'change')
        await page.wait_for_timeout(200)
        print("Editing a reviewed document doesn't autofill:", await page.input_value('#e-category') == '')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
