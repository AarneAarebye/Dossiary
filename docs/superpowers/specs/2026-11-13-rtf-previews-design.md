# Previews for RTF documents — design

Date: 2026-11-13. Page version after this change: 1.66.0 (current 1.65.0). Status: approved in conversation (the
user chose "Real first page" and "rtf.js + browser snapshot").

## Why

Most documents in a library migrated from Mariner Paperless ("Meine Dossiers") are RTF files. The page can only
make previews from images and PDFs, so every RTF card in the grid shows "RTF — No preview". The Mac and iOS apps read
the same `thumbnails/<id>.jpg` files, so a preview made by the page shows up there as well.

## What it does

- An RTF document gets a preview of its **first page**, drawn with its fonts, bold/italic, alignment, lists, tables
  and embedded pictures as far as the RTF library supports them.
- The preview is made the same ways as today's: when a document is captured or added from the Inbox, from
  "Regenerate preview", and from the grid's "Create missing previews (N)" button, which now counts RTF documents.
- Nothing is made automatically when a library is opened (unchanged rule in `docs/architecture/02-data-and-fields.md`).
- An RTF that can't be drawn keeps today's "No preview" card.

## How it works

1. **Detection.** `generateThumbnail(file)` gets a third branch after image and PDF: the file is RTF when
   `file.type` is `text/rtf` or `application/rtf`, or `file.name` ends in `.rtf` (case-insensitive). Browsers report
   different types for RTF, hence both checks.
2. **Library.** `ensureRtfJs()` loads rtf.js 3.0.9 (MIT; it bundles its `codepage` dependency) from jsDelivr, a CDN the
   page already uses for Tesseract, the same way `ensurePdfJs()` does: lazy, once, pinned to an exact version. rtf.js
   ships as three bundles loaded in this order: `WMFJS.bundle.min.js`, `EMFJS.bundle.min.js` (about 56 KB each, they
   draw pictures embedded in RTF) and `RTFJS.bundle.min.js` (about 2.1 MB). If one fails to load the branch returns
   `null`.
3. **RTF to HTML.** The file's bytes go to rtf.js, which produces DOM nodes. They are put into a hidden, white,
   A4-sized box (794 × 1123 CSS px, 20 mm margins), black text on white regardless of the page's dark theme. Anything
   below the first page height is clipped.
4. **Pictures.** Images inside the RTF (blob URLs from rtf.js) are turned into data URLs before the snapshot, because
   a snapshot cannot load outside references. WMF/EMF pictures that rtf.js draws as SVG are inlined as they are.
5. **Snapshot.** The box's HTML plus the CSS it needs is wrapped in an SVG `foreignObject`, loaded as an image from a
   data URL and drawn to a canvas, scaled so the longest side is `THUMB_MAX_DIM` (640 px). `canvasToThumbBytes()`
   makes the JPEG bytes as for PDFs and images.
6. **Hook-ups.** `docsMissingPreview()` matches `.rtf` besides `.pdf/.jpg/.jpeg/.png`. `docsWithOlderPreview()` is not
   changed: it compares sizes of existing previews through `createImageBitmap`, which is only relevant for previews
   the page has made itself. An RTF preview the page made is already full size.
7. **One new text.** The existing "Create missing previews (N)", "No preview" and error strings are reused. The only
   new text is the line for rtf.js in the open-source libraries list (`OPEN_SOURCE_LIBRARIES`, key
   `librariesUseRtfJs`), translated in all seven languages.

## Failure behaviour

- Unreadable or malformed RTF, or rtf.js throwing: `generateThumbnail` returns `null` (an expected, non-error
  outcome, as for unsupported types today).
- File larger than 2 MB, or the whole branch taking longer than 10 seconds: `null`.
- Library not reachable (offline): `null` for this run; the document is offered again next time under "Create
  missing previews".
- The bulk job's existing behaviour is unchanged: one document at a time, stoppable, saved every 25, an unreadable
  file is tried again next time.
- No script of the RTF can run: rtf.js builds DOM nodes, not script elements, and the snapshot is an image.
- Fonts missing on this machine fall back to a similar one, so the preview can differ slightly from Word or Pages.

## Spike first

Before the feature code, a throw-away headless-browser check (Playwright, as in `docs/user-guide/capture.py`) runs
rtf.js and the snapshot on a handful of real RTFs of the kind in the library, plus one with an embedded picture and
one with a table. The result is looked at as pictures. If the `foreignObject` snapshot taints the canvas or looks
wrong, the plan switches to html2canvas (also pinned, lazy) and the spec is updated before building.

## Tests and docs

- Playwright test (`tests/`, using the shared browser-API stub): a small RTF fixture gives non-null JPEG bytes of
  the expected size; a broken file and an over-limit file give `null` without an error; `docsMissingPreview` counts an
  `.rtf` document. A pdf.js-style CDN load is already reachable from the suite; the test follows how it handles it.
- `docs/architecture/02-data-and-fields.md`: the sentence "handles two input types only" becomes "image, PDF and
  RTF", with the reason RTF was added and the pinned-version rule for rtf.js.
- `README.md`/`README.de.md`: the known-limitations line about previews, if it names RTF.
- Release: `APP_VERSION` 1.66.0 with the matching tag, as the `cutting-a-release` skill describes.

## Not in this version

- Mac and iOS apps: no change, they read the page's thumbnails. Rendering RTF natively there (for example
  `NSAttributedString`) is a separate idea.
- The detail panel's preview stays hidden behind `SHOW_DOCUMENT_PREVIEW`.
- Other types (DOCX, ODT, RTFD, plain text) and a page count for RTF.
- Several pages: only page one is drawn.

## Spike result

2026-11-13: the foreignObject snapshot works in headless Chromium on the built-in samples (formatted text, embedded
PNG) and on three real RTFs (German tax-letter templates, 10 to 52 KB, one with centred and right-aligned
paragraphs); the canvas is not tainted (`toBlob` succeeds) and text, bold, italic, colour and the picture are
visible, black on white, with the page clipped at the bottom. One caveat: in the built-in sample the minimal table
(`\trowd`/`\cell`) came out as running text ("Cell ACell B"), not a grid, so rtf.js did not lay it out as a table
there; none of the three real files contained a table to check this. A malformed file makes `render` throw
("Not a valid rtf document"), so the caller must catch it and show no preview. The code in Task 2 is the spike's JS.
