# /Applications/Dossiary Folder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Dossiary, Dossiary Scan Helper and scanix500 into one `/Applications/Dossiary/` folder, with scanix500 running from an installed copy instead of its git checkout, and a `Dossiary.app` launcher that opens `dossiary.html` in Chrome.

**Architecture:** scanix500 gains `--version` and a `scripts/install-app.sh <tag>` that exports a tag with `git archive`, builds a fresh venv in its own never-moved folder under `scanix500/venvs/`, checks it, then points a `venv` symlink at it and rewrites the LaunchAgent. Dossiary gains `packaging/macos/` with an AppleScript launcher and a build script that makes its icon from `dossiary.html`'s own favicon. A final, hands-on task moves the existing apps into the folder.

**Tech Stack:** bash, Python 3.14 venv (Homebrew), argparse, pytest; AppleScript (`osacompile`), `qlmanage`/`sips`/`iconutil`, `codesign`, `launchctl`.

**Spec:** `docs/superpowers/specs/2026-10-15-applications-folder-layout-design.md` (Dossiary repo).

## Global Constraints

- Install folder: `/Applications/Dossiary/`; scanix500 under `/Applications/Dossiary/scanix500/` with `venv` (symlink) → `venvs/<version>-<yyyymmddThhmmss>`, plus `VERSION` containing `<version> (<ref>)`.
- A venv is never renamed or moved after creation (its scripts carry its absolute path).
- LaunchAgent label `com.scanix500.menubar`, plist `~/Library/LaunchAgents/com.scanix500.menubar.plist`, log `~/Library/Logs/scanix500.log`.
- `scanix500` command link: `/opt/homebrew/bin/scanix500` → `<install>/venv/bin/scanix500`.
- Overrides: `SCANIX500_INSTALL_DIR`, `SCANIX500_AGENT_DIR`, `SCANIX500_LOG`, `SCANIX500_BIN_LINK`, `LAUNCHCTL`, `BREW`.
- Steps 1-4 of the install script change nothing outside the new environment; on failure the new environment is removed and `launchctl` is never called.
- `scanix500 --version` prints exactly `scanix500 <version>` and exits 0.
- Launcher opens the `dossiary.html` next to the app with Google Chrome (`com.google.Chrome`), else Microsoft Edge (`com.microsoft.edgemac`); dialog texts exactly: "Dossiary needs Google Chrome or Microsoft Edge." and "dossiary.html was not found next to Dossiary.app. Expected: <path>".
- Launcher signed ad hoc only (`codesign -s -`); no notarization.
- No changes to `dossiary.html` or Dossiary's test suite.
- iX500 repo: `~/Projects/iX500`, tests with `.venv/bin/pytest`. Dossiary repo: `~/Projects/Paperless/Dossiary`. Each repo's work goes on its own feature branch, merged locally when done; pushing and tagging need the user's OK.

---

### Task 1: `scanix500 --version` (iX500 repo)

**Files:**
- Modify: `src/scanix500/cli.py` (imports, `parse_args()`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: `scanix500 --version` → stdout `scanix500 0.5.0\n`, exit 0. Used by Task 2's step 4.

- [ ] **Step 1: Write the failing test** — append to `tests/test_cli.py`:

```python
def test_version_flag_prints_version_without_destination(capsys):
    import pytest
    from scanix500 import __version__

    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"scanix500 {__version__}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_cli.py::test_version_flag_prints_version_without_destination -v`
Expected: FAIL (argparse exits with code 2: "the following arguments are required: destination" / unrecognized `--version`).

- [ ] **Step 3: Implement** — in `src/scanix500/cli.py` add `from scanix500 import __version__` with the other `scanix500` imports, and in `parse_args()` right after the `ArgumentParser(...)` line:

```python
    parser.add_argument("--version", action="version", version=f"scanix500 {__version__}")
```

- [ ] **Step 4: Run the test, then the whole suite**

Run: `.venv/bin/pytest tests/test_cli.py -v` then `.venv/bin/pytest`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/scanix500/cli.py tests/test_cli.py
git commit -m "scanix500 --version"
```

---

### Task 2: `scripts/install-app.sh` (iX500 repo)

**Files:**
- Create: `scripts/install-app.sh` (executable)
- Create: `tests/test_install_app.py`
- Modify: `README.md` (new section "Install as an app on this Mac", placed right after "## Install"'s content, before "## Run")

**Interfaces:**
- Consumes: `scanix500 --version` from Task 1.
- Produces: `scripts/install-app.sh <ref>`; exit 0 on success, 1 on failure (message on stderr prefixed `install-app: `), 2 on missing argument. Used by Task 4.

- [ ] **Step 1: Write the failing tests** — `tests/test_install_app.py`:

```python
"""install-app.sh's failure paths, run with fake brew/launchctl and a temp
install location so nothing real is touched. The success path is checked by
hand (it builds a real venv and loads a real LaunchAgent)."""
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "install-app.sh"


def _fake(bin_dir: Path, name: str, body: str) -> Path:
    path = bin_dir / name
    path.write_text("#!/bin/bash\n" + body)
    path.chmod(0o755)
    return path


def _run(tmp_path: Path, args: list[str], missing_formula: str = ""):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "launchctl-calls"
    launchctl = _fake(bin_dir, "launchctl", f'echo "$@" >> "{calls}"\n')
    brew = _fake(
        bin_dir,
        "brew",
        f'if [ "$1" = list ] && [ "$3" = "{missing_formula}" ]; then exit 1; fi\n'
        'if [ "$1" = --prefix ]; then echo /nonexistent; fi\n'
        "exit 0\n",
    )
    env = dict(
        os.environ,
        SCANIX500_INSTALL_DIR=str(tmp_path / "install"),
        SCANIX500_AGENT_DIR=str(tmp_path / "agents"),
        SCANIX500_LOG=str(tmp_path / "logs" / "scanix500.log"),
        SCANIX500_BIN_LINK=str(tmp_path / "link" / "scanix500"),
        LAUNCHCTL=str(launchctl),
        BREW=str(brew),
    )
    result = subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True)
    return result, calls


def _assert_nothing_changed(tmp_path: Path, calls: Path):
    assert not (tmp_path / "install").exists()
    assert not (tmp_path / "agents").exists()
    assert not (tmp_path / "logs").exists()
    assert not (tmp_path / "link").exists()
    assert not calls.exists(), "launchctl must not be called"


def test_no_argument_prints_usage(tmp_path):
    result, calls = _run(tmp_path, [])
    assert result.returncode == 2
    assert "Usage:" in result.stderr
    _assert_nothing_changed(tmp_path, calls)


def test_missing_prerequisite_stops_before_anything_changes(tmp_path):
    result, calls = _run(tmp_path, ["HEAD"], missing_formula="ocrmypdf")
    assert result.returncode == 1
    assert "install-app: ocrmypdf is missing" in result.stderr
    assert "brew install sane-backends ocrmypdf tesseract tesseract-lang" in result.stderr
    _assert_nothing_changed(tmp_path, calls)


def test_unknown_ref_stops_before_anything_changes(tmp_path):
    result, calls = _run(tmp_path, ["v0.0.0-does-not-exist"])
    assert result.returncode == 1
    assert "install-app: no such tag or commit: v0.0.0-does-not-exist" in result.stderr
    _assert_nothing_changed(tmp_path, calls)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_install_app.py -v`
Expected: 3 FAIL (script doesn't exist; `bash` exits 127).

- [ ] **Step 3: Write the script** — `scripts/install-app.sh`, then `chmod +x scripts/install-app.sh`:

```bash
#!/bin/bash
# Installs a scanix500 release as this Mac's copy, separate from the git
# checkout: <install>/venv -> venvs/<version>-<stamp>, the scanix500-menubar
# LaunchAgent, and the scanix500 command on PATH.
# Usage: scripts/install-app.sh <tag>   (e.g. v0.5.0; any git ref works)
set -euo pipefail

REF="${1:-}"
[ -n "$REF" ] || { echo "Usage: $0 <tag>   (e.g. v0.5.0)" >&2; exit 2; }

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INSTALL_DIR="${SCANIX500_INSTALL_DIR:-/Applications/Dossiary/scanix500}"
AGENT_DIR="${SCANIX500_AGENT_DIR:-$HOME/Library/LaunchAgents}"
LOG_FILE="${SCANIX500_LOG:-$HOME/Library/Logs/scanix500.log}"
BIN_LINK="${SCANIX500_BIN_LINK:-/opt/homebrew/bin/scanix500}"
LAUNCHCTL="${LAUNCHCTL:-launchctl}"
BREW="${BREW:-brew}"
LABEL="com.scanix500.menubar"

fail() { echo "install-app: $*" >&2; exit 1; }

# 1. Homebrew prerequisites
for formula in sane-backends ocrmypdf tesseract; do
  "$BREW" list --versions "$formula" > /dev/null 2>&1 \
    || fail "$formula is missing. Install with: brew install sane-backends ocrmypdf tesseract tesseract-lang"
done

# 2. Export the ref; the working copy and its branch are never touched
git -C "$REPO_ROOT" rev-parse --verify --quiet "$REF^{commit}" > /dev/null \
  || fail "no such tag or commit: $REF"
SRC="$(mktemp -d)"
NEW=""
SWAPPED=0
cleanup() {
  rm -rf "$SRC"
  if [ -n "$NEW" ] && [ "$SWAPPED" = 0 ]; then rm -rf "$NEW"; fi
}
trap cleanup EXIT
git -C "$REPO_ROOT" archive "$REF" | tar -x -C "$SRC"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$SRC/pyproject.toml" | head -1)"
[ -n "$VERSION" ] || fail "no version in pyproject.toml at $REF"

# 3. A new environment in its own folder (a venv can't be moved once made)
PYTHON="${PYTHON:-$("$BREW" --prefix)/bin/python3}"
mkdir -p "$INSTALL_DIR/venvs"
NEW="$INSTALL_DIR/venvs/$VERSION-$(date +%Y%m%dT%H%M%S)"
echo "Installing scanix500 $VERSION ($REF) into $NEW"
"$PYTHON" -m venv "$NEW"
SANE_PREFIX="$("$BREW" --prefix sane-backends)"
CPATH="$SANE_PREFIX/include" LIBRARY_PATH="$SANE_PREFIX/lib" \
  "$NEW/bin/pip" install --quiet python-sane
"$NEW/bin/pip" install --quiet "$SRC[menubar]"

# 4. Check it before switching
REPORTED="$("$NEW/bin/scanix500" --version)" || fail "scanix500 --version failed in the new environment"
[ "$REPORTED" = "scanix500 $VERSION" ] \
  || fail "scanix500 --version printed '$REPORTED', expected 'scanix500 $VERSION'"
"$NEW/bin/python" -c "import sane" || fail "python-sane does not load in the new environment"
[ -x "$NEW/bin/scanix500-menubar" ] || fail "scanix500-menubar is missing from the new environment"

# 5. Switch
"$LAUNCHCTL" bootout "gui/$UID/$LABEL" > /dev/null 2>&1 || true
ln -sfn "venvs/$(basename "$NEW")" "$INSTALL_DIR/venv"
SWAPPED=1
echo "$VERSION ($REF)" > "$INSTALL_DIR/VERSION"

# 6. LaunchAgent pointing at the installed copy
mkdir -p "$AGENT_DIR" "$(dirname "$LOG_FILE")"
PLIST="$AGENT_DIR/$LABEL.plist"
cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/venv/bin/scanix500-menubar</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$INSTALL_DIR/venv/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>$LOG_FILE</string>
    <key>StandardErrorPath</key>
    <string>$LOG_FILE</string>
</dict>
</plist>
PLIST
loaded=0
for _ in 1 2 3 4 5; do
  if "$LAUNCHCTL" bootstrap "gui/$UID" "$PLIST" 2>/dev/null; then loaded=1; break; fi
  sleep 1  # bootout can take a moment to finish
done
[ "$loaded" = 1 ] || fail "step 6: launchctl bootstrap gui/$UID $PLIST failed; earlier environments are still in $INSTALL_DIR/venvs"

# 7. The scanix500 command
mkdir -p "$(dirname "$BIN_LINK")"
ln -sfn "$INSTALL_DIR/venv/bin/scanix500" "$BIN_LINK" || fail "step 7: could not link $BIN_LINK"

# 8. Remove the environments no longer in use
for dir in "$INSTALL_DIR"/venvs/*; do
  [ "$dir" = "$NEW" ] || rm -rf "$dir"
done
echo "scanix500 $VERSION ($REF) is installed in $INSTALL_DIR and running."
```

- [ ] **Step 4: Run the tests, then the whole suite**

Run: `.venv/bin/pytest tests/test_install_app.py -v` then `.venv/bin/pytest`
Expected: all PASS. Also `bash -n scripts/install-app.sh` (no output).

- [ ] **Step 5: README section** — insert before `## Run`:

```markdown
## Install as an app on this Mac

To run scanix500 from an installed copy rather than this checkout (so
switching branches here doesn't change the scanner software in use):

    scripts/install-app.sh v0.5.0

It installs that tag into `/Applications/Dossiary/scanix500/` (a new
`venvs/<version>-<time>` folder, with `venv` pointing at it), points the
`com.scanix500.menubar` LaunchAgent there (log:
`~/Library/Logs/scanix500.log`), and links `/opt/homebrew/bin/scanix500` to
it. It checks the new copy (`scanix500 --version`, `import sane`) before
switching; if anything fails up to then, the installed copy keeps running
untouched. Run it again with a newer tag to update. Needs the Homebrew
packages from "Install" above.
```

- [ ] **Step 6: Commit**

```bash
git add scripts/install-app.sh tests/test_install_app.py README.md
git commit -m "scripts/install-app.sh: install a tagged release into /Applications/Dossiary/scanix500"
```

---

### Task 3: `Dossiary.app` launcher (Dossiary repo)

**Files:**
- Create: `packaging/macos/Dossiary.applescript`
- Create: `packaging/macos/build-launcher.sh` (executable)
- Modify: `.gitignore` (add `packaging/macos/build/`)
- Modify: `CLAUDE.md` ("Repository layout" block: add a `packaging/macos/` line)

**Interfaces:**
- Produces: `packaging/macos/build-launcher.sh [destination]` → `packaging/macos/build/Dossiary.app`, copied to `<destination>/Dossiary.app` when given. Used by Task 4.

- [ ] **Step 1: The AppleScript** — `packaging/macos/Dossiary.applescript`:

```applescript
-- Dossiary launcher: opens the dossiary.html next to this app in Chrome or Edge,
-- the browsers whose folder access Dossiary needs. Built by build-launcher.sh.
on run
	set appPath to POSIX path of (path to me)
	set folderPath to do shell script "dirname " & quoted form of appPath
	set htmlPath to folderPath & "/dossiary.html"
	try
		do shell script "test -f " & quoted form of htmlPath
	on error
		display dialog "dossiary.html was not found next to Dossiary.app. Expected: " & htmlPath buttons {"OK"} default button "OK" with icon stop with title "Dossiary"
		return
	end try
	repeat with bundleId in {"com.google.Chrome", "com.microsoft.edgemac"}
		try
			do shell script "open -b " & bundleId & " " & quoted form of htmlPath
			return
		end try
	end repeat
	display dialog "Dossiary needs Google Chrome or Microsoft Edge." buttons {"OK"} default button "OK" with icon stop with title "Dossiary"
end run
```

- [ ] **Step 2: The build script** — `packaging/macos/build-launcher.sh`, then `chmod +x`:

```bash
#!/bin/bash
# Builds Dossiary.app, a launcher that opens the dossiary.html next to it in
# Chrome (or Edge), with dossiary.html's own favicon as its icon.
# Usage: packaging/macos/build-launcher.sh [destination folder]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
BUILD="$HERE/build"
APP="$BUILD/Dossiary.app"

rm -rf "$BUILD"
mkdir -p "$BUILD/icon.iconset"
osacompile -o "$APP" "$HERE/Dossiary.applescript"

# Icon: the SVG favicon embedded in dossiary.html
python3 - "$REPO_ROOT/dossiary.html" "$BUILD/favicon.svg" <<'PY'
import re, sys, urllib.parse
html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'rel="icon" type="image/svg\+xml" href="data:image/svg\+xml,([^"]+)"', html)
if not m:
    sys.exit("build-launcher: no SVG favicon found in dossiary.html")
open(sys.argv[2], "w", encoding="utf-8").write(urllib.parse.unquote(m.group(1)))
PY
qlmanage -t -s 1024 -o "$BUILD" "$BUILD/favicon.svg" > /dev/null 2>&1
[ -f "$BUILD/favicon.svg.png" ] || { echo "build-launcher: qlmanage did not render the icon" >&2; exit 1; }
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$BUILD/favicon.svg.png" --out "$BUILD/icon.iconset/icon_${size}x${size}.png" > /dev/null
  sips -z $((size * 2)) $((size * 2)) "$BUILD/favicon.svg.png" --out "$BUILD/icon.iconset/icon_${size}x${size}@2x.png" > /dev/null
done
iconutil -c icns -o "$APP/Contents/Resources/applet.icns" "$BUILD/icon.iconset"
# osacompile's Assets.car carries the default script icon and wins over applet.icns
rm -f "$APP/Contents/Resources/Assets.car"
plutil -remove CFBundleIconName "$APP/Contents/Info.plist" 2>/dev/null || true
plutil -replace CFBundleIdentifier -string "io.github.aarneaarebye.dossiary.launcher" "$APP/Contents/Info.plist"

codesign --force --deep -s - "$APP"
echo "Built $APP"

if [ $# -ge 1 ]; then
  DEST="$1"
  mkdir -p "$DEST"
  rm -rf "$DEST/Dossiary.app"
  ditto "$APP" "$DEST/Dossiary.app"
  touch "$DEST/Dossiary.app"  # so Finder picks up the new icon
  echo "Copied to $DEST/Dossiary.app"
fi
```

- [ ] **Step 3: Build and check the bundle**

Run: `packaging/macos/build-launcher.sh`
Expected: `Built …/packaging/macos/build/Dossiary.app`. Then:
- `codesign -v packaging/macos/build/Dossiary.app` → no output, exit 0
- `plutil -p packaging/macos/build/Dossiary.app/Contents/Info.plist | grep -E "CFBundleIdentifier|CFBundleIconName"` → only the identifier line, `io.github.aarneaarebye.dossiary.launcher`
- `ls packaging/macos/build/Dossiary.app/Contents/Resources` → `applet.icns`, no `Assets.car`
- Read `packaging/macos/build/favicon.svg.png` (an image) and confirm it shows the green "D" on the dark rounded square.

- [ ] **Step 4: Check both dialogs and the browser path by hand**

Missing file: `mkdir -p /tmp/launcher-check && rm -rf /tmp/launcher-check/* && ditto packaging/macos/build/Dossiary.app /tmp/launcher-check/Dossiary.app && open /tmp/launcher-check/Dossiary.app` → dialog "dossiary.html was not found next to Dossiary.app. Expected: /private/tmp/launcher-check/dossiary.html" (or `/tmp/…`). Dismiss it.
Opens: `cp dossiary.html /tmp/launcher-check/ && open /tmp/launcher-check/Dossiary.app` → a Chrome tab with `file:///…/launcher-check/dossiary.html` and Dossiary's start screen. Close that tab, then `rm -rf /tmp/launcher-check`.
(The "needs Chrome or Edge" dialog can't be checked on this Mac without uninstalling Chrome; it's covered by reading the script.)

- [ ] **Step 5: `.gitignore` and `CLAUDE.md`**

Add the line `packaging/macos/build/` to `.gitignore`. In `CLAUDE.md`'s "Repository layout" code block, add after the `scan_watch.py` line:

```
packaging/macos/         Dossiary.app launcher (AppleScript) and its build
                          script, build-launcher.sh -- see the spec
                          docs/superpowers/specs/2026-10-15-applications-folder-layout-design.md
```

- [ ] **Step 6: Commit**

```bash
git add packaging/macos/Dossiary.applescript packaging/macos/build-launcher.sh .gitignore CLAUDE.md
git commit -m "Dossiary.app launcher: opens the dossiary.html next to it in Chrome or Edge"
```

---

### Task 4: Move over (hands-on, done by the controller with the user)

Not for a subagent: it changes the running system, needs a tag pushed with the user's OK, and a GUI toggle. Run after Tasks 1-3 are merged into each repo's main.

- [ ] **Step 1: Tag scanix500** — ask the user before pushing. In `~/Projects/iX500` on main: `git tag -a v0.5.0 -m "scanix500 0.5.0"`, then (with OK) `git push origin v0.5.0`.
- [ ] **Step 2: Folder and Scan Helper** — `mkdir -p /Applications/Dossiary`. Quit Dossiary Scan Helper (`osascript -e 'quit app "Dossiary Scan Helper"'`), `mv "/Applications/Dossiary Scan Helper.app" /Applications/Dossiary/`, `open "/Applications/Dossiary/Dossiary Scan Helper.app"`. Ask the user to turn its "Start at login" off and on again. Check `curl -s http://127.0.0.1:8766/health` answers.
- [ ] **Step 3: dossiary.html** — `mv /Applications/dossiary.html /Applications/Dossiary/dossiary.html`.
- [ ] **Step 4: scanix500** — `~/Projects/iX500/scripts/install-app.sh v0.5.0`. Then: `cat /Applications/Dossiary/scanix500/VERSION` → `0.5.0 (v0.5.0)`; `scanix500 --version` → `scanix500 0.5.0`; `launchctl print gui/$UID/com.scanix500.menubar | grep -E "state|program"` → running, program under `/Applications/Dossiary/scanix500/venv/`; `curl -s http://127.0.0.1:8765/health` answers.
- [ ] **Step 5: Launcher** — `packaging/macos/build-launcher.sh /Applications/Dossiary` in the Dossiary repo.
- [ ] **Step 6: Check with the user** — open `/Applications/Dossiary/Dossiary.app`: Dossiary opens in Chrome with the recent libraries listed; 📷 Scan lists both helpers; a scan through scanix500 arrives searchable. After the user's next log out/in, both helpers are running.
- [ ] **Step 7: Memory** — update `feedback_install_to_applications.md` to the "Updates from now on" rules in the spec (paths under `/Applications/Dossiary/`, scanix500 via `install-app.sh <tag>`, launcher rebuilt only when its source changes) and its `MEMORY.md` line.
