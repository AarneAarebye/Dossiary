import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Export selected documents: their files are copied into a folder the person
# picks, named "<date> <title>", with an optional index.csv; the library
# itself never changes, and a folder inside it is refused.
def doc(i, title, date, **extra):
    d = {
        "id": i, "title": title, "category": "Home", "subcategory": None, "document_type": "Invoice",
        "date": date, "import_date": "2026-03-01T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }
    d.update(extra)
    return d

SEED = {
    "documents": [
        doc(1, "Stadtwerke", "2026-02-15T00:00:00+00:00", notes='Paid; "on time"'),
        doc(2, "Stadtwerke", "2026-02-15T00:00:00+00:00"),                 # same name -> numbered
        doc(3, "Insurance: policy/2026", "2026-01-10T00:00:00+00:00"),     # characters not allowed in file names
        doc(4, "Missing file", "2026-01-01T00:00:00+00:00"),
        doc(5, "Not selected", "2026-01-01T00:00:00+00:00"),
    ],
    "tags": [{"id": 1, "name": "tax"}], "document_tags": [{"document_id": 1, "tag_id": 1}],
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 5, "name": "Contract no", "type": "text", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 2, "value": "73.50"},
        {"document_id": 1, "field_id": 3, "value": "EUR"},
        {"document_id": 3, "field_id": 5, "value": "K-99"},
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
        await page.evaluate("""
            async () => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                for(const i of [1, 2, 3, 5]){
                    const h = await dir.getFileHandle(`${i}_a.pdf`, { create: true });
                    const w = await h.createWritable(); await w.write(new TextEncoder().encode(`%PDF-1.4 doc ${i}`)); await w.close();
                }
                // The export destination: a separate folder, which already holds a same-named file.
                window.__EXPORT_DEST = window.__makeEmptyRoot();
                window.__EXPORT_DEST.name = 'For advisor';
                const h = await window.__EXPORT_DEST.getFileHandle('2026-02-15 Stadtwerke.pdf', { create: true });
                const w = await h.createWritable(); await w.write(new TextEncoder().encode('already here')); await w.close();
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(500)
        files_before = await page.evaluate("async () => { const d = await window.__TEST_ROOT.getDirectoryHandle('files'); const n = []; for await (const [k] of d.entries()) n.push(k); return n.sort(); }")

        for i in [1, 2, 3, 4]:
            await page.check(f'.row-select-checkbox[data-id="{i}"]')
        await page.wait_for_timeout(150)
        print("Export button in the bulk-action bar:", await page.locator('#bulk-export-btn').is_visible())
        await page.click('#bulk-export-btn')
        await page.wait_for_timeout(200)
        print("Dialog counts the 4 selected documents:", '4 selected' in await page.inner_text('.modal'))

        # === Scenario 1: a folder inside the library is refused ===
        await page.evaluate("async () => { window.__NEXT_PICKED_DIR = await window.__TEST_ROOT.getDirectoryHandle('files'); }")
        await page.click('#export-start-btn')
        await page.wait_for_timeout(300)
        print("A folder inside the library is refused:", 'inside' in await page.inner_text('#export-status') and await page.locator('#export-start-btn').is_enabled())

        # === Scenario 2: exporting to a real folder ===
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__EXPORT_DEST; }")
        await page.click('#export-start-btn')
        await page.wait_for_timeout(800)
        status = await page.inner_text('#export-status')
        print("Reports 3 exported and 1 that couldn't be:", 'Exported 3 files to “For advisor”' in status and 'Could not export: 1.' in status, repr(status[:120]))
        print("...naming the one that failed:", 'Missing file' in await page.inner_text('#export-failed-list'))
        names = await page.evaluate("async () => { const n = []; for await (const [k] of window.__EXPORT_DEST.entries()) n.push(k); return n.sort(); }")
        print("Files named by date and title, clashes numbered, unsafe characters replaced:",
              names == ['2026-01-10 Insurance- policy-2026.pdf', '2026-02-15 Stadtwerke (2).pdf', '2026-02-15 Stadtwerke (3).pdf', '2026-02-15 Stadtwerke.pdf', 'index.csv'], names)
        existing = await page.evaluate("async () => await (await (await window.__EXPORT_DEST.getFileHandle('2026-02-15 Stadtwerke.pdf')).getFile()).text()")
        print("A file already in the folder is left alone:", existing == 'already here')
        copied = await page.evaluate("async () => await (await (await window.__EXPORT_DEST.getFileHandle('2026-02-15 Stadtwerke (2).pdf')).getFile()).text()")
        print("The copy has the document's own bytes:", copied == '%PDF-1.4 doc 1')
        csv = await page.evaluate("async () => await (await (await window.__EXPORT_DEST.getFileHandle('index.csv')).getFile()).text()")
        lines = csv.lstrip('﻿').strip().split('\r\n')
        print("index.csv: a header plus one row per exported file:", len(lines) == 4, len(lines))
        print("...English uses ',' and quotes values that need it:", lines[0].startswith('File,Title,Date') and '"Paid; ""on time"""' in csv)
        print("...with amount, currency, tags and custom fields:", '73.50,EUR' in csv and 'tax' in csv and 'Contract no' in lines[0] and 'K-99' in csv)
        files_after = await page.evaluate("async () => { const d = await window.__TEST_ROOT.getDirectoryHandle('files'); const n = []; for await (const [k] of d.entries()) n.push(k); return n.sort(); }")
        print("Nothing in the library's files/ changed:", files_before == files_after)
        await page.click('#export-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 3: German uses ';', and index.csv can be switched off ===
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        await page.evaluate("() => { window.__EXPORT_DE = window.__makeEmptyRoot(); window.__NEXT_PICKED_DIR = window.__EXPORT_DE; }")
        await page.click('#bulk-export-btn')
        await page.wait_for_timeout(200)
        await page.click('#export-start-btn')
        await page.wait_for_timeout(800)
        csv_de = await page.evaluate("async () => await (await (await window.__EXPORT_DE.getFileHandle('index.csv')).getFile()).text()")
        print("German index.csv uses ';':", csv_de.lstrip('﻿').startswith('Datei;'))
        await page.click('#export-cancel-btn')
        await page.wait_for_timeout(150)
        await page.evaluate("() => { window.__EXPORT_NO = window.__makeEmptyRoot(); window.__NEXT_PICKED_DIR = window.__EXPORT_NO; }")
        await page.click('#bulk-export-btn')
        await page.wait_for_timeout(200)
        await page.uncheck('#export-index-toggle')
        await page.click('#export-start-btn')
        await page.wait_for_timeout(800)
        names_no = await page.evaluate("async () => { const n = []; for await (const [k] of window.__EXPORT_NO.entries()) n.push(k); return n; }")
        print("Without the index option, only the files are written:", 'index.csv' not in names_no and len(names_no) == 3, names_no)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
