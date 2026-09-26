import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

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
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        async def read_stub_file_size(rel_path):
            return await page.evaluate("""
                async (relPath) => {
                    const parts = relPath.split('/');
                    let dir = window.__TEST_ROOT;
                    for (let i = 0; i < parts.length - 1; i++) { dir = await dir.getDirectoryHandle(parts[i]); }
                    const handle = await dir.getFileHandle(parts[parts.length - 1]);
                    const file = await handle.getFile();
                    return file.size;
                }
            """, rel_path)

        # Doc 1: a plain PDF capture, no OCR -- file_path and original_file_path
        # are two separately-written copies of the SAME bytes (still two real,
        # separately-sized files on disk, per writeOriginalToSubfolder()).
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('plain.pdf', 'wb') as f:
            f.write(b'%PDF-1.4 plain document, no OCR, twenty-two bytes padding here')
        await page.set_input_files('#file-input', 'plain.pdf')
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Plain Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # Doc 2: a real image, OCR'd and saved -- file_path becomes the rebuilt
        # searchable PDF (the stub's fake jsPDF.output() produces real,
        # non-trivial bytes), original_file_path stays the small original PNG.
        # These two are now genuinely DIFFERENT-sized real files, not just two
        # copies of the same bytes.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('scan.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'scan.png')
        await page.wait_for_timeout(150)
        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(300)
        await page.fill('#f-title', 'Scanned Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        # Stage a file directly in inbox/ (never added as a document).
        await page.evaluate("""
            async () => {
                const inboxDir = await window.__TEST_ROOT.getDirectoryHandle('inbox', { create: true });
                const handle = await inboxDir.getFileHandle('staged.pdf', { create: true });
                const writable = await handle.createWritable();
                await writable.write(new TextEncoder().encode('%PDF-1.4 staged inbox file, never added'));
                await writable.close();
            }
        """)

        # Write an extra, genuinely untracked file directly into files/ -- no
        # document's file_path/original_file_path will ever point to this.
        await page.evaluate("""
            async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                const handle = await filesDir.getFileHandle('mystery_leftover.bin', { create: true });
                const writable = await handle.createWritable();
                await writable.write(new TextEncoder().encode('nobody points to this file'));
                await writable.close();
            }
        """)

        # Move Doc 1 to the Waste bin -- its files must still count toward the
        # total (nothing on disk is touched by a soft delete).
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)

        # === Independently compute the expected totals in Python, walking the
        # exact same fake filesystem, so the assertions below don't just trust
        # the app's own arithmetic ===
        doc1_paths = await page.evaluate("window.__DEBUG_getDocPaths(1)")
        doc2_paths = await page.evaluate("window.__DEBUG_getDocPaths(2)")

        doc1_active_size = await read_stub_file_size(doc1_paths['file_path'])
        doc1_original_size = await read_stub_file_size(doc1_paths['original_file_path'])
        doc2_active_size = await read_stub_file_size(doc2_paths['file_path'])
        doc2_original_size = await read_stub_file_size(doc2_paths['original_file_path'])
        mystery_size = await read_stub_file_size('files/mystery_leftover.bin')
        inbox_size = await read_stub_file_size('inbox/staged.pdf')
        db_size = await read_stub_file_size('library.sqlite')

        # writeSidecarFile() (see CLAUDE.md's "Sidecar .txt files" note) writes a
        # <base-name>.txt file directly into files/, next to every captured
        # document's primary file -- a real, on-disk file that's neither this
        # document's own file_path nor original_file_path, so it's genuinely
        # untracked from computeStorageStats()'s point of view, same as the
        # deliberately-planted mystery_leftover.bin above. sidecarBaseNameFromFilePath()
        # derives its path the same way the app itself does: files/<file_path's own
        # basename, minus extension>.txt.
        def sidecar_path(file_path):
            name = file_path[len('files/'):]
            base = name.rsplit('.', 1)[0]
            return f'files/{base}.txt'
        doc1_sidecar_size = await read_stub_file_size(sidecar_path(doc1_paths['file_path']))
        doc2_sidecar_size = await read_stub_file_size(sidecar_path(doc2_paths['file_path']))
        untracked_size = mystery_size + doc1_sidecar_size + doc2_sidecar_size

        # saveNewDocument() unconditionally attempts a thumbnail for every
        # capture (generateThumbnail() supports both image/* and
        # application/pdf, so both doc 1's PDF and doc 2's PNG get one) --
        # thumbnails/1.png and thumbnails/2.png are real files here, per
        # writeThumbnail()'s own fixed `thumbnails/${id}.png` naming. Both are
        # genuinely tracked (thumbnail_path is set on both documents), so they
        # belong in the 'active' thumbnails bucket, not 'untracked'.
        doc1_thumb_size = await read_stub_file_size('thumbnails/1.png')
        doc2_thumb_size = await read_stub_file_size('thumbnails/2.png')

        expected_files_active = doc1_active_size + doc2_active_size
        expected_files_original = doc1_original_size + doc2_original_size
        expected_files_total = expected_files_active + expected_files_original + untracked_size
        expected_thumbnails_active = doc1_thumb_size + doc2_thumb_size
        expected_grand_total = expected_files_total + expected_thumbnails_active + inbox_size + db_size

        print("Doc 2's active file (rebuilt searchable PDF) is a genuinely different size than its original PNG:", doc2_active_size != doc2_original_size)

        stats = await page.evaluate("window.__DEBUG_computeStorageStats()")

        print("files.active matches the independently-computed sum:", stats['files']['active'] == expected_files_active)
        print("files.original matches the independently-computed sum:", stats['files']['original'] == expected_files_original)
        print("files.untracked equals the one deliberately-untracked file's size:", stats['files']['untracked'] == untracked_size)
        print("filesTotal matches active+original+untracked:", stats['filesTotal'] == expected_files_total)
        print("thumbnails.active matches both documents' real thumbnail sizes:", stats['thumbnails']['active'] == expected_thumbnails_active)
        print("thumbnails.untracked is zero (both thumbnails are genuinely tracked):", stats['thumbnails']['untracked'] == 0)
        print("inbox matches the one staged file's size:", stats['inbox'] == inbox_size)
        print("librarySqlite matches the real library.sqlite file size:", stats['librarySqlite'] == db_size)
        print("grandTotal matches the independently-computed total:", stats['grandTotal'] == expected_grand_total)
        print("Doc 1's files (now in the Waste bin) are still counted in files.active/original:",
              stats['files']['active'] >= doc1_active_size and stats['files']['original'] >= doc1_original_size)

        # === Modal rendering: busy state, then final numbers, with Untracked
        # shown since it's non-zero and Thumbnails' own Untracked row absent
        # since no thumbnails/ folder exists in this test at all ===
        # The fake filesystem's getFile() resolves so fast that computeStorageStats()'s
        # whole walk can complete within a single Playwright round-trip, making "is the
        # busy/spinner state visible right after the click" a real race rather than a
        # reliable check -- the same class of timing issue test_duplicate_detection.py's
        # own lazy-backfill test already ran into and fixed by slowing down a stub API
        # call for this one test only. FakeFileHandle isn't reachable by name from a
        # separate page.evaluate() call (its class binding lives in stub_studio2.js's own
        # injected-script scope, not on `window`), so an existing instance's shared
        # prototype is patched instead -- this affects every FakeFileHandle.getFile()
        # call from here on, which is fine since this test's own assertions all run
        # after this point.
        await page.evaluate("""
            async () => {
                const dbHandle = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const proto = Object.getPrototypeOf(dbHandle);
                const originalGetFile = proto.getFile;
                proto.getFile = async function(...args) {
                    await new Promise(r => setTimeout(r, 50));
                    return originalGetFile.apply(this, args);
                };
            }
        """)
        await page.click('#storage-stats-btn')
        await page.wait_for_timeout(50)
        busy_visible = await page.locator('#storage-stats-progress').is_visible()
        print("Busy/spinner state is visible right after opening:", busy_visible)
        await page.wait_for_timeout(2000)

        results_text = await page.locator('#storage-stats-results').inner_text()
        print("Results show the formatted grand total:", 'Total:' in results_text)
        print("Results show the Documents (files/) row:", 'Documents' in results_text)
        print("Results show the Untracked row (non-zero):", 'Untracked' in results_text)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
