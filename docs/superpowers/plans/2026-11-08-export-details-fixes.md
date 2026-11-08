# Export details fixes (1.61.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Close the small review findings left open in 1.61.0 for the export title/description feature.

**Architecture:** Small edits in `openExportModal()` of `dossiary.html`, one new string, two new Playwright scenarios in `tests/test_export_details.py`, a doc fix and a patch version bump.

**Tech Stack:** Vanilla JS single-file page, Playwright (Python) tests run from `tests/` with `/usr/local/bin/python3`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-11-07-export-title-design.md` (behaviour unchanged except as listed here).
- New strings in all 7 languages (en, de, fr, es, it, zh-Hant, hy; Armenian unreviewed); `tests/test_i18n_coverage.py` must pass. New English text is short and plain.
- Version 1.61.1 is kept in sync in `dossiary.html` `APP_VERSION`, `scan_watch.py` `__version__`, `tests/test_scan_watch_version.py`.
- Full suite (all scripts in `tests/`) passes before the final commit. Commit per task. Do not push, tag or release.

---

### Task 1: Page fixes and tests

**Files:**
- Modify: `dossiary.html` (`openExportModal`, STRINGS blocks, CSS)
- Modify: `tests/test_export_details.py`

**Interfaces:**
- Produces: string key `exportDetailsWriteFailed` (English: "The title and description file could not be written."), used in the export summary.

- [ ] **Step 1: Reserve the name always.** In `openExportModal()` change `if(withIndex && (detailsTitle || detailsDescription)) taken.add(EXPORT_DETAILS_FILE);` to `taken.add(EXPORT_DETAILS_FILE);` (an exported document is never named `export-details.json`, because an import skips that name, whether or not a details file is written). Update the comment above it accordingly.
- [ ] **Step 2: Failed details write must not block the summary.** Wrap the details-file write (`dw` create/write/close) in its own try/catch. On failure set a local `detailsWriteFailed = true`; the exported documents and `index.csv` stay counted as successful. Append `exportDetailsWriteFailed` to the final status text (like `detailsSkipped`), escaped, and make the status class `err` in that case. Add the string in all 7 languages (translate properly for de/fr/es/it; zh-Hant by hand; hy best effort).
- [ ] **Step 3: Spacing.** Add a small `margin-top` (match the existing field spacing used elsewhere in modals) so the Title field does not touch the toggles above it. Check by looking at the dialog in a Playwright screenshot saved to the scratchpad.
- [ ] **Step 4: Tests** in `tests/test_export_details.py`, following the file's existing stub style:
  1. HTML special characters (`<b>x</b> & "q"`) in the library title/description: the export dialog prefill shows them as text (input value equals the raw text, no markup injected), and the written `export-details.json` contains them unchanged.
  2. A pre-existing `export-details.json` in the destination: an export with texts overwrites it with the new content; an export with both texts empty leaves the old file untouched.
  3. A document whose export name is `export-details.json` is exported as `export-details (2).json` (or the numbering the existing helper produces), also when both texts are empty.
  4. A failing write of `export-details.json` (stub the destination so only that file's `createWritable` throws): the documents and index.csv are exported, the summary still shows the done text plus the new failure sentence.
- [ ] **Step 5:** Run `/usr/local/bin/python3 test_export_details.py`, `test_export.py`, `test_import_folder.py`, `test_import_collection.py`, `test_i18n_coverage.py` from `tests/`; all pass.
- [ ] **Step 6: Commit** `fix: export details name reserved always, write failure reported, spacing`.

### Task 2: Docs and version 1.61.1

**Files:**
- Modify: `dossiary.html` (`APP_VERSION`), `scan_watch.py`, `tests/test_scan_watch_version.py`, `docs/architecture/08-*.md` (the "1.59.0" note about the collection default: make it "1.59.0–1.60.0"? Only if the sentence at line ~1214 really describes both; otherwise state what is true), `tests/CLAUDE.md` and `tests/coverage/03-tools-export-share-reports-collections.md` (list the four new scenarios), `README.md` / `README.de.md` only if they mention the reserved name or the write behaviour.

- [ ] **Step 1:** Bump the version to 1.61.1 in the three places.
- [ ] **Step 2:** Update the docs above; add to architecture note 08 one sentence each: `export-details.json` is a reserved export name; a failed write of it is reported but does not fail the export.
- [ ] **Step 3:** Run the full suite from `tests/` (one loop over all `test_*.py`, report the count passed); all pass.
- [ ] **Step 4: Commit** `chore: version 1.61.1, docs for the export details fixes`.
