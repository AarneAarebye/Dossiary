# Reminder-type custom fields

## Context

Dossiary has no way to flag that a document needs attention on a future
date — an insurance policy's renewal, a passport's expiry, a warranty's
end date. This is a natural gap for a personal document archive: the
kind of thing someone captures once and then forgets about until it's
overdue. This spec adds a new custom-field type, `reminder`, plus a
lightweight, on-demand check that surfaces anything due or overdue,
without requiring any background process or push notification —
consistent with this app's single-page, no-server architecture.

## Approach

### A new field type, not a flag on `date`

`fields.type` gains a fifth value, `'reminder'`, alongside the existing
`'text'`/`'number'`/`'date'`/`'checkbox'`/`'person'` set — the same
pattern the app already used for `'person'` (a distinct type for a
distinct semantic meaning, not a generic capability bolted onto an
existing type). A `reminder`-type field is rendered, stored, and
formatted **identically** to a `date`-type field (same `<input
type="date">` in `renderGenericFieldHtml()`, same `.slice(0, 10)`
value handling, same `formatDate()` display in
`formatCustomFieldValue()`) — the only difference is that any field of
this type, on any document, regardless of what it's named ("Warranty
End," "Renewal Date," "Passport Expiry," ...), is automatically a
reminder source for the check described below. There's no single
hardcoded field name and no ambiguity with a document's ordinary `Date`
field — only fields explicitly created as type Reminder participate.

"+ Add a custom field" (`addInlineCustomField()`) and the equivalent
`<select id="f-new-field-type">`/`<select id="e-new-field-type">`
dropdowns gain a sixth option, "Reminder," after "Person." Like
`date`/`checkbox`/`person`, a new reminder field does **not** default to
`autocomplete: 1` (a distinct-values dropdown doesn't suit a date any
more for a reminder than it does for a plain date field). It **does**
participate in the generic `show_as_column` system exactly like `date`
does, so someone can optionally show it as a browsable/sortable table
column independent of the check mechanism below — there's no reason to
withhold that. It does **not** get a filter dropdown, again identically
to `date` — `populateFilters()`'s existing `hasFilter` gate
(`type === 'text' || type === 'checkbox'`) already excludes anything
that isn't one of those two, so `reminder` is excluded there for free,
with no code change needed. Field Settings' per-field capability
checkboxes (`capabilitiesHtml()`) work the same way: its guard is an
*exclusion* list (`fieldDef.type === 'person'` or the literal name
`'Amount'`), not an inclusion list keyed to specific types — so the
"Column" checkbox is already offered to any other field type, including
a brand new `reminder` type, with **zero changes** needed to that
function. The "Autocomplete" checkbox stays excluded via the existing
`fieldDef.type === 'text'` guard, also with no change needed.

### The lookahead window is a per-library setting

A new `settings` row, `reminder_lookahead_days` (a plain integer,
stored as text like every other setting), configured in the Field
Settings modal alongside the existing `default_document_type` and
`default_currency` settings — same `loadX()`/`saveX()` pattern
(`loadReminderLookaheadDays()`/`saveReminderLookaheadDays()`). Unset
defaults to `30`, so a library with no configuration still gets
sensible surfacing rather than reminders effectively being off until
someone finds the setting.

### What counts as due

A reminder-type field value on document *D* is due if:

- `D` is not deleted and not archived (archiving already means "no
  longer needed" per this app's own existing rule for that flag — a
  reminder shouldn't keep resurfacing for something explicitly archived;
  un-archiving is, as always, the sanctioned way back), **and**
- the field's stored date is `<= today + reminder_lookahead_days` (this
  covers both "coming up within the window" and "already overdue," a
  single comparison rather than two separate cases), **and**
- there is no *active* snooze for this exact `(document_id, field_id)`
  pair — a new table, `reminder_snoozes (document_id INTEGER, field_id
  INTEGER, snoozed_until TEXT, PRIMARY KEY(document_id, field_id))`. A
  snooze is active when `snoozed_until` is in the future; once
  `snoozed_until` has itself passed, the reminder becomes eligible again
  on the next check, no explicit "un-snooze" action needed. Keyed by the
  pair (not just document, and not just field) because a single document
  can carry more than one reminder-type field (e.g. both a "Registration
  Renewal" and an "Insurance Renewal" on the same vehicle document), each
  snoozed independently.

The check itself (`checkReminders()`) is a pure, cheap in-memory scan
over `allDocs`/`document_field_values` already loaded — no filesystem
access, no schema change beyond the one new table and the one new
`fields.type` value, no polling.

### Trigger and surfacing

Checked automatically once, right after a library finishes opening
(alongside the existing `checkInbox()`/`recordRecentLibrary()`
fire-and-forget calls in `afterDbReady()`) — silently: if nothing is
due, nothing appears, matching `checkInbox()`'s own "nothing staged,
nothing shown" behavior. Also checked on demand via a new toolbar
button, "🔔 Check reminders" (mirroring the existing "📥 Check inbox"
button's placement and always-visible convention) — a manual click that
finds nothing due shows a brief status-line message ("No reminders
due.") rather than staying silent, since a deliberate click deserves
some confirmation it did something, the same reasoning "Check inbox"
already applies for its own empty case.

When something is due, a modal (`openRemindersModal()`, following the
existing Libraries/licenses modal's general shape — a single scrollable
list, no nested forms) lists every due/overdue reminder, sorted by date
ascending (most overdue first, soonest-upcoming next). Each row shows:
the document's title, the reminder field's name (so a document with more
than one reminder field is unambiguous), the date itself, and a
human-readable "N days overdue" / "due in N days" / "due today"
indicator. Clicking anywhere on a row *other than* its Snooze control
closes the modal and opens that document (selects it in the table,
refreshes the detail panel) — the same "click a result, land on the
document" pattern search results and other lists in this app already
use.

Each row also carries a small Snooze control: four choices — 1 week, 1
month, 3 months, or a custom date via a native date picker — matching
the second AskUserQuestion answer above. Choosing one writes
`(document_id, field_id, snoozed_until)` to `reminder_snoozes` via
`INSERT OR REPLACE` (the same upsert convention every other
settings/keyed table in this app already uses) and removes that row from
the currently-open modal's list immediately (optimistic UI, no need to
re-run the whole check) — the underlying reminder date on the document
itself is never touched by snoozing; only the snooze row changes.

## Out of scope

- Any kind of push notification, background timer, or OS-level alert —
  this is a static, single-page app with no server and no way to run
  code when it isn't open; "checked when the library opens or you click
  the button" is the deliberate, honest ceiling here, not a placeholder
  for something more automatic later.
- Editing or clearing a reminder's underlying date from within the
  reminders modal itself — the modal is for *acknowledging/snoozing*,
  not editing; changing the actual date remains a normal edit via the
  document's own Edit form, same as any other custom field.
- Recurring/repeating reminders (e.g. "remind me every year automatically
  after I renew") — a person editing the date forward by hand, the same
  way they'd update any other field, is the only mechanism; no
  auto-advance logic.
- A persistent nav badge or live-updating count for due reminders (unlike
  the Inbox nav item's own live `needs_review` count) — explicitly ruled
  out during brainstorming in favor of the two explicit triggers
  (library-open, and the manual button) only.
- Reminders on archived or deleted documents — excluded entirely, per the
  "what counts as due" section above; no toggle to include them.

## Critical files

- `dossiary.html`:
  - `SCHEMA`/`SCHEMA_MIGRATIONS` — new `reminder_snoozes` table.
  - `addInlineCustomField()`, and the `<select id="f-new-field-type">`/
    `<select id="e-new-field-type">` markup — new "Reminder" option.
  - `renderGenericFieldHtml()`, `formatCustomFieldValue()` — extend the
    existing `field.type === 'date'` checks to also match `'reminder'`
    (input type, value slicing, display formatting all identical to
    `date`).
  - `capabilitiesHtml()` (Field Settings) — no change needed; its
    exclusion-list guard already offers the Column checkbox to any
    non-`person`, non-`'Amount'` field, and its `type === 'text'` guard
    already excludes Autocomplete for anything that isn't text.
  - New `loadReminderLookaheadDays()`/`saveReminderLookaheadDays()`,
    following `loadDefaultCurrency()`/`saveDefaultCurrency()`'s exact
    pattern, plus its own small control in the Field Settings modal.
  - New `checkReminders()` — the pure in-memory due-reminder scan
    described above.
  - New `openRemindersModal()` and its snooze-writing handler.
  - New "🔔 Check reminders" toolbar button, wired the same way
    `#inbox-check-btn` already is.
  - `afterDbReady()` — one new fire-and-forget `checkReminders()` call
    alongside the existing `checkInbox()`/`recordRecentLibrary()` calls.
  - New i18n keys (field type label, toolbar button, modal strings, snooze
    option labels, "No reminders due" status message) across all six
    `STRINGS` blocks.

## Testing

- Creating a `reminder`-type field inline behaves identically to creating
  a `date`-type field in every respect except the type stored and its
  label in the type dropdown/Field Settings' field list.
- A reminder-type field's Column capability checkbox is offered in Field
  Settings (like `date`); its Autocomplete checkbox is not (like `date`);
  it gets no filter dropdown in the toolbar (like `date`).
- A document with a reminder-type field value inside the configured
  lookahead window, or already past its date, is included in
  `checkReminders()`'s result; one further in the future than the
  lookahead window is not.
- An archived document's due reminder is excluded; un-archiving it makes
  it eligible again on the next check. A deleted document's due reminder
  is excluded, restoring included.
- A document with two different reminder-type fields, one due and one
  not, surfaces only the due one, correctly labeled with its own field
  name.
- Snoozing a row removes it from the current modal's list immediately,
  and it stays excluded on a subsequent check until the chosen snooze
  duration has elapsed — confirmed for all four snooze choices (1 week, 1
  month, 3 months, and a custom date).
- The automatic library-open check shows nothing when nothing is due; the
  manual "Check reminders" button reports "No reminders due" in that same
  case rather than staying silent.
- `reminder_lookahead_days` unset defaults to 30; an explicit saved value
  is honored and changes which reminders are included on the next check.
- Clicking a reminder row (not its Snooze control) closes the modal and
  opens/selects the corresponding document.
- The new `reminder_snoozes` table survives a library reopen and is
  correctly created via `SCHEMA_MIGRATIONS` for a library that predates
  this feature.
