import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Regressions found while recapturing the User Guide screenshots in all six
# languages: composite status messages not retranslating, a stale detail panel
# after a slow async render, hidden-column filters reappearing on the Reports
# view, sidebar/panel overflow with longer translations, and Chrome's own page
# translator not being told to stay out.
def doc(i, title, needs_review=0, file_path=None):
    return {
        "id": i, "title": title, "category": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": file_path or f"files/{i}_doc.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": needs_review, "deleted": 0,
    }

SEED = {
    "documents": [
        doc(1, "Normal Doc"),
        doc(2, "Inbox Doc", needs_review=1,
            file_path="files/2_a_really_long_scanned_document_filename_that_has_no_spaces_at_all_20260321_0001.pdf"),
    ],
    "tags": [], "document_tags": [],
    "fields": [{"id": 1, "name": "Organization", "type": "text", "show_as_column": 1, "autocomplete": 1}],
}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    await page.add_init_script(open('stub_studio2.js').read())

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.evaluate("""
            async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                const inboxDir = await window.__TEST_ROOT.getDirectoryHandle('inbox', { create: true });
                const h = await inboxDir.getFileHandle('staged_scan.pdf', { create: true });
                const w = await h.createWritable(); await w.write(new TextEncoder().encode('%PDF-1.4 staged')); await w.close();
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        # === Scenario 1: the page tells browser translators to stay out ===
        attrs = await page.evaluate("({translate: document.documentElement.getAttribute('translate'), meta: document.querySelector('meta[name=google]')?.content})")
        print("<html translate=\"no\"> and the notranslate meta are present:", attrs == {'translate': 'no', 'meta': 'notranslate'}, attrs)

        # === Scenario 2: a composite status message (Inbox add) retranslates on a language switch ===
        # checkInbox() ran once at open; "Check inbox" adds the staged file and reports it.
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(500)
        status_en = await page.inner_text('#status')
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        status_de = await page.inner_text('#status')
        print("Inbox-add status is shown in English first:", 'review queue' in status_en, repr(status_en))
        print("...and retranslates to German on a language switch:", status_de != status_en and 'review queue' not in status_de, repr(status_de))
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(200)

        # === Scenario 3: a slow, superseded openDetail() doesn't overwrite a newer, empty panel ===
        # Make reading the Inbox document's file slow (like a library in iCloud Drive),
        # then switch language on Reports (which re-renders the panel for the
        # still-selected document) and immediately switch to All Documents, where that
        # document isn't shown -- the panel must end up empty, not stale.
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(200)
        await page.click('#doc-tbody tr[data-id="2"]')
        await page.wait_for_timeout(300)
        print("Inbox document selected into the panel:", 'Inbox Doc' in await page.inner_text('#detail-panel-body'))
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(200)
        await page.evaluate("""
            async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const h = await filesDir.getFileHandle('2_a_really_long_scanned_document_filename_that_has_no_spaces_at_all_20260321_0001.pdf', { create: true });
                const orig = h.getFile.bind(h);
                h.getFile = async () => { await new Promise(r => setTimeout(r, 800)); return orig(); };
            }
        """)
        await page.select_option('#lang-select', 'fr')
        await page.click('#nav-item-all')
        await page.wait_for_timeout(1500)
        panel = await page.inner_text('#detail-panel-body')
        print("Panel stays empty after the slow, superseded render finishes:", 'Inbox Doc' not in panel, repr(panel[:60]))
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(200)

        # === Scenario 4: hidden-column filters stay hidden when filters are rebuilt on Reports ===
        # "Organization" is show_as_column but its column is hidden by default, so its
        # filter must stay hidden -- even after a language switch while on Reports,
        # where render() returns before applying column visibility.
        org_filter = page.locator('#dynamic-filters .filter-wrap').first
        print("Hidden-column filter is hidden on All Documents:", not await org_filter.is_visible())
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(200)
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        print("...and still hidden after a language switch on Reports:", not await page.locator('#dynamic-filters .filter-wrap').first.is_visible())
        await page.click('#nav-item-all')
        await page.wait_for_timeout(200)

        # === Scenario 5: sidebar layout holds up with longer translations ===
        await page.select_option('#lang-select', 'es')
        await page.wait_for_timeout(300)
        layout = await page.evaluate("""
            () => {
                const nav = document.getElementById('app-nav').getBoundingClientRect();
                const counts = [...document.querySelectorAll('#app-nav .nav-item-count')].filter(e => e.offsetParent).map(e => e.getBoundingClientRect());
                const smart = document.getElementById('save-smart-collection-btn');
                const sr = smart && smart.offsetParent ? smart.getBoundingClientRect() : null;
                return {
                    navRight: nav.right,
                    countsInside: counts.every(r => r.right <= nav.right + 0.5),
                    countCount: counts.length,
                    smartInside: sr ? sr.right <= nav.right + 0.5 : null,
                    sidebar: document.getElementById('main-layout').classList.contains('nav-style-sidebar'),
                };
            }
        """)
        print("Sidebar nav is active for this check:", layout['sidebar'])
        print("Every nav count badge stays inside the sidebar in Spanish:", layout['countsInside'] and layout['countCount'] >= 3, layout)
        print("'Save as Smart Collection' stays inside the sidebar in Spanish:", layout['smartInside'] is not False, layout['smartInside'])

        # === Scenario 6: long file paths wrap inside the detail panel ===
        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(200)
        await page.click('#doc-tbody tr[data-id="2"]')
        await page.wait_for_timeout(1200)
        overflow = await page.evaluate("""
            () => {
                const panel = document.getElementById('detail-panel');
                const pr = panel.getBoundingClientRect();
                const codes = [...panel.querySelectorAll('.modal-meta code')];
                return {codes: codes.length, inside: codes.every(c => c.getBoundingClientRect().right <= pr.right + 0.5), noHScroll: panel.scrollWidth <= panel.clientWidth + 1};
            }
        """)
        print("Long file paths wrap inside the detail panel (no overflow):", overflow['codes'] >= 1 and overflow['inside'] and overflow['noHScroll'], overflow)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
