import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Rename or merge values: a category, subcategory, document type, tag,
# person, or text custom field value, changed across the whole library --
# merging when the new value already exists (after a confirm) -- with Smart
# Collection criteria, type field setup, the default type and sidecars
# following along.
def doc(i, title, **extra):
    d = {
        "id": i, "title": title, "category": None, "subcategory": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }
    d.update(extra)
    return d

SEED = {
    "documents": [
        doc(1, "Market", category="Grocery", document_type="Recipt"),
        doc(2, "Supermarket", category="Groceries", document_type="Receipt"),
        doc(3, "Binned", category="Grocery", deleted=1),
    ],
    "tags": [{"id": 1, "name": "food"}, {"id": 2, "name": "Food"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}, {"document_id": 1, "tag_id": 2}, {"document_id": 2, "tag_id": 2}],
    "people": [{"id": 1, "name": "Arne"}, {"id": 2, "name": "Arne S"}],
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [{"document_id": 1, "field_id": 1, "value": "Visa"}],
    "document_field_people": [{"document_id": 1, "field_id": 4, "person_id": 1}, {"document_id": 2, "field_id": 4, "person_id": 2}],
    "document_type_fields": [
        {"document_type": "Recipt", "field_name": "Amount", "position": 0},
        {"document_type": "Receipt", "field_name": "Payment method", "position": 0},
    ],
    "settings": [{"key": "default_document_type", "value": "Recipt"}],
    "collections": [
        {"id": 1, "name": "Groceries by Visa", "kind": "smart",
         "criteria": json.dumps({"q": "", "category": "Grocery", "type": "Recipt", "person": "", "showArchived": False,
                                 "dynamic": [{"label": "Payment method", "value": "Visa"}],
                                 "amountMin": "", "amountMax": "", "amountUnset": False})},
    ],
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

        async def state():
            return await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        async def rows():
            return await page.locator('.values-row').evaluate_all("rs => rs.map(r => [r.dataset.value, r.querySelector('.doc-sub').textContent])")
        async def rename(old, new, confirm=None):
            if confirm is not None:
                page.once('dialog', lambda dlg: asyncio.ensure_future(dlg.accept() if confirm else dlg.dismiss()))
            await page.click(f'.values-row[data-value="{old}"] .values-rename-btn')
            await page.fill('.values-rename-input', new)
            await page.press('.values-rename-input', 'Enter')
            await page.wait_for_timeout(400)
        async def kind(k):
            await page.select_option('#values-kind', k)
            await page.wait_for_timeout(150)

        await page.click('#tools-btn'); await page.click('#manage-values-btn')
        await page.wait_for_timeout(200)

        # === Scenario 1: values listed with counts, the Waste bin included ===
        print("Categories listed with their counts, most used first:", await rows() == [['Grocery', '2 documents'], ['Groceries', '1 document']], await rows())

        # === Scenario 2: renaming onto an existing value merges, after confirming ===
        await rename('Grocery', 'Groceries', confirm=True)
        st = await state()
        print("Merge: every document now uses the one category, Waste bin included:", all(d['category'] == 'Groceries' for d in st['documents']))
        print("...the list shows one value:", await rows() == [['Groceries', '3 documents']])
        print("...and says what happened:", 'Renamed “Grocery” to “Groceries”' in await page.inner_text('#values-status'))
        crit = json.loads(next(c for c in st['collections'] if c['id'] == 1)['criteria'])
        print("A Smart Collection filtering on the old category follows along:", crit['category'] == 'Groceries')

        # === Scenario 3: a cancelled merge changes nothing ===
        await kind('document_type')
        await rename('Recipt', 'Receipt', confirm=False)
        st = await state()
        print("Cancelling the merge leaves the type alone:", next(d for d in st['documents'] if d['id'] == 1)['document_type'] == 'Recipt')

        # === Scenario 4: merging a document type moves its documents, keeps the target's setup ===
        await rename('Recipt', 'Receipt', confirm=True)
        st = await state()
        types = {r['document_type'] for r in st['document_type_fields']}
        print("Merged type: documents moved:", next(d for d in st['documents'] if d['id'] == 1)['document_type'] == 'Receipt')
        print("...the old type's field setup dropped, the target's kept:", types == {'Receipt'} and [r['field_name'] for r in st['document_type_fields']] == ['Payment method'])
        print("...the default document type follows:", {s['key']: s['value'] for s in st['settings']}.get('default_document_type') == 'Receipt')
        crit = json.loads(next(c for c in st['collections'] if c['id'] == 1)['criteria'])
        print("...and the Smart Collection's type filter:", crit['type'] == 'Receipt')

        # === Scenario 5: merging two tags that differ only in case ===
        await kind('tag')
        await rename('Food', 'food', confirm=True)
        st = await state()
        print("Tag merge: 'Food' is gone from the tag list:", [t['name'] for t in st['tags']] == ['food'])
        links = sorted((l['document_id'], l['tag_id']) for l in st['document_tags'])
        print("...each document keeps one 'food', no duplicate links:", links == [(1, 1), (2, 1)], links)

        # === Scenario 6: renaming a person, then merging them ===
        await kind('person')
        await rename('Arne S', 'Arne Schwarz')
        st = await state()
        print("Person renamed in place (same id):", {p['id']: p['name'] for p in st['people']} == {1: 'Arne', 2: 'Arne Schwarz'})
        await rename('Arne Schwarz', 'Arne', confirm=True)
        st = await state()
        people_links = sorted((l['document_id'], l['person_id']) for l in st['document_field_people'])
        print("Person merged: both documents now link to Arne, the other person is gone:",
              people_links == [(1, 1), (2, 1)] and [p['name'] for p in st['people']] == ['Arne'], people_links)

        # === Scenario 7: a text custom field's value ===
        await kind('field-1')
        await rename('Visa', 'Visa card')
        st = await state()
        vals = [v['value'] for v in st['document_field_values'] if v['field_id'] == 1]
        crit = json.loads(next(c for c in st['collections'] if c['id'] == 1)['criteria'])
        print("Payment method value renamed:", vals == ['Visa card'])
        print("...and the Smart Collection's Payment method filter follows:", crit['dynamic'][0]['value'] == 'Visa card')

        # === Scenario 8: guards ===
        await page.click('.values-row[data-value="Visa card"] .values-rename-btn')
        await page.fill('.values-rename-input', '   ')
        await page.press('.values-rename-input', 'Enter')
        await page.wait_for_timeout(200)
        print("An empty name is refused with a message:", 'name' in (await page.inner_text('#values-status')).lower(), repr(await page.inner_text('#values-status')))
        await page.press('.values-rename-input', 'Escape')
        await page.wait_for_timeout(150)
        print("Escape cancels without closing the dialog:", await page.locator('#values-list').count() == 1 and await page.locator('.values-rename-input').count() == 0)

        # === Scenario 9: sidecars and the table reflect the changes ===
        sidecar = await page.evaluate("async () => { try{ const d = await window.__TEST_ROOT.getDirectoryHandle('files'); return await (await (await d.getFileHandle('1_a.txt')).getFile()).text(); }catch(e){ return null; } }")
        print("The document's sidecar is rewritten with the new values:", sidecar is not None and 'Category: Groceries' in sidecar and 'Payment method: Visa card' in sidecar)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        cat_options = await page.locator('#category-filter option').evaluate_all("os => os.map(o => o.value)")
        print("The category filter no longer offers the old spelling:", 'Grocery' not in cat_options and 'Groceries' in cat_options, cat_options)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
