# Recent Library List Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-click "recent libraries" list to Dossiary's startup screen, backed by `FileSystemDirectoryHandle` objects persisted in IndexedDB.

**Architecture:** A small native-IndexedDB storage layer (`dossiary-app-db` / `recentLibraries` store) records each successfully opened library's directory handle. The empty-state screen renders up to 5 entries above the existing "Open library folder" button; clicking one re-authorizes access via `requestPermission()` and reuses the exact same "open a folder" logic the fresh-picker path already uses, extracted into a shared `proceedWithRootDirHandle(handle)` helper.

**Tech Stack:** Vanilla JS inside `dossiary.html` (no new dependency), native `indexedDB` API, existing Playwright + `tests/stub_studio2.js` test harness.

## Global Constraints

- No new third-party dependency, no build step — this stays inside `dossiary.html` as plain JS (per `CLAUDE.md`'s single-file rule).
- Storage uses the native `indexedDB` API directly — no wrapper library.
- Every existing test file loads `tests/stub_studio2.js`; do not embed a separate copy (per `CLAUDE.md`'s explicit warning about this).
- Design spec is `docs/superpowers/specs/2026-08-08-recent-library-list-design.md` — refer back to it if a task's rationale is unclear.
- Do not bump `APP_VERSION` / `__version__` as part of this work — version bumps happen separately, only when explicitly requested (see `CONTRIBUTING.md`'s release checklist).

---

## Task 1: Storage layer — IndexedDB helpers, `afterDbReady()` hook, and test stub support

**Files:**
- Modify: `dossiary.html` (new functions near `openLibrary()`, one new call in `afterDbReady()`)
- Modify: `tests/stub_studio2.js` (new `FakeIDB*` classes, `window.indexedDB`, three new methods on `FakeDirHandle`)
- Create: `tests/test_recent_libraries.py`

**Interfaces:**
- Produces (used by Task 2): `openRecentLibrariesDb()` → `Promise<FakeIDBDatabase|IDBDatabase>`; `getRecentLibraries()` → `Promise<Array<{id, name, handle, lastOpenedAt}>>`; `recordRecentLibrary(handle)` → `Promise<void>`, fire-and-forget-safe (never throws); `removeRecentLibrary(id)` → `Promise<void>`; `MAX_RECENT_LIBRARIES` constant (`5`).
- Produces (test stub, used by Tasks 1–2 tests): `FakeDirHandle.isSameEntry(other)`, `.queryPermission(desc)`, `.requestPermission(desc)` — see Step 3 below for exact semantics, including the `_forceDenied`/`_forceThrow` test hooks Task 2's error-path tests rely on.
- Consumes: `nowIso()` (`dossiary.html:481`, already exists), `el()` (`dossiary.html:462`, already exists).

Real Chromium's IndexedDB has native support for serializing a real `FileSystemDirectoryHandle`/`FileSystemFileHandle` that preserves its live, callable methods after a round-trip — that native support is exactly what makes this feature possible for real handles, and it requires no special handling in `dossiary.html`. Our test-only `FakeDirHandle`/`FakeFileHandle` classes have no such native support: if the stub used a *real* browser `indexedDB`, a round-trip would silently strip a stored fake handle down to a plain data-only object (structured clone doesn't preserve arbitrary class prototypes), breaking `isSameEntry`/`queryPermission`/`requestPermission`/`getFileHandle` on anything read back out. So `stub_studio2.js` gets its own lightweight, in-memory `indexedDB` fake that stores values **by reference** rather than doing a real structured-clone round-trip — the same in-memory-fake philosophy already used there for the filesystem and sql.js stubs, needed here for the identical underlying reason.

- [ ] **Step 1: Add the FakeIDB shim and new `FakeDirHandle` methods to `tests/stub_studio2.js`**

Add this block right after the existing `FakeDirHandle` class (after line 57, before `window.__makeEmptyRoot = ...` on line 59):

```js
// ---- Fake IndexedDB (in-memory, stores values by reference) ----
// See the comment in the recent-libraries implementation plan for why this
// can't just use the real browser indexedDB: our fake FileSystemDirectoryHandle
// classes would lose their prototype/methods across a real structured-clone
// round-trip, which a real FileSystemDirectoryHandle never does.
window.__FAKE_IDB_DATABASES = window.__FAKE_IDB_DATABASES || new Map();

class FakeIDBRequest {
  constructor() { this.onsuccess = null; this.onerror = null; this.onupgradeneeded = null; this.result = undefined; this.error = null; }
}
class FakeIDBTransaction {
  constructor() { this.oncomplete = null; this.onerror = null; this._pending = 0; this._completed = false; }
  _begin() { this._pending++; }
  _end() { this._pending--; if (this._pending === 0) this._maybeComplete(); }
  _maybeComplete() {
    if (this._completed) return;
    this._completed = true;
    queueMicrotask(() => { if (this.oncomplete) this.oncomplete({ target: this }); });
  }
}
class FakeIDBObjectStore {
  constructor(tx, storeState) { this._tx = tx; this._state = storeState; }
  _run(work) {
    const req = new FakeIDBRequest();
    this._tx._begin();
    queueMicrotask(() => {
      try { req.result = work(); if (req.onsuccess) req.onsuccess({ target: req }); }
      catch (e) { req.error = e; if (req.onerror) req.onerror({ target: req }); }
      this._tx._end();
    });
    return req;
  }
  add(value) {
    return this._run(() => {
      const id = this._state.nextId++;
      this._state.map.set(id, Object.assign({}, value, { [this._state.keyPath]: id }));
      return id;
    });
  }
  put(value) {
    return this._run(() => {
      const id = value[this._state.keyPath] != null ? value[this._state.keyPath] : this._state.nextId++;
      this._state.map.set(id, Object.assign({}, value, { [this._state.keyPath]: id }));
      return id;
    });
  }
  get(id) { return this._run(() => this._state.map.get(id)); }
  getAll() { return this._run(() => Array.from(this._state.map.values())); }
  delete(id) { return this._run(() => { this._state.map.delete(id); }); }
}
class FakeIDBDatabase {
  constructor() { this._stores = new Map(); } // name -> { map, keyPath, nextId }
  createObjectStore(name, opts) {
    this._stores.set(name, { map: new Map(), keyPath: (opts && opts.keyPath) || 'id', nextId: 1 });
    return { name };
  }
  transaction(storeNames) {
    const tx = new FakeIDBTransaction();
    const names = Array.isArray(storeNames) ? storeNames : [storeNames];
    tx.objectStore = (name) => {
      if (!names.includes(name)) throw new Error('Store not in transaction scope: ' + name);
      return new FakeIDBObjectStore(tx, this._stores.get(name));
    };
    return tx;
  }
}
window.indexedDB = {
  open(name) {
    const req = new FakeIDBRequest();
    queueMicrotask(() => {
      let db = window.__FAKE_IDB_DATABASES.get(name);
      const isNew = !db;
      if (isNew) { db = new FakeIDBDatabase(); window.__FAKE_IDB_DATABASES.set(name, db); }
      req.result = db;
      if (isNew && req.onupgradeneeded) req.onupgradeneeded({ target: req });
      if (req.onsuccess) req.onsuccess({ target: req });
    });
    return req;
  },
};
```

Then add these three methods inside the existing `FakeDirHandle` class body (`tests/stub_studio2.js:28-57`), anywhere after the constructor — e.g. right after `getDirectoryHandle`:

```js
  // Real File System Access permission/identity methods -- default to
  // "needs a fresh confirm, then succeeds", matching real Chromium's behavior
  // for a handle restored after a session gap. Tests force a failure path by
  // setting `_forceDenied = true` or `_forceThrow = 'NotFoundError'` (or any
  // DOMException name) directly on the handle object before triggering a
  // reconnect click.
  async isSameEntry(other) { return this === other; }
  async queryPermission(desc) { return this._forceDenied ? 'denied' : 'prompt'; }
  async requestPermission(desc) {
    if (this._forceThrow) { const e = new Error('Simulated failure'); e.name = this._forceThrow; throw e; }
    return this._forceDenied ? 'denied' : 'granted';
  }
```

- [ ] **Step 2: Add the storage-layer functions to `dossiary.html`**

Insert this block immediately before the `// --- library open / init ---` comment at `dossiary.html:755`:

```js
  // --- recent libraries (startup list) ---
  // FileSystemDirectoryHandle objects are structured-cloneable and can be
  // stored directly in IndexedDB; re-authorizing a stored handle only needs
  // a single click via requestPermission() (a user gesture), not a fresh
  // showDirectoryPicker() dialog. This persists FSA's own handle object, not
  // a localStorage-style workaround around FSA -- see CLAUDE.md's "Recent
  // libraries" note for the fuller reasoning.
  const RECENT_LIBRARIES_DB_NAME = 'dossiary-app-db';
  const RECENT_LIBRARIES_STORE = 'recentLibraries';
  const MAX_RECENT_LIBRARIES = 5;

  function openRecentLibrariesDb(){
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(RECENT_LIBRARIES_DB_NAME, 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore(RECENT_LIBRARIES_STORE, { keyPath: 'id', autoIncrement: true });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async function getRecentLibraries(){
    const idb = await openRecentLibrariesDb();
    return new Promise((resolve, reject) => {
      const req = idb.transaction(RECENT_LIBRARIES_STORE, 'readonly').objectStore(RECENT_LIBRARIES_STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  }

  async function pruneRecentLibraries(){
    const entries = (await getRecentLibraries()).sort((a, b) => b.lastOpenedAt.localeCompare(a.lastOpenedAt));
    if(entries.length <= MAX_RECENT_LIBRARIES) return;
    const idb = await openRecentLibrariesDb();
    const store = idb.transaction(RECENT_LIBRARIES_STORE, 'readwrite').objectStore(RECENT_LIBRARIES_STORE);
    entries.slice(MAX_RECENT_LIBRARIES).forEach(e => store.delete(e.id));
  }

  // Called from afterDbReady() as fire-and-forget, best effort -- same pattern
  // as its neighboring checkInbox() call there. Must never throw into its
  // caller: a stale/unreadable recent-libraries store should never block a
  // library from actually opening.
  async function recordRecentLibrary(handle){
    try{
      const entries = await getRecentLibraries();
      let matchId = null;
      for(const entry of entries){
        // Identity, not name -- a folder can be renamed, and two different
        // folders can share a name.
        if(await handle.isSameEntry(entry.handle)){ matchId = entry.id; break; }
      }
      const idb = await openRecentLibrariesDb();
      await new Promise((resolve, reject) => {
        const store = idb.transaction(RECENT_LIBRARIES_STORE, 'readwrite').objectStore(RECENT_LIBRARIES_STORE);
        const req = matchId != null
          ? store.put({ id: matchId, name: handle.name, handle, lastOpenedAt: nowIso() })
          : store.add({ name: handle.name, handle, lastOpenedAt: nowIso() });
        req.onsuccess = () => resolve();
        req.onerror = () => reject(req.error);
      });
      await pruneRecentLibraries();
    }catch(e){ /* best effort, see comment above */ }
  }

  async function removeRecentLibrary(id){
    const idb = await openRecentLibrariesDb();
    await new Promise((resolve, reject) => {
      const req = idb.transaction(RECENT_LIBRARIES_STORE, 'readwrite').objectStore(RECENT_LIBRARIES_STORE).delete(id);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }

```

- [ ] **Step 3: Wire `recordRecentLibrary()` into `afterDbReady()`**

In `dossiary.html`, change:

```js
  function afterDbReady(){
    emptyState.style.display = 'none';
    initState.style.display = 'none';
    loadDocumentsFromDb();
    setStatus(`Opened ${allDocs.length} documents from ${rootDirHandle.name}.`, 'ok');
    checkInbox(); // fire-and-forget -- best effort, doesn't block the library from opening
  }
```

to:

```js
  function afterDbReady(){
    emptyState.style.display = 'none';
    initState.style.display = 'none';
    loadDocumentsFromDb();
    setStatus(`Opened ${allDocs.length} documents from ${rootDirHandle.name}.`, 'ok');
    checkInbox(); // fire-and-forget -- best effort, doesn't block the library from opening
    recordRecentLibrary(rootDirHandle); // fire-and-forget, same reasoning as checkInbox() above
  }
```

- [ ] **Step 4: Write `tests/test_recent_libraries.py` (storage-layer scenarios only)**

Follow the exact structure of `tests/test_waste_bin.py` (chdir/APP_PATH boilerplate, route stubbing, `add_init_script(stub_js)`). These scenarios read IndexedDB directly (no UI for this yet — that's Task 2), which is enough to exercise Task 1's code before Task 2 exists.

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [], "tags": [], "document_tags": [],
}

async def read_recent_libraries(page):
    return await page.evaluate("""
        (async () => {
            const req = indexedDB.open('dossiary-app-db', 1);
            const idb = await new Promise((resolve, reject) => {
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
            const store = idb.transaction('recentLibraries', 'readonly').objectStore('recentLibraries');
            const all = await new Promise((resolve, reject) => {
                const r = store.getAll();
                r.onsuccess = () => resolve(r.result);
                r.onerror = () => reject(r.error);
            });
            return all.map(e => ({ id: e.id, name: e.name, lastOpenedAt: e.lastOpenedAt }));
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

        # === Scenario 1: opening a library records exactly one entry in IndexedDB ===
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'LibraryA';" % json.dumps(SEED))
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        entries = await read_recent_libraries(page)
        print("one entry recorded after opening LibraryA:", [e['name'] for e in entries])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 5: Run the test and confirm the entry is recorded**

Run: `cd tests && python3 test_recent_libraries.py`
Expected output includes: `one entry recorded after opening LibraryA: ['LibraryA']` and `JS ERRORS: []`. If `JS ERRORS` is non-empty, check the error text — a common mistake at this step is a typo in the `FakeIDBObjectStore`/`FakeIDBDatabase` wiring in Step 1.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/stub_studio2.js tests/test_recent_libraries.py
git commit -m "$(cat <<'EOF'
Add IndexedDB storage layer for a recent-libraries list

Records every successfully opened library's directory handle so it
can be reopened later with a single permission click instead of a
fresh folder picker. Storage-layer only in this commit; the
startup-screen UI that surfaces it comes next.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Startup UI — render, reconnect, remove

**Files:**
- Modify: `dossiary.html` (empty-state HTML, CSS, `openLibrary()` refactor, new render/reconnect/remove wiring)
- Modify: `tests/test_recent_libraries.py` (add UI-driven scenarios)

**Interfaces:**
- Consumes: `getRecentLibraries()`, `recordRecentLibrary()`, `removeRecentLibrary()`, `MAX_RECENT_LIBRARIES` (Task 1); `el()`, `escapeHtml()`, `formatDate()` (`dossiary.html:1679`, pre-existing); `FakeDirHandle.isSameEntry/queryPermission/requestPermission` and `showDirectoryPicker`'s existing `AbortError`-on-unset-`window.__TEST_ROOT` behavior (`tests/stub_studio2.js:61-65`, pre-existing — used to simulate "cancel" and return to the empty-state screen).
- Produces: `proceedWithRootDirHandle(handle)` — the shared "given a granted handle, open it" helper other code may call in the future; `renderRecentLibraries()` — re-populates `#recent-libraries`, safe to call any time the empty-state screen is shown.

- [ ] **Step 1: Add `#recent-libraries` to the empty-state HTML**

In `dossiary.html`, change (around line 268-279):

```html
  <div id="empty-state" class="empty">
    <h2>No library open</h2>
    <p>Open a library folder created by <code>migrate_to_new_library.py</code>, or start a brand new one here.
       Everything happens locally in your browser — nothing is uploaded.</p>
    <button class="primary" id="open-btn">Open library folder</button>
```

to:

```html
  <div id="empty-state" class="empty">
    <h2>No library open</h2>
    <p>Open a library folder created by <code>migrate_to_new_library.py</code>, or start a brand new one here.
       Everything happens locally in your browser — nothing is uploaded.</p>
    <div id="recent-libraries" style="display:none;"></div>
    <button class="primary" id="open-btn">Open library folder</button>
```

(The rest of that `<div id="empty-state">` block — the `.hint` div — is unchanged.)

- [ ] **Step 2: Add CSS for the recent-libraries box and remove button**

Add this block right after the existing `.review-queue-actions{...}` rule (`dossiary.html:119`):

```css
  #recent-libraries{
    text-align:left; margin-bottom:20px; padding:14px 16px;
    border:1px solid var(--line); border-radius:var(--radius);
  }
  #recent-libraries h3{
    font-family:var(--font-mono); font-size:10.5px; text-transform:uppercase; letter-spacing:0.08em;
    color:var(--text-dim); margin:0 0 10px; font-weight:500;
  }
  .recent-lib-remove-btn{
    width:22px; height:22px; padding:0; border:none; background:transparent;
    color:var(--text-dim); font-size:12px; line-height:1; border-radius:50%;
    display:flex; align-items:center; justify-content:center; cursor:pointer;
  }
  .recent-lib-remove-btn:hover{ color:var(--red); background:rgba(224,113,92,0.12); }
```

- [ ] **Step 3: Refactor `openLibrary()` into a shared `proceedWithRootDirHandle()` helper**

In `dossiary.html`, change (`dossiary.html:764-788`):

```js
  async function openLibrary(){
    if(typeof window.showDirectoryPicker !== 'function'){
      setStatus('Your browser does not support the File System Access API. Use Chrome or Edge.', 'err');
      return;
    }
    try{
      setStatus('Opening folder picker…');
      rootDirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
      setStatus('Checking for library.sqlite…');
      try{
        dbFileHandle = await rootDirHandle.getFileHandle('library.sqlite', { create: false });
        filesDirHandle = await rootDirHandle.getDirectoryHandle('files', { create: true });
        await rootDirHandle.getDirectoryHandle('inbox', { create: true }); // ensure it exists so a person can drop a file in by hand, or scan_watch.py's --drop-folder can be pointed here directly, without a manual mkdir first
        await loadDb();
      }catch(e){
        emptyState.style.display = 'none';
        initState.style.display = 'block';
        el('init-message').innerHTML = `No <code>library.sqlite</code> found in "<b>${escapeHtml(rootDirHandle.name)}</b>".`;
        setStatus('');
      }
    }catch(e){
      if(e.name === 'AbortError'){ setStatus('Folder selection cancelled.'); }
      else{ setStatus('Could not open that folder: ' + e.message, 'err'); }
    }
  }
```

to:

```js
  async function openLibrary(){
    if(typeof window.showDirectoryPicker !== 'function'){
      setStatus('Your browser does not support the File System Access API. Use Chrome or Edge.', 'err');
      return;
    }
    try{
      setStatus('Opening folder picker…');
      const handle = await window.showDirectoryPicker({ mode: 'readwrite' });
      await proceedWithRootDirHandle(handle);
    }catch(e){
      if(e.name === 'AbortError'){ setStatus('Folder selection cancelled.'); }
      else{ setStatus('Could not open that folder: ' + e.message, 'err'); }
    }
  }

  // Given an already-granted directory handle (from a fresh showDirectoryPicker()
  // call, or from re-authorizing a stored recent-library handle), check for
  // library.sqlite and proceed -- the one place that knows what "given a folder
  // handle, open it" means.
  async function proceedWithRootDirHandle(handle){
    rootDirHandle = handle;
    setStatus('Checking for library.sqlite…');
    try{
      dbFileHandle = await rootDirHandle.getFileHandle('library.sqlite', { create: false });
      filesDirHandle = await rootDirHandle.getDirectoryHandle('files', { create: true });
      await rootDirHandle.getDirectoryHandle('inbox', { create: true }); // ensure it exists so a person can drop a file in by hand, or scan_watch.py's --drop-folder can be pointed here directly, without a manual mkdir first
      await loadDb();
    }catch(e){
      emptyState.style.display = 'none';
      initState.style.display = 'block';
      el('init-message').innerHTML = `No <code>library.sqlite</code> found in "<b>${escapeHtml(rootDirHandle.name)}</b>".`;
      setStatus('');
    }
  }
```

- [ ] **Step 4: Add `reconnectRecentLibrary()` and `renderRecentLibraries()`**

Add this block right after `removeRecentLibrary()` (end of Task 1's Step 2 block, still inside the `// --- recent libraries ---` section):

```js
  async function reconnectRecentLibrary(id, handle){
    const statusLine = el(`recent-lib-status-${id}`);
    try{
      let perm = await handle.queryPermission({ mode: 'readwrite' });
      if(perm !== 'granted') perm = await handle.requestPermission({ mode: 'readwrite' });
      if(perm !== 'granted'){
        if(statusLine) statusLine.textContent = "Couldn't reopen — access was denied.";
        return;
      }
      await proceedWithRootDirHandle(handle);
    }catch(e){
      if(statusLine) statusLine.textContent = "Couldn't reopen — folder may have moved or access was denied.";
    }
  }

  async function renderRecentLibraries(){
    const container = el('recent-libraries');
    if(!container) return;
    let entries = [];
    try{ entries = await getRecentLibraries(); }catch(e){ entries = []; }
    entries.sort((a, b) => b.lastOpenedAt.localeCompare(a.lastOpenedAt));
    if(!entries.length){ container.innerHTML = ''; container.style.display = 'none'; return; }
    container.style.display = 'block';
    container.innerHTML = `
      <h3>Recent libraries</h3>
      <div id="recent-libraries-list">
        ${entries.map(entry => `
          <div class="review-queue-row" data-id="${entry.id}">
            <div class="file-preview recent-lib-target" data-id="${entry.id}">
              <div class="file-icon">DIR</div>
              <div style="flex:1;">
                <div class="doc-title">${escapeHtml(entry.name)}</div>
                <div class="doc-sub" id="recent-lib-status-${entry.id}">Last opened ${formatDate(entry.lastOpenedAt)}</div>
              </div>
            </div>
            <div class="review-queue-actions">
              <button type="button" class="recent-lib-remove-btn" data-id="${entry.id}" title="Remove" aria-label="Remove ${escapeHtml(entry.name)} from recent libraries">✕</button>
            </div>
          </div>
        `).join('')}
      </div>
    `;
    container.querySelectorAll('.recent-lib-target').forEach(elm => {
      const id = Number(elm.dataset.id);
      const entry = entries.find(e => e.id === id);
      elm.addEventListener('click', () => reconnectRecentLibrary(id, entry.handle));
    });
    container.querySelectorAll('.recent-lib-remove-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        await removeRecentLibrary(Number(btn.dataset.id));
        renderRecentLibraries();
      });
    });
  }
```

- [ ] **Step 5: Call `renderRecentLibraries()` on initial load and after `resetAll()`**

In `dossiary.html`, change the static-wiring line (`dossiary.html:762`):

```js
  el('app-version-label').textContent = `v${APP_VERSION}`;
```

to:

```js
  el('app-version-label').textContent = `v${APP_VERSION}`;
  renderRecentLibraries();
```

And in `resetAll()` (`dossiary.html:835-848`), change the last line:

```js
    subLabel.textContent = 'No library open'; statsEl.innerHTML = ''; setStatus('');
  }
```

to:

```js
    subLabel.textContent = 'No library open'; statsEl.innerHTML = ''; setStatus('');
    renderRecentLibraries();
  }
```

- [ ] **Step 6: Extend `tests/test_recent_libraries.py` with UI scenarios**

Append these scenarios to `main()`, before the final `print("JS ERRORS:", errors)` line. They rely on `window.showDirectoryPicker`'s existing stub behavior: setting `window.__TEST_ROOT = null` before clicking "Switch library" makes the picker throw `AbortError` (already implemented in `tests/stub_studio2.js:61-65`), which leaves the app sitting at the empty-state screen with `#recent-libraries` rendered and stable — exactly what's needed to inspect the list without immediately being carried into re-opening a different folder.

```python
        # === Scenario 2: the recent-libraries list is visible on the startup
        # screen after switching away from LibraryA (simulated "cancel") ===
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")  # "Switch library"
        await page.wait_for_timeout(200)
        row_names = await page.locator('#recent-libraries-list .doc-title').all_inner_texts()
        print("recent-libraries list shows LibraryA:", row_names)

        # === Scenario 3: clicking the row reconnects without a folder-picker
        # call -- straight back into LibraryA ===
        await page.evaluate("window.__TEST_ROOT = null;")  # picker would abort if it were used
        await page.click('.recent-lib-target')
        await page.wait_for_timeout(300)
        empty_state_visible = await page.locator('#empty-state').is_visible()
        print("reconnect succeeded without a picker call, library is open:", not empty_state_visible)

        # === Scenario 4: reopening the same folder again does not create a
        # duplicate entry -- switch away, reopen LibraryA the normal way, check
        # the count stays at 1 and lastOpenedAt moved forward ===
        entries_before = await read_recent_libraries(page)
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'LibraryA';" % json.dumps(SEED))
        # NOTE: this is a *different* FakeDirHandle instance with the same name,
        # not the same object -- isSameEntry() is identity-based, so this should
        # actually add a SECOND entry. To test true dedup we must reopen the
        # exact same handle instance, so instead click the recent-libraries row
        # again (Scenario 3 already proved reconnect works); here just confirm
        # opening a *different* folder that happens to share a name does NOT
        # get merged with the existing entry (dedup is identity-based, not
        # name-based).
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        entries_after_same_name_diff_handle = await read_recent_libraries(page)
        print("a different handle with the same name is NOT merged (identity-based dedup):",
              len(entries_after_same_name_diff_handle) == len(entries_before) + 1)

        # === Scenario 5: 5-entry cap eviction -- open 4 more distinct libraries
        # (6 total now) and confirm the oldest is evicted, exactly 5 remain ===
        for letter in ['C', 'D', 'E', 'F']:
            await page.evaluate("window.__TEST_ROOT = null;")
            await page.click("#reload-btn")
            await page.wait_for_timeout(150)
            await page.evaluate(
                "window.__TEST_ROOT = window.__makeSeededRoot(%s); window.__TEST_ROOT.name = 'Library%s';" % (json.dumps(SEED), letter)
            )
            await page.click("#open-btn")
            await page.wait_for_timeout(250)
        final_entries = await read_recent_libraries(page)
        print("exactly 5 entries remain after opening 6+ distinct libraries:", len(final_entries) == 5)
        print("oldest (first LibraryA) was evicted:", 'LibraryA' not in [e['name'] for e in final_entries])
        print("newest (LibraryF) is present:", 'LibraryF' in [e['name'] for e in final_entries])

        # === Scenario 6: manual removal via the row's own ✕ button ===
        await page.evaluate("window.__TEST_ROOT = null;")
        await page.click("#reload-btn")
        await page.wait_for_timeout(200)
        before_remove = await page.locator('#recent-libraries-list .review-queue-row').count()
        await page.click('.recent-lib-remove-btn >> nth=0')
        await page.wait_for_timeout(200)
        after_remove = await page.locator('#recent-libraries-list .review-queue-row').count()
        print("removing one entry via its own ✕ shrinks the list by exactly one:", after_remove == before_remove - 1)

        # === Scenario 7: a denied/failed reconnect shows an inline error and
        # leaves the entry in the list (does not remove it) ===
        row_count_before_denied = await page.locator('#recent-libraries-list .review-queue-row').count()
        await page.evaluate("""
            (async () => {
                const req = indexedDB.open('dossiary-app-db', 1);
                const idb = await new Promise(r => { req.onsuccess = () => r(req.result); });
                const store = idb.transaction('recentLibraries', 'readonly').objectStore('recentLibraries');
                const all = await new Promise(r => { const rq = store.getAll(); rq.onsuccess = () => r(rq.result); });
                all[0].handle._forceDenied = true;
            })()
        """)
        await page.click('.recent-lib-target >> nth=0')
        await page.wait_for_timeout(200)
        error_text = await page.locator('#recent-libraries-list .doc-sub').first.inner_text()
        print("denied reconnect shows inline error:", error_text)
        row_count_after_denied = await page.locator('#recent-libraries-list .review-queue-row').count()
        print("denied entry stays in the list (not auto-removed):", row_count_after_denied == row_count_before_denied)
        still_on_empty_state = await page.locator('#empty-state').is_visible()
        print("still on the empty-state screen after a denied reconnect:", still_on_empty_state)
```

- [ ] **Step 7: Run the full test and read the output**

Run: `cd tests && python3 test_recent_libraries.py`

Expected: every printed line reads as true/success (e.g. `True`, or a list containing the expected name), and `JS ERRORS: []`. Read each line — this suite prints observations for a human/agent to check, the same convention `test_waste_bin.py` and `test_review_queue.py` use, not a pass/fail assertion framework.

- [ ] **Step 8: Run the full existing suite to check for regressions**

Run: `cd tests && for f in test_*.py; do echo "=== $f ==="; python3 "$f"; done`

Expected: no new `JS ERRORS`, and no existing scenario's printed output changes — the `openLibrary()` refactor in Step 3 must be behavior-preserving for every other test that opens a library via `#open-btn`.

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_recent_libraries.py
git commit -m "$(cat <<'EOF'
Show a recent-libraries list on the startup screen

Clicking an entry re-authorizes its stored directory handle with a
single requestPermission() click and reuses the same open-library
logic as the fresh folder-picker path (openLibrary() is now a thin
wrapper around the shared proceedWithRootDirHandle() helper). Each
entry can be removed manually; denied/failed reconnects show an
inline message and stay in the list rather than being dropped.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `README.de.md`

**Interfaces:** None — documentation only, no code.

- [ ] **Step 1: Replace `CLAUDE.md`'s "No persistence of the folder handle" note**

Change (`CLAUDE.md:1113-1117`):

```markdown
- **No persistence of the folder handle across page reloads.** A person
  re-selects the library folder every session. This is a deliberate,
  accepted limitation (see README), not something to silently work around
  with `localStorage`/`indexedDB` — browser storage APIs beyond what the
  File System Access API itself provides are out of scope here.
```

to:

```markdown
- **Recent libraries** (`renderRecentLibraries()`, `recordRecentLibrary()`,
  `reconnectRecentLibrary()`, `#recent-libraries` on the empty-state screen)
  reverses what an earlier version of this note called an unavoidable
  browser limitation. `FileSystemDirectoryHandle` objects are structured-
  cloneable, so they can be stored directly in IndexedDB (database
  `dossiary-app-db`, object store `recentLibraries`) and later
  re-authorized with a single click via `handle.requestPermission()` — no
  fresh `showDirectoryPicker()` dialog needed, just a user gesture. This is
  still FSA's own handle object being persisted, not a `localStorage`-style
  workaround around FSA. `afterDbReady()` (the single point both
  `loadDb()` and `initNewLibrary()` funnel through) calls
  `recordRecentLibrary(rootDirHandle)` as a fire-and-forget best-effort
  call, same pattern as its neighboring `checkInbox()` call — a failure to
  record history should never block a library from actually opening.
  Dedup uses `handle.isSameEntry()` (folder *identity*, not name — a
  folder can be renamed, and two different folders can share a name), not
  a string comparison; a re-opened library updates its existing entry's
  `lastOpenedAt` rather than creating a duplicate row. Capped at 5 entries,
  oldest evicted first. On by default (matches Finder/Explorer "Recent
  Files" conventions) — a person on a shared computer who doesn't want a
  library remembered removes it via the row's own ✕; there's no separate
  opt-out setting. `openLibrary()`'s original body (given a granted
  handle, check for `library.sqlite` and proceed) is now the shared
  `proceedWithRootDirHandle(handle)` helper, called both from the fresh-
  picker path and from a successful reconnect — so there's exactly one
  place that knows what "given a folder handle, open it" means. Tested via
  `tests/test_recent_libraries.py`; `tests/stub_studio2.js` needed a
  from-scratch in-memory `indexedDB` fake for this (storing values by
  reference, not a real structured-clone round-trip) since a real
  browser's IndexedDB would silently strip our fake `FileSystemDirectoryHandle`
  class down to a plain data object, unlike what happens to a *real* handle.
```

- [ ] **Step 2: Update `CLAUDE.md`'s test-count/coverage paragraph**

Find the sentence in the "How this was tested" section that states the current script count (currently "**46 scripts**" — grep for `46 scripts` to find the exact spot) and bump it to **47**, adding a clause naming `test_recent_libraries.py` and what it covers, in the same style as the other named test files in that paragraph (e.g. "the recent-libraries startup list (`test_recent_libraries.py` — an entry recorded on open, dedup by folder identity rather than name, the 5-entry cap evicting the oldest, one-click reconnect without a fresh folder-picker call, manual removal, and a denied/failed reconnect leaving its entry in place with an inline error)"). Also update the repository-layout comment near the top of `CLAUDE.md` if it states an exact script count.

- [ ] **Step 3: Add a "Recent libraries" bullet to `README.md`'s Features list**

Insert as the first bullet under `## Features` (`README.md:25-27`, right before the existing "Browse" bullet):

```markdown
- **Recent libraries** — the last 5 libraries you've opened show up on the
  startup screen; click one to reopen it with a single permission-confirm
  click, no need to browse to the folder again. This works by storing the
  folder's access handle in your browser's IndexedDB and re-requesting
  permission on it, not by uploading or copying anything — the data itself
  is never touched until you click. Remove an entry with its ✕ (e.g. on a
  shared computer, or a library you're done with) — there's no separate
  setting to turn this off; removing is the opt-out.
```

- [ ] **Step 4: Replace `README.md`'s "Re-select the folder each session" limitation**

Change (`README.md:552-555`):

```markdown
- **Re-select the folder each session.** Browsers don't allow persisting
  direct file-system access across page reloads, so you'll pick the folder
  again each time you open the app. This is a browser constraint, not
  something Dossiary can work around.
```

to:

```markdown
- **Reconnecting a recent library still needs one click.** Browsers won't
  let a page silently regain filesystem access after a reload — even with
  a library remembered in the Recent libraries list (see Features above),
  reopening it takes one explicit click to re-confirm permission. This is
  a browser security requirement, not something Dossiary can skip.
```

- [ ] **Step 5: Mirror both README.md changes into README.de.md**

Insert as the first bullet under `## Funktionen` (`README.de.md:28-30`, right before "Durchsuchen"):

```markdown
- **Zuletzt geöffnete Bibliotheken** — die letzten 5 von Ihnen geöffneten
  Bibliotheken erscheinen auf dem Startbildschirm; klicken Sie auf eine,
  um sie mit einem einzigen Berechtigungsklick erneut zu öffnen, ohne den
  Ordner erneut auswählen zu müssen. Dazu wird das Zugriffs-Handle des
  Ordners in der IndexedDB Ihres Browsers gespeichert und die Berechtigung
  erneut angefragt — es wird nichts hochgeladen oder kopiert, und auf die
  Daten selbst wird erst beim Klick zugegriffen. Entfernen Sie einen
  Eintrag über das ✕ (z. B. auf einem gemeinsam genutzten Computer, oder
  bei einer Bibliothek, die Sie nicht mehr brauchen) — eine separate
  Einstellung zum Deaktivieren gibt es nicht, das Entfernen ist die
  Abmeldung.
```

Change (`README.de.md:625-629`):

```markdown
- **Der Ordner muss jede Sitzung neu ausgewählt werden.** Browser
  erlauben es nicht, direkten Dateisystemzugriff über Seiten-Neuladen
  hinweg zu speichern, daher wählen Sie den Ordner bei jedem Öffnen der
  App erneut aus. Das ist eine Einschränkung des Browsers, kein Punkt,
  den Dossiary umgehen könnte.
```

to:

```markdown
- **Das erneute Verbinden mit einer zuletzt geöffneten Bibliothek braucht
  weiterhin einen Klick.** Browser lassen eine Seite nach einem Neuladen
  nicht stillschweigend wieder auf das Dateisystem zugreifen — selbst mit
  einer in „Zuletzt geöffnete Bibliotheken" gemerkten Bibliothek (siehe
  Funktionen oben) braucht das erneute Öffnen einen expliziten Klick zur
  Bestätigung der Berechtigung. Das ist eine Sicherheitsanforderung des
  Browsers, kein Punkt, den Dossiary umgehen könnte.
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md README.md README.de.md
git commit -m "$(cat <<'EOF'
Document the recent-libraries feature

Replaces the now-inaccurate "no folder handle persistence" claim in
CLAUDE.md and both READMEs' Limitations sections with a description
of what the feature actually does and what still requires a click
(re-authorizing access is a real browser security requirement, not
something this feature works around).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** data model (Task 1 Step 2), dedup via `isSameEntry` (Task 1 Step 2), 5-cap eviction (Task 1 Step 2 `pruneRecentLibraries`, tested Task 2 Step 6 Scenario 5), UI placement above the button (Task 2 Step 1), reconnect flow incl. `queryPermission`→`requestPermission` (Task 2 Step 4, tested Scenario 3), error handling incl. inline message + entry retained (Task 2 Step 4, tested Scenario 7), manual removal (Task 2 Step 4, tested Scenario 6), `proceedWithRootDirHandle` refactor (Task 2 Step 3), docs for `CLAUDE.md`/`README.md`/`README.de.md` (Task 3) — all covered.
- **No CONTRIBUTING.md changes**: confirmed correct — no new CLI flags, no `library.sqlite` schema change (this is browser-side state only), matching the design spec's own "no changes expected" note.
- **No APP_VERSION bump**: intentionally excluded per Global Constraints — a separate, explicitly-requested step per `CONTRIBUTING.md`'s release checklist.
