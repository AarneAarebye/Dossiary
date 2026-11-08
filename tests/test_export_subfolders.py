import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, re
from playwright.async_api import async_playwright

# Export writes into its own new subfolder of the picked folder.
# See docs/superpowers/specs/2026-11-08-export-subfolder-design.md (scenarios 1, 2, 9).
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

        # === classifyImportFolder (the 'exports' kind is classified, not yet acted on) ===
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
            const plain = window.__makeEmptyRoot(); await put(plain, 'a.pdf', '1'); await put(await plain.getDirectoryHandle('sub', {create: true}), 'b.pdf', '2');
            const c = window.__DEBUG_classifyImportFolder;
            const ex = await c(parent);
            return { single: (await c(single)).kind, plain: (await c(plain)).kind, kind: ex.kind,
                     list: (ex.exports || []).map(e => [e.name, e.fileCount, e.about && e.about.title, !!e.index, e.dirHandle.kind]) };
        }""")
        print("classify: own index.csv -> single:", r['single'] == 'single', r)
        print("classify: neither -> plain:", r['plain'] == 'plain', r)
        print("classify: export subfolders -> exports, sorted, hidden and index-less ones left out:",
              r['kind'] == 'exports' and [e[0] for e in r['list']] == ['A export', 'B export'], r['list'])
        print("classify: file counts are listed rows whose file exists, with the details title:",
              r['list'][1][1:] == [2, 'Tax', True, 'directory'] and r['list'][0][1] == 0, r['list'])
        await page.close()

        print("No page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
