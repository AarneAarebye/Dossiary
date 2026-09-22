# PDF capture OCR — Design

**Status:** Approved, ready for implementation planning.

## Problem

Capturing an image lets a person click "Run OCR" before saving, which
populates the searchable `ocr_text` database column and — when word-position
data is available — rebuilds the saved file as a searchable PDF (`runOcr()`,
`buildSearchablePdf()`). Capturing a PDF gets neither: the capture form's
OCR button and language selector are hard-disabled for any non-image upload
(`el('run-ocr-btn').disabled = !isImage;`), so a freshly-scanned PDF is saved
with `ocr_text` left `NULL` and no way to search for it until someone
separately opens Edit and clicks "Run OCR" there — which itself only
populates `ocr_text`, never touches the saved file, and was deliberately
built that way since editing is metadata-only.

## Scope

Extend capture-time OCR to also work for PDF uploads, at parity with how it
already works for images: an opt-in button click before Save, not a
zero-click automatic process. Unlike the existing Edit-time PDF OCR path
(text-only, `runOcrForEdit()`), capture-time PDF OCR also rebuilds the saved
file into a searchable PDF — the same outcome an image capture with OCR
already gets — except for PDFs that already contain real, selectable text,
which are left untouched entirely (OCR is skipped, not run and discarded).

Out of scope: any change to `runOcrForEdit()`'s own metadata-only behavior,
any change to how images are OCR'd or built into searchable PDFs, any page-
count cap or size-based automatic/manual threshold, and any attempt to merge
an existing PDF's own real text/vector content with a new text layer rather
than the rasterize-and-overlay approach described below.

## Architecture

### Enabling the button for PDFs

`dossiary.html:7221-7222`'s `el('run-ocr-btn').disabled = !isImage;` /
`el('ocr-lang').disabled = !isImage;` gain a PDF exception — both controls
become enabled whenever the picked file's type is `image/jpeg`, `image/png`,
or `application/pdf`. The file-preview area's `pickedOcrNotAvailablePdf`
message (`dossiary.html:7232`) is removed for the PDF case, since OCR is now
available there.

### Detecting an already-searchable PDF

Before running any OCR, the picked PDF is checked for real, pre-existing
text: `ensurePdfJs()` loads the document, and each page's
`page.getTextContent()` result is checked for a non-trivial amount of real
text (a simple length/word-count threshold, not a sophisticated heuristic —
this only needs to distinguish "this page has actual embedded text" from
"this page is empty except for an image"). If any page has substantial real
text, the whole document is treated as already-digital: OCR is skipped
entirely, a status message says so (a new i18n key, e.g.
`captureOcrPdfAlreadyText`), and the file saves exactly as picked, completely
untouched. This check runs once, synchronously as part of clicking "Run
OCR" — not a separate pre-flight step — so there's no new control or delay
before someone even has the option to try.

### Running OCR across every page

For a PDF that fails the already-has-text check (i.e., needs OCR), the new
capture-time PDF path mirrors `runOcrForEdit()`'s existing PDF branch
(`dossiary.html:7325-7343`) almost exactly, with one addition: it also needs
per-page word-position data, not just page text, since that's what feeds the
searchable-PDF rebuild at Save. For each page: render via the existing
`renderPdfPageToCanvas(pdf, pageNum, 2)` helper, then
`worker.recognize(canvas, {}, { blocks: true })` (matching `runOcr()`'s own
`{blocks: true}` request for images, rather than `runOcrForEdit()`'s plain
`recognize(canvas)`, since capture-time OCR is the one path that needs word
boxes). Each page's recognized words are flattened via the existing
`flattenOcrWords()` and kept in a per-page array; each page's plain text is
joined the same way `runOcrForEdit()` already joins multi-page text
(`pageTexts.join('\n\n').trim()`) into `pendingOcrText`/`el('f-ocr-text')`.
The status line reuses the already-existing `ocrRecognizingPage` i18n key
(`t('ocrRecognizingPage', {page, total})`) for live per-page progress —
no new progress-reporting mechanism needed, since `runOcrForEdit()` already
established this exact pattern.

### Rebuilding the PDF at Save

`buildSearchablePdf(imageDataUrl, imageFormat, dims, words)`
(`dossiary.html:2852-2876`) currently builds a single-page PDF: one
`addImage()` call, one loop of invisible `doc.text()` calls. It's
generalized to accept an array of per-page entries — `buildSearchablePdf(
pages)`, where each entry is `{ dataUrl, dims, words }` — looping
`doc.addPage([dims.width, dims.height])` for every page after the first
(mirroring the constructor's own initial `format: [width, height]` for page
one), then running the existing per-page `addImage()` + invisible-`text()`
loop unchanged for each page's own image and words. Every existing call site
(the image-capture path) passes a single-element array, so no other caller's
behavior changes — this is a widening of the function's contract, not a
new parallel implementation, per the "generalize, don't duplicate" call made
during design.

`saveNewDocument()`'s `canBuildSearchablePdf` condition
(`dossiary.html:7388-7389`, currently
`pendingOcrWords && pendingOcrWords.length && pendingImageDims && (pendingFile.type === 'image/jpeg' || pendingFile.type === 'image/png')`)
gains a PDF branch: when the picked file is a PDF and per-page OCR data
exists (the new per-page words/dims arrays populated by the PDF OCR path
above, all non-empty), Save calls the now-multi-page `buildSearchablePdf()`
with one entry per source page — rendering each page's already-captured
canvas back to a data URL for `addImage()` (the same canvas already
rendered during the OCR pass is reused, not re-rendered a second time).

## Error handling

A `getTextContent()`/pdf.js failure during the already-has-text check falls
back to treating the document as needing OCR (fail open toward attempting
OCR, not toward silently skipping it) — consistent with this app's existing
"best-effort, never silently do nothing" bias elsewhere (e.g. thumbnail
generation failures don't block Save, they just leave no thumbnail).

A Tesseract failure on any page aborts the whole multi-page OCR attempt
immediately — reusing the existing `ocrFailedStatus` message — rather than
saving partial per-page results as if the run had fully succeeded; this
matches the existing single-image `runOcr()`'s own catch-and-report
behavior, just applied to the multi-page case as a whole rather than
per-page.

If OCR completes across every page but finds zero words anywhere,
`canBuildSearchablePdf` naturally evaluates false (no words to build from),
and the document saves as an ordinary, non-rebuilt PDF — identical to
today's behavior when image OCR finds nothing.

Regardless of whether a given PDF ends up rebuilt, `writeOriginalToSubfolder()`
already unconditionally preserves the true original file before any
processing happens (see CLAUDE.md's own "Preserving an original file on
ingestion" note) — this is completely unaffected by this feature and
continues to give every document a safe, untouched original.

## Testing

New Playwright scenarios, added to this repo's existing OCR-related test
coverage: the OCR button/language selector becoming enabled for a PDF
upload (previously disabled); the skip-with-message path for a stubbed PDF
whose `getTextContent()` reports real text; the `ocrRecognizingPage`
progress status appearing and advancing across a stubbed multi-page PDF;
and a successfully-OCR'd multi-page PDF ending up with `searchable_pdf_built
= 1` and a rebuilt file, verified against the generalized
`buildSearchablePdf()`'s new multi-page array signature. Tesseract and
pdf.js are already stubbed in this project's test environment (per this
repo's own established testing conventions — real recognition can't run in
a sandboxed CI-style environment), so these follow the same stubbing
patterns the existing OCR tests already use rather than running real
recognition.
