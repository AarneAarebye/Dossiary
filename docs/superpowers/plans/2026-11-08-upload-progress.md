# Upload progress, step 1 (page 1.64.0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax.

**Goal:** While a shared library's first version uploads to the Pi, the page shows a live line with elapsed time, and a clear done/waiting/problem message.

**Architecture:** Spec `docs/superpowers/specs/2026-11-08-upload-progress-design.md` (read it fully). Extend `pollSyncState()` in `dossiary.html` to read `uploading`, `hubReachable`, `lastError` from the state answer and drive a small `uploadStatus` controller (spinner line, 1 s elapsed ticker, 2 s poll while uploading, done message). Reuse `setStatusLive` and the `.spinner` style.

**Tech Stack:** Vanilla JS single-file page, Playwright (Python) tests in `tests/`, run with `/usr/local/bin/python3` from `tests/`.

## Global Constraints

- Strings in all 7 language blocks (en, es, fr, de, zh-Hans, zh-Hant, hy; Armenian unreviewed; zh-Hant by hand; translate de/fr/es properly); `tests/test_i18n_coverage.py` passes; English short and plain.
- No change to Dossiary Sync; no behaviour change without an admin token or for libraries that are not uploading.
- Untrusted text (library names, `lastError`) shown as text, never HTML.
- Version 1.64.0 in `dossiary.html` `APP_VERSION`, `scan_watch.py` `__version__`, `tests/test_scan_watch_version.py`. README (+ German), architecture note (find the sync/share note), AGENTS.md script count, tests/CLAUDE.md, tests/coverage doc.
- Full suite passes before the final commit. Do not push, tag or release. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_0117epTz6pLGF3vCWxi4JMsL`.

### Task 1: Upload status controller and tests

**Files:** `dossiary.html` (`pollSyncState`, new controller near the sync code, STRINGS), `tests/test_upload_progress.py` (new), docs.

- [ ] **Step 1:** Write `tests/test_upload_progress.py` with the six scenarios of the spec "Tests" (read `tests/test_share_library.py` for how the admin service and token are stubbed; control the clock if the page code allows, otherwise tolerate real time with generous waits).
- [ ] **Step 2:** Run it: fails.
- [ ] **Step 3:** Implement the controller and strings; hook it into `pollSyncState()`; faster polling while uploading; stop on library switch/close; keep the line alive across status replacement while uploading.
- [ ] **Step 4:** New test passes; run test_share_library.py, test_share.py, the sync tests (grep tests for `pollSyncState`/`SYNC_TICK`), test_i18n_coverage.py.
- [ ] **Step 5:** Version, docs, full suite (background, over 10 minutes), commit `feat: live status while a library uploads to the Pi (1.64.0)`.
