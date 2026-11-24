import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

# Field Settings > New documents > "Set People to the person adding the document" (1.69.0) stores
# settings.default_people = 'adder' (empty when switched off). "Your name in this browser" (1.70.0) is kept in
# localStorage (dossiary_adder_name); with both, the capture form fills People with that name as an amber guess
# (cleared on first touch, saved when kept), and an Inbox add files the document under it. No name, or the setting
# off: People stays empty.

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [{"document_type": "Report", "field_name": "People", "position": 0}]
PEOPLE_INPUT = '#dynamic-fields-f [data-dynamic-field="People"] input'

async def read_db(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text());
        })()
    """)

def setting(db, key):
    rows = [r for r in db.get('settings', []) if r['key'] == key]
    return rows[0]['value'] if rows else None

def people_of(db, doc_id):
    people = {p['id']: p['name'] for p in db.get('people', [])}
    people_field = next((f['id'] for f in db.get('fields', []) if f['name'] == 'People'), None)
    return sorted(people[r['person_id']] for r in db.get('document_field_people', [])
                  if r['document_id'] == doc_id and r['field_id'] == people_field and r['person_id'] in people)

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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, []);")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        async def open_settings():
            await page.click('#tools-btn'); await page.click('#manage-fields-btn')
            await page.wait_for_timeout(150)

        async def close_settings():
            await page.keyboard.press('Escape')
            await page.wait_for_timeout(150)

        async def capture_people():
            await page.click('#add-btn')
            await page.wait_for_timeout(100)
            await page.fill('#f-type', 'Report')
            await page.locator('#f-type').blur()
            await page.wait_for_timeout(150)
            value = await page.locator(PEOPLE_INPUT).input_value()
            guess = 'field-guess' in (await page.locator(PEOPLE_INPUT).get_attribute('class') or '')
            return value, guess

        # --- The setting (1.69.0) ---
        await open_settings()
        box = '#fs-default-people'
        print("the checkbox is in New documents:", await page.locator(f'.fs-group:has(#fs-default-currency) {box}').count() == 1)
        print("off in a library without the setting:", not await page.is_checked(box))
        print("the name field is there and empty:", await page.locator('#fs-adder-name').input_value() == '')
        await page.check(box)
        await page.wait_for_timeout(200)
        print("ticking stores default_people = adder:", setting(await read_db(page), 'default_people') == 'adder')
        await close_settings(); await open_settings()
        print("still ticked when Field Settings opens again:", await page.is_checked(box))
        await close_settings()

        # --- On, but no name in this browser: nothing is filled ---
        value, guess = await capture_people()
        print("no name set: People stays empty and is no guess:", value == '' and not guess)
        await page.click('#modal-close-btn'); await page.wait_for_timeout(150)

        # --- The name (1.70.0) ---
        await open_settings()
        await page.fill('#fs-adder-name', '  Arne ')
        await page.locator('#fs-adder-name').dispatch_event('change')
        await page.wait_for_timeout(100)
        stored = await page.evaluate("localStorage.getItem('dossiary_adder_name')")
        print("the name is kept in this browser, trimmed:", stored == 'Arne')
        print("the name is not written into the library:", 'Arne' not in json.dumps(await read_db(page)))
        await close_settings()

        value, guess = await capture_people()
        print("capture fills People with the name:", value == 'Arne')
        print("as an amber guess:", guess)
        hint = await page.locator('#dynamic-fields-f [data-dynamic-field="People"] .field-guess-hint').inner_text()
        print("with the guess hint naming the person:", 'Arne' in hint)
        # The caret goes to the end by script: the End key doesn't move it on macOS (that is Cmd+Right there).
        await page.locator(PEOPLE_INPUT).evaluate("i => { i.focus(); i.setSelectionRange(i.value.length, i.value.length); }")
        await page.locator(PEOPLE_INPUT).type(', Jana')
        await page.wait_for_timeout(100)
        print("typing clears the guess flag:", 'field-guess' not in (await page.locator(PEOPLE_INPUT).get_attribute('class') or ''))
        await page.fill('#f-title', 'Gas bill')
        await page.set_input_files('#file-input', 'curdoc.pdf')
        await page.wait_for_timeout(300)
        field_before_save = await page.locator(PEOPLE_INPUT).input_value()
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(500)
        db1 = await read_db(page)
        doc = next((d for d in db1['documents'] if d['title'] == 'Gas bill'), None)
        print("the captured document is saved:", doc is not None)
        saved = people_of(db1, doc['id']) if doc is not None else None
        print("its People are the kept guess plus the typed name:", saved == ['Arne', 'Jana'])
        if saved != ['Arne', 'Jana']:
            print("  saved People:", saved, "| field before saving:", repr(field_before_save))
            print("  people rows:", db1.get('people'), "| links:", [r for r in db1.get('document_field_people', []) if doc and r['document_id'] == doc['id']])

        # --- An Inbox add files the document under the name ---
        await page.evaluate("() => window.__addInboxFile(window.__TEST_ROOT, 'scan_one.pdf')")
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(400)
        print("the inbox banner shows the waiting file:", await page.locator('#inbox-banner').is_visible())
        await page.click('#inbox-add-all-btn')
        await page.wait_for_timeout(500)
        db2 = await read_db(page)
        added = next((d for d in db2['documents'] if d['title'] == 'scan_one'), None)
        print("the Inbox file is added:", added is not None)
        print("and filed under the name:", added is not None and people_of(db2, added['id']) == ['Arne'])

        # --- Off again: no guess, though the name stays in the browser ---
        await open_settings()
        await page.uncheck(box)
        await page.wait_for_timeout(200)
        print("unticking stores an empty value:", setting(await read_db(page), 'default_people') == '')
        await close_settings()
        value, guess = await capture_people()
        print("setting off: People stays empty:", value == '' and not guess)
        await page.click('#modal-close-btn'); await page.wait_for_timeout(150)

        # A value the page doesn't know (a later version's) reads as off.
        await page.evaluate("""(() => { window.__DEBUG_dbRun("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_people', ?)", ['Arne']); window.__DEBUG_loadDefaultPeople(); })()""")
        await open_settings()
        print("another value reads as off:", not await page.is_checked(box))
        print("and gives no guess:", await page.evaluate("window.__DEBUG_adderGuess()") is None)
        await close_settings()

        print("no JS errors:", errors == [])
        if errors: print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
