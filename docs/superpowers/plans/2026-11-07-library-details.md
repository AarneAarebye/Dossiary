# Library title and description Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A library gets an optional title and description, stored in its `settings` table, edited in a "Library details…" dialog or from a pencil on each Recent libraries entry, and shown in the header and the Recent libraries list.

**Architecture:** Two `settings` rows (`library_title`, `library_description`) are read at open and written in one save. The Recent libraries IndexedDB entries cache both (written at open and at save) so the closed-library list can show them. The pencil reconnects the library through the existing `reconnectRecentLibrary()` and then opens the dialog.

**Tech Stack:** `dossiary.html` (single file, vanilla JS, sql.js), Playwright for Python tests with `tests/stub_studio2.js`.

**Spec:** `docs/superpowers/specs/2026-11-07-library-details-design.md` (read it; it is binding).

## Global Constraints

- Single file: all code goes into `dossiary.html`; no build step; no new files besides tests and docs.
- No `window.prompt()`/`alert()`; use the app's modal pattern (`modalRoot`, `closeModal`, `onModalKeydown`).
- Every new string exists in all 7 languages (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`, `hy`); `tests/test_i18n_coverage.py` must pass. The `hy` block uses `key: "value"` with double quotes; the others use single quotes, so avoid apostrophes in them or use the typographic ’. Armenian is unreviewed: say so in the report.
- Names and texts inserted into HTML go through `escapeHtml()`; texts shown through `t('key', {…})`.
- Settings are written like `default_currency`: `INSERT OR REPLACE INTO settings (key, value)` then one `persistDb()`, after `ensureCurrentVersion()`.
- Limits: title 60 characters, description 300; whitespace (including line breaks) collapses to one space; empty means "not set".
- No schema change. A library without these settings behaves as before.
- Run tests from `tests/` with `/usr/local/bin/python3` (the one with Playwright). Commit messages end with the two attribution lines given by the session.

---

### Task 1: Settings, dialog, Tools entry, header

**Files:**
- Modify: `dossiary.html` (Tools menu near line 966; the 7 `STRINGS` blocks; settings loaders near `loadDefaultCurrency()`; `loadDocumentsFromDb()` where `subLabel.textContent = rootDirHandle.name`; `resetAll()`; the open flow where `loadDefaultCurrency()` is called)
- Test: `tests/test_library_details.py` (create)

**Interfaces:**
- Produces: globals `libraryTitle`, `libraryDescription` (strings, `''` when unset); `cleanLibraryText(value, max) -> string`; `libraryDisplayName() -> string` (title or `rootDirHandle.name`); `updateLibraryHeader()`; `loadLibraryDetails()`; `async saveLibraryDetails(title, description) -> boolean` (false when `ensureCurrentVersion()` refuses); `openLibraryDetailsModal()`; button `#library-details-btn`; dialog ids `#library-details-title`, `#library-details-description`, `#library-details-save-btn`, `#library-details-cancel-btn`.
- Task 2 will add the Recent libraries cache by hooking into `saveLibraryDetails()` and the open flow.

String keys and English texts (translate the same meaning in the other six languages, matching each block's vocabulary for "library", "title", "description", "folder"; keep the emoji):

| key | English |
|---|---|
| `toolbarLibraryDetails` | `🏷 Library details…` |
| `libraryDetailsTitle` | `Library details` |
| `libraryDetailsIntro` | `A title and a short note for this library. They are saved in the library, so every device that opens it can show them.` |
| `libraryDetailsTitleLabel` | `Title` |
| `libraryDetailsTitleHint` | `Empty: the folder name “{name}” is shown.` |
| `libraryDetailsDescriptionLabel` | `Description` |
| `libraryDetailsSaved` | `Library details saved.` |
| `recentLibrariesEditDetailsTitle` | `Edit title and description` |
| `recentLibrariesEditDetailsAriaLabel` | `Edit title and description of {name}` |
| `recentLibrariesFolderAndOpened` | `{folder} · Last opened {date}` |

(The last three are used in Task 2; add all ten here so the i18n test sees one consistent set. Unused-key notes from the coverage test about them are expected until Task 2.)

- [ ] **Step 1: Write the failing test.** Create `tests/test_library_details.py` with the same header, route handler and stub setup as `tests/test_recent_libraries.py` (read it for how a seeded library is opened and how switching libraries is driven), then:

```python
async def library(page):
    return await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))")

# scenario 1: Tools has the entry and the dialog opens
await page.click('#tools-btn')
print("Tools has Library details:", await page.locator('#library-details-btn').is_visible())
await page.click('#library-details-btn'); await page.wait_for_timeout(150)
print("The dialog starts empty with the folder-name hint:",
      await page.input_value('#library-details-title') == '' and await page.input_value('#library-details-description') == ''
      and 'Documents' in await page.inner_text('.modal'))   # use the seeded folder name

# scenario 2: save a title and description
await page.fill('#library-details-title', 'Birgit’s papers')
await page.fill('#library-details-description', 'Everything about\nthe house   and car')
await page.click('#library-details-save-btn'); await page.wait_for_timeout(300)
print("The header shows the title:", await page.inner_text('#sub-label') == 'Birgit’s papers')
print("...with the cleaned description as tooltip:", await page.get_attribute('#sub-label', 'title') == 'Everything about the house and car')
s = {r['key']: r['value'] for r in (await library(page))['settings']}
print("Both are stored in settings:", s.get('library_title') == 'Birgit’s papers' and s.get('library_description') == 'Everything about the house and car')
```

Add the remaining spec scenarios 3, 4 and 8: a 100-character title is cut to 60 and a 400-character description to 300; a title of only spaces counts as not set (header shows the folder name, tooltip removed); clearing both brings back the folder name; a library seeded with `library_title`/`library_description` settings (use the seeded-root helper's `settings` table, as other tests do) shows them in the header at open. Finish with `print("No page errors:", not errors, errors)`.

- [ ] **Step 2:** Run `cd tests && /usr/local/bin/python3 test_library_details.py`. Expected: the first print is `False` or the script errors on the missing button.
- [ ] **Step 3: Implement.**
  - Add the button after `#manage-fields-btn`:
    `<button type="button" class="tools-menu-item" role="menuitem" id="library-details-btn" data-i18n="toolbarLibraryDetails">🏷 Library details…</button>`
    and wire it: `el('library-details-btn').addEventListener('click', openLibraryDetailsModal);` next to the other Tools listeners (look at how `storage-stats-btn` is wired and how the Tools menu closes after a click).
  - Add the 10 strings to all 7 blocks.
  - Add near `loadDefaultCurrency()`:
```js
  // A library's own title and description (settings rows), shown in the
  // header and cached in the Recent libraries list. Empty means "not set".
  const LIBRARY_TITLE_MAX = 60, LIBRARY_DESCRIPTION_MAX = 300;
  let libraryTitle = '', libraryDescription = '';
  function cleanLibraryText(value, max){
    return String(value || '').replace(/\s+/g, ' ').trim().slice(0, max).trim();
  }
  function loadLibraryDetails(){
    const read = (key, max) => {
      const rows = queryAll('SELECT value FROM settings WHERE key = ?', [key]).rows;
      return rows.length ? cleanLibraryText(rows[0][0], max) : '';
    };
    libraryTitle = read('library_title', LIBRARY_TITLE_MAX);
    libraryDescription = read('library_description', LIBRARY_DESCRIPTION_MAX);
  }
  function libraryDisplayName(){ return libraryTitle || (rootDirHandle ? rootDirHandle.name : ''); }
  function updateLibraryHeader(){
    subLabel.textContent = libraryDisplayName();
    if(libraryDescription) subLabel.title = libraryDescription; else subLabel.removeAttribute('title');
  }
  async function saveLibraryDetails(title, description){
    if(!await ensureCurrentVersion()) return false;
    libraryTitle = cleanLibraryText(title, LIBRARY_TITLE_MAX);
    libraryDescription = cleanLibraryText(description, LIBRARY_DESCRIPTION_MAX);
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('library_title', ?)", [libraryTitle]);
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('library_description', ?)", [libraryDescription]);
    await persistDb();
    updateLibraryHeader();
    return true;
  }
```
  Check that `queryAll` accepts bind parameters (it is used with `?` elsewhere; if its signature differs, adapt). Call `loadLibraryDetails()` where `loadDefaultCurrency()` is called in the open flow; in `loadDocumentsFromDb()` replace `subLabel.textContent = rootDirHandle.name;` with `updateLibraryHeader();` (make sure `loadLibraryDetails()` ran before it, or call it at the top of `loadDocumentsFromDb()` instead if that is the only order that works); in `resetAll()` (and the other place that sets `subLabel.textContent = t('emptyTitle')`) also `subLabel.removeAttribute('title')` and reset `libraryTitle = libraryDescription = ''`.
  - `openLibraryDetailsModal()`: build the modal like the other small dialogs (e.g. `openStorageStatsModal()` / the import dialog markup): heading, intro, labelled Title `<input type="text" id="library-details-title" maxlength="60">` with the hint line (`t('libraryDetailsTitleHint', {name: rootDirHandle.name})`), labelled Description `<textarea id="library-details-description" maxlength="300" rows="3">`, Save (`primary`) and Cancel buttons; prefill with the current values; Escape/backdrop/close behave as in the other dialogs (`document.addEventListener('keydown', onModalKeydown)`). Save: `if(!await saveLibraryDetails(...)) return; closeModal(); setStatusT('libraryDetailsSaved', {}, 'ok');` (use the status helper the other dialogs use; check its signature).
- [ ] **Step 4:** Run `/usr/local/bin/python3 test_library_details.py` (all `True`), `test_i18n_coverage.py`, `test_tools_menu.py`, `test_recent_libraries.py`. Expected: pass. Take a screenshot of the dialog at 1440 and 390 px width and tidy spacing with existing CSS classes only.
- [ ] **Step 5: Commit.** `git add dossiary.html tests && git commit -m "feat: library title and description in a Library details dialog"`

---

### Task 2: Recent libraries list and the pencil

**Files:**
- Modify: `dossiary.html` (`recordRecentLibrary()` near line 4735, `renderRecentLibraries()` near 4812, `reconnectRecentLibrary()` near 4766, the call `recordRecentLibrary(rootDirHandle)` in the open flow near 5274, the other call near 8776, `saveLibraryDetails()` from Task 1)
- Test: `tests/test_library_details.py`

**Interfaces:**
- Consumes: Task 1 (`libraryTitle`, `libraryDescription`, `saveLibraryDetails`, `openLibraryDetailsModal`, the 10 strings).
- Produces: Recent libraries entries `{id, name, handle, lastOpenedAt, title?, description?}`; `recordRecentLibrary(handle, details)` where `details` is `{title, description}` (omitted = keep what the entry has); `updateRecentLibraryDetails(handle, details)`; `reconnectRecentLibrary(id, handle, opts)` with `opts.afterOpen` called only after the library opened.

- [ ] **Step 1: Write the failing tests** (extend `tests/test_library_details.py`; spec scenarios 5, 6 and 7). Use `test_recent_libraries.py`'s way of putting two libraries into the list and of reconnecting. Scenario 5: after saving details for library A and switching away (`#reload-btn`), the start screen's list shows A's title as the name, the description line, and `Documents.dossiary · Last opened` (use the real folder name) as the status text; library B, never given details, shows its folder name and the plain "Last opened" text. Scenario 6: click `.recent-details-btn` of A: the library opens, `#library-details-title` is present with A's title; change it and save: the library's `settings` and (after switching away again) the list show the new title. Scenario 6b: make the stub's `requestPermission`/`queryPermission` on A's stored handle return `'denied'` and click the pencil: the entry's status text shows the existing denial message, no `#library-details-title` exists, and A's `library.sqlite` is unchanged. Scenario 7: a pencil click opens the library once (count `statusOpenedLibrary` updates or spy `proceedWithRootDirHandle` through the stub's open counter; if no counter exists, assert that the dialog is the only modal and the library is open).
- [ ] **Step 2:** Run it. Expected: the new scenarios fail (no `.recent-details-btn`).
- [ ] **Step 3: Implement.**
  - `recordRecentLibrary(handle, details)`: in both the `put` and the `add`, include `title`/`description` from `details` when given; when `details` is omitted on a `put`, keep the existing entry's values (read the matching entry). At the open flow call `recordRecentLibrary(rootDirHandle, { title: libraryTitle, description: libraryDescription })`. The call near line 8776 (`dest`, a library just made or copied) keeps passing no details.
  - Add:
```js
  // Keeps the cached title/description of a Recent libraries entry current
  // without touching its last-opened date. Best effort, like recordRecentLibrary().
  async function updateRecentLibraryDetails(handle, details){
    try{
      for(const entry of await getRecentLibraries()){
        let same = false;
        try{ same = await handle.isSameEntry(entry.handle); }catch(e){ same = false; }
        if(!same) continue;
        const idb = await openRecentLibrariesDb();
        await new Promise((resolve, reject) => {
          const req = idb.transaction(RECENT_LIBRARIES_STORE, 'readwrite').objectStore(RECENT_LIBRARIES_STORE)
            .put({ ...entry, title: details.title, description: details.description });
          req.onsuccess = () => resolve();
          req.onerror = () => reject(req.error);
        });
        return;
      }
    }catch(e){ /* best effort */ }
  }
```
    and call it at the end of `saveLibraryDetails()` (after `updateLibraryHeader()`): `await updateRecentLibraryDetails(rootDirHandle, { title: libraryTitle, description: libraryDescription });`.
  - `renderRecentLibraries()`: name line `escapeHtml(entry.title || entry.name)`; when `entry.description`, add `<div class="doc-sub recent-lib-description">…</div>` (single line with ellipsis via a small CSS rule using existing variables; the existing `.doc-sub` styles otherwise); the status line text is `t('recentLibrariesFolderAndOpened', {folder: entry.name, date: formatDate(entry.lastOpenedAt)})` when `entry.title` is set, else the existing `recentLibrariesLastOpened` text. Add before the trash button: `<button type="button" class="recent-details-btn" data-id="${entry.id}" title="${t('recentLibrariesEditDetailsTitle')}" aria-label="${t('recentLibrariesEditDetailsAriaLabel', {name: escapeHtml(entry.title || entry.name)})}">✎</button>` and its handler `btn.addEventListener('click', (e) => { e.stopPropagation(); reconnectRecentLibrary(id, entry.handle, { afterOpen: openLibraryDetailsModal }); });` (look at how the trash and remove buttons are placed so the pencil gets the same styling; the row's own click handler is on `.recent-lib-target`, a sibling, so `stopPropagation` is a safeguard).
  - `reconnectRecentLibrary(id, handle, opts = {})`: after `await proceedWithRootDirHandle(handle);` add `if(opts.afterOpen && libraryOpen) opts.afterOpen();` — use whatever flag or check the code has for "a library is now open" (for example `rootDirHandle && db`), not a guess; if `proceedWithRootDirHandle` can return without opening (an error inside it, a sync prompt), the dialog must not open.
- [ ] **Step 4:** Run `/usr/local/bin/python3 test_library_details.py`, `test_recent_libraries.py`, `test_i18n_coverage.py`. Expected: all pass, no page errors. Screenshot the start screen with two entries (one with title and description) at 1440 and 390 px; check nothing overflows.
- [ ] **Step 5: Commit.** `git add dossiary.html tests && git commit -m "feat: show a library's title and description in Recent libraries, edit with a pencil"`

---

### Task 3: Docs, version, full suite

**Files:**
- Modify: `dossiary.html` (`APP_VERSION` → `'1.60.0'`), `scan_watch.py` (`__version__`), `tests/test_scan_watch_version.py`, `README.md` and `README.de.md` (a bullet for Library details), `docs/architecture/07-pdf-originals-libraries-i18n.md` (note under "Recent libraries": the cached `title`/`description`, `updateRecentLibraryDetails`, the pencil reconnect flow) and, if it lists the Tools entries, `docs/architecture/04-navigation-reports-columns.md`, `AGENTS.md` (test count and mentions), `tests/CLAUDE.md` and `tests/coverage/` (list `test_library_details.py`, following how `test_import_collection.py` is listed)

- [ ] **Step 1:** Update the docs and the three version places together (see `.claude/skills/cutting-a-release/SKILL.md`; do not tag, push or release). Count the scripts in `tests/` for the new total.
- [ ] **Step 2:** Run the whole suite as `tests/CLAUDE.md` describes, checking each script's exit status. Report any failure with its output; re-run an unrelated failure once and say so.
- [ ] **Step 3: Commit.** `git add -A && git commit -m "docs: library title and description (1.60.0)"` (leave the untracked `start_last_claude` alone).
