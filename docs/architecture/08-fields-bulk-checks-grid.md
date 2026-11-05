# Dossiary architecture notes: Field descriptions and reminders, bulk edit, duplicate and library checks, grid view, splits

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

- **Field descriptions** (`field_descriptions`, `loadFieldDescriptions()`/
  `saveFieldDescription()`, the "Field Descriptions" section in Field
  Settings — `.fs-descriptions`, `renderFieldDescriptionsList()`) let a
  person attach a short, optional hint to any field — the five built-ins
  (Category, Subcategory, Document Type, Date, Tags) plus every generic
  custom field — shown as a `.field-hint` line under the field's label in
  both the capture and edit forms. **`field_descriptions` is keyed by
  `field_name TEXT PRIMARY KEY`, not `fields.id`**, deliberately — the
  five built-ins have no `fields`-table row at all (they're real `<input>`s
  hardcoded into the capture/edit form markup, not part of the generic
  fields system — see the Custom fields note above), so a `fields.id`
  foreign key simply couldn't reach them. Keying by name instead covers
  both groups — built-ins and generic custom fields — with one uniform
  table and one uniform `fieldDescriptions[name]` lookup, rather than a
  built-in-only mechanism plus a second, `fields.id`-keyed one for custom
  fields. **`FIELD_DESCRIPTION_BUILTIN_NAMES`** (`['Category',
  'Subcategory', 'Document Type', 'Date', 'Tags']`) is a hardcoded array
  for the same reason it can't be derived from anything: unlike
  `dynamicColumnDefs()` or `getUsedDocumentTypes()`, there's no table row
  or other in-memory list that already enumerates "fields with a real form
  input but no `fields` row" — Amount, Currency, and Payment method used
  to be in that category too, but aren't anymore (see the sentinel-fields
  note above), so this array is exactly, and only, the five names left
  over after that migration. **A custom field can share a built-in's exact
  name** (e.g. a Mariner-migrated library with a custom "Date" field, since
  the sibling migration script copies field names generically with no
  reserved-word check) — `renderFieldDescriptionsList()` filters
  `fieldDefs` against `FIELD_DESCRIPTION_BUILTIN_NAMES` before appending
  the custom-fields tail, so the built-in always wins the single shared
  row and the list never shows the same name twice; `addInlineCustomField()`'s
  own reserved-name list was deliberately left alone rather than extended
  to also block this collision, since doing so would change behavior for
  existing libraries that already have such a field, a bigger change than
  this feature warranted.
  **`renderFieldDescriptionsList()` is deliberately NOT re-rendered when
  the selected document type changes in Field Settings**, unlike
  `renderFieldSettingsFieldColumns()` (the Fields/Display Fields columns,
  which are genuinely scoped to `fsSelectedType`) — a description belongs
  to the field itself, independent of which type(s) it happens to be
  attached to, the same "property of the field, not of its relationship to
  `fsSelectedType`" reasoning the Per-field capability checkboxes note
  above already established for `show_as_column`/`autocomplete`. The list
  is built once per modal open and stays correct regardless of which type
  is subsequently selected in the other two columns.
  **The save-on-blur handler has no revert-on-empty guard**, unlike the
  Collections rename input it's modeled on (the Manage Collections modal's
  own rename input resets back to the collection's real name on an empty
  blur, rather than saving a blank one — see the Collections entry in `tests/coverage/01-capture-ocr-fields-inbox-nav.md`
  entry) — because an empty description is a
  valid, meaningful value here (it just means "show no hint for this
  field"), not an error state to reject the way an empty collection name
  would be. Blurring an emptied input saves the empty string via the same
  `INSERT OR REPLACE` path as any other value, and the corresponding
  `.field-hint` line correctly disappears from the capture/edit forms.
  **Description text is never run through `t()`** — like a field's own
  name, it's free-form content someone typed for their own library, not
  app chrome; running it through the translation lookup would be wrong
  twice over — it isn't one of this app's ~930 known UI strings in the
  first place, so `t()`'s fallback would just echo it back unchanged, and
  passing it through `t(key, params)` at all would risk a literal `{...}`
  substring in someone's own description being misread as a substitution
  placeholder (`test_field_descriptions.py`'s own Scenario 9 checks
  exactly this: a description containing a literal `{label}` renders
  verbatim). **Document Type is the one built-in field that already had
  its own permanent `.field-hint` line before this feature** (the "Not in
  the list? Type a new one — it'll be created." autocomplete hint) — its
  new description hint is a SECOND, separate `.field-hint` div appended
  after the existing one, not a replacement; a configured description
  shows both, stacked, and a field with no description set continues
  showing just the original hint exactly as before.
- **Renaming a custom field** (`renameField(oldName, newName)`,
  `startFieldRename()`, the ✎ `.fs-rename` button on each custom-field row
  of Field Settings' Field Descriptions list -- that list, unlike the
  Fields/Display Fields columns, shows every field regardless of the
  selected type, so it's the one place every field is reachable). Needed
  because a field's *name*, not just its id, is a key in several places,
  all of which move together in one save: `fields.name`,
  `document_type_fields.field_name`, `field_descriptions.field_name`, and
  Smart Collection criteria JSON (`currentFilters()` saves dynamic filters
  by `label`, the field name) -- plus their in-memory mirrors
  (`fieldDefs`, `fieldNameToId`, `typeFieldOrder`, `fieldDescriptions`,
  `collections[].criteria`) and every document's `customFields`/
  `personFieldValues` map. Column visibility, sort order, datalists, and
  the Reports breakdown are keyed by `field-<id>` and need nothing.
  **`NON_RENAMEABLE_FIELD_NAMES`** (`People`/`Amount`/`Currency`/
  `Payment method`/`Reminder`) get no rename button, since code resolves
  them by literal name (`fieldNameToId['Reminder']`, `formatAmount()`, the
  migrations' idempotency checks); those names plus
  `FIELD_DESCRIPTION_BUILTIN_NAMES` are also rejected as rename *targets*,
  along with any existing field name. Inline edit follows the Collections
  rename input's convention (Enter/blur saves, Escape cancels -- with
  `stopPropagation()` so Escape doesn't also close Field Settings), except
  a rejected name keeps the input open with the reason shown in
  `.fs-rename-status`. Sidecar `.txt` files carry field names
  ("Organization: ..."), so after the rename is saved every document with a
  value in that field gets its sidecar rewritten (`writeSidecarForDoc()`,
  best-effort per file -- one unwritable sidecar mustn't undo a rename
  that's already persisted). `writeSidecarForDoc(d)` is the shared "rewrite
  from in-memory state" helper; bulk edit and "Make searchable" use it too.
- **Reminder-type custom fields** (`fields.type === 'reminder'`, a fifth
  value alongside `text`/`number`/`date`/`checkbox`/`person`) let a
  person turn any custom field — Renewal Date, Warranty End, Policy
  Expiry, whatever name they give it — into a source the app proactively
  surfaces as it comes due, without a fixed, single "the one reminder
  field" concept anywhere. **It's deliberately not a new input shape at
  all**: `renderGenericFieldHtml()`'s `inputType`/value-slicing logic
  checks `field.type === 'date' || field.type === 'reminder'` (picking
  the native `<input type="date">` and slicing `existingValue` to its
  first 10 characters exactly as `date` already does), and
  `formatCustomFieldValue()`'s display formatter has the identical
  `field.type === 'date' || field.type === 'reminder'` check routing both
  through `formatDate()` — a reminder field captures, stores
  (`document_field_values.value`, a plain ISO date string, same column
  every other field type shares), and displays exactly like a Date field
  in every respect except the one flag `checkReminders()` reads. Creating
  one works through the same inline "+ Add a custom field" flow as any
  other type (`addInlineCustomField()`'s type dropdown gains a `Reminder`
  option next to Text/Number/Date/Checkbox/Person) — it gets no
  autocomplete default the way a new Text field does (`autocomplete =
  type === 'text' ? 1 : 0`, unchanged), and in Field Settings'
  per-field capability checkboxes it's offered the **Column** checkbox
  like almost any field (`capabilitiesHtml()`'s guard excludes only
  People and the field literally named `'Amount'` — a
  reminder field isn't either) but never the **Autocomplete** checkbox
  (that one's gated on `field.type === 'text'` specifically, same as
  Date/Number/Checkbox always were) — a dropdown of distinct dates isn't
  a useful autocomplete any more for a reminder than it ever was for a
  plain date.
  **Any field with `type: 'reminder'`, on any document, is automatically
  a reminder source — there is no hardcoded field name anywhere in this
  feature.** `checkReminders()` starts from `fieldDefs.filter(f => f.type
  === 'reminder')`, so a library can have zero, one, or several such
  fields (a document can even carry more than one at once — an
  insurance-policy document with both a Renewal Date and a separate
  Inspection Due field), and every one of them participates identically.
  **`reminder_lookahead_days`** (a `settings` row, `reminderLookaheadDays`
  in JS, defaulting to **30** — `loadReminderLookaheadDays()` falls back
  to 30 for a missing row or anything that doesn't parse as a
  non-negative integer, `saveReminderLookaheadDays()` applies the same
  validation on write) controls how far into the future a reminder counts
  as "coming up soon," and lives in the Field Settings modal right
  alongside `default_document_type`/`default_currency` — same
  `settings`-table `key`/`value` pattern, same per-library scope, same
  reason for living there (no general settings-modal infrastructure
  exists in this app; a control sits spatially attached to what it
  configures). **`reminder_snoozes` (`document_id INTEGER, field_id
  INTEGER, snoozed_until TEXT, PRIMARY KEY (document_id, field_id)`) is
  keyed by a compound `(document_id, field_id)` pair, not just
  `document_id`** — necessarily, since a single document can carry more
  than one reminder-type field (see the two-reminder-field case just
  above), and each needs its own independent snooze state; a
  `document_id`-only key would silently conflate them. Loaded once per
  library open into an in-memory `reminderSnoozes` map keyed by the
  string `` `${documentId}:${fieldId}` `` (`loadReminderSnoozes()`,
  called from `loadDocumentsFromDb()` alongside `loadReminderLookaheadDays()`).
  **What counts as "due"** (`checkReminders()`, a pure, synchronous,
  in-memory scan over `allDocs` — no filesystem or network I/O, matching
  this app's "no silent/background work" principle) is: the document
  isn't `deleted` or `archived`; a reminder-type field on it has a
  non-blank value; that value's date-only portion is on or before
  `addDaysToIsoDate(todayIsoDate(), reminderLookaheadDays)` (so an
  already-overdue date is included with no lower bound, not just ones
  landing inside the window ahead); and, if `reminderSnoozes` has an
  entry for that exact `documentId:fieldId` pair, its `snoozed_until`
  must **not** be strictly after today (an active, still-in-the-future
  snooze excludes the reminder; an expired one — `snoozed_until` today or
  earlier — no longer does, so a snoozed reminder resurfaces on its own
  once the snooze lapses, without anyone having to un-snooze it
  manually). Results are sorted by date ascending, most overdue first.
  **Two explicit trigger points only, no live badge, no background
  polling** — `afterDbReady()` calls `checkReminders()` synchronously
  right after a library finishes loading (safe to do inline, unlike
  `checkInbox()`'s own fire-and-forget call just above it in the same
  function, precisely because this is an in-memory scan with no I/O to
  await) and opens the reminders modal automatically only if anything
  came back due, staying silent otherwise; and the always-visible
  toolbar's **"🔔 Check reminders" button** (`#check-reminders-btn` →
  `checkRemindersAndShowStatus()`) re-runs the same scan on demand,
  reporting `t('reminderNoneDue')` ("No reminders due.") on the status
  line when nothing's due or opening the modal when something is. This
  mirrors `checkInbox()`'s own precedent exactly (see the Inbox note
  above) and for the same reason: the automatic on-open check alone can't
  notice a reminder that becomes due while a library is already sitting
  open in a tab (the same gap `#inbox-check-btn` exists to close for
  staged files), so a manual re-check button is the fix rather than
  polling in the background.
  **`openRemindersModal(dueReminders)`** renders one `.reminder-row` per
  due reminder (via `renderReminderRowHtml()`, called from
  `wireReminderRows()`), each showing the document's title, the
  reminder's field name, its formatted date, and a due/overdue label from
  **`reminderDueLabel(dateIso, todayIso)`** ("Due today" / "N days
  overdue" / "Due in N days", singular/plural handled the same
  ternary-and-key-pair way every other count-dependent string in this app
  is — see the i18n note's own explanation of that pattern). Every row
  offers all four snooze choices (1 week / 1 month / 3 months / a custom
  date via a `<select>` plus a normally-hidden `<input type="date">` that
  only appears once "Custom date…" is chosen) — **`addDaysToIsoDate(iso,
  days)`** is the one shared date-math helper behind both the 1w/1m/3m
  offsets here and the lookahead cutoff above, so there's exactly one
  place that knows how to add N days to an ISO date string.
  **`snoozeReminder(documentId, fieldId, snoozedUntil)` writes only to
  `reminder_snoozes` (`INSERT OR REPLACE`, keyed by the same compound
  pair) — it never touches the reminder field's own stored date.**
  Snoozing is purely "stop bothering me about this until then," not a
  rescheduling of the underlying event; the document's actual Renewal
  Date/Warranty End/etc. value is completely unaffected, and un-snoozing
  early isn't even a feature — the snooze simply expires on its own once
  `snoozed_until` is no longer in the future. Snoozing a row removes it
  from the open modal immediately (`removeReminderRow()`), and once every
  row has been snoozed away the modal closes itself automatically rather
  than sitting open and empty. Clicking a row anywhere outside its
  snooze controls closes the modal, selects that document
  (`selectedDocId = documentId`), re-renders the table so the row
  highlights, and opens its detail panel — the same four operations
  `saveEditedDocument()`'s own success path performs (see the persistent
  detail panel note's "Two call sites that used to rely on an implicit
  trick" paragraph above), just in a different order here (`closeModal()`
  runs first, before `selectedDocId` is even set, since closing the modal
  doesn't depend on which document ends up selected).
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
  hint never renders there. **The Re-enable link's own click handler removes
  only its own hint `<div>`** (`btn.closest('.field-hint').remove()`),
  deliberately NOT by calling `applyDynamicFieldsForType()` again to rebuild
  the whole dynamic-fields container — an earlier version of this feature did
  exactly that, and it was a real bug (caught and fixed in this feature's own
  review): that rebuild reads the document's *originally-persisted* values
  (see the orphaned-field note above), so it would silently discard whatever
  someone had already typed into any *other* field on the same, still-open
  Edit form — the same class of hazard `addInlineCustomField()`'s own
  "critical correctness property" note above exists to prevent for a
  different action (adding a new custom field mid-edit). **`clearReminderFieldValue()` calls `render()`
  but deliberately not `openDetail()`** — unlike `clearDefaultReminder()`,
  which is only ever reached from a context already focused on one specific
  document, Delete can be clicked repeatedly for several different
  documents while working through the Reminders modal's list, and forcing
  the persistent detail panel to jump to each one in turn would be a
  jarring side effect of what's meant to be a quick cleanup action; if the
  panel already happens to be open on the affected document, its displayed
  value may lag until the next unrelated render/selection change, an
  accepted, narrow tradeoff rather than a correctness issue.
  **Clearing a reminder-type field's value (Delete in the Reminders modal, or
  "Clear reminder" in the row context-menu flyout — `clearDefaultReminder()`
  now delegates straight to `clearReminderFieldValue()`, differing only in
  resolving `fieldNameToId['Reminder']` and its own trailing `openDetail()`
  call) also deletes any lingering `reminder_snoozes` row for that exact
  `(document_id, field_id)` pair**, dismissal included — the same "no stored
  value left means there's nothing left to stay dismissed about" reasoning
  `reenableReminder()` already uses, inlined rather than calling
  `reenableReminder()` itself to avoid a second, redundant `persistDb()`.
  Without this, a dismissed reminder whose value gets cleared and later
  re-set to a brand-new value would stay silently, invisibly dismissed —
  `checkReminders()` would never surface it and no UI would show it as
  dismissed anymore, since the Edit-form hint above only renders for a field
  that still has a stored value.
- **The default-reminder context menu** (`migrateDefaultReminderField()`,
  `buildDetailActions()`'s `'default-reminder'` action, `.reminder-flyout`)
  extends the Reminder-type custom fields note above with a single,
  reserved, always-available reminder every document can carry, reachable
  directly from a right-click without first configuring a reminder-type
  field for that document's type at all. **`'Reminder'` is an ordinary
  `fields` row with `type: 'reminder'`** — `migrateDefaultReminderField()`
  (called from both `initNewLibrary()` and `loadDb()`, the same
  idempotent-by-name-check pattern as `migrateSentinelFieldsToGeneric()`/
  `migratePeopleToGenericField()` above: it returns immediately once
  `fieldNameToId['Reminder']` is already set) inserts it once per library,
  with `show_as_column: 0, autocomplete: 0`. It's a real reserved name too
  — `addInlineCustomField()`'s reserved-name check (`['People', 'Amount',
  'Payment method', 'Reminder', ...FIELD_DESCRIPTION_BUILTIN_NAMES]`)
  rejects anyone trying to create a colliding custom field by that name.
  **Deliberately never added to `document_type_fields` for any type** —
  nothing in this feature auto-attaches it, so `checkReminders()`'s "any
  field with `type === 'reminder'`" scan and the Edit form's
  orphaned-field display (see the "orphaned" paragraph above) already
  cover it with zero code changes to either: since it's never configured
  for a type, any document holding a value for it shows that value as an
  orphaned field in Edit, exactly like a reminder-type field removed from
  its type's own configuration would. A person can still manually attach
  it via Field Settings if they want it to render as a normal,
  non-orphaned field for some type — this app just never does that
  automatically.
  **`buildDetailActions(id, d)` is the single function shared between the
  row context menu (`showRowContextMenu()`) and the persistent detail
  panel (`openDetail()`)** — see that function's own note above — so the
  new `'default-reminder'` action (inserted right after `'edit'`, before
  the `SHOW_DOCUMENT_PREVIEW`-gated `'regen-thumb'` entry) appears in both
  places automatically. Its label has two states, computed from
  `d.customFields['Reminder']`: `t('contextMenuAddReminder')` ("Add
  reminder") when unset, `t('contextMenuReminderSet', {date:
  formatDate(...)})` ("Reminder: <date>") when set. Because the panel's
  own rendering reads a separate, hardcoded `actionIdByKey` map
  (`openDetail()`'s own `const actionIdByKey = {...}`) rather than the
  context menu's fully generic iteration, the action needed an explicit
  `'default-reminder': 'default-reminder-btn'` entry there too — without
  it the panel button would render as `id="undefined"`, a real bug the
  branch's own review caught, now guarded by `test_default_reminder.py`'s
  own Scenario 10.
  **The quick-pick flyout is a separate floating `<div
  class="reminder-flyout">` appended to `document.body`, not a child of
  `.row-context-menu`** — the same pattern `'add-to-collection'`'s own
  picker (`.bulk-collection-menu`) already established just below it in
  `buildDetailActions()`: `showRowContextMenu()`'s generic `closeMenu()`
  only ever removes its own `.row-context-menu` element, so a
  picker/flyout that lived inside it would vanish the instant the action
  that opened it finishes running. Being a sibling element tracked by its
  own module-level `openReminderFlyout` variable and its own
  outside-click listener is what lets it survive that auto-close. Offers
  **Today**/**Tomorrow**/**Next week** (`todayIsoDate()`,
  `addDaysToIsoDate(todayIsoDate(), 1)`, `addDaysToIsoDate(todayIsoDate(),
  7)` — the same shared date-math helper the reminders modal's own snooze
  offsets use, see above), **Custom date** (reveals it by replacing the
  flyout's whole `innerHTML` with a fresh `<input type="date"
  class="reminder-flyout-custom-date">` — there's no pre-existing hidden
  element the way the reminders modal's own `.reminder-snooze-custom-date`
  has, since this flyout swaps its entire content per view rather than
  toggling `display`. The resulting input still has `min` set
  to tomorrow and `color-scheme: dark`, mirroring the reminders modal's
  own `.reminder-snooze-custom-date` input's own behavior, and the same
  defensive re-check of `input.value <= todayIsoDate()` for the same
  reason that modal's own handler has one — a native date input's `min` can be
  bypassed by a manually typed value in some browsers), and **Clear
  reminder**, rendered only when `d.customFields['Reminder']` already has
  a value — there's nothing to clear otherwise.
  **`setDefaultReminder(documentId, dateIso)`/`clearDefaultReminder(documentId)`
  write via the exact delete-then-insert pattern `saveEditedDocument()`
  already uses for every other field's `document_field_values` row** —
  `DELETE FROM document_field_values WHERE document_id = ? AND field_id =
  ?` followed by a fresh `INSERT` (set) or nothing (clear), against
  `fieldNameToId['Reminder']`. Both also mutate `d.customFields` directly
  on the same object `allDocs` already holds (matching `toggleArchived()`'s
  own in-place-mutation approach) before calling
  `persistDb()`/`render()`/`openDetail(documentId)`, so the panel and any
  reopened context menu reflect the new value with no extra DB round-trip
  needed to redisplay it. **This is completely unrelated to
  `reminder_snoozes`** (see above) — snoozing/clearing the default
  reminder never touches that table; `reminder_snoozes` exists
  specifically for postponing a reminder-type field's own due date without
  touching its stored value, a concept this feature has no equivalent of
  — clearing the default reminder means deleting its
  `document_field_values` row outright, not writing a snooze.
  **A real click-bubbling bug, caught and fixed during this feature's own
  review**: the flyout option buttons' click handler calls
  `evt.stopPropagation()` — without it, choosing "Custom date…" (whose
  handler synchronously reassigns `flyout.innerHTML` to swap in the date
  input, detaching the very button that was just clicked, before that
  click event finishes bubbling to `document`) let the bubbled click reach
  the flyout's own `outsideClick` listener, whose `flyout.contains(evt.target)`
  check then saw a no-longer-attached target and immediately removed the
  flyout it had just switched to the custom-date view. The other four
  choices don't hit this race (they `await` before touching the DOM, so
  the bubble finishes first) — an obscure default (a synchronous DOM
  mutation racing an in-flight event's own bubble phase) that "works fine"
  right up until the one branch that doesn't take the `await`-first path,
  the same spirit as this file's own DOCTYPE/quirks-mode note above.
- **Comma-aware autocomplete for multi-valued fields** (`wireCommaAutocomplete()`)
  fixes a real limitation of native `<input list="...">`: the browser only
  ever matches suggestions against the *whole* input value, never a
  substring of it, so a comma-separated field (People/Author/Collaborator/
  any other person-type field, and Tags) only ever offered suggestions for
  the *first* entry typed — after "Birgit, " and starting a second name,
  nothing suggested, since no datalist option's value literally starts
  with "Birgit, A". `wireCommaAutocomplete(input, datalistId)` replaces the
  native mechanism by hand: on every keystroke it takes the text after the
  last comma, filters the given datalist's own `<option>` values by it
  (case-insensitive substring, excluding names already used earlier in the
  same input), and renders a small clickable/keyboard-navigable suggestion
  list (`.comma-autocomplete-dropdown`) positioned under the input via the
  existing `.field-with-clear` wrapper's `position:relative` — the same
  wrapper every comma-separated field already had for its clear button, so
  no new markup was needed there. The native `list` attribute is removed
  once this takes over (`input.removeAttribute('list')`), so the browser's
  own broken-for-this-case popup never appears alongside the real one.
  Selecting a suggestion (click, or Enter on a keyboard-highlighted item)
  replaces just the current segment and appends `", "` so typing the next
  entry can continue immediately. Wired from three places: the generic
  `applyDynamicFieldsForType()` rebuild pass (covers every person-type
  field, People included, the same way its clear-button rewiring already
  does), `addInlineCustomField()`'s own insert path (a newly-created
  person-type field, appended without a full container rebuild), and two
  one-off calls for `#f-tags`/`#e-tags` (Tags isn't part of the dynamic
  fields system at all, same as its clear button). A
  `dataset.commaAutocompleteWired` guard makes the function idempotent,
  though in practice every one of these three call sites only ever wires a
  freshly-rendered element, so the guard is defensive rather than
  load-bearing.
- **Bulk edit** (`openBulkEditForm(ids)`, `saveBulkEdit(ids)`, reachable via a
  new "Edit" button in the bulk-action bar and a minimal right-click context
  menu on checked rows) lets someone set field values across every currently
  selected document in one save. It's structurally parallel to the
  single-document Edit form but with two deliberate differences forced by
  operating on many documents at once instead of one: every field starts
  genuinely blank (there's no single correct document to pre-fill from), and
  every **replace-semantics** field (Document Type, Category, Subcategory,
  Date, Notes, every generic custom field) carries its own "Apply to all"
  checkbox, unchecked by default — only checked fields are written to any
  document, and checking one with a blank value is a valid, explicit "clear
  this on every selected document." This is necessary, not just a UX nicety:
  "blank" already means different things per field type elsewhere in this app
  (an unchecked checkbox field is real data, not "unset" — see
  `readDynamicFieldValues()`'s own rule), so there's no value-based way to
  distinguish "leave this alone" from "clear it" that works uniformly across
  every field type; the explicit checkbox is the one mechanism that does.
  **Tags and every person-type field (People, Author, Collaborator, …) get an
  "Add to existing"/"Replace existing" mode toggle instead of an Apply
  checkbox** — the toggle itself is the explicit opt-in (Add, the default, is
  already a safe no-op on a blank input), so no separate checkbox is needed;
  Replace mode reuses the exact delete-then-reinsert `saveEditedDocument()`
  already does for a single document's Tags/People, looped per selected
  document, and — like the scalar fields above — a blank input on Replace
  mode is a deliberate, explicit "clear this on every selected document."
  **Title and the OCR-text box are deliberately excluded** — bulk-setting
  every selected document's title to the identical string has no sensible use
  case (and would actively harm the table's own scannability), and OCR text
  is per-file extracted content tied to that document's own file, not
  metadata in the sense the rest of this form edits.
  **`computeBulkFieldUnion(ids)`** computes, once per modal open, the union
  of every field configured for *any* selected document's Document Type plus
  any field *any* selected document currently holds a value for — since
  selected documents can span different types with different
  `document_type_fields` configurations. A field not common to *every*
  selected document's type renders with the same `.field-orphaned`
  class/hint the single-document Edit form already uses for a field no
  longer configured for a document's current type — here it signals "this
  field doesn't belong to every selected document's type, but applying it
  here still writes it for all of them" (the same underlying mechanic as
  editing a genuinely orphaned field on one document already does), a
  related but distinct meaning from that form's own use of the same class,
  worth keeping straight if this is ever touched again. The union is fixed
  for the life of the form — it is **not** recomputed if the form's own
  Document Type field is changed mid-edit, a deliberate scope cut to avoid
  reconciling against the original per-document union for what would be a
  rare case (changing Document Type as part of the same bulk edit that's
  also setting other fields). **`saveBulkEdit()` snapshots this same union
  exactly once, as `const fieldUnion = computeBulkFieldUnion(ids)` at the
  very top of its `try{}` block, before any write runs** — not because the
  form's own field set can change mid-save (it can't; the form is already
  closed by the time this runs), but because the scalar-field write block
  immediately below it can mutate a selected document's in-memory
  `d.document_type` (when Document Type's own Apply box is checked in the
  same save), and `document_type` is exactly what `computeBulkFieldUnion()`
  groups by. A live-reproduced bug during this feature's own review called
  a fresh `computeBulkFieldUnion(ids)` *after* that mutation for the
  person/generic write loops that follow — which then silently dropped any
  other checked field not configured for a document's *new* type, discarding
  a write the person had explicitly asked for with no error or indication
  anything was skipped. Snapshotting once up front, before the mutation, is
  what keeps every later write block acting on the same field set the form
  actually rendered and the person actually saw when they checked those boxes.
  **The mixed-value indicator** (`bulkScalarMixed()`, `bulkSetMixed()`,
  `refreshBulkMixedHints()`) flags, per field, whether the selected
  documents' *current* values for it already disagree (blank/unset counts as
  one shared value for this comparison — "all blank" isn't mixed, "some set,
  some blank" is) — a field where everyone already agrees gets no hint at
  all. Wording depends on semantics: an additive field on its default Add
  mode gets a purely informational note ("what you enter is added on top,
  nothing is removed"); a replace-semantics field, or an additive field
  switched to Replace mode, gets a real overwrite warning ("checking Apply
  will overwrite ALL of them with the value you enter") — re-evaluated live
  whenever a Tags/person-field mode toggle changes, via a `change` listener
  on every `input[name^="bulk-tags-mode"], input[name^="bulk-field-"]`
  radio, so the hint's wording never lags behind the currently-selected mode.
  **Every DB write for a bulk-edit save is batched into exactly one
  `persistDb()`/`render()` call**, following the same reasoning
  `bulkSetArchived()`/`bulkSetDeleted()`/`bulkSetNeedsReview()` already
  document: looping per-document save functions would re-serialize the whole
  SQLite database once per selected document, which bulk actions exist
  specifically to avoid. Unlike those three functions, though, **a bulk-edit
  save does NOT clear `selectedDocIds`** — editing field values doesn't
  remove a document from the current view the way archiving/deleting/
  flagging can, so keeping the selection lets someone chain a further bulk
  action against the same documents without re-checking every row.
  `saveBulkEdit()` also rewrites every affected document's sidecar `.txt`
  (`sidecarBaseNameFromFilePath()`/`buildSidecarText()`/`writeSidecarFile()`,
  the same three functions `saveEditedDocument()` already uses) from each
  document's complete post-edit in-memory state, not just the fields that
  changed — this has to run after every write block above has already
  updated `d.customFields`/`d.personFieldValues`/`d.tags`/etc. in place, for
  the same reason `saveEditedDocument()`'s own sidecar rewrite is its
  next-to-last step, right before `persistDb()`.
  **The right-click entry point (`showBulkRowContextMenu()`) is mutually
  exclusive with the existing single-document context menu
  (`showRowContextMenu()`) on a per-row basis, not a per-selection one**: the
  existing row `contextmenu` listener branches to the bulk menu only when the
  specific row that was right-clicked is itself checked AND `selectedDocIds`
  has 2+ members — right-clicking an *unchecked* row still shows today's
  single-document menu even while other rows are checked elsewhere, matching
  Finder/Explorer/Gmail's own convention for this exact ambiguity. Unlike
  `showRowContextMenu()`, the bulk branch deliberately does **not** touch
  `selectedDocId`, the detail panel's content, or the single-row `.row-selected`
  highlight — the action targets the whole multi-selection, not specifically
  whichever row happened to be right-clicked, and that row's own checkbox
  already reflects its membership in the selection the menu is about to act
  on. The bulk menu itself is deliberately minimal — just "Edit" — since
  Archive/Delete/Flag for review already have their own buttons in the
  bulk-action bar; duplicating them in the context menu wasn't judged worth
  the extra code for what's already one click away.
  **Dragging documents onto a collection** (`startDocDrag()`,
  `endDocDrag()`, `dropDocsOnCollection()`): rows and grid tiles are
  `draggable` (not in the Waste bin), and every *manual* collection in the
  nav accepts the drop -- a smart collection's rules decide its membership,
  so it doesn't. A checked row carries the whole checked selection (shown
  as an "N documents" drag image), an unchecked one only itself; the drop
  goes through `addDocumentsToCollection()`, and the status line counts
  only documents that weren't in the collection yet ("Already in …"
  otherwise). `draggedDocIds` is set only while one of our own items is
  being dragged, and the page-wide file-drop listeners (drag-and-drop
  import, `#drop-overlay`) return early while it is, so an internal drag
  never shows the import overlay or imports anything. Dragging over a
  collapsed Collections header opens it for the drag only
  (`dragOpenedCollections`, restored without saving the setting). A
  `document`-level `dragend` also ends the drag, since a `render()` during
  the drop can replace the source row before its own `dragend` fires.
  **Collection folders** (`collection_folders (id, name)`,
  `collections.folder_id` via `SCHEMA_MIGRATIONS`, `collectionFolders`,
  `toggleCollectionFolder()`, `renderManageFoldersList()`) only group
  collections in the nav: each folder is a foldable `.nav-folder-header`
  with its collections indented under it, then the unfiled collections.
  Which folders are folded is the `collapsed_collection_folders` setting
  (a JSON id list). Folders are created, renamed and deleted in Manage
  collections, where every collection gets a folder `<select>` (only once a
  folder exists); deleting a folder sets its collections' `folder_id` to
  NULL rather than deleting anything, and a `folder_id` pointing at a
  missing folder reads as unfiled. Dragging documents over a folded folder
  opens it for the drag (`dragOpenedFolders`). "Copy the setup of" copies
  the folders and each smart collection's `folder_id` -- checked with a
  probe `SELECT folder_id`, since an older source library lacks the column
  and a failing SELECT would otherwise skip every smart collection.
- **Duplicate detection** (`documents.file_hash`, `computeFileHash()`,
  `openLibraryCheckModal()`) flags two kinds of likely-duplicate document:
  an exact match on the file's own bytes, and a heuristic match on
  Title + Date. **The hash is computed on the original uploaded bytes, not
  the active `file_path`** -- `buildSearchablePdf()` can rasterize-and-rebuild
  a captured file during OCR, and two byte-identical source scans processed
  through that pipeline at different moments can produce slightly different
  output bytes (embedded timestamps and similar); hashing the *processed*
  file would silently defeat exact-duplicate detection for exactly the case
  it exists to catch. Since `writeOriginalToSubfolder()` already
  unconditionally preserves every new document's raw upload, the hash is
  computed on that same original, at the same moment it's written --
  falling back to hashing `file_path` only for a document with no preserved
  original (a LibraryLifeboat-migrated document, predating this app's own
  ingestion pipeline).
  **New documents get their hash computed and stored at creation time**
  (`saveNewDocument()`, `createReviewDocumentFromFile()`) -- one file,
  already being read at that moment anyway. **Existing documents are
  backfilled lazily**: the first time "Library check" (originally "Find
  duplicates" — see the rename note below) is opened, it reads
  and hashes every not-yet-hashed document's file once, with a progress
  indicator (the same spinner-plus-status-text treatment `runOcr()`'s own
  PDF-page-by-page progress already uses), so every later scan and every
  capture-time check is instant. Until that first backfill runs, the
  capture-time warning can only catch matches against documents that
  already happen to have a hash. **The first backfill can be very slow on a
  cloud-synced library folder** (reported on a 1,345-document library on
  iCloud Drive: an evicted file has to be downloaded before it can be
  read, so hashing means downloading), which shaped three properties of
  the loop: it reads **4 files concurrently** (`BACKFILL_CONCURRENCY`),
  mostly to overlap those downloads; it **persists every 25 hashes**
  (`BACKFILL_PERSIST_EVERY`, plus once at the end) rather than only at the
  end -- `persistDb()` calls are chained through one promise so two
  workers never race on `library.sqlite`'s `createWritable()` -- so a
  closed tab or reload keeps what's done; and it shows a **Stop** button
  (`#duplicates-stop-btn`) that lets in-flight reads finish, persists,
  and shows the results with a note (`#duplicates-stopped-note`) that the
  exact-duplicate section is incomplete. The next Library check resumes
  naturally, since it only ever backfills documents whose `file_hash` is
  still unset. The modal's own close control, backdrop-click, and Escape
  key stay gated on the in-progress backfill flag -- the same "disable,
  only re-enable on completion" treatment the scan dialog uses while a scan
  runs (`scanDialogRunning`, set by `startScanFromDialog()`) -- so Stop is the one sanctioned way out
  mid-pass. A failed mid-pass save sets the same stop flag, so the other
  workers don't keep hashing after the error has already propagated.
  **The capture form warns, non-blocking, the moment a file is picked**
  (`handlePickedFile()`), checking the picked file's hash against every
  non-deleted document's `file_hash` in `allDocs` (the same `!d.deleted`
  exclusion every other duplicate-detection pass in this feature uses) and
  showing a dismissible
  `.field-guess-hint`-style line naming the matched document, with a link
  to open its detail panel -- Save stays enabled regardless. This checks
  the exact-hash case only, never Title+Date -- form fields may still be
  blank at pick time, so a heuristic warning that early would just be
  noise. The hash computed at pick time (`pendingFileHash`/
  `pendingFileHashFile`) is cached and reused at Save rather than
  recomputed, since nothing about the file changes in between.
  **Inbox and drag-and-drop bulk adds silently skip (with explicit
  reporting) a staged file whose hash exactly matches an existing
  document**, via the shared `createReviewDocumentFromFile(file, source)`
  helper both already call -- no document is created for it, its staged
  copy is removed from `inbox/` exactly like a normal successful add
  (an identical copy already lives safely in `files/`, so nothing unique
  is lost), and it's counted toward a new "N skipped as duplicates" clause
  on the status line, alongside the existing "Added N document(s)..."
  report. This is a genuine behavior change -- Inbox had never silently
  not-added a staged file before -- and the explicit status-line reporting
  is what keeps it from being *silent*, per this app's own "no silent
  writes" working convention: nothing here omits information from the
  person, it just avoids creating a redundant document.
  `createReviewDocumentFromFile()` computes the hash and checks for a
  duplicate match **before** writing the file copy or preserving the
  original — not after — specifically so a skipped duplicate never
  writes anything to `files/` at all: an earlier version of this function
  hashed after both writes, which left an orphaned file copy and preserved
  original behind under the reserved id every time a duplicate was
  skipped, and — because the id counter was also rolled back — the *next*
  genuinely-new document then reused that same id, landing its own real
  files right next to those orphans. Checking first avoids that scenario
  outright rather than tolerating it.
  **"Find duplicates"** (a new toolbar button, since renamed "Library
  check" — see the next note — alongside `🔔 Check
  reminders`/`📥 Check inbox` -- the same family of explicit, on-demand
  maintenance actions) opens a modal structured like the Reminders modal:
  after any needed backfill, `allDocs` (deleted documents excluded from
  every grouping pass; archived and needs-review documents included, same
  "tells the truth about the whole non-deleted library" reasoning
  Reports/Collections already use) is grouped two independent ways --
  `computeExactHashDuplicateGroups()` and `computeMetadataDuplicateGroups()`
  -- each producing its own rows, tagged "Exact file match" or "Likely
  duplicate (title + date)"; a document that happens to satisfy both
  passes simply appears in both groups' own rows, rather than being
  deduplicated across the two pass types. A document with a blank Title or
  blank Date is excluded from the Title+Date pass entirely, since matching
  against an empty string would produce meaningless mass-groupings.
  Clicking a document in a group closes the modal, selects that document,
  and opens its detail panel -- the same click-through pattern the
  Reminders modal's own rows already use -- where the existing
  Archive/Delete/Edit actions do the actual resolving; this feature adds
  no bespoke delete or merge action of its own. **The click also filters
  the table down to that whole group**, so the copies sit side by side
  instead of being scattered through (or hidden from) the current view:
  it reuses the Reports drill-down (`drillIntoReportRow(docIds, label,
  'library-check')`, `currentView = 'report-drilldown'`), whose
  archived/needs-review-inclusive, deleted-exclusive membership is exactly
  what duplicate detection counts, so the banner's count always matches
  the group. A new `reportDrilldownReturnTo` state (`'reports'` |
  `'library-check'`, reset in `resetAll()`) picks the banner's back-link
  label (`reportDrilldownBackLink` vs `libraryCheckBackLink`, set in
  `updateReportDrilldownBanner()` on every render rather than only via
  `data-i18n`) and target: for Library check it returns to All Documents
  and reopens the modal, recomputed fresh so a just-deleted duplicate is
  gone, and instant since every document is hashed by then. A
  broken-link row has no group, so clicking it only selects the document,
  as before. Like a Reports drill-down, the group is a snapshot taken at
  click time. **"Not a duplicate" marks** (`not_duplicate_groups
  (group_key TEXT PRIMARY KEY)`, `notDuplicateKeys`, `duplicateGroupKey()`,
  `setNotDuplicate()`, the `.not-duplicate-checkbox` in each group's
  heading) let a person record that a group isn't really a duplicate
  without resolving anything: the group stays listed -- ticked, dimmed,
  `.not-duplicate` -- and sorts after the still-undecided groups of its
  kind the next time the check opens (not immediately, so the list
  doesn't jump under the pointer). The key is the group's kind plus its
  sorted document ids (`exact:1,2`, `metadata:5,6`), stored rather than a
  per-document flag, so a mark means "these exact documents, judged
  together": if another document joins the group (or one leaves), the key
  changes and the group comes back unmarked, a new candidate. A stale key
  left behind that way is a harmless unused row. The table is created by
  `SCHEMA`'s `CREATE TABLE IF NOT EXISTS`, which runs on every library
  open, so existing libraries need no migration entry. **Each group is
  `display:block`** even though it also carries `.fs-list-item` (a
  horizontal flex row) -- without that override every group, and the
  broken-links section, laid its heading and document rows out side by
  side, squeezing titles and overlapping the Re-link buttons (a
  pre-existing bug found while building this). See
  `docs/superpowers/specs/2026-09-24-duplicate-detection-design.md` for
  the full design.
- **The "Find duplicates" modal was renamed to "Library check"
  (`#library-check-btn`, `openLibraryCheckModal()`)** and gained a third,
  persistence-free section: broken file links. `computeBrokenFileLinks(docs)`
  checks every non-deleted document's set `file_path`/`original_file_path`
  via `resolveFileHandle(path, false)`, catching any error (not narrowly
  `NotFoundError`) — unlike the exact-hash duplicate check's `file_hash`,
  this needs no persisted state and no lazy backfill, since an existence
  check never reads a file's bytes; it runs fresh on every modal open. A
  `NULL` path was simply never given one and is never flagged — only a path
  that's actually *set* but fails to resolve counts as broken. Archived and
  needs-review documents are included (same "tells the truth about the
  whole non-deleted library" reasoning duplicate detection's own checks
  already use); only `deleted` documents are excluded.
  **Only the button/modal-open-function/three directly-associated i18n keys
  were renamed** (`toolbarFindDuplicates`→`toolbarLibraryCheck`,
  `duplicatesModalTitle`→`libraryCheckModalTitle`,
  `duplicatesNoneFound`→`libraryCheckNoneFound`, now covering all three
  sections' combined empty state) — the internal DOM ids/classes/i18n keys
  specific to the duplicate-checking sections (`#duplicates-list`,
  `#duplicates-progress`, `.duplicate-group`, `duplicatesBackfillProgress`,
  `duplicatesExactMatchLabel`, `duplicatesMetadataMatchLabel`, and the
  `findDuplicatesBackfillRunning` variable/its own debug hook) are
  deliberately unchanged, since they still describe exactly what they did
  before.
  **Each broken document renders its own row** (`.broken-link-row`, reusing
  `.duplicate-row`'s own click-to-detail-panel wiring for free — its
  `.broken-link-indicators` span stops click propagation, the same
  `onclick="event.stopPropagation()"` pattern the Reminders modal's own
  `.reminder-snooze` wrapper already uses, so clicking "Re-link…" doesn't
  also open the detail panel), showing independent "File"/"Original"
  indicators only for whichever path(s) actually failed to resolve.
  **Re-linking** (`triggerRelink()`/`performRelink()`) opens a plain,
  dynamically-created `<input type="file" accept="application/pdf,image/*">`
  per click — the same accept restriction the capture form's own
  `#file-input` uses, but a fresh element each time rather than a shared
  static one, since each click needs to carry which document and which path
  field it's repairing. The picked file's bytes are written directly into
  the document's **exact existing stored path** via
  `resolveFileHandle(path, true)` (creating whatever directories/file are
  missing) — no database path or row changes at all, since the path itself
  was already correct; only the missing file at it is restored. **Hash
  correctness**: if the just-repaired path is the one `file_hash` was
  derived from — `original_file_path` when the document has one, otherwise
  `file_path`, the same fallback rule `backfillFileHash()` already uses —
  the hash is recomputed via the existing `computeFileHash()` helper and
  persisted (`UPDATE documents SET file_hash = ? WHERE id = ?`); re-linking
  the *other* path leaves `file_hash` untouched, since it was never derived
  from that path. A successful re-link removes just that one indicator from
  the DOM in place (or the whole row, if it was the document's only broken
  one) — no full re-scan of the other two sections, since nothing about
  duplicate grouping changed. A failed write (permission revoked mid-session,
  disk full) is caught and shown as an inline `.relink-error` next to the
  still-present Re-link button, clearing any earlier error on retry, so
  nothing silently looks fixed when it isn't. **Cancelling the picker
  doesn't fire `change`** in most browsers, so the dynamically-created input
  used to be orphaned in the DOM on every cancelled attempt (caught in this
  feature's own final review) — `triggerRelink()` now removes it on the
  `cancel` event current Chromium fires for a dismissed picker, and also
  sweeps up any leftover `input.relink-file-input` at the start of each new
  attempt for browsers that fire neither event (only one native picker can
  be open at a time, so nothing live is ever swept). Headless Chromium
  auto-dismisses an unanswered picker the same way, firing `cancel` — which
  is why `tests/test_broken_links.py` answers every real re-link through
  Playwright's `expect_file_chooser()` rather than `set_input_files()` on
  the input directly (the input is already gone by the time the latter
  would run). **Known, accepted limitation**: a document that was never
  hashed (one predating duplicate detection) and whose hash-deriving path is
  broken can never be backfilled, so it stays in the lazy backfill's
  "unhashed" set and re-triggers that pass (briefly disabling the modal's
  close control) on every Library check open until it's re-linked — cheap,
  since the pass skips a missing file immediately, but worth knowing if the
  progress spinner ever seems to appear on every open.
- **Orphaned tags/people cleanup** (`computeOrphanedTags()`, `computeOrphanedPeople()`,
  `deleteOrphanedTags()`, `deleteOrphanedPeople()`) adds two more sections to the
  "Library check" modal: any `tags`/`people` row not referenced by any non-deleted
  document. Detection is entirely in-memory — every document already carries
  `d.tags` and `d.personFieldValues` (the latter covering *every* person-type
  field, not just the built-in People field, since `personNameToId` is one
  global name registry shared across all of them) — so no new database query,
  no persisted state, and no backfill are needed; both run fresh on every
  modal open, the same reasoning `computeBrokenFileLinks()` already uses.
  **A document sitting in the Waste bin doesn't count as "using" its
  tags/people** — a tag/person referenced only by a deleted document is
  flagged as orphaned — with one accepted, documented consequence: if such a
  tag/person is deleted while orphaned and the document is later restored, it
  comes back silently missing that tag/person, since its join row
  (`document_tags`/`document_field_people`) was cascade-deleted along with
  the tag/person row itself (see below) — no dangling reference is left
  behind. (The design spec described the join row as surviving as harmless
  dead weight; the shipped code deletes it instead, which is strictly
  cleaner and has the same user-visible result.) **Deleting
  a name also scrubs it out of `allDocs`'s own in-memory copies**
  (`d.tags`/`d.people`/every array inside `d.personFieldValues`, across
  *every* document including ones in the Waste bin) — necessary because this
  app never reloads `allDocs` from disk mid-session (every mutation path
  updates the in-memory document objects in place and persists, the same
  update-in-memory → persist → `render()` pattern the Archiving note above
  describes for `toggleArchived()`), so without this scrub a Waste-bin document's
  own in-memory arrays would go stale after the cascade `DELETE` and show the
  just-deleted name again if viewed or restored before the next reload, even
  though the database itself no longer has any row backing it.
  **Orphaned rows deliberately don't reuse `.duplicate-row`** — unlike every
  other row in this modal, an orphaned tag/person doesn't represent a
  document, so there's nothing to click through to a detail panel for; they
  get their own non-clickable `.orphaned-row` markup instead, just a name and
  a Delete button. **Deletion cascades into the relevant join table** —
  `DELETE FROM document_tags WHERE tag_id = ?` / `DELETE FROM
  document_field_people WHERE person_id = ?` — before removing the row
  itself, and refreshes every autocomplete datalist via the existing
  `populateDatalists()` so a deleted name stops being suggested immediately.
  **This is the first destructive action this maintenance-feature family has
  added** (duplicate detection and broken-file-links never destroy data), and
  correspondingly the first `confirm()` dialog anywhere in this app's own UI —
  both the per-row Delete and the per-section "Delete all orphaned" bulk
  action require one. The bulk action follows this app's existing
  bulk-action convention exactly: one shared `confirm()` for the whole
  section (not one per row), every `DELETE` queued first, and exactly one
  `persistDb()` at the end — `deleteOrphanedTags(names)`/
  `deleteOrphanedPeople(names)` take an array specifically so a single-row
  delete and a many-row bulk delete are the same function call with a
  1-element array, not two separate code paths.
- **Unused custom fields** (`computeUnusedFields()`, `deleteFields()`,
  `smartCollectionsFilteringOn()`, the "Unused fields" section of the
  Library check modal, `#unused-fields-section`) are the one way to delete
  a custom field in this app. **"Unused" means no non-deleted document has
  a value** (`customFields[name] !== undefined`, or a non-empty
  `personFieldValues[name]`) -- deliberately regardless of per-type setup:
  a field that's set up for some type but never filled in is still listed,
  with a "Set up for: <types>" note so a deliberately prepared field is
  recognizable, and a field whose only values sit on Waste-bin documents
  is listed with its own note (the same "a Waste-bin document doesn't count
  as using it" rule the orphaned tags/people cleanup above uses).
  `NON_RENAMEABLE_FIELD_NAMES` (People/Amount/Currency/Payment method/
  Reminder) are never listed: the migrations recreate them on every
  library open, so deleting one would be pointless. **`deleteFields(ids)`
  removes everything that refers to the field**: `document_field_values`,
  `document_field_people`, `reminder_snoozes` (by `field_id`),
  `document_type_fields`, `field_descriptions` (by name), the `fields`
  row, their in-memory mirrors, every document's `customFields`/
  `personFieldValues` entry, and the field's own entry in any Smart
  Collection's saved `dynamic` criteria -- left in place, a filter on a
  field that no longer exists would silently match nothing (or
  everything, for a "— Not set —" filter). The `confirm()` names the
  affected Smart Collections so that side effect isn't a surprise. A sort
  on the deleted field's column resets to the default (`import_date`,
  descending) and is persisted; stale `field-<id>` entries in
  `visible_columns` are harmless, since `loadColumnSettings()` already
  drops unknown ids. Single and bulk delete are the same call with a 1-
  or many-element id array, one `persistDb()` at the end, mirroring
  `deleteOrphanedTags()`.
- **Grid view** (`viewMode`, `loadViewMode()`/`saveViewMode()`/
  `applyViewMode()`, `renderGrid()`, `loadTileThumb()`,
  `runPreviewJob()`) is a per-library choice (`view_mode` setting,
  `'list'` | `'grid'`) between the table and preview tiles. **Grid is the
  default** for a library that never chose (only a saved `'list'` gives
  List). Because nearly every test drives the table, the test stub's
  `FakeDatabase` adds `view_mode = 'list'` to any library without one,
  unless a test sets `window.__STUB_KEEP_DEFAULT_VIEW` (as
  `test_grid_view.py` does to check the real default). The
  grid (`#doc-grid`) is a second rendering of the same filtered, sorted
  list inside `.table-wrap`, toggled by a `view-grid` class on
  `#main-layout` that hides `#doc-table`, so `.table-wrap`'s height
  calibration is untouched. Since the table's select-all checkbox lives in
  that hidden header, the grid starts with its own
  (`#grid-select-all-checkbox`, a full-width `.grid-select-all` row), and
  `render()` wires and syncs both. **Tiles share every row handler**: `render()`
  wires click/dblclick/contextmenu over `docItems` (rows plus tiles,
  highlighted together by `highlightDoc()`), tiles carry the same
  `.row-select-checkbox` (bulk selection), and `tableRows()` returns tiles
  in grid mode, so J/K/D/Enter keep working. **The switch lives on the
  count line** (`.count-row` = `#count-line` + `#view-controls`), not the
  toolbar, to stay clear of the toolbar-wrap calibration -- and
  `.view-controls` is pinned to the count line's own 13px height, its 16px
  buttons overflowing slightly, because the first version made the row
  3px taller and `test_footer_pin.py`/`test_collections.py` caught the
  table sliding behind the footer. `#count-line` itself still holds only
  the "Showing N of M" text (several tests read it). The tile size
  (`grid_tile_size`, 140-360px, a `--tile-w` CSS variable) has a slider
  shown only in grid mode. **Previews load lazily** (an
  `IntersectionObserver` on `.table-wrap`, 400px margin) and are cached as
  object URLs per path (`thumbUrlCache`, cleared on library switch and by
  `writeThumbnail()` for the path it rewrites), so a 1,300-document grid
  doesn't read every thumbnail from iCloud at once. Nothing is generated
  automatically, in line with the "no automatic bulk preview generation"
  note under Document previews: **"Create missing previews (N)"** appears
  when listed documents lack one and makes them on click, one at a time,
  saving every 25 and stoppable by clicking again. `THUMB_MAX_DIM` went
  from 320 to 640 so large tiles stay sharp, and **previews are JPEG now**
  (`canvasToThumbBytes()`, quality 0.82, drawn onto white since JPEG has
  no transparency; `writeThumbnail()` writes `thumbnails/<id>.jpg`): a
  640px PNG of a scanned page ran to several hundred KB. **"Recreate older
  previews (N)"** (`runPreviewJob(docs, 'upgrade')`, the same runner as
  'missing') covers previews this app didn't make at full size --
  Mariner's, and its own earlier 320px PNGs -- tracked by a new
  `documents.thumbnail_hd` column (`SCHEMA_MIGRATIONS`), set by
  `writeThumbnail()` (and by the capture/Inbox INSERTs, whose rows don't
  exist yet when the preview is written). For each one it reads the
  existing preview's size first (`createImageBitmap`, `THUMB_SHARP_MIN` =
  480px longest side): a large enough one is only marked, without opening
  the document -- which on iCloud Drive would mean downloading it -- and a
  small or unreadable one is recreated from the document's file. The new
  preview replaces the old path only once written; an unreadable document
  keeps its old preview and stays counted for the next run. The old
  preview file is left on disk (Storage stats lists it as untracked);
  **Library check's "Unused preview files"** (`computeUnusedPreviewFiles()`,
  `deleteUnusedPreviewFiles()`, `renderUnusedPreviewsSection()`) removes
  them: every file under `thumbnails/`, subfolders included, that no
  document's `thumbnail_path` names -- a Waste-bin document still counts as
  using its preview -- listed as a count and total size, deleted after a
  `confirm()`. Walked fresh on every check like the broken-links section;
  `.DS_Store`/`._*` are ignored. Only files under `thumbnails/` are ever
  considered, never documents. The
  status line reports "Previews recreated: N. Already sharp: M.", or that
  it was stopped. `SHOW_DOCUMENT_PREVIEW` (the panel's own preview slot)
  is unchanged.
- **Line-item splits** (`document_splits (document_id, position, category,
  amount, note)`, `d.splits`, `wireSplitsEditor()`, `readSplits()`,
  `allCategoryNames()`): Mariner's split receipts, in both the capture
  and the Edit form (`splitsFieldHtml(p)`/`wireSplitsEditor(p, d)` with the
  `f`/`e` prefix; `d` is null in capture). Lines need a category and an amount
  (`,` or `.` decimals, stored as 2-decimal text); blank lines are
  skipped; `readSplits()` refuses lines that add up to more than the
  Amount (read from the form's own Amount input, so a just-typed Amount
  counts), and `saveNewDocument()`/`saveEditedDocument()` check that before
  writing anything -- in capture before the id is reserved or any file is
  copied, so a refused split leaves nothing behind.
  The rest of the Amount stays with the document's own category -- it is
  never stored as a line. Saving replaces the document's lines
  (delete-then-insert). **Where lines count**: `computeReportGroups()`
  with the `category` breakdown puts each line under its category and the
  rest under the document's (a document counted once per row it touches;
  `grandTotal` unchanged); other breakdowns ignore splits. The toolbar
  Category filter (`matchesCriteria()`) matches a document's category or
  any line's; a Smart Collection `category` rule tests each of them -- a
  positive operator needs any to match, `is_not`/`not_contains` all
  (`empty`/`not_empty` look at the document's own category only). Category
  option lists (filter, datalist, Rename or merge values counts) include
  line categories via `allCategoryNames()`/`valuesForKind()`, and
  `renameValue('category', …)` renames them in `document_splits` too. The
  detail panel shows a "Split" line and `buildSidecarText()` a `Splits:`
  line (`writeSidecarForDoc()` passes `d.splits`). The table is created by
  `SCHEMA`'s `CREATE TABLE IF NOT EXISTS` on every open, so no migration
  entry; copying a library's setup doesn't copy it (it's document data).
- **Calendar view** (`viewMode === 'calendar'`, `renderCalendar()`,
  `calendarMonth`, `calendarWeekStart()`, `shiftMonth()`, `#doc-calendar`)
  is the third value of the same `view_mode` setting and switch: a third
  rendering of the filtered, sorted list inside `.table-wrap` (hidden
  table, `view-calendar` class), so its height calibration is untouched.
  Documents go on their own `date` (first 10 characters, so a stored time
  doesn't matter), never `import_date`; undated ones are listed under the
  month. The grid starts on the locale's first weekday
  (`Intl.Locale#getWeekInfo()`, falling back to Sunday for English and
  Monday otherwise) and leaves days outside the month empty. Each document
  is a `.cal-chip` with a `data-id`, added to `render()`'s `docItems` so it
  gets the same click/dblclick/contextmenu/drag handlers as rows and
  tiles, and `tableRows()` returns the chips so J/K/D work; there's no
  checkbox, so bulk selection stays a List/Grid thing. `calendarMonth`
  ('YYYY-MM') is session state, reset by `resetAll()`, starting at the
  newest dated document listed or else this month; the head shows the
  month's document count. A day with many documents scrolls inside its
  cell (`max-height`).
- **Page tools** (`openPageToolsModal()`, `openCombineModal()`,
  `buildPdfFromPages()`, `replaceActiveFile()`, `refreshAfterPdfChange()`,
  `createSplitDocument()`) are built on **pdf-lib** (`ensurePdfLib()`,
  1.17.1 from cdnjs, MIT), the one dependency added for them -- it copies
  pages between PDFs as they are, text layers included, so nothing is
  re-rendered or re-compressed. `ensurePdfLib()` skips loading when
  `window.PDFLib` already exists, which is how the test stub's fake takes
  over. **"Edit pages…"** is a panel-only action for a non-deleted document
  whose active file is a PDF (`canEditPages()`): a grid of page thumbnails
  (pdf.js) where each page can be rotated, moved, removed (dimmed, and
  restorable until Save) and split after (✂ between cards); "+ Add pages
  from file…" appends a PDF's pages or an image as a page (an A4-wide page
  with the image's proportions). Save is disabled until something changed.
  **The original always survives** (`replaceActiveFile()`, the same two
  rules "Make searchable" uses): with a separate original on disk the active
  copy is overwritten in place; without one the current file becomes
  `original_file_path` and the result goes next to it as `<stem>_edited.pdf`
  (`_combined.pdf` for Combine). `file_hash` stays valid either way, since
  it's derived from the original. Each part after the first becomes a new
  document (`createSplitDocument()`, `source = 'split'`, title "<title>
  (2)" etc.) with the source's category, subcategory, type, date, notes,
  tags, custom fields, people, review flag and manual collections, its own
  hash, and no separate original (the source's original already holds
  those pages). After every write, `refreshAfterPdfChange()` regenerates
  the preview, re-records the text layer (`recordPdfTextLayer()`, so a part
  of a digital PDF gets its own OCR text) and rewrites the sidecar -- all
  best-effort. Existing OCR text on the edited document is kept even if
  pages were removed (it may be hand-corrected). **Combine…**
  (`canCombine()`: non-deleted PDF/JPEG/PNG, 2+ selected) joins the
  selected documents' pages in an order the dialog lets you change; the
  document whose details you keep gets the combined file and the joined OCR
  text, and the others go to the Waste bin with their files untouched, so
  restoring them undoes it by hand. Both dialogs block
  Escape/backdrop/close while writing (`pageToolsRunning`). **The bulk-action
  bar gained a "More ▾" menu** (`#bulk-more-btn`/`#bulk-more-menu`, reusing
  the Add-to-collection menu's CSS) holding Make searchable, Combine… and
  Export…, each keeping its id and listener: adding Combine as one more bar
  button made the button labels wrap to two lines at 1440px in tabs layout,
  growing the bar and pushing `.table-wrap` 16px behind the footer
  (`test_collections.py` Scenario 30 caught it). Occasional bulk actions go
  in that menu, the same rule as the toolbar's Tools menu. Items are shown
  or hidden by `renderBulkActionBar()` as before; the whole menu is hidden in
  the Waste bin.
- **Smart Collection rules and editor** (`matchesRules()`, `matchesRule()`,
  `criteriaToRules()`, `smartRuleFields()`, `openSmartCollectionEditor()`,
  Tools → Manage collections → "+ New smart collection" / "Edit rules…").
  Smart Collection criteria now come in two shapes. The original toolbar
  snapshot (`currentFilters()`'s shape) is still evaluated exactly as
  before, so existing collections behave the same until someone saves them
  from the editor. The rule shape is `{match: 'all'|'any', rules: [{field,
  op, value, value2}]}`; `matchesCriteria()` hands anything with a `rules`
  array to `matchesRules()`. The editor and "Save as Smart Collection"
  both store rules (the latter converting the toolbar via
  `criteriaToRules()`, which also turns an old snapshot into rules when it
  is opened in the editor). **A custom field is referenced by id**
  (`field:<id>`), so renaming a field needs no criteria update; built-ins
  are `any` (the same search text as the toolbar box), `title`,
  `category`, `subcategory`, `document_type`, `tags`, `date`,
  `import_date`, `notes`, `ocr_text` and `status`. Operators depend on the
  field's kind (`SMART_OPS_BY_KIND`): text compares case-insensitively and
  trimmed; tags and person fields use includes/excludes; numbers use
  inclusive gte/lte/between (matching the old Amount range); dates add
  relative operators (`last_days`, `this_month`, `last_month`,
  `this_year`, `last_year`), evaluated against `todayIsoDate()` on every
  render. Mariner's built-in RECENT and TYPES collections are not
  pre-created; the relative date and type rules let a person build them.
  Like the snapshot shape, collection views include archived and
  needs-review documents. `renameValue()` updates rule values (compared
  case-insensitively), and `deleteFields()` drops rules on the deleted
  field (`smartCollectionsFilteringOn()` checks both shapes, resolving ids
  through `fieldDefs` because `fieldNameToId` is already cleared by then).
  The editor's live count covers non-deleted documents; saving is refused
  without a name or with a rule missing its value.
  **The iPhone app (`dossiary-ios`, a sibling repo) ports this rule logic
  to Swift.** `tests/export_smart_rule_cases.py` (not part of the suite)
  writes the cases it checks against -- criteria in both formats and the ids
  this JavaScript matches -- into that repo's test fixtures. After changing
  `matchesRule()`, `matchesRules()`, `matchesCriteria()` or `smartRuleActual()`,
  run it and tell the iPhone app's tests about the change. The iPhone app also
  reads `library.sqlite` directly (read-only): a schema change should keep
  old columns readable, as `SCHEMA_MIGRATIONS` already does.
- **Rename or merge values** (`openManageValuesModal()`, `valuesForKind()`,
  `renameValue()`, `startValueRename()`, Tools → "✎ Rename or merge
  values…") is Mariner's Tag Editor and editable category/merchant lists:
  pick Categories, Subcategories, Document types, Tags, People, or any
  text custom field, see every value with its document count (Waste-bin
  documents included, so a restored one can't bring an old spelling
  back), and rename one in place (same Enter/blur/Escape convention as the
  field rename). **Renaming onto a value that already exists merges the
  two** after a `confirm()` -- it can't be taken apart again. Tags and
  people merge by moving their join rows (`document_tags`/
  `document_field_people`, read whole-table and filtered in JS per the
  sql.js convention above, skipping links the target already has) and
  deleting the old row; a plain rename updates the row in place, keeping
  its id. What else is keyed by the value moves with it: Smart Collection
  criteria (category, type, person, and dynamic filters on that field or
  on person fields), a renamed type's `document_type_fields` setup (on a
  merge the target's own setup wins) and `default_document_type`, and the
  sidecars of every touched document. A person's name is shared by every
  person-type field, so renaming one renames it everywhere -- the same
  global `personNameToId` registry described in the People note.
- **Back up library** (`openBackupModal()`, `listLibraryFiles()`,
  `backupReminderText()`, Tools → "🗄 Back up library…") copies the whole
  library folder into a new `<library> backup <yyyy-mm-dd hhmm>` folder
  (never reusing an existing one) inside a folder the person picks --
  refused if it's the library or inside it (`isInsideLibrary()`, shared
  with export). `library.sqlite` is written from `db.export()` (the
  in-memory database is always the authoritative copy); every other file
  is copied as is, 4 at a time for iCloud's sake, skipping `.DS_Store`/`._*`.
  Plain copies rather than a zip: no dependency, and a backup is simply
  another library folder -- restoring means opening it. **Each backup also
  gets `dossiary.html` and `How to open.txt` at its top**
  (`ownCopyForBackup()`: the jsDelivr download, else a stored copy of
  exactly this version -- never a `confirm()`; see the Export-as-library
  bundles note), written after the files; a library opened from an earlier
  backup has its own old copies skipped from the listing so the fresh ones
  replace them. Without a copy (offline, nothing stored) the backup still
  completes and the summary says so (`backupNoAppCopy`). Stop removes the
  partial folder (`removeEntry(..., {recursive: true})`) so an incomplete
  copy never looks like a backup; files that can't be read are listed.
  `last_backup_at` and `backup_reminder_days` (default 30, 0 = off) are
  `settings` rows; when a backup is due, `afterDbReady()` appends the
  reminder to the "Opened library" status line (a status builder, so it
  retranslates). **`#status` is now a single line** (`nowrap` + ellipsis,
  full text in its `title`), since that reminder made the line wrap at
  320px and pushed `.table-wrap` 26px behind the footer --
  `test_footer_pin.py` caught it; any long status message had the same
  latent risk.
- **Export selected documents** (`openExportModal()`, `exportFileName()`,
  `uniqueFileNameIn()`, `buildExportCsv()`, `#bulk-export-btn` in the
  bulk-action bar's More menu) copies each selected document's active file into a
  folder picked with `showDirectoryPicker()`, named `<yyyy-mm-dd> <title>`
  (characters not allowed in file names replaced, clashes -- including
  files already in that folder, which are never overwritten -- numbered
  " (2)"), plus an optional `index.csv` of the details: the fixed columns,
  Amount/Currency/Payment method, and every other custom field present in
  the export. The CSV separator follows the UI language (`;` for de/fr/es/hy,
  whose spreadsheets use a decimal comma, `,` otherwise) and starts with a
  BOM so spreadsheets read it as UTF-8. **Read-only for the library**, and
  `isInsideLibrary()` (`isSameEntry()` / `resolve()`) refuses the library
  folder or anything in it, so an export can't turn into untracked files
  under `files/`. A document whose file can't be read is listed, not fatal.
  Emailing (Mariner's other export) isn't possible from a browser: a
  `mailto:` link can't carry attachments. **Details in exported PDFs**
  (`pdfWithDetails()`, `#export-details-toggle`, on by default): each
  exported PDF copy gets Title (`displayName()`), Subject (category,
  subcategory, type) and Keywords (tags, written as one comma-separated
  string because pdf-lib joins a list with spaces) via pdf-lib, loaded with
  `updateMetadata: false` so the scanner's own Creator/Producer and dates
  survive and pages are copied as they are. Deliberately the copies only:
  rewriting library files on every edit would mean a slow write per change
  (iCloud) for something the sidecars already provide, and images can't
  carry it this way. A PDF pdf-lib can't open (encrypted, damaged, library
  unavailable) is copied unchanged and counted (`exportDetailsSkipped`).
  Checked against the real pdf-lib 1.17.1 once (properties read back,
  pages and Creator/Producer kept); the suite uses the stub's fake, whose
  `save()` records the properties as `props`.
  **No pauses while it works:** `pdfWithDetails()` loads with `parseSpeed: PDFLib.ParseSpeeds.Fastest` and saves with
  `objectsPerTick: Infinity`. By default pdf-lib gives control back through a `setTimeout` every few dozen objects, and
  opening a document's file (`openDocumentFile()`) opens a new tab first, which puts this page in the background, where
  Chrome stretches every one of those pauses to a second: a 21-page, 570 KB PDF needed 33 of them, 10 to 30 seconds before
  the tab showed anything (measured 2026-11-06; with the options it needs none and takes about 25 ms). The stub's fake records
  the options it was given (`window.__pdfLibLoadOptions`, `__pdfLibSaveOptions`) and `test_export.py` checks them.
- **Export as library** (`openExportLibraryModal()`, `buildExportLibraryDb()`,
  `#bulk-export-library-btn` in the bulk More menu; spec
  `docs/superpowers/specs/2026-10-15-export-as-library-design.md`) turns the
  selected documents into a new `<Name>.dossiary` library, copied or moved.
  The new database is built in memory from the open one with **ids kept**, so
  every stored path stays valid: the documents and their tags, people,
  custom values, splits and reminder snoozes; manual collections holding them
  (with only those members); and setup -- 'used' (fields with a value on
  these documents plus `NON_RENAMEABLE_FIELD_NAMES`, their types' field
  setup, descriptions, settings) or 'all' (`copySetupFrom()`, now taking a
  target database and an excluded-settings list). Never copied:
  `EXPORT_SETTINGS_NOT_COPIED` (`last_backup_at`, `scan_bridge_url`,
  `scan_last_settings`), `not_duplicate_groups`, `ocr_jobs`. Order: each
  document's file and original are read before anything is written (a
  document that can't be read is left out and listed, and stays here on
  Move), previews (only the *read* is best-effort) and fresh sidecars (`sidecarTextForDoc()`; a failed preview or sidecar *write* aborts the export, since the destination is broken),
  `library.sqlite` last; Stop, a failure or nothing readable removes the new
  folder; Move then calls `bulkSetDeleted()` on the exported ids (undone in
  memory if that save fails). "Open it" switches via `switchLibraryAsking()`
  (which asks first while a change is held back) + `proceedWithRootDirHandle()`, and the new library is added to Recent
  libraries. `exportLibraryRunning` blocks closing the dialog meanwhile.
  **Bundles** (spec
  `docs/superpowers/specs/2026-10-20-export-bundle-with-dossiary-design.md`):
  "What to create" (`export-library-output`: `library` | `folder` | `zip` |
  `both`) can add Dossiary itself -- `<Bundle>/dossiary.html`,
  `<Bundle>/<Name>.dossiary/`, `<Bundle>/How to open.txt`
  (`bundleReadmeText()`: the UI language, then English) -- as a folder,
  `<Bundle>.zip`, or both. A `file://` page can't read its own file, so
  `getDossiaryHtmlForBundle()` downloads
  `cdn.jsdelivr.net/gh/AarneAarebye/Dossiary@v<APP_VERSION>/dossiary.html`
  (checked for the same `APP_VERSION`, 15 s timeout), else uses a copy
  chosen once ("Choose dossiary.html…"), whose *contents* are kept in
  IndexedDB (`dossiary-bundle-source`/`copies`) -- not a handle, since
  re-reading one needs a permission prompt that would use up the click the
  folder picker needs; that is also why the download happens only after the
  folder is picked. Library only never calls `fetch`. The zip comes from a
  built-in writer (`createZipWriter()`, `crc32()`, `zipLimits`): stored
  entries, UTF-8 names, ZIP64 past 4 GB or 65,535 entries, appended to one
  `createWritable()` stream so nothing large sits in memory. Zip only writes
  the library straight into the zip through the export loop's `sink`; Both
  writes the folder, then zips it (`listFilesUnder()`). Stop or a failure
  aborts and removes the partial zip and the created folder. The test stub's
  writable streams append like the real API (they used to replace).
  The stored copy lives in the shared `file://` IndexedDB origin, like Recent
  libraries (another local page could plant a copy whose version text
  matches); it is only used when the download fails.
- **Import a folder** (`openImportModal()`, `readImportIndex()`,
  `parseCsv()`, `applyImportedDetails()`, Tools → "📂 Import a folder…") is
  Export's counterpart: every file at the top of a folder picked with
  `showDirectoryPicker({mode: 'read'})` (hidden files skipped, subfolders
  not walked) goes through `createReviewDocumentFromFile(file,
  'folder-import', beforeSave)` -- the Inbox/drag-and-drop path, so exact
  duplicates are skipped and counted, and the folder is only ever read.
  `isInsideLibrary()` refuses the library or anything in it. **With an
  `index.csv`** (Export's, in any UI language: the separator is whichever of
  `;`/`,` the header uses more, and headers are matched against every
  language's `STRINGS` value for the column's key, `IMPORT_CSV_COLUMNS`),
  a file named in its File column gets that row's title, date, import date
  (kept, so a round trip keeps its history), category, subcategory, type,
  notes, tags, People, and every other column as a custom field (created as
  a text field if the library lacks it; an existing person-type field takes
  comma-separated names), and is filed with `needs_review = 0`. The
  `beforeSave` hook applies this inside `createReviewDocumentFromFile()`,
  before its sidecar write and its one `persistDb()`. A document type with
  no field setup before the import gets the fields its rows used appended
  (so they aren't orphaned); a type that already had a setup is left alone.
  **Files without a row, or every file when there is no `index.csv`**, are
  added like a dropped file: filename title, flagged for review. An
  `index.csv` without a File column, or unreadable, is reported and the
  files are still added. The summary is "Label: N" lines (added, with
  details, for review, duplicates, failed, index rows without a file).
- **Share** (`openShareModal()`, `shareEmailHref()`, `#bulk-share-btn` in
  the bulk More menu, the panel-only `'share'` action) is the closest a
  browser gets to Mariner's Email: the Web Share API hands `File`s to the
  system share sheet (Mail, Messages, AirDrop, …). Chrome on macOS supports
  it (`navigator.canShare({files})` is true in Chrome 154 here);
  Playwright's bundled Chromium doesn't, which is how the suite exercises
  the fallback. `navigator.share()` needs a fresh click, and reading files
  can outlast that on iCloud, so the dialog reads them first (named by
  `exportFileName()`, numbered on a clash, PDFs passed through
  `pdfWithDetails()`), then shows its own Share button. A dismissed sheet
  (`AbortError`) is silent; any other error is shown. A file that can't be
  read is listed and the rest still shared. Without file sharing (no
  `canShare`, or `canShare` refusing the files) the dialog offers Export and
  "Write an email" -- a `mailto:` with the titles as subject and
  "date title" lines as body (at most 50), since mailto can't attach files.
- **Storage stats** (`computeStorageStats()`, `formatBytes()`,
  `openStorageStatsModal()`) is a brand new, independent toolbar button (now
  an item in the "🛠 Tools" dropdown) and
  modal — deliberately **not** part of the "Library check" family
  (`openLibraryCheckModal()`) the three prior maintenance features share,
  since this is a read-only overview, not a detect-a-problem-and-fix-it
  check. Answers the question CLAUDE.md's own "Preserving an original file
  on ingestion" note raises but never lets anyone actually see: how much
  of the library's real disk usage is the doubled original-preservation
  overhead versus genuinely distinct content.
  **The walk reads real files on disk, never trusts `allDocs`' own tracked
  paths as the source of truth** — `computeStorageStats()` iterates
  `filesDirHandle.entries()` (the same `for await (const [name, handle] of
  dirHandle.entries())` pattern `checkInbox()` already uses), recursing one
  level into each per-document subfolder, and reads every file's real size
  via `getFile().size` (a metadata read — no file content is ever loaded
  into memory). This is deliberate: summing only `allDocs`' own tracked
  `file_path`/`original_file_path` values would silently miss anything on
  disk that no document row points to at all.
  **Every file under `files/` is classified into exactly one of three
  buckets** by comparing its own relative path against every document's
  `file_path`/`original_file_path` — **including documents in the Waste
  bin**, since a soft-deleted document's files are never touched on disk
  (per the Waste bin's own "nothing on disk is ever touched" design) and
  are still real, space-consuming files:
  - **Active** — matches some document's `file_path`.
  - **Original** — matches some document's `original_file_path`.
  - **Untracked** — matches neither. A genuine, useful side effect of
    walking the real folder rather than the database: nothing else in
    this app can currently show a file under `files/` that no document
    points to at all. This feature only makes it visible — there is no
    delete/cleanup action for it, deliberately out of scope. Every
    captured document's sidecar `.txt` (see the "Sidecar `.txt` files"
    note above — `writeSidecarFile()` writes it straight into `files/`,
    alongside the primary file, not into a path any document's
    `file_path`/`original_file_path` ever references) falls into this
    bucket for exactly this reason — it's real, genuine content that just
    isn't classified as active or original, not a bug in the walk.
  `thumbnails/` gets the same two-way active/untracked split (matched
  against `thumbnail_path`); `inbox/` isn't split further at all, since
  every file staged there is equally "not yet added." `library.sqlite`'s
  own size is added into the grand total but doesn't participate in the
  files/thumbnails/inbox breakdown, since it's a different kind of thing
  entirely. A missing `inbox/` or `thumbnails/` folder (a library that's
  never staged an inbox file, or never generated a thumbnail) is treated
  as zero, not an error — the same "a missing folder just means nothing
  to add" reasoning `checkInbox()` already established; a per-file read
  failure mid-walk is skipped rather than aborting the whole computation,
  the same reasoning `backfillFileHash()` already uses. The top-level
  `files/` iteration itself is wrapped too, not just each per-file read —
  an uncaught throw there (e.g. permission revoked mid-session) would
  otherwise reject `openStorageStatsModal()`'s own `await` and leave its
  spinner up forever.
  **The walk runs immediately when the modal opens** — the click on the
  toolbar button is itself the explicit trigger, matching how
  `openLibraryCheckModal()`'s own file-hash backfill already runs on open
  rather than needing a second confirming click inside the modal. Unlike
  that backfill, this computation never writes anything, so there's no
  "disable Escape/close while running" concern — Escape and the close
  button work normally throughout, even mid-walk.
  **`formatBytes()`** generalizes the ad-hoc `(file.size/1024).toFixed(0)`
  KB-only formatting the capture form's own picked-file-size preview
  (`pickedFileSizeKb`) already uses, since a whole-library total can run
  well past what's sensible to show in KB alone — it auto-scales through
  B/KB/MB/GB/TB rather than being fixed to one unit.
  **Each folder's own split renders as indented sub-rows
  (`.storage-stats-subrow`) directly under that folder's row** — Active/
  Originals/Untracked under Documents (`files/`), Untracked under Previews
  (`thumbnails/`) — not as a flat list after every folder, since both
  "Untracked" rows share one label key and would otherwise be
  indistinguishable. `formatBytes()` promotes to the next unit based on the
  value as it will actually be displayed (rounded to one decimal), so a
  value just under a boundary (1048575 bytes) shows "1.0 MB", not
  "1024.0 KB".
  **The "Untracked" row is only rendered when non-zero**, in both `files/`
  and `thumbnails/` independently — omitted entirely otherwise, matching
  this app's existing "omit sections/rows with nothing to show" convention
  (e.g. how the "Library check" modal's own sections each disappear when
  empty). No per-document breakdown, no sorting, no "biggest documents"
  list — deliberately just the aggregate picture, to keep this a simple
  overview rather than growing into a second browsing UI.
