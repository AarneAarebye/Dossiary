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
        # 9: left untouched, for the translation check
        doc(9, "Untouched", "files/9_untouched.png", None),
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
    "files/9_untouched.png": PNG,
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
        print("Offered for PNG/PDF documents not yet built:", all(offered[i] for i in (1, 2, 3, 4, 7)), sorted(i for i, v in offered.items() if v))
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
        print("...but it's remembered as already searchable:", d3.get('has_text_layer') == 1)
        await close()
        print("...so the panel stops offering it:", await page.locator('#make-searchable-btn').count() == 0)
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
        await select(9)
        print("Action label translates:", await page.inner_text('#make-searchable-btn') == 'Durchsuchbar machen')

        print("JS ERRORS:", errors)
        await browser.close()


# === Bulk: "Make searchable" from the bulk-action bar ===
BULK_SEED = {
    "documents": [
        doc(1, "Scan A", "files/1_a.png", "files/1_a/a.png", file_hash=PNG_HASH),
        doc(2, "Scan B", "files/2_b.pdf", None),
        doc(3, "Digital C", "files/3_c.pdf", None),
        doc(4, "Built D", "files/4_d.pdf", "files/4_d/d.png", searchable_pdf_built=1),
        doc(5, "Word E", "files/5_e.docx", None),
        doc(6, "Missing F", "files/6_f.png", None),  # file not on disk -> fails
        doc(7, "Scan G", "files/7_g.png", None),
        doc(8, "Scan H", "files/8_h.png", None),
    ],
    "tags": [], "document_tags": [],
    "settings": [{"key": "searchable_pdf_built_backfill_migrated", "value": "1"}],
}
BULK_FILES = {
    "files/1_a.png": PNG, "files/1_a/a.png": PNG,
    "files/2_b.pdf": SCAN_PDF, "files/3_c.pdf": b"%PDF-1.4 digital",
    "files/4_d.pdf": b"%PDF built", "files/5_e.docx": b"docx",
    "files/7_g.png": PNG, "files/8_h.png": PNG,
}

async def main_bulk():
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(BULK_SEED)});")
        files_b64 = {k: base64.b64encode(v).decode() for k, v in BULK_FILES.items()}
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

        async def check(ids):
            for i in ids:
                await page.check(f'.row-select-checkbox[data-id="{i}"]')
            await page.wait_for_timeout(150)

        async def clear():
            await page.click('#bulk-clear-selection-btn')
            await page.wait_for_timeout(150)

        async def db_docs():
            state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
            return {d['id']: d for d in state['documents']}

        btn = page.locator('#bulk-make-searchable-btn')

        # === Scenario B1: the bulk button only appears when something selected can be made searchable ===
        await check([4, 5])
        print("Bulk button hidden when nothing selected can be made searchable:", not await btn.is_visible())
        await check([1])
        print("...and shown once an eligible document is selected:", await btn.is_visible())
        await clear()

        # === Scenario B2: the dialog processes only the eligible ones and reports a summary ===
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = false;")
        await check([1, 2, 4, 5, 6])
        await btn.click()
        await page.wait_for_timeout(150)
        count_text = await page.inner_text('#make-searchable-count')
        print("Dialog counts only the eligible documents (3 of 5 selected):", count_text.endswith('3'), repr(count_text))
        await page.click('#make-searchable-start-btn')
        await page.wait_for_timeout(1200)
        status = await page.inner_text('#make-searchable-status')
        print("Summary reports 2 made searchable and 1 failure:", 'Made searchable: 2.' in status and 'Could not be processed: 1.' in status, repr(status))
        failed = await page.locator('#make-searchable-failed-list li').all_inner_texts()
        print("...and names the failed document:", len(failed) == 1 and failed[0].startswith('Missing F'), failed)
        docs = await db_docs()
        print("Eligible documents were rebuilt:", docs[1]['searchable_pdf_built'] == 1 and docs[2]['searchable_pdf_built'] == 1)
        print("...ineligible and failed ones left alone:", docs[4]['file_path'] == 'files/4_d.pdf' and docs[5]['file_path'] == 'files/5_e.docx' and not docs[5].get('searchable_pdf_built') and not docs[6].get('searchable_pdf_built'))
        print("Button turns into Close afterwards:", await page.inner_text('#make-searchable-cancel-btn') == 'Close' and not await page.locator('#make-searchable-start-btn').is_visible())
        await page.click('#make-searchable-cancel-btn')
        await page.wait_for_timeout(150)
        print("Selection kept; the failed document stays eligible, so the button stays for a retry:", await btn.is_visible())
        await clear()

        # === Scenario B3: a PDF with real text is counted separately ===
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = true;")
        await check([3])
        await btn.click()
        await page.wait_for_timeout(150)
        # One document takes the single-document path and message.
        await page.click('#make-searchable-start-btn')
        await page.wait_for_timeout(600)
        print("A single eligible selection uses the single-document message:", 'already contains real text' in await page.inner_text('#make-searchable-status'))
        await page.click('#make-searchable-cancel-btn')
        await page.wait_for_timeout(150)
        await clear()
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = false;")

        # === Scenario B4: Stop lets the current document finish, then stops ===
        await page.evaluate("window.__STUB_OCR_SLOW = true;")
        await check([7, 8])
        await btn.click()
        await page.wait_for_timeout(150)
        await page.click('#make-searchable-start-btn')
        await page.wait_for_timeout(200)
        print("Stop button shown while running:", await page.locator('#make-searchable-stop-btn').is_visible())
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(100)
        print("Dialog can't be closed mid-run:", await page.locator('#make-searchable-status').count() == 1)
        progress = await page.inner_text('#make-searchable-status')
        print("Progress names the current document:", 'Document 1 of 2: Scan G' in progress, repr(progress))
        await page.click('#make-searchable-stop-btn')
        await page.evaluate("window.__STUB_OCR_SLOW = false; window.__RESOLVE_SLOW_OCR();")
        await page.wait_for_timeout(800)
        status = await page.inner_text('#make-searchable-status')
        print("Stopped after the first document:", 'Made searchable: 1.' in status and 'not processed: 1.' in status, repr(status))
        docs = await db_docs()
        print("...the finished one was saved, the other untouched:", docs[7]['searchable_pdf_built'] == 1 and not docs[8].get('searchable_pdf_built'))
        await page.click('#make-searchable-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario B5: not offered in the Waste bin ===
        await clear()
        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        print("No bulk Make searchable in the Waste bin view:", await btn.count() == 1 and not await btn.is_visible())

        print("JS ERRORS (bulk):", errors)
        await browser.close()


# === Library check: "Not searchable yet" section ===
# Two buckets: PDFs not yet opened to look for a text layer, and documents
# known to need OCR (images, and PDFs checked without text). A PDF whose bytes
# contain "%TEXTLAYER" reports real text in the stub.
TEXT_PDF = b"%PDF-1.4 %TEXTLAYER digital"
LC_SEED = {
    "documents": [
        doc(1, "Photo One", "files/1_one.png", None),
        doc(2, "Digital Two", "files/2_two.pdf", None),
        doc(3, "Built Three", "files/3_three.pdf", None, searchable_pdf_built=1),
        doc(4, "Deleted Four", "files/4_four.pdf", None, deleted=1),
        doc(5, "Scanned Five", "files/5_five.pdf", None),
        doc(6, "Missing Six", "files/6_six.pdf", None),  # no file on disk
    ] + [doc(i, f"Scan {i}", f"files/{i}_s.pdf", None) for i in range(7, 13)],
    "tags": [], "document_tags": [],
    # Pre-hashed, so opening Library check doesn't run the duplicate backfill
    # (which would check these PDFs for text itself -- see main_shared_read()).
    "settings": [{"key": "searchable_pdf_built_backfill_migrated", "value": "1"}],
}
for _d in LC_SEED["documents"]:
    _d["file_hash"] = f"hash-{_d['id']}"
LC_FILES = {"files/1_one.png": PNG, "files/2_two.pdf": TEXT_PDF, "files/3_three.pdf": b"%PDF built",
            "files/4_four.pdf": SCAN_PDF, "files/5_five.pdf": SCAN_PDF,
            **{f"files/{i}_s.pdf": SCAN_PDF + str(i).encode() for i in range(7, 13)}}

async def main_library_check():
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(LC_SEED)});")
        files_b64 = {k: base64.b64encode(v).decode() for k, v in LC_FILES.items()}
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

        async def open_check():
            await page.click('#tools-btn'); await page.click('#library-check-btn')
            await page.wait_for_timeout(800)

        async def text(sel):
            return await page.inner_text(sel) if await page.locator(sel).count() else None

        async def db_docs():
            state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
            return {d['id']: d for d in state['documents']}

        # === Scenario L1: unchecked PDFs and known needs-OCR documents are counted apart ===
        await open_check()
        unchecked = await text('#not-searchable-unchecked-count')
        needs = await text('#not-searchable-count')
        print("PDFs not yet checked are counted separately (2,5,6,7-12 = 9):", unchecked is not None and unchecked.endswith(': 9'), repr(unchecked))
        print("Only the image counts as needing OCR before any check:", needs is not None and needs.endswith(': 1'), repr(needs))

        # === Scenario L2: Stop lets in-flight files finish, then stops ===
        await page.evaluate("window.__STUB_PDF_SLOW = true;")
        await page.click('#text-check-btn')
        await page.wait_for_timeout(300)
        print("Progress and Stop shown while checking:", await page.locator('#text-check-progress').is_visible() and await page.locator('#text-check-stop-btn').is_visible())
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(100)
        print("Library check can't be closed mid-check:", await page.locator('#not-searchable-section').count() == 1 and await page.locator('#modal-close-btn').is_disabled())
        await page.click('#text-check-stop-btn')
        await page.evaluate("window.__STUB_PDF_SLOW = false; window.__RESOLVE_SLOW_PDFS();")
        await page.wait_for_timeout(800)
        note = await text('#text-check-note')
        # The missing file (id 6) fails at once without waiting on the slow open,
        # so a worker picks up a fifth file before Stop takes effect: 5 processed,
        # 4 of them checked, and the unreadable one stays unchecked (5 left).
        print("Stopped after the in-flight files, with a note:", note is not None and '5 of 9' in note, repr(note))
        print("...the 4 opened PDFs are counted as checked (5 left):", (await text('#not-searchable-unchecked-count') or '').endswith(': 5'))
        print("Closable again afterwards:", not await page.locator('#modal-close-btn').is_disabled())

        # === Scenario L3: running it again finishes the rest ===
        await page.click('#text-check-btn')
        await page.wait_for_timeout(1000)
        docs = await db_docs()
        print("The digital PDF is recorded as having text:", docs[2].get('has_text_layer') == 1 and docs[2].get('text_checked') == 1)
        print("...and its own text is copied into OCR text, so search finds it:", 'real embedded text' in (docs[2].get('ocr_text') or ''))
        sidecar2 = await page.evaluate("async () => { try{ const d = await window.__TEST_ROOT.getDirectoryHandle('files'); return await (await (await d.getFileHandle('2_two.txt')).getFile()).text(); }catch(e){ return null; } }")
        print("...and into its sidecar .txt:", sidecar2 is not None and 'real embedded text' in sidecar2)
        print("Scanned PDFs are recorded as checked without text:", all(docs[i].get('text_checked') == 1 and not docs[i].get('has_text_layer') for i in [5] + list(range(7, 13))))
        print("The unreadable PDF stays unchecked, to retry later:", not docs[6].get('text_checked'))
        note = await text('#text-check-note')
        print("...and the note says one couldn't be read:", note is not None and 'Could not be read: 1.' in note, repr(note))
        print("Only the unreadable PDF is left to check:", (await text('#not-searchable-unchecked-count') or '').endswith(': 1'))
        print("Needs OCR now counts the image plus the 7 scanned PDFs:", (await text('#not-searchable-count') or '').endswith(': 8'))
        print("Deleted and already-built documents were never opened:", not docs[4].get('text_checked') and not docs[3].get('text_checked'))

        # === Scenario L4: Show in table lists exactly the needs-OCR documents ===
        await page.click('#not-searchable-show-btn')
        await page.wait_for_timeout(300)
        ids = sorted(await page.locator('#doc-tbody tr').evaluate_all("rs => rs.map(r => +r.dataset.id)"))
        print("Show in table lists the needs-OCR documents:", ids == [1, 5, 7, 8, 9, 10, 11, 12], ids)
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(900)

        # === Scenario L5: Make all searchable targets only the needs-OCR bucket ===
        await page.click('#not-searchable-make-btn')
        await page.wait_for_timeout(150)
        print("Make all searchable opens the bulk dialog for the 8 needing OCR:", (await text('#make-searchable-count') or '').endswith('8'))
        await page.click('#make-searchable-start-btn')
        await page.wait_for_timeout(2500)
        status = await text('#make-searchable-status') or ''
        print("All 8 made searchable:", 'Made searchable: 8.' in status, repr(status[:80]))
        await page.click('#make-searchable-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario L6: what's left is only the unreadable PDF ===
        await open_check()
        print("Only the unreadable PDF remains, still unchecked:", (await text('#not-searchable-unchecked-count') or '').endswith(': 1') and await page.locator('#not-searchable-count').count() == 0)

        print("JS ERRORS (library check):", errors)
        await browser.close()

# === Duplicate backfill checks PDFs for text from the same read ===
SR_SEED = {
    "documents": [
        doc(1, "Digital", "files/1_d.pdf", None),
        doc(2, "Scanned", "files/2_s.pdf", None),
        doc(3, "Digital with OCR text", "files/3_t.pdf", None, ocr_text="Text kept from Mariner"),
        doc(4, "Captured with original", "files/4_c.pdf", "files/4_c/c.pdf"),
    ],
    "tags": [], "document_tags": [],
    "settings": [{"key": "searchable_pdf_built_backfill_migrated", "value": "1"}],
}
SR_FILES = {"files/1_d.pdf": TEXT_PDF, "files/2_s.pdf": SCAN_PDF, "files/3_t.pdf": TEXT_PDF + b"3",
            "files/4_c.pdf": TEXT_PDF + b"4", "files/4_c/c.pdf": TEXT_PDF + b"4o"}

async def main_shared_read():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SR_SEED)});")
        files_b64 = {k: base64.b64encode(v).decode() for k, v in SR_FILES.items()}
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
        await page.click('#tools-btn'); await page.click('#library-check-btn')
        await page.wait_for_timeout(1000)
        state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        docs = {d['id']: d for d in state['documents']}
        print("Backfill hashed every document:", all(docs[i].get('file_hash') for i in [1, 2, 3, 4]))
        print("...and checked the PDFs it read for text, without a separate pass:",
              docs[1].get('text_checked') == 1 and docs[1].get('has_text_layer') == 1 and docs[2].get('text_checked') == 1 and not docs[2].get('has_text_layer'))
        print("A PDF's own text fills empty OCR text:", 'real embedded text' in (docs[1].get('ocr_text') or ''))
        print("...but never replaces existing OCR text:", docs[3].get('ocr_text') == 'Text kept from Mariner')
        print("A document hashed from its separate original isn't text-checked by the backfill:", not docs[4].get('text_checked'))
        unchecked = page.locator('#not-searchable-unchecked-count')
        print("Only that one is left for Check for text:", await unchecked.count() == 1 and (await unchecked.inner_text()).endswith(': 1'))
        print("JS ERRORS (shared read):", errors)
        await browser.close()

asyncio.run(main())
asyncio.run(main_bulk())
asyncio.run(main_library_check())
asyncio.run(main_shared_read())
