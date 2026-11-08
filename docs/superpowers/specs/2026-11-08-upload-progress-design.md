# Showing the progress of a library's first upload to the Pi

Date: 2026-11-08. Two steps, agreed 2026-11-08 ("Both, in two steps"). Step 1 (this spec's main part): page only, release 1.64.0. Step 2: real file/byte counts from Dossiary Sync, shown as a progress bar (a separate spec and plan, written after step 1 ships).

## Problem

After "⇪ Share this library…" the page says once "Shared “Meine Dossiers” — uploading to the Pi." and then nothing. Dossiary Sync reports only a yes/no flag while the first version goes to the hub (`GET /admin/libraries/<id>/state` → `uploading: true`, plus `version`, `hubReachable`, `lastError`). A library with 96 documents and previews takes minutes, and the person cannot tell whether it is working, finished or stuck.

## Step 1 (page, 1.64.0): live status

Source: the state poll the page already runs for a synced library (`pollSyncState()`, every `SYNC_TICK_MS` = 5 s, only with an admin token). No change to Dossiary Sync.

Behaviour for the open library:
- While `state.uploading === true`: a persistent line in the status area (not a toast that disappears): a spinner and **"Uploading to the Pi… {elapsed}"**, elapsed as `m:ss` ticking every second from when the page first saw `uploading` (or from the share finishing, whichever is earlier). While uploading, the state is polled every 2 s instead of 5 s.
- `uploading` turns false and the state's `version >= 1` after the page saw it uploading: the line becomes **"Uploaded “{name}” to the Pi (version {n}). Other devices can get it now."** (kind ok, stays until the next status message).
- While uploading and `hubReachable === false`: **"Waiting for the Pi… it is not reachable. The upload continues when it is back."**; the elapsed time keeps running.
- While uploading and `lastError` is a non-empty string: **"The upload has a problem: {lastError}"** (kind err) with the elapsed line kept; it goes back to normal if the error clears.
- No admin token, an old Dossiary Sync without the field, an unreadable answer: nothing changes (today's behaviour). Libraries that are not uploading show nothing new.
- Plain text only (`lastError` and names are inserted escaped / as text).
- Closing the library or switching libraries stops the ticker.
- The status survives a status-line replacement by other messages: when something else overwrites the line, the upload line returns on the next poll tick while still uploading.

New strings (7 languages en, es, fr, de, zh-Hans, zh-Hant, hy; Armenian unreviewed): `syncUploadingLine` ("Uploading to the Pi… {elapsed}"), `syncUploadDone`, `syncUploadWaitingHub`, `syncUploadProblem`.

## Tests

New `tests/test_upload_progress.py` (Playwright with the page's sync stubs, as `test_share_library.py`): a stub admin service answering `/admin/libraries/<id>/state` with a scripted sequence:
1. `uploading:true` → spinner line with elapsed time that advances; poll interval 2 s while uploading.
2. then `uploading:false, version:1` → the done line with the name and version.
3. `uploading:true, hubReachable:false` → the waiting line; then recovery.
4. `uploading:true, lastError:"x"` → the problem line (text with HTML in it shown as text); then cleared.
5. No admin token / 404 / malformed body → no upload line, no error.
6. Switching library stops the ticker (no further status updates).
Existing sync/share tests keep passing.

## Step 2 (outline, own spec later)

Dossiary Sync 0.17.0 adds counts to the state while a first upload runs (files and bytes done / total); the page shows "Uploading 142 of 290 files (48%)" with a bar. Needs a new Mac service build (both Macs) and a new Pi package, then page 1.65.0.

## Out of scope (step 1)

Percentages; the Get-it download side on the other Mac; the phones.
