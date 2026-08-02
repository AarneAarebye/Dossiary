import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

FIELD_ROWS = [{"id": 1, "name": "Organization", "type": "text"}]
TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "Organization", "position": 0},
    {"document_type": "Certificate", "field_name": "People", "position": 0},
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, {json.dumps(FIELD_ROWS)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('#f-field-1', 'Acme Corp')
        await page.fill('#f-title', 'Clear Test Doc')
        with open('orphanclear.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 orphanclear")
        await page.set_input_files('#file-input', 'orphanclear.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        await page.fill('#e-type', 'Certificate')
        await page.locator('#e-type').blur()
        await page.wait_for_timeout(150)

        # Use the orphaned field's own clear button to wipe it out entirely
        await page.fill('#e-field-1', '')
        await page.wait_for_timeout(100)
        await page.click('#save-edit-btn')
        await page.wait_for_timeout(300)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("document_field_values count after clearing orphaned field (should be 0):", len(persisted['document_field_values']))
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # Re-open to confirm it's genuinely gone, not just hidden
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)
        org_count_after = await page.locator('[data-dynamic-field="Organization"]').count()
        print("Organization field gone entirely after clear+save (should be 0):", org_count_after)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
