import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# While an export runs, its Cancel button reads Stop. Stop ends the export after the
# file being copied: that file is complete, the subfolder is kept with an index.csv of
# exactly the copied files, and the dialog then behaves as after a finished export.
N = 40
STOP_AT = 3  # Stop is clicked while the 3rd export file is being written

def doc(i):
    return {
        "id": i, "title": f"Doc {i:02d}", "category": "Home", "subcategory": None, "document_type": "Invoice",
        "date": f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00", "import_date": "2026-03-01T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }

DOCS = [doc(i) for i in range(1, N + 1)]
SEED = {"documents": DOCS, "tags": [], "document_tags": []}
results = []

def check(label, ok, extra=''):
    results.append(bool(ok))
    print(f"{label}:", bool(ok), extra if not ok else '')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        errors = []

        async def start():
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
            await page.evaluate("""async (n) => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                for(let i = 1; i <= n; i++){
                    const w = await (await dir.getFileHandle(`${i}_a.pdf`, { create: true })).createWritable();
                    await w.write(new TextEncoder().encode(`%PDF-1.4 doc ${i} ` + 'x'.repeat(200))); await w.close();
                }
            }""", N)
            await page.click("#open-btn")
            await page.wait_for_timeout(500)
            return page

        async def open_export(page):
            for i in range(1, N + 1):
                box = page.locator(f'.row-select-checkbox[data-id="{i}"]')
                if not await box.is_checked(): await box.check()
            await page.click('#bulk-more-btn'); await page.click('#bulk-export-btn')
            await page.wait_for_timeout(200)
            await page.fill('#export-title', 'Stop test')
            await page.evaluate("() => { window.__DEST = window.__makeEmptyRoot(); window.__NEXT_PICKED_DIR = window.__DEST; }")

        async def wait_done(page):
            await page.wait_for_function("() => { const s = document.getElementById('export-status'); return s && /\\b(ok|err)\\b/.test(s.className); }", timeout=20000)

        async def subfolder(page):
            return await page.evaluate("""async () => {
                const out = {};
                for await (const [k, h] of window.__DEST.entries()){
                    if(h.kind !== 'directory'){ out[k] = null; continue; }
                    const files = {};
                    for await (const [k2, f] of h.entries()) files[k2] = await (await f.getFile()).text();
                    out[k] = files;
                }
                return out;
            }""")

        def csv_files(text):
            lines = [l for l in text.replace('\r\n', '\n').split('\n') if l.strip()]
            sep = ';' if ';' in lines[0] and ',' not in lines[0] else ','
            return [l.split(sep)[0].strip('"') for l in lines[1:]]

        # === An export that finishes normally is unchanged ===
        page = await start()
        await open_export(page)
        await page.click('#export-start-btn')
        await wait_done(page)
        top = await subfolder(page)
        names = list(top)
        files = top[names[0]] if names else {}
        full_files = files  # what a complete export writes, to compare the stopped one against
        pdfs = sorted(k for k in files if k.endswith('.pdf'))
        check("A full export copies all files", len(pdfs) == N, len(pdfs))
        check("...index.csv lists them all", sorted(csv_files(files.get('index.csv', 'x\n'))) == pdfs)
        status = await page.inner_text('#export-status')
        check("...and says Exported", status.strip() == f'Exported {N} files to “{names[0] if names else ""}”.', status)
        check("...and the button reads Close", await page.inner_text('#export-cancel-btn') == 'Close')
        await page.click('#export-cancel-btn'); await page.wait_for_timeout(150)
        check("...which closes the dialog", await page.locator('#export-start-btn').count() == 0)
        await page.close()

        # === Stop during a 40-file export ===
        page = await start()
        await open_export(page)
        # Hook: on the STOP_AT-th file the export creates, note the buttons' state and click Stop
        # (twice: the second click must do nothing), while that file is still being written.
        await page.evaluate("""async (stopAt) => {
            const proto = Object.getPrototypeOf(await window.__makeEmptyRoot().getFileHandle('probe', { create: true }));
            const orig = proto.createWritable;
            window.__HOOK = { count: 0 };
            proto.createWritable = async function(){
                const h = window.__HOOK;
                if(h.armed && /\\.pdf$/.test(this.name) && ++h.count === stopAt){
                    const b = document.getElementById('export-cancel-btn');
                    h.text = b.textContent; h.enabled = !b.disabled;
                    h.closeDisabled = document.getElementById('modal-close-btn').disabled;
                    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
                    h.openAfterEscape = !!document.getElementById('export-start-btn');
                    b.click(); b.click();
                    h.disabledAfterClick = b.disabled;
                    h.openAfterStop = !!document.getElementById('export-start-btn');
                }
                return orig.call(this);
            };
            window.__HOOK.armed = true;
        }""", STOP_AT)
        await page.click('#export-start-btn')
        await wait_done(page)
        hook = await page.evaluate("() => window.__HOOK")
        check("During the run the Cancel button reads Stop and is enabled", hook.get('text') == 'Stop' and hook.get('enabled'), hook)
        check("...the ✕ is disabled while running", hook.get('closeDisabled'), hook)
        check("...Escape does not close the dialog while running", hook.get('openAfterEscape'), hook)
        check("...Stop keeps the dialog open and disables itself (a second click does nothing)",
              hook.get('openAfterStop') and hook.get('disabledAfterClick'), hook)
        top = await subfolder(page)
        names = list(top)
        check("The export subfolder is kept", len(names) == 1 and top[names[0]] is not None, names)
        files = top[names[0]] if names else {}
        pdfs = sorted(k for k in files if k.endswith('.pdf'))
        check(f"The export ended early: {STOP_AT} files copied (the one being written finished)", len(pdfs) == STOP_AT, pdfs)
        complete = all(files[k] == full_files.get(k) for k in pdfs)
        check("No copied file is partial (each equals the same file of a complete export)", complete and len(pdfs) > 0, {k: len(v) for k, v in files.items()})
        check("index.csv and export-details.json are written", 'index.csv' in files and 'export-details.json' in files, list(files))
        listed = sorted(csv_files(files.get('index.csv', 'x\n')))
        check("index.csv lists exactly the copied files", listed == pdfs, (listed, pdfs))
        status = await page.inner_text('#export-status')
        cls = await page.get_attribute('#export-status', 'class')
        expected = f'Stopped after {STOP_AT} of {N} files. They are in “{names[0] if names else ""}”, which is marked as incomplete.'
        check("The message says it stopped, how many and where", status.strip() == expected and 'ok' in cls, (status, cls))
        check("Start is hidden and the Cancel button reads Close",
              not await page.is_visible('#export-start-btn') and await page.inner_text('#export-cancel-btn') == 'Close'
              and await page.is_enabled('#export-cancel-btn') and await page.is_enabled('#modal-close-btn'))
        await page.click('#export-cancel-btn'); await page.wait_for_timeout(150)
        check("Close closes the dialog", await page.locator('#export-start-btn').count() == 0)
        await page.close()

        # === Stop while the 1st file is being read: that file still finishes ===
        page = await start()
        await open_export(page)
        await page.evaluate("""async () => {
            const proto = Object.getPrototypeOf(await window.__makeEmptyRoot().getFileHandle('probe', { create: true }));
            const origGet = proto.getFile;
            let done = false;
            proto.getFile = async function(){
                if(!done && /_a\\.pdf$/.test(this.name) && document.getElementById('export-status')?.className.includes('busy')){
                    done = true; document.getElementById('export-cancel-btn').click();
                }
                return origGet.call(this);
            };
        }""")
        await page.click('#export-start-btn')
        await wait_done(page)
        top = await subfolder(page)
        files = list(top.values())[0] if top else {}
        pdfs = [k for k in (files or {}) if k.endswith('.pdf')]
        # The click lands while the 1st file is read, so that file still finishes.
        check("Stop while the 1st file is read: only that file is copied", len(pdfs) == 1 and 'index.csv' in files, top)
        status = await page.inner_text('#export-status')
        check("...and the message says 1 of 40", status.startswith(f'Stopped after 1 of {N} files.'), status)
        await page.close()

        # === Before a run, Cancel still closes the dialog ===
        page = await start()
        await open_export(page)
        check("Before a run the button reads Cancel", await page.inner_text('#export-cancel-btn') == 'Cancel')
        await page.click('#export-cancel-btn'); await page.wait_for_timeout(150)
        check("...and closes the dialog", await page.locator('#export-start-btn').count() == 0)
        await page.close()

        check("No page errors", not errors, errors)
        await browser.close()
        print(f"{sum(results)}/{len(results)} checks passed")
        assert all(results)

asyncio.run(main())
