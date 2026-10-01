import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Folders grouping collections: created, renamed and deleted in Manage
# collections, where each collection gets a folder picker; the nav shows
# each folder as a foldable sub-header (folding remembered per library) with
# its collections under it, then unfiled ones; deleting a folder keeps its
# collections; a folded folder opens while documents are dragged over it;
# and a library copying another's setup gets its folders.
def doc(i, title):
    return {"id": i, "title": title, "category": "Home", "document_type": "Letter", "date": f"2026-03-0{i}",
            "import_date": f"2026-03-0{i}T10:00:00Z", "created_at": f"2026-03-0{i}T10:00:00Z",
            "file_path": f"files/{i}.pdf", "source": "captured", "archived": 0, "needs_review": 0, "deleted": 0}
SEED = {
    "documents": [doc(1, "Gas bill"), doc(2, "Tax letter")],
    "collections": [
        {"id": 1, "name": "Utilities", "kind": "manual", "criteria": None},
        {"id": 2, "name": "Tax 2025", "kind": "manual", "criteria": None},
        {"id": 3, "name": "Bills", "kind": "smart", "criteria": json.dumps({"match": "all", "rules": [{"field": "title", "op": "contains", "value": "bill"}]})},
    ],
    "collection_documents": [],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'Home.dossiary';")
        await page.click('#open-btn')
        await page.wait_for_timeout(500)

        async def saved():
            return await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")
        async def nav_order():
            return await page.evaluate("""() => [...document.querySelectorAll('#nav-collections-list .nav-folder-header, #nav-collections-list .nav-item')]
                .map(n => (n.classList.contains('nav-folder-header') ? 'F:' : (n.classList.contains('nav-item-in-folder') ? '  ' : '')) + n.querySelector('.nav-item-label').textContent)""")
        async def open_manage():
            await page.click('#tools-btn')
            await page.click('#manage-collections-btn')
            await page.wait_for_timeout(300)
        def row(name):
            return page.locator('#manage-collections-list .manage-collection-row', has=page.locator(f'input[value="{name}"]'))

        print("Without folders, the nav lists collections as before:", await nav_order() == ['Bills', 'Tax 2025', 'Utilities'])
        await open_manage()
        print("No folder picker while there are no folders:", await page.locator('.manage-collection-folder-select').count() == 0)

        # === Create folders, file collections ===
        await page.fill('#manage-new-folder-input', 'Taxes')
        await page.click('#manage-new-folder-btn')
        await page.fill('#manage-new-folder-input', 'Household')
        await page.press('#manage-new-folder-input', 'Enter')
        await page.wait_for_timeout(300)
        print("New folders are listed:", await page.locator('#manage-folders-list .manage-folder-rename-input').evaluate_all("ns => ns.map(n => n.value)") == ['Household', 'Taxes'])
        print("Each collection gets a folder picker:", await page.locator('.manage-collection-folder-select').count() == 3
              and await row('Utilities').locator('select option').all_inner_texts() == ['No folder', 'Household', 'Taxes'])
        await row('Utilities').locator('select').select_option(label='Household')
        await page.wait_for_timeout(200)
        await row('Bills').locator('select').select_option(label='Household')
        await page.wait_for_timeout(200)
        await row('Tax 2025').locator('select').select_option(label='Taxes')
        await page.wait_for_timeout(300)
        db = await saved()
        folders = {f['name']: f['id'] for f in db['collection_folders']}
        print("Folders and assignments are saved:", {c['name']: c.get('folder_id') for c in db['collections']}
              == {'Utilities': folders['Household'], 'Tax 2025': folders['Taxes'], 'Bills': folders['Household']})
        print("Folder rows count their collections:", await page.locator('.manage-folder-row .manage-collection-count').all_inner_texts() == ['2', '1'])
        await page.click('#mc-done-btn')
        await page.wait_for_timeout(200)
        print("The nav groups collections under their folders:", await nav_order() == ['F:Household', '  Bills', '  Utilities', 'F:Taxes', '  Tax 2025'])

        # === An unfiled collection comes after the folders ===
        await open_manage()
        await page.fill('#manage-new-collection-input', 'Misc')
        await page.click('#manage-new-collection-btn')
        await page.wait_for_timeout(300)
        await page.click('#mc-done-btn')
        print("An unfiled collection follows the folders:", (await nav_order())[-1] == 'Misc')

        # === Folding is remembered ===
        await page.click('#nav-folder-' + str(folders['Household']))
        await page.wait_for_timeout(300)
        print("Clicking a folder folds it:", not await page.locator('#nav-item-collection-1').is_visible()
              and await page.get_attribute('#nav-folder-' + str(folders['Household']), 'aria-expanded') == 'false')
        await page.click('#reload-btn')
        await page.wait_for_timeout(200)
        await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("...and stays folded after reopening:", not await page.locator('#nav-item-collection-1').is_visible()
              and await page.locator('#nav-item-collection-2').is_visible())

        # === Dragging over a folded folder opens it, then it folds again ===
        await page.hover('#doc-tbody tr[data-id="1"]')
        await page.mouse.down()
        await page.hover('#nav-folder-' + str(folders['Household']))
        await page.hover('#nav-folder-' + str(folders['Household']), position={'x': 5, 'y': 5})
        opened = await page.locator('#nav-item-collection-1').is_visible()
        await page.hover('#nav-item-collection-1')
        await page.hover('#nav-item-collection-1', position={'x': 6, 'y': 6})
        await page.mouse.up()
        await page.wait_for_timeout(400)
        db = await saved()
        print("A folded folder opens while dragging over it, and takes the drop:", opened
              and [r['document_id'] for r in db['collection_documents'] if r['collection_id'] == 1] == [1])
        print("...then folds again:", not await page.locator('#nav-item-collection-1').is_visible())
        await page.click('#nav-folder-' + str(folders['Household']))
        await page.wait_for_timeout(200)

        # === Rename and delete ===
        await open_manage()
        rename = page.locator('#manage-folders-list .manage-folder-row', has=page.locator('input[value="Taxes"]')).locator('input')
        await rename.fill('Tax papers')
        await rename.press('Enter')
        await page.wait_for_timeout(300)
        print("A folder can be renamed:", 'F:Tax papers' in await nav_order())
        await page.locator('#manage-folders-list .manage-folder-row', has=page.locator('input[value="Household"]')).locator('.manage-folder-delete-btn').click()
        await page.wait_for_timeout(400)
        db = await saved()
        print("Deleting a folder keeps its collections, unfiled:", [f['name'] for f in db['collection_folders']] == ['Tax papers']
              and {c['name'] for c in db['collections'] if c.get('folder_id') is None} == {'Utilities', 'Bills', 'Misc'}
              and len(db['collections']) == 4)
        await page.click('#mc-done-btn')
        print("The nav shows the remaining folder, then the unfiled collections:", await nav_order() == ['F:Tax papers', '  Tax 2025', 'Bills', 'Misc', 'Utilities'])

        # === Copying the setup brings the folders along ===
        await page.evaluate("() => { const r = window.__makeEmptyRoot(); r.name = 'Documents'; window.__TEST_ROOT_NEW = r; }")
        await page.click('#reload-btn')
        await page.wait_for_timeout(200)
        await page.evaluate("() => { window.__TEST_ROOT_OLD = window.__TEST_ROOT; window.__TEST_ROOT = window.__TEST_ROOT_NEW; }")
        await page.click('#open-btn')
        await page.wait_for_timeout(400)
        value = await page.evaluate("() => [...document.querySelectorAll('#copy-setup-select option')].find(o => o.textContent === 'Home.dossiary').value")
        await page.select_option('#copy-setup-select', value)
        await page.fill('#new-library-name', 'Next year')
        await page.click('#create-library-btn')
        await page.wait_for_timeout(500)
        print("A library copying this setup gets the folders and its smart collection:",
              await nav_order() == ['F:Tax papers', 'Bills'])

        # === German ===
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(200)
        await open_manage()
        print("Labels follow the language:", await page.inner_text('.manage-section-heading') == 'ORDNER'
              and await page.inner_text('#manage-new-folder-btn') == '+ Neuer Ordner')

        print("ERRORS:", errors)
        await browser.close()

asyncio.run(main())
