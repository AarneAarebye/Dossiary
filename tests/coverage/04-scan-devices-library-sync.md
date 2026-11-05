# Test coverage narrative, part 4 of 4: Scan dialog, devices, deleting and sharing libraries, leases and page counts

Split out of `tests/CLAUDE.md`. This part continues mid-sentence from part 3; the whole narrative was one long paragraph in `tests/CLAUDE.md` and is kept word for word.

Index: `tests/CLAUDE.md`.

close or cancel; and, in `main_bulk()`, the bulk-action bar's button only
appearing when a selected document is eligible, the dialog counting and
processing only those, a summary naming the one failed document (missing
file), a single eligible selection falling back to the single-document
message, Stop letting the current document finish and saving it while
leaving the next untouched, and no bulk button in the Waste bin; and, in
`main_library_check()`, Library check's two counts (PDFs not checked for
text yet vs. documents needing OCR; deleted and already-built documents
never counted or opened), "Check for text" with Stop mid-run (in-flight
files finish, a "stopped after N of M" note, the modal unclosable while
it runs) and a second run finishing the rest, a digital PDF recorded as
having text, scanned PDFs as checked without, an unreadable PDF left
unchecked to retry, "Show in table" listing exactly the needs-OCR
documents, "Make all searchable" processing only those, and a found text
layer copied into OCR text and the sidecar; and, in `main_errors()`, Library check's needs-OCR count and "Show in table" leaving
out an image and a checked PDF whose OCR text was typed in (Make searchable
still offered for them), a read-only active file (the stub's
`handle.readOnly = true` throws Chrome's `NoModificationAllowedError`)
reported with its library path and "read-only" instead of "OCR failed", a
missing file reported as missing, "no text found" (`window.__STUB_OCR_NO_WORDS`)
shown in the neutral status colour on a single run and, in bulk, counted
and listed apart from failures with the documents still eligible; and, in `main_shared_read()`,
the duplicate backfill hashing every document and text-checking the PDFs
it read from the same bytes (text copied only into empty OCR text, a
document hashed from a separate original left for "Check for text", and
a PDF checked before its text was copied counted as "Text not in search
yet" and fixed by the same Check for text pass, without touching another
PDF's existing OCR text) --
the stub's
pdf.js fake reports real text for a PDF whose bytes contain `%TEXTLAYER`
and has a `__STUB_PDF_SLOW` hook for the Stop test -- the
seed marks the `searchable_pdf_built` backfill done,
since that one-time migration would otherwise flag every seeded captured
document with an original as already built), person-type fields as
columns and filters (`test_person_field_columns.py` -- Author gets a
Column checkbox but no Autocomplete, People gets neither; the column shows
every name as a pill; the filter lists each name once and matches "includes
this name", with "— Not set —" matching no names; a Smart Collection saved
from that filter matches the same documents; sorting by the joined names;
and Reports offering the field as a breakdown), the
the scan dialog (`test_scan_dialog.py` -- a fake `fetch` defined in the
test plays any number of helpers by base URL (`FAKE_HELPERS`, version 1,
version 2, legacy, unreachable, or not a helper), each request logged in
`window.__CALLS`: discovery across both default ports and the manual
address (127.0.0.1 not probed twice, a non-helper `/health` ignored,
invalid scanner entries dropped, a 401 from `/scanners` meaning not
paired, no Authorization header without a token, only loopback addresses
probed -- not one on another machine, https, or a port out of range, but
`http://[::1]`); the dialog's scanner
list with the helper in brackets for a duplicated name, only the settings
each scanner supports (two-sided only for a duplex feeder, known extras
only), remembered settings per library and the fallback for a gone
scanner; "nothing found" with its links and Look again saving a new
address (and refusing one on another machine); version 1 scans (query string, split on blank pages, multi-file,
an already-staged same name kept, partial, hard failure keeping the
dialog open, 404 outdated, 409, unreachable, non-JSON, missing files) and
version 2 scans (the exact JSON body, extras as known booleans, 422/503/500
messages, partial, an unwritable `inbox/` -- the stub's
`dirHandle.readOnly = true` -- keeping the dialog open with the file and
reason and adding nothing, a read-only `library.sqlite` not stopping the
scan or leaving the status on "Scanning…"); the OCR scenarios
(`scenario_ocr_request`: settings, the `ocr`/`ocrLanguages` request fields,
job rows; `scenario_ocr_jobs`: the runner -- 202 then 200 swap-in with the
original kept, resume after reopening, 404/500/unreachable/changed-pages
fallbacks, the setting off, Waste bin deletion, the stale guard, and a scan
renamed by the inbox keeping its job on the right document). The fake
helper answers `/ocr/<job>` from `H.ocrResponses` (default 200 with a
`%TEXTLAYER` PDF, or 202 while `H.ocrHold`); the scenarios hold the timer
with `window.__DEBUG_holdOcrJobs(true)` and drive every pass with
`__DEBUG_runOcrJobPass()`. The stub starts libraries with `scan_auto_ocr`
`'0'` unless `window.__STUB_KEEP_SCAN_AUTO_OCR` is set, like the
`view_mode` note above. Final-review additions: `scenario_ocr_jobs` checks that `queueScanOcr()` with a stale root (`__DEBUG_queueScanOcr`) adds nothing, that a pending document's panel offers no "Edit pages…"/"Make searchable" and the bulk Combine/Make searchable buttons stay hidden (and "Edit pages…" is back once the swap-in finished); `test_edit_ocr.py` has a document whose job finishes while Save awaits its write (the stub's `window.__STUB_ON_DB_WRITE` hook runs `__DEBUG_setDocOcrText`) and checks memory and database keep the recognized text. `test_edit_ocr.py` marks its first three documents `has_text_layer` (via `__DEBUG_dbRun` + `__DEBUG_loadDocumentsFromDb`) so the Edit form's "Make searchable" still reads their text instantly, and adds a scanned PDF for the new behaviour: the button queues an `'edit'` `ocr_jobs` row (with the setting off), locks the text box, a save keeps `ocr_text`, a pass makes it searchable; the running state (button text, the elapsed-time counter in the dialog
and on the status line, stopped and replaced by the result, toolbar disabled,
Escape/close/backdrop blocked); inline pairing for both versions (local
code check, wrong code, `{code, client}` JSON, token per helper, a 401
dropping it, two helpers paired at once with the first `/pair` answer held
back (`pairDelayMs`) still storing both tokens, a legacy bridge scanning
without a header); and `scenario_split` for the one Scan button: no Scan
Multi button and no helper contacted on library open, ticking split
ticking skip (untickable again), the option's label and its always-visible hint starting with "Scan
Multi:", skip blank pages' own hint, the folded options table (only with both options; four rows; folds
again), the "Scan and split" button text following the checkbox, the request's extras, split
remembered on reopening, Toolbar buttons… without Scan Multi, an old
hidden `scan-multi` setting harmless, the German button text. The shared
stub fails every request to another localhost origin unless
`window.__ALLOW_REAL_HELPERS` is set, which only
`manual_scan_reference_helper.py` (a manual check against the real
reference helper, not part of the suite) does).
The devices dialog (`test_devices_dialog.py` -- a fake `fetch` playing
Dossiary Sync's admin API on `127.0.0.1:8769` per scenario (`FAKE_SYNC`,
answering 415 to a POST without JSON like the real one): the start screen's
button opening it with no library open; not running with
the install link and Look again; Connect asking for a code as JSON, a wrong
code, the right one normalised and its token stored; a 429 naming the wait;
a stored valid token going straight to the devices with role labels and
relative last-seen times; per-library checkboxes for phones only, allow and
deny requests with the status line, a refused change undone; Remove behind
`confirm()`; the ✎ rename (input with the current name, Enter/blur posts the
trimmed name as JSON, Escape/unchanged/empty send nothing and keep the dialog,
400/503 shown under the input, hostile name as text, 401 back to Connect);
the language switch blocked while open; Disconnect; a revoked
token dropped on open and on a 401; a blocked `localStorage`, and one that
reads but won't store (the token stays in memory); German labels and
relative times; "Add iPhone or iPad…" with a fake `window.qrcode` (the
cdnjs request is aborted): no library ticked keeps "Show QR code" disabled
and sends nothing, a refused pair-code shows the reason, the QR SVG of the
`link`, the grouped code and fingerprint as text, the countdown, expiry
clearing the QR and offering New code, the QR surviving a Remove, Done
reloading the devices, a 401 on pair-code, the library failing to load,
no shared libraries; hostile `<img onerror>` device/library/code/
fingerprint names shown as text; the service going down after connecting
(toggle, Remove and Show QR code each end in a clear error, nothing stuck
disabled); an answer in the wrong shape and the failing one of the two
list requests reported; every call carrying a timeout signal).
Delete library (`test_delete_library.py` -- a fake `fetch` playing the
admin API's state and delete routes: a synced delete from Tools (the typed
name enabling the button, one JSON POST with `takeOver: false`, the library
closed, the Recent entry gone, the success text in the dialog and on the
status line, no lease call and no admin call afterwards); another device
holding the lease (the state's `lease.holder: 'other'`) → "Take over and delete" posting `takeOver: true` and the
`trashed: false` text; a 501
saying the library was closed but not deleted (Recent entry kept), a 409
offering take over, 503/502/an old service's 404 each keeping the dialog
open with its reason, then 404 `unknown-library` counted as gone; a
`.kept-aside` write failing (the root's `getDirectoryHandle` patched)
leaving the library open, sending nothing, the change still saved later;
Escape blocked while the request runs; no token → the connect hint and the
devices button; unsynced → Close and forget, no admin call at all, the
folder named and left on disk; the Recent row's 🗑 asking for read
permission first and deleting a library that isn't open, and a denied
permission noted on the row; deleted on another Mac via the state poll,
with nothing unsaved (no `.kept-aside`) and with an unwritten change (a
`.kept-aside` copy holding it, named in the notice) and with a change
only in memory when the poll answers (kept aside, then closed); ordinary, `deleted:
null` and 404 state answers never closing it; a late tab: a `{deleted,
trashed: true}` answer closing a clean tab, and with an unwritten change
making no kept-aside attempt, staying open read-only (saves and editing
refused, nothing written, no admin calls), Escape not dismissing the
offer, "Download unsaved changes" producing exactly `db.export()` (via
`expect_download()` and `__DEBUG_dbExportText()`) named `<name> unsaved
<date time>.sqlite`, Close library closing without a release; a failed
kept-aside copy (not trashed) giving the same offer; a `deleted` answer naming
no device closing a clean tab ("another Mac") and a save made before the poll
knows being written with no admin call, the poll then closing the clean tab; a tab opened after the deletion (no live answer
first, `open_app(live=False)`) staying open as a local library -- no notice,
Recent kept, no base marker for a local library, editing and a save writing to disk, no admin calls
after the first answer, the sync file left, Delete taking the unsynced
path, a reopen this session still local -- also when its first answer is the
trashed state with a change made before it, while a first answer in the grace period (deleted, not
trashed) closes with the notice, keeping an unwritten change aside first
(every other scenario first gets one ordinary answer); German labels; a hostile
folder name, busy device and `deletedBy` shown as text).
Share this library and Get it (`test_share_library.py` -- a fake `fetch`
playing the Mac's check, share, state, available and get routes, and a fake
libraries folder `window.__LIB_ROOT`: the Tools item only for an unsynced
library; phones only, none ticked; no stored folder → the chooser naming the
root from a check with a probe that doesn't exist; a wrong folder refused
(probe written there, then removed, nothing stored); the right one stored
with its path; in place: one JSON share `{folder, phones: []}` after
`library.sqlite` was saved, no copy, reopened synced, the status line, the
status line "Shared … uploading to the Pi.", the shared library polled like any
synced one, the header height unchanged, no Share item afterwards; from elsewhere with the stored folder
(no picker): the numbered " 2" copy with the ticked phone, every file but
the sync bookkeeping and clutter, `library.sqlite` from memory, the original
unchanged, Recent replaced, the hub's name and the note; Stop (Escape
blocked meanwhile) and an unreadable file removing the copy; a 503 after the
copy keeping it and Try again posting the same copy; not connected → Connect
opening the devices dialog; in place known up front (read-only name); 409
already-shared and an unknown code with its status; Get it: the list, the
uploading one disabled, the chooser under the row, Downloading…, `{}` as
JSON, Open opening the folder and Recent recording it, errors under the row,
the section hidden for an empty list and a 404; German labels; an
IndexedDB spy (`IDB_SPY`) confirming the folder lives in its own
`dossiary-libraries-root` database at version 1 while `dossiary-app-db` stays
at version 1 with only `recentLibraries`, and `window.__IDB_FAIL = 'blocked' |
'error'` showing the chooser instead of a hang, the share going ahead).
Saving in a synced library (`test_no_lease.py`, 37 scenarios -- replaced
`test_sync_lease.py`, removed with the editing lease; a fake folder
(`__LIB_ROOT`-style stub with `.dossiary-sync.json` and `.dossiary-base.json`
files), a fake `fetch` playing the state route, a stored admin token or none).
Checks that no lease call is ever made (only `GET …/state`, and
`POST …/delete` from the Delete dialog); `synced_save` (a save writes
`library.sqlite` at once plus a base marker naming the loaded version);
`base_follows_loaded_version`, `newer_reloads` and `guard` (a newer version in
the sync file reloads quietly when nothing is in the way; a save with memory
behind a newer, foreign disk keeps it aside in `.kept-aside/this Mac-<time>` with
the notice, a job's save quietly); `poll_reads_state` (the reduced poll: `deleted`,
`keptAside` once per entry through `KEPT_ASIDE_SEEN_KEY`, `version`),
`poll_deleted`, `no_sync_file` / `no_token` / `service_down` (nothing breaks, no
admin call without a token or a sync file), `backup`, `reload_keeps_view` and
`reload_waits_for_dialog`, `edit_on_newer_version`, `guard_more`,
`form_open_newer_arrives`, `library_check_stale`, `reload_refused`,
`person_change_not_dropped`, `drops_meet_newer`, `quiet_copy_reused`,
`reload_race`, `doc_ids` (reserved ids), `open_race`, `no_reload_while_opening`,
`sync_read_before_writes`, `view_prefs` (a view preference alone stays in memory
and goes out with the next real save), `kept_aside`, `export_leaves_sync_files`,
`tokenless_write_pulled_over` (no token: a write a pull raced with is kept aside
with the notice) against `token_write_then_foreign_reloads_quietly` (with a token
it is an ordinary reload), `token_rejected`, `ocr_job_runs` (jobs write in a
synced library without a token); the base rule: `base_follows_own_push` (own
push via the poll and via the sync file alone; a write the sync file changed
under, and a foreign base marker, leave base at 3), `many_own_pushes` (25 pushes,
each marker names the version before it, nothing kept aside),
`base_pull_between_write_and_marker` (a pull's marker written between the tab's
write and its marker leaves the write unproven); `switch_asks_when_unsaved` (the
keep-aside copy fails: Switch library and Export's "Open it" ask, Cancel keeps
the change, "Switch anyway" switches). Ticks use `__DEBUG_syncNow()` (no
argument). `test_devices_dialog.py`, `test_delete_library.py` and
`test_share_library.py` carry the admin dialogs.
`export_smart_rule_cases.py` is likewise not a test: it writes the Smart Collection cases the iPhone app (`dossiary-ios`) checks its Swift port against.
This
list itself can go stale — if you add a test, or a feature loses its test,
update this paragraph in the same change; don't let this description
silently drift the way it once did (an earlier version of this section
described only two basic scenarios, long after the suite had grown well
past that).
Separately, and worth remembering: a single commit whose message described
itself as a trivial doc-only rename (updating references to the sibling
repo's own former, never-public name) turned out, on closer inspection, to have
silently reverted **four** already-shipped, already-documented features at
once — the scan-hint toggle, the extra OCR languages, edit-time OCR's
multi-page support (back to first-page-only), and the PDF page count
feature entirely, deleting `tests/test_page_count.py` and 32 lines of
`tests/test_edit_ocr.py` along with it. It was built from a base that
predated the commits that added those features, and none of it showed up
as a conflict. The lesson: a commit message describing a small, obviously-
safe-sounding change (a rename, a reference update) is not a reliable
signal of its actual diff size or risk — if something regresses that a
commit's message gives no reason to suspect it touched, check that commit's
actual diff rather than trusting the message, especially for any commit
touching `dossiary.html` alongside doc files.

