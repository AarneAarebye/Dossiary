import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Dragging documents onto a collection in the nav: a row (or grid tile)
# dropped on a manual collection is added to it; a checked row carries the
# whole checked selection; a document already there isn't added twice; a
# smart collection isn't a drop target; nothing is draggable in the Waste
# bin; and the drag never triggers the file-drop overlay or import.
def doc(i, title, deleted=0):
    return {"id": i, "title": title, "category": "Home", "document_type": "Letter", "date": f"2026-03-0{i}",
            "import_date": f"2026-03-0{i}T10:00:00Z", "created_at": f"2026-03-0{i}T10:00:00Z",
            "file_path": f"files/{i}.pdf", "source": "captured", "archived": 0, "needs_review": 0, "deleted": deleted}
SEED = {
    "documents": [doc(1, "Gas bill"), doc(2, "Water bill"), doc(3, "Phone bill"), doc(4, "Old letter", deleted=1)],
    "collections": [
        {"id": 1, "name": "Utilities", "kind": "manual", "criteria": None},
        {"id": 2, "name": "Smart one", "kind": "smart", "criteria": json.dumps({"match": "all", "rules": [{"field": "title", "op": "contains", "value": "bill"}]})},
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
        await page.click('#open-btn')
        await page.wait_for_timeout(500)

        async def members(cid):
            return await page.evaluate(f"""() => {{
                const t = JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes));
                return t.collection_documents.filter(r => r.collection_id === {cid}).map(r => r.document_id).sort();
            }}""")
        row = lambda i: f'#doc-tbody tr[data-id="{i}"]'

        print("Rows are draggable:", await page.get_attribute(row(1), 'draggable') == 'true')
        # Watch for the file-drop overlay during the drags below.
        await page.evaluate("""() => { window.__overlaySeen = false; new MutationObserver(() => {
            if(document.getElementById('drop-overlay').style.display === 'flex') window.__overlaySeen = true;
        }).observe(document.getElementById('drop-overlay'), { attributes: true }); }""")

        # === One unchecked row ===
        await page.drag_and_drop(row(1), '#nav-item-collection-1')
        await page.wait_for_timeout(400)
        print("Dropping a row on a manual collection adds it:", await members(1) == [1])
        print("...and says so:", await page.inner_text('#status') == 'Added 1 document to “Utilities”.')

        # === The checked selection travels together ===
        await page.check(f'{row(2)} .row-select-checkbox')
        await page.check(f'{row(3)} .row-select-checkbox')
        await page.drag_and_drop(row(3), '#nav-item-collection-1')
        await page.wait_for_timeout(400)
        print("Dragging a checked row carries every checked row:", await members(1) == [1, 2, 3]
              and await page.inner_text('#status') == 'Added 2 documents to “Utilities”.')

        # === Already there ===
        await page.drag_and_drop(row(1), '#nav-item-collection-1')
        await page.wait_for_timeout(400)
        m, st = await members(1), await page.inner_text('#status')
        print("A document already in it isn't added twice:", m == [1, 2, 3] and st == 'Already in “Utilities”.')

        # === Smart collection: not a target ===
        await page.drag_and_drop(row(1), '#nav-item-collection-2')
        await page.wait_for_timeout(400)
        print("A smart collection doesn't take drops:", await members(2) == [] and await page.inner_text('#status') == 'Already in “Utilities”.')
        print("No file-drop overlay appeared and nothing was imported:", not await page.evaluate("window.__overlaySeen")
              and await page.locator('#doc-tbody tr').count() == 3 and await page.locator('#nav-count-inbox').inner_text() == '0')
        print("No drop highlight is left behind:", await page.locator('.nav-item.drop-target').count() == 0)

        # === Grid tiles drag too ===
        await page.click('#view-grid-btn')
        await page.wait_for_timeout(300)
        # Empty the collection by hand so the tile drop is observable.
        await page.evaluate("() => { window.__DEBUG_dbRun('DELETE FROM collection_documents WHERE collection_id = ?', [1]); }")
        await page.uncheck(f'#doc-grid .doc-tile[data-id="2"] .row-select-checkbox')
        await page.uncheck(f'#doc-grid .doc-tile[data-id="3"] .row-select-checkbox')
        await page.drag_and_drop('#doc-grid .doc-tile[data-id="2"]', '#nav-item-collection-1')
        await page.wait_for_timeout(400)
        print("A grid tile can be dropped on a collection:", await members(1) == [2])
        await page.click('#view-list-btn')
        await page.wait_for_timeout(300)

        # === Collapsed Collections section opens for the drag ===
        await page.click('#nav-collections-toggle')
        await page.wait_for_timeout(300)
        collapsed = await page.evaluate("() => document.getElementById('nav-collections-section').classList.contains('collapsed')")
        await page.hover(row(3))
        await page.mouse.down()
        await page.hover('#nav-collections-toggle')
        await page.hover('#nav-collections-toggle', position={'x': 5, 'y': 5})
        opened = await page.evaluate("() => !document.getElementById('nav-collections-section').classList.contains('collapsed')")
        await page.hover('#nav-item-collection-1')
        await page.hover('#nav-item-collection-1', position={'x': 6, 'y': 6})
        await page.mouse.up()
        await page.wait_for_timeout(400)
        print("A collapsed Collections section opens while dragging over it:", collapsed and opened and await members(1) == [2, 3])
        print("...and closes again afterwards:", await page.evaluate("() => document.getElementById('nav-collections-section').classList.contains('collapsed')"))
        await page.click('#nav-collections-toggle')
        await page.wait_for_timeout(200)

        # === Waste bin ===
        await page.click('#nav-item-trash')
        await page.wait_for_timeout(300)
        print("Nothing is draggable in the Waste bin:", await page.get_attribute(row(4), 'draggable') == 'false')

        # === German ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(200)
        await page.drag_and_drop(row(1), '#nav-item-collection-1')
        await page.wait_for_timeout(400)
        print("The message follows the language:", await page.inner_text('#status') == '1 Dokument zu „Utilities“ hinzugefügt.')

        print("ERRORS:", errors)
        await browser.close()

asyncio.run(main())
