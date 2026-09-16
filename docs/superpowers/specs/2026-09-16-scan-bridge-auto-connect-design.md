# Scan bridge auto-connect & file transfer — Design

**Status:** Approved, ready for implementation planning.

**Relationship to prior work:** This amends the already-shipped
[2026-09-14-scanix500-bridge-design.md](2026-09-14-scanix500-bridge-design.md)
and its Dossiary-side toolbar-buttons implementation. It keeps that spec's
core contract — the embedded `ThreadingHTTPServer` inside
`scanix500-menubar`, the `_scanning` busy-guard, the `ScanTrigger` protocol,
`route_scan_request()`'s dispatch shape, and the `Dossiary Scan`/
`Dossiary Scan Multi` fixed profile names — unchanged. It replaces two
specific pieces of that design: how Dossiary learns the bridge's URL, and
how the scanned file gets from scanix500 into the library.

## Problem

The shipped feature requires a person to (1) manually create two scanix500
profiles with a destination folder pointed at exactly the right library's
`inbox/` subfolder, and (2) manually type the bridge's URL into Dossiary's
Field Settings. Both are one-time friction that a first-time setup
shouldn't need, and (2) breaks silently if scanix500 restarts on a
different port.

Two changes fix this:

1. **Auto-connect**: Dossiary tries the default port itself before ever
   asking the person to type anything, and only falls back to a minimal
   manual-entry dialog if that fails.
2. **File transfer over the connection**: instead of relying on scanix500
   writing the file to a folder Dossiary is trusting it got right, the
   scanned file's bytes ride back in the same HTTP response Dossiary is
   already waiting on. This also removes any requirement that a profile's
   destination match a specific library at all.

## Architecture

### scanix500 side (`scanix500-menubar`)

**`GET /health`** — new, minimal endpoint alongside the existing
`POST /scan/<profile-name>`. Returns `200` with a small JSON body (e.g.
`{"service": "scanix500-bridge"}`) immediately, no busy-guard interaction,
no scanner involvement. This is a distinct route from the scan trigger
specifically so probing for "is anything here" never risks accidentally
firing a real scan attempt at an unknown or unrelated service on that
port.

**`POST /scan/<profile-name>` response gains a `files` field.** The scan
pipeline itself is unchanged — scanix500 still runs the scan and writes
the resulting PDF(s) to the profile's own configured `destination` folder,
exactly as today. The new behavior is additive: after writing, the bridge
reads each written file back and includes it in the JSON response:

```json
{
  "ok": true,
  "partial": false,
  "message": "...",
  "output_paths": ["/Users/.../destination/scan_1.pdf"],
  "files": [
    { "filename": "scan_1.pdf", "content_base64": "JVBERi0xLjQK..." }
  ]
}
```

`output_paths` (already shipped) keeps its existing meaning — where the
file landed on scanix500's own disk. `files` is new: the same file(s),
base64-encoded, for Dossiary to write into the library itself.

**A profile's `destination` folder is no longer required to be a specific
Dossiary library's `inbox/`.** Since Dossiary now gets the file over the
wire, `destination` becomes purely a local safety net — deliberately still
required (the scan pipeline needs *somewhere* to write), but it can be any
folder the person chooses (their Desktop, a dedicated "scan backups"
folder, anything). This simplifies onboarding: creating the `Dossiary
Scan`/`Dossiary Scan Multi` profiles once no longer requires knowing or
typing the exact path to a specific library's `inbox/` subfolder.

**No automatic cleanup of the safety-net files.** Matches this app's own
established stance elsewhere (no auto-empty on Dossiary's Waste bin, no
automatic deletion anywhere in this app's own philosophy) — if the
destination folder accumulates old scans over time, that's a manual
cleanup for the person, not something either side of the bridge manages
automatically. Accepted tradeoff, not a gap to close later.

### Dossiary side (`dossiary.html`)

**Auto-connect flow**, replacing today's "must type `scan_bridge_url`
before either button works" gate:

1. Scan or Scan Multi clicked with no stored `scan_bridge_url` → Dossiary
   sends `GET http://localhost:8765/health` with a short client-side
   timeout (a few seconds — this is a reachability probe, unlike the
   deliberately un-timed-out scan request itself).
2. Success → `http://localhost:8765` is saved as `scan_bridge_url`
   immediately (same settings-table persistence as today) and the
   originally-clicked scan proceeds right away — the person's first click
   just works, no dialog shown at all.
3. Failure (refused/timeout) → a small **"Configure Scanner
   Connection"** dialog opens: one **Port** field, pre-filled with `8765`,
   plus a short instruction to check scanix500-menubar's own menu for its
   current port. Submitting re-probes `GET /health` on that port; success
   saves `http://localhost:<port>` and proceeds with the original scan;
   failure keeps the dialog open with an error status.
4. A **later** scan against an already-stored `scan_bridge_url` that fails
   (bridge restarted on a different port, app not running) reopens the
   same dialog rather than just showing an unreachable-bridge status with
   no recovery path — reusing the flow from step 3, not a second
   mechanism.
5. The existing Field Settings `scan_bridge_url` text field is kept
   unchanged, as a manual override/escape hatch (a non-default port
   configured from the start, or a future non-localhost bridge).

**`triggerScan()` changes**: on a successful (`ok: true` or `ok: false,
partial: true`) response, instead of immediately calling
`checkInbox()`/`addAllInboxFilesAndShowStatus()` and trusting the file is
already sitting in `inbox/`, Dossiary first decodes every entry in the
response's `files` array and writes each one into the library's own
`inbox/` folder via its existing File System Access handle. *Then* it
runs the same `checkInbox()`/`addAllInboxFilesAndShowStatus()` pipeline,
completely unchanged from today — from that point on, a bridge-delivered
scan is indistinguishable from any other file that showed up in `inbox/`.
Written filenames must not silently overwrite an existing same-named
`inbox/` file; the exact collision-avoidance mechanism (e.g. a
uniqueness suffix) is an implementation detail for the plan, not fixed
here, but the requirement is binding.

A malformed or missing `files` array on an otherwise-`ok` response (e.g. a
bridge running an older version that hasn't shipped this change yet) is
treated as a hard failure for that scan — reported via the existing
`scanBridgeUnreachable`-style status messaging, not a silent no-op. This
keeps the two sides honest about the protocol version they're speaking
rather than degrading confusingly.

## Data flow (happy path)

See the approved sequence: Dossiary POSTs to `/scan/<profile>` → bridge
drives the scanner via SANE using the profile's settings → bridge writes
the result to `destination` (safety net, unchanged pipeline) → bridge
resolves the still-open request with `files` (base64) alongside the
existing `ok`/`partial`/`message`/`output_paths` → Dossiary decodes and
writes into its own `inbox/` → existing `checkInbox()` ingestion pipeline
runs unchanged → document appears in the 🚩 Inbox view, both buttons
re-enable.

## Error handling

Builds on the already-shipped semantics (404 unknown profile, 409 busy,
no client-side timeout on the scan request itself, buttons always
re-enabled via `try/finally`) rather than replacing them:

- **Health-probe failure** (auto-connect step 1/3/4 above): opens the
  configure dialog, not a scan-time error status — no scan was attempted.
- **Malformed/missing `files` on an `ok` response**: treated as failure,
  reported via existing unreachable-style messaging (see above).
- **Partial multi-file scans** (Scan Multi / split-on-blank): unchanged
  from the shipped `ok:false, partial:true` contract — whatever files the
  bridge did manage to produce and encode are included in `files` and
  still get written into `inbox/`, exactly as a partial result already
  runs the Inbox pipeline today.
- **A write failure on Dossiary's side** (decoding or writing a
  transferred file into `inbox/` throws): falls into the same catch block
  `triggerScan()` already uses for network failures — reported via
  `scanBridgeUnreachable`-style messaging. The safety-net copy still
  exists in the profile's `destination` folder as a manual recovery path
  (draggable into Dossiary via the existing drag-and-drop feature — no new
  recovery mechanism needed).

## What this removes from the shipped design

- The instruction that a profile's `destination` must point at a specific
  library's `inbox/` folder. It no longer needs to point anywhere in
  particular.
- The requirement to manually type `scan_bridge_url` before either button
  works at all — it's now the fallback path, not the only path.
- Per-library scanix500 profiles were considered (each Dossiary library
  getting its own named profile pair) but explicitly rejected: once the
  file transfers over the connection instead of relying on filesystem
  placement, scanix500 no longer needs to know which library it's serving
  — one global `Dossiary Scan`/`Dossiary Scan Multi` pair, as already
  shipped, is sufficient.
