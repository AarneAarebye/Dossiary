# Broken File Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the shipped "Find duplicates" modal/button to the more general "Library check," and add a new broken-file-link check to it — detecting any non-deleted document whose `file_path`/`original_file_path` no longer resolves to a real file, with a "Re-link…" action that restores the missing file at its exact existing stored path and recomputes `file_hash` when appropriate.

**Architecture:** `openFindDuplicatesModal()` becomes `openLibraryCheckModal()`, gaining a third, persistence-free check (`computeBrokenFileLinks()`) alongside its two existing duplicate-grouping computations. `renderDuplicateGroups()` becomes `renderLibraryCheckResults()`, rendering a third "Broken file links" section whose rows reuse the existing `.duplicate-row` class (for its click-to-detail-panel behavior) plus new indicator/button markup. Re-linking uses a dynamically created `<input type="file">` per click (mirroring the capture form's static file input) to pick replacement bytes, written directly into the already-correct stored path via the existing `resolveFileHandle(path, true)`.

**Tech Stack:** Vanilla JS in `dossiary.html` (no framework), File System Access API, `crypto.subtle` (SHA-256), Playwright-driven Python test scripts against `tests/stub_studio2.js`.

## Global Constraints

- Single-file app — all changes go in `dossiary.html`; no new files except the two test additions this plan specifies.
- Only `file_path`/`original_file_path` are checked — never `thumbnail_path`.
- The re-link write goes to the **exact existing stored path** via `resolveFileHandle(path, true)` — no database row/path changes, ever.
- `file_hash` is recomputed after a re-link **only** when the repaired path is the one it was derived from (`original_file_path` if the document has one, else `file_path`) — the same fallback rule `backfillFileHash()` already uses. The other path leaves `file_hash` untouched.
- A `NULL` path is never flagged as broken — only a path that is *set* but fails to resolve.
- The check runs fresh on every modal open, over every non-deleted document (archived/needs-review included) — no persisted state, no lazy backfill for this check (unlike the existing `file_hash` backfill, which is unaffected and keeps running first when needed).
- Any error from `resolveFileHandle(path, false)` counts as "broken" — not narrowly `NotFoundError`.
- Rename scope: `#find-duplicates-btn` → `#library-check-btn`; `openFindDuplicatesModal()` → `openLibraryCheckModal()`; `window.__DEBUG_openFindDuplicatesModal` → `window.__DEBUG_openLibraryCheckModal`; i18n keys `toolbarFindDuplicates` → `toolbarLibraryCheck`, `duplicatesModalTitle` → `libraryCheckModalTitle`, `duplicatesNoneFound` → `libraryCheckNoneFound` (now a whole-modal empty state covering all three sections). Everything else stays as-is: `findDuplicatesBackfillRunning` (variable name), `window.__DEBUG_findDuplicatesBackfillRunning`, `#duplicates-list`, `#duplicates-progress`, `#duplicates-empty`, `.duplicate-group`, `.duplicate-group-label`, `.duplicate-row`, `duplicatesBackfillProgress`, `duplicatesExactMatchLabel`, `duplicatesMetadataMatchLabel` — these describe the duplicate-checking sections specifically, which are unchanged.
- Follow this repo's i18n convention: every language's set of keys for one feature sits on one dense source line, appended after the immediately-preceding related keys.
- Every test file must load `tests/stub_studio2.js` — never an embedded copy.

---

### Task 1: Rename "Find duplicates" to "Library check"

**Files:**
- Modify: `dossiary.html` (button HTML ~line 702; module-level i18n keys at lines 1069/1270/1471/1672/1873/2200; `openFindDuplicatesModal()` at lines 5573-5636; `renderDuplicateGroups()` declaration at line 5638; debug hook at line 3705; toolbar wiring at line 8653)
- Modify: `tests/test_duplicate_detection.py` (6 call sites for the debug hook)
- Test: `tests/test_duplicate_detection.py` (run existing suite, no new scenarios this task)

**Interfaces:**
- Consumes: nothing new.
- Produces: `openLibraryCheckModal()` (async, no params) — the modal-open entry point every later task in this plan extends. `window.__DEBUG_openLibraryCheckModal` — the test-facing hook. i18n keys `toolbarLibraryCheck`, `libraryCheckModalTitle`, `libraryCheckNoneFound` — used by Task 2's rendering work.

This task is a pure rename with no behavior change — every existing scenario in `tests/test_duplicate_detection.py` must still pass afterward, proving the rename didn't alter behavior.

- [ ] **Step 1: Rename the toolbar button**

In `dossiary.html`, find this line (around line 702):

```html
        <button id="find-duplicates-btn" data-i18n="toolbarFindDuplicates">🔍 Find duplicates</button>
```

Replace with:

```html
        <button id="library-check-btn" data-i18n="toolbarLibraryCheck">🔍 Library check</button>
```

- [ ] **Step 2: Rename the three i18n keys across all six languages**

In `dossiary.html`, each language's `STRINGS` block has one dense line containing `duplicatesModalTitle`, `duplicatesBackfillProgress`, `duplicatesExactMatchLabel`, `duplicatesMetadataMatchLabel`, `duplicatesNoneFound`, `toolbarFindDuplicates` (in that order, at the end of the line). Only three of these six keys are renamed — `duplicatesBackfillProgress`, `duplicatesExactMatchLabel`, `duplicatesMetadataMatchLabel` are untouched. Apply these six edits (one per language):

English (line 1069) — find:
```
duplicatesModalTitle: 'Find duplicates', duplicatesBackfillProgress: 'Checking {done} of {total} documents for duplicates…', duplicatesExactMatchLabel: 'Exact file match', duplicatesMetadataMatchLabel: 'Likely duplicate (title + date)', duplicatesNoneFound: 'No duplicates found.', toolbarFindDuplicates: '🔍 Find duplicates',
```
Replace with:
```
libraryCheckModalTitle: 'Library check', duplicatesBackfillProgress: 'Checking {done} of {total} documents for duplicates…', duplicatesExactMatchLabel: 'Exact file match', duplicatesMetadataMatchLabel: 'Likely duplicate (title + date)', libraryCheckNoneFound: 'No issues found.', toolbarLibraryCheck: '🔍 Library check',
```

Spanish (line 1270) — find:
```
duplicatesModalTitle: 'Buscar duplicados', duplicatesBackfillProgress: 'Comprobando {done} de {total} documentos en busca de duplicados…', duplicatesExactMatchLabel: 'Coincidencia exacta de archivo', duplicatesMetadataMatchLabel: 'Posible duplicado (título + fecha)', duplicatesNoneFound: 'No se encontraron duplicados.', toolbarFindDuplicates: '🔍 Buscar duplicados',
```
Replace with:
```
libraryCheckModalTitle: 'Revisión de la biblioteca', duplicatesBackfillProgress: 'Comprobando {done} de {total} documentos en busca de duplicados…', duplicatesExactMatchLabel: 'Coincidencia exacta de archivo', duplicatesMetadataMatchLabel: 'Posible duplicado (título + fecha)', libraryCheckNoneFound: 'No se encontraron problemas.', toolbarLibraryCheck: '🔍 Revisión de la biblioteca',
```

French (line 1471) — find:
```
duplicatesModalTitle: 'Rechercher les doublons', duplicatesBackfillProgress: 'Vérification de {done} sur {total} documents pour les doublons…', duplicatesExactMatchLabel: 'Fichier identique', duplicatesMetadataMatchLabel: 'Doublon probable (titre + date)', duplicatesNoneFound: 'Aucun doublon trouvé.', toolbarFindDuplicates: '🔍 Rechercher les doublons',
```
Replace with:
```
libraryCheckModalTitle: 'Vérification de la bibliothèque', duplicatesBackfillProgress: 'Vérification de {done} sur {total} documents pour les doublons…', duplicatesExactMatchLabel: 'Fichier identique', duplicatesMetadataMatchLabel: 'Doublon probable (titre + date)', libraryCheckNoneFound: 'Aucun problème détecté.', toolbarLibraryCheck: '🔍 Vérifier la bibliothèque',
```

German (line 1672) — find:
```
duplicatesModalTitle: 'Duplikate finden', duplicatesBackfillProgress: 'Prüfe {done} von {total} Dokumenten auf Duplikate…', duplicatesExactMatchLabel: 'Exakte Dateiübereinstimmung', duplicatesMetadataMatchLabel: 'Wahrscheinliches Duplikat (Titel + Datum)', duplicatesNoneFound: 'Keine Duplikate gefunden.', toolbarFindDuplicates: '🔍 Duplikate finden',
```
Replace with:
```
libraryCheckModalTitle: 'Bibliotheksprüfung', duplicatesBackfillProgress: 'Prüfe {done} von {total} Dokumenten auf Duplikate…', duplicatesExactMatchLabel: 'Exakte Dateiübereinstimmung', duplicatesMetadataMatchLabel: 'Wahrscheinliches Duplikat (Titel + Datum)', libraryCheckNoneFound: 'Keine Probleme gefunden.', toolbarLibraryCheck: '🔍 Bibliothek prüfen',
```

Chinese Simplified (line 1873) — find:
```
duplicatesModalTitle: '查找重复项', duplicatesBackfillProgress: '正在检查第 {done}/{total} 个文档是否重复……', duplicatesExactMatchLabel: '文件完全匹配', duplicatesMetadataMatchLabel: '可能重复（标题+日期）', duplicatesNoneFound: '未发现重复项。', toolbarFindDuplicates: '🔍 查找重复项',
```
Replace with:
```
libraryCheckModalTitle: '资料库检查', duplicatesBackfillProgress: '正在检查第 {done}/{total} 个文档是否重复……', duplicatesExactMatchLabel: '文件完全匹配', duplicatesMetadataMatchLabel: '可能重复（标题+日期）', libraryCheckNoneFound: '未发现问题。', toolbarLibraryCheck: '🔍 资料库检查',
```

Chinese Traditional (line 2200) — find:
```
duplicatesModalTitle: '查找重複項', duplicatesBackfillProgress: '正在檢查第 {done}/{total} 個文檔是否重複……', duplicatesExactMatchLabel: '文件完全匹配', duplicatesMetadataMatchLabel: '可能重複（標題+日期）', duplicatesNoneFound: '未發現重複項。', toolbarFindDuplicates: '🔍 查找重複項',
```
Replace with:
```
libraryCheckModalTitle: '資料庫檢查', duplicatesBackfillProgress: '正在檢查第 {done}/{total} 個文檔是否重複……', duplicatesExactMatchLabel: '文件完全匹配', duplicatesMetadataMatchLabel: '可能重複（標題+日期）', libraryCheckNoneFound: '未發現問題。', toolbarLibraryCheck: '🔍 資料庫檢查',
```

- [ ] **Step 3: Rename the modal-open function, its debug hook, and its internal key references**

In `dossiary.html`, at line 5573, find:
```javascript
  async function openFindDuplicatesModal(){
```
Replace with:
```javascript
  async function openLibraryCheckModal(){
```

At line 5580 (inside that function), find:
```javascript
          <h2>${t('duplicatesModalTitle')}</h2>
```
Replace with:
```javascript
          <h2>${t('libraryCheckModalTitle')}</h2>
```

At line 5647 (inside `renderDuplicateGroups`, still same name until Step 4), find:
```javascript
      listEl.innerHTML = `<p id="duplicates-empty">${t('duplicatesNoneFound')}</p>`;
```
Replace with:
```javascript
      listEl.innerHTML = `<p id="duplicates-empty">${t('libraryCheckNoneFound')}</p>`;
```

At line 3705, find:
```javascript
  window.__DEBUG_openFindDuplicatesModal = openFindDuplicatesModal;
```
Replace with:
```javascript
  window.__DEBUG_openLibraryCheckModal = openLibraryCheckModal;
```

At line 8653, find:
```javascript
  el('find-duplicates-btn').addEventListener('click', openFindDuplicatesModal);
```
Replace with:
```javascript
  el('library-check-btn').addEventListener('click', openLibraryCheckModal);
```

- [ ] **Step 4: Rename `renderDuplicateGroups` to `renderLibraryCheckResults`**

At line 5635 (the call site inside `openLibraryCheckModal()`), find:
```javascript
    renderDuplicateGroups(exactGroups, metadataGroups);
```
Replace with:
```javascript
    renderLibraryCheckResults(exactGroups, metadataGroups);
```

At line 5638 (the declaration), find:
```javascript
  function renderDuplicateGroups(exactGroups, metadataGroups){
```
Replace with:
```javascript
  function renderLibraryCheckResults(exactGroups, metadataGroups){
```

(Task 2 will add a third parameter to both this declaration and its call site — leave the signature at two parameters for now, since this task is rename-only.)

- [ ] **Step 5: Update `tests/test_duplicate_detection.py`'s six debug-hook call sites**

In `tests/test_duplicate_detection.py`, replace every occurrence of `window.__DEBUG_openFindDuplicatesModal` with `window.__DEBUG_openLibraryCheckModal`. There are six call sites, at (current) lines 219, 247, 268, 374, 477, and 569. Do **not** touch `window.__DEBUG_findDuplicatesBackfillRunning` (line 575) — that name is unchanged per this plan's Global Constraints.

The simplest correct approach is a project-wide search-and-replace scoped to this one file:

```bash
cd tests
sed -i '' 's/__DEBUG_openFindDuplicatesModal/__DEBUG_openLibraryCheckModal/g' test_duplicate_detection.py
```

Then manually verify with `grep -n "__DEBUG_openFindDuplicatesModal\|__DEBUG_openLibraryCheckModal\|__DEBUG_findDuplicatesBackfillRunning" test_duplicate_detection.py` that exactly zero occurrences of the old name remain, six occurrences of the new name exist, and the one `__DEBUG_findDuplicatesBackfillRunning` reference is untouched.

- [ ] **Step 6: Run the full existing duplicate-detection suite to confirm the rename is behavior-preserving**

Run: `cd tests && python3 test_duplicate_detection.py`
Expected: `PASS` (or equivalent all-green output) with no failures — every existing scenario exercises the renamed button/function/hook and must still pass unchanged, since this task changed only names, not logic.

- [ ] **Step 7: Also run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: PASS — confirms every renamed/kept i18n key still exists identically across all six `STRINGS` blocks (this static check would catch a typo'd key name or a language block that didn't get all three renames applied).

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_duplicate_detection.py
git commit -m "$(cat <<'EOF'
Rename Find duplicates to Library check

Prep work for the broken-file-links feature: the modal and toolbar
button are being generalized to cover more than just duplicate
detection, so they take the more general name first.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```

---

### Task 2: Detect broken file links and render a new section for them

**Files:**
- Modify: `dossiary.html` (new `computeBrokenFileLinks()` function; `openLibraryCheckModal()` extended; `renderLibraryCheckResults()` extended with a third parameter and new section rendering; new CSS rules near line 192; three new i18n keys across six languages; two new test-only debug hooks near line 3705)
- Test: `tests/test_broken_links.py` (new file)

**Interfaces:**
- Consumes: `resolveFileHandle(relPath, create)` (existing, dossiary.html:4613) — returns a `FileSystemFileHandle`, throws on failure when `create` is falsy. `displayName(d)` (existing, dossiary.html:4624). `escapeHtml(s)` (existing). `t(key, params)` (existing). `openLibraryCheckModal()`/`renderLibraryCheckResults(exactGroups, metadataGroups)` from Task 1.
- Produces: `computeBrokenFileLinks(docs)` — async function, takes an array of document objects (already filtered to non-deleted), returns a Promise resolving to an array of `{ doc, broken: { file: true|undefined, original: true|undefined } }` entries, one per document with at least one broken path. `renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks)` — now takes a third parameter, the array `computeBrokenFileLinks()` returns. New CSS classes `.broken-link-row`, `.broken-link-indicators`, `.broken-link-indicator` for Task 3 to also use. New i18n keys `libraryCheckBrokenLinksLabel`, `libraryCheckFileLabel`, `libraryCheckOriginalLabel` for Task 3's rendering to also use. Test-only hooks `window.__DEBUG_computeBrokenFileLinks` and `window.__DEBUG_getDocPaths(documentId)` (returns `{file_path, original_file_path}` read from `allDocs`) for Task 3's tests to also use.

This task adds detection and read-only display only — no re-link button wiring or file-picker logic yet (that's Task 3). Rows render with their "File"/"Original" text indicators but no button, so this task's own tests only cover detection and rendering, not repair.

- [ ] **Step 1: Add `computeBrokenFileLinks()`**

In `dossiary.html`, immediately after `computeMetadataDuplicateGroups()` (which ends at line 5571, right before the blank line and `async function openLibraryCheckModal(){` from Task 1), insert:

```javascript
  // Checks every doc's set file_path/original_file_path for real existence --
  // cheap (never reads a file's bytes, just resolveFileHandle(path, false) and
  // catches whatever it throws, not narrowly NotFoundError, matching this app's
  // existing generic file-error handling in buildDetailActions()'s own
  // alert(t('detailOpenFileError', ...))) so this runs fresh on every modal
  // open with no persisted state and no backfill, unlike file_hash above. A
  // NULL path was simply never given one and is never flagged -- only a path
  // that's actually SET but doesn't resolve counts as broken.
  async function computeBrokenFileLinks(docs){
    const results = [];
    for(const d of docs){
      const broken = {};
      if(d.file_path){
        try{ await resolveFileHandle(d.file_path, false); }
        catch(e){ broken.file = true; }
      }
      if(d.original_file_path){
        try{ await resolveFileHandle(d.original_file_path, false); }
        catch(e){ broken.original = true; }
      }
      if(broken.file || broken.original) results.push({ doc: d, broken });
    }
    return results;
  }

```

- [ ] **Step 2: Wire it into `openLibraryCheckModal()`**

At the end of `openLibraryCheckModal()` (around line 5632-5636 after Task 1's rename), find:
```javascript
    const activeDocs = allDocs.filter(d => !d.deleted);
    const exactGroups = computeExactHashDuplicateGroups(activeDocs);
    const metadataGroups = computeMetadataDuplicateGroups(activeDocs);
    renderLibraryCheckResults(exactGroups, metadataGroups);
  }
```
Replace with:
```javascript
    const activeDocs = allDocs.filter(d => !d.deleted);
    const exactGroups = computeExactHashDuplicateGroups(activeDocs);
    const metadataGroups = computeMetadataDuplicateGroups(activeDocs);
    const brokenLinks = await computeBrokenFileLinks(activeDocs);
    renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks);
  }
```

- [ ] **Step 3: Extend `renderLibraryCheckResults()` with the new section**

Find the current function (from Task 1's rename):
```javascript
  function renderLibraryCheckResults(exactGroups, metadataGroups){
    // Defensive: the modal could have been replaced by something else (e.g.
    // another modal opened via keyboard Tab-through while this one's close
    // button was disabled during a backfill) by the time this runs -- not a
    // full focus-trap, just a guard against writing into a container that's
    // no longer there.
    const listEl = el('duplicates-list');
    if(!listEl) return;
    if(!exactGroups.length && !metadataGroups.length){
      listEl.innerHTML = `<p id="duplicates-empty">${t('libraryCheckNoneFound')}</p>`;
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

Replace it with:
```javascript
  function renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks){
    // Defensive: the modal could have been replaced by something else (e.g.
    // another modal opened via keyboard Tab-through while this one's close
    // button was disabled during a backfill) by the time this runs -- not a
    // full focus-trap, just a guard against writing into a container that's
    // no longer there.
    const listEl = el('duplicates-list');
    if(!listEl) return;
    if(!exactGroups.length && !metadataGroups.length && !brokenLinks.length){
      listEl.innerHTML = `<p id="duplicates-empty">${t('libraryCheckNoneFound')}</p>`;
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
    // Each broken-link row reuses .duplicate-row (for its existing click-to-
    // detail-panel wiring below) plus its own .broken-link-row marker class.
    // The indicators span stops propagation so clicking "Re-link..." (wired in
    // Task 3) doesn't also trigger the row's own click-through.
    const brokenLinkRowHtml = (entry) => `
      <div class="duplicate-row broken-link-row" data-document-id="${entry.doc.id}">
        <span class="doc-title">${escapeHtml(displayName(entry.doc))}</span>
        <span class="broken-link-indicators" onclick="event.stopPropagation()">
          ${entry.broken.file ? `<span class="broken-link-indicator" data-path-field="file_path">${t('libraryCheckFileLabel')}</span>` : ''}
          ${entry.broken.original ? `<span class="broken-link-indicator" data-path-field="original_file_path">${t('libraryCheckOriginalLabel')}</span>` : ''}
        </span>
      </div>
    `;
    const brokenLinksSection = brokenLinks.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label">${t('libraryCheckBrokenLinksLabel')}</div>
        ${brokenLinks.map(brokenLinkRowHtml).join('')}
      </div>
    ` : '';
    listEl.innerHTML = [
      ...exactGroups.map(g => groupHtml(g, 'duplicatesExactMatchLabel')),
      ...metadataGroups.map(g => groupHtml(g, 'duplicatesMetadataMatchLabel')),
      brokenLinksSection,
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

(Task 3 will add the "Re-link…" button markup inside each `.broken-link-indicator` span, plus its own click wiring, right after this function.)

- [ ] **Step 4: Add the new CSS**

In `dossiary.html`, right after the existing `.duplicate-row:hover{ background:var(--ink-2); }` rule (line 192), insert:

```css
  .broken-link-indicators{ display:flex; align-items:center; gap:10px; flex-shrink:0; flex-wrap:wrap; justify-content:flex-end; }
  .broken-link-indicator{ display:flex; align-items:center; gap:6px; font-family:var(--font-mono); font-size:11.5px; color:var(--text-dim); flex-wrap:wrap; }
```

- [ ] **Step 5: Add the three new i18n keys across all six languages**

Same dense-line convention as Task 1 — append to the same line each language's Task-1-renamed keys now sit on, right after `toolbarLibraryCheck: '...',`.

English (line 1069) — the line now ends `..., toolbarLibraryCheck: '🔍 Library check',`. Append immediately after it (still the same line):
```
libraryCheckBrokenLinksLabel: 'Broken file links', libraryCheckFileLabel: 'File', libraryCheckOriginalLabel: 'Original',
```

Spanish (line 1270) — append after `toolbarLibraryCheck: '🔍 Revisión de la biblioteca',`:
```
libraryCheckBrokenLinksLabel: 'Enlaces de archivo rotos', libraryCheckFileLabel: 'Archivo', libraryCheckOriginalLabel: 'Original',
```

French (line 1471) — append after `toolbarLibraryCheck: '🔍 Vérifier la bibliothèque',`:
```
libraryCheckBrokenLinksLabel: 'Liens de fichiers rompus', libraryCheckFileLabel: 'Fichier', libraryCheckOriginalLabel: 'Original',
```

German (line 1672) — append after `toolbarLibraryCheck: '🔍 Bibliothek prüfen',`:
```
libraryCheckBrokenLinksLabel: 'Fehlende Dateiverknüpfungen', libraryCheckFileLabel: 'Datei', libraryCheckOriginalLabel: 'Original',
```

Chinese Simplified (line 1873) — append after `toolbarLibraryCheck: '🔍 资料库检查',`:
```
libraryCheckBrokenLinksLabel: '损坏的文件链接', libraryCheckFileLabel: '文件', libraryCheckOriginalLabel: '原件',
```

Chinese Traditional (line 2200) — append after `toolbarLibraryCheck: '🔍 資料庫檢查',`:
```
libraryCheckBrokenLinksLabel: '損壞的檔案連結', libraryCheckFileLabel: '檔案', libraryCheckOriginalLabel: '原件',
```

- [ ] **Step 6: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: PASS — the three new keys must exist identically (same key set) across all six `STRINGS` blocks.

- [ ] **Step 7: Add two new debug hooks needed for testing**

In `dossiary.html`, near line 3705-3710 (where `window.__DEBUG_openLibraryCheckModal` and `window.__DEBUG_findDuplicatesBackfillRunning` are defined), add:

```javascript
  // computeBrokenFileLinks() itself so a test can independently verify its
  // output without going through the full modal-open flow
  window.__DEBUG_computeBrokenFileLinks = computeBrokenFileLinks;
  // Test-only: reads a document's own file_path/original_file_path directly
  // from in-memory state, so a test can locate the exact stub-filesystem path
  // to delete (simulating a file moved/deleted outside the app) without
  // duplicating this app's own file-naming logic.
  window.__DEBUG_getDocPaths = (documentId) => {
    const d = allDocs.find(x => x.id === documentId);
    return d ? { file_path: d.file_path, original_file_path: d.original_file_path } : undefined;
  };
```

- [ ] **Step 8: Write `tests/test_broken_links.py` (detection scenarios)**

This suite's real convention (confirmed by reading `tests/test_duplicate_detection.py` in full) is: an `async def main():` function using `playwright.async_api`, stubbing `sql-wasm.js`/`tesseract`/`jspdf`/`pdf.js` network requests, injecting `stub_studio2.js` via `page.add_init_script`, opening a fresh empty library via `window.__TEST_ROOT = window.__makeEmptyRoot();` + clicking `#open-btn` then `#init-btn`, driving the real UI (`#add-btn`, `#file-input` via `page.set_input_files`, `#f-title`, `#f-date`, `#save-doc-btn`) to create real documents, and printing `print("<description>:", <bool>)` lines — no `assert`/exit-code convention, no seeding-helper JSON blob. `window.__TEST_ROOT` is the same fake root directory handle the app itself holds, directly walkable (`getDirectoryHandle`/`getFileHandle`/`removeEntry`) to simulate a file moved or deleted outside the app. Create `tests/test_broken_links.py` with exactly this structure:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio
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

        async def delete_stub_file(rel_path):
            # Walks window.__TEST_ROOT the same way resolveFileHandle() does,
            # ending in removeEntry() on the parent directory instead of
            # getFileHandle() -- simulates the underlying file being moved or
            # deleted outside the app, without touching the document's own
            # stored path at all.
            await page.evaluate("""
                async (relPath) => {
                    const parts = relPath.split('/');
                    let dir = window.__TEST_ROOT;
                    for (let i = 0; i < parts.length - 1; i++) {
                        dir = await dir.getDirectoryHandle(parts[i]);
                    }
                    await dir.removeEntry(parts[parts.length - 1]);
                }
            """, rel_path)

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

        # Doc 1: fine, both paths resolve -- must not be flagged at all.
        await capture_document('Fine Doc', b'%PDF-1.4 fine doc', 'fine.pdf')

        # Doc 2: file_path broken, original_file_path fine.
        await capture_document('Broken File Doc', b'%PDF-1.4 broken file doc', 'broken-file.pdf')
        doc2_paths = await page.evaluate("window.__DEBUG_getDocPaths(2)")
        await delete_stub_file(doc2_paths['file_path'])

        # Doc 3: original_file_path broken, file_path fine.
        await capture_document('Broken Original Doc', b'%PDF-1.4 broken original doc', 'broken-original.pdf')
        doc3_paths = await page.evaluate("window.__DEBUG_getDocPaths(3)")
        await delete_stub_file(doc3_paths['original_file_path'])

        # Doc 4: both paths broken.
        await capture_document('Both Broken Doc', b'%PDF-1.4 both broken doc', 'both-broken.pdf')
        doc4_paths = await page.evaluate("window.__DEBUG_getDocPaths(4)")
        await delete_stub_file(doc4_paths['file_path'])
        await delete_stub_file(doc4_paths['original_file_path'])

        # Doc 5: original_file_path forced to NULL (simulating a document with
        # no distinct original, e.g. a migrated document -- not reachable via
        # this app's own capture UI, which always preserves an original, so
        # this is set directly via __DEBUG_dbRun + a refresh from the DB).
        # file_path is left fine -- must NOT be flagged, since a NULL path is
        # never checked in the first place.
        await capture_document('No Original Doc', b'%PDF-1.4 no original doc', 'no-original.pdf')
        await page.evaluate("""
            async () => {
                window.__DEBUG_dbRun('UPDATE documents SET original_file_path = NULL WHERE id = ?', [5]);
                await window.__DEBUG_loadDocumentsFromDb();
            }
        """)

        # Doc 6: both paths broken, then the document itself is deleted -- must
        # be excluded from the check entirely, even though its paths are broken.
        await capture_document('Deleted Broken Doc', b'%PDF-1.4 deleted broken doc', 'deleted-broken.pdf')
        doc6_paths = await page.evaluate("window.__DEBUG_getDocPaths(6)")
        await delete_stub_file(doc6_paths['file_path'])
        await delete_stub_file(doc6_paths['original_file_path'])
        await page.click('tr[data-id="6"]')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)

        # === Render check: opening the modal shows a "Broken file links" row
        # per affected document, with the right File/Original indicators ===
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)

        broken_row_ids = await page.evaluate("""
            () => Array.from(document.querySelectorAll('.broken-link-row')).map(r => r.dataset.documentId)
        """)
        print("Exactly 3 broken-link rows shown (docs 2, 3, 4):", sorted(broken_row_ids) == ['2', '3', '4'])

        doc2_row = page.locator('.broken-link-row[data-document-id="2"]')
        print("Doc 2's row shows a File indicator:", await doc2_row.locator('.broken-link-indicator[data-path-field="file_path"]').count() == 1)
        print("Doc 2's row shows no Original indicator:", await doc2_row.locator('.broken-link-indicator[data-path-field="original_file_path"]').count() == 0)

        doc3_row = page.locator('.broken-link-row[data-document-id="3"]')
        print("Doc 3's row shows an Original indicator:", await doc3_row.locator('.broken-link-indicator[data-path-field="original_file_path"]').count() == 1)
        print("Doc 3's row shows no File indicator:", await doc3_row.locator('.broken-link-indicator[data-path-field="file_path"]').count() == 0)

        doc4_row = page.locator('.broken-link-row[data-document-id="4"]')
        print("Doc 4's row shows both File and Original indicators:",
              await doc4_row.locator('.broken-link-indicator[data-path-field="file_path"]').count() == 1 and
              await doc4_row.locator('.broken-link-indicator[data-path-field="original_file_path"]').count() == 1)

        print("Doc 5 (NULL original_file_path, file_path fine) is not flagged at all:",
              await page.locator('.broken-link-row[data-document-id="5"]').count() == 0)
        print("Doc 6 (deleted) is excluded even though its paths are broken:",
              await page.locator('.broken-link-row[data-document-id="6"]').count() == 0)
        print("Doc 1 (fine) is not flagged:",
              await page.locator('.broken-link-row[data-document-id="1"]').count() == 0)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 9: Run the new test**

Run: `cd tests && python3 test_broken_links.py`
Expected: PASS, all checks green.

- [ ] **Step 10: Run the existing duplicate-detection suite again to confirm no regression**

Run: `cd tests && python3 test_duplicate_detection.py`
Expected: PASS — the third-parameter addition to `renderLibraryCheckResults()` and the new broken-links section must not disturb any exact-hash/metadata-match scenario, including the "no duplicates found" empty-state scenario (which now must also account for `brokenLinks.length` being zero in that test's own fixture).

- [ ] **Step 11: Commit**

```bash
git add dossiary.html tests/test_broken_links.py
git commit -m "$(cat <<'EOF'
Detect broken file links in the Library check modal

Adds a persistence-free check for documents whose file_path/
original_file_path no longer resolves to a real file, rendered as a
new section in the just-renamed Library check modal. Detection and
display only -- re-linking lands in the next commit.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```

---

### Task 3: Re-link mechanism and hash recompute

**Files:**
- Modify: `dossiary.html` (new `triggerRelink()`/`performRelink()` functions; "Re-link…" button markup added to `renderLibraryCheckResults()`'s broken-link indicator HTML; two new i18n keys across six languages)
- Test: `tests/test_broken_links.py` (extended with re-link scenarios)

**Interfaces:**
- Consumes: `resolveFileHandle(relPath, create)` (existing). `computeFileHash(file)` (existing, dossiary.html:2759) — takes a `File`, returns a Promise resolving to a hex SHA-256 string. `persistDb()` (existing, dossiary.html:3440) — no params, writes `db.export()` bytes to `dbFileHandle`. `allDocs` (existing module-level array). `db.run(sql, params)` (existing). `.broken-link-indicator`/`.broken-link-row` (from Task 2).
- Produces: `triggerRelink(documentId, pathField, indicatorEl)` — opens a file picker, delegates to `performRelink()` on selection. `performRelink(documentId, pathField, file, indicatorEl)` — async, writes the picked file's bytes to the document's stored path for `pathField`, recomputes/persists `file_hash` when appropriate, and updates the DOM in place (removing the indicator on success, showing an inline error on failure). New i18n keys `libraryCheckRelinkBtn`, `libraryCheckRelinkFailed`.

- [ ] **Step 1: Add the "Re-link…" button to each broken-link indicator**

In `dossiary.html`, in `renderLibraryCheckResults()` (from Task 2), find:
```javascript
    const brokenLinkRowHtml = (entry) => `
      <div class="duplicate-row broken-link-row" data-document-id="${entry.doc.id}">
        <span class="doc-title">${escapeHtml(displayName(entry.doc))}</span>
        <span class="broken-link-indicators" onclick="event.stopPropagation()">
          ${entry.broken.file ? `<span class="broken-link-indicator" data-path-field="file_path">${t('libraryCheckFileLabel')}</span>` : ''}
          ${entry.broken.original ? `<span class="broken-link-indicator" data-path-field="original_file_path">${t('libraryCheckOriginalLabel')}</span>` : ''}
        </span>
      </div>
    `;
```
Replace with:
```javascript
    const brokenLinkRowHtml = (entry) => `
      <div class="duplicate-row broken-link-row" data-document-id="${entry.doc.id}">
        <span class="doc-title">${escapeHtml(displayName(entry.doc))}</span>
        <span class="broken-link-indicators" onclick="event.stopPropagation()">
          ${entry.broken.file ? `<span class="broken-link-indicator" data-path-field="file_path">${t('libraryCheckFileLabel')} <button type="button" class="relink-btn" data-document-id="${entry.doc.id}" data-path-field="file_path">${t('libraryCheckRelinkBtn')}</button></span>` : ''}
          ${entry.broken.original ? `<span class="broken-link-indicator" data-path-field="original_file_path">${t('libraryCheckOriginalLabel')} <button type="button" class="relink-btn" data-document-id="${entry.doc.id}" data-path-field="original_file_path">${t('libraryCheckRelinkBtn')}</button></span>` : ''}
        </span>
      </div>
    `;
```

Then, still inside `renderLibraryCheckResults()`, right after the existing `.duplicate-row` click-wiring block (`listEl.querySelectorAll('.duplicate-row').forEach(...)`), add a new wiring block for the re-link buttons:
```javascript
    listEl.querySelectorAll('.relink-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const documentId = Number(btn.dataset.documentId);
        const pathField = btn.dataset.pathField;
        triggerRelink(documentId, pathField, btn.closest('.broken-link-indicator'));
      });
    });
```

- [ ] **Step 2: Add `triggerRelink()` and `performRelink()`**

In `dossiary.html`, right after `renderLibraryCheckResults()`'s closing `}`, insert:

```javascript
  // Opens a plain native file picker (same accept restriction as the capture
  // form's own #file-input) scoped to one broken path on one document. A
  // dynamically created input, not the static capture-form one, since each
  // click needs to carry which document + which path field it's repairing.
  // Cancelling the picker with no file chosen is a silent no-op, matching how
  // the capture form's own file input already behaves.
  function triggerRelink(documentId, pathField, indicatorEl){
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/pdf,image/*';
    input.className = 'relink-file-input'; // stable selector for tests to target, since this element has no persistent id
    input.style.display = 'none';
    document.body.appendChild(input);
    input.addEventListener('change', async () => {
      const file = input.files[0];
      document.body.removeChild(input);
      if(!file) return;
      await performRelink(documentId, pathField, file, indicatorEl);
    });
    input.click();
  }

  // Writes the picked file's bytes into the document's EXACT existing stored
  // path for pathField ('file_path' or 'original_file_path') -- no database
  // path/row changes at all, since the path itself was already correct; only
  // the missing file at it is restored. resolveFileHandle(path, true) creates
  // whatever directories/file are missing along the way.
  //
  // Recomputes and persists file_hash only when the just-repaired path is the
  // one it was derived from -- original_file_path when the document has one,
  // otherwise file_path -- the same fallback rule backfillFileHash() already
  // uses. Re-linking the OTHER path leaves file_hash untouched, since it was
  // never derived from that path in the first place.
  //
  // On success, removes just this one now-fixed indicator from the DOM in
  // place (or the whole row, if it was the document's only broken indicator)
  // -- no full re-scan of the other two sections is needed, since nothing
  // about duplicate grouping changed. On failure, shows an inline error next
  // to the still-present Re-link button, so nothing silently looks fixed when
  // it isn't; any earlier error on the same indicator is cleared first so a
  // retry doesn't stack duplicate messages.
  async function performRelink(documentId, pathField, file, indicatorEl){
    const d = allDocs.find(x => x.id === documentId);
    if(!d) return;
    const path = d[pathField];
    const existingError = indicatorEl.querySelector('.relink-error');
    if(existingError) existingError.remove();
    try{
      const fileHandle = await resolveFileHandle(path, true);
      const writable = await fileHandle.createWritable();
      await writable.write(await file.arrayBuffer());
      await writable.close();

      const hashSourceField = d.original_file_path ? 'original_file_path' : 'file_path';
      if(pathField === hashSourceField){
        const newHash = await computeFileHash(file);
        d.file_hash = newHash;
        db.run('UPDATE documents SET file_hash = ? WHERE id = ?', [newHash, documentId]);
        await persistDb();
      }

      const row = indicatorEl.closest('.broken-link-row');
      indicatorEl.remove();
      if(row && !row.querySelector('.broken-link-indicator')) row.remove();
    }catch(e){
      indicatorEl.insertAdjacentHTML('beforeend', `<span class="relink-error">${t('libraryCheckRelinkFailed', {error: escapeHtml(e.message)})}</span>`);
    }
  }

```

- [ ] **Step 3: Add CSS for the inline error text**

In `dossiary.html`, right after the `.broken-link-indicator{...}` rule added in Task 2, insert:
```css
  .relink-error{ color:var(--red); }
```

- [ ] **Step 4: Add the two remaining i18n keys across all six languages**

Append to the same dense line each language's Task-2 keys sit on, right after `libraryCheckOriginalLabel: '...',`.

English (line 1069) — append:
```
libraryCheckRelinkBtn: 'Re-link…', libraryCheckRelinkFailed: 'Could not re-link: {error}',
```

Spanish (line 1270) — append:
```
libraryCheckRelinkBtn: 'Volver a enlazar…', libraryCheckRelinkFailed: 'No se pudo volver a enlazar: {error}',
```

French (line 1471) — append:
```
libraryCheckRelinkBtn: 'Relier…', libraryCheckRelinkFailed: 'Impossible de relier le fichier : {error}',
```

German (line 1672) — append:
```
libraryCheckRelinkBtn: 'Neu verknüpfen…', libraryCheckRelinkFailed: 'Datei konnte nicht neu verknüpft werden: {error}',
```

Chinese Simplified (line 1873) — append:
```
libraryCheckRelinkBtn: '重新链接…', libraryCheckRelinkFailed: '无法重新链接：{error}',
```

Chinese Traditional (line 2200) — append:
```
libraryCheckRelinkBtn: '重新連結…', libraryCheckRelinkFailed: '無法重新連結：{error}',
```

- [ ] **Step 5: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: PASS.

- [ ] **Step 6: Extend `tests/test_broken_links.py` with re-link scenarios**

Driving a real native file-picker dialog isn't scriptable the same way `showDirectoryPicker()` isn't (see `tests/CLAUDE.md`'s own note on this) — but `triggerRelink()`'s dynamically-created `<input class="relink-file-input">` (from Step 2 above, with its stable class name added specifically for this) IS a real, ordinary `<input type="file">` element sitting in the DOM the moment its button is clicked, so it can be targeted the exact same way this suite's own `#file-input` already is: `page.set_input_files('input.relink-file-input', {...})`, no `expect_file_chooser()`/native-dialog handling needed at all. No new debug hook is needed for any of this — reuse `__DEBUG_getFileHash`/`__DEBUG_getDocPaths`/`__DEBUG_dbRun`/`__DEBUG_loadDocumentsFromDb` from Step 7 above, plus the write-failure-simulating technique `main_backfill_failure()` already establishes in `tests/test_duplicate_detection.py` (monkey-patching a live `FakeFileHandle`'s own `createWritable` — see that function's own comment there for why this works: `getFileHandle()` returns the existing entry from its `_children` map, not a copy, so patching the handle obtained from a test-side call affects the app's own later call to the same path too).

Add these scenarios to `tests/test_broken_links.py`, inside the same `main()` (after the render-check scenarios from Step 8, before `await browser.close()`):

```python
        # === Re-link scenarios ===

        # Doc 1 has been completely fine until now (never touched in the
        # detection scenarios above) -- break its file_path here, to test a
        # genuinely SUCCESSFUL re-link of the non-hash-deriving path (doc 1
        # has a real original_file_path, so file_path is NOT its hash-deriving
        # path) leaves file_hash completely untouched. This is the clean,
        # dedicated version of that check -- the doc 4 scenario further below
        # also re-links a non-hash-deriving path, but that attempt is made to
        # FAIL on purpose (to test the error-handling path instead), so it
        # doesn't exercise a successful "wrong path re-linked, hash unchanged"
        # case on its own.
        doc1_paths = await page.evaluate("window.__DEBUG_getDocPaths(1)")
        await delete_stub_file(doc1_paths['file_path'])
        doc1_hash_before = await page.evaluate("window.__DEBUG_getFileHash(1)")

        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)
        await page.click('.broken-link-row[data-document-id="1"] .relink-btn[data-path-field="file_path"]')
        await page.set_input_files('input.relink-file-input', {
            'name': 'replacement1.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 replacement bytes for doc 1 file_path',
        })
        await page.wait_for_timeout(300)

        print("Doc 1's row is gone after its only broken indicator is fixed:",
              await page.locator('.broken-link-row[data-document-id="1"]').count() == 0)
        doc1_hash_after = await page.evaluate("window.__DEBUG_getFileHash(1)")
        print("Doc 1's file_hash is untouched by a successful re-link of the non-hash-deriving path:",
              doc1_hash_after == doc1_hash_before)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # Doc 2 has file_path broken and NO original_file_path at all (forced
        # NULL the same way doc 5 was) -- so file_path IS its hash-deriving
        # path, and re-linking it should recompute file_hash.
        await page.evaluate("""
            async () => {
                window.__DEBUG_dbRun('UPDATE documents SET original_file_path = NULL WHERE id = ?', [2]);
                await window.__DEBUG_loadDocumentsFromDb();
            }
        """)
        doc2_hash_before = await page.evaluate("window.__DEBUG_getFileHash(2)")

        # Re-open the modal (closed at the end of the doc 1 scenario above) --
        # doc 2/3/4's re-link scenarios below all share this one modal session,
        # since re-linking updates the DOM in place with no need to reopen
        # between them.
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)

        await page.click('.broken-link-row[data-document-id="2"] .relink-btn[data-path-field="file_path"]')
        await page.set_input_files('input.relink-file-input', {
            'name': 'replacement2.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 replacement bytes for doc 2',
        })
        await page.wait_for_timeout(300)

        print("Doc 2's row is gone after its only broken indicator is fixed:",
              await page.locator('.broken-link-row[data-document-id="2"]').count() == 0)
        doc2_hash_after = await page.evaluate("window.__DEBUG_getFileHash(2)")
        print("Doc 2's file_hash was recomputed (file_path was its hash-deriving path, no original):",
              doc2_hash_after is not None and doc2_hash_after != doc2_hash_before)

        doc2_paths = await page.evaluate("window.__DEBUG_getDocPaths(2)")
        written_ok = await page.evaluate("""
            async (relPath) => {
                const parts = relPath.split('/');
                let dir = window.__TEST_ROOT;
                for (let i = 0; i < parts.length - 1; i++) { dir = await dir.getDirectoryHandle(parts[i]); }
                const handle = await dir.getFileHandle(parts[parts.length - 1]);
                const file = await handle.getFile();
                const text = await file.text();
                return text.includes('replacement bytes for doc 2');
            }
        """, doc2_paths['file_path'])
        print("Doc 2's file_path now has the replacement bytes on disk:", written_ok)

        # Doc 3 has original_file_path broken and DOES have an original_file_path
        # at all -- it's the hash-deriving path, so re-linking it recomputes
        # file_hash.
        doc3_hash_before = await page.evaluate("window.__DEBUG_getFileHash(3)")
        await page.click('.broken-link-row[data-document-id="3"] .relink-btn[data-path-field="original_file_path"]')
        await page.set_input_files('input.relink-file-input', {
            'name': 'replacement3.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 replacement bytes for doc 3 original',
        })
        await page.wait_for_timeout(300)
        doc3_hash_after = await page.evaluate("window.__DEBUG_getFileHash(3)")
        print("Doc 3's file_hash WAS recomputed (original_file_path IS its hash-deriving path):",
              doc3_hash_after is not None and doc3_hash_after != doc3_hash_before)

        # Doc 4 still has both paths broken. Re-link its original_file_path
        # first (the hash-deriving path, since it has one) and confirm its
        # file_path indicator ALONE remains, with file_hash now set from the
        # original. Then re-link file_path too, and confirm THAT does NOT
        # change file_hash again, since file_path is not the hash-deriving path
        # for a document that has an original.
        await page.click('.broken-link-row[data-document-id="4"] .relink-btn[data-path-field="original_file_path"]')
        await page.set_input_files('input.relink-file-input', {
            'name': 'replacement4-original.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 replacement bytes for doc 4 original',
        })
        await page.wait_for_timeout(300)
        doc4_hash_after_original = await page.evaluate("window.__DEBUG_getFileHash(4)")
        print("Doc 4's row still exists (file_path is still broken):",
              await page.locator('.broken-link-row[data-document-id="4"]').count() == 1)
        print("Doc 4's original-only indicator is gone, file_path indicator remains:",
              await page.locator('.broken-link-row[data-document-id="4"] .broken-link-indicator[data-path-field="original_file_path"]').count() == 0 and
              await page.locator('.broken-link-row[data-document-id="4"] .broken-link-indicator[data-path-field="file_path"]').count() == 1)

        # Simulate a write failure for doc 4's remaining broken path (file_path)
        # the same live-instance-patching way main_backfill_failure() already
        # does for library.sqlite in test_duplicate_detection.py: pre-create
        # the FakeFileHandle at the exact stored path, then patch its own
        # createWritable() to throw -- the app's later resolveFileHandle(path,
        # true) call for the same path returns this same instance.
        doc4_paths = await page.evaluate("window.__DEBUG_getDocPaths(4)")
        await page.evaluate("""
            async (relPath) => {
                const parts = relPath.split('/');
                let dir = window.__TEST_ROOT;
                for (let i = 0; i < parts.length - 1; i++) { dir = await dir.getDirectoryHandle(parts[i], { create: true }); }
                const handle = await dir.getFileHandle(parts[parts.length - 1], { create: true });
                handle.createWritable = async () => { throw new Error('Simulated disk failure'); };
            }
        """, doc4_paths['file_path'])

        await page.click('.broken-link-row[data-document-id="4"] .relink-btn[data-path-field="file_path"]')
        await page.set_input_files('input.relink-file-input', {
            'name': 'replacement4-file.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 this write will fail',
        })
        await page.wait_for_timeout(300)

        print("After a failed write, doc 4's file_path Re-link button is still present:",
              await page.locator('.broken-link-row[data-document-id="4"] .relink-btn[data-path-field="file_path"]').count() == 1)
        print("After a failed write, an inline error is shown:",
              await page.locator('.broken-link-row[data-document-id="4"] .relink-error').count() == 1)
        doc4_hash_after_failed_write = await page.evaluate("window.__DEBUG_getFileHash(4)")
        print("A failed write does not touch file_hash:", doc4_hash_after_failed_write == doc4_hash_after_original)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)
```

- [ ] **Step 7: Run the extended test**

Run: `cd tests && python3 test_broken_links.py`
Expected: PASS, all checks green including the new re-link scenarios.

- [ ] **Step 8: Run the full duplicate-detection suite again**

Run: `cd tests && python3 test_duplicate_detection.py`
Expected: PASS — confirms the new re-link button/wiring doesn't interfere with the existing duplicate-row click-through behavior (the `.duplicate-row` click listener must still fire correctly for plain duplicate-group rows, which have no `.broken-link-indicators` span at all).

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_broken_links.py
git commit -m "$(cat <<'EOF'
Add re-link action for broken file links

Picks a replacement file via a native file picker and writes its
bytes directly into the document's exact existing stored path -- no
database path changes. Recomputes file_hash only when the repaired
path is the one it was derived from, matching the fallback rule
backfillFileHash() already uses.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```

---

### Task 4: Document the feature in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing code-level — this is a documentation-only task.
- Produces: an updated architecture note for future readers of `CLAUDE.md`.

- [ ] **Step 1: Add a "Broken file links" architecture note**

In `CLAUDE.md`, immediately after the existing note about duplicate detection would sit chronologically (search for the most recently added feature note in the "Architecture notes" section — likely near wherever the Reports drill-down or duplicate-detection note currently ends, since this repo's convention is to append new feature notes at the end of that section in shipping order), add a new note following this repo's established voice and level of detail (see any existing note, e.g. the Reminder-type custom fields note, for the expected depth — rationale, exact function/id names, what's deliberately NOT covered, and any real bugs caught during the build):

```markdown
- **The "Find duplicates" modal was renamed to "Library check"
  (`#library-check-btn`, `openLibraryCheckModal()`)** and gained a third,
  persistence-free section: broken file links. `computeBrokenFileLinks(docs)`
  checks every non-deleted document's set `file_path`/`original_file_path`
  via `resolveFileHandle(path, false)`, catching any error (not narrowly
  `NotFoundError`) — unlike the exact-hash duplicate check's `file_hash`,
  this needs no persisted state and no lazy backfill, since an existence
  check never reads a file's bytes; it runs fresh on every modal open. A
  `NULL` path was simply never given one and is never flagged — only a path
  that's actually *set* but fails to resolve counts as broken. Archived and
  needs-review documents are included (same "tells the truth about the
  whole non-deleted library" reasoning duplicate detection's own checks
  already use); only `deleted` documents are excluded.
  **Only the button/modal-open-function/three directly-associated i18n keys
  were renamed** (`toolbarFindDuplicates`→`toolbarLibraryCheck`,
  `duplicatesModalTitle`→`libraryCheckModalTitle`,
  `duplicatesNoneFound`→`libraryCheckNoneFound`, now covering all three
  sections' combined empty state) — the internal DOM ids/classes/i18n keys
  specific to the duplicate-checking sections (`#duplicates-list`,
  `#duplicates-progress`, `.duplicate-group`, `duplicatesBackfillProgress`,
  `duplicatesExactMatchLabel`, `duplicatesMetadataMatchLabel`, and the
  `findDuplicatesBackfillRunning` variable/its own debug hook) are
  deliberately unchanged, since they still describe exactly what they did
  before.
  **Each broken document renders its own row** (`.broken-link-row`, reusing
  `.duplicate-row`'s own click-to-detail-panel wiring for free — its
  `.broken-link-indicators` span stops click propagation, the same
  `onclick="event.stopPropagation()"` pattern the Reminders modal's own
  `.reminder-snooze` wrapper already uses, so clicking "Re-link…" doesn't
  also open the detail panel), showing independent "File"/"Original"
  indicators only for whichever path(s) actually failed to resolve.
  **Re-linking** (`triggerRelink()`/`performRelink()`) opens a plain,
  dynamically-created `<input type="file" accept="application/pdf,image/*">`
  per click — the same accept restriction the capture form's own
  `#file-input` uses, but a fresh element each time rather than a shared
  static one, since each click needs to carry which document and which path
  field it's repairing. The picked file's bytes are written directly into
  the document's **exact existing stored path** via
  `resolveFileHandle(path, true)` (creating whatever directories/file are
  missing) — no database path or row changes at all, since the path itself
  was already correct; only the missing file at it is restored. **Hash
  correctness**: if the just-repaired path is the one `file_hash` was
  derived from — `original_file_path` when the document has one, otherwise
  `file_path`, the same fallback rule `backfillFileHash()` already uses —
  the hash is recomputed via the existing `computeFileHash()` helper and
  persisted (`UPDATE documents SET file_hash = ? WHERE id = ?`); re-linking
  the *other* path leaves `file_hash` untouched, since it was never derived
  from that path. A successful re-link removes just that one indicator from
  the DOM in place (or the whole row, if it was the document's only broken
  one) — no full re-scan of the other two sections, since nothing about
  duplicate grouping changed. A failed write (permission revoked mid-session,
  disk full) is caught and shown as an inline `.relink-error` next to the
  still-present Re-link button, clearing any earlier error on retry, so
  nothing silently looks fixed when it isn't.
```

- [ ] **Step 2: Verify the new note reads correctly in context**

Read the surrounding paragraphs in `CLAUDE.md` once the insertion is made, confirming the new note doesn't duplicate or contradict anything already said about `resolveFileHandle()`, `computeFileHash()`, or the duplicate-detection feature, and that it's inserted in shipping-chronological order relative to its neighbors.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document the Library check rename and broken-file-links feature

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```
