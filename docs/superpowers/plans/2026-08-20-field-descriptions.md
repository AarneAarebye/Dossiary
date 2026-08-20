# Field Descriptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any field — the five built-ins with no `fields`-table row
(Category, Subcategory, Document Type, Date, Tags) and every generic
custom field (Payment method, Amount, Currency, People, Organization,
Organization To, and any other) — carry an optional short description,
editable from a new Field Settings section and shown as a static hint
line under the field's label in the capture/edit forms.

**Architecture:** One new flat key-value table, `field_descriptions
(field_name TEXT PRIMARY KEY, description TEXT)`, loaded once per library
open into an in-memory map and read directly by the existing
form-rendering functions. No rename capability, no per-type scoping —
purely additive.

**Tech Stack:** Vanilla JS, single-file `dossiary.html`, sql.js, no build
step. Tests: standalone Playwright scripts under `tests/`, driven against
`tests/stub_studio2.js`'s fake File System Access API / SQLite.

## Global Constraints

- Single-file app — all changes go in `dossiary.html`, no new files except
  the test file.
- `db.exec(sql)` for parameter-free reads, `db.run(sql, params)` with `?`
  placeholders for writes — no new query patterns.
- Description text is free-form, user-authored content — like field
  names, it must **never** be run through `t()`. Only the new Field
  Settings section's own static chrome (heading text) is translated.
- Every new user-facing chrome string needs a translation in all six
  `STRINGS` blocks: `en`, `de`, `es`, `fr`, `zh-Hans`, `zh-Hant` —
  enforced by `tests/test_i18n_coverage.py`, which must pass unmodified
  once keys are added.
- Every new test file must load `tests/stub_studio2.js` — never an
  embedded/duplicated stub.
- Reference spec: `docs/superpowers/specs/2026-08-20-field-descriptions-design.md`.

---

### Task 1: Data model and Field Settings editing UI

**Files:**
- Modify: `dossiary.html` — `SCHEMA` (~line 1923), the module-level
  `let` declarations near `fieldDefs` (~line 2068), `loadDocumentsFromDb()`
  (~line 2698-2738), `openFieldSettingsModal()` (~line 4981-5032).
- Create: `tests/test_field_descriptions.py`

**Interfaces:**
- Consumes: nothing from later tasks.
- Produces: `fieldDescriptions` — a module-level `let fieldDescriptions =
  {}` map, `field_name -> description` (string, possibly empty).
  `loadFieldDescriptions()` — populates it from the DB, called from
  `loadDocumentsFromDb()`. `saveFieldDescription(fieldName, description)`
  — persists one entry (`INSERT OR REPLACE`) and updates the in-memory
  map. Task 2 reads `fieldDescriptions[fieldName]` directly wherever it
  renders a hint — it does not call either function itself.

- [ ] **Step 1: Add the new table to `SCHEMA`**

In `dossiary.html`, find `SCHEMA` (~line 1923-1962), ending with:

```js
    CREATE TABLE IF NOT EXISTS collection_documents (
      collection_id INTEGER, document_id INTEGER, PRIMARY KEY (collection_id, document_id)
    );
  `;
```

Add a new table directly above the closing backtick:

```js
    CREATE TABLE IF NOT EXISTS collection_documents (
      collection_id INTEGER, document_id INTEGER, PRIMARY KEY (collection_id, document_id)
    );
    CREATE TABLE IF NOT EXISTS field_descriptions (
      field_name TEXT PRIMARY KEY, description TEXT
    );
  `;
```

No `SCHEMA_MIGRATIONS` entry is needed — `CREATE TABLE IF NOT EXISTS`
already creates this table for an existing library that's missing it,
the same way it already does for every other table in `SCHEMA`.

- [ ] **Step 2: Add the module-level state and load/save functions**

In `dossiary.html`, find (~line 2068-2074):

```js
  let fieldDefs = [];       // [{id, name, type}, ...] from the `fields` table -- type is one of
                            // 'text' | 'number' | 'date' | 'checkbox'
  let fieldNameToId = {};   // name -> id, built from fieldDefs
  let nextFieldId = 1;
  let fieldValuesByDocId = {}; // { docId: { fieldName: valueString, ... } }
  let defaultDocumentType = null; // prefills Document Type when opening "Add document"
  let defaultCurrency = null;     // prefills Currency (as a dismissible guess) on new captures; unset means no guess
```

Add one line after `nextFieldId`:

```js
  let fieldDefs = [];       // [{id, name, type}, ...] from the `fields` table -- type is one of
                            // 'text' | 'number' | 'date' | 'checkbox'
  let fieldNameToId = {};   // name -> id, built from fieldDefs
  let nextFieldId = 1;
  let fieldDescriptions = {}; // field_name -> description (string, possibly empty) -- covers both
                               // the five built-ins with no `fields` row (Category, Subcategory,
                               // Document Type, Date, Tags) and every fieldDefs entry, keyed by
                               // name rather than id so one mechanism covers both kinds of field.
  let fieldValuesByDocId = {}; // { docId: { fieldName: valueString, ... } }
  let defaultDocumentType = null; // prefills Document Type when opening "Add document"
  let defaultCurrency = null;     // prefills Currency (as a dismissible guess) on new captures; unset means no guess
```

Then, directly below `loadFieldDefs()` (~line 2957-2969):

```js
  function loadFieldDefs(){
    const { rows } = queryAll('SELECT id, name, type, show_as_column, autocomplete FROM fields');
    fieldDefs = rows.map(([id, name, type, showAsColumn, autocomplete]) => ({
      id, name, type, showAsColumn: !!showAsColumn, autocomplete: !!autocomplete,
    }));
    fieldNameToId = {};
    let maxFieldId = 0;
    for(const f of fieldDefs){
      fieldNameToId[f.name] = f.id;
      maxFieldId = Math.max(maxFieldId, f.id);
    }
    nextFieldId = maxFieldId + 1;
  }
```

add:

```js
  function loadFieldDescriptions(){
    const { rows } = queryAll('SELECT field_name, description FROM field_descriptions');
    fieldDescriptions = {};
    for(const [fieldName, description] of rows){
      fieldDescriptions[fieldName] = description || '';
    }
  }

  function saveFieldDescription(fieldName, description){
    db.run('INSERT OR REPLACE INTO field_descriptions (field_name, description) VALUES (?, ?)', [fieldName, description]);
    fieldDescriptions[fieldName] = description;
  }
```

- [ ] **Step 3: Call `loadFieldDescriptions()` from `loadDocumentsFromDb()`**

In `dossiary.html`, find (~line 2736-2738):

```js
    loadFieldDefs();
    loadCollections();
    loadFieldValues();
```

Change to:

```js
    loadFieldDefs();
    loadFieldDescriptions();
    loadCollections();
    loadFieldValues();
```

- [ ] **Step 4: Add the "Field Descriptions" section to Field Settings**

In `dossiary.html`, find `openFieldSettingsModal()` (~line 4981-5032):

```js
          <div class="fs-columns">
            <div class="fs-col">
              <h3>${t('fieldSettingsColDocTypes')}</h3>
              <div class="fs-list" id="fs-type-list"></div>
            </div>
            <div class="fs-col">
              <h3>${t('fieldSettingsColFields')}</h3>
              <div class="fs-list" id="fs-available-list"></div>
            </div>
            <div class="fs-col">
              <h3>${t('fieldSettingsColDisplayFields')}</h3>
              <div class="fs-list" id="fs-display-list"></div>
            </div>
          </div>
          <div class="modal-actions" style="margin-top:16px;">
            <button id="fs-done-btn">${t('commonDone')}</button>
          </div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('fs-done-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
    el('fs-default-type').addEventListener('change', (e) => saveDefaultDocumentType(e.target.value));
    el('fs-default-currency').addEventListener('change', (e) => saveDefaultCurrency(e.target.value));

    renderFieldSettingsTypeList();
    renderFieldSettingsFieldColumns();
  }
```

Change to (new section between `.fs-columns` and `.modal-actions`, plus
the new render call at the bottom):

```js
          <div class="fs-columns">
            <div class="fs-col">
              <h3>${t('fieldSettingsColDocTypes')}</h3>
              <div class="fs-list" id="fs-type-list"></div>
            </div>
            <div class="fs-col">
              <h3>${t('fieldSettingsColFields')}</h3>
              <div class="fs-list" id="fs-available-list"></div>
            </div>
            <div class="fs-col">
              <h3>${t('fieldSettingsColDisplayFields')}</h3>
              <div class="fs-list" id="fs-display-list"></div>
            </div>
          </div>
          <div class="fs-descriptions" style="margin-top:16px;">
            <h3>${t('fieldSettingsDescriptionsHeading')}</h3>
            <div class="fs-list" id="fs-descriptions-list"></div>
          </div>
          <div class="modal-actions" style="margin-top:16px;">
            <button id="fs-done-btn">${t('commonDone')}</button>
          </div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('fs-done-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
    el('fs-default-type').addEventListener('change', (e) => saveDefaultDocumentType(e.target.value));
    el('fs-default-currency').addEventListener('change', (e) => saveDefaultCurrency(e.target.value));

    renderFieldSettingsTypeList();
    renderFieldSettingsFieldColumns();
    renderFieldDescriptionsList();
  }
```

- [ ] **Step 5: Add `renderFieldDescriptionsList()`**

Directly below `openFieldSettingsModal()`'s closing brace (right before
`renderFieldSettingsTypeList()`, ~line 5033), add a new function. The
five built-ins are listed first, in this fixed order, followed by every
`fieldDefs` entry in its existing order — this list is **not**
re-rendered when `fsSelectedType` changes (unlike
`renderFieldSettingsFieldColumns()`), since a description belongs to the
field itself, not to any one document type:

```js
  const FIELD_DESCRIPTION_BUILTIN_NAMES = ['Category', 'Subcategory', 'Document Type', 'Date', 'Tags'];

  function renderFieldDescriptionsList(){
    const listEl = el('fs-descriptions-list');
    const names = [...FIELD_DESCRIPTION_BUILTIN_NAMES, ...fieldDefs.map(f => f.name)];
    listEl.innerHTML = names.map(name => `
      <div class="fs-list-item fs-description-item" data-field-name="${escapeHtml(name)}">
        <div class="fs-field-row">
          <span>${escapeHtml(name)}</span>
        </div>
        <input type="text" class="fs-description-input" value="${escapeHtml(fieldDescriptions[name] || '')}" placeholder="${t('fieldSettingsDescriptionPlaceholder')}" />
      </div>
    `).join('');
    listEl.querySelectorAll('.fs-description-item').forEach(itemEl => {
      const fieldName = itemEl.dataset.fieldName;
      const input = itemEl.querySelector('.fs-description-input');
      const commit = async () => {
        saveFieldDescription(fieldName, input.value.trim());
        await persistDb();
      };
      input.addEventListener('keydown', (e) => { if(e.key === 'Enter') input.blur(); });
      input.addEventListener('blur', commit);
    });
  }
```

Unlike the Collections rename input (which resets back to the unchanged
name on an empty commit), an empty description is a valid, meaningful
value here — it just means "no hint," so no revert-on-empty guard is
needed; `commit()` always saves whatever's in the input, including `''`.

- [ ] **Step 6: Add the two new i18n keys to all six `STRINGS` blocks**

In `dossiary.html`, each language block has a line containing
`fieldSettingsColDisplayFields: '...'`. Add the two new keys directly
after that line (English ~843, Spanish ~1003, French ~1163, German
~1323, Chinese Simplified ~1483 — packed onto their own line matching
the surrounding style; Chinese Traditional ~1750 uses one-key-per-line
formatting matching its own existing style).

English (~line 843):
```js
      fieldSettingsColDocTypes: 'Document Types', fieldSettingsColFields: 'Fields', fieldSettingsColDisplayFields: 'Display Fields',
      fieldSettingsDescriptionsHeading: 'Field Descriptions', fieldSettingsDescriptionPlaceholder: 'No description set',
```

Spanish (~line 1003):
```js
      fieldSettingsColDocTypes: 'Tipos de documento', fieldSettingsColFields: 'Campos', fieldSettingsColDisplayFields: 'Campos mostrados',
      fieldSettingsDescriptionsHeading: 'Descripciones de campos', fieldSettingsDescriptionPlaceholder: 'Sin descripción',
```

French (~line 1163):
```js
      fieldSettingsColDocTypes: 'Types de document', fieldSettingsColFields: 'Champs', fieldSettingsColDisplayFields: 'Champs affichés',
      fieldSettingsDescriptionsHeading: 'Descriptions des champs', fieldSettingsDescriptionPlaceholder: 'Aucune description',
```

German (~line 1323):
```js
      fieldSettingsColDocTypes: 'Dokumenttypen', fieldSettingsColFields: 'Felder', fieldSettingsColDisplayFields: 'Anzeigefelder',
      fieldSettingsDescriptionsHeading: 'Feldbeschreibungen', fieldSettingsDescriptionPlaceholder: 'Keine Beschreibung',
```

Chinese Simplified (~line 1483):
```js
      fieldSettingsColDocTypes: '文档类型', fieldSettingsColFields: '字段', fieldSettingsColDisplayFields: '显示字段',
      fieldSettingsDescriptionsHeading: '字段说明', fieldSettingsDescriptionPlaceholder: '未设置说明',
```

Chinese Traditional (~line 1750, one key per line matching this block's
existing style):
```js
      fieldSettingsColDisplayFields: '顯示字段',
      fieldSettingsDescriptionsHeading: '字段說明',
      fieldSettingsDescriptionPlaceholder: '未設置說明',
```

- [ ] **Step 7: Run the i18n coverage check**

Run: `cd tests && /usr/local/bin/python3 test_i18n_coverage.py`
Expected: passes with all six languages reporting exact key parity.

- [ ] **Step 8: Manual verification**

Serve the repo and open `dossiary.html` against a library with at least
one custom field. Open Field Settings, confirm the new "Field
Descriptions" section lists Category/Subcategory/Document Type/Date/Tags
followed by every custom field, type a description into one, click
elsewhere (blur), reopen Field Settings and confirm it's still there.

- [ ] **Step 9: Write the test file**

Create `tests/test_field_descriptions.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc 1", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Organization", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 2, "name": "Organization To", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 3, "name": "Paid", "type": "checkbox", "show_as_column": 0, "autocomplete": 0},
        {"id": 4, "name": "Year", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 5, "name": "Date From", "type": "date", "show_as_column": 0, "autocomplete": 0},
        {"id": 6, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_type_fields": [
        {"document_type": "Receipt", "field_name": "Organization", "position": 0},
        {"document_type": "Receipt", "field_name": "Organization To", "position": 1},
        {"document_type": "Receipt", "field_name": "Paid", "position": 2},
        {"document_type": "Receipt", "field_name": "Year", "position": 3},
        {"document_type": "Receipt", "field_name": "Date From", "position": 4},
        {"document_type": "Receipt", "field_name": "Author", "position": 5},
    ],
}

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

async def read_db(page):
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

        # === Scenario 1: field_descriptions table exists and starts empty ===
        persisted = await read_db(page)
        assert 'field_descriptions' in persisted, "field_descriptions table should exist after opening a library"
        print("field_descriptions table exists:", 'field_descriptions' in persisted)

        # === Scenario 2: Field Settings lists the five built-ins first, in order,
        # then every custom field (Organization, Organization To) ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        names = await page.evaluate(
            "() => Array.from(document.querySelectorAll('#fs-descriptions-list .fs-description-item')).map(el => el.dataset.fieldName)"
        )
        assert names == ['Category', 'Subcategory', 'Document Type', 'Date', 'Tags', 'Organization', 'Organization To', 'Paid', 'Year', 'Date From', 'Author'], \
            f"unexpected field order, got {names}"
        print("Field Descriptions lists built-ins then custom fields, in order:", names)

        # === Scenario 3: typing a description and blurring persists it ===
        org_input = page.locator('.fs-description-item[data-field-name="Organization"] .fs-description-input')
        await org_input.fill('Sender or origin of this document -- can be a person or organization')
        await page.locator('.fs-description-item[data-field-name="Organization To"] .fs-description-input').click()
        await page.wait_for_timeout(150)

        persisted2 = await read_db(page)
        saved = next((r for r in persisted2['field_descriptions'] if r['field_name'] == 'Organization'), None)
        assert saved is not None and saved['description'] == 'Sender or origin of this document -- can be a person or organization', \
            f"description not persisted correctly, got {saved}"
        print("Description persisted via blur:", saved)

        # === Scenario 4: reopening Field Settings shows the saved value ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        reopened_value = await page.locator('.fs-description-item[data-field-name="Organization"] .fs-description-input').input_value()
        assert reopened_value == 'Sender or origin of this document -- can be a person or organization', \
            f"reopened value mismatch, got {reopened_value!r}"
        print("Reopening Field Settings shows the saved description:", reopened_value)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 10: Run the test**

Run: `cd tests && /usr/local/bin/python3 test_field_descriptions.py`
Expected: every `assert` passes, `JS ERRORS: []`, script exits 0.

- [ ] **Step 11: Commit**

```bash
git add dossiary.html tests/test_field_descriptions.py
git commit -m "Add field_descriptions table and Field Settings editing UI"
```

---

### Task 2: Show descriptions in the capture and edit forms

**Files:**
- Modify: `dossiary.html` — `renderGenericFieldHtml()` (~line 3299-3341),
  `renderPersonFieldHtml()` (~line 3257-3270), the capture form's
  template (~lines 5266-5321), the edit form's template (~lines
  4683-4734).
- Modify: `tests/test_field_descriptions.py` (append new scenarios to
  the file Task 1 created).

**Interfaces:**
- Consumes: Task 1's `fieldDescriptions` map (already loaded by the time
  any form renders) and `SEED`/helper functions in
  `tests/test_field_descriptions.py`.
- Produces: nothing further consumed by any later task — this is the
  last task in the plan.

- [ ] **Step 1: Add the hint to `renderGenericFieldHtml()`'s checkbox branch**

In `dossiary.html`, find `renderGenericFieldHtml()`'s checkbox branch
(~line 3303-3311):

```js
    if(field.type === 'checkbox'){
      const checked = existingValue === '1' ? 'checked' : '';
      return `
        <div class="field${orphanedClass}" data-dynamic-field="${escapeHtml(field.name)}" data-field-id="${field.id}">
          <label class="checkbox-label" for="${inputId}"><input type="checkbox" id="${inputId}" ${checked} /> ${escapeHtml(field.name)}</label>
          ${orphanedHint}
        </div>
      `;
    }
```

Change to:

```js
    if(field.type === 'checkbox'){
      const checked = existingValue === '1' ? 'checked' : '';
      const description = fieldDescriptions[field.name];
      const descriptionHint = description ? `<div class="field-hint">${escapeHtml(description)}</div>` : '';
      return `
        <div class="field${orphanedClass}" data-dynamic-field="${escapeHtml(field.name)}" data-field-id="${field.id}">
          <label class="checkbox-label" for="${inputId}"><input type="checkbox" id="${inputId}" ${checked} /> ${escapeHtml(field.name)}</label>
          ${descriptionHint}
          ${orphanedHint}
        </div>
      `;
    }
```

- [ ] **Step 2: Add the hint to `renderGenericFieldHtml()`'s text/number/date branch**

In `dossiary.html`, find the rest of `renderGenericFieldHtml()` (~line
3312-3341):

```js
    let inputType = 'text', extra = '';
    if(field.type === 'number'){ inputType = 'number'; extra = 'step="any"'; }
    else if(field.type === 'date'){ inputType = 'date'; }

    const isCurrency = field.name === 'Currency';
    const isCurrencyGuess = isCurrency && !existingValue && !!defaultCurrency
      && (prefix === 'f' || (prefix === 'e' && amountFilled));
    let value = field.type === 'date' ? (existingValue ? existingValue.slice(0, 10) : '') : (existingValue || '');
    if(isCurrencyGuess) value = defaultCurrency;

    let listAttr = '';
    if(isCurrency) listAttr = 'list="currency-list"';
    else if(field.autocomplete && field.type === 'text') listAttr = `list="field-${field.id}-list"`;

    const guessHint = isCurrencyGuess
      ? `<div class="field-guess-hint" id="${inputId}-hint">${t('fieldCurrencyGuessHint', {currency: escapeHtml(defaultCurrency)})}</div>`
      : '';

    return `
      <div class="field${orphanedClass}" data-dynamic-field="${escapeHtml(field.name)}" data-field-id="${field.id}">
        <label for="${inputId}">${escapeHtml(field.name)}</label>
        <div class="field-with-clear">
          <input type="${inputType}" id="${inputId}" ${extra} ${listAttr} class="${isCurrencyGuess ? 'field-guess' : ''}" value="${escapeHtml(String(value))}" />
          <button type="button" class="clear-btn" id="${inputId}-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: escapeHtml(field.name)})}">✕</button>
        </div>
        ${guessHint}
        ${orphanedHint}
      </div>
    `;
  }
```

Change to add the `description`/`descriptionHint` computation and
interpolate it into the returned template (placed after `guessHint`, so
a Currency field showing both its guess hint and a user-set description
shows the guess first, description second):

```js
    let inputType = 'text', extra = '';
    if(field.type === 'number'){ inputType = 'number'; extra = 'step="any"'; }
    else if(field.type === 'date'){ inputType = 'date'; }

    const isCurrency = field.name === 'Currency';
    const isCurrencyGuess = isCurrency && !existingValue && !!defaultCurrency
      && (prefix === 'f' || (prefix === 'e' && amountFilled));
    let value = field.type === 'date' ? (existingValue ? existingValue.slice(0, 10) : '') : (existingValue || '');
    if(isCurrencyGuess) value = defaultCurrency;

    let listAttr = '';
    if(isCurrency) listAttr = 'list="currency-list"';
    else if(field.autocomplete && field.type === 'text') listAttr = `list="field-${field.id}-list"`;

    const guessHint = isCurrencyGuess
      ? `<div class="field-guess-hint" id="${inputId}-hint">${t('fieldCurrencyGuessHint', {currency: escapeHtml(defaultCurrency)})}</div>`
      : '';
    const description = fieldDescriptions[field.name];
    const descriptionHint = description ? `<div class="field-hint">${escapeHtml(description)}</div>` : '';

    return `
      <div class="field${orphanedClass}" data-dynamic-field="${escapeHtml(field.name)}" data-field-id="${field.id}">
        <label for="${inputId}">${escapeHtml(field.name)}</label>
        <div class="field-with-clear">
          <input type="${inputType}" id="${inputId}" ${extra} ${listAttr} class="${isCurrencyGuess ? 'field-guess' : ''}" value="${escapeHtml(String(value))}" />
          <button type="button" class="clear-btn" id="${inputId}-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: escapeHtml(field.name)})}">✕</button>
        </div>
        ${guessHint}
        ${descriptionHint}
        ${orphanedHint}
      </div>
    `;
  }
```

- [ ] **Step 3: Add the hint to `renderPersonFieldHtml()`**

In `dossiary.html`, find `renderPersonFieldHtml()` (~line 3257-3270):

```js
  function renderPersonFieldHtml(prefix, field, existingPeople, orphaned){
    const value = (existingPeople || []).join(', ');
    const inputId = `${prefix}-field-${field.id}`;
    return `
      <div class="field${orphaned ? ' field-orphaned' : ''}" data-dynamic-field="${escapeHtml(field.name)}" data-field-id="${field.id}">
        <label for="${inputId}">${t('fieldPersonLabelSuffix', {name: escapeHtml(field.name)})}</label>
        <div class="field-with-clear">
          <input type="text" id="${inputId}" list="person-list" value="${escapeHtml(value)}" placeholder="${t('fieldPersonPlaceholder')}" />
          <button type="button" class="clear-btn" id="${inputId}-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: escapeHtml(field.name)})}">✕</button>
        </div>
        ${orphaned ? `<div class="field-orphaned-hint">${t('fieldOrphanedHint')}</div>` : ''}
      </div>
    `;
  }
```

Change to:

```js
  function renderPersonFieldHtml(prefix, field, existingPeople, orphaned){
    const value = (existingPeople || []).join(', ');
    const inputId = `${prefix}-field-${field.id}`;
    const description = fieldDescriptions[field.name];
    const descriptionHint = description ? `<div class="field-hint">${escapeHtml(description)}</div>` : '';
    return `
      <div class="field${orphaned ? ' field-orphaned' : ''}" data-dynamic-field="${escapeHtml(field.name)}" data-field-id="${field.id}">
        <label for="${inputId}">${t('fieldPersonLabelSuffix', {name: escapeHtml(field.name)})}</label>
        <div class="field-with-clear">
          <input type="text" id="${inputId}" list="person-list" value="${escapeHtml(value)}" placeholder="${t('fieldPersonPlaceholder')}" />
          <button type="button" class="clear-btn" id="${inputId}-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: escapeHtml(field.name)})}">✕</button>
        </div>
        ${descriptionHint}
        ${orphaned ? `<div class="field-orphaned-hint">${t('fieldOrphanedHint')}</div>` : ''}
      </div>
    `;
  }
```

- [ ] **Step 4: Add hints for the five built-ins in the capture form**

In `dossiary.html`, inside the capture form's template, find each of
these five blocks and change them as shown. Document Type is the one
built-in that already has its own permanent `.field-hint` line
(`captureDocTypeHint`) — its new description hint is a **second**,
separate `.field-hint` div added after the existing one, not a
replacement.

Document Type (~line 5266-5273), find:
```js
          <div class="field field-prominent">
            <label for="f-type">${t('captureDocTypeLabel')}</label>
            <div class="field-with-clear">
              <input type="text" id="f-type" list="type-list" value="${escapeHtml(defaultDocumentType || '')}" placeholder="${t('captureDocTypePlaceholder')}" />
              <button type="button" class="clear-btn" id="f-type-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('captureDocTypeLabel')})}">✕</button>
            </div>
            <div class="field-hint">${t('captureDocTypeHint')}</div>
          </div>
```
change to:
```js
          <div class="field field-prominent">
            <label for="f-type">${t('captureDocTypeLabel')}</label>
            <div class="field-with-clear">
              <input type="text" id="f-type" list="type-list" value="${escapeHtml(defaultDocumentType || '')}" placeholder="${t('captureDocTypePlaceholder')}" />
              <button type="button" class="clear-btn" id="f-type-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('captureDocTypeLabel')})}">✕</button>
            </div>
            <div class="field-hint">${t('captureDocTypeHint')}</div>
            ${fieldDescriptions['Document Type'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Document Type'])}</div>` : ''}
          </div>
```

Date (~line 5276-5281), find:
```js
            <div class="field">
              <label for="f-date">${t('captureDateLabel')}</label>
              <input type="date" id="f-date" class="field-guess" value="${todayIsoDate()}" />
              <div class="field-guess-hint" id="f-date-hint">${t('captureDateGuessHint')}</div>
            </div>
```
change to:
```js
            <div class="field">
              <label for="f-date">${t('captureDateLabel')}</label>
              <input type="date" id="f-date" class="field-guess" value="${todayIsoDate()}" />
              <div class="field-guess-hint" id="f-date-hint">${t('captureDateGuessHint')}</div>
              ${fieldDescriptions['Date'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Date'])}</div>` : ''}
            </div>
```

Category (~line 5283-5290), find:
```js
            <div class="field">
              <label for="f-category">${t('captureCategoryLabel')}</label>
              <div class="field-with-clear">
                <input type="text" id="f-category" list="category-list" />
                <button type="button" class="clear-btn" id="f-category-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('captureCategoryLabel')})}">✕</button>
              </div>
            </div>
```
change to:
```js
            <div class="field">
              <label for="f-category">${t('captureCategoryLabel')}</label>
              <div class="field-with-clear">
                <input type="text" id="f-category" list="category-list" />
                <button type="button" class="clear-btn" id="f-category-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('captureCategoryLabel')})}">✕</button>
              </div>
              ${fieldDescriptions['Category'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Category'])}</div>` : ''}
            </div>
```

Subcategory (~line 5291-5298), find:
```js
            <div class="field">
              <label for="f-subcategory">${t('captureSubcategoryLabel')}</label>
              <div class="field-with-clear">
                <input type="text" id="f-subcategory" list="subcategory-list" placeholder="${t('captureSubcategoryPlaceholder')}" />
                <button type="button" class="clear-btn" id="f-subcategory-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('captureSubcategoryLabel')})}">✕</button>
              </div>
            </div>
```
change to:
```js
            <div class="field">
              <label for="f-subcategory">${t('captureSubcategoryLabel')}</label>
              <div class="field-with-clear">
                <input type="text" id="f-subcategory" list="subcategory-list" placeholder="${t('captureSubcategoryPlaceholder')}" />
                <button type="button" class="clear-btn" id="f-subcategory-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('captureSubcategoryLabel')})}">✕</button>
              </div>
              ${fieldDescriptions['Subcategory'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Subcategory'])}</div>` : ''}
            </div>
```

Tags (~line 5316-5321), find:
```js
          <div class="field">
            <label for="f-tags">${t('captureTagsLabel')}</label>
            <div class="field-with-clear">
              <input type="text" id="f-tags" list="tag-list" placeholder="${t('captureTagsPlaceholder')}" />
              <button type="button" class="clear-btn" id="f-tags-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('tableColTags')})}">✕</button>
            </div>
          </div>
```
change to:
```js
          <div class="field">
            <label for="f-tags">${t('captureTagsLabel')}</label>
            <div class="field-with-clear">
              <input type="text" id="f-tags" list="tag-list" placeholder="${t('captureTagsPlaceholder')}" />
              <button type="button" class="clear-btn" id="f-tags-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('tableColTags')})}">✕</button>
            </div>
            ${fieldDescriptions['Tags'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Tags'])}</div>` : ''}
          </div>
```

- [ ] **Step 5: Add hints for the five built-ins in the edit form**

Same five fields, same logic, in the edit form's template.

Document Type (~line 4683-4690), find:
```js
          <div class="field field-prominent">
            <label for="e-type">${t('editDocTypeLabel')}</label>
            <div class="field-with-clear">
              <input type="text" id="e-type" list="type-list" value="${escapeHtml(d.document_type || '')}" placeholder="${t('editDocTypePlaceholder')}" />
              <button type="button" class="clear-btn" id="e-type-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('editDocTypeLabel')})}">✕</button>
            </div>
            <div class="field-hint">${t('editDocTypeHint')}</div>
          </div>
```
change to:
```js
          <div class="field field-prominent">
            <label for="e-type">${t('editDocTypeLabel')}</label>
            <div class="field-with-clear">
              <input type="text" id="e-type" list="type-list" value="${escapeHtml(d.document_type || '')}" placeholder="${t('editDocTypePlaceholder')}" />
              <button type="button" class="clear-btn" id="e-type-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('editDocTypeLabel')})}">✕</button>
            </div>
            <div class="field-hint">${t('editDocTypeHint')}</div>
            ${fieldDescriptions['Document Type'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Document Type'])}</div>` : ''}
          </div>
```

Date (~line 4692-4695), find:
```js
          <div class="field-row">
            <div class="field"><label for="e-title">${t('editTitleLabel')}</label><input type="text" id="e-title" value="${escapeHtml(d.title || '')}" /></div>
            <div class="field"><label for="e-date">${t('editDateLabel')}</label><input type="date" id="e-date" value="${escapeHtml((d.date || '').slice(0, 10))}" /></div>
          </div>
```
change to:
```js
          <div class="field-row">
            <div class="field"><label for="e-title">${t('editTitleLabel')}</label><input type="text" id="e-title" value="${escapeHtml(d.title || '')}" /></div>
            <div class="field">
              <label for="e-date">${t('editDateLabel')}</label>
              <input type="date" id="e-date" value="${escapeHtml((d.date || '').slice(0, 10))}" />
              ${fieldDescriptions['Date'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Date'])}</div>` : ''}
            </div>
          </div>
```

Category (~line 4696-4703), find:
```js
            <div class="field">
              <label for="e-category">${t('editCategoryLabel')}</label>
              <div class="field-with-clear">
                <input type="text" id="e-category" list="category-list" value="${escapeHtml(d.category || '')}" />
                <button type="button" class="clear-btn" id="e-category-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('editCategoryLabel')})}">✕</button>
              </div>
            </div>
```
change to:
```js
            <div class="field">
              <label for="e-category">${t('editCategoryLabel')}</label>
              <div class="field-with-clear">
                <input type="text" id="e-category" list="category-list" value="${escapeHtml(d.category || '')}" />
                <button type="button" class="clear-btn" id="e-category-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('editCategoryLabel')})}">✕</button>
              </div>
              ${fieldDescriptions['Category'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Category'])}</div>` : ''}
            </div>
```

Subcategory (~line 4704-4711), find:
```js
            <div class="field">
              <label for="e-subcategory">${t('editSubcategoryLabel')}</label>
              <div class="field-with-clear">
                <input type="text" id="e-subcategory" list="subcategory-list" value="${escapeHtml(d.subcategory || '')}" placeholder="${t('editSubcategoryPlaceholder')}" />
                <button type="button" class="clear-btn" id="e-subcategory-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('editSubcategoryLabel')})}">✕</button>
              </div>
            </div>
```
change to:
```js
            <div class="field">
              <label for="e-subcategory">${t('editSubcategoryLabel')}</label>
              <div class="field-with-clear">
                <input type="text" id="e-subcategory" list="subcategory-list" value="${escapeHtml(d.subcategory || '')}" placeholder="${t('editSubcategoryPlaceholder')}" />
                <button type="button" class="clear-btn" id="e-subcategory-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('editSubcategoryLabel')})}">✕</button>
              </div>
              ${fieldDescriptions['Subcategory'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Subcategory'])}</div>` : ''}
            </div>
```

Tags (~line 4729-4734), find:
```js
          <div class="field">
            <label for="e-tags">${t('captureTagsLabel')}</label>
            <div class="field-with-clear">
              <input type="text" id="e-tags" list="tag-list" value="${escapeHtml((d.tags||[]).join(', '))}" placeholder="${t('captureTagsPlaceholder')}" />
              <button type="button" class="clear-btn" id="e-tags-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('tableColTags')})}">✕</button>
            </div>
          </div>
```
change to:
```js
          <div class="field">
            <label for="e-tags">${t('captureTagsLabel')}</label>
            <div class="field-with-clear">
              <input type="text" id="e-tags" list="tag-list" value="${escapeHtml((d.tags||[]).join(', '))}" placeholder="${t('captureTagsPlaceholder')}" />
              <button type="button" class="clear-btn" id="e-tags-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: t('tableColTags')})}">✕</button>
            </div>
            ${fieldDescriptions['Tags'] ? `<div class="field-hint">${escapeHtml(fieldDescriptions['Tags'])}</div>` : ''}
          </div>
```

- [ ] **Step 6: Manual verification**

Set a description for Category and for a custom field (e.g.
Organization) in Field Settings. Open "Add document" and confirm both
hints show under their labels. Save a document, open Edit, confirm the
same two hints show there too. Set a description on Document Type and
confirm you see **two** stacked hint lines under it (the existing
built-in one, then your new one) in both forms.

- [ ] **Step 7: Append the display scenarios to the test file**

Open `tests/test_field_descriptions.py` (created in Task 1). Insert the
following directly before the existing:

```python
        print("JS ERRORS:", errors)
        await browser.close()
```

lines at the end of `main()`, i.e. immediately after Task 1's Scenario 4
block:

```python
        # === Scenario 5: setting a description for a built-in (Category) and a
        # custom field (Organization) shows the hint under each label in the
        # capture form; a field with no description shows no hint at all ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.locator('.fs-description-item[data-field-name="Category"] .fs-description-input').fill('Where this document belongs, e.g. Travel or Medical')
        await page.locator('.fs-description-item[data-field-name="Tags"] .fs-description-input').click()
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        await page.fill('#f-type', 'Receipt')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)

        category_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'f-category\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert category_hints == ['Where this document belongs, e.g. Travel or Medical'], f"Category hint missing or wrong, got {category_hints}"
        print("Category shows its description hint in the capture form:", category_hints)

        org_field = page.locator('[data-dynamic-field="Organization"]')
        org_hints = await org_field.locator('.field-hint').all_text_contents()
        assert org_hints == ['Sender or origin of this document -- can be a person or organization'], f"Organization hint missing or wrong, got {org_hints}"
        print("Organization (custom field) shows its description hint in the capture form:", org_hints)

        subcategory_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'f-subcategory\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert subcategory_hints == [], f"Subcategory should show no hint (no description set), got {subcategory_hints}"
        print("Subcategory shows no hint when no description is set:", subcategory_hints)

        # === Scenario 6: Document Type shows BOTH its existing built-in hint and
        # the new description hint, stacked, when a description is set for it ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.locator('.fs-description-item[data-field-name="Document Type"] .fs-description-input').fill('What kind of document this is')
        await page.locator('.fs-description-item[data-field-name="Date"] .fs-description-input').click()
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        type_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'f-type\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert len(type_hints) == 2, f"Document Type should show two stacked hints (built-in + description), got {type_hints}"
        assert type_hints[1] == 'What kind of document this is', f"second Document Type hint should be the description, got {type_hints}"
        print("Document Type shows both its built-in hint and the new description hint, stacked:", type_hints)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 7: the same hints show correctly in the edit form too ===
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(150)
        await page.click('.row-edit-btn')
        await page.wait_for_timeout(200)
        edit_category_hints = await page.evaluate(
            "() => Array.from(document.querySelector('label[for=\\'e-category\\']').closest('.field').querySelectorAll('.field-hint')).map(el => el.textContent)"
        )
        assert edit_category_hints == ['Where this document belongs, e.g. Travel or Medical'], f"edit-form Category hint missing or wrong, got {edit_category_hints}"
        print("Category shows its description hint in the edit form too:", edit_category_hints)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 8: a generic field of every type (checkbox, number, date,
        # person -- text is already covered by Organization in Scenario 5) shows
        # its description hint correctly, proving renderGenericFieldHtml()'s
        # checkbox branch, its text/number/date branch, and renderPersonFieldHtml()
        # all got the same treatment ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        await page.locator('.fs-description-item[data-field-name="Paid"] .fs-description-input').fill('Whether this was already paid')
        await page.locator('.fs-description-item[data-field-name="Year"] .fs-description-input').fill('The tax year this applies to')
        await page.locator('.fs-description-item[data-field-name="Date From"] .fs-description-input').fill('Start of the period this covers')
        await page.locator('.fs-description-item[data-field-name="Author"] .fs-description-input').fill('Who wrote or created this document')
        await page.locator('.fs-description-item[data-field-name="Category"] .fs-description-input').click()  # blur the last input
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        await page.fill('#f-type', 'Receipt')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)

        for field_name, expected in [
            ('Paid', 'Whether this was already paid'),
            ('Year', 'The tax year this applies to'),
            ('Date From', 'Start of the period this covers'),
            ('Author', 'Who wrote or created this document'),
        ]:
            hints = await page.locator(f'[data-dynamic-field="{field_name}"]').locator('.field-hint').all_text_contents()
            assert hints == [expected], f"{field_name} hint missing or wrong, got {hints}"
            print(f"{field_name} shows its description hint in the capture form:", hints)

        # === Scenario 9: description text is never run through t() -- a
        # description containing a literal "{label}" (which would be silently
        # substituted or replaced if it were passed to t() with a params object,
        # the way translated strings are) renders completely verbatim ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        literal_text = 'Not a real placeholder: {label} stays exactly as typed'
        await page.locator('.fs-description-item[data-field-name="Organization To"] .fs-description-input').fill(literal_text)
        await page.locator('.fs-description-item[data-field-name="Category"] .fs-description-input').click()
        await page.wait_for_timeout(150)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        await page.fill('#f-type', 'Receipt')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        org_to_hints = await page.locator('[data-dynamic-field="Organization To"]').locator('.field-hint').all_text_contents()
        assert org_to_hints == [literal_text], f"literal-braces description was altered, got {org_to_hints}"
        print("Description containing a literal '{label}' renders verbatim, not run through t():", org_to_hints)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)
```

- [ ] **Step 8: Run the full test file**

Run: `cd tests && /usr/local/bin/python3 test_field_descriptions.py`
Expected: every `assert` passes, `JS ERRORS: []`, script exits 0.

- [ ] **Step 9: Run the full existing suite to confirm no regressions**

Run:
```bash
cd tests
for f in test_*.py; do /usr/local/bin/python3 "$f" || echo "FAILED: $f"; done
```
Expected: no `FAILED:` lines.

- [ ] **Step 10: Commit**

```bash
git add dossiary.html tests/test_field_descriptions.py
git commit -m "Show field descriptions as a hint line in capture/edit forms"
```
