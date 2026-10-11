import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

# A PDF added through the Inbox (scan dialog, inbox/ folder, drag and drop)
# gets its own text layer as OCR text right away, so a scan a helper already
# OCR'd is searchable without running OCR in Dossiary.

import asyncio
from playwright.async_api import async_playwright

TEXT = 'This PDF already has real embedded text content in it.'


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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        await page.evaluate("""
            () => {
                window.__TEST_ROOT = window.__makeEmptyRoot();
                window.__addInboxFile(window.__TEST_ROOT, 'scan-with-text.pdf', new TextEncoder().encode('%PDF-1.4 has text'));
            }
        """)
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = true;")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(300)
        await page.click('#inbox-add-all-btn')
        await page.wait_for_timeout(600)

        db = await page.evaluate("(async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text()))()")
        doc = db['documents'][0] if db['documents'] else {}
        print("a PDF with a text layer gets that text as OCR text:", (doc.get('ocr_text') or '').strip() == TEXT)
        print("...and is recorded as checked, with a text layer:", doc.get('text_checked') == 1 and doc.get('has_text_layer') == 1)
        files = await page.evaluate("""
            (async () => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const names = [];
                for await (const [name] of dir.entries()) names.push(name);
                const sidecar = names.find(n => n.endsWith('.txt'));
                return sidecar ? await (await (await dir.getFileHandle(sidecar)).getFile()).text() : '';
            })()
        """)
        print("the sidecar carries the text for Spotlight:", TEXT in files)

        # A PDF without a text layer: checked, no text, nothing invented.
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = false;")
        await page.evaluate("window.__addInboxFile(window.__TEST_ROOT, 'image-only.pdf', new TextEncoder().encode('%PDF-1.4 image only'))")
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(600)
        db = await page.evaluate("(async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text()))()")
        doc = next((d for d in db['documents'] if d['title'] == 'image-only'), {})
        print("a PDF without a text layer is checked and left without OCR text:",
              doc.get('text_checked') == 1 and doc.get('has_text_layer') == 0 and not doc.get('ocr_text'))

        print("no page errors:", errors == [])
        if errors:
            print(errors)
        await browser.close()

asyncio.run(main())
