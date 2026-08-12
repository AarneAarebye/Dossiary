# Bulk Archive, Delete, and Flag-for-Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the bulk-action bar (currently "Add to collection" only) with view-aware Archive/Delete/Flag-for-review/Restore actions that apply to every currently-selected document in one batched update.

**Architecture:** Three new functions (`bulkSetArchived`, `bulkSetDeleted`, `bulkSetNeedsReview`) each loop parameterized `UPDATE` calls over the selected ids, then persist and re-render exactly once — not by looping the existing single-document `toggleArchived()`/`toggleDeleted()`/`toggleNeedsReview()`, which would re-serialize and rewrite the whole SQLite database once per selected document. `renderBulkActionBar()` becomes view-aware, showing/hiding buttons per `currentView` to match `openDetail()`'s existing per-document-state action-set precedent.

**Tech Stack:** Vanilla JS in `dossiary.html` (no build step, no framework). Tests are standalone Playwright/Python scripts in `tests/`.

## Global Constraints

- Single file (`dossiary.html`) — no build step, no new `<script src>` dependencies.
- No schema change, no new `settings` keys, no new SQL beyond parameterized single-row `UPDATE ... WHERE id = ?` (matching the existing convention and `tests/stub_studio2.js`'s fake SQL engine, which only understands a single `WHERE col = ?` equality, not `WHERE id IN (...)`).
- Bulk actions are unconditional sets, not per-document toggles: "Archive selected" always sets `archived = 1` for every selected document regardless of each one's current value (same pattern for "Flag for review selected" → `needs_review = 1`, "Done" → `needs_review = 0`, "Restore selected" → `deleted = 0`).
- No confirmation dialog for any bulk action, including delete — consistent with every existing single-document toggle in this app.
- View-aware button visibility, matching `openDetail()`'s existing precedent exactly:
  - `currentView === 'trash'`: only "Restore selected" (Add to collection, Archive, Delete, Flag for review/Done all hidden).
  - `currentView === 'inbox'`: Add to collection, Archive, Delete, and a button labeled "Done" (not "Flag for review selected").
  - every other view (`'all'`, `'collection-<id>'`; `'reports'` is moot, it has no selection UI): Add to collection, Archive, Delete, "Flag for review selected".
- Selection (`selectedDocIds`) clears and the bar re-renders after every bulk action, matching the existing bulk-add-to-collection behavior.

---

## Task 1: View-aware bulk archive/delete/flag-for-review actions

**Files:**
- Modify: `dossiary.html:557-569` (bulk-action-bar markup — add 4 buttons, add an id to the collection-menu wrap)
- Modify: `dossiary.html:2707-2715` (`renderBulkActionBar()` — add view-aware visibility/label logic)
- Modify: `dossiary.html:3056` (insert the three new bulk functions right after `toggleDeleted()`)
- Modify: `dossiary.html:4405` (wire the four new buttons' click handlers, right after the existing `bulk-clear-selection-btn` wiring)
- Test: `tests/test_collections.py` (append 4 new scenarios after the existing Scenario 24, renumber the current Scenario 25 to Scenario 29)

**Interfaces:**
- Consumes: `selectedDocIds` (existing module-level `Set` of selected document ids), `allDocs`, `db`, `persistDb()`, `render()`, `currentView`, `el(id)` — all pre-existing, unchanged signatures.
- Produces: `bulkSetArchived(ids, value)`, `bulkSetDeleted(ids, value)`, `bulkSetNeedsReview(ids, value)` — each `async`, takes an array of document ids and a boolean, returns nothing. No later task depends on these (this is the only task in this plan).

- [ ] **Step 1: Add the four new buttons to the bulk-action-bar markup**

Find (`dossiary.html`, currently around lines 557-569):

```html
      <div class="bulk-action-bar" id="bulk-action-bar" style="display:none;">
        <span id="bulk-action-count"></span>
        <div class="bulk-collection-menu-wrap">
          <button type="button" id="bulk-add-to-collection-btn">Add to collection ▾</button>
          <div class="bulk-collection-menu" id="bulk-collection-menu" style="display:none;"></div>
        </div>
        <span class="add-field-form" id="bulk-new-collection-form" style="display:none;">
          <input type="text" id="bulk-new-collection-input" placeholder="New collection name" />
          <button type="button" id="bulk-new-collection-save-btn">Create &amp; add</button>
          <button type="button" id="bulk-new-collection-cancel-btn">Cancel</button>
        </span>
        <button type="button" id="bulk-clear-selection-btn">Clear selection</button>
      </div>
```

Replace with (adds an `id` to the collection-menu wrap so it can be toggled in Step 3, and adds four new buttons before "Clear selection" — `#bulk-restore-btn` starts hidden in markup since `'all'` is always the view on library open, never `'trash'`):

```html
      <div class="bulk-action-bar" id="bulk-action-bar" style="display:none;">
        <span id="bulk-action-count"></span>
        <div class="bulk-collection-menu-wrap" id="bulk-collection-menu-wrap">
          <button type="button" id="bulk-add-to-collection-btn">Add to collection ▾</button>
          <div class="bulk-collection-menu" id="bulk-collection-menu" style="display:none;"></div>
        </div>
        <span class="add-field-form" id="bulk-new-collection-form" style="display:none;">
          <input type="text" id="bulk-new-collection-input" placeholder="New collection name" />
          <button type="button" id="bulk-new-collection-save-btn">Create &amp; add</button>
          <button type="button" id="bulk-new-collection-cancel-btn">Cancel</button>
        </span>
        <button type="button" id="bulk-archive-btn">Archive selected</button>
        <button type="button" id="bulk-delete-btn">Delete selected</button>
        <button type="button" id="bulk-review-btn">Flag for review selected</button>
        <button type="button" id="bulk-restore-btn" style="display:none;">Restore selected</button>
        <button type="button" id="bulk-clear-selection-btn">Clear selection</button>
      </div>
```

- [ ] **Step 2: Make `renderBulkActionBar()` view-aware**

Find (`dossiary.html`, currently around lines 2707-2715):

```js
  function renderBulkActionBar(){
    const bar = el('bulk-action-bar');
    if(!bar) return;
    const visible = selectedDocIds.size > 0;
    mainLayout.classList.toggle('bulk-bar-visible', visible);
    if(!visible){ bar.style.display = 'none'; return; }
    bar.style.display = 'flex';
    el('bulk-action-count').textContent = `${selectedDocIds.size} selected`;
  }
```

Replace with:

```js
  function renderBulkActionBar(){
    const bar = el('bulk-action-bar');
    if(!bar) return;
    const visible = selectedDocIds.size > 0;
    mainLayout.classList.toggle('bulk-bar-visible', visible);
    if(!visible){ bar.style.display = 'none'; return; }
    bar.style.display = 'flex';
    el('bulk-action-count').textContent = `${selectedDocIds.size} selected`;

    // Waste bin is the one view where nothing but Restore makes sense -- matches
    // openDetail()'s own action-set precedent for a deleted document exactly
    // (Edit/Archive/Flag for review/Add to collection are all genuinely absent
    // there too, not just disabled, for the same reason).
    const isTrash = currentView === 'trash';
    el('bulk-collection-menu-wrap').style.display = isTrash ? 'none' : '';
    el('bulk-archive-btn').style.display = isTrash ? 'none' : '';
    el('bulk-delete-btn').style.display = isTrash ? 'none' : '';
    el('bulk-review-btn').style.display = isTrash ? 'none' : '';
    el('bulk-restore-btn').style.display = isTrash ? '' : 'none';
    // Inbox already means "flagged" for everything visible there, so the bulk
    // action is Done (clear the flag), not Flag for review (set it) -- same
    // relabeling openDetail()'s own single-document review-toggle button already
    // does for an individual document.
    el('bulk-review-btn').textContent = currentView === 'inbox' ? 'Done' : 'Flag for review selected';
  }
```

- [ ] **Step 3: Add the three bulk functions**

Find (`dossiary.html`, currently ending around line 3056):

```js
  async function toggleDeleted(id){
    const d = allDocs.find(x => x.id === id);
    if(!d) return;
    d.deleted = !d.deleted;
    db.run('UPDATE documents SET deleted = ? WHERE id = ?', [d.deleted ? 1 : 0, id]);
    await persistDb();
    render(); // render()'s own renderNav() call refreshes badge counts/active view
  }

  async function regenerateThumbnail(id){
```

Replace with (inserts the three new functions between `toggleDeleted()` and `regenerateThumbnail()`):

```js
  async function toggleDeleted(id){
    const d = allDocs.find(x => x.id === id);
    if(!d) return;
    d.deleted = !d.deleted;
    db.run('UPDATE documents SET deleted = ? WHERE id = ?', [d.deleted ? 1 : 0, id]);
    await persistDb();
    render(); // render()'s own renderNav() call refreshes badge counts/active view
  }

  // Bulk versions of the toggle*() functions above -- deliberately NOT built by
  // looping the single-document toggles, since persistDb() re-serializes and
  // rewrites the entire SQLite database on every call; looping it once per
  // selected document would be wasteful for exactly the case bulk-select exists
  // to handle (potentially many documents at once). Each does its UPDATEs first,
  // then persists and re-renders exactly once. Also deliberately NOT a
  // per-document toggle -- "Archive selected" always sets archived=1 for every
  // selected document regardless of its current value (same for the other two),
  // since a mixed-state selection (e.g. from a Collection view, which
  // deliberately includes archived/needs-review documents) toggling each
  // independently would produce a confusing, non-uniform result.
  async function bulkSetArchived(ids, value){
    ids.forEach(id => db.run('UPDATE documents SET archived = ? WHERE id = ?', [value ? 1 : 0, id]));
    ids.forEach(id => { const d = allDocs.find(x => x.id === id); if(d) d.archived = value; });
    await persistDb();
    selectedDocIds = new Set();
    render();
  }

  async function bulkSetDeleted(ids, value){
    ids.forEach(id => db.run('UPDATE documents SET deleted = ? WHERE id = ?', [value ? 1 : 0, id]));
    ids.forEach(id => { const d = allDocs.find(x => x.id === id); if(d) d.deleted = value; });
    await persistDb();
    selectedDocIds = new Set();
    render();
  }

  async function bulkSetNeedsReview(ids, value){
    ids.forEach(id => db.run('UPDATE documents SET needs_review = ? WHERE id = ?', [value ? 1 : 0, id]));
    ids.forEach(id => { const d = allDocs.find(x => x.id === id); if(d) d.needs_review = value; });
    await persistDb();
    selectedDocIds = new Set();
    render();
  }

  async function regenerateThumbnail(id){
```

- [ ] **Step 4: Wire the four new buttons' click handlers**

Find (`dossiary.html`, currently around line 4405):

```js
  el('bulk-clear-selection-btn').addEventListener('click', () => { selectedDocIds = new Set(); render(); });
```

Replace with:

```js
  el('bulk-archive-btn').addEventListener('click', () => bulkSetArchived([...selectedDocIds], true));
  el('bulk-delete-btn').addEventListener('click', () => bulkSetDeleted([...selectedDocIds], true));
  el('bulk-review-btn').addEventListener('click', () => bulkSetNeedsReview([...selectedDocIds], currentView !== 'inbox'));
  el('bulk-restore-btn').addEventListener('click', () => bulkSetDeleted([...selectedDocIds], false));
  el('bulk-clear-selection-btn').addEventListener('click', () => { selectedDocIds = new Set(); render(); });
```

(`bulk-review-btn`'s handler computes its target value from `currentView` at click time, matching the same condition `renderBulkActionBar()` uses for the button's label — `true` (flag) everywhere except Inbox, `false` (Done/unflag) in Inbox.)

- [ ] **Step 5: Renumber the existing Scenario 25 to Scenario 29**

`tests/test_collections.py` currently has its last real scenario (the sticky-header calibration check) commented as "Scenario 25" — this plan's new scenarios take that number, so the existing one needs to move to 29 first, before anything is inserted, to avoid a collision.

Find (`tests/test_collections.py`, currently around line 455):

```python
    # === Scenario 25: sticky-header height calibration, across all four
```

Replace with:

```python
    # === Scenario 29: sticky-header height calibration, across all four
```

- [ ] **Step 6: Append the new test scenarios**

Find (`tests/test_collections.py`, currently around lines 447-453 — the end of Scenario 24, right before the first `async with async_playwright()` block closes):

```python
        all_nav_active = await page.locator('#nav-item-all').get_attribute('class')
        print("Deleting the currently-viewed collection falls back to All Documents (nav-item-all active):", 'active' in (all_nav_active or ''))
        count_line_after_delete = await page.locator('#count-line').text_content()
        print("countLine no longer stuck on the deleted collection's denominator:", 'undefined' not in (count_line_after_delete or ''))

        print("JS ERRORS:", errors)
        await browser.close()
```

Replace with (adds Scenarios 25-28 right before the existing "JS ERRORS" print/close; all four reuse `SEED`'s existing documents 1-4 and collection 1's existing membership of docs 3 & 4 — no `SEED` changes needed):

```python
        all_nav_active = await page.locator('#nav-item-all').get_attribute('class')
        print("Deleting the currently-viewed collection falls back to All Documents (nav-item-all active):", 'active' in (all_nav_active or ''))
        count_line_after_delete = await page.locator('#count-line').text_content()
        print("countLine no longer stuck on the deleted collection's denominator:", 'undefined' not in (count_line_after_delete or ''))

        # === Scenario 25: bulk action buttons visible in All Documents -- Archive,
        # Delete, Flag for review, and Add to collection all present; Restore absent ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        print("Archive button visible in All Documents:", await page.locator('#bulk-archive-btn').is_visible())
        print("Delete button visible in All Documents:", await page.locator('#bulk-delete-btn').is_visible())
        review_btn_text_all = await page.locator('#bulk-review-btn').inner_text()
        print("Review button reads 'Flag for review selected' in All Documents:", review_btn_text_all)
        print("Restore button hidden in All Documents:", not await page.locator('#bulk-restore-btn').is_visible())
        print("Add to collection visible in All Documents:", await page.locator('#bulk-add-to-collection-btn').is_visible())

        # === Scenario 26: bulk archive sets unconditionally on a mixed-state
        # selection -- doc 3 (not archived) and doc 4 (already archived, from SEED)
        # are both members of the "Manual Trip Folder" collection, so selecting both
        # there and clicking Archive should leave BOTH archived, not just doc 3 ===
        await page.click('#nav-item-collection-1')
        await page.wait_for_timeout(150)
        await page.check('tr[data-id="3"] .row-select-checkbox')
        await page.check('tr[data-id="4"] .row-select-checkbox')
        await page.click('#bulk-archive-btn')
        await page.wait_for_timeout(200)
        bulk_bar_hidden_after_archive = await page.locator('#bulk-action-bar').is_visible()
        print("bulk bar hidden after Archive (selection cleared):", not bulk_bar_hidden_after_archive)
        persisted_after_archive = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).documents;
            })()
        """)
        doc3_archived = next(d for d in persisted_after_archive if d['id'] == 3)['archived']
        doc4_archived = next(d for d in persisted_after_archive if d['id'] == 4)['archived']
        print("doc 3 (was not archived) is now archived:", doc3_archived)
        print("doc 4 (was already archived) is still archived:", doc4_archived)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        doc3_row_in_all = await page.locator('tr[data-id="3"]').count()
        print("newly-archived doc 3 no longer shows in All Documents by default:", doc3_row_in_all == 0)

        # === Scenario 27: bulk "Flag for review selected" ===
        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.click('#bulk-review-btn')
        await page.wait_for_timeout(200)
        persisted_after_flag = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).documents;
            })()
        """)
        doc1_flagged = next(d for d in persisted_after_flag if d['id'] == 1)['needs_review']
        doc2_flagged = next(d for d in persisted_after_flag if d['id'] == 2)['needs_review']
        print("doc 1 flagged for review after bulk action:", doc1_flagged)
        print("doc 2 flagged for review after bulk action:", doc2_flagged)

        await page.click('#nav-item-inbox')
        await page.wait_for_timeout(150)
        flagged_docs_in_inbox = await page.locator('#doc-tbody tr').count()
        print("both newly-flagged docs now show in the Inbox view:", flagged_docs_in_inbox)

        # === Scenario 28: Inbox relabels the button to "Done"; Restore stays hidden
        # there; bulk Done clears the flag ===
        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        review_btn_text_inbox = await page.locator('#bulk-review-btn').inner_text()
        print("Review button reads 'Done' in Inbox view:", review_btn_text_inbox)
        print("Restore button still hidden in Inbox view:", not await page.locator('#bulk-restore-btn').is_visible())
        print("Archive button still visible in Inbox view:", await page.locator('#bulk-archive-btn').is_visible())

        await page.click('#bulk-review-btn')
        await page.wait_for_timeout(200)
        persisted_after_done = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).documents;
            })()
        """)
        doc1_done = next(d for d in persisted_after_done if d['id'] == 1)['needs_review']
        doc2_done = next(d for d in persisted_after_done if d['id'] == 2)['needs_review']
        print("doc 1 no longer flagged after bulk Done:", doc1_done)
        print("doc 2 no longer flagged after bulk Done:", doc2_done)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        docs_back_in_all = await page.locator('tr[data-id="1"], tr[data-id="2"]').count()
        print("both docs are back in All Documents after Done:", docs_back_in_all)

        # === Scenario 28b: bulk delete, and the Waste bin view showing ONLY Restore
        # -- matching openDetail()'s own precedent for a deleted document exactly
        # (Add to collection/Archive/Delete/Flag for review all genuinely absent,
        # not just disabled) ===
        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.click('#bulk-delete-btn')
        await page.wait_for_timeout(200)
        persisted_after_delete = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).documents;
            })()
        """)
        doc1_deleted = next(d for d in persisted_after_delete if d['id'] == 1)['deleted']
        doc2_deleted = next(d for d in persisted_after_delete if d['id'] == 2)['deleted']
        print("doc 1 deleted after bulk action:", doc1_deleted)
        print("doc 2 deleted after bulk action:", doc2_deleted)
        docs_gone_from_all = await page.locator('tr[data-id="1"], tr[data-id="2"]').count()
        print("both deleted docs gone from All Documents:", docs_gone_from_all == 0)

        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        docs_in_trash = await page.locator('tr[data-id="1"], tr[data-id="2"]').count()
        print("both deleted docs show in the Waste bin:", docs_in_trash)

        await page.check('tr[data-id="1"] .row-select-checkbox')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.wait_for_timeout(150)
        print("Restore button visible in Waste bin:", await page.locator('#bulk-restore-btn').is_visible())
        print("Add to collection hidden in Waste bin:", not await page.locator('#bulk-add-to-collection-btn').is_visible())
        print("Archive button hidden in Waste bin:", not await page.locator('#bulk-archive-btn').is_visible())
        print("Delete button hidden in Waste bin:", not await page.locator('#bulk-delete-btn').is_visible())
        print("Review button hidden in Waste bin:", not await page.locator('#bulk-review-btn').is_visible())

        await page.click('#bulk-restore-btn')
        await page.wait_for_timeout(200)
        persisted_after_restore = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text()).documents;
            })()
        """)
        doc1_restored = next(d for d in persisted_after_restore if d['id'] == 1)['deleted']
        doc2_restored = next(d for d in persisted_after_restore if d['id'] == 2)['deleted']
        print("doc 1 no longer deleted after bulk Restore:", doc1_restored)
        print("doc 2 no longer deleted after bulk Restore:", doc2_restored)
        docs_gone_from_trash = await page.locator('tr[data-id="1"], tr[data-id="2"]').count()
        print("both restored docs gone from the Waste bin:", docs_gone_from_trash == 0)

        print("JS ERRORS:", errors)
        await browser.close()
```

- [ ] **Step 7: Run the test to verify it fails against the current (unmodified) app**

Run: `cd tests && python3 test_collections.py`

Expected: FAIL/incorrect output — clicking `.row-select-checkbox` and then looking for `#bulk-archive-btn`/`#bulk-delete-btn`/`#bulk-review-btn`/`#bulk-restore-btn` will time out or return `is_visible() == False` for all of them, since none of these elements exist yet in the unmodified markup. Confirm the run does not cleanly print the full expected sequence — this is the "red" step.

- [ ] **Step 8: Apply the `dossiary.html` changes**

Apply Steps 1-4 above to `dossiary.html`.

- [ ] **Step 9: Run the test again to verify it passes**

Run: `cd tests && python3 test_collections.py`

Expected: every new scenario's printed line reflects success — `Archive button visible in All Documents: True`, `Delete button visible in All Documents: True`, `Review button reads 'Flag for review selected' in All Documents: Flag for review selected`, `Restore button hidden in All Documents: True`, `Add to collection visible in All Documents: True`; `bulk bar hidden after Archive (selection cleared): True`, `doc 3 (was not archived) is now archived: 1`, `doc 4 (was already archived) is still archived: 1`, `newly-archived doc 3 no longer shows in All Documents by default: True`; `doc 1 flagged for review after bulk action: 1`, `doc 2 flagged for review after bulk action: 1`, `both newly-flagged docs now show in the Inbox view: 2`; `Review button reads 'Done' in Inbox view: Done`, `Restore button still hidden in Inbox view: True`, `Archive button still visible in Inbox view: True`, `doc 1 no longer flagged after bulk Done: 0`, `doc 2 no longer flagged after bulk Done: 0`, `both docs are back in All Documents after Done: 2`; `doc 1 deleted after bulk action: 1`, `doc 2 deleted after bulk action: 1`, `both deleted docs gone from All Documents: True`, `both deleted docs show in the Waste bin: 2`, `Restore button visible in Waste bin: True`, `Add to collection hidden in Waste bin: True`, `Archive button hidden in Waste bin: True`, `Delete button hidden in Waste bin: True`, `Review button hidden in Waste bin: True`, `doc 1 no longer deleted after bulk Restore: 0`, `doc 2 no longer deleted after bulk Restore: 0`, `both restored docs gone from the Waste bin: True`. Also confirm all pre-existing scenarios (1-24, 29) still print their original expected values unchanged, and `JS ERRORS: []`.

- [ ] **Step 10: Run the full regression suite**

```bash
cd tests
for f in test_*.py; do python3 "$f" > /tmp/out_$f.txt 2>&1 || echo "FAILED: $f"; done
```

Expected: no `FAILED:` lines (52 test files total — no file added or removed, `test_collections.py` is extended in place).

- [ ] **Step 11: Commit**

```bash
git add dossiary.html tests/test_collections.py
git commit -m "Add view-aware bulk archive, delete, and flag-for-review actions"
```

---

## Self-Review

**Spec coverage:**
- View-aware button sets per view (All/Collection, Inbox, Trash) — Steps 1-2, covered.
- Unconditional-set (not toggle) semantics — Step 3's `bulkSetArchived`/`bulkSetDeleted`/`bulkSetNeedsReview` all take an explicit `value` rather than reading/flipping current state, covered.
- No confirmation dialog — nothing in this plan adds one, covered by omission (matches spec's Non-goals).
- Single batched `persistDb()`/`render()` per bulk action, not per document — Step 3's implementation, covered.
- "Done" label swap in Inbox — Step 2 (`renderBulkActionBar()`) and Step 4 (click handler computing the matching value), covered.
- Test coverage for button visibility per view, unconditional-set behavior on a genuinely mixed-state selection, and selection-clearing — Step 6's Scenarios 25-28b, covered.
- Non-goal (no bulk remove-from-collection) — nothing in this plan adds one.
- Non-goal (no schema/dependency changes) — confirmed, this plan only touches `dossiary.html` and one test file.

**Placeholder scan:** No TBD/TODO, no "add appropriate error handling," no "similar to Task N" (single task), no undefined references — every code block is the actual, complete text to write or the actual current text to find.

**Type consistency:** `bulkSetArchived(ids, value)`, `bulkSetDeleted(ids, value)`, `bulkSetNeedsReview(ids, value)` all share the identical `(array, boolean)` signature and are called identically at their four wiring sites in Step 4. `el('bulk-collection-menu-wrap')` (the new id added in Step 1) is the one element referenced by both Step 1's markup and Step 2's `renderBulkActionBar()` — verified the id matches exactly in both places.
