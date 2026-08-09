# Preserve Original File on Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every new document (capture form or Inbox) gets its raw, untouched bytes preserved at `original_file_path` from the moment it's added, regardless of file type or whether OCR ever runs — with a new `searchable_pdf_built` flag replacing `original_file_path`'s old implicit meaning.

**Architecture:** A small shared helper (`writeOriginalToSubfolder()`) writes the raw file into a subfolder before any processing; both `saveNewDocument()` and `addInboxFile()` call it unconditionally. A new `searchable_pdf_built` column, backed by a one-time backfill migration (mirroring `migrateTextFieldsAutocompleteDefault()`'s pattern), takes over the "has this document's `file_path` actually been through searchable-PDF processing" signal that `original_file_path`'s presence used to carry alone.

**Tech Stack:** Vanilla JS inside `dossiary.html` (no new dependency), existing `SCHEMA`/`SCHEMA_MIGRATIONS` pattern, existing Playwright + `tests/stub_studio2.js` test harness.

## Global Constraints

- No new third-party dependency, no build step — stays inside `dossiary.html` as plain JS.
- LibraryLifeboat-migrated documents (`source = 'migrated'`) are explicitly out of scope — never touched by the backfill or any new ingestion logic.
- `searchable_pdf_built` is **not** loaded into the in-memory `allDocs` model or referenced by any UI in this plan — nothing reads it yet (that's sub-project 2's job). Don't add it to `loadDocumentsFromDb()`'s SELECT or either `allDocs.push({...})` call; doing so now would be unused code with no consumer.
- Design spec is `docs/superpowers/specs/2026-08-09-preserve-original-on-ingestion-design.md` — refer back to it if a task's rationale is unclear.
- Every existing test file loads `tests/stub_studio2.js`; do not embed a separate copy.
- Prefer the codebase's established migration convention exactly: `queryAll('SELECT ... FROM table')` (no `WHERE`, whole table into JS) then per-row `db.run('UPDATE table SET col = ? WHERE id = ?', [val, id])` — this is what `migrateSentinelFieldsToGeneric()` already does, and it's what `tests/stub_studio2.js`'s fake SQL engine actually supports (its `UPDATE` regex only matches a single parameterized `SET col = ?` / `WHERE col = ?` shape — a compound `WHERE x IS NOT NULL AND y = 'literal'` clause is **not** supported and must not be used).

---

## Task 1: `searchable_pdf_built` schema column + one-time backfill migration

**Files:**
- Modify: `dossiary.html` (`SCHEMA`, `SCHEMA_MIGRATIONS`, new `migrateSearchablePdfBuiltFlag()` function, two call sites)
- Create: `tests/test_searchable_pdf_built_migration.py`

**Interfaces:**
- Produces (used by Tasks 2–3): the `searchable_pdf_built INTEGER DEFAULT 0` column exists on `documents` in both fresh and upgraded libraries.
- Consumes: `queryAll(sql)` (`dossiary.html:852`, already exists), the `settings` table's existing one-time-marker convention.

- [ ] **Step 1: Add the column to `SCHEMA`**

In `dossiary.html`, change (`dossiary.html:357`):

```js
      archived INTEGER DEFAULT 0, needs_review INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0
```

to:

```js
      archived INTEGER DEFAULT 0, needs_review INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0,
      searchable_pdf_built INTEGER DEFAULT 0
```

- [ ] **Step 2: Add the migration entry to `SCHEMA_MIGRATIONS`**

In `dossiary.html`, change (`dossiary.html:389-400`):

```js
  const SCHEMA_MIGRATIONS = [
    'ALTER TABLE documents ADD COLUMN import_date TEXT',
    'ALTER TABLE documents ADD COLUMN subcategory TEXT',
    'ALTER TABLE documents ADD COLUMN thumbnail_path TEXT',
    'ALTER TABLE document_type_fields ADD COLUMN field_name TEXT',
    'ALTER TABLE documents ADD COLUMN currency TEXT',
    'ALTER TABLE fields ADD COLUMN show_as_column INTEGER DEFAULT 0',
    'ALTER TABLE fields ADD COLUMN autocomplete INTEGER DEFAULT 0',
    'ALTER TABLE documents ADD COLUMN archived INTEGER DEFAULT 0',
    'ALTER TABLE documents ADD COLUMN needs_review INTEGER DEFAULT 0',
    'ALTER TABLE documents ADD COLUMN deleted INTEGER DEFAULT 0',
  ];
```

to:

```js
  const SCHEMA_MIGRATIONS = [
    'ALTER TABLE documents ADD COLUMN import_date TEXT',
    'ALTER TABLE documents ADD COLUMN subcategory TEXT',
    'ALTER TABLE documents ADD COLUMN thumbnail_path TEXT',
    'ALTER TABLE document_type_fields ADD COLUMN field_name TEXT',
    'ALTER TABLE documents ADD COLUMN currency TEXT',
    'ALTER TABLE fields ADD COLUMN show_as_column INTEGER DEFAULT 0',
    'ALTER TABLE fields ADD COLUMN autocomplete INTEGER DEFAULT 0',
    'ALTER TABLE documents ADD COLUMN archived INTEGER DEFAULT 0',
    'ALTER TABLE documents ADD COLUMN needs_review INTEGER DEFAULT 0',
    'ALTER TABLE documents ADD COLUMN deleted INTEGER DEFAULT 0',
    'ALTER TABLE documents ADD COLUMN searchable_pdf_built INTEGER DEFAULT 0',
  ];
```

- [ ] **Step 3: Add the one-time backfill migration function**

In `dossiary.html`, insert this immediately after `migrateTextFieldsAutocompleteDefault()`'s closing brace (`dossiary.html:1349`, right before `function loadFieldValues(){`):

```js
  // One-time backfill for the new searchable_pdf_built flag (see the "Preserve
  // original file on ingestion" design). Before this change, original_file_path
  // IS NOT NULL implicitly meant "went through the capture form's searchable-PDF
  // branch" -- the only code path that ever set it. Once every new document gets
  // original_file_path unconditionally (see writeOriginalToSubfolder()), that
  // implication breaks, so this runs exactly once (tracked via a dedicated
  // settings row, same reasoning as migrateTextFieldsAutocompleteDefault() above
  // -- there's no way to tell "never touched" apart from "correctly computed as
  // unprocessed" just by looking at the documents table) to backfill the flag for
  // documents that already exist under the old rule. source = 'captured' is the
  // same predicate that already, uniquely, identified that old rule -- no
  // scan-inbox document could have original_file_path set (addInboxFile() always
  // wrote NULL), and migrated documents are deliberately excluded: their
  // original_file_path reflects Mariner's own historical layout, unrelated to
  // whether Dossiary's own OCR pipeline has ever touched them.
  function migrateSearchablePdfBuiltFlag(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'searchable_pdf_built_backfill_migrated'").rows;
    if(rows.length) return; // already run once for this library
    const { columns, rows: docRows } = queryAll('SELECT id, original_file_path, source FROM documents');
    const idx = Object.fromEntries(columns.map((c, i) => [c, i]));
    for(const row of docRows){
      const docId = row[idx.id];
      const originalFilePath = row[idx.original_file_path];
      const source = row[idx.source];
      if(originalFilePath != null && source === 'captured'){
        db.run('UPDATE documents SET searchable_pdf_built = ? WHERE id = ?', [1, docId]);
      }
    }
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('searchable_pdf_built_backfill_migrated', ?)", ['1']);
  }
```

- [ ] **Step 4: Wire the migration into `initNewLibrary()` and `loadDb()`**

In `dossiary.html`, change (`dossiary.html:953`):

```js
      migrateTextFieldsAutocompleteDefault(); // no-op here (no text fields exist yet beyond the sentinels above), but marks this library as migrated
```

to:

```js
      migrateTextFieldsAutocompleteDefault(); // no-op here (no text fields exist yet beyond the sentinels above), but marks this library as migrated
      migrateSearchablePdfBuiltFlag(); // no-op here (no documents exist yet), but marks this library as migrated
```

And change (`dossiary.html:977`):

```js
    migrateTextFieldsAutocompleteDefault(); // one-time; no-op if this library was already migrated
```

to:

```js
    migrateTextFieldsAutocompleteDefault(); // one-time; no-op if this library was already migrated
    migrateSearchablePdfBuiltFlag(); // one-time; no-op if this library was already migrated
```

- [ ] **Step 5: Write `tests/test_searchable_pdf_built_migration.py`**

Follow the exact structure of `tests/test_sentinel_field_migration.py` (chdir/APP_PATH boilerplate, route stubbing, `add_init_script(stub_js)`, seeding via `window.__makeSeededRoot()`, reading `library.sqlite` back via `page.evaluate`, and the `#reload-btn` idempotency check at the end).

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json
from playwright.async_api import async_playwright

# Three old-shape documents, exactly what a library predating this migration
# looks like:
# - doc 1: source='captured', original_file_path set -- under the OLD rule this
#   could only mean the searchable-PDF branch ran, so should be backfilled to
#   searchable_pdf_built=1.
# - doc 2: source='migrated', original_file_path set -- Mariner's own layout,
#   unrelated to Dossiary's OCR pipeline; must NOT be backfilled.
# - doc 3: source='scan-inbox', original_file_path NOT set -- addInboxFile()
#   never set it under the old rule; stays unbackfilled (falsy/0).
SEED = {
    "documents": [
        {
            "id": 1, "title": "Old Searchable Capture", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": "Hello", "ocr_language": "eng",
            "file_path": "files/1_doc.pdf", "original_file_path": "files/1_doc/original.jpg",
            "created_at": "2026-01-01T00:00:00Z", "source": "captured", "source_legacy_id": None,
        },
        {
            "id": 2, "title": "Migrated Doc", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_doc.pdf", "original_file_path": "files/2_doc/original.pdf",
            "created_at": "2026-01-01T00:00:00Z", "source": "migrated", "source_legacy_id": 9,
        },
        {
            "id": 3, "title": "Inbox Doc", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_doc.jpg", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00Z", "source": "scan-inbox", "source_legacy_id": None,
        },
    ],
    "tags": [], "document_tags": [],
}

async def read_docs(page):
    return await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            const f = await fh.getFile();
            return JSON.parse(await f.text()).documents;
        })()
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        docs = await read_docs(page)
        by_id = {d['id']: d for d in docs}
        print("doc1 (captured, had original) searchable_pdf_built (should be 1):", by_id[1].get('searchable_pdf_built'))
        print("doc2 (migrated, had original) searchable_pdf_built (should stay unset/falsy, NOT backfilled):", by_id[2].get('searchable_pdf_built'))
        print("doc3 (scan-inbox, no original) searchable_pdf_built (should stay unset/falsy):", by_id[3].get('searchable_pdf_built'))

        # === Idempotency: reopening the same (now-migrated) library doesn't
        # re-run the backfill or change any value ===
        await page.click('#reload-btn')
        await page.wait_for_timeout(400)
        docs2 = await read_docs(page)
        by_id2 = {d['id']: d for d in docs2}
        print("doc1 stable after reopen (should still be 1):", by_id2[1].get('searchable_pdf_built'))
        print("doc2 stable after reopen (should still be unset/falsy):", by_id2[2].get('searchable_pdf_built'))
        print("doc3 stable after reopen (should still be unset/falsy):", by_id2[3].get('searchable_pdf_built'))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 6: Run the test**

Run: `cd tests && python3 test_searchable_pdf_built_migration.py`

Expected: `doc1 ... (should be 1): 1`, `doc2 ...: None` (or `0`), `doc3 ...: None` (or `0`), all three stable across the reopen, and `JS ERRORS: []`.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_searchable_pdf_built_migration.py
git commit -m "$(cat <<'EOF'
Add searchable_pdf_built column and its one-time backfill migration

Once every new document gets original_file_path unconditionally
(next commits), its presence alone can no longer mean "this went
through searchable-PDF processing" -- this flag takes over that
signal. Existing libraries get backfilled once, scoped to
source='captured' documents only, since that's the only path that
ever set original_file_path under the old rule.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Preserve original on capture (`saveNewDocument()`)

**Files:**
- Modify: `dossiary.html` (new `writeOriginalToSubfolder()` helper, `saveNewDocument()`)
- Modify: `tests/test_searchable_pdf.py`, `tests/test_studio2.py`

**Interfaces:**
- Consumes: `safeFilename(name, fallback)` (`dossiary.html:521`, already exists), `filesDirHandle` (module-level state, already exists), `searchable_pdf_built` column (Task 1).
- Produces (used by Task 3): `writeOriginalToSubfolder(id, baseName, file)` → `Promise<string>` (the relative `original_file_path` to store), placed right before `saveNewDocument()`.

- [ ] **Step 1: Add the shared `writeOriginalToSubfolder()` helper**

In `dossiary.html`, insert this immediately before `async function saveNewDocument(){` (`dossiary.html:3182`):

```js
  // Writes `file`'s raw bytes into files/<id>_<baseName>/<originalName>, returning
  // the relative path to store as original_file_path. Called before any
  // processing, from both saveNewDocument() (below) and addInboxFile(), so every
  // new document's untouched original is preserved from the moment it's added,
  // regardless of file type or whether it's ever OCR'd -- see the "Preserve
  // original file on ingestion" design note in CLAUDE.md for why this is
  // unconditional now, not just for the searchable-PDF path.
  async function writeOriginalToSubfolder(id, baseName, file){
    const subfolderName = `${id}_${baseName}`;
    const subfolderHandle = await filesDirHandle.getDirectoryHandle(subfolderName, { create: true });
    const originalName = safeFilename(file.name, 'original');
    const originalHandle = await subfolderHandle.getFileHandle(originalName, { create: true });
    const writable = await originalHandle.createWritable();
    await writable.write(await file.arrayBuffer());
    await writable.close();
    return `files/${subfolderName}/${originalName}`;
  }

```

- [ ] **Step 2: Rewrite `saveNewDocument()`'s file-writing block to always preserve the original**

In `dossiary.html`, change (`dossiary.html:3195-3234`):

```js
      let filePathForDb, originalFilePathForDb, sidecarBaseName;

      if(canBuildSearchablePdf){
        const imageFormat = pendingFile.type === 'image/jpeg' ? 'JPEG' : 'PNG';
        const dataUrl = await fileToDataUrl(pendingFile);
        const pdfBytes = await buildSearchablePdf(dataUrl, imageFormat, pendingImageDims, pendingOcrWords);

        const baseName = safeFilename((el('f-title').value.trim() || pendingFile.name.replace(/\.[^.]+$/, '')), 'document');
        const processedName = `${id}_${baseName}.pdf`;
        const processedHandle = await filesDirHandle.getFileHandle(processedName, { create: true });
        const processedWritable = await processedHandle.createWritable();
        await processedWritable.write(pdfBytes);
        await processedWritable.close();

        // Original raw file goes in a subfolder next to the processed PDF -- the
        // same layout Mariner Paperless used, and what migrate_to_new_library.py
        // produces for migrated documents.
        const subfolderName = `${id}_${baseName}`;
        const subfolderHandle = await filesDirHandle.getDirectoryHandle(subfolderName, { create: true });
        const originalName = safeFilename(pendingFile.name, 'original');
        const originalHandle = await subfolderHandle.getFileHandle(originalName, { create: true });
        const originalWritable = await originalHandle.createWritable();
        await originalWritable.write(await pendingFile.arrayBuffer());
        await originalWritable.close();

        filePathForDb = `files/${processedName}`;
        originalFilePathForDb = `files/${subfolderName}/${originalName}`;
        sidecarBaseName = `${id}_${baseName}`;
      }else{
        // No word-position OCR data available (PDF upload, unsupported image type,
        // or OCR wasn't run) -- just save the picked file directly, same as before.
        const destName = `${id}_${safeFilename(pendingFile.name, 'document')}`;
        const destHandle = await filesDirHandle.getFileHandle(destName, { create: true });
        const writable = await destHandle.createWritable();
        await writable.write(await pendingFile.arrayBuffer());
        await writable.close();
        filePathForDb = `files/${destName}`;
        originalFilePathForDb = null;
        sidecarBaseName = destName.replace(/\.[^.]+$/, '');
      }
```

to:

```js
      let filePathForDb, sidecarBaseName;

      const baseName = safeFilename((el('f-title').value.trim() || pendingFile.name.replace(/\.[^.]+$/, '')), 'document');
      // Preserve the untouched original from the moment the document is added,
      // regardless of file type or whether a searchable PDF gets built below.
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, pendingFile);
      let searchablePdfBuilt = 0;

      if(canBuildSearchablePdf){
        const imageFormat = pendingFile.type === 'image/jpeg' ? 'JPEG' : 'PNG';
        const dataUrl = await fileToDataUrl(pendingFile);
        const pdfBytes = await buildSearchablePdf(dataUrl, imageFormat, pendingImageDims, pendingOcrWords);

        const processedName = `${id}_${baseName}.pdf`;
        const processedHandle = await filesDirHandle.getFileHandle(processedName, { create: true });
        const processedWritable = await processedHandle.createWritable();
        await processedWritable.write(pdfBytes);
        await processedWritable.close();

        filePathForDb = `files/${processedName}`;
        sidecarBaseName = `${id}_${baseName}`;
        searchablePdfBuilt = 1;
      }else{
        // No word-position OCR data available (PDF upload, unsupported image type,
        // or OCR wasn't run) -- just save the picked file directly, same as before.
        // The original preserved above still gives this document a real, safe
        // "original" even though nothing was processed.
        const destName = `${id}_${safeFilename(pendingFile.name, 'document')}`;
        const destHandle = await filesDirHandle.getFileHandle(destName, { create: true });
        const writable = await destHandle.createWritable();
        await writable.write(await pendingFile.arrayBuffer());
        await writable.close();
        filePathForDb = `files/${destName}`;
        sidecarBaseName = destName.replace(/\.[^.]+$/, '');
      }
```

- [ ] **Step 3: Add `searchable_pdf_built` to the `INSERT`**

In `dossiary.html`, change (`dossiary.html:3263-3268`):

```js
      db.run(`
        INSERT INTO documents (id, title, category, subcategory, document_type, date,
                                import_date, notes, ocr_text, ocr_language, file_path, original_file_path,
                                created_at, source, source_legacy_id, thumbnail_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'captured', NULL, ?)
      `, [id, title, category, subcategory, documentType, date, importDate, notes, ocrText, ocrLanguage, filePathForDb, originalFilePathForDb, createdAt, thumbnailPathForDb]);
```

to:

```js
      db.run(`
        INSERT INTO documents (id, title, category, subcategory, document_type, date,
                                import_date, notes, ocr_text, ocr_language, file_path, original_file_path,
                                created_at, source, source_legacy_id, thumbnail_path, searchable_pdf_built)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'captured', NULL, ?, ?)
      `, [id, title, category, subcategory, documentType, date, importDate, notes, ocrText, ocrLanguage, filePathForDb, originalFilePathForDb, createdAt, thumbnailPathForDb, searchablePdfBuilt]);
```

Do **not** add `searchable_pdf_built` to the `allDocs.push({...})` call right after — per Global Constraints, nothing reads it from the in-memory model in this plan.

- [ ] **Step 4: Extend `tests/test_searchable_pdf.py` to check `searchable_pdf_built`**

In `tests/test_searchable_pdf.py`, right after the existing line (search for `print("documents[0]:", db_state['documents'][0])`):

```python
        print("documents[0]:", db_state['documents'][0])
```

add:

```python
        print("searchable_pdf_built (should be 1):", db_state['documents'][0].get('searchable_pdf_built'))
```

- [ ] **Step 5: Extend `tests/test_studio2.py`'s plain-PDF-save scenario**

In `tests/test_studio2.py`, right after the existing lines (search for `status after first save on new library`):

```python
        status2 = await page.locator("#status").inner_text()
        print("status after first save on new library:", status2)
```

add:

```python
        db_state = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc1 = db_state['documents'][0]
        print("plain PDF save gets a real original_file_path (should not be None):", doc1.get('original_file_path'))
        print("plain PDF save searchable_pdf_built (should be 0):", doc1.get('searchable_pdf_built'))
```

- [ ] **Step 6: Run both tests**

Run: `cd tests && python3 test_searchable_pdf.py`
Expected: all existing lines unchanged, plus `searchable_pdf_built (should be 1): 1`, and `JS ERRORS: []`.

Run: `cd tests && python3 test_studio2.py`
Expected: all existing lines unchanged, plus a real (non-`None`) `original_file_path` and `searchable_pdf_built (should be 0): 0`, and `JS ERRORS: []`.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_searchable_pdf.py tests/test_studio2.py
git commit -m "$(cat <<'EOF'
Preserve the original file on every capture, not just searchable PDFs

saveNewDocument() now writes the untouched original into its
subfolder unconditionally, via the new shared
writeOriginalToSubfolder() helper -- a plain PDF upload or an
un-OCR'd image gets a real original_file_path too, not just
documents that go through the searchable-PDF branch.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Preserve original on Inbox add (`addInboxFile()`)

**Files:**
- Modify: `dossiary.html` (`addInboxFile()`)
- Modify: `tests/test_inbox.py`

**Interfaces:**
- Consumes: `writeOriginalToSubfolder(id, baseName, file)` (Task 2), `safeFilename(name, fallback)`.

- [ ] **Step 1: Rewrite `addInboxFile()` to preserve the original**

In `dossiary.html`, change (`dossiary.html:3441-3474`):

```js
  async function addInboxFile(name){
    const entry = pendingInboxFiles.find(f => f.name === name);
    if(!entry) return;
    const statusEl = el('inbox-status');
    if(statusEl){ statusEl.className = 'status busy'; statusEl.innerHTML = `<span class="spinner"></span> Adding "${escapeHtml(name)}"…`; }
    let id;
    try{
      id = nextDocId++;
      const file = await entry.handle.getFile();
      const destName = `${id}_${safeFilename(file.name, 'document')}`;
      const destHandle = await filesDirHandle.getFileHandle(destName, { create: true });
      const writable = await destHandle.createWritable();
      await writable.write(await file.arrayBuffer());
      await writable.close();

      // Best-effort, same as saveNewDocument() -- a missing preview isn't fatal.
      let thumbnailPathForDb = null;
      try{
        const thumbBytes = await generateThumbnail(file);
        if(thumbBytes) thumbnailPathForDb = await writeThumbnail(id, thumbBytes);
      }catch(e){ /* no preview -- not fatal */ }

      const title = file.name.replace(/\.[^.]+$/, '') || null;
      const documentType = defaultDocumentType || null;
      const createdAt = nowIso();
      const filePathForDb = `files/${destName}`;
      const sidecarBaseName = destName.replace(/\.[^.]+$/, '');

      db.run(`
        INSERT INTO documents (id, title, category, subcategory, document_type, date,
                                import_date, notes, ocr_text, ocr_language, file_path, original_file_path,
                                created_at, source, source_legacy_id, thumbnail_path, needs_review)
        VALUES (?, ?, NULL, NULL, ?, NULL, ?, NULL, NULL, NULL, ?, NULL, ?, 'scan-inbox', NULL, ?, 1)
      `, [id, title, documentType, createdAt, filePathForDb, createdAt, thumbnailPathForDb]);
```

to:

```js
  async function addInboxFile(name){
    const entry = pendingInboxFiles.find(f => f.name === name);
    if(!entry) return;
    const statusEl = el('inbox-status');
    if(statusEl){ statusEl.className = 'status busy'; statusEl.innerHTML = `<span class="spinner"></span> Adding "${escapeHtml(name)}"…`; }
    let id;
    try{
      id = nextDocId++;
      const file = await entry.handle.getFile();
      const baseName = safeFilename(file.name.replace(/\.[^.]+$/, ''), 'document');
      const destName = `${id}_${safeFilename(file.name, 'document')}`;
      const destHandle = await filesDirHandle.getFileHandle(destName, { create: true });
      const writable = await destHandle.createWritable();
      await writable.write(await file.arrayBuffer());
      await writable.close();

      // Preserve the untouched original from the moment the document is added --
      // Inbox never runs OCR automatically, so this document is always
      // unprocessed at this point (searchable_pdf_built stays 0 below).
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, file);

      // Best-effort, same as saveNewDocument() -- a missing preview isn't fatal.
      let thumbnailPathForDb = null;
      try{
        const thumbBytes = await generateThumbnail(file);
        if(thumbBytes) thumbnailPathForDb = await writeThumbnail(id, thumbBytes);
      }catch(e){ /* no preview -- not fatal */ }

      const title = file.name.replace(/\.[^.]+$/, '') || null;
      const documentType = defaultDocumentType || null;
      const createdAt = nowIso();
      const filePathForDb = `files/${destName}`;
      const sidecarBaseName = destName.replace(/\.[^.]+$/, '');

      db.run(`
        INSERT INTO documents (id, title, category, subcategory, document_type, date,
                                import_date, notes, ocr_text, ocr_language, file_path, original_file_path,
                                created_at, source, source_legacy_id, thumbnail_path, needs_review, searchable_pdf_built)
        VALUES (?, ?, NULL, NULL, ?, NULL, ?, NULL, NULL, NULL, ?, ?, ?, 'scan-inbox', NULL, ?, 1, 0)
      `, [id, title, documentType, createdAt, filePathForDb, originalFilePathForDb, createdAt, thumbnailPathForDb]);
```

- [ ] **Step 2: Fix the stale `original_file_path: null` in `addInboxFile()`'s in-memory push**

In `dossiary.html`, find the `allDocs.push({...})` call inside `addInboxFile()` (a few lines below the `INSERT`, search for `source: 'scan-inbox'` inside an `allDocs.push`):

```js
        original_file_path: null, created_at: createdAt, source: 'scan-inbox', source_legacy_id: null,
```

change to:

```js
        original_file_path: originalFilePathForDb, created_at: createdAt, source: 'scan-inbox', source_legacy_id: null,
```

(This is a correctness fix, not new scope — the in-memory document object must match what was just written to the database, the same way `file_path` already does on the line above it.)

- [ ] **Step 3: Extend `tests/test_inbox.py`**

In `tests/test_inbox.py`, change (search for `print("doc1:"`):

```python
        doc1 = persisted['documents'][0]
        print("doc1:", {k: doc1[k] for k in ['id', 'title', 'category', 'document_type', 'date', 'source', 'file_path']})
```

to:

```python
        doc1 = persisted['documents'][0]
        print("doc1:", {k: doc1[k] for k in ['id', 'title', 'category', 'document_type', 'date', 'source', 'file_path']})
        print("inbox-added doc gets a real original_file_path (should not be None):", doc1.get('original_file_path'))
        print("inbox-added doc searchable_pdf_built (should be 0):", doc1.get('searchable_pdf_built'))
```

- [ ] **Step 4: Run the test**

Run: `cd tests && python3 test_inbox.py`
Expected: all existing lines unchanged, plus a real (non-`None`) `original_file_path` and `searchable_pdf_built (should be 0): 0`, and `JS errors: []`.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_inbox.py
git commit -m "$(cat <<'EOF'
Preserve the original file on every Inbox add too

addInboxFile() now calls the shared writeOriginalToSubfolder()
helper unconditionally, same as saveNewDocument() -- an inbox-added
document (never auto-OCR'd) gets a real original_file_path with
searchable_pdf_built=0, instead of the old hardcoded NULL.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Documentation + full regression

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `README.de.md`, `CONTRIBUTING.md`

**Interfaces:** None — documentation only, no code.

- [ ] **Step 1: Update `CLAUDE.md`'s "Searchable PDF generation" note**

Change (`CLAUDE.md:1090-1097`):

```markdown
  - When a searchable PDF is built, the *processed* file is the generated
    PDF (`file_path`), and the *original* upload is preserved untouched in
    a subfolder next to it (`original_file_path`) — mirroring the layout
    `migrate_to_new_library.py` produces for migrated documents and that
    Mariner Paperless itself used. When a searchable PDF *isn't* built
    (PDF upload, or an image format other than JPEG/PNG), the picked file
    is saved directly as `file_path` with `original_file_path` left `NULL`
    — there's no meaningfully separate "original" in that case.
```

to:

```markdown
  - When a searchable PDF is built, the *processed* file is the generated
    PDF (`file_path`), and the *original* upload is preserved untouched in
    a subfolder next to it (`original_file_path`) — mirroring the layout
    `migrate_to_new_library.py` produces for migrated documents and that
    Mariner Paperless itself used. See "Preserving an original file on
    ingestion" below for what happens when a searchable PDF *isn't* built.
```

- [ ] **Step 2: Add a new "Preserving an original file on ingestion" note**

In `CLAUDE.md`, insert this new bullet immediately after the "Searchable PDF generation" bullet ends (right before the `- **Sidecar `.txt` files**` bullet):

```markdown
- **Preserving an original file on ingestion** (`writeOriginalToSubfolder()`,
  called unconditionally from both `saveNewDocument()` and `addInboxFile()`)
  reverses what used to be true only for the searchable-PDF path above:
  every new document, regardless of file type or whether OCR ever runs,
  gets its raw, untouched bytes written into `files/<id>_<baseName>/` and
  `original_file_path` set to that — before any processing happens.
  `file_path` keeps meaning exactly what it always has: whatever's
  currently active (the searchable PDF when one was built, otherwise a
  plain copy of the same content) — only whether a *sibling* original also
  exists has changed. LibraryLifeboat-migrated documents are untouched by
  this — their `original_file_path` reflects Mariner's own historical
  layout via `migrate_to_new_library.py`, not this app's own ingestion.
  **This means `original_file_path IS NOT NULL` can no longer be read as
  "this document went through searchable-PDF processing"** — a new
  `searchable_pdf_built` column (`documents.searchable_pdf_built`, `0`/`1`)
  is the explicit signal for that now, set to `1` only in
  `saveNewDocument()`'s searchable-PDF branch, `0` everywhere else
  (including every Inbox add, since Inbox never runs OCR automatically).
  A one-time backfill migration (`migrateSearchablePdfBuiltFlag()`, same
  settings-row-tracked-once pattern as `migrateTextFieldsAutocompleteDefault()`
  below) sets `searchable_pdf_built = 1` for existing documents where
  `original_file_path IS NOT NULL AND source = 'captured'` — the same
  predicate that uniquely identified the old rule — deliberately excluding
  `source = 'migrated'` documents, whose `original_file_path` predates and
  is unrelated to this app's own OCR pipeline. Every new document now
  permanently uses roughly double the disk space (an original plus an
  active copy, even when nothing is ever processed) — an accepted
  tradeoff, not an oversight. `searchable_pdf_built` is not yet loaded
  into the in-memory `allDocs` model or read by any UI — nothing consumes
  it yet; it exists for a planned future "build a searchable PDF after the
  fact" action to gate on.
```

- [ ] **Step 3: Bump the script-count mentions from 47 to 48**

In `CLAUDE.md`, change (`CLAUDE.md:38`):

```
tests/                   Playwright regression suite (47 scripts) + shared
```

to:

```
tests/                   Playwright regression suite (48 scripts) + shared
```

And change (`CLAUDE.md:1157-1158`):

```markdown
There's a real, runnable Playwright regression suite in `tests/` — **47
scripts covering most of the app's actual functionality**:
```

to:

```markdown
There's a real, runnable Playwright regression suite in `tests/` — **48
scripts covering most of the app's actual functionality**:
```

Also add a clause naming the new test file to that same paragraph's list of named scenarios, in the same style as its neighbors — e.g. "the `searchable_pdf_built` backfill migration (`test_searchable_pdf_built_migration.py` — a `captured` document with a pre-existing original correctly backfilled to `1`, a `migrated` document's unrelated original correctly left alone, a `scan-inbox` document with no original left alone, and stability across a reopen)".

In `CONTRIBUTING.md`, change (`CONTRIBUTING.md:30`):

```
There's a real Playwright regression suite in `tests/` (47 scripts, nothing
```

to:

```
There's a real Playwright regression suite in `tests/` (48 scripts, nothing
```

- [ ] **Step 4: Update `README.md`'s schema section**

In `README.md`, add `searchable_pdf_built` to the Mermaid diagram's `documents` block (`README.md:328-351`, right after `int deleted`):

```
    int deleted
    int searchable_pdf_built
  }
```

And add it to the plain-text column listing (`README.md:389-418`, right after the `original_file_path` line):

```
    file_path           TEXT     -- relative to library root, e.g. "files/3_invoice.pdf"
    original_file_path  TEXT     -- relative to library root; now set for every new
                                  -- document (Inbox or capture), not just searchable PDFs
    searchable_pdf_built INTEGER -- 0/1, default 0; whether Dossiary's own OCR+jsPDF
                                  -- pipeline built the file currently at file_path --
                                  -- original_file_path's presence alone no longer means this
```

- [ ] **Step 5: Mirror the same `README.md` schema changes into `README.de.md`**

Same two additions (Mermaid diagram block and plain-text listing), at `README.de.md`'s equivalent `## Datenbankschema` section (around `README.de.md:328-351` for the diagram, `README.de.md:389-418` for the plain-text listing — offsets differ slightly from `README.md` due to German text length; locate by the same `int deleted` / `original_file_path` anchors), translated into German in the same style as the surrounding column comments.

- [ ] **Step 6: Run the full test suite**

Run: `cd tests && for f in test_*.py; do echo "=== $f ==="; python3 "$f"; done`

Expected: all 48 files run to completion, no Python tracebacks, every `JS ERRORS`/`JS errors` line is `[]`, and no existing scenario's printed output changed other than the new lines added in Tasks 2–3.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md README.md README.de.md CONTRIBUTING.md
git commit -m "$(cat <<'EOF'
Document preserving an original file on ingestion

Updates CLAUDE.md's searchable-PDF note (no longer accurate on its
own), adds a new architecture note explaining searchable_pdf_built
and why original_file_path's old meaning changed, and updates the
schema docs and script counts in README.md/README.de.md/CONTRIBUTING.md.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** schema column + one-time backfill (Task 1), `saveNewDocument()` always preserving original (Task 2), `addInboxFile()` always preserving original (Task 3), visible-consequences documentation including the disk-space tradeoff and the "Original" UI now appearing more often (Task 4), testing-impact items from the spec (existing test extensions in Tasks 2–3, new migration test in Task 1) — all covered.
- **Type/interface consistency:** `writeOriginalToSubfolder(id, baseName, file)` is defined once in Task 2 and consumed identically (same parameter order and meaning) by Task 3 — verified.
- **Scope discipline:** `searchable_pdf_built` is deliberately never added to `loadDocumentsFromDb()`'s SELECT or `allDocs.push({...})` in any task, per Global Constraints — this is sub-project 2's job, not this plan's.
