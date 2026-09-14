# Scan / Scan Multi toolbar buttons, via a scanix500 HTTP bridge

## Context

Legacy Mariner Paperless's toolbar had two scan buttons — **Scan** (simplex,
single scan) and **Scan Multi** (duplex, continuous multi-page scan) — each
directly engaging the scanner. Dossiary currently has no equivalent: per
CLAUDE.md's "No direct scanner integration in the app itself" note, a
browser tab has no API to control scanner hardware, so the existing
scan-related UI is just a static OS-aware hint plus the Inbox/`scan_watch.py`
pipeline (a separate watched-folder helper that stages files for an
explicit "Check inbox" click).

Separately, the user has a side project,
[`scanix500`](https://github.com/AarneAarebye/iX500) — a vendor-independent
Python pipeline that drives this specific ScanSnap iX500 directly via SANE
(replacing Ricoh's ScanSnap Home, which no longer activates this unit). It
ships three pieces: the `scanix500` CLI (ADF duplex capture → blank-page
filtering → OCR → PDF, writing directly to a destination folder), a macOS
menu bar app (`scanix500-menubar`, one item per saved **profile** — a
name, destination folder, and flags — triggering `run_scan(profile)`), and
a physical-button trigger (pressing the scanner's own Scan button runs the
reserved "Hardware Button" profile). None of this is reachable from a
browser tab today — there is no HTTP API, only CLI/menu/hardware-button
entry points.

This spec adds two toolbar buttons to Dossiary — **Scan** and **Scan
Multi** — backed by a new, small HTTP bridge added to scanix500's existing
menu bar app, so clicking a button in Dossiary triggers a real scan on the
physical iX500 and the result lands in the library's Inbox automatically.

**Mapping note:** legacy Paperless's Scan/Scan Multi distinction was
simplex vs. duplex — but scanix500 has no simplex mode; its pipeline
always does ADF duplex capture with automatic blank-backside filtering, so
its ordinary scan already behaves like legacy Paperless's "Scan Multi." Per
the approved design decision, this spec repurposes "Scan Multi" for
scanix500's own genuinely distinct capability instead: `--split-on-blank`,
which splits one ADF load into several separate PDFs at blank separator
sheets, letting several physical documents be fed and captured in one
batch. **Scan** → a normal profile (one PDF per ADF load). **Scan Multi**
→ a profile with `--split-on-blank` enabled.

## Approach

### Two repos, one HTTP contract

This is a two-sided change spanning both repos, tied together by a small
fixed API:

- **scanix500** (`AarneAarebye/iX500`) gains an HTTP bridge, embedded in
  the existing `scanix500-menubar` process.
- **Dossiary** (`dossiary.html`) gains two toolbar buttons and a new
  per-library setting pointing at the bridge's URL.

### scanix500 side: embedded HTTP bridge

**Why embedded, not a standalone process:** `ScanixMenuBarApp` already has
an in-process `self._scanning` busy-guard preventing two trigger sources
(a menu click and a physical button press) from racing to open the same
USB device concurrently. A separate bridge process would either duplicate
that guard (risking drift) or bypass it (risking a real device conflict
between a Dossiary-triggered scan and a hardware-button press). Embedding
the bridge as one more thread inside the same process reuses the existing
guard, `self.profiles`, and `run_scan()` call verbatim — no new
scan-execution path.

New module `src/scanix500/menubar/bridge.py`:

- A `http.server.ThreadingHTTPServer` (stdlib — matches the project's
  existing dependency-conscious style; `http.server` needs no new
  dependency) bound to `127.0.0.1` only — never `0.0.0.0` — since this is
  a single-machine, single-user trust boundary, not a networked service.
- Started as a daemon thread from `ScanixMenuBarApp.__init__`, alongside
  the existing `self._button_timer` setup.
- Port defaults to `8765`, overridable via an environment variable
  (`SCANIX500_BRIDGE_PORT`) read at startup — no config file needed for
  this alone.
- `POST /scan/<profile-name>` (the name is the final URL path segment,
  percent-decoded): looks up the profile via the existing
  `find_profile(self.profiles, name)`. Responses:
  - `404` — no profile with that name exists.
  - `409` — a scan is already running (`self._scanning` is true); the
    request is rejected immediately, not queued or blocked.
  - `200` with a JSON body `{"ok": bool, "partial": bool, "message": str,
    "output_paths": [str, ...]}` — the handler calls the existing
    `run_scan(profile)` directly (it already runs synchronously via
    `subprocess.run`, so the HTTP handler thread blocking on it is exactly
    the existing behavior, just observed from a different caller) and
    serializes its `ScanResult` verbatim. `ok: false` here means the scan
    itself failed or partially failed — the HTTP layer still returns 200,
    since the *request* was handled correctly; only genuinely unexpected
    conditions (unknown profile, already busy) get a non-200 status.
  - The handler sets/clears `self._scanning` the same way `_start_scan()`
    does, and updates the menu bar icon/notification the same way a
    menu-triggered scan does — a Dossiary-triggered scan should look
    identical, from the menu bar's own perspective, to any other trigger.
- Every response — success or error — includes
  `Access-Control-Allow-Origin: *`, and `OPTIONS` requests get a handled
  no-op preflight response. Dossiary is served from `file://` or a
  `localhost` origin (see CLAUDE.md's own note on how this app is tested);
  either way its `fetch()` calls are cross-origin from the bridge's
  perspective and need this header to let the response body be read.
  **Accepted trust model, stated explicitly, not a gap to close later**:
  no authentication, no token, no origin allow-list narrower than `*` —
  this mirrors the existing physical-button trigger's own trust model
  (anyone with physical access to the machine can already trigger a scan
  via the menu or the button; a localhost-only HTTP endpoint with no auth
  is the same class of trust, not a materially larger exposure, for a
  single-user desktop tool with no other services expected to be running
  on this port).

### Dossiary side: two toolbar buttons + a bridge-URL setting

**New setting** — `scan_bridge_url` (a `settings` table row, loaded/saved
the same way `default_currency` is: `loadScanBridgeUrl()`/
`saveScanBridgeUrl()`), configured via a new text field in the Field
Settings modal (alongside `default_document_type`/`default_currency`/
`reminder_lookahead_days` — no other settings-modal infrastructure exists
in this app, so this follows the same established spot). Unset by default
(`null`) — an empty value means the feature isn't configured yet; clicking
either button then shows a clear "Configure the scanner bridge URL in
Field Settings first" status message rather than attempting a request to
nothing. When set, it's the bridge's base URL exactly as scanix500 prints
it at startup (e.g. `http://127.0.0.1:8765`) — no trailing slash assumed
or stripped implicitly; the code appends `/scan/<profile>` directly to
whatever's stored, so a trailing slash left by the person produces a
double slash. This is accepted as a minor, self-correcting rough edge (a
malformed URL fails visibly via the existing network-error handling below,
not silently) rather than adding trimming logic for a single hand-typed
setting.

**Two new toolbar buttons**, placed next to the existing `#inbox-check-btn`/
`#check-reminders-btn` pair (same family: bringing new documents into the
library) — `#scan-btn` ("📷 Scan") and `#scan-multi-btn` ("📸 Scan Multi").
Both call a shared `triggerScan(profileName)`:

1. If `scanBridgeUrl` is unset, show the "not configured" status
   immediately and return — no network call attempted.
2. Disable both scan buttons (prevents a double-click starting a second
   request while one is in flight — the bridge's own 409 already guards
   the scanner itself, but a disabled button avoids a confusing "scan
   already running" error from a person's own double-click) and set a
   "Scanning…" status line, mirroring the existing Check Inbox status
   pattern.
3. `fetch(`${scanBridgeUrl}/scan/${encodeURIComponent(profileName)}`,
   {method: 'POST'})`.
4. On a resolved response with `ok: true` (bridge JSON, not the Fetch
   `Response.ok`) — re-enable both buttons, then run the existing
   `checkInbox()` + `addAllInboxFilesAndShowStatus()` pair verbatim (the
   same call the Check Inbox button already makes), which reports what
   actually landed in the library and jumps to the 🚩 Inbox view. The
   bridge's own `message`/`output_paths` are not separately surfaced —
   the Inbox-add flow's own report is the authoritative "what happened to
   your library" statement, and duplicating both would be redundant/
   possibly inconsistent.
5. On a resolved response with `ok: false` but `partial: true` (a
   multi-feed jam that still produced a partial PDF, per scanix500's own
   `ScanResult` semantics) — re-enable both buttons, then still run the
   Check Inbox pipeline (a partial file was written and is worth pulling
   in), and additionally show the bridge's own `message` so the person
   knows the scan was incomplete.
6. On a resolved response with `ok: false` and `partial: false` (a hard
   scan failure) — re-enable both buttons, show the bridge's own
   `message` as an error status. No Check Inbox call — nothing new was
   written.
7. On HTTP 404 (unknown profile) or 409 (already scanning), or any
   network failure (bridge unreachable — most commonly
   `scanix500-menubar` isn't running) — re-enable both buttons, show a
   clear status naming the likely cause (404: "profile not configured in
   scanix500 — create it in the menu bar app"; 409: "a scan is already in
   progress"; network error: "couldn't reach the scanner bridge at
   `<url>` — is scanix500-menubar running?").

**Fixed profile names**, not user-configurable: `"Dossiary Scan"` and
`"Dossiary Scan Multi"`. The person creates these two profiles once,
manually, via the menu bar app's existing Add Profile flow — Multi with
`split-on-blank` enabled, both with their destination set to the actual
library's real `inbox/` folder path (a real filesystem path, which the
native menu bar app has direct access to, unlike Dossiary's own browser
JS — see the design-discussion note on why this reuses scanix500's
existing profile system rather than Dossiary trying to communicate a path
itself). This is a one-time manual setup step, documented in both repos,
not automated by either app.

### i18n

Every new user-facing string needs all six `STRINGS` blocks (`en`, `de`,
`es`, `fr`, `zh-Hans`, `zh-Hant`), per this app's established convention —
`zh-Hant` derived from the finished `zh-Hans` wording via a real OpenCC
`s2t` run, never hand-guessed. New keys needed: the two toolbar button
labels, the Field Settings label for the bridge URL, the "not configured"
status message, the "Scanning…" status message, and the four
failure-status messages (unreachable, unknown profile, already scanning,
hard failure — the partial-scan message reuses the bridge's own raw
`message` string interpolated into a translated wrapper, the same pattern
`reminderDueLabel`-style messages already use elsewhere for combining a
translated template with dynamic content).

## Explicitly out of scope

- No automatic creation of the two scanix500 profiles from Dossiary —
  profile management stays entirely inside the menu bar app's own existing
  UI; this spec doesn't touch `profiles.py`'s CRUD functions at all.
- No authentication/token/origin allow-list on the bridge beyond binding
  to `127.0.0.1` — see the accepted trust-model note above.
- No support for running the bridge on a different machine than
  Dossiary's browser — `scan_bridge_url` is a plain text field for
  flexibility (e.g. a non-default port), not a statement that a remote
  bridge is a supported configuration; CORS/trust assumptions above are
  specifically a same-machine model.
- No new simplex-scan capability invented in scanix500 to more literally
  match legacy Paperless's original Scan/Scan Multi meaning — see the
  Mapping note above; this spec repurposes the two-button UI for
  scanix500's real capability instead.
- No change to the existing Inbox/`scan_watch.py` pipeline itself — this
  spec adds a new way to get a file into `inbox/` (a direct scanix500
  write, same as a manual drag-in), not a new consumer of it; `checkInbox()`/
  `addAllInboxFilesAndShowStatus()` are called, not modified.
- No progress/percentage UI during a scan — only a static "Scanning…"
  status, matching the existing Check Inbox pattern; scanix500's own
  `ScanResult` carries no incremental progress data to show even if this
  were built.

## Critical files

**scanix500 (`AarneAarebye/iX500`):**
- New `src/scanix500/menubar/bridge.py` — the `ThreadingHTTPServer`,
  request routing, and JSON response shaping.
- `src/scanix500/menubar/app.py` — `ScanixMenuBarApp.__init__` starts the
  bridge thread; the bridge's scan-trigger path must go through the same
  `_scanning` guard/notification logic `_start_scan()`/`_run_scan_thread()`/
  `_on_scan_complete()` already use, not a parallel copy.
- New `tests/menubar/test_bridge.py` — request-handling logic (profile
  lookup, busy-guard, JSON shaping), mocking `run_scan` the same way
  `tests/menubar/test_runner.py` already covers `run_scan`'s own internals;
  a real `ThreadingHTTPServer` + `urllib.request` round-trip test for the
  wiring itself.
- `README.md`/`CLAUDE.md` — document the bridge, its port/env var, the
  manual one-time "Dossiary Scan"/"Dossiary Scan Multi" profile setup, and
  the accepted trust model.

**Dossiary:**
- `dossiary.html`:
  - New `settings` row `scan_bridge_url` — `loadScanBridgeUrl()`/
    `saveScanBridgeUrl()`, same pattern as `loadDefaultCurrency()`/
    `saveDefaultCurrency()`.
  - Field Settings modal — a new labeled text input for the bridge URL.
  - Toolbar — two new buttons (`#scan-btn`, `#scan-multi-btn`) next to
    `#inbox-check-btn`/`#check-reminders-btn`.
  - New shared `triggerScan(profileName)` function and its two click
    handlers.
  - New i18n keys across all six `STRINGS` blocks (see i18n section
    above).
  - `.table-wrap`'s sticky-header `max-height` calibration (see CLAUDE.md's
    own architecture note) will likely need its now-familiar recalibration
    bump — two more toolbar buttons is exactly the class of change that's
    broken this before (the reminders feature's own "🔔 Check reminders"
    button did the same). Re-verify empirically per that note's own
    methodology, don't assume the existing constants still hold.
- `CLAUDE.md` — a new architecture note describing the Scan/Scan Multi
  buttons, the bridge contract, the fixed profile names, and the one-time
  manual setup step (mirroring the Inbox/`scan_watch.py` note's own
  level of detail).
- New `tests/test_scan_bridge.py` — extends `tests/stub_studio2.js` (or a
  small dedicated stub) to intercept `fetch()` calls to the configured
  bridge URL and return canned responses, covering the scenarios in
  Testing below.

## Testing

**scanix500** (`tests/menubar/test_bridge.py`):
- `POST /scan/<known-profile>` with `run_scan` mocked to return a
  successful `ScanResult` → response is `200` with the exact JSON shape,
  and the mock was called with the correct `Profile`.
- `POST /scan/<unknown-profile>` → `404`, `run_scan` never called.
- `POST /scan/<known-profile>` while `_scanning` is already true → `409`,
  `run_scan` never called.
- A failed/partial `ScanResult` (`ok: false`, `partial: true`) → still
  `200`, with `ok`/`partial`/`message`/`output_paths` reflected exactly.
- Every response (including error responses) carries
  `Access-Control-Allow-Origin: *`; an `OPTIONS` preflight gets a handled
  response, not a 404/501.
- The busy-guard is shared: after a bridge-triggered scan starts (mocked
  to not return immediately), a concurrent menu-triggered
  `_start_scan()` call is also blocked, and vice versa — proves the two
  trigger paths share one guard, not two independent ones.

**Dossiary** (`tests/test_scan_bridge.py`):
- `scan_bridge_url` unset → clicking Scan/Scan Multi shows the
  "not configured" status immediately, with no `fetch()` attempted.
- A successful bridge response (`ok: true`) → status shows "Scanning…"
  while in flight, then the Check Inbox pipeline's own success message,
  and the view navigates to 🚩 Inbox — confirmed via the same
  `read_db()`/DOM-assertion pattern other Inbox-add tests already use.
- A partial response (`ok: false, partial: true`) → the bridge's own
  message is shown AND the Check Inbox pipeline still runs (the partial
  file is picked up).
- A hard-failure response (`ok: false, partial: false`) → the bridge's
  own message is shown as an error status, and Check Inbox is NOT
  triggered (confirm no new document was added).
- A simulated network failure (fetch rejects) → the "couldn't reach the
  scanner bridge" status is shown, naming the configured URL.
- A simulated 404 → the "profile not configured" status is shown.
- A simulated 409 → the "already scanning" status is shown.
- Both buttons are disabled while a request is in flight and re-enabled
  afterward in every one of the above outcomes (including failure paths —
  a stuck-disabled button after an error would be a real regression).
- Clicking Scan Multi triggers a request to the `"Dossiary Scan Multi"`
  profile path specifically (not the same URL as Scan) — confirmed via
  the intercepted request's own URL/path.
