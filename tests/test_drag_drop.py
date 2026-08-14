import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

async def dispatch_drag(page, event_type, filenames=None):
    files_js = ""
    if filenames is not None:
        parts = ",".join(f"new File([new Uint8Array([1,2,3,4])], {name!r}, {{type: 'application/pdf'}})" for name in filenames)
        files_js = f"[{parts}].forEach(f => dt.items.add(f));"
    await page.evaluate(f"""
        () => {{
            const dt = new DataTransfer();
            {files_js}
            const ev = new DragEvent({event_type!r}, {{ bubbles: true, cancelable: true, dataTransfer: dt }});
            document.dispatchEvent(ev);
        }}
    """)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
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
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        # === Scenario 1: dragging over the page with no library open is a no-op --
        # no overlay, and a drop shouldn't crash or add anything ===
        await dispatch_drag(page, 'dragenter')
        await page.wait_for_timeout(100)
        overlay_visible_no_library = await page.locator('#drop-overlay').is_visible()
        print("overlay stays hidden with no library open:", not overlay_visible_no_library)
        await dispatch_drag(page, 'drop', ['ignored.pdf'])
        await page.wait_for_timeout(150)
        print("no JS error from a drop with no library open:", len(errors) == 0)

        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(300)

        # === Scenario 2: overlay shows on dragenter, hides after a drop ===
        await dispatch_drag(page, 'dragenter')
        await page.wait_for_timeout(100)
        overlay_visible_during_drag = await page.locator('#drop-overlay').is_visible()
        print("overlay visible during drag:", overlay_visible_during_drag)

        await dispatch_drag(page, 'drop', ['receipt.pdf'])
        await page.wait_for_timeout(300)
        overlay_visible_after_drop = await page.locator('#drop-overlay').is_visible()
        print("overlay hidden after drop:", not overlay_visible_after_drop)

        # === Scenario 3: the dropped file is added as a needs-review document with
        # source='dropped', lands on the Inbox nav view, and the status line names it ===
        status_text = await page.locator('#status').inner_text()
        print("status line after single-file drop:", status_text)
        current_view_is_inbox = await page.locator('#nav-item-inbox.active').count()
        print("landed on the Inbox nav view:", current_view_is_inbox == 1)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).documents;
            })()
        """)
        print("total documents after single-file drop:", len(persisted))
        doc1 = persisted[0]
        print("doc1:", {k: doc1[k] for k in ['id', 'title', 'source', 'needs_review', 'file_path']})

        # === Scenario 4: dropping multiple files at once adds one document per file ===
        await dispatch_drag(page, 'dragenter')
        await page.wait_for_timeout(100)
        await dispatch_drag(page, 'drop', ['invoice_a.pdf', 'invoice_b.pdf'])
        await page.wait_for_timeout(300)

        status_after_multi = await page.locator('#status').inner_text()
        print("status line after multi-file drop:", status_after_multi)

        persisted_after_multi = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).documents;
            })()
        """)
        print("total documents after multi-file drop:", len(persisted_after_multi))
        print("sources are all 'dropped':", sorted(d['source'] for d in persisted_after_multi))

        inbox_row_count = await page.locator('#doc-tbody tr').count()
        print("Inbox view shows all 3 dropped docs:", inbox_row_count)

        # === Scenario 5: a drop with no files (e.g. dragging non-file content) is a
        # no-op -- no navigation, no crash, no new document ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await dispatch_drag(page, 'dragenter')
        await page.wait_for_timeout(100)
        await dispatch_drag(page, 'drop')  # no filenames -- empty DataTransfer
        await page.wait_for_timeout(200)
        stayed_on_all = await page.locator('#nav-item-all.active').count()
        print("empty drop stays on current view:", stayed_on_all == 1)
        persisted_after_empty_drop = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).documents;
            })()
        """)
        print("no new document from an empty drop:", len(persisted_after_empty_drop) == 3)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
