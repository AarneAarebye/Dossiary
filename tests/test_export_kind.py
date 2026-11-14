import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# One "Export…" entry in the selection bar's More menu. Its dialog starts with
# "Export as: ○ Files in a folder ○ New library"; switching re-renders the other
# dialog for the same documents, the choice is remembered while the page is open,
# and the row is locked while either export runs.
def doc(i, title):
    return {
        "id": i, "title": title, "category": "Home", "subcategory": None, "document_type": "Invoice",
        "date": f"2026-01-{i:02d}T00:00:00+00:00", "import_date": "2026-03-01T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }

SEED = {"documents": [doc(1, "One"), doc(2, "Two"), doc(3, "Three")], "tags": [], "document_tags": []}
results = []
def check(label, ok, extra=''):
    results.append(bool(ok))
    print(f"{label}:", bool(ok), extra if not ok else '')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        errors = []
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'MyLib';")
        await page.evaluate("""async () => {
            const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
            for(const i of [1, 2, 3]){
                const w = await (await dir.getFileHandle(`${i}_a.pdf`, { create: true })).createWritable();
                await w.write(new TextEncoder().encode(`%PDF-1.4 doc ${i}`)); await w.close();
            }
        }""")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        for i in (1, 2):
            await page.check(f'.row-select-checkbox[data-id="{i}"]')
        await page.click('#bulk-more-btn')
        texts = [t.strip() for t in await page.locator('.bulk-collection-option').all_inner_texts()]
        check("The menu has one Export… entry", texts.count('Export…') == 1, texts)
        check("...and no Export as library entry", not any('library' in t.lower() and 'export' in t.lower() for t in texts)
              and await page.locator('#bulk-export-library-btn').count() == 0, texts)

        await page.click('#bulk-export-btn'); await page.wait_for_timeout(200)
        check("The dialog opens on Files in a folder (the default)",
              await page.is_checked('#export-kind-files') and await page.locator('#export-start-btn').count() == 1
              and await page.locator('#export-library-start-btn').count() == 0)
        check("The choice row reads Export as / Files in a folder / New library",
              'Export as' in await page.text_content('.export-kind-row') and 'Files in a folder' in await page.text_content('.export-kind-row')
              and 'New library' in await page.text_content('.export-kind-row'))
        check("The files dialog keeps its title", await page.inner_text('.modal h2') == 'Export documents', await page.inner_text('.modal h2'))
        await page.check('#export-kind-library'); await page.wait_for_timeout(150)
        check("New library switches to the library dialog",
              await page.is_checked('#export-kind-library') and await page.locator('#export-library-start-btn').count() == 1
              and await page.locator('#export-start-btn').count() == 0)
        check("...for the same documents", (await page.inner_text('#export-library-size')).startswith('Documents: 2 '), await page.inner_text('#export-library-size'))
        check("...with its own title", await page.inner_text('.modal h2') == 'Export as library', await page.inner_text('.modal h2'))
        await page.check('#export-kind-files'); await page.wait_for_timeout(150)
        check("Files in a folder switches back, for the same documents", await page.locator('#export-start-btn').count() == 1
              and await page.locator('#export-library-start-btn').count() == 0 and ' 2 ' in await page.inner_text('.modal p'), await page.inner_text('.modal p'))
        await page.check('#export-kind-library'); await page.wait_for_timeout(150)
        await page.click('#export-library-cancel-btn'); await page.wait_for_timeout(150)
        check("Cancel closes it", await page.locator('.modal').count() == 0)

        await page.click('#bulk-more-btn'); await page.click('#bulk-export-btn'); await page.wait_for_timeout(200)
        check("Reopening remembers New library", await page.is_checked('#export-kind-library')
              and await page.locator('#export-library-start-btn').count() == 1)
        await page.keyboard.press('Escape'); await page.wait_for_timeout(150)
        check("Escape closes it", await page.locator('.modal').count() == 0)

        # === The row is locked during a (slow) files export ===
        await page.click('#bulk-more-btn'); await page.click('#bulk-export-btn'); await page.wait_for_timeout(200)
        await page.check('#export-kind-files'); await page.wait_for_timeout(150)
        await page.evaluate("""async () => {
            window.__DEST = window.__makeEmptyRoot(); window.__NEXT_PICKED_DIR = window.__DEST;
            const proto = Object.getPrototypeOf(await window.__makeEmptyRoot().getFileHandle('probe', { create: true }));
            const orig = proto.createWritable;
            window.__SEEN = null;
            proto.createWritable = async function(){
                if(/^2026-.*\\.pdf$/.test(this.name) && window.__SEEN === null){
                    window.__SEEN = [document.getElementById('export-kind-files').disabled, document.getElementById('export-kind-library').disabled];
                }
                return orig.call(this);
            };
        }""")
        await page.click('#export-start-btn')
        await page.wait_for_function("() => /\\b(ok|err)\\b/.test(document.getElementById('export-status').className)", timeout=20000)
        seen = await page.evaluate("() => window.__SEEN")
        check("Files export: the choice row is disabled while it runs", seen == [True, True], seen)
        await page.click('#export-cancel-btn'); await page.wait_for_timeout(150)

        # === ...and during an export as library ===
        await page.click('#bulk-more-btn'); await page.click('#bulk-export-btn'); await page.wait_for_timeout(200)
        check("Reopening remembers Files in a folder", await page.is_checked('#export-kind-files'))
        await page.check('#export-kind-library'); await page.wait_for_timeout(150)
        await page.evaluate("""async () => {
            window.__LIB_PARENT = window.__makeEmptyRoot(); window.__LIB_PARENT.name = 'Outside'; window.__NEXT_PICKED_DIR = window.__LIB_PARENT;
            const files = await window.__TEST_ROOT.getDirectoryHandle('files');
            const h = await files.getFileHandle('1_a.pdf');
            const orig = h.getFile.bind(h);
            window.__SEEN2 = null;
            h.getFile = async () => {
                if(window.__SEEN2 === null) window.__SEEN2 = [document.getElementById('export-kind-files').disabled, document.getElementById('export-kind-library').disabled];
                return orig();
            };
        }""")
        await page.click('#export-library-start-btn')
        await page.wait_for_function("() => /\\b(ok|err)\\b/.test(document.getElementById('export-library-status').className)", timeout=20000)
        seen = await page.evaluate("() => window.__SEEN2")
        check("Export as library: the choice row is disabled while it runs", seen == [True, True], seen)
        await page.click('#export-library-cancel-btn'); await page.wait_for_timeout(150)

        # === German texts ===
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(200)
        await page.click('#bulk-more-btn')
        de_texts = [t.strip() for t in await page.locator('.bulk-collection-option').all_inner_texts()]
        await page.click('#bulk-export-btn'); await page.wait_for_timeout(200)
        row = await page.text_content('.export-kind-row')
        check("German: one Exportieren… entry and the choice row texts",
              de_texts.count('Exportieren…') == 1 and 'Exportieren als' in row and 'Dateien in einem Ordner' in row and 'Neue Bibliothek' in row, (de_texts, row))

        check("No page errors", not errors, errors)
        await browser.close()
        print(f"{sum(results)}/{len(results)} checks passed")
        assert all(results)

asyncio.run(main())
