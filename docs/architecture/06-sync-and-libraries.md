# Dossiary architecture notes: Dossiary Sync: the connection, a library deleted elsewhere, share library, saving without a lease

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

- **Dossiary Sync connection** (`openDevicesDialog()`, `syncAdminFetch()`,
  Tools → `#devices-btn`, "🔗 Dossiary Sync…"). **Since 1.71.0 the page
  only connects**: the devices list, Remove, a phone's libraries, pairing
  with a QR code, Make editor/phone, Rename, Delete library and Get it moved
  to Dossiary for Mac (0.11–0.13; dossiary-osx
  `docs/superpowers/specs/2026-11-24-admin-and-maintenance-design.md`,
  decision 6), with their page code, translations and qrcode-generator
  (`tests/test_delete_library.py` became `tests/test_deleted_elsewhere.py`,
  keeping only a library deleted on another device); the start screen's `#empty-devices-btn`
  and the Recent libraries 🗑 went too. The page keeps the token so an open
  synced library is checked with `pollSyncState()` (`GET
  /admin/libraries/<id>/state`) and so Share this library… works until the
  Mac has Put on Hub. The dialog talks to the loopback-only admin API on
  `http://127.0.0.1:8769` (3 s health timeout, 15 s for every other call,
  so a hung service never leaves a button disabled). Not answering → an
  explanation and the dossiary-sync link, with Look again (the token is
  kept); otherwise Connect asks the service to show a code as a macOS
  notification (a 429 names the wait) and swaps the typed code for an admin
  token, kept per browser in `localStorage` (`dossiary_sync_admin_token`,
  every access in try/catch; when `localStorage` refuses to store it, the
  in-memory copy is used for the rest of the session). **Every POST carries
  `Content-Type: application/json` and a JSON body** (`{}` when there's
  nothing to say): the service answers 415 otherwise, and the fake in the
  tests does the same, so a missing header fails the suite. A token the
  service no longer knows (`connected: false`, or a 401 from `GET
  /admin/libraries`, the one protected call the dialog makes) is dropped and
  Connect comes back. Connected (`loadDevicesConnected()`):
  `syncConnectedText`, `syncAdminInMacNote` pointing at Dossiary for Mac,
  and Disconnect (`DELETE /admin/connect`, the token forgotten either way);
  another failure of that call is shown as escaped text with Look again.
  `devicesDialogSeq` drops answers for a dialog that was closed or reopened
  meanwhile. `normalizeSyncDevice()` stays for Share's phone list. Tested by
  `tests/test_devices_dialog.py` (a fake `fetch` per scenario; the shared
  stub blocks the real service).
- **A library deleted elsewhere** (`syncLibraryDeletedElsewhere()`,
  `syncDetachDeleted()`; the page's own Delete library left in 1.71.0 --
  Dossiary for Mac's File › Delete Library… replaces it, spec in dossiary-ios
  `docs/superpowers/specs/2026-10-25-delete-library-design.md`). **Deleted
  elsewhere**: `pollSyncState()` seeing `deleted` in the state calls
  `syncLibraryDeletedElsewhere()` (after the save, when the poll is a
  save's confirm) -- also a late one, after the folder is already in the
  Trash (`trashed: true`, other fields possibly missing), (the
  state poll is the only way the page learns it; a save made before the poll
  knows is written as usual). Nothing
  unsaved: close any dialog, `resetAll()`, forget
  the Recent entry, and a notice (`#sync-deleted-dialog`) naming the device.
  Something in memory that isn't on disk: kept aside inside the folder first
  (not tried when `trashed`); if that isn't possible the library stays open
  read-only (`syncLibraryGone`: `persistDb()` and `ensureCurrentVersion()`
  refuse, the sync timer and OCR runner stop, no admin calls) with a notice
  offering "Download unsaved changes" (`db.export()` as `<name> unsaved
  <yyyy-mm-dd hhmm>.sqlite`, a Blob and `<a download>`) and "Close library"
  -- no ✕ or Escape -- so memory is never dropped without the person
  choosing to. **Only a tab that saw the library live runs this path**
  (`syncSeenLive`: an answered state without `deleted` since it opened). A tab whose first answer already says `deleted`
  with `trashed: true` (a first answer in the grace period, not trashed yet,
  takes the normal path above) --
  a folder taken back out of the Trash keeps its `.dossiary-sync.json` and
  meets the service's persisted record -- calls `syncDetachDeleted()`
  instead: `syncLibrary` = null (no admin calls or marker; saves go
  straight to disk), the id joins `syncDetachedLibraryIds` so reopening it
  this session stays local,
  the Recent entry stays, the sync file is left alone (it may be shared
  again), and the status line says `syncLibraryDetachedLocal`. Closing every dialog loses text typed into an open form (memory's
  changes are kept aside), and a running dialog's job finds its library gone. Tested by `tests/test_deleted_elsewhere.py`.
- **Share this library** (`openShareLibraryDialog()`,
  `ensureLibrariesRootHandle()`, `copyLibraryInto()`; Tools → `#share-library-btn`, shown only for an open
  library without `.dossiary-sync.json` (`updateShareLibraryItem()`, run when Tools
  opens); spec in dossiary-ios
  `docs/superpowers/specs/2026-10-25-share-library-design.md`). Every synced
  library lives in this Mac's **libraries folder**; a page never learns real
  paths, so Dossiary keeps a handle to that folder in a database of its own,
  `dossiary-libraries-root` (version 1, store `librariesRoot`, `{id: 'root',
  handle, root}`). `dossiary-app-db` deliberately stays at version 1: bumping
  it would block forever while an older Dossiary tab held the old connection,
  and an older copy on the shared `file://` origin would then hit a
  VersionError and show no Recent libraries. A blocked or failing open of the
  new database rejects (`onblocked`/`onerror`), so the stored folder counts as
  missing and the chooser appears instead of a hang (a choice that can't be
  stored is used for that time only). `ensureLibrariesRootHandle({slot, isOpen})` uses the
  stored handle when its permission is (or is again) granted; otherwise the
  slot names the folder to choose (the `root` a `POST
  /admin/libraries-root/check` with a probe that doesn't exist answers) and
  "Choose folder…" picks it: a `.dossiary-probe-<uuid>` file is written into
  the choice, the check is asked, and the probe is removed again either way;
  `ok: false` → "That isn't {root}. Choose that folder." and nothing stored.
  **Share**: without an admin token the dialog explains and offers Connect
  (the Dossiary Sync dialog); otherwise a name (the folder name without
  `.dossiary`, read-only once the library is known to be in place) and one
  unticked checkbox per paired phone (`GET /admin/devices`, role `phone`).
  Share: the libraries folder (refused with `shareLibraryRootIsLibrary` when
  it is the open library's own folder or inside it, `isInsideLibraryFolder()`),
  then background jobs are held (`holdBackgroundForShare()`:
  `shareHoldsBackground` stops a preview run after its current preview,
  skips OCR runner passes and makes `persistDb({background: true})` a no-op,
  until the reopen's `resetAll()` or a failure releases it), then
  `persistDb()` (the share route hashes `library.sqlite` at call time --
  deliberately after the folder choice, so the save sits right before the
  call), then either in place (`root.resolve(rootDirHandle)` is one step
  long) → `POST /admin/libraries/share {folder, phones}` with no timeout (the
  Mac creates the library on the Pi first), or a copy into a new
  `<Name>.dossiary` (numbered " 2", … when taken;
  `createEmptyLibraryFolder()` checks the folder it got is empty -- a
  same-named folder that appeared between the name check and the create is
  never used or removed, the next name is tried) by `copyLibraryInto()` --
  Back up's copier, pulled out of it unchanged: `library.sqlite` from
  `db.export()`, every other file from `listLibraryFiles()` (no sync
  bookkeeping, no `.DS_Store`/`._*`), 4 at a time -- with progress and Stop;
  Stop or the first unreadable/unwritable file removes the copy and says
  which file and why. A share that fails after the copy keeps it, says so,
  and the button becomes "Try again" (the same copy, posted again). No
  answer, or a 409 `already-shared` (a Try again after an answer that never
  arrived): when the folder's `.dossiary-sync.json` now names a library (not
  the one it named before the first attempt, `ctx.priorSyncIds`, nor a
  detached one), the share went through and is finished as a success.
  Success:
  `resetAll()` + `proceedWithRootDirHandle()` on the shared folder (so the new
  sync file is read), a copy replaces the original in Recent libraries
  (`forgetRecentLibrary()` first, the open records the copy), the status line
  "Shared “<hub's name>” — uploading to the Pi.", and for a copy a notice
  naming `<root>/<Name>.dossiary` and the original (never touched). The sync marker
  that used to read "uploading…" while `GET …/state` said `uploading: true` (`renderSyncMarker()`) was removed on
  2026-10-28; the status line stays and the shared library is polled like any synced one. **Upload
  status** (1.64.0, spec `docs/superpowers/specs/2026-11-08-upload-progress-design.md`, step 1):
  `noteUploadState()`, called by `pollSyncState()` for every answer it can read, drives `syncUpload`
  (`{libraryId, root, since, seen, graceUntil, hubDown, error, build, ticker}`, times from
  `performance.now()`). `uploading: true` → the status line
  "Uploading to the Pi… m:ss" (`syncUploadingLine`, kind busy, spinner), `since` being the share's end
  (`finishShare()` calls `uploadStatusBegin()`) or the first answer that said uploading; `hubReachable:
  false` adds `syncUploadWaitingHub`, a non-empty `lastError` adds `syncUploadProblem` (kind err, the
  error as text) and goes back when it clears; the poll runs every `SYNC_UPLOAD_TICK_MS` = 2 s
  (`setSyncTickMs()`) instead of 5 s. **Dossiary Sync leaves the `uploading` key out when it is false**
  (dossiary-sync `EditorControl.swift` encodes it only when true), so a missing key (or false) means not
  uploading: once this page saw `uploading: true` for the library (`seen`), such an answer with
  `version >= 1` → `syncUploadDone` (kind ok); without a version → back to 5 s and the line cleared if it
  is still ours. An older Dossiary Sync never sends the key: never seen true, nothing changes. Right after
  a share the first answers may not say uploading yet: for `SYNC_UPLOAD_SHARE_GRACE_MS` (30 s) the 2 s
  poll and the share's start are kept (a late `uploading: true` continues the elapsed time, a
  `version >= 1` meanwhile is the done line), then back to 5 s without a message
  (`__DEBUG_uploadShareFinished(agoMs)` lets tests start it). The line goes through `setStatusLive()`, so a language change
  retranslates it; the 1 s ticker (`uploadTick()`) changes only the text of `.sync-upload-elapsed`
  (spinner and title stay, so nothing flickers; `#status` is not a live region), and only while
  `lastStatusBuild` is still the upload line's builder: another message keeps the line until the next
  poll puts the upload line back. `stopSyncTimer()` (close, switch library, deleted or detached) and a
  lost admin token stop it. Error codes
  are mapped (already-shared, not-a-library, unknown-device, hub-*; a 404
  without a known code = an older Dossiary Sync); any other is shown with its
  code and status. `shareLibraryRunning` blocks closing while saving, copying
  or sharing. **Get it** (the
  devices dialog's list of hub libraries) left in 1.71.0 for Dossiary for
  Mac's Get from Hub…. Tested by `tests/test_share_library.py`; a
  directory handle's `_granted` in the stub makes `queryPermission()` answer
  granted.
- **The Dossiary Sync folder and cloud drives** (1.65.0; spec dossiary-sync
  `docs/superpowers/specs/2026-11-08-standard-libraries-folder-design.md`;
  `cloudProviderOf()`, `showNotSharedHint()`). Dossiary Sync 0.17.0 makes
  `~/Dossiary` the standard synced-libraries folder, marks it with
  `.dossiary-root.json` and refuses cloud drives for it. The devices dialog's
  folder line and cloud warning left in 1.71.0 (Dossiary for Mac shows the
  warning); what follows up to the 409 is history. The devices dialog's connected view asks `POST
  /admin/libraries-root/check` once (with a probe that doesn't exist, like the
  chooser's first call) and, from the new keys, shows "Dossiary Sync folder:
  {path}" (`path`, `~` abbreviated by the service) and, only while `cloud` is
  a string, an amber warning naming the provider with the move command
  (`SYNC_FOLDER_MOVE_COMMAND`) in its own `<code>` (`user-select: all`, so one
  click selects it to copy). Both values come from the service and are put in
  as escaped text: the translated template is split at `{path}`/`{provider}`
  and at the command instead of being filled by `t()` (whose `replaceAll`
  would also read `$` patterns in the value). An older service (no keys, or a
  404 without the route) adds nothing; the result lives in
  `devicesState.folder`, so a re-render kept it. A 409 `{"error":
  "cloud-drive", "provider"}` from share maps to
  `shareLibraryCloudRefused`; a copy the share flow
  made for that share is removed again (it could never be shared) instead of
  being kept for Try again. `removeOwnShareCopy()` removes it (and a partial
  copy after a failed or stopped copy) only when the folder of that name is
  still the very handle the flow created (`isSameEntry`) and has no sync file;
  a renamed, replaced or vanished folder is left alone. Only a removal that
  worked forgets `ctx.copy`; otherwise the copy-kept text shows and Try again
  shares that same copy, no second numbered copy. **"Not shared yet"**: after a library opens
  (`afterDbReady()`), when it has no sync file and is directly inside the
  stored libraries folder whose permission is still granted
  (`peekLibrariesRoot()`, no prompt; `isDirectlyIn()`) and that folder holds
  the marker, the status line gets "Not shared yet: Tools → Share this
  library…" appended (only while the opened line is still the status). The
  page never learns real paths, so this is the one reliable way to know a
  library sits in the Dossiary Sync folder; "not registered" means
  `!syncLibrary && !syncLibraryGone` after `readSyncFile()` (no usable
  `.dossiary-sync.json`, or one naming a library detached in this session),
  the same test that shows the Share item, with no admin call. Tested by `tests/test_libraries_folder.py`.
- **Saving in a synced library (no editing lease)** (historical context:
  dossiary-ios `docs/superpowers/specs/2026-10-22-pi-hub-lease-design.md` and
  `2026-10-23-offline-first-sync-design.md` describe the editing lease and the
  "Work disconnected" switch the page used to have; both are **superseded** by
  dossiary-osx `docs/superpowers/specs/2026-10-28-dossiary-html-hub-cut-design.md`.
  The page no longer takes, heartbeats or releases a lease, has no sync marker
  in the header, no take-over dialog and no held-back changes.)
  **Saves go straight to disk** (`persistDb()`), in a synced library or not.
  A library takes part in sync only if it has a readable `.dossiary-sync.json`
  (`{libraryId, hub, version}`) at its root; the page still keeps three things
  because Dossiary Sync (the Mac service) decides push/pull/keep-aside from them:
  - **`.dossiary-sync.json` is read** at open (before `library.sqlite`, since
    the service writes the database first, so the version read can only be older
    than the database) and again before every save (`syncFileVersion()`).
    A synced library is not written on open: migrations and view preferences
    stay in memory until the next real save (`SYNC_VIEW_PREF_KEYS`; with or
    without an admin token, a view preference alone is never written).
  - **`syncLibrary.base`** is the version memory is provably based on, and
    **`.dossiary-base.json`** (`writeSyncBaseMarker()`, `{version, sha256,
    writtenAt}`) is written after every write of `library.sqlite`, naming that
    base and the SHA-256 of the bytes. The service pushes a changed database
    only if the marker matches the bytes and its base is the folder's version or
    lies on this Mac's own-push chain; any other base (or no marker after 10 s)
    is kept aside on both sides and the hub's version pulled (`baseOfDatabaseChange`
    and `continuesOwnPushes` in dossiary-sync's `EditorLoop.swift`). The service
    keeps only its last own pushes (`ownPushesKept`: 1000 from dossiary-sync
    0.12.2, 20 before), so a base that never moved would make the 1001st push of
    a session (the 21st with an older service) a kept-aside version.
    Keep-aside copies never get a marker.
  - **The base follows this Mac's own pushes only when Dossiary Sync confirms
    them** (dossiary-osx `docs/superpowers/specs/2026-10-28-confirmed-push-base-design.md`).
    When a newer version turns out to be this tab's own bytes (`syncDiskIsOurs()`:
    library.sqlite hashes to the loaded or the last-written hash), `version` is
    taken over but `base` is not: the files cannot tell this Mac's push from a
    phone edit pulled just before the page's write landed on top of it. `base`
    moves only in `syncConfirmPush()`, from a state poll: when the answer's
    `lastPushedHash` (SHA-256 hex of the database the service last pushed or
    installed; dossiary-sync **>= 0.12.2**) is the hash of bytes this tab loaded
    (`syncLoadedHash`) or wrote since its last open, reload or keep-aside
    (`syncWrittenHashes`, the last 64; not only the last write, since saves can
    come faster than pushes), `base` (and `version`) become the answer's
    `version`. Why this is safe: the pair (version W, `lastPushedHash` h) is
    commit-verified by the hub (it refuses a commit whose bytes don't hash to the
    claimed `sqliteHash`, dossiary-sync `HubStore.swift` commit; a pull records
    the hash of the bytes it installs), so it always means "the hub's version W
    holds exactly the bytes h". Memory descends from every hash in the page's
    list, so with h in it all of W is in memory and nothing of W can be pushed
    over, whether W came from this Mac's push or from a pull (a pull can install
    bytes this tab once wrote, e.g. a re-pull of its own push; that is fine). A
    phone edit's bytes are not in the list, so it never confirms: **the old
    millisecond race of the evidence rule (`markerBefore`, sync-file reads around
    the write, `syncBaseMayFollow()`, all removed) is closed.** Until confirmed,
    `base` and every marker keep naming the last confirmed version, which the
    service accepts along its own-push chain (a second save before the poll is
    fine). **Fallback:** an answer without `lastPushedHash` (an older Dossiary
    Sync) or no token (no poll at all) leaves `base` at the loaded version (or
    the version a reload of foreign bytes set): safe, but the 1001st own push of
    a session is then kept aside and announced instead of pushed (nothing lost).
    That limit needs dossiary-sync >= 0.12.2; an older service keeps only 20 own
    pushes, so there it is the 21st.
    **The person must run Dossiary Sync 0.12.2 or newer** for the base to follow.
  **The guard stays**: `syncBehind()` (memory is based on an older version than
  the sync file's) with disk not this tab's (`!syncDiskIsOurs()`) means a save
  never overwrites the newer version: memory is kept aside in
  `<library>/.kept-aside/<device>-<time>/library.sqlite` and the newer version
  reloaded (`syncKeepAsideAndReload()`, with the `#sync-notice-dialog` notice for a
  person's change, a plain status line for a job's data alone). If the copy cannot
  be written, the change stays in memory (`syncDirty()` blocks reloads, the status
  line says so, `beforeunload` and **`switchLibraryAsking()`** ask first; its three
  call sites are the Switch library button, Export as library's "Open it" and Get
  it's "Open"). The device name comes from a state answer's `lease.holder: 'this'`,
  which the page's own saves no longer provoke, so folders are usually named
  **`this Mac-<time>`**. `.kept-aside/` is skipped by `listLibraryFiles()`, as are
  both bookkeeping files (Export as library writes neither). Dossiary Sync's own
  `keptAside` list does not know the page's copies.
  **`syncWroteSinceLoad`** (a real write since the last reload or keep-aside;
  formerly `syncWroteWithoutLease`) matters only **without an admin token**
  (`syncWriteUnreported()`): then nothing reports the service's own keep-aside of a
  write a pull raced with, so a newer version found after a save keeps memory aside
  with the notice instead of reloading it away. With a token the service's
  keep-aside shows up in the poll's `keptAside`, and a newer version after a save is
  an ordinary reload (otherwise every phone edit after a Mac save would leave a
  kept-aside copy). A token that is present but whose poll keeps failing (non-401)
  leaves the service's keep-aside unannounced (data safe, just silent).
  **Poll** (`pollSyncState()`, every 5 s via `syncTick()`, only with a token; `GET
  /admin/libraries/<id>/state`): 401 forgets the token; `deleted` (+ `trashed`)
  starts the deleted-elsewhere path (Delete library below); new `keptAside` entries
  (`noteKeptAside()`, remembered in localStorage under `KEPT_ASIDE_SEEN_KEY` so a
  reload doesn't repeat them) give one status line each and a reload;
  `lastPushedHash` goes to `syncConfirmPush()` (above); a higher `version` goes to
  `syncNoteNewer()` and `maybeReload()`. Nothing else is read.
  **Reload** (`maybeReload()` → `reloadLibraryKeepingView()`) when behind and
  nothing is in the way (no dialog, no save in flight, nothing dirty, no job);
  keeps view, search, filters, selection, scroll and view preferences. Flows call
  `ensureCurrentVersion()` first (formerly `ensureEditLease`, ~40 entry points): it
  reloads first, refuses under a dialog or keeps memory aside; it reads the sync
  file every time. Background jobs write files only when `syncMayWriteFiles()`
  (not behind) / `syncBackgroundMayWrite()` allow it; they need no token.
  Other invariants: nothing a person changed is dropped (written, in memory while
  dirty, or kept aside); real changes are counted (`trackDbChanges()`,
  `syncDirty()`), a reload never replaces them; new document ids skip ids on disk,
  in the database and in flight (`reserveDocId()`, `checkReservedDocId()`,
  `releaseDocId()`, `settleDocId()` in a `finally`).
  Test hooks: `__DEBUG_syncState()` (`version, base, reloads, dirty, flowPending,
  wroteSinceLoad, writtenHashes` -- the length of `syncWrittenHashes`), `__DEBUG_syncNow()` (runs the tick), `__DEBUG_persistDb(opts)`,
  `__DEBUG_ensureCurrentVersion()`, `__DEBUG_reserveDocId()` & co. Tested by
  `tests/test_no_lease.py`.
