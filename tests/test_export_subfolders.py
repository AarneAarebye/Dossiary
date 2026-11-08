import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, re
from playwright.async_api import async_playwright

# Export writes into its own new subfolder of the picked folder.
# Import lists the export subfolders of a picked folder and imports the ticked ones.
# See docs/superpowers/specs/2026-11-08-export-subfolder-design.md (scenarios 1-9).
def doc(i, title, date):
    return {
        "id": i, "title": title, "category": "Home", "subcategory": None, "document_type": "Invoice",
        "date": date, "import_date": "2026-03-01T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }

DOCS = [doc(1, "Stadtwerke", "2026-02-15T00:00:00+00:00"), doc(2, "Water", "2026-01-10T00:00:00+00:00"),
        doc(3, "Missing", "2026-01-01T00:00:00+00:00")]
SEED = {"documents": DOCS, "tags": [], "document_tags": []}
NAME_RE = r'^(.*) · \d{4}-\d{2}-\d{2} \d{2}-\d{2}( \(\d+\))?$'

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        errors = []

        async def start(files=(1, 2)):
            page = await browser.new_page(viewport={'width': 1440, 'height': 900})
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
            await page.evaluate("""async (nums) => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                for(const i of nums){
                    const w = await (await dir.getFileHandle(`${i}_a.pdf`, { create: true })).createWritable();
                    await w.write(new TextEncoder().encode(`%PDF-1.4 doc ${i}`)); await w.close();
                }
            }""", list(files))
            await page.click("#open-btn")
            await page.wait_for_timeout(500)
            return page

        async def run_export(page, ids=(1, 2), title=None, index=True, dest_js="window.__makeEmptyRoot()"):
            for i in ids:
                await page.check(f'.row-select-checkbox[data-id="{i}"]')
            await page.click('#bulk-more-btn'); await page.click('#bulk-export-btn')
            await page.wait_for_timeout(200)
            await page.fill('#export-title', title if title is not None else '')
            if not index: await page.uncheck('#export-index-toggle')
            await page.evaluate("() => { if(!window.__DEST) window.__DEST = %s; window.__NEXT_PICKED_DIR = window.__DEST; }" % dest_js)
            await page.click('#export-start-btn')
            await page.wait_for_timeout(800)

        async def listing(page):
            return await page.evaluate("""async () => {
                const top = {};
                for await (const [k, h] of window.__DEST.entries()){
                    if(h.kind === 'directory'){ const n = []; for await (const [k2] of h.entries()) n.push(k2); top[k] = n.sort(); } else top[k] = null;
                }
                return top;
            }""")

        # === Scenario 1: titled export lands in "{title} · date", the parent holds only it ===
        page = await start()
        await run_export(page, title='Tax 2025')
        top = await listing(page)
        names = list(top)
        m = re.match(NAME_RE, names[0]) if len(names) == 1 else None
        print("The picked folder holds only the new subfolder:", len(names) == 1 and top[names[0]] is not None, names)
        print("Subfolder is named '{title} · YYYY-MM-DD HH-MM':", bool(m) and m.group(1) == 'Tax 2025', names)
        print("Files, index.csv and export-details.json are inside it:",
              top[names[0]] == ['2026-01-10 Water.pdf', '2026-02-15 Stadtwerke.pdf', 'export-details.json', 'index.csv'], top[names[0]])
        status = await page.inner_text('#export-status')
        print("The done message names the subfolder:", f'to “{names[0]}”' in status, repr(status[:100]))

        # Same-minute clash: the name this minute would use already exists -> ' (2)'
        await page.close()

        page = await start()
        # Pre-create the names for this minute and the next, so a minute rollover can't matter.
        await page.evaluate("""async () => {
            const { exportSubfolderName } = window.__DEBUG_exportFolderNames;
            window.__DEST = window.__makeEmptyRoot();
            const now = new Date();
            window.__NAMES = [exportSubfolderName('Tax 2025', now), exportSubfolderName('Tax 2025', new Date(now.getTime() + 60000))];
            for(const n of new Set(window.__NAMES)) await window.__DEST.getDirectoryHandle(n, { create: true });
        }""")
        await run_export(page, title='Tax 2025')
        top = await listing(page)
        names = await page.evaluate("() => [...new Set(window.__NAMES)]")
        made = [k for k in top if k.endswith(' (2)') and k[:-4] in names]
        print("A name clash gets ' (2)' with the files inside:", len(made) == 1 and len(top[made[0]]) == 4, list(top))
        await page.close()

        # === A failure before the loop (permission denied) hands the dialog back ===
        page = await start()
        await page.evaluate("""() => {
            const d = window.__DEST = window.__makeEmptyRoot();
            const orig = d.getDirectoryHandle.bind(d);
            d.getDirectoryHandle = async (n, o) => { if(o && o.create) throw new DOMException('Permission denied', 'NotAllowedError'); return orig(n, o); };
        }""")
        await run_export(page, title='x')
        print("Subfolder creation failing shows the error:", 'Permission denied' in await page.inner_text('#export-status')
              and 'err' in (await page.get_attribute('#export-status', 'class')))
        print("...and the dialog is usable again:", await page.is_enabled('#export-start-btn') and await page.is_enabled('#export-cancel-btn')
              and await page.is_enabled('#modal-close-btn') and await page.is_enabled('#export-index-toggle') and await page.is_enabled('#export-title'))
        await page.click('#export-cancel-btn'); await page.wait_for_timeout(150)
        print("...and Cancel closes it:", await page.locator('#export-start-btn').count() == 0)
        await page.close()

        # === Forbidden characters and no title ===
        page = await start()
        await run_export(page, title='A/B: C*D?')
        names = list(await listing(page))
        m = re.match(NAME_RE, names[0])
        print("Forbidden characters in the title become '-':", bool(m) and m.group(1) == 'A-B- C-D-', names)
        await page.close()

        page = await start()
        await run_export(page, title='')
        names = list(await listing(page))
        print("No title: 'Export YYYY-MM-DD HH-MM':", bool(re.match(r'^Export \d{4}-\d{2}-\d{2} \d{2}-\d{2}$', names[0])), names)
        await page.close()

        # === Scenario 2: index off -> files only; all failing -> no subfolder ===
        page = await start()
        await run_export(page, title='Plain', index=False)
        top = await listing(page); sub = list(top)[0]
        print("Index off: the subfolder holds the files only:", top[sub] == ['2026-01-10 Water.pdf', '2026-02-15 Stadtwerke.pdf'], top[sub])
        await page.close()

        page = await start(files=())
        await run_export(page, ids=(1, 2), title='Nothing')
        top = await listing(page)
        print("Every file failing leaves no subfolder behind:", top == {}, top)
        status = await page.inner_text('#export-status')
        print("...and the failures are reported:", 'Could not export: 2' in status)
        print("...and the message names the picked folder, not the removed subfolder:", 'to “Export ' not in status, repr(status[:80]))
        await page.close()

        # === Scenario 9: helpers ===
        page = await start()
        r = await page.evaluate("""() => {
            const { sanitizeFolderName, exportSubfolderName } = window.__DEBUG_exportFolderNames;
            const d = new Date(2026, 0, 5, 7, 3);
            return {
              long: sanitizeFolderName('x'.repeat(150)).length,
              forb: sanitizeFolderName('a/b\\\\c:d*e?f"g<h>i|j\\u0001k'),
              ws: sanitizeFolderName('  a    b  '),
              empty: sanitizeFolderName('   '),
              cut: exportSubfolderName('y'.repeat(150), d),
              none: exportSubfolderName('', d),
              onlyForbidden: exportSubfolderName('///', d),
              titled: exportSubfolderName('Tax', d),
            };
        }""")
        print("sanitizeFolderName cuts at 100:", r['long'] == 100)
        print("sanitizeFolderName replaces forbidden and control characters:", r['forb'] == 'a-b-c-d-e-f-g-h-i-j-k', r['forb'])
        print("sanitizeFolderName collapses whitespace and trims:", r['ws'] == 'a b' and r['empty'] == '', r)
        print("exportSubfolderName: long title cut before the date part:", r['cut'] == 'y' * 100 + ' · 2026-01-05 07-03', r['cut'])
        print("exportSubfolderName: no title falls back to 'Export':", r['none'] == 'Export 2026-01-05 07-03', r['none'])
        print("exportSubfolderName: '///' is a title of dashes, not empty:", r['onlyForbidden'] == '--- · 2026-01-05 07-03', r['onlyForbidden'])
        print("exportSubfolderName: with a title:", r['titled'] == 'Tax · 2026-01-05 07-03')
        await page.close()

        # === Scenario 7: extra "index (N).csv" / "export-details (N).json" next to index.csv ===
        async def import_folder(page, files, choose_none=True):
            await page.evaluate("""async (files) => {
                const dir = window.__makeEmptyRoot(); dir.name = 'Mixed';
                for(const [n, c] of Object.entries(files)){
                    const w = await (await dir.getFileHandle(n, {create: true})).createWritable();
                    await w.write(new TextEncoder().encode(c)); await w.close();
                }
                window.__NEXT_PICKED_DIR = dir;
            }""", files)
            await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
            await page.click('#import-start-btn'); await page.wait_for_timeout(500)
            if choose_none:
                await page.check('#import-coll-none'); await page.click('#import-run-btn')
            await page.wait_for_timeout(1200)
            lib = await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")
            return await page.inner_text('#import-summary'), lib

        page = await start()
        summary, lib = await import_folder(page, {
            'index.csv': 'File,Title\nnew-a.pdf,Listed A\n',
            'new-a.pdf': '%PDF-1.4 listed a', 'new-b.pdf': '%PDF-1.4 unlisted b',
            'index (2).csv': 'File,Title\nnew-b.pdf,Wrong title\n',
            'export-details (2).json': '{"format": 1, "title": "Other export"}',
        })
        new_docs = [d for d in lib['documents'] if d['id'] > 3]
        titles = sorted(d['title'] for d in new_docs)
        print("7. index.csv plus extra index files: the two documents import as today:", 'Added: 2' in summary and 'With details from index.csv: 1' in summary, repr(summary))
        print("7. ...the extra index files are not documents:", len(new_docs) == 2 and not any('index' in t.lower() or 'export-details' in t.lower() for t in titles), titles)
        print("7. ...and index (2).csv is never read (the unlisted file keeps no title from it):", 'Wrong title' not in titles and 'Listed A' in titles, titles)
        print("7. ...the note names the skipped files:", 'Skipped 2 extra index files from other exports.' in summary, repr(summary))
        await page.close()

        page = await start()
        summary, lib = await import_folder(page, {'new-c.pdf': '%PDF-1.4 c', 'index (3).csv': 'File,Title\n'}, choose_none=False)
        print("7. Without an index.csv, 'index (3).csv' is an ordinary file and no note shows:",
              'Added: 2' in summary and 'extra index' not in summary, repr(summary))
        await page.close()

        # === classifyImportFolder ===
        page = await start()
        r = await page.evaluate("""async () => {
            const put = async (dir, n, c) => { const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); };
            const single = window.__makeEmptyRoot(); await put(single, 'index.csv', 'File\\n'); await single.getDirectoryHandle('sub', {create: true});
            const parent = window.__makeEmptyRoot(); await put(parent, 'loose.pdf', 'x');
            const e1 = await parent.getDirectoryHandle('B export', {create: true});
            await put(e1, 'index.csv', 'File,Title\\na.pdf,A\\nb.pdf,B\\ngone.pdf,G\\n'); await put(e1, 'a.pdf', '1'); await put(e1, 'b.pdf', '2');
            await put(e1, 'export-details.json', '{"format":1,"title":"Tax"}');
            const e2 = await parent.getDirectoryHandle('A export', {create: true}); await put(e2, 'index.csv', 'File\\nz.pdf\\n');
            await put(await parent.getDirectoryHandle('no index', {create: true}), 'c.pdf', '3');
            await put(await parent.getDirectoryHandle('.hidden', {create: true}), 'index.csv', 'File\\n');
            const bad = await parent.getDirectoryHandle('C bad index', {create: true}); await put(bad, 'index.csv', 'Title\\nfoo\\n'); await put(bad, 'd.pdf', '4');
            const plain = window.__makeEmptyRoot(); await put(plain, 'a.pdf', '1'); await put(await plain.getDirectoryHandle('sub', {create: true}), 'b.pdf', '2');
            const c = window.__DEBUG_classifyImportFolder;
            const ex = await c(parent);
            return { single: (await c(single)).kind, plain: (await c(plain)).kind, kind: ex.kind,
                     list: (ex.exports || []).map(e => [e.name, e.fileCount, e.about && e.about.title, !!e.index, e.dirHandle.kind]) };
        }""")
        print("classify: own index.csv -> single:", r['single'] == 'single', r)
        print("classify: neither -> plain:", r['plain'] == 'plain', r)
        print("classify: export subfolders -> exports, sorted, hidden, index-less and unusable-index ones left out:",
              r['kind'] == 'exports' and [e[0] for e in r['list']] == ['A export', 'B export'], r['list'])
        print("classify: file counts are listed rows whose file exists, with the details title:",
              r['list'][1][1:] == [2, 'Tax', True, 'directory'] and r['list'][0][1] == 0, r['list'])
        await page.close()

        # === Importing several exports from one parent folder (scenarios 3, 4, 5, 6, 8) ===
        async def build_parent(page, spec, top=None):
            # spec: {subfolder: {file name: content}}; top: files at the parent's top level
            await page.evaluate("""async ([spec, top]) => {
                const put = async (dir, n, c) => { const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); };
                const parent = window.__makeEmptyRoot(); parent.name = 'Exports';
                for(const [n, c] of Object.entries(top)) await put(parent, n, c);
                for(const [sub, files] of Object.entries(spec)){
                    const d = await parent.getDirectoryHandle(sub, {create: true});
                    for(const [n, c] of Object.entries(files)) await put(d, n, c);
                }
                window.__PARENT = parent; window.__NEXT_PICKED_DIR = parent;
            }""", [spec, top or {}])

        async def open_import(page):
            await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
            await page.click('#import-start-btn'); await page.wait_for_timeout(500)

        async def run_import(page):
            await page.click('#import-run-btn'); await page.wait_for_timeout(1500)

        async def library(page):
            return await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")

        def titles_in(lib, cid):
            ids = {cd['document_id'] for cd in lib['collection_documents'] if cd['collection_id'] == cid}
            return sorted(d['title'] for d in lib['documents'] if d['id'] in ids)

        TAX = 'Tax · 2026-11-01 10-00'
        HOME = 'Export 2026-11-02 09-00'
        TWO_EXPORTS = {
            TAX: {'index.csv': 'File,Title\ntax-a.pdf,Tax A\ntax-b.pdf,Tax B\ngone.pdf,Gone\n',
                  'export-details.json': json.dumps({"format": 1, "title": "Tax <b>2025</b>", "description": "Receipts & <i>bills</i> " + "x" * 280}),
                  'tax-a.pdf': '%PDF-1.4 tax a', 'tax-b.pdf': '%PDF-1.4 tax b'},
            HOME: {'index.csv': 'File,Title\nhome-a.pdf,Home A\n', 'home-a.pdf': '%PDF-1.4 home a', 'extra.pdf': '%PDF-1.4 home extra'},
        }

        # --- 3. Both listed and ticked; two collections, each with only its own documents ---
        page = await start()
        await build_parent(page, TWO_EXPORTS, top={'loose.pdf': '%PDF-1.4 loose'})
        await open_import(page)
        rows = page.locator('.import-export-row')
        print("3. The panel says how many exports the folder holds:", await page.inner_text('#import-exports-found') == 'This folder holds 2 exports.')
        print("3. One row per export, both ticked:", await rows.count() == 2
              and await page.is_checked('#import-export-check-0') and await page.is_checked('#import-export-check-1'))
        row0, row1 = await rows.nth(0).inner_text(), await rows.nth(1).inner_text()
        print("3. A row without details shows the subfolder name and its file count:", HOME in row0 and '1 file listed' in row0, repr(row0))
        print("3. A row with details shows the title and description as text, and the listed files present:",
              'Tax <b>2025</b>' in row1 and 'Receipts & <i>bills</i>' in row1 and '2 files listed' in row1, repr(row1[:80]))
        print("3. ...no HTML from the export is rendered:", await page.locator('#import-exports-list b, #import-exports-list i').count() == 0)
        desc_box = await page.evaluate("() => { const d = document.querySelector('.import-export-desc'); return [d.scrollWidth > d.clientWidth, getComputedStyle(d).textOverflow]; }")
        print("3. The long description is one line with an ellipsis:", desc_box == [True, 'ellipsis'], desc_box)
        print("3. 'A new collection for each export' is the default:", await page.is_checked('#import-coll-new')
              and 'A new collection for each export' in await page.inner_text('#import-options'))
        names = await page.locator('#import-coll-names li').all_inner_texts()
        print("3. The collection names are listed, one per export:", len(names) == 2
              and re.match(r'^Export 2026-11-02 09-00 · \d{4}-\d{2}-\d{2} \d{2}:\d{2}$', names[0]) is not None
              and re.match(r'^Tax <b>2025</b> · \d{4}-\d{2}-\d{2} \d{2}:\d{2}$', names[1]) is not None, names)
        print("3. ...there is no single name field:", await page.locator('#import-coll-name').count() == 0)
        await run_import(page)
        lib = await library(page)
        colls = {c['name']: c for c in lib['collections']}
        print("3. Two collections with the listed names:", sorted(colls) == sorted(names) and all(c['kind'] == 'manual' for c in colls.values()), list(colls))
        print("3. Each holds only its own export's documents:", titles_in(lib, colls[names[1]]['id']) == ['Tax A', 'Tax B']
              and titles_in(lib, colls[names[0]]['id']) == ['Home A'])
        new_titles = sorted(d['title'] for d in lib['documents'] if d['id'] > 3)
        print("3. The parent's own top-level file is not imported:", len(new_titles) == 4 and not any('loose' in t for t in new_titles), new_titles)
        summary = await page.inner_text('#import-summary')
        print("3. The totals add up:", 'Added: 4' in summary and 'With details from index.csv: 3' in summary and 'In the Inbox for review: 1' in summary
              and 'Rows in index.csv without a file: 1' in summary, repr(summary))
        print("3. One block per export, with its counts and collection:", await page.locator('#import-summary .import-export-result').count() == 2
              and f'Added to the collection “{names[1]}”: 2' in summary and f'Added to the collection “{names[0]}”: 1' in summary)
        print("3. The status line names the run:", await page.inner_text('#import-status') == 'Exports imported from “Exports”: 2'
              and 'ok' in await page.get_attribute('#import-status', 'class'))
        print("3. The dialog can be closed again:", await page.inner_text('#import-cancel-btn') == 'Close' and await page.is_enabled('#modal-close-btn'))
        await page.close()

        # --- 3b. Two real exports into one folder, then importing that folder ---
        page = await start()
        await run_export(page, ids=(1,), title='First')
        await page.click('#export-cancel-btn'); await page.wait_for_timeout(150)
        await page.uncheck('.row-select-checkbox[data-id="1"]')  # only doc 2 in the second export
        await run_export(page, ids=(2,), title='Second')
        await page.click('#export-cancel-btn'); await page.wait_for_timeout(150)
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__DEST; }")
        await open_import(page)
        row_texts = await page.locator('.import-export-row').all_inner_texts()
        print("3b. Two real exports are both listed with their titles:", len(row_texts) == 2 and 'First' in row_texts[0] and 'Second' in row_texts[1], row_texts)
        names = await page.locator('#import-coll-names li').all_inner_texts()
        await run_import(page)
        lib = await library(page)
        colls = {c['name']: c['id'] for c in lib['collections']}
        print("3b. Each collection holds the one document of its own export:",
              len(colls) == 2 and titles_in(lib, colls[names[0]]) == ['Stadtwerke'] and titles_in(lib, colls[names[1]]) == ['Water'],
              names, [titles_in(lib, i) for i in colls.values()])
        summary = await page.inner_text('#import-summary')
        print("3b. ...and the totals add up:", summary.startswith('Added: 2\nWith details from index.csv: 2\n')
              and await page.locator('#import-summary .import-export-result').count() == 2, repr(summary))
        await page.close()

        # --- 4. Untick one: only the other is imported; nothing ticked: Import disabled ---
        page = await start()
        await build_parent(page, TWO_EXPORTS)
        await open_import(page)
        await page.uncheck('#import-export-check-0')
        print("4. Unticking drops its collection name from the list:", await page.locator('#import-coll-names li').count() == 1)
        await page.uncheck('#import-export-check-1')
        print("4. Nothing ticked: Import disabled:", await page.is_disabled('#import-run-btn'))
        await page.check('#import-export-check-1')
        print("4. Ticked again: Import enabled:", await page.is_enabled('#import-run-btn'))
        await run_import(page)
        lib = await library(page)
        new_titles = sorted(d['title'] for d in lib['documents'] if d['id'] > 3)
        print("4. Only the ticked export is imported, into one collection:", new_titles == ['Tax A', 'Tax B'] and len(lib['collections']) == 1, new_titles)
        print("4. ...and the summary has one block:", await page.locator('#import-summary .import-export-result').count() == 1
              and await page.inner_text('#import-status') == 'Exports imported from “Exports”: 1')
        await page.close()

        # --- 5. "No collection" and "One existing collection" apply to all ticked exports ---
        page = await start()
        await build_parent(page, TWO_EXPORTS)
        await open_import(page)
        print("5. 'An existing collection' is disabled with no manual collection:", await page.is_disabled('#import-coll-existing'))
        await page.check('#import-coll-none')
        print("5. With 'No collection' the names list is dimmed:", 'disabled' in (await page.get_attribute('#import-coll-names', 'class')))
        await run_import(page)
        lib = await library(page)
        print("5. 'No collection': both exports imported, no collection made:",
              len([d for d in lib['documents'] if d['id'] > 3]) == 4 and lib['collections'] == [], lib['collections'])
        # A collection to choose: the same two exports with new contents, one ticked, "new" (makes one collection)
        spec2 = {TAX: {'index.csv': 'File,Title\nt2.pdf,T2\n', 't2.pdf': '%PDF-1.4 t2'},
                 HOME: {'index.csv': 'File,Title\nh2.pdf,H2\n', 'h2.pdf': '%PDF-1.4 h2'},
                 'Same A': {'index.csv': 'File,Title\ns1.pdf,S1\n', 's1.pdf': '%PDF-1.4 s1', 'export-details.json': '{"format":1,"title":"Same"}'},
                 'Same B': {'index.csv': 'File,Title\ns2.pdf,S2\n', 's2.pdf': '%PDF-1.4 s2', 'export-details.json': '{"format":1,"title":"Same"}'}}
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)
        await build_parent(page, spec2)
        await open_import(page)
        names = await page.locator('#import-coll-names li').all_inner_texts()
        print("5. Two exports with the same title get unique collection names in one run:",
              len(names) == 4 and names[2] == names[1] + ' (2)' and names[1].startswith('Same · '), names)
        for n in (0, 3): await page.uncheck(f'#import-export-check-{n}')
        await run_import(page)
        lib = await library(page)
        same = {c['name']: c['id'] for c in lib['collections']}
        print("5. ...and both are made as listed:", sorted(same) == sorted(names[1:3]) and titles_in(lib, same[names[1]]) == ['S1'] and titles_in(lib, same[names[2]]) == ['S2'], list(same))
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)
        await build_parent(page, {TAX: {'index.csv': 'File,Title\nt3.pdf,T3\n', 't3.pdf': '%PDF-1.4 t3'},
                                  HOME: {'index.csv': 'File,Title\nh3.pdf,H3\n', 'h3.pdf': '%PDF-1.4 h3'}})
        await open_import(page)
        await page.check('#import-coll-existing')
        await page.select_option('#import-coll-select', str(same[names[1]]))
        print("5. 'An existing collection' with a selection enables Import:", await page.is_enabled('#import-run-btn'))
        await run_import(page)
        lib = await library(page)
        print("5. 'One existing collection': both exports' documents land in it, no new collection:",
              titles_in(lib, same[names[1]]) == ['H3', 'S1', 'T3'] and len(lib['collections']) == 2, titles_in(lib, same[names[1]]))
        await page.close()

        # --- 6. What is listed; a plain folder is unchanged ---
        page = await start()
        await build_parent(page, {TAX: TWO_EXPORTS[TAX], 'no index': {'n.pdf': '%PDF-1.4 n'},
                                  '.hidden': {'index.csv': 'File\nh.pdf\n', 'h.pdf': '%PDF-1.4 h'},
                                  'bad index': {'index.csv': 'Title\nfoo\n', 'b.pdf': '%PDF-1.4 b'}},
                          top={'loose.pdf': '%PDF-1.4 loose'})
        await open_import(page)
        rows = await page.locator('.import-export-row').all_inner_texts()
        print("6. Only the subfolder with a usable index.csv is listed:", len(rows) == 1 and 'Tax <b>2025</b>' in rows[0]
              and await page.inner_text('#import-exports-found') == 'This folder holds 1 export.', rows)
        await run_import(page)
        new_titles = sorted(d['title'] for d in (await library(page))['documents'] if d['id'] > 3)
        print("6. Top-level files and other subfolders are not imported:", new_titles == ['Tax A', 'Tax B'], new_titles)
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)
        await build_parent(page, {'no index': {'n.pdf': '%PDF-1.4 n2'}, 'bad index': {'index.csv': 'Title\nfoo\n'}},
                          top={'p1.pdf': '%PDF-1.4 p1', 'p2.pdf': '%PDF-1.4 p2'})
        await open_import(page)
        await page.wait_for_timeout(800)
        summary = await page.inner_text('#import-summary')
        print("6. A folder with neither imports as a plain folder, at once:", await page.locator('.import-export-row').count() == 0
              and 'Added: 2' in summary and 'In the Inbox for review: 2' in summary
              and await page.inner_text('#import-status') == 'Imported from “Exports”.', repr(summary))
        await page.close()

        # --- A document type new at the start counts as new in every export ---
        page = await start()
        await build_parent(page, {
            'L1': {'index.csv': 'File,Title,Type,Unit\nl1.pdf,L1,Lease,4B\n', 'l1.pdf': '%PDF-1.4 l1'},
            'L2': {'index.csv': 'File,Title,Type,Landlord\nl2.pdf,L2,Lease,Ms Smith\n', 'l2.pdf': '%PDF-1.4 l2'},
        })
        await open_import(page)
        await page.check('#import-coll-none')
        await run_import(page)
        lib = await library(page)
        lease = sorted(r['field_name'] for r in lib['document_type_fields'] if r['document_type'] == 'Lease')
        print("A new type gets the fields of both exports:", lease == ['Landlord', 'Unit'], lease)
        await page.close()

        # --- 8. A failing file and a failing export do not stop the next export ---
        page = await start()
        await build_parent(page, {
            'A unreadable': {'index.csv': 'File,Title\nok.pdf,OK\nbroken.pdf,Broken\n', 'ok.pdf': '%PDF-1.4 ok', 'broken.pdf': '%PDF-1.4 broken'},
            'B gone': {'index.csv': 'File,Title\nb.pdf,B\n', 'b.pdf': '%PDF-1.4 b'},
            'C fine': {'index.csv': 'File,Title\nc.pdf,C\n', 'c.pdf': '%PDF-1.4 c'},
        })
        await open_import(page)
        await page.evaluate("""() => {
            const p = window.__PARENT;
            p._children.get('A unreadable')._children.get('broken.pdf').getFile = async () => { throw new Error('Read failed'); };
            p._children.get('B gone').entries = async function*(){ throw new Error('Folder is gone'); };
        }""")
        await run_import(page)
        lib = await library(page)
        new_titles = sorted(d['title'] for d in lib['documents'] if d['id'] > 3)
        print("8. The exports after the failures still import:", new_titles == ['C', 'OK'], new_titles)
        blocks = await page.locator('#import-summary .import-export-result').all_inner_texts()
        print("8. The summary shows all three exports:", len(blocks) == 3, blocks)
        print("8. ...the unreadable file is counted in its export:", 'A unreadable' in blocks[0] and 'Could not import: 1' in blocks[0])
        print("8. ...the failed export says why:", 'B gone' in blocks[1] and 'This export could not be imported: Folder is gone' in blocks[1]
              and await page.locator('#import-summary .import-export-result.failed').count() == 1)
        print("8. ...and the next export has its collection:", 'C fine' in blocks[2] and 'Added to the collection' in blocks[2])
        print("8. The failed file is listed with its export:", 'A unreadable / broken.pdf: Read failed' in await page.inner_text('#import-failed-list'))
        print("8. The status is red and the dialog can be closed:", 'err' in await page.get_attribute('#import-status', 'class')
              and await page.is_enabled('#import-cancel-btn') and await page.is_enabled('#modal-close-btn'))
        await page.keyboard.press('Escape'); await page.wait_for_timeout(150)
        print("8. ...Escape closes it (the run's lock is released):", await page.locator('#import-start-btn').count() == 0)
        await page.close()

        print("No page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
