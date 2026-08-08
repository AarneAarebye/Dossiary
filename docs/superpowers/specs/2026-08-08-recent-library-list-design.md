# Recent library list — design

Date: 2026-08-08
Status: approved, ready for implementation plan

## Problem

`openLibrary()` (`dossiary.html:764`) always calls `showDirectoryPicker()`
fresh — there is no memory of previously opened libraries. `CLAUDE.md` and
`README.md` both currently document this as a deliberate, unavoidable
limitation ("Browsers don't allow persisting direct file-system access
across page reloads... not something to silently work around with
localStorage/indexedDB").

That claim overstates the platform limitation. The File System Access API
allows a `FileSystemDirectoryHandle` itself to be stored in IndexedDB
(handles are structured-cloneable) and later re-authorized via
`handle.queryPermission()` / `handle.requestPermission()` — a single click,
no OS folder dialog. Apps like Excalidraw and VS Code for the Web use this
pattern for "recent files." This design reverses the prior documented
stance and adds a real one-click "recent libraries" list, storing FSA's own
handle object (not a workaround around FSA — a use of it).

## Goals

- On the empty-state screen, show up to 5 previously opened libraries.
- Clicking one re-authorizes access with a single click and proceeds
  straight into the normal open flow — no folder picker dialog needed
  unless permission was fully revoked at the OS/browser level.
- On by default (matches Finder/Explorer "Recent Files" / VS Code "Recent
  Projects" conventions) — no extra confirmation step in the open flow.
- A person can remove an entry manually (✕), which is the only way an
  entry disappears short of the 5-entry cap evicting it.
- No new dependency, no build step — plain `indexedDB`, consistent with
  this app's single-file/no-third-party-install rule.

## Non-goals

- No "don't remember this library" opt-out checkbox in the open flow.
- No attempt to detect/warn about a shared-computer scenario beyond
  documenting that removal (✕) is the mitigation.
- No change to how the *actual* library-loading logic
  (`library.sqlite` detection, `loadDb()`, `initNewLibrary()`) behaves —
  only how `rootDirHandle` gets acquired before that logic runs.

## Data model

New IndexedDB database `dossiary-app-db` (version 1), object store
`recentLibraries`, `keyPath: 'id'`, `autoIncrement: true`. Each record:

```js
{
  id: <auto>,
  name: <string>,          // handle.name at the time it was recorded
  handle: <FileSystemDirectoryHandle>,
  lastOpenedAt: <ISO 8601 string>
}
```

No index needed — the store never holds more than 5 records, so reading
all of them and sorting in JS (`lastOpenedAt` descending) is simpler than
maintaining an index.

A small helper module inside `dossiary.html` wraps the raw IndexedDB calls
(`openRecentLibrariesDb()`, `getRecentLibraries()`,
`recordRecentLibrary(handle)`, `removeRecentLibrary(id)`) — no external
IndexedDB wrapper library; native `indexedDB.open()`/`transaction()`/
request-based API only.

## Control flow

**Recording an entry.** `afterDbReady()` is the single point both
`loadDb()` (existing library) and `initNewLibrary()` (brand new library)
already funnel through — one new call there,
`recordRecentLibrary(rootDirHandle)`:

1. Load all existing entries.
2. For each, call `await existing.handle.isSameEntry(rootDirHandle)` to
   find a match by actual folder identity (not by name — names can
   collide across different folders, or the same folder can be renamed
   between sessions).
3. If a match is found, update that record's `lastOpenedAt` and `name`
   (in case it was renamed) in place.
4. If no match, insert a new record.
5. If the store now holds more than 5 records, delete the one(s) with the
   oldest `lastOpenedAt` until exactly 5 remain.

**Refactor: `proceedWithRootDirHandle(handle)`.** The current body of
`openLibrary()` after `rootDirHandle = await showDirectoryPicker(...)` —
checking for `library.sqlite`, setting `filesDirHandle`, ensuring
`inbox/` exists, calling `loadDb()` or falling into the init-state
screen — is extracted into this shared helper, taking an already-granted
handle. `openLibrary()` becomes: acquire `rootDirHandle` via
`showDirectoryPicker()`, then call `proceedWithRootDirHandle(rootDirHandle)`.
The new reconnect path (below) calls the same helper after acquiring its
handle a different way, so there is exactly one place that knows what
"given a folder handle, open it" means.

**Reconnecting from the list.** On page load (before any library is
open), `renderRecentLibraries()` reads all stored entries, sorts by
`lastOpenedAt` descending, and renders rows into `#recent-libraries`
inside `#empty-state`. Clicking a row:

1. `await handle.queryPermission({mode: 'readwrite'})`.
2. If not `'granted'`, `await handle.requestPermission({mode: 'readwrite'})`
   — this is fired synchronously from within the click handler so it
   still counts as a user gesture.
3. If the result is `'granted'`, call `proceedWithRootDirHandle(handle)`.
4. Otherwise (denied, or the call throws — e.g. `NotFoundError` if the
   folder was moved or deleted), show an inline error on that row and
   leave the entry in the list untouched.

## UI

`#recent-libraries` sits inside `#empty-state`, above the existing "Open
library folder" button. Hidden (or simply empty) on first run — no layout
change for someone who has never opened a library before. Each row reuses
the existing `.review-queue-row` list-row styling (name + a small
`.doc-sub`-style secondary line) with:

- The folder name (`handle.name`).
- A relative "last opened" date via the existing `formatDate()` helper.
- A small ✕ remove button, same visual pattern as other list-item removal
  affordances in this app (e.g. `wireClearButton`-adjacent `.clear-btn`
  styling), calling `removeRecentLibrary(id)` and re-rendering the list.
- On error (see above), an inline message under the row: "Couldn't
  reopen — folder may have moved or access was denied."

## Error handling

| Situation | Behavior |
|---|---|
| Permission still granted from a prior session | No prompt shown at all — straight into `proceedWithRootDirHandle()`. |
| Permission needs re-granting, user allows | Same as above, one click. |
| Permission denied (user declines the browser prompt) | Inline error on the row; entry stays in the list. |
| Folder moved/deleted (`NotFoundError` or similar) | Same inline error; entry stays in the list. |
| Folder still exists but no longer has `library.sqlite` | Falls into the existing `#init-state` "no library.sqlite found" screen, same as the fresh-picker path today — not treated as an error. |

Nothing is ever auto-removed from the list. The only removal path is the
row's own ✕ button, or natural eviction once a 6th distinct library is
opened.

## Docs to update

- `CLAUDE.md`: replace the "No persistence of the folder handle across
  page reloads" architecture note with one describing this feature — the
  IndexedDB-handle approach, why it's on by default, the `isSameEntry`
  dedup, the 5-entry cap, and why this isn't the "browser storage beyond
  what FSA itself provides" the old note ruled out (it persists FSA's own
  handle object, not a workaround around FSA).
- `README.md` / `README.de.md`: replace the "Re-select the folder each
  session" known-limitation bullet with a "Recent libraries" Features
  bullet, including a one-line note that removing an entry (✕) is how to
  stop a library being reachable with one click on a shared computer.
- `CONTRIBUTING.md`: no changes expected (no new CLI flags, no schema
  change to `library.sqlite` itself — this is browser-side state only).

## Testing

New `tests/test_recent_libraries.py`, following this suite's existing
Playwright-driven, stub-based conventions. `tests/stub_studio2.js`'s fake
`FileSystemDirectoryHandle` needs three additions it doesn't currently
have: `isSameEntry(other)`, `queryPermission(descriptor)`, and
`requestPermission(descriptor)` (returning `'granted'` by default, with a
way for a specific test to force `'denied'`/a thrown error). Real
`indexedDB` is available natively in Playwright's Chromium — unlike
`showDirectoryPicker`, it does not need to be stubbed.

Scenarios to cover:

- First run: `#recent-libraries` is empty/hidden.
- Opening (or initializing) a library adds it to the list.
- Reopening the same folder again does not create a duplicate row —
  `lastOpenedAt` updates and it sorts to the top.
- Clicking a recent-library row reconnects without a folder-picker call,
  loading straight into the library.
- A 6th distinct library evicts the oldest of the prior 5.
- Manual removal (✕) removes only that entry.
- A denied/failed reconnect shows the inline error and leaves the entry
  in place (does not remove it).

## Open risks / things to verify during implementation

- Confirm real Chrome/Edge behavior for `queryPermission()` on a handle
  restored from IndexedDB after a full browser restart (not just a page
  reload) — Chromium's own persisted-permission behavior here has shifted
  across versions historically; a manual real-browser check after
  implementation is warranted, same as this codebase's existing practice
  for anything the stub-based suite can't fully validate (e.g. the
  searchable-PDF text-layer rendering).
