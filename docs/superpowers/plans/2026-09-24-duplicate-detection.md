# Duplicate detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect and surface duplicate documents two ways — an exact SHA-256 file-content match, and a Title+Date metadata heuristic — via a capture-time warning, silent-but-reported skipping during Inbox/drag-and-drop bulk adds, and an on-demand "Find duplicates" modal.

**Architecture:** A new `documents.file_hash` column, computed lazily (eagerly for new documents, backfilled once on first "Find duplicates" open for existing ones) via a shared `computeFileHash(file)` helper. Three integration points reuse this column: the capture form's file-pick handler, the shared `createReviewDocumentFromFile()` Inbox/drag-and-drop helper, and a new Reminders-modal-styled results modal.

**Tech Stack:** Vanilla JS inside `dossiary.html`'s single IIFE (Web Crypto API's `crypto.subtle.digest`); Playwright tests extending a new `tests/test_duplicate_detection.py`; no new dependencies.

## Global Constraints

- Single-file app — all code changes live in `dossiary.html`. Tests in `tests/test_duplicate_detection.py`. Docs in `CLAUDE.md`/`tests/CLAUDE.md`. No new files beyond those, no build step, no external dependencies.
- The hash is computed on the **original uploaded bytes**, not the possibly-rebuilt active `file_path` — `writeOriginalToSubfolder()`'s own `File` object for new documents, falling back to `file_path` only for documents with no preserved original (LibraryLifeboat-migrated ones).
- Capture-time warning is **non-blocking** — exact-hash only, never the Title+Date heuristic, and Save always stays enabled.
- Inbox/drag-and-drop: an exact-hash match is **skipped, not added**, with explicit status-line reporting of the skip count, and the staged file is removed from `inbox/` exactly like a normal successful add.
- "Find duplicates" adds no bespoke delete/merge action — clicking a document in a group closes the modal and opens the existing detail panel, where Archive/Delete/Edit already exist.
- Deleted documents are excluded from every grouping pass; archived and needs-review documents are included.
- All 6 supported languages (`en`, `de`, `es`, `fr`, `zh-Hans`, `zh-Hant`) need every new i18n key — `tests/test_i18n_coverage.py` fails the whole suite otherwise.

---

### Task 1: Schema, `computeFileHash()`, and hash storage on document creation

**Files:**
- Modify: `dossiary.html` (`SCHEMA` ~line 2315, `SCHEMA_MIGRATIONS` ~line 2368, `loadDocumentsFromDb()` ~line 3288, new `computeFileHash()` near `safeFilename()` ~line 2722, `saveNewDocument()` ~line 7611, `createReviewDocumentFromFile()` ~line 7926) — re-verify all line numbers with `grep` before editing, since earlier edits within this task shift later ones.
- Test: `tests/test_duplicate_detection.py` (new)

**Interfaces:**
- Produces: `computeFileHash(file)` — `async function`, takes a `File`/`Blob`, returns a `Promise<string>` (lowercase hex SHA-256). Every `documents` row (in DB and in `allDocs`) gains a `file_hash` property (`string | null`). `window.__DEBUG_computeFileHash` and `window.__DEBUG_getFileHash(documentId)` test-only hooks.
- Consumes: `writeOriginalToSubfolder(id, baseName, file)` (unchanged signature — this task doesn't modify it, just calls `computeFileHash()` on the same `file` argument it already receives), `resolveFileHandle` (used only by later tasks, not this one).

#### Step 1: Add `file_hash` to `SCHEMA`

Find the `documents` table definition inside `SCHEMA` (confirm with `grep -n "searchable_pdf_built INTEGER DEFAULT 0" dossiary.html`):

```js
      archived INTEGER DEFAULT 0, needs_review INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0,
      searchable_pdf_built INTEGER DEFAULT 0
    );
```

Change to:

```js
      archived INTEGER DEFAULT 0, needs_review INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0,
      searchable_pdf_built INTEGER DEFAULT 0, file_hash TEXT
    );
```

#### Step 2: Add the migration entry

Find `SCHEMA_MIGRATIONS` (confirm with `grep -n "ALTER TABLE reminder_snoozes ADD COLUMN dismissed"`):

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
    'ALTER TABLE reminder_snoozes ADD COLUMN dismissed INTEGER DEFAULT 0',
  ];
```

Add one more entry at the end:

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
    'ALTER TABLE reminder_snoozes ADD COLUMN dismissed INTEGER DEFAULT 0',
    'ALTER TABLE documents ADD COLUMN file_hash TEXT',
  ];
```

#### Step 3: Add `computeFileHash()`

Find `safeFilename()` (confirm with `grep -n "function safeFilename"`, currently ~line 2722-2727):

```js
  function safeFilename(name, fallback){
    if(!name) name = fallback;
    let cleaned = name.replace(/[^a-zA-Z0-9\-_. ()]/g, '_').trim();
    cleaned = cleaned.replace(/^\.+/, '');
    return cleaned || fallback;
  }
```

Insert immediately after it:

```js
  // Lowercase hex SHA-256 of `file`'s own bytes, via the Web Crypto API --
  // used for exact-duplicate detection (see the "Duplicate detection" note
  // in CLAUDE.md). Always hash the ORIGINAL uploaded bytes, never a
  // possibly-rebuilt active file (buildSearchablePdf() can embed a fresh
  // timestamp on otherwise-identical source images), so two truly
  // identical uploads always produce the same hash regardless of what
  // OCR/processing happens to either of them afterward.
  async function computeFileHash(file){
    const buffer = await file.arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', buffer);
    return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
  }
```

#### Step 4: Read `file_hash` back in `loadDocumentsFromDb()`

Find the `SELECT` (confirm with `grep -n "FROM documents" dossiary.html`, currently ~line 3292-3296):

```js
    const { columns, rows } = queryAll(`
      SELECT id, title, category, subcategory, document_type, date, import_date, notes,
             ocr_text, ocr_language, file_path, original_file_path, created_at, source, source_legacy_id, thumbnail_path, archived, needs_review, deleted
      FROM documents
    `);
```

Change to:

```js
    const { columns, rows } = queryAll(`
      SELECT id, title, category, subcategory, document_type, date, import_date, notes,
             ocr_text, ocr_language, file_path, original_file_path, created_at, source, source_legacy_id, thumbnail_path, archived, needs_review, deleted, file_hash
      FROM documents
    `);
```

Find the `allDocs.push()` inside the same function's row loop (confirm with `grep -n "deleted: !!row\[idx.deleted\]"`, currently ~line 3358-3377):

```js
        deleted: !!row[idx.deleted],
        customFields: fieldValuesByDocId[id] || {}, // { "Organization": "Dr. Schröter", "Paid": "1", ... }
```

Change to:

```js
        deleted: !!row[idx.deleted],
        file_hash: row[idx.file_hash] || null,
        customFields: fieldValuesByDocId[id] || {}, // { "Organization": "Dr. Schröter", "Paid": "1", ... }
```

#### Step 5: Compute and store the hash in `saveNewDocument()`

Find (confirm with `grep -n "Preserve the untouched original from the moment"` — the comment appears twice in the file, once above `writeOriginalToSubfolder()`'s own definition and once above its call site inside `saveNewDocument()`; use the one inside `saveNewDocument()`, currently ~line 7629-7633):

```js
      const baseName = safeFilename((el('f-title').value.trim() || pendingFile.name.replace(/\.[^.]+$/, '')), 'document');
      // Preserve the untouched original from the moment the document is added,
      // regardless of file type or whether a searchable PDF gets built below.
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, pendingFile);
      let searchablePdfBuilt = 0;
```

Change to:

```js
      const baseName = safeFilename((el('f-title').value.trim() || pendingFile.name.replace(/\.[^.]+$/, '')), 'document');
      // Preserve the untouched original from the moment the document is added,
      // regardless of file type or whether a searchable PDF gets built below.
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, pendingFile);
      // Reuse the hash already computed when this file was picked (see
      // handlePickedFile()) rather than re-hashing the same bytes -- fall back to
      // computing it fresh if, for whatever reason, no pick-time hash was cached
      // for this exact file (e.g. a future call site that sets pendingFile without
      // going through handlePickedFile()).
      const fileHashForDb = (pendingFileHash && pendingFileHashFile === pendingFile)
        ? pendingFileHash
        : await computeFileHash(pendingFile);
      let searchablePdfBuilt = 0;
```

Find the `INSERT INTO documents` statement inside `saveNewDocument()` (confirm with `grep -n "INSERT INTO documents (id, title, category, subcategory, document_type, date," dossiary.html` — there are two very similar-looking `INSERT INTO documents` statements in the file, one in `saveNewDocument()` and one in `createReviewDocumentFromFile()`; use the one whose column list includes `searchable_pdf_built` but NOT `needs_review`, currently ~line 7696-7701):

```js
      db.run(`
        INSERT INTO documents (id, title, category, subcategory, document_type, date,
                                import_date, notes, ocr_text, ocr_language, file_path, original_file_path,
                                created_at, source, source_legacy_id, thumbnail_path, searchable_pdf_built)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'captured', NULL, ?, ?)
      `, [id, title, category, subcategory, documentType, date, importDate, notes, ocrText, ocrLanguage, filePathForDb, originalFilePathForDb, createdAt, thumbnailPathForDb, searchablePdfBuilt]);
```

Change to:

```js
      db.run(`
        INSERT INTO documents (id, title, category, subcategory, document_type, date,
                                import_date, notes, ocr_text, ocr_language, file_path, original_file_path,
                                created_at, source, source_legacy_id, thumbnail_path, searchable_pdf_built, file_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'captured', NULL, ?, ?, ?)
      `, [id, title, category, subcategory, documentType, date, importDate, notes, ocrText, ocrLanguage, filePathForDb, originalFilePathForDb, createdAt, thumbnailPathForDb, searchablePdfBuilt, fileHashForDb]);
```

Find the matching `allDocs.push()` a few lines below (confirm with `grep -n "thumbnail_path: thumbnailPathForDb, customFields: customFieldsForDoc,"`, currently ~line 7756-7763):

```js
      allDocs.push({
        id, title, category, subcategory, document_type: documentType, date,
        import_date: importDate,
        notes, ocr_text: ocrText, ocr_language: ocrLanguage, file_path: filePathForDb,
        original_file_path: originalFilePathForDb, created_at: createdAt, source: 'captured', source_legacy_id: null,
        thumbnail_path: thumbnailPathForDb, customFields: customFieldsForDoc,
        personFieldValues: personFieldValuesForDoc, tags: tagsForDoc, people: peopleForDoc,
      });
```

Change to:

```js
      allDocs.push({
        id, title, category, subcategory, document_type: documentType, date,
        import_date: importDate,
        notes, ocr_text: ocrText, ocr_language: ocrLanguage, file_path: filePathForDb,
        original_file_path: originalFilePathForDb, created_at: createdAt, source: 'captured', source_legacy_id: null,
        thumbnail_path: thumbnailPathForDb, file_hash: fileHashForDb, customFields: customFieldsForDoc,
        personFieldValues: personFieldValuesForDoc, tags: tagsForDoc, people: peopleForDoc,
      });
```

#### Step 6: Declare `pendingFileHash`/`pendingFileHashFile` module state

Find the `pendingFile`-family declarations (confirm with `grep -n "let pendingPdfOcrPages = null"`, currently ~line 2519-2523):

```js
  let pendingFile = null;
  let pendingOcrText = '';
  let pendingOcrWords = null;      // flat array of {text, bbox:{x0,y0,x1,y1}} from Tesseract, or null if no OCR run
  let pendingImageDims = null;     // {width, height} in pixels of the picked image, or null for non-images
  let pendingPdfOcrPages = null;   // array of {dataUrl, imageFormat, dims, words} per page (one entry per PDF page), or null if no PDF OCR run
```

Add two more lines:

```js
  let pendingFile = null;
  let pendingOcrText = '';
  let pendingOcrWords = null;      // flat array of {text, bbox:{x0,y0,x1,y1}} from Tesseract, or null if no OCR run
  let pendingImageDims = null;     // {width, height} in pixels of the picked image, or null for non-images
  let pendingPdfOcrPages = null;   // array of {dataUrl, imageFormat, dims, words} per page (one entry per PDF page), or null if no PDF OCR run
  let pendingFileHash = null;      // SHA-256 hex of pendingFile's bytes, computed once at pick time -- see handlePickedFile()
  let pendingFileHashFile = null;  // the exact File object pendingFileHash was computed for, so a later pick can tell whether the cached hash is still valid
```

(Task 2 is the one that actually computes and assigns these two variables, in `handlePickedFile()`; this task only declares them and reads them back in `saveNewDocument()`'s fallback logic above, matching the "pick-time hash cached and reused" design decision.)

#### Step 7: Compute and store the hash in `createReviewDocumentFromFile()`

Find (confirm with `grep -n "async function createReviewDocumentFromFile"`, currently ~line 7926-7979):

```js
  async function createReviewDocumentFromFile(file, source){
    const id = nextDocId++;
    try{
      const baseName = safeFilename(file.name.replace(/\.[^.]+$/, ''), 'document');
      const ext = (file.name.match(/\.[^.]+$/) || [''])[0];
      const destName = ext ? `${id}_${baseName}${ext}` : `${id}_${baseName}_file`;
      const destHandle = await filesDirHandle.getFileHandle(destName, { create: true });
      const writable = await destHandle.createWritable();
      await writable.write(await file.arrayBuffer());
      await writable.close();

      // Preserve the untouched original from the moment the document is added --
      // neither Inbox nor drag-and-drop ever run OCR automatically, so this
      // document is always unprocessed at this point (searchable_pdf_built
      // stays 0 below).
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, file);
```

Change to:

```js
  async function createReviewDocumentFromFile(file, source){
    const id = nextDocId++;
    try{
      const baseName = safeFilename(file.name.replace(/\.[^.]+$/, ''), 'document');
      const ext = (file.name.match(/\.[^.]+$/) || [''])[0];
      const destName = ext ? `${id}_${baseName}${ext}` : `${id}_${baseName}_file`;
      const destHandle = await filesDirHandle.getFileHandle(destName, { create: true });
      const writable = await destHandle.createWritable();
      await writable.write(await file.arrayBuffer());
      await writable.close();

      // Preserve the untouched original from the moment the document is added --
      // neither Inbox nor drag-and-drop ever run OCR automatically, so this
      // document is always unprocessed at this point (searchable_pdf_built
      // stays 0 below).
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, file);
      const fileHashForDb = await computeFileHash(file);
```

(Task 3 is the one that turns this hash into an actual duplicate-skip decision; this task only computes and stores it unconditionally, so every newly-created document has a `file_hash` from this point on regardless of which task lands first within this plan's own execution order.)

Find the `INSERT INTO documents` statement a few lines below (confirm with `grep -n "VALUES (?, ?, NULL, NULL, ?, NULL, ?, NULL, NULL, NULL, ?, ?, ?, ?, NULL, ?, 1, 0)"`, currently ~line 7956-7961):

```js
      db.run(`
        INSERT INTO documents (id, title, category, subcategory, document_type, date,
                                import_date, notes, ocr_text, ocr_language, file_path, original_file_path,
                                created_at, source, source_legacy_id, thumbnail_path, needs_review, searchable_pdf_built)
        VALUES (?, ?, NULL, NULL, ?, NULL, ?, NULL, NULL, NULL, ?, ?, ?, ?, NULL, ?, 1, 0)
      `, [id, title, documentType, createdAt, filePathForDb, originalFilePathForDb, createdAt, source, thumbnailPathForDb]);
```

Change to:

```js
      db.run(`
        INSERT INTO documents (id, title, category, subcategory, document_type, date,
                                import_date, notes, ocr_text, ocr_language, file_path, original_file_path,
                                created_at, source, source_legacy_id, thumbnail_path, needs_review, searchable_pdf_built, file_hash)
        VALUES (?, ?, NULL, NULL, ?, NULL, ?, NULL, NULL, NULL, ?, ?, ?, ?, NULL, ?, 1, 0, ?)
      `, [id, title, documentType, createdAt, filePathForDb, originalFilePathForDb, createdAt, source, thumbnailPathForDb, fileHashForDb]);
```

Find the matching `allDocs.push()` (confirm with `grep -n "archived: false, needs_review: true, deleted: false,"`, currently ~line 7966-7972):

```js
      allDocs.push({
        id, title, category: null, subcategory: null, document_type: documentType,
        date: null, import_date: createdAt, notes: null, ocr_text: null, ocr_language: null, file_path: filePathForDb,
        original_file_path: originalFilePathForDb, created_at: createdAt, source, source_legacy_id: null,
        thumbnail_path: thumbnailPathForDb, archived: false, needs_review: true, deleted: false,
        customFields: {}, personFieldValues: {}, tags: [], people: [],
      });
```

Change to:

```js
      allDocs.push({
        id, title, category: null, subcategory: null, document_type: documentType,
        date: null, import_date: createdAt, notes: null, ocr_text: null, ocr_language: null, file_path: filePathForDb,
        original_file_path: originalFilePathForDb, created_at: createdAt, source, source_legacy_id: null,
        thumbnail_path: thumbnailPathForDb, file_hash: fileHashForDb, archived: false, needs_review: true, deleted: false,
        customFields: {}, personFieldValues: {}, tags: [], people: [],
      });
```

#### Step 8: Add two test-only debug hooks

Find `window.__DEBUG_getCustomFieldValue` (confirm with `grep -n "window.__DEBUG_getCustomFieldValue"`, currently ~line 3687-3690):

```js
  window.__DEBUG_getCustomFieldValue = (documentId, fieldName) => {
    const d = allDocs.find(x => x.id === documentId);
    return d && d.customFields ? d.customFields[fieldName] : undefined;
  };
```

Add immediately after:

```js
  // Test-only: read a document's own persisted file_hash directly, and expose
  // computeFileHash() itself so a test can independently verify its output
  // against a hand-computed SHA-256 for known byte content.
  window.__DEBUG_getFileHash = (documentId) => {
    const d = allDocs.find(x => x.id === documentId);
    return d ? d.file_hash : undefined;
  };
  window.__DEBUG_computeFileHash = computeFileHash;
```

#### Step 9: Write the failing test

Create `tests/test_duplicate_detection.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, hashlib
from playwright.async_api import async_playwright

# Two byte strings used throughout this file: DOC_A_BYTES/DOC_B_BYTES are
# genuinely different content (so documents built from them get different
# hashes); DOC_A_BYTES is reused verbatim for a second document to prove two
# documents built from IDENTICAL bytes get the SAME hash.
DOC_A_BYTES = b'%PDF-1.4 fake pdf content A for duplicate-detection tests'
DOC_B_BYTES = b'%PDF-1.4 completely different fake pdf content B'

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

        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        # === Scenario 1: computeFileHash() matches a hand-computed SHA-256 ===
        js_hash = await page.evaluate(
            "async (bytes) => { const buf = new Uint8Array(bytes).buffer; const file = new File([buf], 'x.pdf', {type: 'application/pdf'}); return await window.__DEBUG_computeFileHash(file); }",
            list(DOC_A_BYTES),
        )
        expected_hash = hashlib.sha256(DOC_A_BYTES).hexdigest()
        print("computeFileHash() matches hashlib.sha256():", js_hash == expected_hash)

        # === Scenario 2: two documents captured from byte-identical files get the
        # same file_hash; a third captured from different bytes gets a different one ===
        async def capture_document(title, file_bytes, filename):
            await page.click('#add-btn')
            await page.wait_for_timeout(100)
            await page.set_input_files('#file-input', {
                'name': filename, 'mimeType': 'application/pdf', 'buffer': file_bytes,
            })
            await page.wait_for_timeout(150)
            await page.fill('#f-title', title)
            await page.click('#save-doc-btn')
            await page.wait_for_timeout(200)

        await capture_document('Doc A1', DOC_A_BYTES, 'a1.pdf')
        await capture_document('Doc A2 (same bytes as A1)', DOC_A_BYTES, 'a2.pdf')
        await capture_document('Doc B (different bytes)', DOC_B_BYTES, 'b.pdf')

        hash_a1 = await page.evaluate("window.__DEBUG_getFileHash(1)")
        hash_a2 = await page.evaluate("window.__DEBUG_getFileHash(2)")
        hash_b = await page.evaluate("window.__DEBUG_getFileHash(3)")
        print("Doc A1 has a non-null file_hash:", hash_a1 is not None and len(hash_a1) == 64)
        print("Doc A1 and Doc A2 (identical bytes) share the same file_hash:", hash_a1 == hash_a2)
        print("Doc A1 and Doc B (different bytes) have different file_hash values:", hash_a1 != hash_b)
        print("Doc A1's file_hash matches hashlib.sha256() of its own bytes:", hash_a1 == hashlib.sha256(DOC_A_BYTES).hexdigest())

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

#### Step 10: Run it to confirm it fails before the implementation lands

Run: `cd tests && python3 test_duplicate_detection.py`
Expected: a Python/Playwright error or a `False`/`None` result on every `file_hash`-related line, since `computeFileHash`/`file_hash` don't exist yet before Steps 1-8 are applied.

(If you're implementing Steps 1-8 and this test in the same pass, as this plan's own step order suggests, you can instead run this once at the very end, after Step 8 — either order is fine; the point of Step 10 in isolation only matters if you're following strict red-green TDD with a reviewer checking the intermediate red state.)

#### Step 11: Implement Steps 1-8 above, then run the test again

Run: `cd tests && python3 test_duplicate_detection.py`
Expected:
```
computeFileHash() matches hashlib.sha256(): True
Doc A1 has a non-null file_hash: True
Doc A1 and Doc A2 (identical bytes) share the same file_hash: True
Doc A1 and Doc B (different bytes) have different file_hash values: True
Doc A1's file_hash matches hashlib.sha256() of its own bytes: True
JS ERRORS: []
```

#### Step 12: Run the broader suite to confirm no regressions

Run: `cd tests && python3 test_reports.py && python3 test_inbox.py && python3 test_drag_drop.py`
Expected: every existing print line unchanged from before this task, `JS ERRORS: []` in all three.

#### Step 13: Commit

```bash
git add dossiary.html tests/test_duplicate_detection.py
git commit -m "feat: compute and store a SHA-256 file_hash for every new document"
```

---

### Task 2: Capture-time non-blocking duplicate warning

**Files:**
- Modify: `dossiary.html` (`handlePickedFile()` ~line 7358, its surrounding HTML ~line 7223, i18n keys in all 6 `STRINGS` blocks)
- Test: `tests/test_duplicate_detection.py` (extend)

**Interfaces:**
- Consumes: `computeFileHash(file)`, `pendingFileHash`/`pendingFileHashFile` (Task 1), `allDocs` (each document's `file_hash`), `el()`, `t()`, `escapeHtml()`, `openDetail()`, `setView()` — all pre-existing or from Task 1.
- Produces: no new functions consumed by later tasks — this task is UI-only, self-contained.

#### Step 1: Add the warning's HTML placeholder

Find `#file-preview-area` (confirm with `grep -n 'id="file-preview-area"'`, currently ~line 7223):

```html
          <div id="file-preview-area"></div>
```

Change to:

```html
          <div id="file-preview-area"></div>
          <div class="field-guess-hint" id="f-duplicate-warning" style="display:none;"></div>
```

#### Step 2: Wire the hash-and-check into `handlePickedFile()`

Find `handlePickedFile()` (confirm with `grep -n "function handlePickedFile"`, currently ~line 7358-7394):

```js
  function handlePickedFile(file){
    pendingFile = file;
    pendingOcrWords = null;
    pendingImageDims = null;
    pendingPdfOcrPages = null;
    // Clear any OCR text left over from a previously-picked file -- otherwise it
    // lingers in the textarea (and in pendingOcrText, which would get saved) across
    // a file switch, even though it no longer has anything to do with this file.
    pendingOcrText = '';
    el('f-ocr-text').value = '';
    el('save-doc-btn').disabled = false;
    const isImage = file.type.startsWith('image/');
    const isPdf = file.type === 'application/pdf';
    el('run-ocr-btn').disabled = !isImage && !isPdf;
    el('ocr-lang').disabled = !isImage && !isPdf;

    const previewArea = el('file-preview-area');
```

Change to:

```js
  function handlePickedFile(file){
    pendingFile = file;
    pendingOcrWords = null;
    pendingImageDims = null;
    pendingPdfOcrPages = null;
    pendingFileHash = null;
    pendingFileHashFile = null;
    el('f-duplicate-warning').style.display = 'none';
    // Clear any OCR text left over from a previously-picked file -- otherwise it
    // lingers in the textarea (and in pendingOcrText, which would get saved) across
    // a file switch, even though it no longer has anything to do with this file.
    pendingOcrText = '';
    el('f-ocr-text').value = '';
    el('save-doc-btn').disabled = false;
    const isImage = file.type.startsWith('image/');
    const isPdf = file.type === 'application/pdf';
    el('run-ocr-btn').disabled = !isImage && !isPdf;
    el('ocr-lang').disabled = !isImage && !isPdf;

    // Fire-and-forget, same pattern as getPdfPageCount()'s own .then() below --
    // hashing is fast and purely informational (Save stays enabled either way),
    // so this never blocks the rest of handlePickedFile() from running. Guarded
    // by pendingFile === file so a fast pick-another-file doesn't let a stale
    // hash/warning land on the new file's preview after this one resolves late.
    computeFileHash(file).then(hash => {
      if(pendingFile !== file) return;
      pendingFileHash = hash;
      pendingFileHashFile = file;
      const match = allDocs.find(d => !d.deleted && d.file_hash === hash);
      const warningEl = el('f-duplicate-warning');
      if(match){
        warningEl.innerHTML = `${t('captureDuplicateWarning', {title: escapeHtml(displayName(match)), id: match.id})} <button type="button" class="link-btn" id="f-duplicate-warning-open-btn">${t('captureDuplicateWarningOpenBtn')}</button> <button type="button" class="link-btn" id="f-duplicate-warning-dismiss-btn">${t('captureDuplicateWarningDismissBtn')}</button>`;
        warningEl.style.display = 'block';
        el('f-duplicate-warning-open-btn').addEventListener('click', () => {
          closeModal();
          selectedDocId = match.id;
          render();
          openDetail(match.id);
        });
        el('f-duplicate-warning-dismiss-btn').addEventListener('click', () => {
          warningEl.style.display = 'none';
        });
      }else{
        warningEl.style.display = 'none';
      }
    });

    const previewArea = el('file-preview-area');
```

#### Step 3: Add the `.link-btn` CSS

Find `.field-guess-hint` (confirm with `grep -n "field-guess-hint{"`, currently ~line 451):

```css
  .field-guess-hint{ font-family:var(--font-mono); font-size:10.5px; color:var(--amber); margin-top:5px; }
```

Add immediately after:

```css
  .field-guess-hint .link-btn{ background:transparent; border:none; padding:0; margin-left:6px; color:var(--amber); text-decoration:underline; cursor:pointer; font-family:var(--font-mono); font-size:10.5px; }
  .field-guess-hint .link-btn:hover{ color:var(--phosphor); }
```

#### Step 4: Add the two new i18n keys to all six languages

Find `captureDateGuessHint:` in each language block (confirm with `grep -n "captureDateGuessHint:"` — 6 matches, one per language in `en`/`es`/`fr`/`de`/`zh-Hans`/`zh-Hant` order) and add the two new keys immediately after it on the same line/block.

**English:**
```js
captureDateGuessHint: '...(existing value, unchanged)...', captureDuplicateWarning: 'This file looks identical to "{title}" (#{id}).', captureDuplicateWarningOpenBtn: 'Open it', captureDuplicateWarningDismissBtn: 'Dismiss',
```

**Spanish:**
```js
captureDuplicateWarning: 'Este archivo parece idéntico a "{title}" (#{id}).', captureDuplicateWarningOpenBtn: 'Abrirlo', captureDuplicateWarningDismissBtn: 'Descartar',
```

**French:**
```js
captureDuplicateWarning: 'Ce fichier semble identique à « {title} » (#{id}).', captureDuplicateWarningOpenBtn: 'L\'ouvrir', captureDuplicateWarningDismissBtn: 'Ignorer',
```

**German:**
```js
captureDuplicateWarning: 'Diese Datei scheint identisch mit "{title}" (#{id}) zu sein.', captureDuplicateWarningOpenBtn: 'Öffnen', captureDuplicateWarningDismissBtn: 'Verwerfen',
```

**Chinese Simplified:**
```js
captureDuplicateWarning: '此文件似乎与 "{title}"（#{id}）相同。', captureDuplicateWarningOpenBtn: '打开', captureDuplicateWarningDismissBtn: '忽略',
```

**Chinese Traditional:**
```js
captureDuplicateWarning: '此文件似乎與 "{title}"（#{id}）相同。', captureDuplicateWarningOpenBtn: '打開', captureDuplicateWarningDismissBtn: '忽略',
```

Do not literally insert the placeholder text `'...(existing value, unchanged)...'` shown above for English — that line is illustrating where the new keys attach; keep the real, already-existing `captureDateGuessHint` value exactly as it is in the file today, and only append the three new keys after it, exactly as they already do for every other densely-packed line in this file's `STRINGS` blocks.

#### Step 5: Add the test scenarios

Extend `tests/test_duplicate_detection.py`, inserting before the final `print("JS ERRORS:", errors)` line:

```python
        # === Scenario 3: picking a file byte-identical to an already-saved document
        # shows a non-blocking warning immediately, naming that document ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'a3.pdf', 'mimeType': 'application/pdf', 'buffer': DOC_A_BYTES,
        })
        await page.wait_for_timeout(150)
        warning_visible = await page.locator('#f-duplicate-warning').is_visible()
        warning_text = await page.locator('#f-duplicate-warning').inner_text()
        print("Duplicate warning visible for a byte-identical pick:", warning_visible)
        print("Duplicate warning names the matched document:", 'Doc A1' in warning_text and '#1' in warning_text)
        save_disabled = await page.locator('#save-doc-btn').is_disabled()
        print("Save button NOT disabled by the warning (non-blocking):", not save_disabled)
        await page.fill('#f-title', 'Doc A3 (also identical to A1)')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)
        save_succeeded = await page.evaluate("window.__DEBUG_getFileHash(4) !== undefined")
        print("Save succeeded despite the warning:", save_succeeded)

        # === Scenario 4: picking a file with no existing match shows no warning ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'c.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 yet another genuinely different file',
        })
        await page.wait_for_timeout(150)
        no_warning = not await page.locator('#f-duplicate-warning').is_visible()
        print("No warning shown for a file with no existing match:", no_warning)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)
```

(The capture modal is closed at the end so the test file leaves a clean state, since Task 3's own scenarios come next.)

#### Step 6: Run and verify

Run: `cd tests && python3 test_duplicate_detection.py`
Expected, appended to Task 1's own already-passing lines:
```
Duplicate warning visible for a byte-identical pick: True
Duplicate warning names the matched document: True
Save button NOT disabled by the warning (non-blocking): True
Save succeeded despite the warning: True
No warning shown for a file with no existing match: True
JS ERRORS: []
```

#### Step 7: Run `test_i18n_coverage.py` and a capture-form regression check

Run: `cd tests && python3 test_i18n_coverage.py && python3 test_studio2.py`
Expected: both pass, `JS ERRORS: []`. `test_i18n_coverage.py` confirms the 3 new keys exist in all 6 languages with matching key sets; `test_studio2.py` exercises the capture form's own existing OCR-related behavior, which this task's edits sit directly alongside.

#### Step 8: Commit

```bash
git add dossiary.html tests/test_duplicate_detection.py
git commit -m "feat: warn, non-blocking, when a picked file matches an existing document's hash"
```

---

### Task 3: Inbox / drag-and-drop duplicate skip-and-report

**Files:**
- Modify: `dossiary.html` (`createReviewDocumentFromFile()` ~line 7926, `addInboxFile()` ~line 7981, `addAllInboxFiles()` ~line 8000, `addDroppedFiles()` ~line 8017, `addAllInboxFilesAndShowStatus()` ~line 8057, i18n keys)
- Test: `tests/test_duplicate_detection.py` (extend)

**Interfaces:**
- Consumes: `computeFileHash(file)`, `file_hash` on `allDocs` entries (Task 1).
- Produces: `createReviewDocumentFromFile(file, source)` now returns `{ id, title, skippedDuplicate: false }` on success or `{ id: null, title: null, skippedDuplicate: true }` when skipped as a duplicate (still resolves, never throws, for that case) — still throws on a genuine I/O failure, unchanged. `addInboxFile(name)` now returns one of the strings `'added'` | `'skipped'` | `'failed'`. `addAllInboxFiles()` now returns `{ added, skipped, failed }` (all numbers) instead of nothing.

#### Step 1: Make `createReviewDocumentFromFile()` skip a hash match

Find (confirm with `grep -n "const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, file);" dossiary.html` — two matches; use the one inside `createReviewDocumentFromFile()`, immediately followed by the `fileHashForDb` line Task 1 Step 7 just added):

```js
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, file);
      const fileHashForDb = await computeFileHash(file);
```

Change to:

```js
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, file);
      const fileHashForDb = await computeFileHash(file);

      // An exact-hash match against an already-in-the-library document (deleted
      // ones excluded, same as every other duplicate-detection pass) means this
      // staged/dropped file is redundant -- an identical copy is already safely
      // stored, so no second document is created for it. The raw file this
      // function already wrote to `destHandle`/`filesDirHandle` above, and the
      // original it just preserved via writeOriginalToSubfolder(), are both
      // harmless orphaned copies at this point; they're not cleaned up here
      // (out of scope for this change -- this app already tolerates orphaned
      // files elsewhere, e.g. tags/people rows left behind after their last use).
      const duplicateMatch = allDocs.find(d => !d.deleted && d.file_hash === fileHashForDb);
      if(duplicateMatch){
        nextDocId--; // roll back the reservation -- no document was actually created
        return { id: null, title: null, skippedDuplicate: true };
      }
```

#### Step 2: Update the two existing success-path returns to include `skippedDuplicate: false`

Find the `return { id, title };` at the end of `createReviewDocumentFromFile()`'s `try` block (confirm with `grep -n "return { id, title };" dossiary.html`):

```js
      return { id, title };
```

Change to:

```js
      return { id, title, skippedDuplicate: false };
```

#### Step 3: Update `addInboxFile()` to handle and report a skip

Find (confirm with `grep -n "async function addInboxFile"`, currently ~line 7981-7998):

```js
  async function addInboxFile(name){
    const entry = pendingInboxFiles.find(f => f.name === name);
    if(!entry) return;
    try{
      const file = await entry.handle.getFile();
      const { id, title } = await createReviewDocumentFromFile(file, 'scan-inbox');

      await inboxDirHandle.removeEntry(name);
      pendingInboxFiles = pendingInboxFiles.filter(f => f.name !== name);

      renderStats(); populateFilters(); populateDatalists(); render();
      subLabel.textContent = rootDirHandle.name;
      updateInboxBanner();
      setStatusT('dragdropAddedFromInboxStatus', {title: title || t('commonDocumentFallback', {id}), id}, 'ok');
    }catch(e){
      setStatusT('dragdropAddFailedStatus', {name, error: e.message}, 'err');
    }
  }
```

Change to:

```js
  async function addInboxFile(name){
    const entry = pendingInboxFiles.find(f => f.name === name);
    if(!entry) return 'failed';
    try{
      const file = await entry.handle.getFile();
      const result = await createReviewDocumentFromFile(file, 'scan-inbox');

      // Removed from inbox/ either way -- a skipped duplicate's staged copy is
      // just as redundant as a successfully-added file's own staged copy once
      // it's been accounted for, since an identical copy already lives safely
      // in files/. This is the same explicit "Check inbox"/"Add all" click that
      // already removes every successfully-added file, not a new, separate
      // automatic deletion.
      await inboxDirHandle.removeEntry(name);
      pendingInboxFiles = pendingInboxFiles.filter(f => f.name !== name);

      renderStats(); populateFilters(); populateDatalists(); render();
      subLabel.textContent = rootDirHandle.name;
      updateInboxBanner();

      if(result.skippedDuplicate){
        setStatusT('dragdropSkippedDuplicateFromInboxStatus', {name}, 'ok');
        return 'skipped';
      }
      setStatusT('dragdropAddedFromInboxStatus', {title: result.title || t('commonDocumentFallback', {id: result.id}), id: result.id}, 'ok');
      return 'added';
    }catch(e){
      setStatusT('dragdropAddFailedStatus', {name, error: e.message}, 'err');
      return 'failed';
    }
  }
```

#### Step 4: Update `addAllInboxFiles()` to aggregate outcomes

Find (confirm with `grep -n "async function addAllInboxFiles"`, currently ~line 8000-8004):

```js
  async function addAllInboxFiles(){
    for(const name of pendingInboxFiles.map(f => f.name)){
      await addInboxFile(name);
    }
  }
```

Change to:

```js
  async function addAllInboxFiles(){
    const outcome = { added: 0, skipped: 0, failed: 0 };
    for(const name of pendingInboxFiles.map(f => f.name)){
      const result = await addInboxFile(name);
      outcome[result]++;
    }
    return outcome;
  }
```

#### Step 5: Update `addAllInboxFilesAndShowStatus()` to report the skip count

Find (confirm with `grep -n "async function addAllInboxFilesAndShowStatus"`, currently ~line 8057-8086):

```js
  async function addAllInboxFilesAndShowStatus(){
    const count = pendingInboxFiles.length;
    const folderLabel = `${rootDirHandle.name}/inbox/`;
    if(!count){
      setStatusT('dragdropNoFilesWaiting', {folder: folderLabel}, 'ok');
      return;
    }
    await addAllInboxFiles();
    const added = count - pendingInboxFiles.length;
    if(!added){
      setStatus(
        count === 1
          ? t('dragdropCouldNotAddAnyOfCountSingular', {count, folder: folderLabel})
          : t('dragdropCouldNotAddAnyOfCountPlural', {count, folder: folderLabel}),
        'err'
      );
      return;
    }
    setView('inbox');
    const failed = count - added;
    const addedPart = added === 1
      ? t('dragdropAddedToReviewQueueSingular', {count: added, folder: folderLabel})
      : t('dragdropAddedToReviewQueuePlural', {count: added, folder: folderLabel});
    const failedPart = failed
      ? (failed === 1
          ? t('dragdropPartialFailureStillThereSingular', {count: failed})
          : t('dragdropPartialFailureStillTherePlural', {count: failed}))
      : '';
    setStatus(addedPart + failedPart, failed ? 'err' : 'ok');
  }
```

Change to:

```js
  async function addAllInboxFilesAndShowStatus(){
    const count = pendingInboxFiles.length;
    const folderLabel = `${rootDirHandle.name}/inbox/`;
    if(!count){
      setStatusT('dragdropNoFilesWaiting', {folder: folderLabel}, 'ok');
      return;
    }
    const { added, skipped, failed } = await addAllInboxFiles();
    if(!added && !skipped){
      setStatus(
        count === 1
          ? t('dragdropCouldNotAddAnyOfCountSingular', {count, folder: folderLabel})
          : t('dragdropCouldNotAddAnyOfCountPlural', {count, folder: folderLabel}),
        'err'
      );
      return;
    }
    // Only jump to the Inbox view when something new actually needs reviewing --
    // a batch that was entirely duplicates has nothing new to look at there.
    if(added) setView('inbox');
    const parts = [];
    if(added){
      parts.push(added === 1
        ? t('dragdropAddedToReviewQueueSingular', {count: added, folder: folderLabel})
        : t('dragdropAddedToReviewQueuePlural', {count: added, folder: folderLabel}));
    }
    if(skipped){
      parts.push(skipped === 1
        ? t('dragdropSkippedDuplicatesSingular', {count: skipped})
        : t('dragdropSkippedDuplicatesPlural', {count: skipped}));
    }
    if(failed){
      parts.push(failed === 1
        ? t('dragdropPartialFailureStillThereSingular', {count: failed})
        : t('dragdropPartialFailureStillTherePlural', {count: failed}));
    }
    setStatus(parts.join(' '), failed ? 'err' : 'ok');
  }
```

#### Step 6: Update `addDroppedFiles()` to track and report skips

Find (confirm with `grep -n "async function addDroppedFiles"`, currently ~line 8017-8041):

```js
  async function addDroppedFiles(files){
    let added = 0, failed = 0, lastTitle = null, lastId = null;
    for(const file of files){
      try{
        const { id, title } = await createReviewDocumentFromFile(file, 'dropped');
        added++; lastId = id; lastTitle = title;
      }catch(e){ failed++; }
    }
    if(!added){
      if(failed === 1) setStatusT('dragdropDropFailedSingle', null, 'err');
      else setStatusT('dragdropDropFailedMulti', {count: failed}, 'err');
      return;
    }
    renderStats(); populateFilters(); populateDatalists(); render();
    setView('inbox');
    const addedMsg = added === 1
      ? t('dragdropAddedSingleForReview', {title: lastTitle || t('commonDocumentFallback', {id: lastId}), id: lastId})
      : t('dragdropAddedMultiForReview', {count: added});
    const failedMsg = failed
      ? (failed === 1
          ? t('dragdropPartialFailureSingular', {count: failed})
          : t('dragdropPartialFailurePlural', {count: failed}))
      : '';
    setStatus(addedMsg + failedMsg, failed ? 'err' : 'ok');
  }
```

Change to:

```js
  async function addDroppedFiles(files){
    let added = 0, skipped = 0, failed = 0, lastTitle = null, lastId = null;
    for(const file of files){
      try{
        const result = await createReviewDocumentFromFile(file, 'dropped');
        if(result.skippedDuplicate){ skipped++; continue; }
        added++; lastId = result.id; lastTitle = result.title;
      }catch(e){ failed++; }
    }
    if(!added && !skipped){
      if(failed === 1) setStatusT('dragdropDropFailedSingle', null, 'err');
      else setStatusT('dragdropDropFailedMulti', {count: failed}, 'err');
      return;
    }
    renderStats(); populateFilters(); populateDatalists(); render();
    if(added) setView('inbox');
    const parts = [];
    if(added){
      parts.push(added === 1
        ? t('dragdropAddedSingleForReview', {title: lastTitle || t('commonDocumentFallback', {id: lastId}), id: lastId})
        : t('dragdropAddedMultiForReview', {count: added}));
    }
    if(skipped){
      parts.push(skipped === 1
        ? t('dragdropSkippedDuplicatesSingular', {count: skipped})
        : t('dragdropSkippedDuplicatesPlural', {count: skipped}));
    }
    if(failed){
      parts.push(failed === 1
        ? t('dragdropPartialFailureSingular', {count: failed})
        : t('dragdropPartialFailurePlural', {count: failed}));
    }
    setStatus(parts.join(' '), failed ? 'err' : 'ok');
  }
```

#### Step 7: Add the new i18n keys to all six languages

Find `dragdropAddedFromInboxStatus:` (confirm with `grep -n "dragdropAddedFromInboxStatus:"` — 6 matches) and add a new key right after it in each language block:

**English** (after `dragdropAddedFromInboxStatus: 'Added "{title}" as #{id} from the inbox.',`):
```js
dragdropSkippedDuplicateFromInboxStatus: 'Skipped "{name}" -- an identical file is already in the library.',
```

**Spanish:**
```js
dragdropSkippedDuplicateFromInboxStatus: 'Se omitió "{name}": ya existe un archivo idéntico en la biblioteca.',
```

**French:**
```js
dragdropSkippedDuplicateFromInboxStatus: '« {name} » ignoré : un fichier identique existe déjà dans la bibliothèque.',
```

**German:**
```js
dragdropSkippedDuplicateFromInboxStatus: '"{name}" übersprungen -- eine identische Datei ist bereits in der Bibliothek vorhanden.',
```

**Chinese Simplified:**
```js
dragdropSkippedDuplicateFromInboxStatus: '已跳过 "{name}"——库中已存在相同的文件。',
```

**Chinese Traditional:**
```js
dragdropSkippedDuplicateFromInboxStatus: '已跳過 "{name}"——庫中已存在相同的文件。',
```

Find `dragdropAddedToReviewQueueSingular:`/`dragdropAddedToReviewQueuePlural:` (confirm with `grep -n "dragdropAddedToReviewQueueSingular:"` — 6 matches) and add two new keys right after each language's pair:

**English:**
```js
dragdropSkippedDuplicatesSingular: '{count} file was skipped as a duplicate.', dragdropSkippedDuplicatesPlural: '{count} files were skipped as duplicates.',
```

**Spanish:**
```js
dragdropSkippedDuplicatesSingular: 'Se omitió {count} archivo por ser un duplicado.', dragdropSkippedDuplicatesPlural: 'Se omitieron {count} archivos por ser duplicados.',
```

**French:**
```js
dragdropSkippedDuplicatesSingular: '{count} fichier a été ignoré (doublon).', dragdropSkippedDuplicatesPlural: '{count} fichiers ont été ignorés (doublons).',
```

**German:**
```js
dragdropSkippedDuplicatesSingular: '{count} Datei wurde als Duplikat übersprungen.', dragdropSkippedDuplicatesPlural: '{count} Dateien wurden als Duplikate übersprungen.',
```

**Chinese Simplified** (identical text in both slots, per this app's own established convention for a language with no grammatical plural):
```js
dragdropSkippedDuplicatesSingular: '已跳过 {count} 个重复文件。', dragdropSkippedDuplicatesPlural: '已跳过 {count} 个重复文件。',
```

**Chinese Traditional:**
```js
dragdropSkippedDuplicatesSingular: '已跳過 {count} 個重複文件。', dragdropSkippedDuplicatesPlural: '已跳過 {count} 個重複文件。',
```

#### Step 8: Add the test scenarios

Extend `tests/test_duplicate_detection.py`, again before the final `print("JS ERRORS:", errors)` line. This scenario needs a fresh seeded library with an `inbox/` folder already populated — build it via `window.__TEST_ROOT` the same way `test_inbox.py` does; re-read that file's own seeding helper if the exact shape below doesn't match current conventions, but the structure is:

```python
        # === Scenario 5: Inbox bulk-add skips an exact-duplicate staged file
        # (removing it from inbox/, reporting the skip count) while a genuinely
        # new staged file in the same batch is still added normally ===
        # Doc A1 (id 1) from earlier scenarios already has file_hash for DOC_A_BYTES.
        await page.evaluate("""
            async () => {
                const inboxDir = await window.__TEST_ROOT.getDirectoryHandle('inbox', { create: true });
                const dupFile = await inboxDir.getFileHandle('staged_duplicate.pdf', { create: true });
                const dupWritable = await dupFile.createWritable();
                await dupWritable.write(new TextEncoder().encode('%PDF-1.4 fake pdf content A for duplicate-detection tests'));
                await dupWritable.close();
                const newFile = await inboxDir.getFileHandle('staged_new.pdf', { create: true });
                const newWritable = await newFile.createWritable();
                await newWritable.write(new TextEncoder().encode('%PDF-1.4 a genuinely new staged file, never seen before'));
                await newWritable.close();
            }
        """)
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(300)
        status_text = await page.locator('#status').inner_text()
        print("Status line reports 1 added:", '1' in status_text and 'review' in status_text.lower())
        print("Status line reports 1 skipped as duplicate:", 'skipped' in status_text.lower() or 'duplicate' in status_text.lower())
        inbox_now_empty = await page.evaluate("""
            async () => {
                const inboxDir = await window.__TEST_ROOT.getDirectoryHandle('inbox', { create: true });
                const names = [];
                for await (const [name] of inboxDir.entries()) names.push(name);
                return names.length === 0;
            }
        """)
        print("Both staged files removed from inbox/ (duplicate skipped, new one added):", inbox_now_empty)
        new_doc_titles = await page.locator('#doc-tbody tr .doc-title').all_inner_texts()
        print("The genuinely new file became a real document:", any('staged_new' in t for t in new_doc_titles))
```

#### Step 9: Run and verify

Run: `cd tests && python3 test_duplicate_detection.py`
Expected: the new Scenario 5 lines all print `True`, alongside every line from Tasks 1-2 still printing exactly as before, `JS ERRORS: []`.

If the exact status-line substring checks above don't match the real rendered text (this plan wrote them loosely on purpose, in terms of what to look for, not exact wording, since the precise concatenation depends on Step 5/6's `parts.join(' ')` output) — read the actual status text the test prints out and tighten the assertions to check for the real key content (the added count, the skipped count, "duplicate" appearing somewhere) rather than leaving a loose check in the committed test.

#### Step 10: Run the broader suite

Run: `cd tests && python3 test_inbox.py && python3 test_drag_drop.py && python3 test_i18n_coverage.py`
Expected: every existing scenario in both files still passes unchanged (this task's changes are additive — a batch with zero duplicates behaves exactly as before, since `skipped` stays `0` and every `if(skipped)`/`if(added)` branch degrades to the old behavior), and `test_i18n_coverage.py` confirms the 3 new keys (1 singular-form status message, 2 singular/plural pairs) exist in all 6 languages.

#### Step 11: Commit

```bash
git add dossiary.html tests/test_duplicate_detection.py
git commit -m "feat: skip exact-duplicate files during Inbox/drag-and-drop bulk adds, with reporting"
```

---

### Task 4: "Find duplicates" modal

**Files:**
- Modify: `dossiary.html` (toolbar HTML ~line 694, new modal functions near `openRemindersModal()` ~line 5469, `resolveFileHandle()` usage, static button wiring near line 8337, i18n keys)
- Test: `tests/test_duplicate_detection.py` (extend)

**Interfaces:**
- Consumes: `file_hash` on `allDocs` (Task 1), `resolveFileHandle(relPath, create)`, `computeFileHash(file)`, `persistDb()`, `closeModal()`, `selectedDocId`, `render()`, `openDetail()`, `onModalKeydown`, `modalRoot`, `el()`, `t()`, `escapeHtml()`, `displayName()`.
- Produces: `openFindDuplicatesModal()` — the toolbar button's click handler; `window.__DEBUG_openFindDuplicatesModal` test-only hook.

#### Step 1: Add the toolbar button

Find (confirm with `grep -n 'id="check-reminders-btn"'`, currently ~line 695):

```html
        <button id="check-reminders-btn" data-i18n="toolbarCheckReminders">🔔 Check reminders</button>
```

Add immediately after:

```html
        <button id="check-reminders-btn" data-i18n="toolbarCheckReminders">🔔 Check reminders</button>
        <button id="find-duplicates-btn" data-i18n="toolbarFindDuplicates">🔍 Find duplicates</button>
```

#### Step 2: Add the grouping and backfill functions

Find `openRemindersModal()` (confirm with `grep -n "function openRemindersModal"`, currently ~line 5469). Insert everything below immediately **before** it (so these new functions sit right above the Reminders-modal family they're modeled on):

```js
  // Reads and hashes every not-yet-hashed, non-deleted document's file once,
  // persisting each result as it's computed. A missing/unreadable file (moved
  // or deleted from disk outside the app) is skipped for this pass, not a hard
  // error -- this app doesn't treat a missing file as fatal anywhere else
  // either, and the rest of the library still gets hashed. Every db.run() here
  // is batched into exactly one persistDb() call at the very end, by the
  // caller, matching this app's own "batch writes, persist once" convention
  // for bulk operations -- this function itself does NOT call persistDb().
  async function backfillFileHash(d){
    try{
      const relPath = d.original_file_path || d.file_path;
      const fileHandle = await resolveFileHandle(relPath, false);
      const file = await fileHandle.getFile();
      const hash = await computeFileHash(file);
      d.file_hash = hash;
      db.run('UPDATE documents SET file_hash = ? WHERE id = ?', [hash, d.id]);
    }catch(e){ /* file missing/unreadable -- leave file_hash null, not fatal */ }
  }

  // Groups `docs` (already filtered to non-deleted) by exact file_hash, keeping
  // only groups with 2+ members -- a document with no hash at all (backfill
  // failed for it, or somehow still null) never contributes to this pass.
  function computeExactHashDuplicateGroups(docs){
    const byHash = {};
    for(const d of docs){
      if(!d.file_hash) continue;
      (byHash[d.file_hash] = byHash[d.file_hash] || []).push(d);
    }
    return Object.values(byHash).filter(group => group.length >= 2);
  }

  // Groups `docs` by normalized (trimmed, case-insensitive) Title + exact Date,
  // keeping only groups with 2+ members. A document with a blank Title or blank
  // Date is excluded entirely -- matching on empty strings would produce
  // meaningless mass-groupings of every untitled/undated document.
  function computeMetadataDuplicateGroups(docs){
    const byKey = {};
    for(const d of docs){
      const title = (d.title || '').trim();
      const date = d.date || '';
      if(!title || !date) continue;
      const key = title.toLowerCase() + '|' + date;
      (byKey[key] = byKey[key] || []).push(d);
    }
    return Object.values(byKey).filter(group => group.length >= 2);
  }

  async function openFindDuplicatesModal(){
    const closeBtn = () => el('modal-close-btn');
    const unhashed = allDocs.filter(d => !d.deleted && !d.file_hash);

    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <h2>${t('duplicatesModalTitle')}</h2>
          <div id="duplicates-progress" style="display:${unhashed.length ? 'block' : 'none'};"></div>
          <div class="fs-list" id="duplicates-list" style="display:${unhashed.length ? 'none' : 'block'};"></div>
        </div>
      </div>
    `;

    let backfillRunning = unhashed.length > 0;
    const wireClose = () => {
      el('modal-close-btn').addEventListener('click', () => { if(!backfillRunning) closeModal(); });
      el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop' && !backfillRunning) closeModal(); });
      document.addEventListener('keydown', onModalKeydown);
    };
    wireClose();

    if(unhashed.length){
      // Close control disabled for the duration -- same "disable, only
      // re-enable on completion" treatment triggerScan() already uses for the
      // Scan/Scan Multi buttons, since this pass is already writing persisted
      // hashes to the database as it goes and isn't meant to be interrupted
      // mid-pass.
      el('modal-close-btn').disabled = true;
      const progressEl = el('duplicates-progress');
      let done = 0;
      for(const d of unhashed){
        progressEl.innerHTML = '<span class="spinner"></span> ' + t('duplicatesBackfillProgress', {done, total: unhashed.length});
        await backfillFileHash(d);
        done++;
      }
      progressEl.innerHTML = '<span class="spinner"></span> ' + t('duplicatesBackfillProgress', {done, total: unhashed.length});
      await persistDb();
      backfillRunning = false;
      el('modal-close-btn').disabled = false;
      el('duplicates-progress').style.display = 'none';
      el('duplicates-list').style.display = 'block';
    }

    const activeDocs = allDocs.filter(d => !d.deleted);
    const exactGroups = computeExactHashDuplicateGroups(activeDocs);
    const metadataGroups = computeMetadataDuplicateGroups(activeDocs);
    renderDuplicateGroups(exactGroups, metadataGroups);
  }

  function renderDuplicateGroups(exactGroups, metadataGroups){
    const listEl = el('duplicates-list');
    if(!exactGroups.length && !metadataGroups.length){
      listEl.innerHTML = `<p id="duplicates-empty">${t('duplicatesNoneFound')}</p>`;
      return;
    }
    const groupHtml = (group, labelKey) => `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label">${t(labelKey)}</div>
        ${group.map(d => `
          <div class="duplicate-row" data-document-id="${d.id}">
            <span class="doc-title">${escapeHtml(displayName(d))}</span>
            <span class="doc-sub">#${d.id}${d.date ? ' · ' + formatDate(d.date) : ''}</span>
          </div>
        `).join('')}
      </div>
    `;
    listEl.innerHTML = [
      ...exactGroups.map(g => groupHtml(g, 'duplicatesExactMatchLabel')),
      ...metadataGroups.map(g => groupHtml(g, 'duplicatesMetadataMatchLabel')),
    ].join('');
    listEl.querySelectorAll('.duplicate-row').forEach(row => {
      row.addEventListener('click', () => {
        const documentId = Number(row.dataset.documentId);
        closeModal();
        selectedDocId = documentId;
        render();
        openDetail(documentId);
      });
    });
  }

```

#### Step 3: Add a small amount of CSS

Find `.reminder-row` (confirm with `grep -n "\.reminder-row{"`) and add the new rules immediately after that whole `.reminder-row`/`.reminder-row-title`/`.reminder-row-sub` block:

```css
  .duplicate-group{ margin-bottom:14px; }
  .duplicate-group-label{ font-family:var(--font-mono); font-size:11px; color:var(--amber); text-transform:uppercase; letter-spacing:0.04em; margin-bottom:6px; }
  .duplicate-row{ display:flex; justify-content:space-between; gap:12px; padding:8px 10px; border-radius:var(--radius); cursor:pointer; }
  .duplicate-row:hover{ background:var(--ink-2); }
```

#### Step 4: Wire the toolbar button's click handler and expose the debug hook

Find `el('check-reminders-btn').addEventListener('click', checkRemindersAndShowStatus);` (confirm with `grep -n "check-reminders-btn').addEventListener"`) and add immediately after:

```js
  el('find-duplicates-btn').addEventListener('click', openFindDuplicatesModal);
```

Find `window.__DEBUG_openRemindersModal = openRemindersModal;` (confirm with `grep -n "window.__DEBUG_openRemindersModal"`) and add immediately after:

```js
  window.__DEBUG_openFindDuplicatesModal = openFindDuplicatesModal;
```

#### Step 5: Add the new i18n keys to all six languages

Find `reminderModalTitle:` (confirm with `grep -n "reminderModalTitle:"` — 6 matches) and add 6 new keys immediately after each language's reminder-keys block ends (same line, appended, matching this file's own dense-packing style):

**English:**
```js
duplicatesModalTitle: 'Find duplicates', duplicatesBackfillProgress: 'Checking {done} of {total} documents for duplicates…', duplicatesExactMatchLabel: 'Exact file match', duplicatesMetadataMatchLabel: 'Likely duplicate (title + date)', duplicatesNoneFound: 'No duplicates found.', toolbarFindDuplicates: '🔍 Find duplicates',
```

**Spanish:**
```js
duplicatesModalTitle: 'Buscar duplicados', duplicatesBackfillProgress: 'Comprobando {done} de {total} documentos en busca de duplicados…', duplicatesExactMatchLabel: 'Coincidencia exacta de archivo', duplicatesMetadataMatchLabel: 'Posible duplicado (título + fecha)', duplicatesNoneFound: 'No se encontraron duplicados.', toolbarFindDuplicates: '🔍 Buscar duplicados',
```

**French:**
```js
duplicatesModalTitle: 'Rechercher les doublons', duplicatesBackfillProgress: 'Vérification de {done} sur {total} documents pour les doublons…', duplicatesExactMatchLabel: 'Fichier identique', duplicatesMetadataMatchLabel: 'Doublon probable (titre + date)', duplicatesNoneFound: 'Aucun doublon trouvé.', toolbarFindDuplicates: '🔍 Rechercher les doublons',
```

**German:**
```js
duplicatesModalTitle: 'Duplikate finden', duplicatesBackfillProgress: 'Prüfe {done} von {total} Dokumenten auf Duplikate…', duplicatesExactMatchLabel: 'Exakte Dateiübereinstimmung', duplicatesMetadataMatchLabel: 'Wahrscheinliches Duplikat (Titel + Datum)', duplicatesNoneFound: 'Keine Duplikate gefunden.', toolbarFindDuplicates: '🔍 Duplikate finden',
```

**Chinese Simplified:**
```js
duplicatesModalTitle: '查找重复项', duplicatesBackfillProgress: '正在检查第 {done}/{total} 个文档是否重复……', duplicatesExactMatchLabel: '文件完全匹配', duplicatesMetadataMatchLabel: '可能重复（标题+日期）', duplicatesNoneFound: '未发现重复项。', toolbarFindDuplicates: '🔍 查找重复项',
```

**Chinese Traditional:**
```js
duplicatesModalTitle: '查找重複項', duplicatesBackfillProgress: '正在檢查第 {done}/{total} 個文檔是否重複……', duplicatesExactMatchLabel: '文件完全匹配', duplicatesMetadataMatchLabel: '可能重複（標題+日期）', duplicatesNoneFound: '未發現重複項。', toolbarFindDuplicates: '🔍 查找重複項',
```

#### Step 6: Add the test scenarios

Extend `tests/test_duplicate_detection.py`, before the final `print("JS ERRORS:", errors)` line:

```python
        # === Scenario 6: "Find duplicates" groups exact-hash matches and
        # Title+Date metadata matches correctly, excludes a blank-title/date
        # document, and clicking a document in a group opens its detail panel ===
        # By this point the library has: docs 1/2/4 sharing DOC_A_BYTES' hash
        # (Scenarios 2 and 3), doc 3 with a different hash, and doc 5 from
        # Scenario 4's no-warning pick (also a unique hash). None of these five
        # share a Title+Date pair yet, so add two more documents that do.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'meta1.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 metadata-match doc one',
        })
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Electric Bill')
        await page.fill('#f-date', '2026-03-01')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'meta2.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 metadata-match doc two, different bytes',
        })
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Electric Bill')
        await page.fill('#f-date', '2026-03-01')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)

        # A same-title, different-date document -- must NOT be grouped with the pair above.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'meta3.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 same title different date',
        })
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Electric Bill')
        await page.fill('#f-date', '2026-04-01')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)

        await page.evaluate("window.__DEBUG_openFindDuplicatesModal()")
        await page.wait_for_timeout(300)
        exact_labels = await page.locator('.duplicate-group-label').all_inner_texts()
        print("Modal shows at least one 'Exact file match' group:", any('Exact' in l for l in exact_labels))
        print("Modal shows at least one 'Likely duplicate' (title+date) group:", any('title' in l.lower() for l in exact_labels))

        # Exactly 2 documents share the Electric Bill / 2026-03-01 pairing (the
        # third, dated 2026-04-01, must not appear alongside them).
        all_group_text = await page.locator('#duplicates-list').inner_text()
        print("Both same-date Electric Bill documents appear together:", all_group_text.count('Electric Bill') >= 2)

        first_row = page.locator('.duplicate-row').first
        first_row_doc_id = await first_row.get_attribute('data-document-id')
        await first_row.click()
        await page.wait_for_timeout(200)
        modal_closed = await page.locator('#modal-backdrop').count() == 0
        detail_panel_text = await page.locator('#detail-panel-body').inner_text()
        print("Clicking a duplicate-group document closes the modal:", modal_closed)
        print("...and opens that exact document's detail panel:", f'#{first_row_doc_id}' in detail_panel_text)

        # === Scenario 7: a second "Find duplicates" open does not re-hash
        # already-hashed documents (no progress shown, since nothing is unhashed) ===
        await page.evaluate("window.__DEBUG_openFindDuplicatesModal()")
        await page.wait_for_timeout(300)
        progress_hidden = not await page.locator('#duplicates-progress').is_visible()
        print("No backfill progress shown on a second open (everything already hashed):", progress_hidden)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # === Scenario 8: a deleted document is excluded from every grouping pass ===
        # Doc A1/A2/A3 (ids 1, 2, 4) share DOC_A_BYTES' hash -- a 3-member exact-hash
        # group. Delete doc 4 (Doc A3) and confirm the group shrinks to 2 members,
        # and that doc 4's own title no longer appears anywhere in the modal.
        await page.click('tr[data-id="4"]')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)
        await page.evaluate("window.__DEBUG_openFindDuplicatesModal()")
        await page.wait_for_timeout(300)
        list_text_after_delete = await page.locator('#duplicates-list').inner_text()
        print("Deleted document's title no longer appears in any duplicate group:", 'Doc A3' not in list_text_after_delete)
        # The exact-hash group containing Doc A1 now has exactly 2 rows (A1 and A2),
        # not the original 3.
        exact_group_locator = page.locator('.duplicate-group').filter(has_text='Doc A1')
        exact_group_row_count = await exact_group_locator.locator('.duplicate-row').count()
        print("Exact-hash group shrinks from 3 to 2 members after the deletion:", exact_group_row_count == 2)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)
```

#### Step 7: Run and verify

Run: `cd tests && python3 test_duplicate_detection.py`
Expected: all Scenario 6-7 lines print `True`, every earlier scenario (Tasks 1-3) still prints exactly as before, `JS ERRORS: []`.

If any specific assertion above doesn't cleanly isolate what it's meant to check once you see the real rendered output (the loose `has_text`/substring checks are written defensively, not as exact strings, since the real HTML structure depends on how this step is actually implemented) — tighten them against the real DOM rather than leaving a check that could pass vacuously; in particular, confirm the "Both same-date Electric Bill documents appear together" check would actually go `False` if the grouping logic were broken (e.g. temporarily change `computeMetadataDuplicateGroups()`'s key to include a random per-render token and confirm the test then fails, then revert).

#### Step 8: Run the broader suite

Run: `cd tests && python3 test_i18n_coverage.py && python3 test_footer_pin.py`

Expected: `test_i18n_coverage.py` passes with the 8 new keys (6 in the biggest single block, plus `toolbarFindDuplicates`, plus the earlier tasks' own keys) present in all 6 languages. `test_footer_pin.py` is the important regression check here — adding a 5th toolbar button (`🔍 Find duplicates`) alongside the existing 4 (`📥`/`🔔`/`📷`/`📸`) is exactly the class of change that has repeatedly pushed `.toolbar` onto an extra wrapped row at specific desktop widths in this codebase's history, breaking `.table-wrap`'s sticky-header calibration by a few px each time. If `test_footer_pin.py` reports a new failure, follow the exact empirical methodology `CLAUDE.md`'s own `.table-wrap` note describes (a `getBoundingClientRect()` sweep across 700-1600px, confirming whether the real last row is actually clipped via `measure_last_row_not_clipped()` before assuming a CSS bump is even needed) rather than guessing at new pixel constants.

#### Step 9: Commit

```bash
git add dossiary.html tests/test_duplicate_detection.py
git commit -m "feat: add a 'Find duplicates' modal with exact-hash and title+date grouping"
```

---

### Task 5: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `tests/CLAUDE.md`

**Interfaces:**
- Consumes: the shipped behavior from Tasks 1-4 (this task only documents it, no code changes).

#### Step 1: Add a "Duplicate detection" architecture note to `CLAUDE.md`

Find the end of the "Bulk edit" note (the last bulleted architecture note in the file, right before the `## How this was tested` section — confirm with `grep -n "## How this was tested" CLAUDE.md` and read the paragraph immediately above it) and insert a new bullet after it, before `## How this was tested`:

```markdown
- **Duplicate detection** (`documents.file_hash`, `computeFileHash()`,
  `openFindDuplicatesModal()`) flags two kinds of likely-duplicate document:
  an exact match on the file's own bytes, and a heuristic match on
  Title + Date. **The hash is computed on the original uploaded bytes, not
  the active `file_path`** -- `buildSearchablePdf()` can rasterize-and-rebuild
  a captured file during OCR, and two byte-identical source scans processed
  through that pipeline at different moments can produce slightly different
  output bytes (embedded timestamps and similar); hashing the *processed*
  file would silently defeat exact-duplicate detection for exactly the case
  it exists to catch. Since `writeOriginalToSubfolder()` already
  unconditionally preserves every new document's raw upload, the hash is
  computed on that same original, at the same moment it's written --
  falling back to hashing `file_path` only for a document with no preserved
  original (a LibraryLifeboat-migrated document, predating this app's own
  ingestion pipeline).
  **New documents get their hash computed and stored at creation time**
  (`saveNewDocument()`, `createReviewDocumentFromFile()`) -- one file,
  already being read at that moment anyway. **Existing documents are
  backfilled lazily**: the first time "Find duplicates" is opened, it reads
  and hashes every not-yet-hashed document's file once, with a progress
  indicator (the same spinner-plus-status-text treatment `runOcr()`'s own
  PDF-page-by-page progress already uses), persisting each hash as it's
  computed (batched into a single `persistDb()` call at the end, not one
  per document) so every later scan and every capture-time check is
  instant. Until that first backfill runs, the capture-time warning can
  only catch matches against documents that already happen to have a hash.
  The modal's own close control (and backdrop-click) are disabled for the
  duration of a running backfill -- the same "disable, only re-enable on
  completion" treatment `triggerScan()` already uses for the Scan/Scan
  Multi buttons -- since the pass is already writing persisted hashes as
  it goes and isn't meant to be interrupted mid-pass.
  **The capture form warns, non-blocking, the moment a file is picked**
  (`handlePickedFile()`), checking the picked file's hash against every
  document's `file_hash` in `allDocs` and showing a dismissible
  `.field-guess-hint`-style line naming the matched document, with a link
  to open its detail panel -- Save stays enabled regardless. This checks
  the exact-hash case only, never Title+Date -- form fields may still be
  blank at pick time, so a heuristic warning that early would just be
  noise. The hash computed at pick time (`pendingFileHash`/
  `pendingFileHashFile`) is cached and reused at Save rather than
  recomputed, since nothing about the file changes in between.
  **Inbox and drag-and-drop bulk adds silently skip (with explicit
  reporting) a staged file whose hash exactly matches an existing
  document**, via the shared `createReviewDocumentFromFile(file, source)`
  helper both already call -- no document is created for it, its staged
  copy is removed from `inbox/` exactly like a normal successful add
  (an identical copy already lives safely in `files/`, so nothing unique
  is lost), and it's counted toward a new "N skipped as duplicates" clause
  on the status line, alongside the existing "Added N document(s)..."
  report. This is a genuine behavior change -- Inbox had never silently
  not-added a staged file before -- and the explicit status-line reporting
  is what keeps it from being *silent*, per this app's own "no silent
  writes" working convention: nothing here omits information from the
  person, it just avoids creating a redundant document.
  **"Find duplicates"** (a new toolbar button, alongside `🔔 Check
  reminders`/`📥 Check inbox` -- the same family of explicit, on-demand
  maintenance actions) opens a modal structured like the Reminders modal:
  after any needed backfill, `allDocs` (deleted documents excluded from
  every grouping pass; archived and needs-review documents included, same
  "tells the truth about the whole non-deleted library" reasoning
  Reports/Collections already use) is grouped two independent ways --
  `computeExactHashDuplicateGroups()` and `computeMetadataDuplicateGroups()`
  -- each producing its own rows, tagged "Exact file match" or "Likely
  duplicate (title + date)"; a document that happens to satisfy both
  passes simply appears in both groups' own rows, rather than being
  deduplicated across the two pass types. A document with a blank Title or
  blank Date is excluded from the Title+Date pass entirely, since matching
  against an empty string would produce meaningless mass-groupings.
  Clicking a document in a group closes the modal, selects that document,
  and opens its detail panel -- the same click-through pattern the
  Reminders modal's own rows already use -- where the existing
  Archive/Delete/Edit actions do the actual resolving; this feature adds
  no bespoke delete or merge action of its own. See
  `docs/superpowers/specs/2026-09-24-duplicate-detection-design.md` for
  the full design.
```

#### Step 2: Extend `tests/CLAUDE.md`'s test-coverage narrative

Find the end of the "bulk-editing across a multi-document selection" paragraph (confirm with `grep -n "row's own checkbox stays checked immediately after a save), and the Scan/Scan Multi"` in `tests/CLAUDE.md`) — it currently reads (abbreviated; use the real surrounding text, this is just the anchor):

```
row's own checkbox stays checked immediately after a save), and the Scan/Scan Multi toolbar buttons (`test_scan_bridge.py` --
```

Insert a new sentence-clause immediately before `and the Scan/Scan Multi toolbar buttons`, so it reads (again, splice into the real surrounding sentence rather than replacing the whole paragraph):

```
row's own checkbox stays checked immediately after a save), duplicate
detection (`test_duplicate_detection.py` -- `computeFileHash()` matching a
hand-computed SHA-256 for known byte content; two documents captured from
byte-identical files sharing the same `file_hash` while a third, genuinely
different document gets a different one; the capture-time warning
appearing immediately (non-blocking -- Save still succeeds) when a picked
file's bytes match an already-saved document, and staying hidden for a
file with no match; an Inbox bulk-add batch where one staged file is an
exact duplicate (skipped, removed from `inbox/`, counted on the status
line) and a second staged file in the same batch is genuinely new (added
normally); the "Find duplicates" modal grouping an exact-hash match and a
Title+Date metadata match into separate, correctly-labeled groups, a
same-title-different-date document correctly excluded from the Title+Date
grouping, clicking a document in a group closing the modal and opening
its detail panel, and a second modal open not re-triggering the backfill
progress indicator once every document already has a hash), the
Scan/Scan Multi toolbar buttons (`test_scan_bridge.py` --
```

#### Step 3: Commit

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "docs: document the duplicate detection feature"
```
