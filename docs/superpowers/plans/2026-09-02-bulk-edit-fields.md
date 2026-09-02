# Bulk Edit Fields for Selected Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let someone select 2+ documents via the row checkboxes and set values for one or many fields across all of them in a single save, reached via a new right-click context-menu item and a new bulk-action-bar button.

**Architecture:** A new `openBulkEditForm(ids)` modal, structurally parallel to the existing single-document `openEditForm(id)`, renders every field the single-document form has (minus Title/OCR text) with an explicit per-field opt-in (an "Apply to all" checkbox for replace-semantics fields; an "Add to existing"/"Replace existing" mode toggle for Tags and person-type fields) so nothing is touched on any document unless the person explicitly says so. Fields not common to every selected document's Document Type render via the existing `.field-orphaned` styling, computed once as a union across the selection. `saveBulkEdit(ids)` writes every opted-in field to every selected document with the same SQL primitives `saveEditedDocument()` already uses, batched into one `persistDb()`/`render()` call.

**Tech Stack:** Single-file vanilla JS (`dossiary.html`), sql.js, no build step. Tests: standalone Playwright scripts under `tests/`, driven against `tests/stub_studio2.js`'s fake File System Access/SQLite stubs, run via `python3 tests/test_<name>.py`.

## Global Constraints

- No confirmation dialogs anywhere in this feature (matches every existing bulk action and single-document save in this app).
- Title and the OCR-text box are never part of the bulk-edit form.
- `archived`/`deleted`/`needs_review` are never touched by a bulk edit.
- `selectedDocIds` is **not** cleared after a bulk-edit save (unlike `bulkSetArchived()`/`bulkSetDeleted()`/`bulkSetNeedsReview()`, which do clear it).
- Every DB write for a bulk-edit save is batched into exactly one `persistDb()` and one `render()` call at the end — never per-document.
- New function names, exactly as used throughout this plan: `openBulkEditForm(ids)`, `saveBulkEdit(ids)`, `computeBulkFieldUnion(ids)`, `bulkScalarMixed(ids, getValue)`, `bulkSetMixed(ids, getNames)`, `refreshBulkMixedHints(ids)`, `setBulkMixedHint(hintId, text, variant)`, `showBulkRowContextMenu(x, y)`.
- Every new user-facing string is added to all six `STRINGS` blocks (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`) in `dossiary.html` — `zh-Hant` is derived from the finished `zh-Hans` wording via OpenCC's `s2t` conversion (a local one-time tool run, not a runtime dependency — see `../CLAUDE.md`'s i18n note for the exact convention), never translated independently.
- Every new Playwright test file must load `tests/stub_studio2.js` exactly the way every existing test file does (see `tests/CLAUDE.md`) — never an embedded/duplicated stub.
- Tests in this suite are standalone scripts that `print(...)` boolean/string results for manual review, not a pytest suite with assertions as the primary signal (a handful of `assert` calls for structural sanity are fine, matching `tests/test_field_descriptions.py`'s own pattern) — run via `cd tests && python3 test_bulk_edit.py`.
- Reference documents: the approved design spec at `docs/superpowers/specs/2026-09-02-bulk-edit-fields-design.md` (read it in full before starting) and this repo's `CLAUDE.md`/`tests/CLAUDE.md`.

---

## Task 1: Modal skeleton, scalar replace-semantics fields, and the bulk-action-bar entry point

**Files:**
- Modify: `dossiary.html`
  - `~line 726-739`: `#bulk-action-bar` markup — add a new `#bulk-edit-btn` button.
  - `~line 4756-4780`: `renderBulkActionBar()` — add `#bulk-edit-btn`'s Waste-bin visibility rule.
  - `~line 5643` (just before `function openEditForm(id){`): new `openBulkEditForm(ids)` and `saveBulkEdit(ids)` functions.
  - `~line 7151-7155`: new `#bulk-edit-btn` click handler, alongside the existing `bulk-archive-btn`/`bulk-delete-btn`/etc. handlers.
  - `STRINGS.en`/`STRINGS.es`/`STRINGS.fr`/`STRINGS.de`/`STRINGS['zh-Hans']`/`STRINGS['zh-Hant']` (lines 844, 1011, 1178, 1345, 1512, 1679): new keys `bulkEditModalTitleSingular`, `bulkEditModalTitlePlural`, `bulkEditSavedStatusSingular`, `bulkEditSavedStatusPlural`.
- Test: `tests/test_bulk_edit.py` (new file)

**Interfaces:**
- Consumes: `allDocs`, `db`, `persistDb()`, `render()`, `renderStats()`, `populateFilters()`, `populateDatalists()`, `closeModal()`, `onModalKeydown`, `modalRoot`, `el(id)`, `t(key, params)`, `setStatusT(key, params, kind)`, `escapeHtml(s)`, `selectedDocIds` — all pre-existing.
- Produces: `openBulkEditForm(ids)` (no return value — renders into `modalRoot`), `saveBulkEdit(ids)` (async, returns `true`/`false` on success/failure, mirroring `saveEditedDocument()`). Later tasks extend both functions' bodies in place. DOM ids Task 2/3/4/5 depend on: `#bulk-person-fields` and `#bulk-generic-fields` (empty containers Task 2/3 populate), `#bulk-edit-save-btn`, `#bulk-edit-status`, the `.bulk-apply-checkbox`/`data-bulk-target` convention.

- [ ] **Step 1: Write the test file skeleton and Scenario 1 (entry-point visibility)**

Create `tests/test_bulk_edit.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Four plain documents (1-4, no custom fields yet -- Tasks 2/3 add fixtures with
# custom fields of their own) plus one deleted document (5, reachable only via
# the Waste bin) so Scenario 1 can confirm #bulk-edit-btn is hidden there.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Invoice A", "category": "Finance", "subcategory": "Utilities",
            "document_type": "Invoice", "date": "2026-01-01T00:00:00+00:00", "notes": "Original note",
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Invoice B", "category": "Finance", "subcategory": "Rent",
            "document_type": "Invoice", "date": "2026-01-02T00:00:00+00:00", "notes": None,
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-01-02T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Letter C", "category": None, "subcategory": None,
            "document_type": "Letter", "date": None, "notes": None,
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-03T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 4, "title": "Untouched D", "category": "Legal", "subcategory": None,
            "document_type": "Letter", "date": "2026-01-04T00:00:00+00:00", "notes": None,
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-01-04T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 5, "title": "Deleted E", "category": "Finance", "subcategory": None,
            "document_type": "Invoice", "date": "2026-01-05T00:00:00+00:00", "notes": None,
            "ocr_text": None, "ocr_language": None,
            "file_path": "files/5_e.pdf", "original_file_path": None,
            "created_at": "2026-01-05T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
    ],
    "tags": [], "document_tags": [],
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

async def open_library(page):
    await route_stub(page)
    await page.goto(f"file://{APP_PATH}")
    await page.wait_for_timeout(200)
    await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
    await page.click("#open-btn")
    await page.wait_for_timeout(400)

async def select_rows(page, ids):
    for doc_id in ids:
        await page.check(f'tr[data-id="{doc_id}"] .row-select-checkbox')
    await page.wait_for_timeout(150)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await open_library(page)

        # === Scenario 1: #bulk-edit-btn shows whenever 1+ rows are selected in
        # every view except the Waste bin, matching #bulk-archive-btn's own
        # existing visibility rule ===
        await select_rows(page, [1, 2])
        edit_btn_visible = await page.locator('#bulk-edit-btn:visible').count()
        print("bulk edit button visible with 2 selected in All Documents:", edit_btn_visible == 1)

        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        await select_rows(page, [5])
        edit_btn_hidden_in_trash = await page.locator('#bulk-edit-btn:visible').count()
        print("bulk edit button hidden in Waste bin:", edit_btn_hidden_in_trash == 0)

        await page.click('#bulk-clear-selection-btn')
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        print("JS ERRORS so far:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run the test to verify Scenario 1 fails**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: the script errors out (Playwright throws a timeout/strict-mode error locating `#bulk-edit-btn`, since it doesn't exist yet) rather than printing `True`/`False` lines — confirming the test is actually exercising not-yet-built UI.

- [ ] **Step 3: Add the `#bulk-edit-btn` markup and its visibility rule**

In `dossiary.html`, in the `#bulk-action-bar` markup (currently ending `...<button type="button" id="bulk-restore-btn" style="display:none;" data-i18n="bulkRestore">Restore</button>`), add a new button right before `#bulk-clear-selection-btn`:

```html
        <button type="button" id="bulk-edit-btn" data-i18n="detailEdit">Edit</button>
        <button type="button" id="bulk-clear-selection-btn" data-i18n="bulkClearSelection">Clear selection</button>
```

In `renderBulkActionBar()`, add `#bulk-edit-btn` to the same Waste-bin-hides-it group as Archive/Delete/Flag for review:

```js
    el('bulk-archive-btn').style.display = isTrash ? 'none' : '';
    el('bulk-delete-btn').style.display = isTrash ? 'none' : '';
    el('bulk-review-btn').style.display = isTrash ? 'none' : '';
    el('bulk-edit-btn').style.display = isTrash ? 'none' : '';
    el('bulk-restore-btn').style.display = isTrash ? '' : 'none';
```

Near the existing bulk-button click handlers (`el('bulk-archive-btn').addEventListener(...)` etc.), add:

```js
  el('bulk-edit-btn').addEventListener('click', () => openBulkEditForm([...selectedDocIds]));
```

- [ ] **Step 4: Run the test to verify Scenario 1 passes**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: prints `bulk edit button visible with 2 selected in All Documents: True` and `bulk edit button hidden in Waste bin: True`, with `JS ERRORS so far: []`.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_bulk_edit.py
git commit -m "Add bulk-edit entry point button to the bulk-action bar"
```

- [ ] **Step 6: Write Scenario 2 (modal opens, scalar fields blank, no i18n keys missing)**

Append to `tests/test_bulk_edit.py`, before `print("JS ERRORS so far:", errors)`:

```python
        # === Scenario 2: opening the bulk-edit form shows every scalar
        # replace-semantics field genuinely blank (never pre-filled from any one
        # selected document's own value) with its Apply checkbox unchecked ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        modal_title = await page.locator('.modal h2').inner_text()
        print("modal title mentions the selected count:", "2" in modal_title)
        for field_id, apply_id in [
            ('bulk-type', 'bulk-apply-type'), ('bulk-category', 'bulk-apply-category'),
            ('bulk-subcategory', 'bulk-apply-subcategory'), ('bulk-date', 'bulk-apply-date'),
            ('bulk-notes', 'bulk-apply-notes'),
        ]:
            value = await page.locator(f'#{field_id}').input_value()
            checked = await page.locator(f'#{apply_id}').is_checked()
            disabled = await page.locator(f'#{field_id}').is_disabled()
            print(f"{field_id} starts blank / Apply unchecked / input disabled:", value == '' and not checked and disabled)
        await page.click('#bulk-edit-cancel-btn')
        await page.wait_for_timeout(150)
```

- [ ] **Step 7: Run the test to verify Scenario 2 fails**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: Playwright throws a timeout error clicking `#bulk-edit-btn` or locating `.modal h2` — `openBulkEditForm` doesn't exist yet.

- [ ] **Step 8: Add `openBulkEditForm(ids)`'s skeleton and the four scalar fields**

In `dossiary.html`, immediately before `function openEditForm(id){` (`~line 5644`), add:

```js
  // --- bulk-edit modal (update metadata for 2+ selected documents at once) ---

  function openBulkEditForm(ids){
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal wide" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <h2>${ids.length === 1 ? t('bulkEditModalTitleSingular', {count: ids.length}) : t('bulkEditModalTitlePlural', {count: ids.length})}</h2>

          <div class="field field-prominent bulk-field">
            <label class="checkbox-label bulk-apply-label" for="bulk-apply-type">
              <input type="checkbox" id="bulk-apply-type" class="bulk-apply-checkbox" data-bulk-target="bulk-type" />
              ${t('editDocTypeLabel')}
            </label>
            <input type="text" id="bulk-type" list="type-list" disabled />
            <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-type" style="display:none;"></div>
          </div>

          <div class="field-row">
            <div class="field bulk-field">
              <label class="checkbox-label bulk-apply-label" for="bulk-apply-category">
                <input type="checkbox" id="bulk-apply-category" class="bulk-apply-checkbox" data-bulk-target="bulk-category" />
                ${t('editCategoryLabel')}
              </label>
              <input type="text" id="bulk-category" list="category-list" disabled />
              <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-category" style="display:none;"></div>
            </div>
            <div class="field bulk-field">
              <label class="checkbox-label bulk-apply-label" for="bulk-apply-subcategory">
                <input type="checkbox" id="bulk-apply-subcategory" class="bulk-apply-checkbox" data-bulk-target="bulk-subcategory" />
                ${t('editSubcategoryLabel')}
              </label>
              <input type="text" id="bulk-subcategory" list="subcategory-list" disabled />
              <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-subcategory" style="display:none;"></div>
            </div>
          </div>

          <div class="field bulk-field">
            <label class="checkbox-label bulk-apply-label" for="bulk-apply-date">
              <input type="checkbox" id="bulk-apply-date" class="bulk-apply-checkbox" data-bulk-target="bulk-date" />
              ${t('editDateLabel')}
            </label>
            <input type="date" id="bulk-date" disabled />
            <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-date" style="display:none;"></div>
          </div>

          <div class="field">
            <label for="bulk-tags">${t('captureTagsLabel')}</label>
            <input type="text" id="bulk-tags" placeholder="${t('captureTagsPlaceholder')}" />
            <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-tags" style="display:none;"></div>
          </div>

          <div id="bulk-person-fields"></div>

          <div class="field bulk-field">
            <label class="checkbox-label bulk-apply-label" for="bulk-apply-notes">
              <input type="checkbox" id="bulk-apply-notes" class="bulk-apply-checkbox" data-bulk-target="bulk-notes" />
              ${t('captureNotesLabel')}
            </label>
            <textarea id="bulk-notes" rows="3" disabled></textarea>
            <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-notes" style="display:none;"></div>
          </div>

          <div id="bulk-generic-fields"></div>

          <div class="modal-actions">
            <button class="primary" id="bulk-edit-save-btn">${t('editSaveChanges')}</button>
            <button id="bulk-edit-cancel-btn">${t('commonCancel')}</button>
          </div>
          <div class="status" id="bulk-edit-status" style="padding:10px 0 0;"></div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('bulk-edit-cancel-btn').addEventListener('click', () => closeModal());
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
    el('bulk-edit-save-btn').addEventListener('click', () => saveBulkEdit(ids));

    modalRoot.querySelectorAll('.bulk-apply-checkbox').forEach(cb => {
      cb.addEventListener('change', () => {
        const target = el(cb.dataset.bulkTarget);
        if(target) target.disabled = !cb.checked;
      });
    });
  }
```

Note: the Tags field and the `#bulk-person-fields`/`#bulk-generic-fields` containers are laid out now but not yet functional — Tasks 2 and 3 wire them.

- [ ] **Step 9: Add `saveBulkEdit(ids)` for the four scalar fields**

Immediately after `openBulkEditForm`, add:

```js
  async function saveBulkEdit(ids){
    const statusEl = el('bulk-edit-status');
    const saveBtn = el('bulk-edit-save-btn');
    saveBtn.disabled = true;
    statusEl.className = 'status busy';
    statusEl.innerHTML = '<span class="spinner"></span> ' + t('statusSaving');

    try{
      const scalarFields = [
        { applyId: 'bulk-apply-type', inputId: 'bulk-type', column: 'document_type', trim: true },
        { applyId: 'bulk-apply-category', inputId: 'bulk-category', column: 'category', trim: true },
        { applyId: 'bulk-apply-subcategory', inputId: 'bulk-subcategory', column: 'subcategory', trim: true },
        { applyId: 'bulk-apply-date', inputId: 'bulk-date', column: 'date', trim: false },
        { applyId: 'bulk-apply-notes', inputId: 'bulk-notes', column: 'notes', trim: true },
      ];
      const scalarUpdates = {};
      scalarFields.forEach(({applyId, inputId, column, trim}) => {
        if(!el(applyId).checked) return;
        const raw = el(inputId).value;
        scalarUpdates[column] = (trim ? raw.trim() : raw) || null;
      });
      if(Object.keys(scalarUpdates).length){
        const setClause = Object.keys(scalarUpdates).map(c => `${c} = ?`).join(', ');
        const params = Object.values(scalarUpdates);
        ids.forEach(id => db.run(`UPDATE documents SET ${setClause} WHERE id = ?`, [...params, id]));
        ids.forEach(id => {
          const d = allDocs.find(x => x.id === id);
          if(d) Object.assign(d, scalarUpdates);
        });
      }

      await persistDb();
      renderStats(); populateFilters(); populateDatalists();
      render();

      setStatusT(ids.length === 1 ? 'bulkEditSavedStatusSingular' : 'bulkEditSavedStatusPlural', {count: ids.length}, 'ok');
      closeModal();
      return true;
    }catch(e){
      statusEl.className = 'status err';
      statusEl.textContent = t('statusSaveFailed', {error: e.message});
      saveBtn.disabled = false;
      return false;
    }
  }
```

- [ ] **Step 10: Add the four new i18n keys to all six `STRINGS` blocks**

In `STRINGS.en` (near `editTitle: 'Edit document', ...` on line 956), add:

```js
      bulkEditModalTitleSingular: 'Edit {count} document', bulkEditModalTitlePlural: 'Edit {count} documents',
      bulkEditSavedStatusSingular: 'Updated {count} document.', bulkEditSavedStatusPlural: 'Updated {count} documents.',
```

Repeat with translated text in the same position (near each language's own `editTitle` line) for `STRINGS.es`, `STRINGS.fr`, `STRINGS.de`, `STRINGS['zh-Hans']`:

```js
// es
      bulkEditModalTitleSingular: 'Editar {count} documento', bulkEditModalTitlePlural: 'Editar {count} documentos',
      bulkEditSavedStatusSingular: 'Se actualizó {count} documento.', bulkEditSavedStatusPlural: 'Se actualizaron {count} documentos.',
// fr
      bulkEditModalTitleSingular: 'Modifier {count} document', bulkEditModalTitlePlural: 'Modifier {count} documents',
      bulkEditSavedStatusSingular: '{count} document mis à jour.', bulkEditSavedStatusPlural: '{count} documents mis à jour.',
// de
      bulkEditModalTitleSingular: '{count} Dokument bearbeiten', bulkEditModalTitlePlural: '{count} Dokumente bearbeiten',
      bulkEditSavedStatusSingular: '{count} Dokument aktualisiert.', bulkEditSavedStatusPlural: '{count} Dokumente aktualisiert.',
// zh-Hans
      bulkEditModalTitleSingular: '编辑 {count} 份文档', bulkEditModalTitlePlural: '编辑 {count} 份文档',
      bulkEditSavedStatusSingular: '已更新 {count} 份文档。', bulkEditSavedStatusPlural: '已更新 {count} 份文档。',
```

For `STRINGS['zh-Hant']`, derive from the `zh-Hans` lines above via OpenCC's `s2t` conversion (same one-time local-tool step this repo's other Traditional-Chinese strings used — install `opencc-python-reimplemented` into a scratch venv if not already available, convert, then discard the venv) rather than translating independently:

```js
// zh-Hant (derived via OpenCC s2t from the zh-Hans lines above)
      bulkEditModalTitleSingular: '編輯 {count} 份文檔', bulkEditModalTitlePlural: '編輯 {count} 份文檔',
      bulkEditSavedStatusSingular: '已更新 {count} 份文檔。', bulkEditSavedStatusPlural: '已更新 {count} 份文檔。',
```

- [ ] **Step 11: Run `test_i18n_coverage.py` to confirm no key drift**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: passes — every new `t('bulkEdit...')` call has a matching key in all six `STRINGS` blocks.

- [ ] **Step 12: Run `test_bulk_edit.py` to verify Scenario 2 passes**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: every printed line reads `True`, `JS ERRORS so far: []`.

- [ ] **Step 13: Write Scenarios 3-6 (Apply-checked write, Apply-unchecked no-touch, blank+checked clears, no-op save)**

Append before `print("JS ERRORS so far:", errors)`:

```python
        # === Scenario 3: checking Apply and typing a value writes it to every
        # selected document, and leaves an unselected document (id 4) untouched ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('#bulk-apply-category')
        await page.fill('#bulk-category', 'Bulk-Set Category')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        docs_by_id = {d['id']: d for d in persisted['documents']}
        print("doc 1 category bulk-set:", docs_by_id[1]['category'] == 'Bulk-Set Category')
        print("doc 2 category bulk-set:", docs_by_id[2]['category'] == 'Bulk-Set Category')
        print("doc 4 (not selected) category untouched:", docs_by_id[4]['category'] == 'Legal')
        print("selection survives a bulk-edit save:", await page.locator('tr[data-id="1"] .row-select-checkbox').is_checked())

        # === Scenario 4: leaving Apply unchecked on a field never touches it,
        # regardless of what's typed into its input ===
        await select_rows(page, [3, 4])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.fill('#bulk-notes', 'should never be saved')  # Apply left unchecked
        await page.check('#bulk-apply-subcategory')
        await page.fill('#bulk-subcategory', 'Bulk-Set Subcategory')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        docs_by_id = {d['id']: d for d in persisted['documents']}
        print("doc 3 notes untouched despite typed text (Apply unchecked):", docs_by_id[3]['notes'] is None)
        print("doc 3 subcategory bulk-set (Apply checked):", docs_by_id[3]['subcategory'] == 'Bulk-Set Subcategory')

        # === Scenario 5: Apply checked with a blank value is an explicit clear ===
        await page.click('#bulk-clear-selection-btn')
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('#bulk-apply-category')  # leave input blank
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        docs_by_id = {d['id']: d for d in persisted['documents']}
        print("doc 1 category cleared by Apply-checked + blank:", docs_by_id[1]['category'] is None)
        print("doc 2 category cleared by Apply-checked + blank:", docs_by_id[2]['category'] is None)

        # === Scenario 6: saving with every Apply box unchecked is a genuine no-op ===
        await select_rows(page, [3, 4])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        before = await read_db(page)
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        after = await read_db(page)
        print("saving with nothing checked changes nothing:", before['documents'] == after['documents'])
```

- [ ] **Step 14: Run the test to verify Scenarios 3-6 fail**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: Scenario 3 onward fails or errors (`saveBulkEdit` doesn't yet write anything for Category/Subcategory as coded... actually it does since Step 9 already covers all five scalar fields) — since Steps 8-9 already implement all scalar fields, this step should already show these scenarios passing at this point. Skip re-verifying failure here; proceed directly to Step 15's pass-confirmation run.

- [ ] **Step 15: Run the full test file and confirm every line passes**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: every printed boolean is `True`, `JS ERRORS so far: []`.

- [ ] **Step 16: Commit**

```bash
git add dossiary.html tests/test_bulk_edit.py
git commit -m "Add bulk-edit modal skeleton and scalar replace-semantics fields"
```

---

## Task 2: Tags and person-type fields (Add/Replace mode toggle) + `computeBulkFieldUnion`

**Files:**
- Modify: `dossiary.html`
  - `openBulkEditForm(ids)` (Task 1): add the Tags mode toggle, wire `wireCommaAutocomplete`, and populate `#bulk-person-fields`.
  - `saveBulkEdit(ids)` (Task 1): add Tags and person-type field writes.
  - New `computeBulkFieldUnion(ids)` function (placed near `applyDynamicFieldsForType()`, `~line 3852`).
  - New `renderBulkPersonFieldHtml(field, orphaned)` function (placed near `renderPersonFieldHtml()`, `~line 3744`).
  - `STRINGS.*`: new keys `bulkAddToExisting`, `bulkReplaceExisting`.
- Test: `tests/test_bulk_edit.py`

**Interfaces:**
- Consumes: `typeFieldOrder`, `fieldDefs`, `tagNameToId`, `nextTagId`, `personNameToId`, `nextPersonId`, `wireCommaAutocomplete(input, datalistId)`, `escapeHtml(s)` — all pre-existing. `openBulkEditForm`/`saveBulkEdit` from Task 1.
- Produces: `computeBulkFieldUnion(ids)` → `[{field: {id, name, type}, orphaned: boolean}, ...]`, ordered as configured-fields-first (by the order they appear across the selected documents' distinct types) then data-only fields — used unfiltered here for person-type fields and reused as-is by Task 3 for non-person fields, and by Task 4 for mixed-value hints on every field the union contains.

- [ ] **Step 1: Write Scenario 7 (union of person-type fields across two different types)**

Append to `tests/test_bulk_edit.py`, before the final `print("JS ERRORS so far:", errors)` (add a fresh seed reload first, since this scenario needs `fields`/`document_type_fields` fixtures the earlier scenarios' seed doesn't have):

```python
SEED_WITH_FIELDS = {
    "documents": SEED["documents"],
    # doc 1 starts with a pre-existing "old-tag" so Scenario 10b can prove
    # Replace mode actually discards it (Add mode, tested in Scenario 10, has
    # nothing to prove discarding since it never removes anything).
    "tags": [{"id": 1, "name": "old-tag"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}],
    "fields": [
        {"id": 1, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Vendor", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 3, "name": "Paid", "type": "checkbox", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_type_fields": [
        {"document_type": "Invoice", "field_name": "Vendor", "position": 0},
        {"document_type": "Invoice", "field_name": "Paid", "position": 1},
        {"document_type": "Letter", "field_name": "Author", "position": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 2, "value": "Acme Corp"},
        {"document_id": 1, "field_id": 3, "value": "1"},
        {"document_id": 2, "field_id": 3, "value": "0"},
    ],
    "document_field_people": [
        {"document_id": 3, "field_id": 1, "person_id": 100},
    ],
    "people": [{"id": 100, "name": "Jane Author"}],
}

async def main2():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED_WITH_FIELDS)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Scenario 7: selecting an Invoice (Vendor-configured) and a Letter
        # (Author-configured) shows both fields, Author rendered as a
        # comma-separated person-type input with the Add/Replace toggle ===
        await select_rows(page, [1, 3])  # doc 1 = Invoice, doc 3 = Letter
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        author_input_present = await page.locator('#bulk-field-1').count()
        author_mode_toggle_present = await page.locator('input[name="bulk-field-1-mode"]').count()
        print("Author (person-type) field rendered with its mode toggle:", author_input_present == 1 and author_mode_toggle_present == 2)

        # === Scenario 8: default mode is "Add to existing" -- typing a name adds
        # to doc 3's existing Author ("Jane Author") without removing it ===
        await page.fill('#bulk-field-1', 'New Coauthor')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        author_links = [r for r in persisted['document_field_people'] if r['field_id'] == 1 and r['document_id'] == 3]
        people_by_id = {p['id']: p['name'] for p in persisted['people']}
        author_names = sorted(people_by_id[r['person_id']] for r in author_links)
        print("Add mode keeps existing Author and adds the new one:", author_names == ['Jane Author', 'New Coauthor'])

        # === Scenario 9: switching to "Replace existing" and saving discards
        # whatever was there before ===
        await select_rows(page, [1, 3])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('input[name="bulk-field-1-mode"][value="replace"]')
        await page.fill('#bulk-field-1', 'Only This Author')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        author_links = [r for r in persisted['document_field_people'] if r['field_id'] == 1 and r['document_id'] == 3]
        people_by_id = {p['id']: p['name'] for p in persisted['people']}
        author_names = sorted(people_by_id[r['person_id']] for r in author_links)
        print("Replace mode discards prior Author names:", author_names == ['Only This Author'])

        # === Scenario 10: Tags default Add mode -- typed tags add without
        # removing what's already there; blank input on Add mode is a no-op ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.fill('#bulk-tags', 'urgent')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        tag_names = {t['id']: t['name'] for t in persisted['tags']}
        doc1_tags = sorted(tag_names[r['tag_id']] for r in persisted['document_tags'] if r['document_id'] == 1)
        print("Tags Add mode adds a new tag, keeping the pre-existing one:", doc1_tags == ['old-tag', 'urgent'])

        # === Scenario 10b: switching Tags to "Replace existing" and saving
        # discards doc 1's pre-existing "old-tag"/"urgent" entirely, leaving
        # only what was just typed ===
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('input[name="bulk-tags-mode"][value="replace"]')
        await page.fill('#bulk-tags', 'only-this-tag')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        tag_names = {t['id']: t['name'] for t in persisted['tags']}
        doc1_tags = sorted(tag_names[r['tag_id']] for r in persisted['document_tags'] if r['document_id'] == 1)
        print("Tags Replace mode discards prior tags:", doc1_tags == ['only-this-tag'])

        print("JS ERRORS (main2):", errors)
        await browser.close()

asyncio.run(main2())
```

- [ ] **Step 2: Run the test to verify Scenarios 7-10 fail**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: `Author (person-type) field rendered with its mode toggle: False` (or a Playwright locator timeout), since `#bulk-person-fields` is currently always empty and Tags has no mode toggle yet.

- [ ] **Step 3: Add `computeBulkFieldUnion(ids)`**

In `dossiary.html`, immediately after `applyDynamicFieldsForType()` (`~line 3936`, right after its closing `}`), add:

```js
  // Computes the field-union a bulk edit shows: every field configured for ANY
  // selected document's Document Type, plus any field ANY selected document
  // currently holds a value for (covering a field removed from its type's
  // configuration, or a reclassified document) -- see the design spec's
  // "Field list: union across selected documents" section. `orphaned` is true
  // when a field isn't configured for EVERY selected document's type, mirroring
  // (but distinct in meaning from) applyDynamicFieldsForType()'s own orphaned-
  // field concept: here it means "doesn't apply to every selected document's
  // type," not "this one document has stale data."
  function computeBulkFieldUnion(ids){
    const docs = ids.map(id => allDocs.find(d => d.id === id)).filter(Boolean);
    const distinctTypes = [...new Set(docs.map(d => (d.document_type || '').trim()))];

    const configuredByType = {}; // fieldName -> Set of distinctTypes that configure it
    distinctTypes.forEach(typeName => {
      (typeFieldOrder[typeName] || []).forEach(({field: fieldName}) => {
        if(!configuredByType[fieldName]) configuredByType[fieldName] = new Set();
        configuredByType[fieldName].add(typeName);
      });
    });

    const hasDataFieldNames = new Set();
    docs.forEach(d => {
      Object.keys(d.customFields || {}).forEach(name => hasDataFieldNames.add(name));
      Object.keys(d.personFieldValues || {}).forEach(name => {
        if((d.personFieldValues[name] || []).length) hasDataFieldNames.add(name);
      });
    });

    const orderedNames = [];
    const seen = new Set();
    distinctTypes.forEach(typeName => {
      (typeFieldOrder[typeName] || []).forEach(({field: fieldName}) => {
        if(!seen.has(fieldName)){ seen.add(fieldName); orderedNames.push(fieldName); }
      });
    });
    hasDataFieldNames.forEach(fieldName => {
      if(!seen.has(fieldName)){ seen.add(fieldName); orderedNames.push(fieldName); }
    });

    return orderedNames.map(fieldName => {
      const fieldDef = fieldDefs.find(f => f.name === fieldName);
      if(!fieldDef) return null;
      const configuredTypes = configuredByType[fieldName] || new Set();
      const orphaned = configuredTypes.size < distinctTypes.length;
      return { field: fieldDef, orphaned };
    }).filter(Boolean);
  }
```

- [ ] **Step 4: Add `renderBulkPersonFieldHtml(field, orphaned)`**

Immediately after `renderPersonFieldHtml()` (`~line 3760`, right after its closing `}`), add:

```js
  // Bulk-edit's own person-type field renderer -- structurally similar to
  // renderPersonFieldHtml() but with the "Add to existing"/"Replace existing"
  // mode toggle instead of a plain label + clear button, since a bulk edit
  // never pre-fills a value and never offers a single-input clear (see the
  // design spec's "Additive fields, with an Add/Replace mode toggle" section).
  function renderBulkPersonFieldHtml(field, orphaned){
    const inputId = `bulk-field-${field.id}`;
    const modeName = `bulk-field-${field.id}-mode`;
    return `
      <div class="field${orphaned ? ' field-orphaned' : ''}">
        <label for="${inputId}">${t('fieldPersonLabelSuffix', {name: escapeHtml(field.name)})}</label>
        <input type="text" id="${inputId}" placeholder="${t('fieldPersonPlaceholder')}" />
        <div class="bulk-mode-toggle">
          <label class="checkbox-label"><input type="radio" name="${modeName}" value="add" checked /> ${t('bulkAddToExisting')}</label>
          <label class="checkbox-label"><input type="radio" name="${modeName}" value="replace" /> ${t('bulkReplaceExisting')}</label>
        </div>
        <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-field-${field.id}" style="display:none;"></div>
        ${orphaned ? `<div class="field-orphaned-hint">${t('fieldOrphanedHint')}</div>` : ''}
      </div>
    `;
  }
```

- [ ] **Step 5: Wire Tags' mode toggle and populate `#bulk-person-fields` inside `openBulkEditForm`**

In `openBulkEditForm(ids)` (Task 1), replace the Tags field's markup:

```html
          <div class="field">
            <label for="bulk-tags">${t('captureTagsLabel')}</label>
            <input type="text" id="bulk-tags" placeholder="${t('captureTagsPlaceholder')}" />
            <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-tags" style="display:none;"></div>
          </div>
```

with:

```html
          <div class="field">
            <label for="bulk-tags">${t('captureTagsLabel')}</label>
            <input type="text" id="bulk-tags" placeholder="${t('captureTagsPlaceholder')}" />
            <div class="bulk-mode-toggle">
              <label class="checkbox-label"><input type="radio" name="bulk-tags-mode" value="add" checked /> ${t('bulkAddToExisting')}</label>
              <label class="checkbox-label"><input type="radio" name="bulk-tags-mode" value="replace" /> ${t('bulkReplaceExisting')}</label>
            </div>
            <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-tags" style="display:none;"></div>
          </div>
```

Then, right after the `.bulk-apply-checkbox` wiring loop at the end of `openBulkEditForm`, add:

```js
    const bulkFieldUnion = computeBulkFieldUnion(ids);
    el('bulk-person-fields').innerHTML = bulkFieldUnion
      .filter(({field}) => field.type === 'person')
      .map(({field, orphaned}) => renderBulkPersonFieldHtml(field, orphaned))
      .join('');
    wireCommaAutocomplete(el('bulk-tags'), 'tag-list');
    modalRoot.querySelectorAll('#bulk-person-fields input[type="text"]').forEach(input => wireCommaAutocomplete(input, 'person-list'));
```

- [ ] **Step 6: Add Tags and person-type field writes to `saveBulkEdit`**

In `saveBulkEdit(ids)` (Task 1), immediately after the scalar-fields block (right before `await persistDb();`), add:

```js
      const tagsMode = document.querySelector('input[name="bulk-tags-mode"]:checked').value;
      const typedTagNames = el('bulk-tags').value.split(',').map(s => s.trim()).filter(Boolean);
      if(typedTagNames.length || tagsMode === 'replace'){
        ids.forEach(id => {
          if(tagsMode === 'replace') db.run('DELETE FROM document_tags WHERE document_id = ?', [id]);
          const d = allDocs.find(x => x.id === id);
          const tagsForDoc = tagsMode === 'replace' ? [] : [...(d ? (d.tags || []) : [])];
          typedTagNames.forEach(name => {
            let tagId = tagNameToId[name];
            if(tagId === undefined){
              tagId = nextTagId++;
              db.run('INSERT INTO tags (id, name) VALUES (?, ?)', [tagId, name]);
              tagNameToId[name] = tagId;
            }
            db.run('INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)', [id, tagId]);
            if(!tagsForDoc.includes(name)) tagsForDoc.push(name);
          });
          if(d) d.tags = tagsForDoc;
        });
      }

      const idToFieldName = Object.fromEntries(fieldDefs.map(f => [f.id, f.name]));
      const personFieldEntries = computeBulkFieldUnion(ids).filter(({field}) => field.type === 'person');
      for(const {field} of personFieldEntries){
        const modeInput = document.querySelector(`input[name="bulk-field-${field.id}-mode"]:checked`);
        if(!modeInput) continue;
        const mode = modeInput.value;
        const typedNames = el(`bulk-field-${field.id}`).value.split(',').map(s => s.trim()).filter(Boolean);
        if(!typedNames.length && mode !== 'replace') continue;
        ids.forEach(id => {
          if(mode === 'replace') db.run('DELETE FROM document_field_people WHERE document_id = ? AND field_id = ?', [id, field.id]);
          const d = allDocs.find(x => x.id === id);
          const existing = mode === 'replace' ? [] : [...((d && d.personFieldValues && d.personFieldValues[field.name]) || [])];
          typedNames.forEach(name => {
            let personId = personNameToId[name];
            if(personId === undefined){
              personId = nextPersonId++;
              db.run('INSERT INTO people (id, name) VALUES (?, ?)', [personId, name]);
              personNameToId[name] = personId;
            }
            db.run('INSERT OR IGNORE INTO document_field_people (document_id, field_id, person_id) VALUES (?, ?, ?)', [id, field.id, personId]);
            if(!existing.includes(name)) existing.push(name);
          });
          if(d){
            if(!d.personFieldValues) d.personFieldValues = {};
            d.personFieldValues[field.name] = existing;
            if(field.name === 'People') d.people = existing;
          }
        });
      }
```

(`idToFieldName` is unused so far but Task 3 relies on it too — leave it in place.)

- [ ] **Step 7: Add `bulkAddToExisting`/`bulkReplaceExisting` to all six `STRINGS` blocks**

Same pattern as Task 1 Step 10 — add near each language's own `bulkClearSelection`/`bulkFlagForReview` keys:

```js
// en
      bulkAddToExisting: 'Add to existing', bulkReplaceExisting: 'Replace existing',
// es
      bulkAddToExisting: 'Añadir a lo existente', bulkReplaceExisting: 'Reemplazar lo existente',
// fr
      bulkAddToExisting: 'Ajouter à l\'existant', bulkReplaceExisting: 'Remplacer l\'existant',
// de
      bulkAddToExisting: 'Zu Bestehendem hinzufügen', bulkReplaceExisting: 'Bestehendes ersetzen',
// zh-Hans
      bulkAddToExisting: '添加到现有内容', bulkReplaceExisting: '替换现有内容',
// zh-Hant (derived via OpenCC s2t from the zh-Hans line above)
      bulkAddToExisting: '添加到現有內容', bulkReplaceExisting: '替換現有內容',
```

- [ ] **Step 8: Run `test_i18n_coverage.py`, then `test_bulk_edit.py`, and confirm everything passes**

Run: `cd tests && python3 test_i18n_coverage.py && python3 test_bulk_edit.py`
Expected: both scripts print all-`True`/no missing-key output, `JS ERRORS (main2): []`.

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_bulk_edit.py
git commit -m "Add Tags and person-type fields with Add/Replace mode to bulk edit"
```

---

## Task 3: Generic custom fields (union rendering) + sidecar `.txt` sync

**Files:**
- Modify: `dossiary.html`
  - New `renderBulkGenericFieldHtml(field, orphaned)` (placed near `renderGenericFieldHtml()`, `~line 3837`).
  - `openBulkEditForm(ids)`: populate `#bulk-generic-fields`, wire its Apply checkboxes.
  - `saveBulkEdit(ids)`: write generic (non-person) fields, then rewrite every affected document's sidecar `.txt`.
  - `STRINGS.*`: new key `bulkFieldValueLabel`.
- Test: `tests/test_bulk_edit.py`

**Interfaces:**
- Consumes: `computeBulkFieldUnion(ids)` (Task 2), `sidecarBaseNameFromFilePath(filePath)`, `buildSidecarText({...})`, `writeSidecarFile(baseName, text)` — all pre-existing.
- Produces: `renderBulkGenericFieldHtml(field, orphaned)` — no other task consumes this directly, but Task 4 relies on the `bulk-field-${field.id}`/`bulk-apply-field-${field.id}`/`bulk-mixed-hint-field-${field.id}` id convention it establishes.

- [ ] **Step 1: Write Scenarios 11-13 (generic field union with orphaned styling, Apply-checked write, sidecar sync)**

Append to `main2()` in `tests/test_bulk_edit.py`, before `print("JS ERRORS (main2):", errors)`:

```python
        # === Scenario 11: Vendor (configured only for Invoice, not Letter) shows
        # with .field-orphaned styling since it isn't common to both selected
        # types; a checkbox-type field shows its own separate value checkbox ===
        await select_rows(page, [1, 3])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        vendor_field_orphaned = await page.locator('#bulk-field-2').locator('xpath=ancestor::div[contains(@class,"field-orphaned")]').count()
        print("Vendor field renders with .field-orphaned styling:", vendor_field_orphaned == 1)

        # === Scenario 12: checking Vendor's Apply box and typing a value writes
        # it to every selected document, including doc 3 (Letter), where Vendor
        # isn't normally configured at all -- same as editing an orphaned field
        # already does for a single document ===
        await page.check('#bulk-apply-field-2')
        await page.fill('#bulk-field-2', 'New Vendor LLC')
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        vendor_values = {r['document_id']: r['value'] for r in persisted['document_field_values'] if r['field_id'] == 2}
        print("doc 1 Vendor bulk-set:", vendor_values.get(1) == 'New Vendor LLC')
        print("doc 3 (orphaned) Vendor also bulk-set:", vendor_values.get(3) == 'New Vendor LLC')

        # === Scenario 12b: a checkbox-type field's "Apply to all" and its own
        # Yes/No value checkbox are independent -- doc 1 starts Paid=1, doc 2
        # starts Paid=0. Toggling the VALUE checkbox while leaving Apply
        # unchecked changes nothing on save; checking Apply then saves
        # whatever the value checkbox currently shows (unchecked = "0") to
        # every selected document regardless of each one's prior value ===
        await page.click('#bulk-clear-selection-btn')
        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('#bulk-field-3')  # toggle the VALUE checkbox only -- Apply left unchecked
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        paid_values = {r['document_id']: r['value'] for r in persisted['document_field_values'] if r['field_id'] == 3}
        print("Paid untouched on both docs when only the value checkbox was toggled (Apply unchecked):", paid_values.get(1) == '1' and paid_values.get(2) == '0')

        await select_rows(page, [1, 2])
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        await page.check('#bulk-apply-field-3')  # Apply checked; value checkbox left unchecked ("No")
        await page.click('#bulk-edit-save-btn')
        await page.wait_for_timeout(300)
        persisted = await read_db(page)
        paid_values = {r['document_id']: r['value'] for r in persisted['document_field_values'] if r['field_id'] == 3}
        print("Paid bulk-set to '0' on both docs once Apply is checked:", paid_values.get(1) == '0' and paid_values.get(2) == '0')

        # === Scenario 13: the sidecar .txt for an affected document reflects the
        # complete post-edit state, not just the fields that changed ===
        sidecar_text = await page.evaluate("""
            (async () => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files');
                const fh = await dir.getFileHandle('1_a.txt');
                const f = await fh.getFile();
                return await f.text();
            })()
        """)
        print("sidecar reflects the bulk-set Vendor value:", 'New Vendor LLC' in sidecar_text)
        print("sidecar still reflects the document's own unrelated title:", 'Invoice A' in sidecar_text)
```

- [ ] **Step 2: Run the test to verify Scenarios 11-13 fail**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: `Vendor field renders with .field-orphaned styling: False` (or a locator timeout), since `#bulk-generic-fields` is currently always empty.

- [ ] **Step 3: Add `renderBulkGenericFieldHtml(field, orphaned)`**

Immediately after `renderGenericFieldHtml()` (`~line 3837`, right after its closing `}`), add:

```js
  // Bulk-edit's own generic (non-person) field renderer -- an "Apply to all"
  // checkbox stands in for renderGenericFieldHtml()'s plain <label> (see the
  // design spec's "The 'Apply' toggle" section), and there's no clear button
  // or Date-today/Currency-default guess treatment, since a bulk edit never
  // pre-fills a value to guess from or clear. A checkbox-type field shows a
  // second, independent checkbox for its own Yes/No value, gated by the same
  // Apply checkbox as every other field type.
  function renderBulkGenericFieldHtml(field, orphaned){
    const applyId = `bulk-apply-field-${field.id}`;
    const inputId = `bulk-field-${field.id}`;
    const orphanedClass = orphaned ? ' field-orphaned' : '';
    const orphanedHint = orphaned ? `<div class="field-orphaned-hint">${t('fieldOrphanedHint')}</div>` : '';
    const applyLabel = `
      <label class="checkbox-label bulk-apply-label" for="${applyId}">
        <input type="checkbox" id="${applyId}" class="bulk-apply-checkbox" data-bulk-target="${inputId}" />
        ${escapeHtml(field.name)}
      </label>
    `;
    if(field.type === 'checkbox'){
      return `
        <div class="field bulk-field${orphanedClass}">
          ${applyLabel}
          <label class="checkbox-label"><input type="checkbox" id="${inputId}" disabled /> ${t('bulkFieldValueLabel')}</label>
          <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-field-${field.id}" style="display:none;"></div>
          ${orphanedHint}
        </div>
      `;
    }
    let inputType = 'text', extra = '';
    if(field.type === 'number'){ inputType = 'number'; extra = 'step="any"'; }
    else if(field.type === 'date' || field.type === 'reminder'){ inputType = 'date'; }
    return `
      <div class="field bulk-field${orphanedClass}">
        ${applyLabel}
        <input type="${inputType}" id="${inputId}" ${extra} disabled />
        <div class="field-hint bulk-mixed-hint" id="bulk-mixed-hint-field-${field.id}" style="display:none;"></div>
        ${orphanedHint}
      </div>
    `;
  }
```

- [ ] **Step 4: Populate `#bulk-generic-fields` and wire its Apply checkboxes in `openBulkEditForm`**

In `openBulkEditForm(ids)`, right after the `#bulk-person-fields` population added in Task 2, add:

```js
    el('bulk-generic-fields').innerHTML = bulkFieldUnion
      .filter(({field}) => field.type !== 'person')
      .map(({field, orphaned}) => renderBulkGenericFieldHtml(field, orphaned))
      .join('');
    modalRoot.querySelectorAll('#bulk-generic-fields .bulk-apply-checkbox').forEach(cb => {
      cb.addEventListener('change', () => {
        const target = el(cb.dataset.bulkTarget);
        if(target) target.disabled = !cb.checked;
      });
    });
```

- [ ] **Step 5: Add generic-field writes and the sidecar-sync loop to `saveBulkEdit`**

In `saveBulkEdit(ids)`, immediately after the person-field-writing loop added in Task 2, still before `await persistDb();`, add:

```js
      const genericFieldEntries = computeBulkFieldUnion(ids).filter(({field}) => field.type !== 'person');
      for(const {field} of genericFieldEntries){
        const applyCb = el(`bulk-apply-field-${field.id}`);
        if(!applyCb || !applyCb.checked) continue;
        const inputEl = el(`bulk-field-${field.id}`);
        const value = field.type === 'checkbox' ? (inputEl.checked ? '1' : '0') : inputEl.value.trim();
        ids.forEach(id => {
          db.run('DELETE FROM document_field_values WHERE document_id = ? AND field_id = ?', [id, field.id]);
          if(value !== '') db.run('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [id, field.id, value]);
          const d = allDocs.find(x => x.id === id);
          if(d){
            if(!d.customFields) d.customFields = {};
            if(value !== '') d.customFields[field.name] = value; else delete d.customFields[field.name];
          }
        });
      }

      // Rewrite every affected document's sidecar .txt with its complete
      // post-edit state -- d has already been updated in-memory by every write
      // block above, mirroring saveEditedDocument()'s own sidecar-rewrite step.
      for(const id of ids){
        const d = allDocs.find(x => x.id === id);
        if(!d) continue;
        const sidecarBaseName = sidecarBaseNameFromFilePath(d.file_path);
        if(!sidecarBaseName) continue;
        const otherPersonFieldsForSidecar = { ...(d.personFieldValues || {}) };
        delete otherPersonFieldsForSidecar['People'];
        await writeSidecarFile(sidecarBaseName, buildSidecarText({
          title: d.title, category: d.category, subcategory: d.subcategory, documentType: d.document_type,
          date: d.date, importDate: d.import_date, customFields: d.customFields || {}, personFields: otherPersonFieldsForSidecar,
          people: d.people || [], notes: d.notes, ocrText: d.ocr_text, tags: d.tags || [],
        }));
      }
```

- [ ] **Step 6: Add `bulkFieldValueLabel` to all six `STRINGS` blocks**

```js
// en
      bulkFieldValueLabel: 'Value',
// es
      bulkFieldValueLabel: 'Valor',
// fr
      bulkFieldValueLabel: 'Valeur',
// de
      bulkFieldValueLabel: 'Wert',
// zh-Hans
      bulkFieldValueLabel: '值',
// zh-Hant (identical to zh-Hans here -- OpenCC s2t makes no character change for this word)
      bulkFieldValueLabel: '值',
```

- [ ] **Step 7: Run `test_i18n_coverage.py`, then `test_bulk_edit.py`, and confirm everything passes**

Run: `cd tests && python3 test_i18n_coverage.py && python3 test_bulk_edit.py`
Expected: both scripts print all-`True`/no missing-key output.

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_bulk_edit.py
git commit -m "Add generic custom-field union and sidecar sync to bulk edit"
```

---

## Task 4: Mixed-value indicator

**Files:**
- Modify: `dossiary.html`
  - New `bulkScalarMixed(ids, getValue)`, `bulkSetMixed(ids, getNames)`, `setBulkMixedHint(hintId, text, variant)`, `refreshBulkMixedHints(ids)` functions.
  - `openBulkEditForm(ids)`: call `refreshBulkMixedHints(ids)` once at the end, and wire every mode-toggle radio's `change` event to re-call it.
  - `STRINGS.*`: new keys `bulkMixedOverwriteWarning`, `bulkMixedAddedOnTop`.
- Test: `tests/test_bulk_edit.py`

**Interfaces:**
- Consumes: `computeBulkFieldUnion(ids)` (Task 2), the scalar/Tags/person/generic field DOM ids established in Tasks 1-3.
- Produces: nothing further downstream — this is the last piece of the modal's own field behavior; Task 5 only adds a second entry point into the already-complete `openBulkEditForm`.

- [ ] **Step 1: Write Scenarios 14-16 (mixed scalar warning, uniform shows nothing, additive mode-dependent wording)**

Append to `main2()` in `tests/test_bulk_edit.py`, before `print("JS ERRORS (main2):", errors)` (reuses `SEED_WITH_FIELDS`, where doc 1's category is `"Finance"` and doc 3's is `None` — already mixed):

```python
        # === Scenario 14: a replace-semantics field with differing current
        # values across the selection shows the overwrite-warning hint; the same
        # field with identical values shows no hint at all ===
        await page.click('#bulk-clear-selection-btn')
        await select_rows(page, [1, 3])  # doc 1 category="Finance", doc 3 category=None -- mixed
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        category_hint_visible = await page.locator('#bulk-mixed-hint-category:visible').count()
        print("mixed Category shows the overwrite-warning hint:", category_hint_visible == 1)
        date_hint_visible = await page.locator('#bulk-mixed-hint-date:visible').count()
        print("Date (both None -- uniform) shows no hint:", date_hint_visible == 0)
        await page.click('#bulk-edit-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 15: an additive field (Tags) with differing tag sets shows
        # the "added on top" hint on the default Add mode ===
        await select_rows(page, [1, 2])  # doc 1 now has 'urgent' from Scenario 10, doc 2 doesn't
        await page.click('#bulk-edit-btn')
        await page.wait_for_timeout(200)
        tags_hint_text_add = await page.locator('#bulk-mixed-hint-tags').inner_text()
        print("mixed Tags on Add mode shows the 'added on top' hint:", 'Tags' in tags_hint_text_add or 'tags' in tags_hint_text_add.lower())

        # === Scenario 16: switching that same field to Replace mode live-updates
        # the hint to the overwrite-warning wording ===
        await page.check('input[name="bulk-tags-mode"][value="replace"]')
        await page.wait_for_timeout(150)
        tags_hint_visible_replace = await page.locator('#bulk-mixed-hint-tags:visible').count()
        overwrite_warning_en = "overwrite"
        tags_hint_text_replace = await page.locator('#bulk-mixed-hint-tags').inner_text()
        print("switching to Replace mode shows the overwrite-warning wording:", tags_hint_visible_replace == 1 and overwrite_warning_en in tags_hint_text_replace.lower())
```

- [ ] **Step 2: Run the test to verify Scenarios 14-16 fail**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: `mixed Category shows the overwrite-warning hint: False` (hint divs currently always stay `display:none`, since nothing computes or sets them yet).

- [ ] **Step 3: Add `bulkScalarMixed`, `bulkSetMixed`, and `setBulkMixedHint`**

Immediately after `computeBulkFieldUnion()` (Task 2, `~line` right after its closing `}`), add:

```js
  // "Mixed" means the selected documents don't all agree on this field's
  // current value -- blank/unset counts as one shared value for this
  // comparison, so "all blank" is NOT mixed, but "some set, some blank" is.
  function bulkScalarMixed(ids, getValue){
    const norm = v => (v === null || v === undefined || v === '') ? '' : v;
    const values = new Set(ids.map(id => norm(getValue(allDocs.find(d => d.id === id)))));
    return values.size > 1;
  }
  // Same idea for a multi-valued (Tags/person-type) field -- compares the
  // selected documents' name/tag SETS, order-independent.
  function bulkSetMixed(ids, getNames){
    const serialize = names => [...(names || [])].map(n => n.toLowerCase()).sort().join('');
    const values = new Set(ids.map(id => serialize(getNames(allDocs.find(d => d.id === id)))));
    return values.size > 1;
  }
  function setBulkMixedHint(hintId, text, variant){
    const hintEl = el(hintId);
    if(!hintEl) return;
    if(text){
      hintEl.textContent = text;
      hintEl.className = variant === 'warning' ? 'field-guess-hint' : 'field-orphaned-hint';
      hintEl.style.display = '';
    }else{
      hintEl.style.display = 'none';
    }
  }
```

- [ ] **Step 4: Add `refreshBulkMixedHints(ids)`**

Immediately after `setBulkMixedHint`, add:

```js
  function refreshBulkMixedHints(ids){
    const scalarChecks = [
      { column: 'document_type', hintId: 'bulk-mixed-hint-type', labelKey: 'editDocTypeLabel' },
      { column: 'category', hintId: 'bulk-mixed-hint-category', labelKey: 'editCategoryLabel' },
      { column: 'subcategory', hintId: 'bulk-mixed-hint-subcategory', labelKey: 'editSubcategoryLabel' },
      { column: 'date', hintId: 'bulk-mixed-hint-date', labelKey: 'editDateLabel' },
      { column: 'notes', hintId: 'bulk-mixed-hint-notes', labelKey: 'captureNotesLabel' },
    ];
    scalarChecks.forEach(({column, hintId, labelKey}) => {
      const mixed = bulkScalarMixed(ids, d => d[column]);
      setBulkMixedHint(hintId, mixed ? t('bulkMixedOverwriteWarning', {field: t(labelKey)}) : '', 'warning');
    });

    const tagsMixed = bulkSetMixed(ids, d => d.tags);
    const tagsModeInput = document.querySelector('input[name="bulk-tags-mode"]:checked');
    const tagsMode = tagsModeInput ? tagsModeInput.value : 'add';
    setBulkMixedHint('bulk-mixed-hint-tags',
      tagsMixed ? t(tagsMode === 'replace' ? 'bulkMixedOverwriteWarning' : 'bulkMixedAddedOnTop', {field: t('captureTagsLabel')}) : '',
      tagsMode === 'replace' ? 'warning' : 'info');

    computeBulkFieldUnion(ids).forEach(({field}) => {
      const hintId = `bulk-mixed-hint-field-${field.id}`;
      if(field.type === 'person'){
        const mixed = bulkSetMixed(ids, d => (d.personFieldValues || {})[field.name]);
        const modeInput = document.querySelector(`input[name="bulk-field-${field.id}-mode"]:checked`);
        const mode = modeInput ? modeInput.value : 'add';
        setBulkMixedHint(hintId,
          mixed ? t(mode === 'replace' ? 'bulkMixedOverwriteWarning' : 'bulkMixedAddedOnTop', {field: field.name}) : '',
          mode === 'replace' ? 'warning' : 'info');
      }else{
        const mixed = bulkScalarMixed(ids, d => (d.customFields || {})[field.name]);
        setBulkMixedHint(hintId, mixed ? t('bulkMixedOverwriteWarning', {field: field.name}) : '', 'warning');
      }
    });
  }
```

- [ ] **Step 5: Call `refreshBulkMixedHints` and wire live mode-toggle updates in `openBulkEditForm`**

At the very end of `openBulkEditForm(ids)` (after the `#bulk-generic-fields` population/wiring added in Task 3), add:

```js
    modalRoot.querySelectorAll('input[type="radio"][name^="bulk-tags-mode"], input[type="radio"][name^="bulk-field-"]').forEach(radio => {
      radio.addEventListener('change', () => refreshBulkMixedHints(ids));
    });
    refreshBulkMixedHints(ids);
```

- [ ] **Step 6: Add `bulkMixedOverwriteWarning`/`bulkMixedAddedOnTop` to all six `STRINGS` blocks**

```js
// en
      bulkMixedOverwriteWarning: 'Documents in this selection currently have different {field} — checking Apply (or choosing Replace) will overwrite ALL of them with the value you enter.',
      bulkMixedAddedOnTop: 'Documents in this selection currently have different {field} — what you enter here is added on top of each document\'s own existing values; nothing is removed.',
// es
      bulkMixedOverwriteWarning: 'Los documentos de esta selección tienen valores distintos de {field} — marcar Aplicar (o elegir Reemplazar) sobrescribirá TODOS con el valor que introduzcas.',
      bulkMixedAddedOnTop: 'Los documentos de esta selección tienen {field} distintos — lo que escribas aquí se añade a los valores ya existentes de cada documento; no se elimina nada.',
// fr
      bulkMixedOverwriteWarning: 'Les documents de cette sélection ont des {field} différents — cocher Appliquer (ou choisir Remplacer) écrasera TOUS les documents avec la valeur saisie.',
      bulkMixedAddedOnTop: 'Les documents de cette sélection ont des {field} différents — ce que vous saisissez ici s\'ajoute aux valeurs déjà existantes de chaque document ; rien n\'est supprimé.',
// de
      bulkMixedOverwriteWarning: 'Die Dokumente in dieser Auswahl haben unterschiedliche {field} — wenn du „Anwenden" ankreuzt (oder „Ersetzen" wählst), werden ALLE mit dem eingegebenen Wert überschrieben.',
      bulkMixedAddedOnTop: 'Die Dokumente in dieser Auswahl haben unterschiedliche {field} — was du hier einträgst, wird zu den vorhandenen Werten jedes Dokuments hinzugefügt; nichts wird entfernt.',
// zh-Hans
      bulkMixedOverwriteWarning: '此選集中的文檔目前有不同的 {field} —— 勾選「應用」（或選擇「替換」）將用你輸入的值覆蓋所有文檔。',
      bulkMixedAddedOnTop: '此選集中的文檔目前有不同的 {field} —— 你在此輸入的內容會添加到每份文檔已有的值之上，不會刪除任何內容。',
```

Note: the `zh-Hans` block above must actually use Simplified characters — write it as:

```js
// zh-Hans
      bulkMixedOverwriteWarning: '此选集中的文档目前有不同的 {field} —— 勾选“应用”（或选择“替换”）将用你输入的值覆盖所有文档。',
      bulkMixedAddedOnTop: '此选集中的文档目前有不同的 {field} —— 你在此输入的内容会添加到每份文档已有的值之上，不会删除任何内容。',
// zh-Hant (derived via OpenCC s2t from the zh-Hans lines above)
      bulkMixedOverwriteWarning: '此選集中的文檔目前有不同的 {field} —— 勾選「應用」（或選擇「替換」）將用你輸入的值覆蓋所有文檔。',
      bulkMixedAddedOnTop: '此選集中的文檔目前有不同的 {field} —— 你在此輸入的內容會添加到每份文檔已有的值之上，不會刪除任何內容。',
```

- [ ] **Step 7: Run `test_i18n_coverage.py`, then `test_bulk_edit.py`, and confirm everything passes**

Run: `cd tests && python3 test_i18n_coverage.py && python3 test_bulk_edit.py`
Expected: both scripts print all-`True`/no missing-key output.

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_bulk_edit.py
git commit -m "Add mixed-value indicator to the bulk-edit form"
```

---

## Task 5: Right-click bulk context menu on checked rows

**Files:**
- Modify: `dossiary.html`
  - `~line 4702` (the existing row `contextmenu` listener inside `render()`): branch to a new bulk menu when the right-clicked row is checked and 2+ rows are selected.
  - New `showBulkRowContextMenu(x, y)` function (placed near `showRowContextMenu()`, `~line 5019`).
- Test: `tests/test_bulk_edit.py`

**Interfaces:**
- Consumes: `selectedDocIds`, `openRowContextMenu` (the existing module-level tracked-menu variable), `openBulkEditForm(ids)` (Task 1), `t(key, params)`.
- Produces: nothing further downstream — this is the last functional piece of the feature; Task 6 is documentation only.

- [ ] **Step 1: Write Scenarios 17-19 (bulk menu on checked rows, single-doc menu on unchecked rows, bulk menu's Edit opens the modal)**

Append to `main2()` in `tests/test_bulk_edit.py`, before `print("JS ERRORS (main2):", errors)`:

```python
        # === Scenario 17: right-clicking a CHECKED row while 2+ are selected
        # shows the bulk context menu with exactly one item, "Edit" -- not the
        # single-document menu ===
        await page.click('#bulk-clear-selection-btn')
        await select_rows(page, [1, 2])
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        bulk_menu_items = await page.locator('.row-context-menu .row-context-menu-item').all_inner_texts()
        print("bulk context menu shows exactly one item, Edit:", bulk_menu_items == ['Edit'])
        await page.mouse.click(10, 10)  # click outside to dismiss
        await page.wait_for_timeout(150)

        # === Scenario 18: right-clicking an UNCHECKED row keeps today's
        # single-document menu, even while other rows are checked elsewhere ===
        await page.click('tr[data-id="3"]', button='right')  # doc 3 not checked
        await page.wait_for_timeout(150)
        single_doc_menu_items = await page.locator('.row-context-menu .row-context-menu-item').all_inner_texts()
        print("unchecked row still shows the single-document menu (more than one item):", len(single_doc_menu_items) > 1)
        await page.mouse.click(10, 10)
        await page.wait_for_timeout(150)

        # === Scenario 19: clicking the bulk menu's "Edit" opens the bulk-edit
        # modal for the checked selection ===
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        await page.click('.row-context-menu .row-context-menu-item:has-text("Edit")')
        await page.wait_for_timeout(200)
        bulk_modal_opened = await page.locator('#bulk-edit-save-btn').count()
        print("bulk context menu's Edit opens the bulk-edit modal:", bulk_modal_opened == 1)
        await page.click('#bulk-edit-cancel-btn')
        await page.wait_for_timeout(150)
```

- [ ] **Step 2: Run the test to verify Scenarios 17-19 fail**

Run: `cd tests && python3 test_bulk_edit.py`
Expected: `bulk context menu shows exactly one item, Edit: False` — right-clicking a checked row currently still opens the existing single-document menu (which has several items, not one).

- [ ] **Step 3: Add `showBulkRowContextMenu(x, y)`**

Immediately before `showRowContextMenu(id, x, y)` (`~line 5019`), add:

```js
  // Right-click's bulk sibling to showRowContextMenu() -- shown instead of the
  // single-document menu when the right-clicked row is part of a 2+-document
  // selection. Deliberately minimal (just "Edit"): Archive/Delete/Flag for
  // review already live in the bulk-action bar, so this menu doesn't duplicate
  // them (see the design spec's "Entry points" section).
  function showBulkRowContextMenu(x, y){
    if(openRowContextMenu){ openRowContextMenu.remove(); openRowContextMenu = null; }

    const menu = document.createElement('div');
    menu.className = 'row-context-menu';
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';

    const editBtn = document.createElement('button');
    editBtn.type = 'button';
    editBtn.className = 'row-context-menu-item';
    editBtn.textContent = t('detailEdit');
    menu.appendChild(editBtn);

    document.body.appendChild(menu);
    openRowContextMenu = menu;

    const closeMenu = () => {
      if(openRowContextMenu === menu){ menu.remove(); openRowContextMenu = null; }
      document.removeEventListener('click', closeMenu);
      document.removeEventListener('contextmenu', closeMenu);
    };

    editBtn.addEventListener('click', () => {
      openBulkEditForm([...selectedDocIds]);
      closeMenu();
    });

    setTimeout(() => {
      document.addEventListener('click', closeMenu);
      document.addEventListener('contextmenu', closeMenu);
    }, 0);
  }
```

- [ ] **Step 4: Branch the existing `contextmenu` listener to the bulk menu**

In `render()`'s row-wiring pass, replace the existing listener:

```js
    tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('contextmenu', (e) => {
      if(e.target.closest('.select-col, .row-edit-col')) return;
      e.preventDefault();
      const id = Number(tr.dataset.id);
      selectedDocId = id;
      tbody.querySelectorAll('tr.row-selected').forEach(r => r.classList.remove('row-selected'));
      tr.classList.add('row-selected');
      openDetail(id);
      showRowContextMenu(id, e.clientX, e.clientY);
    }));
```

with:

```js
    tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('contextmenu', (e) => {
      if(e.target.closest('.select-col, .row-edit-col')) return;
      e.preventDefault();
      const id = Number(tr.dataset.id);
      // A checked row, while 2+ are checked, gets the bulk menu instead --
      // deliberately does NOT touch selectedDocId/the detail panel/single-row
      // highlighting, since the action targets the whole multi-selection, not
      // specifically the row that happened to be right-clicked (its checkbox
      // already reflects its membership in that selection).
      if(selectedDocIds.has(id) && selectedDocIds.size >= 2){
        showBulkRowContextMenu(e.clientX, e.clientY);
        return;
      }
      selectedDocId = id;
      tbody.querySelectorAll('tr.row-selected').forEach(r => r.classList.remove('row-selected'));
      tr.classList.add('row-selected');
      openDetail(id);
      showRowContextMenu(id, e.clientX, e.clientY);
    }));
```

- [ ] **Step 5: Run the full test file and confirm every line passes**

Run: `cd tests && python3 test_i18n_coverage.py && python3 test_bulk_edit.py`
Expected: both scripts print all-`True`/no missing-key output, `JS ERRORS so far: []`, `JS ERRORS (main2): []`.

- [ ] **Step 6: Run the full existing test suite for regressions**

Run: `cd tests && for f in test_*.py; do echo "=== $f ==="; python3 "$f" 2>&1 | tail -5; done`
Expected: no new failures anywhere else in the suite — in particular `test_detail_panel.py`'s existing right-click scenarios (which right-click *unchecked* rows) should be completely unaffected, since the new branch only fires when the target row is checked and 2+ are selected.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_bulk_edit.py
git commit -m "Add right-click bulk context menu for 2+ selected documents"
```

---

## Task 6: Documentation

**Files:**
- Modify: `CLAUDE.md` — new architecture note.

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing (documentation only).

- [ ] **Step 1: Add a new architecture note to `CLAUDE.md`**

In `CLAUDE.md`, in the "Architecture notes" section, immediately after the existing "Comma-aware autocomplete for multi-valued fields" note (the last bullet in that section), add a new bullet:

```markdown
- **Bulk edit** (`openBulkEditForm(ids)`, `saveBulkEdit(ids)`, reachable via a
  new "Edit" button in the bulk-action bar and a minimal right-click context
  menu on checked rows) lets someone set field values across every currently
  selected document in one save. It's structurally parallel to the
  single-document Edit form but with two deliberate differences forced by
  operating on many documents at once instead of one: every field starts
  genuinely blank (there's no single correct document to pre-fill from), and
  every **replace-semantics** field (Document Type, Category, Subcategory,
  Date, Notes, every generic custom field) carries its own "Apply to all"
  checkbox, unchecked by default — only checked fields are written to any
  document, and checking one with a blank value is a valid, explicit "clear
  this on every selected document." This is necessary, not just a UX nicety:
  "blank" already means different things per field type elsewhere in this app
  (an unchecked checkbox field is real data, not "unset" — see
  `readDynamicFieldValues()`'s own rule), so there's no value-based way to
  distinguish "leave this alone" from "clear it" that works uniformly across
  every field type; the explicit checkbox is the one mechanism that does.
  **Tags and every person-type field (People, Author, Collaborator, …) get an
  "Add to existing"/"Replace existing" mode toggle instead of an Apply
  checkbox** — the toggle itself is the explicit opt-in (Add, the default, is
  already a safe no-op on a blank input), so no separate checkbox is needed;
  Replace mode reuses the exact delete-then-reinsert `saveEditedDocument()`
  already does for a single document's Tags/People, looped per selected
  document, and — like the scalar fields above — a blank input on Replace
  mode is a deliberate, explicit "clear this on every selected document."
  **Title and the OCR-text box are deliberately excluded** — bulk-setting
  every selected document's title to the identical string has no sensible use
  case (and would actively harm the table's own scannability), and OCR text
  is per-file extracted content tied to that document's own file, not
  metadata in the sense the rest of this form edits.
  **`computeBulkFieldUnion(ids)`** computes, once per modal open, the union
  of every field configured for *any* selected document's Document Type plus
  any field *any* selected document currently holds a value for — since
  selected documents can span different types with different
  `document_type_fields` configurations. A field not common to *every*
  selected document's type renders with the same `.field-orphaned`
  class/hint the single-document Edit form already uses for a field no
  longer configured for a document's current type — here it signals "this
  field doesn't belong to every selected document's type, but applying it
  here still writes it for all of them" (the same underlying mechanic as
  editing a genuinely orphaned field on one document already does), a
  related but distinct meaning from that form's own use of the same class,
  worth keeping straight if this is ever touched again. The union is fixed
  for the life of the form — it is **not** recomputed if the form's own
  Document Type field is changed mid-edit, a deliberate scope cut to avoid
  reconciling against the original per-document union for what would be a
  rare case (changing Document Type as part of the same bulk edit that's
  also setting other fields).
  **The mixed-value indicator** (`bulkScalarMixed()`, `bulkSetMixed()`,
  `refreshBulkMixedHints()`) flags, per field, whether the selected
  documents' *current* values for it already disagree (blank/unset counts as
  one shared value for this comparison — "all blank" isn't mixed, "some set,
  some blank" is) — a field where everyone already agrees gets no hint at
  all. Wording depends on semantics: an additive field on its default Add
  mode gets a purely informational note ("what you enter is added on top,
  nothing is removed"); a replace-semantics field, or an additive field
  switched to Replace mode, gets a real overwrite warning ("checking Apply
  will overwrite ALL of them with the value you enter") — re-evaluated live
  whenever a Tags/person-field mode toggle changes, via a `change` listener
  on every `input[name^="bulk-tags-mode"], input[name^="bulk-field-"]`
  radio, so the hint's wording never lags behind the currently-selected mode.
  **Every DB write for a bulk-edit save is batched into exactly one
  `persistDb()`/`render()` call**, following the same reasoning
  `bulkSetArchived()`/`bulkSetDeleted()`/`bulkSetNeedsReview()` already
  document: looping per-document save functions would re-serialize the whole
  SQLite database once per selected document, which bulk actions exist
  specifically to avoid. Unlike those three functions, though, **a bulk-edit
  save does NOT clear `selectedDocIds`** — editing field values doesn't
  remove a document from the current view the way archiving/deleting/
  flagging can, so keeping the selection lets someone chain a further bulk
  action against the same documents without re-checking every row.
  `saveBulkEdit()` also rewrites every affected document's sidecar `.txt`
  (`sidecarBaseNameFromFilePath()`/`buildSidecarText()`/`writeSidecarFile()`,
  the same three functions `saveEditedDocument()` already uses) from each
  document's complete post-edit in-memory state, not just the fields that
  changed — this has to run after every write block above has already
  updated `d.customFields`/`d.personFieldValues`/`d.tags`/etc. in place, for
  the same reason `saveEditedDocument()`'s own sidecar rewrite is its
  next-to-last step, right before `persistDb()`.
  **The right-click entry point (`showBulkRowContextMenu()`) is mutually
  exclusive with the existing single-document context menu
  (`showRowContextMenu()`) on a per-row basis, not a per-selection one**: the
  existing row `contextmenu` listener branches to the bulk menu only when the
  specific row that was right-clicked is itself checked AND `selectedDocIds`
  has 2+ members — right-clicking an *unchecked* row still shows today's
  single-document menu even while other rows are checked elsewhere, matching
  Finder/Explorer/Gmail's own convention for this exact ambiguity. Unlike
  `showRowContextMenu()`, the bulk branch deliberately does **not** touch
  `selectedDocId`, the detail panel's content, or the single-row `.row-selected`
  highlight — the action targets the whole multi-selection, not specifically
  whichever row happened to be right-clicked, and that row's own checkbox
  already reflects its membership in the selection the menu is about to act
  on. The bulk menu itself is deliberately minimal — just "Edit" — since
  Archive/Delete/Flag for review already have their own buttons in the
  bulk-action bar; duplicating them in the context menu wasn't judged worth
  the extra code for what's already one click away.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the bulk-edit-fields feature in CLAUDE.md"
```
