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

SEED_WITH_FIELDS = {
    "documents": SEED["documents"],
    # doc 1 starts with a pre-existing "old-tag" so Scenario 10b can prove
    # Replace mode actually discards it (Add mode, tested in Scenario 10, has
    # nothing to prove discarding since it never removes anything).
    "tags": [{"id": 1, "name": "old-tag"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}],
    "fields": [
        {"id": 1, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Vendor", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 3, "name": "Paid", "type": "checkbox", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_type_fields": [
        {"document_type": "Invoice", "field_name": "Vendor", "position": 0},
        {"document_type": "Invoice", "field_name": "Paid", "position": 1},
        {"document_type": "Letter", "field_name": "Author", "position": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 2, "value": "Acme Corp"},
        {"document_id": 1, "field_id": 3, "value": "1"},
        {"document_id": 2, "field_id": 3, "value": "0"},
    ],
    "document_field_people": [
        {"document_id": 3, "field_id": 1, "person_id": 100},
    ],
    "people": [{"id": 100, "name": "Jane Author"}],
}

async def main2():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED_WITH_FIELDS)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Scenario 7: selecting an Invoice (Vendor-configured) and a Letter
        # (Author-configured) shows both fields, Author rendered as a
        # comma-separated person-type input with the Add/Replace toggle ===
        await select_rows(page, [1, 3])  # doc 1 = Invoice, doc 3 = Letter
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        author_input_present = await page.locator('#bulk-field-1').count()
        author_mode_toggle_present = await page.locator('input[name="bulk-field-1-mode"]').count()
        print("Author (person-type) field rendered with its mode toggle:", author_input_present == 1 and author_mode_toggle_present == 2)

        # === Scenario 8: default mode is "Add to existing" -- typing a name adds
        # to doc 3's existing Author ("Jane Author") without removing it ===
        await page.fill('#bulk-field-1', 'New Coauthor')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        author_links = [r for r in persisted['document_field_people'] if r['field_id'] == 1 and r['document_id'] == 3]
        people_by_id = {p['id']: p['name'] for p in persisted['people']}
        author_names = sorted(people_by_id[r['person_id']] for r in author_links)
        print("Add mode keeps existing Author and adds the new one:", author_names == ['Jane Author', 'New Coauthor'])

        # === Scenario 9: switching to "Replace existing" and saving discards
        # whatever was there before ===
        await select_rows(page, [1, 3])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('input[name="bulk-field-1-mode"][value="replace"]')
        await page.fill('#bulk-field-1', 'Only This Author')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        author_links = [r for r in persisted['document_field_people'] if r['field_id'] == 1 and r['document_id'] == 3]
        people_by_id = {p['id']: p['name'] for p in persisted['people']}
        author_names = sorted(people_by_id[r['person_id']] for r in author_links)
        print("Replace mode discards prior Author names:", author_names == ['Only This Author'])

        # === Scenario 10: Tags default Add mode -- typed tags add without
        # removing what's already there; blank input on Add mode is a no-op ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.fill('#bulk-tags', 'urgent')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        tag_names = {t['id']: t['name'] for t in persisted['tags']}
        doc1_tags = sorted(tag_names[r['tag_id']] for r in persisted['document_tags'] if r['document_id'] == 1)
        print("Tags Add mode adds a new tag, keeping the pre-existing one:", doc1_tags == ['old-tag', 'urgent'])

        # === Scenario 10b: switching Tags to "Replace existing" and saving
        # discards doc 1's pre-existing "old-tag"/"urgent" entirely, leaving
        # only what was just typed ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('input[name="bulk-tags-mode"][value="replace"]')
        await page.fill('#bulk-tags', 'only-this-tag')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        tag_names = {t['id']: t['name'] for t in persisted['tags']}
        doc1_tags = sorted(tag_names[r['tag_id']] for r in persisted['document_tags'] if r['document_id'] == 1)
        print("Tags Replace mode discards prior tags:", doc1_tags == ['only-this-tag'])

        # === Scenario 11: the comma-autocomplete dropdown for #bulk-tags
        # renders positioned right under its own input, not off in some
        # unrelated ancestor's corner (regression check for the
        # .bulk-autocomplete-wrap positioning fix -- #bulk-tags has no
        # .field-with-clear wrapper, unlike #e-tags/#f-tags, so it needs its
        # own position:relative anchor for the dropdown to size against) ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.fill('#bulk-tags', 'only')
        await page.wait_for_timeout(150)
        input_box = await page.locator('#bulk-tags').bounding_box()
        dropdown_box = await page.locator('#bulk-tags').locator('xpath=following::div[contains(@class,"comma-autocomplete-dropdown")][1]').bounding_box()
        dropdown_near_input = dropdown_box is not None and abs(dropdown_box['y'] - input_box['y']) < 50
        print("Tags autocomplete dropdown renders near its own input:", dropdown_near_input)
        await page.click('#bulk-edit-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 12: Vendor (configured only for Invoice, not Letter) shows
        # with .field-orphaned styling since it isn't common to both selected
        # types; a checkbox-type field shows its own separate value checkbox ===
        await select_rows(page, [1, 3])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        vendor_field_orphaned = await page.locator('#bulk-field-2').locator('xpath=ancestor::div[contains(@class,"field-orphaned")]').count()
        print("Vendor field renders with .field-orphaned styling:", vendor_field_orphaned == 1)

        # === Scenario 13: checking Vendor's Apply box and typing a value writes
        # it to every selected document, including doc 3 (Letter), where Vendor
        # isn't normally configured at all -- same as editing an orphaned field
        # already does for a single document ===
        await page.check('#bulk-apply-field-2')
        await page.fill('#bulk-field-2', 'New Vendor LLC')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        vendor_values = {r['document_id']: r['value'] for r in persisted['document_field_values'] if r['field_id'] == 2}
        print("doc 1 Vendor bulk-set:", vendor_values.get(1) == 'New Vendor LLC')
        print("doc 3 (orphaned) Vendor also bulk-set:", vendor_values.get(3) == 'New Vendor LLC')

        # === Scenario 13b: a checkbox-type field's "Apply to all" and its own
        # Yes/No value checkbox are independent -- doc 1 starts Paid=1, doc 2
        # starts Paid=0. Toggling the VALUE checkbox while leaving Apply
        # unchecked changes nothing on save; checking Apply then saves
        # whatever the value checkbox currently shows (unchecked = "0") to
        # every selected document regardless of each one's prior value ===
        await page.click('#bulk-clear-selection-btn')
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        # The value checkbox is disabled (Apply is unchecked), so a real click can't
        # toggle it -- set its .checked directly via JS to prove the independence
        # property even in this edge case: since Apply stays unchecked, the field
        # is skipped entirely on save regardless of what the (unreachable-by-a-real-
        # user) value checkbox's state happens to be.
        await page.evaluate("document.getElementById('bulk-field-3').checked = true")
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        paid_values = {r['document_id']: r['value'] for r in persisted['document_field_values'] if r['field_id'] == 3}
        print("Paid untouched on both docs when only the value checkbox was toggled (Apply unchecked):", paid_values.get(1) == '1' and paid_values.get(2) == '0')

        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('#bulk-apply-field-3')  # Apply checked; value checkbox left unchecked ("No")
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        paid_values = {r['document_id']: r['value'] for r in persisted['document_field_values'] if r['field_id'] == 3}
        print("Paid bulk-set to '0' on both docs once Apply is checked:", paid_values.get(1) == '0' and paid_values.get(2) == '0')

        # === Scenario 14: the sidecar .txt for an affected document reflects the
        # complete post-edit state, not just the fields that changed ===
        sidecar_text = await page.evaluate("""
            (async () => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await dir.getFileHandle('1_a.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        print("sidecar reflects the bulk-set Vendor value:", 'New Vendor LLC' in sidecar_text)
        print("sidecar still reflects the document's own unrelated title:", 'Invoice A' in sidecar_text)

        print("JS ERRORS (main2):", errors)
        await browser.close()

asyncio.run(main2())
