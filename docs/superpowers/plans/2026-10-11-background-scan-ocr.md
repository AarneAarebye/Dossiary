# Background OCR for scans (Dossiary) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every scan lands in the Inbox at once and becomes searchable without the person doing anything: Dossiary asks a helper that offers `ocr` for a searchable PDF, follows the job, swaps the result in (keeping the plain scan as the original), and runs its own OCR when no helper result comes.

**Architecture:** Step 2 of `docs/superpowers/specs/2026-10-11-background-scan-ocr-design.md` (read section 4; the wire format is the "Background OCR" section of dossiary-scan-helper's `PROTOCOL.md`, merged 2026-10-11). Jobs are rows in a new `ocr_jobs` table (one per document); a runner started after a scan and on library open polls `GET /ocr/<job>` every 3 s, swaps results in with the existing `replaceActiveFile()`/`refreshAfterPdfChange()`, and runs the existing `makeDocumentSearchable()` as the fallback, one document at a time.

**Tech Stack:** Single-file app `dossiary.html` (vanilla JS, sql.js); Playwright tests in `tests/` with the shared stub `tests/stub_studio2.js`.

## Global Constraints

- Read `CLAUDE.md` (repo root) and `tests/CLAUDE.md` first: single file, sql.js conventions (whole-table `SELECT` + JS filtering, `db.run(sql, params)` for writes), the status line (`setStatusT`/`setStatusLive`), i18n (`t()`, six languages: en, de, es, fr, zh-Hans, zh-Hant — every new key in all six, `tests/test_i18n_coverage.py` must pass), and the rule that every printed test check reads `True` on pass.
- Table, exactly: `CREATE TABLE IF NOT EXISTS ocr_jobs (document_id INTEGER PRIMARY KEY, helper_url TEXT, job_id TEXT, file_hash TEXT, created_at TEXT)`. `job_id` NULL means "waiting for Dossiary's own OCR" (the fallback). No `last_reached_at` column: how long a helper has been unreachable is tracked in memory (see Task 2) so a 3-second poll never rewrites `library.sqlite`.
- Settings rows: `scan_auto_ocr` (`'1'`/`'0'`, missing = on) and `scan_ocr_language` (an OCR language value as used by `ocrLanguageOptionsHtml()`, missing = `'eng+deu'`, i.e. Auto).
- Requests: `ocr: true` only when `scan_auto_ocr` is on and the chosen scanner has an `ocr` object; `ocrLanguages` = the codes of `scan_ocr_language` split on `+`, in that order, kept only if in the scanner's `ocr.languages`; omitted when that leaves none.
- Poll interval 3000 ms; one poll pass at a time; one fallback OCR at a time; give up on an unreachable helper (network error or 401) after 10 minutes → fallback.
- A helper result is swapped in only if the document's *active* file still has the `file_hash` recorded for the job (the delivered scan's hash); otherwise it's discarded and the fallback runs on the current file.
- Nothing may write into another library: every await in the runner and the fallback is followed by a check that `rootDirHandle` is still the library the work started in; if not, it stops without writing.
- Only scans: drag-and-drop and `inbox/` files are unchanged.
- Messages are plain English (and translated), written for a person.
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01AnMx4wtUcaKMWsQm9eXUTo
  ```

---

### Task 1: Settings, the `ocr_jobs` table, requesting OCR and recording jobs

**Files:**
- Modify: `dossiary.html`, `tests/stub_studio2.js`, `tests/test_scan_dialog.py`

**Interfaces:**
- Produces: `let scanAutoOcr` (bool), `let scanOcrLanguage` (string); `scanOcrLanguagesFor(scanner) -> string[]`; `writeScanFilesToInbox(files) -> string[]` (the inbox names written, in order); `addInboxFile(name, onAdded)` / `addAllInboxFiles(onAdded)` / `addAllInboxFilesAndShowStatus(onAdded)` where `onAdded(name, id)` is called for each added document; `queueScanOcr(helperUrl, rawFiles, writtenNames, idsByName) -> Promise<number>` (rows written); `ocrJobRows() -> [{document_id, helper_url, job_id, file_hash, created_at}]`; `deleteOcrJob(docId)` (no persist); debug hook `window.__DEBUG_ocrJobRows`. Task 2 adds the runner and calls it from `queueScanOcr`.

- [ ] **Step 1: Stub support**

In `tests/stub_studio2.js`:
- add `ocr_jobs` to all three `this.tables = {…}` literals (`ocr_jobs: parsed.ocr_jobs || []` in the seeded one, `ocr_jobs: []` in the two empty ones) and to the seed list near line 540 (`ocr_jobs: seed.ocr_jobs || []`);
- give `INSERT OR REPLACE INTO ocr_jobs` a dedupe branch by `document_id`, next to the existing `not_duplicate_groups` one: `if (table === 'ocr_jobs' && isReplace) { this.tables.ocr_jobs = this.tables.ocr_jobs.filter(r => r.document_id !== row.document_id); }`;
- after the existing `view_mode` default (line ~208), add the same pattern so every existing test keeps today's behaviour: `if (!window.__STUB_KEEP_SCAN_AUTO_OCR && !this.tables.settings.some(r => r.key === 'scan_auto_ocr')) { this.tables.settings.push({ key: 'scan_auto_ocr', value: '0' }); }`.

Check that `UPDATE ocr_jobs SET job_id = ?, helper_url = ? WHERE document_id = ?` with `null` params and `DELETE FROM ocr_jobs WHERE document_id = ?` work in the stub (they match its existing `UPDATE … WHERE col = ?` / `DELETE … WHERE col = ?` patterns; extend the regexes if not).

- [ ] **Step 2: Test harness and failing tests**

In `tests/test_scan_dialog.py`'s `FAKE_HELPERS` JS:
- version 2 `/scan`: parse the request body (`const req = JSON.parse(opts.body || '{}')`) and, when `req.ocr`, add `ocrJob: 'job-' + n` to the file entry;
- add, before the `/scan` branch, a `/ocr/` branch for version 2 helpers:

```js
        if(path.startsWith('/ocr/') && H.version === 2){
            if(!valid) return v2err(401, 'Pair this browser first.');
            const jid = decodeURIComponent(path.slice('/ocr/'.length));
            const queue = (H.ocrResponses || {})[jid];
            const next = queue && queue.length ? queue.shift() : null;
            if(next && next.network) throw new TypeError('Failed to fetch');
            if(next) return json(next.status, next.body);
            return json(200, { ok: true, files: [{ name: 'scan.pdf', pages: 1, data: btoa('%PDF-1.4 searchable %TEXTLAYER ' + jid) }] });
        }
```

(The stub's pdf.js reports real text for bytes containing `%TEXTLAYER`.)

Add a scenario `scenario_ocr_request(p)` (and call it from the file's `main`), opening the app with `window.__STUB_KEEP_SCAN_AUTO_OCR = true` set in an init script (follow how other scenarios add init scripts or set flags before the library opens), with `V2_OCR_SCANNER = {"id": "fake:ocr", "name": "Fake OCR Scanner", "sources": ["flatbed"], "duplex": False, "colorModes": ["color"], "resolutions": [300], "extras": [], "ocr": {"languages": ["deu", "eng"]}}` added to a version 2 helper's scanners. Checks (each printed `…: True`):
1. Field Settings shows `#fs-scan-auto-ocr` checked and `#fs-scan-ocr-lang` with value `eng+deu`.
2. Scanning with the OCR scanner sends `ocr: true` and `ocrLanguages: ["eng", "deu"]`; scanning with a scanner without `ocr` (e.g. `fake:flatbed` from `V2_SCANNERS`) sends neither field.
3. After the OCR scan, `window.__DEBUG_ocrJobRows()` has one row: the new document's id, the helper URL, job id `job-<n>`, and `file_hash` equal to that document's `file_hash` in the database.
4. After the non-OCR v2 scan (plain fake bytes, no text layer), a row with `job_id` null (fallback) exists for that document.
5. Setting `scan_ocr_language` to `deu` in Field Settings → the next OCR scan sends `ocrLanguages: ["deu"]`; to `fra` → no `ocrLanguages` (not offered).
6. Unticking `#fs-scan-auto-ocr` saves `scan_auto_ocr = '0'`; the next scan sends no `ocr` field and adds no row.
7. With the shared stub's default (`scan_auto_ocr` '0', no `__STUB_KEEP_SCAN_AUTO_OCR`), a scan sends no `ocr` and adds no rows — what every other scenario relies on.

Run: `cd tests && python3 test_scan_dialog.py 2>&1 | grep -v ": True$"` → the new checks print `False`/errors.

- [ ] **Step 3: Implement**

`dossiary.html`:

1. `SCHEMA`: add next to `not_duplicate_groups`:

```sql
    CREATE TABLE IF NOT EXISTS ocr_jobs (
      document_id INTEGER PRIMARY KEY,
      helper_url TEXT,
      job_id TEXT,
      file_hash TEXT,
      created_at TEXT
    );
```

2. Settings: module-level `let scanAutoOcr = true; let scanOcrLanguage = 'eng+deu';` near `scanBridgeUrl`. In `loadScanBridgeUrl()` (called from `loadDocumentsFromDb()`), also: `scanAutoOcr = readSetting('scan_auto_ocr') !== '0'; scanOcrLanguage = readSetting('scan_ocr_language') || 'eng+deu';`. In `resetAll()`: `scanAutoOcr = true; scanOcrLanguage = 'eng+deu';`.

3. Field Settings, after the `fs-scan-bridge-url` field:

```html
            <div class="field">
              <label class="scan-dialog-check"><input type="checkbox" id="fs-scan-auto-ocr" ${scanAutoOcr ? 'checked' : ''} /> ${t('fieldSettingsScanAutoOcrLabel')}</label>
            </div>
            <div class="field">
              <label for="fs-scan-ocr-lang">${t('fieldSettingsScanOcrLanguageLabel')}</label>
              <select id="fs-scan-ocr-lang">${ocrLanguageOptionsHtml(scanOcrLanguage)}</select>
            </div>
```

wired next to the `fs-scan-bridge-url` listener:

```js
    el('fs-scan-auto-ocr').addEventListener('change', async (e) => { scanAutoOcr = e.target.checked; writeSetting('scan_auto_ocr', scanAutoOcr ? '1' : '0'); await persistDb(); });
    el('fs-scan-ocr-lang').addEventListener('change', async (e) => { scanOcrLanguage = e.target.value; writeSetting('scan_ocr_language', scanOcrLanguage); await persistDb(); });
```

4. Language codes and the request:

```js
  // ocrLanguages for a scan request: the scan OCR language setting
  // ('eng+deu', 'deu', …) in its own order -- the protocol reads the order as
  // priority -- limited to what the scanner offers. [] lets the helper choose.
  function scanOcrLanguagesFor(scanner){
    const offered = scanner.ocr && Array.isArray(scanner.ocr.languages) ? scanner.ocr.languages : [];
    return scanOcrLanguage.split('+').filter(code => offered.includes(code));
  }
```

In `buildScanRequest()`'s version 2 branch, after `body.duplex = …`:

```js
    if(scanAutoOcr && s.ocr && typeof s.ocr === 'object'){
      body.ocr = true;
      const languages = scanOcrLanguagesFor(s);
      if(languages.length) body.ocrLanguages = languages;
    }
```

Make sure the scanner object kept by discovery still carries `ocr` (check `loadHelperScanners()`/`validHelperScanner()` keep the whole entry; if entries are rebuilt field by field, add `ocr`).

5. `writeScanFilesToInbox(files)` returns the array of `uniqueName`s it wrote, in order.

6. `addInboxFile(name, onAdded)`: right after `createReviewDocumentFromFile()` succeeds without `skippedDuplicate`, call `if(onAdded) onAdded(name, result.id);`. `addAllInboxFiles(onAdded)` passes it on; `addAllInboxFilesAndShowStatus(onAdded)` passes it to `addAllInboxFiles`. Existing callers pass nothing.

7. Jobs:

```js
  // ---- Background OCR for scans (spec 2026-10-11-background-scan-ocr) ----
  // One row per document: job_id set = waiting for the helper's searchable
  // PDF (GET /ocr/<job>); job_id NULL = waiting for Dossiary's own OCR.
  function ocrJobRows(){
    if(!db) return [];
    return queryAll('SELECT document_id, helper_url, job_id, file_hash, created_at FROM ocr_jobs').rows
      .map(r => ({ document_id: r[0], helper_url: r[1], job_id: r[2], file_hash: r[3], created_at: r[4] }));
  }
  function deleteOcrJob(docId){
    db.run('DELETE FROM ocr_jobs WHERE document_id = ?', [docId]);
  }

  // After a scan's files were added: a row per new document that the helper
  // is making searchable (its file had an ocrJob), or -- with no job and no
  // text layer of its own -- that Dossiary should OCR itself. Off entirely
  // when "Make scans searchable automatically" is off.
  async function queueScanOcr(helperUrl, rawFiles, writtenNames, idsByName){
    if(!scanAutoOcr || !Array.isArray(rawFiles)) return 0;
    const now = nowIso();
    let queued = 0;
    rawFiles.forEach((entry, i) => {
      const id = idsByName[writtenNames[i]];
      const d = id != null ? allDocs.find(x => x.id === id) : null;
      if(!d) return; // skipped as a duplicate, or not added
      const job = entry && typeof entry.ocrJob === 'string' && entry.ocrJob ? entry.ocrJob : null;
      if(!job && d.has_text_layer) return; // already searchable (e.g. scanix500 before 0.4 ran OCR itself)
      db.run('INSERT OR REPLACE INTO ocr_jobs (document_id, helper_url, job_id, file_hash, created_at) VALUES (?, ?, ?, ?, ?)',
        [d.id, job ? helperUrl : null, job, d.file_hash || null, now]);
      queued++;
    });
    if(queued) await persistDb();
    return queued;
  }
  window.__DEBUG_ocrJobRows = () => ocrJobRows();
```

8. `performScanRequest()`: keep `const writtenNames = await writeScanFilesToInbox(files);` inside the existing try, and replace `await addAllInboxFilesAndShowStatus();` with:

```js
    const idsByName = {};
    await addAllInboxFilesAndShowStatus((name, id) => { idsByName[name] = id; });
    await queueScanOcr(helperUrl, body.files, writtenNames, idsByName);
```

9. Waste bin: in `toggleDeleted(id)`, before `persistDb()`: `if(d.deleted) deleteOcrJob(id);`. In `bulkSetDeleted(ids, value)`, before `persistDb()`: `if(value) ids.forEach(deleteOcrJob);`.

10. i18n, all six languages (match each block's existing quote style; zh-Hant is the OpenCC Traditional form of zh-Hans):

| key | en | de | es | fr | zh-Hans | zh-Hant |
|---|---|---|---|---|---|---|
| `fieldSettingsScanAutoOcrLabel` | Make scans searchable automatically | Scans automatisch durchsuchbar machen | Hacer que los escaneos se puedan buscar automáticamente | Reconnaître automatiquement le texte des numérisations | 自动使扫描件可搜索 | 自動使掃描件可搜尋 |
| `fieldSettingsScanOcrLanguageLabel` | Text recognition language for scans | Sprache der Texterkennung für Scans | Idioma del reconocimiento de texto para escaneos | Langue de reconnaissance du texte pour les numérisations | 扫描件的文字识别语言 | 掃描件的文字識別語言 |

- [ ] **Step 4: Run the tests**

Run: `cd tests && python3 test_scan_dialog.py 2>&1 | grep -v ": True$"` → only the `--- scenario…` headers. Also `python3 test_i18n_coverage.py | tail -1` → `PASS`, and `python3 test_inbox.py`, `python3 test_drag_drop.py`, `python3 test_waste_bin.py` → no `False`.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/stub_studio2.js tests/test_scan_dialog.py
git commit -m "Scans: ask a helper offering OCR for a searchable PDF, and record the jobs"
```

---

### Task 2: The job runner — polling, swap-in, fallback

**Files:**
- Modify: `dossiary.html`, `tests/test_scan_dialog.py`, `CLAUDE.md`, `tests/CLAUDE.md`

**Interfaces:**
- Consumes: Task 1's `ocrJobRows()`, `deleteOcrJob()`, `queueScanOcr()`, settings, harness (`H.ocrResponses`, `ocrJob: 'job-<n>'`).
- Produces: `startOcrJobRunner()`, `stopOcrJobRunner()`, `runOcrJobPass()`, `ocrPendingDocIds` (Set); `makeDocumentSearchable(id, lang, onProgress, isStale)` gains the optional `isStale`; debug hooks `window.__DEBUG_runOcrJobPass`, `window.__DEBUG_ocrFallbackIdle`, `window.__DEBUG_setOcrGiveUpMs`.

- [ ] **Step 1: Failing tests**

Add `scenario_ocr_jobs(p)` to `tests/test_scan_dialog.py` (same setup as Task 1's scenario: `__STUB_KEEP_SCAN_AUTO_OCR`, a v2 helper with the OCR scanner). Drive the runner with `await page.evaluate("window.__DEBUG_runOcrJobPass()")` instead of waiting for the 3 s timer, and wait for a fallback with a small loop on `window.__DEBUG_ocrFallbackIdle()`. Checks:
1. A job answering 202 once (`H.ocrResponses['job-<n>'] = [{status: 202, body: {ok: true, state: 'running', position: 0}}]`): after one pass the row is still there and the document's row shows the pending pill (`reading text…`); after the next pass (default 200) the row is gone, the document's active file bytes contain `%TEXTLAYER`, its `original_file_path` file still holds the plain bytes (`%PDF-1.4 fake v2`), its `ocr_text` is filled, the pill is gone, and the status line reads `Text added to “<title>”.`.
2. Resume: queue a job, close and reopen the library (Switch library + open, as other tests do), run a pass → the result is swapped in.
3. 404 (`[{status: 404, body: {ok: false, partial: false, message: 'gone'}}]`): after a pass the row has `job_id` null; after the fallback finishes, the row is gone and the document has `searchable_pdf_built` 1 (stub Tesseract + jsPDF).
4. 500: same as 404.
5. Unreachable: `H.ocrResponses[job] = [{network: true}, {network: true}]` with `window.__DEBUG_setOcrGiveUpMs(0)` → after a pass the row turns into a fallback row; with the default 10 minutes, one network failure leaves the row as it is.
6. Changed pages: after the scan, overwrite the document's active file in the stub filesystem with different bytes (`%PDF-1.4 edited`), then a pass with the default 200 → the active file is *not* the helper's result, the row turned into a fallback row.
7. Waste bin: deleting a pending document (panel Delete, and bulk Delete for another) removes its row.
8. Setting off with a fallback row queued: no fallback runs (row stays, document unchanged).
9. Library switch during a fallback: start a fallback (make the stub OCR slow if the stub offers a hook, otherwise check the guard directly via `makeDocumentSearchable(id, 'eng', () => {}, () => true)` returning `{status: 'stale'}` and writing nothing) → nothing written.
10. No page errors.

Run: `cd tests && python3 test_scan_dialog.py 2>&1 | grep -v ": True$"` → new checks fail.

- [ ] **Step 2: Implement**

1. `makeDocumentSearchable(id, lang, onProgress, isStale)`: right after `const pdf = await pdfjsLib.getDocument(…).promise;` (PDF branch) add `if(isStale && isStale()) return { status: 'stale' };` before `recordPdfTextLayer()`; and right after `const pdfBytes = await buildSearchablePdf(pages);` add the same line. Existing callers pass nothing and are unaffected.

2. The runner (in the "Background OCR for scans" section from Task 1):

```js
  const OCR_JOB_POLL_MS = 3000;
  let ocrGiveUpMs = 10 * 60 * 1000;     // unreachable this long -> Dossiary's own OCR
  let ocrJobTimer = null;
  let ocrJobPassRunning = false;
  let ocrFallbackRunning = false;
  let ocrPendingDocIds = new Set();      // documents still waiting for text (pill in table/grid/panel)
  let ocrUnreachableSince = {};          // helper URL -> Date.now() of its first failed poll in a row

  function startOcrJobRunner(){
    if(!ocrJobTimer) ocrJobTimer = setInterval(runOcrJobPass, OCR_JOB_POLL_MS);
    runOcrJobPass();
  }
  function stopOcrJobRunner(){
    if(ocrJobTimer){ clearInterval(ocrJobTimer); ocrJobTimer = null; }
    ocrPendingDocIds = new Set(); ocrUnreachableSince = {};
  }

  function refreshOcrPending(rows){
    const ids = new Set(rows.map(r => r.document_id));
    const changed = ids.size !== ocrPendingDocIds.size || [...ids].some(id => !ocrPendingDocIds.has(id));
    ocrPendingDocIds = ids;
    if(!changed) return;
    render();
    if(selectedDocId != null) openDetail(selectedDocId);
    if(ids.size){
      setStatusLive(() => ids.size === 1 ? t('ocrJobsWaitingSingular', {count: 1}) : t('ocrJobsWaitingPlural', {count: ids.size}), 'busy');
    }
  }

  // Back to Dossiary's own OCR for this document.
  async function switchToFallback(docId){
    db.run('UPDATE ocr_jobs SET job_id = ?, helper_url = ? WHERE document_id = ?', [null, null, docId]);
    await persistDb();
  }

  async function pollOcrJob(row, root){
    const d = allDocs.find(x => x.id === row.document_id);
    if(!d || d.deleted){ deleteOcrJob(row.document_id); await persistDb(); return; }
    let response = null;
    try{
      response = await fetch(`${row.helper_url}/ocr/${encodeURIComponent(row.job_id)}`, { headers: scanAuthHeaders(row.helper_url) });
    }catch(e){ response = null; }
    if(rootDirHandle !== root) return;
    if(!response || response.status === 401){
      const since = ocrUnreachableSince[row.helper_url] ??= Date.now();
      if(Date.now() - since >= ocrGiveUpMs) await switchToFallback(d.id);
      return;
    }
    delete ocrUnreachableSince[row.helper_url];
    if(response.status === 202) return;
    if(response.status !== 200){ await switchToFallback(d.id); return; } // 404 (gone/expired) or 500 (failed, final)
    const body = await response.json().catch(() => null);
    let bytes = null;
    try{ bytes = decodeScanFiles(body && body.files)[0].bytes; }catch(e){ bytes = null; }
    if(!bytes){ await switchToFallback(d.id); return; }
    // The result is for the delivered scan; if "Edit pages…" or "Combine…"
    // changed the document since, it would undo that -- discard it.
    let currentHash = null;
    try{ currentHash = await computeFileHash(await (await resolveFileHandle(d.file_path, false)).getFile()); }catch(e){}
    if(rootDirHandle !== root) return;
    if(!currentHash || currentHash !== row.file_hash){ await switchToFallback(d.id); return; }
    try{
      await replaceActiveFile(d, bytes, '_searchable');
      await refreshAfterPdfChange(d, bytes);
    }catch(e){
      if(rootDirHandle === root) await switchToFallback(d.id);
      return;
    }
    if(rootDirHandle !== root) return;
    deleteOcrJob(d.id);
    await persistDb();
    setStatusT('ocrJobTextAdded', { title: d.title || t('commonDocumentFallback', {id: d.id}) }, 'ok');
  }

  async function runOcrFallback(docId, root){
    ocrFallbackRunning = true;
    let outcome = null, error = null;
    const d = allDocs.find(x => x.id === docId);
    try{
      if(d && !d.deleted && canMakeSearchable(d)){
        outcome = await makeDocumentSearchable(docId, scanOcrLanguage, () => {}, () => rootDirHandle !== root);
      }
    }catch(e){ error = e; }
    finally{ ocrFallbackRunning = false; }
    if(rootDirHandle !== root || !db) return;
    deleteOcrJob(docId);
    await persistDb();
    const title = d ? (d.title || t('commonDocumentFallback', {id: d.id})) : '';
    if(error) setStatusT('ocrJobFailed', { title, error: fileErrorText(error, 'fileErrorWrite') }, 'err');
    else if(outcome && outcome.status === 'no-words') setStatusT('ocrJobNoText', { title }, 'ok');
    else if(outcome && outcome.status === 'built') setStatusT('ocrJobTextAdded', { title }, 'ok');
    refreshOcrPending(ocrJobRows());
  }

  async function runOcrJobPass(){
    if(!db || ocrJobPassRunning) return;
    ocrJobPassRunning = true;
    const root = rootDirHandle;
    try{
      for(const row of ocrJobRows().filter(r => r.job_id)){
        await pollOcrJob(row, root);
        if(rootDirHandle !== root) return;
      }
      const rows = ocrJobRows();
      refreshOcrPending(rows);
      if(!rows.length){ stopOcrJobRunner(); return; }
      const next = rows.find(r => !r.job_id);
      if(next && scanAutoOcr && !ocrFallbackRunning) runOcrFallback(next.document_id, root); // not awaited: polling goes on meanwhile
    }finally{
      ocrJobPassRunning = false;
    }
  }

  window.__DEBUG_runOcrJobPass = () => runOcrJobPass();
  window.__DEBUG_ocrFallbackIdle = () => !ocrFallbackRunning;
  window.__DEBUG_setOcrGiveUpMs = (ms) => { ocrGiveUpMs = ms; };
```

(`stopOcrJobRunner()` clears `ocrPendingDocIds`; when the last row goes, `refreshOcrPending(rows)` with an empty list has already re-rendered without pills before the stop.)

3. Start and stop: at the end of `queueScanOcr()`, `if(queued) startOcrJobRunner();`. At the end of `afterDbReady()`: `if(ocrJobRows().length) startOcrJobRunner();`. At the start of `resetAll()`: `stopOcrJobRunner();`. In `toggleDeleted`/`bulkSetDeleted` (Task 1's lines) also `ocrPendingDocIds.delete(id)`.

4. Pending pill: in the table row's `doc-sub` (next to the `archived` pill, line ~6357) and the grid tile's `tile-sub` (line ~11876) add `${ocrPendingDocIds.has(d.id) ? ` <span class="pill">${t('ocrPendingPill')}</span>` : ''}`; in `openDetail()`'s `modal-meta`, a line `${ocrPendingDocIds.has(d.id) ? `<div class="doc-sub">${t('ocrPendingPill')}</div>` : ''}`.

5. i18n, all six languages:

| key | en | de | es | fr | zh-Hans | zh-Hant |
|---|---|---|---|---|---|---|
| `ocrPendingPill` | reading text… | Text wird erkannt… | leyendo el texto… | lecture du texte… | 正在识别文字… | 正在識別文字… |
| `ocrJobsWaitingSingular` | Reading text: {count} document left… | Texterkennung: noch {count} Dokument… | Leyendo texto: queda {count} documento… | Lecture du texte : encore {count} document… | 正在识别文字：还剩 {count} 个文档… | 正在識別文字：還剩 {count} 個文檔… |
| `ocrJobsWaitingPlural` | Reading text: {count} documents left… | Texterkennung: noch {count} Dokumente… | Leyendo texto: quedan {count} documentos… | Lecture du texte : encore {count} documents… | 正在识别文字：还剩 {count} 个文档… | 正在識別文字：還剩 {count} 個文檔… |
| `ocrJobTextAdded` | Text added to “{title}”. | Text zu „{title}“ hinzugefügt. | Texto añadido a «{title}». | Texte ajouté à « {title} ». | 已为“{title}”添加文字。 | 已為「{title}」添加文字。 |
| `ocrJobNoText` | No text found in “{title}”. | Kein Text in „{title}“ gefunden. | No se encontró texto en «{title}». | Aucun texte trouvé dans « {title} ». | 在“{title}”中未找到文字。 | 在「{title}」中未找到文字。 |
| `ocrJobFailed` | Couldn’t make “{title}” searchable: {error} | „{title}“ konnte nicht durchsuchbar gemacht werden: {error} | No se pudo hacer buscable «{title}»: {error} | Impossible de rendre « {title} » consultable : {error} | 无法使“{title}”可搜索：{error} | 無法使「{title}」可搜尋：{error} |

6. Docs:
- `CLAUDE.md`, in the "Scanning: the scan dialog and its helpers" note, a paragraph **Background OCR (2026-10-11)**: what's requested and when (setting, languages), the `ocr_jobs` table and `job_id` NULL, the runner (3 s, one pass/one fallback at a time, started after a scan and on open, stopped in `resetAll()`), swap-in with the original kept and the hash check, the fallback triggers (404/500, 10 minutes unreachable or 401, discarded result, no `ocrJob` and no text layer), the Waste bin, the library-switch guard (`isStale`), and why `last_reached_at` isn't stored. Point to the spec and to dossiary-scan-helper's `PROTOCOL.md`.
- `tests/CLAUDE.md`: extend the `test_scan_dialog.py` description with the OCR scenarios and the stub's `scan_auto_ocr` default (`window.__STUB_KEEP_SCAN_AUTO_OCR`), like the `view_mode` note.

- [ ] **Step 3: Run the tests**

Run: `cd tests && python3 test_scan_dialog.py 2>&1 | grep -v ": True$"` → only headers. Also `python3 test_i18n_coverage.py | tail -1` (PASS), `python3 test_make_searchable.py`, `python3 test_page_tools.py`, `python3 test_waste_bin.py`, `python3 test_grid_view.py`, `python3 test_detail_panel.py` → no `False`.

- [ ] **Step 4: Commit**

```bash
git add dossiary.html tests/test_scan_dialog.py CLAUDE.md tests/CLAUDE.md
git commit -m "Scans: follow OCR jobs, swap in the searchable PDF, fall back to Dossiary's own OCR"
```
