import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Keyboard shortcuts for working through the review queue: J/K or arrows to
# move, E to edit, D for Done-and-next, Enter/O to open the file, ? for the
# list, and Ctrl/Cmd(+Shift)+Enter to save (and finish) from the Edit form.
# Table keys must never fire while typing in a field or with a dialog open.
def doc(i, title, needs_review=1, date="2026-03-01T00:00:00+00:00"):
    return {
        "id": i, "title": title, "category": None, "document_type": None,
        "date": date, "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "scan-inbox", "source_legacy_id": None,
        "archived": 0, "needs_review": needs_review, "deleted": 0,
    }

# import_date descending is the default sort; give each a distinct one so the
# Inbox order is predictable: 1, 2, 3, 4.
SEED = {
    "documents": [dict(doc(i, f"Scan {i}"), import_date=f"2026-03-{10 - i:02d}T00:00:00+00:00") for i in range(1, 5)]
                 + [dict(doc(5, "Reviewed", needs_review=0), import_date="2026-03-01T00:00:00+00:00")],
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
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.evaluate("""
            async () => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                for(const i of [1, 2, 3, 4, 5]){
                    const h = await dir.getFileHandle(`${i}_a.pdf`, { create: true });
                    const w = await h.createWritable(); await w.write(new TextEncoder().encode('%PDF-1.4')); await w.close();
                }
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(500)
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(200)
        await page.evaluate("document.activeElement && document.activeElement.blur()")

        async def selected():
            return await page.evaluate("() => { const r = document.querySelector('#doc-tbody tr.row-selected'); return r ? +r.dataset.id : null; }")
        async def panel_title():
            return await page.inner_text('#detail-panel-body h2') if await page.locator('#detail-panel-body h2').count() else ''

        # === Scenario 1: moving through the list ===
        await page.keyboard.press('j')
        await page.wait_for_timeout(150)
        print("J with nothing selected selects the first row:", await selected() == 1)
        await page.keyboard.press('ArrowDown')
        await page.wait_for_timeout(150)
        print("Arrow down moves to the next row and shows it in the panel:", await selected() == 2 and 'Scan 2' in await panel_title())
        await page.keyboard.press('k')
        await page.wait_for_timeout(150)
        print("K moves back:", await selected() == 1)
        await page.keyboard.press('ArrowUp')
        await page.wait_for_timeout(150)
        print("Up at the top stays on the first row:", await selected() == 1)

        # === Scenario 2: D marks Done and moves on ===
        await page.keyboard.press('d')
        await page.wait_for_timeout(400)
        ids = await page.locator('#doc-tbody tr').evaluate_all("rs => rs.map(r => +r.dataset.id)")
        print("D clears the review flag, so the document leaves the Inbox:", 1 not in ids, ids)
        print("...and the next one is selected, ready to review:", await selected() == 2 and 'Scan 2' in await panel_title())

        # === Scenario 3: E opens Edit; Ctrl+Shift+Enter is Save & Done ===
        await page.keyboard.press('e')
        await page.wait_for_timeout(300)
        print("E opens the Edit form:", await page.locator('#save-edit-btn').count() == 1)
        await page.fill('#e-title', 'Scan 2 reviewed')
        await page.keyboard.press('Control+Shift+Enter')
        await page.wait_for_timeout(500)
        state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        d2 = next(d for d in state['documents'] if d['id'] == 2)
        print("Ctrl+Shift+Enter saves and marks Done from inside a field:", d2['title'] == 'Scan 2 reviewed' and not d2['needs_review'] and await page.locator('#save-edit-btn').count() == 0)

        # === Scenario 4: Ctrl+Enter is plain Save ===
        await page.keyboard.press('j')
        await page.wait_for_timeout(150)
        sel = await selected()
        await page.keyboard.press('e')
        await page.wait_for_timeout(300)
        await page.fill('#e-title', 'Saved only')
        await page.keyboard.press('Control+Enter')
        await page.wait_for_timeout(500)
        state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        dn = next(d for d in state['documents'] if d['id'] == sel)
        print("Ctrl+Enter saves without clearing the review flag:", dn['title'] == 'Saved only' and bool(dn['needs_review']))

        # === Scenario 5: keys don't fire while typing or with a dialog open ===
        before = await selected()
        await page.click('#search')
        await page.keyboard.type('jkd')
        await page.wait_for_timeout(200)
        print("Typing j/k/d into the search box doesn't move or mark anything:", await selected() in (before, None) and await page.input_value('#search') == 'jkd')
        await page.fill('#search', '')
        await page.evaluate("document.activeElement.blur()")
        await page.wait_for_timeout(150)
        await page.keyboard.press('?')
        await page.wait_for_timeout(200)
        print("? opens the shortcuts list:", await page.locator('#shortcuts-list').count() == 1)
        rows_before = await page.locator('#doc-tbody tr').count()
        await page.keyboard.press('d')
        await page.wait_for_timeout(200)
        print("...and table keys do nothing while it's open:", await page.locator('#doc-tbody tr').count() == rows_before)
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(150)
        print("Escape closes it:", await page.locator('#shortcuts-list').count() == 0)

        # === Scenario 6: D does nothing on a document that isn't in review ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)
        await page.click('#doc-tbody tr[data-id="5"] td:nth-child(3)')
        await page.wait_for_timeout(200)
        await page.evaluate("document.activeElement && document.activeElement.blur()")
        await page.keyboard.press('d')
        await page.wait_for_timeout(300)
        state = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        d5 = next(d for d in state['documents'] if d['id'] == 5)
        print("D leaves a reviewed document alone (it doesn't flag it):", not d5['needs_review'])

        # === Scenario 7: Enter opens the selected document's file ===
        # Wrapped in a function: a bare "... window.open = (url) => ..." string is
        # itself taken for an arrow function by Playwright and gets called.
        await page.evaluate("() => { window.__opened = []; window.open = (url) => { window.__opened.push(url); return null; }; }")
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(300)
        print("Enter opens the selected document's file:", await page.evaluate("window.__opened.length === 1 && window.__opened[0].startsWith('blob:')"))

        # === Scenario 8: labels translate ===
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        await page.evaluate("document.activeElement && document.activeElement.blur()")
        await page.keyboard.press('?')
        await page.wait_for_timeout(200)
        print("Shortcuts list translates:", 'Tastenkürzel' in await page.inner_text('.modal'))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
