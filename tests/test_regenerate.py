import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Seed a "migrated" document with a real file but NO thumbnail (simulating one where
# Mariner didn't have a thumbnail, or an older migration predating this feature)
SEED = {
    "documents": [{
        "id": 1, "title": "No Preview Doc", "category": "Test", "subcategory": None,
        "document_type": None, "payment_method": None, "amount": None, "date": None,
        "import_date": None, "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": "files/1_doc.png", "original_file_path": None,
        "created_at": "2026-01-01T00:00:00Z", "source": "migrated", "source_legacy_id": 1,
        "thumbnail_path": None,
    }],
    "tags": [], "document_tags": [], "people": [], "document_people": [], "settings": [],
}

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
        combined = stub_js + f"""
        window.__makeNoThumbRoot = function() {{
            const root = new FakeDirHandle('TestLib');
            const dbBytes = new TextEncoder().encode(JSON.stringify({json.dumps(SEED)}));
            root._children.set('library.sqlite', new FakeFileHandle('library.sqlite', dbBytes));
            const filesDir = new FakeDirHandle('files');
            root._children.set('files', filesDir);
            // a real 1x1 PNG so canvas-based thumbnail generation actually works
            const pngBytes = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII='), c => c.charCodeAt(0));
            filesDir._children.set('1_doc.png', new FakeFileHandle('1_doc.png', pngBytes));
            return root;
        }};
        """
        await page.add_init_script(combined)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeNoThumbRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        label_before = await page.locator('#regen-thumb-btn').inner_text()
        empty_state = await page.locator('.modal-thumb-empty').inner_text()
        print("button label before (should be 'Generate preview'):", label_before)
        print("empty state text:", empty_state)

        await page.click('#regen-thumb-btn')
        await page.wait_for_timeout(400)

        img_present = await page.locator('.modal-thumb').count()
        status_text = await page.locator('#thumb-status').inner_text()
        print("thumbnail image present after generate:", img_present)
        print("status after generate:", status_text)

        label_after = await page.locator('#regen-thumb-btn').inner_text()
        print("button label after (should be 'Regenerate preview'):", label_after)

        # click Regenerate again to confirm it works a second time too
        await page.click('#regen-thumb-btn')
        await page.wait_for_timeout(400)
        img_present2 = await page.locator('.modal-thumb').count()
        print("thumbnail image still present after second regenerate:", img_present2)

        # verify persisted
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("persisted thumbnail_path:", persisted['documents'][0]['thumbnail_path'])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
