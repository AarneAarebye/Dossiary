import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import tempfile

def _write_patched_app_with_preview_enabled():
    """Writes a copy of dossiary.html with SHOW_DOCUMENT_PREVIEW flipped to
    true, so this test can keep exercising the real thumbnail-display
    pipeline even though it now defaults to off (see dossiary.html's own
    SHOW_DOCUMENT_PREVIEW comment). Returns the temp file's path; caller
    is responsible for deleting it."""
    with open(APP_PATH) as f:
        html = f.read()
    target = "const SHOW_DOCUMENT_PREVIEW = false;"
    replacement = "const SHOW_DOCUMENT_PREVIEW = true;"
    assert target in html, "SHOW_DOCUMENT_PREVIEW declaration not found -- did its exact text change in dossiary.html?"
    patched = html.replace(target, replacement)
    fd, path = tempfile.mkstemp(suffix='.html', dir=_os2.path.dirname(APP_PATH))
    with _os2.fdopen(fd, 'w') as f:
        f.write(patched)
    return path

import asyncio, base64
from playwright.async_api import async_playwright

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
        patched_app_path = _write_patched_app_with_preview_enabled()
        await page.goto(f"file://{patched_app_path}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        # === Scenario 1: capture an IMAGE document -> real canvas-based thumbnail ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('thumbimg.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'thumbimg.png')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Image Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1 = persisted['documents'][0]
        print("doc1 thumbnail_path:", doc1['thumbnail_path'])

        thumb_exists = await page.evaluate("""
            (async () => {
                try {
                    const thumbsDir = await window.__TEST_ROOT.getDirectoryHandle('thumbnails');
                    const fh = await thumbsDir.getFileHandle('1.png');
                    const f = await fh.getFile();
                    return { exists: true, size: f.size };
                } catch(e) { return { exists: false, error: e.message }; }
            })()
        """)
        print("thumbnail file on disk:", thumb_exists)

        # open detail, check it shows a real <img>
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        img_present = await page.locator('.modal-thumb').count()
        button_label = await page.locator('#regen-thumb-btn').inner_text()
        print("modal shows <img> thumbnail:", img_present)
        print("button label (should be 'Regenerate preview'):", button_label)

        # === Scenario 2: capture a PDF document -> stubbed pdf.js thumbnail ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('thumbpdf.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 fake pdf for thumbnail test")
        await page.set_input_files('#file-input', 'thumbpdf.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'PDF Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc2 = [d for d in persisted2['documents'] if d['id'] == 2][0]
        print("doc2 (PDF) thumbnail_path:", doc2['thumbnail_path'])

        pdfjs_log = await page.evaluate("window.__STUB_LOG.filter(l => l.includes('pdfjsLib'))")
        print("pdfjsLib was called:", len(pdfjs_log) > 0)

        # === Scenario 3: with the real (unpatched) app, the preview is
        # hidden by default -- no image, no empty-state placeholder, no
        # Generate/Regenerate button -- but a real thumbnail_path and a
        # real file in thumbnails/ still get written, proving generation
        # itself is untouched by SHOW_DOCUMENT_PREVIEW ===
        await page.close()
        page = await browser.new_page()
        errors3 = []
        page.on("pageerror", lambda exc: errors3.append(str(exc)))
        page.on("console", lambda msg: errors3.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await page.route('**/*', route_handler)
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('thumbimg2.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'thumbimg2.png')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Hidden Preview Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        thumb_slot_count = await page.locator('.modal-thumb, .modal-thumb-empty').count()
        regen_btn_count = await page.locator('#regen-thumb-btn').count()
        print("preview slot present with default (should be False -- flag is off):", thumb_slot_count > 0)
        print("regen-thumb-btn present with default (should be False -- flag is off):", regen_btn_count > 0)

        persisted3 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc3 = persisted3['documents'][0]
        thumb_on_disk3 = await page.evaluate("""
            (async () => {
                try {
                    const thumbsDir = await window.__TEST_ROOT.getDirectoryHandle('thumbnails');
                    const fh = await thumbsDir.getFileHandle('1.png');
                    const f = await fh.getFile();
                    return { exists: true, size: f.size };
                } catch(e) { return { exists: false, error: e.message }; }
            })()
        """)
        print("thumbnail_path still written despite hidden preview (should be truthy):", doc3['thumbnail_path'])
        print("thumbnail file still on disk despite hidden preview:", thumb_on_disk3)

        print("JS ERRORS:", errors + errors3)
        await browser.close()
        _os2.remove(patched_app_path)

asyncio.run(main())
