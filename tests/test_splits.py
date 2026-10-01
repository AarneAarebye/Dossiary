import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Line-item splits: in the Edit form a document's Amount can be split across
# categories (amount + optional note per line), the rest staying with its
# own category. Saved lines show in the detail panel and the sidecar; a
# Category breakdown in Reports counts each line under its category; the
# Category filter and Smart Collection category rules see the lines; a
# category rename follows into them; lines that don't add up are refused.
def doc(i, title, category, amount):
    return {"id": i, "title": title, "category": category, "document_type": "Receipt", "date": f"2026-03-0{i}",
            "import_date": f"2026-03-0{i}T10:00:00Z", "created_at": f"2026-03-0{i}T10:00:00Z",
            "file_path": f"files/{i}_doc.pdf", "source": "captured", "archived": 0, "needs_review": 0, "deleted": 0}
SEED = {
    "documents": [doc(1, "Supermarket", "Groceries", 30), doc(2, "Pharmacy", "Health", 10)],
    "fields": [
        {"id": 1, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Currency", "type": "text", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_type_fields": [
        {"document_type": "Receipt", "field_name": "Amount", "position": 0},
        {"document_type": "Receipt", "field_name": "Currency", "position": 1},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 1, "value": "30.00"}, {"document_id": 1, "field_id": 2, "value": "EUR"},
        {"document_id": 2, "field_id": 1, "value": "10.00"}, {"document_id": 2, "field_id": 2, "value": "EUR"},
    ],
    "collections": [
        {"id": 1, "name": "Household things", "kind": "smart", "criteria": json.dumps({"match": "all", "rules": [{"field": "category", "op": "is", "value": "Household"}]})},
        {"id": 2, "name": "Not household", "kind": "smart", "criteria": json.dumps({"match": "all", "rules": [{"field": "category", "op": "is_not", "value": "Household"}]})},
    ],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
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
        await page.click('#open-btn')
        await page.wait_for_timeout(500)

        async def saved():
            return await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")
        async def edit(doc_id):
            await page.click(f'#doc-tbody tr[data-id="{doc_id}"]')
            await page.wait_for_timeout(200)
            await page.click('#edit-doc-btn')
            await page.wait_for_timeout(300)
        async def report_rows():
            return [tuple(await r.locator('td').all_inner_texts()) for r in await page.locator('.report-currency-group').first.locator('tbody tr').all()]

        # === Splitting a document ===
        await edit(1)
        print("The Edit form offers to split:", await page.inner_text('#e-splits-start') == '+ Split across categories'
              and not await page.locator('#e-splits-body').is_visible())
        await page.click('#e-splits-start')
        await page.wait_for_timeout(150)
        row = page.locator('#e-split-rows .split-row').first
        await row.locator('.split-category').fill('Household')
        await row.locator('.split-amount').fill('12,5')
        await row.locator('.split-note').fill('cleaning')
        await page.wait_for_timeout(150)
        print("The summary shows what's split and what stays:", await page.inner_text('#e-splits-summary') == 'Split 12.50 of 30.00; 17.50 stays with “Groceries”.')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(500)
        db = await saved()
        print("The line is saved:", [(r['document_id'], r['category'], r['amount'], r['note']) for r in db['document_splits']] == [(1, 'Household', '12.50', 'cleaning')])
        print("The detail panel shows it:", 'Split Household 12.50 (cleaning)' in await page.inner_text('#detail-panel-body'))
        sidecar = await page.evaluate("() => new TextDecoder().decode(window.__TEST_ROOT._children.get('files')._children.get('1_doc.txt')._bytes)")
        print("...and so does the sidecar:", 'Splits: Household 12.50 (cleaning)' in sidecar)

        # === Filters and smart collections ===
        options = await page.locator('#category-filter option').all_inner_texts()
        print("A category used only in a split is in the Category filter:", 'Household' in options)
        await page.select_option('#category-filter', 'Household')
        await page.wait_for_timeout(300)
        print("Filtering by it finds the split document:", await page.locator('#doc-tbody tr .doc-title').all_inner_texts() == ['Supermarket'])
        await page.select_option('#category-filter', '')
        await page.wait_for_timeout(200)
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(300)
        print("A smart rule 'Category is Household' matches it:", await page.locator('#doc-tbody tr .doc-title').all_inner_texts() == ['Supermarket'])
        await page.click('#nav-item-collection-2')
        await page.wait_for_timeout(300)
        print("...and 'Category is not Household' leaves it out:", await page.locator('#doc-tbody tr .doc-title').all_inner_texts() == ['Pharmacy'])
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)

        # === Reports ===
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(300)
        rows = await report_rows()
        print("By Category, each line counts under its own category:", sorted(rows) == sorted([('Groceries', '1', '17.50'), ('Household', '1', '12.50'), ('Health', '1', '10.00')]))
        print("...and the grand total is unchanged:", await page.locator('.report-currency-group').first.locator('tfoot td').all_inner_texts() == ['Grand total', '2', '40.00'])
        await page.click('.report-currency-group >> text=Household')
        await page.wait_for_timeout(300)
        print("Drilling into the split category lists the document:", await page.locator('#doc-tbody tr .doc-title').all_inner_texts() == ['Supermarket'])
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(200)
        await page.select_option('#report-breakdown-field', 'document_type')
        await page.wait_for_timeout(200)
        print("Other breakdowns ignore splits:", await report_rows() == [('Receipt', '2', '40.00')])
        await page.select_option('#report-breakdown-field', 'category')
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)

        # === Validation ===
        await edit(1)
        print("Reopening Edit shows the saved line:", await page.locator('#e-splits-body').is_visible()
              and await page.locator('#e-split-rows .split-amount').input_value() == '12.50')
        await page.click('#e-split-add')
        last = page.locator('#e-split-rows .split-row').last
        await last.locator('.split-category').fill('Toys')
        await last.locator('.split-amount').fill('20')
        await page.wait_for_timeout(150)
        print("Lines adding up to more than the Amount are flagged:", await page.inner_text('#e-splits-summary') == 'The lines add up to more than the Amount.')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        print("...and not saved:", await page.locator('#e-splits').count() == 1 and await page.inner_text('#edit-status') == 'The lines add up to more than the Amount.'
              and len((await saved())['document_splits']) == 1)
        await last.locator('.split-amount').fill('')
        await page.wait_for_timeout(150)
        print("A line without an amount is flagged:", await page.inner_text('#e-splits-summary') == 'Every line needs a category and an amount.')
        await last.locator('.split-remove-btn').click()
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(200)

        # === Renaming a category follows into split lines ===
        await page.click('#tools-btn')
        await page.click('#manage-values-btn')
        await page.wait_for_timeout(300)
        await page.select_option('#values-kind', 'category')
        await page.wait_for_timeout(200)
        await page.locator('.values-row[data-value="Household"] .values-rename-btn').click()
        await page.fill('.values-rename-input', 'Home')
        await page.press('.values-rename-input', 'Enter')
        await page.wait_for_timeout(400)
        print("Renaming a category renames it in split lines:", [r['category'] for r in (await saved())['document_splits']] == ['Home'])
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(200)

        # === Removing the split ===
        await edit(1)
        await page.locator('#e-split-rows .split-remove-btn').click()
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(400)
        print("Removing every line removes the split:", (await saved())['document_splits'] == []
              and 'Split' not in await page.inner_text('#detail-panel-body'))

        # === Splitting while adding a document ===
        await page.click('#add-btn')
        await page.wait_for_timeout(300)
        await page.set_input_files('#file-input', 'tiny.pdf')
        await page.wait_for_timeout(300)
        await page.fill('#f-type', 'Receipt')
        await page.dispatch_event('#f-type', 'change')
        await page.wait_for_timeout(200)
        await page.fill('#f-title', 'Hardware store')
        await page.fill('#f-category', 'DIY')
        await page.locator('#dynamic-fields-f [data-dynamic-field="Amount"] input').fill('50')
        print("The capture form offers to split too:", await page.inner_text('#f-splits-start') == '+ Split across categories')
        await page.click('#f-splits-start')
        await page.locator('#f-split-rows .split-category').fill('Garden')
        await page.locator('#f-split-rows .split-amount').fill('80')
        await page.wait_for_timeout(150)
        files_before = await page.evaluate("() => [...window.__TEST_ROOT._children.get('files')._children.keys()].length")
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)
        print("Too much is refused before anything is written:", await page.inner_text('#capture-status') == 'The lines add up to more than the Amount.'
              and await page.evaluate("() => [...window.__TEST_ROOT._children.get('files')._children.keys()].length") == files_before
              and not await page.locator('#save-doc-btn').is_disabled())
        await page.locator('#f-split-rows .split-amount').fill('20')
        await page.wait_for_timeout(150)
        print("...and the summary updates:", await page.inner_text('#f-splits-summary') == 'Split 20.00 of 50.00; 30.00 stays with “DIY”.')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(600)
        db = await saved()
        new_id = max(d['id'] for d in db['documents'])
        print("Saving a new document saves its line:", [(r['document_id'], r['category'], r['amount']) for r in db['document_splits']] == [(new_id, 'Garden', '20.00')])
        await page.click(f'#doc-tbody tr[data-id="{new_id}"]')
        await page.wait_for_timeout(300)
        print("...shown in the detail panel:", 'Split Garden 20.00' in await page.inner_text('#detail-panel-body'))

        # === German ===
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(200)
        await edit(1)
        await page.click('#e-splits-start')
        await page.locator('#e-split-rows .split-category').fill('Haushalt')
        await page.locator('#e-split-rows .split-amount').fill('5')
        await page.wait_for_timeout(150)
        print("German labels:", await page.inner_text('#e-splits-summary') == '5.00 von 30.00 aufgeteilt; 25.00 bleibt bei „Groceries“.')

        print("ERRORS:", errors)
        await browser.close()

asyncio.run(main())
