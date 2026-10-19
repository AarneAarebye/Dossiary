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
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)

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

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
