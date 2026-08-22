import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, base64
from playwright.async_api import async_playwright

# Covers the detail view's "Copy" buttons next to the File/Original path lines
# (copyPathToClipboard()) -- the Clipboard API isn't subject to the same
# no-absolute-path/no-Finder-reveal restrictions as the File System Access API, so
# copying the displayed (library-name-prefixed) path is the practical alternative to
# "reveal in Finder", which no browser tab can do at all.

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(permissions=['clipboard-read', 'clipboard-write'])
        page = await context.new_page()
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
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        # === Doc that never runs OCR (no searchable PDF built) -- both copy buttons
        # show now, since every capture preserves its own untouched original
        # (see "Preserving an original file on ingestion" in CLAUDE.md), and each
        # copies its own distinct path ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Plain PDF Doc')
        with open('copytest1.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 copytest1")
        await page.set_input_files('#file-input', 'copytest1.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        file_copy_count = await page.locator('#copy-file-path-btn').count()
        original_copy_count = await page.locator('#copy-original-path-btn').count()
        print("File copy button present (should be 1):", file_copy_count)
        print("Original copy button present even though no searchable PDF was built (should be 1):", original_copy_count)
        assert original_copy_count == 1

        await page.click('#copy-file-path-btn')
        await page.wait_for_timeout(100)
        btn_text = await page.locator('#copy-file-path-btn').inner_text()
        clip = await page.evaluate("navigator.clipboard.readText()")
        print("button shows 'Copied!' right after click:", btn_text == 'Copied!')
        print("clipboard content matches the displayed path:", clip)
        assert clip == 'EmptyLibrary/files/1_Plain PDF Doc.pdf', f"unexpected clipboard content: {clip!r}"

        await page.wait_for_timeout(1600)
        btn_text_after = await page.locator('#copy-file-path-btn').inner_text()
        print("button label resets back to 'Copy' after the timeout:", btn_text_after == 'Copy')
        assert btn_text_after == 'Copy'

        await page.click('#copy-original-path-btn')
        await page.wait_for_timeout(100)
        clip1 = await page.evaluate("navigator.clipboard.readText()")
        print("Original button copies the preserved original's own path (distinct from file_path):", clip1)
        assert clip1 == 'EmptyLibrary/files/1_Plain PDF Doc/copytest1.pdf', f"unexpected clipboard content: {clip1!r}"

        # === Doc WITH a searchable-PDF original -- both copy buttons show, and each
        # copies its own distinct path (not a stale/shared value) ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('copytest2.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'copytest2.png')
        await page.wait_for_timeout(150)
        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(300)
        await page.fill('#f-title', 'Scanned Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(200)
        both_present = await page.locator('#copy-file-path-btn').count() == 1 and await page.locator('#copy-original-path-btn').count() == 1
        print("both File and Original copy buttons present:", both_present)
        assert both_present

        await page.click('#copy-original-path-btn')
        await page.wait_for_timeout(100)
        clip2 = await page.evaluate("navigator.clipboard.readText()")
        print("Original button copies the original's own path, not the processed file's:", clip2)
        assert clip2 == 'EmptyLibrary/files/2_Scanned Doc/copytest2.png', f"unexpected clipboard content: {clip2!r}"

        print("JS ERRORS:", errors)
        for fn in ('copytest1.pdf', 'copytest2.png'):
            if _os.path.exists(fn):
                _os.remove(fn)
        await browser.close()

asyncio.run(main())
