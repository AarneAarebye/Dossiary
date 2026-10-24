# The scan dialog and photo scans: Format and Paper size

Date: 2026-10-24
Repo: Dossiary (this one). Single file `dossiary.html`; the scan dialog is `openScanDialog()` and
its helpers (see AGENTS.md, "Scanning: the scan dialog and its helpers").

Sub-project 2c of the photo work. The protocol additions (`formats`, `areas`, `format`, `area`, the
size limit, area id `full`, images only from the flatbed) are in dossiary-scan-helper's
`PROTOCOL.md` ("Formats and areas") and implemented by scanix500 0.9.0 (the Pi's 8800F) and the
macOS helper 0.5.0 (local flatbeds, and the Pi's scanners through it). Their design:
`/Users/aarneaarebye/Projects/iX500/docs/superpowers/specs/2026-10-24-photos-protocol-and-8800f-design.md`
and dossiary-scan-helper's `docs/superpowers/specs/2026-10-24-macos-helper-photos-design.md`.

## Goal

The scan dialog lets a person scan a photo: choose JPEG or PNG instead of PDF, and choose the
paper size (the scan area) for any flatbed scan. Everything else about scanning stays as it is,
and a helper that doesn't list `formats` or `areas` (scanix500 before 0.9.0, the macOS helper
before 0.5.0, version 1 scanix500) behaves exactly as today.

Importing JPEG and PNG needs no work: documents can already be images, and "Make searchable"
already turns one into a searchable PDF (`makeDocumentSearchable()`).

## Decisions (with the reasons)

- **Scanned images get the same automatic OCR as scanned PDFs** (the user's choice). With
  `scan_auto_ocr` on, an image from a scan is queued for Dossiary's own OCR and ends up as a
  searchable PDF, original kept. The helpers refuse `ocr` with an image, so the request carries no
  `ocr`; the existing path for a file without `ocrJob` does the rest (`queueScanOcr()` queues a
  row with a NULL `job_id` when the document has no text layer, and the fallback runner calls
  `makeDocumentSearchable()`, which handles images).
- **Resolutions over the helpers' 100-megapixel limit are hidden** (the user's choice) where
  Dossiary knows the area's size; for `full` the helper's refusal message is shown instead.
- **Paper size is sent for PDFs too.** The protocol makes the first area the default, so a flatbed
  that lists areas always gets one, and an A5 PDF from the 8800F is a feature.

## What changes

### Reading the scanner list (`loadHelperScanners()`)

Each scanner gets `formats` (strings in `pdf`, `jpeg`, `png`; default `['pdf']` when the entry has
none or none valid) and `areas` (strings in `full`, `a4`, `a5`, `a6`, `10x15`, `13x18`; default
`[]`). Unknown ids are dropped, like unknown extras. The scanner entry check
(`validHelperScanner()`) is unchanged: an entry without the new fields stays valid.

### The dialog (`renderScanSettings()`, `readScanDialogSettings()`)

- **Format** select, shown when the scanner lists more than one format, labelled by
  `scanFormatPdf`/`scanFormatJpeg`/`scanFormatPng` ("PDF", "JPEG", "PNG"). Default PDF; the
  remembered choice if still offered.
- **Paper size** select, shown when the scanner lists areas, labelled "Whole glass" (`full`),
  "A4", "A5", "A6", "10 × 15 cm", "13 × 18 cm". Default: the first area the scanner lists (or the
  remembered one if still listed). A scanner that lists exactly one area shows no select but still
  sends it.
- **Images only from the flatbed.** With the feeder as source the Format select is hidden and the
  format is `pdf`; going back to the flatbed restores the earlier choice. A scanner with only a
  feeder never shows Format. Paper size is hidden too and no `area` is sent: only a flatbed scan has a scan area.
- **Black & white** is hidden from the Color select while JPEG is chosen (JPEG can't be 1-bit);
  if it was selected, Color falls back to the first remaining mode.
- **Resolutions over the limit are hidden** for the standard areas: pixel count is
  `round(w_mm / 25.4 * dpi) * round(h_mm / 25.4 * dpi)` with a4 210x297, a5 148x210, a6 105x148,
  10x15 100x150, 13x18 130x180, and `MAX_PIXELS` = 100,000,000 (exactly that is allowed). The list
  follows the Paper size select (and the format doesn't matter). If the current resolution drops
  out, the next lower remaining one is selected; if none remains the lowest is kept and the
  helper's refusal message explains. For `full` nothing is filtered (the glass size is the
  helper's to know) and a refusal comes back as the helper's 422 message in the dialog, as any
  other refusal does.
- Two-sided, split and skip-blank are untouched: they are feeder settings, and the Format select
  is hidden for the feeder anyway.

### The request (`buildScanRequest()`)

Version 2 body: `format` is the chosen format (not always `'pdf'`); `area` is added when the
scanner lists areas and the source is the flatbed. `ocr`/`ocrLanguages` are added only when the format is `pdf` (and the existing
conditions hold). Version 1 requests are unchanged.

### Remembering (`scan_last_settings`)

The saved object gets `format` and `area`. On load each is used only if the chosen scanner still
offers it; otherwise the defaults above apply. Old saved settings without them behave as before.

### Results

JPEG and PNG files already go through `decodeScanFiles()`, `writeScanFilesToInbox()` and
`addAllInboxFilesAndShowStatus()`. The file names come from the helper (`.jpg`, `.png`), and
`pages` is 1. Nothing changes there, but the plan includes a check that a scanned image ends as a
searchable PDF through the own-OCR fallback (and, with `scan_auto_ocr` off, stays an image).

### Text

New strings in all seven languages (English, German, Spanish, French, Chinese Simplified and
Traditional, Armenian): `scanDialogFormatLabel` ("Format"), `scanDialogAreaLabel` ("Paper size"),
`scanFormatPdf`, `scanFormatJpeg`, `scanFormatPng`, `scanAreaFull` ("Whole glass"), `scanAreaA4`,
`scanAreaA5`, `scanAreaA6`, `scanArea10x15`, `scanArea13x18`. The i18n coverage test
(`test_i18n_coverage.py`) must stay green. The user guides (seven languages) get a short passage
in their scanning chapter, and AGENTS.md's scanning section gets the new behaviour.

## Testing

Playwright, extending `tests/test_scan_dialog.py` (its `FAKE_HELPERS` fake fetch plays the
helpers; the scanner entries gain `formats` and `areas`; scan responses with image files):
- a scanner without `formats`/`areas` shows neither control and sends `format: 'pdf'` and no `area`;
- Format and Paper size shown for a flatbed scanner with them; their defaults (PDF, first area);
- the request body carries the chosen `format` and `area`, and no `ocr` for an image;
- feeder hides Format and sends `pdf`; switching back restores the choice;
- JPEG hides black & white; PNG keeps it;
- resolutions over the limit disappear for A4 and reappear for 10x15; the current resolution drops
  to the next lower; `full` filters nothing;
- remembered `format`/`area` come back, and are ignored when no longer offered;
- a scanned JPEG lands in the inbox, is added, and gets an OCR row (own OCR) with `scan_auto_ocr`
  on, none with it off.

Manual, with real hardware: a 10x15 JPEG from the Pi's 8800F and from the MF650C through the
macOS helper, into a library, and the searchable-PDF swap on one.

## Risks

1. The own-OCR fallback has only been exercised on PDFs from scans; an image row (`job_id` NULL,
   document is an image file) may need a check in `runOcrJobPass()`/`makeDocumentSearchable()`
   when the file's extension changes from `.jpg` to `.pdf`. The plan verifies this first.
2. The size table is a copy of the protocol's; if a helper's areas change the dialog filters
   wrongly, not dangerously (the helper still refuses). tests pin the pixel counts of three known cases (10x15 at 300, A4 and A5 at 1200 dpi).

## Out of scope

Film/transparency (project 3); custom areas; TIFF; one image file per page from a feeder; letting
the person turn automatic OCR off per scan; changes to the helpers.
