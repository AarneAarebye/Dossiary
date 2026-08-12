# Inbox Auto-Add Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Skip the Inbox review modal — both the toolbar's "Check inbox" button and the inbox banner's own button add every currently-staged file directly as a needs-review document, with no intermediate confirmation click.

**Architecture:** `checkInbox()` keeps its exact current contract (scans `inbox/`, never writes, runs automatically once per library-open or on an explicit `#inbox-check-btn` click). A new shared function, `addAllInboxFilesAndShowStatus()`, wraps the existing `addAllInboxFiles()`/`addInboxFile()` write logic (unchanged) with navigation to the Inbox nav view and a status-line summary, and becomes the click target for both entry points. `openInboxModal()` and `renderInboxList()` are deleted as dead code once nothing calls them.

**Tech Stack:** Vanilla JS in `dossiary.html` (no build step, no framework). Tests are standalone Playwright/Python scripts in `tests/`, driven against the shared `tests/stub_studio2.js` fake-browser-API stub.

## Global Constraints

- Single file (`dossiary.html`) — no build step, no new `<script src>` dependencies.
- No schema change, no new `settings` keys, no new SQL.
- `addInboxFile()`'s per-file defaults are unchanged: filename-derived title, `document_type` prefilled from `default_document_type` if configured, `needs_review = 1`, `source = 'scan-inbox'`, category/subcategory/payment/amount/date/notes left `NULL`, no automatic OCR.
- No per-file selective add from either entry point — both always add everything currently staged (see spec's Non-goals).
- Tests use the shared `tests/stub_studio2.js` stub (never an embedded copy) and the existing `window.__makeEmptyRoot()`/`window.__addInboxFile()` test helpers — both are pure fake-filesystem helpers, untouched by this change.
- CLAUDE.md's Inbox architecture note must be updated in the same change (per this repo's own stated convention of never letting that note silently drift from the code).

---

## Task 1: Skip the Inbox review modal — auto-add on click

**Files:**
- Modify: `dossiary.html:518` (toolbar button — no markup change, only its click wiring changes, further down the file)
- Modify: `dossiary.html:527-529` (inbox banner markup)
- Modify: `dossiary.html:4220-4269` (delete `openInboxModal()` and `renderInboxList()`)
- Modify: `dossiary.html:4280-4346` (`addInboxFile()` — remove modal-only status handling, add real error reporting)
- Modify: `dossiary.html:4348-4353` (`addAllInboxFiles()` — remove the now-dead `closeModal()` call)
- Modify: `dossiary.html:4364-4373` (replace modal-opening click wiring with the new shared helper + its wiring)
- Modify: `CLAUDE.md:1176-1241` (rewrite the Inbox architecture note)
- Test: `tests/test_inbox.py` (full rewrite)

**Interfaces:**
- Consumes: `checkInbox()`, `pendingInboxFiles` (module-level array), `addInboxFile(name)`, `addAllInboxFiles()`, `setStatus(msg, kind)`, `setView(view)`, `rootDirHandle` — all pre-existing, unchanged signatures.
- Produces: `addAllInboxFilesAndShowStatus()` — no parameters, no return value, `async`. Later code (none in this plan, but future features) can call it as the single entry point for "add everything staged and report what happened."

- [ ] **Step 1: Replace `tests/test_inbox.py` with the new test scenarios**

This test currently exercises the modal (`#inbox-review-btn` opening it, `.inbox-add-one-btn`, `#inbox-add-all-btn` inside the modal, `#modal-close-btn`, `#inbox-refresh-btn`) — all of that is being removed from the app. Replace the whole file:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

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

        # Seed an empty library with two files already waiting in inbox/, mirroring what
        # a watched-folder helper like scan_watch.py would have deposited before the
        # library was ever opened.
        await page.evaluate("""
            () => {
                window.__TEST_ROOT = window.__makeEmptyRoot();
                window.__addInboxFile(window.__TEST_ROOT, 'scan001.pdf');
                window.__addInboxFile(window.__TEST_ROOT, 'scan002.jpg');
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: banner shows the pending count as soon as the library opens ===
        banner_visible = await page.locator('#inbox-banner').is_visible()
        banner_text = await page.locator('#inbox-banner-text').inner_text()
        print("banner visible after open:", banner_visible)
        print("banner text:", banner_text)

        # === Scenario 2: clicking the banner's "Add all" button adds both staged files
        # directly -- no modal ever appears -- lands on the Inbox nav view, and reports
        # the folder + count on the status line ===
        await page.click('#inbox-add-all-btn')
        await page.wait_for_timeout(400)

        modal_present = await page.locator('#modal-backdrop').count()
        print("no modal appeared after Add all:", modal_present == 0)

        current_view_is_inbox = await page.locator('#nav-item-inbox.active').count()
        print("landed on the Inbox nav view:", current_view_is_inbox == 1)

        status_text = await page.locator('#status').inner_text()
        print("status line after Add all:", status_text)
        print("status line names the folder:", 'EmptyLibrary/inbox/' in status_text)
        print("status line names the count:", '2' in status_text)

        banner_visible_after = await page.locator('#inbox-banner').is_visible()
        print("banner hidden once inbox emptied:", not banner_visible_after)

        # The saved documents should carry only the file + a filename-derived title --
        # nothing else assumed -- and land with source 'scan-inbox'.
        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("total documents after Add all:", len(persisted['documents']))
        print("sources:", sorted(d['source'] for d in persisted['documents']))
        doc1 = next(d for d in persisted['documents'] if d['id'] == 1)
        print("doc1:", {k: doc1[k] for k in ['id', 'title', 'category', 'document_type', 'date', 'source', 'file_path']})
        print("inbox-added doc gets a real original_file_path (should not be None):", doc1.get('original_file_path'))
        print("inbox-added doc searchable_pdf_built (should be 0):", doc1.get('searchable_pdf_built'))

        inbox_after_all = await page.evaluate("""
            (async () => {
                const inbox = await window.__TEST_ROOT.getDirectoryHandle('inbox');
                const names = [];
                for await (const [name] of inbox.entries()) names.push(name);
                return names;
            })()
        """)
        print("inbox/ contents after Add all (should be empty):", inbox_after_all)

        files_after_all = await page.evaluate("""
            (async () => {
                const files = await window.__TEST_ROOT.getDirectoryHandle('files');
                const names = [];
                for await (const [name] of files.entries()) names.push(name);
                return names;
            })()
        """)
        print("files/ contents after Add all:", sorted(files_after_all))

        # Both land flagged for review (needs_review=1, see addInboxFile()), so both
        # show in the Inbox nav view, not All Documents, until someone clicks Done --
        # see CLAUDE.md's nav architecture note.
        main_rows_before_done = await page.locator('#doc-tbody tr').count()
        print("All Documents rows before Done (should be 0, both live in Inbox):", main_rows_before_done)
        inbox_row_count = await page.locator('#doc-tbody tr').count()  # already on the Inbox view from above
        print("Inbox view shows both inbox-added docs:", inbox_row_count)

        # Done-ing one of them moves it into All Documents with the inbox-added pill;
        # the other stays in the Inbox queue -- exercises the existing, unchanged
        # toggleNeedsReview() flow, not new code from this change.
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#review-toggle-btn')
        await page.wait_for_timeout(200)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        pill_text = await page.locator('tr[data-id="1"] .pill.captured').inner_text()
        print("table pill for inbox-added doc after Done:", pill_text)

        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        remaining_row_count = await page.locator('tr[data-id="2"]').count()
        print("the other inbox-added doc is still in the Inbox queue:", remaining_row_count)

        # === Scenario 3: reopening the (now-empty) library keeps the banner hidden ===
        # #reload-btn's own click handler calls resetAll() then openLibrary() -- the stub's
        # showDirectoryPicker keeps returning the same __TEST_ROOT, and library.sqlite
        # already exists on it now, so this re-loads straight in without #init-btn.
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        banner_on_reopen = await page.locator('#inbox-banner').is_visible()
        print("banner visible on reopening an already-emptied library:", banner_on_reopen)

        # === Scenario 4: a file staged (e.g. by scan_watch.py) *after* the library was
        # already open doesn't show up on its own -- checkInbox() only runs once, right
        # after the library opens (see afterDbReady()) -- but the always-visible "Check
        # inbox" toolbar button lets someone notice and add it directly, without opening
        # any modal ===
        await page.evaluate("window.__addInboxFile(window.__TEST_ROOT, 'late_arrival.pdf');")
        banner_still_hidden = await page.locator('#inbox-banner').is_visible()
        print("banner still hidden right after a late file is staged (no auto-poll):", not banner_still_hidden)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(400)

        modal_present_after_check = await page.locator('#modal-backdrop').count()
        print("no modal appeared after Check inbox:", modal_present_after_check == 0)

        current_view_is_inbox_after_check = await page.locator('#nav-item-inbox.active').count()
        print("Check inbox landed on the Inbox nav view:", current_view_is_inbox_after_check == 1)

        status_after_check = await page.locator('#status').inner_text()
        print("status line after Check inbox found the late file:", status_after_check)

        late_doc_row = await page.locator('tr[data-id="3"]').count()
        print("late-arriving file was added directly:", late_doc_row == 1)

        # === Scenario 5: clicking "Check inbox" when nothing is staged reports that on
        # the status line and does not navigate anywhere ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(300)

        status_when_empty = await page.locator('#status').inner_text()
        print("status line when inbox is empty:", status_when_empty)

        stayed_on_all = await page.locator('#nav-item-all.active').count()
        print("stayed on All Documents (no navigation for a no-op):", stayed_on_all == 1)

        print("JS errors:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run the test to verify it fails against the current (unmodified) app**

Run: `cd tests && python3 test_inbox.py`

Expected: FAIL/incorrect output on multiple lines — `#inbox-add-all-btn` doesn't exist yet outside the modal (the click will error or hit nothing, since today that id only exists inside `openInboxModal()`'s markup, which isn't open), so `"no modal appeared after Add all: True"` will actually show a modal did appear once the code tries to proceed (or the click itself will throw because the banner still has `#inbox-review-btn`, not `#inbox-add-all-btn`, so `page.click('#inbox-add-all-btn')` will timeout/error since nothing with that id exists on the page yet). Confirm the run does NOT cleanly print the full expected sequence above — this is the "red" step proving the test exercises not-yet-built behavior.

- [ ] **Step 3: Update the inbox banner markup**

In `dossiary.html`, find:

```html
      <div class="inbox-banner" id="inbox-banner" style="display:none;">
        <span id="inbox-banner-text"></span>
        <button class="accent" id="inbox-review-btn">Review</button>
      </div>
```

Replace with:

```html
      <div class="inbox-banner" id="inbox-banner" style="display:none;">
        <span id="inbox-banner-text"></span>
        <button class="accent" id="inbox-add-all-btn">Add all</button>
      </div>
```

(The id `inbox-add-all-btn` is safe to reuse here — the modal element that currently owns that id is deleted in Step 4, in the same change.)

- [ ] **Step 4: Delete `openInboxModal()` and `renderInboxList()`**

In `dossiary.html`, find and delete this entire block (from `function openInboxModal(){` through the end of `renderInboxList()`, currently around lines 4220-4269):

```js
  function openInboxModal(){
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal wide" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="Close">✕</button>
          <h2>Inbox</h2>
          <p style="font-family:var(--font-mono); font-size:11.5px; color:var(--text-dim); margin-top:-8px;">
            Files dropped into this library's <code>inbox/</code> folder (e.g. by a watched-folder scan
            helper) — add each with default values, then fill in the rest from its Edit dialog.
          </p>
          <p style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-top:-8px;">
            Folder: <code>${escapeHtml(rootDirHandle.name)}/inbox/</code>
          </p>
          <div id="inbox-list"></div>
          <div class="modal-actions">
            <button class="accent" id="inbox-add-all-btn">Add all with defaults</button>
            <button id="inbox-refresh-btn">Refresh</button>
          </div>
          <div class="status" id="inbox-status" style="padding:10px 0 0;"></div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
    el('inbox-refresh-btn').addEventListener('click', async () => { await checkInbox(); openInboxModal(); });
    el('inbox-add-all-btn').addEventListener('click', addAllInboxFiles);
    renderInboxList();
  }

  function renderInboxList(){
    const listEl = el('inbox-list');
    if(!listEl) return;
    if(!pendingInboxFiles.length){
      listEl.innerHTML = `<p style="font-family:var(--font-mono); font-size:12px; color:var(--text-dim);">Nothing waiting.</p>`;
      el('inbox-add-all-btn').disabled = true;
      return;
    }
    el('inbox-add-all-btn').disabled = false;
    listEl.innerHTML = pendingInboxFiles.map(f => `
      <div class="file-preview">
        <div class="file-icon">${escapeHtml((f.name.split('.').pop() || '').toUpperCase())}</div>
        <div style="flex:1;"><div class="doc-title">${escapeHtml(f.name)}</div></div>
        <button class="inbox-add-one-btn" data-name="${escapeHtml(f.name)}">Add</button>
      </div>
    `).join('');
    listEl.querySelectorAll('.inbox-add-one-btn').forEach(btn => {
      btn.addEventListener('click', () => addInboxFile(btn.dataset.name));
    });
  }
```

Leave the comment block immediately above this (the one starting `// Adds one inbox file as a new document...`, right before `async function addInboxFile(name){`) exactly where it is — it documents `addInboxFile()`, not the modal, and stays accurate.

- [ ] **Step 5: Remove `addInboxFile()`'s modal-only status handling, add real error reporting**

`addInboxFile()` currently references two modal-only things that no longer exist after Step 4: a local `statusEl` pointing at `#inbox-status`, and a call to `renderInboxList()`. The `renderInboxList()` call is not guarded by any existence check — calling it will throw `renderInboxList is not defined` once Step 4 deletes that function, which the surrounding `try/catch` would silently swallow and misreport as a failed add (even though the document was actually saved moments earlier). Remove both, and add a real `setStatus(..., 'err')` call in the catch block so a failed add is still visible now that the modal's own error line is gone.

Find:

```js
  async function addInboxFile(name){
    const entry = pendingInboxFiles.find(f => f.name === name);
    if(!entry) return;
    const statusEl = el('inbox-status');
    if(statusEl){ statusEl.className = 'status busy'; statusEl.innerHTML = `<span class="spinner"></span> Adding "${escapeHtml(name)}"…`; }
    let id;
    try{
```

Replace with:

```js
  async function addInboxFile(name){
    const entry = pendingInboxFiles.find(f => f.name === name);
    if(!entry) return;
    let id;
    try{
```

Find (still inside `addInboxFile()`, a bit further down):

```js
      renderStats(); populateFilters(); populateDatalists(); render();
      subLabel.textContent = rootDirHandle.name;
      updateInboxBanner();
      renderInboxList();
      if(statusEl){ statusEl.className = 'status ok'; statusEl.textContent = `Added "${title}" as #${id}.`; }
      setStatus(`Added "${title || 'Document #' + id}" as #${id} from the inbox.`, 'ok');
    }catch(e){
      if(id !== undefined) nextDocId--; // roll back the reservation since the add didn't complete
      if(statusEl){ statusEl.className = 'status err'; statusEl.textContent = `Failed to add "${name}": ${e.message}`; }
    }
  }
```

Replace with:

```js
      renderStats(); populateFilters(); populateDatalists(); render();
      subLabel.textContent = rootDirHandle.name;
      updateInboxBanner();
      setStatus(`Added "${title || 'Document #' + id}" as #${id} from the inbox.`, 'ok');
    }catch(e){
      if(id !== undefined) nextDocId--; // roll back the reservation since the add didn't complete
      setStatus(`Failed to add "${name}": ${e.message}`, 'err');
    }
  }
```

- [ ] **Step 6: Remove the now-dead `closeModal()` call in `addAllInboxFiles()`**

Find:

```js
  async function addAllInboxFiles(){
    for(const name of pendingInboxFiles.map(f => f.name)){
      await addInboxFile(name);
    }
    if(!pendingInboxFiles.length) closeModal();
  }
```

Replace with:

```js
  async function addAllInboxFiles(){
    for(const name of pendingInboxFiles.map(f => f.name)){
      await addInboxFile(name);
    }
  }
```

- [ ] **Step 7: Add the shared helper and rewire both entry points**

Find:

```js
  el('inbox-review-btn').addEventListener('click', openInboxModal);
  // Always-visible toolbar entry point to checkInbox() -- the banner above only
  // reflects whatever checkInbox() found the one time it runs automatically
  // (right after a library opens, see afterDbReady()), and the Inbox modal's own
  // "Refresh" button is only reachable through that same banner. Without this,
  // there was no way to notice files a watched-folder helper (e.g. scan_watch.py)
  // staged *after* the library was already open, short of fully reopening it.
  // Still a single explicit click, not automatic polling -- keeps the same
  // "no silent writes" principle as everything else in this app.
  el('inbox-check-btn').addEventListener('click', async () => { await checkInbox(); openInboxModal(); });
```

Replace with:

```js
  // Adds every currently-staged inbox file directly (no review step -- see
  // CLAUDE.md's Inbox note for why the modal that used to sit here was removed),
  // jumps to the Inbox nav view so the newly needs-review-flagged documents are
  // immediately visible, and reports what happened via the status line. A count
  // of zero (nothing staged) reports that instead of navigating anywhere, since
  // there's nothing new to look at.
  async function addAllInboxFilesAndShowStatus(){
    const count = pendingInboxFiles.length;
    const folderLabel = `${rootDirHandle.name}/inbox/`;
    if(!count){
      setStatus(`No files waiting in ${folderLabel}.`, 'ok');
      return;
    }
    await addAllInboxFiles();
    setView('inbox');
    setStatus(`Added ${count} document${count === 1 ? '' : 's'} to the review queue from ${folderLabel}.`, 'ok');
  }

  el('inbox-add-all-btn').addEventListener('click', addAllInboxFilesAndShowStatus);
  // Always-visible toolbar entry point to checkInbox() -- the banner above only
  // reflects whatever checkInbox() found the one time it runs automatically
  // (right after a library opens, see afterDbReady()). Without this, there was
  // no way to notice files a watched-folder helper (e.g. scan_watch.py) staged
  // *after* the library was already open, short of fully reopening it. Still a
  // single explicit click, not automatic polling -- keeps the same "no silent
  // writes" principle as everything else in this app.
  el('inbox-check-btn').addEventListener('click', async () => { await checkInbox(); await addAllInboxFilesAndShowStatus(); });
```

- [ ] **Step 8: Run the test again to verify it passes**

Run: `cd tests && python3 test_inbox.py`

Expected: every printed line reflects success — `no modal appeared after Add all: True`, `landed on the Inbox nav view: True`, `status line names the folder: True`, `status line names the count: True`, `banner hidden once inbox emptied: True`, `total documents after Add all: 2`, `sources: ['scan-inbox', 'scan-inbox']`, doc1 fields matching (`category: None`, `document_type: None` since no `default_document_type` was configured in this seed, `date: None`, `source: 'scan-inbox'`), `original_file_path` not `None`, `searchable_pdf_built: 0`, `inbox/ contents after Add all (should be empty): []`, `files/ contents after Add all` listing both moved files, `All Documents rows before Done (should be 0, both live in Inbox): 0`, `Inbox view shows both inbox-added docs: 2`, the Done flow's pill text, `the other inbox-added doc is still in the Inbox queue: 1`, `banner visible on reopening an already-emptied library: False`, `banner still hidden right after a late file is staged (no auto-poll): True`, `no modal appeared after Check inbox: True`, `Check inbox landed on the Inbox nav view: True`, a status line mentioning the late file's addition, `late-arriving file was added directly: True`, `status line when inbox is empty` mentioning "No files waiting", `stayed on All Documents (no navigation for a no-op): True`, and `JS errors: []`.

- [ ] **Step 9: Update CLAUDE.md's Inbox architecture note**

Find the existing Inbox bullet (currently `CLAUDE.md:1176-1241`, starting `- **Inbox** (\`checkInbox()\`, \`openInboxModal()\`, \`addInboxFile()\`,` and ending `...especially with more than one library folder in play.` right before the `- **scan_watch.py** is the other half of Inbox...` bullet). Replace the entire bullet with:

```markdown
- **Inbox** (`checkInbox()`, `addInboxFile()`, `addAllInboxFiles()`,
  `addAllInboxFilesAndShowStatus()`, the `#inbox-banner` element) reads a
  library's `inbox/` folder (a sibling of `library.sqlite` and `files/` at
  the library root) and adds everything currently staged there directly,
  with no per-file review step — mirroring legacy Mariner Paperless's own
  ScanSnap watch-folder integration (a scanned file showing up already
  filed, with the rest of the metadata left for later cleanup), but
  deliberately split into two pieces rather than a single background
  auto-import, for two reasons documented in more detail in "Working
  conventions" below: (1) this app is meant to be the library's sole
  writer to `library.sqlite` — it loads the whole database into memory
  and only writes it back out on an explicit save, so a second process
  inserting rows directly risks silently losing work to whichever side
  saved last; (2) every write is supposed to come from an explicit click,
  never from data that just showed up on disk. So `inbox/` is populated by
  something else entirely outside this file (see `scan_watch.py` below,
  though nothing stops a person from just dragging a file into that folder
  by hand — **the folder itself is created for you** by both
  `initNewLibrary()` and `openLibrary()`'s existing-library path, right
  alongside the equivalent `files/` call; a real gap reported against an
  earlier version of this app, since `checkInbox()`'s own `getDirectoryHandle('inbox',
  { create: false })` deliberately never creates it — that's correct for
  *checking* (a missing folder just means "nothing to add, not an
  error"), but nothing else ever brought it into existence either, so a
  person couldn't actually drag a file in by hand, or point
  `scan_watch.py`'s `--drop-folder` at it directly, without first manually
  creating it in Finder/Explorer/their file manager. Creating an empty
  folder here doesn't conflict with the "no silent writes" principle
  below — no data is written, it's the same "ensure the expected
  structure exists" role `files/`'s own `{ create: true }` already plays)
  and this app never watches or polls it — `checkInbox()` only runs once,
  right after `afterDbReady()`, or when the toolbar's always-visible
  **"📥 Check inbox" button** (`#inbox-check-btn`) is clicked. That toolbar
  button exists specifically because the automatic once-at-open call is
  the *only* other thing that ever triggers a scan — a file a
  watched-folder helper (e.g. `scan_watch.py`) stages *after* someone
  already has the library open in their browser (the normal way people
  actually use it — leaving the tab open while scanning throughout the
  day) would have no visible way to be noticed short of fully reopening
  the library. This is still a single explicit click, not automatic
  polling — same "no silent writes" principle as everything else in this
  section.

  **Both entry points add everything staged, immediately, with no
  intermediate review step** — clicking `#inbox-check-btn` (after its own
  fresh `checkInbox()` scan) or the banner's own `#inbox-add-all-btn`
  ("Add all") both call the same `addAllInboxFilesAndShowStatus()`, which
  adds every currently-staged file via `addAllInboxFiles()`/`addInboxFile()`,
  jumps to the 🚩 Inbox nav view so the newly needs-review-flagged
  documents are immediately visible, and reports what happened on the
  status line (`"Added N document(s) to the review queue from
  <folder>/inbox/."`); a `checkInbox()` scan that finds nothing staged
  reports `"No files waiting in <folder>/inbox/."` on the status line
  instead, without navigating anywhere — there's nothing new to look at.
  This intentionally removed what used to be a review modal
  (`openInboxModal()`, listing each staged file with its own "Add" button
  plus an "Add all with defaults" button) — that extra confirmation step
  existed specifically so nothing got written without a person looking at
  it first, but now that the Waste bin (see its own note above) gives
  every write a safe, fully reversible undo path, it stopped pulling its
  weight: the click on "Check inbox" or "Add all" is already the explicit
  gesture that satisfies principle (2) above, a second confirming click on
  top of it was redundant. An inbox-added document gets
  `source = 'scan-inbox'` (distinct from `'captured'` and `'migrated'`)
  and only two things set beyond the file itself: a filename-derived
  title, and `document_type` prefilled from `default_document_type` if
  one's configured (same intent as the capture form's own default-type
  prefill) — category, subcategory, payment method, amount, date, and
  notes are all left `NULL` rather than guessed, and no OCR runs
  automatically (that stays an explicit action from the Edit dialog's
  existing `runOcrForEdit()`, so a bulk add doesn't silently kick off a
  slow OCR pass per file). This mirrors `saveNewDocument()`'s file-copy/
  thumbnail/sidecar logic closely but isn't a shared function with it,
  since the two have different inputs (a form's DOM fields vs. nothing but
  a filename) and different defaults for nearly every column. The folder
  being read from is surfaced in the status-line message itself now
  (`${rootDirHandle.name}/inbox/`, plain text, not a link — the File
  System Access API exposes no absolute filesystem path for a
  `FileSystemDirectoryHandle`, only its own name, and there's no API to
  launch a native file manager from a browser tab, so this is
  deliberately as far as it can go) rather than a dedicated modal line,
  since there's no modal anymore; still useful to confirm at a glance that
  `scan_watch.py --library` is pointed at the folder you expect,
  especially with more than one library folder in play.
```

- [ ] **Step 10: Run the full regression suite**

Run each test script from `tests/` (52 files total before this change; still 52 after — no test file added or removed, `test_inbox.py` is rewritten in place):

```bash
cd tests
for f in test_*.py; do python3 "$f" > /tmp/out_$f.txt 2>&1 || echo "FAILED: $f"; done
```

Expected: no `FAILED:` lines. `test_inbox_folder_creation.py` in particular should be untouched by this change (it doesn't reference the modal or either button) — confirm it still passes as a sanity check that folder-creation behavior wasn't disturbed.

- [ ] **Step 11: Commit**

```bash
git add dossiary.html CLAUDE.md tests/test_inbox.py
git commit -m "Skip the Inbox review modal -- both entry points add staged files directly as needs-review documents"
```

---

## Self-Review

**Spec coverage:**
- Toolbar button behavior change (checkInbox → direct add → nav → status) — Steps 7, covered.
- Banner button relabel + behavior change — Steps 3, 7, covered.
- Empty-inbox case (status message, no navigation) — Step 7 (`addAllInboxFilesAndShowStatus()`'s `if(!count)` branch) and asserted in Step 1's Scenario 5, covered.
- Modal + `renderInboxList()` removal as dead code — Step 4, covered.
- `addAllInboxFiles()`'s dead `closeModal()` call — Step 6, covered.
- `addInboxFile()`'s now-dangling `renderInboxList()` call (a real bug if missed, not called out explicitly in the spec's prose but implied by "removed as dead code" — the spec's Error Handling section already anticipates `addInboxFile()`'s existing try/catch, this plan makes the specific dangling-call fix explicit) — Step 5, covered.
- Folder-path transparency line, previously only in the modal — folded into the status-line message (`folderLabel`) — Step 7, covered; this wasn't explicitly spelled out in the spec's own text but follows directly from "don't silently drop existing behavior" and the spec's own emphasis on preserving `addInboxFile()`'s defaults untouched.
- CLAUDE.md update — Step 9, covered.
- Test rewrite covering every scenario the spec's Testing section lists — Step 1, covered.
- `test_inbox_folder_creation.py` needing no changes — confirmed in Step 10.
- Non-goals (no per-file selective add, no OCR/default changes, no `inbox/`-population changes) — nothing in this plan touches any of those.

**Placeholder scan:** No TBD/TODO, no "add appropriate error handling" (Step 5 shows the exact `setStatus` call), no "similar to Task N" (single task, all code is real and complete), no undefined references.

**Type consistency:** `addAllInboxFilesAndShowStatus()` has no parameters and no return value, used identically at both call sites (Step 7). `pendingInboxFiles`, `checkInbox()`, `addAllInboxFiles()`, `addInboxFile()`, `setStatus()`, `setView()`, `rootDirHandle` are all pre-existing and used with their real, current signatures throughout — verified against the actual current file contents, not from memory.
