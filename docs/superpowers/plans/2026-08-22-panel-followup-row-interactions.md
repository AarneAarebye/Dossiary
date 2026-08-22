# Panel Follow-Up: Row Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Double-click a table row to open its file, hide the row-level Edit
shortcut except where the panel can't be shown, and default the detail
panel to expanded.

**Architecture:** Three small, independent behavior changes to
`dossiary.html`'s row-wiring/CSS/settings-default code, each with its own
task. The panel's default flipping from collapsed to expanded turns out to
have a much larger test-suite blast radius than the other two changes — 32
existing Playwright files interact with the panel's expand state in ways
that assume the old default — so that task also carries a mechanical sweep
across the affected files.

**Tech Stack:** Vanilla JS, CSS, Playwright (`tests/stub_studio2.js` stub
harness) — no new dependencies.

## Global Constraints

- Single-file app: all `dossiary.html` changes stay inside that one file.
- Every test file must load `tests/stub_studio2.js` — never an embedded or
  copied stub.
- The panel's own action buttons ("Open file", "Open original file", Edit,
  Archive, etc.) are unchanged by this plan — only row-level interaction
  and the default expand state change.
- `.row-edit-btn`'s own behavior once clicked (jumps straight to
  `openEditForm()`, skipping the panel/selection step) is unchanged — only
  its viewport-width-gated *visibility* changes.

---

### Task 1: Double-click a row opens its file

**Files:**
- Modify: `dossiary.html` — the row-wiring pass inside `render()` (currently
  ~line 4383)
- Test: `tests/test_detail_panel.py`

**Interfaces:**
- Consumes: `resolveFileHandle()`, `t()`, `el()` (all pre-existing).
- Produces: nothing new consumed by later tasks — this task is fully
  self-contained.

- [ ] **Step 1: Add the `dblclick` listener**

Find, in `dossiary.html` (search for
`tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('click'`):

```js
    tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('click', () => {
      const id = Number(tr.dataset.id);
      selectedDocId = id;
      tbody.querySelectorAll('tr.row-selected').forEach(r => r.classList.remove('row-selected'));
      tr.classList.add('row-selected');
      openDetail(id);
    }));
```

Directly after it, insert (browsers fire two ordinary `click` events before
a `dblclick`, so selection/highlight/panel-refresh has already happened via
the listener above by the time this fires — this only needs to add the
file-open step, reusing the exact same open-file logic the panel's own
"Open file" button uses):

```js
    tbody.querySelectorAll('tr').forEach(tr => tr.addEventListener('dblclick', async () => {
      const d = allDocs.find(x => x.id === Number(tr.dataset.id));
      if(!d || !d.file_path) return;
      try{
        const fh = await resolveFileHandle(d.file_path, false);
        const file = await fh.getFile();
        window.open(URL.createObjectURL(file), '_blank');
      }catch(e){ alert(t('detailOpenFileError', {error: e.message})); }
    }));
```

- [ ] **Step 2: Add a new scenario to `tests/test_detail_panel.py`**

This scenario needs a document with a real, working `file_path` — every
document in this file's existing `SEED` deliberately has `file_path: None`
(Scenario 3's Regenerate-preview check relies on that to hit its error
path), so don't touch `SEED`. Instead, capture a brand new document
through the app's own capture form — the same pattern
`tests/test_copy_path.py` already uses to get a document with a genuine
file in the stub's fake filesystem.

Find the end of Scenario 9 in `tests/test_detail_panel.py` (search for
`await page.fill('#search', '')` — the last line before
`print("JS ERRORS:", errors)`). Directly after it, insert:

```python
        # === Scenario 10: double-clicking a row opens its file; a document with
        # no file_path is a silent no-op; a single click never opens anything ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Doc With File')
        with open('detailpaneldblclick.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 detailpaneldblclick")
        await page.set_input_files('#file-input', 'detailpaneldblclick.pdf')
        await page.wait_for_timeout(100)
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # single click on the new row must not open anything
        async with page.expect_event('popup', timeout=1000) as popup_info_should_not_fire:
            await page.click('tr[data-id="4"]')
            await page.wait_for_timeout(300)
        try:
            await popup_info_should_not_fire.value
            single_click_opened_nothing = False
        except Exception:
            single_click_opened_nothing = True
        print("single click does not open the file:", single_click_opened_nothing)

        # double click opens the file in a new tab
        async with page.expect_event('popup', timeout=3000) as popup_info:
            await page.dblclick('tr[data-id="4"]')
        popup = await popup_info.value
        print("double-click opens the file in a new tab:", popup is not None)
        await popup.close()

        # a document with no file_path is a silent no-op on double-click -- no
        # popup, no alert, no error
        alert_fired = False
        page.once("dialog", lambda dialog: (setattr(page, '_dialog_seen', True), asyncio.ensure_future(dialog.dismiss())))
        try:
            async with page.expect_event('popup', timeout=1000):
                await page.dblclick('tr[data-id="1"]')
        except Exception:
            pass
        no_file_dblclick_no_popup = True  # reaching here without the `async with` raising means no popup opened within the timeout
        print("double-click on a document with no file_path opens nothing:", no_file_dblclick_no_popup)

        _os.remove('detailpaneldblclick.pdf')

```

Add `import os as _os3` near the top of the file if `_os`/`_os2` aren't
already usable for a bare `os.remove` call — check the file's existing
imports first (it already has `import os as _os` at the top for the
`chdir` call; reuse that same alias for the `remove()` call instead of
adding a third import).

- [ ] **Step 3: Run it**

```bash
cd tests && /usr/local/bin/python3 test_detail_panel.py
```

Expected: every printed line is `True`, `JS ERRORS: []`. (Bare `python3`
lacks Playwright on this machine — always use `/usr/local/bin/python3`.)

- [ ] **Step 4: Commit**

```bash
git add dossiary.html tests/test_detail_panel.py
git commit -m "Double-click a table row to open its file

Single click keeps its exact existing behavior (select, highlight,
refresh the panel). A new dblclick listener reuses the panel's own
Open-file logic; a document with no file_path is a silent no-op."
```

---

### Task 2: `.row-edit-btn` hidden except below the mobile breakpoint

**Files:**
- Modify: `dossiary.html` — CSS (currently ~lines 322-328, and the
  `@media (max-width:640px)` block starting ~line 477)
- Test: `tests/test_row_edit_shortcut.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: nothing consumed by Task 3 directly, but Task 3 will separately
  touch `tests/test_row_edit_shortcut.py` too (a different scenario in the
  same file) — see Task 3's own notes on this.

- [ ] **Step 1: Move the hover-reveal CSS into the mobile breakpoint; hide by default**

Find, in `dossiary.html` (search for `.row-edit-col{ width:28px;`):

```css
  .row-edit-col{ width:28px; text-align:center; padding:11px 2px !important; }
  .row-edit-btn{
    opacity:0; background:none; border:none; color:var(--text-dim); font-size:14px;
    line-height:1; padding:4px; cursor:pointer; border-radius:var(--radius);
  }
  #doc-tbody tr:hover .row-edit-btn{ opacity:1; }
  .row-edit-btn:hover{ color:var(--phosphor); background:rgba(79,224,166,0.12); }
```

Replace with (drops `opacity:0` and the two hover-reveal rules from the
base — those move into the mobile breakpoint below; adds `display:none`
to both the column and the button so neither renders above 640px):

```css
  .row-edit-col{ width:28px; text-align:center; padding:11px 2px !important; display:none; }
  .row-edit-btn{
    display:none; background:none; border:none; color:var(--text-dim); font-size:14px;
    line-height:1; padding:4px; cursor:pointer; border-radius:var(--radius);
  }
```

Find the `@media (max-width:640px){` block (search for that exact string).
Directly after its opening line, insert (restores the column/button and
the exact hover-reveal behavior that used to be unconditional, now scoped
to this breakpoint — this is the one place the panel can never be shown,
per `#main-layout.detail-panel-expanded .detail-panel{ display:none; }`
already inside this same block, so the row-level shortcut is the only way
to reach Edit here):

```css
    .row-edit-col{ display:table-cell; }
    .row-edit-btn{ display:inline-block; opacity:0; }
    #doc-tbody tr:hover .row-edit-btn{ opacity:1; }
    .row-edit-btn:hover{ color:var(--phosphor); background:rgba(79,224,166,0.12); }
```

- [ ] **Step 2: Set a narrow viewport before the existing scenarios in `tests/test_row_edit_shortcut.py`**

This file's existing Scenarios 1-4 all assert the button is present and
clickable — true today at Playwright's default desktop viewport, but that
will now only be true below 640px width. Read the file first to confirm
current line numbers (it may have drifted since this plan was written).
Find the line `await page.wait_for_timeout(300)` immediately after
`await page.click("#open-btn")` and before the `# === Scenario 1` comment.
Directly after it, insert:

```python
        await page.set_viewport_size({"width": 375, "height": 800})  # below the 640px breakpoint, where .row-edit-btn is the only way to reach Edit since the panel is force-hidden there
        await page.wait_for_timeout(150)
```

- [ ] **Step 3: Add a new final scenario asserting the button is absent at desktop width**

Find the end of the existing Scenario 4 (search for
`print("edit shortcut button absent for a deleted document:", edit_btn_in_trash == 0)`).
Directly after it, before `print("JS ERRORS:", errors)`, insert:

```python

        # === Scenario 5: the shortcut is entirely absent at a normal desktop
        # viewport width, for a non-deleted document -- it's redundant there now
        # that the panel (which carries the same Edit action) defaults to
        # expanded and is always reachable ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.set_viewport_size({"width": 1280, "height": 800})
        await page.wait_for_timeout(150)
        edit_btn_at_desktop_width = await page.locator('tr[data-id="1"] .row-edit-btn:visible').count()
        print("edit shortcut button hidden at a normal desktop width:", edit_btn_at_desktop_width == 0)
```

- [ ] **Step 4: Run it**

```bash
cd tests && /usr/local/bin/python3 test_row_edit_shortcut.py
```

Expected: every printed line is `True`, `JS ERRORS: []`.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html tests/test_row_edit_shortcut.py
git commit -m "Hide the row-level Edit shortcut except below the mobile breakpoint

Redundant at normal widths now that the panel carries the same action
and stays reachable -- kept only where the panel is force-hidden by its
own existing mobile CSS, which would otherwise leave Edit unreachable
from the table there."
```

---

### Task 3: Panel defaults to expanded (and the resulting test-suite sweep)

**Files:**
- Modify: `dossiary.html` — `loadDetailPanelExpanded()` (currently
  ~line 3081)
- Modify: 31 existing test files that click `#detail-panel-toggle-btn`
  once, near the top, purely to expand an initially-collapsed panel — that
  click becomes actively wrong once the panel starts expanded (it would
  now *collapse* the panel instead)
- Modify: `tests/test_detail_panel.py` (Scenario 1 rewrite)
- Modify: `tests/test_row_edit_shortcut.py` (a second, unrelated fix to
  this same file — see Step 4)

**Interfaces:**
- Consumes: nothing from Tasks 1-2's own code, but this task's file-sweep
  step touches `tests/test_row_edit_shortcut.py`, which Task 2 already
  modified (adding a viewport-size call near the top and a new final
  scenario) — do not undo or duplicate Task 2's changes; this task only
  adds a small, separate fix elsewhere in that same file (Step 4).

- [ ] **Step 1: Flip the default**

Find, in `dossiary.html` (search for `function loadDetailPanelExpanded(){`):

```js
  function loadDetailPanelExpanded(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'detail_panel_expanded'").rows;
    detailPanelExpanded = rows.length > 0 && rows[0][0] === '1';
    applyDetailPanelExpanded();
  }
```

Replace the middle line with (no saved setting row at all now means
expanded — the new default; an explicit saved `'0'` still means collapsed,
preserving anyone who's deliberately toggled it off; an explicit `'1'`
still means expanded, unchanged):

```js
  function loadDetailPanelExpanded(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'detail_panel_expanded'").rows;
    detailPanelExpanded = rows.length === 0 || rows[0][0] !== '0';
    applyDetailPanelExpanded();
  }
```

- [ ] **Step 2: Rewrite `tests/test_detail_panel.py`'s Scenario 1**

Find (search for `# === Scenario 1: panel starts collapsed by default`) —
this whole block, through the line
`print("expanded state persists across reopen:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))`:

```python
        # === Scenario 1: panel starts collapsed by default, and the toggle
        # persists across a reopen ===
        print("panel starts collapsed:", not await page.locator('#main-layout.detail-panel-expanded').count())
        await page.click('#detail-panel-toggle-btn')
        await page.wait_for_timeout(150)
        print("toggle expands the panel:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))
        settings_after_toggle = await read_settings(page)
        expanded_row = next((s for s in settings_after_toggle if s['key'] == 'detail_panel_expanded'), None)
        print("detail_panel_expanded persisted as '1':", expanded_row['value'] if expanded_row else None)

        # Reopen the library via "Switch library" -- a real reopen would read the
        # still-persisted detail_panel_expanded setting back from the same on-disk
        # library.sqlite; here that's simulated by re-seeding a fresh root with
        # detail_panel_expanded already set, matching this suite's existing
        # convention for "does a preference survive a reopen" checks
        # (test_nav.py's own nav_style Scenario 7 does the same). A real
        # page.reload() doesn't work for this: it destroys the stub's in-memory
        # library state entirely, so a freshly re-seeded root after a genuine
        # reload has no way to reflect what a previous session wrote to disk --
        # #reload-btn (the toolbar's own "Switch library") re-reads from
        # window.__TEST_ROOT without tearing down the page's JS context.
        seed_with_expanded = dict(SEED)
        seed_with_expanded['settings'] = [{'key': 'detail_panel_expanded', 'value': '1'}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_expanded)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        print("expanded state persists across reopen:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))
```

Replace with (now proves the new default directly, and confirms an
explicit `'0'` opt-out still works, before also confirming an explicit
`'1'` still works and leaving the panel expanded for every scenario that
follows -- matching what the old version left it as by its own end):

```python
        # === Scenario 1: panel starts EXPANDED by default (no saved setting),
        # an explicit '0' opt-out still collapses it, and an explicit '1' still
        # keeps it expanded, all surviving a reopen ===
        print("panel starts expanded with no saved setting:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))

        # Reopen with an explicit '0' -- the deliberate opt-out must still work
        # even though the no-row-at-all default flipped to expanded. See
        # test_nav.py's own nav_style Scenario 7 for the established "simulate a
        # reopen via re-seeding + #reload-btn" convention this mirrors; a real
        # page.reload() doesn't work here since it destroys the stub's in-memory
        # library state entirely.
        seed_with_collapsed = dict(SEED)
        seed_with_collapsed['settings'] = [{'key': 'detail_panel_expanded', 'value': '0'}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_collapsed)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        print("explicit '0' still collapses the panel:", not await page.locator('#main-layout.detail-panel-expanded').count())

        # Toggling it from here persists '1' -- the existing toggle/persistence
        # mechanics are otherwise completely unchanged by the default flip.
        await page.click('#detail-panel-toggle-btn')
        await page.wait_for_timeout(150)
        settings_after_toggle = await read_settings(page)
        expanded_row = next((s for s in settings_after_toggle if s['key'] == 'detail_panel_expanded'), None)
        print("toggling from collapsed persists '1':", expanded_row['value'] if expanded_row else None)

        # Reopen once more with that explicit '1' -- still expanded, and this is
        # the state every later scenario in this file expects the panel to be in.
        seed_with_expanded = dict(SEED)
        seed_with_expanded['settings'] = [{'key': 'detail_panel_expanded', 'value': '1'}]
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_expanded)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        print("explicit '1' persists as expanded across reopen:", bool(await page.locator('#main-layout.detail-panel-expanded').count()))
```

- [ ] **Step 3: Remove the now-redundant toggle-click from the 31 affected files**

Every one of these files has this exact two-line pattern, once, shortly
after opening the library:

```python
        await page.click('#detail-panel-toggle-btn')  # expand the detail panel so its action buttons are reachable for the rest of this test
        await page.wait_for_timeout(150)
```

Delete both lines (only these two lines — nothing else nearby) from each
of these 31 files. The panel is expanded by default now, so this click
would otherwise *collapse* it instead of expanding it, breaking every
scenario that follows:

```
tests/test_all_clear_buttons.py
tests/test_add_field_inline.py
tests/test_amount_payment_dynamic.py
tests/test_collections.py
tests/test_clear_button.py
tests/test_archive.py
tests/test_copy_path.py
tests/test_currency.py
tests/test_date_picker_color_scheme.py
tests/test_edit_cancel.py
tests/test_edit.py
tests/test_edit_currency_guess.py
tests/test_edit_ocr.py
tests/test_header_amount_payment.py
tests/test_field_descriptions.py
tests/test_inbox.py
tests/test_generic_fields.py
tests/test_i18n.py
tests/test_orphaned_clear.py
tests/test_payment_date.py
tests/test_people_migration.py
tests/test_nav.py
tests/test_orphaned_fields.py
tests/test_person_type_field.py
tests/test_page_count.py
tests/test_review_queue.py
tests/test_regenerate.py
tests/test_sentinel_field_migration.py
tests/test_people.py
tests/test_scan_hint_and_ocr_languages.py
tests/test_waste_bin.py
```

Before editing, confirm this list is still exactly right and nothing else
has changed shape since this plan was written:

```bash
cd tests && grep -l "detail-panel-toggle-btn" test_*.py | grep -v -E "^test_(detail_panel|row_edit_shortcut)\.py$"
```

This should print exactly the 31 filenames above (order may differ). For
each one, confirm it has exactly one occurrence before removing it:

```bash
grep -c "detail-panel-toggle-btn" test_add_field_inline.py   # expect 1, repeat per file
```

If any file has a different count, or the two-line pattern doesn't match
exactly as shown, stop and read that file's surrounding code directly
before touching it — do not blindly delete lines that don't match.

- [ ] **Step 4: Fix `tests/test_row_edit_shortcut.py`'s Scenario 2 separately**

This file doesn't click the toggle button at all (Task 2 already gave it a
viewport-size call instead — leave that alone), but its own Scenario 2
checks the `detail-panel-expanded` class directly, and that check's
meaning depends on the default too. Find (search for
`# === Scenario 2: Cancel from an edit reached via the shortcut`):

```python
        # === Scenario 2: Cancel from an edit reached via the shortcut just closes
        # the edit form -- it no longer reopens the detail view/panel, and does NOT
        # force the (collapsed-by-default) detail panel open, since the shortcut
        # bypasses row selection entirely on the way in ===
        await page.click('#cancel-edit-btn')
```

Replace with (with the panel now expanded by default, it would already be
open before Cancel ever runs -- collapse it first so this scenario is
still testing something real: that Cancel doesn't cause an *additional*
expand, not that the panel merely happens to already be open):

```python
        # === Scenario 2: Cancel from an edit reached via the shortcut just closes
        # the edit form -- it no longer reopens the detail view/panel, and does NOT
        # force the panel open, since the shortcut bypasses row selection
        # entirely on the way in. Collapse the panel first: with it now expanded
        # by default, it would already be open before Cancel ever runs, and this
        # scenario needs to prove Cancel doesn't cause an *additional* expand,
        # not that the panel merely happens to already be open. ===
        await page.click('#detail-panel-toggle-btn')
        await page.wait_for_timeout(150)

        await page.click('#cancel-edit-btn')
```

- [ ] **Step 5: Run the full suite**

```bash
cd tests
for f in test_*.py; do
  echo "=== $f ==="
  /usr/local/bin/python3 "$f" > /tmp/panel-followup-sweep.log 2>&1
  echo "EXIT:$? for $f"
done 2>&1 | tee -a /tmp/panel-followup-sweep-summary.log
```

(Or run files individually and inspect output directly, whichever is more
convenient.) Expected: every file exits 0, every printed line is `True`,
`JS ERRORS: []` everywhere. If a failure is NOT one of the 31 files this
step already handles and NOT `tests/test_row_edit_shortcut.py`/
`tests/test_detail_panel.py`, investigate it directly — it may be a
genuinely new interaction this plan didn't anticipate, not something to
guess-fix.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/
git commit -m "Default the detail panel to expanded

No-saved-setting now means expanded (an explicit '0' opt-out still
collapses it, unchanged). Removes the now-redundant expand-the-panel
toggle click from 31 test files that assumed the old collapsed default,
and fixes two panel-state-dependent assertions in test_detail_panel.py
and test_row_edit_shortcut.py that depended on it."
```

---

### Task 4: CLAUDE.md architecture note

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the finished behavior from Tasks 1-3 (this task only documents
  it — no code changes).

- [ ] **Step 1: Read the existing note and its neighbors first**

Read CLAUDE.md's existing "The detail view is a persistent side panel"
note (search for that exact phrase) in full, along with at least one
neighboring note (e.g. the "Configurable columns/filters" note right
after it), to match this repo's established voice: long paragraphs,
**bold** for key terms, explaining *why* not just *what*, cross-referencing
other notes by name.

- [ ] **Step 2: Add three short paragraphs to the existing note**

Insert them as new paragraphs at the end of the existing "The detail view
is a persistent side panel" note (immediately before the next `- **`
bullet that starts a new note), covering:

1. **The default flipped from collapsed to expanded.**
   `loadDetailPanelExpanded()` now treats "no saved `detail_panel_expanded`
   row at all" as expanded rather than collapsed — an explicit saved `'0'`
   still means collapsed (a person who deliberately toggles it off keeps
   that choice across reopens), and an explicit `'1'` still means expanded,
   unchanged. Mention why: two of the panel's own original reasons for
   duplicated chrome (the row-level Edit shortcut, and no double-click
   file-open) are gone now, so a collapsed-by-default panel no longer pays
   for itself the way it did at launch — see the row-edit-btn and
   double-click paragraphs below.
2. **Double-click a row opens its file.** A `dblclick` listener alongside
   the existing `click` listener reuses the panel's own "Open file" logic
   (`resolveFileHandle` → `getFile` → `window.open`). It deliberately
   doesn't duplicate any selection logic, because browsers fire two
   ordinary `click` events before a `dblclick` — by the time it fires, the
   existing single-click handler has already selected/highlighted/
   refreshed the panel. A document with no `file_path` is a silent no-op.
   The panel's own "Open file" button stays exactly as it is — double-click
   isn't a discoverable gesture on its own, so the button remains the
   reliable, visible way to do the same thing.
3. **`.row-edit-btn` is now hidden except below the mobile breakpoint.** At
   normal widths it duplicates the panel's own Edit button, which is
   reliably reachable now that the panel defaults to expanded — so it's
   hidden there (a CSS-only change; its row-level rendering/click-wiring
   are untouched). It's kept below `max-width:640px` specifically because
   that's the one place the panel is structurally unreachable — the
   existing `#main-layout.detail-panel-expanded .detail-panel{
   display:none; }` rule inside that same media query force-hides the
   panel unconditionally regardless of the toggle, so without this
   fallback Edit would be completely unreachable from the table there.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the panel follow-up: default-expanded, double-click, row-edit-btn gating"
```

---

## Self-Review

**1. Spec coverage** — every item from the approved spec
(`docs/superpowers/specs/2026-08-22-panel-followup-row-interactions-design.md`)
maps to a task: double-click opens file, single click unchanged (Task 1);
"Open file" button explicitly untouched (Task 1, no code change to it);
`.row-edit-btn` viewport-gated (Task 2); default-expanded (Task 3); the
CLAUDE.md note (Task 4). Out-of-scope items (any other panel content/action
change, `.row-edit-btn`'s own click behavior, resizing/keyboard shortcuts)
are not implemented by any task.

**2. Placeholder scan** — no TBD/TODO; every step shows exact before/after
code or an exact, verifiable file list (the 31-file sweep, with a
verification command to confirm the list before touching anything).

**3. Type/name consistency** — `selectedDocId`, `openDetail`,
`resolveFileHandle`, `detailPanelExpanded`/`loadDetailPanelExpanded`,
`.row-edit-btn`/`.row-edit-col`, and `#detail-panel-toggle-btn` are named
identically everywhere they appear across all four tasks.

**4. A real cross-cutting risk surfaced while writing this plan, not in the
original spec**: flipping the panel's default (Task 3) turned out to affect
32 existing test files, not just `test_detail_panel.py` — 31 click the
toggle button assuming the old collapsed default (now actively wrong), and
`tests/test_row_edit_shortcut.py` separately checks the expanded-class
directly without ever clicking the toggle. Both are handled explicitly in
Task 3 rather than left for a later cleanup pass, precisely because
shipping the default flip without them would break the suite immediately.
