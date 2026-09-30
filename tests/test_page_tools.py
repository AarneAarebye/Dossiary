import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, hashlib, tempfile
from playwright.async_api import async_playwright

# Page tools: "Edit pages…" (rotate, reorder, remove, add pages from a file,
# split into several documents) and bulk "Combine…". The stub's fake pdf-lib
# writes each "PDF" as a JSON page list ({src, page, rotation, text}), so the
# checks below read back exactly which pages ended up where.
BUNDLE = "%PDF-1.4 bundle"
LEGACY = "%PDF-1.4 legacy %TEXTLAYER"
RECEIPT = "%PDF-1.4 receipt"
PHOTO = "JPEGDATA photo"
sha = lambda text: hashlib.sha256(text.encode()).hexdigest()

def doc(i, title, file_path, original=None, **extra):
    d = {
        "id": i, "title": title, "category": None, "subcategory": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "import_date": f"2026-03-0{i}T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": file_path, "original_file_path": original,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }
    d.update(extra)
    return d

SEED = {
    "documents": [
        doc(1, "Scan bundle", "files/1_scan.pdf", "files/1_scan/scan.pdf", category="Bills", file_hash=sha(BUNDLE)),
        doc(2, "Legacy", "files/2_legacy.pdf", source="migrated", ocr_text="legacy text"),
        doc(3, "Photo", "files/3_photo.jpg", "files/3_photo/photo.jpg", file_hash=sha(PHOTO), ocr_text="photo text"),
        doc(4, "Receipt", "files/4_receipt.pdf"),
        doc(5, "Binned", "files/5_binned.pdf", deleted=1),
    ],
    "tags": [{"id": 1, "name": "tax"}], "document_tags": [{"document_id": 1, "tag_id": 1}],
    "people": [{"id": 1, "name": "Arne"}],
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [{"document_id": 1, "field_id": 2, "value": "12"}],
    "document_field_people": [{"document_id": 1, "field_id": 4, "person_id": 1}],
    "collections": [{"id": 1, "name": "Tax 2026", "kind": "manual", "criteria": None}],
    "collection_documents": [{"collection_id": 1, "document_id": 1}],
    "settings": [{"key": "searchable_pdf_built_backfill_migrated", "value": "1"}],
}
FILES = {
    "files/1_scan.pdf": BUNDLE, "files/1_scan/scan.pdf": BUNDLE,
    "files/2_legacy.pdf": LEGACY, "files/3_photo.jpg": PHOTO, "files/3_photo/photo.jpg": PHOTO,
    "files/4_receipt.pdf": RECEIPT, "files/5_binned.pdf": "%PDF-1.4 binned",
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
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url or 'pdf-lib' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__STUB_PDF_NUM_PAGES = 4;")
        await page.evaluate("""async (files) => {
            for(const [path, text] of Object.entries(files)){
                const parts = path.split('/');
                let dir = window.__TEST_ROOT;
                for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
                await w.write(new TextEncoder().encode(text)); await w.close();
            }
        }""", FILES)
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        async def state():
            return await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        async def read(path):
            return await page.evaluate("""async (path) => {
                const parts = path.split('/'); let dir = window.__TEST_ROOT;
                try{
                    for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part);
                    return await (await (await dir.getFileHandle(parts[parts.length - 1])).getFile()).text();
                }catch(e){ return null; }
            }""", path)
        async def pages_of(path):
            text = await read(path)
            if not text or not text.startswith('%PDF-FAKELIB'): return None
            return [(p['src'].replace('%PDF-1.4 ', '').replace(' %TEXTLAYER', ''), p['page'], p['rotation']) for p in json.loads(text.split('\n', 1)[1])['pages']]
        async def select(i):
            await page.click(f'#doc-tbody tr[data-id="{i}"] td.title-cell, #doc-tbody tr[data-id="{i}"] td:nth-child(3)')
            await page.wait_for_timeout(200)
        async def card(i, cls):
            await page.click(f'.page-card[data-pos="{i}"] .{cls}')
        docs_by_id = lambda st: {d['id']: d for d in st['documents']}

        # === Scenario 1: where "Edit pages…" is offered ===
        await select(1)
        print("Offered for a PDF in the panel:", await page.locator('#edit-pages-btn').count() == 1)
        await select(3)
        print("Not offered for an image:", await page.locator('#edit-pages-btn').count() == 0)
        await page.click('#doc-tbody tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        items = await page.locator('.row-context-menu-item').all_inner_texts()
        print("Not in the right-click menu (panel only):", not any('Edit pages' in x for x in items), items)
        await page.keyboard.press('Escape')
        await page.mouse.click(5, 895)

        # === Scenario 2: rotate, reorder, remove and split ===
        await select(1)
        await page.click('#edit-pages-btn')
        await page.wait_for_timeout(400)
        print("One card per page:", await page.locator('.page-card').count() == 4)
        print("Save disabled until something changes:", await page.locator('#pages-save-btn').is_disabled())
        await card(0, 'page-rotate-right')
        print("Rotation shows on the thumbnail:", 'rotate(90deg)' in await page.locator('.page-card[data-pos="0"] .page-thumb').get_attribute('style'))
        await card(2, 'page-move-left')           # order: 1, 3, 2, 4
        await card(3, 'page-remove')
        print("A removed page stays visible, dimmed:", 'removed' in await page.locator('.page-card[data-pos="3"]').get_attribute('class'))
        await page.click('.page-split-toggle >> nth=0')  # split after the first card
        print("Summary counts pages and documents:", await page.inner_text('#pages-summary') == 'Pages: 3 · Documents after saving: 2', await page.inner_text('#pages-summary'))
        await page.click('#pages-save-btn')
        await page.wait_for_timeout(800)
        st = await state(); by = docs_by_id(st)
        print("Dialog closed, status reports two documents:", await page.locator('#page-grid').count() == 0 and 'Saved as 2 documents' in await page.inner_text('#status'))
        print("Edited copy replaced in place (the document has its own original):", by[1]['file_path'] == 'files/1_scan.pdf' and await pages_of('files/1_scan.pdf') == [('bundle', 1, 90)], await pages_of('files/1_scan.pdf'))
        print("Original untouched:", await read('files/1_scan/scan.pdf') == BUNDLE and by[1]['original_file_path'] == 'files/1_scan/scan.pdf')
        new = max(st['documents'], key=lambda d: d['id'])
        print("Split part is a new document with the rest, in the new order:", new['id'] == 6 and await pages_of(new['file_path']) == [('bundle', 3, 0), ('bundle', 2, 0)], new['file_path'])
        print("...titled and filed like the source:", new['title'] == 'Scan bundle (2)' and new['category'] == 'Bills' and new['source'] == 'split' and new['original_file_path'] is None)
        print("...with its tags, people, amount and collection:",
              {(l['document_id'], l['tag_id']) for l in st['document_tags']} >= {(6, 1)}
              and any(l['document_id'] == 6 and l['person_id'] == 1 for l in st['document_field_people'])
              and any(v['document_id'] == 6 and v['field_id'] == 2 and v['value'] == '12' for v in st['document_field_values'])
              and any(c['collection_id'] == 1 and c['document_id'] == 6 for c in st['collection_documents']))
        print("...its own hash and a sidecar:", new['file_hash'] == hashlib.sha256((await read(new['file_path'])).encode()).hexdigest()
              and 'Category: Bills' in (await read(new['file_path'].replace('.pdf', '.txt')) or ''))
        print("Both documents in the table:", await page.locator('#doc-tbody tr[data-id="6"]').count() == 1)

        # === Scenario 3: a document with no original keeps its file as the original ===
        await select(2)
        await page.click('#edit-pages-btn')
        await page.wait_for_timeout(400)
        await card(0, 'page-rotate-left')
        await page.click('#pages-save-btn')
        await page.wait_for_timeout(600)
        d2 = docs_by_id(await state())[2]
        print("No original: the file becomes the original, the edit goes next to it:",
              d2['original_file_path'] == 'files/2_legacy.pdf' and d2['file_path'] == 'files/2_legacy_edited.pdf' and await read('files/2_legacy.pdf') == LEGACY)
        print("...rotated left:", (await pages_of('files/2_legacy_edited.pdf'))[0] == ('legacy', 1, 270))
        print("...text layer recorded, existing OCR text kept:", d2['has_text_layer'] == 1 and d2['ocr_text'] == 'legacy text')
        print("Status for a single document:", 'Pages saved.' in await page.inner_text('#status'))

        # === Scenario 4: adding pages from a file, and the last-page guard ===
        await select(4)
        await page.click('#edit-pages-btn')
        await page.wait_for_timeout(400)
        png = tempfile.NamedTemporaryFile(suffix='.png', delete=False); png.write(b'PNGDATA'); png.close()
        async with page.expect_file_chooser() as fc:
            await page.click('#pages-add-file-btn')
        await (await fc.value).set_files(png.name)
        await page.wait_for_timeout(400)
        print("An added image becomes a page:", await page.locator('.page-card').count() == 5)
        for i in range(5): await card(i, 'page-remove')
        await page.click('#pages-save-btn')
        await page.wait_for_timeout(200)
        print("Removing every page is refused:", 'At least one page' in await page.inner_text('#pages-status'))
        for i in range(5): await card(i, 'page-restore')
        await page.click('#pages-save-btn')
        await page.wait_for_timeout(600)
        d4 = docs_by_id(await state())[4]
        pages4 = await pages_of(d4['file_path'])
        print("Saved with the image as the last page:", len(pages4) == 5 and pages4[-1][0] == 'image:png', pages4)
        _os.remove(png.name)

        # === Scenario 5: combine ===
        await page.check('.row-select-checkbox[data-id="3"]')
        await page.wait_for_timeout(100)
        print("Combine hidden for a single document:", await page.locator('#bulk-combine-btn').evaluate("b => b.style.display === 'none'"))
        await page.check('.row-select-checkbox[data-id="2"]')
        await page.wait_for_timeout(100)
        print("Combine shown for two:", await page.locator('#bulk-combine-btn').evaluate("b => b.style.display !== 'none'"))
        more = page.locator('#bulk-more-menu')
        await page.click('#bulk-more-btn')
        print("More menu opens, aria-expanded set:", await more.is_visible() and await page.get_attribute('#bulk-more-btn', 'aria-expanded') == 'true')
        await page.keyboard.press('Escape')
        print("...Escape closes it:", not await more.is_visible() and await page.get_attribute('#bulk-more-btn', 'aria-expanded') == 'false')
        await page.click('#bulk-more-btn'); await page.mouse.click(700, 880)
        print("...so does a click elsewhere:", not await more.is_visible())
        box = await page.locator('#bulk-action-bar').bounding_box()
        print("Bulk bar stays one line with Combine offered:", box['height'] < 70, box['height'])
        await page.click('#bulk-more-btn'); await page.click('#bulk-combine-btn')
        print("...and choosing an item closes the menu:", not await more.is_visible())
        await page.wait_for_timeout(200)
        rows = lambda: page.locator('.combine-row').evaluate_all("rs => rs.map(r => Number(r.dataset.id))")
        before = await rows()
        await page.click('.combine-row >> nth=0 >> .combine-down')
        print("Documents can be reordered:", await rows() == before[::-1], before)
        if (await rows())[0] != 3:
            await page.click('.combine-row[data-id="3"] .combine-up')
        print("...Photo first:", await rows() == [3, 2])
        await page.check('.combine-row[data-id="3"] input[type=radio]')
        await page.click('#combine-start-btn')
        await page.wait_for_timeout(800)
        by = docs_by_id(await state())
        combined = await pages_of(by[3]['file_path'])
        print("Kept document gets the combined PDF, next to its original:", by[3]['file_path'] == 'files/3_photo.pdf' and combined == [('image:jpg', 1, 0), ('legacy', 1, 270), ('legacy', 2, 0), ('legacy', 3, 0), ('legacy', 4, 0)], by[3]['file_path'], combined)
        print("...its original untouched, the matching image copy removed:", await read('files/3_photo/photo.jpg') == PHOTO and await read('files/3_photo.jpg') is None)
        print("...OCR text of both joined:", by[3]['ocr_text'] == 'photo text\n\nlegacy text')
        print("The other document is in the Waste bin, files untouched:", by[2]['deleted'] == 1 and await read('files/2_legacy_edited.pdf') is not None)
        print("Status names the result:", 'Combined 2 documents into “Photo”' in await page.inner_text('#status'))

        # === Scenario 6: pdf-lib listed among the libraries, German labels ===
        await page.click('#libraries-link')
        await page.wait_for_timeout(150)
        print("pdf-lib credited with its license:", 'pdf-lib' in await page.inner_text('.modal') and 'MIT' in await page.inner_text('.modal'))
        await page.click('#modal-close-btn')
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        await select(1)
        print("German button label:", await page.inner_text('#edit-pages-btn') == 'Seiten bearbeiten…')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
