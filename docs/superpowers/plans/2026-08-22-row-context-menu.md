# Row Context Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Right-clicking a table row opens a context menu carrying most of
the detail panel's own document actions, plus a new "Detail" item that
toggles the panel's own expanded/collapsed state.

**Architecture:** `openDetail()`'s action-array-building and per-button
click-wiring logic is extracted into one shared function,
`buildDetailActions(id, d)`, returning plain action descriptors. Both
`openDetail()` (rendering panel buttons) and a new context-menu builder
(rendering menu items) consume the same descriptors, so the two surfaces
can never drift out of sync. A new `contextmenu` listener on each `<tr>`
selects the row exactly like `click` already does, then shows the menu.

**Tech Stack:** Vanilla JS, template-string HTML rendering, Playwright
(`tests/stub_studio2.js` stub harness) — no new dependencies.

## Global Constraints

- Single-file app: all changes stay inside `dossiary.html`.
- Every new user-facing string needs a key in all six `STRINGS` blocks
  (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`) — `tests/test_i18n_coverage.py`
  fails the whole suite otherwise.
- The panel's existing button ids (`#open-file-btn`, `#open-original-btn`,
  `#edit-doc-btn`, `#regen-thumb-btn`, `#archive-toggle-btn`,
  `#review-toggle-btn`, `#add-to-collection-btn`, `#remove-from-collection-btn`,
  `#delete-toggle-btn`) must not change — existing tests reference them
  directly.
- "Regenerate preview" never appears in the context menu — it stays a
  panel-only action.
- The context menu has no presence in Reports view, and doesn't appear
  when right-clicking `.select-col`/`.row-edit-col` cells.
- Clicking any context-menu item closes the menu before that item's own
  action runs.

---

### Task 1: Extract `buildDetailActions()` (pure refactor, no behavior change)

**Files:**
- Modify: `dossiary.html` — `openDetail()` (currently ~lines 4612-4814)

**Interfaces:**
- Produces: `function buildDetailActions(id, d)` → returns
  `Array<{key: string, label: string, variant: 'primary'|'danger'|null, panelOnly?: true, onClick: (e?) => void|Promise<void>}>`.
  Every existing action except "Regenerate preview" gets a descriptor;
  "Regenerate preview" gets one too, but marked `panelOnly: true` so a
  later task's context-menu builder can filter it out — this keeps the
  panel's own rendering simple (render every descriptor, unconditionally,
  exactly as today) while giving the context menu an explicit signal for
  the one action it must never show.

- [ ] **Step 1: Read the current `openDetail()` in full**

Read `dossiary.html` from `async function openDetail(id){` through the
end of that function (currently ~lines 4612-4814) to confirm the exact
current code before editing — line numbers may have drifted slightly
since this plan was written.

- [ ] **Step 2: Add `buildDetailActions()`**

Find the line directly before `async function openDetail(id){` and insert
this new function immediately above it:

```js
  // Shared by openDetail() (rendering panel buttons) and the row context
  // menu (rendering menu items) -- one source of truth for which actions
  // apply to a document right now (deleted-document Restore-only,
  // Add/Remove Collection's view-dependent visibility, etc.) and what each
  // one does, so the two surfaces can't drift out of sync with each other.
  // "Regenerate preview" is the one action marked panelOnly: true -- it's
  // still returned here (so openDetail() needs no special-casing to render
  // it in its usual position), but the context menu filters it out.
  function buildDetailActions(id, d){
    const manualCollections = collections.filter(c => c.kind === 'manual');
    const actions = [];
    if(d.file_path){
      actions.push({
        key: 'open-file', label: t('detailOpenFile'), variant: 'primary',
        onClick: async () => {
          try{
            const fh = await resolveFileHandle(d.file_path, false);
            const file = await fh.getFile();
            window.open(URL.createObjectURL(file), '_blank');
          }catch(e){ alert(t('detailOpenFileError', {error: e.message})); }
        },
      });
    }
    if(d.original_file_path){
      actions.push({
        key: 'open-original', label: t('detailOpenOriginal'), variant: null,
        onClick: async () => {
          try{
            const fh = await resolveFileHandle(d.original_file_path, false);
            const file = await fh.getFile();
            window.open(URL.createObjectURL(file), '_blank');
          }catch(e){ alert(t('detailOpenFileError', {error: e.message})); }
        },
      });
    }
    // A deleted document only offers Restore -- see toggleDeleted()'s own
    // comment for why "deleted" is the strongest of the three staging flags.
    if(!d.deleted){
      actions.push({ key: 'edit', label: t('detailEdit'), variant: null, onClick: () => openEditForm(id) });
      actions.push({
        key: 'regen-thumb', label: d.thumbnail_path ? t('detailRegeneratePreview') : t('detailGeneratePreview'),
        variant: null, panelOnly: true, onClick: () => regenerateThumbnail(id),
      });
      actions.push({
        key: 'archive-toggle', label: d.archived ? t('detailUnarchive') : t('detailArchive'),
        variant: null, onClick: () => toggleArchived(id),
      });
      actions.push({
        key: 'review-toggle', label: d.needs_review ? t('commonDone') : t('bulkFlagForReview'),
        variant: null,
        onClick: async () => { await toggleNeedsReview(id); openDetail(id); },
      });
      if(manualCollections.length){
        actions.push({
          key: 'add-to-collection', label: t('detailAddToCollection'), variant: null,
          // Reads e.target.getBoundingClientRect() synchronously, before any
          // await, to position the collection picker relative to whichever
          // element was actually clicked -- works unchanged whether that's
          // the panel's own button or a context-menu item, as long as the
          // caller hasn't already removed that element from the DOM by the
          // time this runs (see the context-menu builder's own comment on
          // why it calls onClick before removing itself, not after).
          onClick: (e) => {
            e.stopPropagation();
            const menu = document.createElement('div');
            menu.className = 'bulk-collection-menu';
            menu.style.cssText = 'position:absolute; z-index:50;';
            const rect = e.target.getBoundingClientRect();
            menu.style.top = (rect.bottom + window.scrollY + 6) + 'px';
            menu.style.left = (rect.left + window.scrollX) + 'px';
            menu.innerHTML = manualCollections.map(c => `<button type="button" class="modal-collection-option" data-collection-id="${c.id}">${escapeHtml(c.name)}</button>`).join('');
            document.body.appendChild(menu);
            openDocCollectionMenu = menu;
            menu.querySelectorAll('.modal-collection-option').forEach(btn => {
              btn.addEventListener('click', async () => {
                await addDocumentsToCollection(Number(btn.dataset.collectionId), [id]);
                menu.remove();
                if(openDocCollectionMenu === menu) openDocCollectionMenu = null;
                openDetail(id);
              });
            });
            const removeMenu = (evt) => {
              if(!menu.contains(evt.target)){
                menu.remove();
                if(openDocCollectionMenu === menu) openDocCollectionMenu = null;
                document.removeEventListener('click', removeMenu);
              }
            };
            setTimeout(() => document.addEventListener('click', removeMenu), 0);
          },
        });
      }
      if(currentView.startsWith('collection-')){
        const viewedCollection = collections.find(c => c.id === Number(currentView.slice('collection-'.length)));
        if(viewedCollection && viewedCollection.kind === 'manual'){
          actions.push({
            key: 'remove-from-collection', label: t('detailRemoveFromCollection'), variant: null,
            onClick: async () => {
              const collectionId = Number(currentView.slice('collection-'.length));
              db.run('DELETE FROM collection_documents WHERE collection_id = ? AND document_id = ?', [collectionId, id]);
              await persistDb();
              loadCollections();
              closeModal();
              render();
            },
          });
        }
      }
      actions.push({
        key: 'delete-toggle', label: t('commonDelete'), variant: 'danger',
        onClick: async () => { await toggleDeleted(id); openDetail(id); },
      });
    } else {
      actions.push({
        key: 'delete-toggle', label: t('bulkRestore'), variant: 'primary',
        onClick: async () => { await toggleDeleted(id); openDetail(id); },
      });
    }
    return actions;
  }

```

- [ ] **Step 3: Replace `openDetail()`'s own action-array construction**

Find (currently ~lines 4638-4660, inside `openDetail()`, right after the
`if(!d){...return;}` block):

```js
    const actions = [];
    const manualCollections = collections.filter(c => c.kind === 'manual');
    if(d.file_path) actions.push(`<button class="primary" id="open-file-btn">${t('detailOpenFile')}</button>`);
    if(d.original_file_path) actions.push(`<button id="open-original-btn">${t('detailOpenOriginal')}</button>`);
    // A deleted document only offers Restore -- editing, archiving, and flagging a
    // document that's sitting in the waste bin don't make sense (it isn't reachable
    // anywhere those would matter until it's restored), so those buttons are left out
    // entirely rather than shown disabled. See toggleDeleted()'s own comment for why
    // "deleted" is the strongest of the three staging flags.
    if(!d.deleted){
      actions.push(`<button id="edit-doc-btn">${t('detailEdit')}</button>`);
      actions.push(`<button id="regen-thumb-btn">${d.thumbnail_path ? t('detailRegeneratePreview') : t('detailGeneratePreview')}</button>`);
      actions.push(`<button id="archive-toggle-btn">${d.archived ? t('detailUnarchive') : t('detailArchive')}</button>`);
      actions.push(`<button id="review-toggle-btn">${d.needs_review ? t('commonDone') : t('bulkFlagForReview')}</button>`);
      if(manualCollections.length) actions.push(`<button id="add-to-collection-btn">${t('detailAddToCollection')}</button>`);
      if(currentView.startsWith('collection-')){
        const viewedCollection = collections.find(c => c.id === Number(currentView.slice('collection-'.length)));
        if(viewedCollection && viewedCollection.kind === 'manual') actions.push(`<button id="remove-from-collection-btn">${t('detailRemoveFromCollection')}</button>`);
      }
      actions.push(`<button class="danger" id="delete-toggle-btn">${t('commonDelete')}</button>`);
    } else {
      actions.push(`<button class="primary" id="delete-toggle-btn">${t('bulkRestore')}</button>`);
    }
```

Replace with (maps each descriptor to the exact same button HTML the old
code produced — same ids via a `key`→`id` lookup, same `class="primary"`/
`class="danger"`/no-class pattern via `variant`):

```js
    const detailActions = buildDetailActions(id, d);
    const actionIdByKey = {
      'open-file': 'open-file-btn', 'open-original': 'open-original-btn', 'edit': 'edit-doc-btn',
      'regen-thumb': 'regen-thumb-btn', 'archive-toggle': 'archive-toggle-btn', 'review-toggle': 'review-toggle-btn',
      'add-to-collection': 'add-to-collection-btn', 'remove-from-collection': 'remove-from-collection-btn',
      'delete-toggle': 'delete-toggle-btn',
    };
    const actions = detailActions.map(a => {
      const cls = a.variant ? ` class="${a.variant}"` : '';
      return `<button${cls} id="${actionIdByKey[a.key]}">${a.label}</button>`;
    });
```

- [ ] **Step 4: Replace `openDetail()`'s own action-wiring block**

Find (currently ~lines 4741-4813, inside `openDetail()`, after
`panelBody.innerHTML = ...`):

```js
    if(d.file_path){
      el('open-file-btn').addEventListener('click', async () => {
        try{
          const fh = await resolveFileHandle(d.file_path, false);
          const file = await fh.getFile();
          window.open(URL.createObjectURL(file), '_blank');
        }catch(e){ alert(t('detailOpenFileError', {error: e.message})); }
      });
    }
    if(d.original_file_path){
      el('open-original-btn').addEventListener('click', async () => {
        try{
          const fh = await resolveFileHandle(d.original_file_path, false);
          const file = await fh.getFile();
          window.open(URL.createObjectURL(file), '_blank');
        }catch(e){ alert(t('detailOpenFileError', {error: e.message})); }
      });
    }
    if(fileFullPath) el('copy-file-path-btn').addEventListener('click', (e) => copyPathToClipboard(fileFullPath, e.target));
    if(originalFullPath) el('copy-original-path-btn').addEventListener('click', (e) => copyPathToClipboard(originalFullPath, e.target));
    if(!d.deleted){
      el('edit-doc-btn').addEventListener('click', () => openEditForm(id));
      el('regen-thumb-btn').addEventListener('click', () => regenerateThumbnail(id));
      el('archive-toggle-btn').addEventListener('click', () => toggleArchived(id));
      el('review-toggle-btn').addEventListener('click', async () => {
        await toggleNeedsReview(id);
        openDetail(id); // refresh the panel so the button now reads Flag for review/Done correctly
      });
      if(el('add-to-collection-btn')){
        el('add-to-collection-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          const menu = document.createElement('div');
          menu.className = 'bulk-collection-menu';
          menu.style.cssText = 'position:absolute; z-index:50;';
          const rect = e.target.getBoundingClientRect();
          menu.style.top = (rect.bottom + window.scrollY + 6) + 'px';
          menu.style.left = (rect.left + window.scrollX) + 'px';
          menu.innerHTML = manualCollections.map(c => `<button type="button" class="modal-collection-option" data-collection-id="${c.id}">${escapeHtml(c.name)}</button>`).join('');
          document.body.appendChild(menu);
          openDocCollectionMenu = menu;
          menu.querySelectorAll('.modal-collection-option').forEach(btn => {
            btn.addEventListener('click', async () => {
              await addDocumentsToCollection(Number(btn.dataset.collectionId), [id]);
              menu.remove();
              if(openDocCollectionMenu === menu) openDocCollectionMenu = null;
              openDetail(id); // refresh so a newly-relevant Remove action, if any, appears
            });
          });
          const removeMenu = (evt) => {
            if(!menu.contains(evt.target)){
              menu.remove();
              if(openDocCollectionMenu === menu) openDocCollectionMenu = null;
              document.removeEventListener('click', removeMenu);
            }
          };
          setTimeout(() => document.addEventListener('click', removeMenu), 0);
        });
      }
      if(el('remove-from-collection-btn')){
        el('remove-from-collection-btn').addEventListener('click', async () => {
          const collectionId = Number(currentView.slice('collection-'.length));
          db.run('DELETE FROM collection_documents WHERE collection_id = ? AND document_id = ?', [collectionId, id]);
          await persistDb();
          loadCollections();
          closeModal();
          render();
        });
      }
    }
    el('delete-toggle-btn').addEventListener('click', async () => {
      await toggleDeleted(id);
      openDetail(id); // refresh the panel so it now shows Restore-only (or the full action set again)
    });
  }
```

Replace with (every button's click now just calls its own descriptor's
`onClick` — the copy-path buttons aren't part of `buildDetailActions()`
since they're not shared with the context menu, so their wiring is
untouched):

```js
    if(fileFullPath) el('copy-file-path-btn').addEventListener('click', (e) => copyPathToClipboard(fileFullPath, e.target));
    if(originalFullPath) el('copy-original-path-btn').addEventListener('click', (e) => copyPathToClipboard(originalFullPath, e.target));
    detailActions.forEach(a => {
      const btnEl = el(actionIdByKey[a.key]);
      if(btnEl) btnEl.addEventListener('click', a.onClick);
    });
  }
```

(`actionIdByKey` and `detailActions` from Step 3 are both in scope here,
since they're declared earlier in the same `openDetail()` function body.)

- [ ] **Step 5: Manual verification**

This step is a pure refactor with no intended behavior change, so
verification means confirming the panel still looks and behaves
identically. Run the existing detail-panel test file:

```bash
cd tests && /usr/local/bin/python3 test_detail_panel.py
```

Expected: every printed line is `True` (or matches its prior expected
value), `JS ERRORS: []` — identical to before this refactor, since nothing
about the panel's actual behavior should have changed.

- [ ] **Step 6: Full regression run**

Because this refactors the single most central rendering function for the
detail panel — used by every existing test that opens/interacts with a
document's detail — run the entire suite, not just the one file most
directly touched:

```bash
cd tests && for f in test_*.py; do
  echo "=== $f ==="
  /usr/local/bin/python3 "$f" > /tmp/task1-sweep.log 2>&1
  echo "EXIT:$? for $f"
done
```

Expected: every file exits 0, `JS ERRORS: []` everywhere. If anything
fails, it's a real regression from this refactor (the extraction is meant
to be behavior-preserving) — fix it before moving on, don't defer it.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html
git commit -m "Extract buildDetailActions() from openDetail()

Pure refactor: the panel's action-building and click-wiring logic now
lives in one function returning plain descriptors, consumed by
openDetail() to render its existing buttons unchanged. No behavior
change -- this sets up the row context menu (a later task) to reuse the
exact same logic instead of maintaining a second, independent list."
```

---

### Task 2: The context menu itself

**Files:**
- Modify: `dossiary.html` — CSS (near the existing `.bulk-collection-menu`
  rules, currently ~lines 310-320), the row-wiring pass inside `render()`
  (currently ~lines 4385-4410), STRINGS blocks (all six languages)
- Test: `tests/test_detail_panel.py`

**Interfaces:**
- Consumes: `buildDetailActions(id, d)` from Task 1; `detailPanelExpanded`,
  `saveDetailPanelExpanded(value)` (existing, ~line 3089); `selectedDocId`,
  `openDetail(id)` (existing).
- Produces: `let openRowContextMenu = null;` (module state, mirrors the
  existing `let openDocCollectionMenu = null;` pattern) — tracks the
  currently-open context menu so a later feature could clean it up the
  same way `closeModal()` already does for `openDocCollectionMenu`, though
  this task doesn't need to wire that in itself (the context menu removes
  itself on outside click regardless of anything else in the app).

- [ ] **Step 1: Add the CSS**

Find (currently ~lines 310-320):

```css
  .bulk-collection-menu-wrap{ position:relative; }
  .bulk-collection-menu{
    position:absolute; top:calc(100% + 6px); left:0; background:var(--panel); border:1px solid var(--line);
    border-radius:var(--radius); padding:6px; z-index:40; min-width:200px; box-shadow:0 8px 24px rgba(0,0,0,0.4);
  }
  /* .modal-collection-option is the detail panel's own single-document collection
     picker (see openDetail()'s add-to-collection-btn handler) -- identically
     purposed to .bulk-collection-option above, so it shares the exact same list-row
     styling rather than falling through to the plain global button{} rule. */
  .bulk-collection-option, .modal-collection-option{ display:block; width:100%; text-align:left; padding:8px 10px; background:transparent; border:none; color:var(--text); font-family:var(--font-mono); font-size:12.5px; cursor:pointer; border-radius:var(--radius); }
  .bulk-collection-option:hover, .modal-collection-option:hover{ background:rgba(79,224,166,0.1); color:var(--phosphor); }
```

Directly after it, insert (matches the same floating-menu look; unlike
`.bulk-collection-menu` this one is `position:fixed` since it anchors to a
raw click coordinate, not to a button's own `getBoundingClientRect()`):

```css
  .row-context-menu{
    position:fixed; background:var(--panel); border:1px solid var(--line);
    border-radius:var(--radius); padding:6px; z-index:60; min-width:200px; box-shadow:0 8px 24px rgba(0,0,0,0.4);
  }
  .row-context-menu-item{ display:block; width:100%; text-align:left; padding:8px 10px; background:transparent; border:none; color:var(--text); font-family:var(--font-mono); font-size:12.5px; cursor:pointer; border-radius:var(--radius); }
  .row-context-menu-item:hover{ background:rgba(79,224,166,0.1); color:var(--phosphor); }
  .row-context-menu-item.danger{ color:var(--red); }
  .row-context-menu-item.danger:hover{ background:rgba(255,107,107,0.1); }
```

(If `--red` isn't the exact existing danger-color custom property name,
check the existing `.danger` button rule elsewhere in this file's CSS and
match its actual color value/variable instead.)

- [ ] **Step 2: Add `openRowContextMenu` module state**

Find (currently ~line 2172):

```js
  let openDocCollectionMenu = null;
```

Directly after it, insert:

```js
  let openRowContextMenu = null;
```

- [ ] **Step 3: Add the `contextmenu` listener and the menu-building function**

Find (currently ~lines 4397-4410, the existing `dblclick` listener, ending
with):

```js
    tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('dblclick', async (e) => {
      // .select-col/.row-edit-col opt out of the row's own click handler via
      // their own onclick="event.stopPropagation()" -- but that only stops
      // `click`, not `dblclick` (a separate event type), so a double-click
      // landing on either cell still reached here unless explicitly guarded.
      if(e.target.closest('.select-col, .row-edit-col')) return;
      const d = allDocs.find(x => x.id === Number(tr.dataset.id));
      if(!d || !d.file_path) return;
      try{
        const fh = await resolveFileHandle(d.file_path, false);
        const file = await fh.getFile();
        window.open(URL.createObjectURL(file), '_blank');
      }catch(e){ alert(t('detailOpenFileError', {error: e.message})); }
    }));
```

Directly after that whole block, insert:

```js
    // Right-click selects the row (identical to the click listener above)
    // and opens a context menu carrying most of the panel's own actions.
    // Same opt-out guard as dblclick, for the same reason: those cells'
    // onclick="event.stopPropagation()" only covers `click`.
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

- [ ] **Step 4: Add `showRowContextMenu()`**

Find the line directly before `function buildDetailActions(id, d){` (added
in Task 1, Step 2) and insert this new function immediately above it:

```js
  // Shows the row context menu at a fixed viewport position (clientX/clientY
  // from the contextmenu event are already viewport-relative, unlike the
  // add-to-collection picker's own position:absolute + scrollX/scrollY
  // positioning, which anchors to a button's own getBoundingClientRect()
  // instead of a raw click coordinate).
  function showRowContextMenu(id, x, y){
    const d = allDocs.find(doc => doc.id === id);
    if(!d) return;
    if(openRowContextMenu){ openRowContextMenu.remove(); openRowContextMenu = null; }

    const menu = document.createElement('div');
    menu.className = 'row-context-menu';
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';

    const detailLabel = detailPanelExpanded ? t('contextMenuHideDetails') : t('contextMenuShowDetails');
    const detailBtn = document.createElement('button');
    detailBtn.type = 'button';
    detailBtn.className = 'row-context-menu-item';
    detailBtn.textContent = detailLabel;
    menu.appendChild(detailBtn);

    const actionButtons = [];
    buildDetailActions(id, d).filter(a => !a.panelOnly).forEach(a => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'row-context-menu-item' + (a.variant === 'danger' ? ' danger' : '');
      btn.textContent = a.label;
      menu.appendChild(btn);
      actionButtons.push({ btn, onClick: a.onClick });
    });

    document.body.appendChild(menu);
    openRowContextMenu = menu;

    const closeMenu = () => {
      if(openRowContextMenu === menu){ menu.remove(); openRowContextMenu = null; }
      document.removeEventListener('click', closeMenu);
    };

    detailBtn.addEventListener('click', (e) => {
      // Call the handler BEFORE removing the menu -- closeMenu() only
      // detaches this container from the DOM, so it's safe either order for
      // this specific handler, but every item below follows the same order
      // for consistency (and because add-to-collection's own handler
      // specifically needs e.target still attached to the DOM when it reads
      // e.target.getBoundingClientRect() -- removing the menu first would
      // detach that button, making the rect collapse to all zeros).
      saveDetailPanelExpanded(!detailPanelExpanded);
      closeMenu();
    });
    actionButtons.forEach(({ btn, onClick }) => {
      btn.addEventListener('click', (e) => {
        onClick(e);
        closeMenu();
      });
    });

    // Same delayed-registration pattern as openDocCollectionMenu's own
    // outside-click dismissal (add-to-collection-btn's handler, inside
    // buildDetailActions()) -- the setTimeout(...,0) is what keeps the
    // very click that opened this menu (the contextmenu event itself,
    // which is a separate event from any subsequent `click`) from
    // immediately closing it.
    setTimeout(() => document.addEventListener('click', closeMenu), 0);
  }

```

- [ ] **Step 5: Add the two new i18n keys**

Add `contextMenuShowDetails`/`contextMenuHideDetails` to all six language
blocks, right after each one's existing `detailPanelEmpty` key (same
clustering convention this file already uses throughout `STRINGS`).

English (find `detailPanelEmpty: 'Select a document to see its details.',`
at ~line 827):

```js
      detailPanelEmpty: 'Select a document to see its details.',
      contextMenuShowDetails: 'Show Details', contextMenuHideDetails: 'Hide Details',
```

Spanish (find `detailPanelEmpty: 'Selecciona un documento para ver sus detalles.',`
at ~line 989):

```js
      detailPanelEmpty: 'Selecciona un documento para ver sus detalles.',
      contextMenuShowDetails: 'Mostrar detalles', contextMenuHideDetails: 'Ocultar detalles',
```

French (find `detailPanelEmpty: 'Sélectionnez un document pour voir ses détails.',`
at ~line 1151):

```js
      detailPanelEmpty: 'Sélectionnez un document pour voir ses détails.',
      contextMenuShowDetails: 'Afficher les détails', contextMenuHideDetails: 'Masquer les détails',
```

German (find `detailPanelEmpty: 'Wähle ein Dokument aus, um seine Details zu sehen.',`
at ~line 1313):

```js
      detailPanelEmpty: 'Wähle ein Dokument aus, um seine Details zu sehen.',
      contextMenuShowDetails: 'Details anzeigen', contextMenuHideDetails: 'Details ausblenden',
```

Chinese Simplified (find `detailPanelEmpty: '选择一个文档以查看其详情。',`
at ~line 1475):

```js
      detailPanelEmpty: '选择一个文档以查看其详情。',
      contextMenuShowDetails: '显示详情', contextMenuHideDetails: '隐藏详情',
```

Chinese Traditional (find `detailPanelEmpty: '選擇一個文檔以查看其詳情。',`
at ~line 1704) — character-converted from the Simplified wording above,
matching this file's existing OpenCC-derivation convention for `zh-Hant`:

```js
      detailPanelEmpty: '選擇一個文檔以查看其詳情。',
      contextMenuShowDetails: '顯示詳情', contextMenuHideDetails: '隱藏詳情',
```

- [ ] **Step 6: Manual verification**

Run the existing i18n coverage check to confirm the six new keys are
correctly present in every language:

```bash
cd tests && /usr/local/bin/python3 test_i18n_coverage.py
```

Expected: `PASS`.

- [ ] **Step 7: New Playwright test scenarios in `tests/test_detail_panel.py`**

Find the end of the file (search for `print("JS ERRORS:", errors)` — the
last line before `await browser.close()`). Directly before it, insert:

```python
        # === Scenario 11: right-click selects the row and opens a context
        # menu, whether or not the panel is currently expanded ===
        await page.click('#detail-panel-toggle-btn')  # collapse it, so this genuinely exercises "regardless of panel state"
        await page.wait_for_timeout(150)
        panel_collapsed_before_right_click = not await page.locator('#main-layout.detail-panel-expanded').count()
        print("panel collapsed ahead of Scenario 11:", panel_collapsed_before_right_click)

        await page.click('tr[data-id="2"]', button='right')
        await page.wait_for_timeout(200)
        row2_selected_via_right_click = await page.locator('tr[data-id="2"].row-selected').count()
        print("right-click selects/highlights the row:", row2_selected_via_right_click == 1)
        menu_visible = await page.locator('.row-context-menu:visible').count()
        print("right-click opens the context menu:", menu_visible == 1)

        # === Scenario 12: the context menu's action set matches the panel's
        # own, minus Regenerate preview, plus Detail ===
        menu_item_texts = await page.locator('.row-context-menu .row-context-menu-item').all_inner_texts()
        print("Regenerate preview never appears in the context menu:", not any('preview' in t.lower() for t in menu_item_texts))
        print("Detail item is present:", any('Details' in t for t in menu_item_texts))
        print("Edit is present:", any(t == 'Edit' for t in menu_item_texts))
        print("Archive is present:", any(t == 'Archive' for t in menu_item_texts))
        print("Delete is present:", any(t == 'Delete' for t in menu_item_texts))

        # === Scenario 13: "Detail" toggles the panel without changing
        # selection; selecting a different row afterward doesn't itself
        # change panel visibility ===
        await page.click('.row-context-menu .row-context-menu-item:has-text("Show Details")')
        await page.wait_for_timeout(150)
        panel_expanded_after_detail_click = bool(await page.locator('#main-layout.detail-panel-expanded').count())
        print("Detail expands the panel:", panel_expanded_after_detail_click)
        still_row2_selected = await page.locator('tr[data-id="2"].row-selected').count()
        print("Detail does not change which document is selected:", still_row2_selected == 1)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(150)
        panel_still_expanded_after_other_selection = bool(await page.locator('#main-layout.detail-panel-expanded').count())
        print("selecting a different row afterward doesn't change panel visibility:", panel_still_expanded_after_other_selection)

        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(200)
        await page.click('.row-context-menu .row-context-menu-item:has-text("Hide Details")')
        await page.wait_for_timeout(150)
        panel_collapsed_after_second_detail_click = not await page.locator('#main-layout.detail-panel-expanded').count()
        print("Detail collapses the panel on a second invocation:", panel_collapsed_after_second_detail_click)

        # === Scenario 14: a representative action (Archive) actually does
        # the same thing from the context menu as it does from the panel ===
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(200)
        await page.click('.row-context-menu .row-context-menu-item:has-text("Archive")')
        await page.wait_for_timeout(200)
        await page.click('#detail-panel-toggle-btn')  # expand to check the panel's own button label
        await page.wait_for_timeout(150)
        archived_via_context_menu = await page.locator('#archive-toggle-btn').inner_text()
        print("Archive from the context menu actually archives the document:", 'Unarchive' in archived_via_context_menu)
        await page.click('#archive-toggle-btn')  # unarchive again
        await page.wait_for_timeout(200)

        # === Scenario 15: no context menu on .select-col/.row-edit-col, or
        # in Reports view ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        dialog_fired = []
        page.on('dialog', lambda dialog: (dialog_fired.append(dialog.message), asyncio.ensure_future(dialog.dismiss())))
        await page.click('tr[data-id="1"] .select-col', button='right')
        await page.wait_for_timeout(200)
        no_menu_on_checkbox = await page.locator('.row-context-menu:visible').count()
        print("no context menu when right-clicking the select checkbox:", no_menu_on_checkbox == 0)

        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        no_rows_in_reports = await page.locator('#doc-tbody tr').count()
        print("Reports view has no rows to right-click in the first place:", no_rows_in_reports == 0)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)

        # === Scenario 16: "Add to Collection" from the context menu closes
        # the menu and opens the collection picker cleanly, positioned near
        # the click rather than collapsed to (0,0) ===
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(200)
        await page.click('.row-context-menu .row-context-menu-item:has-text("Add to collection")')
        await page.wait_for_timeout(150)
        context_menu_gone = await page.locator('.row-context-menu:visible').count()
        print("context menu closes when Add to Collection is clicked:", context_menu_gone == 0)
        picker_visible = await page.locator('.bulk-collection-menu:visible').count()
        print("collection picker opens:", picker_visible == 1)
        picker_top = await page.locator('.bulk-collection-menu').evaluate('el => parseFloat(el.style.top)')
        print("collection picker is positioned near the click, not collapsed to (0,0):", picker_top > 0)
        await page.click('#nav-item-all')  # dismiss the picker by clicking elsewhere
        await page.wait_for_timeout(150)

```

(Adjust exact button-label text-matching selectors, e.g. `has-text("Archive")`
vs `has-text("Unarchive")`, if the document's actual current state at that
point in the file differs from what's assumed above — read the surrounding
existing scenarios' current state at the point of insertion first, since
`SEED`/prior scenarios may have changed doc 1's archived/flagged state by
the time Scenario 11 runs.)

- [ ] **Step 8: Run it**

```bash
cd tests && /usr/local/bin/python3 test_detail_panel.py
```

Expected: every printed line is `True`, `JS ERRORS: []`.

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_detail_panel.py
git commit -m "Add a right-click context menu to table rows

Right-click selects the row (same as left-click) and opens a menu with
most of the detail panel's own actions, built from the same
buildDetailActions() descriptors the panel itself uses -- everything
except Regenerate preview, plus a new Detail item that toggles the
panel's expanded/collapsed state without changing the selection."
```

---

### Task 3: CLAUDE.md architecture note

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the finished behavior from Tasks 1-2 (this task only
  documents it — no code changes).

- [ ] **Step 1: Read the existing note first**

Read CLAUDE.md's "The detail view is a persistent side panel" note in
full (search for that exact phrase) — including the paragraphs the panel
follow-up branch already appended to it (default-expanded, double-click,
row-edit-btn gating) — to match voice and to place the new content
correctly relative to what's already there.

- [ ] **Step 2: Add a new paragraph**

Insert a new paragraph at the end of that same note (after its existing
final paragraph, before the next `- **` bullet that starts a new note),
covering: `buildDetailActions(id, d)` as the one shared source of truth
for which document actions apply and what they do, consumed by both
`openDetail()` and the new `showRowContextMenu()`; why `panelOnly: true`
exists (Regenerate preview is the one action that never appears outside
the panel); the `contextmenu` listener's reuse of the same
`.select-col`/`.row-edit-col` opt-out guard `dblclick` already
established; and the "Detail" item's own semantics (toggles
`detailPanelExpanded` without touching `selectedDocId`, so it's
orthogonal to which document is currently selected, mirroring the
existing "row click never auto-expands" principle from the opposite
direction — selecting a document never touches panel visibility, and now,
symmetrically, toggling panel visibility never touches which document is
selected).

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the row context menu and buildDetailActions() extraction"
```

---

## Self-Review

**1. Spec coverage** — every item from the approved spec
(`docs/superpowers/specs/2026-08-22-row-context-menu-design.md`) maps to a
task: the shared-action extraction (Task 1); right-click selection,
`preventDefault()`, the `.select-col`/`.row-edit-col` guard, menu
positioning/dismissal, "Add to Collection" positioning correctness, the
"Detail" toggle item, and the close-menu-before-onClick ordering (all
Task 2); documentation (Task 3). Out-of-scope items (multi-row/bulk
actions, a keyboard-triggered menu, any change to what an action does
once triggered) are not implemented by any task.

**2. Placeholder scan** — no TBD/TODO; every step shows exact before/after
code, exact file locations, and exact translated strings for all six
languages.

**3. Type/name consistency** — `buildDetailActions(id, d)`,
`showRowContextMenu(id, x, y)`, `openRowContextMenu`, `.row-context-menu`/
`.row-context-menu-item`, and the `panelOnly` flag are named identically
everywhere they're introduced (Task 1/2) and consumed (Task 2/3).

**4. A real ordering subtlety worth restating**: the context menu's own
item-click dispatch calls each action's `onClick` *before* removing the
menu from the DOM, not after — this is load-bearing for "Add to
Collection," whose handler reads `e.target.getBoundingClientRect()`
synchronously at the top of its own function body, before any `await`.
Removing the menu (and thus detaching that button) first would collapse
the rect to all zeros and mis-position the collection picker. Task 2 Step
4's code and its inline comment make this explicit; Task 2 Step 7's
Scenario 16 test specifically guards against a regression here (asserting
the picker's computed `top` position is greater than zero, not just that
it appeared).
