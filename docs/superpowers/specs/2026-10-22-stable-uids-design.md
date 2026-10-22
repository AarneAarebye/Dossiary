# Stable IDs for library records — design (two-Mac editing, part 1)

Date: 2026-10-22
Status: approved in brainstorming, awaiting spec review

## Why

Two Macs are going to edit the same library, and part 3 merges versions that diverged while offline. Today every record is identified only by a per-library integer (`documents.id`, `tags.id`, …) that each Mac assigns as `MAX(id)+1`, so two Macs create different documents with the same number. Merging needs an identity that is the same for the same record everywhere and different for different records. This part adds that identity; nothing visible changes.

The whole effort is three parts: 1 stable IDs (this), 2 the Pi as hub with a per-library lease taken at the first change, 3 offline editing with automatic merging. The iPhone app's sync (plan 4) comes after part 2.

## What gets an ID

A `uid TEXT` column on every table whose rows can be created on either Mac: `documents`, `tags`, `people`, `fields`, `collections`, `collection_folders`, `document_splits`, `reminder_snoozes`. Join and lookup tables keyed by these rows (`document_tags`, `document_field_people`, `document_field_values`, `collection_documents`, `document_type_fields`, `field_descriptions`, `settings`, `not_duplicate_groups`, `ocr_jobs`) need none — they're identified by what they connect. Integer ids stay the primary keys; every existing reference keeps working.

## Where IDs come from

- **Existing rows** (in a library opened for the first time with this version) get a **derived** UUID: version 5 (SHA-1, RFC 4122/9562) in a fixed namespace `DOSSIARY_UID_NAMESPACE` (a constant UUID chosen once and never changed), with the name `<table>:<key>`:
  - `documents:<id>`, `tags:<id>`, `people:<id>`, `fields:<id>`, `collections:<id>`, `collection_folders:<id>`
  - `document_splits:<document_id>:<position>`, `reminder_snoozes:<document_id>:<field_id>`
  So two copies of the same library compute identical IDs for the same rows, on any Mac, offline, in any order. (IDs only need to be unique within a library; the same derived ID appearing in two unrelated libraries is harmless.)
- **New rows** get a random version-4 UUID (`crypto.randomUUID()`), in every creation path: capture, Inbox, drag-and-drop, folder import, split documents (Edit pages), combine, inline new field, new tag/person (find-or-create), new collection/folder, splits saved in capture/Edit, reminder snoozes/dismissals, restore paths that insert.
- **Export as library** copies rows with their `uid` unchanged (it already keeps integer ids). **"Copy the setup of"** copies `fields`/`collections`/`collection_folders` rows with their `uid` (they're the same definitions). **Import a folder** creates new documents → new random `uid`.

## When existing rows get their IDs

`migrateStableUids()` runs on every library open (from both `initNewLibrary()` and `loadDb()`, after `applySchemaMigrations()` adds the columns): for each listed table, every row whose `uid` is NULL or empty gets its derived UUID; then a `settings` row `stable_uids_migrated` = `'1'` is written and the database persisted once. It is cheap when nothing is missing, and it also repairs a row inserted without a `uid` by an older version of the app (a library opened on another Mac running an older Dossiary) — that row gets its derived ID, not a random one, so copies still agree.

`uid` columns are added through `SCHEMA_MIGRATIONS` (`ALTER TABLE … ADD COLUMN uid TEXT`), as every added column before. No unique index is added in this part (part 3 decides how to look rows up by `uid`).

## Elsewhere

- The iPhone app reads `library.sqlite` with explicit column lists (extra columns ignored) — unaffected.
- dossiary-sync copies files — unaffected.
- LibraryLifeboat's migration writes libraries without `uid`; the first open in Dossiary fills them in.

## Testing

`tests/test_stable_uids.py` (Playwright, shared stub):
- An old library (no `uid` columns) opened: every row of every listed table has a `uid` in UUID v5 form; the values equal a reference computation (a few hard-coded expected UUIDs, computed independently in Python with `uuid.uuid5`, so the JavaScript derivation is pinned to the standard); `stable_uids_migrated` set.
- The same old library opened twice from two fresh copies → identical `uid`s.
- Reopening changes nothing; a row whose `uid` was cleared gets the same derived value back.
- Each creation path listed above sets a random v4 `uid` on its new rows (one scenario per path family: capture, Inbox/drop, import, split/combine, field/tag/person/collection/folder creation, splits, reminder snooze).
- Export as library keeps `uid`s; Import gives new ones.
The stub (`tests/stub_studio2.js`) must handle `ALTER TABLE … ADD COLUMN uid` and the backfill `UPDATE … SET uid = ? WHERE …` shapes the app sends; extend its regexes rather than working around them.
