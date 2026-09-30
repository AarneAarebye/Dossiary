import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

# The Smart Collection editor: rule-based criteria (field / operator / value,
# match all or any, relative dates), editing an existing collection --
# including one saved the old way, as a toolbar snapshot -- creating one from
# scratch, the toolbar's "Save as Smart Collection" storing rules, and rules
# following a value rename and a field deletion.
TODAY = datetime.now(timezone.utc).date()
def iso(d): return f"{d.isoformat()}T00:00:00+00:00"
D1 = TODAY - timedelta(days=5)
D2 = TODAY - timedelta(days=40)
D3 = TODAY.replace(year=TODAY.year - 1, month=6, day=15)

def doc(i, title, date, **extra):
    d = {
        "id": i, "title": title, "category": None, "subcategory": None, "document_type": None,
        "date": iso(date) if date else None, "import_date": iso(TODAY), "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": None, "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }
    d.update(extra)
    return d

LEGACY = {"q": "", "category": "Travel", "type": "", "person": "", "showArchived": False, "dynamic": [],
          "amountMin": "50", "amountMax": "", "amountUnset": False}

SEED = {
    "documents": [
        doc(1, "Hotel Berlin", D1, category="Travel"),
        doc(2, "Train", D2, category="Travel"),
        doc(3, "Groceries", D3, category="Food", archived=1),
        doc(4, "Letter", None, needs_review=1, notes="important contract"),
        doc(5, "Old ticket", D1, category="Travel", deleted=1),
    ],
    "tags": [{"id": 1, "name": "trip"}, {"id": 2, "name": "rail"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}, {"document_id": 2, "tag_id": 1}, {"document_id": 2, "tag_id": 2}],
    "people": [{"id": 1, "name": "Arne"}, {"id": 2, "name": "Jana"}],
    "fields": [
        {"id": 1, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 5, "name": "Paid", "type": "checkbox", "show_as_column": 0, "autocomplete": 0},
        {"id": 6, "name": "Organization", "type": "text", "show_as_column": 0, "autocomplete": 1},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 2, "value": "120"}, {"document_id": 2, "field_id": 2, "value": "30"},
        {"document_id": 3, "field_id": 2, "value": "55"},
        {"document_id": 1, "field_id": 5, "value": "1"}, {"document_id": 2, "field_id": 5, "value": "0"},
    ],
    "document_field_people": [{"document_id": 1, "field_id": 4, "person_id": 1}, {"document_id": 2, "field_id": 4, "person_id": 2}],
    "collections": [{"id": 1, "name": "Big trips", "kind": "smart", "criteria": json.dumps(LEGACY)}],
}

def expected_ids(pred):
    dates = {1: D1, 2: D2, 3: D3, 4: None}
    return sorted(i for i, d in dates.items() if d and pred(d))

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        async def state():
            return await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        async def ids(match, *rules):
            return await page.evaluate("c => window.__DEBUG_smartMatchIds(c)", {"match": match, "rules": list(rules)})
        async def table_ids():
            return sorted(await page.locator('#doc-tbody tr[data-id]').evaluate_all("rs => rs.map(r => Number(r.dataset.id))"))
        R = lambda field, op, value=None, value2=None: {k: v for k, v in {"field": field, "op": op, "value": value, "value2": value2}.items() if v is not None}

        # === Scenario 1: every kind of rule, evaluated directly ===
        checks = [
            ("Category is (case-insensitive)", await ids('all', R('category', 'is', 'travel')), [1, 2]),
            ("Category is not", await ids('all', R('category', 'is_not', 'Travel')), [3, 4]),
            ("Category contains", await ids('all', R('category', 'contains', 'oo')), [3]),
            ("Category is empty", await ids('all', R('category', 'empty')), [4]),
            ("Tags include", await ids('all', R('tags', 'includes', 'rail')), [2]),
            ("Tags don't include", await ids('all', R('tags', 'excludes', 'trip')), [3, 4]),
            ("Tags empty", await ids('all', R('tags', 'empty')), [3, 4]),
            ("People include (person field)", await ids('all', R('field:4', 'includes', 'jana')), [2]),
            ("Checkbox checked", await ids('all', R('field:5', 'checked')), [1]),
            ("Checkbox not checked", await ids('all', R('field:5', 'unchecked')), [2]),
            ("Checkbox not set", await ids('all', R('field:5', 'empty')), [3, 4]),
            ("Amount between (inclusive)", await ids('all', R('field:2', 'between', '55', '120')), [1, 3]),
            ("Amount at least", await ids('all', R('field:2', 'gte', '55')), [1, 3]),
            ("Amount at most", await ids('all', R('field:2', 'lte', '30')), [2]),
            ("Amount is", await ids('all', R('field:2', 'is', '30')), [2]),
            ("Amount empty", await ids('all', R('field:2', 'empty')), [4]),
            ("Any text contains (notes)", await ids('all', R('any', 'contains', 'CONTRACT')), [4]),
            ("Any text doesn't contain", await ids('all', R('any', 'not_contains', 'train')), [1, 3, 4]),
            ("Status archived", await ids('all', R('status', 'archived')), [3]),
            ("Status in review", await ids('all', R('status', 'in_review')), [4]),
            ("Date in the last 30 days", await ids('all', R('date', 'last_days', '30')), [1]),
            ("Date this year", await ids('all', R('date', 'this_year')), expected_ids(lambda d: d.year == TODAY.year)),
            ("Date last year", await ids('all', R('date', 'last_year')), expected_ids(lambda d: d.year == TODAY.year - 1)),
            ("Date this month", await ids('all', R('date', 'this_month')), expected_ids(lambda d: (d.year, d.month) == (TODAY.year, TODAY.month))),
            ("Date before", await ids('all', R('date', 'before', D2.isoformat())), [3]),
            ("Date on", await ids('all', R('date', 'on', D1.isoformat())), [1]),
            ("Date empty", await ids('all', R('date', 'empty')), [4]),
            ("Imported between", await ids('all', R('import_date', 'between', TODAY.isoformat(), TODAY.isoformat())), [1, 2, 3, 4]),
            ("All of two rules", await ids('all', R('category', 'is', 'Travel'), R('field:2', 'gte', '50')), [1]),
            ("Any of two rules", await ids('any', R('category', 'is', 'Food'), R('tags', 'includes', 'rail')), [2, 3]),
            ("No rules match everything (not the Waste bin)", await ids('all'), [1, 2, 3, 4]),
        ]
        for label, got, want in checks:
            print(f"{label}:", got == want, got if got != want else '')

        # === Scenario 2: an old toolbar-snapshot collection opens in the editor as rules ===
        await page.click('#tools-btn'); await page.click('#manage-collections-btn')
        await page.wait_for_timeout(200)
        await page.click('.manage-collection-row[data-collection-id="1"] .manage-collection-edit-btn')
        await page.wait_for_timeout(200)
        rules = await page.locator('.smart-rule').evaluate_all("""rs => rs.map(r => [r.querySelector('.smart-rule-field').value,
            r.querySelector('.smart-rule-op').value, [...r.querySelectorAll('.smart-rule-value')].map(i => i.value)])""")
        print("Old criteria shown as rules (Category is Travel, Amount at least 50):",
              rules == [['category', 'is', ['Travel']], ['field:2', 'gte', ['50']]], rules)
        print("Name filled in:", await page.input_value('#smart-name-input') == 'Big trips')
        print("Live count for the unchanged rules:", await page.inner_text('#smart-match-count') == '1 document matches')
        await page.fill('.smart-rule[data-idx="1"] .smart-rule-value', '20')
        await page.wait_for_timeout(100)
        print("Count follows the edited value:", await page.inner_text('#smart-match-count') == '2 documents match')
        await page.click('#smart-save-btn')
        await page.wait_for_timeout(300)
        print("Saving returns to Manage Collections:", await page.locator('#manage-collections-list').count() == 1)
        crit = json.loads((await state())['collections'][0]['criteria'])
        print("Saved as rules:", crit == {"match": "all", "rules": [{"field": "category", "op": "is", "value": "Travel"}, {"field": "field:2", "op": "gte", "value": "20"}]}, crit)
        await page.click('#mc-done-btn')
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(200)
        print("The collection shows the new matches:", await table_ids() == [1, 2], await table_ids())

        # === Scenario 3: a new collection from scratch, with validation ===
        await page.click('#tools-btn'); await page.click('#manage-collections-btn')
        await page.wait_for_timeout(200)
        await page.click('#manage-new-smart-btn')
        await page.wait_for_timeout(200)
        print("New collection starts with one rule:", await page.locator('.smart-rule').count() == 1)
        await page.click('#smart-save-btn')
        await page.wait_for_timeout(100)
        print("A missing name is refused:", 'name' in await page.inner_text('#smart-editor-status'))
        await page.fill('#smart-name-input', 'Recent or open')
        await page.click('#smart-save-btn')
        await page.wait_for_timeout(100)
        print("An empty rule value is refused:", 'value' in await page.inner_text('#smart-editor-status'))
        await page.select_option('.smart-rule[data-idx="0"] .smart-rule-field', 'date')
        await page.select_option('.smart-rule[data-idx="0"] .smart-rule-op', 'last_days')
        await page.fill('.smart-rule[data-idx="0"] .smart-rule-value', '30')
        await page.wait_for_timeout(100)
        print("Date rule offers relative choices:", 'this_year' in await page.locator('.smart-rule[data-idx="0"] .smart-rule-op option').evaluate_all("os => os.map(o => o.value)"))
        await page.click('#smart-add-rule-btn')
        await page.select_option('.smart-rule[data-idx="1"] .smart-rule-field', 'status')
        await page.select_option('.smart-rule[data-idx="1"] .smart-rule-op', 'in_review')
        print("A status rule needs no value box:", await page.locator('.smart-rule[data-idx="1"] .smart-rule-value').count() == 0)
        await page.click('#smart-add-rule-btn')
        await page.select_option('.smart-rule[data-idx="2"] .smart-rule-field', 'field:2')
        await page.select_option('.smart-rule[data-idx="2"] .smart-rule-op', 'between')
        print("'Between' shows two value boxes:", await page.locator('.smart-rule[data-idx="2"] .smart-rule-value').count() == 2)
        await page.click('.smart-rule[data-idx="2"] .smart-rule-remove')
        print("A rule can be removed:", await page.locator('.smart-rule').count() == 2)
        await page.wait_for_timeout(100)
        print("All rules: nothing is both recent and in review:", await page.inner_text('#smart-match-count') == '0 documents match')
        await page.select_option('#smart-match-select', 'any')
        await page.wait_for_timeout(100)
        print("Any rule: two documents:", await page.inner_text('#smart-match-count') == '2 documents match')
        await page.click('#smart-save-btn')
        await page.wait_for_timeout(300)
        st = await state()
        new = next(c for c in st['collections'] if c['name'] == 'Recent or open')
        print("New Smart Collection saved:", new['kind'] == 'smart' and json.loads(new['criteria'])['match'] == 'any')
        await page.click('#mc-done-btn')
        await page.click(f'#nav-item-collection-{new["id"]}')
        await page.wait_for_timeout(200)
        print("...and shows the recent and the in-review document:", await table_ids() == [1, 4], await table_ids())

        # === Scenario 4: the toolbar's "Save as Smart Collection" stores rules ===
        await page.click('#nav-item-all')
        await page.select_option('#category-filter', 'Travel')
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.fill('#smart-collection-name-input', 'Travel')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(300)
        await page.select_option('#category-filter', '')
        st = await state()
        tc = next(c for c in st['collections'] if c['name'] == 'Travel')
        print("Toolbar filters saved as rules:", json.loads(tc['criteria']) == {"match": "all", "rules": [{"field": "category", "op": "is", "value": "Travel"}]}, tc['criteria'])

        # === Scenario 5: rules follow a value rename ===
        await page.click('#tools-btn'); await page.click('#manage-values-btn')
        await page.wait_for_timeout(200)
        await page.click('.values-row[data-value="Travel"] .values-rename-btn')
        await page.fill('.values-rename-input', 'Journeys')
        await page.press('.values-rename-input', 'Enter')
        await page.wait_for_timeout(400)
        await page.click('#modal-close-btn')
        st = await state()
        crits = {c['name']: json.loads(c['criteria']) for c in st['collections']}
        print("Renamed category followed in rule-based collections:",
              crits['Travel']['rules'][0]['value'] == 'Journeys' and crits['Big trips']['rules'][0]['value'] == 'Journeys')
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(200)
        print("...and the collection still matches:", await table_ids() == [1, 2], await table_ids())

        # === Scenario 6: deleting a field removes its rules ===
        await page.evaluate("""async () => {
            const h = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const data = JSON.parse(await (await h.getFile()).text());
            data.collections.find(c => c.id === 1).criteria = JSON.stringify({match: 'all', rules: [
                {field: 'category', op: 'is', value: 'Journeys'}, {field: 'field:6', op: 'is', value: 'Acme'}]});
            const w = await h.createWritable(); await w.write(JSON.stringify(data)); await w.close();
        }""")
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(500)
        await page.click('#tools-btn'); await page.click('#library-check-btn')
        await page.wait_for_timeout(1000)
        row = page.locator('#unused-fields-section .unused-field-row').filter(has_text='Organization')
        await row.locator('.unused-field-delete-btn').click()
        await page.wait_for_timeout(400)
        crit = json.loads(next(c for c in (await state())['collections'] if c['id'] == 1)['criteria'])
        print("Deleting a field removes only its rule:", crit['rules'] == [{"field": "category", "op": "is", "value": "Journeys"}], crit)

        # === Scenario 7: German labels ===
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(100)
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        await page.click('#tools-btn'); await page.click('#manage-collections-btn')
        await page.wait_for_timeout(200)
        await page.click('.manage-collection-row[data-collection-id="1"] .manage-collection-edit-btn')
        await page.wait_for_timeout(200)
        print("Editor in German:", 'Smart Collection bearbeiten' in await page.inner_text('.modal h2')
              and 'ist' in await page.locator('.smart-rule-op').first.evaluate("s => s.selectedOptions[0].textContent"))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
