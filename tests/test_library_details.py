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
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(150)

        # === Scenario 5: Recent libraries shows the title, the description and the folder ===
        # Library A gets details, library B never does. Both handles are kept on
        # window so the test can reach them after switching away.
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__A = window.__makeSeededRoot(%s); window.__A.name = 'Documents.dossiary'; window.__TEST_ROOT = window.__A;" % json.dumps(SEED))
        await page.click("#open-btn")
        await page.wait_for_timeout(400)
        await save('Home papers', 'Bills and the house')
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__B = window.__makeSeededRoot(%s); window.__B.name = 'Other.dossiary'; window.__TEST_ROOT = window.__B;" % json.dumps(SEED))
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        async def switch_away():
            await page.evaluate("window.__TEST_ROOT = null;")
            await page.click("#reload-btn")
            await page.wait_for_timeout(250)

        def row_of(folder):
            return page.locator('#recent-libraries-list .review-queue-row').filter(has_text=folder)

        async def settings_of(var):
            return await page.evaluate("(v) => Object.fromEntries(JSON.parse(new TextDecoder().decode(window[v]._children.get('library.sqlite')._bytes)).settings.map(r => [r.key, r.value]))", var)

        async def entry_of(var):
            return await page.evaluate("""(v) => new Promise(resolve => {
                const req = indexedDB.open('dossiary-app-db', 1);
                req.onsuccess = () => {
                    const r = req.result.transaction('recentLibraries', 'readonly').objectStore('recentLibraries').getAll();
                    r.onsuccess = () => { const e = r.result.find(x => x.handle === window[v]); resolve(e ? { title: e.title, description: e.description, lastOpenedAt: e.lastOpenedAt } : null); };
                };
            })""", var)

        await switch_away()
        a_row, b_row = row_of('Documents.dossiary'), row_of('Other.dossiary')
        print("A's entry shows its title as the name:", await a_row.locator('.doc-title').inner_text() == 'Home papers')
        print("...the description line:", await a_row.locator('.recent-lib-description').inner_text() == 'Bills and the house')
        a_status = await a_row.locator('[id^=recent-lib-status-]').inner_text()
        print("...and the folder name with the last-opened date:", a_status.startswith('Documents.dossiary · Last opened ') and len(a_status) > len('Documents.dossiary · Last opened '))
        print("B's entry shows its folder name:", await b_row.locator('.doc-title').inner_text() == 'Other.dossiary')
        print("...with no description line:", await b_row.locator('.recent-lib-description').count() == 0)
        print("...and the plain last-opened text:", (await b_row.locator('[id^=recent-lib-status-]').inner_text()).startswith('Last opened '))
        print("A library with seeded details shows them in the list too:", await row_of('Family archive').locator('.recent-lib-description').inner_text() == 'Shared with the kids')
        print("Every entry has a pencil:", await page.locator('#recent-libraries-list .recent-details-btn').count() == await page.locator('#recent-libraries-list .review-queue-row').count())
        print("The pencil sits before the trash button:",
              await a_row.evaluate("r => { const p = r.querySelector('.recent-details-btn'), t = r.querySelector('.recent-delete-btn'); return !!p && p.nextElementSibling === t; }"))
        print("The pencil's label names the title:", await a_row.locator('.recent-details-btn').get_attribute('aria-label') == 'Edit title and description of Home papers')

        # === Scenario 6/7: the pencil opens the library once, then the dialog ===
        await page.evaluate("""() => {
            window.__A_OPENS = 0;
            const orig = window.__A.getFileHandle.bind(window.__A);
            window.__A.getFileHandle = (name, opts) => { if(name === 'library.sqlite' && !(opts && opts.create)) window.__A_OPENS++; return orig(name, opts); };
        }""")
        await a_row.locator('.recent-details-btn').click()
        await page.wait_for_timeout(500)
        print("The pencil opened the library:", not await page.locator('#empty-state').is_visible())
        print("...once (no second open through the row):", await page.evaluate("window.__A_OPENS") == 1)
        print("...and shows the dialog with A's title:", await page.locator('#library-details-title').count() == 1 and await page.input_value('#library-details-title') == 'Home papers')
        print("...as the only modal:", await page.locator('.modal').count() == 1)
        print("The header shows A's title:", await page.inner_text('#sub-label') == 'Home papers')
        await page.click('#library-details-cancel-btn')
        await page.wait_for_timeout(100)

        # A failed save changes nothing: header, dialog values, list entry.
        await page.evaluate("(async () => { (await window.__A.getFileHandle('library.sqlite')).readOnly = true; })()")
        await open_dialog()
        await page.fill('#library-details-title', 'Broken title')
        await page.fill('#library-details-description', 'Broken note')
        await page.click('#library-details-save-btn')
        await page.wait_for_timeout(300)
        print("A failed save keeps the dialog open:", await page.locator('#library-details-title').count() == 1)
        print("...with Save enabled again:", await page.is_enabled('#library-details-save-btn'))
        print("...says so in the status line:", 'Save failed' in await page.inner_text('#status'))
        print("...leaves the header alone:", await page.inner_text('#sub-label') == 'Home papers' and await page.get_attribute('#sub-label', 'title') == 'Bills and the house')
        print("...writes nothing to disk:", (await settings_of('__A')).get('library_title') == 'Home papers')
        print("...and leaves the list entry alone:", (await entry_of('__A'))['title'] == 'Home papers')
        await page.click('#library-details-cancel-btn')
        await page.wait_for_timeout(100)
        await open_dialog()
        print("...so reopening still shows the saved values:",
              await page.input_value('#library-details-title') == 'Home papers' and await page.input_value('#library-details-description') == 'Bills and the house')
        await page.click('#library-details-cancel-btn')
        await page.evaluate("(async () => { (await window.__A.getFileHandle('library.sqlite')).readOnly = false; })()")

        opened_at = (await entry_of('__A'))['lastOpenedAt']
        await save('House papers', 'Bills and the house')
        print("Saving updates the library:", (await settings_of('__A')).get('library_title') == 'House papers')
        entry = await entry_of('__A')
        print("...and the Recent libraries entry at once:", entry['title'] == 'House papers' and entry['description'] == 'Bills and the house')
        print("...without changing its last-opened date:", entry['lastOpenedAt'] == opened_at)
        await switch_away()
        print("The list shows the new title:", await row_of('Documents.dossiary').locator('.doc-title').inner_text() == 'House papers')

        # === Scenario 6b: a denied reconnect opens no dialog and writes nothing ===
        before = await page.evaluate("Array.from(window.__A._children.get('library.sqlite')._bytes).join(',')")
        await page.evaluate("window.__A._forceDenied = true;")
        # Found by its title: the denial replaces the status line holding the folder name.
        await row_of('House papers').locator('.recent-details-btn').click()
        await page.wait_for_timeout(300)
        print("A denied pencil shows the denial message:",
              await row_of('House papers').locator('[id^=recent-lib-status-]').inner_text() == "Couldn't reopen — access was denied.")
        print("...opens no dialog:", await page.locator('#library-details-title').count() == 0)
        print("...stays on the start screen:", await page.locator('#empty-state').is_visible())
        print("...and leaves library.sqlite unchanged:",
              await page.evaluate("Array.from(window.__A._children.get('library.sqlite')._bytes).join(',')") == before)
        await page.evaluate("window.__A._forceDenied = false;")

        # A library that fails to open (no library.sqlite) gets no dialog either.
        await page.evaluate("window.__B._children.delete('library.sqlite');")
        await row_of('Other.dossiary').locator('.recent-details-btn').click()
        await page.wait_for_timeout(400)
        print("A folder that is not a library gets no dialog:", await page.locator('#library-details-title').count() == 0)

        print("No page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
