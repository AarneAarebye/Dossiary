import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# The export dialog's optional title and description: prefilled from the
# library's own, editable for this export only, written to export-details.json
# next to index.csv. See docs/superpowers/specs/2026-11-07-export-title-design.md.
def doc(i, title, date, ext='pdf'):
    return {
        "id": i, "title": title, "category": "Home", "subcategory": None, "document_type": "Invoice",
        "date": date, "import_date": "2026-03-01T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.{ext}", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }

DOCS = [doc(1, "Stadtwerke", "2026-02-15T00:00:00+00:00"), doc(2, "Water", "2026-01-10T00:00:00+00:00"),
        doc(3, "export-details", None, 'json')]
SEED_WITH = {"documents": DOCS, "tags": [], "document_tags": [],
             "settings": [{"key": "library_title", "value": "Birgit’s papers"}, {"key": "library_description", "value": "House and car"}]}
SEED_WITHOUT = {"documents": DOCS, "tags": [], "document_tags": []}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        errors = []

        async def start(seed, width=1440):
            page = await browser.new_page(viewport={'width': width, 'height': 900})
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
            await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed)});")
            await page.evaluate("""
                async () => {
                    const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                    for(const n of ['1_a.pdf', '2_a.pdf', '3_a.json']){
                        const w = await (await dir.getFileHandle(n, { create: true })).createWritable();
                        await w.write(new TextEncoder().encode('%PDF-1.4 ' + n)); await w.close();
                    }
                }
            """)
            await page.click("#open-btn")
            await page.wait_for_timeout(500)
            return page

        async def library(page):
            return await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")

        async def open_export(page, ids=(1, 2)):
            for i in ids:
                await page.check(f'.row-select-checkbox[data-id="{i}"]')
            await page.click('#bulk-more-btn')
            await page.click('#bulk-export-btn')
            await page.wait_for_timeout(200)

        async def run_export(page, dest_setup=""):
            await page.evaluate("async () => { window.__EXPORT_DEST = window.__makeEmptyRoot(); window.__EXPORT_DEST.name = 'Out'; %s window.__NEXT_PICKED_DIR = window.__EXPORT_DEST; }" % dest_setup)
            await page.click('#export-start-btn')
            await page.wait_for_timeout(800)

        async def dest_files(page):
            return await page.evaluate("""async () => { const o = {}; for await (const [k, h] of window.__EXPORT_DEST.entries()){ if(h.kind === 'file') o[k] = await (await h.getFile()).text(); } return o; }""")

        # === Scenario 1: prefilled from the library ===
        page = await start(SEED_WITH)
        await open_export(page)
        print("Title and description prefilled from the library:",
              await page.input_value('#export-title') == 'Birgit’s papers' and await page.input_value('#export-description') == 'House and car')
        print("Inputs carry maxlength 60 / 300:",
              await page.get_attribute('#export-title', 'maxlength') == '60' and await page.get_attribute('#export-description', 'maxlength') == '300')
        print("The hint is shown:", 'Saved next to index.csv and shown when the folder is imported. The library itself is not changed.' in await page.inner_text('.modal'))
        # === Scenario 3a: index toggle disables the fields ===
        await page.uncheck('#export-index-toggle')
        print("Index off: both fields disabled:", await page.is_disabled('#export-title') and await page.is_disabled('#export-description'))
        await run_export(page)
        files = await dest_files(page)
        print("...and no details file, no index:", 'export-details.json' not in files and 'index.csv' not in files, list(files))
        await page.close()

        # library without texts
        page = await start(SEED_WITHOUT)
        await open_export(page)
        print("Library without texts: both fields empty:", await page.input_value('#export-title') == '' and await page.input_value('#export-description') == '')

        # === Scenario 3b: both cleared -> no file ===
        await run_export(page)
        files = await dest_files(page)
        print("Both fields empty: no export-details.json:", 'export-details.json' not in files and 'index.csv' in files, list(files))
        await page.close()

        # === Scenario 2: edited texts are written, library unchanged ===
        page = await start(SEED_WITH)
        before = (await library(page))['settings']
        await open_export(page)
        await page.fill('#export-title', 'Annual\nreview  2025')
        await page.fill('#export-description', 'Taxes for\nthe   year  ')
        await run_export(page)
        files = await dest_files(page)
        d = json.loads(files.get('export-details.json', '{}'))
        print("export-details.json written with format 1 and cleaned texts:",
              d == {'format': 1, 'title': 'Annual review 2025', 'description': 'Taxes for the year'}, d)
        print("The library's settings are unchanged:", (await library(page))['settings'] == before)
        print("Fields disabled while/after the run:", await page.is_disabled('#export-title'))
        await page.close()

        # === Scenario 3c: destination already holds an index.csv ===
        page = await start(SEED_WITH)
        await open_export(page)
        await run_export(page, "const w = await (await window.__EXPORT_DEST.getFileHandle('index.csv', { create: true })).createWritable(); await w.write('old'); await w.close();")
        files = await dest_files(page)
        print("Existing index.csv: new index numbered, no details file:",
              'index (2).csv' in files and files.get('index.csv') == 'old' and 'export-details.json' not in files, list(files))
        await page.close()

        # === Scenario 4: a 100-character title is cut to 60 ===
        page = await start(SEED_WITHOUT)
        await open_export(page)
        await page.evaluate("document.getElementById('export-title').value = 'x'.repeat(100)")
        await run_export(page)
        d = json.loads((await dest_files(page)).get('export-details.json', '{}'))
        print("A 100-character title is cut to 60:", d.get('title') == 'x' * 60 and d.get('description') == '', len(d.get('title', '')))
        await page.close()

        # === Scenario 5: a document that would be named export-details.json is numbered ===
        page = await start(SEED_WITH)
        await open_export(page, ids=(1, 3))
        await run_export(page)
        files = await dest_files(page)
        d = json.loads(files.get('export-details.json', '{}'))
        print("A document named export-details.json is numbered, the details file keeps its name:",
              'export-details (2).json' in files and files['export-details (2).json'].startswith('%PDF') and d.get('format') == 1, list(files))
        await page.close()

        print("No page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
