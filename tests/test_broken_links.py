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

        async def relink(button_selector, file_payload):
            # Clicks a Re-link... button and answers its native picker through
            # Playwright's own file-chooser interception (without it, headless
            # Chromium auto-dismisses the picker, firing `cancel`).
            async with page.expect_file_chooser() as fc_info:
                await page.click(button_selector)
            chooser = await fc_info.value
            await chooser.set_files(file_payload)

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

        # === Re-link scenarios ===

        # Doc 1 has been completely fine until now (never touched in the
        # detection scenarios above) -- break its file_path here, to test a
        # genuinely SUCCESSFUL re-link of the non-hash-deriving path (doc 1
        # has a real original_file_path, so file_path is NOT its hash-deriving
        # path) leaves file_hash completely untouched. This is the clean,
        # dedicated version of that check -- the doc 4 scenario further below
        # also re-links a non-hash-deriving path, but that attempt is made to
        # FAIL on purpose (to test the error-handling path instead), so it
        # doesn't exercise a successful "wrong path re-linked, hash unchanged"
        # case on its own.
        doc1_paths = await page.evaluate("window.__DEBUG_getDocPaths(1)")
        await delete_stub_file(doc1_paths['file_path'])
        doc1_hash_before = await page.evaluate("window.__DEBUG_getFileHash(1)")

        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)

        # Clicking "Re-link..." must NOT also fire the row's own click-to-
        # detail-panel handler (which would close the modal and select doc 1)
        # -- guarded by .broken-link-indicators' stopPropagation.
        selected_before = await page.evaluate("document.querySelector('tr.row-selected') ? document.querySelector('tr.row-selected').dataset.id : null")
        await page.click('.broken-link-row[data-document-id="1"] .relink-btn[data-path-field="file_path"]')
        await page.wait_for_timeout(100)
        selected_after = await page.evaluate("document.querySelector('tr.row-selected') ? document.querySelector('tr.row-selected').dataset.id : null")
        print("Clicking Re-link... leaves the Library check modal open (row click-through not triggered):",
              await page.locator('#modal-backdrop').count() == 1)
        print("...and doesn't change the table's selected row:", selected_before == selected_after)

        # With no file-chooser handler attached, headless Chromium dismisses the
        # native picker on its own, firing `cancel` (not `change`) exactly as a
        # real person cancelling the dialog does -- so the click just above is
        # itself a real cancelled attempt. It must be a no-op that also removes
        # the hidden input, rather than orphaning it in the DOM.
        await page.wait_for_timeout(200)
        print("A cancelled picker leaves no orphaned hidden input behind:",
              await page.locator('input.relink-file-input').count() == 0)
        print("...and doc 1's broken indicator is still there (cancel is a no-op):",
              await page.locator('.broken-link-row[data-document-id="1"] .relink-btn[data-path-field="file_path"]').count() == 1)
        # An older browser that fires neither `change` nor `cancel` on
        # dismissal would leave its input behind -- simulate such a leftover
        # directly, and confirm the next attempt sweeps it up rather than
        # letting them accumulate.
        await page.evaluate("""
            () => {
                const stale = document.createElement('input');
                stale.type = 'file'; stale.className = 'relink-file-input'; stale.style.display = 'none';
                document.body.appendChild(stale);
            }
        """)
        await relink('.broken-link-row[data-document-id="1"] .relink-btn[data-path-field="file_path"]', {
            'name': 'replacement1.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 replacement bytes for doc 1 file_path',
        })
        await page.wait_for_timeout(300)
        print("A stale leftover hidden input is swept up by the next Re-link attempt:",
              await page.locator('input.relink-file-input').count() == 0)

        print("Doc 1's row is gone after its only broken indicator is fixed:",
              await page.locator('.broken-link-row[data-document-id="1"]').count() == 0)
        doc1_hash_after = await page.evaluate("window.__DEBUG_getFileHash(1)")
        print("Doc 1's file_hash is untouched by a successful re-link of the non-hash-deriving path:",
              doc1_hash_after == doc1_hash_before)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # Doc 2 has file_path broken and NO original_file_path at all (forced
        # NULL the same way doc 5 was) -- so file_path IS its hash-deriving
        # path, and re-linking it should recompute file_hash.
        await page.evaluate("""
            async () => {
                window.__DEBUG_dbRun('UPDATE documents SET original_file_path = NULL WHERE id = ?', [2]);
                await window.__DEBUG_loadDocumentsFromDb();
            }
        """)
        doc2_hash_before = await page.evaluate("window.__DEBUG_getFileHash(2)")

        # Re-open the modal (closed at the end of the doc 1 scenario above) --
        # doc 2/3/4's re-link scenarios below all share this one modal session,
        # since re-linking updates the DOM in place with no need to reopen
        # between them.
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)

        await relink('.broken-link-row[data-document-id="2"] .relink-btn[data-path-field="file_path"]', {
            'name': 'replacement2.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 replacement bytes for doc 2',
        })
        await page.wait_for_timeout(300)

        print("Doc 2's row is gone after its only broken indicator is fixed:",
              await page.locator('.broken-link-row[data-document-id="2"]').count() == 0)
        doc2_hash_after = await page.evaluate("window.__DEBUG_getFileHash(2)")
        print("Doc 2's file_hash was recomputed (file_path was its hash-deriving path, no original):",
              doc2_hash_after is not None and doc2_hash_after != doc2_hash_before)

        doc2_paths = await page.evaluate("window.__DEBUG_getDocPaths(2)")
        written_ok = await page.evaluate("""
            async (relPath) => {
                const parts = relPath.split('/');
                let dir = window.__TEST_ROOT;
                for (let i = 0; i < parts.length - 1; i++) { dir = await dir.getDirectoryHandle(parts[i]); }
                const handle = await dir.getFileHandle(parts[parts.length - 1]);
                const file = await handle.getFile();
                const text = await file.text();
                return text.includes('replacement bytes for doc 2');
            }
        """, doc2_paths['file_path'])
        print("Doc 2's file_path now has the replacement bytes on disk:", written_ok)

        # Doc 3 has original_file_path broken and DOES have an original_file_path
        # at all -- it's the hash-deriving path, so re-linking it recomputes
        # file_hash.
        doc3_hash_before = await page.evaluate("window.__DEBUG_getFileHash(3)")
        await relink('.broken-link-row[data-document-id="3"] .relink-btn[data-path-field="original_file_path"]', {
            'name': 'replacement3.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 replacement bytes for doc 3 original',
        })
        await page.wait_for_timeout(300)
        doc3_hash_after = await page.evaluate("window.__DEBUG_getFileHash(3)")
        print("Doc 3's file_hash WAS recomputed (original_file_path IS its hash-deriving path):",
              doc3_hash_after is not None and doc3_hash_after != doc3_hash_before)

        # Doc 4 still has both paths broken. Re-link its original_file_path
        # first (the hash-deriving path, since it has one) and confirm its
        # file_path indicator ALONE remains, with file_hash now set from the
        # original. Then re-link file_path too, and confirm THAT does NOT
        # change file_hash again, since file_path is not the hash-deriving path
        # for a document that has an original.
        await relink('.broken-link-row[data-document-id="4"] .relink-btn[data-path-field="original_file_path"]', {
            'name': 'replacement4-original.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 replacement bytes for doc 4 original',
        })
        await page.wait_for_timeout(300)
        doc4_hash_after_original = await page.evaluate("window.__DEBUG_getFileHash(4)")
        print("Doc 4's row still exists (file_path is still broken):",
              await page.locator('.broken-link-row[data-document-id="4"]').count() == 1)
        print("Doc 4's original-only indicator is gone, file_path indicator remains:",
              await page.locator('.broken-link-row[data-document-id="4"] .broken-link-indicator[data-path-field="original_file_path"]').count() == 0 and
              await page.locator('.broken-link-row[data-document-id="4"] .broken-link-indicator[data-path-field="file_path"]').count() == 1)

        # Simulate a write failure for doc 4's remaining broken path (file_path)
        # the same live-instance-patching way main_backfill_failure() already
        # does for library.sqlite in test_duplicate_detection.py: pre-create
        # the FakeFileHandle at the exact stored path, then patch its own
        # createWritable() to throw -- the app's later resolveFileHandle(path,
        # true) call for the same path returns this same instance.
        doc4_paths = await page.evaluate("window.__DEBUG_getDocPaths(4)")
        await page.evaluate("""
            async (relPath) => {
                const parts = relPath.split('/');
                let dir = window.__TEST_ROOT;
                for (let i = 0; i < parts.length - 1; i++) { dir = await dir.getDirectoryHandle(parts[i], { create: true }); }
                const handle = await dir.getFileHandle(parts[parts.length - 1], { create: true });
                handle.createWritable = async () => { throw new Error('Simulated disk failure'); };
            }
        """, doc4_paths['file_path'])

        await relink('.broken-link-row[data-document-id="4"] .relink-btn[data-path-field="file_path"]', {
            'name': 'replacement4-file.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 this write will fail',
        })
        await page.wait_for_timeout(300)

        print("After a failed write, doc 4's file_path Re-link button is still present:",
              await page.locator('.broken-link-row[data-document-id="4"] .relink-btn[data-path-field="file_path"]').count() == 1)
        print("After a failed write, an inline error is shown:",
              await page.locator('.broken-link-row[data-document-id="4"] .relink-error').count() == 1)
        doc4_hash_after_failed_write = await page.evaluate("window.__DEBUG_getFileHash(4)")
        print("A failed write does not touch file_hash:", doc4_hash_after_failed_write == doc4_hash_after_original)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
