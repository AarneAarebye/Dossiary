# Spinner for the library-loading status line

## Context

Opening a library on a cloud-synced drive (iCloud Drive, Dropbox, etc.)
can take several seconds — reported up to ~10 seconds — while the folder
handle is checked, the SQLite engine loads, and `library.sqlite` itself is
read. During that whole window, the only feedback is the status line's
plain text changing between five messages (`openLibrary()`,
`proceedWithRootDirHandle()`, `initNewLibrary()`, `loadDb()` in
`dossiary.html`): "Opening folder picker…", "Checking for
library.sqlite…", "Setting up SQLite engine…", "Loading SQLite engine…",
"Reading library.sqlite…". This app already has an established small
spinner (`.spinner`, amber, used for OCR, saving, and thumbnail
regeneration) for exactly this "an operation is in progress" signal, but
it isn't used anywhere in this load sequence.

## Approach

### Teach the shared status setter a `'busy'` kind, rather than a sixth ad-hoc spinner

Every other spinner in this app (edit-save, OCR, thumbnail regenerate) is
wired ad-hoc, directly setting its own panel-local status element's
`innerHTML`. The library-loading status line is different: it's the one
place in the app where status is set through a single shared pair of
functions, `setStatus(msg, kind)`/`setStatusT(key, params, kind)`
(`dossiary.html` ~lines 2241-2242), which today only ever write plain
`textContent`. Rather than adding a sixth independent ad-hoc spinner
call site, `setStatus()` gets one new branch: when `kind === 'busy'`, it
renders `<span class="spinner"></span> ` plus the message — HTML-escaped
via the existing `escapeHtml()` helper, since `setStatus()`'s `msg`
argument isn't guaranteed free of `<`/`&` (e.g. `statusCouldNotOpenFolder`
interpolates a native `Error.message` into its text) — through
`innerHTML` instead of `textContent`. Every other `kind` (`null`, `'ok'`,
`'err'`) is completely unchanged.

This also comes with a real correctness benefit for free: `setLang()`
already re-renders whatever status message is currently showing when the
UI language is toggled, by replaying `setStatusT(lastStatusKey,
lastStatusParams, lastStatusKind)` (`dossiary.html` ~line 1992) — since
`lastStatusKind` is already tracked and replayed through this same
function, toggling the language mid-load will correctly keep the spinner
showing in the newly-selected language, with no changes needed to that
replay logic at all.

### The five call sites that flip to `'busy'`

Each of the five "in progress" messages in `openLibrary()`,
`proceedWithRootDirHandle()`, `initNewLibrary()`, and `loadDb()` changes
its `setStatusT(key, params, kind)` call's `kind` argument from absent/
`null` to `'busy'`: "Opening folder picker…", "Checking for
library.sqlite…", "Setting up SQLite engine…", "Loading SQLite engine…",
"Reading library.sqlite…" — applied uniformly to every step in the
sequence, including the folder-picker step itself, rather than only the
steps known to be slow on a cloud drive, since that's simpler to reason
about than special-casing which steps get the treatment. The two
already-*finished* messages this sequence can end on — "Initialized a new
empty library." and "Opened library — N documents" — keep their existing
`'ok'` kind unchanged: no spinner once the operation is actually done.

No new CSS, no new visual language: this reuses the exact `.spinner`/
`.status.busy` styling already defined and already visually established
elsewhere in the app.

## Out of scope

- Any change to the ad-hoc spinner wiring already used elsewhere (edit
  save, OCR, thumbnail regenerate) — those stay exactly as they are.
- A bigger/more prominent loading treatment (full-screen dimming, a
  centered overlay, etc.) — explicitly ruled out in favor of the small
  in-place indicator.
- Any attempt at a determinate progress bar — none of these steps expose
  meaningful progress (`file.arrayBuffer()` has no byte-level progress
  event), so this stays an indeterminate spinner, consistent with every
  other spinner in the app.
- Any change to how long loading actually takes — this is purely a
  feedback/perception fix, not a performance optimization.

## Critical files

- `dossiary.html`:
  - `setStatus(msg, kind)` (~line 2241) — the one code change: a new
    `kind === 'busy'` branch rendering the spinner + escaped message via
    `innerHTML`.
  - `openLibrary()` (~line 2766), `proceedWithRootDirHandle()` (~line
    2781), `initNewLibrary()` (~line 2797), `loadDb()` (~lines 2819,
    2821) — five `setStatusT(...)` call sites, each gaining a `'busy'`
    third argument.

## Testing

- Opening a library (both the fresh-init and existing-library paths)
  shows the spinner alongside each of the five in-progress messages in
  turn, and the spinner is gone once the final "Initialized a new empty
  library."/"Opened library — N documents" message shows.
- Toggling the UI language while one of the five busy messages is showing
  re-renders it in the new language with the spinner still present (not
  silently dropped).
- A message using `kind='busy'` that happens to contain HTML-special
  characters renders as literal text, not interpreted as markup —
  confirms the `escapeHtml()` call is actually wired in, not skipped.
- Every other existing status message (`'ok'`, `'err'`, no kind) is
  visually unchanged — no spinner, plain text, matching current
  screenshots/behavior exactly.
