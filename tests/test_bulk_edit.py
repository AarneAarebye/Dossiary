import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Four plain documents (1-4, no custom fields yet -- Tasks 2/3 add fixtures with
# custom fields of their own) plus one deleted document (5, reachable only via
# the Waste bin) so Scenario 1 can confirm #bulk-edit-btn is hidden there.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Invoice A", "category": "Finance", "subcategory": "Utilities",
            "document_type": "Invoice", "date": "2026-01-01T00:00:00+00:00", "notes": "Original note",
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Invoice B", "category": "Finance", "subcategory": "Rent",
            "document_type": "Invoice", "date": "2026-01-02T00:00:00+00:00", "notes": None,
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-01-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Letter C", "category": None, "subcategory": None,
            "document_type": "Letter", "date": None, "notes": None,
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 4, "title": "Untouched D", "category": "Legal", "subcategory": None,
            "document_type": "Letter", "date": "2026-01-04T00:00:00+00:00", "notes": None,
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-01-04T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 5, "title": "Deleted E", "category": "Finance", "subcategory": None,
            "document_type": "Invoice", "date": "2026-01-05T00:00:00+00:00", "notes": None,
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/5_e.pdf", "original_file_path": None,
            "created_at": "2026-01-05T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
    ],
    "tags": [], "document_tags": [],
}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    stub_js = open('stub_studio2.js').read()
    await page.add_init_script(stub_js)

async def read_db(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)

async def open_library(page):
    await route_stub(page)
    await page.goto(f"file://{APP_PATH}")
    await page.wait_for_timeout(200)
    await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
    await page.click("#open-btn")
    await page.wait_for_timeout(400)

async def select_rows(page, ids):
    for doc_id in ids:
        await page.check(f'tr[data-id="{doc_id}"] .row-select-checkbox')
    await page.wait_for_timeout(150)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await open_library(page)

        # === Scenario 1: #bulk-edit-btn shows whenever 1+ rows are selected in
        # every view except the Waste bin, matching #bulk-archive-btn's own
        # existing visibility rule ===
        await select_rows(page, [1, 2])
        edit_btn_visible = await page.locator('#bulk-edit-btn:visible').count()
        print("bulk edit button visible with 2 selected in All Documents:", edit_btn_visible == 1)

        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        await select_rows(page, [5])
        edit_btn_hidden_in_trash = await page.locator('#bulk-edit-btn:visible').count()
        print("bulk edit button hidden in Waste bin:", edit_btn_hidden_in_trash == 0)

        await page.click('#bulk-clear-selection-btn')
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 2: opening the bulk-edit form shows every scalar
        # replace-semantics field genuinely blank (never pre-filled from any one
        # selected document's own value) with its Apply checkbox unchecked ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        modal_title = await page.locator('.modal h2').inner_text()
        print("modal title mentions the selected count:", "2" in modal_title)
        for field_id, apply_id in [
            ('bulk-type', 'bulk-apply-type'), ('bulk-category', 'bulk-apply-category'),
            ('bulk-subcategory', 'bulk-apply-subcategory'), ('bulk-date', 'bulk-apply-date'),
            ('bulk-notes', 'bulk-apply-notes'),
        ]:
            value = await page.locator(f'#{field_id}').input_value()
            checked = await page.locator(f'#{apply_id}').is_checked()
            disabled = await page.locator(f'#{field_id}').is_disabled()
            print(f"{field_id} starts blank / Apply unchecked / input disabled:", value == '' and not checked and disabled)
        await page.click('#bulk-edit-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 3: checking Apply and typing a value writes it to every
        # selected document, and leaves an unselected document (id 4) untouched ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('#bulk-apply-category')
        await page.fill('#bulk-category', 'Bulk-Set Category')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        docs_by_id = {d['id']: d for d in persisted['documents']}
        print("doc 1 category bulk-set:", docs_by_id[1]['category'] == 'Bulk-Set Category')
        print("doc 2 category bulk-set:", docs_by_id[2]['category'] == 'Bulk-Set Category')
        print("doc 4 (not selected) category untouched:", docs_by_id[4]['category'] == 'Legal')
        print("selection survives a bulk-edit save:", await page.locator('tr[data-id="1"] .row-select-checkbox').is_checked())

        # === Scenario 4: leaving Apply unchecked on a field never touches it,
        # regardless of what's typed into its input ===
        await select_rows(page, [3, 4])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.fill('#bulk-notes', 'should never be saved', force=True)  # Apply left unchecked (input disabled, so force the fill)
        await page.check('#bulk-apply-subcategory')
        await page.fill('#bulk-subcategory', 'Bulk-Set Subcategory')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        docs_by_id = {d['id']: d for d in persisted['documents']}
        print("doc 3 notes untouched despite typed text (Apply unchecked):", docs_by_id[3]['notes'] is None)
        print("doc 3 subcategory bulk-set (Apply checked):", docs_by_id[3]['subcategory'] == 'Bulk-Set Subcategory')

        # === Scenario 5: Apply checked with a blank value is an explicit clear ===
        await page.click('#bulk-clear-selection-btn')
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('#bulk-apply-category')  # leave input blank
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        docs_by_id = {d['id']: d for d in persisted['documents']}
        print("doc 1 category cleared by Apply-checked + blank:", docs_by_id[1]['category'] is None)
        print("doc 2 category cleared by Apply-checked + blank:", docs_by_id[2]['category'] is None)

        # === Scenario 6: saving with every Apply box unchecked is a genuine no-op ===
        await select_rows(page, [3, 4])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        before = await read_db(page)
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        after = await read_db(page)
        print("saving with nothing checked changes nothing:", before['documents'] == after['documents'])

        print("JS ERRORS so far:", errors)
        await browser.close()

asyncio.run(main())
