"""Manual check: Dossiary's scan dialog against the real reference helper.

Not part of the suite (named manual_* so suite runners skip it): it needs
~/Projects/Paperless/dossiary-scan-helper next to this repo. Starts the
reference helper on port 8766 (fake scanners, pairing code 000000), opens
Dossiary with the test stub's fake library, pairs through the dialog, scans
with "Fake Splitter" and split on blank pages, and expects two documents.
"""
import os, subprocess, sys, time, asyncio
os.chdir(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.abspath(os.path.join('..', 'dossiary.html'))
HELPER_REPO = os.path.expanduser('~/Projects/Paperless/dossiary-scan-helper/reference')
from playwright.async_api import async_playwright


async def main():
    helper = subprocess.Popen([sys.executable, '-m', 'scanbridge_ref', '--port', '8766'], cwd=HELPER_REPO,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(1)
    try:
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
            await page.add_init_script("window.__ALLOW_REAL_HELPERS = true;")
            await page.add_init_script(open('stub_studio2.js').read())
            await page.goto(f"file://{APP_PATH}")
            await page.wait_for_timeout(200)
            await page.evaluate("localStorage.removeItem('dossiary_scan_tokens')")
            await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({}); window.__TEST_ROOT.name = 'RefLib';")
            await page.click('#open-btn')
            await page.wait_for_timeout(1500)

            await page.click('#scan-btn')
            await page.wait_for_timeout(1500)
            row = '.scan-pair-row[data-url="http://localhost:8766"]'
            print("reference helper shows a pair row:", await page.locator(row).count() == 1)
            await page.fill(f'{row} .scan-pair-code', '000000')
            await page.click(f'{row} .scan-pair-btn')
            await page.wait_for_timeout(1500)
            options = await page.eval_on_selector_all('#scan-dialog-scanner option', 'els => els.map(e => e.textContent)')
            print("its seven fake scanners are listed:", sum(1 for o in options if o.startswith('Fake ')) == 7)
            print("Scan Multi shown (Fake Splitter can split):", await page.is_visible('#scan-multi-btn'))
            await page.select_option('#scan-dialog-scanner', 'http://localhost:8766|fake:splitter')
            await page.check('.scan-dialog-extra[data-extra=splitOnBlank]')
            await page.click('#scan-dialog-start-btn')
            await page.wait_for_timeout(3000)
            db = await page.evaluate("(async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text()))()")
            print("split on blank pages gave two documents:", len(db['documents']) == 2)

            await page.click('#scan-btn')
            await page.wait_for_timeout(1500)
            await page.select_option('#scan-dialog-scanner', 'http://localhost:8766|fake:offline')
            await page.click('#scan-dialog-start-btn')
            await page.wait_for_timeout(1500)
            print("an offline scanner's 503 message is shown:", len(await page.inner_text('#scan-dialog-status')) > 0)
            print("no page errors:", errors == [])
            await browser.close()
    finally:
        helper.terminate()
        helper.wait()

asyncio.run(main())
