import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

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
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededEmptyRoot([], []);")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)

        # === Scenario 1: scan_bridge_url is unset by default, persists an
        # explicit value, and survives a reopen (mirrors reminder_lookahead_days'
        # own Scenario 2 in tests/test_reminders.py) ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        url_field_present = await page.locator('#fs-scan-bridge-url').count()
        print("Scanner bridge URL field present in Field Settings:", url_field_present == 1)
        url_default = await page.evaluate("document.getElementById('fs-scan-bridge-url').value")
        print("scan_bridge_url defaults to empty with no persisted setting:", url_default == '')

        await page.fill('#fs-scan-bridge-url', 'http://127.0.0.1:8765')
        await page.dispatch_event('#fs-scan-bridge-url', 'change')
        await page.wait_for_timeout(200)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        url_row = next((s for s in persisted['settings'] if s['key'] == 'scan_bridge_url'), None)
        print("scan_bridge_url persisted as 'http://127.0.0.1:8765':", url_row['value'] if url_row else None)

        # Reopen (same convention test_reminders.py Scenario 2 uses -- re-seed a
        # fresh root with the setting already present, simulating a real reopen
        # reading the same on-disk library.sqlite back)
        seed_with_url = {'settings': [{'key': 'scan_bridge_url', 'value': 'http://127.0.0.1:8765'}]}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        url_after_reopen = await page.evaluate("document.getElementById('fs-scan-bridge-url').value")
        print("scan_bridge_url reads back as 'http://127.0.0.1:8765' after reopening:", url_after_reopen == 'http://127.0.0.1:8765')
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
