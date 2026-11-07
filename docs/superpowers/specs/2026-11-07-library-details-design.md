# Library title and description ("Library details")

Date: 2026-11-07. Scope: the page (`dossiary.html`) only. The Mac app and iPhone/iPad read the same settings in a later step.

## Problem

A library shows only its folder name (for example `Birgit.dossiary`) in the Recent libraries list and in the header. People want a short title and a note that say what the library is.

## Decisions (agreed 2026-11-07)

- Stored **inside the library**, as two rows in the `settings` table of `library.sqlite`, so they travel with the library to other devices. No schema change; an old library without them works unchanged.
- A **title** and a **description** (not one subtitle line).
- Edited in a **Library details…** dialog (Tools menu) and through a **pencil on each Recent libraries entry**.
- Shown in Recent libraries (title, description, folder name) and in the header (title, with the description as tooltip).
- Page first. Mac app and iPhone/iPad later.

## Data

| setting key | meaning | limit |
|---|---|---|
| `library_title` | display title | 60 characters, one line |
| `library_description` | a short note | 300 characters |

- Both are trimmed on save, and runs of whitespace (including line breaks) collapse to one space. Longer input is cut at the limit (the inputs also carry `maxlength`).
- A missing row, an empty value or only whitespace means "not set". The display name is then the folder name.
- Saving an empty title and an empty description writes empty values (like `default_currency`), no delete.

## Behaviour

**Library details dialog** (Tools → "Library details…", button `#library-details-btn`, needs an open library):
- Fields: Title (single line input, `maxlength` 60, hint "Empty: the folder name “{name}” is shown."), Description (textarea, `maxlength` 300), Save and Cancel.
- Save: `ensureCurrentVersion()` first (synced library: reload if a newer version is on disk), both settings written in one `persistDb()`, then the header and the Recent libraries entry update, the dialog closes and the status line says "Library details saved."
- Save is not disabled when nothing changed (no special case).

**Header:** `#sub-label` shows the title, or the folder name when there is no title. The description is its `title` attribute (tooltip); removed when empty. The empty-state text is unchanged and carries no tooltip.

**Recent libraries:** each entry stores `title` and `description` (copied from the library every time it is opened and every time the details are saved). Rendering, per entry:
- Name line: the title, or the folder name when there is no title.
- If a description exists: a second line with it (CSS single line, ellipsis).
- The status line (`recent-lib-status-<id>`, also used for reopen errors) reads "{folder name} · Last opened {date}" when a title is set, and the existing "Last opened {date}" text otherwise.
- A library never opened since this change has no stored details and looks as it does today until its first open.
- A **pencil** button (✎, class `recent-details-btn`, title "Edit title and description") sits before the trash button. Clicking it reconnects the library like clicking the row does (the browser's permission prompt if needed), and once the library is open shows the Library details dialog. It never changes a closed library: if the reconnect is denied or fails, the entry shows the existing error text and no dialog opens. The pencil click must not also trigger the row's own reconnect.

## Code changes

- Tools menu button `#library-details-btn` (after `manage-fields-btn`), wired to `openLibraryDetailsModal()`; shown like the other Tools entries (hidden or disabled with no library open, as they are).
- New: `loadLibraryDetails()` (reads the two settings into `libraryTitle`/`libraryDescription`, called where `loadDefaultCurrency()` is called), `saveLibraryDetails(title, description)`, `cleanLibraryText(value, max)`, `libraryDisplayName()`, `updateLibraryHeader()`, `openLibraryDetailsModal()`.
- `loadDocumentsFromDb()` and `resetAll()`: set the header through `updateLibraryHeader()` / clear the tooltip.
- `recordRecentLibrary(handle, details)`: stores `title`, `description`; the call in the open flow passes the current details. `saveLibraryDetails` updates the matching entry (identity via `isSameEntry`, as `recordRecentLibrary` does) without touching `lastOpenedAt`.
- `renderRecentLibraries()`: new markup and the pencil handler; `reconnectRecentLibrary(id, handle, opts)` gets `opts.afterOpen` (called only when the library opened).
- New strings in all 7 languages (Armenian unreviewed): `toolbarLibraryDetails`, `libraryDetailsTitle`, `libraryDetailsIntro`, `libraryDetailsTitleLabel`, `libraryDetailsTitleHint` (`{name}`), `libraryDetailsDescriptionLabel`, `libraryDetailsSaved`, `recentLibrariesEditDetailsTitle`, `recentLibrariesEditDetailsAriaLabel` (`{name}`), `recentLibrariesFolderAndOpened` (`{folder}`, `{date}`).
- Version 1.60.0, README (+ German), architecture note 04 (navigation) or 07 (new and recent libraries), AGENTS.md, tests index.

## Tests

New `tests/test_library_details.py` (Playwright, same stubs as `test_recent_libraries.py`):
1. Tools has "Library details…"; the dialog opens with empty fields and the folder-name hint.
2. Save a title and a description: the header shows the title, its tooltip the description; both are in `library.sqlite` `settings` (`library_title`, `library_description`).
3. Whitespace and line breaks collapse; text over the limit is cut; a title of only spaces counts as not set.
4. Clearing the title brings back the folder name.
5. After switching library, the Recent libraries entry shows the title, the description line and "{folder} · Last opened …"; an entry without details looks as before.
6. The pencil on a closed library's entry reconnects it, then shows the dialog; saving updates the entry and the library. A denied reconnect (stub `requestPermission` returns `denied`) shows the error and opens no dialog and writes nothing.
7. Clicking the pencil does not also open the library through the row handler a second time (one open).
8. A library with the settings written by another device (seed them) shows them in the header at open and in the list.

`test_recent_libraries.py` and `test_i18n_coverage.py` keep passing.

## Out of scope

Mac app and iPhone/iPad (they will read `library_title`/`library_description` later; the iPhone editing them needs a hub update); a different display title per language; editing the folder name itself; an image or icon for a library.
