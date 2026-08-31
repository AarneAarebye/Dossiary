# Default Reminder via Right-Click Context Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single, always-available default reminder to every document,
reachable directly from the row's right-click context menu, set via an
Outlook-style quick-pick flyout (Today / Tomorrow / Next week / Custom
date…) rather than a form.

**Architecture:** The default reminder is an ordinary, reserved `fields`
row (`name: 'Reminder'`, `type: 'reminder'`), auto-created once per
library and never attached to any document type's configured field list.
This means it's picked up by `checkReminders()`'s existing due-reminder
scan and rendered by the Edit form's existing orphaned-field display with
zero changes to either — the whole feature is new UI (a context-menu
action + a floating flyout) plus two small write functions on top of
already-shipped machinery.

**Tech Stack:** Same as the rest of `dossiary.html` — vanilla JS in a
single top-level IIFE, sql.js, Playwright test suite in `tests/`.

## Global Constraints

- The reserved field name is exactly `'Reminder'` (capital R, singular) —
  used consistently as the literal string everywhere: the `fields.name`
  value, the reserved-name check, and every `fieldNameToId['Reminder']`
  lookup.
- `'Reminder'` is never added to `document_type_fields` by any code in
  this plan — it must never appear as a "configured" field for any type,
  by design (see the design spec's "Data model" section).
- All new debug/test-only hooks follow the established `window.__DEBUG_*`
  naming convention (per the final review of the shipped reminder-fields
  feature) — never expose an unprefixed production global.
- Every new user-facing string needs an entry in all six `STRINGS` blocks
  (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`) — this repo's
  `test_i18n_coverage.py` is a hard gate that fails the whole suite if
  any language is missing a key. `zh-Hant` text is hand-converted from
  the finished `zh-Hans` wording, matching this repo's own established
  convention (verify near-identical existing keys for the exact character
  substitutions, e.g. `reminderSnooze1Week`'s `周`→`週`).
- Every write in this feature is triggered by an explicit person action
  (a flyout click) — no automatic or background writes, matching this
  app's own "Working conventions" principle already documented in
  `CLAUDE.md`.

---

## File Structure

Everything lives in the existing `dossiary.html` single-file app plus one
new test file:

- `dossiary.html` — modified in place (migration function, reserved-name
  list, two new write functions, one new `buildDetailActions()` entry,
  new CSS, new i18n keys). No new files inside the app itself; this repo
  deliberately stays single-file.
- `tests/test_default_reminder.py` — new, dedicated test file for this
  feature, following this repo's established one-file-per-feature
  convention (matching `test_reminders.py`, `test_collections.py`, etc.).
- `CLAUDE.md` / `tests/CLAUDE.md` — documentation, Task 3.

---

### Task 1: The default Reminder field — auto-creation, reserved name, and write/clear functions

**Files:**
- Modify: `dossiary.html` (new `migrateDefaultReminderField()`, its two
  call sites in `initNewLibrary()`/`loadDb()`, the reserved-name array in
  `addInlineCustomField()`, new `setDefaultReminder()`/
  `clearDefaultReminder()` functions, two new `__DEBUG_*` test hooks)
- Test: `tests/test_default_reminder.py` (new file)

**Interfaces:**
- Consumes: `fieldDefs`/`fieldNameToId`/`nextFieldId` (existing
  module-level state, already populated by `loadFieldDefs()`), `allDocs`
  (existing, each entry has `.id`, `.customFields`), `db.run(sql,
  params)`/`persistDb()`/`render()`/`openDetail(id)` (existing).
- Produces: `setDefaultReminder(documentId, dateIso)` — async, no return
  value, writes/updates the Reminder field's value for that document.
  `clearDefaultReminder(documentId)` — async, no return value, removes
  it. Both are consumed directly by Task 2's flyout UI. `fieldNameToId['Reminder']`
  is guaranteed non-`undefined` after `migrateDefaultReminderField()` has
  run (called from both `initNewLibrary()` and `loadDb()`), which Task 2
  relies on.

- [ ] **Step 1: Write the failing test**

Create `tests/test_default_reminder.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

SEED = {
    "documents": [
        {
            "id": 1, "title": "Insurance Policy", "category": "Finance", "document_type": "Policy",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": None, "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [], "settings": [],
}

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)

        # === Scenario 1: the 'Reminder' field is auto-created for a fresh library
        # open, idempotently -- reopening doesn't duplicate or otherwise disturb it ===
        field_row = await page.evaluate("window.__DEBUG_findFieldByName('Reminder')")
        print("'Reminder' field auto-created with type 'reminder':", field_row is not None and field_row['type'] == 'reminder')

        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        field_row_after_reopen = await page.evaluate("window.__DEBUG_findFieldByName('Reminder')")
        print("re-opening the same library doesn't duplicate the field (same id):", field_row_after_reopen is not None and field_row_after_reopen['id'] == field_row['id'])

        # === Scenario 2: 'Reminder' is rejected as a name when creating a custom
        # field inline, matching the existing reserved-name behavior ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'Policy')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        await page.fill('#f-new-field-name', 'Reminder')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(100)
        validation_text = await page.locator('#f-new-field-status').inner_text()
        print("'Reminder' is rejected as a reserved custom-field name:", 'reserved' in validation_text.lower() or 'Reminder' in validation_text)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 3: setDefaultReminder()/clearDefaultReminder() write/remove
        # the value correctly, in memory and persisted, and it participates in
        # checkReminders() exactly like any other reminder-type field ===
        result = await page.evaluate("""
            (async () => {
                await window.__DEBUG_setDefaultReminder(1, todayIsoDate());
                const inMemory = allDocs.find(d => d.id === 1).customFields['Reminder'];
                const due = checkReminders();
                const includesDoc1 = due.some(r => r.documentId === 1 && r.fieldName === 'Reminder');
                return { inMemory, includesDoc1 };
            })()
        """)
        print("setDefaultReminder() updates the document's in-memory customFields:", result['inMemory'] == True or bool(result['inMemory']))
        print("a default reminder due today is included by checkReminders():", result['includesDoc1'])

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        reminder_field_id = field_row['id']
        saved_value = next((v['value'] for v in persisted['document_field_values'] if v['document_id'] == 1 and v['field_id'] == reminder_field_id), None)
        print("the value is actually persisted to document_field_values:", saved_value is not None)

        await page.evaluate("window.__DEBUG_clearDefaultReminder(1)")
        await page.wait_for_timeout(100)
        result2 = await page.evaluate("""
            () => {
                const inMemory = allDocs.find(d => d.id === 1).customFields['Reminder'];
                const due = checkReminders();
                const stillIncluded = due.some(r => r.documentId === 1 && r.fieldName === 'Reminder');
                return { inMemory, stillIncluded };
            }
        """)
        print("clearDefaultReminder() removes it from in-memory customFields:", not result2['inMemory'])
        print("and checkReminders() no longer includes it:", not result2['stillIncluded'])

        persisted2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        saved_value_after_clear = next((v for v in persisted2['document_field_values'] if v['document_id'] == 1 and v['field_id'] == reminder_field_id), None)
        print("and the persisted row is actually gone, not just blanked:", saved_value_after_clear is None)

        # === Scenario 4: a document with a default reminder value shows it as an
        # orphaned, editable field in the Edit form, regardless of its type, since
        # 'Reminder' is never attached to document_type_fields ===
        await page.evaluate("window.__DEBUG_setDefaultReminder(1, todayIsoDate())")
        await page.wait_for_timeout(100)
        await page.click(f'tr[data-id="1"]')
        await page.wait_for_timeout(150)
        await page.click('#edit-doc-btn')  # the detail panel's own Edit button, wired via actionIdByKey['edit'] = 'edit-doc-btn' in openDetail()
        await page.wait_for_timeout(150)
        orphaned_reminder = page.locator('[data-dynamic-field="Reminder"].field-orphaned')
        print("the Reminder field shows as an orphaned, editable field in Edit:", await orphaned_reminder.count() == 1)
        orphaned_input = orphaned_reminder.locator('input')
        orphaned_value = await orphaned_input.input_value()
        print("with the correct saved value pre-filled:", orphaned_value == await page.evaluate("todayIsoDate()"))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_default_reminder.py`
Expected: fails immediately — `window.__DEBUG_findFieldByName is not a
function` (or similar), since none of `migrateDefaultReminderField()`,
the reserved-name entry, `setDefaultReminder()`/`clearDefaultReminder()`,
or the debug hooks exist yet.

- [ ] **Step 3: Implement**

In `dossiary.html`, find `migratePeopleToGenericField()` (search for
`function migratePeopleToGenericField(){`) and add a new function
immediately after its closing brace:

```js
  // The default, always-available reminder every document can carry, reachable
  // directly from the row context menu (see buildDetailActions()'s 'default-reminder'
  // action) rather than requiring a person to configure a reminder-type field for
  // their document's type first. It's an ordinary reminder-type field under the hood
  // -- nothing about checkReminders() or the orphaned-field display in the Edit form
  // needs to change to support it -- the only thing special about it is that this
  // migration ensures it always exists, and it's a reserved name (see
  // addInlineCustomField()'s own reserved-name check) so nobody can accidentally
  // create a colliding custom field. Deliberately NEVER added to document_type_fields
  // for any type -- see this feature's own design spec for why: a person can still
  // manually attach it via Field Settings if they want it to appear as a normal,
  // non-orphaned field for some type, but this app never does that automatically.
  function migrateDefaultReminderField(){
    loadFieldDefs(); // ensure fieldDefs/fieldNameToId/nextFieldId reflect the DB before we touch either
    if(fieldNameToId['Reminder'] !== undefined) return; // already migrated

    const id = nextFieldId++;
    db.run('INSERT INTO fields (id, name, type, show_as_column, autocomplete) VALUES (?, ?, ?, ?, ?)',
      [id, 'Reminder', 'reminder', 0, 0]);
    fieldDefs.push({ id, name: 'Reminder', type: 'reminder', showAsColumn: false, autocomplete: false });
    fieldNameToId['Reminder'] = id;
  }
```

Find the two existing call sites for `migratePeopleToGenericField();`
(search for that exact string — one inside `initNewLibrary()`, one inside
`loadDb()`) and add a `migrateDefaultReminderField();` line immediately
after each, matching the existing comment style:

```js
      migrateSentinelFieldsToGeneric(); // seeds Payment method/Amount/Currency as available fields from the start
      migratePeopleToGenericField(); // seeds People as an available person-type field from the start
      migrateDefaultReminderField(); // seeds the always-available default Reminder field from the start
      migrateTextFieldsAutocompleteDefault(); // no-op here (no text fields exist yet beyond the sentinels above), but marks this library as migrated
```

(in `initNewLibrary()`), and:

```js
    migrateSentinelFieldsToGeneric(); // one-time; no-op if this library was already migrated
    migratePeopleToGenericField(); // one-time; no-op if this library was already migrated
    migrateDefaultReminderField(); // one-time; no-op if this library was already migrated
    migrateTextFieldsAutocompleteDefault(); // one-time; no-op if this library was already migrated
```

(in `loadDb()`).

Find `addInlineCustomField()`'s reserved-name check (search for
`['People', 'Amount', 'Payment method', ...FIELD_DESCRIPTION_BUILTIN_NAMES]`)
and add `'Reminder'` to the literal array:

```js
    if(['People', 'Amount', 'Payment method', 'Reminder', ...FIELD_DESCRIPTION_BUILTIN_NAMES].includes(name)){
```

Find `toggleArchived()` (search for `async function toggleArchived(id){`)
and add the two new write functions immediately after its closing brace:

```js
  // Writes/updates the single default-reminder value for a document, following
  // the exact delete-then-insert pattern saveEditedDocument() already uses for
  // every other custom field value (see that function's own document_field_values
  // handling). Mutates the same object allDocs already holds for this document
  // (matching toggleArchived()'s own approach) so a following render()/openDetail()
  // picks up the change with no extra lookup needed.
  async function setDefaultReminder(documentId, dateIso){
    const d = allDocs.find(x => x.id === documentId);
    if(!d) return;
    const fieldId = fieldNameToId['Reminder'];
    db.run('DELETE FROM document_field_values WHERE document_id = ? AND field_id = ?', [documentId, fieldId]);
    db.run('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [documentId, fieldId, dateIso]);
    d.customFields = d.customFields || {};
    d.customFields['Reminder'] = dateIso;
    await persistDb();
    render();
    openDetail(documentId); // refresh the panel so it reflects the new orphaned-field value if it's currently shown
  }

  // The delete half of setDefaultReminder() above -- removes the value entirely
  // rather than writing a blank one, so the field goes back to not being an
  // orphaned field at all for this document (no value means nothing to orphan).
  async function clearDefaultReminder(documentId){
    const d = allDocs.find(x => x.id === documentId);
    if(!d) return;
    const fieldId = fieldNameToId['Reminder'];
    db.run('DELETE FROM document_field_values WHERE document_id = ? AND field_id = ?', [documentId, fieldId]);
    if(d.customFields) delete d.customFields['Reminder'];
    await persistDb();
    render();
    openDetail(documentId);
  }
```

Add two test-only debug hooks. Find the existing block of `__DEBUG_*`
hooks (search for `window.__DEBUG_reminderSnoozesRawRows`) and add two
more immediately after it:

```js
  // Test-only: looks up a fields row by name, for asserting migrateDefaultReminderField()'s
  // own behavior without a dedicated production API for it (nothing else in the app
  // needs to look up an arbitrary field by name from outside its own closure).
  window.__DEBUG_findFieldByName = (name) => fieldDefs.find(f => f.name === name) || null;
  window.__DEBUG_setDefaultReminder = setDefaultReminder;
  window.__DEBUG_clearDefaultReminder = clearDefaultReminder;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_default_reminder.py`
Expected: every scenario prints `True`, `JS ERRORS: []`.

- [ ] **Step 5: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `PASS` (this task adds no new i18n keys, but confirm nothing
broke).

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_default_reminder.py
git commit -m "Add the default Reminder field, auto-created and reserved

An ordinary reminder-type field, always present via migrateDefaultReminderField(),
never attached to any document type's configured fields -- checkReminders()
and the Edit form's orphaned-field display already handle it correctly
with zero changes. setDefaultReminder()/clearDefaultReminder() write and
remove its value; Task 2 wires these to the row context menu."
```

---

### Task 2: Context menu action and quick-pick flyout

**Files:**
- Modify: `dossiary.html` (new `buildDetailActions()` entry, new CSS for
  the flyout, new `let openReminderFlyout` module state + its
  `closeModal()` cleanup, new i18n keys)
- Test: `tests/test_default_reminder.py` (extend)

**Interfaces:**
- Consumes: `setDefaultReminder()`/`clearDefaultReminder()` (Task 1),
  `addDaysToIsoDate()`/`todayIsoDate()`/`formatDate()` (existing),
  `buildDetailActions(id, d)` (existing, shared by the panel and
  `showRowContextMenu()`).
- Produces: nothing new consumed by later tasks — this is the
  user-facing surface of the feature.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_default_reminder.py`, before the final
`print("JS ERRORS:"...)`/`await browser.close()` block (move those two
lines to after this new code):

```python
        # === Scenario 5: the context menu shows "Add reminder" for a document with
        # no default reminder, and the flyout offers Today/Tomorrow/Next week/Custom
        # date but not Clear reminder ===
        await page.evaluate("window.__DEBUG_clearDefaultReminder(1)")
        await page.wait_for_timeout(100)
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        add_reminder_item = page.locator('.row-context-menu-item', has_text='Add reminder')
        print("context menu shows 'Add reminder' when none is set:", await add_reminder_item.count() == 1)
        await add_reminder_item.click()
        await page.wait_for_timeout(150)

        # The row context menu's own generic closeMenu() should have removed the
        # .row-context-menu itself, but NOT the flyout it just opened -- the same
        # "separate DOM element, tracked separately" property Add to Collection's
        # own picker already relies on.
        context_menu_gone = await page.locator('.row-context-menu').count() == 0
        flyout_present = await page.locator('.reminder-flyout').count() == 1
        print("the row context menu closes but the flyout it opened stays open:", context_menu_gone and flyout_present)

        flyout_options = await page.locator('.reminder-flyout-option').all_inner_texts()
        has_today = any('Today' in o for o in flyout_options)
        has_tomorrow = any('Tomorrow' in o for o in flyout_options)
        has_next_week = any('Next week' in o for o in flyout_options)
        has_custom = any('Custom date' in o for o in flyout_options)
        has_clear = any('Clear reminder' in o for o in flyout_options)
        print("flyout offers Today/Tomorrow/Next week/Custom date:", has_today and has_tomorrow and has_next_week and has_custom)
        print("but not Clear reminder, since none is set yet:", not has_clear)

        # === Scenario 6: choosing "Today" sets it immediately and updates the
        # context menu's label on the next right-click ===
        await page.locator('.reminder-flyout-option', has_text='Today').click()
        await page.wait_for_timeout(150)
        flyout_gone = await page.locator('.reminder-flyout').count() == 0
        print("choosing a preset closes the flyout:", flyout_gone)

        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        reminder_set_item = page.locator('.row-context-menu-item', has_text='Reminder:')
        print("the menu item now reads 'Reminder: <date>':", await reminder_set_item.count() == 1)

        # === Scenario 7: Custom date reveals a hidden date input with a min of
        # tomorrow, matching the reminders modal's own already-established pattern ===
        await reminder_set_item.click()  # reopens the flyout (now to CHANGE the existing reminder)
        await page.wait_for_timeout(150)
        custom_date_input = page.locator('.reminder-flyout-custom-date')
        custom_date_visible_before = await custom_date_input.is_visible()
        print("the custom-date input starts hidden:", not custom_date_visible_before)
        await page.locator('.reminder-flyout-option', has_text='Custom date').click()
        await page.wait_for_timeout(100)
        custom_date_visible_after = await custom_date_input.is_visible()
        print("choosing 'Custom date…' reveals it:", custom_date_visible_after)
        min_attr = await custom_date_input.get_attribute('min')
        expected_min = await page.evaluate("addDaysToIsoDate(todayIsoDate(), 1)")
        print("its min attribute is tomorrow:", min_attr == expected_min)
        color_scheme = await custom_date_input.evaluate("el => getComputedStyle(el).colorScheme")
        print("and it's styled for dark mode:", color_scheme == 'dark')

        await custom_date_input.fill('2026-12-25')
        await custom_date_input.dispatch_event('change')
        await page.wait_for_timeout(150)
        flyout_gone_after_custom = await page.locator('.reminder-flyout').count() == 0
        print("confirming a custom date closes the flyout:", flyout_gone_after_custom)

        # === Scenario 8: Clear reminder removes it and the label reverts ===
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        await page.locator('.row-context-menu-item', has_text='Reminder:').click()
        await page.wait_for_timeout(150)
        await page.locator('.reminder-flyout-option', has_text='Clear reminder').click()
        await page.wait_for_timeout(150)

        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        add_reminder_again = page.locator('.row-context-menu-item', has_text='Add reminder')
        print("after clearing, the menu item reverts to 'Add reminder':", await add_reminder_again.count() == 1)
        await page.click('tr[data-id="1"]', button='right')  # close the reopened menu

        # === Scenario 9: setting a reminder via the flyout produces state
        # checkReminders() correctly includes, an end-to-end confirmation that the
        # UI-triggered write matches Task 1's own function-level behavior ===
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="1"]', button='right')
        await page.wait_for_timeout(150)
        await page.locator('.row-context-menu-item', has_text='Add reminder').click()
        await page.wait_for_timeout(150)
        await page.locator('.reminder-flyout-option', has_text='Today').click()
        await page.wait_for_timeout(150)
        due_after_ui_set = await page.evaluate("checkReminders().some(r => r.documentId === 1 && r.fieldName === 'Reminder')")
        print("a reminder set via the flyout is picked up by checkReminders():", due_after_ui_set)

        # === Scenario 10: buildDetailActions() is shared with the detail panel --
        # the same action, and its flyout, must also work from there, not just the
        # row context menu, confirming the actionIdByKey entry added in Step 3 ===
        await page.evaluate("window.__DEBUG_clearDefaultReminder(1)")
        await page.wait_for_timeout(100)
        await page.click('tr[data-id="1"]')  # left-click selects the row and opens the panel
        await page.wait_for_timeout(150)
        panel_btn = page.locator('#default-reminder-btn')
        panel_btn_text = await panel_btn.inner_text()
        print("the detail panel shows a real 'Add reminder' button, not id=\"undefined\":", 'Add reminder' in panel_btn_text)
        await panel_btn.click()
        await page.wait_for_timeout(150)
        await page.locator('.reminder-flyout-option', has_text='Tomorrow').click()
        await page.wait_for_timeout(150)
        panel_btn_after = page.locator('#default-reminder-btn')
        panel_btn_text_after = await panel_btn_after.inner_text()
        print("choosing a preset from the panel button updates its own label too:", 'Reminder:' in panel_btn_text_after)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_default_reminder.py`
Expected: fails at `add_reminder_item` (count 0) or an equivalent early
assertion, since the context menu has no "Add reminder" item yet.

- [ ] **Step 3: Implement**

In `dossiary.html`, find `let openDocCollectionMenu = null;` (search for
that exact string) and add a new module-level variable right after it:

```js
  let openReminderFlyout = null; // same "lives outside modalRoot, tracked separately" reasoning as openDocCollectionMenu just above
```

Find `closeModal()`'s existing `openDocCollectionMenu` cleanup line
(search for `if(openDocCollectionMenu){ openDocCollectionMenu.remove(); openDocCollectionMenu = null; }`)
and add a matching line for the new flyout right after it:

```js
    if(openDocCollectionMenu){ openDocCollectionMenu.remove(); openDocCollectionMenu = null; }
    if(openReminderFlyout){ openReminderFlyout.remove(); openReminderFlyout = null; }
```

Find `buildDetailActions(id, d)`'s `if(!d.deleted){` block (search for
`actions.push({ key: 'edit', label: t('detailEdit')`) and add a new
action descriptor immediately after the `edit` action, before
`regen-thumb`/`archive-toggle`:

```js
      actions.push({ key: 'edit', label: t('detailEdit'), variant: null, onClick: () => openEditForm(id) });
      actions.push({
        key: 'default-reminder',
        label: d.customFields && d.customFields['Reminder']
          ? t('contextMenuReminderSet', {date: formatDate(d.customFields['Reminder'])})
          : t('contextMenuAddReminder'),
        variant: null,
        // Same "read e.target's rect before removing anything, positioned via a
        // floating element appended to document.body outside modalRoot/the row
        // context menu" pattern add-to-collection already uses just below -- see
        // that action's own comment for why the ordering (call onClick, THEN close
        // the menu that triggered it) matters for this to work.
        onClick: (e) => {
          e.stopPropagation();
          const rect = e.target.getBoundingClientRect();
          const hasReminder = !!(d.customFields && d.customFields['Reminder']);
          const flyout = document.createElement('div');
          flyout.className = 'reminder-flyout';
          flyout.style.top = (rect.bottom + window.scrollY + 6) + 'px';
          flyout.style.left = (rect.left + window.scrollX) + 'px';

          const renderChoices = () => {
            flyout.innerHTML = `
              <button type="button" class="reminder-flyout-option" data-choice="today">${t('defaultReminderToday')}</button>
              <button type="button" class="reminder-flyout-option" data-choice="tomorrow">${t('defaultReminderTomorrow')}</button>
              <button type="button" class="reminder-flyout-option" data-choice="nextweek">${t('defaultReminderNextWeek')}</button>
              <button type="button" class="reminder-flyout-option" data-choice="custom">${t('defaultReminderCustomDate')}</button>
              ${hasReminder ? `<button type="button" class="reminder-flyout-option" data-choice="clear">${t('defaultReminderClear')}</button>` : ''}
            `;
            flyout.querySelectorAll('.reminder-flyout-option').forEach(btn => {
              btn.addEventListener('click', async () => {
                const choice = btn.dataset.choice;
                if(choice === 'today'){ await setDefaultReminder(id, todayIsoDate()); removeFlyout(); }
                else if(choice === 'tomorrow'){ await setDefaultReminder(id, addDaysToIsoDate(todayIsoDate(), 1)); removeFlyout(); }
                else if(choice === 'nextweek'){ await setDefaultReminder(id, addDaysToIsoDate(todayIsoDate(), 7)); removeFlyout(); }
                else if(choice === 'clear'){ await clearDefaultReminder(id); removeFlyout(); }
                else if(choice === 'custom'){ renderCustomDate(); }
              });
            });
          };

          const renderCustomDate = () => {
            flyout.innerHTML = `
              <input type="date" class="reminder-flyout-custom-date" min="${addDaysToIsoDate(todayIsoDate(), 1)}" />
            `;
            const input = flyout.querySelector('.reminder-flyout-custom-date');
            input.focus();
            input.addEventListener('change', async () => {
              if(!input.value) return;
              // Defensive, same reasoning as the reminders modal's own custom-snooze-date
              // handler: a native date input's min attribute can be bypassed by a manually
              // typed value in some browsers, so re-check here too.
              if(input.value <= todayIsoDate()) return;
              await setDefaultReminder(id, input.value);
              removeFlyout();
            });
          };

          const removeFlyout = () => {
            flyout.remove();
            if(openReminderFlyout === flyout) openReminderFlyout = null;
            document.removeEventListener('click', outsideClick);
          };
          const outsideClick = (evt) => { if(!flyout.contains(evt.target)) removeFlyout(); };

          renderChoices();
          document.body.appendChild(flyout);
          openReminderFlyout = flyout;
          setTimeout(() => document.addEventListener('click', outsideClick), 0);
        },
      });
```

`buildDetailActions()` is shared by both the row context menu and the
detail panel — the context menu iterates its returned array generically,
but `openDetail()`'s own panel rendering maps each action's `key` to a
fixed button `id` via a hardcoded `actionIdByKey` object, and wires click
listeners the same way. Without adding an entry for the new
`'default-reminder'` key there, the panel would render a button with
`id="undefined"` instead of a real, clickable one. Find `actionIdByKey`
(search for `const actionIdByKey = {`) and add the new entry:

```js
    const actionIdByKey = {
      'open-file': 'open-file-btn', 'open-original': 'open-original-btn', 'edit': 'edit-doc-btn',
      'default-reminder': 'default-reminder-btn',
      'regen-thumb': 'regen-thumb-btn', 'archive-toggle': 'archive-toggle-btn', 'review-toggle': 'review-toggle-btn',
      'add-to-collection': 'add-to-collection-btn', 'remove-from-collection': 'remove-from-collection-btn',
      'delete-toggle': 'delete-toggle-btn',
    };
```

This is the only change needed for the panel — its button-rendering
template (`` `<button${cls} id="${actionIdByKey[a.key]}">${a.label}</button>` ``)
and its click-wiring loop (`` detailActions.forEach(a => { const btnEl = el(actionIdByKey[a.key]); if(btnEl) btnEl.addEventListener('click', a.onClick); }); ``)
are both already fully generic and need no further edits — adding the
map entry makes the panel pick up the new action automatically,
rendering "Add reminder" (or "Reminder: {date}") as a real panel button
too, consistent with every other action `buildDetailActions()` already
feeds to both surfaces.

Add the new CSS. Find `.reminder-snooze-custom-date{ color-scheme:dark; }`
(the last line of the reminders modal's own CSS block) and add the new
rules right after it:

```css
  .reminder-snooze-custom-date{ color-scheme:dark; }
  .reminder-flyout{
    position:absolute; z-index:50; background:var(--panel); border:1px solid var(--line);
    border-radius:var(--radius); padding:6px; min-width:160px; box-shadow:0 8px 24px rgba(0,0,0,0.4);
  }
  .reminder-flyout-option{ display:block; width:100%; text-align:left; padding:8px 10px; background:transparent; border:none; color:var(--text); font-family:var(--font-mono); font-size:12.5px; cursor:pointer; border-radius:var(--radius); }
  .reminder-flyout-option:hover{ background:rgba(79,224,166,0.1); color:var(--phosphor); }
  .reminder-flyout-custom-date{
    background:var(--ink-2); border:1px solid var(--line); color:var(--text); color-scheme:dark;
    font-family:var(--font-mono); font-size:11.5px; padding:5px 7px; border-radius:var(--radius); width:100%;
  }
```

Add the new i18n keys to all six `STRINGS` blocks. Find
`reminderSnoozeCustom:` in each language block (search for that string —
it appears once per language, six times total) and add the new keys
right after it on the same line:

- `en`: `contextMenuAddReminder: 'Add reminder', contextMenuReminderSet: 'Reminder: {date}', defaultReminderToday: 'Today', defaultReminderTomorrow: 'Tomorrow', defaultReminderNextWeek: 'Next week', defaultReminderCustomDate: 'Custom date…', defaultReminderClear: 'Clear reminder',`
- `es`: `contextMenuAddReminder: 'Añadir recordatorio', contextMenuReminderSet: 'Recordatorio: {date}', defaultReminderToday: 'Hoy', defaultReminderTomorrow: 'Mañana', defaultReminderNextWeek: 'Próxima semana', defaultReminderCustomDate: 'Fecha personalizada…', defaultReminderClear: 'Quitar recordatorio',`
- `fr`: `contextMenuAddReminder: 'Ajouter un rappel', contextMenuReminderSet: 'Rappel : {date}', defaultReminderToday: 'Aujourd\\'hui', defaultReminderTomorrow: 'Demain', defaultReminderNextWeek: 'Semaine prochaine', defaultReminderCustomDate: 'Date personnalisée…', defaultReminderClear: 'Supprimer le rappel',`
- `de`: `contextMenuAddReminder: 'Erinnerung hinzufügen', contextMenuReminderSet: 'Erinnerung: {date}', defaultReminderToday: 'Heute', defaultReminderTomorrow: 'Morgen', defaultReminderNextWeek: 'Nächste Woche', defaultReminderCustomDate: 'Eigenes Datum…', defaultReminderClear: 'Erinnerung entfernen',`
- `zh-Hans`: `contextMenuAddReminder: '添加提醒', contextMenuReminderSet: '提醒：{date}', defaultReminderToday: '今天', defaultReminderTomorrow: '明天', defaultReminderNextWeek: '下周', defaultReminderCustomDate: '自定义日期…', defaultReminderClear: '清除提醒',`
- `zh-Hant`: `contextMenuAddReminder: '添加提醒', contextMenuReminderSet: '提醒：{date}', defaultReminderToday: '今天', defaultReminderTomorrow: '明天', defaultReminderNextWeek: '下週', defaultReminderCustomDate: '自訂日期…', defaultReminderClear: '清除提醒',`
  (zh-Hant differs from zh-Hans only in `周`→`週` and `自定义`→`自訂`,
  matching `reminderSnooze1Week`/`reminderSnoozeCustom`'s own established
  conversions exactly — every other character in these keys is identical
  between the two scripts, confirmed against `captureAddFieldToggleCollapsed`'s
  own zh-Hans/zh-Hant pair for "添加" itself)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd tests && python3 test_default_reminder.py`
Expected: all 10 scenarios print `True`/expected values, `JS ERRORS: []`.

- [ ] **Step 5: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `PASS`.

- [ ] **Step 6: Run the full existing suite**

Run: `cd tests && for f in test_*.py; do python3 "$f" > /tmp/task2_$f.log 2>&1; echo "EXIT:$? for $f"; done`
Expected: 65/65 exit 0 (64 pre-existing scripts plus this plan's new
`test_default_reminder.py`).

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_default_reminder.py
git commit -m "Add the default-reminder context menu action and quick-pick flyout

'Add reminder' (or 'Reminder: <date>' once set) appears in the row
context menu for every non-deleted document. The flyout offers Today/
Tomorrow/Next week/Custom date, plus Clear reminder once one's set --
the same 'separate floating element outside the row context menu'
pattern Add to Collection's own picker already uses, so it survives the
context menu's own auto-close."
```

---

### Task 3: Documentation

**Files:**
- Modify: `CLAUDE.md` (new architecture note), `tests/CLAUDE.md` (new
  paragraph describing `test_default_reminder.py`'s coverage, and the
  script-count bump)

**Interfaces:**
- Consumes: the finished behavior from Tasks 1-2 (this task only
  documents it — no code changes).

- [ ] **Step 1: Read the existing notes first**

Read `CLAUDE.md`'s "Reminder-type custom fields" note (added by the prior
reminder-fields feature) in full — this new note extends it directly, so
match its voice and cross-reference it explicitly rather than repeating
its own explanation of `checkReminders()`/the field type/etc. Also read
`tests/CLAUDE.md`'s closing "This list itself can go stale" paragraph and
its immediately-preceding entry (the reminder-type custom fields one) to
match voice and placement.

- [ ] **Step 2: Add the CLAUDE.md architecture note**

Insert a new bullet in `CLAUDE.md`'s "Architecture notes" section, right
after the existing "Reminder-type custom fields" note, covering: the
`'Reminder'` field as a reserved, auto-created (`migrateDefaultReminderField()`),
never-type-attached reminder-type field; that it inherits `checkReminders()`
and the Edit form's orphaned-field display with zero code changes to
either, by construction; the row context menu's `default-reminder` action
and its two label states; the flyout's four/five choices and that it's a
separate floating element from the row context menu (surviving that
menu's own auto-close, the same way Add to Collection's picker already
does); and `setDefaultReminder()`/`clearDefaultReminder()`'s
delete-then-insert write pattern, matching `saveEditedDocument()`'s own
per-field convention.

- [ ] **Step 3: Add the tests/CLAUDE.md coverage paragraph and bump the script count**

In `tests/CLAUDE.md`'s "How this was tested" section, append a new clause
describing `test_default_reminder.py`'s coverage (right before "This list
itself can go stale," following that paragraph's own dense, run-on
style): the `'Reminder'` field's auto-creation and reopen-idempotency;
its rejection as a custom-field name; `setDefaultReminder()`/
`clearDefaultReminder()`'s write/persist/clear behavior and their
integration with `checkReminders()`, verified at the function level via
`__DEBUG_setDefaultReminder`/`__DEBUG_clearDefaultReminder`; a set
default reminder showing as an orphaned, editable field in the Edit
form for any document type; the context menu's two label states; the
flyout surviving the row context menu's own auto-close (the same
separate-floating-element property Add to Collection's picker relies
on); all four presets plus Clear reminder (shown only once a reminder is
set); the custom-date input's hidden/revealed/min-attribute/dark-mode
behavior, matching the reminders modal's own already-established pattern;
and an end-to-end confirmation that a flyout-driven write is picked up by
`checkReminders()` the same way a function-level write already is.

Update the script count at the top of `tests/CLAUDE.md`'s "How this was
tested" section (search for `"64 scripts"` and `"63 of them Playwright-driven"`)
and `CLAUDE.md`'s own repo-layout comment (search for `"64 scripts"`
near the `tests/` line) — both become "65 scripts" / "64 of them
Playwright-driven" respectively, since `test_default_reminder.py` is new.

- [ ] **Step 4: Verify the script count**

Run: `ls tests/test_*.py | wc -l`
Expected: `65`.

- [ ] **Step 5: Run the full suite one final time**

Run: `cd tests && for f in test_*.py; do python3 "$f" > /tmp/task3_$f.log 2>&1; echo "EXIT:$? for $f"; done`
Expected: 65/65 exit 0 — confirms the documentation-only change broke
nothing.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "Document the default-reminder context menu feature"
```

---

## Self-Review

**1. Spec coverage** — every section of
`docs/superpowers/specs/2026-08-31-default-reminder-context-menu-design.md`
maps to a task: the reserved, auto-created field and its inherited
`checkReminders()`/orphaned-field behavior (Task 1); the context menu
entry, its two label states, and the quick-pick flyout with all four
presets plus Clear (Task 2); documentation (Task 3). The "Out of scope"
items (no live badge/highlight, no note/label field, no auto-attach to
`document_type_fields`, no bulk action, no due/overdue styling in the
menu itself) are not implemented by any task — confirmed by re-reading
Task 2's own action descriptor and flyout code, which write only a date,
never touch `document_type_fields`, and add nothing to the bulk-action
bar. One consequence the spec itself didn't call out, caught while
tracing the actual `buildDetailActions()` code during this review:
since that function is genuinely shared between the row context menu and
the detail panel, the new action automatically becomes a real panel
button too, once `actionIdByKey` (a hardcoded key-to-id map the panel's
rendering depends on, unlike the context menu's own fully generic
iteration) gets the new entry Task 2 adds. This is a natural, low-risk
consequence of correctly reusing the existing shared mechanism — not
scope creep — and Task 2 now includes both the fix and a dedicated test
(Scenario 10) for it, rather than leaving the panel silently broken
(`id="undefined"`) the way an earlier draft of this plan would have.

**2. Placeholder scan** — no TBD/TODO; every step shows exact before/
after code and exact translated strings for all six languages, including
the zh-Hant conversion rationale cross-checked against two already-shipped
precedent keys (`reminderSnooze1Week`, `captureAddFieldToggleCollapsed`)
rather than guessed from scratch.

**3. Type/name consistency** — `setDefaultReminder(documentId, dateIso)`/
`clearDefaultReminder(documentId)` are defined once in Task 1 and called
identically (same names, same argument order) by Task 2's flyout code.
`fieldNameToId['Reminder']` is established by Task 1's migration and read
identically by both of Task 1's own write functions and Task 2's
`buildDetailActions()` check (`d.customFields['Reminder']`). The CSS
class names (`.reminder-flyout`, `.reminder-flyout-option`,
`.reminder-flyout-custom-date`) are introduced once in Task 2 and used
consistently by both the implementation and Task 2's own test assertions.

**4. A real ordering dependency worth restating**: Task 1's
`migrateDefaultReminderField()` must run (via its `initNewLibrary()`/
`loadDb()` call sites) before Task 2's `buildDetailActions()` code reads
`fieldNameToId['Reminder']` — already naturally satisfied, since both
call sites live inside the same startup path this app's other
`fieldNameToId` consumers already depend on, but worth an implementer
resuming from Task 2 onward confirming directly (e.g. via
`window.__DEBUG_findFieldByName('Reminder')`) rather than assuming.
