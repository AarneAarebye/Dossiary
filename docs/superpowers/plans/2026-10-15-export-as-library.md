# Export as Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "More ▾ → Export as library…" turns the selected documents into a new, ready-to-open `<Name>.dossiary` library, copying or moving them, with either only the setup they use or all of it.

**Architecture:** Task 1 builds the new library's database in memory from the open one (`buildExportLibraryDb(srcDb, ids, setupMode)`, sharing row-copy helpers with a generalized `copySetupFrom()`), tested through a debug hook. Task 2 adds the dialog: it copies each document's files into the new folder (4 at a time), writes `library.sqlite` last, removes the folder on Stop/failure, moves exported documents to the Waste bin only after success, and offers to open the new library.

**Tech Stack:** `dossiary.html` (vanilla JS, sql.js, File System Access API); Playwright for Python tests with `tests/stub_studio2.js`.

**Spec:** `docs/superpowers/specs/2026-10-15-export-as-library-design.md`

## Global Constraints

- Single file: all app code in `dossiary.html`; no new dependency.
- sql.js convention: `db.exec()` reads whole tables with **explicit column lists** (no `SELECT *`, no `WHERE`), filtered in JS; writes via `run(sql, params)`. The test stub's `FakeDatabase` only understands this shape.
- Ids are kept in the new library (documents, tags, people, fields, collections, folders).
- Settings never copied by Export as library: `last_backup_at`, `scan_bridge_url`, `scan_last_settings`. Tables never copied: `not_duplicate_groups`, `ocr_jobs`.
- "Only what these documents use": fields with a value/person/snooze on an exported document plus `NON_RENAMEABLE_FIELD_NAMES` (People, Amount, Currency, Payment method, Reminder); `document_type_fields` for exported documents' types limited to those fields; `field_descriptions` for those fields plus `FIELD_DESCRIPTION_BUILTIN_NAMES`; settings minus the excluded three; no Smart Collections.
- "Everything": `copySetupFrom()` with the excluded-settings list above.
- Manual collections holding an exported document, with only exported documents as members; folders of those collections.
- Order: files → `library.sqlite` last → (Move only, after success) Waste bin. Stop/failure/nothing-readable removes the new folder. The open library is never written before the Move step.
- A document whose active file or original can't be read is left out (and stays in this library on Move); preview and sidecar writes are best-effort.
- Every new UI string exists in all six `STRINGS` blocks (en, es, fr, de, zh-Hans, zh-Hant); `tests/test_i18n_coverage.py` must pass.
- Work on a feature branch; merge into main locally when done (push only with the user's OK); then copy `dossiary.html` to `/Applications/Dossiary/dossiary.html`.

---

### Task 1: Build the exported library's database

**Files:**
- Modify: `dossiary.html` — `copySetupFrom()` (near `SETUP_SETTINGS_NOT_COPIED`, ~line 4033); new code right after `copySetupFrom()`.
- Create: `tests/test_export_library.py`

**Interfaces:**
- Produces: `selectRows(srcDb, table, cols) → Array<row>`, `insertRows(dstDb, table, cols, rows)`, `copySetupFrom(srcDb, dstDb = db, settingsNotCopied = SETUP_SETTINGS_NOT_COPIED)`, `EXPORT_SETTINGS_NOT_COPIED`, `DOCUMENT_COLUMNS`, `buildExportLibraryDb(srcDb, ids: number[], setupMode: 'used'|'all') → SQL.Database`, and the test hook `window.__DEBUG_buildExportLibrary(ids, mode) → Uint8Array` (`.export()` of the built database).

- [ ] **Step 1: Write the failing test** — `tests/test_export_library.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Export as library: selected documents become a new <Name>.dossiary library,
# copied or moved, with only the setup they use or all of it.
def doc(i, title, doc_type, file_path, original=None, thumb=None):
    return {
        "id": i, "title": title, "category": "Home", "document_type": doc_type,
        "date": "2026-03-01T00:00:00+00:00", "import_date": f"2026-03-0{i}T00:00:00+00:00",
        "notes": None, "ocr_text": f"text {i}", "ocr_language": None,
        "file_path": file_path, "original_file_path": original, "thumbnail_path": thumb,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 1 if i == 2 else 0, "deleted": 0, "file_hash": f"hash{i}",
    }

SEED = {
    "documents": [
        doc(1, "Invoice", "Invoice", "files/1_a.pdf", "files/1_a/a.pdf", "thumbnails/1.jpg"),
        doc(2, "Letter", "Letter", "files/2_b.pdf"),
        doc(3, "Other", "Other", "files/3_c.pdf"),
    ],
    "tags": [{"id": 1, "name": "tax"}, {"id": 2, "name": "private"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}, {"document_id": 3, "tag_id": 2}],
    "people": [{"id": 1, "name": "Jana"}, {"id": 2, "name": "Arne"}, {"id": 3, "name": "Zed"}],
    "fields": [
        {"id": 1, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 5, "name": "Reminder", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
        {"id": 10, "name": "Organization", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 11, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 12, "name": "Unused", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 13, "name": "Never", "type": "text", "show_as_column": 0, "autocomplete": 1},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 10, "value": "Stadtwerke"},
        {"document_id": 1, "field_id": 2, "value": "12.50"},
        {"document_id": 1, "field_id": 3, "value": "EUR"},
        {"document_id": 3, "field_id": 12, "value": "secret"},
    ],
    "document_field_people": [
        {"document_id": 1, "field_id": 1, "person_id": 1},
        {"document_id": 2, "field_id": 11, "person_id": 2},
        {"document_id": 3, "field_id": 1, "person_id": 3},
    ],
    "document_type_fields": [
        {"document_type": "Invoice", "field_name": "Organization", "position": 0},
        {"document_type": "Invoice", "field_name": "Amount", "position": 1},
        {"document_type": "Invoice", "field_name": "Unused", "position": 2},
        {"document_type": "Letter", "field_name": "Author", "position": 0},
        {"document_type": "Other", "field_name": "Unused", "position": 0},
    ],
    "field_descriptions": [
        {"field_name": "Organization", "description": "Who sent it"},
        {"field_name": "Unused", "description": "x"},
        {"field_name": "Category", "description": "cat hint"},
    ],
    "document_splits": [{"document_id": 1, "position": 0, "category": "Home", "amount": "5.00", "note": ""}],
    "reminder_snoozes": [{"document_id": 1, "field_id": 5, "snoozed_until": "2026-12-01", "dismissed": 0}],
    "collection_folders": [{"id": 1, "name": "Folder A"}, {"id": 2, "name": "Folder B"}],
    "collections": [
        {"id": 1, "name": "Taxes", "kind": "manual", "criteria": None, "folder_id": 1},
        {"id": 2, "name": "Private", "kind": "manual", "criteria": None, "folder_id": None},
        {"id": 3, "name": "Smart", "kind": "smart", "criteria": json.dumps({"match": "all", "rules": []}), "folder_id": 2},
    ],
    "collection_documents": [
        {"collection_id": 1, "document_id": 1}, {"collection_id": 1, "document_id": 3},
        {"collection_id": 2, "document_id": 3},
    ],
    "settings": [
        {"key": "default_currency", "value": "EUR"},
        {"key": "last_backup_at", "value": "2026-01-01T00:00:00Z"},
        {"key": "scan_bridge_url", "value": "http://localhost:9999"},
        {"key": "scan_last_settings", "value": "{}"},
    ],
    "not_duplicate_groups": [{"group_key": "exact:1,3"}],
    "ocr_jobs": [{"document_id": 2, "helper_url": "http://localhost:8766", "job_id": "j", "file_hash": "hash2",
                  "created_at": "2026-03-01T00:00:00Z", "ocr_language": None, "requested_by": "edit"}],  # an Edit-form job counts as pending whatever the scan setting says
}

BUILD_JS = "([ids, mode]) => JSON.parse(new TextDecoder().decode(window.__DEBUG_buildExportLibrary(ids, mode)))"

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'MyLib';")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        # === Scenario 1: "only what these documents use" ===
        used = await page.evaluate(BUILD_JS, [[1, 2], 'used'])
        print("Only the exported documents, ids kept:", sorted(d['id'] for d in used['documents']) == [1, 2])
        print("...with their details:", next(d for d in used['documents'] if d['id'] == 2)['needs_review'] == 1
              and next(d for d in used['documents'] if d['id'] == 1)['file_hash'] == 'hash1')
        print("Only their tags:", [t['name'] for t in used['tags']] == ['tax'])
        print("Only their people:", sorted(x['name'] for x in used['people']) == ['Arne', 'Jana'])
        print("Their custom values, people links, splits and snoozes:",
              sorted({r['document_id'] for r in used['document_field_values']}) == [1]
              and sorted((r['document_id'], r['field_id']) for r in used['document_field_people']) == [(1, 1), (2, 11)]
              and [r['amount'] for r in used['document_splits']] == ['5.00']
              and [(r['document_id'], r['field_id']) for r in used['reminder_snoozes']] == [(1, 5)])
        print("Only used fields plus the built-ins:",
              sorted(f['name'] for f in used['fields']) == ['Amount', 'Author', 'Currency', 'Organization', 'Payment method', 'People', 'Reminder'],
              sorted(f['name'] for f in used['fields']))
        print("Type setup only for exported types and copied fields:",
              sorted((r['document_type'], r['field_name']) for r in used['document_type_fields'])
              == [('Invoice', 'Amount'), ('Invoice', 'Organization'), ('Letter', 'Author')])
        print("Descriptions of copied fields and built-ins:",
              sorted(r['field_name'] for r in used['field_descriptions']) == ['Category', 'Organization'])
        keys = {r['key'] for r in used['settings']}
        print("Settings copied, minus this library's history and scanner:",
              'default_currency' in keys and not keys & {'last_backup_at', 'scan_bridge_url', 'scan_last_settings'})
        print("Manual collections with only exported members, and their folder:",
              [(c['id'], c['name'], c['kind']) for c in used['collections']] == [(1, 'Taxes', 'manual')]
              and [(r['collection_id'], r['document_id']) for r in used['collection_documents']] == [(1, 1)]
              and [f['name'] for f in used['collection_folders']] == ['Folder A'])
        print("No duplicate marks or pending OCR jobs:", used['not_duplicate_groups'] == [] and used['ocr_jobs'] == [])

        # === Scenario 2: "everything from this library" ===
        everything = await page.evaluate(BUILD_JS, [[1, 2], 'all'])
        print("All fields:", sorted(f['name'] for f in everything['fields'])
              == ['Amount', 'Author', 'Currency', 'Never', 'Organization', 'Payment method', 'People', 'Reminder', 'Unused'])
        print("Smart Collections and every folder, plus the exported manual one:",
              sorted((c['id'], c['kind']) for c in everything['collections']) == [(1, 'manual'), (3, 'smart')]
              and sorted(f['id'] for f in everything['collection_folders']) == [1, 2])
        keys = {r['key'] for r in everything['settings']}
        print("...still without history and scanner settings:", not keys & {'last_backup_at', 'scan_bridge_url', 'scan_last_settings'})
        print("Documents are still only the exported ones:", sorted(d['id'] for d in everything['documents']) == [1, 2])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd tests && python3 test_export_library.py`
Expected: a Playwright error (`window.__DEBUG_buildExportLibrary is not a function`).

- [ ] **Step 3: Implement** — in `dossiary.html`, replace `copySetupFrom()` (the whole function, keeping its comment) with:

```js
  // Rows of `table` with explicit columns, read whole and filtered by the
  // caller (the sql.js convention above); [] when the table or a column
  // doesn't exist (an older library).
  function selectRows(srcDb, table, cols){
    try{
      const res = srcDb.exec(`SELECT ${cols.join(', ')} FROM ${table}`);
      return res && res.length ? res[0].values : [];
    }catch(e){ return []; }
  }
  function insertRows(dstDb, table, cols, rows){
    const placeholders = cols.map(() => '?').join(', ');
    for(const row of rows) dstDb.run(`INSERT OR REPLACE INTO ${table} (${cols.join(', ')}) VALUES (${placeholders})`, row);
  }
  // Copies into a fresh, empty database (the global db by default). Field ids
  // are kept, since visible_columns, sort_key and smart collection rules refer
  // to them. Runs before the field migrations, which then find their fields by
  // name and add only what the source lacked. A table the source can't provide
  // (an older library) is skipped.
  function copySetupFrom(srcDb, dstDb = db, settingsNotCopied = SETUP_SETTINGS_NOT_COPIED){
    const copy = (table, cols, keep) => insertRows(dstDb, table, cols, selectRows(srcDb, table, cols).filter(row => !keep || keep(row)));
    copy('fields', ['id', 'name', 'type', 'show_as_column', 'autocomplete']);
    copy('document_type_fields', ['document_type', 'field_name', 'position']);
    copy('field_descriptions', ['field_name', 'description']);
    copy('collection_folders', ['id', 'name']);
    copy('collections', collectionColumns(srcDb), row => row[2] === 'smart');
    copy('settings', ['key', 'value'], row => !settingsNotCopied.includes(row[0]));
  }
  // folder_id is newer than collections itself; an older source lacks it.
  function collectionColumns(srcDb){
    try{ srcDb.exec('SELECT folder_id FROM collections'); return ['id', 'name', 'kind', 'criteria', 'folder_id']; }
    catch(e){ return ['id', 'name', 'kind', 'criteria']; }
  }

  // --- Export as library ---
  // Settings that stay with this library and this computer when documents go
  // to a new library: its backup history, the scanner's address and the last
  // scan settings.
  const EXPORT_SETTINGS_NOT_COPIED = ['last_backup_at', 'scan_bridge_url', 'scan_last_settings'];
  const DOCUMENT_COLUMNS = ['id', 'title', 'category', 'subcategory', 'document_type', 'payment_method', 'amount', 'currency',
    'date', 'import_date', 'notes', 'ocr_text', 'ocr_language', 'file_path', 'original_file_path', 'created_at', 'source',
    'source_legacy_id', 'thumbnail_path', 'archived', 'needs_review', 'deleted', 'searchable_pdf_built', 'file_hash',
    'has_text_layer', 'text_checked', 'thumbnail_hd'];

  // The new library's database for "Export as library": documents `ids` with
  // everything that belongs to them, and setup -- 'used' (fields holding a
  // value on these documents plus the built-ins the migrations would add
  // anyway) or 'all' (what "Copy the setup of" copies). Ids are kept, so every
  // stored path (files/<id>_...) and reference stays valid. Duplicate marks and
  // pending OCR jobs belong to this library and aren't copied.
  function buildExportLibraryDb(srcDb, ids, setupMode){
    const dst = new SQL.Database();
    dst.run(SCHEMA);
    const idSet = new Set(ids);
    const forDocs = (table, cols) => {
      const rows = selectRows(srcDb, table, cols).filter(row => idSet.has(row[0]));
      insertRows(dst, table, cols, rows);
      return rows;
    };
    const docs = forDocs('documents', DOCUMENT_COLUMNS);
    const docTypes = new Set(docs.map(row => row[DOCUMENT_COLUMNS.indexOf('document_type')]).filter(Boolean));
    const docTags = forDocs('document_tags', ['document_id', 'tag_id']);
    const docPeople = forDocs('document_people', ['document_id', 'person_id']);
    const fieldPeople = forDocs('document_field_people', ['document_id', 'field_id', 'person_id']);
    const fieldValues = forDocs('document_field_values', ['document_id', 'field_id', 'value']);
    forDocs('document_splits', ['document_id', 'position', 'category', 'amount', 'note']);
    const snoozes = forDocs('reminder_snoozes', ['document_id', 'field_id', 'snoozed_until', 'dismissed']);

    const tagIds = new Set(docTags.map(row => row[1]));
    insertRows(dst, 'tags', ['id', 'name'], selectRows(srcDb, 'tags', ['id', 'name']).filter(row => tagIds.has(row[0])));
    const personIds = new Set([...docPeople.map(row => row[1]), ...fieldPeople.map(row => row[2])]);
    insertRows(dst, 'people', ['id', 'name'], selectRows(srcDb, 'people', ['id', 'name']).filter(row => personIds.has(row[0])));

    if(setupMode === 'all'){
      copySetupFrom(srcDb, dst, EXPORT_SETTINGS_NOT_COPIED);
    }else{
      const usedFieldIds = new Set([...fieldValues.map(row => row[1]), ...fieldPeople.map(row => row[1]), ...snoozes.map(row => row[1])]);
      const fieldCols = ['id', 'name', 'type', 'show_as_column', 'autocomplete'];
      const fields = selectRows(srcDb, 'fields', fieldCols).filter(row => usedFieldIds.has(row[0]) || NON_RENAMEABLE_FIELD_NAMES.includes(row[1]));
      insertRows(dst, 'fields', fieldCols, fields);
      const fieldNames = new Set(fields.map(row => row[1]));
      insertRows(dst, 'document_type_fields', ['document_type', 'field_name', 'position'],
        selectRows(srcDb, 'document_type_fields', ['document_type', 'field_name', 'position']).filter(row => docTypes.has(row[0]) && fieldNames.has(row[1])));
      insertRows(dst, 'field_descriptions', ['field_name', 'description'],
        selectRows(srcDb, 'field_descriptions', ['field_name', 'description']).filter(row => fieldNames.has(row[0]) || FIELD_DESCRIPTION_BUILTIN_NAMES.includes(row[0])));
      insertRows(dst, 'settings', ['key', 'value'],
        selectRows(srcDb, 'settings', ['key', 'value']).filter(row => !EXPORT_SETTINGS_NOT_COPIED.includes(row[0])));
    }

    // Manual collections holding an exported document, with only those documents.
    const memberships = selectRows(srcDb, 'collection_documents', ['collection_id', 'document_id']).filter(row => idSet.has(row[1]));
    const memberOf = new Set(memberships.map(row => row[0]));
    const collCols = collectionColumns(srcDb);
    const manual = selectRows(srcDb, 'collections', collCols).filter(row => row[2] === 'manual' && memberOf.has(row[0]));
    insertRows(dst, 'collections', collCols, manual);
    insertRows(dst, 'collection_documents', ['collection_id', 'document_id'], memberships);
    if(setupMode !== 'all'){ // 'all' already copied every folder
      const folderIds = new Set(manual.map(row => row[4]).filter(v => v != null));
      insertRows(dst, 'collection_folders', ['id', 'name'], selectRows(srcDb, 'collection_folders', ['id', 'name']).filter(row => folderIds.has(row[0])));
    }
    return dst;
  }
  window.__DEBUG_buildExportLibrary = (ids, mode) => buildExportLibraryDb(db, ids, mode).export(); // test-only hook (tests/test_export_library.py)
```

Note `NON_RENAMEABLE_FIELD_NAMES` and `FIELD_DESCRIPTION_BUILTIN_NAMES` are `const`s declared later in the file; they're only read when `buildExportLibraryDb()` runs, long after the script has finished loading, so the order is fine.

- [ ] **Step 4: Run the test, then the setup-copy test (copySetupFrom() changed)**

Run: `cd tests && python3 test_export_library.py && python3 test_copy_setup.py`
Expected: every printed check `True`, `JS ERRORS: []` in both.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_export_library.py
git commit -m "Export as library: build the new library's database (used setup or all)"
```

---

### Task 2: The dialog, file copy, Move and Open

**Files:**
- Modify: `dossiary.html` — More menu markup (after `#bulk-share-btn`, ~line 1012); `let backupRunning` area (~line 2973); `onModalKeydown()` (~line 7748); `writeSidecarForDoc()` (~line 10192); new modal code after `openBackupModal()`; the listener block (after `el('bulk-share-btn').addEventListener`, ~line 14377); six `STRINGS` blocks.
- Modify: `tests/test_export_library.py` (add scenarios before `print("JS ERRORS:"...)`)
- Modify: `README.md`, `README.de.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: `buildExportLibraryDb(srcDb, ids, setupMode)` from Task 1.
- Produces: `openExportLibraryModal(ids)`, `sidecarTextForDoc(d) → string`, `exportLibraryRunning` flag.

- [ ] **Step 1: Add the UI scenarios to the test** — insert before `print("JS ERRORS:", errors)`:

```python
        # Files for the UI scenarios
        await page.evaluate("""
            async () => {
                const put = async (path, text) => {
                    const parts = path.split('/');
                    let dir = window.__TEST_ROOT;
                    for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                    const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
                    await w.write(new TextEncoder().encode(text)); await w.close();
                };
                await put('files/1_a.pdf', 'active 1');
                await put('files/1_a/a.pdf', 'original 1');
                await put('thumbnails/1.jpg', 'thumb 1');
                await put('files/2_b.pdf', 'active 2');
                await put('files/3_c.pdf', 'active 3');
                window.__EXPORT_PARENT = window.__makeEmptyRoot();
                window.__EXPORT_PARENT.name = 'Outside';
            }
        """)
        LIST_IN = """async (name) => {
            const out = [];
            const walk = async (dir, prefix) => {
                for await (const [n, h] of dir.entries()){
                    if(h.kind === 'directory') await walk(h, prefix + n + '/');
                    else out.push(prefix + n);
                }
            };
            await walk(await window.__EXPORT_PARENT.getDirectoryHandle(name), '');
            return out.sort();
        }"""
        PARENT_NAMES = "async () => { const n = []; for await (const [k] of window.__EXPORT_PARENT.entries()) n.push(k); return n.sort(); }"
        SOURCE_DB = "async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())"

        async def open_dialog(ids):
            await page.click('#nav-item-all')
            await page.wait_for_timeout(150)
            for i in ids:
                await page.check(f'tr[data-id="{i}"] .row-select-checkbox')
            await page.click('#bulk-more-btn')
            await page.click('#bulk-export-library-btn')
            await page.wait_for_timeout(300)

        # === Scenario 3: the dialog's defaults, and the library's own folder is refused ===
        await open_dialog([1, 2])
        print("Default name is the library's plus (export):", await page.input_value('#export-library-name') == 'MyLib (export)')
        print("Hint names the new folder:", 'MyLib (export).dossiary' in await page.inner_text('#export-library-hint'))
        print("Copy and 'only what's used' are the defaults:",
              await page.is_checked('input[name="export-library-mode"][value="copy"]')
              and await page.is_checked('input[name="export-library-setup"][value="used"]'))
        print("Pending OCR is mentioned:", '1' in await page.inner_text('#export-library-ocr-note'))
        await page.check('input[name="export-library-mode"][value="move"]')
        print("Move explains the Waste bin:", await page.is_visible('#export-library-move-note'))
        await page.check('input[name="export-library-mode"][value="copy"]')
        await page.evaluate("async () => { window.__NEXT_PICKED_DIR = await window.__TEST_ROOT.getDirectoryHandle('files'); }")
        await page.click('#export-library-start-btn')
        await page.wait_for_timeout(300)
        print("A folder inside the library is refused:", 'inside' in await page.inner_text('#export-library-status'))

        # === Scenario 4: Copy writes a complete library; this one is unchanged ===
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT; }")
        await page.click('#export-library-start-btn')
        await page.wait_for_timeout(1000)
        print("One new .dossiary folder:", await page.evaluate(PARENT_NAMES) == ['MyLib (export).dossiary'])
        files = await page.evaluate(LIST_IN, 'MyLib (export).dossiary')
        print("Files, originals, previews and fresh sidecars at the same paths:",
              files == ['files/1_a.pdf', 'files/1_a.txt', 'files/1_a/a.pdf', 'files/2_b.pdf', 'files/2_b.txt', 'library.sqlite', 'thumbnails/1.jpg'], files)
        new_db = await page.evaluate("async () => JSON.parse(await (await (await (await window.__EXPORT_PARENT.getDirectoryHandle('MyLib (export).dossiary')).getFileHandle('library.sqlite')).getFile()).text())")
        print("Its database holds the two documents:", sorted(d['id'] for d in new_db['documents']) == [1, 2])
        sidecar = await page.evaluate("async () => (await (await (await (await (await window.__EXPORT_PARENT.getDirectoryHandle('MyLib (export).dossiary')).getDirectoryHandle('files')).getFileHandle('1_a.txt')).getFile()).text())")
        print("The sidecar carries the details:", 'Invoice' in sidecar and 'tax' in sidecar)
        status = await page.inner_text('#export-library-status')
        print("Summary:", 'Documents exported: 2' in status and 'Outside/MyLib (export).dossiary' in status, repr(status))
        src = await page.evaluate(SOURCE_DB)
        print("Copy leaves this library unchanged:", all(not d['deleted'] for d in src['documents']))
        print("'Open it' is offered:", await page.is_visible('#export-library-open-btn'))
        await page.click('#export-library-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 5: an existing folder name is refused ===
        await open_dialog([1])
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT; }")
        await page.click('#export-library-start-btn')
        await page.wait_for_timeout(300)
        print("An existing folder is never reused:", 'already a folder' in await page.inner_text('#export-library-status'))

        # === Scenario 6: Stop removes the incomplete library; Escape can't close mid-copy ===
        await page.fill('#export-library-name', 'Stopped')
        await page.evaluate("""async () => {
            const h = await (await window.__TEST_ROOT.getDirectoryHandle('files')).getFileHandle('1_a.pdf');
            const orig = h.getFile.bind(h);
            h.getFile = async () => { await new Promise(r => setTimeout(r, 1200)); h.getFile = orig; return orig(); };
            window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT;
        }""")
        await page.click('#export-library-start-btn')
        await page.wait_for_timeout(300)
        await page.keyboard.press('Escape')
        print("Dialog can't be closed while exporting:", await page.locator('#export-library-status').count() == 1)
        await page.click('#export-library-stop-btn')
        await page.wait_for_timeout(1800)
        print("Stopping removes the incomplete library:",
              await page.evaluate(PARENT_NAMES) == ['MyLib (export).dossiary'] and 'removed' in await page.inner_text('#export-library-status'))
        await page.click('#export-library-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 7: Move, with one document's file missing ===
        await page.evaluate("async () => { await (await window.__TEST_ROOT.getDirectoryHandle('files')).removeEntry('2_b.pdf'); }")
        await open_dialog([1, 2])
        await page.fill('#export-library-name', 'Moved')
        await page.check('input[name="export-library-mode"][value="move"]')
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT; }")
        await page.click('#export-library-start-btn')
        await page.wait_for_timeout(1000)
        moved_db = await page.evaluate("async () => JSON.parse(await (await (await (await window.__EXPORT_PARENT.getDirectoryHandle('Moved.dossiary')).getFileHandle('library.sqlite')).getFile()).text())")
        print("The unreadable document is left out:", [d['id'] for d in moved_db['documents']] == [1])
        status = await page.inner_text('#export-library-status')
        print("...and listed:", 'Left out' in status and 'Letter' in status, repr(status))
        src = await page.evaluate(SOURCE_DB)
        flags = {d['id']: d['deleted'] for d in src['documents']}
        print("Moved document goes to the Waste bin; the left-out one stays:", flags[1] == 1 and not flags[2] and not flags[3], flags)
        print("Summary counts the move:", 'Moved to the Waste bin here: 1' in status)

        # === Scenario 8: Open it switches to the new library ===
        await page.click('#export-library-open-btn')
        await page.wait_for_timeout(700)
        print("The new library is open:", 'Moved.dossiary' in await page.inner_text('#sub-label'))
        print("...showing the exported document:", await page.locator('tr[data-id="1"]').count() == 1 and await page.locator('tr[data-id="2"]').count() == 0)
```

- [ ] **Step 2: Run it to verify the new scenarios fail**

Run: `cd tests && python3 test_export_library.py`
Expected: scenarios 1-2 still `True`; then a timeout clicking `#bulk-export-library-btn`.

- [ ] **Step 3: Menu item, running flag, Escape guard**

After the `#bulk-share-btn` button in the More menu markup add:

```html
            <button type="button" class="bulk-collection-option" id="bulk-export-library-btn" data-i18n="exportLibraryAction">Export as library…</button>
```

After `let backupRunning = false; ...` add:

```js
  let exportLibraryRunning = false; // Export as library is writing -- blocks closing its dialog
```

In `onModalKeydown()` add `&& !exportLibraryRunning` next to `!backupRunning`.

After `el('bulk-share-btn').addEventListener(...)` add:

```js
  el('bulk-export-library-btn').addEventListener('click', () => openExportLibraryModal([...selectedDocIds]));
```

- [ ] **Step 4: Sidecar text helper** — replace `writeSidecarForDoc()` with:

```js
  // A document's sidecar text from its in-memory state.
  function sidecarTextForDoc(d){
    const otherPersonFields = { ...(d.personFieldValues || {}) };
    delete otherPersonFields['People'];
    return buildSidecarText({
      title: d.title, category: d.category, subcategory: d.subcategory, documentType: d.document_type,
      date: d.date, importDate: d.import_date, customFields: d.customFields || {}, personFields: otherPersonFields,
      people: d.people || [], notes: d.notes, ocrText: d.ocr_text, tags: d.tags || [], splits: d.splits || [],
    });
  }
  // Rewrites a document's sidecar .txt from its current in-memory state (d is
  // already updated). Shared by every path that changes metadata outside the
  // Edit form: bulk edit, "Make searchable", renaming a field.
  async function writeSidecarForDoc(d){
    const sidecarBaseName = sidecarBaseNameFromFilePath(d.file_path);
    if(!sidecarBaseName) return;
    await writeSidecarFile(sidecarBaseName, sidecarTextForDoc(d));
  }
```

- [ ] **Step 5: The dialog** — add right after `openBackupModal()`'s closing brace:

```js
  // --- Export as library (dialog) ---
  // Copies (or moves) the selected documents into a new <Name>.dossiary
  // library: files first, 4 documents at a time (iCloud downloads overlap),
  // library.sqlite last so a half-written folder never looks like a library,
  // and only then -- for Move -- the documents go to this library's Waste bin.
  // Stop, a failure, or nothing readable removes the new folder. A document
  // whose file or original can't be read is left out and listed.
  function exportLibraryDefaultName(){
    return `${rootDirHandle.name.replace(/\.dossiary$/i, '')} ${t('exportLibraryNameSuffix')}`;
  }
  function openExportLibraryModal(ids){
    const docs = ids.map(id => allDocs.find(x => x.id === id)).filter(d => d && !d.deleted);
    if(!docs.length) return;
    const pendingOcr = docs.filter(d => isOcrPendingDoc(d.id)).length;
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <h2>${t('exportLibraryTitle')}</h2>
          <p>${t('exportLibraryIntro')}</p>
          <div class="field">
            <label for="export-library-name">${t('newLibraryNameLabel')}</label>
            <input type="text" id="export-library-name" value="${escapeHtml(exportLibraryDefaultName())}" />
            <div class="field-hint" id="export-library-hint"></div>
          </div>
          <div class="field">
            <label>${t('exportLibraryModeLabel')}</label>
            <label class="show-archived-toggle"><input type="radio" name="export-library-mode" value="copy" checked /> ${t('exportLibraryCopy')}</label>
            <label class="show-archived-toggle"><input type="radio" name="export-library-mode" value="move" /> ${t('exportLibraryMove')}</label>
            <div class="field-hint" id="export-library-move-note" style="display:none;">${t('exportLibraryMoveNote')}</div>
          </div>
          <div class="field">
            <label>${t('exportLibrarySetupLabel')}</label>
            <label class="show-archived-toggle"><input type="radio" name="export-library-setup" value="used" checked /> ${t('exportLibrarySetupUsed')}</label>
            <label class="show-archived-toggle"><input type="radio" name="export-library-setup" value="all" /> ${t('exportLibrarySetupAll')}</label>
          </div>
          <p class="doc-sub" id="export-library-size">${escapeHtml(t('exportLibraryCount', {count: docs.length}))}</p>
          ${pendingOcr ? `<p class="doc-sub" id="export-library-ocr-note">${escapeHtml(t('exportLibraryOcrPending', {count: pendingOcr}))}</p>` : ''}
          <div class="status" id="export-library-status"></div>
          <div class="modal-actions">
            <button class="primary" id="export-library-start-btn">${t('exportLibraryStart')}</button>
            <button class="primary" id="export-library-open-btn" style="display:none;">${t('exportLibraryOpen')}</button>
            <button id="export-library-stop-btn" style="display:none;">${t('duplicatesBackfillStopBtn')}</button>
            <button id="export-library-cancel-btn">${t('commonCancel')}</button>
          </div>
        </div>
      </div>
    `;
    const tryClose = () => { if(!exportLibraryRunning) closeModal(); };
    el('modal-close-btn').addEventListener('click', tryClose);
    el('export-library-cancel-btn').addEventListener('click', tryClose);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') tryClose(); });
    document.addEventListener('keydown', onModalKeydown);

    const nameInput = el('export-library-name');
    const updateHint = () => {
      const raw = nameInput.value.trim();
      el('export-library-hint').textContent = raw ? t('exportLibraryHint', {name: libraryFolderName(raw)}) : '';
    };
    nameInput.addEventListener('input', updateHint);
    updateHint();
    document.querySelectorAll('input[name="export-library-mode"]').forEach(r => r.addEventListener('change', () => {
      el('export-library-move-note').style.display = document.querySelector('input[name="export-library-mode"]:checked').value === 'move' ? '' : 'none';
    }));
    // Total size: a metadata read per file, filled in when it's known.
    (async () => {
      let total = 0;
      for(const d of docs){
        for(const path of [d.file_path, d.original_file_path]){
          if(!path) continue;
          try{ total += (await (await resolveFileHandle(path, false)).getFile()).size; }catch(e){ /* not counted */ }
        }
      }
      const sizeEl = el('export-library-size');
      if(sizeEl) sizeEl.textContent = t('exportLibraryCountSize', {count: docs.length, size: formatBytes(total)});
    })();

    let stopRequested = false;
    let dest = null;
    el('export-library-stop-btn').addEventListener('click', (e) => { stopRequested = true; e.currentTarget.disabled = true; });
    el('export-library-open-btn').addEventListener('click', async () => {
      const handle = dest;
      closeModal();
      resetAll();
      await proceedWithRootDirHandle(handle);
    });
    el('export-library-start-btn').addEventListener('click', async () => {
      const statusEl = el('export-library-status');
      const fail = (text) => { statusEl.className = 'status err'; statusEl.textContent = text; };
      const raw = nameInput.value.trim();
      if(!raw || /[\/\\:*?"<>|]/.test(raw) || raw.startsWith('.')) return fail(t('newLibraryNameInvalid'));
      const folderName = libraryFolderName(raw);
      let parent;
      try{ parent = await window.showDirectoryPicker({ mode: 'readwrite' }); }
      catch(e){ return; } // picker cancelled
      if(await isInsideLibrary(parent)) return fail(t('backupInsideLibrary'));
      let exists = false;
      try{ await parent.getDirectoryHandle(folderName); exists = true; }catch(e){ /* free */ }
      if(exists) return fail(t('newLibraryExists', {name: folderName}));
      const move = document.querySelector('input[name="export-library-mode"]:checked').value === 'move';
      const setupMode = document.querySelector('input[name="export-library-setup"]:checked').value;

      const startBtn = el('export-library-start-btn'), cancelBtn = el('export-library-cancel-btn'), stopBtn = el('export-library-stop-btn');
      startBtn.disabled = cancelBtn.disabled = nameInput.disabled = true;
      document.querySelectorAll('input[name^="export-library-"]').forEach(r => { r.disabled = true; });
      stopBtn.style.display = '';
      el('modal-close-btn').disabled = true;
      exportLibraryRunning = true;
      statusEl.className = 'status busy';
      statusEl.innerHTML = '<span class="spinner"></span> ' + escapeHtml(t('exportLibraryProgress', {done: 0, total: docs.length}));

      const exported = new Set(), leftOut = [];
      let outcome = 'done', errorMessage = '', moveError = '';
      try{
        dest = await parent.getDirectoryHandle(folderName, { create: true });
        await dest.getDirectoryHandle('files', { create: true });
        await dest.getDirectoryHandle('inbox', { create: true });
        const writeTo = async (path, data) => {
          const parts = path.split('/');
          let dir = dest;
          for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
          const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
          await w.write(data);
          await w.close();
        };
        const readPath = (path) => withFileOp('read', path, async () => (await (await resolveFileHandle(path, false)).getFile()).arrayBuffer());
        let next = 0, done = 0;
        const worker = async () => {
          while(!stopRequested && next < docs.length){
            const d = docs[next++];
            try{
              // Both read before anything is written, so a document left out
              // leaves no files behind in the new library.
              const main = d.file_path ? await readPath(d.file_path) : null;
              const original = d.original_file_path ? await readPath(d.original_file_path) : null;
              if(main) await writeTo(d.file_path, main);
              if(original) await writeTo(d.original_file_path, original);
              if(d.thumbnail_path){ try{ await writeTo(d.thumbnail_path, await readPath(d.thumbnail_path)); }catch(e){ /* best-effort */ } }
              const stem = sidecarBaseNameFromFilePath(d.file_path);
              if(stem){ try{ await writeTo(`files/${stem}.txt`, sidecarTextForDoc(d)); }catch(e){ /* best-effort */ } }
              exported.add(d.id);
            }catch(e){
              if(!e.fileOp){ stopRequested = true; throw e; } // the new folder can't be written: give up
              leftOut.push({ d, reason: fileErrorText(e, 'exportLibraryError') });
            }
            done++;
            statusEl.innerHTML = '<span class="spinner"></span> ' + escapeHtml(t('exportLibraryProgress', {done, total: docs.length}));
          }
        };
        await Promise.all(Array.from({length: Math.min(4, docs.length)}, worker));
        if(stopRequested) outcome = 'stopped';
        else if(!exported.size) outcome = 'nothing';
        else await writeTo('library.sqlite', buildExportLibraryDb(db, docs.map(d => d.id).filter(id => exported.has(id)), setupMode).export());
      }catch(e){
        outcome = 'error';
        errorMessage = e.message;
      }
      if(outcome !== 'done' && dest){
        // A partial copy isn't a library -- don't leave one around looking like it.
        try{ await parent.removeEntry(folderName, { recursive: true }); }catch(e){}
        dest = null;
      }
      let moved = 0;
      if(outcome === 'done'){
        recordRecentLibrary(dest).catch(() => {});
        if(move){
          const ids = [...exported];
          try{ await bulkSetDeleted(ids, true); moved = ids.length; }
          catch(e){
            moveError = e.message;
            ids.forEach(id => { db.run('UPDATE documents SET deleted = ? WHERE id = ?', [0, id]); const d = allDocs.find(x => x.id === id); if(d) d.deleted = false; });
            render();
          }
        }
      }
      exportLibraryRunning = false;
      el('modal-close-btn').disabled = false;
      stopBtn.style.display = 'none';
      startBtn.style.display = 'none';
      cancelBtn.disabled = false;
      cancelBtn.textContent = t('detailCloseAriaLabel');
      if(outcome === 'done'){
        const lines = [t('exportLibraryDone', {folder: `${parent.name}/${folderName}`}), t('exportLibraryExported', {count: exported.size})];
        if(leftOut.length) lines.push(t('exportLibraryLeftOut', {count: leftOut.length}));
        if(moved) lines.push(t('exportLibraryMoved', {count: moved}));
        if(moveError) lines.push(t('exportLibraryMoveSaveFailed', {error: moveError}));
        statusEl.className = 'status ' + (leftOut.length || moveError ? 'err' : 'ok');
        statusEl.innerHTML = lines.map(escapeHtml).join('<br>')
          + (leftOut.length ? `<ul id="export-library-left-out">${leftOut.map(({d, reason}) => `<li>${escapeHtml(displayName(d))}: ${escapeHtml(reason)}</li>`).join('')}</ul>` : '');
        el('export-library-open-btn').style.display = '';
      }else if(outcome === 'stopped'){
        fail(t('exportLibraryStopped'));
      }else if(outcome === 'nothing'){
        fail(t('exportLibraryNothing'));
      }else{
        fail(t('exportLibraryError', {error: errorMessage}));
      }
    });
  }
```

- [ ] **Step 6: Strings** — add to each `STRINGS` block, right after that block's `shareAction: '…',` entry (keep each on as few lines as the surrounding entries use):

English (`STRINGS.en`):
```js
      exportLibraryAction: 'Export as library…', exportLibraryTitle: 'Export as library', exportLibraryIntro: 'Makes a new Dossiary library from the selected documents, ready to open. You choose where to create it after clicking Export library.', exportLibraryNameSuffix: '(export)', exportLibraryHint: 'Creates the folder “{name}” in the folder you choose.', exportLibraryModeLabel: 'Documents', exportLibraryCopy: 'Copy them — this library stays as it is', exportLibraryMove: 'Move them', exportLibraryMoveNote: 'The documents go to the Waste bin here once the new library has been written. Restoring them from the Waste bin undoes it.', exportLibrarySetupLabel: 'Setup', exportLibrarySetupUsed: 'Only what these documents use', exportLibrarySetupAll: 'Everything from this library', exportLibraryCount: 'Documents: {count}', exportLibraryCountSize: 'Documents: {count} ({size})', exportLibraryOcrPending: 'Still being made searchable: {count}. They are exported as they are now.', exportLibraryStart: 'Export library', exportLibraryProgress: 'Copying documents: {done} of {total}', exportLibraryStopped: 'Stopped. The incomplete library was removed.', exportLibraryError: 'Export failed: {error}. The incomplete library was removed.', exportLibraryNothing: 'None of the documents could be read, so no library was made.', exportLibraryDone: 'Created “{folder}”.', exportLibraryExported: 'Documents exported: {count}', exportLibraryLeftOut: 'Left out because a file couldn’t be read: {count}', exportLibraryMoved: 'Moved to the Waste bin here: {count}', exportLibraryMoveSaveFailed: 'The documents couldn’t be moved to the Waste bin here ({error}). The new library is complete, and the documents are still in this library too.', exportLibraryOpen: 'Open it',
```

Spanish (`STRINGS.es`):
```js
      exportLibraryAction: 'Exportar como biblioteca…', exportLibraryTitle: 'Exportar como biblioteca', exportLibraryIntro: 'Crea una nueva biblioteca de Dossiary con los documentos seleccionados, lista para abrir. Eliges dónde crearla después de pulsar Exportar biblioteca.', exportLibraryNameSuffix: '(exportación)', exportLibraryHint: 'Crea la carpeta «{name}» en la carpeta que elijas.', exportLibraryModeLabel: 'Documentos', exportLibraryCopy: 'Copiarlos: esta biblioteca no cambia', exportLibraryMove: 'Moverlos', exportLibraryMoveNote: 'Los documentos van a la Papelera aquí en cuanto se haya escrito la nueva biblioteca. Restaurarlos desde la Papelera lo deshace.', exportLibrarySetupLabel: 'Configuración', exportLibrarySetupUsed: 'Solo lo que usan estos documentos', exportLibrarySetupAll: 'Todo lo de esta biblioteca', exportLibraryCount: 'Documentos: {count}', exportLibraryCountSize: 'Documentos: {count} ({size})', exportLibraryOcrPending: 'Aún se están haciendo buscables: {count}. Se exportan tal como están ahora.', exportLibraryStart: 'Exportar biblioteca', exportLibraryProgress: 'Copiando documentos: {done} de {total}', exportLibraryStopped: 'Detenido. Se eliminó la biblioteca incompleta.', exportLibraryError: 'La exportación falló: {error}. Se eliminó la biblioteca incompleta.', exportLibraryNothing: 'No se pudo leer ninguno de los documentos, así que no se creó ninguna biblioteca.', exportLibraryDone: 'Creada «{folder}».', exportLibraryExported: 'Documentos exportados: {count}', exportLibraryLeftOut: 'Omitidos porque no se pudo leer un archivo: {count}', exportLibraryMoved: 'Movidos a la Papelera aquí: {count}', exportLibraryMoveSaveFailed: 'No se pudieron mover los documentos a la Papelera aquí ({error}). La nueva biblioteca está completa y los documentos siguen también en esta biblioteca.', exportLibraryOpen: 'Abrirla',
```

French (`STRINGS.fr`):
```js
      exportLibraryAction: 'Exporter en bibliothèque…', exportLibraryTitle: 'Exporter en bibliothèque', exportLibraryIntro: 'Crée une nouvelle bibliothèque Dossiary à partir des documents sélectionnés, prête à ouvrir. Vous choisissez où la créer après avoir cliqué sur Exporter la bibliothèque.', exportLibraryNameSuffix: '(export)', exportLibraryHint: 'Crée le dossier « {name} » dans le dossier que vous choisissez.', exportLibraryModeLabel: 'Documents', exportLibraryCopy: 'Les copier — cette bibliothèque reste telle quelle', exportLibraryMove: 'Les déplacer', exportLibraryMoveNote: 'Les documents vont dans la Corbeille ici une fois la nouvelle bibliothèque écrite. Les restaurer depuis la Corbeille annule l’opération.', exportLibrarySetupLabel: 'Configuration', exportLibrarySetupUsed: 'Seulement ce qu’utilisent ces documents', exportLibrarySetupAll: 'Tout ce que contient cette bibliothèque', exportLibraryCount: 'Documents : {count}', exportLibraryCountSize: 'Documents : {count} ({size})', exportLibraryOcrPending: 'Encore en cours de rendu interrogeable : {count}. Ils sont exportés dans leur état actuel.', exportLibraryStart: 'Exporter la bibliothèque', exportLibraryProgress: 'Copie des documents : {done} sur {total}', exportLibraryStopped: 'Arrêté. La bibliothèque incomplète a été supprimée.', exportLibraryError: 'L’export a échoué : {error}. La bibliothèque incomplète a été supprimée.', exportLibraryNothing: 'Aucun des documents n’a pu être lu, aucune bibliothèque n’a donc été créée.', exportLibraryDone: '« {folder} » créé.', exportLibraryExported: 'Documents exportés : {count}', exportLibraryLeftOut: 'Écartés car un fichier n’a pas pu être lu : {count}', exportLibraryMoved: 'Déplacés dans la Corbeille ici : {count}', exportLibraryMoveSaveFailed: 'Les documents n’ont pas pu être déplacés dans la Corbeille ici ({error}). La nouvelle bibliothèque est complète, et les documents sont aussi toujours dans cette bibliothèque.', exportLibraryOpen: 'L’ouvrir',
```

German (`STRINGS.de`):
```js
      exportLibraryAction: 'Als Bibliothek exportieren…', exportLibraryTitle: 'Als Bibliothek exportieren', exportLibraryIntro: 'Erstellt aus den ausgewählten Dokumenten eine neue Dossiary-Bibliothek, die sich sofort öffnen lässt. Wo sie angelegt wird, wählst du nach Klick auf „Bibliothek exportieren“.', exportLibraryNameSuffix: '(Export)', exportLibraryHint: 'Legt den Ordner „{name}“ in dem Ordner an, den du wählst.', exportLibraryModeLabel: 'Dokumente', exportLibraryCopy: 'Kopieren – diese Bibliothek bleibt, wie sie ist', exportLibraryMove: 'Verschieben', exportLibraryMoveNote: 'Die Dokumente kommen hier in den Papierkorb, sobald die neue Bibliothek geschrieben ist. Wiederherstellen aus dem Papierkorb macht es rückgängig.', exportLibrarySetupLabel: 'Einrichtung', exportLibrarySetupUsed: 'Nur was diese Dokumente nutzen', exportLibrarySetupAll: 'Alles aus dieser Bibliothek', exportLibraryCount: 'Dokumente: {count}', exportLibraryCountSize: 'Dokumente: {count} ({size})', exportLibraryOcrPending: 'Werden noch durchsuchbar gemacht: {count}. Sie werden so exportiert, wie sie jetzt sind.', exportLibraryStart: 'Bibliothek exportieren', exportLibraryProgress: 'Dokumente werden kopiert: {done} von {total}', exportLibraryStopped: 'Angehalten. Die unvollständige Bibliothek wurde entfernt.', exportLibraryError: 'Export fehlgeschlagen: {error}. Die unvollständige Bibliothek wurde entfernt.', exportLibraryNothing: 'Keines der Dokumente konnte gelesen werden, daher wurde keine Bibliothek angelegt.', exportLibraryDone: '„{folder}“ angelegt.', exportLibraryExported: 'Exportierte Dokumente: {count}', exportLibraryLeftOut: 'Ausgelassen, weil eine Datei nicht lesbar war: {count}', exportLibraryMoved: 'Hier in den Papierkorb verschoben: {count}', exportLibraryMoveSaveFailed: 'Die Dokumente konnten hier nicht in den Papierkorb verschoben werden ({error}). Die neue Bibliothek ist vollständig, und die Dokumente sind auch weiterhin in dieser Bibliothek.', exportLibraryOpen: 'Öffnen',
```

Chinese Simplified (`STRINGS['zh-Hans']`):
```js
      exportLibraryAction: '导出为资料库…', exportLibraryTitle: '导出为资料库', exportLibraryIntro: '用所选文档创建一个可直接打开的新 Dossiary 资料库。点击“导出资料库”后再选择创建位置。', exportLibraryNameSuffix: '（导出）', exportLibraryHint: '将在你选择的文件夹中创建文件夹“{name}”。', exportLibraryModeLabel: '文档', exportLibraryCopy: '复制——此资料库保持不变', exportLibraryMove: '移动', exportLibraryMoveNote: '新资料库写入完成后，这些文档会移到此处的回收站。从回收站恢复即可撤销。', exportLibrarySetupLabel: '设置', exportLibrarySetupUsed: '仅这些文档用到的内容', exportLibrarySetupAll: '此资料库的全部内容', exportLibraryCount: '文档：{count}', exportLibraryCountSize: '文档：{count}（{size}）', exportLibraryOcrPending: '仍在设为可搜索：{count}。将按当前状态导出。', exportLibraryStart: '导出资料库', exportLibraryProgress: '正在复制文档：{done} / {total}', exportLibraryStopped: '已停止。不完整的资料库已删除。', exportLibraryError: '导出失败：{error}。不完整的资料库已删除。', exportLibraryNothing: '所有文档都无法读取，因此没有创建资料库。', exportLibraryDone: '已创建“{folder}”。', exportLibraryExported: '已导出的文档：{count}', exportLibraryLeftOut: '因文件无法读取而略过：{count}', exportLibraryMoved: '已移到此处的回收站：{count}', exportLibraryMoveSaveFailed: '无法将这些文档移到此处的回收站（{error}）。新资料库已完整，这些文档也仍在此资料库中。', exportLibraryOpen: '打开',
```

Chinese Traditional (`STRINGS['zh-Hant']`, the same text converted with OpenCC s2t as the rest of this block):
```js
      exportLibraryAction: '導出為資料庫…', exportLibraryTitle: '導出為資料庫', exportLibraryIntro: '用所選文檔創建一個可直接打開的新 Dossiary 資料庫。點擊「導出資料庫」後再選擇創建位置。', exportLibraryNameSuffix: '（導出）', exportLibraryHint: '將在你選擇的文件夾中創建文件夾「{name}」。', exportLibraryModeLabel: '文檔', exportLibraryCopy: '複製——此資料庫保持不變', exportLibraryMove: '移動', exportLibraryMoveNote: '新資料庫寫入完成後，這些文檔會移到此處的回收站。從回收站恢復即可撤銷。', exportLibrarySetupLabel: '設置', exportLibrarySetupUsed: '僅這些文檔用到的內容', exportLibrarySetupAll: '此資料庫的全部內容', exportLibraryCount: '文檔：{count}', exportLibraryCountSize: '文檔：{count}（{size}）', exportLibraryOcrPending: '仍在設為可搜索：{count}。將按當前狀態導出。', exportLibraryStart: '導出資料庫', exportLibraryProgress: '正在複製文檔：{done} / {total}', exportLibraryStopped: '已停止。不完整的資料庫已刪除。', exportLibraryError: '導出失敗：{error}。不完整的資料庫已刪除。', exportLibraryNothing: '所有文檔都無法讀取，因此沒有創建資料庫。', exportLibraryDone: '已創建「{folder}」。', exportLibraryExported: '已導出的文檔：{count}', exportLibraryLeftOut: '因文件無法讀取而略過：{count}', exportLibraryMoved: '已移到此處的回收站：{count}', exportLibraryMoveSaveFailed: '無法將這些文檔移到此處的回收站（{error}）。新資料庫已完整，這些文檔也仍在此資料庫中。', exportLibraryOpen: '打開',
```

- [ ] **Step 7: Run the tests**

Run: `cd tests && python3 test_export_library.py && python3 test_i18n_coverage.py && python3 test_export.py && python3 test_backup.py && python3 test_copy_setup.py`
Expected: every printed check `True`, `JS ERRORS: []`, and the coverage check passing.

- [ ] **Step 8: Docs**

`README.md`, after the **Export** bullet:

```markdown
- **Export as library** — select documents and choose **More ▾ → Export as
  library…** to make a new, ready-to-open `<Name>.dossiary` library from
  them: to hand documents to someone, or to split a library. **Copy** leaves
  this library as it is; **Move** puts the documents in this library's Waste
  bin once the new library is written (restoring them undoes it). The new
  library gets only the fields and settings these documents use, or
  everything from this library if you choose. A document whose file can't
  be read is left out and listed.
```

`README.de.md`, after its Export bullet:

```markdown
- **Als Bibliothek exportieren** — Dokumente auswählen und **Mehr ▾ → Als
  Bibliothek exportieren…** wählen: Daraus entsteht eine neue
  `<Name>.dossiary`-Bibliothek, die sich sofort öffnen lässt — zum
  Weitergeben oder um eine Bibliothek aufzuteilen. **Kopieren** lässt diese
  Bibliothek, wie sie ist; **Verschieben** legt die Dokumente hier in den
  Papierkorb, sobald die neue Bibliothek geschrieben ist (Wiederherstellen
  macht es rückgängig). Die neue Bibliothek bekommt nur die Felder und
  Einstellungen, die diese Dokumente nutzen, oder auf Wunsch alles aus
  dieser Bibliothek. Ein Dokument, dessen Datei nicht lesbar ist, wird
  ausgelassen und aufgeführt.
```

`CLAUDE.md`, a new architecture bullet right after the "Export selected documents" bullet:

```markdown
- **Export as library** (`openExportLibraryModal()`, `buildExportLibraryDb()`,
  `#bulk-export-library-btn` in the bulk More menu; spec
  `docs/superpowers/specs/2026-10-15-export-as-library-design.md`) turns the
  selected documents into a new `<Name>.dossiary` library, copied or moved.
  The new database is built in memory from the open one with **ids kept**, so
  every stored path stays valid: the documents and their tags, people,
  custom values, splits and reminder snoozes; manual collections holding them
  (with only those members); and setup -- 'used' (fields with a value on
  these documents plus `NON_RENAMEABLE_FIELD_NAMES`, their types' field
  setup, descriptions, settings) or 'all' (`copySetupFrom()`, now taking a
  target database and an excluded-settings list). Never copied:
  `EXPORT_SETTINGS_NOT_COPIED` (`last_backup_at`, `scan_bridge_url`,
  `scan_last_settings`), `not_duplicate_groups`, `ocr_jobs`. Order: each
  document's file and original are read before anything is written (a
  document that can't be read is left out and listed, and stays here on
  Move), previews and fresh sidecars (`sidecarTextForDoc()`) best-effort,
  `library.sqlite` last; Stop, a failure or nothing readable removes the new
  folder; Move then calls `bulkSetDeleted()` on the exported ids (undone in
  memory if that save fails). "Open it" switches via `resetAll()` +
  `proceedWithRootDirHandle()`, and the new library is added to Recent
  libraries. `exportLibraryRunning` blocks closing the dialog meanwhile.
```

- [ ] **Step 9: Run the full suite**

Run (from `tests/`):

```bash
fails=""; for f in test_*.py; do out=$(python3 "$f" 2>&1); rc=$?; if [ $rc -ne 0 ] || echo "$out" | grep -qE ": False\b|Traceback|AssertionError|ERRORS[^:]*: \[.+\]"; then fails="$fails $f"; fi; done; echo "FAILING:$fails"
```

Expected: `FAILING:` with nothing after it. Then update the test-script count in `README.md`, `README.de.md` and `CONTRIBUTING.md` (98 → 99): `grep -n "98" README.md README.de.md CONTRIBUTING.md` to find the lines.

- [ ] **Step 10: Commit**

```bash
git add dossiary.html tests/test_export_library.py README.md README.de.md CLAUDE.md CONTRIBUTING.md
git commit -m "Export as library: copy or move selected documents into a new .dossiary library"
```
