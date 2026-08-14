#!/usr/bin/env python3
"""Watches a folder for finished scans and stages them for Dossiary's Inbox.

Standalone companion to dossiary.html -- not loaded by the app itself, and
deliberately has no dependency on it beyond agreeing on one folder name ("inbox").
Run this pointed at wherever your scan software (e.g. ScanSnap Home's "save to
folder" destination) drops finished files, and at the Dossiary library
folder you want them to end up in:

    python3 scan_watch.py --drop-folder ~/Scans --library ~/Documents/MyLibrary

Every stabilized file in --drop-folder is moved into <library>/inbox/. That's the
entire job: no SQLite, no metadata, no document IDs. Dossiary itself reads
that inbox/ folder on library open and shows a "Review" banner; turning a staged
file into an actual document (with defaults you then clean up, same idea as legacy
Mariner Paperless's own ScanSnap watch-folder integration) always requires an
explicit click inside the app. That split exists on purpose: Dossiary is the
library's sole writer to library.sqlite (it loads the whole database into memory
and only writes it back out on an explicit save), so a second process writing rows
into it directly could silently lose work to whichever side saved last. Keeping
this script filesystem-only sidesteps that entirely, and also means it never adds
a document to your archive without you clicking to do so, in keeping with
Dossiary's "no silent writes" design (see CLAUDE.md).
"""

import argparse
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

__version__ = '1.8.1'  # kept in sync with Dossiary's own APP_VERSION and this repo's git tag


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def collision_safe_dest(inbox_dir, name):
    dest = inbox_dir / name
    if not dest.exists():
        return dest
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while True:
        candidate = inbox_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def stage_stable_files(drop_dir, inbox_dir, settle_seconds):
    """Moves any file in drop_dir whose mtime is old enough into inbox_dir.

    Deliberately stateless across calls (no in-memory "seen before" tracking) --
    "stable" just means the file's own last-modified time is at least
    settle_seconds in the past, checked fresh every pass. That makes a single
    --once invocation correct on its own (nothing to warm up across polls), not
    just the continuous loop, at the cost of needing the file's real mtime to be
    trustworthy -- true for a normal scanner/OS write, but keep that in mind if
    this is ever pointed at something that pre-dates or rewrites mtimes oddly.
    """
    now = time.time()
    for path in sorted(drop_dir.iterdir()):
        if not path.is_file() or path.name.startswith('.'):
            continue
        try:
            stat = path.stat()
        except OSError as e:
            log(f"Could not stat {path.name}: {e}")
            continue
        if now - stat.st_mtime < settle_seconds:
            continue  # modified too recently -- probably still being written

        dest = collision_safe_dest(inbox_dir, path.name)
        try:
            shutil.move(str(path), str(dest))
            log(f"Staged {path.name} -> inbox/{dest.name}")
        except OSError as e:
            log(f"Failed to move {path.name}: {e}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--drop-folder', required=True, type=Path, help='Folder your scan software saves finished files into.')
    parser.add_argument('--library', required=True, type=Path, help="A Dossiary library folder (containing library.sqlite); files are staged into its inbox/ subfolder.")
    parser.add_argument('--poll-interval', type=float, default=2.0, help='Seconds between checks of the drop folder (default: 2).')
    parser.add_argument('--settle-seconds', type=float, default=2.0, help='How long a file must stop changing before it is considered fully written (default: 2).')
    parser.add_argument('--once', action='store_true', help='Do a single pass (useful for testing or a cron-style invocation) instead of watching continuously.')
    args = parser.parse_args()

    if not args.drop_folder.is_dir():
        sys.exit(f"--drop-folder does not exist or is not a directory: {args.drop_folder}")
    if not (args.library / 'library.sqlite').is_file():
        log(f"Warning: no library.sqlite found in {args.library} -- is this really a Dossiary library folder?")

    inbox_dir = args.library / 'inbox'
    inbox_dir.mkdir(parents=True, exist_ok=True)

    # If --drop-folder and the library's own inbox/ are the same directory,
    # stage_stable_files() would move each file "into" the folder it's already
    # in, see it there again on the very next poll, and stage it again --
    # forever, piling up _1_1_1... collision suffixes on the same file. resolve()
    # first so this catches the mistake even via a relative path, a trailing
    # slash, or a symlink, not just a literal identical string.
    if args.drop_folder.resolve() == inbox_dir.resolve():
        sys.exit(
            f"--drop-folder and the library's inbox/ folder are the same directory ({inbox_dir}).\n"
            "Point --drop-folder at wherever your scan software saves finished files "
            "(e.g. ScanSnap Home's save-to-folder destination) -- not at the library "
            "folder or its inbox/ subfolder itself."
        )

    log(f"Watching {args.drop_folder} -> {inbox_dir}")
    try:
        while True:
            stage_stable_files(args.drop_folder, inbox_dir, args.settle_seconds)
            if args.once:
                break
            time.sleep(args.poll_interval)
    except KeyboardInterrupt:
        log("Stopped.")


if __name__ == '__main__':
    main()
