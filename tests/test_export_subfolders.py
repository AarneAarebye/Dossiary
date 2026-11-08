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
        # Pre-create the subfolder this minute would use, to make the clash deterministic.
        await page.evaluate("""async () => {
            window.__DEST = window.__makeEmptyRoot();
            window.__NAME = window.__DEBUG_exportFolderNames.exportSubfolderName('Tax 2025', new Date());
            await window.__DEST.getDirectoryHandle(window.__NAME, { create: true });
        }""")
        await run_export(page, title='Tax 2025')
        top = await listing(page)
        base = await page.evaluate("() => window.__NAME")
        print("A name clash gets ' (2)':", f'{base} (2)' in top and top[base] == [] and len(top[f'{base} (2)']) == 4, list(top))
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
        print("...and the failures are reported:", 'Could not export: 2' in await page.inner_text('#export-status'))
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

        print("No page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
