# One /Applications/Dossiary folder for the installed apps

Date: 2026-10-15
Repos: Dossiary (launcher), iX500/scanix500 (install script)

## Goal

Everything used day to day sits in one folder, `/Applications/Dossiary/`,
and none of it runs from a git checkout. Today scanix500's menu bar app runs
from `~/Projects/iX500/.venv` through a LaunchAgent, so checking out a branch
there changes the scanner software in use. After this change the project
folders are for development only.

## Layout

```
/Applications/Dossiary/
├── Dossiary.app                  launcher: opens dossiary.html in Chrome/Edge
├── dossiary.html                 the app itself
├── Dossiary Scan Helper.app      signed helper, starts at login
└── scanix500/
    ├── venv/                     Python environment installed from a release tag
    └── VERSION                   e.g. "0.5.0 (v0.5.0)"
```

Not installed: `scan_watch.py`. Scans reach Dossiary through the scan
dialog (scanix500 or the Scan Helper), so the watched-folder helper stays in
the repo for people who scan with other software.

## Dossiary.app (launcher)

- An AppleScript app compiled with `osacompile`. Source and build script in
  the Dossiary repo: `packaging/macos/Dossiary.applescript`,
  `packaging/macos/build-launcher.sh`.
- On launch it opens the `dossiary.html` in the same folder as the app
  (resolved from the app's own location, never a fixed path), with
  Google Chrome, else Microsoft Edge. With neither installed it shows a
  dialog: "Dossiary needs Google Chrome or Microsoft Edge." With no
  `dossiary.html` next to it, a dialog says which file is missing and where.
- Icon: Dossiary's favicon (the SVG in `dossiary.html`'s `<link rel="icon">`)
  rendered to an `.icns` by the build script (`qlmanage`/`sips` for the PNG
  sizes, `iconutil` for the `.icns`), replacing the applet icon.
- Signed ad hoc (`codesign -s -`). For this Mac only; notarizing is out of
  scope until the launcher is ever handed to someone else.
- `build-launcher.sh [destination]` builds into `packaging/macos/build/` and,
  given a destination, copies `Dossiary.app` there. Not part of a normal
  Dossiary release; rebuilt only when the launcher source changes.

## scanix500 --version

`scanix500 --version` prints `scanix500 <version>` (from
`scanix500.__version__`) and exits 0, via argparse's `action="version"`, so it
works without the otherwise required `destination` argument. Covered by a
test in `tests/test_cli.py`. The install script uses it (below).

## scanix500 installed copy

New script in the iX500 repo: `scripts/install-app.sh <ref>` (a tag like
`v0.5.0`; any git ref is accepted, but releases use tags).

1. Checks the Homebrew prerequisites (`sane-backends`, `ocrmypdf`,
   `tesseract`) and stops with the `brew install` line if one is missing.
2. Exports `<ref>` with `git archive` into a temporary folder, so the
   working copy and its current branch are never touched.
3. Creates `/Applications/Dossiary/scanix500/venv.new`, installs
   `python-sane` with the `CPATH`/`LIBRARY_PATH` the README describes, then
   the exported package (not editable, no dev extras).
4. Checks the new environment: `venv.new/bin/scanix500 --version` must print
   `scanix500 <version>` with the version the exported `pyproject.toml`
   declares, `venv.new/bin/python -c "import sane"` must succeed (scanix500
   imports `sane` lazily, so `--version` alone doesn't prove it built), and
   `venv.new/bin/scanix500-menubar` must exist.
5. Stops the LaunchAgent (`launchctl bootout gui/$UID/com.scanix500.menubar`,
   ignoring "not loaded"), moves `venv` to `venv.old`, `venv.new` to `venv`,
   writes `VERSION`, removes `venv.old`.
6. Writes `~/Library/LaunchAgents/com.scanix500.menubar.plist` pointing at
   the installed venv, with the log at `~/Library/Logs/scanix500.log`
   (not `/tmp`, which is cleared on restart), and loads it
   (`launchctl bootstrap`).
7. Replaces the broken `/opt/homebrew/bin/scanix500` wrapper (it imports
   scanix500 from Homebrew's Python, where it isn't installed) with a
   symlink to `venv/bin/scanix500`.

Any failure in steps 1-4 leaves the installed version and the running
LaunchAgent untouched and removes `venv.new`. A failure in 5-7 is reported
with the step that failed; `venv.old` is kept until the swap completes, so
the previous version can be put back by hand.

`packaging/com.scanix500.menubar.plist` stays the template for people
running from their own venv; the script writes its own filled-in copy. The
README gains a short "Install as an app on this Mac" section.

The first install needs a tag for the current version: `pyproject.toml`
says 0.5.0 but the newest tag is v0.3.0. Tagging (and pushing the tag)
happens with the user's OK as part of that step.

## Moving over (one-off)

1. Create `/Applications/Dossiary/`.
2. Quit Dossiary Scan Helper, move it into the folder, start it, then turn
   its "Start at login" off and on so the login item points at the new
   location. Pairing is stored outside the app and is expected to survive,
   as it did when the app first moved to /Applications.
3. Move `/Applications/dossiary.html` into the folder. Recent libraries,
   language and scan pairing tokens are stored per browser for all `file://`
   pages, not per path, so nothing is lost; bookmarks to the old path need
   updating.
4. Run `scripts/install-app.sh v0.5.0` in the iX500 repo.
5. Run `packaging/macos/build-launcher.sh /Applications/Dossiary`.
6. Check: Dossiary.app opens Dossiary in Chrome with the recent libraries
   listed; 📷 Scan lists both helpers; a scan through scanix500 arrives
   searchable; after a log out and in, both helpers are running.

## Updates from now on

This replaces the "copy to /Applications" memory rule:

- Dossiary release: copy `dossiary.html` to `/Applications/Dossiary/`.
- Scan Helper release: quit it, replace the app in `/Applications/Dossiary/`,
  start it again.
- scanix500 release: tag, then `scripts/install-app.sh <tag>`.
- Launcher: rebuild only when its source changes.

## Testing

- Launcher: built and opened by hand, with Chrome present; the missing-
  `dossiary.html` dialog checked by running a copy from an empty folder.
- `scanix500 --version`: unit test, run by the iX500 suite.
- `install-app.sh`: a run against the real tag (the move above), plus a run
  with a nonexistent ref, which must fail at step 2 with the running
  scanix500 untouched (`launchctl print gui/$UID/com.scanix500.menubar`
  still shows it running).
- No changes to `dossiary.html` or the test suite.

## Out of scope

- A real, bundled `scanix500.app` (py2app, signed). Worth doing only if
  scanix500 is ever handed to other people.
- Installing for other people (Jana gets the Scan Helper zip and
  `dossiary.html`, as before).
- Automatic updates.
