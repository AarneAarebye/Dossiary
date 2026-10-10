import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Tools → Toolbar buttons…: the daily toolbar buttons a library doesn't use
# can be hidden (never Add document or Tools), live and remembered per
# library; ticking one again brings it back; a hidden button stays hidden
# even where other code sets its display (Details in Reports and back).
SEED = {"documents": [{"id": 1, "title": "Letter", "category": "Home", "document_type": "Letter", "date": "2026-03-01",
                       "import_date": "2026-03-01T10:00:00Z", "created_at": "2026-03-01T10:00:00Z", "file_path": "files/1.pdf",
                       "source": "captured", "archived": 0, "needs_review": 0, "deleted": 0}]}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.evaluate("""() => { window.fetch = async (url) => {
            if(url === 'http://localhost:8765/health') return new Response(JSON.stringify({service: 'scanix500-bridge'}), {status: 200});
            throw new TypeError('Failed to fetch'); }; }""")
        await page.click('#open-btn')
        await page.wait_for_timeout(500)
        await page.wait_for_timeout(200)

        visible = lambda sel: page.locator(sel).is_visible()
        async def open_dialog():
            await page.click('#tools-btn')
            await page.click('#toolbar-buttons-btn')
            await page.wait_for_timeout(200)
        def box(label):
            return page.locator('.toolbar-buttons-list label', has_text=label).locator('input')

        print("All buttons show by default:", all([await visible(s) for s in ['#inbox-check-btn', '#check-reminders-btn', '#scan-btn', '#scan-multi-btn', '#detail-panel-toggle-btn', '#columns-btn']]))
        await open_dialog()
        labels = await page.locator('.toolbar-buttons-list label').all_inner_texts()
        print("The dialog lists the optional buttons, ticked:", [l.strip() for l in labels] == ['📥 Check inbox', '🔔 Check reminders', '📷 Scan', '📸 Scan Multi', '☰ Details', '⚙ Columns']
              and await page.locator('.toolbar-buttons-list input:checked').count() == 6)
        print("...but not Add document or Tools:", not any('Add document' in l or 'Tools' in l for l in labels))
        await box('Scan').first.uncheck()
        await box('Scan Multi').uncheck()
        await box('Columns').uncheck()
        await box('Details').uncheck()
        await page.wait_for_timeout(200)
        print("Unticking hides them at once:", not await visible('#scan-btn') and not await visible('#scan-multi-btn')
              and not await visible('#columns-btn') and not await visible('#detail-panel-toggle-btn') and await visible('#inbox-check-btn'))
        await page.click('#toolbar-buttons-done-btn')
        db = await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")
        print("The choice is saved in the library:", sorted(json.loads(next(r['value'] for r in db['settings'] if r['key'] == 'hidden_toolbar_buttons'))) == ['columns', 'details', 'scan', 'scan-multi'])

        await page.click('#nav-item-reports')
        await page.wait_for_timeout(200)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)
        print("Details stays hidden after Reports (which sets its display):", not await visible('#detail-panel-toggle-btn'))

        await page.click('#reload-btn')
        await page.wait_for_timeout(200)
        await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("...and after reopening the library:", not await visible('#scan-btn') and not await visible('#columns-btn') and await visible('#add-btn') and await visible('#tools-btn'))

        await open_dialog()
        await box('Scan').first.check()
        await page.wait_for_timeout(200)
        print("Ticking a button again brings it back:", await visible('#scan-btn') and not await visible('#scan-multi-btn'))
        await page.click('#toolbar-buttons-done-btn')

        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(200)
        await open_dialog()
        print("German labels:", await page.inner_text('.modal h2') == 'Buttons der Werkzeugleiste'
              and '📷 Scannen' in [l.strip() for l in await page.locator('.toolbar-buttons-list label').all_inner_texts()])

        print("ERRORS:", errors)
        await browser.close()

asyncio.run(main())
