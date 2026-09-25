import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio
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
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        async def delete_stub_file(rel_path):
            # Walks window.__TEST_ROOT the same way resolveFileHandle() does,
            # ending in removeEntry() on the parent directory instead of
            # getFileHandle() -- simulates the underlying file being moved or
            # deleted outside the app, without touching the document's own
            # stored path at all.
            await page.evaluate("""
                async (relPath) => {
                    const parts = relPath.split('/');
                    let dir = window.__TEST_ROOT;
                    for (let i = 0; i < parts.length - 1; i++) {
                        dir = await dir.getDirectoryHandle(parts[i]);
                    }
                    await dir.removeEntry(parts[parts.length - 1]);
                }
            """, rel_path)

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

        # Doc 1: fine, both paths resolve -- must not be flagged at all.
        await capture_document('Fine Doc', b'%PDF-1.4 fine doc', 'fine.pdf')

        # Doc 2: file_path broken, original_file_path fine.
        await capture_document('Broken File Doc', b'%PDF-1.4 broken file doc', 'broken-file.pdf')
        doc2_paths = await page.evaluate("window.__DEBUG_getDocPaths(2)")
        await delete_stub_file(doc2_paths['file_path'])

        # Doc 3: original_file_path broken, file_path fine.
        await capture_document('Broken Original Doc', b'%PDF-1.4 broken original doc', 'broken-original.pdf')
        doc3_paths = await page.evaluate("window.__DEBUG_getDocPaths(3)")
        await delete_stub_file(doc3_paths['original_file_path'])

        # Doc 4: both paths broken.
        await capture_document('Both Broken Doc', b'%PDF-1.4 both broken doc', 'both-broken.pdf')
        doc4_paths = await page.evaluate("window.__DEBUG_getDocPaths(4)")
        await delete_stub_file(doc4_paths['file_path'])
        await delete_stub_file(doc4_paths['original_file_path'])

        # Doc 5: original_file_path forced to NULL (simulating a document with
        # no distinct original, e.g. a migrated document -- not reachable via
        # this app's own capture UI, which always preserves an original, so
        # this is set directly via __DEBUG_dbRun + a refresh from the DB).
        # file_path is left fine -- must NOT be flagged, since a NULL path is
        # never checked in the first place.
        await capture_document('No Original Doc', b'%PDF-1.4 no original doc', 'no-original.pdf')
        await page.evaluate("""
            async () => {
                window.__DEBUG_dbRun('UPDATE documents SET original_file_path = NULL WHERE id = ?', [5]);
                await window.__DEBUG_loadDocumentsFromDb();
            }
        """)

        # Doc 6: both paths broken, then the document itself is deleted -- must
        # be excluded from the check entirely, even though its paths are broken.
        await capture_document('Deleted Broken Doc', b'%PDF-1.4 deleted broken doc', 'deleted-broken.pdf')
        doc6_paths = await page.evaluate("window.__DEBUG_getDocPaths(6)")
        await delete_stub_file(doc6_paths['file_path'])
        await delete_stub_file(doc6_paths['original_file_path'])
        await page.click('tr[data-id="6"]')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)

        # === Render check: opening the modal shows a "Broken file links" row
        # per affected document, with the right File/Original indicators ===
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)

        broken_row_ids = await page.evaluate("""
            () => Array.from(document.querySelectorAll('.broken-link-row')).map(r => r.dataset.documentId)
        """)
        print("Exactly 3 broken-link rows shown (docs 2, 3, 4):", sorted(broken_row_ids) == ['2', '3', '4'])

        doc2_row = page.locator('.broken-link-row[data-document-id="2"]')
        print("Doc 2's row shows a File indicator:", await doc2_row.locator('.broken-link-indicator[data-path-field="file_path"]').count() == 1)
        print("Doc 2's row shows no Original indicator:", await doc2_row.locator('.broken-link-indicator[data-path-field="original_file_path"]').count() == 0)

        doc3_row = page.locator('.broken-link-row[data-document-id="3"]')
        print("Doc 3's row shows an Original indicator:", await doc3_row.locator('.broken-link-indicator[data-path-field="original_file_path"]').count() == 1)
        print("Doc 3's row shows no File indicator:", await doc3_row.locator('.broken-link-indicator[data-path-field="file_path"]').count() == 0)

        doc4_row = page.locator('.broken-link-row[data-document-id="4"]')
        print("Doc 4's row shows both File and Original indicators:",
              await doc4_row.locator('.broken-link-indicator[data-path-field="file_path"]').count() == 1 and
              await doc4_row.locator('.broken-link-indicator[data-path-field="original_file_path"]').count() == 1)

        print("Doc 5 (NULL original_file_path, file_path fine) is not flagged at all:",
              await page.locator('.broken-link-row[data-document-id="5"]').count() == 0)
        print("Doc 6 (deleted) is excluded even though its paths are broken:",
              await page.locator('.broken-link-row[data-document-id="6"]').count() == 0)
        print("Doc 1 (fine) is not flagged:",
              await page.locator('.broken-link-row[data-document-id="1"]').count() == 0)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
