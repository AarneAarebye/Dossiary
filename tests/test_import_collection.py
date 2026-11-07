import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import re
import asyncio, json
from playwright.async_api import async_playwright

# Import a folder or earlier export: the titles, and the step that adds the
# documents of a folder with an index.csv to a manual collection (new or
# existing). Folders are built in the test, no export step.
async def make_folder(page, name, files, index_rows):
    """files: {filename: text}; index_rows: list of (filename, title). Writes index.csv when index_rows is not None."""
    await page.evaluate("""async ([name, files, rows]) => {
        const dir = window.__makeEmptyRoot(); dir.name = name;
        const put = async (n, c) => { const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); };
        for(const [n, c] of Object.entries(files)) await put(n, c);
        if(rows !== null) await put('index.csv', 'File,Title\\n' + rows.map(r => r[0] + ',' + r[1]).join('\\n') + '\\n');
        window.__FOLDER = dir;
    }""", [name, files, index_rows])

async def library(page):
    return await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")

async def open_import(page):
    await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)

async def pick(page):
    await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__FOLDER; }")
    await page.click('#import-start-btn'); await page.wait_for_timeout(400)

# The pre-filled new-collection name: "{folder or export title} · YYYY-MM-DD HH:MM".
def STAMPED(base):
    return re.escape(base) + r' · \d{4}-\d{2}-\d{2} \d{2}:\d{2}$'

def members(rows, cid):
    return sorted(cd['document_id'] for cd in rows['collection_documents'] if cd['collection_id'] == cid)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

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
        # Scenario 9 makes saving collection links fail. The app binds db.run
        # when a library opens (trackDbChanges), so the switch goes in first.
        await page.evaluate("""async () => {
            const proto = (await window.initSqlJs()).Database.prototype;
            const run = proto.run;
            proto.run = function(sql, params){
                if(window.__FAIL_COLLECTION_LINKS && /INTO collection_documents/.test(sql)) throw new Error('disk full');
                return run.call(this, sql, params);
            };
        }""")
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({documents: [], fields: []});")
        await page.click("#open-btn"); await page.wait_for_timeout(500)
        await page.click('#tools-btn')
        print("The Tools entry names earlier exports:", 'earlier export' in await page.inner_text('#import-folder-btn'))
        await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
        print("The dialog title names earlier exports:", 'earlier export' in await page.inner_text('.modal h2'))
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === 1. A folder without index.csv imports at once, no options panel ===
        await make_folder(page, 'Plain', {'a.pdf': '%PDF-1.4 a'}, None)
        await open_import(page); await pick(page); await page.wait_for_timeout(1000)
        print("1. A plain folder shows no options panel:", not await page.locator('#import-options').is_visible())
        print("1. ...and imports at once:", 'Added: 1' in await page.inner_text('#import-summary'))
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === 2. With index.csv: the panel, "A new collection" by default ===
        await make_folder(page, 'Indexed', {'b.pdf': '%PDF-1.4 b', 'c.pdf': '%PDF-1.4 c', 'loose.pdf': '%PDF-1.4 loose'}, [('b.pdf', 'Bee'), ('c.pdf', 'Sea')])
        await open_import(page); await pick(page)
        print("2. The options panel shows:", await page.locator('#import-options').is_visible())
        print("2. ...with the matched count:", '2 files in this folder are listed in index.csv.' in await page.inner_text('#import-options'))
        print("2. Nothing is imported before Import is clicked:", len((await library(page))['documents']) == 1)
        print("2. \"A new collection\" is the default:", await page.is_checked('#import-coll-new') and not await page.is_checked('#import-coll-none'))
        print("2. ...its name enabled, Import enabled:", await page.is_enabled('#import-coll-name') and await page.is_enabled('#import-run-btn'))
        print("2. ...named \"{folder} · date time\":", bool(re.match(STAMPED('Indexed'), await page.input_value('#import-coll-name'))), await page.input_value('#import-coll-name'))
        print("2. Without an export-details.json there is no \"About this export\":", 'About this export' not in await page.inner_text('#import-options'))
        await page.check('#import-coll-none')
        print("2. Choosing \"No collection\" disables the name:", await page.is_disabled('#import-coll-name') and await page.is_enabled('#import-run-btn'))
        print("2. \"An existing collection\" is disabled with no manual collection:", await page.is_disabled('#import-coll-existing') and await page.is_disabled('#import-coll-select'))
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        summary = await page.inner_text('#import-summary')
        print("2. Import adds all three files:", 'Added: 3' in summary, repr(summary))
        rows = await library(page)
        print("2. ...and no collection:", rows['collections'] == [] and 'Added to the collection' not in summary)
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === 3. A new collection, named after the folder (the default) ===
        await make_folder(page, 'Taxes 2025', {'d.pdf': '%PDF-1.4 d', 'e.pdf': '%PDF-1.4 e', 'loose2.pdf': '%PDF-1.4 loose2'}, [('d.pdf', 'Dee'), ('e.pdf', 'Eee')])
        await open_import(page); await pick(page)
        taxes = await page.input_value('#import-coll-name')
        print("3. The new name is pre-filled with the folder name and the time:", bool(re.match(STAMPED('Taxes 2025'), taxes)), taxes)
        print("3. Import is enabled for the new name:", await page.is_enabled('#import-run-btn'))
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        rows = await library(page)
        colls = [c for c in rows['collections'] if c['name'] == taxes]
        print("3. One manual collection with that name:", len(colls) == 1 and colls[0]['kind'] == 'manual', rows['collections'])
        by_title = {d['title']: d['id'] for d in rows['documents']}
        cid = colls[0]['id'] if colls else None
        print("3. It holds exactly the two files with a row:", members(rows, cid) == sorted([by_title.get('Dee'), by_title.get('Eee')]), members(rows, cid))
        print("3. ...not the loose file:", 'loose2' in by_title and by_title['loose2'] not in members(rows, cid))
        summary = await page.inner_text('#import-summary')
        print("3. The summary names the collection:", f'Added to the collection “{taxes}”: 2' in summary, repr(summary))
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === 4. An existing collection; a duplicate with a row joins too ===
        await make_folder(page, 'Taxes 2025', {'d.pdf': '%PDF-1.4 d', 'f.pdf': '%PDF-1.4 f'}, [('d.pdf', 'Dee'), ('f.pdf', 'Eff')])
        await open_import(page); await pick(page)
        print("4. \"An existing collection\" is offered now:", await page.is_enabled('#import-coll-existing'))
        await page.check('#import-coll-existing')
        await page.select_option('#import-coll-select', label=taxes)
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        rows = await library(page)
        summary = await page.inner_text('#import-summary')
        by_title = {d['title']: d['id'] for d in rows['documents']}
        print("4. d.pdf is skipped as a duplicate, f.pdf added:", 'Added: 1' in summary and 'Already in the library, skipped: 1' in summary, repr(summary))
        print("4. No second collection:", len(rows['collections']) == 1 and rows['collections'][0]['name'] == taxes, rows['collections'])
        print("4. The collection holds three documents, the duplicate's original and f.pdf among them:",
              members(rows, cid) == sorted([by_title.get('Dee'), by_title.get('Eee'), by_title.get('Eff')]), members(rows, cid))
        print("4. The summary counts both:", f'Added to the collection “{taxes}”: 2' in summary, repr(summary))
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === 5. A taken name (ignoring case) disables Import ===
        await make_folder(page, 'Other', {'h.pdf': '%PDF-1.4 h'}, [('h.pdf', 'Aitch')])
        await open_import(page); await pick(page)
        print("5. One listed file is worded in the singular:", '1 file in this folder is listed in index.csv.' in await page.inner_text('#import-options'))
        print("5. \"A new collection\" is already chosen:", await page.is_checked('#import-coll-new'))
        await page.fill('#import-coll-name', taxes.lower())
        print("5. A taken name disables Import:", await page.is_disabled('#import-run-btn'))
        print("5. ...and says so:", await page.locator('#import-coll-warn').is_visible() and 'already exists' in await page.inner_text('#import-coll-warn'))
        await page.fill('#import-coll-name', '   ')
        print("5. An empty name disables Import:", await page.is_disabled('#import-run-btn') and not await page.locator('#import-coll-warn').is_visible())
        await page.fill('#import-coll-name', 'Fresh name')
        print("5. A free name enables it again:", await page.is_enabled('#import-run-btn'))

        # === 7. Cancel with the panel showing imports nothing ===
        count_before = len((await library(page))['documents'])
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(300)
        print("7. Cancel closes the dialog:", await page.locator('.modal').count() == 0)
        print("7. ...and imports nothing:", len((await library(page))['documents']) == count_before and 'Fresh name' not in [c['name'] for c in (await library(page))['collections']])

        # === 6. Nothing qualifies: no empty collection is left behind ===
        await make_folder(page, 'Empty rows', {'g.pdf': '%PDF-1.4 g'}, [('other.pdf', 'Other')])
        await open_import(page); await pick(page)
        print("6. The default is a new collection here too:", await page.is_checked('#import-coll-new'))
        await page.fill('#import-coll-name', 'Ghost')
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        rows = await library(page)
        summary = await page.inner_text('#import-summary')
        print("6. The file is imported:", 'Added: 1' in summary, repr(summary))
        print("6. No collection Ghost:", 'Ghost' not in [c['name'] for c in rows['collections']])
        print("6. ...and no collection line:", 'Added to the collection' not in summary)
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === 8. Two identical files with rows: one document, counted once ===
        await make_folder(page, 'Twins', {'x1.pdf': '%PDF-1.4 twin', 'x2.pdf': '%PDF-1.4 twin'}, [('x1.pdf', 'Twin one'), ('x2.pdf', 'Twin two')])
        await open_import(page); await pick(page)
        twins_name = await page.input_value('#import-coll-name')
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        rows = await library(page)
        summary = await page.inner_text('#import-summary')
        twins = [c for c in rows['collections'] if c['name'] == twins_name]
        print("8. The second twin is skipped as a duplicate of the first:", 'Added: 1' in summary and 'Already in the library, skipped: 1' in summary, repr(summary))
        print("8. The collection holds the one document:", len(twins) == 1 and len(members(rows, twins[0]['id'])) == 1)
        print("8. ...and the summary counts it once:", f'Added to the collection “{twins_name}”: 1' in summary, repr(summary))
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === 9. Saving the collection throws: the import still ends, in red ===
        await page.evaluate("() => { window.__FAIL_COLLECTION_LINKS = true; }")
        await make_folder(page, 'Broken', {'k.pdf': '%PDF-1.4 k'}, [('k.pdf', 'Kay')])
        await open_import(page); await pick(page)
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        await page.evaluate("() => { window.__FAIL_COLLECTION_LINKS = false; }")
        summary = await page.inner_text('#import-summary')
        status_class = await page.get_attribute('#import-status', 'class')
        print("9. The document is still imported:", 'Added: 1' in summary, repr(summary))
        print("9. The summary says the collection could not be saved:", 'the collection could not be saved' in summary)
        print("9. ...with the status in the error colour, not left busy:", 'err' in status_class and 'busy' not in status_class, status_class)
        print("9. The dialog can be closed:", await page.is_enabled('#import-cancel-btn') and await page.is_enabled('#modal-close-btn'))
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # === 10. The same folder twice at once: the pre-filled name gets " (2)" ===
        # A fixed clock, so the minute can't change between the imports.
        await page.clock.set_fixed_time("2026-11-08T10:15:00")
        await make_folder(page, 'Again', {'r.pdf': '%PDF-1.4 r'}, [('r.pdf', 'Arr')])
        await open_import(page); await pick(page)
        first = await page.input_value('#import-coll-name')
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)
        await make_folder(page, 'Again', {'r.pdf': '%PDF-1.4 r', 'r2.pdf': '%PDF-1.4 r2'}, [('r.pdf', 'Arr'), ('r2.pdf', 'Arr two')])
        await open_import(page); await pick(page)
        second = await page.input_value('#import-coll-name')
        print("10. The second panel pre-fills the name with \" (2)\":", second == first + ' (2)', repr(first), repr(second))
        print("10. ...with no warning, Import enabled:", not await page.locator('#import-coll-warn').is_visible() and await page.is_enabled('#import-run-btn'))
        await page.fill('#import-coll-name', first.upper())
        print("10. A typed taken name is still refused, not renamed:", await page.is_disabled('#import-run-btn') and await page.input_value('#import-coll-name') == first.upper())
        await page.fill('#import-coll-name', second)
        await page.click('#import-run-btn'); await page.wait_for_timeout(1200)
        rows = await library(page)
        names = [c['name'] for c in rows['collections']]
        print("10. A second collection is created:", first in names and second in names, names)
        c2 = [c for c in rows['collections'] if c['name'] == second]
        print("10. ...holding both listed files (the duplicate's original too):", len(c2) == 1 and len(members(rows, c2[0]['id'])) == 2)
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        # A third collection name gets " (3)".
        await make_folder(page, 'Again', {'r3.pdf': '%PDF-1.4 r3'}, [('r3.pdf', 'Arr three')])
        await open_import(page); await pick(page)
        third = await page.input_value('#import-coll-name')
        print("10. A third import in that minute pre-fills \" (3)\":", third == first + ' (3)', repr(third))
        await page.click('#import-cancel-btn'); await page.wait_for_timeout(150)

        print("No page errors:", not errors, errors)

asyncio.run(main())
