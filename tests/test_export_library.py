import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Export as library: selected documents become a new <Name>.dossiary library,
# copied or moved, with only the setup they use or all of it.
def doc(i, title, doc_type, file_path, original=None, thumb=None):
    return {
        "id": i, "title": title, "category": "Home", "document_type": doc_type,
        "date": "2026-03-01T00:00:00+00:00", "import_date": f"2026-03-0{i}T00:00:00+00:00",
        "notes": None, "ocr_text": f"text {i}", "ocr_language": None,
        "file_path": file_path, "original_file_path": original, "thumbnail_path": thumb,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 1 if i == 2 else 0, "deleted": 0, "file_hash": f"hash{i}",
    }

SEED = {
    "documents": [
        doc(1, "Invoice", "Invoice", "files/1_a.pdf", "files/1_a/a.pdf", "thumbnails/1.jpg"),
        doc(2, "Letter", "Letter", "files/2_b.pdf"),
        doc(3, "Other", "Other", "files/3_c.pdf"),
    ],
    "tags": [{"id": 1, "name": "tax"}, {"id": 2, "name": "private"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}, {"document_id": 3, "tag_id": 2}],
    "people": [{"id": 1, "name": "Jana"}, {"id": 2, "name": "Arne"}, {"id": 3, "name": "Zed"}],
    "fields": [
        {"id": 1, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 5, "name": "Reminder", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
        {"id": 10, "name": "Organization", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 11, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 12, "name": "Unused", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 13, "name": "Never", "type": "text", "show_as_column": 0, "autocomplete": 1},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 10, "value": "Stadtwerke"},
        {"document_id": 1, "field_id": 2, "value": "12.50"},
        {"document_id": 1, "field_id": 3, "value": "EUR"},
        {"document_id": 3, "field_id": 12, "value": "secret"},
    ],
    "document_field_people": [
        {"document_id": 1, "field_id": 1, "person_id": 1},
        {"document_id": 2, "field_id": 11, "person_id": 2},
        {"document_id": 3, "field_id": 1, "person_id": 3},
    ],
    "document_type_fields": [
        {"document_type": "Invoice", "field_name": "Organization", "position": 0},
        {"document_type": "Invoice", "field_name": "Amount", "position": 1},
        {"document_type": "Invoice", "field_name": "Unused", "position": 2},
        {"document_type": "Letter", "field_name": "Author", "position": 0},
        {"document_type": "Other", "field_name": "Unused", "position": 0},
    ],
    "field_descriptions": [
        {"field_name": "Organization", "description": "Who sent it"},
        {"field_name": "Unused", "description": "x"},
        {"field_name": "Category", "description": "cat hint"},
    ],
    "document_splits": [{"document_id": 1, "position": 0, "category": "Home", "amount": "5.00", "note": ""}],
    "reminder_snoozes": [{"document_id": 1, "field_id": 5, "snoozed_until": "2026-12-01", "dismissed": 0}],
    "collection_folders": [{"id": 1, "name": "Folder A"}, {"id": 2, "name": "Folder B"}],
    "collections": [
        {"id": 1, "name": "Taxes", "kind": "manual", "criteria": None, "folder_id": 1},
        {"id": 2, "name": "Private", "kind": "manual", "criteria": None, "folder_id": None},
        {"id": 3, "name": "Smart", "kind": "smart", "criteria": json.dumps({"match": "all", "rules": []}), "folder_id": 2},
    ],
    "collection_documents": [
        {"collection_id": 1, "document_id": 1}, {"collection_id": 1, "document_id": 3},
        {"collection_id": 2, "document_id": 3},
    ],
    "settings": [
        {"key": "default_currency", "value": "EUR"},
        {"key": "last_backup_at", "value": "2026-01-01T00:00:00Z"},
        {"key": "scan_bridge_url", "value": "http://localhost:9999"},
        {"key": "scan_last_settings", "value": "{}"},
    ],
    "not_duplicate_groups": [{"group_key": "exact:1,3"}],
    "ocr_jobs": [{"document_id": 2, "helper_url": "http://localhost:8766", "job_id": "j", "file_hash": "hash2",
                  "created_at": "2026-03-01T00:00:00Z", "ocr_language": None, "requested_by": "edit"}],  # an Edit-form job counts as pending whatever the scan setting says
}

BUILD_JS = "([ids, mode]) => JSON.parse(new TextDecoder().decode(window.__DEBUG_buildExportLibrary(ids, mode)))"

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'MyLib';")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        # === Scenario 1: "only what these documents use" ===
        used = await page.evaluate(BUILD_JS, [[1, 2], 'used'])
        print("Only the exported documents, ids kept:", sorted(d['id'] for d in used['documents']) == [1, 2])
        print("...with their details:", next(d for d in used['documents'] if d['id'] == 2)['needs_review'] == 1
              and next(d for d in used['documents'] if d['id'] == 1)['file_hash'] == 'hash1')
        print("Only their tags:", [t['name'] for t in used['tags']] == ['tax'])
        print("Only their people:", sorted(x['name'] for x in used['people']) == ['Arne', 'Jana'])
        print("Their custom values, people links, splits and snoozes:",
              sorted({r['document_id'] for r in used['document_field_values']}) == [1]
              and sorted((r['document_id'], r['field_id']) for r in used['document_field_people']) == [(1, 1), (2, 11)]
              and [r['amount'] for r in used['document_splits']] == ['5.00']
              and [(r['document_id'], r['field_id']) for r in used['reminder_snoozes']] == [(1, 5)])
        print("Only used fields plus the built-ins:",
              sorted(f['name'] for f in used['fields']) == ['Amount', 'Author', 'Currency', 'Organization', 'Payment method', 'People', 'Reminder'],
              sorted(f['name'] for f in used['fields']))
        print("Type setup only for exported types and copied fields:",
              sorted((r['document_type'], r['field_name']) for r in used['document_type_fields'])
              == [('Invoice', 'Amount'), ('Invoice', 'Organization'), ('Letter', 'Author')])
        print("Descriptions of copied fields and built-ins:",
              sorted(r['field_name'] for r in used['field_descriptions']) == ['Category', 'Organization'])
        keys = {r['key'] for r in used['settings']}
        print("Settings copied, minus this library's history and scanner:",
              'default_currency' in keys and not keys & {'last_backup_at', 'scan_bridge_url', 'scan_last_settings'})
        print("Manual collections with only exported members, and their folder:",
              [(c['id'], c['name'], c['kind']) for c in used['collections']] == [(1, 'Taxes', 'manual')]
              and [(r['collection_id'], r['document_id']) for r in used['collection_documents']] == [(1, 1)]
              and [f['name'] for f in used['collection_folders']] == ['Folder A'])
        print("No duplicate marks or pending OCR jobs:", used['not_duplicate_groups'] == [] and used['ocr_jobs'] == [])

        # === Scenario 2: "everything from this library" ===
        everything = await page.evaluate(BUILD_JS, [[1, 2], 'all'])
        print("All fields:", sorted(f['name'] for f in everything['fields'])
              == ['Amount', 'Author', 'Currency', 'Never', 'Organization', 'Payment method', 'People', 'Reminder', 'Unused'])
        print("Smart Collections and every folder, plus the exported manual one:",
              sorted((c['id'], c['kind']) for c in everything['collections']) == [(1, 'manual'), (3, 'smart')]
              and sorted(f['id'] for f in everything['collection_folders']) == [1, 2])
        keys = {r['key'] for r in everything['settings']}
        print("...still without history and scanner settings:", not keys & {'last_backup_at', 'scan_bridge_url', 'scan_last_settings'})
        print("Documents are still only the exported ones:", sorted(d['id'] for d in everything['documents']) == [1, 2])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
