# Dossiary architecture notes: Dossiary Sync: devices dialog, delete library, share library, saving without a lease

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

- **iPhone & other devices** (`openDevicesDialog()`, `syncAdminFetch()`,
  Tools → `#devices-btn`, and `#empty-devices-btn` on the start screen,
  since it needs no open library; spec in dossiary-ios
  `docs/superpowers/specs/2026-10-22-dossiary-devices-dialog-design.md`)
  manages Dossiary Sync's paired devices through its loopback-only admin
  API on `http://127.0.0.1:8769` (3 s health timeout, 15 s for every other
  call, so a hung service never leaves a button disabled). Not answering → an
  explanation and the dossiary-sync link; otherwise Connect asks the service
  to show a code as a macOS notification (a 429 names the wait) and swaps
  the typed code for an admin token, kept per browser in `localStorage`
  (`dossiary_sync_admin_token`, every access in try/catch; when
  `localStorage` refuses to store it, the in-memory copy is used for the
  rest of the session). **Every POST carries `Content-Type:
  application/json` and a JSON body** (`{}` when there's nothing to say):
  the service answers 415 otherwise, and the fake in the tests does the
  same, so a missing header fails the suite. A token the service no longer
  knows (`connected: false`, or a 401) is dropped and Connect comes back.
  Connected: devices with role labels (phone/mirror/restore), relative
  last-seen (`Intl.RelativeTimeFormat`), one checkbox per shared library
  for phones (allow/deny at once, status line, a refusal undoes the tick),
  Remove behind `confirm()`, a ✎ next to each name (`startDeviceRename()`, `POST
  /admin/devices/<id>/name {name}`: inline input, Enter/blur saves, Escape
  cancels with `stopPropagation()`, unchanged/empty sends nothing, a failure
  keeps the input open with `.devices-rename-error`), shared libraries read-only with a
  note pointing at Tools › "Share this library…" (`#devices-share-note`), Disconnect. An answer in the wrong
  shape says so (`devicesUnexpectedAnswer`), and when libraries and devices
  are fetched together the error shown is the one that actually failed.
  **"Add iPhone or iPad…"** (`#devices-add-slot`, `renderDevicesAddSlot()`,
  `requestPairCode()`, state in `devicesPair`, which survives a re-render of
  the list such as Remove): library checkboxes, none ticked, and "Show QR
  code" disabled until one is; `POST /admin/pair-code {libraries}` →
  `{code, expires, fingerprint, addresses, link}`. The QR code of `link`
  (`dossiary-sync://pair?v=1&f=…&c=…&a=…`) is drawn locally as an SVG
  (`qrSvgMarkup()`, one `<path>`, black on white with a 4-module quiet zone
  whatever the theme) by **qrcode-generator 1.4.4** (Kazuhiko Arase, MIT,
  checked against its repo's LICENSE), loaded from cdnjs on demand by
  `ensureQrCode()` like pdf-lib (skipped when `window.qrcode` already
  exists, which is how the tests' fake takes over) and listed in
  `OPEN_SOURCE_LIBRARIES`; nothing is sent anywhere. Beside it: the
  instructions, a "Valid for m:ss" countdown (`devicesPairTimer`, stopped
  when the dialog closes or the section re-renders), the code (grouped
  `XXXX XXXX`) and fingerprint as text. Expired → the QR is cleared and
  "New code" asks again; Done folds the section and reloads the devices so
  the new phone shows. Closing the dialog doesn't cancel the code (it
  expires on its own; a new one replaces it on the service). A QR library
  that can't load still shows code and fingerprint, with a note. A 401
  anywhere drops the token. `devicesDialogSeq` drops answers for a dialog
  that was closed or reopened meanwhile. Every service-supplied string
  (device, library, code, fingerprint) is escaped; tests feed `<img
  onerror>` names. Tested by `tests/test_devices_dialog.py` (a fake `fetch`
  per scenario plus a fake `window.qrcode`; the shared stub blocks the real
  service, and the cdnjs QR request is aborted). The real library was
  checked once by rendering a link and decoding the screenshot with
  OpenCV.
- **Delete library** (`openDeleteLibraryDialog(handle, {open})`, Tools →
  `#delete-library-btn`, and the 🗑 `.recent-delete-btn` on each Recent
  libraries row, which asks for read permission on the stored handle first,
  like reconnect; spec in dossiary-ios
  `docs/superpowers/specs/2026-10-25-delete-library-design.md`). The dialog
  reads `.dossiary-sync.json` (`readSyncLibraryIdOf()`; the open library's
  `syncLibrary` when it's the one being deleted). **Synced**: needs an admin
  token (without one it says to connect in iPhone & other devices… and
  offers that button); the library's name ("Household" for
  `Household.dossiary`, `libraryDisplayName()`; the folder name works too)
  must be typed to enable Delete; a `GET …/state` first, and the service
  answering `lease.holder: 'other'` (another device is editing) turns the button
  into "Take over and delete" (`takeOver: true`; the page never takes a lease
  itself, the service's delete does the taking over). On click the open library is closed first --
  anything memory holds that isn't on disk is written to `.kept-aside/`
  inside the folder (`keepAsideBeforeClosing()`; if that copy can't be
  written, nothing is closed or sent and the dialog shows why), then
  `resetAll()` -- then `POST /admin/libraries/<id>/delete {takeOver}`; the
  page takes no lease before it and releases none after. When the delete then
  fails the error adds "… was closed but not deleted" (`deleteLibraryClosedNotDeleted`);
  the Recent entry stays. 200 `deleted` (with `trashed`
  true or false) and 404 `unknown-library` (already gone) forget the Recent
  entry (`forgetRecentLibrary()`, by `isSameEntry()`) and show the outcome in
  the dialog and on the status line; 409 offers take over; 501 (hub too
  old), 503, 502, a 404 without `unknown-library` (this Mac's dossiary-sync
  too old) and no answer keep the dialog open with the reason; a 401 drops
  the token. `deleteLibraryRunning` blocks closing while the request runs.
  **Unsynced**: "Close and forget" without typing and without any admin
  call -- the browser never erases a folder (it can't move one to the
  Trash), so the result names the folder to trash in Finder. **Deleted
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
  this session stays local and the Delete dialog takes the unsynced path,
  the Recent entry stays, the sync file is left alone (it may be shared
  again), and the status line says `syncLibraryDetachedLocal`. Closing every dialog loses text typed into an open form (memory's
  changes are kept aside), and a running dialog's job finds its library gone. Every name in the dialog is escaped. Tested by
  `tests/test_delete_library.py`.
- **Share this library and Get it** (`openShareLibraryDialog()`,
  `ensureLibrariesRootHandle()`, `copyLibraryInto()`, `loadDevicesAvailable()`,
  `getLibraryHere()`; Tools → `#share-library-btn`, shown only for an open
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
  (the devices dialog); otherwise a name (the folder name without
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
  (`{libraryId, root, since, hubDown, error, build, ticker}`). `uploading: true` → the status line
  "Uploading to the Pi… m:ss" (`syncUploadingLine`, kind busy, spinner), `since` being the share's end
  (`finishShare()` calls `uploadStatusBegin()`) or the first answer that said uploading; `hubReachable:
  false` adds `syncUploadWaitingHub`, a non-empty `lastError` adds `syncUploadProblem` (kind err, the
  error as text) and goes back when it clears; the poll runs every `SYNC_UPLOAD_TICK_MS` = 2 s
  (`setSyncTickMs()`) instead of 5 s. `uploading: false` with `version >= 1` → `syncUploadDone` (kind
  ok); false without a version, or no boolean `uploading` (an older Dossiary Sync) → back to 5 s and the
  line cleared if it is still ours. The line goes through `setStatusLive()`, so a language change
  retranslates it; the 1 s ticker (`uploadTick()`) changes only the text of `.sync-upload-elapsed`
  (spinner and title stay, so nothing flickers; `#status` is not a live region), and only while
  `lastStatusBuild` is still the upload line's builder: another message keeps the line until the next
  poll puts the upload line back. `stopSyncTimer()` (close, switch library, deleted or detached) and a
  lost admin token stop it. Error codes
  are mapped (already-shared, not-a-library, unknown-device, hub-*; a 404
  without a known code = an older Dossiary Sync); any other is shown with its
  code and status. `shareLibraryRunning` blocks closing while saving, copying
  or sharing. **Get it**: the devices dialog's `#devices-available-slot` lists
  `GET /admin/libraries/available` under "On the Pi, not on this Mac"
  (hidden when empty or not OK -- an older service's 404, an origin Mac's
  `[]`); "Get it" is disabled with "being uploaded" while `available` is
  false; a click makes sure of the libraries folder (the chooser opens under
  the row), then `POST …/<id>/get {}` with no timeout (`syncAdminFetch(...,
  {noTimeout: true})`) shows "Downloading…", and success offers "Open", which
  opens the last path component of `folder` inside the libraries folder
  (`switchLibraryAsking()` + `proceedWithRootDirHandle()`; Recent records it).
  After a successful Get the libraries are fetched again, so the new one
  shows under Libraries and in the phones' checkboxes at once. Errors show
  under the row. A re-render drops a chooser still open under a row and
  frees that row's button (each attempt is an object in `gets`; one no
  longer there is ignored when it resumes). Tested by `tests/test_share_library.py`; a
  directory handle's `_granted` in the stub makes `queryPermission()` answer
  granted.
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
