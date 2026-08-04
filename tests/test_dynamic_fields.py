import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

FIELD_ROWS = [
    {"id": 1, "name": "Organization", "type": "text"},
    {"id": 2, "name": "Organization To", "type": "text"},
]
TYPE_FIELD_ROWS = [
    {"document_type": "Medical Referral", "field_name": "Organization To", "position": 0},
    {"document_type": "Medical Referral", "field_name": "People", "position": 1},
    {"document_type": "Pension", "field_name": "Organization", "position": 0},
    {"document_type": "Reorder Test", "field_name": "People", "position": 0},
    {"document_type": "Reorder Test", "field_name": "Organization", "position": 1},
    {"document_type": "Reorder Test", "field_name": "Organization To", "position": 2},
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, {json.dumps(FIELD_ROWS)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)

        # Brand new/unconfigured type -> NOTHING renders (not "show everything" fallback --
        # that was the old 3-fixed-field design; the new generic system shows nothing until
        # a type is explicitly configured, matching Mariner's own real behavior)
        container_children = await page.evaluate("document.getElementById('dynamic-fields-f').children.length")
        print("--- No type selected: container children (should be 0) ---", container_children)

        await page.fill('#f-type', 'Medical Referral')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        org_count = await page.locator('[data-dynamic-field="Organization"]').count()
        org_to_count = await page.locator('[data-dynamic-field="Organization To"]').count()
        people_count = await page.locator('[data-dynamic-field="People"]').count()
        print("--- Type = Medical Referral ---")
        print(f"Organization present (should be 0 -- not configured for this type): {org_count}")
        print(f"Organization To present (should be 1): {org_to_count}")
        print(f"People present (should be 1): {people_count}")

        await page.fill('#f-type', 'Pension')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        org_count = await page.locator('[data-dynamic-field="Organization"]').count()
        org_to_count = await page.locator('[data-dynamic-field="Organization To"]').count()
        people_count = await page.locator('[data-dynamic-field="People"]').count()
        print("--- Type = Pension ---")
        print(f"Organization present (should be 1): {org_count}")
        print(f"Organization To present (should be 0): {org_to_count}")
        print(f"People present (should be 0): {people_count}")

        await page.fill('#f-type', 'Some Brand New Type')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        container_children2 = await page.evaluate("document.getElementById('dynamic-fields-f').children.length")
        print("--- Type = unknown new type: container children (should be 0) ---", container_children2)

        # Real reorder test: People should end up FIRST, before Organization/Organization To
        await page.fill('#f-type', 'Reorder Test')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        order2 = await page.evaluate("""
            Array.from(document.getElementById('dynamic-fields-f').children).map(el => el.dataset.dynamicField)
        """)
        print("DOM order for Reorder Test (should be [People, Organization, Organization To]):", order2)

        # Known, accepted behavior: switching types rebuilds the container from scratch,
        # so a value typed into a field that's then removed is NOT retained (documented
        # tradeoff of the fully-dynamic field system vs. the old fixed 3-field show/hide).
        await page.fill('#f-type', 'Pension')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('#f-field-1', 'Deutsche Rentenversicherung')
        await page.fill('#f-type', 'Medical Referral')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        org_still_present = await page.locator('[data-dynamic-field="Organization"]').count()
        print("Organization field removed after switching away from Pension (expected, by design):", org_still_present == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
