import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import re
import asyncio, json
from playwright.async_api import async_playwright

# Import a folder: the counterpart to Export. Every file in the picked folder
# becomes a document; an index.csv (as Export writes it, in any UI language)
# gives the listed files their details, and the rest go to the Inbox. Checked
# as a round trip: export from one library, import into an empty one.
def doc(i, title, date, **extra):
    d = {
        "id": i, "title": title, "category": "Home", "subcategory": "Energy", "document_type": "Invoice",
        "date": date, "import_date": "2026-03-01T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }
    d.update(extra)
    return d

FIELDS = [
    {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
    {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
    {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
    {"id": 4, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    {"id": 5, "name": "Contract no", "type": "text", "show_as_column": 0, "autocomplete": 0},
]
SOURCE = {
    "documents": [
        doc(1, "Stadtwerke", "2026-02-15T00:00:00+00:00", notes='Paid; "on time"'),
        doc(2, "Insurance", "2026-01-10T00:00:00+00:00", category="Insurance", subcategory=None, document_type="Policy"),
    ],
    "tags": [{"id": 1, "name": "tax"}, {"id": 2, "name": "weekly shop"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}, {"document_id": 1, "tag_id": 2}],
    "people": [{"id": 1, "name": "Arne"}, {"id": 2, "name": "Jana"}],
    "document_field_people": [{"document_id": 1, "field_id": 4, "person_id": 1}, {"document_id": 1, "field_id": 4, "person_id": 2}],
    "fields": FIELDS,
    "document_field_values": [
        {"document_id": 1, "field_id": 2, "value": "73.50"},
        {"document_id": 1, "field_id": 3, "value": "EUR"},
        {"document_id": 2, "field_id": 5, "value": "K-99"},
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SOURCE)});")
        await page.evaluate("""
            async () => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                for(const i of [1, 2]){
                    const w = await (await dir.getFileHandle(`${i}_a.pdf`, { create: true })).createWritable();
                    await w.write(new TextEncoder().encode(`%PDF-1.4 doc ${i}`)); await w.close();
                }
                window.__FOLDER = window.__makeEmptyRoot(); window.__FOLDER.name = 'From Arne';
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        # Export both documents (German UI, so index.csv uses ';' and German headers).
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        for i in [1, 2]:
            await page.check(f'.row-select-checkbox[data-id="{i}"]')
        await page.click('#bulk-more-btn'); await page.click('#bulk-export-btn')
        await page.wait_for_timeout(200)
        await page.uncheck('#export-details-toggle')
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__FOLDER; }")
        await page.click('#export-start-btn')
        await page.wait_for_timeout(800)
        await page.click('#export-cancel-btn')
        await page.wait_for_timeout(150)
        # A loose file without an index row, plus a hidden file to ignore.
        await page.evaluate("""async () => {
            for(const [n, c] of [['scan 7.pdf', '%PDF-1.4 loose'], ['.DS_Store', 'junk']]){
                const w = await (await window.__FOLDER.getFileHandle(n, { create: true })).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close();
            }
        }""")
        names = await page.evaluate("async () => { const n = []; for await (const [k] of window.__FOLDER.entries()) n.push(k); return n.sort(); }")
        print("The export folder holds two files and index.csv:", '2026-02-15 Stadtwerke.pdf' in names and 'index.csv' in names, names)

        # === Switch to an empty library ===
        await page.select_option('#lang-select', 'en')
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps({'documents': [], 'fields': FIELDS})});")
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("The new library starts empty:", await page.locator("#doc-tbody tr[data-id]").count() == 0)

        await page.click('#tools-btn')
        print("Import a folder is in the Tools menu:", await page.locator('#import-folder-btn').is_visible())
        await page.click('#import-folder-btn')
        await page.wait_for_timeout(200)
        print("The dialog explains index.csv:", 'index.csv' in await page.inner_text('.modal'))

        # === Scenario 1: a folder inside the library is refused ===
        await page.evaluate("async () => { window.__NEXT_PICKED_DIR = await window.__TEST_ROOT.getDirectoryHandle('files'); }")
        await page.click('#import-start-btn')
        await page.wait_for_timeout(300)
        print("A folder inside the library is refused:", 'inside' in await page.inner_text('#import-status') and await page.locator('#import-start-btn').is_enabled())

        # === Scenario 2: importing the exported folder ===
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__FOLDER; }")
        await page.click('#import-start-btn')
        await page.wait_for_timeout(1200)
        summary = await page.inner_text('#import-summary')
        print("Summary: 3 added, 2 with details, 1 for review:", 'Added: 3' in summary and 'With details from index.csv: 2' in summary and 'In the Inbox for review: 1' in summary, repr(summary))
        print("The folder was only read, not changed:", await page.evaluate("async () => { const n = []; for await (const [k] of window.__FOLDER.entries()) n.push(k); return n.length; }") == 5)
        rows = await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")
        docs = {d['title']: d for d in rows['documents']}
        s = docs.get('Stadtwerke', {})
        print("Title, date, category, subcategory, type, notes come from index.csv:",
              (s.get('date'), s.get('category'), s.get('subcategory'), s.get('document_type'), s.get('notes')) == ('2026-02-15', 'Home', 'Energy', 'Invoice', 'Paid; "on time"'), s)
        print("...the original import date is kept:", s.get('import_date') == '2026-03-01')
        print("Imported documents are new records with random v4 uids:",
              all(re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', d.get('uid') or '') for d in rows['documents']))
        print("...and it is filed, not flagged for review:", s.get('needs_review') == 0 and s.get('source') == 'folder-import')
        field_ids = {f['name']: f['id'] for f in rows['fields']}
        vals = {(v['document_id'], v['field_id']): v['value'] for v in rows['document_field_values']}
        print("Amount and Currency round-trip:", vals.get((s['id'], field_ids['Amount'])) == '73.50' and vals.get((s['id'], field_ids['Currency'])) == 'EUR')
        tag_names = {t['id']: t['name'] for t in rows['tags']}
        print("Tags round-trip (one with a space too):", sorted(tag_names[dt['tag_id']] for dt in rows['document_tags'] if dt['document_id'] == s['id']) == ['tax', 'weekly shop'])
        person_names = {p['id']: p['name'] for p in rows['people']}
        print("People round-trip:", sorted(person_names[x['person_id']] for x in rows['document_field_people'] if x['document_id'] == s['id']) == ['Arne', 'Jana'])
        ins = docs.get('Insurance', {})
        print("A custom field round-trips:", vals.get((ins.get('id'), field_ids['Contract no'])) == 'K-99')
        dtf = [r['field_name'] for r in rows['document_type_fields'] if r['document_type'] == 'Invoice']
        print("A type new to this library gets the fields its documents use:", set(dtf) >= {'Amount', 'Currency', 'People'}, dtf)
        loose = docs.get('scan 7', {})
        print("A file without an index row is added for review:", str(loose.get('needs_review')) == '1' and loose.get('category') is None)
        print("Hidden files are ignored:", len(rows['documents']) == 3)
        sidecar = await page.evaluate(f"async () => {{ const d = await window.__TEST_ROOT.getDirectoryHandle('files'); for await (const [k, h] of d.entries()) if(k.startsWith('{s['id']}_') && k.endsWith('.txt')) return await (await h.getFile()).text(); return ''; }}")
        print("The sidecar carries the imported details:", 'Home' in sidecar and 'tax' in sidecar, repr(sidecar[:120]))
        await page.click('#import-cancel-btn')
        await page.wait_for_timeout(150)
        print("Lands in the table:", await page.locator('#doc-tbody tr').count() >= 2)

        # === Scenario 3: importing the same folder again skips everything ===
        await page.click('#tools-btn'); await page.click('#import-folder-btn')
        await page.wait_for_timeout(200)
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__FOLDER; }")
        await page.click('#import-start-btn')
        await page.wait_for_timeout(1000)
        summary2 = await page.inner_text('#import-summary')
        print("A second import skips files already in the library:", 'Added: 0' in summary2 and 'Already in the library, skipped: 3' in summary2, repr(summary2))
        await page.click('#import-cancel-btn')

        # === Scenario 4: a folder without index.csv: every file for review; and an empty folder ===
        await page.evaluate("""async () => {
            window.__PLAIN = window.__makeEmptyRoot(); window.__PLAIN.name = 'Plain';
            for(const n of ['a.pdf', 'b.jpg']){ const w = await (await window.__PLAIN.getFileHandle(n, { create: true })).createWritable(); await w.write(new TextEncoder().encode('plain ' + n)); await w.close(); }
            window.__EMPTY = window.__makeEmptyRoot(); window.__EMPTY.name = 'Nothing';
            window.__NEXT_PICKED_DIR = window.__EMPTY;
        }""")
        await page.click('#tools-btn'); await page.click('#import-folder-btn')
        await page.wait_for_timeout(200)
        await page.click('#import-start-btn')
        await page.wait_for_timeout(300)
        print("An empty folder says there is nothing to import:", 'no files' in await page.inner_text('#import-status'))
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__PLAIN; }")
        await page.click('#import-start-btn')
        await page.wait_for_timeout(1000)
        summary3 = await page.inner_text('#import-summary')
        print("Without index.csv every file is added for review:", 'Added: 2' in summary3 and 'In the Inbox for review: 2' in summary3 and 'index.csv' not in summary3, repr(summary3))

        print("JS ERRORS:", errors)
        # Stable uids: every row this test created in a uid table got its uid
        # when it was inserted (migrateStableUids() only runs on open).
        print("Every row in the uid tables has a uid:", await page.evaluate("""() => {
            const data = JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes));
            return ['documents', 'tags', 'people', 'fields', 'collections', 'collection_folders', 'document_splits', 'reminder_snoozes']
                .every(t => (data[t] || []).every(r => /^[0-9a-f]{8}-[0-9a-f]{4}-[45][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(r.uid || '')));
        }"""))
        await browser.close()

asyncio.run(main())
