import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# The "🛠 Tools" toolbar dropdown: occasional-use actions (Manage fields,
# Manage collections, Library check, Storage stats, Switch library) live in it
# instead of directly on the toolbar; daily actions stay on the toolbar.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc", "category": None, "document_type": None,
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
}

MENU_IDS = ['manage-fields-btn', 'manage-collections-btn', 'library-check-btn', 'storage-stats-btn', 'reload-btn']
TOOLBAR_IDS = ['inbox-check-btn', 'check-reminders-btn', 'scan-btn', 'scan-multi-btn', 'add-btn', 'detail-panel-toggle-btn', 'columns-btn', 'tools-btn']

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
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        async def visible(i): return await page.locator(f'#{i}').is_visible()
        async def menu_open(): return await page.locator('#tools-menu').is_visible()

        # === Scenario 1: daily actions on the toolbar, occasional ones hidden in Tools ===
        print("Daily actions stay visible on the toolbar:", all([await visible(i) for i in TOOLBAR_IDS]))
        print("Occasional actions are not shown until Tools is opened:", not any([await visible(i) for i in MENU_IDS]))
        print("Tools menu starts closed, aria-expanded=false:", not await menu_open() and await page.get_attribute('#tools-btn', 'aria-expanded') == 'false')

        # === Scenario 2: opening shows every item, in order, with a divider before Switch library ===
        await page.click('#tools-btn')
        await page.wait_for_timeout(100)
        print("Clicking Tools opens the menu, aria-expanded=true:", await menu_open() and await page.get_attribute('#tools-btn', 'aria-expanded') == 'true')
        order = await page.locator('#tools-menu > *').evaluate_all("els => els.map(e => e.id || e.className)")
        print("Items in order, divider before Switch library:", order == MENU_IDS[:4] + ['tools-menu-divider', 'reload-btn'], order)
        print("Every item is visible while open:", all([await visible(i) for i in MENU_IDS]))

        # === Scenario 3: choosing an item runs it and closes the menu ===
        await page.click('#library-check-btn')
        await page.wait_for_timeout(400)
        print("Choosing Library check opens its modal:", await page.locator('#duplicates-list').count() == 1)
        print("...and closes the Tools menu:", not await menu_open() and await page.get_attribute('#tools-btn', 'aria-expanded') == 'false')
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
        await page.wait_for_timeout(300)
        print("Choosing Manage fields opens Field Settings:", await page.locator('#fs-descriptions-list').count() == 1 and not await menu_open())
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 4: Escape and an outside click close it ===
        await page.click('#tools-btn')
        await page.wait_for_timeout(100)
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(100)
        focused = await page.evaluate("document.activeElement && document.activeElement.id")
        print("Escape closes the menu and returns focus to Tools:", not await menu_open() and focused == 'tools-btn', focused)
        await page.click('#tools-btn')
        await page.wait_for_timeout(100)
        await page.click('#search')
        await page.wait_for_timeout(100)
        print("Clicking elsewhere closes the menu:", not await menu_open() and await page.get_attribute('#tools-btn', 'aria-expanded') == 'false')
        await page.click('#tools-btn'); await page.click('#tools-btn')
        await page.wait_for_timeout(100)
        print("Clicking Tools again toggles it closed:", not await menu_open())

        # === Scenario 5: only one toolbar dropdown open at a time ===
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        await page.click('#tools-btn')
        await page.wait_for_timeout(100)
        print("Opening Tools closes Columns:", await menu_open() and not await page.locator('#columns-menu').is_visible())
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        print("Opening Columns closes Tools:", await page.locator('#columns-menu').is_visible() and not await menu_open())

        # === Scenario 6: labels follow the UI language ===
        await page.click('#search')
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        print("Tools label translates:", await page.inner_text('#tools-btn') == '🛠 Werkzeuge ▾')
        await page.click('#tools-btn')
        await page.wait_for_timeout(100)
        print("Menu items translate too:", 'Speichernutzung' in await page.inner_text('#storage-stats-btn'))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
