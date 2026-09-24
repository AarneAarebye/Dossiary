import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, hashlib
from playwright.async_api import async_playwright

# Two byte strings used throughout this file: DOC_A_BYTES/DOC_B_BYTES are
# genuinely different content (so documents built from them get different
# hashes); DOC_A_BYTES is reused verbatim for a second document to prove two
# documents built from IDENTICAL bytes get the SAME hash.
DOC_A_BYTES = b'%PDF-1.4 fake pdf content A for duplicate-detection tests'
DOC_B_BYTES = b'%PDF-1.4 completely different fake pdf content B'

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

        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        # === Scenario 1: computeFileHash() matches a hand-computed SHA-256 ===
        js_hash = await page.evaluate(
            "async (bytes) => { const buf = new Uint8Array(bytes).buffer; const file = new File([buf], 'x.pdf', {type: 'application/pdf'}); return await window.__DEBUG_computeFileHash(file); }",
            list(DOC_A_BYTES),
        )
        expected_hash = hashlib.sha256(DOC_A_BYTES).hexdigest()
        print("computeFileHash() matches hashlib.sha256():", js_hash == expected_hash)

        # === Scenario 2: two documents captured from byte-identical files get the
        # same file_hash; a third captured from different bytes gets a different one ===
        async def capture_document(title, file_bytes, filename):
            await page.click('#add-btn')
            await page.wait_for_timeout(100)
            await page.set_input_files('#file-input', {
                'name': filename, 'mimeType': 'application/pdf', 'buffer': file_bytes,
            })
            await page.wait_for_timeout(150)
            await page.fill('#f-title', title)
            await page.click('#save-doc-btn')
            await page.wait_for_timeout(200)

        await capture_document('Doc A1', DOC_A_BYTES, 'a1.pdf')
        await capture_document('Doc A2 (same bytes as A1)', DOC_A_BYTES, 'a2.pdf')
        await capture_document('Doc B (different bytes)', DOC_B_BYTES, 'b.pdf')

        hash_a1 = await page.evaluate("window.__DEBUG_getFileHash(1)")
        hash_a2 = await page.evaluate("window.__DEBUG_getFileHash(2)")
        hash_b = await page.evaluate("window.__DEBUG_getFileHash(3)")
        print("Doc A1 has a non-null file_hash:", hash_a1 is not None and len(hash_a1) == 64)
        print("Doc A1 and Doc A2 (identical bytes) share the same file_hash:", hash_a1 == hash_a2)
        print("Doc A1 and Doc B (different bytes) have different file_hash values:", hash_a1 != hash_b)
        print("Doc A1's file_hash matches hashlib.sha256() of its own bytes:", hash_a1 == hashlib.sha256(DOC_A_BYTES).hexdigest())

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
