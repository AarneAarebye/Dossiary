# Background OCR for scans — design

Date: 2026-10-11
Status: approved in brainstorming, awaiting spec review

## Goal

A scan should land in the Inbox within seconds, and every scan should end up
searchable without the person doing anything. Today they get one or the
other: scanix500 runs OCR (ocrmypdf, `deu+eng`) before its scan request
answers, so a 3-sheet duplex scan took about 1:45 in the hardware test; the
macOS helper returns plain image PDFs, so its scans need "Make searchable" by
hand; and Dossiary never runs OCR on its own.

Decisions taken in brainstorming:

- Both goals: fast pages *and* automatic OCR, whichever helper scanned.
- The helper does the OCR, after answering (approach B): the best engine on
  each system (ocrmypdf on scanix500, Apple Vision on macOS), no heavy work
  in the browser. Rejected: Dossiary-only OCR with Tesseract.js (weaker
  German recognition, the tab does the work) and keeping OCR inside the scan
  with a progress display (doesn't remove the wait).
- When no helper result comes, Dossiary runs its own OCR as a fallback, so
  every scan ends up searchable.
- Out of scope: progress while the scanner itself is scanning (Dossiary's
  elapsed-time display stays), and a Paper size choice. Both are separate
  follow-ups needing protocol fields of their own.

## 1. Flow

1. Scan: the helper scans, builds plain image PDFs and answers `POST /scan`
   at once, with an `ocrJob` id per file.
2. Dossiary saves the pages to the Inbox (`needs_review`, as today) and the
   dialog closes.
3. The helper runs OCR in the background, one file after another.
4. Dossiary asks `GET /ocr/<job>` every few seconds and shows "Reading text:
   1 of 2 documents…" on the status line.
5. When a searchable PDF arrives, Dossiary swaps it in; the plain scan stays
   as the document's original.

## 2. Protocol (`PROTOCOL.md`, version 2, compatible additions)

All additions are optional: a helper without OCR leaves them out, and a
client that doesn't know them ignores them.

### Scanner entry

```json
{ "id": "sane:ix500", …, "ocr": { "languages": ["deu", "eng", "fra", "spa"] } }
```

`ocr` is present only when the helper can make a searchable PDF for this
scanner's results. `languages` lists Tesseract-style codes (`deu`, `eng`,
`fra`, `spa`, `chi_sim`, `chi_tra`); a helper maps them to its engine's own.

### `POST /scan`

New optional fields: `"ocr": true` and `"ocrLanguages": ["deu", "eng"]`
(default: the helper's own choice). Validation adds: `ocr` not a boolean or
`ocrLanguages` not an array of strings → 400; `ocr: true` for a scanner
without `ocr`, or a language not in its list → 422.

With `ocr: true`, the response is the usual one, answered as soon as the
plain PDFs exist, and each file entry gains `"ocrJob": "<id>"` (URL-safe,
unguessable, at least 128 bits). The files are the plain scan.

### `GET /ocr/<job>`

Needs the pairing token (401 otherwise), like `/scanners` and `/scan`.

| Answer | Meaning |
|---|---|
| `202 {"ok": true, "state": "queued" \| "running", "position": n}` | not done; `position` is the number of jobs ahead of it (0 = running) |
| `200 {"ok": true, "files": [{"name", "pages", "data"}]}` | the searchable PDF, same `name` and `pages` as the plain file |
| `404` | unknown job, or already fetched, or expired |
| `500 {"ok": false, "partial": false, "message"}` | OCR failed; the message is for a person |

Fetching a `200` result deletes it. Results are kept on disk until fetched,
at most 7 days, so a helper restart doesn't lose them. Jobs run one at a
time per helper. A new scan may start while jobs run (the scanner is free);
only a second simultaneous scan gets 409.

### Fake scanner mode and conformance

A new fake scanner, `fake:ocr` (Fake OCR Scanner, flatbed, one page), offers
`ocr: {languages: ["deu", "eng"]}`. With `ocr: true` its file carries an
`ocrJob` that answers 202 for about 2 seconds, then 200 with a PDF whose
page has the text layer `Flatbed page 1`. The conformance suite checks the
field validation, 202 → 200, a second fetch → 404, an unknown job → 404, a
missing token → 401, and that other fake scanners still answer without
`ocrJob`. Every helper in fake mode, scanix500's `scanix500-bridge` and the
reference helper included, gets the eighth fake.

## 3. Helpers

### scanix500

- A scan request with `ocr: true` runs the scan program with `--skip-ocr`,
  so the bridge answers once the plain PDFs exist.
- A queue in the menu bar app runs ocrmypdf on each file in order, page by
  page as today (one failing page doesn't fail the batch), with `--deskew`
  and the requested languages (`deu+eng` by default).
- Jobs and results live in `~/Library/Application Support/scanix500/ocr-jobs/<id>/`,
  deleted when fetched or after 7 days (checked when the app starts and
  after each job).
- The bridge folder's safety-net copy is replaced by the searchable version
  when it's ready.
- The hardware Scan button and menu profiles are unchanged: they still run
  OCR before saving, since nothing fetches their results later.

### macOS helper (dossiary-scan-helper)

- Text recognition with Apple's Vision framework (`VNRecognizeTextRequest`,
  accurate level, `recognitionLanguages` from the request: `de-DE`, `en-US`,
  `fr-FR`, `es-ES`, `zh-Hans`, `zh-Hant`). Vision ships with macOS and builds
  with the Command Line Tools alone.
- The recognized words go into the PDF as invisible text over each word
  (text drawing mode invisible), the technique ocrmypdf uses; the page image
  is copied unchanged.
- Same job model and storage as scanix500, in
  `~/Library/Application Support/dossiary-scan-helper/ocr-jobs/`. No
  straightening.

### Windows helper (later)

Windows has built-in OCR (`Windows.Media.Ocr`) and can follow the same
model. Until it does, it leaves out `ocr` and Dossiary's fallback covers it.

## 4. Dossiary

### After the scan

- Dossiary sends `ocr: true` (and `ocrLanguages` from the OCR language in
  Field Settings, Auto meaning `deu`+`eng`) when the chosen scanner offers
  `ocr` and the new setting is on.
- The plain PDFs are saved to the Inbox as today and the dialog closes.
- For each file with an `ocrJob`, a row goes into a new table `ocr_jobs`
  (`document_id`, `helper_url`, `job_id`, `file_hash` of the delivered file,
  `created_at`, `last_reached_at`), created by `SCHEMA`'s
  `CREATE TABLE IF NOT EXISTS`, so a closed tab or a reopened library picks
  the jobs up again.

### Waiting for results

- While a library is open and jobs exist, Dossiary asks `GET /ocr/<job>`
  every 3 seconds, one job at a time — a read-only request to a helper on
  this computer, like scanner discovery.
- The status line shows "Reading text: 1 of 3 documents…"; a pending
  document's panel and tile show a small "reading text…" label.
- On `200`: the PDF is swapped in with the code "Make searchable" uses
  (`replaceActiveFile()`): the plain scan stays as the original, OCR text is
  filled only if empty (`recordPdfTextLayer()`), sidecar and preview are
  refreshed, and the job row is deleted.
- If the document's active file no longer has the delivered `file_hash`
  (changed by "Edit pages…" or "Combine…"), the result is discarded and the
  fallback runs on the current file.
- Moving the document to the Waste bin deletes its job row.

### Fallback: Dossiary's own OCR

Runs when the helper offers no `ocr`, a job answers `404` or `500`, the
helper hasn't been reachable for 10 minutes (`last_reached_at`), or a result
was discarded. Dossiary queues its own "Make searchable" (Tesseract, the
Field Settings OCR language, Auto by default) for that document, in the
background, one document at a time, with the same status-line display. The
fallback queue is persisted the same way (a job row with `job_id` NULL), so a
closed tab resumes it.

### Setting and scope

- Field Settings gains "Make scans searchable automatically" (`settings` row
  `scan_auto_ocr`), on by default. Off: Dossiary doesn't request helper OCR
  and never runs its own; today's behaviour.
- Only scans. Drag-and-drop and `inbox/` files stay as they are (an existing
  text layer is read; no automatic OCR).

### Tests

`tests/test_scan_dialog.py`'s fake helpers gain OCR jobs; new checks:
`ocr: true` and languages sent only to a scanner offering `ocr`; a job
answering 202 then 200 swapping the file in with the original kept; a
reopened library resuming jobs; 404, 500 and an unreachable helper leading
to the fallback; changed pages discarding the result; the Waste bin
cancelling a job; the setting off sending no `ocr` and running nothing.

## 5. Order of work

Each step is usable on its own and gets its own implementation plan in the
repo it changes:

1. `PROTOCOL.md`, the conformance suite and the reference helper
   (dossiary-scan-helper).
2. Dossiary: requesting OCR, jobs, swap-in and the fallback. Works with the
   reference helper and, through the fallback, with every helper.
3. scanix500: OCR jobs instead of OCR inside the scan.
4. macOS helper: OCR jobs with Vision.
