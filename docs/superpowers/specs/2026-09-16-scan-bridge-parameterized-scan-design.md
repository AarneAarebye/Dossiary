# Scan bridge: parameterized scan (remove profile lookup) — Design

**Status:** Approved, ready for implementation planning.

**Relationship to prior work:** This amends the scan bridge contract shipped
in [2026-09-14-scanix500-bridge-design.md](2026-09-14-scanix500-bridge-design.md)
and extended in [2026-09-16-scan-bridge-auto-connect-design.md](2026-09-16-scan-bridge-auto-connect-design.md).
Those specs are otherwise unchanged: `GET /health`, the busy-guard, the
`ScanTrigger` protocol, the `{ok, partial, message, output_paths, files}`
response shape, Dossiary's auto-connect flow, and the `files`-field
decode-and-write into `inbox/` all stay exactly as they are. This spec
replaces one specific piece: how a Dossiary-triggered scan tells scanix500
what settings to use.

## Problem

Today, `POST /scan/<profile-name>` requires the person to manually
pre-create two scanix500 profiles — `"Dossiary Scan"` and `"Dossiary Scan
Multi"` — in scanix500-menubar's own Add Profile UI, with names that must
match Dossiary's own hardcoded constants exactly, before either toolbar
button works at all. This is unnecessary setup friction: Dossiary already
knows exactly what scan settings it wants (`split_on_blank` distinguishes
its two buttons; `skip_blank_filter`/`skip_ocr` are otherwise ordinary
flags), so there's no real need for an intermediate named profile it has to
ask a person to create by hand first.

## Scope

This change is scoped to the Dossiary↔bridge communication path only.
`profiles.json`, the menu bar app's own manual "click a profile in the
dropdown to scan" UI, and the reserved `"Hardware Button"` profile (used
when someone presses the physical scan button on the device) are
completely untouched — those all continue to work exactly as they do
today, independent of this change.

## Architecture

### The new wire contract

```
POST /scan?skip_blank_filter=<true|false>&skip_ocr=<true|false>&split_on_blank=<true|false>
```

No profile name anywhere in the request. All three query parameters are
required and must be exactly the literal string `"true"` or `"false"`
(case-sensitive, matching what `String(jsBoolean)` produces in Dossiary's
own JS) — a missing or malformed parameter is a `400 Bad Request` naming
the problem, not a silent default. `GET /health`, the `409` busy response,
and the success/partial/failure response body shape are all completely
unchanged from the already-shipped contract.

`POST /scan/<profile-name>` is **removed**. It's Dossiary-only surface
area today (per the repo's own documented "Dossiary integration"
contract), and once Dossiary moves to the new endpoint, keeping the old
one around would just be unused protocol sprawl. The README's own curl
smoke-test section, which currently exercises the old endpoint against a
manually-created `"Default"` profile, gets updated to exercise the new one
instead.

### scanix500 side

**`route_scan_request()` drops its profile lookup entirely.** Its current
signature takes `(profiles: list[Profile], name: str, trigger:
ScanTrigger)` and calls `find_profile(profiles, name)`; the new version
takes the three parsed boolean flags and the resolved destination folder
(see below) instead, and constructs an **ephemeral** `Profile` object on
the fly — name `"Dossiary Bridge Scan"` (used only for internal
bookkeeping; it's never added to `profiles.json` or shown in any menu),
`destination` from the new setting, and the three flags from the request —
then passes that straight into the existing `trigger.trigger(profile)`
call. This is the key simplification: `ScanTrigger`, `ScanixMenuBarApp.
_execute_scan()`, `runner.run_scan()`, and `_build_argv()` all already just
take a `Profile` and don't care where it came from, so **none of that
pipeline changes at all** — only the thing that constructs the `Profile`
changes, from "look one up by name" to "build one from request
parameters."

The HTTP handler's `do_POST()` gains query-string parsing for the new
`/scan` path (using the same `urlsplit()` it already calls for every
request — this is a trivial extension of existing parsing, not a new
mechanism) and a small boolean-parameter validator that produces the
`400` on anything malformed. It still never reads `self.rfile` — the
existing comment explaining why that's safe only under HTTP/1.0 remains
accurate and unchanged, since query-string parameters don't touch the
request body at all.

### The new bridge-scan-folder setting

A single new, small, persisted value — **not** a `Profile`, not stored in
`profiles.json` — holding the folder a Dossiary-triggered scan's
safety-net copy gets written to (the same "write to disk first,
unconditionally, before the response is built" safety-net behavior the
2026-09-16 auto-connect amendment already established; only *where* it
writes changes here). Defaults to `~/Documents/Scans` (the same default
`"Default"`/`"Hardware Button"` profiles already use) until someone
configures it explicitly.

Editable via a new **"Set Bridge Scan Folder…"** menu item in
scanix500-menubar's own menu (alongside the existing "Add Profile…" item),
reusing whatever folder-picking UI mechanism the existing Add/Edit
Profile form already uses for its own `destination` field — no new picker
UI pattern needs to be invented. Stored in its own small file next to
`profiles.json` (e.g. a plain text file holding just the path, following
the same atomic-write-via-tempfile pattern `save_profiles()` already
uses, since it's a single string value with no need for JSON structure).

### Dossiary side

`SCAN_PROFILE_NAME`/`SCAN_MULTI_PROFILE_NAME` are removed. `triggerScan()`
POSTs directly to:

```javascript
`${scanBridgeUrl}/scan?skip_blank_filter=false&skip_ocr=false&split_on_blank=${isMulti}`
```

(exact query-string construction — e.g. via `URLSearchParams` vs. a
template literal — is an implementation detail for the plan, not fixed
here) where `isMulti` is `true` for the Scan Multi button, `false` for
plain Scan. Everything downstream of the POST — status handling, the
`files`-field decode-and-write into `inbox/`, the auto-connect flow, the
`404`/`409`/network-failure branches — is **completely unchanged**; only
the request URL construction changes. The `404` branch's meaning shifts
slightly (there's no more "unknown profile" case to report, since there's
no more profile name) — it becomes generically "not found," which in
practice should no longer be reachable at all once this ships, since the
new endpoint always exists at a fixed path with no name to get wrong. The
new `400` case (a malformed/missing query parameter, which should never
happen from Dossiary's own correctly-written request but is a real
possible response) needs its own status handling, distinct from `404`.

## Error handling

Builds on the already-shipped semantics rather than replacing them:

- **`400 Bad Request`**: any of the three query parameters missing or not
  exactly `"true"`/`"false"`. New case, replacing the old `404`
  "unknown profile" case's role in the protocol.
- **`404`**: now only reachable for a request to a path that isn't `/scan`
  or `/health` at all — the same generic "not found" the bridge already
  returns for any unrecognized path.
- **`409` busy**, **`ok`/`partial`/`message`/`output_paths`/`files`
  response shape**, **no server-side timeout on the scan itself**: all
  unchanged.
- **Dossiary's own status messaging** (`scanProfileNotConfigured`, etc.)
  gets adjusted to match: the "profile not found" message no longer makes
  sense as worded, and needs new copy for the `400` case across all 6
  languages (exact wording is a plan-level detail).

## What this removes from the shipped design

- `POST /scan/<profile-name>` and its profile-name-lookup semantics.
- The requirement to manually pre-create `"Dossiary Scan"`/`"Dossiary Scan
  Multi"` profiles in scanix500-menubar before either Dossiary button
  works — this was the entire motivation for the change.
- `SCAN_PROFILE_NAME`/`SCAN_MULTI_PROFILE_NAME` from `dossiary.html`.
- The README's "Dossiary integration" section's own description of the
  fixed-profile-name contract, replaced with a description of the new
  parameterized endpoint.
