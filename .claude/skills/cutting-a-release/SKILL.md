---
name: cutting-a-release
description: Use when bumping dossiary.html/scan_watch.py's version number and cutting a new Dossiary release (tagging, syncing version constants).
---

## Versioning

`dossiary.html` and `scan_watch.py` share one version number (`1.8.3` as of
this writing), kept manually in sync with this repo's git tag on each
release — no build step or shared version file to do this automatically.
`dossiary.html` has its own `APP_VERSION` constant (the very first line
inside the top-level IIFE), shown in the footer next to the copyright line
via `#app-version-label`, set once during the same static-wiring pass as
the Libraries-link click handler — deliberately not gated behind a library
being open, since the version should be visible regardless of app state.
`scan_watch.py` has its own separate `__version__`, exposed the standard
way via `argparse`'s `--version` flag. When cutting a release, bump both
constants together with the tag — nothing currently checks that they agree
with each other or with the tag, or with `LibraryLifeboat`'s own version
(the sibling repo's `migrate_to_new_library.py` produces the schema this
app expects, so a large version skew between the two is worth noticing,
though the two repos don't currently enforce or check compatibility by
version number — only by the schema itself matching).

