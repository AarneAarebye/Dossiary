# Hub-cut inventory (working notes; deleted in Task 8)

Branch `feat/cut-hub-lease`, base `1323fee`, `dossiary.html` 19650 lines. Line numbers are the file as it stood at the branch point; they move as soon as Task 5 starts editing.

## Baseline (before any change)

Whole suite run once, 4 parallel batches, `python3 tests/test_*.py`, logs in `/tmp/claude-501/base-<script>.log`.

- 109 scripts, **109 exit 0, 0 non-zero**. No printed check line ends in `: False`.
- `: False` does appear inside the printed state dumps of `test_share_library.py` (line 91, `{'r': False, 'written': False}` after a `True` check) and many lines of `test_sync_lease.py` (`'unsaved': False` etc. after a `True` check). Those are data, not failed checks.
- Lines containing `True` across all logs: 2823.
- The three non-Playwright scripts (`test_i18n_coverage.py`, `test_user_guides.py`, `test_scan_watch_version.py`) all exit 0.

## Classification totals (201 matching lines in `dossiary.html`)

| Class | Lines |
|---|---|
| REMOVE | 157 |
| KEEP-GUARD | 35 |
| KEEP-ADMIN | 2 |
| KEEP-BOOKKEEPING | 7 |
| total | 201 |

Searched for: `syncLease`, `syncConfirmLease`, `syncBehind`, `pollSyncState`, `syncWroteWithoutLease`, `setLibraryConnection`, `SYNC_VIEW_PREF_KEYS`, `syncLastState`, `connectionPending`, `connectionError`, `disconnectedSince`, `sync-marker`, `sync-notice-dialog`, `syncMayWriteFiles`, `__DEBUG_sync*`. `syncLease*` also matches the helpers `syncLeasePending`, `syncLeaseCall`, `syncLeaseForBackgroundOnly`, `syncLeaseResult`, `syncLeaseHolder`, `syncLeaseSaysDeleted`, `syncLeasePendingBackground`. Where a line mixes a removed and a kept term it carries the class of the term that has to survive, and the reason says what to drop from it.

## Findings that change the plan (read first)

1. **The delete flow does not acquire a lease from the page.** `performSyncedDelete()` (18010) posts `POST /admin/libraries/<id>/delete {takeOver}` and the hub takes the lease itself. The page only (a) reads `GET .../state` to decide whether the button says "Take over and delete" (`res.body.lease.holder === 'other'`, 17913-17918: reads the answer, not `syncLease`) and (b) releases a lease **the editing state machine happened to hold** (`ctx.heldLease = syncLease.state === 'holding' || 'offline'` at 18005, release POST at 18027, after a failed delete). With the editing lease gone `ctx.heldLease` is always false, so the release call and its `syncAdminFetch(.../lease, release)` go too. The plan's "small standalone helper that acquires/releases the lease" is not needed: nothing in the page needs to acquire a lease before deleting. `test_delete_library.py` still asserts a lease is held before delete (case 3, line 240) and counts `/lease` release calls (lines 196, 249, 268, 547): those checks were about the editing lease and must be rewritten/removed (it is the behaviour removed on purpose).
2. **No admin flow other than delete touches the lease.** Share (`/admin/libraries/share`, only offered when `!syncLibrary`), devices (`/admin/devices*`, `/admin/pair-code`, `/admin/connect*`, `/admin/libraries`, `/admin/libraries/available`, `/admin/libraries/<id>/get`) and the libraries-root check make no lease call. The only lease HTTP is `syncLeaseCall()` (17166), reached from `acquireLeaseForWrite`, `syncHeartbeat`, `syncRetryFromOffline`, `releaseLease` (all REMOVE) and the delete release above. The one other contact is `GET .../state` inside the devices dialog (18962) which only feeds `stateAnswered` for the Work-disconnected button (REMOVE with the button) and the delete dialog's take-over wording (stays).
3. **Every save becomes a "lease-less write".** `syncWroteWithoutLease` is today the exception (`unconnected`/`unsynced`); after the cut it is the only case. Its keep-aside-with-notice behaviour (16946, `maybeReload` 17609-17627, `syncKeepAsideAndReload`) is exactly the surviving guard in the spec ("a Mac save that collides is kept aside, notice names it"), so it is classified KEEP-GUARD and its conditions (`syncLease.state !== 'holding'...`) collapse to true. Decision for Task 5: keep the flag as the single "the last real write may have been pulled over" marker, or fold into `syncDiskIsOurs()`.
4. **`pollSyncState()` is mixed.** Besides the lease states it is the only place a live tab learns of (a) a library deleted elsewhere (`syncLibraryDeletedElsewhere`, `syncDetachDeleted`; `test_delete_library.py` drives it through `__DEBUG_syncNow` ~18 times), (b) a newer hub version while the tab is open (`syncNoteNewer(st.version)`, 17517; otherwise only `syncNewerOnDisk()` at write time reads `.dossiary-sync.json`), (c) kept-aside versions (`noteKeptAside`, 17566; shown in the devices dialog too). The spec says "the state poll for the lease" goes and `.dossiary-sync.json` "is no longer read for the lease". If the poll is removed entirely, (a)-(c) stop working while the tab is open. The inventory classifies the function and the tick call KEEP-GUARD (reduced to: 401 handling, deleted, version, keptAside; no lease/disconnected/offline branches, no marker render). **The person/Task 5 should confirm this reading of the spec.** It also decides whether `__DEBUG_syncNow`/`__DEBUG_syncState` stay (they do in this reading: KEEP-BOOKKEEPING).
5. **`ensureEditLease()` has 49 call sites** (first line of ~46 entry points + definition + 2 debug) which the search terms above do not match. It does two jobs: take the lease (REMOVE) and "if memory is behind a newer version, reload/keep aside before the flow starts, refuse under an open dialog" (KEEP-GUARD, lines 16933-16975). Suggest Task 5 renames it to what remains (e.g. `ensureCurrentVersion()`), keeping the call sites. `syncNewerOnDisk()` (17153) must then run for every flow, not only when `state !== holding`.
6. **Other held-back machinery is lease-adjacent and not in the search list but dies with the take-over dialog:** `syncHoldBack` (16710), `writeHeldBackCopy[Now]` (16725-16757), `syncUnsavedChanges` (most uses), `switchLibraryAsking` (17350, called at 4840, 8668, 18786; dialog keys `syncDiscard*`), `syncJobDataHeld`/`syncRetryHeldBack` (17093-17122), `syncBackgroundMayWrite` (17129), `syncPersonActivity` (17079), `syncEditDialogEl`/`SYNC_EDIT_DIALOG_MAX_MS`, heartbeat/idle constants. `syncKeepAsideAndReload` calls `syncHoldBack()` at 16855 when even the keep-aside copy fails: that fallback needs a replacement (a plain error status) in Task 5; `syncKeptAsideFailed` stays.
7. **Share's "uploading..." marker** (18652 `pollSyncState()` right after sharing, `syncMarkerUploading*` strings) goes with the marker. The share-done status line stays.
8. **`SYNC_VIEW_PREF_KEYS`** (16634) is also what keeps view-preference `db.run`s out of `syncChangeSeq` (so `syncDirty()` ignores them) and what a reload carries over (17696). It stays (KEEP-BOOKKEEPING) even though "view-only saves are memory-only in some states" goes; `opts.viewOnly` in `persistDb` becomes only a hint, and 9+ callers pass it.

## Per-reference classification

| Line | Class | Why | Code |
|---|---|---|---|
| 43 | REMOVE | sync marker CSS/element | `.sub-sync-marker{ flex-shrink:1; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; pad` |
| 46 | REMOVE | sync marker CSS/element | `.sub-sync-marker[data-state="holding"]{ color:var(--phosphor); }` |
| 47 | REMOVE | sync marker CSS/element | `.sub-sync-marker[data-state="other"], .sub-sync-marker[data-state="unsaved"]{ color:var(--amber); }` |
| 48 | REMOVE | sync marker CSS/element | `.sub-sync-marker[data-state="sync-error"]{ color:var(--red); }` |
| 49 | REMOVE | sync marker CSS/element | `.sub-sync-marker.sub-sync-link{ cursor:pointer; text-decoration:underline; text-underline-offset:2px; }` |
| 50 | REMOVE | sync marker CSS/element | `.sub-sync-marker.sub-sync-link:focus-visible{ outline:1px solid currentColor; outline-offset:-1px; }` |
| 857 | REMOVE | sync marker CSS/element | `<div class="sub"><span id="sub-label">No library open</span><button type="button" id="reload-btn" class="sub-s` |
| 5447 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `// Two-Mac editing at a glance (states are syncLease.state; "real" = not` |
| 5450 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `//   holding / offline : confirm first (syncConfirmLease(): a state poll` |
| 5462 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `//                       and remembered (syncWroteWithoutLease): a newer` |
| 5466 | KEEP-GUARD | comment: the behind-a-newer-version rule survives | `//   behind a newer version (syncBehind(), disk not ours) on a real write` |
| 5472 | KEEP-GUARD | comment: behind-a-newer-version kept aside survives | `// than its memory (syncBehind(): kept aside instead). Without a lease a` |
| 5502 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `let leaseless = false;   // a real write with no lease to be had (see syncWroteWithoutLease)` |
| 5513 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `if(syncLease.state !== 'holding' && syncLease.state !== 'offline' && syncLease.state !== 'disconnected'){` |
| 5514 | KEEP-GUARD | newer-on-disk check; must run for every save once the state branch is gone | `if(syncBehind() \|\| syncReloadWanted \|\| await syncNewerOnDisk()) setTimeout(() => { maybeReload(); }, 0);` |
| 5517 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `if(syncUnsavedChanges \|\| syncLeasePending \|\| syncReloading) return false;` |
| 5518 | KEEP-GUARD | behind/reload-wanted branch of the write gate | `if(syncBehind() \|\| syncReloadWanted){` |
| 5527 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `if(syncLease.state === 'holding' \|\| syncLease.state === 'offline'){` |
| 5529 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `const answered = await syncConfirmLease();` |
| 5533 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `if(!answered && (syncLease.state === 'holding' \|\| syncLease.state === 'offline')){` |
| 5538 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `const free = syncLease.state !== 'holding' && syncLease.state !== 'offline' && syncLease.state !== 'disconnect` |
| 5540 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `if(opts.background && syncLease.state === 'other'){ syncHoldBack(); return false; }` |
| 5542 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `const backingOff = syncLease.state === 'unsynced' && syncNow() - syncUnsyncedAt < SYNC_UNANSWERED_RETRY_MS;` |
| 5545 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `const wasHolding = syncLease.state === 'holding';` |
| 5550 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `if(ok && opts.background && !wasHolding && syncLease.state === 'holding' && !syncPersonFlowPending) syncLeaseF` |
| 5554 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `const device = syncLease.deviceName \|\| t('syncAnotherMac');` |
| 5575 | KEEP-GUARD | syncBehind() && !diskIsOurs -> keep aside + reload (the guard) | `if(syncBehind() && !(await syncDiskIsOurs())){` |
| 5576 | KEEP-GUARD | quiet keep-aside decision; drop only the syncWroteWithoutLease term | `const quiet = !!opts.background && !syncUnsavedChanges && !syncPersonFlowPending && syncPersonFlowHold === 0 &` |
| 5580 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `leaseless = syncLease.state === 'unconnected' \|\| syncLease.state === 'unsynced' \|\| syncLease.state === 'discon` |
| 5581 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `leased = syncLease.state === 'holding' \|\| syncLease.state === 'offline';` |
| 5600 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `if(leaseless) syncWroteWithoutLease = true;` |
| 5601 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `else if(leased) syncWroteWithoutLease = false;` |
| 5607 | REMOVE | persistDb lease gating (state machine / acquire / confirm) | `if(!opts.background){ syncLeaseForBackgroundOnly = false; syncPersonFlowPending = false; }` |
| 14515 | KEEP-GUARD | preview job gate: reduces to !syncBehind() once leases go | `if(!syncMayWriteFiles()){ previewsRun.stop = true; break; }   // two-Mac editing: no lease, no preview files` |
| 15672 | KEEP-GUARD | OCR/preview file-write gate: reduces to !syncBehind() | `if(!syncMayWriteFiles()) return;   // the lease went meanwhile: the row stays queued` |
| 15707 | KEEP-GUARD | job gate: keep syncBehind(); drop the "other" lease state and syncUnsavedChanges | `if(syncLibrary && (syncLease.state === 'other' \|\| syncBehind() \|\| syncUnsavedChanges)) return;` |
| 16508 | REMOVE | token connect: lease state transition + retry of held-back | `if(token && syncLibrary && syncLease.state === 'unconnected'){` |
| 16574 | REMOVE | lease state variable/reset | `let syncLease = { state: 'none' };    // 'none' \| 'holding' \| 'offline' \| 'disconnected' (+since) \| 'other' (+` |
| 16583 | REMOVE | lease state variable/reset | `let syncLeasePending = null;          // the acquire in flight; concurrent saves share it (one dialog)` |
| 16587 | REMOVE | lease state variable/reset | `let syncClockOffset = 0;              // tests advance the clock through __DEBUG_syncNow()` |
| 16592 | REMOVE | lease state variable/reset | `let syncLeasePendingBackground = false;  // the acquire in flight was a background write's (it never asks)` |
| 16594 | REMOVE | lease state variable/reset | `let syncLastState = null;             // the last GET /admin/libraries/<id>/state answer` |
| 16612 | REMOVE | lease state variable/reset | `let syncLeaseForBackgroundOnly = false; // the lease was taken by a background job and no person has changed a` |
| 16618 | KEEP-GUARD | flag of a write made without a lease; every save is lease-less after the cut, so it becomes the normal case | `let syncWroteWithoutLease = false;` |
| 16634 | KEEP-BOOKKEEPING | view-pref keys: also drive syncDirty()/trackDbChanges and what a reload carries over | `const SYNC_VIEW_PREF_KEYS = ['nav_style', 'sort_key', 'sort_dir', 'detail_panel_expanded', 'collections_nav_ex` |
| 16651 | KEEP-BOOKKEEPING | isViewPrefWrite(): keeps view prefs out of syncChangeSeq | `return SYNC_VIEW_PREF_KEYS.includes(key);` |
| 16681 | REMOVE | lease state variable/reset | `syncLease = lease;` |
| 16689 | KEEP-GUARD | clearSyncState: reset of the lease-less write flag | `syncLoadedHash = null; syncLastWrittenHash = null; syncWroteWithoutLease = false;` |
| 16691 | REMOVE | lease state variable/reset | `syncLease = { state: 'none' };` |
| 16696 | REMOVE | lease state variable/reset | `syncLastState = null;` |
| 16700 | REMOVE | lease state variable/reset | `syncLeaseForBackgroundOnly = false;` |
| 16789 | REMOVE | base follows version only while holding | `if(syncLease.state === 'holding' \|\| syncLease.state === 'offline') lib.base = lib.version;` |
| 16859 | KEEP-GUARD | syncKeepAsideAndReload: reset of the flag after keeping memory aside | `syncWroteWithoutLease = false;                   // memory (with that write) is aside too` |
| 16891 | KEEP-GUARD | the notice dialog ids; the dialog stays | `ids: { layer: 'sync-notice-layer', dialog: 'sync-notice-dialog', ok: 'sync-notice-ok-btn', cancel: 'sync-notic` |
| 16919 | REMOVE | ensureEditLease: lease acquisition half | `if(syncLease.state !== 'holding' && syncLease.state !== 'offline' && syncLease.state !== 'disconnected'){` |
| 16921 | REMOVE | ensureEditLease: lease acquisition half | `const backingOff = syncLease.state === 'unsynced' && syncNow() - syncUnsyncedAt < SYNC_UNANSWERED_RETRY_MS;` |
| 16927 | REMOVE | ensureEditLease: lease acquisition half | `const device = syncLease.deviceName \|\| t('syncAnotherMac');` |
| 16933 | KEEP-GUARD | ensureEditLease: behind-a-newer-version check, stays as the start-of-flow guard | `if(syncBehind() && await syncDiskIsOurs() && !syncReloadWanted) return lib === syncLibrary;` |
| 16934 | KEEP-GUARD | ensureEditLease: behind/reload-wanted branch, stays | `if(syncBehind() \|\| syncReloadWanted){` |
| 16946 | KEEP-GUARD | ensureEditLease: lease-less write met a newer foreign version -> keep aside + notice | `if(syncWroteWithoutLease && !syncDirty() && !syncUnsavedChanges && !(await syncDiskIsOurs())){` |
| 16952 | KEEP-GUARD | ensureEditLease: job-only unwritten data vs person change decision | `if(!personPendingBefore && !syncUnsavedChanges && syncPersistsInFlight === 0 && !syncWroteWithoutLease){` |
| 16966 | KEEP-GUARD | ensureEditLease: refuse while a reload is pending | `if(syncBehind() \|\| syncReloadWanted \|\| syncReloading){ syncRefuseUpdating(); return false; }` |
| 17080 | REMOVE | lease bookkeeping / held-back retry / background lease | `syncLeaseForBackgroundOnly = false;` |
| 17082 | REMOVE | lease bookkeeping / held-back retry / background lease | `if(syncLease.state === 'holding' \|\| syncLease.state === 'offline') lastRealSaveAt = syncNow();` |
| 17100 | REMOVE | lease bookkeeping / held-back retry / background lease | `const wasHolding = syncLease.state === 'holding';` |
| 17102 | REMOVE | lease bookkeeping / held-back retry / background lease | `const ok = syncLease.state === 'disconnected' \|\| await ensureLease(true);` |
| 17104 | REMOVE | lease bookkeeping / held-back retry / background lease | `if(syncLease.state === 'holding' \|\| syncLease.state === 'offline' \|\| syncLease.state === 'disconnected'){` |
| 17106 | REMOVE | lease bookkeeping / held-back retry / background lease | `if(!wasHolding && syncLease.state === 'holding') syncLeaseForBackgroundOnly = true;` |
| 17109 | REMOVE | lease bookkeeping / held-back retry / background lease | `syncLeaseForBackgroundOnly = false;` |
| 17123 | KEEP-GUARD | syncMayWriteFiles(): shrinks to !syncBehind() | `function syncMayWriteFiles(){` |
| 17125 | KEEP-GUARD | the syncBehind() term of syncMayWriteFiles stays | `if(syncBehind() \|\| syncUnsavedChanges) return false;` |
| 17126 | REMOVE | lease bookkeeping / held-back retry / background lease | `return syncLease.state === 'holding' \|\| syncLease.state === 'offline' \|\| syncLease.state === 'disconnected';` |
| 17132 | REMOVE | lease bookkeeping / held-back retry / background lease | `if(syncLease.state === 'none'){` |
| 17135 | REMOVE | lease bookkeeping / held-back retry / background lease | `if(syncLease.state === 'holding') syncLeaseForBackgroundOnly = true;   // given back soon (syncTick)` |
| 17137 | KEEP-GUARD | result of syncMayWriteFiles(); function otherwise dies | `return syncMayWriteFiles();` |
| 17144 | KEEP-GUARD | comment on syncNoteNewer (mentions pollSyncState); text to be rewritten | `// Mac's own push (pollSyncState()), which never lands here.` |
| 17148 | KEEP-GUARD | definition of syncBehind() | `const syncBehind = () => !!syncLibrary && syncKnownNewer > syncLibrary.version;` |
| 17162 | KEEP-GUARD | syncNewerOnDisk: noting the sync-file version; becomes unconditional | `if(syncLease.state !== 'holding') syncNoteNewer(version);` |
| 17163 | KEEP-GUARD | syncNewerOnDisk returns syncBehind() | `return syncBehind();` |
| 17166 | REMOVE | lease HTTP call, acquire, answers | `function syncLeaseCall(action, takeOver, opts = {}){` |
| 17176 | REMOVE | lease HTTP call, acquire, answers | `setTimeout(() => syncLeaseSaysDeleted(lib), 0);` |
| 17184 | REMOVE | lease HTTP call, acquire, answers | `let syncLeaseDeletedChecking = false;` |
| 17185 | REMOVE | lease HTTP call, acquire, answers | `async function syncLeaseSaysDeleted(lib){` |
| 17186 | REMOVE | lease HTTP call, acquire, answers | `if(syncLeaseDeletedChecking \|\| lib !== syncLibrary \|\| syncLibraryGone) return;` |
| 17187 | REMOVE | lease HTTP call, acquire, answers | `syncLeaseDeletedChecking = true;` |
| 17189 | REMOVE | lease HTTP call, acquire, answers | `await pollSyncState({ noReload: true });` |
| 17195 | REMOVE | lease HTTP call, acquire, answers | `}finally{ syncLeaseDeletedChecking = false; }` |
| 17197 | REMOVE | lease HTTP call, acquire, answers | `const syncLeaseResult = (res) => res && res.ok && res.body && typeof res.body.result === 'string' ? res.body.r` |
| 17198 | REMOVE | lease HTTP call, acquire, answers | `const syncLeaseHolder = (res) => (res && res.body && res.body.lease && typeof res.body.lease === 'object') ? r` |
| 17212 | REMOVE | lease HTTP call, acquire, answers | `while(syncLeasePending){` |
| 17213 | REMOVE | lease HTTP call, acquire, answers | `const joinedBackground = syncLeasePendingBackground;` |
| 17214 | REMOVE | lease HTTP call, acquire, answers | `const ok = await syncLeasePending;` |
| 17217 | REMOVE | lease HTTP call, acquire, answers | `syncLeasePendingBackground = background;` |
| 17218 | REMOVE | lease HTTP call, acquire, answers | `syncLeasePending = acquireLeaseForWrite(background).finally(() => { syncLeasePending = null; });` |
| 17219 | REMOVE | lease HTTP call, acquire, answers | `return syncLeasePending;` |
| 17229 | REMOVE | lease HTTP call, acquire, answers | `const res = await syncLeaseCall('acquire', false);` |
| 17232 | REMOVE | lease HTTP call, acquire, answers | `const result = syncLeaseResult(res);` |
| 17234 | REMOVE | lease HTTP call, acquire, answers | `const other = syncOtherLease(syncLeaseHolder(res) \|\| {});` |
| 17242 | REMOVE | lease HTTP call, acquire, answers | `const res2 = await syncLeaseCall('acquire', true);` |
| 17255 | REMOVE | lease HTTP call, acquire, answers | `const result = syncLeaseResult(res);` |
| 17260 | KEEP-GUARD | comment in applyAcquireAnswer; the function dies, the sentence is about syncBehind | `// version here can be newer than this tab's memory (syncBehind()).` |
| 17266 | REMOVE | lease HTTP call, acquire, answers | `if(result === 'granted' && syncLibrary && res.body.version === syncLibrary.version && !syncBehind()){` |
| 17267 | REMOVE | lease HTTP call, acquire, answers | `syncWroteWithoutLease = false;` |
| 17270 | REMOVE | lease HTTP call, acquire, answers | `const lease = syncLeaseHolder(res);` |
| 17352 | REMOVE | take-over dialog / tick / poll lease states / confirm | `const device = escapeHtml(syncLease.deviceName \|\| t('syncAnotherMac'));` |
| 17379 | REMOVE | take-over dialog / tick / poll lease states / confirm | `// (pollSyncState()).` |
| 17387 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(syncLease.state === 'unconnected' && readSyncAdminToken()){` |
| 17396 | REMOVE | take-over dialog / tick / poll lease states / confirm | `const state = syncLease.state;` |
| 17403 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(held && !syncLeaseForBackgroundOnly && editDialogOpen && now - syncLastInputAt < SYNC_EDIT_DIALOG_MAX_MS) l` |
| 17408 | REMOVE | take-over dialog / tick / poll lease states / confirm | `const idleAfter = syncLeaseForBackgroundOnly ? SYNC_HEARTBEAT_MS : SYNC_IDLE_RELEASE_MS;` |
| 17409 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(held && now - lastRealSaveAt >= idleAfter && !(syncLeaseForBackgroundOnly && syncBackgroundJobRunning())){` |
| 17416 | KEEP-GUARD | tick keeps asking the state if a reduced pollSyncState() stays (deleted elsewhere, newer version, kept aside) -- DECISION for Task 5 | `const answered = await pollSyncState();` |
| 17419 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(syncLease.state === 'unsynced' && (syncUnsavedChanges \|\| syncJobDataHeld()) && (answered \|\| syncNow() - syn` |
| 17421 | REMOVE | take-over dialog / tick / poll lease states / confirm | `}else if(syncLease.state === 'disconnected' && (syncUnsavedChanges \|\| syncJobDataHeld())){` |
| 17435 | KEEP-GUARD | pollSyncState(): lease half REMOVE; deleted-elsewhere, syncNoteNewer(st.version) and noteKeptAside are the only ways a live tab learns of a phone edit/deletion -- DECISION | `async function pollSyncState(opts = {}){` |
| 17440 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(res) syncAnswerSeq++;   // the service answered (syncConfirmLease() asks only that)` |
| 17444 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(syncLease.state !== 'holding' && syncLease.state !== 'offline') setSyncLease({ state: 'unconnected' });` |
| 17469 | REMOVE | syncLastState: only the marker (lastError, uploading) reads it | `syncLastState = st;` |
| 17473 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(typeof st.disconnectedSince === 'string' && st.disconnectedSince){` |
| 17474 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(syncLease.state !== 'disconnected') setSyncLease({ state: 'disconnected', since: st.disconnectedSince });` |
| 17479 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(syncLease.state === 'disconnected') setSyncLease({ state: 'none' });   // reconnected` |
| 17484 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(syncLease.state === 'holding' && otherHolds){` |
| 17488 | REMOVE | take-over dialog / tick / poll lease states / confirm | `}else if(syncLease.state === 'holding' && !thisHolds){` |
| 17493 | REMOVE | take-over dialog / tick / poll lease states / confirm | `}else if(syncLease.state === 'none' && otherHolds){` |
| 17495 | REMOVE | take-over dialog / tick / poll lease states / confirm | `}else if(syncLease.state === 'other' && otherHolds){` |
| 17497 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(other.deviceName !== syncLease.deviceName \|\| other.since !== syncLease.since) setSyncLease(other);` |
| 17498 | REMOVE | take-over dialog / tick / poll lease states / confirm | `}else if(syncLease.state === 'other' && !otherHolds){` |
| 17500 | REMOVE | take-over dialog / tick / poll lease states / confirm | `}else if(syncLease.state === 'offline' && (otherHolds \|\| (st.offline === false && st.hubReachable !== false)))` |
| 17515 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(syncLease.state === 'holding' && thisHolds && !leftOffline){` |
| 17516 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(st.version > lib.version && !syncBehind()) lib.version = lib.base = st.version;` |
| 17517 | KEEP-GUARD | else-branch is syncNoteNewer(st.version): stays, unconditional | `}else if(syncLease.state !== 'offline'){` |
| 17527 | REMOVE | take-over dialog / tick / poll lease states / confirm | `// period (pollSyncState() switches the state); a heartbeat over 2 minutes` |
| 17538 | REMOVE | take-over dialog / tick / poll lease states / confirm | `async function syncConfirmLease(){` |
| 17544 | REMOVE | take-over dialog / tick / poll lease states / confirm | `await pollSyncState({ noReload: true, timeoutMs: SYNC_CONFIRM_TIMEOUT_MS });` |
| 17549 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(syncLease.state === 'holding' && syncNow() - syncLastHeartbeatAt > SYNC_STALE_HOLD_MS){` |
| 17552 | REMOVE | take-over dialog / tick / poll lease states / confirm | `if(!answered && syncLease.state === 'holding') return false;` |
| 17590 | KEEP-BOOKKEEPING | test hook for syncBackgroundJobRunning(); stays while jobs gate reloads (check tests) | `window.__DEBUG_syncBackgroundBusy = (on) => { syncTestBackgroundBusy = !!on; };` |
| 17596 | REMOVE | syncReloadBlocked: syncLeasePending term | `\|\| syncPersistsInFlight > 0 \|\| (!force && !!syncLeasePending) \|\| syncUnsavedChanges \|\| syncDirty() \|\| syncBack` |
| 17607 | KEEP-GUARD | maybeReload: nothing to reload unless behind | `if(!syncReloadWanted && !syncBehind()) return false;` |
| 17609 | KEEP-GUARD | maybeReload: lease-less write branch (becomes unconditional) | `if(syncWroteWithoutLease){` |
| 17615 | KEEP-GUARD | maybeReload: still not behind after the disk check | `return lib === syncLibrary && !syncBehind() && !syncReloadWanted;` |
| 17618 | KEEP-GUARD | maybeReload: recheck behind | `if(!syncReloadWanted && !syncBehind()) return false;` |
| 17619 | KEEP-GUARD | oursWithoutLease: with no lease states it is always true | `oursWithoutLease = syncLease.state !== 'holding' && syncLease.state !== 'offline';` |
| 17627 | KEEP-GUARD | maybeReload: reset of the flag after reload | `syncWroteWithoutLease = false;` |
| 17696 | KEEP-BOOKKEEPING | reloadLibraryKeepingView: which settings rows to carry over | `const prefs = queryAll('SELECT key, value FROM settings').rows.filter(r => SYNC_VIEW_PREF_KEYS.includes(r[0]))` |
| 17728 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const res = await syncLeaseCall('heartbeat', false, { timeoutMs: opts.timeoutMs });` |
| 17729 | REMOVE | heartbeat/offline/release/marker/debug hooks | `if(lib !== syncLibrary \|\| syncLease.state !== 'holding') return true;` |
| 17731 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const result = syncLeaseResult(res);` |
| 17734 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const holder = syncLeaseHolder(res);` |
| 17740 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const again = await syncLeaseCall('acquire', false, { timeoutMs: opts.timeoutMs });` |
| 17741 | REMOVE | heartbeat/offline/release/marker/debug hooks | `if(lib !== syncLibrary \|\| syncLease.state !== 'holding') return true;` |
| 17742 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const r = syncLeaseResult(again);` |
| 17752 | REMOVE | heartbeat/offline/release/marker/debug hooks | `else if(r === 'busy') setSyncLease(syncOtherLease(syncLeaseHolder(again) \|\| {}));` |
| 17760 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const res = await syncLeaseCall('acquire', false);` |
| 17761 | REMOVE | heartbeat/offline/release/marker/debug hooks | `if(lib !== syncLibrary \|\| syncLease.state !== 'offline') return;` |
| 17762 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const r = syncLeaseResult(res);` |
| 17766 | REMOVE | heartbeat/offline/release/marker/debug hooks | `else if(r === 'busy') setSyncLease(syncOtherLease(syncLeaseHolder(res) \|\| {}));` |
| 17773 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const held = syncLease.state === 'holding' \|\| syncLease.state === 'offline';` |
| 17775 | REMOVE | heartbeat/offline/release/marker/debug hooks | `if(held && readSyncAdminToken()) syncLeaseCall('release', false, { keepalive: true });` |
| 17779 | REMOVE | heartbeat/offline/release/marker/debug hooks | `if(held && readSyncAdminToken()) await syncLeaseCall('release', false);` |
| 17780 | REMOVE | heartbeat/offline/release/marker/debug hooks | `if(lib === syncLibrary && (syncLease.state === 'holding' \|\| syncLease.state === 'offline')) setSyncLease({ sta` |
| 17787 | REMOVE | heartbeat/offline/release/marker/debug hooks | `const marker = el('sync-marker');` |
| 17789 | REMOVE | heartbeat/offline/release/marker/debug hooks | `let state = syncLibrary ? (syncUnsavedChanges ? 'unsaved' : syncLease.state) : 'none';` |
| 17793 | REMOVE | heartbeat/offline/release/marker/debug hooks | `title = t('syncMarkerUnsavedTitle', { device: syncLease.deviceName \|\| t('syncAnotherMac') });` |
| 17794 | REMOVE | heartbeat/offline/release/marker/debug hooks | `}else if(state === 'holding' && syncLastState && typeof syncLastState.lastError === 'string' && syncLastState.` |
| 17795 | REMOVE | heartbeat/offline/release/marker/debug hooks | `if(syncLastState.hubReachable === false){` |
| 17802 | REMOVE | heartbeat/offline/release/marker/debug hooks | `title = syncLastState.lastError;` |
| 17805 | REMOVE | heartbeat/offline/release/marker/debug hooks | `}else if(syncLastState && syncLastState.uploading === true && ['none', 'holding', 'offline', 'unsynced'].inclu` |
| 17811 | REMOVE | heartbeat/offline/release/marker/debug hooks | `text = t(SYNC_MARKER_KEYS[state], { device: syncLease.deviceName \|\| '' });` |
| 17817 | REMOVE | heartbeat/offline/release/marker/debug hooks | `else if(state === 'unsynced') title = syncLease.reason \|\| '';` |
| 17835 | REMOVE | heartbeat/offline/release/marker/debug hooks | `window.__DEBUG_syncLease = () => syncLease;` |
| 17836 | KEEP-BOOKKEEPING | test hook: tests drive the tick with it (test_delete_library, test_share_library); stays if a tick stays | `window.__DEBUG_syncNow = async (ms) => { syncClockOffset += ms \|\| 0; await syncTick(); };` |
| 17837 | KEEP-BOOKKEEPING | __DEBUG_syncState: dirty/unsaved/reloads fields are read by tests; state/pending/wroteWithoutLease fields go | `window.__DEBUG_syncState = () => ({ state: syncLease.state, version: syncLibrary ? syncLibrary.version : null,` |
| 17838 | KEEP-BOOKKEEPING | rest of __DEBUG_syncState | `pending: !!syncLeasePending, reloads: syncReloadCount, dirty: syncDirty(), flowPending: syncPersonFlowPending,` |
| 17841 | REMOVE | heartbeat/offline/release/marker/debug hooks | `window.__DEBUG_syncClockSkip = (ms) => { syncClockOffset += ms \|\| 0; };   // time passes with no tick (a sleep` |
| 18005 | REMOVE | delete flow: remembers a lease held by editing | `ctx.heldLease = syncLease.state === 'holding' \|\| syncLease.state === 'offline';` |
| 18073 | KEEP-ADMIN | comment on delete-elsewhere handling, mentions pollSyncState seeing `deleted` | `// pollSyncState() saw `deleted` (or a lease call answered 404` |
| 18097 | REMOVE | syncDetachDeleted: resets syncLease; the variable goes | `syncLease = { state: 'none' };` |
| 18195 | KEEP-ADMIN | __DEBUG_syncLibraryGone: deleted-elsewhere state | `window.__DEBUG_syncLibraryGone = () => syncLibraryGone;` |
| 18652 | REMOVE | marker "uploading" refresh after share | `if(syncLibrary) pollSyncState();   // the marker shows "uploading…" right away` |
| 18947 | REMOVE | devices dialog: Work disconnected / Reconnect | `disconnectedSince: {},` |
| 18948 | REMOVE | devices dialog: Work disconnected / Reconnect | `connectionError: {},   // library id → why the last Disconnect/Reconnect failed` |
| 18949 | REMOVE | devices dialog: Work disconnected / Reconnect | `connectionPending: {}, // library id → a Disconnect/Reconnect is being sent` |
| 18965 | REMOVE | devices dialog: Work disconnected / Reconnect | `state.disconnectedSince[l.id] = ok && typeof res.body.disconnectedSince === 'string' ? res.body.disconnectedSi` |
| 18976 | REMOVE | devices dialog: Work disconnected / Reconnect | `<li>${escapeHtml(l.name)}${l.available ? '' : ` <span class="devices-unavailable">(${t('devicesLibraryNotAvail` |
| 18977 | REMOVE | devices dialog: Work disconnected / Reconnect | `<div class="devices-lib-error">${escapeHtml(devicesState.connectionError[l.id])}</div>` : ''}${(kept[l.id] \|\| ` |
| 18985 | REMOVE | devices dialog: Work disconnected / Reconnect | `const since = (devicesState.disconnectedSince \|\| {})[id];` |
| 18987 | REMOVE | devices dialog: Work disconnected / Reconnect | `const dis = (devicesState.connectionPending \|\| {})[id] ? ' disabled' : '';` |
| 19034 | REMOVE | devices dialog: Work disconnected / Reconnect | `if(btn) setLibraryConnection(seq, btn.dataset.library, btn.classList.contains('devices-lib-reconnect-btn'));` |
| 19260 | REMOVE | setLibraryConnection and its calls | `async function setLibraryConnection(seq, libraryId, connected){` |
| 19262 | REMOVE | setLibraryConnection and its calls | `if(!state \|\| state.connectionPending[libraryId]) return;   // one request at a time per library` |
| 19264 | REMOVE | setLibraryConnection and its calls | `state.connectionPending[libraryId] = true;` |
| 19265 | REMOVE | setLibraryConnection and its calls | `delete state.connectionError[libraryId];` |
| 19268 | REMOVE | setLibraryConnection and its calls | `delete state.connectionPending[libraryId];` |
| 19271 | REMOVE | setLibraryConnection and its calls | `if(!res \|\| !res.ok){ state.connectionError[libraryId] = syncErrorText(res); render(); return; }` |
| 19272 | REMOVE | setLibraryConnection and its calls | `state.disconnectedSince[libraryId] = res.body && typeof res.body.disconnectedSince === 'string' ? res.body.dis` |
| 19274 | REMOVE | setLibraryConnection and its calls | `if(syncLibrary && syncLibrary.libraryId === libraryId) await pollSyncState({ noReload: true });` |
| 19390 | REMOVE | sync-marker click/keyboard handlers | `el('sync-marker').addEventListener('click', () => {` |
| 19391 | REMOVE | sync-marker click/keyboard handlers | `if(el('sync-marker').dataset.state === 'unconnected' && modalRoot.innerHTML === '') openDevicesDialog();` |
| 19393 | REMOVE | sync-marker click/keyboard handlers | `el('sync-marker').addEventListener('keydown', (e) => {` |
| 19394 | REMOVE | sync-marker click/keyboard handlers | `if((e.key === 'Enter' \|\| e.key === ' ') && el('sync-marker').dataset.state === 'unconnected'){` |

### Line clusters (brief's list, verified against this tree)

| Brief cluster | Found at | Contents |
|---|---|---|
| 5447-5607 | 5445-5607 | comment block + `persistDb()` lease gating; lines 5574-5579 (`syncBehind() && !syncDiskIsOurs()` keep-aside) are the guard that stays |
| 14515, 15672, 15707 | same | `syncMayWriteFiles()` / lease-`other` gates for preview and OCR jobs |
| 16508 | 16508-16511 | token set -> leave `unconnected`, retry held-back |
| 16574-16700 | 16574-16701 | state variables (`syncLease`, held-back, heartbeat...), `SYNC_FILE_NAME`/`SYNC_BASE_FILE_NAME` (KEEP-BOOKKEEPING, not matched by the search), `readSyncFile`, `setSyncLease`, `clearSyncState` |
| 16789 | 16789 | `lib.base = lib.version` only while holding |
| 16859-16966 | 16833-16975 | `syncKeepAsideAndReload` (stays), `ensureEditLease` (split, see finding 5) |
| 17080-17270 | 17079-17282 | person activity, held-back retry, `syncMayWriteFiles`, `syncNoteNewer`/`syncBehind`/`syncNewerOnDisk` (stay), lease call/answers/acquire |
| 17352-17552 | 17337-17559 | take-over dialog, `switchLibraryAsking`, timer, `syncTick`, `pollSyncState` (split), `syncConfirmLease` |
| 17596-17627 | 17587-17639 | `syncReloadBlocked`, `maybeReload` (stay; drop the `syncLeasePending` term and lease-state tests) |
| 17696-17838 | 17696, 17726-17841 | view-pref carry-over (stays), heartbeat, offline retry, release, `pagehide` release, marker render, `__DEBUG_sync*` |
| 18005, 18073-18097 | same | delete flow's held-lease memory (REMOVE); delete-elsewhere handling (stays) |
| 18652 | 18652 | marker refresh after share |
| 18947-18987, 19034, 19260-19274 | same | devices dialog Work disconnected / Reconnect |
| not in brief | 19390-19398, 43-50, 857 | `#sync-marker` span, CSS and click/keydown handlers |

## Strings (STRINGS, all seven languages: de, en, es, fr, hy, zh-Hans, zh-Hant)

Every key below exists in all seven language blocks (checked). `test_i18n_coverage.py` requires the same key set in each.

### Used only by REMOVE code: 33 keys, delete from all seven

- `devicesLibraryDisconnect`
- `devicesLibraryDisconnectedSince`
- `devicesLibraryReconnect`
- `syncDiscardBtn`
- `syncDiscardText`
- `syncDiscardTitle`
- `syncHeldBackCopyStatus`
- `syncHeldBackCopyTitle`
- `syncHeldBackSavedStatus`
- `syncMarkerDisconnected`
- `syncMarkerDisconnectedTitle`
- `syncMarkerEditing`
- `syncMarkerEditingOffline`
- `syncMarkerEditingOfflineTitle`
- `syncMarkerEditingOn`
- `syncMarkerEditingOnTitle`
- `syncMarkerEditingTitle`
- `syncMarkerNotConnected`
- `syncMarkerNotConnectedTitle`
- `syncMarkerNotSynced`
- `syncMarkerUnsaved`
- `syncMarkerUnsavedTitle`
- `syncMarkerUploading`
- `syncMarkerUploadingTitle`
- `syncNotRunningReason`
- `syncNotSavedStatus`
- `syncNotStartedStatus`
- `syncTakeOverBtn`
- `syncTakeOverHint`
- `syncTakeOverText`
- `syncTakeOverTextNoTime`
- `syncTakeOverTitle`
- `syncTookOverStatus`

`data-i18n="toolbarSwitchLibrary"` (line 857) is NOT removed: the switch-library button stays.

### Shared with kept code (stay)

- `syncAnotherMac`: also kept at 9609, 13635, 16835, 17002, 17582, 17961, 18109, 18190 (kept-aside and deleted-elsewhere messages).
- `syncLibraryDeletedElsewhere`: kept at 16581, 17463-17464, 18102, 18127.
- `devicesUnexpectedAnswer`: kept at 16547, 18284.
- `devicesLibraryNotAvailable`, `devicesNoLibraries`, `devicesLibrariesHeading`, `devicesDisconnect`, `devicesDisconnected`: devices dialog proper, stay.
- `syncNoticeOk`, `syncKeptAside*`, `syncFlowKeptAside`, `syncCloseDialogFirst[Unknown]`, `syncLibraryUpdating`, `syncDocIdTakenError`, `syncLibraryDeleted*`, `syncDeleted*`, `syncLibraryDetachedLocal`, `syncKeptAside`: the guard, notice and deleted-elsewhere paths, stay.
- After Task 5, re-check usage per key: `syncSinceText()` (17283) is used only by the take-over dialog and goes with it.

## Tests referencing any of the identifiers

| Test | Refs | Notes |
|---|---|---|
| `tests/test_sync_lease.py` | 117 lines | whole file goes (spec). Also the only user of `__DEBUG_syncBackgroundBusy`, `__DEBUG_syncClockSkip`, `__DEBUG_syncLease`, `devices-lib-disconnect/reconnect`. Contains behaviour that SURVIVES and needs a replacement test in Task 3: newer version reloads once; opening Edit on a newer version reloads first; reload given up when a person's change arrives; lease-less write met by a foreign newer version -> kept aside + notice; reserved doc-id check; kept-aside announced once |
| `tests/test_delete_library.py` | 47 lines | uses `__DEBUG_syncLease()` (case 3, line 240), `__DEBUG_syncNow` (18x, keep), `__DEBUG_syncState` (dirty/unsaved, keep), `__DEBUG_ensureEditLease` (8x, name changes), `__DEBUG_persistDb` (7x), `/lease` release assertions (196, 249, 268, 547), `sync-marker` (166, 626). Needs editing; not weakening: the lease checks are on removed behaviour |
| `tests/test_share_library.py` | 18 lines | `__DEBUG_syncState` (8x), `__DEBUG_syncNow`, `sync-marker` (2x, the "uploading" marker), `/lease` (1x), `dossiary-base`; needs editing for the marker |
| `tests/test_devices_dialog.py` | 0 refs by name | no Work-disconnected/Reconnect/lease assertions found; must still pass |
| others | none | `tests/*.js` stubs contain none |
