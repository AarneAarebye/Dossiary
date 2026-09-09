# Reminder Dismiss/Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new per-row actions to the Reminders modal — Dismiss (permanently stop a reminder-type field from resurfacing, keeping its stored value) and Delete (clear the field's value outright) — plus an Edit-form hint and Re-enable path for a dismissed field.

**Architecture:** `reminder_snoozes` gains a `dismissed` column, sharing the existing compound `(document_id, field_id)` key with ordinary snoozing. Three new functions (`dismissReminder`, `reenableReminder`, `clearReminderFieldValue`) follow the exact DB-write-plus-in-memory-update shape `snoozeReminder()`/`clearDefaultReminder()` already use. The in-memory `reminderSnoozes` map's value shape changes from a bare string to `{snoozedUntil, dismissed}`.

**Tech Stack:** Single-file vanilla JS (`dossiary.html`), sql.js, no build step. Tests: standalone Playwright scripts under `tests/`, driven against `tests/stub_studio2.js`, extending the existing `tests/test_reminders.py`.

## Global Constraints

- No confirmation dialogs for Dismiss or Delete, matching every other action in this app.
- Dismissal is scoped to `(document_id, field_id)`, never to a specific value — editing a dismissed field to a new date does not un-dismiss it.
- Dismiss and a snooze are mutually exclusive on the same row: setting one always clears the other (`dismissReminder()` clears `snoozed_until`; the existing `snoozeReminder()` must explicitly clear `dismissed` too, since a reminder can only ever be snoozed via the modal while it's currently due, which by construction means it wasn't dismissed — but the write should be explicit, not rely on that invariant holding forever).
- `reenableReminder()` does a full `DELETE FROM reminder_snoozes`, not a flag flip — matches "never touched" and "re-enabled" being the identical state.
- `clearReminderFieldValue()` calls `render()` (so a `show_as_column` reminder field updates in the table) but never `openDetail()` (avoids yanking the persistent detail panel to a different document while working through the modal's list).
- Every new user-facing string is added to all six `STRINGS` blocks (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`) — `zh-Hant` derived from the finished `zh-Hans` wording via a real OpenCC `s2t` run, this repo's established convention.
- Tests extend `tests/test_reminders.py` (not a new file), continuing that file's scenario numbering from 7, and reuse its established conventions: `window.__makeSeededRoot`/`__makeSeededEmptyRoot`, `__DEBUG_dbRun`, `__DEBUG_loadDocumentsFromDb`, `__DEBUG_checkReminders`, `__DEBUG_todayIsoDate`/`__DEBUG_addDaysToIsoDate`, and reading persisted `library.sqlite` bytes back via `window.__TEST_ROOT.getFileHandle('library.sqlite')` rather than trusting DOM/in-memory state alone for anything that's supposed to be written to disk.
- Reference documents: the approved design spec at `docs/superpowers/specs/2026-09-09-reminder-dismiss-delete-design.md` (read it in full before starting) and this repo's `CLAUDE.md`/`tests/CLAUDE.md`.

---

## Task 1: Schema, `reminderSnoozes` shape change, `checkReminders()`, `snoozeReminder()`

**Files:**
- Modify: `dossiary.html`
  - `~line 2189-2192`: `SCHEMA`'s `reminder_snoozes` table definition — add `dismissed INTEGER DEFAULT 0`.
  - `~line 2200-2212`: `SCHEMA_MIGRATIONS` — add the matching `ALTER TABLE` entry.
  - `~line 2314`: `reminderSnoozes` variable's own comment.
  - `~line 2425-2446`: `checkReminders()` — dismissed-check added before the snooze check.
  - `~line 3418-3425`: `loadReminderSnoozes()` — new shape.
  - `~line 3443`: `__DEBUG_reminderSnoozesRawRows` — SELECT gains the new column.
  - `~line 5228-5232`: `snoozeReminder()` — new shape, explicit `dismissed = 0`.
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Consumes: nothing new — this task only changes existing functions' internals.
- Produces: `reminderSnoozes[key]` is now `{snoozedUntil: string|null, dismissed: boolean}` instead of a bare string. Every later task that reads or writes `reminderSnoozes` must use this shape.

- [ ] **Step 1: Write the failing test for the new shape and `checkReminders()`'s dismissed exclusion**

Read `tests/test_reminders.py` in full first — it already has Scenarios 1-6. Append this as Scenario 7, right after the end of Scenario 6 (before the closing of `main()`):

```python
        # === Scenario 7: reminder_snoozes.dismissed loads into the new
        # {snoozedUntil, dismissed} shape, and checkReminders() excludes a
        # dismissed field unconditionally -- even one that's overdue with no
        # snoozed_until at all, and even one whose snooze row also carries a
        # stale future snoozed_until (dismissed must win regardless) ===
        dismiss_seed = {
            "documents": [
                {
                    "id": 1, "title": "Doc Dismissed No Snooze", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 2, "title": "Doc Dismissed With Stale Future Snooze", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 3, "title": "Doc Not Dismissed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {  # doc 4: two reminder fields on the SAME document -- one dismissed
                   # (Renewal Date), one left alone (Warranty End) -- proves dismissal is
                   # scoped per-field, not per-document
                    "id": 4, "title": "Doc Two Fields One Dismissed", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
                {"id": 2, "name": "Warranty End", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(dismiss_seed)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        result7 = await page.evaluate("""
            () => {
                const add = (days) => window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), days);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, add(-5)]);  // overdue
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [2, 1, add(0)]);   // due today
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [3, 1, add(0)]);   // due today, never touched
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [4, 1, add(0)]);   // doc4 Renewal Date: due today, will be dismissed below
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [4, 2, add(0)]);   // doc4 Warranty End: due today, left alone
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [1, 1, null, 1]);
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [2, 1, add(30), 1]);
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [4, 1, null, 1]);
                window.__DEBUG_loadDocumentsFromDb();
                const loaded1 = window.__DEBUG_reminderSnoozes['1:1'];
                const loaded2 = window.__DEBUG_reminderSnoozes['2:1'];
                const due = window.__DEBUG_checkReminders();
                return { loaded1, loaded2, dueIds: due.map(r => r.documentId), doc4Fields: due.filter(r => r.documentId === 4).map(r => r.fieldName) };
            }
        """)
        print("dismissed row (no snooze) loads into memory as {snoozedUntil: null, dismissed: true}:", result7['loaded1'] == {'snoozedUntil': None, 'dismissed': True})
        print("dismissed row (with a stale future snoozed_until) still loads dismissed=true:", result7['loaded2']['dismissed'] == True)
        print("checkReminders() excludes both dismissed docs 1 and 2, includes docs 3 and 4:", sorted(result7['dueIds']) == [3, 4])
        print("doc 4 contributes only Warranty End (Renewal Date dismissed, per-field not per-document):", result7['doc4Fields'] == ['Warranty End'])

        # Editing doc 1's dismissed field to a brand-new date does NOT un-dismiss it --
        # dismissal is scoped to (document_id, field_id), never to the specific value
        # that was due at the time it was dismissed.
        result7b = await page.evaluate("""
            () => {
                const add = (days) => window.__DEBUG_addDaysToIsoDate(window.__DEBUG_todayIsoDate(), days);
                window.__DEBUG_dbRun('DELETE FROM document_field_values WHERE document_id = ? AND field_id = ?', [1, 1]);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, add(-1)]);
                window.__DEBUG_loadDocumentsFromDb();
                return window.__DEBUG_checkReminders().map(r => r.documentId);
            }
        """)
        print("doc 1 stays excluded after its dismissed field's value is changed to a brand-new date:", 1 not in result7b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: `dismissed row (no snooze) loads into memory as {snoozedUntil: null, dismissed: true}: False` (or a raw JS error) — the `dismissed` column doesn't exist yet and `reminderSnoozes` still stores a bare string.

- [ ] **Step 3: Add the `dismissed` column to `SCHEMA` and `SCHEMA_MIGRATIONS`**

In `dossiary.html`, change:

```js
    CREATE TABLE IF NOT EXISTS reminder_snoozes (
      document_id INTEGER, field_id INTEGER, snoozed_until TEXT,
      PRIMARY KEY (document_id, field_id)
    );
```

to:

```js
    CREATE TABLE IF NOT EXISTS reminder_snoozes (
      document_id INTEGER, field_id INTEGER, snoozed_until TEXT, dismissed INTEGER DEFAULT 0,
      PRIMARY KEY (document_id, field_id)
    );
```

Then add one more entry to `SCHEMA_MIGRATIONS` (the array currently ending `'ALTER TABLE documents ADD COLUMN searchable_pdf_built INTEGER DEFAULT 0',`), right before its closing `];`:

```js
    'ALTER TABLE reminder_snoozes ADD COLUMN dismissed INTEGER DEFAULT 0',
```

- [ ] **Step 4: Update `reminderSnoozes`'s own comment**

Change:

```js
  let reminderSnoozes = {};    // { "<documentId>:<fieldId>": "<snoozed_until ISO date>", ... }
```

to:

```js
  let reminderSnoozes = {};    // { "<documentId>:<fieldId>": { snoozedUntil, dismissed }, ... } -- snoozedUntil is an ISO date string or null, dismissed is a real boolean
```

- [ ] **Step 5: Update `loadReminderSnoozes()`**

Change:

```js
  function loadReminderSnoozes(){
    reminderSnoozes = {};
    const { rows } = queryAll('SELECT document_id, field_id, snoozed_until FROM reminder_snoozes');
    for(const [documentId, fieldId, snoozedUntil] of rows){
      reminderSnoozes[`${documentId}:${fieldId}`] = snoozedUntil;
    }
    window.__DEBUG_reminderSnoozes = reminderSnoozes; // test-only hook (tests/test_reminders.py) -- the simplest way to assert on this module-private variable from outside the page's own closure
  }
```

to:

```js
  function loadReminderSnoozes(){
    reminderSnoozes = {};
    const { rows } = queryAll('SELECT document_id, field_id, snoozed_until, dismissed FROM reminder_snoozes');
    for(const [documentId, fieldId, snoozedUntil, dismissed] of rows){
      reminderSnoozes[`${documentId}:${fieldId}`] = { snoozedUntil, dismissed: !!dismissed };
    }
    window.__DEBUG_reminderSnoozes = reminderSnoozes; // test-only hook (tests/test_reminders.py) -- the simplest way to assert on this module-private variable from outside the page's own closure
  }
```

- [ ] **Step 6: Update `__DEBUG_reminderSnoozesRawRows`**

Change:

```js
  window.__DEBUG_reminderSnoozesRawRows = () => queryAll('SELECT document_id, field_id, snoozed_until FROM reminder_snoozes').rows;
```

to:

```js
  window.__DEBUG_reminderSnoozesRawRows = () => queryAll('SELECT document_id, field_id, snoozed_until, dismissed FROM reminder_snoozes').rows;
```

- [ ] **Step 7: Update `checkReminders()`'s exclusion check**

Change:

```js
      for(const field of reminderFields){
        const raw = customFields[field.name];
        if(!raw) continue;
        const dateOnly = raw.slice(0, 10);
        if(dateOnly > cutoff) continue;
        const snoozedUntil = reminderSnoozes[`${d.id}:${field.id}`];
        if(snoozedUntil && snoozedUntil > todayIso) continue;
        results.push({ documentId: d.id, fieldId: field.id, fieldName: field.name, date: dateOnly, docTitle: displayName(d) });
      }
```

to:

```js
      for(const field of reminderFields){
        const raw = customFields[field.name];
        if(!raw) continue;
        const dateOnly = raw.slice(0, 10);
        if(dateOnly > cutoff) continue;
        const snoozeEntry = reminderSnoozes[`${d.id}:${field.id}`];
        if(snoozeEntry && snoozeEntry.dismissed) continue;
        if(snoozeEntry && snoozeEntry.snoozedUntil && snoozeEntry.snoozedUntil > todayIso) continue;
        results.push({ documentId: d.id, fieldId: field.id, fieldName: field.name, date: dateOnly, docTitle: displayName(d) });
      }
```

- [ ] **Step 8: Update `snoozeReminder()`**

Change:

```js
  async function snoozeReminder(documentId, fieldId, snoozedUntil){
    reminderSnoozes[`${documentId}:${fieldId}`] = snoozedUntil;
    db.run('INSERT OR REPLACE INTO reminder_snoozes (document_id, field_id, snoozed_until) VALUES (?, ?, ?)', [documentId, fieldId, snoozedUntil]);
    await persistDb();
  }
```

to:

```js
  async function snoozeReminder(documentId, fieldId, snoozedUntil){
    reminderSnoozes[`${documentId}:${fieldId}`] = { snoozedUntil, dismissed: false };
    db.run('INSERT OR REPLACE INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [documentId, fieldId, snoozedUntil, 0]);
    await persistDb();
  }
```

- [ ] **Step 9: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: all lines print `True`, `JS ERRORS: []`. Scenarios 1-6 must still pass too (Scenario 3's own `snoozed_until`-only assertions read from `window.__DEBUG_reminderSnoozes['1:1']` as a bare value — re-check Scenario 3's own print statements still make sense against the new object shape; if Scenario 3 prints `undefined` or an object where it expected a string, update Scenario 3's own assertions to read `.snoozedUntil` off the object instead of expecting a bare string, since that scenario predates this change).

- [ ] **Step 10: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Add reminder_snoozes.dismissed column and the dismissed-exclusion check"
```

---

## Task 2: `dismissReminder()`, `reenableReminder()`, `clearReminderFieldValue()`

**Files:**
- Modify: `dossiary.html`
  - New functions placed immediately after `snoozeReminder()` (`~line 5232`, right before the `copyPathToClipboard()` function that follows it).
  - New `__DEBUG_` hooks placed near the existing `__DEBUG_setDefaultReminder`/`__DEBUG_clearDefaultReminder` hooks (`~line 3457-3458`).
  - `STRINGS.en`/`STRINGS.es`/`STRINGS.fr`/`STRINGS.de`/`STRINGS['zh-Hans']`/`STRINGS['zh-Hant']` — four new keys each, inserted right after each language's own `defaultReminderClear:` entry (the last key in that reminder-related run — `~line 1025` in `en`, `~1198` in `es`, `~1371` in `fr`, `~1544` in `de`, `~1717` in `zh-Hans`, `~2013` in `zh-Hant`).
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Consumes: `reminderSnoozes` (Task 1's new shape), `fieldDefs`, `allDocs`, `db`, `persistDb()`, `render()`.
- Produces: `async function dismissReminder(documentId, fieldId)`, `async function reenableReminder(documentId, fieldId)`, `async function clearReminderFieldValue(documentId, fieldId)` — all three consumed by Task 3 (modal buttons) and Task 4 (`reenableReminder` only, from the Edit form).

- [ ] **Step 1: Write the failing test for all three functions**

Append as Scenario 8, right after Scenario 7:

```python
        # === Scenario 8: dismissReminder()/reenableReminder()/clearReminderFieldValue()
        # each write the correct persisted state and update reminderSnoozes/allDocs
        # in memory, exercised directly via their __DEBUG_ hooks (no UI yet -- Task 3
        # wires the real buttons) ===
        seed8 = {
            "documents": [
                {
                    "id": 1, "title": "Doc For Dismiss", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [
                {"document_id": 1, "field_id": 1, "value": "2026-06-01"},
            ],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed8)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        async def read_db():
            return await page.evaluate("""
                (async () => {
                    const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                    const f = await fh.getFile();
                    return JSON.parse(await f.text());
                })()
            """)

        # dismissReminder
        await page.evaluate("window.__DEBUG_dismissReminder(1, 1)")
        await page.wait_for_timeout(150)
        persisted = await read_db()
        snooze_row = next((s for s in persisted['reminder_snoozes'] if s['document_id'] == 1 and s['field_id'] == 1), None)
        print("dismissReminder() persists dismissed=1:", snooze_row is not None and snooze_row['dismissed'] == 1)
        in_memory_dismissed = await page.evaluate("window.__DEBUG_reminderSnoozes['1:1']")
        print("dismissReminder() updates in-memory reminderSnoozes:", in_memory_dismissed == {'snoozedUntil': None, 'dismissed': True})
        still_has_value = await page.evaluate("window.__DEBUG_getCustomFieldValue(1, 'Renewal Date')")
        print("dismissReminder() does NOT touch the field's own stored value:", still_has_value == '2026-06-01')

        # reenableReminder
        await page.evaluate("window.__DEBUG_reenableReminder(1, 1)")
        await page.wait_for_timeout(150)
        persisted = await read_db()
        snooze_row_after = next((s for s in persisted['reminder_snoozes'] if s['document_id'] == 1 and s['field_id'] == 1), None)
        print("reenableReminder() deletes the reminder_snoozes row entirely:", snooze_row_after is None)
        in_memory_after = await page.evaluate("window.__DEBUG_reminderSnoozes['1:1']")
        print("reenableReminder() removes the in-memory entry too:", in_memory_after is None)

        # clearReminderFieldValue
        await page.evaluate("window.__DEBUG_clearReminderFieldValue(1, 1)")
        await page.wait_for_timeout(150)
        persisted = await read_db()
        value_row = next((v for v in persisted['document_field_values'] if v['document_id'] == 1 and v['field_id'] == 1), None)
        print("clearReminderFieldValue() deletes the document_field_values row:", value_row is None)
        in_memory_value = await page.evaluate("window.__DEBUG_getCustomFieldValue(1, 'Renewal Date')")
        print("clearReminderFieldValue() clears the in-memory customFields entry too:", in_memory_value is None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: a JS error (`window.__DEBUG_dismissReminder is not a function` or similar) — none of the three functions or their hooks exist yet.

- [ ] **Step 3: Add the three functions**

In `dossiary.html`, immediately after `snoozeReminder()`'s closing `}` (`~line 5232`), add:

```js
  // The permanent version of snoozeReminder() above -- "stop bothering me about
  // this field on this document, indefinitely" rather than "until a date". Lives
  // on the same reminder_snoozes row (same compound key), since the two states
  // are mutually exclusive for a given (document_id, field_id): dismissing clears
  // any in-flight snooze. checkReminders() checks `dismissed` before it ever looks
  // at `snoozedUntil`, so a null snoozedUntil here has no separate effect on that
  // check -- it's written anyway to keep the row's own stored state honest.
  async function dismissReminder(documentId, fieldId){
    reminderSnoozes[`${documentId}:${fieldId}`] = { snoozedUntil: null, dismissed: true };
    db.run('INSERT OR REPLACE INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [documentId, fieldId, null, 1]);
    await persistDb();
  }

  // Undoes dismissReminder() -- a full DELETE rather than flipping `dismissed`
  // back to 0, since once re-enabled there's no other meaningful state left on
  // that row to keep (no active snooze coexists with a dismissal); this matches
  // how a document that was never snoozed or dismissed at all has no
  // reminder_snoozes row either, so "re-enabled" and "never touched" end up in
  // the identical, simplest state.
  async function reenableReminder(documentId, fieldId){
    delete reminderSnoozes[`${documentId}:${fieldId}`];
    db.run('DELETE FROM reminder_snoozes WHERE document_id = ? AND field_id = ?', [documentId, fieldId]);
    await persistDb();
  }

  // The generalized version of clearDefaultReminder() below -- same delete-only
  // pattern (no reinsert), but driven by an explicit fieldId instead of resolving
  // fieldNameToId['Reminder'] internally, so it works for any reminder-type field.
  // Called from the Reminders modal's Delete button; deliberately calls render()
  // (so a show_as_column reminder field updates in the table too) but NOT
  // openDetail() -- unlike clearDefaultReminder(), which is only ever reached from
  // a context already focused on one specific document (the row context menu, the
  // detail panel), this can be invoked repeatedly for several different documents
  // while working through the Reminders modal's list, and forcing the persistent
  // detail panel to jump to each one in turn would be a jarring, unwanted side
  // effect of a quick cleanup action. If the panel already happens to be open on
  // the affected document, its displayed value may lag until the next unrelated
  // render/selection change -- an accepted, narrow tradeoff, not a correctness
  // issue (the underlying data is already correct; only that one already-open
  // view hasn't repainted yet).
  async function clearReminderFieldValue(documentId, fieldId){
    const d = allDocs.find(x => x.id === documentId);
    if(!d) return;
    const fieldDef = fieldDefs.find(f => f.id === fieldId);
    db.run('DELETE FROM document_field_values WHERE document_id = ? AND field_id = ?', [documentId, fieldId]);
    if(d.customFields && fieldDef) delete d.customFields[fieldDef.name];
    await persistDb();
    render();
  }
```

- [ ] **Step 4: Add the three `__DEBUG_` hooks**

In `dossiary.html`, immediately after `window.__DEBUG_clearDefaultReminder = clearDefaultReminder;` (`~line 3458`), add:

```js
  window.__DEBUG_dismissReminder = dismissReminder;
  window.__DEBUG_reenableReminder = reenableReminder;
  window.__DEBUG_clearReminderFieldValue = clearReminderFieldValue;
```

- [ ] **Step 5: Add the four new i18n keys to all six `STRINGS` blocks**

In `STRINGS.en`, right after `defaultReminderClear: 'Clear reminder',` on its existing line, add:

```js
reminderDismissBtn: 'Dismiss', reminderDeleteBtn: 'Delete', reminderDismissedHint: 'Reminders are dismissed for this field.', reminderReenableBtn: 'Re-enable',
```

Repeat in the same position (right after each language's own `defaultReminderClear:` entry) for the other five languages:

```js
// es
reminderDismissBtn: 'Descartar', reminderDeleteBtn: 'Eliminar', reminderDismissedHint: 'Los recordatorios están desactivados para este campo.', reminderReenableBtn: 'Reactivar',
// fr
reminderDismissBtn: 'Ignorer', reminderDeleteBtn: 'Supprimer', reminderDismissedHint: 'Les rappels sont désactivés pour ce champ.', reminderReenableBtn: 'Réactiver',
// de
reminderDismissBtn: 'Verwerfen', reminderDeleteBtn: 'Löschen', reminderDismissedHint: 'Erinnerungen sind für dieses Feld deaktiviert.', reminderReenableBtn: 'Wieder aktivieren',
// zh-Hans
reminderDismissBtn: '忽略', reminderDeleteBtn: '删除', reminderDismissedHint: '此字段的提醒已停用。', reminderReenableBtn: '重新启用',
```

For `STRINGS['zh-Hant']`, derive from the `zh-Hans` line above via a real OpenCC `s2t` conversion (install `opencc-python-reimplemented` into a scratch venv if not already available, convert, then discard the venv — this repo's established one-time-tool convention) rather than trusting the sample below blindly:

```js
// zh-Hant (verify via a real OpenCC s2t run)
reminderDismissBtn: '忽略', reminderDeleteBtn: '刪除', reminderDismissedHint: '此字段的提醒已停用。', reminderReenableBtn: '重新啟用',
```

- [ ] **Step 6: Run `test_i18n_coverage.py`, then `test_reminders.py`**

Run: `cd tests && python3 test_i18n_coverage.py && python3 test_reminders.py`
Expected: `test_i18n_coverage.py` passes (all six languages have the four new keys — note `reminderDismissBtn`/`reminderDeleteBtn`/`reminderReenableBtn` won't actually be referenced by any `t()` call or `data-i18n` attribute until Tasks 3-4 wire them up, so this run will report them "never referenced" in its informational list, same as any key added ahead of its call site — this is expected, not a failure, since the coverage check only fails on a key *referenced but missing from some language*, not an unreferenced one). `test_reminders.py`: all lines print `True`.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Add dismissReminder/reenableReminder/clearReminderFieldValue"
```

---

## Task 3: Reminders modal — Dismiss/Delete buttons per row

**Files:**
- Modify: `dossiary.html`
  - `renderReminderRowHtml()` (`~line 5155-5174`): two new buttons per row.
  - `wireReminderRows()` (`~line 5176-5218`): wiring for the two new buttons.
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Consumes: `dismissReminder(documentId, fieldId)`, `clearReminderFieldValue(documentId, fieldId)` (Task 2), `removeReminderRow(rowEl)` (pre-existing).
- Produces: nothing further downstream — this is the primary user-facing deliverable of the feature.

- [ ] **Step 1: Write the failing test for the modal buttons**

Append as Scenario 9, right after Scenario 8:

```python
        # === Scenario 9: the Reminders modal's Dismiss and Delete buttons work
        # end to end -- clicking either removes that row, persists the correct
        # change, and the modal auto-closes once every row is gone via a mix of
        # Dismiss/Delete/Snooze (not just Snooze alone, which Scenario 5 already
        # covers) ===
        seed9 = {
            "documents": [
                {
                    "id": 1, "title": "Doc To Dismiss", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 2, "title": "Doc To Delete", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
                {
                    "id": 3, "title": "Doc To Snooze", "category": None, "document_type": None,
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
                {"id": 2, "name": "Warranty End", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_field_values": [],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed9)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                const today = window.__DEBUG_todayIsoDate();
                const add = (days) => window.__DEBUG_addDaysToIsoDate(today, days);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, today]);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [2, 2, add(60)]); // doc 2's OTHER reminder field, deliberately outside the lookahead window (so it never shows its own modal row) -- must survive deleting field 1's value below
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [2, 1, today]);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [3, 1, today]);
                window.__DEBUG_loadDocumentsFromDb();
            }
        """)
        due9 = await page.evaluate("window.__DEBUG_checkReminders()")
        await page.evaluate("(due) => window.__DEBUG_openRemindersModal(due)", due9)
        await page.wait_for_timeout(200)

        buttons_present = await page.locator('.reminder-row[data-document-id="1"] .reminder-dismiss-btn').count()
        delete_present = await page.locator('.reminder-row[data-document-id="1"] .reminder-delete-btn').count()
        print("each row shows both a Dismiss and a Delete button:", buttons_present == 1 and delete_present == 1)
        delete_is_danger = await page.locator('.reminder-row[data-document-id="1"] .reminder-delete-btn').get_attribute('class')
        print("the Delete button carries the app's .danger styling:", 'danger' in (delete_is_danger or ''))

        async def read_db():
            return await page.evaluate("""
                (async () => {
                    const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                    const f = await fh.getFile();
                    return JSON.parse(await f.text());
                })()
            """)

        # Dismiss doc 1
        await page.click('.reminder-row[data-document-id="1"] .reminder-dismiss-btn')
        await page.wait_for_timeout(200)
        doc1_gone = await page.locator('.reminder-row[data-document-id="1"]').count()
        print("clicking Dismiss removes doc 1's row:", doc1_gone == 0)
        persisted = await read_db()
        doc1_snooze = next((s for s in persisted['reminder_snoozes'] if s['document_id'] == 1 and s['field_id'] == 1), None)
        print("Dismiss persists dismissed=1 for doc 1:", doc1_snooze is not None and doc1_snooze['dismissed'] == 1)
        doc1_value = next((v for v in persisted['document_field_values'] if v['document_id'] == 1 and v['field_id'] == 1), None)
        print("Dismiss does NOT clear doc 1's stored value:", doc1_value is not None)

        # Delete doc 2
        await page.click('.reminder-row[data-document-id="2"] .reminder-delete-btn')
        await page.wait_for_timeout(200)
        doc2_gone = await page.locator('.reminder-row[data-document-id="2"]').count()
        print("clicking Delete removes doc 2's row:", doc2_gone == 0)
        persisted = await read_db()
        doc2_value = next((v for v in persisted['document_field_values'] if v['document_id'] == 2 and v['field_id'] == 1), None)
        print("Delete clears doc 2's stored value entirely:", doc2_value is None)
        doc2_other_field_value = next((v for v in persisted['document_field_values'] if v['document_id'] == 2 and v['field_id'] == 2), None)
        print("Delete leaves doc 2's OTHER reminder field (Warranty End) untouched:", doc2_other_field_value is not None)

        # Snooze doc 3, then confirm the modal auto-closes once all three are gone
        await page.locator('.reminder-row[data-document-id="3"] .reminder-snooze-select').select_option('1w')
        await page.wait_for_timeout(200)
        modal_closed = await page.locator('.reminder-row').count()
        print("modal auto-closes once every row has been cleared via a mix of Dismiss/Delete/Snooze:", modal_closed == 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: `each row shows both a Dismiss and a Delete button: False` — the buttons don't exist in the row markup yet.

- [ ] **Step 3: Add the two buttons to `renderReminderRowHtml()`**

Change:

```js
  function renderReminderRowHtml(r, todayIso){
    return `
      <div class="reminder-row" data-document-id="${r.documentId}" data-field-id="${r.fieldId}">
        <div>
          <div class="reminder-row-title">${escapeHtml(r.docTitle)}</div>
          <div class="reminder-row-sub">${escapeHtml(r.fieldName)} · ${formatDate(r.date)} · ${reminderDueLabel(r.date, todayIso)}</div>
        </div>
        <span class="reminder-snooze" onclick="event.stopPropagation()">
          <select class="reminder-snooze-select" data-document-id="${r.documentId}" data-field-id="${r.fieldId}">
            <option value="">${t('reminderSnoozeLabel')}</option>
            <option value="1w">${t('reminderSnooze1Week')}</option>
            <option value="1m">${t('reminderSnooze1Month')}</option>
            <option value="3m">${t('reminderSnooze3Months')}</option>
            <option value="custom">${t('reminderSnoozeCustom')}</option>
          </select>
          <input type="date" class="reminder-snooze-custom-date" data-document-id="${r.documentId}" data-field-id="${r.fieldId}" min="${addDaysToIsoDate(todayIso, 1)}" style="display:none;" />
        </span>
      </div>
    `;
  }
```

to:

```js
  function renderReminderRowHtml(r, todayIso){
    return `
      <div class="reminder-row" data-document-id="${r.documentId}" data-field-id="${r.fieldId}">
        <div>
          <div class="reminder-row-title">${escapeHtml(r.docTitle)}</div>
          <div class="reminder-row-sub">${escapeHtml(r.fieldName)} · ${formatDate(r.date)} · ${reminderDueLabel(r.date, todayIso)}</div>
        </div>
        <span class="reminder-snooze" onclick="event.stopPropagation()">
          <select class="reminder-snooze-select" data-document-id="${r.documentId}" data-field-id="${r.fieldId}">
            <option value="">${t('reminderSnoozeLabel')}</option>
            <option value="1w">${t('reminderSnooze1Week')}</option>
            <option value="1m">${t('reminderSnooze1Month')}</option>
            <option value="3m">${t('reminderSnooze3Months')}</option>
            <option value="custom">${t('reminderSnoozeCustom')}</option>
          </select>
          <input type="date" class="reminder-snooze-custom-date" data-document-id="${r.documentId}" data-field-id="${r.fieldId}" min="${addDaysToIsoDate(todayIso, 1)}" style="display:none;" />
          <button type="button" class="reminder-dismiss-btn" data-document-id="${r.documentId}" data-field-id="${r.fieldId}">${t('reminderDismissBtn')}</button>
          <button type="button" class="reminder-delete-btn danger" data-document-id="${r.documentId}" data-field-id="${r.fieldId}">${t('reminderDeleteBtn')}</button>
        </span>
      </div>
    `;
  }
```

(The existing `<span class="reminder-snooze" onclick="event.stopPropagation()">` wrapper already stops the row's own click-to-open-detail handler from firing for anything inside it — the two new buttons inherit that guard for free, the same way the Snooze select and custom-date input already do, with no extra wiring needed.)

- [ ] **Step 4: Wire the two buttons in `wireReminderRows()`**

Immediately after the existing `.reminder-snooze-custom-date` wiring block's closing `});` (right before `wireReminderRows()`'s own final closing `}`), add:

```js
    modalRoot.querySelectorAll('.reminder-dismiss-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const documentId = Number(btn.dataset.documentId);
        const fieldId = Number(btn.dataset.fieldId);
        await dismissReminder(documentId, fieldId);
        removeReminderRow(btn.closest('.reminder-row'));
      });
    });
    modalRoot.querySelectorAll('.reminder-delete-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const documentId = Number(btn.dataset.documentId);
        const fieldId = Number(btn.dataset.fieldId);
        await clearReminderFieldValue(documentId, fieldId);
        removeReminderRow(btn.closest('.reminder-row'));
      });
    });
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: every line in Scenarios 1-9 prints `True`, `JS ERRORS: []`.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Add Dismiss and Delete buttons to the Reminders modal"
```

---

## Task 4: Edit-form dismissed-field hint and Re-enable

**Files:**
- Modify: `dossiary.html`
  - `renderGenericFieldHtml()` (`~line 3862-3910`): new `documentId` parameter, new conditional hint.
  - `applyDynamicFieldsForType()` (`~line 3966-4050`): new `documentId` parameter, threaded to both `renderGenericFieldHtml()` call sites, new `.reminder-reenable-btn` wiring pass.
  - The four call sites of `applyDynamicFieldsForType()` (`~line 6309`, `~6312` in the edit form; `~6912`, `~6915` in the capture form).
- Test: `tests/test_reminders.py` (extend)

**Interfaces:**
- Consumes: `reenableReminder(documentId, fieldId)` (Task 2), `reminderSnoozes` (Task 1's shape).
- Produces: nothing further downstream — this is the last piece of the feature.

- [ ] **Step 1: Write the failing test for the hint and Re-enable**

Append as Scenario 10, right after Scenario 9:

```python
        # === Scenario 10: a dismissed reminder-type field shows the
        # "Reminders are dismissed" hint in the Edit form, an otherwise-identical
        # non-dismissed one doesn't, and clicking Re-enable clears the dismissal
        # (both the hint disappearing and checkReminders() including the field
        # again) ===
        seed10 = {
            "documents": [
                {
                    "id": 1, "title": "Doc With Dismissed Field", "category": None, "document_type": "Policy",
                    "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
                    "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00Z",
                    "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0,
                },
            ],
            "tags": [], "document_tags": [],
            "fields": [
                {"id": 1, "name": "Renewal Date", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
                {"id": 2, "name": "Warranty End", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
            ],
            "document_type_fields": [
                {"document_type": "Policy", "field_name": "Renewal Date", "position": 0},
                {"document_type": "Policy", "field_name": "Warranty End", "position": 1},
            ],
            # Filled in below via JS, using real dates relative to today -- same reason
            # Scenario 4's own seed does this rather than hardcoding literal dates: a
            # hardcoded date drifts into "not due" (excluded by the lookahead window)
            # or "overdue" depending purely on which real day the suite happens to run,
            # which would make the final checkReminders()-inclusion assertion below
            # flaky rather than deterministic.
            "document_field_values": [],
            "reminder_snoozes": [],
        }
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed10)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        renewal_value = await page.evaluate("""
            () => {
                const today = window.__DEBUG_todayIsoDate();
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 1, today]);
                window.__DEBUG_dbRun('INSERT INTO document_field_values (document_id, field_id, value) VALUES (?, ?, ?)', [1, 2, today]);
                window.__DEBUG_dbRun('INSERT INTO reminder_snoozes (document_id, field_id, snoozed_until, dismissed) VALUES (?, ?, ?, ?)', [1, 1, null, 1]);
                window.__DEBUG_loadDocumentsFromDb();
                return today;
            }
        """)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)

        renewal_hint = await page.locator('[data-dynamic-field="Renewal Date"] .reminder-reenable-btn').count()
        warranty_hint = await page.locator('[data-dynamic-field="Warranty End"] .reminder-reenable-btn').count()
        print("the dismissed field (Renewal Date) shows the Re-enable hint:", renewal_hint == 1)
        print("the non-dismissed field (Warranty End) does not show it:", warranty_hint == 0)

        # Capture form never shows this hint -- there's no document yet to check.
        # By the time the capture form's own markup replaces modalRoot's content,
        # the edit form (and its hint) is already gone -- no modal-specific
        # selector scoping is needed, just confirm the hint's class is absent
        # from the page entirely while the capture form is open.
        await page.click('#cancel-edit-btn')
        await page.wait_for_timeout(150)
        await page.click('#add-btn')
        await page.wait_for_timeout(200)
        await page.fill('#f-type', 'Policy')
        await page.wait_for_timeout(200)
        capture_hint_count = await page.locator('.reminder-reenable-btn').count()
        print("the capture form never shows a Re-enable hint (no document exists yet):", capture_hint_count == 0)
        await page.click('#cancel-doc-btn')
        await page.wait_for_timeout(150)

        # Re-enable from the edit form
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        await page.click('#edit-doc-btn')
        await page.wait_for_timeout(300)
        await page.click('[data-dynamic-field="Renewal Date"] .reminder-reenable-btn')
        await page.wait_for_timeout(200)
        hint_gone = await page.locator('[data-dynamic-field="Renewal Date"] .reminder-reenable-btn').count()
        print("clicking Re-enable removes the hint immediately:", hint_gone == 0)

        still_shows_value = await page.locator('#e-field-1').input_value()
        print("Re-enabling does not touch the field's own value:", still_shows_value == renewal_value)

        due_after_reenable = await page.evaluate("window.__DEBUG_checkReminders()")
        renewal_due_again = any(r['documentId'] == 1 and r['fieldName'] == 'Renewal Date' for r in due_after_reenable)
        print("checkReminders() includes Renewal Date again after Re-enable:", renewal_due_again)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd tests && python3 test_reminders.py`
Expected: `the dismissed field (Renewal Date) shows the Re-enable hint: False` — `renderGenericFieldHtml()` doesn't render this hint yet.

- [ ] **Step 3: Add the `documentId` parameter and hint to `renderGenericFieldHtml()`**

Change the function signature and add the hint computation + output. The full function becomes:

```js
  function renderGenericFieldHtml(prefix, field, existingValue, orphaned, amountFilled, documentId){
    const inputId = `${prefix}-field-${field.id}`;
    const orphanedClass = orphaned ? ' field-orphaned' : '';
    const orphanedHint = orphaned ? `<div class="field-orphaned-hint">${t('fieldOrphanedHint')}</div>` : '';
    if(field.type === 'checkbox'){
      const checked = existingValue === '1' ? 'checked' : '';
      const description = fieldDescriptions[field.name];
      const descriptionHint = description ? `<div class="field-hint">${escapeHtml(description)}</div>` : '';
      return `
        <div class="field${orphanedClass}" data-dynamic-field="${escapeHtml(field.name)}" data-field-id="${field.id}">
          <label class="checkbox-label" for="${inputId}"><input type="checkbox" id="${inputId}" ${checked} /> ${escapeHtml(field.name)}</label>
          ${descriptionHint}
          ${orphanedHint}
        </div>
      `;
    }
    let inputType = 'text', extra = '';
    if(field.type === 'number'){ inputType = 'number'; extra = 'step="any"'; }
    else if(field.type === 'date' || field.type === 'reminder'){ inputType = 'date'; }

    const isCurrency = field.name === 'Currency';
    const isCurrencyGuess = isCurrency && !existingValue && !!defaultCurrency
      && (prefix === 'f' || (prefix === 'e' && amountFilled));
    let value = (field.type === 'date' || field.type === 'reminder') ? (existingValue ? existingValue.slice(0, 10) : '') : (existingValue || '');
    if(isCurrencyGuess) value = defaultCurrency;

    let listAttr = '';
    if(isCurrency) listAttr = 'list="currency-list"';
    else if(field.autocomplete && field.type === 'text') listAttr = `list="field-${field.id}-list"`;

    const guessHint = isCurrencyGuess
      ? `<div class="field-guess-hint" id="${inputId}-hint">${t('fieldCurrencyGuessHint', {currency: escapeHtml(defaultCurrency)})}</div>`
      : '';
    const description = fieldDescriptions[field.name];
    const descriptionHint = description ? `<div class="field-hint">${escapeHtml(description)}</div>` : '';

    // Only reminder-type fields can be dismissed, and only in the edit form (a
    // real document, not a capture-in-progress) -- documentId is null from the
    // capture form's own call sites, so this is naturally a no-op there.
    const snoozeEntry = (field.type === 'reminder' && documentId != null) ? reminderSnoozes[`${documentId}:${field.id}`] : null;
    const isDismissed = !!(snoozeEntry && snoozeEntry.dismissed);
    const dismissedHint = isDismissed
      ? `<div class="field-hint">${t('reminderDismissedHint')} <button type="button" class="copy-path-btn reminder-reenable-btn" data-document-id="${documentId}" data-field-id="${field.id}">${t('reminderReenableBtn')}</button></div>`
      : '';

    return `
      <div class="field${orphanedClass}" data-dynamic-field="${escapeHtml(field.name)}" data-field-id="${field.id}">
        <label for="${inputId}">${escapeHtml(field.name)}</label>
        <div class="field-with-clear">
          <input type="${inputType}" id="${inputId}" ${extra} ${listAttr} class="${isCurrencyGuess ? 'field-guess' : ''}" value="${escapeHtml(String(value))}" />
          <button type="button" class="clear-btn" id="${inputId}-clear" title="${t('fieldClearTitle')}" aria-label="${t('fieldClearAriaLabel', {name: escapeHtml(field.name)})}">✕</button>
        </div>
        ${guessHint}
        ${descriptionHint}
        ${dismissedHint}
        ${orphanedHint}
      </div>
    `;
  }
```

(`class="copy-path-btn reminder-reenable-btn"` reuses the existing small-inline-underlined-text-button style already used for the detail view's "Copy" path buttons — no new CSS needed, `copy-path-btn` supplies the visual style, `reminder-reenable-btn` is the behavioral hook Step 5 below wires.)

- [ ] **Step 4: Thread `documentId` through `applyDynamicFieldsForType()`**

Change the function signature from:

```js
  function applyDynamicFieldsForType(prefix, typeName, existingValues, existingPersonFieldValues, isEdit){
```

to:

```js
  function applyDynamicFieldsForType(prefix, typeName, existingValues, existingPersonFieldValues, isEdit, documentId){
```

Then update both `renderGenericFieldHtml()` call sites inside it. Change:

```js
      const existingValue = existingValues ? existingValues[fieldName] : undefined;
      return renderGenericFieldHtml(prefix, fieldDef, existingValue, false, amountFilled);
    }).join('');
```

to:

```js
      const existingValue = existingValues ? existingValues[fieldName] : undefined;
      return renderGenericFieldHtml(prefix, fieldDef, existingValue, false, amountFilled, documentId);
    }).join('');
```

And change:

```js
          orphanedHtml.push(renderGenericFieldHtml(prefix, fieldDef, existingValues[fieldName], true, amountFilled));
```

to:

```js
          orphanedHtml.push(renderGenericFieldHtml(prefix, fieldDef, existingValues[fieldName], true, amountFilled, documentId));
```

- [ ] **Step 5: Add the Re-enable wiring pass**

At the end of `applyDynamicFieldsForType()`, immediately after the existing `container.querySelectorAll('input[list="person-list"]').forEach(...)` line (the function's last statement before its closing `}`), add:

```js
    container.querySelectorAll('.reminder-reenable-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const docId = Number(btn.dataset.documentId);
        const fieldId = Number(btn.dataset.fieldId);
        await reenableReminder(docId, fieldId);
        applyDynamicFieldsForType(prefix, typeName, existingValues, existingPersonFieldValues, isEdit, documentId);
      });
    });
```

(This re-invokes the same function with the same closure arguments to rebuild the container from scratch — since `reminderSnoozes` has now lost this field's dismissed entry, `renderGenericFieldHtml()`'s own `isDismissed` check on the next pass correctly omits the hint, with no separate "just remove this one hint div" logic needed.)

- [ ] **Step 6: Update the four call sites**

In the edit form (`openEditForm()`), change:

```js
    applyDynamicFieldsForType('e', d.document_type || '', d.customFields, d.personFieldValues, true);
    updateAddFieldVisibility('e');
    el('e-type').addEventListener('change', () => {
      applyDynamicFieldsForType('e', el('e-type').value, d.customFields, d.personFieldValues, true);
      updateAddFieldVisibility('e');
    });
```

to:

```js
    applyDynamicFieldsForType('e', d.document_type || '', d.customFields, d.personFieldValues, true, d.id);
    updateAddFieldVisibility('e');
    el('e-type').addEventListener('change', () => {
      applyDynamicFieldsForType('e', el('e-type').value, d.customFields, d.personFieldValues, true, d.id);
      updateAddFieldVisibility('e');
    });
```

In the capture form (`openCaptureModal()`), change:

```js
    applyDynamicFieldsForType('f', defaultDocumentType || ''); // pre-filled default type's fields show immediately, if one is set
    updateAddFieldVisibility('f');
    el('f-type').addEventListener('change', () => {
      applyDynamicFieldsForType('f', el('f-type').value);
      updateAddFieldVisibility('f');
    });
```

to:

```js
    applyDynamicFieldsForType('f', defaultDocumentType || '', undefined, undefined, false, null); // pre-filled default type's fields show immediately, if one is set -- documentId is always null here, there's no document yet to check for a dismissal
    updateAddFieldVisibility('f');
    el('f-type').addEventListener('change', () => {
      applyDynamicFieldsForType('f', el('f-type').value, undefined, undefined, false, null);
      updateAddFieldVisibility('f');
    });
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd tests && python3 test_reminders.py`
Expected: every line in Scenarios 1-10 prints `True`, `JS ERRORS: []`.

- [ ] **Step 8: Run the full existing test suite for regressions**

Run: `cd tests && for f in test_*.py; do out=$(python3 "$f" 2>&1); code=$?; if [ $code -ne 0 ] || echo "$out" | grep -qE "Traceback"; then echo "=== $f (exit $code) ==="; echo "$out" | tail -20; fi; done; echo "=== sweep done ==="`
Expected: `=== sweep done ===` with nothing printed above it — `applyDynamicFieldsForType()`/`renderGenericFieldHtml()` are used by every capture/edit form interaction in the app, so this is the primary regression risk for this task; in particular re-run `test_field_descriptions.py`, `test_generic_fields.py`, `test_orphaned_fields.py`, and `test_person_type_field.py` explicitly, since they exercise these two functions most directly.

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_reminders.py
git commit -m "Add dismissed-reminder hint and Re-enable to the Edit form"
```

---

## Task 5: Documentation

**Files:**
- Modify: `CLAUDE.md` — extend the existing "Reminder-type custom fields" architecture note.

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing (documentation only).

- [ ] **Step 1: Extend the "Reminder-type custom fields" note in `CLAUDE.md`**

Find the existing "Reminder-type custom fields" bullet in CLAUDE.md's "Architecture notes" section (search for that exact heading text). Immediately after its existing content (right before the next bullet, "The default-reminder context menu"), add:

```markdown
  **Dismiss and Delete** (`dismissReminder()`, `reenableReminder()`,
  `clearReminderFieldValue()`) extend the Reminders modal with two more
  per-row actions alongside Snooze. Dismiss is the permanent form of a
  snooze — "stop reminding me about this field on this document,
  indefinitely" rather than "until a date" — sharing the exact same
  `reminder_snoozes` row (same compound `(document_id, field_id)` key) via
  a new `dismissed INTEGER DEFAULT 0` column rather than a separate table;
  the two states are mutually exclusive on a given row, so setting either
  one always clears the other (`dismissReminder()` writes `snoozed_until =
  NULL`; `snoozeReminder()` writes `dismissed = 0`). `checkReminders()`
  checks `dismissed` before it ever looks at `snoozed_until` — an active
  dismissal excludes a reminder unconditionally, with no expiry, unlike an
  ordinary snooze which resurfaces once `snoozed_until` passes.
  **Dismissal is scoped to the field on the document, never to a specific
  value** — editing "Renewal Date" to a brand-new date after dismissing it
  does not un-dismiss it, matching the same `(document_id, field_id)`
  granularity snoozing already uses. Delete
  (`clearReminderFieldValue(documentId, fieldId)`) is the generalized form
  of `clearDefaultReminder()` below, driven by an explicit field id instead
  of the one reserved `'Reminder'` field name, so it works for any
  reminder-type field. **`reminderSnoozes`'s in-memory shape changed** from
  a bare `snoozed_until` string per key to `{snoozedUntil, dismissed}`, to
  carry both pieces of state — `loadReminderSnoozes()`, `checkReminders()`,
  `snoozeReminder()`, and the `__DEBUG_reminderSnoozes`/
  `__DEBUG_reminderSnoozesRawRows` test hooks all moved together.
  **`reenableReminder()` does a full `DELETE FROM reminder_snoozes`, not a
  flag flip** — once re-enabled there's no other state worth keeping on
  that row, so "re-enabled" and "a field that was never snoozed or
  dismissed at all" end up in the identical, simplest state. Since a
  permanent dismissal has no natural expiry the way a snooze does, the Edit
  form shows a small hint under a dismissed reminder-type field ("Reminders
  are dismissed for this field.") with a Re-enable link — this needed
  `documentId` threaded as a new trailing parameter through
  `applyDynamicFieldsForType()` and `renderGenericFieldHtml()`, neither of
  which previously received it; the capture form's own two call sites pass
  `null`, since there's no document yet for a dismissal to apply to, so the
  hint never renders there. **`clearReminderFieldValue()` calls `render()`
  but deliberately not `openDetail()`** — unlike `clearDefaultReminder()`,
  which is only ever reached from a context already focused on one specific
  document, Delete can be clicked repeatedly for several different
  documents while working through the Reminders modal's list, and forcing
  the persistent detail panel to jump to each one in turn would be a
  jarring side effect of what's meant to be a quick cleanup action; if the
  panel already happens to be open on the affected document, its displayed
  value may lag until the next unrelated render/selection change, an
  accepted, narrow tradeoff rather than a correctness issue.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Document reminder Dismiss/Delete in CLAUDE.md"
```
