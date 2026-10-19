# Export as library, bundled with Dossiary — design

## Goal

Hand selected documents to someone else as something they can open right away:
the exported library plus a copy of `dossiary.html` and short instructions, as a
folder, a `.zip` file, or both. Bundles can be large (gigabytes of scans).

The recipient gets a full, ordinary library: they can browse, search, edit and
add. Nothing is read-only.

## What the person sees

**Export as library** (bulk "More ▾" menu, `openExportLibraryModal()`) gains one
more choice, **What to create** (`export-library-output` radios):

| Value | Label (en) | Result |
|---|---|---|
| `library` (default) | Library only | Today's behaviour: `<Name>.dossiary` in the picked folder |
| `folder` | Library + Dossiary, as a folder | `<Name>/` bundle folder |
| `zip` | Library + Dossiary, as a .zip file | `<Name>.zip` |
| `both` | Both | `<Name>/` and `<Name>.zip` |

Name, Copy/Move and setup (used/all) are unchanged and apply to every output.

### Bundle layout

For the name "Tax 2025":

```
Tax 2025/                  bundle folder (the zip unzips to exactly this)
  dossiary.html            the app, same version as the one exporting
  Tax 2025.dossiary/       the library, identical to "Library only" output
  How to open.txt          instructions
```

The bundle folder's name is the typed name without `.dossiary`
(`libraryFolderName()` minus the extension); the zip is `<that name>.zip`.

### How to open.txt

Plain UTF-8 text in the current UI language; when that isn't English, the
English text follows after a blank line and a `----` separator. Content:

1. If you received a .zip file, unzip it first.
2. Open `dossiary.html` in Google Chrome or Microsoft Edge on a computer
   (Windows, macOS or Linux). Safari, Firefox, iPhone and iPad can't run it.
3. Click "Open library folder" and choose the folder `<Name>.dossiary`.
   Next time it is listed under Recent libraries.

The button name in step 3 is the actual `t('…')` label of `#open-btn` in that
language, so the instructions match what the recipient sees.

### After export

- **Folder or Both:** "Open it" stays and opens the exported library here, as
  today. The library recorded in Recent libraries is the inner
  `<Name>.dossiary`.
- **Zip only:** no "Open it", nothing recorded in Recent libraries. The
  summary names the zip and its size.
- Any zip over 25 MB adds a note: too large for most email; use AirDrop, a
  shared folder or a USB stick.

## How it works

### 1. Getting dossiary.html (before anything is written)

`getDossiaryHtmlForBundle()` returns the file's text or `null`:

1. **Download**: `fetch('https://cdn.jsdelivr.net/gh/AarneAarebye/Dossiary@v' +
   APP_VERSION + '/dossiary.html')`. Accepted only if the response is OK and
   contains `APP_VERSION = '<APP_VERSION>'`. (Checked 2026-10-20: jsDelivr
   serves the tagged file with `access-control-allow-origin: *`, readable from
   a `file://` page.)
2. **Remembered copy**: the *contents* of a dossiary.html chosen earlier,
   stored with its version in IndexedDB (database `dossiary-bundle-source`,
   store `copies`, one record `{id: 'dossiary.html', version, text,
   savedAt}`). The contents, not a file handle: re-reading a stored handle
   needs `requestPermission()`, whose prompt would use up the click that the
   folder picker needs. A stored copy is outdated after an update, which the
   version check below catches.
3. **Ask**: when 1 fails and there is no stored copy, nothing is written; the
   dialog shows a note ("Dossiary couldn't download its own copy (offline, or
   this version isn't released). Choose dossiary.html once — it will be
   remembered — then click Export library again.") and a **Choose
   dossiary.html…** button (`showOpenFilePicker`, `.html`). The chosen file
   is read and stored at once.

A file without `const APP_VERSION = '…'` is refused ("That file isn't
Dossiary."). A stored or chosen copy whose version differs from
`APP_VERSION` asks: "This dossiary.html is version X; you are running Y.
Use it anyway?" (`confirm()`). Declining stops the export before anything is
written.

Order on the Start click: check the name, pick the destination folder
(which needs the click's user activation, so it comes before any network
wait), refuse an existing folder/zip name, then get dossiary.html (download
with a 15 s timeout, else the stored copy), then write. Library only never
contacts the network.

### 2. The folder

The existing export loop writes into `<Bundle>/<Name>.dossiary` instead of
`<picked>/<Name>.dossiary`; then `dossiary.html` and `How to open.txt` are
written into `<Bundle>/`. Refused up front, as today, if `<Bundle>` already
exists in the picked folder (`newLibraryExists` message with the bundle name).

### 3. The zip (`ZipWriter`)

A small built-in writer, no dependency:

- Entries are **stored** (method 0, no compression): scans and PDFs barely
  compress, and it keeps writing linear and fast.
- One `createWritable()` stream on `<Name>.zip`; entries are appended in
  sequence. Each entry's bytes are read whole (as the folder export already
  does), CRC32 computed (table-based, built in), local header + data written.
  Reads may run 4 at a time as today; appends are serialized.
- Central directory and end record at the end. **ZIP64** extra fields and the
  ZIP64 end records are written when any offset/size passes 0xFFFFFFFF or there
  are more than 65 535 entries. The threshold is a variable the tests can lower
  (`window.__DEBUG_setZip64Threshold`).
- Names are UTF-8 with general-purpose flag bit 11 set; paths use `/` and start
  with `<Bundle>/`. Directory entries aren't needed.
- Entry order: library files as they are exported, then `library.sqlite`,
  `dossiary.html`, `How to open.txt`.
- **Zip only** reads straight from the library into the zip; no folder is
  written. **Both** writes the folder first, then zips it from the folder just
  written (same bytes, and the library database is built once).

Refused up front if `<Name>.zip` already exists in the picked folder.

### 4. Errors, Stop, Move

Unchanged rules, extended to the new outputs:

- A document that can't be read is left out and listed; it isn't in the
  library, folder or zip.
- Stop, a write failure, or nothing exported removes everything this run
  created: the bundle folder and/or the zip (`removeEntry`, recursive for the
  folder). An aborted `createWritable()` is `abort()`ed so no partial zip
  appears.
- Move sends the exported documents to the Waste bin only after every chosen
  output was written completely.
- `exportLibraryRunning` blocks closing the dialog for the whole run.

## Text and languages

New strings in all seven `STRINGS` blocks: the four output labels, the
download/choose note and button, the version-mismatch question, zip done/size
lines, the email-size note, and the `How to open.txt` lines. Armenian items go
onto the review page (`hy/build_review.py`); the English goes to the Desktop
for Grammarly. `test_i18n_coverage.py` covers the keys as usual.

## Docs

README.md/README.de.md (Export as library paragraph) and the CLAUDE.md
"Export as library" note. No User Guide mentions Export as library, so none
changes.

## Testing (`tests/test_export_bundle.py`)

The stub fakes `fetch` for the jsDelivr URL and `showOpenFilePicker`.

1. Folder: layout, `dossiary.html` equals the faked download, `How to open.txt`
   in German + English, inner library opens.
2. Zip only: Python `zipfile` lists the expected names, every file's bytes and
   CRC match the source; no folder created; no Recent libraries entry.
3. Both: folder and zip with identical contents.
4. ZIP64: threshold lowered, Python `zipfile` still reads it.
5. UTF-8 names (Armenian and Chinese titles) survive.
6. Download fails → Choose button → chosen file stored; the next Export
   library click uses it, and a later export doesn't ask again.
7. Version mismatch → confirm declined → nothing written.
8. Stop mid-run → no bundle folder, no zip.
9. Move + zip → documents in the Waste bin only after success.
10. Library only: no `fetch` call at all.

## Out of scope

- Compressing the zip.
- Splitting large zips into parts.
- Opening the bundled library automatically on the recipient's side (a page
  can't open a folder without the person picking it).
- A read-only mode for recipients.
