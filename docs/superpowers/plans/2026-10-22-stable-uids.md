# Stable IDs — Implementation Plan (two-Mac editing, part 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every record that can be created on either Mac gets a stable `uid`: derived (UUID v5) for existing rows, random (UUID v4) for new ones.

**Architecture:** `uid TEXT` columns added through `SCHEMA_MIGRATIONS`; `migrateStableUids()` backfills derived IDs on every open; a small `newUid()`/`derivedUid(table, key)` pair used by every INSERT of the listed tables.

**Tech Stack:** `dossiary.html` (single file, no build step), Web Crypto (`crypto.subtle.digest('SHA-1')`, `crypto.randomUUID()`), Playwright tests with `tests/stub_studio2.js`.

Spec: `docs/superpowers/specs/2026-10-22-stable-uids-design.md` — read it.

## Global Constraints

- Repo `~/Projects/Paperless/Dossiary`, work in the worktree `.worktrees/stable-uids` (branch `stable-uids`); commit per task; never push; don't bump `APP_VERSION`.
- Tables with `uid`: `documents`, `tags`, `people`, `fields`, `collections`, `collection_folders`, `document_splits`, `reminder_snoozes`. No other table.
- Derived names exactly: `documents:<id>`, `tags:<id>`, `people:<id>`, `fields:<id>`, `collections:<id>`, `collection_folders:<id>`, `document_splits:<document_id>:<position>`, `reminder_snoozes:<document_id>:<field_id>`; UUID v5 per RFC 9562 (SHA-1 of namespace bytes + UTF-8 name, version nibble 5, variant 10), lowercase hyphenated; namespace constant `DOSSIARY_UID_NAMESPACE = 'a3f1c0de-5d0c-4b4e-9e1a-d055a12f0001'` (fixed forever).
- New rows: `crypto.randomUUID()`.
- Follow CLAUDE.md conventions: sql.js calling conventions (`db.run(sql, params)` for writes), additive migrations only, settings marker pattern, the stub extended for new SQL shapes. Every printed test check reads `True` on pass (tests/CLAUDE.md).

### Task 1: Columns, derivation, backfill

**Files:** `dossiary.html` (`SCHEMA` gains `uid TEXT` in the eight `CREATE TABLE`s; `SCHEMA_MIGRATIONS` gains eight `ALTER TABLE … ADD COLUMN uid TEXT`; `DOSSIARY_UID_NAMESPACE`, `async function derivedUid(table, key)`, `function newUid()`, `async function migrateStableUids()` called from `initNewLibrary()` and `loadDb()` right after the schema migrations; `window.__DEBUG_derivedUid` for tests); `tests/stub_studio2.js` (whatever new SQL shapes the backfill needs); `tests/test_stable_uids.py` (migration scenarios); CLAUDE.md architecture note (short: why, derived vs random, the marker, the namespace never changes).

- [ ] Tests first: `__DEBUG_derivedUid('documents', '1')` and `('reminder_snoozes', '3:7')` equal the values Python's `uuid.uuid5(uuid.UUID(NS), name)` gives (compute them in the test with Python and compare); an old seeded library (rows in all eight tables, no `uid`) → every row has the expected derived uid, marker set; two fresh copies of the same seed → identical uids; reopen → unchanged; a cleared uid restored to the same value; a new library (initNewLibrary) also runs it without error.
- [ ] Implement; run `tests/test_stable_uids.py`, `tests/test_i18n_coverage.py` (no new strings expected), and a broad sample of existing tests that open seeded libraries (`test_studio.py`, `test_edit.py`, `test_collections.py`, `test_reminders.py`, `test_splits.py`); commit "Stable uids: columns and derived backfill".

### Task 2: Every creation path sets a uid

**Files:** `dossiary.html` — every `INSERT INTO documents|tags|people|fields|collections|collection_folders|document_splits` and `INSERT OR REPLACE INTO reminder_snoozes` (grep them all; at the time of writing: documents 3, tags 4, people 4, fields 5, collections 3, collection_folders 1, document_splits 2, reminder_snoozes 2) includes `uid` with `newUid()` — except: Export as library's database builder and "Copy the setup of" copy the source row's `uid` unchanged (select it explicitly; a source without the column gives NULL, which the target's own `migrateStableUids()` on first open fills in); a reminder snooze `INSERT OR REPLACE` keeps an existing row's uid (read it first or use the derived value when absent — decide and document; the pair is the natural key, so using `derivedUid('reminder_snoozes', …)` for every write is acceptable and simplest). Tests in `tests/test_stable_uids.py` (creation scenarios) plus checks in `test_export_library.py`/`test_copy_setup.py`/`test_import_folder.py` that the uid is kept/new as the spec says. Update tests/CLAUDE.md's test list.

- [ ] Tests first (one per path family, asserting a v4 uid on each new row); implement; run the new tests and the existing tests of each touched path (capture, inbox, drag-drop, import, page tools/combine, add-field-inline, tags/people, collections/folders, splits, reminders, export library, copy setup); commit "Stable uids: set on every new record".

## Controller checklist
Merge `stable-uids` into main locally; install `dossiary.html` into `/Applications/Dossiary`; open a real library once and check its rows got uids (read the database copy, never modify the user's library by hand).
