import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, base64, hashlib, json
from playwright.async_api import async_playwright

# "Make searchable": OCR an already-saved document and rebuild it as a searchable
# PDF after the fact, keeping the untouched original -- see CLAUDE.md's
# "Make searchable" note for the path rules exercised here.
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
PNG_HASH = hashlib.sha256(PNG).hexdigest()
SCAN_PDF = b"%PDF-1.4 scanned image only"

def doc(i, title, file_path, original=None, **extra):
    d = {
        "id": i, "title": title, "category": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": file_path, "original_file_path": original,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0, "searchable_pdf_built": 0, "file_hash": None,
    }
    d.update(extra)
    return d

SEED = {
    "documents": [
        # 1: image capture with its own preserved original (byte-identical copy)
        doc(1, "Scanned Letter", "files/1_scan.png", "files/1_scan/scan.png", file_hash=PNG_HASH),
        # 2: a legacy scanned PDF with no original at all, OCR text corrected by hand
        doc(2, "Old Scan", "files/2_old.pdf", None, source="migrated", ocr_text="Hand-corrected text", ocr_language="deu"),
        # 3: a PDF that already contains real text
        doc(3, "Digital PDF", "files/3_digital.pdf", "files/3_digital/digital.pdf"),
        # 4: image whose active copy no longer matches the preserved original's hash
        doc(4, "Edited Copy", "files/4_copy.png", "files/4_copy/copy.png", file_hash="0" * 64),
        # 5: an unsupported file type
        doc(5, "Word File", "files/5_notes.docx", "files/5_notes/notes.docx"),
        # 6: already built at capture time
        doc(6, "Already Searchable", "files/6_done.pdf", "files/6_done/done.png", searchable_pdf_built=1),
        # 7: PDF whose preserved original is missing on disk
        doc(7, "Lost Original", "files/7_lost.pdf", "files/7_lost/lost.pdf"),
        # 8: plain image for the close-while-running check
        doc(8, "Slow Scan", "files/8_slow.png", None),
    ],
    "tags": [], "document_tags": [],
    # Mark the one-time searchable_pdf_built backfill as done: it would otherwise
    # flag every seeded captured document with an original as already built.
    "settings": [{"key": "searchable_pdf_built_backfill_migrated", "value": "1"}],
}

FILES = {
    "files/1_scan.png": PNG, "files/1_scan/scan.png": PNG, "files/1_scan.txt": b"old sidecar",
    "files/2_old.pdf": SCAN_PDF,
    "files/3_digital.pdf": b"%PDF-1.4 digital", "files/3_digital/digital.pdf": b"%PDF-1.4 digital",
    "files/4_copy.png": PNG, "files/4_copy/copy.png": PNG,
    "files/5_notes.docx": b"docx", "files/5_notes/notes.docx": b"docx",
    "files/6_done.pdf": b"%PDF built", "files/6_done/done.png": PNG,
    "files/7_lost.pdf": SCAN_PDF,
    "files/8_slow.png": PNG,
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        files_b64 = {k: base64.b64encode(v).decode() for k, v in FILES.items()}
        await page.evaluate("""
            async (files) => {
                for(const [path, b64] of Object.entries(files)){
                    const parts = path.split('/');
                    let dir = window.__TEST_ROOT;
                    for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                    const h = await dir.getFileHandle(parts[parts.length - 1], { create: true });
                    const w = await h.createWritable();
                    await w.write(Uint8Array.from(atob(b64), c => c.charCodeAt(0)));
                    await w.close();
                }
            }
        """, files_b64)
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        async def select(i):
            await page.click(f'#doc-tbody tr[data-id="{i}"]')
            await page.wait_for_timeout(250)

        async def exists(path):
            return await page.evaluate("""
                async (path) => {
                    const parts = path.split('/');
                    try{
                        let dir = window.__TEST_ROOT;
                        for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part);
                        await dir.getFileHandle(parts[parts.length - 1]);
                        return true;
                    }catch(e){ return false; }
                }
            """, path)

        async def read_text(path):
            return await page.evaluate("""
                async (path) => {
                    const parts = path.split('/');
                    let dir = window.__TEST_ROOT;
                    for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part);
                    return await (await (await dir.getFileHandle(parts[parts.length - 1])).getFile()).text();
                }
            """, path)

        async def db_doc(i):
            state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
            return next(d for d in state['documents'] if d['id'] == i)

        async def run(i, lang=None):
            await select(i)
            await page.click('#make-searchable-btn')
            await page.wait_for_timeout(150)
            if lang: await page.select_option('#make-searchable-lang', lang)
            await page.click('#make-searchable-start-btn')
            await page.wait_for_timeout(600)
            return await page.inner_text('#make-searchable-status')

        async def close():
            await page.click('#make-searchable-cancel-btn')
            await page.wait_for_timeout(150)

        # === Scenario 1: the action is offered only where it can do something ===
        offered = {}
        for i in range(1, 8):
            await select(i)
            offered[i] = await page.locator('#make-searchable-btn').count() == 1
        print("Offered for PNG/PDF documents not yet built:", all(offered[i] for i in (1, 2, 3, 4, 7)), offered)
        print("Not offered for an unsupported type:", not offered[5])
        print("Not offered for an already-built searchable PDF:", not offered[6])
        await page.click('#doc-tbody tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        in_menu = 'Make searchable' in await page.locator('.row-context-menu').inner_text()
        print("Panel-only: not in the row context menu:", not in_menu)
        await page.keyboard.press('Escape')
        await page.mouse.click(5, 5)
        await page.wait_for_timeout(100)

        # === Scenario 2: image with a preserved original -- active copy replaced by a PDF ===
        await page.evaluate("window.__JSPDF_CALLS = []; window.__STUB_LOG.length = 0;")
        status = await run(1, 'fra')
        print("Image document reports done:", 'searchable PDF' in status, repr(status))
        d1 = await db_doc(1)
        print("file_path now points at the new PDF:", d1['file_path'] == 'files/1_scan.pdf', d1['file_path'])
        print("original_file_path unchanged:", d1['original_file_path'] == 'files/1_scan/scan.png')
        print("searchable_pdf_built set, OCR text + language stored:", d1['searchable_pdf_built'] == 1 and d1['ocr_text'] == 'Hello World' and d1['ocr_language'] == 'fra')
        print("Chosen OCR language reached Tesseract:", any('createWorker(["fra"])' in l for l in await page.evaluate("window.__STUB_LOG")))
        print("New PDF written with the text layer:", (await read_text('files/1_scan.pdf')).startswith('FAKE-PDF-BYTES:') and 'Hello' in await read_text('files/1_scan.pdf'))
        print("Byte-identical superseded PNG copy removed:", not await exists('files/1_scan.png'))
        print("Preserved original untouched:", await exists('files/1_scan/scan.png'))
        print("Sidecar refreshed with the OCR text:", 'Hello World' in await read_text('files/1_scan.txt'))
        await close()
        print("Panel no longer offers the action:", await page.locator('#make-searchable-btn').count() == 0)

        # === Scenario 3: a legacy PDF with no original -- it becomes the original ===
        status = await run(2)
        d2 = await db_doc(2)
        print("Legacy PDF: current file becomes the original:", d2['original_file_path'] == 'files/2_old.pdf', d2['original_file_path'])
        print("...searchable PDF written next to it:", d2['file_path'] == 'files/2_old_searchable.pdf' and await exists('files/2_old_searchable.pdf'))
        print("...old file still on disk:", await exists('files/2_old.pdf'))
        print("...hand-corrected OCR text kept, language unchanged:", d2['ocr_text'] == 'Hand-corrected text' and d2['ocr_language'] == 'deu')
        await close()

        # === Scenario 4: a PDF that already has real text is left alone ===
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = true;")
        status = await run(3)
        d3 = await db_doc(3)
        print("Text PDF reports it was left unchanged:", 'already contains real text' in status, repr(status))
        print("...and nothing changed in the database:", d3['file_path'] == 'files/3_digital.pdf' and not d3.get('searchable_pdf_built'))
        await close()
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = false;")

        # === Scenario 5: a copy that doesn't match the original's hash is kept ===
        await run(4)
        d4 = await db_doc(4)
        print("Mismatched image: new PDF active:", d4['file_path'] == 'files/4_copy.pdf')
        print("...and the non-identical old copy is kept on disk:", await exists('files/4_copy.png'))
        await close()

        # === Scenario 6: a missing original is never relied on ===
        await run(7)
        d7 = await db_doc(7)
        print("Missing original: current file becomes the original:", d7['original_file_path'] == 'files/7_lost.pdf')
        print("...not overwritten in place:", d7['file_path'] == 'files/7_lost_searchable.pdf' and (await read_text('files/7_lost.pdf')).startswith('%PDF-1.4 scanned'))
        await close()

        # === Scenario 7: the dialog can't be closed while OCR is running ===
        await page.evaluate("window.__STUB_OCR_SLOW = true;")
        new_id = 8
        await select(new_id)
        await page.click('#make-searchable-btn')
        await page.wait_for_timeout(150)
        await page.click('#make-searchable-start-btn')
        await page.wait_for_timeout(200)
        await page.keyboard.press('Escape')
        await page.click('#modal-backdrop', position={'x': 5, 'y': 5})
        await page.wait_for_timeout(150)
        print("Escape and backdrop don't close the dialog mid-run:", await page.locator('#make-searchable-status').count() == 1)
        print("...close and cancel are disabled mid-run:", await page.locator('#modal-close-btn').is_disabled() and await page.locator('#make-searchable-cancel-btn').is_disabled())
        await page.evaluate("window.__STUB_OCR_SLOW = false; window.__RESOLVE_SLOW_OCR();")
        await page.wait_for_timeout(600)
        print("...and closable again once it finishes:", not await page.locator('#modal-close-btn').is_disabled())
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(150)
        print("Escape closes it afterwards:", await page.locator('#make-searchable-status').count() == 0)

        # === Scenario 8: translated ===
        await select(5)
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        await select(7)
        await select(3)
        print("Action label translates:", await page.inner_text('#make-searchable-btn') == 'Durchsuchbar machen')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
