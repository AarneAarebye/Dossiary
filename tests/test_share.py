import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Share…: hands the selected documents' files (named like Export's copies,
# PDFs carrying their details) to the system share sheet, from the bulk
# More menu or a document's panel. The files are read first and the
# dialog's own Share button then makes the share (a share needs a fresh
# click). A file that can't be read is listed. A dismissed share sheet is no
# error. Where the browser can't share files (this test's Chromium), the
# dialog offers Export and a prepared email instead.
def doc(i, title, date, **extra):
    d = {"id": i, "title": title, "category": "Home", "document_type": "Letter", "date": date,
         "import_date": "2026-03-01T00:00:00Z", "created_at": "2026-03-01T00:00:00Z", "file_path": f"files/{i}_a.pdf",
         "source": "captured", "archived": 0, "needs_review": 0, "deleted": 0}
    d.update(extra)
    return d
SEED = {
    "documents": [doc(1, "Gas bill", "2026-02-15"), doc(2, "Water bill", "2026-02-20"), doc(3, "Missing file", "2026-01-01")],
    "tags": [{"id": 1, "name": "utilities"}], "document_tags": [{"document_id": 1, "tag_id": 1}],
}
FAKE_SHARE = """() => {
    window.__SHARED = null;
    window.__SHARE_MODE = 'ok';
    Object.defineProperty(navigator, 'canShare', { configurable: true, value: (data) => !!(data && data.files && data.files.length) });
    Object.defineProperty(navigator, 'share', { configurable: true, value: async (data) => {
        if(window.__SHARE_MODE === 'abort') throw Object.assign(new Error('Share canceled'), { name: 'AbortError' });
        if(window.__SHARE_MODE === 'fail') throw Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' });
        window.__SHARED = { title: data.title, files: await Promise.all(data.files.map(async f => ({ name: f.name, type: f.type, text: await f.text() }))) };
    } });
}"""

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
        await page.evaluate("""async () => {
            const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
            for(const i of [1, 2]){
                const w = await (await dir.getFileHandle(`${i}_a.pdf`, { create: true })).createWritable();
                await w.write(new TextEncoder().encode(`%PDF-1.4 doc ${i}`)); await w.close();
            }
        }""")
        await page.click('#open-btn')
        await page.wait_for_timeout(500)

        async def bulk_share(ids):
            for i in ids: await page.check(f'#doc-tbody tr[data-id="{i}"] .row-select-checkbox')
            await page.click('#bulk-more-btn')
            await page.click('#bulk-share-btn')
            await page.wait_for_timeout(500)

        # === This Chromium can't share files: Export and email instead ===
        await bulk_share([1, 2])
        print("Without share support, the dialog says so:", 'can’t hand files to other apps' in await page.inner_text('#share-status')
              and await page.locator('#share-export-btn').is_visible() and await page.locator('#share-email-btn').is_visible()
              and not await page.locator('#share-go-btn').is_visible())
        href = await page.get_attribute('#share-email-btn', 'data-href')
        print("...with an email prepared listing the documents:", href.startswith('mailto:?subject=Gas%20bill%3B%20Water%20bill&body=')
              and '2026-02-15%20Gas%20bill' in href)
        await page.click('#share-export-btn')
        await page.wait_for_timeout(300)
        print("...and Export one click away:", await page.locator('#export-start-btn').is_visible())
        await page.click('#export-cancel-btn')
        await page.click('#bulk-clear-selection-btn')
        await page.wait_for_timeout(200)

        # === With share support ===
        await page.evaluate(FAKE_SHARE)
        await bulk_share([1, 2, 3])
        status = await page.inner_text('#share-status')
        print("Files are read first, then Share is offered:", status.startswith('Ready: 2 file(s).') and 'Could not read: 1.' in status
              and await page.locator('#share-go-btn').is_visible())
        print("...listing the file that couldn't be read:", 'Missing file' in await page.inner_text('#share-failed-list'))
        print("Nothing is shared before the click:", await page.evaluate("window.__SHARED") is None)
        await page.click('#share-go-btn')
        await page.wait_for_timeout(300)
        shared = await page.evaluate("window.__SHARED")
        print("The files go to the share sheet, named like exported copies:", [f['name'] for f in shared['files']] == ['2026-02-15 Gas bill.pdf', '2026-02-20 Water bill.pdf'])
        first = shared['files'][0]['text']
        print("...PDFs carrying their details:", first.startswith('%PDF-FAKELIB') and json.loads(first.split('\n', 1)[1])['props']['keywords'] == ['utilities'])
        print("...and the dialog confirms it:", await page.inner_text('#share-status') == 'Handed over to the app you chose.'
              and not await page.locator('#share-go-btn').is_visible())
        await page.click('#share-close-btn')
        await page.click('#bulk-clear-selection-btn')
        await page.wait_for_timeout(200)

        # === From the panel, a dismissed sheet, a failure ===
        await page.click('#doc-tbody tr[data-id="2"]')
        await page.wait_for_timeout(300)
        print("The panel offers Share…:", await page.inner_text('#share-btn') == 'Share…')
        await page.click('#share-btn')
        await page.wait_for_timeout(400)
        await page.evaluate("window.__SHARE_MODE = 'abort'; window.__SHARED = null;")
        await page.click('#share-go-btn')
        await page.wait_for_timeout(200)
        print("Dismissing the share sheet isn't an error:", (await page.inner_text('#share-status')).startswith('Ready: 1 file(s).')
              and await page.locator('#share-go-btn').is_visible())
        await page.evaluate("window.__SHARE_MODE = 'fail';")
        await page.click('#share-go-btn')
        await page.wait_for_timeout(200)
        print("A refused share is reported:", await page.inner_text('#share-status') == 'Sharing failed: Permission denied')
        await page.evaluate("window.__SHARE_MODE = 'ok';")
        await page.click('#share-go-btn')
        await page.wait_for_timeout(200)
        shared = await page.evaluate("window.__SHARED")
        print("A single document is shared with its title:", shared['title'] == 'Water bill' and len(shared['files']) == 1)
        await page.click('#share-close-btn')

        # === German ===
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(200)
        await page.click('#share-btn')
        await page.wait_for_timeout(400)
        print("German labels:", (await page.inner_text('#share-status')).startswith('Bereit: 1 Datei(en).') and await page.inner_text('#share-go-btn') == 'Teilen')

        print("ERRORS:", errors)
        await browser.close()

asyncio.run(main())
