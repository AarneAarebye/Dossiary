# Dismiss and Delete for reminders in the Reminders modal

## Context

Reminder-type custom fields (`fields.type === 'reminder'`) and the
Reminders modal (`openRemindersModal()`) already ship a **Snooze**
control per row — 1 week / 1 month / 3 months / a custom date, writing to
`reminder_snoozes` (`document_id, field_id, snoozed_until`) without
touching the field's own stored value. A snooze always expires and the
reminder resurfaces on its own; there is no way to make a reminder stop
resurfacing permanently, and no quick way to clear an arbitrary
reminder-type field's value from the modal at all — the only existing
"clear the value" affordance is `clearDefaultReminder()`, reachable via
the row context menu's flyout, and hardcoded to the one reserved
`'Reminder'` field specifically (see `docs/superpowers/specs/2026-08-31-default-reminder-context-menu-design.md`).

This adds two new per-row actions to the Reminders modal, for *any*
reminder-type field on *any* document: **Dismiss** (stop this field from
ever reminding again on this document, but keep its stored value) and
**Delete** (clear the field's stored value outright, the same effect
`clearDefaultReminder()` already has, generalized beyond the one reserved
field).

## Approach

### Row layout

Each reminder row keeps its existing Snooze dropdown and gains two more
buttons beside it: **Dismiss** (plain) and **Delete** (styled `.danger`,
matching every other destructive action's styling elsewhere in this app —
e.g. the row context menu's own `.danger` items). Both are wired with
`event.stopPropagation()`, the same guard the Snooze control already
needs, so clicking either doesn't also trigger the row's own
click-to-open-detail handler. Clicking Dismiss or Delete removes that row
from the modal immediately (`removeReminderRow()`, the same function
Snooze already calls on success), and the modal auto-closes once every
row is gone — identical behavior to snoozing away every row today. Like
every other action in this app, neither shows a confirmation dialog:
`clearDefaultReminder()` already deletes a field's value with zero
confirmation, and this is the same class of action, just reachable from
a second place and for any reminder-type field instead of one.

### Schema: `reminder_snoozes` gains a `dismissed` column

A dismissal is the strongest form of snooze — "forever" instead of
"until a date" — so it lives on the same compound-keyed
`(document_id, field_id)` row rather than a new table:

```sql
ALTER TABLE reminder_snoozes ADD COLUMN dismissed INTEGER DEFAULT 0
```

Added via `SCHEMA`/`SCHEMA_MIGRATIONS` the standard additive way this
app already handles every column addition. **Dismissal is scoped to the
field on the document, not to whichever value happened to be due at the
time** — per the approved design decision, if "Renewal Date" is
dismissed today and later edited to a completely new date, it stays
dismissed; there's no per-value tracking, matching the same
document+field (not document+field+value) granularity `reminder_snoozes`
already uses for ordinary snoozing.

`checkReminders()` gains one more exclusion, checked before the existing
`snoozed_until` comparison: if the `(documentId, fieldId)` pair's
`reminder_snoozes` row has `dismissed` set, the reminder is excluded
unconditionally, with no expiry — unlike an ordinary snooze, which
resurfaces once `snoozed_until` passes, a dismissal never does on its
own.

**The in-memory `reminderSnoozes` map's value shape changes** from a bare
ISO date string (`{ "<documentId>:<fieldId>": "<snoozed_until>" }`) to an
object carrying both fields (`{ "<documentId>:<fieldId>": { snoozedUntil,
dismissed } }`), since a row can now carry either piece of state.
`loadReminderSnoozes()`, `checkReminders()`, `snoozeReminder()`'s own
in-memory update, and the existing `__DEBUG_reminderSnoozes` test hook
all read/write this map and need to move to the new shape together — this
is a real, if small, refactor of already-shipped code, not purely
additive.

### New functions

- **`dismissReminder(documentId, fieldId)`** — `INSERT OR REPLACE INTO
  reminder_snoozes (document_id, field_id, snoozed_until, dismissed)
  VALUES (?, ?, NULL, 1)`, mirroring `snoozeReminder()`'s own shape.
  `snoozed_until` is cleared (`NULL`) since dismissal supersedes any
  in-flight snooze on the same field — the two are mutually exclusive
  states for a given `(document_id, field_id)` pair, and dismissal always
  wins once set.
- **`reenableReminder(documentId, fieldId)`** — `DELETE FROM
  reminder_snoozes WHERE document_id = ? AND field_id = ?`. A full delete
  rather than flipping `dismissed` back to `0`, since once re-enabled
  there's no other meaningful state left on that row to keep (no active
  snooze coexists with a dismissal) — this matches how a document that
  was never snoozed at all has no `reminder_snoozes` row either, so
  "re-enabled" and "never touched" end up in the identical, simplest
  state.
- **`clearReminderFieldValue(documentId, fieldId)`** — `DELETE FROM
  document_field_values WHERE document_id = ? AND field_id = ?`, the same
  delete-only pattern (no reinsert) `clearDefaultReminder()` already
  uses, generalized to take a field id instead of resolving
  `fieldNameToId['Reminder']` internally. Also mutates `d.customFields`
  on the in-memory `allDocs` entry directly, matching
  `clearDefaultReminder()`'s own in-place-mutation approach, so the modal
  and any other open view reflect the change without an extra DB
  round-trip.

All three follow the existing `snoozeReminder()`/`clearDefaultReminder()`
precedent of a direct DB write plus an in-memory update, not a full
`loadDocumentsFromDb()` reload.

### Undo path for Dismiss: a hint on the field itself

A permanent dismissal has no natural expiry the way a snooze does, so
the Edit form — the one place someone would land if they wondered why a
field stopped reminding them — shows a small hint under a dismissed
reminder-type field: *"Reminders are dismissed for this field."* with a
**"Re-enable"** link/button that calls `reenableReminder()`. This follows
the same `.field-hint`-family convention already used for the Currency
guess hint, the orphaned-field hint, and the field-description hint —
one more conditional line stacked under the field's input.

**This needs `documentId` threaded through two functions that don't
currently receive it**: `applyDynamicFieldsForType(prefix, typeName,
existingValues, existingPersonFieldValues, isEdit)` and
`renderGenericFieldHtml(prefix, field, existingValue, orphaned,
amountFilled)`. Both gain one more parameter (a document id, or `null`)
so `renderGenericFieldHtml()` can look up
`reminderSnoozes[`${documentId}:${field.id}`]?.dismissed` for
`reminder`-type fields specifically and render the hint conditionally.
The capture form (`prefix === 'f'`) always passes `null` — there's no
document yet for a dismissal to apply to, so the hint never renders
there regardless of what the new parameter's value ends up being.

### Explicitly out of scope

- The default-reminder context-menu flyout (`.reminder-flyout`, the
  quick-pick UI for the one reserved `'Reminder'` field) is untouched —
  its existing "Clear reminder" option already covers Delete for that one
  field, and this design deliberately doesn't add a matching "Dismiss"
  option there. The three new functions above are generic enough
  (`documentId`/`fieldId`, not tied to any one field name) that a future
  change could wire them into the flyout too without rework, but nothing
  about the flyout changes in this pass.
- No new entry point for Delete/Dismiss outside the Reminders modal — no
  row-context-menu item, no bulk-edit integration, nothing on the detail
  panel. This is scoped to the modal only.

## UI

Per-row markup gains two buttons after the existing Snooze `<select>`:

```html
<button type="button" class="reminder-dismiss-btn" data-doc-id="..." data-field-id="...">Dismiss</button>
<button type="button" class="reminder-delete-btn danger" data-doc-id="..." data-field-id="...">Delete</button>
```

(exact class names/wiring left to the implementation plan). The Edit
form's new hint reuses the existing `.field-hint`/`-hint` line pattern
already stacking under a field — no new CSS class needed for the hint
text itself, just a small inline "Re-enable" control.

## Non-goals

- No confirmation dialog for Dismiss or Delete, consistent with every
  other action in this app.
- No per-value dismissal tracking — dismissal is field-on-document, full
  stop, per the approved design decision.
- No un-delete for the cleared field value — clearing a
  `document_field_values` row is the same "just gone" behavior
  `clearDefaultReminder()` already has today; there's no new undo
  mechanism for this half of the feature (only Dismiss gets a
  re-enable path, since only Dismiss claims to be permanent-but-reversible;
  Delete is explicitly a one-way clear, matching its existing precedent).
- No changes to the flyout, row context menu, bulk-edit form, or any
  other reminder entry point.

## Critical files

- `dossiary.html`:
  - `SCHEMA`/`SCHEMA_MIGRATIONS` — new `reminder_snoozes.dismissed`
    column.
  - `loadReminderSnoozes()`, `checkReminders()`, `snoozeReminder()`,
    `__DEBUG_reminderSnoozes` — all touched by the `reminderSnoozes`
    in-memory shape change (bare string → `{snoozedUntil, dismissed}`).
  - New `dismissReminder(documentId, fieldId)`,
    `reenableReminder(documentId, fieldId)`,
    `clearReminderFieldValue(documentId, fieldId)`.
  - `openRemindersModal()` / `renderReminderRowHtml()` /
    `wireReminderRows()` — new Dismiss/Delete buttons per row, wired to
    the three functions above plus `removeReminderRow()`.
  - `applyDynamicFieldsForType()`, `renderGenericFieldHtml()` — new
    `documentId` parameter threading, plus the new conditional
    dismissed-hint rendering for `reminder`-type fields in the edit form.
  - New i18n keys (Dismiss button, Delete button, the dismissed-field
    hint text, the Re-enable button) across all six `STRINGS` blocks —
    `zh-Hant` derived from the finished `zh-Hans` wording via a real
    OpenCC `s2t` run, this repo's established convention.

## Testing

Extends `tests/test_reminders.py` (the existing reminder-scenario file)
rather than a new file, following this repo's one-file-per-feature
convention scoped to where the existing coverage already lives:

- Clicking Dismiss removes that row from the modal and does **not**
  clear the field's stored value (confirmed via `read_db()` on
  `document_field_values`).
- A dismissed field never reappears in `checkReminders()`'s results on a
  subsequent library reopen, even though its due date is still in the
  past/lookahead window.
- Editing a dismissed field's value to a new date and re-checking
  reminders confirms it's still excluded (the field-on-document scoping,
  not value scoping).
- The Edit form shows the "Reminders are dismissed for this field." hint
  for a dismissed reminder-type field, and does **not** show it for an
  otherwise-identical non-dismissed reminder-type field.
- Clicking "Re-enable" in the Edit form clears the dismissal (confirmed
  both by the hint disappearing and by `checkReminders()` including that
  field again once its date next qualifies).
- Clicking Delete removes that row from the modal and clears the field's
  value (`document_field_values` row actually gone via `read_db()`, not
  just hidden), leaving the document's other fields untouched.
- A document with two reminder-type fields, one Dismissed and one left
  alone: only the dismissed one is excluded from `checkReminders()`,
  confirming the per-field (not per-document) granularity.
- Snoozing, then Dismissing the same field overrides the snooze
  (`reminder_snoozes.snoozed_until` cleared, `dismissed` set) — verified
  directly against the persisted row, not just `checkReminders()`'s
  output, since a stale `snoozed_until` sitting alongside `dismissed = 1`
  would still produce a correct exclusion today but could reappear
  incorrectly if `dismissed`'s own precedence in `checkReminders()` were
  ever weakened later.
- The modal auto-closes once every row has been Dismissed/Deleted/
  Snoozed away, in any mixed combination — not just via Snooze alone as
  the existing coverage checks today.
