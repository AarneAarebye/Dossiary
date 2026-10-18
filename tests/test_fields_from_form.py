import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

# "Set up fields for this type…" in the capture and Edit forms: Field Settings
# opens on top of the form (a second modal layer), with the form's type
# selected -- even a brand-new one -- and closing it rebuilds the form's fields
# from the new setup without losing what was typed.

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc 1", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Organization", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 2, "name": "Year", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Paid", "type": "checkbox", "show_as_column": 0, "autocomplete": 0},
        {"id": 4, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 1, "value": "ACME"},
    ],
    "document_type_fields": [
        {"document_type": "Receipt", "field_name": "Organization", "position": 0},
    ],
    "field_descriptions": [],
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

async def dyn(page, prefix, name):
    return page.locator(f'#dynamic-fields-{prefix} [data-dynamic-field="{name}"] input')

async def shown_fields(page, prefix):
    return await page.eval_on_selector_all(f'#dynamic-fields-{prefix} [data-dynamic-field]', 'els => els.map(e => e.dataset.dynamicField)')

async def overlay_open(page):
    return await page.locator('#modal-root-over .modal').count() == 1

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Scenario 1: Edit form -- the link opens Field Settings above the form
        # with the document's type selected; adding a field keeps what was typed ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(150)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-title', 'Typed title')
        await (await dyn(page, 'e', 'Organization')).fill('Typed org')
        await page.click('#e-type-fields-btn')
        await page.wait_for_timeout(200)
        print("Edit: Field Settings opens above the form:", await overlay_open(page))
        print("Edit: the form is still open underneath:", await page.locator('#modal-root #e-title').count() == 1)
        active = await page.locator('#fs-type-list .fs-list-item.active').inner_text()
        print("Edit: the document's type is selected:", active.strip() == 'Receipt')
        await page.click('#fs-available-list [data-field="Year"] .fs-add')
        await page.wait_for_timeout(150)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(200)
        print("Edit: Done closes only Field Settings:", not await overlay_open(page) and await page.locator('#e-title').count() == 1)
        print("Edit: the new field is shown:", await shown_fields(page, 'e') == ['Organization', 'Year'])
        print("Edit: typed title kept:", await page.locator('#e-title').input_value() == 'Typed title')
        print("Edit: typed field value kept:", await (await dyn(page, 'e', 'Organization')).input_value() == 'Typed org')

        # === Scenario 2: a brand-new type typed into Edit is listed and selected,
        # Escape closes only Field Settings, and saving keeps the new setup ===
        await page.fill('#e-type', 'Invoice')
        await page.locator('#e-type').blur()
        await page.wait_for_timeout(150)
        await (await dyn(page, 'e', 'Organization')).fill('Org for invoice')
        await page.click('#e-type-fields-btn')
        await page.wait_for_timeout(200)
        types = await page.eval_on_selector_all('#fs-type-list .fs-list-item', 'els => els.map(e => e.dataset.type)')
        print("Edit: new type listed:", 'Invoice' in types)
        active = await page.locator('#fs-type-list .fs-list-item.active').inner_text()
        print("Edit: new type selected:", active.strip() == 'Invoice')
        await page.click('#fs-available-list [data-field="Paid"] .fs-add')
        await page.wait_for_timeout(100)
        await page.click('#fs-available-list [data-field="Author"] .fs-add')
        await page.wait_for_timeout(150)
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(200)
        print("Edit: Escape closes only Field Settings:", not await overlay_open(page) and await page.locator('#e-title').count() == 1)
        fields = await shown_fields(page, 'e')
        print("Edit: Invoice's fields shown:", fields[:2] == ['Paid', 'Author'])
        print("Edit: Organization still shown as orphaned with the typed value:",
              'Organization' in fields
              and await page.locator('#dynamic-fields-e [data-dynamic-field="Organization"].field-orphaned').count() == 1
              and await (await dyn(page, 'e', 'Organization')).input_value() == 'Org for invoice')
        await page.check('#dynamic-fields-e [data-dynamic-field="Paid"] input')
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        doc = next(d for d in persisted['documents'] if d['id'] == 1)
        print("Edit: saved with the new type:", doc['document_type'] == 'Invoice' and doc['title'] == 'Typed title')
        invoice_fields = sorted((r['position'], r['field_name']) for r in persisted['document_type_fields'] if r['document_type'] == 'Invoice')
        print("Edit: the new type's setup saved:", invoice_fields == [(0, 'Paid'), (1, 'Author')])
        paid_values = [r['value'] for r in persisted['document_field_values'] if r['document_id'] == 1 and r['field_id'] == 3]
        print("Edit: the checkbox ticked before saving saved:", paid_values == ['1'])

        # === Scenario 3: capture form -- a new type, backdrop click closes,
        # typed values survive two rounds ===
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        await page.fill('#f-title', 'Hello')
        await page.fill('#f-type', 'Letter')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(100)
        await page.click('#f-type-fields-btn')
        await page.wait_for_timeout(200)
        active = await page.locator('#fs-type-list .fs-list-item.active').inner_text()
        print("Capture: new type selected:", active.strip() == 'Letter')
        await page.click('#fs-available-list [data-field="Organization"] .fs-add')
        await page.wait_for_timeout(150)
        await page.mouse.click(5, 5)  # the stacked backdrop
        await page.wait_for_timeout(200)
        print("Capture: backdrop click closes only Field Settings:", not await overlay_open(page) and await page.locator('#f-title').count() == 1)
        print("Capture: the new field is shown:", await shown_fields(page, 'f') == ['Organization'])
        await (await dyn(page, 'f', 'Organization')).fill('Sender Ltd')
        await page.click('#f-type-fields-btn')
        await page.wait_for_timeout(200)
        await page.click('#fs-available-list [data-field="Year"] .fs-add')
        await page.wait_for_timeout(150)
        await page.click('#fs-modal-close-btn')
        await page.wait_for_timeout(200)
        print("Capture: second field added:", await shown_fields(page, 'f') == ['Organization', 'Year'])
        print("Capture: typed values kept:",
              await page.locator('#f-title').input_value() == 'Hello'
              and await (await dyn(page, 'f', 'Organization')).input_value() == 'Sender Ltd')

        # === Scenario 4: the default-currency guess follows a default changed in
        # Field Settings; a typed currency is left alone ===
        await page.click('#f-type-fields-btn')
        await page.wait_for_timeout(200)
        await page.click('#fs-available-list [data-field="Currency"] .fs-add')
        await page.wait_for_timeout(100)
        await page.fill('#fs-default-currency', 'EUR')
        await page.click('#fs-done-btn')  # blurring the input saves it first
        await page.wait_for_timeout(250)
        cur = await dyn(page, 'f', 'Currency')
        print("Capture: Currency shows the new default as a guess:",
              await cur.input_value() == 'EUR' and 'field-guess' in (await cur.get_attribute('class') or ''))
        await page.click('#f-type-fields-btn')
        await page.wait_for_timeout(200)
        await page.fill('#fs-default-currency', 'CHF')
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(250)
        print("Capture: an untouched guess follows the changed default:", await (await dyn(page, 'f', 'Currency')).input_value() == 'CHF')
        await (await dyn(page, 'f', 'Currency')).fill('USD')
        await page.click('#f-type-fields-btn')
        await page.wait_for_timeout(200)
        await page.fill('#fs-default-currency', 'GBP')
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(250)
        cur = await dyn(page, 'f', 'Currency')
        print("Capture: a typed currency is kept, not a guess:",
              await cur.input_value() == 'USD' and 'field-guess' not in (await cur.get_attribute('class') or ''))

        # === Scenario 5: Escape while renaming a field cancels only the rename ===
        await page.click('#f-type-fields-btn')
        await page.wait_for_timeout(200)
        await page.click('#fs-descriptions-list [data-field-name="Organization"] .fs-rename')
        await page.wait_for_timeout(100)
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(150)
        print("Rename Escape leaves Field Settings open:", await overlay_open(page) and await page.locator('.fs-rename-input').count() == 0)
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(150)
        print("A second Escape closes Field Settings, not the form:", not await overlay_open(page) and await page.locator('#f-title').count() == 1)
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(150)
        print("A third Escape closes the form:", await page.locator('#f-title').count() == 0)

        # === Scenario 6: Field Settings from the Tools menu still works as before ===
        await page.click('#tools-btn')
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        print("Tools: Field Settings opens in the normal layer:",
              await page.locator('#modal-root #fs-type-list').count() == 1 and not await overlay_open(page))
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        print("Tools: closes normally:", await page.locator('#fs-type-list').count() == 0)

        # === Scenario 7: German label ===
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        label = await page.locator('#f-type-fields-btn').inner_text()
        print("German link label:", label.strip() == 'Felder für diesen Typ einrichten…')

        print("No page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
