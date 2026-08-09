import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json
from playwright.async_api import async_playwright

# Three old-shape documents, exactly what a library predating this migration
# looks like:
# - doc 1: source='captured', original_file_path set -- under the OLD rule this
#   could only mean the searchable-PDF branch ran, so should be backfilled to
#   searchable_pdf_built=1.
# - doc 2: source='migrated', original_file_path set -- Mariner's own layout,
#   unrelated to Dossiary's OCR pipeline; must NOT be backfilled.
# - doc 3: source='scan-inbox', original_file_path NOT set -- addInboxFile()
#   never set it under the old rule; stays unbackfilled (falsy/0).
SEED = {
    "documents": [
        {
            "id": 1, "title": "Old Searchable Capture", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": "Hello", "ocr_language": "eng",
            "file_path": "files/1_doc.pdf", "original_file_path": "files/1_doc/original.jpg",
            "created_at": "2026-01-01T00:00:00Z", "source": "captured", "source_legacy_id": None,
        },
        {
            "id": 2, "title": "Migrated Doc", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_doc.pdf", "original_file_path": "files/2_doc/original.pdf",
            "created_at": "2026-01-01T00:00:00Z", "source": "migrated", "source_legacy_id": 9,
        },
        {
            "id": 3, "title": "Inbox Doc", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_doc.jpg", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00Z", "source": "scan-inbox", "source_legacy_id": None,
        },
    ],
    "tags": [], "document_tags": [],
}

async def read_docs(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text()).documents;
        })()
    """)

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        docs = await read_docs(page)
        by_id = {d['id']: d for d in docs}
        print("doc1 (captured, had original) searchable_pdf_built (should be 1):", by_id[1].get('searchable_pdf_built'))
        print("doc2 (migrated, had original) searchable_pdf_built (should stay unset/falsy, NOT backfilled):", by_id[2].get('searchable_pdf_built'))
        print("doc3 (scan-inbox, no original) searchable_pdf_built (should stay unset/falsy):", by_id[3].get('searchable_pdf_built'))

        # === Idempotency: reopening the same (now-migrated) library doesn't
        # re-run the backfill or change any value ===
        await page.click('#reload-btn')
        await page.wait_for_timeout(400)
        docs2 = await read_docs(page)
        by_id2 = {d['id']: d for d in docs2}
        print("doc1 stable after reopen (should still be 1):", by_id2[1].get('searchable_pdf_built'))
        print("doc2 stable after reopen (should still be unset/falsy):", by_id2[2].get('searchable_pdf_built'))
        print("doc3 stable after reopen (should still be unset/falsy):", by_id2[3].get('searchable_pdf_built'))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
