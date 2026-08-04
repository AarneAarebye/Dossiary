import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [
    {"document_type": "Invoice", "field_name": "People", "position": 0},
]

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, []);")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Capture form: fill type, verify dynamic fields show, clear it, verify they hide ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        people_present_before = await page.locator('[data-dynamic-field="People"]').count()
        print("People field present after selecting Invoice:", people_present_before)

        clear_btn_visible = await page.locator('#f-type-clear').is_visible()
        print("clear button visible:", clear_btn_visible)

        await page.click('#f-type-clear')
        await page.wait_for_timeout(150)
        type_value_after_clear = await page.locator('#f-type').input_value()
        people_present_after = await page.locator('[data-dynamic-field="People"]').count()
        print("f-type value after clear (should be empty):", repr(type_value_after_clear))
        print("People field present after clear (should be 0):", people_present_after)

        focused_id = await page.evaluate("document.activeElement.id")
        print("focus returned to f-type after clear:", focused_id == 'f-type')

        # === Edit form: same check, with a real document ===
        await page.fill('#f-type', 'Invoice')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(100)
        with open('cleartest.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 cleartest")
        await page.set_input_files('#file-input', 'cleartest.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Clear Button Test')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(200)

        edit_clear_visible = await page.locator('#e-type-clear').is_visible()
        print("edit form clear button visible:", edit_clear_visible)
        await page.click('#e-type-clear')
        await page.wait_for_timeout(150)
        edit_type_value = await page.locator('#e-type').input_value()
        print("e-type value after clear (should be empty):", repr(edit_type_value))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
