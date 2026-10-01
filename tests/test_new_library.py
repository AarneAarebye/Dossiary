import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Creating a new library: picking a folder without a library offers a
# "<Name>.dossiary" folder created inside it (name checked, never reusing an
# existing folder), while "Use this folder as the library" still sets up the
# picked folder itself -- the main action when that folder already ends in
# .dossiary.
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1280, 'height': 900})
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

        async def pick(js_root):
            await page.evaluate(f"() => {{ window.__TEST_ROOT = {js_root}; }}")
            if await page.locator('#pick-again-btn').is_visible():
                await page.click('#pick-again-btn')   # from the no-library screen
            else:
                if await page.locator('#reload-btn').is_visible():
                    await page.click('#reload-btn')   # from an open library
                    await page.wait_for_timeout(200)
                await page.click('#open-btn')
            await page.wait_for_timeout(400)
        async def entries(expr):
            return await page.evaluate(f"async () => {{ const n = []; for await (const [k] of ({expr}).entries()) n.push(k); return n.sort(); }}")

        # === Scenario 1: a "<Name>.dossiary" folder inside the picked folder ===
        await pick("(() => { const r = window.__makeEmptyRoot(); r.name = 'Documents'; return r; })()")
        print("No-library screen shows the name form with a default name:", await page.locator('#new-library-form').is_visible()
              and await page.input_value('#new-library-name') == 'My Documents')
        print("...and previews the folder it will create:", await page.inner_text('#new-library-hint') == 'Creates the folder “My Documents.dossiary” inside “Documents”.')
        print("Creating is the main action, using the picked folder the second:", 'primary' in await page.get_attribute('#create-library-btn', 'class')
              and 'primary' not in (await page.get_attribute('#init-btn', 'class') or ''))
        await page.fill('#new-library-name', 'Tax/2026')
        await page.click('#create-library-btn')
        await page.wait_for_timeout(200)
        print("A name with a slash is refused:", 'without' in await page.inner_text('#new-library-error'))
        await page.evaluate("async () => { await window.__TEST_ROOT.getDirectoryHandle('Taken.dossiary', { create: true }); }")
        await page.fill('#new-library-name', 'Taken')
        await page.click('#create-library-btn')
        await page.wait_for_timeout(200)
        print("An existing folder is never reused:", 'already a folder called “Taken.dossiary”' in await page.inner_text('#new-library-error'))
        await page.fill('#new-library-name', 'Family Papers')
        print("Typing updates the preview and clears the error:", 'Family Papers.dossiary' in await page.inner_text('#new-library-hint')
              and await page.inner_text('#new-library-error') == '')
        await page.press('#new-library-name', 'Enter')
        await page.wait_for_timeout(600)
        print("Enter creates the library folder:", await entries('window.__TEST_ROOT') == ['Family Papers.dossiary', 'Taken.dossiary'])
        inside = await entries("await window.__TEST_ROOT.getDirectoryHandle('Family Papers.dossiary')")
        print("...with the library inside it, nothing in the picked folder itself:", 'library.sqlite' in inside and 'files' in inside and 'inbox' in inside, inside)
        print("The new library is open, named after its folder:", await page.inner_text('#sub-label') == 'Family Papers.dossiary'
              and await page.locator('#init-state').is_hidden())

        # === Scenario 2: a name already ending in .dossiary doesn't get it twice ===
        await pick("(() => { const r = window.__makeEmptyRoot(); r.name = 'Archive'; return r; })()")
        await page.fill('#new-library-name', 'Old Letters.DOSSIARY')
        print("Extension not doubled:", 'Creates the folder “Old Letters.DOSSIARY”' in await page.inner_text('#new-library-hint'))

        # === Scenario 3: a picked folder already ending in .dossiary is used as is ===
        await pick("(() => { const r = window.__makeEmptyRoot(); r.name = 'Prepared.dossiary'; return r; })()")
        print("Picked .dossiary folder: no name form, 'Use this folder' is the main action:",
              await page.locator('#new-library-form').is_hidden() and 'primary' in await page.get_attribute('#init-btn', 'class'))
        await page.click('#init-btn')
        await page.wait_for_timeout(500)
        print("...and the library is set up in it directly:", 'library.sqlite' in await entries('window.__TEST_ROOT'))

        # === Scenario 4: German ===
        await pick("(() => { const r = window.__makeEmptyRoot(); r.name = 'Ablage'; return r; })()")
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        print("Untouched default name and preview follow the language:", await page.input_value('#new-library-name') == 'Meine Dokumente'
              and 'Legt den Ordner „Meine Dokumente.dossiary“ in „Ablage“ an.' == await page.inner_text('#new-library-hint'))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
