import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, io, json, re, zipfile
from playwright.async_api import async_playwright

# Export as library bundled with Dossiary: the library plus a copy of
# dossiary.html and "How to open.txt", as a folder, a .zip file, or both.
VERSION = re.search(r"const APP_VERSION = '([^']+)'", open(APP_PATH, encoding='utf-8').read()).group(1)
OWN_COPY_URL = f"https://cdn.jsdelivr.net/gh/AarneAarebye/Dossiary@v{VERSION}/dossiary.html"
OWN_COPY = f"<!DOCTYPE html><html><body><script>const APP_VERSION = '{VERSION}';</script>downloaded copy</body></html>"
CHOSEN = f"<!DOCTYPE html><html><body><script>const APP_VERSION = '{VERSION}';</script>chosen copy</body></html>"

def doc(i, title, file_path, original=None):
    return {
        "id": i, "title": title, "category": "Home", "document_type": "Invoice",
        "date": "2026-03-01T00:00:00+00:00", "import_date": f"2026-03-0{i}T00:00:00+00:00",
        "notes": None, "ocr_text": f"text {i}", "ocr_language": None,
        "file_path": file_path, "original_file_path": original, "thumbnail_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0, "file_hash": f"hash{i}",
    }

SEED = {
    "documents": [doc(1, "Invoice", "files/1_a.pdf", "files/1_a/a.pdf"), doc(2, "Letter", "files/2_Հաշիվ_发票.pdf")],
    "fields": [
        {"id": 1, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 5, "name": "Reminder", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
    ],
    "settings": [{"key": "text_autocomplete_default_migrated", "value": "1"}],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" and 'ERR_FAILED' not in msg.text else None)

        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)

        # jsDelivr, faked: registered after the catch-all, so it wins.
        fetches = []
        net = {'online': True, 'body': OWN_COPY}
        async def own_copy_route(route):
            fetches.append(route.request.url)
            if not net['online']:
                await route.abort()
                return
            await route.fulfill(status=200, body=net['body'], content_type='text/html',
                                headers={'access-control-allow-origin': '*'})
        await page.route('https://cdn.jsdelivr.net/gh/**', own_copy_route)

        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'MyLib';")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)
        await page.evaluate("""() => {
            window.__CONFIRM_ANSWER = true; window.__CONFIRM_MSGS = [];
            window.confirm = (m) => { window.__CONFIRM_MSGS.push(m); return window.__CONFIRM_ANSWER; };
        }""")

        # === Scenario 1: names ===
        n = await page.evaluate("() => [window.__DEBUG_bundleNames('Tax 2025'), window.__DEBUG_bundleNames('Old.DOSSIARY')]")
        print("Bundle names from 'Tax 2025':", n[0] == {'library': 'Tax 2025.dossiary', 'bundle': 'Tax 2025', 'zip': 'Tax 2025.zip'}, n[0])
        print("...and from a name already ending in .dossiary:", n[1] == {'library': 'Old.DOSSIARY', 'bundle': 'Old', 'zip': 'Old.zip'}, n[1])

        # === Scenario 2: the download ===
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("Downloads its own version from jsDelivr:", fetches == [OWN_COPY_URL], fetches)
        print("...and uses it:", got == {'text': OWN_COPY})
        net['body'] = OWN_COPY.replace(VERSION, '0.0.1')
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("A download of another version is not used:", got == {'missing': True}, got)
        net['body'] = OWN_COPY
        net['online'] = False
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("Offline with nothing stored: missing:", got == {'missing': True}, got)

        # === Scenario 3: a chosen copy, and the stored copy ===
        got = await page.evaluate(f"() => window.__DEBUG_getDossiaryHtmlForBundle({json.dumps(CHOSEN)})")
        print("Offline, a copy chosen in this dialog is used:", got == {'text': CHOSEN})
        await page.evaluate(f"() => window.__DEBUG_storeOwnCopy({json.dumps(CHOSEN)}, {json.dumps(VERSION)})")
        stored = await page.evaluate("() => window.__DEBUG_loadStoredOwnCopy()")
        print("The stored copy keeps text and version:", stored['text'] == CHOSEN and stored['version'] == VERSION and stored['id'] == 'dossiary.html')
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("Offline, the stored copy is used without asking:", got == {'text': CHOSEN} and await page.evaluate("() => window.__CONFIRM_MSGS.length") == 0)
        await page.evaluate(f"() => window.__DEBUG_storeOwnCopy({json.dumps(CHOSEN)}, '0.0.1')")
        await page.evaluate("() => { window.__CONFIRM_ANSWER = false; }")
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        msgs = await page.evaluate("() => window.__CONFIRM_MSGS")
        print("An older stored copy asks first, naming both versions:", len(msgs) == 1 and '0.0.1' in msgs[0] and VERSION in msgs[0], msgs)
        print("...declining stops:", got == {'declined': True})
        await page.evaluate("() => { window.__CONFIRM_ANSWER = true; }")
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("...accepting uses it:", got == {'text': CHOSEN})
        await page.evaluate(f"() => window.__DEBUG_storeOwnCopy({json.dumps(CHOSEN)}, {json.dumps(VERSION)})")
        net['online'] = True

        # === Scenario 4: How to open.txt ===
        readme = await page.evaluate("() => window.__DEBUG_bundleReadmeText('Tax 2025.dossiary')")
        print("English instructions name the button, the folder and Recent libraries:",
              'Open library folder' in readme and 'Tax 2025.dossiary' in readme and 'Recent libraries' in readme and 'Chrome' in readme, repr(readme))
        print("...the version, and no second language:", VERSION in readme and '----' not in readme)
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        readme = await page.evaluate("() => window.__DEBUG_bundleReadmeText('Steuer.dossiary')")
        de_part, _, en_part = readme.partition('\n\n----\n\n')
        print("German first, then English:", 'Bibliotheksordner öffnen' in de_part and 'Zuletzt geöffnete Bibliotheken' in de_part
              and 'Open library folder' in en_part and 'Steuer.dossiary' in en_part, repr(readme))
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(200)

        # Files for the dialog scenarios
        await page.evaluate("""
            async () => {
                const put = async (path, text) => {
                    const parts = path.split('/');
                    let dir = window.__TEST_ROOT;
                    for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                    const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
                    await w.write(new TextEncoder().encode(text)); await w.close();
                };
                await put('files/1_a.pdf', 'active 1');
                await put('files/1_a/a.pdf', 'original 1');
                await put('files/2_Հաշիվ_发票.pdf', 'active 2');
                window.__EXPORT_PARENT = window.__makeEmptyRoot();
                window.__EXPORT_PARENT.name = 'Outside';
            }
        """)
        LIST_IN = """async (name) => {
            const out = [];
            const walk = async (dir, prefix) => {
                for await (const [n, h] of dir.entries()){
                    if(h.kind === 'directory') await walk(h, prefix + n + '/');
                    else out.push(prefix + n);
                }
            };
            await walk(await window.__EXPORT_PARENT.getDirectoryHandle(name), '');
            return out.sort();
        }"""
        READ_IN = """async ([name, path]) => {
            let dir = await window.__EXPORT_PARENT.getDirectoryHandle(name);
            const parts = path.split('/');
            for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part);
            return await (await (await dir.getFileHandle(parts[parts.length - 1])).getFile()).text();
        }"""
        ZIP_BYTES = "async (name) => Array.from(new Uint8Array(await (await (await window.__EXPORT_PARENT.getFileHandle(name)).getFile()).arrayBuffer()))"
        PARENT_NAMES = "async () => { const n = []; for await (const [k] of window.__EXPORT_PARENT.entries()) n.push(k); return n.sort(); }"
        SOURCE_DB = "async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())"
        RECENT = "() => [...window.__FAKE_IDB_DATABASES.get('dossiary-app-db')._stores.get('recentLibraries').map.values()].map(e => e.name)"

        async def open_dialog(ids, name, output):
            await page.click('#nav-item-all')
            await page.wait_for_timeout(150)
            # Clear any selection left over from the previous scenario
            # (setView() keeps it when the view doesn't change).
            for box in await page.query_selector_all('tr .row-select-checkbox:checked'):
                await box.uncheck()
            for i in ids:
                await page.check(f'tr[data-id="{i}"] .row-select-checkbox')
            await page.click('#bulk-more-btn')
            await page.click('#bulk-export-library-btn')
            await page.wait_for_timeout(300)
            await page.fill('#export-library-name', name)
            await page.check(f'input[name="export-library-output"][value="{output}"]')

        async def start():
            await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT; }")
            await page.click('#export-library-start-btn')
            await page.wait_for_timeout(1200)

        async def close_dialog():
            await page.click('#export-library-cancel-btn')
            await page.wait_for_timeout(150)

        # === Scenario 5: Library only stays as it was, and offline ===
        fetches.clear()
        await open_dialog([1], 'Plain', 'library')
        print("Library only is the default output:", await page.evaluate("() => document.querySelector('input[name=\"export-library-output\"][value=\"library\"]').defaultChecked"))
        print("No bundle hint for Library only:", not await page.is_visible('#export-library-output-hint'))
        print("Hint names the library folder:", 'Plain.dossiary' in await page.inner_text('#export-library-hint'))
        await start()
        print("Library only never downloads:", fetches == [])
        print("...and makes just the library:", 'Plain.dossiary' in await page.evaluate(PARENT_NAMES))
        await close_dialog()

        # === Scenario 6: Library + Dossiary as a folder ===
        fetches.clear()
        await open_dialog([1, 2], 'Tax 2025', 'folder')
        print("Folder hint names bundle and library:", 'Tax 2025' in await page.inner_text('#export-library-hint')
              and 'Tax 2025.dossiary' in await page.inner_text('#export-library-hint'))
        print("The bundle explanation shows:", await page.is_visible('#export-library-output-hint'))
        await start()
        print("Downloaded its own copy:", fetches == [OWN_COPY_URL], fetches)
        files = await page.evaluate(LIST_IN, 'Tax 2025')
        print("Bundle folder layout:", files == ['How to open.txt', 'Tax 2025.dossiary/files/1_a.pdf', 'Tax 2025.dossiary/files/1_a.txt',
              'Tax 2025.dossiary/files/1_a/a.pdf', 'Tax 2025.dossiary/files/2_Հաշիվ_发票.pdf', 'Tax 2025.dossiary/files/2_Հաշիվ_发票.txt',
              'Tax 2025.dossiary/library.sqlite', 'dossiary.html'], files)
        print("dossiary.html is the downloaded copy:", await page.evaluate(READ_IN, ['Tax 2025', 'dossiary.html']) == OWN_COPY)
        readme = await page.evaluate(READ_IN, ['Tax 2025', 'How to open.txt'])
        print("How to open names the library folder:", 'Tax 2025.dossiary' in readme and 'Open library folder' in readme)
        status = await page.inner_text('#export-library-status')
        print("Summary names the bundle folder:", 'Outside/Tax 2025' in status and 'Documents exported: 2' in status, repr(status))
        print("Open it is offered:", await page.is_visible('#export-library-open-btn'))
        print("Recent libraries gets the inner library:", 'Tax 2025.dossiary' in await page.evaluate(RECENT))
        await close_dialog()

        # === Scenario 7: an existing bundle folder is refused ===
        await open_dialog([1], 'Tax 2025', 'folder')
        await start()
        print("Existing bundle folder refused:", 'already a folder' in await page.inner_text('#export-library-status'))
        await close_dialog()

        # === Scenario 8: offline, nothing stored -> Choose dossiary.html ===
        await page.evaluate("() => window.__FAKE_IDB_DATABASES.delete('dossiary-bundle-source')")
        net['online'] = False
        await open_dialog([1], 'Offline', 'folder')
        print("Choose button hidden at first:", not await page.is_visible('#export-bundle-choose'))
        await start()
        print("Asks for dossiary.html:", 'couldn’t download' in await page.inner_text('#export-library-status')
              and await page.is_visible('#export-bundle-choose'))
        print("...and wrote nothing:", 'Offline' not in await page.evaluate(PARENT_NAMES))
        await page.evaluate("""() => {
            window.__PICKED_HTML = '<html>not it</html>';
            window.showOpenFilePicker = async () => [{ kind: 'file', name: 'dossiary.html',
                getFile: async () => new File([window.__PICKED_HTML], 'dossiary.html', { type: 'text/html' }) }];
        }""")
        await page.click('#export-bundle-choose-btn')
        await page.wait_for_timeout(200)
        print("A file that isn't Dossiary is refused:", 'isn’t Dossiary' in await page.inner_text('#export-bundle-choose-note'))
        await page.evaluate(f"() => {{ window.__PICKED_HTML = {json.dumps(CHOSEN)}; }}")
        await page.click('#export-bundle-choose-btn')
        await page.wait_for_timeout(200)
        print("The chosen copy is confirmed with its version:", VERSION in await page.inner_text('#export-bundle-choose-note'))
        print("...and stored:", (await page.evaluate("() => window.__DEBUG_loadStoredOwnCopy()") or {}).get('text') == CHOSEN)
        await start()
        print("Second click exports with the chosen copy:", await page.evaluate(READ_IN, ['Offline', 'dossiary.html']) == CHOSEN)
        await close_dialog()

        # === Scenario 9: the stored copy is used later without asking ===
        await open_dialog([1], 'Again', 'folder')
        await start()
        print("Stored copy used, no Choose step:", await page.evaluate(READ_IN, ['Again', 'dossiary.html']) == CHOSEN
              and not await page.is_visible('#export-bundle-choose'))
        await close_dialog()

        # === Scenario 10: an outdated stored copy, declined ===
        await page.evaluate("() => { window.__FAKE_IDB_DATABASES.get('dossiary-bundle-source')._stores.get('copies').map.get('dossiary.html').version = '0.0.1'; window.__CONFIRM_ANSWER = false; window.__CONFIRM_MSGS = []; }")
        await open_dialog([1], 'Declined', 'folder')
        await start()
        print("Outdated copy asks first:", len(await page.evaluate("() => window.__CONFIRM_MSGS")) == 1)
        print("Declining writes nothing and offers Choose:", 'Declined' not in await page.evaluate(PARENT_NAMES)
              and await page.is_visible('#export-bundle-choose'))
        await close_dialog()
        await page.evaluate(f"() => {{ window.__CONFIRM_ANSWER = true; return window.__DEBUG_storeOwnCopy({json.dumps(CHOSEN)}, {json.dumps(VERSION)}); }}")
        net['online'] = True

        # === Scenario 11: zip only ===
        await open_dialog([1, 2], 'Zipped', 'zip')
        print("Zip hint names the zip:", 'Zipped.zip' in await page.inner_text('#export-library-hint'))
        await start()
        names = await page.evaluate(PARENT_NAMES)
        print("Only the zip is made:", 'Zipped.zip' in names and 'Zipped' not in names, names)
        z = zipfile.ZipFile(io.BytesIO(bytes(await page.evaluate(ZIP_BYTES, 'Zipped.zip'))))
        print("Zip entries:", sorted(z.namelist()) == ['Zipped/How to open.txt', 'Zipped/Zipped.dossiary/files/1_a.pdf',
              'Zipped/Zipped.dossiary/files/1_a.txt', 'Zipped/Zipped.dossiary/files/1_a/a.pdf',
              'Zipped/Zipped.dossiary/files/2_Հաշիվ_发票.pdf', 'Zipped/Zipped.dossiary/files/2_Հաշիվ_发票.txt',
              'Zipped/Zipped.dossiary/library.sqlite', 'Zipped/dossiary.html'], sorted(z.namelist()))
        print("Zip contents and CRCs:", z.read('Zipped/Zipped.dossiary/files/1_a.pdf') == b'active 1'
              and z.read('Zipped/dossiary.html').decode() == OWN_COPY and z.testzip() is None)
        db_in_zip = json.loads(z.read('Zipped/Zipped.dossiary/library.sqlite'))
        print("The zipped library holds both documents:", sorted(d['id'] for d in db_in_zip['documents']) == [1, 2])
        status = await page.inner_text('#export-library-status')
        print("Summary names the zip and its size:", re.search(r'Outside/Zipped\.zip.*\(\d', status) is not None, repr(status))
        print("No email note for a small zip:", 'too large' not in status)
        print("No Open it for a zip:", not await page.is_visible('#export-library-open-btn'))
        print("Nothing added to Recent libraries:", not any('Zipped' in n for n in await page.evaluate(RECENT)))
        await close_dialog()

        # === Scenario 12: an existing zip is refused ===
        await open_dialog([1], 'Zipped', 'zip')
        await start()
        print("Existing zip refused:", 'already a file' in await page.inner_text('#export-library-status'))
        await close_dialog()

        # === Scenario 13: both ===
        await open_dialog([1, 2], 'Pair', 'both')
        print("Both hint names folder and zip:", 'Pair.zip' in await page.inner_text('#export-library-hint'))
        await start()
        folder_files = await page.evaluate(LIST_IN, 'Pair')
        z = zipfile.ZipFile(io.BytesIO(bytes(await page.evaluate(ZIP_BYTES, 'Pair.zip'))))
        print("Folder and zip hold the same files:", sorted(n[len('Pair/'):] for n in z.namelist()) == folder_files, folder_files)
        same = True
        for f in folder_files:
            same = same and z.read('Pair/' + f).decode() == await page.evaluate(READ_IN, ['Pair', f])
        print("...with the same contents:", same and z.testzip() is None)
        status = await page.inner_text('#export-library-status')
        print("Summary names both:", 'Outside/Pair' in status and 'Outside/Pair.zip' in status)
        print("Open it is offered:", await page.is_visible('#export-library-open-btn'))
        await close_dialog()

        # === Scenario 14: the email-size note, and ZIP64 + UTF-8 end to end ===
        await page.evaluate("() => window.__DEBUG_setZipLimits({ emailBytes: 10, zip64Bytes: 4, zip64Entries: 2 })")
        await open_dialog([1, 2], 'Հարկ 2025', 'zip')
        await start()
        print("Large zip gets the email note:", 'too large' in await page.inner_text('#export-library-status'))
        raw = bytes(await page.evaluate(ZIP_BYTES, 'Հարկ 2025.zip'))
        z = zipfile.ZipFile(io.BytesIO(raw))
        print("ZIP64 zip with Armenian and Chinese names reads back:", b'PK\x06\x06' in raw and z.testzip() is None
              and 'Հարկ 2025/Հարկ 2025.dossiary/files/2_Հաշիվ_发票.pdf' in z.namelist())
        await page.evaluate("() => window.__DEBUG_setZipLimits({ emailBytes: 25 * 1024 * 1024, zip64Bytes: 0xFFFFFFFF, zip64Entries: 0xFFFF })")
        await close_dialog()

        # === Scenario 15: Stop removes a partial zip ===
        await open_dialog([1, 2], 'Stopped', 'zip')
        await page.evaluate("""async () => {
            const h = await (await window.__TEST_ROOT.getDirectoryHandle('files')).getFileHandle('1_a.pdf');
            const orig = h.getFile.bind(h);
            h.getFile = async () => { await new Promise(r => setTimeout(r, 1200)); h.getFile = orig; return orig(); };
            window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT;
        }""")
        await page.click('#export-library-start-btn')
        await page.wait_for_timeout(300)
        await page.click('#export-library-stop-btn')
        await page.wait_for_timeout(1800)
        print("Stopping removes the partial zip:", 'Stopped.zip' not in await page.evaluate(PARENT_NAMES)
              and 'removed' in await page.inner_text('#export-library-status'))
        await close_dialog()

        # === Scenario 16: Move with a zip ===
        await open_dialog([1], 'MoveZip', 'zip')
        await page.check('input[name="export-library-mode"][value="move"]')
        await start()
        src = await page.evaluate(SOURCE_DB)
        flags = {d['id']: d['deleted'] for d in src['documents']}
        print("Moved after the zip was written:", 'MoveZip.zip' in await page.evaluate(PARENT_NAMES) and flags[1] == 1 and not flags[2], flags)
        await close_dialog()

        # === Scenario 17: German labels ===
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        await page.click('#nav-item-all')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.click('#bulk-more-btn')
        await page.click('#bulk-export-library-btn')
        await page.wait_for_timeout(300)
        body = await page.text_content(".modal")  # inner_text would give the CSS-uppercased labels
        print("German output choices:", 'Bibliothek + Dossiary als Ordner' in body and 'Beides: Ordner und .zip-Datei' in body)
        await close_dialog()
        await page.select_option('#lang-select', 'en')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
