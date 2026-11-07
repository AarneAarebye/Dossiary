# Import a folder: clearer title and "add to a collection"

Date: 2026-11-07. Scope: the page (`dossiary.html`) only. The Mac and iOS apps have no folder import.

## Problem

1. The Tools entry "Import a folder…" does not say that it also takes back an earlier export (a folder with an `index.csv`), so people do not know they can.
2. A folder import from an export puts the documents into the library, but the collection they were in (or a new one for this batch) has to be rebuilt by hand.

## Decisions (agreed 2026-11-07)

- **Title:** "Import a folder or earlier export…" (Tools menu) and "Import a folder or earlier export" (dialog title). Translated in all 7 languages. The dialog's intro text stays.
- **Collections:** only for folders that have a readable `index.csv` (one with a File column). Folders without one import immediately, exactly as today, with no new step.
- **Which documents join the collection:** only the files that have a row in `index.csv`. Files without a row go to the Inbox for review and are not added.
- **Duplicates:** a file with a row that is skipped because an identical document is already in the library adds that existing document to the collection.
- **Manual collections only.** Smart collections are saved filters and cannot take members.

## Behaviour

Flow today: "Choose folder…" → picker → the import starts at once.

Flow with an `index.csv`: "Choose folder…" → picker → the dialog shows an options panel and waits for "Import":

- A line: "{count} files in this folder are listed in index.csv." (`count` = files in the folder that have a row.)
- Three radio choices under "Add the imported documents to a collection":
  - **No collection** (default).
  - **An existing collection**: a dropdown of the library's manual collections, sorted by name. Disabled, with the radio disabled, when the library has none.
  - **A new collection**: a text field pre-filled with the folder's name.
- "Import" is disabled when "An existing collection" is chosen with nothing selected, when "A new collection" has an empty (trimmed) name, or when the new name equals (ignoring case) the name of an existing manual collection. In that last case an inline note says: "A collection with this name already exists. Choose it under “An existing collection”."
- "Cancel" and the close button leave without importing anything.

After the import loop, if a collection was chosen and at least one document qualifies:

- "A new collection" creates the manual collection with `createManualCollection(name)`; "An existing collection" uses the chosen id.
- `addDocumentsToCollection(id, ids)` adds the added documents and the existing documents behind skipped duplicates.
- No collection is created when nothing qualifies (for example every file lacks a row), so no empty collection is left behind.
- The summary gets the line "Added to the collection “{name}”: {count}".
- If creating or filling the collection fails (a helper returns `null`/`false`), the documents stay imported and the summary shows "The documents were imported, but the collection could not be saved." with the dialog status in the error colour.

Nothing else about the import changes: the folder is only read, the Inbox rule for files without a row, the duplicate skipping, the Person flow hold and the summary lines stay as they are.

## Code changes

- `createReviewDocumentFromFile()`: the duplicate return gains `duplicateOfId: duplicateMatch.id` (`{ id: null, title: null, skippedDuplicate: true, duplicateOfId }`). Other callers ignore it.
- `openImportModal()`: an `#import-options` container; when `index` exists, `askImportCollection(folderName, matchedCount)` renders the panel and resolves with `{mode: 'none'} | {mode: 'existing', id} | {mode: 'new', name}`; the loop collects `memberIds`; the collection step runs after the loop and after the table re-render.
- New strings (English; all 7 languages): `importIndexFound`, `importAddLabel`, `importAddNone`, `importAddExisting`, `importAddNew`, `importNewNamePlaceholder`, `importNameTaken`, `importRunBtn`, `importCountCollection`, `importCollectionFailed`; changed: `toolbarImportFolder`, `importModalTitle`.
- Version 1.59.0 (`APP_VERSION`), README, architecture doc 08, `AGENTS.md` mention, test coverage index.

## Tests

New `tests/test_import_collection.py` (Playwright, same stubs as `test_import_folder.py`):

1. A folder without `index.csv` imports at once; no options panel.
2. A folder with `index.csv`: the panel shows the matched count, "No collection" is the default, and "Import" with it adds no collection.
3. "A new collection": the name is pre-filled with the folder name; after the import the collection exists, holds exactly the files that had a row, and not the loose file.
4. "An existing collection": a second folder import adds to it; documents already in the library (duplicates with a row) are added too.
5. A taken name disables "Import" and shows the note; the dropdown and the radio are disabled when no manual collection exists.
6. Nothing qualifies (the only files lack a row): no collection is created.
7. The title reads "Import a folder or earlier export" in the dialog and Tools menu.

`test_import_folder.py` and `test_i18n_coverage.py` keep passing (the latter checks that all 7 languages have every key).

## Out of scope

Collections for folders without `index.csv`; smart collections; reading collection membership from `index.csv` (Export does not write it); the Mac and iOS apps.
