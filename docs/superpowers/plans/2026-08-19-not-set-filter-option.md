# "Not Set" Filter Option Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person filter the document table to only documents missing
a given field (Category, Type, People, or any custom text/checkbox field
that already has a filter dropdown), via one new "— Not set —" option
added to each existing dropdown.

**Architecture:** A single new sentinel constant (`FILTER_UNSET`) flows
through two existing functions — `populateFilters()` gains one new
`<option>` per dropdown, and `matchesCriteria()` (the one shared predicate
both the live toolbar and saved Smart Collection criteria already use)
gains one new branch per field type to interpret that sentinel. No new
functions, no new data model, no new UI elements beyond the option itself.

**Tech Stack:** Plain JS/CSS/HTML (no new dependencies), Playwright for the
new regression test (using the existing `tests/stub_studio2.js` stub).

## Global Constraints

- One shared i18n key (`toolbarFieldNotSet`), not per-field keys — added to
  all six `STRINGS` language blocks (`en`/`de`/`es`/`fr`/`zh-Hans`/
  `zh-Hant`).
- A checkbox custom field explicitly saved as unchecked (stored as the
  string `'0'`) must NOT be treated as "not set" — only a field that was
  never saved at all for that document counts as unset. Text fields are
  never saved blank in the first place (existing behavior — blank text
  fields are skipped on save), so this distinction only matters for
  checkbox fields in practice, but the underlying check (`actual !==
  undefined`) must be correct for both.
- Number/Date/Amount/Currency fields have no filter dropdown today and get
  no "not set" option — out of scope, not a bug to "complete."
- The existing 58-script Playwright suite must all still pass.

---

### Task 1: Add the `FILTER_UNSET` sentinel, the new dropdown option, and the new match logic

**Files:**
- Modify: `dossiary.html:1994` (add the `FILTER_UNSET` constant just above
  `FIELD_DEFS`)
- Modify: `dossiary.html:3543-3559` (`populateFilters()` — Category/Type/
  People's option-list template strings, and the dynamic-filter template
  string)
- Modify: `dossiary.html:3778-3785` (`matchesCriteria()` — the category/
  type/person checks and the dynamic-fields loop)
- Modify: `dossiary.html` — `STRINGS.en`/`.de`/`.es`/`.fr`/`['zh-Hans']`/
  `['zh-Hant']` (one new key each)
- Modify: `CLAUDE.md` (brief addition to the existing "Configurable
  columns/filters" note)

**Interfaces:**
- Produces: `FILTER_UNSET` (the string `'__unset__'`), used by both
  `populateFilters()` and `matchesCriteria()`. Task 2's test relies on this
  exact string value to check dropdown option values directly.

- [ ] **Step 1: Add the `FILTER_UNSET` constant**

Edit `dossiary.html`, replacing:

```js
  const FIELD_DEFS = [
```

with:

```js
  // Sentinel value for "this field has no saved value on the document at
  // all" -- distinct from the empty string, which populateFilters()'s own
  // "All X" option already uses to mean "this filter isn't active." A real
  // category/type/person/field name could theoretically collide with this
  // exact string if someone typed it verbatim as free text, but that's an
  // extremely unlikely edge case, not worth guarding against further.
  const FILTER_UNSET = '__unset__';
  const FIELD_DEFS = [
```

- [ ] **Step 2: Add the new option to Category/Type/People's dropdowns**

Edit `dossiary.html`, replacing:

```js
  function populateFilters(){
    const categories = [...new Set(allDocs.map(d => d.category).filter(Boolean))].sort();
    const types = [...new Set(allDocs.map(d => d.document_type).filter(Boolean))].sort();
    const people = [...new Set(allDocs.flatMap(d => d.people || []))].sort();
    categoryFilter.innerHTML = `<option value="">${t('toolbarAllCategories')}</option>` + categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    typeFilter.innerHTML = `<option value="">${t('toolbarAllTypes')}</option>` + types.map(tp => `<option value="${escapeHtml(tp)}">${escapeHtml(tp)}</option>`).join('');
    personFilter.innerHTML = `<option value="">${t('toolbarAllPeople')}</option>` + people.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('');
```

with:

```js
  function populateFilters(){
    const categories = [...new Set(allDocs.map(d => d.category).filter(Boolean))].sort();
    const types = [...new Set(allDocs.map(d => d.document_type).filter(Boolean))].sort();
    const people = [...new Set(allDocs.flatMap(d => d.people || []))].sort();
    const notSetOption = `<option value="${FILTER_UNSET}">${t('toolbarFieldNotSet')}</option>`;
    categoryFilter.innerHTML = `<option value="">${t('toolbarAllCategories')}</option>` + notSetOption + categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    typeFilter.innerHTML = `<option value="">${t('toolbarAllTypes')}</option>` + notSetOption + types.map(tp => `<option value="${escapeHtml(tp)}">${escapeHtml(tp)}</option>`).join('');
    personFilter.innerHTML = `<option value="">${t('toolbarAllPeople')}</option>` + notSetOption + people.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('');
```

- [ ] **Step 3: Add the new option to every dynamic custom-field dropdown**

Edit `dossiary.html`, replacing:

```js
    const dynamicFiltersEl = el('dynamic-filters');
    dynamicFiltersEl.innerHTML = dynamicColumnDefs().filter(f => f.hasFilter).map(f => {
      const values = [...new Set(allDocs.map(d => (d.customFields || {})[f.label]).filter(Boolean))].sort();
      return `<span class="filter-wrap" data-field="${f.id}"><select id="dyn-filter-${f.id}" data-field-label="${escapeHtml(f.label)}">
        <option value="">${t('toolbarAllDynamic', {label: escapeHtml(f.label.toLowerCase())})}</option>
        ${values.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('')}
      </select></span>`;
    }).join('');
```

with:

```js
    const dynamicFiltersEl = el('dynamic-filters');
    dynamicFiltersEl.innerHTML = dynamicColumnDefs().filter(f => f.hasFilter).map(f => {
      const values = [...new Set(allDocs.map(d => (d.customFields || {})[f.label]).filter(Boolean))].sort();
      return `<span class="filter-wrap" data-field="${f.id}"><select id="dyn-filter-${f.id}" data-field-label="${escapeHtml(f.label)}">
        <option value="">${t('toolbarAllDynamic', {label: escapeHtml(f.label.toLowerCase())})}</option>
        ${notSetOption}
        ${values.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join('')}
      </select></span>`;
    }).join('');
```

- [ ] **Step 4: Teach `matchesCriteria()` to interpret the sentinel**

Edit `dossiary.html`, replacing:

```js
  function matchesCriteria(d, criteria){
    const { q, category, type, person, dynamic } = criteria;
    if(category && d.category !== category) return false;
    if(type && d.document_type !== type) return false;
    if(person && !(d.people||[]).includes(person)) return false;
    for(const f of dynamic){
      if((d.customFields || {})[f.label] !== f.value) return false;
    }
```

with:

```js
  function matchesCriteria(d, criteria){
    const { q, category, type, person, dynamic } = criteria;
    if(category){
      if(category === FILTER_UNSET ? !!d.category : d.category !== category) return false;
    }
    if(type){
      if(type === FILTER_UNSET ? !!d.document_type : d.document_type !== type) return false;
    }
    if(person){
      if(person === FILTER_UNSET ? (d.people||[]).length > 0 : !(d.people||[]).includes(person)) return false;
    }
    for(const f of dynamic){
      const actual = (d.customFields || {})[f.label];
      // A checkbox field explicitly saved as unchecked is stored as the
      // string '0' -- real, meaningful data, not "unset" (see
      // readDynamicFieldValues()'s own note on this same distinction for
      // the save path). Only a field with NO saved value at all
      // (actual === undefined) counts as not set; a falsy-looking value
      // like '0' does not.
      if(f.value === FILTER_UNSET ? actual !== undefined : actual !== f.value) return false;
    }
```

- [ ] **Step 5: Add the `toolbarFieldNotSet` i18n key to all six languages**

Edit `dossiary.html`, replacing (English, `STRINGS.en`):

```js
      toolbarAllTypes: 'All types', toolbarAllPeople: 'All people', toolbarAllDynamic: 'All {label}',
```

with:

```js
      toolbarAllTypes: 'All types', toolbarAllPeople: 'All people', toolbarAllDynamic: 'All {label}', toolbarFieldNotSet: '— Not set —',
```

Replacing (Spanish, `STRINGS.es`):

```js
      toolbarAllTypes: 'Todos los tipos', toolbarAllPeople: 'Todas las personas', toolbarAllDynamic: 'Todos los {label}',
```

with:

```js
      toolbarAllTypes: 'Todos los tipos', toolbarAllPeople: 'Todas las personas', toolbarAllDynamic: 'Todos los {label}', toolbarFieldNotSet: '— Sin definir —',
```

Replacing (French, `STRINGS.fr`):

```js
      toolbarAllTypes: 'Tous les types', toolbarAllPeople: 'Toutes les personnes', toolbarAllDynamic: '{label} : tous',
```

with:

```js
      toolbarAllTypes: 'Tous les types', toolbarAllPeople: 'Toutes les personnes', toolbarAllDynamic: '{label} : tous', toolbarFieldNotSet: '— Non défini —',
```

Replacing (German, `STRINGS.de`):

```js
      toolbarAllTypes: 'Alle Typen', toolbarAllPeople: 'Alle Personen', toolbarAllDynamic: 'Alle {label}',
```

with:

```js
      toolbarAllTypes: 'Alle Typen', toolbarAllPeople: 'Alle Personen', toolbarAllDynamic: 'Alle {label}', toolbarFieldNotSet: '— Nicht gesetzt —',
```

Replacing (Chinese Simplified, `STRINGS['zh-Hans']`):

```js
      toolbarAllTypes: '所有类型', toolbarAllPeople: '所有人员', toolbarAllDynamic: '所有{label}',
```

with:

```js
      toolbarAllTypes: '所有类型', toolbarAllPeople: '所有人员', toolbarAllDynamic: '所有{label}', toolbarFieldNotSet: '— 未设置 —',
```

Replacing (Chinese Traditional, `STRINGS['zh-Hant']` — this block uses
one-key-per-line formatting, unlike the other five; the value below is the
correct OpenCC `s2t` (Simplified→Traditional) conversion of the Simplified
string just added above, keeping the two scripts in lockstep the same way
this app's other `zh-Hant` strings already are — see `CLAUDE.md`'s own
note on why `zh-Hant` is always derived from `zh-Hans`, never translated
independently):

```js
      toolbarAllDynamic: '所有{label}',
```

with:

```js
      toolbarAllDynamic: '所有{label}',
      toolbarFieldNotSet: '— 未設置 —',
```

- [ ] **Step 6: Document the sentinel mechanism in `CLAUDE.md`**

Find the existing "Configurable columns/filters" note in `CLAUDE.md`
(search for `FIELD_DEFS`, `visibleColumns`, `renderColumnsMenu()`). Add a
short paragraph after it (a few sentences, matching this file's existing
voice) explaining: `FILTER_UNSET` is a dedicated sentinel distinct from
the empty-string "no filter active" value; `populateFilters()` adds one
"— Not set —" option per dropdown (Category/Type/People plus every
dynamic filter); `matchesCriteria()` — the single function both the live
toolbar and saved Smart Collection criteria already share — interprets it
per field type (scalar `!!value`, array `.length > 0`, dynamic fields
`actual !== undefined`); and the checkbox-`'0'`-is-real-data-not-unset
distinction is deliberate, matching `readDynamicFieldValues()`'s own
existing rule for the save path (an unchecked box is meaningful data, not
"empty").

- [ ] **Step 7: Manually verify in a real browser**

Open the app with a seeded library containing at least one document with
a blank Category. Confirm the Category dropdown shows "— Not set —" right
after "All categories," and selecting it narrows the table to only that
document. Repeat for Type. This is a quick sanity check before Task 2's
automated coverage — if this doesn't work, don't proceed to Task 2.

- [ ] **Step 8: Run the full test suite to confirm no regressions**

Run:

```bash
cd tests && python3 -c "
import subprocess, glob
failed = []
files = sorted(glob.glob('test_*.py'))
for f in files:
    p = subprocess.run(['python3', f], capture_output=True, text=True, timeout=180)
    if p.returncode != 0 or 'Traceback' in p.stdout or 'Traceback' in p.stderr:
        failed.append(f)
        print(f'FAILED: {f}')
print(f'TOTAL: {len(files)}  FAILED: {failed}')
"
```

Expected: `TOTAL: 58  FAILED: []` (this task doesn't add a new test file
yet — Task 2 does — so the count doesn't change here).

- [ ] **Step 9: Commit**

```bash
git add dossiary.html CLAUDE.md
git commit -m "$(cat <<'EOF'
Add a "not set" option to every filter dropdown

Category, Type, People, and any custom text/checkbox field's filter
dropdown all gain a new "— Not set —" option, via a FILTER_UNSET
sentinel distinct from the empty-string "no filter active" value.
matchesCriteria() -- the one predicate both the live toolbar and
saved Smart Collection criteria already share -- interprets it per
field type, so this works everywhere filters already apply (the
toolbar, Smart Collections, and Reports' own filter composition) with
no separate code path. A checkbox field explicitly saved as
unchecked ('0') is real data, not "unset" -- only a field with no
saved value at all counts.
EOF
)"
```

---

### Task 2: Add Playwright test coverage

**Files:**
- Create: `tests/test_not_set_filter.py`

**Interfaces:**
- Consumes: `FILTER_UNSET`'s exact string value (`'__unset__'`) from
  Task 1, to check dropdown option values directly.

- [ ] **Step 1: Write the test file**

Create `tests/test_not_set_filter.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: everything set (Category, Type, People, Status text field, Paid
#        checkbox checked) -- the baseline "nothing should match a 'not
#        set' filter" document.
# Doc 2: Category is blank -- the only document that should match the
#        Category "not set" filter.
# Doc 3: Type is blank, People has no one linked, Status was never saved,
#        and Paid was never saved either (no document_field_values row at
#        all for either custom field) -- the document every OTHER "not
#        set" filter (Type/People/Status/Paid) should match.
# Doc 4: Paid is explicitly saved as unchecked ('0') -- must NOT appear
#        under Paid's "not set" filter, since '0' is real saved data, not
#        a missing value. Category/Type/People/Status are all set on this
#        one so only the Paid check is actually being exercised.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc 1 (everything set)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Doc 2 (no category)", "category": None, "document_type": "Receipt",
            "date": "2026-03-02T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-03-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Doc 3 (no type, no people, no custom fields)", "category": "Travel", "document_type": None,
            "date": "2026-03-03T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-03-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 4, "title": "Doc 4 (Paid explicitly unchecked)", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-04T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-03-04T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Status", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 2, "name": "Paid", "type": "checkbox", "show_as_column": 1, "autocomplete": 0},
        {"id": 3, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 1, "value": "Open"},
        {"document_id": 1, "field_id": 2, "value": "1"},
        {"document_id": 4, "field_id": 1, "value": "Open"},
        {"document_id": 4, "field_id": 2, "value": "0"},
    ],
    "people": [
        {"id": 1, "name": "Alice"},
    ],
    "document_field_people": [
        {"document_id": 1, "field_id": 3, "person_id": 1},
        {"document_id": 4, "field_id": 3, "person_id": 1},
    ],
}

FILTER_UNSET = '__unset__'

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
    ))

async def option_label(page, select_id, value):
    return await page.evaluate(f"""
        () => {{
            const opts = Array.from(document.querySelector('{select_id}').options);
            const opt = opts.find(o => o.value === '{value}');
            return opt ? opt.textContent : null;
        }}
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

        # Dynamic custom-field filters (Status, Paid) only render into the
        # DOM behind a data-field-wrapped <span> that applyColumnVisibility()
        # hides unless that field's own COLUMN is toggled visible -- a
        # completely separate on/off switch from the filter dropdown itself
        # (dynamicColumnDefs() defaults every custom field's column to
        # defaultVisible:false, per dossiary.html's own dynamicColumnDefs()).
        # Toggle both on once, via the same Columns-menu checkbox flow
        # test_generic_column_system.py's own tests already use, before any
        # scenario below tries to interact with either dynamic filter.
        await page.click('#columns-btn')
        await page.wait_for_timeout(100)
        await page.check('#col-toggle-field-1')  # Status
        await page.check('#col-toggle-field-2')  # Paid
        await page.wait_for_timeout(150)
        await page.click('#columns-btn')  # close the menu
        await page.wait_for_timeout(100)

        # === Scenario 1: the "not set" option exists, with the exact
        # expected value, in every filter dropdown (built-in and dynamic) ===
        category_label = await option_label(page, '#category-filter', FILTER_UNSET)
        assert category_label is not None, "Category filter is missing a '__unset__'-valued option"
        print(f"Category filter has a 'Not set' option: {category_label!r}")

        type_label = await option_label(page, '#type-filter', FILTER_UNSET)
        assert type_label is not None, "Type filter is missing a '__unset__'-valued option"
        print(f"Type filter has a 'Not set' option: {type_label!r}")

        person_label = await option_label(page, '#person-filter', FILTER_UNSET)
        assert person_label is not None, "Person filter is missing a '__unset__'-valued option"
        print(f"Person filter has a 'Not set' option: {person_label!r}")

        status_label = await option_label(page, '#dyn-filter-field-1', FILTER_UNSET)
        assert status_label is not None, "Status (dynamic text field) filter is missing a '__unset__'-valued option"
        print(f"Status filter has a 'Not set' option: {status_label!r}")

        paid_label = await option_label(page, '#dyn-filter-field-2', FILTER_UNSET)
        assert paid_label is not None, "Paid (dynamic checkbox field) filter is missing a '__unset__'-valued option"
        print(f"Paid filter has a 'Not set' option: {paid_label!r}")

        # === Scenario 2: Category "not set" matches only doc 2 ===
        await page.select_option('#category-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2'], f"Category 'not set' should show only doc 2, got {ids}"
        print("Category 'not set' filter shows only doc 2:", ids)
        await page.select_option('#category-filter', '')
        await page.wait_for_timeout(150)

        # === Scenario 3: Type "not set" matches only doc 3 ===
        await page.select_option('#type-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['3'], f"Type 'not set' should show only doc 3, got {ids}"
        print("Type 'not set' filter shows only doc 3:", ids)
        await page.select_option('#type-filter', '')
        await page.wait_for_timeout(150)

        # === Scenario 4: People "not set" matches only doc 3 (docs 1 and 4
        # both have Alice linked; doc 2 also has no People value seeded, so
        # confirm it's included too since this scenario isn't scoped by
        # Category) ===
        await page.select_option('#person-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2', '3'], f"People 'not set' should show docs 2 and 3, got {ids}"
        print("People 'not set' filter shows docs 2 and 3:", ids)
        await page.select_option('#person-filter', '')
        await page.wait_for_timeout(150)

        # === Scenario 5: Status (dynamic text field) "not set" matches
        # only doc 3 (docs 1 and 4 have it saved; doc 2 also has no Status
        # value seeded) ===
        await page.select_option('#dyn-filter-field-1', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2', '3'], f"Status 'not set' should show docs 2 and 3, got {ids}"
        print("Status 'not set' filter shows docs 2 and 3:", ids)
        await page.select_option('#dyn-filter-field-1', '')
        await page.wait_for_timeout(150)

        # === Scenario 6: Paid (dynamic checkbox field) "not set" matches
        # only doc 3 -- critically, NOT doc 4, whose Paid is explicitly
        # '0' (unchecked), which is real saved data, not "unset" ===
        await page.select_option('#dyn-filter-field-2', FILTER_UNSET)
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2', '3'], f"Paid 'not set' should show docs 2 and 3 (not doc 4, whose Paid=0 is real data), got {ids}"
        print("Paid 'not set' filter shows docs 2 and 3, correctly excluding doc 4's explicit '0':", ids)
        await page.select_option('#dyn-filter-field-2', '')
        await page.wait_for_timeout(150)

        # === Scenario 7: a Smart Collection saved with a "not set" filter
        # active reproduces the same filtering on its own saved criteria --
        # proving the shared matchesCriteria() path works for saved
        # criteria, not just the live toolbar select ===
        await page.select_option('#category-filter', FILTER_UNSET)
        await page.wait_for_timeout(150)
        await page.click('#save-smart-collection-btn')
        await page.wait_for_timeout(150)
        await page.fill('#smart-collection-name-input', 'No Category')
        await page.click('#smart-collection-name-save-btn')
        await page.wait_for_timeout(200)
        await page.select_option('#category-filter', '')
        await page.wait_for_timeout(150)

        smart_collection_nav = page.locator('.nav-item[data-view^="collection-"]', has_text='No Category')
        await smart_collection_nav.click()
        await page.wait_for_timeout(150)
        ids = await visible_ids(page)
        assert ids == ['2'], f"'No Category' Smart Collection should show only doc 2, got {ids}"
        print("Smart Collection saved with a 'not set' filter correctly reproduces the same filtering:", ids)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run the test and confirm it passes**

Run: `cd tests && python3 test_not_set_filter.py`
Expected: all print lines show the expected values with no `AssertionError`,
`JS ERRORS: []`, exit code 0, no `Traceback`.

- [ ] **Step 3: Run the full suite to confirm the new file integrates cleanly**

Run:

```bash
cd tests && python3 -c "
import subprocess, glob
failed = []
files = sorted(glob.glob('test_*.py'))
for f in files:
    p = subprocess.run(['python3', f], capture_output=True, text=True, timeout=180)
    if p.returncode != 0 or 'Traceback' in p.stdout or 'Traceback' in p.stderr:
        failed.append(f)
        print(f'FAILED: {f}')
print(f'TOTAL: {len(files)}  FAILED: {failed}')
"
```

Expected: `TOTAL: 59  FAILED: []` (58 existing scripts plus this one new
file).

- [ ] **Step 4: Update `CLAUDE.md`'s script count and "How this was tested" section**

Edit `CLAUDE.md`, replacing:

```markdown
tests/                   Playwright regression suite (58 scripts) + shared
```

with:

```markdown
tests/                   Playwright regression suite (59 scripts) + shared
```

Then find the sentence in `CLAUDE.md`'s "How this was tested" section
stating the script count and Playwright-driven/static-check split (search
for `58 scripts covering most of the app's actual functionality`), and
update it to `59 scripts`, `58 of them Playwright-driven`. Add one short
sentence describing `test_not_set_filter.py`'s coverage (the option
appears in every dropdown; each field type's "not set" filter narrows to
exactly the expected documents; the checkbox-`'0'`-is-not-unset
distinction; and the Smart Collection round-trip) to the same paragraph,
matching its existing style of naming each test file and summarizing what
it covers — this list is explicitly called out in that same section as
something that must stay current in the same change that adds a test, not
a separate follow-up.

- [ ] **Step 5: Commit**

```bash
git add tests/test_not_set_filter.py CLAUDE.md
git commit -m "$(cat <<'EOF'
Add regression coverage for the "not set" filter option

Confirms the option appears in every filter dropdown (built-in and
dynamic), each field type's "not set" filter narrows to exactly the
right documents, a checkbox field explicitly saved as unchecked
('0') is correctly excluded (real data, not "unset"), and a Smart
Collection saved with a "not set" filter active reproduces the same
filtering from its own saved criteria.
EOF
)"
```
