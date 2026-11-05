# Test coverage narrative, part 2 of 4: Detail panel, reminders, bulk edit, duplicate detection and broken links

Split out of `tests/CLAUDE.md`. This part continues mid-sentence from part 1; the whole narrative was one long paragraph in `tests/CLAUDE.md` and is kept word for word.

Index: `tests/CLAUDE.md`.

and comma-aware autocomplete
for multi-valued fields (`test_comma_autocomplete.py` — the native `list=`
attribute genuinely removed once `wireCommaAutocomplete()` wires a field,
for both People and Tags; typing a second name after a comma (e.g.
"Birgit, A") actually suggesting matches for that second segment, not
nothing, reproducing the exact reported bug native `<input list>` has;
clicking a suggestion completing just that segment and appending `", "`
so the next entry can start immediately; a name already used earlier in
the same input correctly excluded from later suggestions; ArrowDown/Enter
keyboard selection; an empty segment showing no dropdown at all; the same
behavior confirmed for Tags; and the whole mechanism working identically
in the edit form, not just capture),
and the persistent detail panel (`test_detail_panel.py` — its last
scenario checks file sizes after the File/Original paths: 2.0 KB and
1.5 MB for known byte counts, 500 B, and "missing" (translated, "fehlt"
in German) for an original whose path is set but whose file was never
written; the rest of the file is run against a
patched copy of the app with `SHOW_DOCUMENT_PREVIEW` forced back to `true`
(the same patched-copy technique described near the end of this file),
specifically so this file's own "every panel action still works" coverage
— including Regenerate preview and the context-menu-never-shows-it
assertion described below — keeps exercising the real, restorable preview
pipeline even though the shipped app hides it by default; the panel now
starting **expanded** by default with no saved setting, an explicit `'0'`
still collapsing it, and its expanded/collapsed state otherwise persisting
across a reopen, mirroring `test_nav.py`'s own `nav_style` persistence
pattern; clicking a row highlighting it and showing its metadata in the panel, and
clicking a different row moving both the highlight and the panel's
content; every action available in the old detail modal still working
from the panel with correct in-place refresh (Archive/Unarchive, Flag for
review/Done, Add to Collection, regenerate preview); a deleted document's
panel dropping to Restore-only with Edit/Archive genuinely absent, not
just disabled; Cancel from an edit reached via the row-level `.row-edit-btn`
shortcut closing the edit form without forcing a collapsed panel open;
saving an edit reached via
the row-level `.row-edit-btn` shortcut — which bypasses the panel/selection
step on the way in — selecting the just-edited document as the panel's new
selection and highlighting its row; the toggle button being absent in
Reports view; the panel force-collapsing below the mobile breakpoint
regardless of the saved preference; and, this same branch's own follow-up
row-interaction behaviors — double-clicking a row opening its document's
file in a new tab (a PDF as an in-memory copy titled with the document's
name, read back from the stub's fake pdf-lib through a wrapped
`URL.createObjectURL`), a single click never opening anything, a document with
no `file_path` being a silent no-op on double-click, and (the propagation-
leak fix caught in this branch's own final review) double-clicking the
row's `.select-col` checkbox also being a silent no-op rather than
toggling the checkbox and opening the file, since that cell's own
`click`-only `event.stopPropagation()` doesn't cover `dblclick` on its
own); and this same file's later right-click-context-menu scenarios,
covering that branch's own follow-up feature — right-click selecting and
highlighting a row and refreshing the panel's content exactly like a plain
click does, verified to work the same whether the panel is currently
expanded or collapsed; the context menu's item set for a normal document
matching the panel's own action set minus "Regenerate preview" (which
never appears in the menu at all, panel-exclusive by design) plus a
"Detail" entry the panel itself has no equivalent of; "Detail" toggling
the panel's expanded/collapsed state on repeated invocations without ever
touching which document is selected, and, symmetrically, selecting a
different row afterward not touching panel visibility either; Archive
from the context menu actually archiving the document end-to-end,
verified against the panel's own button label afterward rather than just
the menu closing; right-clicking `.select-col` opening no menu at all, and
Reports view having no rows to right-click in the first place; "Add to
Collection" from the context menu closing the menu and opening the
collection picker positioned near the actual click point rather than
collapsed to `(0,0)` (which is what a stale, already-detached `e.target`
would produce); and a dedicated large-seed (25-document) scenario
reproducing the exact viewport-overflow bug this branch's final
whole-branch review caught — right-clicking a row near the bottom of a
1280×800 viewport used to push the menu's last item (with "Add to
Collection" in play, six items deep) to a bottom edge of 831px against an
800px-tall viewport; `showRowContextMenu()` now measures the menu's real
rendered height once it's in the DOM and, only when it would overflow,
clamps `top` so the whole menu — every item, not just the visible ones at
the moment of the click — stays on-screen, verified via
`getBoundingClientRect()` on every `.row-context-menu-item`, confirmed
non-vacuous by temporarily reverting the clamp and re-running the same
scenario (it then correctly reports `False`, with the last item's
`bottom` past 800px); and reminder-type custom fields (`test_reminders.py`,
twelve scenarios — creating a `reminder`-type field inline via the same "+
Add a custom field" flow and confirming it behaves identically to `date`
end to end: the type option present in the dropdown, the field rendering
as a native `<input type="date">` immediately after creation, the saved
value round-tripping through `library.sqlite` as a plain ISO date string
under `type: 'reminder'`, and the detail panel displaying it exactly like
any other date — plus Field Settings offering the Column capability
checkbox for it but never Autocomplete, matching `date`/`number`/
`checkbox`'s own treatment; `reminder_lookahead_days` defaulting to 30
with nothing persisted, saving an explicit `14` and reading it back
correctly after a simulated reopen; the `reminder_snoozes` table loading
a seeded row into the in-memory `reminderSnoozes` map via the
`__DEBUG_reminderSnoozes` test-only hook, and a real `INSERT OR REPLACE`
against its compound `(document_id, field_id)` key confirmed to actually
replace rather than duplicate the row — checked two ways, not one,
because the first check alone (reading back `reminderSnoozes['1:1']`
after the replace) is vacuous: `loadReminderSnoozes()`'s for-of loop
overwrites the same map key on every matching row regardless of whether
the underlying table actually deduped, so it reads back the correct
final value even if the stub left two rows sitting side by side; the
real assertion reads the raw table rows back via a second
`__DEBUG_reminderSnoozesRawRows` hook and confirms there's exactly one,
holding the new value — this was the first genuinely compound-key `INSERT
OR REPLACE` dedupe branch `stub_studio2.js` needed, every prior one
(`settings.key`, `field_descriptions.field_name`) having been a single
column; `checkReminders()`'s full "what counts as due" rule exercised
against a 9-document seed (due today, overdue by 5 days, due in 10 days
inside a 14-day lookahead, due in 60 days outside it, due today but
archived, due today but deleted, due today but actively snoozed 5 days
into the future, due today with an already-expired 1-day-past snooze,
and one document carrying two reminder fields where only one is
actually due) — with every date computed relative to the app's own
`todayIsoDate()`/`addDaysToIsoDate()` rather than hardcoded, so the
scenario stays correct regardless of which real day the suite runs on —
confirming exactly the right five documents come back due, the
two-reminder-field document contributes only its one genuinely-due field
rather than both, and results sort by date ascending with the most
overdue entry first; the reminders modal rendering one row per due
reminder with a due/overdue label, all four snooze choices (1 week/1
month/3 months/a custom date, the last revealing its date input only once
chosen) persisting the expected `snoozed_until` and removing their own
row from the modal, the modal auto-closing once every row has been
snoozed away, and clicking a remaining row closing the modal and
selecting/highlighting that document in the table — the same select/
render/closeModal/openDetail sequence `saveEditedDocument()`'s own
success path already uses, just reordered so `closeModal()` runs first;
and both trigger points — a genuinely fresh library open with a due
reminder already in the seed surfacing the modal automatically with no
manual action, the "Check reminders" toolbar button opening the same
modal on demand, and that same button reporting the "No reminders due."
empty-case status message when a freshly-opened library has nothing due
at all); the Dismiss/Delete feature added on top of Snooze — `reminder_snoozes.dismissed`
loading into the `{snoozedUntil, dismissed}` in-memory shape and `checkReminders()`
excluding a dismissed field unconditionally, even one that's overdue with no
`snoozed_until` at all and even one whose row also still carries a stale future
`snoozed_until` (dismissed must win regardless); dismissal scoped to the
`(document_id, field_id)` pair, not the document — a 4-document seed proves both
that editing a dismissed field's value to a brand-new date does NOT un-dismiss it,
and that a document carrying two reminder fields with only one dismissed
contributes only its non-dismissed field to `checkReminders()`'s results;
`dismissReminder()`/`reenableReminder()`/`clearReminderFieldValue()` exercised
directly via their `__DEBUG_` hooks for both persisted and in-memory state —
Dismiss persists `dismissed=1` without touching the field's own stored value,
Re-enable does a full `DELETE FROM reminder_snoozes` rather than a flag flip, and
Delete removes the `document_field_values` row and the in-memory `customFields`
entry alike; the Reminders modal's own Dismiss and Delete buttons end to end —
present on every row alongside Snooze, the Delete button carrying the app's
`.danger` styling, clicking Dismiss removing that row while leaving its stored
value alone, clicking Delete removing its row while clearing its value AND
leaving that same document's *other* reminder field untouched, and the modal
auto-closing once every row is gone through a mix of Dismiss/Delete/Snooze
rather than Snooze alone; and the Edit form's dismissed-field hint and Re-enable
link — a dismissed reminder-type field shows a `.reminder-reenable-btn` hint an
otherwise-identical non-dismissed field doesn't, the capture form never shows it
at all (no document exists yet to be dismissed against), and clicking Re-enable
removes only its own hint element and clears the dismissal
(`checkReminders()` includes the field again) *without* discarding an unsaved
edit already typed into a different dynamic field on the same still-open form —
the specific regression this feature's own review round caught and fixed
(Re-enable used to trigger a full `applyDynamicFieldsForType()` rebuild, which
re-reads the document's originally-persisted values and silently wiped
in-progress edits elsewhere on the form; see `CLAUDE.md`'s own note on this).
Scenario 8's seeded reminder date is computed relative to `todayIsoDate()`
rather than hardcoded, fixing a real flake an earlier hardcoded literal caused:
once real time passed it, it became overdue, which made `checkReminders()`'s own
documented auto-surface-on-open behavior pop the Reminders modal on a later
scenario's reload and block its first click — Scenario 9 now defensively presses
Escape before its own reload for the same reason. `snoozeReminder()`'s own
defensive `dismissed = 0` write — untested until a later final-review pass, since
no earlier scenario snoozed a field that was currently dismissed — is exercised
by seeding a dismissed `reminder_snoozes` row via `__DEBUG_dbRun` (the same
direct-write pattern Scenario 3 already uses for this table) and then calling the
real function through a new `__DEBUG_snoozeReminder` hook rather than duplicating
its own `INSERT OR REPLACE` a second time, so the assertion actually exercises
the app's own code path instead of just re-proving the stub's dedupe behavior;
checked both in the in-memory `reminderSnoozes` map and the raw persisted row
(`dismissed` back to `0`, `snoozed_until` set to the new date, not a stale
leftover `dismissed = 1`). A later final-review fix made `clearReminderFieldValue()`
also delete any lingering `reminder_snoozes` row for the field it clears, and
`clearDefaultReminder()` now delegates to it instead of duplicating its logic
(see `CLAUDE.md`'s own note on this) — Scenario 12 covers this end to end for
**both** call paths: a custom reminder-type field cleared via
`clearReminderFieldValue()` (the Reminders modal's own Delete button) and the
reserved `'Reminder'` field cleared via `clearDefaultReminder()` (the row
context-menu flyout's "Clear reminder"), each seeded with a real stored value
*and* a dismissal on top of it, confirming the `reminder_snoozes` row is gone
entirely (not merely flipped to `dismissed = 0`) via `__DEBUG_reminderSnoozesRawRows()`,
and then — the real end-to-end proof, not just a DB-level check — setting a
brand-new value on the same field afterward and confirming `checkReminders()`
actually includes it again, i.e. the field is NOT silently still excluded as if
still dismissed, which is the exact bug this fix exists to prevent; and the default-reminder context
menu built on top of that feature (`test_default_reminder.py`, ten scenarios — the `'Reminder'`
field auto-created by `migrateDefaultReminderField()` on a fresh library
open, and reopening the same library confirmed not to duplicate it (same
`id` before and after a simulated reload); `'Reminder'` rejected as a name
when creating a custom field inline, matching the existing reserved-name
behavior; `setDefaultReminder()`/`clearDefaultReminder()` exercised
directly via `__DEBUG_setDefaultReminder`/`__DEBUG_clearDefaultReminder`,
checking both in-memory and persisted state and their `checkReminders()`
integration — the in-memory assertions read back through a dedicated
`__DEBUG_getCustomFieldValue` hook added specifically for this, after an
earlier draft of this same scenario dropped them in favor of only
checking `checkReminders()`'s own output and the raw persisted row,
silently losing coverage of the one thing `setDefaultReminder()`/
`clearDefaultReminder()` do that neither of those other two checks can
tell apart from a bug: whether `d.customFields` on the in-memory `allDocs`
object actually got mutated, not just the database; a document with a
default reminder value showing up as an orphaned, editable field in the
Edit form regardless of its type, with the correct value pre-filled; the
context menu's two label states ("Add reminder" when unset, "Reminder:
<date>" once set); the flyout surviving the row context menu's own
`closeMenu()` auto-close — the same separate-floating-element property
Add to Collection's own picker already relies on — and offering
Today/Tomorrow/Next week/Custom date but not Clear reminder until a
reminder actually exists; all four presets plus Clear reminder each
verified end to end (Today setting it immediately and updating the
context-menu label on the next right-click, Clear reverting that label
back to "Add reminder"); the custom-date input starting hidden, becoming
visible only once "Custom date…" is chosen, carrying a `min` of tomorrow,
and reading `color-scheme: dark` via `getComputedStyle()` — matching the
reminders modal's own already-established `.reminder-snooze-custom-date`
pattern; an end-to-end confirmation that a reminder set through the
flyout (not just through the `__DEBUG_` hooks) is picked up by
`checkReminders()` the same way a function-level write already is; and,
as its own dedicated closing scenario, `buildDetailActions()`'s
`'default-reminder'` action confirmed to render as a real, correctly-`id`'d
button in the detail panel too (`#default-reminder-btn`, not
`id="undefined"`) and to update its own label after a preset is chosen
from there — the specific panel-rendering regression this scenario exists
to catch, since `openDetail()`'s `actionIdByKey` map is a separate,
hardcoded lookup the context menu's own generic iteration doesn't depend
on, so a missing entry there fails silently in the panel alone); and
bulk-editing across a multi-document selection (`test_bulk_edit.py`, 23
scenarios across two `main()`/`main2()` runs) — both entry points, the
bulk-action bar's own Edit button (visible with 1+ selected everywhere
except the Waste bin, matching `#bulk-archive-btn`'s own rule, and using
singular vs. plural modal-title wording correctly for exactly 1 selected
document) and the right-click bulk context menu (a single "Edit" item,
shown only when the specifically-right-clicked row is itself checked
*and* 2+ rows are selected, falling back to today's ordinary
single-document menu for an unchecked row even while others are checked
elsewhere); every replace-semantics scalar field (Document Type,
Category, Subcategory, Date, Notes, and every generic custom field)
starting genuinely blank with its own "Apply to all" checkbox unchecked
and its input disabled, Apply-checked-with-a-value writing to every
selected document while leaving unselected ones untouched, Apply-checked-
with-a-blank-value clearing it explicitly, and Apply-left-unchecked never
writing regardless of what's typed into the (force-filled, since
disabled) input; the additive Tags/person-type fields' Add/Replace mode
toggle (Add keeping existing values and adding on top, Replace discarding
them, both against a field — Author — pre-seeded with a real prior value
so discarding is actually provable) plus its own comma-autocomplete
dropdown positioning (`.bulk-autocomplete-wrap`, since `#bulk-tags` has no
`.field-with-clear` wrapper the way `#e-tags`/`#f-tags` do); the generic
custom-field union (`computeBulkFieldUnion()`) rendering a field common to
every selected document's type normally and a field configured for only
*some* of them with `.field-orphaned` styling, still fully writable to
every selected document exactly like editing an orphaned field on one
document already is, and a checkbox-type field's own value control
correctly independent of its Apply checkbox; the mixed-value indicator
(`bulkScalarMixed()`/`bulkSetMixed()`/`refreshBulkMixedHints()`) showing
an overwrite warning only when selected documents' current values
genuinely disagree, staying silent when they already agree, and switching
an additive field's hint wording live between the informational
"added on top" phrasing (Add mode) and the overwrite warning (Replace
mode) the instant the mode toggle changes; sidecar `.txt` sync reflecting
a bulk-set field's new value alongside the document's own unrelated,
unchanged title; the live-reproduced Document-Type-plus-another-field
same-save data-loss bug and its fix — bulk-changing Document Type to a
type that doesn't configure a second, simultaneously-applied field no
longer silently drops that field's own write, proving `saveBulkEdit()`'s
field-union snapshot (taken once, before the scalar-field write block can
mutate any document's in-memory `document_type`) actually holds; the
spec-mandated "blank input on Replace mode is an explicit clear" property
for both a Tags field and a person-type field (Author), each first forced
to a known non-empty value via its own Replace-mode save — since the
suite's own accumulated multi-scenario selection state makes relying on
"whatever's there already" unreliable — then Replace-moded again with a
blank input and confirmed to leave zero rows, not merely unchanged ones;
and the one deliberate deviation from every other bulk action in this
app — `bulkSetArchived()`/`bulkSetDeleted()`/`bulkSetNeedsReview()` all
clear `selectedDocIds` on success, but a bulk-edit save does not, since
changing field values (unlike archiving/deleting/flagging) never removes
a document from the view its selection lives in — confirmed by checking a
row's own checkbox stays checked immediately after a save), duplicate
detection (`test_duplicate_detection.py` -- `computeFileHash()` matching a
hand-computed SHA-256 for known byte content; two documents captured from
byte-identical files sharing the same `file_hash` while a third, genuinely
different document gets a different one; the capture-time warning
appearing immediately (non-blocking -- Save still succeeds) when a picked
file's bytes match an already-saved document, and staying hidden for a
file with no match; an Inbox bulk-add batch where one staged file is an
exact duplicate (skipped, removed from `inbox/`, counted on the status
line) and a second staged file in the same batch is genuinely new (added
normally); the "Library check" modal (originally "Find duplicates")
grouping an exact-hash match and a
Title+Date metadata match into separate, correctly-labeled groups, a
same-title-different-date document correctly excluded from the Title+Date
grouping, clicking a document in a group closing the modal and opening
its detail panel while filtering the table to exactly that group's
documents (clicked row selected, a banner naming the group and its size,
and a "← Back to Library check" link that reopens the modal over the
unfiltered All Documents view), and a second modal open not re-triggering the backfill
progress indicator once every document already has a hash; a deleted
document excluded from groupings (an exact-hash group correctly shrinking
from 3 to 2 members after one is deleted, its title no longer appearing
in the modal; and, against a 60-document library with an artificially
slowed `crypto.subtle.digest()`, the backfill hashing up to 4 files at
once, persisting to `library.sqlite` mid-pass, the Stop button halting
it early with a "Stopped after checking N of 60" note and the close
button re-enabled, and a second Library check resuming with only the
remaining documents; and "Not a duplicate" marks -- a ticked group
staying listed, dimmed, without the modal closing, the mark saved to
`not_duplicate_groups`, the group sorting after the unmarked group of its
kind on reopen and staying ticked after reopening the library, unticking
removing the saved mark, and a document joining a marked title + date
group (via the capture form) making it a new, unmarked group)), the
Library check modal's broken-file-links section
(`test_broken_links.py` -- documents whose `file_path`, `original_file_path`,
