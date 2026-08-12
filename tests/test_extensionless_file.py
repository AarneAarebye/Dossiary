import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

# Regression test for a finding from the final whole-branch review of the
# "preserve original file on ingestion" feature: a picked/staged file with NO
# extension at all made destName (the active copy's filename) collide exactly
# with writeOriginalToSubfolder()'s subfolder name (both were `${id}_${baseName}`),
# which made the File System Access API throw TypeMismatchError (file vs. directory
# with the same name) and the whole save fail. Covers both ingestion paths:
# saveNewDocument() (capture form) and addInboxFile() (Inbox).

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)

        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'pdf.js' in url or 'jspdf' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)

        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        # === Scenario 1: capture form (saveNewDocument()'s plain-save branch) ===
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(300)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)

        # A file with literally no extension at all -- no dot anywhere in the name.
        extensionless_path = _os.path.abspath('scanned_document')
        with open(extensionless_path, 'wb') as f:
            f.write(b'not really a pdf, just raw bytes with no extension')
        await page.set_input_files('#file-input', extensionless_path)
        await page.wait_for_timeout(150)

        await page.fill('#f-title', 'No Extension Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)
        status = await page.locator("#status").inner_text()
        print("status after saving an extensionless file (should be a success message, not 'failed'):", status)

        db_state = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1 = db_state['documents'][0]
        print("capture: file_path:", doc1.get('file_path'))
        print("capture: original_file_path:", doc1.get('original_file_path'))
        print("capture: file_path and original_file_path are different strings (no TypeMismatchError collision):",
              doc1.get('file_path') != doc1.get('original_file_path'))

        _os.remove(extensionless_path)

        # === Scenario 2: Inbox add (addInboxFile()) ===
        # showDirectoryPicker() always returns whatever window.__TEST_ROOT currently
        # points at (see stub_studio2.js), so switch it to a second, fresh empty root
        # with the extensionless file already staged in inbox/ before reopening --
        # #reload-btn's click handler calls resetAll() then openLibrary() itself, which
        # invokes showDirectoryPicker(), so no separate #open-btn click is needed here.
        await page.evaluate("""
            () => {
                window.__TEST_ROOT = window.__makeEmptyRoot();
                window.__addInboxFile(window.__TEST_ROOT, 'scanned_document');
            }
        """)
        await page.click('#reload-btn')
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(300)

        banner_visible = await page.locator('#inbox-banner').is_visible()
        print("inbox banner visible with the extensionless file staged:", banner_visible)

        await page.click('#inbox-add-all-btn')
        await page.wait_for_timeout(300)
        status = await page.locator('#status').inner_text()
        print("status line after adding the extensionless file via inbox:", status)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        docs = persisted['documents']
        print("inbox: number of documents persisted (should be 1):", len(docs))
        if docs:
            doc = docs[0]
            print("inbox: file_path:", doc.get('file_path'))
            print("inbox: original_file_path:", doc.get('original_file_path'))
            print("inbox: file_path and original_file_path are different strings (no TypeMismatchError collision):",
                  doc.get('file_path') != doc.get('original_file_path'))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
