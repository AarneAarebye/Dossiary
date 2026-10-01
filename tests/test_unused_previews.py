import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Library check's "Unused preview files": files under thumbnails/ (subfolders
# included) that no document points to -- a Waste-bin document still counts
# -- listed with their total size and deleted on confirmation, leaving every
# used preview and every document alone.
def doc(i, title, **extra):
    d = {
        "id": i, "title": title, "category": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": None, "original_file_path": None, "thumbnail_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }
    d.update(extra)
    return d

SEED = {
    "documents": [
        doc(1, "Current", thumbnail_path="thumbnails/1.jpg", thumbnail_hd=1),
        doc(2, "In the bin", thumbnail_path="thumbnails/2.png", deleted=1),
    ],
    "tags": [], "document_tags": [],
}
FILES = {
    "thumbnails/1.jpg": "used jpeg",
    "thumbnails/1.png": "old png, now unused",
    "thumbnails/2.png": "used by a binned document",
    "thumbnails/mariner/ABC123.png": "old mariner preview",
    "thumbnails/.DS_Store": "finder clutter",
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        dialogs = []
        answer = {'accept': False}
        async def on_dialog(d):
            dialogs.append(d.message)
            await (d.accept() if answer['accept'] else d.dismiss())
        page.on("dialog", lambda d: asyncio.ensure_future(on_dialog(d)))
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
        await page.evaluate("""async (files) => {
            for(const [path, text] of Object.entries(files)){
                const parts = path.split('/'); let dir = window.__TEST_ROOT;
                for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
                await w.write(new TextEncoder().encode(text)); await w.close();
            }
        }""", FILES)
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        async def exists(path):
            return await page.evaluate("""async (path) => {
                const parts = path.split('/'); let dir = window.__TEST_ROOT;
                try{ for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part); await dir.getFileHandle(parts[parts.length - 1]); return true; }
                catch(e){ return false; }
            }""", path)

        await page.click('#tools-btn'); await page.click('#library-check-btn')
        await page.wait_for_timeout(800)
        summary = await page.inner_text('#unused-previews-summary')
        unused_bytes = len(FILES["thumbnails/1.png"]) + len(FILES["thumbnails/mariner/ABC123.png"])
        print("Section lists the two unused files with their size:", '2 (' in summary and f'{unused_bytes} B' in summary, repr(summary))

        await page.click('#unused-previews-delete-btn')
        await page.wait_for_timeout(300)
        print("Asks first, naming the count:", len(dialogs) == 1 and 'Delete 2 unused preview files' in dialogs[0], dialogs)
        print("Declining deletes nothing:", await exists('thumbnails/1.png') and await exists('thumbnails/mariner/ABC123.png'))

        answer['accept'] = True
        await page.click('#unused-previews-delete-btn')
        await page.wait_for_timeout(400)
        print("Confirming deletes the unused files, subfolders included:", not await exists('thumbnails/1.png') and not await exists('thumbnails/mariner/ABC123.png'))
        print("Used previews stay, including a Waste-bin document's:", await exists('thumbnails/1.jpg') and await exists('thumbnails/2.png'))
        print("Finder clutter isn't counted or touched:", await exists('thumbnails/.DS_Store'))
        print("Result shown in place:", 'Deleted unused preview files: 2.' in await page.inner_text('#unused-previews-result'))

        await page.click('#modal-close-btn')
        await page.click('#tools-btn'); await page.click('#library-check-btn')
        await page.wait_for_timeout(800)
        print("The next check finds nothing left:", await page.locator('#unused-previews-section').count() == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
