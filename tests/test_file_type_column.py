import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# The built-in File type column (FIELD_DEFS id 'file_type', fileTypeOf()):
# the uppercased extension of the active file's name, hidden by default,
# toggled from the Columns menu (stored in visible_columns, shared with the
# Mac app), sortable, with a dropdown filter of the types present plus
# "— Not set —".
#
# One document per case. Docs 4, 5 and 7 have no file type: no extension, no
# file at all, and a dot only in the folder name. Doc 8 is a dot-file.

def doc(i, title, file_path):
    return {
        "id": i, "title": title, "category": "Misc", "document_type": "Letter",
        "date": f"2026-03-0{i}T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": file_path, "original_file_path": None,
        "created_at": f"2026-03-0{i}T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }

SEED = {
    "documents": [
        doc(1, "Doc 1 pdf", "files/2026/1_a.pdf"),
        doc(2, "Doc 2 rtf", "files/2_b.rtf"),
        doc(3, "Doc 3 JPG", "files/3_SCAN.JPG"),
        doc(4, "Doc 4 no extension", "files/4_noext"),
        doc(5, "Doc 5 no file", None),
        doc(6, "Doc 6 jpeg", "files/6_photo.jpeg"),
        doc(7, "Doc 7 dotted folder", "files/my.folder/7_noext"),
        doc(8, "Doc 8 dot-file", "files/.txt"),
    ],
    "tags": [], "document_tags": [],
    "fields": [],
    "document_field_values": [],
}

FILTER_UNSET = '__unset__'
EXPECTED = {'1': 'PDF', '2': 'RTF', '3': 'JPG', '4': '', '5': '', '6': 'JPEG', '7': '', '8': ''}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    stub_js = open('stub_studio2.js').read()
    await page.add_init_script(stub_js)

async def visible_ids(page):
    return sorted(await page.evaluate(
        "() => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)"
    ), key=int)

async def row_order(page):
    return await page.evaluate(
        "() => Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => tr.dataset.id)"
    )

async def persisted(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Hidden by default, with nothing stored ===
        th_visible = await page.locator('th[data-field="file_type"]').is_visible()
        filter_visible = await page.locator('span[data-field="file_type"]').is_visible()
        print("File type column hidden by default:", not th_visible)
        print("File type filter hidden by default:", not filter_visible)
        print("Category column still visible by default:", await page.locator('th[data-field="category"]').is_visible())

        # === Columns menu: listed with its label, toggling on stores file_type ===
        await page.click('#columns-btn')
        await page.wait_for_timeout(150)
        label = await page.locator('label[for="col-toggle-file_type"]').inner_text()
        print("Columns menu lists File type:", label.strip() == 'File type')
        print("File type checkbox unchecked by default:", not await page.locator('#col-toggle-file_type').is_checked())
        await page.check('#col-toggle-file_type')
        await page.wait_for_timeout(200)
        await page.click('#columns-btn')  # close the menu
        await page.wait_for_timeout(100)
        print("File type column visible after toggle ON:", await page.locator('th[data-field="file_type"]').is_visible())
        print("File type filter visible after toggle ON:", await page.locator('span[data-field="file_type"]').is_visible())
        db = await persisted(page)
        vc = json.loads(next(r for r in db['settings'] if r['key'] == 'visible_columns')['value'])
        print("visible_columns stores 'file_type':", 'file_type' in vc)
        print("visible_columns keeps the default columns:", all(c in vc for c in ['category', 'document_type', 'people', 'date', 'import_date', 'amount', 'tags']))

        # === Values per document ===
        cells = await page.evaluate("""
            () => Object.fromEntries(Array.from(document.querySelectorAll('#doc-tbody tr')).map(tr => {
                const td = tr.querySelector('td[data-field="file_type"]');
                return [tr.dataset.id, td.querySelector('.doc-sub') ? '' : td.textContent.trim()];
            }))
        """)
        for doc_id, want in EXPECTED.items():
            print(f"doc {doc_id} file type is {want or '(empty)'}:", cells.get(doc_id) == want)

        # === Sorting: ascending puts the empty values first (like other text
        # columns), then JPEG < JPG < PDF < RTF; descending reverses ===
        await page.click('th[data-key="file_type"]')
        await page.wait_for_timeout(200)
        order = await row_order(page)
        empties = [i for i in order if EXPECTED[i] == '']
        print("ascending sort: empty file types first:", order[:len(empties)] == empties and len(empties) == 4)
        print("ascending sort: JPEG, JPG, PDF, RTF after them:", order[len(empties):] == ['6', '3', '1', '2'])
        db = await persisted(page)
        sort_key = next(r['value'] for r in db['settings'] if r['key'] == 'sort_key')
        print("sort_key stored as file_type:", sort_key == 'file_type')
        await page.click('th[data-key="file_type"]')
        await page.wait_for_timeout(200)
        order = await row_order(page)
        print("descending sort: RTF, PDF, JPG, JPEG first:", order[:4] == ['2', '1', '3', '6'])
        print("descending sort: empty file types last:", sorted(order[4:]) == sorted(empties))

        # === Filter: options are the distinct types present plus "not set" ===
        options = await page.evaluate("() => Array.from(document.querySelectorAll('#file-type-filter option')).map(o => o.value)")
        print("filter options are All, Not set and the four types:", options == ['', FILTER_UNSET, 'JPEG', 'JPG', 'PDF', 'RTF'])
        first_label = await page.evaluate("() => document.querySelector('#file-type-filter option').textContent")
        print("filter's first option reads 'All file types':", first_label == 'All file types')

        await page.select_option('#file-type-filter', 'JPG')
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        print("filter JPG shows only doc 3 (not the JPEG one):", ids == ['3'])
        await page.select_option('#file-type-filter', 'PDF')
        await page.wait_for_timeout(150)
        print("filter PDF shows only doc 1:", await visible_ids(page) == ['1'])
        await page.select_option('#file-type-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        print("filter 'not set' shows docs 4, 5, 7, 8:", ids == ['4', '5', '7', '8'])
        await page.select_option('#file-type-filter', '')
        await page.wait_for_timeout(150)
        print("clearing the filter shows all 8 documents:", len(await visible_ids(page)) == 8)

        # === Reports breakdown deliberately doesn't offer File type ===
        breakdown = await page.evaluate("() => Array.from(document.querySelectorAll('#report-breakdown-field option')).map(o => o.value)")
        print("Reports breakdown has no file_type option:", 'file_type' not in breakdown)

        # === German label in the table header and Columns menu ===
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        # text_content(), not inner_text(): table headers are upper-cased by CSS (thead th), inner_text() would read DATEITYP.
        print("German header reads 'Dateityp':", ((await page.locator('th[data-field="file_type"]').text_content()) or '').strip() == 'Dateityp')
        await page.click('#columns-btn')
        await page.wait_for_timeout(150)
        print("German Columns menu label reads 'Dateityp':", (await page.locator('label[for="col-toggle-file_type"]').inner_text()).strip() == 'Dateityp')
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(200)

        # === Reopen: the stored choice (as the Mac app would also write it) survives ===
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(400)
        print("File type column still visible after reopen:", await page.locator('th[data-field="file_type"]').is_visible())

        print("no page errors:", not errors, errors)
        await browser.close()

asyncio.run(main())
