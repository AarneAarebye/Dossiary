# System scanner helper — design

Date: 2026-10-09
Status: approved in brainstorming, awaiting spec review

## Goal

Let people without an iX500 scan from Dossiary with whatever scanner their
macOS or Windows computer already supports, using the system's standard
scanner interface (ImageCaptureCore on macOS, WIA on Windows). A browser
can't reach a scanner, so a small helper app — a new GitHub project,
`dossiary-scan-helper` — does the scanning and talks to Dossiary over a
local HTTP bridge, the way scanix500 already does for the iX500.

Decisions taken in brainstorming:

- Audience: other Dossiary users, on macOS and Windows, with any scanner.
- A one-click helper app per system, in a separate repo
  (`~/Projects/Paperless/dossiary-scan-helper`, GitHub
  `AarneAarebye/dossiary-scan-helper`, MIT).
- Scan settings are chosen in a dialog inside Dossiary; the helper scans
  without showing a window of its own.
- One protocol for both helpers: scanix500 and the new helper both speak
  it, and Dossiary shows all their scanners in one dialog. The iX500's own
  abilities (split on blank pages, skip blank pages) stay available.
- Two small native apps (Swift on macOS, C#/.NET on Windows) sharing one
  written protocol and one conformance test suite.
- Unsigned first releases, with install notes explaining the system
  warning; signing comes later without design changes.

## 1. Bridge protocol, version 2

Version 1 is today's scanix500 protocol: `GET /health`, then a scan request
with `skip_blank_filter`, `skip_ocr` and `split_on_blank` query parameters,
answered with `{ok, partial, message, files: [{name, data(base64)}]}`.
Version 2 adds scanner discovery and generic settings. It is written up as
`PROTOCOL.md` in the new repo, generated from this section.

### `GET /health`

```json
{ "ok": true, "helper": "dossiary-scan-helper-macos", "version": "1.0.0", "protocol": 2, "paired": false }
```

A response without `protocol` is a version 1 helper. `paired` says
whether the request's `Authorization` token is valid (see Security).

### `GET /scanners`

```json
{ "scanners": [
  { "id": "ic:HP-ENVY-6000", "name": "HP ENVY 6000 (network)",
    "sources": ["flatbed", "feeder"], "duplex": true,
    "colorModes": ["color", "gray", "bw"], "resolutions": [150, 200, 300, 600],
    "extras": [] },
  { "id": "sane:ix500", "name": "ScanSnap iX500", "sources": ["feeder"], "duplex": true,
    "colorModes": ["color", "gray", "bw"], "resolutions": [150, 300, 600],
    "extras": ["splitOnBlank", "skipBlankPages"] } ] }
```

- `id` is stable for a given scanner and helper, so Dossiary can remember
  the last one used.
- `duplex` is true only if the feeder can scan both sides.
- `extras` lists helper-specific abilities. Known extras:
  - `splitOnBlank` — a blank page separates documents; one PDF per document.
  - `skipBlankPages` — blank pages are dropped.
  Dossiary ignores extras it doesn't know.
- An empty list is a valid answer (helper running, no scanner found).

### `POST /scan`

Request body (JSON):

```json
{ "scanner": "ic:HP-ENVY-6000", "source": "feeder", "duplex": true,
  "colorMode": "color", "resolution": 300, "format": "pdf",
  "extras": { "splitOnBlank": false } }
```

- `format` is `"pdf"` only in version 2.
- Missing optional fields use the scanner's first listed value
  (`duplex` false, `extras` off).
- The request blocks until the scan has finished — no client timeout,
  same as today.

Response: the version 1 shape, so Dossiary's inbox-writing code is reused
unchanged:

```json
{ "ok": true, "partial": false, "message": "3 pages scanned.",
  "files": [ { "name": "scan_20261009_1432.pdf", "pages": 3, "data": "<base64>" } ] }
```

One PDF holding every page; with `splitOnBlank`, one PDF per document.
Each file reports its own page count (`pages`), since a native PDF
writer may compress its page objects and a client can't count them
reliably from the bytes. Version 1 helpers don't send `pages`.
`partial: true` means something went wrong but usable pages came back
(for example a paper jam after page 3).

### Errors

| Code | Meaning |
|---|---|
| 400 | malformed request |
| 404 | unknown scanner id |
| 409 | a scan is already running |
| 422 | a setting the scanner doesn't support |
| 503 | scanner offline, or the system denied access |

Every error body is `{ok: false, partial: false, message}`, with a message
fit for Dossiary's status line.

### Security

- Helpers listen on `127.0.0.1` only.
- CORS allows only the origins `null` (a `file://` page) and
  `http://localhost:<port>` / `http://127.0.0.1:<port>`; any other
  `Origin` gets 403. A request without an `Origin` header (curl, the
  conformance suite) is allowed.
- **Pairing (added after the final review of step 1).** The origin check
  alone isn't enough: `Origin: null` also comes from any website's
  sandboxed iframes, so a malicious page could otherwise start a scan and
  read the result. Every helper therefore pairs with a browser once:
  - The helper's menu offers "Pair a browser…", showing a 6-digit code
    valid for 2 minutes and 5 attempts.
  - `POST /pair` with `{"code": "123456", "client": "<description>"}`
    answers `{"ok": true, "token": "<random, at least 128 bits>"}`; a wrong,
    expired or exhausted code answers 403.
  - `GET /scanners` and `POST /scan` require `Authorization: Bearer
    <token>` and answer 401 without a valid one. `GET /health` stays open
    and reports `"paired": true|false` for the token it was sent (if any).
  - Tokens persist in the helper until "Forget paired browsers".
  - In fake scanner mode the code is always `000000` (no expiry or attempt
    limit), so the conformance suite can pair.
- These rules are in `PROTOCOL.md` and tested by the conformance suite.

### Compatibility

- scanix500 gains `/scanners` and the JSON `POST /scan` (reporting
  `sane:ix500` with both extras) and keeps its version 1 request for older
  Dossiary versions.
- Dossiary uses version 2 with a helper that reports `protocol: 2`, and
  version 1 otherwise.

### Ports

- scanix500: `8765` (unchanged).
- dossiary-scan-helper: `8766`.

## 2. Dossiary

### Toolbar

- **📷 Scan** opens the new scan dialog.
- **📸 Scan Multi** becomes a shortcut: it opens the same dialog with
  "Split on blank pages" ticked. It is shown only while some found scanner
  offers `splitOnBlank` (in practice: the iX500 is connected); otherwise
  it's hidden. To know that before any dialog opens, Dossiary runs the
  same discovery once when a library opens (read-only requests to
  localhost, nothing written) and again whenever the dialog opens.
- No new toolbar buttons, so the toolbar can't grow (see CLAUDE.md's
  `.table-wrap` calibration note). Both buttons stay hideable via
  Tools → Toolbar buttons….

### Scan dialog

- **Pairing:** a version 2 helper whose `/health` says `"paired": false`
  shows up in the dialog as "<helper> — not paired yet" with a code field.
  The person opens "Pair a browser…" in the helper, types the code, and
  Dossiary stores the returned token in `localStorage`, keyed by the
  helper's address. That's per browser, not per library, since pairing
  belongs to the browser. A 401 later (tokens forgotten in the helper)
  brings the code field back.

- On opening, Dossiary checks `localhost:8765`, `localhost:8766` and the
  stored manual address (`scan_bridge_url`) with `GET /health` (short
  timeout, as `probeScanBridgeHealth()` does today), then `GET /scanners`
  on each version 2 helper. A version 1 helper contributes one entry,
  "ScanSnap iX500", with split on blank pages as its only extra.
- The scanner list shows every scanner found. With two helpers reporting
  the same name, the helper is added in brackets.
- For the chosen scanner, the dialog shows only what it supports: source,
  two-sided, color mode, resolution, and a checkbox per known extra.
- The last scanner and its settings are remembered per library
  (`scan_last_settings`, a JSON settings row); a scanner that's gone
  falls back to the first in the list.
- While scanning: the button reads "Scanning…", and Escape, the backdrop
  and the close button are blocked until the request settles (the
  `makeSearchableRunning` pattern).
- Results go through the existing path: `writeScanFilesToInbox()`, then
  `checkInbox()`/`addAllInboxFilesAndShowStatus()`, then the Inbox view.
  A `partial` result keeps today's behavior (inbox pipeline, then the
  helper's message on the status line).

### Nothing found

If no helper answers, the dialog says a scan helper is needed, links to
the dossiary-scan-helper releases page and to scanix500, and offers the
existing manual address field. This replaces today's "Configure Scanner
Connection" port dialog.

### i18n and docs

- All new strings in all six languages.
- README, README.de, the six User Guides and CLAUDE.md updated. User
  Guide screenshots recaptured on release (the capture script has no
  scanner, so the dialog's "nothing found" state is what it can show).

### Tests (Dossiary suite)

- Driven through the stub with a fake `fetch` for both ports: discovery
  across two helpers, a version 1 helper, the per-scanner settings,
  remembered settings, Scan Multi shown/hidden, the scan request body,
  results reaching the Inbox, `partial`, each error code's message,
  nothing found.

## 3. The helpers (`dossiary-scan-helper`)

### Repository

```
PROTOCOL.md      the version 2 protocol
macos/           Swift package: menu bar app
windows/         C# .NET 8 solution: tray app
conformance/     Python suite run against any helper over HTTP
reference/       a minimal Python helper with fake scanners (for Dossiary
                 development and for testing the suite itself)
docs/            install guides (including the unsigned-app warning)
```

### macOS (Swift, ImageCaptureCore)

- Menu bar icon with the found scanners, the port, "Start at login" and
  Quit.
- `ICDeviceBrowser` finds USB, network and AirPrint/eSCL scanners and
  keeps the list current.
- A scan opens a session, sets the functional unit (feeder/flatbed),
  duplex, color mode/bit depth and resolution, collects the pages, and
  builds the PDF with PDFKit. No window is shown.
- If the system denies scanner access, scans answer 503 with a message
  saying where to allow it.

### Windows (C# .NET 8, WIA 2.0)

- Tray icon with the same menu.
- WIA's device manager lists scanners; feeder/flatbed and duplex come from
  the device's properties, and only what the device reports is offered.
- Pages come back as images and are joined into a PDF with PDFsharp (MIT).
- Shipped as one self-contained `.exe` (no .NET install needed).

### Both

- `127.0.0.1:8766`, the shared origin check, one scan at a time (409
  otherwise), a log file for support.
- Plain image PDFs, no OCR: Dossiary's Make searchable does that.
- A `--fake-scanners` flag replaces the system scanners with generated
  ones that return numbered test pages.

### Testing

- The conformance suite checks every endpoint, error code, the origin
  check and the PDF output. CI runs it against each helper in
  `--fake-scanners` mode on GitHub's macOS and Windows runners, and
  against the reference helper.
- Real hardware is checked by hand before each release, with a short
  checklist in `docs/`.
- scanix500 runs the same suite against its version 2 endpoints.

## 4. Order of work

Each step is usable on its own and gets its own implementation plan in the
repo it changes.

1. **Protocol and conformance** (new repo): `PROTOCOL.md`, the
   conformance suite, the reference helper. Creating the public GitHub
   repo needs the owner's OK at the start of this step.
2. **Dossiary**: the scan dialog, discovery on both ports, version 1
   fallback, Scan Multi as shortcut. Tested against the stub and the
   reference helper; released before any real helper exists.
3. **macOS helper.**
4. **scanix500 version 2.**
5. **Windows helper** (needs a Windows machine or VM with a scanner for
   the manual check; CI covers it until then).

## Out of scope

- Signing and notarization (unsigned builds first).
- OCR in the helpers.
- Linux.
- Page preview or page picking before saving (pages go to the Inbox,
  where Edit pages… fixes them).
