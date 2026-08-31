# Default reminder via right-click context menu

## Context

Dossiary's reminder-type custom fields (shipped as v1.17.0) let a person
turn any custom field into a reminder source, but only after configuring
one for a document's type — creating the field inline, choosing type
Reminder, then filling in a date through the Edit form. That's the right
mechanism for a named, structured reminder ("Renewal Date", "Warranty
End"), but it's real friction for the common Outlook-style case: "remind
me about *this* document sometime" with no particular field in mind.

This adds a single, always-available default reminder, reachable directly
from the row's right-click context menu, set via a quick-pick flyout
(Today / Tomorrow / Next week / Custom date…) rather than a form — the
same interaction shape as Outlook's own right-click "Follow Up" flag.

## Approach

### A reserved field, not a new mechanism

The default reminder is an ordinary `fields` row — `name: 'Reminder'`,
`type: 'reminder'` — auto-created once per library, the same way
`migratePeopleToGenericField()` already ensures a `'People'` field exists
(idempotent, checked via `fieldNameToId['Reminder'] !== undefined`, called
from both `initNewLibrary()` and `loadDb()`). `'Reminder'` joins the
existing reserved-name list in `addInlineCustomField()`
(`['People', 'Amount', 'Payment method', ...FIELD_DESCRIPTION_BUILTIN_NAMES]`)
so nobody can accidentally create a colliding custom field by that name.

**Critically, this field is never attached to any type's
`document_type_fields` configuration.** It doesn't need to be "set up" per
document type the way a custom reminder field does — it's simply always
reachable via the context menu, for every document, regardless of type.
This is what keeps the feature small: two existing mechanisms already do
the rest of the work with zero new code.

- `checkReminders()` already reads a document's field values directly
  (`(d.customFields || {})[field.name]`), independent of whether that
  field is configured for the document's current type — a value written
  to the Reminder field is picked up by the very next check, automatic or
  manual, with no changes to `checkReminders()` itself.
- `applyDynamicFieldsForType()`'s existing **orphaned-field** display
  already renders any field with a real, saved value that isn't in the
  current type's configured field list — fully editable, with a
  `.field-orphaned-hint` note. A document with a Reminder value shows it
  in the Edit form this way automatically; no new form-rendering code
  needed there either.

Both of these are existing, already-tested behaviors this feature simply
inherits by construction, not new integration points to build.

### Context menu entry and flyout

`buildDetailActions(id, d)` — the single source of truth already shared
between the detail panel and the row context menu (see the "Right-click
context menu" note in `CLAUDE.md`) — gains one new, unconditional action
descriptor, present for every document regardless of type or existing
reminder state:

- No default reminder set: label reads **"Add reminder"**.
- One already set: label reads **"Reminder: {date}"** (using the same
  `formatDate()` this app already uses everywhere else a date is shown).

Clicking it opens a small flyout menu, positioned near the click point via
`getBoundingClientRect()` on the clicked element and appended to
`document.body` — the identical pattern the existing "Add to Collection"
picker already uses (see `buildDetailActions()`'s own `add-to-collection`
action), including removing itself on an outside click. The flyout offers:

- **Today**
- **Tomorrow**
- **Next week** (`addDaysToIsoDate(todayIsoDate(), 7)`)
- **Custom date…** (reveals an inline `<input type="date">`, same
  hide/reveal pattern the reminders modal's own custom-snooze-date input
  uses — including its `min` attribute set to tomorrow and its
  `color-scheme: dark` rule, both lessons already learned and fixed in
  that feature)
- **Clear reminder** — shown only when a default reminder is currently
  set on this document

Picking a preset or confirming a custom date writes the value immediately
and closes the flyout — no form, no separate save step, matching the
Outlook interaction this is modeled on.

### Mechanics

Two new small functions, mirroring `saveEditedDocument()`'s own existing
per-field write pattern (`DELETE FROM document_field_values WHERE
document_id = ? AND field_id = ?` followed by a fresh `INSERT` when a
value is present):

- `setDefaultReminder(documentId, dateIso)` — deletes any existing row for
  `(documentId, reminderFieldId)`, inserts the new one, updates
  `allDocs`'s in-memory `customFields['Reminder']` for that document,
  persists, and re-renders (refreshing the panel/table row and, if the
  document is currently selected, the detail panel).
- `clearDefaultReminder(documentId)` — the delete half only, same
  in-memory/persist/re-render sequence.

Both are plain, explicit-action writes — no different from any other edit
this app already makes — respecting the same "every write comes from an
explicit click" principle `checkReminders()`'s own read-only design
already follows.

## Out of scope

- No live badge, count, or visual highlight for a set-but-not-yet-due
  default reminder anywhere outside the existing reminders modal /
  "Check reminders" toolbar button flow — matches the shipped feature's
  own explicit "no persistent nav badge" decision.
- The flyout only ever sets a date — no note, label, or description
  field. A person wanting more structure already has the full
  reminder-type custom field mechanism for that.
- `'Reminder'` is never auto-attached to any type's `document_type_fields`
  list by this feature — not even after a person sets one via the
  flyout. By default it stays reachable only via the context menu and,
  once set, the orphaned-field display in Edit. This doesn't prevent a
  person from manually attaching `'Reminder'` to a type themselves via
  the existing Field Settings modal, the same as they could for any other
  field — if they do, it simply becomes a normal (non-orphaned) field in
  the capture/edit forms for that type too, same as any other field
  someone chooses to configure. That's an existing, unrelated mechanism
  this feature doesn't need to special-case for or against.
- No bulk "set reminder" action from the multi-select bulk-action bar —
  this is a single-document, single-click convenience; bulk reminder
  management wasn't asked for and isn't implied by the Outlook comparison.
- The context-menu label shows only the date, not a due/overdue
  indicator (e.g. no "3 days overdue" styling in the menu itself) — that
  richer treatment already exists in the reminders modal, and duplicating
  it in the context menu wasn't part of this request.

## Critical files

- `dossiary.html`:
  - New `migrateDefaultReminderField()` (or folded into an existing
    migration call site) — ensures the `'Reminder'` field row exists,
    following `migratePeopleToGenericField()`'s exact pattern.
  - `addInlineCustomField()`'s reserved-name array — add `'Reminder'`.
  - `buildDetailActions(id, d)` — one new unconditional action descriptor
    and its flyout-building `onClick`, modeled on the existing
    `add-to-collection` action.
  - New `setDefaultReminder()`/`clearDefaultReminder()` functions.
  - New CSS for the flyout (can likely reuse `.bulk-collection-menu`'s
    existing styling wholesale, or a near-identical sibling class).
  - New i18n keys: the two context-menu label variants (plain "Add
    reminder" and the `{date}`-parameterized "Reminder: {date}" form),
    the four flyout choices, and "Clear reminder" — across all six
    `STRINGS` blocks.

## Testing

- The `'Reminder'` field is auto-created for both a brand-new library and
  an existing one that predates this feature, idempotently across a
  reopen.
- `'Reminder'` is rejected as a name when creating a custom field inline,
  matching the existing reserved-name behavior for People/Amount/Payment
  method.
- The context menu shows "Add reminder" for a document with no default
  reminder set, and "Reminder: {date}" once one is.
- Choosing Today/Tomorrow/Next week writes the correct date and updates
  the menu label on the next right-click; Custom date reveals its input
  (hidden before, visible+interactive after, matching the reminders
  modal's own already-fixed hide/reveal pattern) and its `min` attribute
  rejects today-or-earlier.
- Clear reminder removes the value; the menu reverts to "Add reminder" and
  the field disappears from the Edit form's orphaned-fields section for
  that document.
- A default reminder set on a document participates in `checkReminders()`
  exactly like any other reminder-type field value — due/overdue
  inclusion, archived/deleted exclusion, and snoozing (via the existing
  reminders modal) all work unmodified, with no new test surface needed
  in `checkReminders()` itself beyond confirming the Reminder field's
  values flow through the same existing logic.
- The field shows correctly as an orphaned, editable field in the Edit
  form for any document type (since it's never configured for any type),
  and a value changed there is reflected back correctly by the context
  menu's label on the next right-click.
