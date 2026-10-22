import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, uuid
from playwright.async_api import async_playwright

# Stable uids (two-Mac editing, part 1): every row of the eight listed tables
# gets a uid. Existing rows get a derived UUID v5 in DOSSIARY_UID_NAMESPACE with
# the name "<table>:<key>", so two copies of the same library agree; the
# backfill runs on every open and marks the library with stable_uids_migrated.
NS = uuid.UUID('a3f1c0de-5d0c-4b4e-9e1a-d055a12f0001')
def expected(table, key):
    return str(uuid.uuid5(NS, f"{table}:{key}"))

def doc(i, title):
    return {"id": i, "title": title, "category": "Mail", "document_type": "Letter", "date": f"2026-03-0{i}",
            "import_date": f"2026-03-0{i}T10:00:00Z", "created_at": f"2026-03-0{i}T10:00:00Z",
            "file_path": f"files/{i}_doc.pdf", "source": "captured", "archived": 0, "needs_review": 0, "deleted": 0}
# An old library: rows in all eight tables, no uid anywhere.
SEED = {
    "documents": [doc(1, "Letter one"), doc(2, "Letter two"), doc(3, "Letter three")],
    "tags": [{"id": 1, "name": "tax"}, {"id": 4, "name": "home"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}],
    "people": [{"id": 2, "name": "Jana"}],
    "fields": [
        {"id": 7, "name": "Renewal", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
        {"id": 8, "name": "Organization", "type": "text", "show_as_column": 0, "autocomplete": 1},
    ],
    "collections": [{"id": 1, "name": "Taxes", "kind": "manual", "criteria": None, "folder_id": 5}],
    "collection_folders": [{"id": 5, "name": "Money"}],
    "document_splits": [{"document_id": 2, "position": 0, "category": "Food", "amount": "5.00", "note": ""},
                        {"document_id": 2, "position": 1, "category": "Home", "amount": "3.00", "note": ""}],
    "reminder_snoozes": [{"document_id": 3, "field_id": 7, "snoozed_until": "2099-01-01", "dismissed": 0}],
    "settings": [{"key": "text_autocomplete_default_migrated", "value": "1"}],
}
KEY_COLS = {"documents": ["id"], "tags": ["id"], "people": ["id"], "fields": ["id"], "collections": ["id"],
            "collection_folders": ["id"], "document_splits": ["document_id", "position"],
            "reminder_snoozes": ["document_id", "field_id"]}

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

        # === The derivation is standard UUID v5 ===
        for table, key in [('documents', '1'), ('reminder_snoozes', '3:7'), ('document_splits', '2:1'), ('tags', '42')]:
            got = await page.evaluate(f"window.__DEBUG_derivedUid({json.dumps(table)}, {json.dumps(key)})")
            print(f"derivedUid('{table}', '{key}') matches Python uuid5:", got == expected(table, key))

        async def saved(root='window.__TEST_ROOT'):
            return await page.evaluate(f"() => JSON.parse(new TextDecoder().decode({root}._children.get('library.sqlite')._bytes))")
        async def open_seed(var):
            await page.evaluate(f"window.{var} = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT = window.{var};")
            if await page.locator('#reload-btn').is_visible():
                await page.click('#reload-btn')
                await page.wait_for_timeout(200)
            await page.click('#open-btn')
            await page.wait_for_timeout(600)
        def uids(data):
            out = {}
            for table, cols in KEY_COLS.items():
                for r in data.get(table, []):
                    out[(table, ':'.join(str(r[c]) for c in cols))] = r.get('uid')
            return out

        # === An old library gets derived uids on open ===
        await open_seed('ROOT_A')
        a = await saved('window.ROOT_A')
        ua = uids(a)
        seeded_keys = {(t, ':'.join(str(r[c]) for c in KEY_COLS[t])) for t in KEY_COLS for r in SEED.get(t, [])}
        print("Every seeded row of all eight tables got a uid:", all(ua.get(k) for k in seeded_keys))
        print("Every row's uid is the derived v5 value:", all(v == expected(t, k) for (t, k), v in ua.items() if (t, k) in seeded_keys))
        print("Rows the app added on open (built-in fields) also have their derived uid:",
              all(r.get('uid') == expected('fields', r['id']) for r in a['fields']))
        print("The stable_uids_migrated marker is set:",
              any(s['key'] == 'stable_uids_migrated' and s['value'] == '1' for s in a['settings']))
        print("Tables without a uid are left alone:", all('uid' not in r for r in a['document_tags']))

        # === A second copy of the same old library computes identical uids ===
        await open_seed('ROOT_B')
        ub = uids(await saved('window.ROOT_B'))
        print("Two fresh copies of the same seed get identical uids:", ua == ub)

        # === Reopening changes nothing; a cleared uid comes back the same ===
        await page.evaluate("""() => {
          const r = window.ROOT_B._children.get('library.sqlite');
          const data = JSON.parse(new TextDecoder().decode(r._bytes));
          data.documents.find(d => d.id === 2).uid = null;
          data.document_splits.find(s => s.document_id === 2 && s.position === 1).uid = '';
          r._bytes = new TextEncoder().encode(JSON.stringify(data));
        }""")
        await page.click('#reload-btn')
        await page.wait_for_timeout(200)
        await page.click('#open-btn')
        await page.wait_for_timeout(600)
        ub2 = uids(await saved('window.ROOT_B'))
        print("Reopening keeps every uid unchanged, cleared ones restored to the same value:", ub2 == ub)
        print("The restored document uid is the derived one:", ub2[('documents', '2')] == expected('documents', 2))

        # === A brand new library runs it too ===
        await page.evaluate("window.ROOT_NEW = window.__makeEmptyRoot(); window.ROOT_NEW.name = 'Fresh.dossiary'; window.__TEST_ROOT = window.ROOT_NEW;")
        await page.click('#reload-btn')
        await page.wait_for_timeout(200)
        await page.click('#open-btn')
        await page.wait_for_timeout(300)
        await page.click('#init-btn')
        await page.wait_for_timeout(600)
        fresh = await saved('window.ROOT_NEW')
        print("A new library's built-in fields have derived uids:",
              len(fresh['fields']) > 0 and all(r.get('uid') == expected('fields', r['id']) for r in fresh['fields']))
        print("A new library is marked migrated:",
              any(s['key'] == 'stable_uids_migrated' and s['value'] == '1' for s in fresh['settings']))

        print("No page errors:", not errors, errors if errors else '')
        await browser.close()

asyncio.run(main())
