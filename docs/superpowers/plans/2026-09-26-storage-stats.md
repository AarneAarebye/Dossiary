# Storage Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "💾 Storage stats" toolbar button and modal showing real disk usage for the open library — a grand total, a per-folder breakdown (`files/`/`thumbnails/`/`inbox/`/`library.sqlite`), and, within `files/`, an active/original/untracked split answering how much of the library's size is the doubled original-preservation overhead this app's own ingestion pipeline creates.

**Architecture:** `computeStorageStats()` walks the real `files/` (including each document's own original-preserving subfolder), `thumbnails/`, and `inbox/` folders via `for await (const [name, handle] of dirHandle.entries())` — the same iteration pattern `checkInbox()` already uses — reading each file's real size via `getFile().size` and classifying every file under `files/`/`thumbnails/` against `allDocs`' own `file_path`/`original_file_path`/`thumbnail_path` values. This is an independent, brand-new modal — not an extension of the existing "Library check" modal family — since it's a read-only overview, not a detect-and-fix check.

**Tech Stack:** Vanilla JS in `dossiary.html` (no framework), File System Access API, Playwright-driven Python test scripts against `tests/stub_studio2.js`.

## Global Constraints

- A brand new, independent toolbar button and modal — do NOT fold this into `openLibraryCheckModal()`/`renderLibraryCheckResults()`.
- The walk reads real files on disk (`files/`, `thumbnails/`, `inbox/`, `library.sqlite`) — never trusts `allDocs`' own tracked paths alone as the source of totals, since that would silently miss any file nothing in the database points to.
- Every file under `files/` is classified into exactly one of three buckets — active (matches some document's `file_path`), original (matches some document's `original_file_path`), or untracked (matches neither) — checked against **every** document in `allDocs`, Waste-bin documents included, since a soft-deleted document's files are never removed from disk.
- `thumbnails/` gets the same two-way active/untracked split (matched against `thumbnail_path`); `inbox/` is a flat, unsplit total.
- `library.sqlite`'s own size is added to the grand total but does not participate in the files/thumbnails/inbox breakdown.
- A missing `inbox/` folder is treated as zero, not an error (matching `checkInbox()`'s own existing precedent). A per-file read failure mid-walk is skipped, not fatal (matching `backfillFileHash()`'s own existing precedent).
- The walk runs immediately when the modal opens — no separate "Calculate" button inside the modal.
- Every size is shown with a human-readable, auto-scaling unit (KB/MB/GB), not a fixed unit.
- The "Untracked" row (in either `files/` or `thumbnails/`) is only rendered when its value is greater than zero — omitted entirely otherwise, matching this app's existing "omit sections/rows with nothing to show" convention.
- New i18n keys follow the established per-language dense-line convention, appended to the same line as the immediately preceding related keys, across all six languages (English, Spanish, French, German, Chinese Simplified, Chinese Traditional).
- Every test file must load `tests/stub_studio2.js` — never an embedded copy.

---

### Task 1: Compute and display storage stats

**Files:**
- Modify: `dossiary.html` (new `formatBytes()` and `computeStorageStats()` functions; new `openStorageStatsModal()` function; new toolbar button; new CSS; eleven new i18n keys across six languages; one new test-only debug hook)
- Test: `tests/test_storage_stats.py` (new file)

**Interfaces:**
- Consumes: `filesDirHandle` (existing module-level variable, dossiary.html:2420, already resolved to the library's `files/` directory handle at library-open time — always exists once a library is open). `rootDirHandle` (existing module-level variable, used to resolve `thumbnails/`, `inbox/`, and `library.sqlite` fresh, matching `writeThumbnail()`'s own `rootDirHandle.getDirectoryHandle('thumbnails', {create:true})` pattern and `checkInbox()`'s own `rootDirHandle.getDirectoryHandle('inbox', {create:false})` pattern). `allDocs` (existing module-level array — each document object already carries `d.file_path`, `d.original_file_path`, `d.thumbnail_path`, and `d.deleted`). `escapeHtml(s)`, `t(key, params)`, `closeModal()`, `onModalKeydown(e)`, `modalRoot`, `el(id)` (all existing).
- Produces: `formatBytes(bytes)` — sync function, takes a non-negative integer byte count, returns a human-readable string like `"1.2 MB"` (or `"512 B"` for anything under 1024 bytes). `computeStorageStats()` — async function, no parameters, returns a Promise resolving to `{ files: {active, original, untracked}, thumbnails: {active, untracked}, inbox, librarySqlite, filesTotal, thumbnailsTotal, grandTotal }`, every value a byte count (number). `openStorageStatsModal()` — async function, no parameters, the toolbar button's click handler.

- [ ] **Step 1: Add `formatBytes()`**

In `dossiary.html`, immediately after `computeFileHash()` (which ends at line 2763, right before the blank line and `async function ensureSqlJs(){`), insert:

```javascript
  // Formats a byte count as a human-readable, auto-scaling string (B/KB/MB/GB/TB)
  // -- generalizes the ad-hoc (file.size/1024).toFixed(0) KB-only formatting the
  // capture form's own picked-file-size preview already uses (see
  // pickedFileSizeKb), since a whole-library total can run well past what's
  // sensible to show in KB alone.
  function formatBytes(bytes){
    if(bytes < 1024) return `${bytes} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let value = bytes;
    let unitIndex = -1;
    do{
      value /= 1024;
      unitIndex++;
    }while(value >= 1024 && unitIndex < units.length - 1);
    return `${value.toFixed(1)} ${units[unitIndex]}`;
  }

```

- [ ] **Step 2: Add `computeStorageStats()`**

In `dossiary.html`, right after `formatBytes()`'s closing `}` (from Step 1), insert:

```javascript
  // Walks the real files/, thumbnails/, and inbox/ folders (plus library.sqlite's
  // own size) and sums real byte sizes via getFile().size -- never trusting
  // allDocs' own tracked paths alone, since that would silently miss anything on
  // disk no document row points to. Every file under files/ is classified as
  // 'active' (matches some document's file_path), 'original' (matches some
  // document's original_file_path), or 'untracked' (matches neither) --
  // Waste-bin documents are included in this comparison, since their files are
  // never touched on disk and are still real, space-consuming files. thumbnails/
  // gets the same two-way active/untracked split (matched against
  // thumbnail_path); inbox/ isn't split further, since every file there is
  // equally "not yet added." A per-file read failure mid-walk is skipped, not
  // fatal, the same reasoning backfillFileHash() already uses for a
  // missing/unreadable file.
  async function computeStorageStats(){
    const filePaths = new Set(allDocs.map(d => d.file_path).filter(Boolean));
    const originalPaths = new Set(allDocs.map(d => d.original_file_path).filter(Boolean));
    const thumbnailPaths = new Set(allDocs.map(d => d.thumbnail_path).filter(Boolean));

    const files = { active: 0, original: 0, untracked: 0 };
    for await (const [name, handle] of filesDirHandle.entries()){
      if(handle.kind === 'file'){
        const relPath = `files/${name}`;
        try{
          const size = (await handle.getFile()).size;
          if(filePaths.has(relPath)) files.active += size;
          else if(originalPaths.has(relPath)) files.original += size;
          else files.untracked += size;
        }catch(e){ /* unreadable file -- skip it, not fatal */ }
      }else if(handle.kind === 'directory'){
        try{
          for await (const [subName, subHandle] of handle.entries()){
            if(subHandle.kind !== 'file') continue;
            const relPath = `files/${name}/${subName}`;
            try{
              const size = (await subHandle.getFile()).size;
              if(filePaths.has(relPath)) files.active += size;
              else if(originalPaths.has(relPath)) files.original += size;
              else files.untracked += size;
            }catch(e){ /* unreadable file -- skip it, not fatal */ }
          }
        }catch(e){ /* unreadable subfolder -- skip it, not fatal */ }
      }
    }

    const thumbnails = { active: 0, untracked: 0 };
    try{
      const thumbsDir = await rootDirHandle.getDirectoryHandle('thumbnails', { create: false });
      for await (const [name, handle] of thumbsDir.entries()){
        if(handle.kind !== 'file') continue;
        const relPath = `thumbnails/${name}`;
        try{
          const size = (await handle.getFile()).size;
          if(thumbnailPaths.has(relPath)) thumbnails.active += size;
          else thumbnails.untracked += size;
        }catch(e){ /* unreadable file -- skip it, not fatal */ }
      }
    }catch(e){ /* no thumbnails/ folder yet -- leave totals at 0, not an error */ }

    let inbox = 0;
    try{
      const inboxDir = await rootDirHandle.getDirectoryHandle('inbox', { create: false });
      for await (const [name, handle] of inboxDir.entries()){
        if(handle.kind !== 'file') continue;
        try{
          inbox += (await handle.getFile()).size;
        }catch(e){ /* unreadable file -- skip it, not fatal */ }
      }
    }catch(e){ /* no inbox/ folder yet -- leave at 0, not an error, matching checkInbox()'s own precedent */ }

    let librarySqlite = 0;
    try{
      const dbHandle = await rootDirHandle.getFileHandle('library.sqlite', { create: false });
      librarySqlite = (await dbHandle.getFile()).size;
    }catch(e){ /* unreadable -- leave at 0, not fatal */ }

    const filesTotal = files.active + files.original + files.untracked;
    const thumbnailsTotal = thumbnails.active + thumbnails.untracked;
    const grandTotal = filesTotal + thumbnailsTotal + inbox + librarySqlite;

    return { files, thumbnails, inbox, librarySqlite, filesTotal, thumbnailsTotal, grandTotal };
  }

```

- [ ] **Step 3: Add `openStorageStatsModal()`**

In `dossiary.html`, right after `computeStorageStats()`'s closing `}` (from Step 2), insert:

```javascript
  // Opens a brand new, independent modal (not part of the "Library check"
  // family) showing real disk usage. Runs the walk immediately on open -- the
  // click on the toolbar button is itself the explicit trigger, matching how
  // openLibraryCheckModal()'s own file-hash backfill already runs on open
  // rather than needing a second confirming click inside the modal. Unlike
  // that backfill, this computation never writes anything, so there's no
  // "disable Escape/close while running" concern -- Escape and the close
  // button work normally throughout.
  async function openStorageStatsModal(){
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <h2>${t('storageStatsModalTitle')}</h2>
          <div id="storage-stats-progress"><span class="spinner"></span> ${t('storageStatsComputing')}</div>
          <div id="storage-stats-results" style="display:none;"></div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);

    const stats = await computeStorageStats();

    // Defensive: the modal could have been replaced by something else (e.g.
    // Escape closing it, or another modal opened) by the time the walk
    // finishes -- not a full focus-trap, just a guard against writing into a
    // container that's no longer there.
    const progressEl = el('storage-stats-progress');
    if(progressEl) progressEl.style.display = 'none';
    const resultsEl = el('storage-stats-results');
    if(!resultsEl) return;
    resultsEl.style.display = 'block';

    const rowHtml = (labelKey, size) => `
      <div class="storage-stats-row">
        <span>${t(labelKey)}</span>
        <span>${formatBytes(size)}</span>
      </div>
    `;
    resultsEl.innerHTML = [
      `<div class="storage-stats-total">${t('storageStatsGrandTotal', {size: formatBytes(stats.grandTotal)})}</div>`,
      rowHtml('storageStatsFilesLabel', stats.filesTotal),
      rowHtml('storageStatsThumbnailsLabel', stats.thumbnailsTotal),
      rowHtml('storageStatsInboxLabel', stats.inbox),
      rowHtml('storageStatsDatabaseLabel', stats.librarySqlite),
      rowHtml('storageStatsActiveLabel', stats.files.active),
      rowHtml('storageStatsOriginalsLabel', stats.files.original),
      stats.files.untracked > 0 ? rowHtml('storageStatsUntrackedLabel', stats.files.untracked) : '',
      stats.thumbnails.untracked > 0 ? rowHtml('storageStatsUntrackedLabel', stats.thumbnails.untracked) : '',
    ].join('');
  }

```

- [ ] **Step 4: Add the toolbar button**

In `dossiary.html`, find this line (around line 708):
```html
        <button id="library-check-btn" data-i18n="toolbarLibraryCheck">🔍 Library check</button>
```
Replace with:
```html
        <button id="library-check-btn" data-i18n="toolbarLibraryCheck">🔍 Library check</button>
        <button id="storage-stats-btn" data-i18n="toolbarStorageStats">💾 Storage stats</button>
```

- [ ] **Step 5: Wire the toolbar button**

In `dossiary.html`, find (around line 8964):
```javascript
  el('library-check-btn').addEventListener('click', openLibraryCheckModal);
```
Replace with:
```javascript
  el('library-check-btn').addEventListener('click', openLibraryCheckModal);
  el('storage-stats-btn').addEventListener('click', openStorageStatsModal);
```

- [ ] **Step 6: Add the new CSS**

In `dossiary.html`, right after the existing `.orphaned-row{...}` rule (line 198), insert:

```css
  .storage-stats-row{ display:flex; justify-content:space-between; align-items:center; gap:12px; padding:8px 10px; }
  .storage-stats-total{ font-weight:600; font-size:15px; color:var(--phosphor); border-bottom:1px solid var(--line); margin-bottom:6px; padding:4px 10px 14px; }
```

- [ ] **Step 7: Add the eleven new i18n keys across all six languages**

Same dense-line convention as every prior feature in this modal family — append to the same line each language's `libraryCheckConfirmDeleteAllPeoplePlural` key sits on.

English (line 1075) — append after `libraryCheckConfirmDeleteAllPeoplePlural: 'Delete these {count} unused people? This can\'t be undone.',`:
```
toolbarStorageStats: '💾 Storage stats', storageStatsModalTitle: 'Storage stats', storageStatsComputing: 'Computing storage usage…', storageStatsGrandTotal: 'Total: {size}', storageStatsFilesLabel: 'Documents (files/)', storageStatsThumbnailsLabel: 'Previews (thumbnails/)', storageStatsInboxLabel: 'Inbox (inbox/)', storageStatsDatabaseLabel: 'Database (library.sqlite)', storageStatsActiveLabel: 'Active', storageStatsOriginalsLabel: 'Originals', storageStatsUntrackedLabel: 'Untracked',
```

Spanish (line 1276) — append after `libraryCheckConfirmDeleteAllPeoplePlural: '¿Eliminar estas {count} personas sin usar? Esto no se puede deshacer.',`:
```
toolbarStorageStats: '💾 Uso de almacenamiento', storageStatsModalTitle: 'Uso de almacenamiento', storageStatsComputing: 'Calculando el uso de almacenamiento…', storageStatsGrandTotal: 'Total: {size}', storageStatsFilesLabel: 'Documentos (files/)', storageStatsThumbnailsLabel: 'Vistas previas (thumbnails/)', storageStatsInboxLabel: 'Bandeja de entrada (inbox/)', storageStatsDatabaseLabel: 'Base de datos (library.sqlite)', storageStatsActiveLabel: 'Activos', storageStatsOriginalsLabel: 'Originales', storageStatsUntrackedLabel: 'Sin seguimiento',
```

French (line 1477) — append after `libraryCheckConfirmDeleteAllPeoplePlural: 'Supprimer ces {count} personnes inutilisées ? Cette action est irréversible.',`:
```
toolbarStorageStats: '💾 Utilisation du stockage', storageStatsModalTitle: 'Utilisation du stockage', storageStatsComputing: 'Calcul de l\'utilisation du stockage…', storageStatsGrandTotal: 'Total : {size}', storageStatsFilesLabel: 'Documents (files/)', storageStatsThumbnailsLabel: 'Aperçus (thumbnails/)', storageStatsInboxLabel: 'Boîte de réception (inbox/)', storageStatsDatabaseLabel: 'Base de données (library.sqlite)', storageStatsActiveLabel: 'Actifs', storageStatsOriginalsLabel: 'Originaux', storageStatsUntrackedLabel: 'Non suivis',
```

German (line 1678) — append after `libraryCheckConfirmDeleteAllPeoplePlural: 'Diese {count} unbenutzten Personen löschen? Dies kann nicht rückgängig gemacht werden.',`:
```
toolbarStorageStats: '💾 Speichernutzung', storageStatsModalTitle: 'Speichernutzung', storageStatsComputing: 'Speichernutzung wird berechnet…', storageStatsGrandTotal: 'Gesamt: {size}', storageStatsFilesLabel: 'Dokumente (files/)', storageStatsThumbnailsLabel: 'Vorschaubilder (thumbnails/)', storageStatsInboxLabel: 'Posteingang (inbox/)', storageStatsDatabaseLabel: 'Datenbank (library.sqlite)', storageStatsActiveLabel: 'Aktiv', storageStatsOriginalsLabel: 'Originale', storageStatsUntrackedLabel: 'Nicht zugeordnet',
```

Chinese Simplified (line 1879) — append after `libraryCheckConfirmDeleteAllPeoplePlural: '删除这 {count} 个未使用的人员？此操作无法撤销。',`:
```
toolbarStorageStats: '💾 存储统计', storageStatsModalTitle: '存储统计', storageStatsComputing: '正在计算存储占用……', storageStatsGrandTotal: '总计：{size}', storageStatsFilesLabel: '文档（files/）', storageStatsThumbnailsLabel: '预览图（thumbnails/）', storageStatsInboxLabel: '收件箱（inbox/）', storageStatsDatabaseLabel: '数据库（library.sqlite）', storageStatsActiveLabel: '当前使用', storageStatsOriginalsLabel: '原件', storageStatsUntrackedLabel: '未追踪',
```

Chinese Traditional (line 2206) — append after `libraryCheckConfirmDeleteAllPeoplePlural: '刪除這 {count} 個未使用的人員？此操作無法撤銷。',`:
```
toolbarStorageStats: '💾 儲存統計', storageStatsModalTitle: '儲存統計', storageStatsComputing: '正在計算儲存佔用……', storageStatsGrandTotal: '總計：{size}', storageStatsFilesLabel: '文檔（files/）', storageStatsThumbnailsLabel: '預覽圖（thumbnails/）', storageStatsInboxLabel: '收件箱（inbox/）', storageStatsDatabaseLabel: '資料庫（library.sqlite）', storageStatsActiveLabel: '目前使用', storageStatsOriginalsLabel: '原件', storageStatsUntrackedLabel: '未追蹤',
```

- [ ] **Step 8: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: PASS — the eleven new keys must exist identically across all six `STRINGS` blocks.

- [ ] **Step 9: Add a test-only debug hook**

In `dossiary.html`, near line 3725 (right after `window.__DEBUG_computeOrphanedPeople = computeOrphanedPeople;`), add:

```javascript
  // Test-only: exposes computeStorageStats() directly, same reasoning as the
  // other __DEBUG_compute* hooks above -- lets a test verify its output without
  // going through the full modal-open flow.
  window.__DEBUG_computeStorageStats = computeStorageStats;
```

- [ ] **Step 10: Write `tests/test_storage_stats.py`**

This suite's real convention (confirmed by reading `tests/test_broken_links.py`, `tests/test_orphaned_lookups.py`, and `tests/test_searchable_pdf.py` in full) is: `async def main(): ...; asyncio.run(main())` using `playwright.async_api`, driving the real app UI to create documents, and printing `print("<description>:", <bool>)` lines. `tests/test_searchable_pdf.py` shows the exact pattern for capturing a document that builds a searchable PDF: a real tiny PNG, `#run-ocr-btn`, then Save — the stubbed `jsPDF.output()` in `stub_studio2.js` returns real, non-trivial bytes (`'FAKE-PDF-BYTES:' + JSON.stringify(...)`), so the resulting `file_path` genuinely has a different byte size than the original PNG's `original_file_path`, which is exactly what this feature's own "active and original are different real files" claim needs to prove.

Create `tests/test_storage_stats.py` with exactly this content:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, base64
from playwright.async_api import async_playwright

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

        async def read_stub_file_size(rel_path):
            return await page.evaluate("""
                async (relPath) => {
                    const parts = relPath.split('/');
                    let dir = window.__TEST_ROOT;
                    for (let i = 0; i < parts.length - 1; i++) { dir = await dir.getDirectoryHandle(parts[i]); }
                    const handle = await dir.getFileHandle(parts[parts.length - 1]);
                    const file = await handle.getFile();
                    return file.size;
                }
            """, rel_path)

        # Doc 1: a plain PDF capture, no OCR -- file_path and original_file_path
        # are two separately-written copies of the SAME bytes (still two real,
        # separately-sized files on disk, per writeOriginalToSubfolder()).
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('plain.pdf', 'wb') as f:
            f.write(b'%PDF-1.4 plain document, no OCR, twenty-two bytes padding here')
        await page.set_input_files('#file-input', 'plain.pdf')
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Plain Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # Doc 2: a real image, OCR'd and saved -- file_path becomes the rebuilt
        # searchable PDF (the stub's fake jsPDF.output() produces real,
        # non-trivial bytes), original_file_path stays the small original PNG.
        # These two are now genuinely DIFFERENT-sized real files, not just two
        # copies of the same bytes.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('scan.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'scan.png')
        await page.wait_for_timeout(150)
        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(300)
        await page.fill('#f-title', 'Scanned Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        # Stage a file directly in inbox/ (never added as a document).
        await page.evaluate("""
            async () => {
                const inboxDir = await window.__TEST_ROOT.getDirectoryHandle('inbox', { create: true });
                const handle = await inboxDir.getFileHandle('staged.pdf', { create: true });
                const writable = await handle.createWritable();
                await writable.write(new TextEncoder().encode('%PDF-1.4 staged inbox file, never added'));
                await writable.close();
            }
        """)

        # Write an extra, genuinely untracked file directly into files/ -- no
        # document's file_path/original_file_path will ever point to this.
        await page.evaluate("""
            async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                const handle = await filesDir.getFileHandle('mystery_leftover.bin', { create: true });
                const writable = await handle.createWritable();
                await writable.write(new TextEncoder().encode('nobody points to this file'));
                await writable.close();
            }
        """)

        # Move Doc 1 to the Waste bin -- its files must still count toward the
        # total (nothing on disk is touched by a soft delete).
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)

        # === Independently compute the expected totals in Python, walking the
        # exact same fake filesystem, so the assertions below don't just trust
        # the app's own arithmetic ===
        doc1_paths = await page.evaluate("window.__DEBUG_getDocPaths(1)")
        doc2_paths = await page.evaluate("window.__DEBUG_getDocPaths(2)")

        doc1_active_size = await read_stub_file_size(doc1_paths['file_path'])
        doc1_original_size = await read_stub_file_size(doc1_paths['original_file_path'])
        doc2_active_size = await read_stub_file_size(doc2_paths['file_path'])
        doc2_original_size = await read_stub_file_size(doc2_paths['original_file_path'])
        untracked_size = await read_stub_file_size('files/mystery_leftover.bin')
        inbox_size = await read_stub_file_size('inbox/staged.pdf')
        db_size = await read_stub_file_size('library.sqlite')

        # saveNewDocument() unconditionally attempts a thumbnail for every
        # capture (generateThumbnail() supports both image/* and
        # application/pdf, so both doc 1's PDF and doc 2's PNG get one) --
        # thumbnails/1.png and thumbnails/2.png are real files here, per
        # writeThumbnail()'s own fixed `thumbnails/${id}.png` naming. Both are
        # genuinely tracked (thumbnail_path is set on both documents), so they
        # belong in the 'active' thumbnails bucket, not 'untracked'.
        doc1_thumb_size = await read_stub_file_size('thumbnails/1.png')
        doc2_thumb_size = await read_stub_file_size('thumbnails/2.png')

        expected_files_active = doc1_active_size + doc2_active_size
        expected_files_original = doc1_original_size + doc2_original_size
        expected_files_total = expected_files_active + expected_files_original + untracked_size
        expected_thumbnails_active = doc1_thumb_size + doc2_thumb_size
        expected_grand_total = expected_files_total + expected_thumbnails_active + inbox_size + db_size

        print("Doc 2's active file (rebuilt searchable PDF) is a genuinely different size than its original PNG:", doc2_active_size != doc2_original_size)

        stats = await page.evaluate("window.__DEBUG_computeStorageStats()")

        print("files.active matches the independently-computed sum:", stats['files']['active'] == expected_files_active)
        print("files.original matches the independently-computed sum:", stats['files']['original'] == expected_files_original)
        print("files.untracked equals the one deliberately-untracked file's size:", stats['files']['untracked'] == untracked_size)
        print("filesTotal matches active+original+untracked:", stats['filesTotal'] == expected_files_total)
        print("thumbnails.active matches both documents' real thumbnail sizes:", stats['thumbnails']['active'] == expected_thumbnails_active)
        print("thumbnails.untracked is zero (both thumbnails are genuinely tracked):", stats['thumbnails']['untracked'] == 0)
        print("inbox matches the one staged file's size:", stats['inbox'] == inbox_size)
        print("librarySqlite matches the real library.sqlite file size:", stats['librarySqlite'] == db_size)
        print("grandTotal matches the independently-computed total:", stats['grandTotal'] == expected_grand_total)
        print("Doc 1's files (now in the Waste bin) are still counted in files.active/original:",
              stats['files']['active'] >= doc1_active_size and stats['files']['original'] >= doc1_original_size)

        # === Modal rendering: busy state, then final numbers, with Untracked
        # shown since it's non-zero and Thumbnails' own Untracked row absent
        # since no thumbnails/ folder exists in this test at all ===
        await page.click('#storage-stats-btn')
        busy_visible = await page.locator('#storage-stats-progress').is_visible()
        print("Busy/spinner state is visible right after opening:", busy_visible)
        await page.wait_for_timeout(300)

        results_text = await page.locator('#storage-stats-results').inner_text()
        print("Results show the formatted grand total:", 'Total:' in results_text)
        print("Results show the Documents (files/) row:", 'Documents' in results_text)
        print("Results show the Untracked row (non-zero):", 'Untracked' in results_text)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

The modal-rendering check above triggers the modal via a real click on the toolbar button (`#storage-stats-btn`, wired in Step 5) rather than calling any internal function directly — this exercises the full, real, end-to-end path a person would actually take.

- [ ] **Step 11: Run the new test**

Run: `cd tests && python3 test_storage_stats.py`
Expected: PASS, all checks green, `JS ERRORS: []`.

- [ ] **Step 12: Run the existing duplicate-detection, broken-links, and orphaned-lookups suites to confirm no regression**

Run: `cd tests && python3 test_duplicate_detection.py`
Run: `cd tests && python3 test_broken_links.py`
Run: `cd tests && python3 test_orphaned_lookups.py`
Expected: all PASS — this feature adds a new, fully independent modal and toolbar button, so nothing in the existing "Library check" modal family should be affected at all.

- [ ] **Step 13: Commit**

```bash
git add dossiary.html tests/test_storage_stats.py
git commit -m "$(cat <<'EOF'
Add Storage stats modal

Walks the real files/, thumbnails/, and inbox/ folders (plus
library.sqlite's own size) to show real disk usage: a grand total, a
per-folder breakdown, and -- within files/ -- an active/original/
untracked split answering how much of the library is the doubled
original-preservation overhead this app's own ingestion pipeline
creates. An independent toolbar button and modal, not part of the
existing Library check family, since this is a read-only overview
with no detect-and-fix action of its own.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```

---

### Task 2: Document the feature in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing code-level — this is a documentation-only task.
- Produces: an updated architecture note for future readers of `CLAUDE.md`.

- [ ] **Step 1: Add a "Storage stats" architecture note**

In `CLAUDE.md`, immediately after the existing "Orphaned tags/people cleanup" note (search for `**Orphaned tags/people cleanup**` — it ends right before `## How this was tested`), add a new note in this repo's established voice (rationale-first, exact function/id names, explicit "what's deliberately not covered" callouts):

```markdown
- **Storage stats** (`computeStorageStats()`, `formatBytes()`,
  `openStorageStatsModal()`) is a brand new, independent toolbar button and
  modal — deliberately **not** part of the "Library check" family
  (`openLibraryCheckModal()`) the three prior maintenance features share,
  since this is a read-only overview, not a detect-a-problem-and-fix-it
  check. Answers the question CLAUDE.md's own "Preserving an original file
  on ingestion" note raises but never lets anyone actually see: how much
  of the library's real disk usage is the doubled original-preservation
  overhead versus genuinely distinct content.
  **The walk reads real files on disk, never trusts `allDocs`' own tracked
  paths as the source of truth** — `computeStorageStats()` iterates
  `filesDirHandle.entries()` (the same `for await (const [name, handle] of
  dirHandle.entries())` pattern `checkInbox()` already uses), recursing one
  level into each per-document subfolder, and reads every file's real size
  via `getFile().size` (a metadata read — no file content is ever loaded
  into memory). This is deliberate: summing only `allDocs`' own tracked
  `file_path`/`original_file_path` values would silently miss anything on
  disk that no document row points to at all.
  **Every file under `files/` is classified into exactly one of three
  buckets** by comparing its own relative path against every document's
  `file_path`/`original_file_path` — **including documents in the Waste
  bin**, since a soft-deleted document's files are never touched on disk
  (per the Waste bin's own "nothing on disk is ever touched" design) and
  are still real, space-consuming files:
  - **Active** — matches some document's `file_path`.
  - **Original** — matches some document's `original_file_path`.
  - **Untracked** — matches neither. A genuine, useful side effect of
    walking the real folder rather than the database: nothing else in
    this app can currently show a file under `files/` that no document
    points to at all. This feature only makes it visible — there is no
    delete/cleanup action for it, deliberately out of scope.
  `thumbnails/` gets the same two-way active/untracked split (matched
  against `thumbnail_path`); `inbox/` isn't split further at all, since
  every file staged there is equally "not yet added." `library.sqlite`'s
  own size is added into the grand total but doesn't participate in the
  files/thumbnails/inbox breakdown, since it's a different kind of thing
  entirely. A missing `inbox/` or `thumbnails/` folder (a library that's
  never staged an inbox file, or never generated a thumbnail) is treated
  as zero, not an error — the same "a missing folder just means nothing
  to add" reasoning `checkInbox()` already established; a per-file read
  failure mid-walk is skipped rather than aborting the whole computation,
  the same reasoning `backfillFileHash()` already uses.
  **The walk runs immediately when the modal opens** — the click on the
  toolbar button is itself the explicit trigger, matching how
  `openLibraryCheckModal()`'s own file-hash backfill already runs on open
  rather than needing a second confirming click inside the modal. Unlike
  that backfill, this computation never writes anything, so there's no
  "disable Escape/close while running" concern — Escape and the close
  button work normally throughout, even mid-walk.
  **`formatBytes()`** generalizes the ad-hoc `(file.size/1024).toFixed(0)`
  KB-only formatting the capture form's own picked-file-size preview
  (`pickedFileSizeKb`) already uses, since a whole-library total can run
  well past what's sensible to show in KB alone — it auto-scales through
  B/KB/MB/GB/TB rather than being fixed to one unit.
  **The "Untracked" row is only rendered when non-zero**, in both `files/`
  and `thumbnails/` independently — omitted entirely otherwise, matching
  this app's existing "omit sections/rows with nothing to show" convention
  (e.g. how the "Library check" modal's own sections each disappear when
  empty). No per-document breakdown, no sorting, no "biggest documents"
  list — deliberately just the aggregate picture, to keep this a simple
  overview rather than growing into a second browsing UI.
```

- [ ] **Step 2: Verify the new note reads correctly in context**

Read the surrounding paragraphs in `CLAUDE.md` once the insertion is made, confirming it doesn't duplicate or contradict anything already said about `checkInbox()`, `backfillFileHash()`, `writeOriginalToSubfolder()`, or the "Library check" modal family, and that it's inserted in shipping-chronological order relative to its neighbors (right after the "Orphaned tags/people cleanup" note, right before `## How this was tested`).

- [ ] **Step 3: Update `tests/CLAUDE.md`'s test-count and coverage summary**

`tests/CLAUDE.md`'s own "How this was tested" section states an exact test-script count near its top (confirm the exact current numbers by reading that file before editing, since they may have shifted since the orphaned-lookups feature's own final review last bumped them) and lists every test file's own coverage in one long paragraph. Add one more sentence to that paragraph (following the exact style of its existing `test_orphaned_lookups.py` entry, inserted right after it) describing `test_storage_stats.py`'s coverage: the real-folder walk correctly sums `files/`/`thumbnails/`/`inbox/`/`library.sqlite` against an independently-computed expectation, not just the app's own arithmetic; a document whose searchable PDF was built has genuinely different-sized active and original files, both correctly attributed; a deliberately untracked file lands in the Untracked bucket and nowhere else; a document moved to the Waste bin still has its files counted; and the modal shows a busy state before resolving to final numbers. Also bump the script-count numbers by one to match the new file.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document the Storage stats feature

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```
