# Scan helper discoverability — Design

**Status:** Approved, ready for implementation planning.

**Relationship to prior work:** This is a discoverability/UX change on top of
the already-shipped scan-bridge integration —
[2026-09-14-scanix500-bridge-design.md](2026-09-14-scanix500-bridge-design.md),
[2026-09-16-scan-bridge-auto-connect-design.md](2026-09-16-scan-bridge-auto-connect-design.md),
and
[2026-09-16-scan-bridge-parameterized-scan-design.md](2026-09-16-scan-bridge-parameterized-scan-design.md).
None of those specs are touched — the bridge's wire contract, the
`triggerScan()`/auto-connect flow, and `scanix500-menubar`'s own feature set
(profiles, hardware-button scanning, the bridge scan folder setting) are all
unchanged. This spec is purely about how a person *finds and understands*
that companion app in the first place.

## Problem

Getting Dossiary's Scan/Scan Multi toolbar buttons working requires
installing a separate macOS app (`scanix500-menubar`, from a differently
named sibling repo, `AarneAarebye/iX500`). Today, nothing in Dossiary itself
tells a person this, names the app, or links to it — they'd have to already
know it exists. And the one piece of in-app feedback that *does* exist when
nothing is configured — the "Configure Scanner Connection" dialog's Port
field — assumes the bridge is already installed and just misconfigured,
which is actively unhelpful advice for someone who hasn't installed anything
yet.

This is explicitly a framing/discoverability problem, not a problem with the
companion app's install process or feature set. `scanix500-menubar` stays
exactly as it is — this spec adds no new app, no new build target, and no
new repo.

## Scope

Two repos, both documentation/UI-only changes:

- **Dossiary** (`dossiary.html`): a new "Scanner Integration" section in
  Field Settings, and one added line in the existing "Configure Scanner
  Connection" dialog.
- **iX500**: a short callout added to the top of `README.md`.

No changes to the bridge's wire contract, `triggerScan()`'s request/response
handling, or anything in `scanix500-menubar`'s own Python code.

## Dossiary-side changes

### Field Settings: "Scanner Integration" section

A new section in the Field Settings modal, alongside the existing
`scan_bridge_url` manual-override text field (`#fs-scan-bridge-url`) — same
modal, so the explanation and the escape-hatch setting it's explaining sit
next to each other. Static content: a short paragraph explaining what
scanning from the toolbar requires (a small companion app, `scanix500-menubar`,
running locally), and a direct link to its latest GitHub release
(`https://github.com/AarneAarebye/iX500/releases/latest`) rather than to the
bare repo — a release page's own asset list is the actual next step someone
needs, not a repo's file tree.

Like every other string in this app, the paragraph text and link label get
entries in all 6 `STRINGS.*` blocks. Since `openFieldSettingsModal()`'s
whole template is rebuilt from scratch on every open (not static page
markup), this follows the established convention for that class of
content — inline `${t('key')}` calls at template-build time, not
`data-i18n` attributes, which only resolve on markup that survives across
renders. The link's `href` itself is not translated (it's a URL, not UI
copy), only the surrounding text is.

### The Configure Scanner Connection dialog gains a persistent download line

`openScanConnectDialog()`'s template gains one more line, shown
unconditionally every time the dialog opens (both the first-open case with
nothing configured yet, and any later reopen after a network-level probe
failure): a "Don't have the scan helper installed? [Download it]" link,
pointing at the same release URL as the Field Settings section. This sits
alongside the existing, unchanged Port field — not a replacement for it, and
not conditionally shown. Same i18n treatment as the Field Settings section —
`openScanConnectDialog()` is also rebuilt fresh on every open, so this uses
inline `${t('key')}` calls too, with new entries across all 6 languages.

**Why not detect which case applies and show only the relevant one:** a
browser's `fetch()` cannot distinguish "nothing is listening on this port"
from "something's listening on a different port" or "a firewall blocked the
connection" — every one of those failure modes surfaces as the same generic
network error (a `TypeError` in Chrome) with no further detail. There is no
reliable signal in `probeScanBridgeHealth()`'s failure path to branch on, so
the dialog shows both pieces of advice together every time, rather than
guessing.

## iX500-side changes

A short callout added at the very top of `README.md`, above the existing
detailed setup/architecture documentation — something to the effect of "New
here via Dossiary? Download the latest release, run
`scanix500-menubar.app`, and Dossiary's Scan buttons will connect
automatically" with a link to the releases page. This mirrors the
README-vs-USER_GUIDE split Dossiary's own docs already use (README for
people who want the internals, a lightweight on-ramp for people who just
want the thing to work) — except scoped to a few sentences at the top of
the existing README, not a whole separate document; this repo's audience
doesn't need a second beginner guide the way Dossiary's non-technical users
did.

No other changes to the README's structure, no renaming of the app or
repo, no new release-asset naming convention, no in-app "Dossiary" branding
added to `scanix500-menubar` itself. The friction being solved is "I didn't
know this existed or where to find it," which a link and a short callout
solve without touching the project's own identity.

## Error handling

Already covered above — the one behavior change in this spec is additive
UI (a download link shown unconditionally in an existing dialog), not new
control flow. No new error states, no new network calls, no change to what
counts as success/failure anywhere in the existing auto-connect flow.

## Testing

Dossiary: a couple of new scenarios in `tests/test_scan_bridge.py` (this
repo's existing print-based Playwright convention) — confirming the Field
Settings "Scanner Integration" section renders with its link, and that the
Configure Scanner Connection dialog's new download line is present whenever
the dialog opens (both the "nothing configured yet" and "existing URL
failed at the network level" cases already covered by existing scenarios).
The new i18n keys' presence in all 6 languages is already covered for free
by `tests/test_i18n_coverage.py`'s existing static grep-and-check, once the
new `data-i18n` attributes/keys exist.

iX500: no test — the README callout is documentation-only.

## What this doesn't change

- `scanix500-menubar`'s feature set (profiles, hardware-button scanning,
  the bridge scan folder setting) — unchanged.
- The bridge's wire contract (`GET /health`, `POST /scan?...`) — unchanged.
- `triggerScan()`'s request construction or response handling — unchanged.
- No new app, build target, or repo.
- No renaming of `scanix500`/`scanix500-menubar`, no new release-asset
  branding.
