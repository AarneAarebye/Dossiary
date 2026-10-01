import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# "Copy the setup of" on the new-library screen: a new library can start with
# another library's fields (ids kept), document types' field order, field
# descriptions, smart collections and settings -- never its documents, tags,
# people, manual collections or last-backup date. The source is chosen from
# recent libraries or with "Another library folder…", is only read, and one
# that can't be read is reported before anything is created.
SOURCE_SEED = {
    'fields': [
        {'id': 1, 'name': 'Payment method', 'type': 'text', 'show_as_column': 1, 'autocomplete': 1},
        {'id': 2, 'name': 'Amount', 'type': 'number', 'show_as_column': 0, 'autocomplete': 0},
        {'id': 3, 'name': 'Currency', 'type': 'text', 'show_as_column': 1, 'autocomplete': 1},
        {'id': 4, 'name': 'People', 'type': 'person', 'show_as_column': 0, 'autocomplete': 0},
        {'id': 5, 'name': 'Reminder', 'type': 'reminder', 'show_as_column': 0, 'autocomplete': 0},
        # Autocomplete deliberately switched off -- must not be switched back on.
        {'id': 10, 'name': 'Organization', 'type': 'text', 'show_as_column': 1, 'autocomplete': 0},
    ],
    'document_type_fields': [
        {'document_type': 'Invoice', 'field_name': 'Organization', 'position': 0},
        {'document_type': 'Invoice', 'field_name': 'Amount', 'position': 1},
        {'document_type': 'Invoice', 'field_name': 'Currency', 'position': 2},
    ],
    'field_descriptions': [{'field_name': 'Organization', 'description': 'Who sent it'}],
    'collections': [
        {'id': 1, 'name': 'Big invoices', 'kind': 'smart', 'criteria': json.dumps({'match': 'all', 'rules': [{'field': 'field:2', 'op': 'gte', 'value': '100'}]})},
        {'id': 2, 'name': 'Tax 2025', 'kind': 'manual', 'criteria': None},
    ],
    'collection_documents': [{'collection_id': 2, 'document_id': 1}],
    'settings': [
        {'key': 'default_document_type', 'value': 'Invoice'},
        {'key': 'default_currency', 'value': 'EUR'},
        {'key': 'visible_columns', 'value': json.dumps(['category', 'date', 'field-10'])},
        {'key': 'last_backup_at', 'value': '2025-12-31T10:00:00Z'},
        {'key': 'text_autocomplete_default_migrated', 'value': '1'},
        {'key': 'currency_column_default_migrated', 'value': '1'},
        {'key': 'searchable_pdf_built_backfill_migrated', 'value': '1'},
    ],
    'documents': [{'id': 1, 'title': 'Old invoice', 'category': 'Home', 'document_type': 'Invoice', 'date': '2025-03-01',
                   'import_date': '2025-03-02T10:00:00Z', 'created_at': '2025-03-02T10:00:00Z', 'file_path': 'files/1_old.pdf',
                   'source': 'captured', 'needs_review': 0, 'archived': 0, 'deleted': 0}],
    'tags': [{'id': 1, 'name': 'taxes'}],
    'document_tags': [{'document_id': 1, 'tag_id': 1}],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1280, 'height': 900})
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

        async def pick(js_root):
            await page.evaluate(f"() => {{ window.__TEST_ROOT = {js_root}; }}")
            if await page.locator('#pick-again-btn').is_visible():
                await page.click('#pick-again-btn')
            else:
                if await page.locator('#reload-btn').is_visible():
                    await page.click('#reload-btn')
                    await page.wait_for_timeout(200)
                await page.click('#open-btn')
            await page.wait_for_timeout(400)
        async def lib_db(expr):
            return await page.evaluate(f"""() => {{
                const f = ({expr})._children.get('library.sqlite');
                return f ? JSON.parse(new TextDecoder().decode(f._bytes)) : null;
            }}""")
        async def option_labels():
            return await page.evaluate("() => [...document.querySelectorAll('#copy-setup-select option')].map(o => [o.value, o.textContent])")

        # Open the source once, so it's in Recent libraries.
        await page.evaluate(f"() => {{ window.__SOURCE = window.__makeSeededRoot({json.dumps(SOURCE_SEED)}); window.__SOURCE.name = 'Tax 2025.dossiary'; }}")
        await pick("window.__SOURCE")
        print("Source library opened:", 'Old invoice' in await page.inner_text('#doc-tbody'))
        source_before = await page.evaluate("() => new TextDecoder().decode(window.__SOURCE._children.get('library.sqlite')._bytes)")

        # === Scenario 1: copy from a recent library into a new <Name>.dossiary ===
        await pick("(() => { const r = window.__makeEmptyRoot(); r.name = 'Documents'; return r; })()")
        print("The new-library screen offers 'Copy the setup of':", await page.locator('#copy-setup-row').is_visible())
        labels = await option_labels()
        print("...defaulting to Nothing:", await page.input_value('#copy-setup-select') == '' and labels[0][1] == 'Nothing, start empty')
        print("...listing the recent library and 'Another library folder…':",
              any(l[1] == 'Tax 2025.dossiary' and l[0].startswith('recent:') for l in labels) and labels[-1] == ['pick', 'Another library folder…'])
        recent_value = next(l[0] for l in labels if l[1] == 'Tax 2025.dossiary')
        await page.select_option('#copy-setup-select', recent_value)
        await page.fill('#new-library-name', 'Tax 2026')
        await page.click('#create-library-btn')
        await page.wait_for_timeout(500)
        new = await lib_db("window.__TEST_ROOT._children.get('Tax 2026.dossiary')")
        fields = {f['name']: f for f in new['fields']}
        print("Custom field copied with its id and flags:", fields.get('Organization', {}).get('id') == 10
              and fields['Organization']['show_as_column'] == 1 and fields['Organization']['autocomplete'] == 0)
        print("No field is duplicated by the built-in field setup:", len(new['fields']) == len(fields) == 6)
        print("Document types' field order copied:", sorted((r['document_type'], r['field_name'], r['position']) for r in new['document_type_fields'])
              == [('Invoice', 'Amount', 1), ('Invoice', 'Currency', 2), ('Invoice', 'Organization', 0)])
        print("Field descriptions copied:", new['field_descriptions'] == [{'field_name': 'Organization', 'description': 'Who sent it'}])
        print("Smart collections copied, manual ones not:", [c['name'] for c in new['collections']] == ['Big invoices'] and new['collection_documents'] == [])
        settings = {r['key']: r['value'] for r in new['settings']}
        print("Settings copied:", settings.get('default_document_type') == 'Invoice' and settings.get('default_currency') == 'EUR'
              and json.loads(settings.get('visible_columns', '[]')) == ['category', 'date', 'field-10'])
        print("...but not the last backup date:", 'last_backup_at' not in settings)
        print("No documents, tags or people:", new['documents'] == [] and new['tags'] == [] and new['document_tags'] == [] and new['people'] == [])
        status = await page.inner_text('#status')
        print("Status line says where the setup came from:", 'Setup copied from “Tax 2025.dossiary”.' in status)
        print("The new library opens with the copied column:", await page.locator('#doc-thead-row th', has_text='Organization').count() == 1)
        await page.click('#nav-collections-toggle') if not await page.locator('#nav-collections-list', has_text='Big invoices').is_visible() else None
        print("...and the smart collection in the sidebar:", await page.locator('#nav-collections-list', has_text='Big invoices').count() == 1)
        source_after = await page.evaluate("() => new TextDecoder().decode(window.__SOURCE._children.get('library.sqlite')._bytes)")
        print("The source library is untouched:", source_before == source_after)

        # === Scenario 2: "Another library folder…" with "Use this folder as the library" ===
        await pick("(() => { const r = window.__makeEmptyRoot(); r.name = 'Taxes 2027'; return r; })()")
        await page.evaluate(f"() => {{ const r = window.__makeSeededRoot({json.dumps(SOURCE_SEED)}); r.name = 'Elsewhere'; window.__NEXT_PICKED_DIR = r; }}")
        await page.select_option('#copy-setup-select', 'pick')
        await page.wait_for_timeout(300)
        print("A picked folder is added and selected:", await page.input_value('#copy-setup-select') == 'picked'
              and ['picked', 'Elsewhere'] in await option_labels())
        await page.click('#init-btn')
        await page.wait_for_timeout(500)
        new2 = await lib_db("window.__TEST_ROOT")
        print("Using the picked folder itself copies the setup too:", any(f['name'] == 'Organization' for f in new2['fields'])
              and [c['name'] for c in new2['collections']] == ['Big invoices'] and new2['documents'] == [])

        # === Scenario 3: a folder that isn't a library is reported, nothing is created ===
        await pick("(() => { const r = window.__makeEmptyRoot(); r.name = 'Documents'; return r; })()")
        await page.evaluate("() => { const r = window.__makeEmptyRoot(); r.name = 'Holiday photos'; window.__NEXT_PICKED_DIR = r; }")
        await page.select_option('#copy-setup-select', 'pick')
        await page.wait_for_timeout(300)
        await page.fill('#new-library-name', 'Broken')
        await page.click('#create-library-btn')
        await page.wait_for_timeout(300)
        print("A folder without library.sqlite is reported:", 'isn’t a Dossiary library' in await page.inner_text('#copy-setup-error'))
        print("...and no library folder was created:", not await page.evaluate("() => window.__TEST_ROOT._children.has('Broken.dossiary')")
              and await page.locator('#init-state').is_visible())

        # === Scenario 4: cancelling the folder picker falls back to Nothing ===
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = null; window.__TEST_ROOT_SAVED = window.__TEST_ROOT; window.__TEST_ROOT = null; }")
        await page.select_option('#copy-setup-select', '')
        await page.select_option('#copy-setup-select', 'pick')
        await page.wait_for_timeout(300)
        print("Cancelling the picker keeps the earlier choice:", await page.input_value('#copy-setup-select') == 'picked')
        await page.evaluate("() => { window.__TEST_ROOT = window.__TEST_ROOT_SAVED; }")

        # === Scenario 5: Nothing creates a plain library; the labels follow the language ===
        await page.select_option('#copy-setup-select', '')
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(200)
        labels = await option_labels()
        print("Options retranslate on a language change:", labels[0][1] == 'Nichts, leer beginnen' and labels[-1][1] == 'Anderer Bibliotheksordner…'
              and await page.input_value('#copy-setup-select') == '')
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'en'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(200)
        await page.fill('#new-library-name', 'Plain')
        await page.click('#create-library-btn')
        await page.wait_for_timeout(500)
        plain = await lib_db("window.__TEST_ROOT._children.get('Plain.dossiary')")
        print("Nothing gives a plain new library:", not any(f['name'] == 'Organization' for f in plain['fields'])
              and plain['collections'] == [] and 'Setup copied' not in await page.inner_text('#status'))

        print("ERRORS:", errors)
        await browser.close()

asyncio.run(main())
