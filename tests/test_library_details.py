import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# A library's own title and description ("Library details", Tools menu):
# two settings rows (library_title, library_description) shown in the header,
# the description as the header's tooltip. See
# docs/superpowers/specs/2026-11-07-library-details-design.md.
SEED = {"documents": [], "tags": [], "document_tags": []}

async def library(page):
    return await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")

async def settings(page):
    return {r['key']: r['value'] for r in (await library(page))['settings']}

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

        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'Birgit.dossiary';" % json.dumps(SEED))
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        async def open_dialog():
            await page.click('#tools-btn')
            await page.click('#library-details-btn')
            await page.wait_for_timeout(150)

        async def save(title, description):
            await open_dialog()
            await page.fill('#library-details-title', title)
            await page.fill('#library-details-description', description)
            await page.click('#library-details-save-btn')
            await page.wait_for_timeout(300)

        # === Scenario 1: Tools has the entry and the dialog opens ===
        print("Header shows the folder name with no title:", await page.inner_text('#sub-label') == 'Birgit.dossiary')
        print("...and no tooltip:", await page.get_attribute('#sub-label', 'title') is None)
        await page.click('#tools-btn')
        print("Tools has Library details:", await page.locator('#library-details-btn').is_visible())
        await page.click('#library-details-btn')
        await page.wait_for_timeout(150)
        print("The Tools menu closed:", not await page.locator('#tools-menu').is_visible())
        modal_text = await page.inner_text('.modal')
        print("The dialog starts empty:",
              await page.input_value('#library-details-title') == '' and await page.input_value('#library-details-description') == '')
        print("...with the folder-name hint:", 'Empty: the folder name “Birgit.dossiary” is shown.' in modal_text)
        print("...and its heading:", 'Library details' in modal_text)
        print("The inputs carry maxlength 60 / 300:",
              await page.get_attribute('#library-details-title', 'maxlength') == '60'
              and await page.get_attribute('#library-details-description', 'maxlength') == '300')
        await page.click('#library-details-cancel-btn')
        await page.wait_for_timeout(100)
        print("Cancel closes the dialog:", await page.locator('.modal').count() == 0)
        print("Cancel writes nothing:", 'library_title' not in await settings(page))

        # === Scenario 2: save a title and a description ===
        await save('Birgit’s papers', 'Everything about\nthe house   and car')
        print("The dialog closed:", await page.locator('.modal').count() == 0)
        print("The header shows the title:", await page.inner_text('#sub-label') == 'Birgit’s papers')
        print("...with the cleaned description as tooltip:", await page.get_attribute('#sub-label', 'title') == 'Everything about the house and car')
        s = await settings(page)
        print("Both are stored in settings:", s.get('library_title') == 'Birgit’s papers' and s.get('library_description') == 'Everything about the house and car')
        print("The status line says saved:", 'Library details saved.' in await page.inner_text('#status'))
        await open_dialog()
        print("Reopening prefills both:",
              await page.input_value('#library-details-title') == 'Birgit’s papers'
              and await page.input_value('#library-details-description') == 'Everything about the house and car')
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(100)
        print("Escape closes the dialog:", await page.locator('.modal').count() == 0)

        # === Scenario 3: limits and whitespace ===
        # maxlength stops typing, so set the values directly to check the
        # save-side cut as well.
        await open_dialog()
        await page.evaluate("() => { document.getElementById('library-details-title').value = 'T'.repeat(100); document.getElementById('library-details-description').value = 'D'.repeat(400); }")
        await page.click('#library-details-save-btn')
        await page.wait_for_timeout(300)
        s = await settings(page)
        print("A 100-character title is cut to 60:", s.get('library_title') == 'T' * 60)
        print("A 400-character description is cut to 300:", s.get('library_description') == 'D' * 300)
        await save('   ', '  a  note ')
        print("A title of only spaces counts as not set (folder name shown):", await page.inner_text('#sub-label') == 'Birgit.dossiary')
        print("...while the description stays as tooltip:", await page.get_attribute('#sub-label', 'title') == 'a note')
        print("...and the stored title is empty:", (await settings(page)).get('library_title') == '')

        # === Scenario 4: clearing both brings back the folder name ===
        await save('Something', 'Else')
        await save('', '')
        print("Clearing both brings back the folder name:", await page.inner_text('#sub-label') == 'Birgit.dossiary')
        print("...and removes the tooltip:", await page.get_attribute('#sub-label', 'title') is None)
        s = await settings(page)
        print("...stored as empty values:", s.get('library_title') == '' and s.get('library_description') == '')

        # A language change keeps the title (applyI18n only rewrites the header
        # when no library is open).
        await save('Kept title', 'Kept note')
        await page.select_option('#lang-select', 'fr')
        await page.wait_for_timeout(150)
        print("A language change keeps the title:", await page.inner_text('#sub-label') == 'Kept title')
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(150)

        # === Scenario 8: a library with details written by another device ===
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")
        await page.wait_for_timeout(200)
        print("Switching away shows the empty-state title:", await page.inner_text('#sub-label') == 'No library open')
        print("...with no tooltip:", await page.get_attribute('#sub-label', 'title') is None)
        seeded = dict(SEED, settings=[{"key": "library_title", "value": "  Family\narchive "}, {"key": "library_description", "value": "Shared with   the kids"}])
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'Family.dossiary';" % json.dumps(seeded))
        await page.click("#open-btn")
        await page.wait_for_timeout(400)
        print("A seeded title shows in the header at open (cleaned):", await page.inner_text('#sub-label') == 'Family archive')
        print("...and the seeded description as tooltip:", await page.get_attribute('#sub-label', 'title') == 'Shared with the kids')

        # Switching to a library with no details shows its folder name, no stale title.
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'Plain.dossiary';" % json.dumps(SEED))
        await page.click("#open-btn")
        await page.wait_for_timeout(400)
        print("A library without details shows its folder name:", await page.inner_text('#sub-label') == 'Plain.dossiary')
        print("...with no stale tooltip:", await page.get_attribute('#sub-label', 'title') is None)

        # German UI: the Tools entry and dialog follow the language.
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        print("German Tools entry:", (await page.inner_text('#library-details-btn')).strip() == '🏷 Bibliotheksdetails…')

        print("No page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
