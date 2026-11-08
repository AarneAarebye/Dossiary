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
        doc(3, "export-details", None, 'json'), doc(4, "index", None, 'csv')]
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
            await page.add_init_script("window.__sub = async (r) => { for await (const [k, h] of r.entries()) if(h.kind === 'directory') return h; };")
            await page.goto(f"file://{APP_PATH}")
            await page.wait_for_timeout(200)
            await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed)});")
            await page.evaluate("""
                async () => {
                    const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                    for(const n of ['1_a.pdf', '2_a.pdf', '3_a.json', '4_a.csv']){
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
            return await page.evaluate("""async () => { const o = {}; const sub = await window.__sub(window.__EXPORT_DEST); for await (const [k, h] of sub.entries()){ if(h.kind === 'file') o[k] = await (await h.getFile()).text(); } return o; }""")

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

        # === Scenario 3c: a document named index.csv is numbered, the index keeps its name ===
        page = await start(SEED_WITH)
        await open_export(page, ids=(1, 4))
        await run_export(page)
        files = await dest_files(page)
        print("A document named index.csv is numbered, the index keeps its name:",
              'index (2).csv' in files and files['index (2).csv'].startswith('%PDF') and not files.get('index.csv', '').startswith('%PDF'), list(files))
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

        # === Scenario 6: HTML special characters stay text, in the dialog and in the file ===
        SPECIAL = '<b>x</b> & "q"'
        page = await start({"documents": DOCS, "tags": [], "document_tags": [],
                            "settings": [{"key": "library_title", "value": SPECIAL}, {"key": "library_description", "value": SPECIAL}]})
        await open_export(page)
        print("Special characters: the prefill is the raw text:",
              await page.input_value('#export-title') == SPECIAL and await page.input_value('#export-description') == SPECIAL)
        print("Special characters: no markup injected into the dialog:", await page.locator('.modal b').count() == 0)
        await run_export(page)
        d = json.loads((await dest_files(page)).get('export-details.json', '{}'))
        print("Special characters: written unchanged:", d.get('title') == SPECIAL and d.get('description') == SPECIAL, d)
        await page.close()

        # === Scenario 7: the details file only exists when there are texts ===
        page = await start(SEED_WITH)
        await open_export(page)
        await run_export(page)
        d = json.loads((await dest_files(page)).get('export-details.json', '{}'))
        print("An export with texts writes export-details.json:",
              d.get('title') == 'Birgit’s papers' and d.get('description') == 'House and car', d)
        await page.close()
        page = await start(SEED_WITHOUT)
        await open_export(page)
        await run_export(page)
        files = await dest_files(page)
        print("No details file when both texts are empty:", 'export-details.json' not in files and 'index.csv' in files, list(files))
        await page.close()

        # === Scenario 8: the name stays reserved when no details file is written ===
        page = await start(SEED_WITHOUT)
        await open_export(page, ids=(1, 3))
        await run_export(page)
        files = await dest_files(page)
        print("Both texts empty: the document named export-details.json is numbered, no details file:",
              'export-details (2).json' in files and files['export-details (2).json'].startswith('%PDF') and 'export-details.json' not in files, list(files))
        await page.close()

        # === Scenario 9: a failing details write does not block the summary ===
        page = await start(SEED_WITH)
        await open_export(page)
        await run_export(page, "const orig = window.__EXPORT_DEST.getDirectoryHandle.bind(window.__EXPORT_DEST); window.__EXPORT_DEST.getDirectoryHandle = async (n, o) => { const d = await orig(n, o); if(o && o.create){ const h = await d.getFileHandle('export-details.json', { create: true }); h.readOnly = true; } return d; };")
        files = await dest_files(page)
        status = await page.inner_text('#export-status')
        print("Failing details write: documents and index.csv are exported:",
              '1_a.pdf' in ''.join(files) or any(k.endswith('.pdf') for k in files), list(files))
        print("Failing details write: index.csv written:", 'index.csv' in files)
        print("Failing details write: done text plus the failure sentence:",
              'Exported 2' in status and 'The title and description file could not be written.' in status, repr(status))
        print("Failing details write: shown as an error:", 'err' in (await page.get_attribute('#export-status', 'class')))
        await page.close()

        # ================= The import side (spec scenarios 4-8) =================
        STAMP = r' · \d{4}-\d{2}-\d{2} \d{2}:\d{2}$'

        async def import_folder(page, name, files):
            """files: {filename: text}. Builds the folder, opens Import, picks it."""
            await page.evaluate("""async ([name, files]) => {
                const dir = window.__makeEmptyRoot(); dir.name = name;
                for(const [n, c] of Object.entries(files)){ const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); }
                window.__NEXT_PICKED_DIR = dir;
            }""", [name, files])
            await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
            await page.click('#import-start-btn'); await page.wait_for_timeout(400)

        async def close_import(page):
            await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === Import 4: export from the library, import the folder elsewhere ===
        page = await start(SEED_WITH)
        await open_export(page)
        await page.fill('#export-title', '<b>x</b> Birgit’s papers')
        await run_export(page)
        exported = await dest_files(page)
        await page.close()
        print("Import 4: the export wrote a details file to import:", 'export-details.json' in exported and 'index.csv' in exported, list(exported))

        page = await start({"documents": [], "tags": [], "document_tags": []})
        await import_folder(page, 'Out', exported)
        opts = await page.inner_text('#import-options')
        print("Import 4: the panel shows \"About this export\":", 'About this export' in opts, repr(opts))
        print("Import 4: ...the title, as text:", '<b>x</b> Birgit’s papers' in opts and '&lt;b&gt;x&lt;/b&gt;' in await page.inner_html('#import-options'))
        print("Import 4: ...and the description:", 'House and car' in opts)
        import re as _re
        name = await page.input_value('#import-coll-name')
        print("Import 7: \"A new collection\" is the default:", await page.is_checked('#import-coll-new') and await page.is_enabled('#import-coll-name') and await page.is_enabled('#import-run-btn'))
        print("Import 7: ...named after the export title, with date and time:", bool(_re.match(_re.escape('<b>x</b> Birgit’s papers') + STAMP, name)), repr(name))
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        rows = await library(page)
        print("Import 4: exactly the exported files become documents (no json):",
              sorted(d['title'] for d in rows['documents']) == ['Stadtwerke', 'Water'], [d['title'] for d in rows['documents']])
        colls = [c for c in rows['collections'] if c['name'] == name]
        print("Import 4: the collection holds both:", len(colls) == 1 and len([cd for cd in rows['collection_documents'] if cd['collection_id'] == colls[0]['id']]) == 2)
        await close_import(page)

        # === Round trip: documents named index.csv / export-details.json come back ===
        # Export numbers them "index (2).csv" / "export-details (2).json"; the index
        # lists those names, so the import takes them as documents, not as extra
        # index files of another export.
        rt = await start(SEED_WITH)
        await open_export(rt, ids=(1, 3, 4))
        await run_export(rt)
        exported = await dest_files(rt)
        await rt.close()
        print("Round trip: the export numbered both documents:",
              'index (2).csv' in exported and 'export-details (2).json' in exported and 'index.csv' in exported, list(exported))
        for extra, label in (({}, 'listed only'), ({'index (3).csv': 'File,Title\n'}, 'plus an unlisted index (3).csv')):
            rt = await start({"documents": [], "tags": [], "document_tags": []})
            await import_folder(rt, 'Out', {**exported, **extra})
            await rt.click('#import-run-btn'); await rt.wait_for_timeout(1200)
            rows = await library(rt)
            summary = await rt.inner_text('#import-summary')
            titles = sorted(d['title'] for d in rows['documents'])
            print(f"Round trip ({label}): all three documents imported with their details:",
                  titles == ['Stadtwerke', 'export-details', 'index'] and 'With details from index.csv: 3' in summary
                  and 'Rows in index.csv without a file' not in summary, titles, repr(summary))
            if extra:
                print(f"Round trip ({label}): the unlisted one is skipped with the note:", 'Skipped 1 extra index files from other exports.' in summary, repr(summary))
            else:
                print(f"Round trip ({label}): no extra-index note:", 'extra index' not in summary, repr(summary))
            await rt.close()

        # === Import 5: no block without a usable details file ===
        index = 'File,Title\nm.pdf,Em\n'
        for label, extra, fname in [('no details file', {}, 'm1'), ('malformed', {'export-details.json': '{nope'}, 'm2'),
                                     ('empty texts', {'export-details.json': '{"format":1,"title":"","description":"   "}'}, 'm3'),
                                     ('not an object', {'export-details.json': '"just text"'}, 'm4')]:
            before = len((await library(page))['documents'])
            await import_folder(page, fname, {'m.pdf': '%PDF-1.4 ' + fname, 'index.csv': index, **extra})
            print(f"Import 5 ({label}): the panel shows, without the block:",
                  await page.locator('#import-options').is_visible() and 'About this export' not in await page.inner_text('#import-options') and await page.locator('.import-about').count() == 0)
            await page.click('#import-run-btn'); await page.wait_for_timeout(1000)
            print(f"Import 5 ({label}): one document added:", 'Added: 1' in await page.inner_text('#import-summary') and len((await library(page))['documents']) == before + 1)
            await close_import(page)

        # === Import 6: details file but no index.csv: imports at once, json skipped ===
        before = len((await library(page))['documents'])
        await import_folder(page, 'NoIndex', {'n.pdf': '%PDF-1.4 n', 'export-details.json': '{"format":1,"title":"T","description":""}'})
        await page.wait_for_timeout(800)
        print("Import 6: no options panel, imported at once:", not await page.locator('#import-options').is_visible() and 'Added: 1' in await page.inner_text('#import-summary'))
        print("Import 6: the json is not a document:", len((await library(page))['documents']) == before + 1)
        await close_import(page)
        # Only an index and the details file: nothing to import.
        await import_folder(page, 'OnlyMeta', {'index.csv': index, 'export-details.json': '{"format":1,"title":"T","description":""}'})
        print("Import 6: a folder with only index.csv and the details file has no files:", 'no files' in await page.inner_text('#import-status'))
        await close_import(page)

        # === Import 7: without a title, the folder name ===
        await import_folder(page, 'Folder Seven', {'s.pdf': '%PDF-1.4 seven', 'index.csv': 'File,Title\ns.pdf,Seven\n',
                                                   'export-details.json': '{"format":1,"title":"","description":"Only words"}'})
        name = await page.input_value('#import-coll-name')
        print("Import 7: a description alone still shows the block:", 'Only words' in await page.inner_text('#import-options') and await page.locator('.import-about .doc-title').count() == 0)
        print("Import 7: no title: the folder name, with date and time:", bool(_re.match('Folder Seven' + STAMP, name)), repr(name))
        await close_import(page)

        # === Import 8: a 200-character title is cut to 60 ===
        await import_folder(page, 'Long', {'l.pdf': '%PDF-1.4 long', 'index.csv': 'File,Title\nl.pdf,Long\n',
                                           'export-details.json': json.dumps({'format': 1, 'title': 'y' * 200, 'description': 'z' * 400})})
        print("Import 8: the title is cut to 60:", await page.inner_text('.import-about .doc-title') == 'y' * 60)
        print("Import 8: the description is cut to 300:", ('z' * 300) in await page.inner_text('.import-about') and ('z' * 301) not in await page.inner_text('.import-about'))
        print("Import 8: the collection name uses the cut title:", bool(_re.match('y' * 60 + STAMP, await page.input_value('#import-coll-name'))))
        await close_import(page)
        await page.close()

        print("No page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
