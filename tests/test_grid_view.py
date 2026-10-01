import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2, sys
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, base64
from playwright.async_api import async_playwright

# The grid view: a per-library List/Grid switch on the count line, preview
# tiles sharing the table's selection, panel, context menu, bulk selection and
# keyboard shortcuts, a remembered tile size, lazily loaded previews, and an
# explicit "Create missing previews" run. Pass a path as the first argument to
# also save a screenshot of the grid there.
SHOT = sys.argv[1] if len(sys.argv) > 1 else None
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")

def doc(i, title, **extra):
    d = {
        "id": i, "title": title, "category": "Bills", "subcategory": None, "document_type": None,
        "date": f"2026-03-{i:02d}T00:00:00+00:00", "import_date": f"2026-03-{i:02d}T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_doc.pdf", "original_file_path": None, "thumbnail_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }
    d.update(extra)
    return d

SEED = {
    "documents": [
        doc(1, "Electricity bill", thumbnail_path="thumbnails/1.png"),
        doc(2, "Water bill", thumbnail_path="thumbnails/2.png"),
        doc(3, "Insurance letter"),                    # no preview yet
        doc(4, "Tax notice"),                          # no preview yet
        doc(5, "Gone preview", thumbnail_path="thumbnails/5.png"),  # preview file missing
        doc(6, "In the bin", deleted=1),
    ],
    "tags": [], "document_tags": [],
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
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url or 'pdf-lib' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.evaluate("""async (png) => {
            const bytes = Uint8Array.from(atob(png), c => c.charCodeAt(0));
            const put = async (path, data) => {
                const parts = path.split('/'); let dir = window.__TEST_ROOT;
                for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
                await w.write(data); await w.close();
            };
            for(const i of [1, 2, 3, 4, 5, 6]) await put(`files/${i}_doc.pdf`, new TextEncoder().encode('%PDF-1.4 doc ' + i));
            await put('thumbnails/1.png', bytes);
            await put('thumbnails/2.png', bytes);
        }""", base64.b64encode(PNG).decode())
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        async def state():
            return await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        settings = lambda st: {s['key']: s['value'] for s in st['settings']}
        tiles = lambda: page.locator('#doc-grid .doc-tile').evaluate_all("ts => ts.map(t => Number(t.dataset.id))")
        count_row = page.locator('.count-row')
        h_list = (await count_row.bounding_box())['height']

        # === Scenario 1: List is the default; the switch sits on the count line ===
        print("List view by default, no tiles:", await page.locator('#doc-table').is_visible() and await tiles() == [])
        print("Switch shown with List pressed, size slider hidden:",
              await page.get_attribute('#view-list-btn', 'aria-pressed') == 'true' and not await page.locator('#grid-size-range').is_visible())
        print("Count line text unchanged:", await page.inner_text('#count-line') == 'Showing 5 of 5 documents')

        # === Scenario 2: switching to Grid ===
        await page.click('#view-grid-btn')
        await page.wait_for_timeout(400)
        print("Grid shows one tile per listed document, in the table's order, Waste bin excluded:", await tiles() == [5, 4, 3, 2, 1], await tiles())
        print("The table is hidden:", not await page.locator('#doc-table').is_visible())
        print("Choice saved in the library:", settings(await state()).get('view_mode') == 'grid')
        line_h = (await page.locator('#count-line').bounding_box())['height']
        print("The count row stays as tall as the count line alone (part of the table's height budget):",
              (await count_row.bounding_box())['height'] == h_list == line_h, h_list, line_h)
        imgs = await page.locator('#doc-grid .doc-tile[data-id="1"] .tile-thumb img').count()
        print("A tile with a preview shows the image:", imgs == 1)
        print("A tile without one shows a placeholder with the file kind:",
              'PDF' in await page.inner_text('#doc-grid .doc-tile[data-id="3"] .tile-thumb') and 'No preview' in await page.inner_text('#doc-grid .doc-tile[data-id="3"] .tile-thumb'))
        print("A missing preview file is said so:", 'Preview missing' in await page.inner_text('#doc-grid .doc-tile[data-id="5"] .tile-thumb'))
        print("Tiles are larger than the old 110x140 panel preview:", (await page.locator('#doc-grid .doc-tile[data-id="1"] .tile-thumb').bounding_box())['height'] > 140)

        # === Scenario 3: tiles behave like rows ===
        await page.click('#doc-grid .doc-tile[data-id="2"]')
        await page.wait_for_timeout(250)
        print("Click selects and shows details:", 'row-selected' in await page.get_attribute('#doc-grid .doc-tile[data-id="2"]', 'class')
              and 'Water bill' in await page.inner_text('#detail-panel-body'))
        await page.keyboard.press('j')
        await page.wait_for_timeout(250)
        print("J moves to the next tile:", 'row-selected' in await page.get_attribute('#doc-grid .doc-tile[data-id="1"]', 'class')
              and 'Electricity bill' in await page.inner_text('#detail-panel-body'))
        await page.click('#doc-grid .doc-tile[data-id="4"]', button='right')
        await page.wait_for_timeout(200)
        print("Right-click opens the document menu:", await page.locator('.row-context-menu').count() == 1)
        await page.keyboard.press('Escape'); await page.mouse.click(5, 895)
        await page.check('#doc-grid .doc-tile[data-id="3"] .row-select-checkbox')
        await page.check('#doc-grid .doc-tile[data-id="4"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        print("Tile checkboxes drive the bulk-action bar:", await page.inner_text('#bulk-action-count') == '2 selected', await page.inner_text('#bulk-action-count'))
        await page.click('#bulk-clear-selection-btn')

        # === Scenario 4: tile size ===
        print("Slider shown in grid view:", await page.locator('#grid-size-range').is_visible())
        before = (await page.locator('#doc-grid .doc-tile[data-id="1"]').bounding_box())['width']
        await page.evaluate("() => { const r = document.getElementById('grid-size-range'); r.value = 340; r.dispatchEvent(new Event('input')); r.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(300)
        after = (await page.locator('#doc-grid .doc-tile[data-id="1"]').bounding_box())['width']
        print("Larger size makes tiles wider:", after > before, before, after)
        print("Size saved:", settings(await state()).get('grid_tile_size') == '340')

        # === Scenario 5: creating missing previews ===
        btn = page.locator('#create-previews-btn')
        print("Button offers the two documents without a preview:", await btn.is_visible() and '(2)' in await btn.inner_text(), await btn.inner_text())
        await btn.click()
        await page.wait_for_timeout(800)
        st = await state()
        paths = {d['id']: d['thumbnail_path'] for d in st['documents']}
        print("Previews created and saved:", paths[3] == 'thumbnails/3.png' and paths[4] == 'thumbnails/4.png', paths)
        print("...shown in their tiles:", await page.locator('#doc-grid .doc-tile[data-id="3"] .tile-thumb img').count() == 1)
        print("...and the button goes away:", not await btn.is_visible())
        print("The deleted document got none:", paths[6] is None)

        # === Scenario 6: persistence, back to List, German ===
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("Reopening keeps the grid and size:", await tiles() == [5, 4, 3, 2, 1]
              and await page.input_value('#grid-size-range') == '340')
        if SHOT:
            await page.evaluate("() => { const r = document.getElementById('grid-size-range'); r.value = 200; r.dispatchEvent(new Event('input')); }")
            await page.click('#doc-grid .doc-tile[data-id="2"]')
            await page.wait_for_timeout(300)
            await page.screenshot(path=SHOT)
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        print("German labels:", await page.inner_text('#view-grid-btn') == '▦ Raster' and await page.inner_text('#view-list-btn') == '☰ Liste')
        await page.click('#view-list-btn')
        await page.wait_for_timeout(300)
        print("Back to the list:", await page.locator('#doc-table').is_visible() and await tiles() == [] and settings(await state()).get('view_mode') == 'list')
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(200)
        print("No view switch in Reports:", not await page.locator('#view-controls').is_visible())

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
