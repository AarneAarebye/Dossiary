import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [], "tags": [], "document_tags": [],
}

async def read_recent_libraries(page):
    return await page.evaluate("""
        (async () => {
            const req = indexedDB.open('dossiary-app-db', 1);
            const idb = await new Promise((resolve, reject) => {
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
            const store = idb.transaction('recentLibraries', 'readonly').objectStore('recentLibraries');
            const all = await new Promise((resolve, reject) => {
                const r = store.getAll();
                r.onsuccess = () => resolve(r.result);
                r.onerror = () => reject(r.error);
            });
            return all.map(e => ({ id: e.id, name: e.name, lastOpenedAt: e.lastOpenedAt }));
        })()
    """)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
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
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        # === Scenario 1: opening a library records exactly one entry in IndexedDB ===
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'LibraryA';" % json.dumps(SEED))
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        entries = await read_recent_libraries(page)
        print("one entry recorded after opening LibraryA:", [e['name'] for e in entries])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
