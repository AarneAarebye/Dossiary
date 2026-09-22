# PDF Capture OCR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let someone click "Run OCR" on a PDF upload in the capture form,
the same way they already can for an image — OCR'ing every page and, at
Save, rebuilding the saved file as a multi-page searchable PDF, unless the
PDF already contains real, selectable text (in which case OCR is skipped
entirely and the file saves untouched).

**Architecture:** Generalize the single-page `buildSearchablePdf()` into a
multi-page function taking an array of per-page image+word data, add a new
PDF branch inside `runOcr()` that detects already-searchable PDFs via
pdf.js's `getTextContent()` and otherwise OCRs every page (mirroring
`runOcrForEdit()`'s existing multi-page PDF rendering, but additionally
capturing word-position data), and wire the result into
`saveNewDocument()`'s existing `canBuildSearchablePdf` branch.

**Tech Stack:** Vanilla JS (no framework), Tesseract.js, pdf.js, jsPDF,
Playwright for tests (`tests/test_searchable_pdf.py`,
`tests/stub_studio2.js`).

## Global Constraints

- This is opt-in via the existing "Run OCR" button, not automatic —
  clicking the button is still required, matching how image OCR already
  works. No zero-click automatic OCR.
- A PDF whose pages already contain real, substantial extractable text
  (detected via pdf.js's `page.getTextContent()`) must have OCR skipped
  entirely — the file saves completely untouched, with a status message
  explaining why. Never rasterize-and-rebuild an already-searchable PDF.
- No page-count cap or size threshold — OCR runs across every page
  regardless of count, with a live "page N of M" progress status
  (`t('ocrRecognizingPage', {page, total})`, an existing i18n key — do not
  add a new one for this).
- `buildSearchablePdf()`'s generalization to multiple pages must be a
  **widening of its existing contract**, not a new parallel function — every
  existing image-capture call site becomes a single-element array, reusing
  the same per-page `addImage()` + invisible-`text()` loop and the same two
  documented jsPDF unit gotchas (`hotfixes: ['px_scaling']`; `setFontSize()`
  always takes points, so word heights convert via `* 0.75`).
- A Tesseract failure on any page aborts the whole multi-page OCR attempt via
  the existing `ocrFailedStatus` message — no partial per-page results are
  ever left in `f-ocr-text` or used to build a searchable PDF.
- `writeOriginalToSubfolder()`'s unconditional preservation of the true
  original file is completely unaffected by this plan — do not touch it.
- No change to `runOcrForEdit()`'s own metadata-only behavior, or to how
  images are OCR'd.

---

### Task 1: Capture-time PDF OCR, multi-page searchable-PDF rebuild, tests

**Files:**
- Modify: `dossiary.html`
- Modify: `tests/stub_studio2.js`
- Modify: `tests/test_searchable_pdf.py`

**Interfaces:**
- Consumes: `ensurePdfJs()`, `ensureTesseract()`, `renderPdfPageToCanvas(pdf,
  pageNum, scale)`, `flattenOcrWords(data)`, `writeOriginalToSubfolder()` (all
  already shipped, unchanged).
- Produces: `buildSearchablePdf(pages)` — **changed signature**, now takes an
  array of `{ dataUrl, imageFormat, dims, words }` entries (previously
  `buildSearchablePdf(imageDataUrl, imageFormat, dims, words)` for a single
  page) — this is the one signature change later code in this same task
  must match. A new module-level variable `pendingPdfOcrPages` (array of the
  same per-page shape, or `null`), alongside the existing `pendingFile`/
  `pendingOcrText`/`pendingOcrWords`/`pendingImageDims`.

- [ ] **Step 1: Add the new module-level variable**

Find, near the top of the file (currently `dossiary.html:2479-2482`):

```javascript
  let pendingFile = null;
  let pendingOcrText = '';
  let pendingOcrWords = null;      // flat array of {text, bbox:{x0,y0,x1,y1}} from Tesseract, or null if no OCR run
  let pendingImageDims = null;     // {width, height} in pixels of the picked image, or null for non-images
```

Replace with:

```javascript
  let pendingFile = null;
  let pendingOcrText = '';
  let pendingOcrWords = null;      // flat array of {text, bbox:{x0,y0,x1,y1}} from Tesseract, or null if no OCR run
  let pendingImageDims = null;     // {width, height} in pixels of the picked image, or null for non-images
  let pendingPdfOcrPages = null;   // array of {dataUrl, imageFormat, dims, words} per page (one entry per PDF page), or null if no PDF OCR run
```

- [ ] **Step 2: Generalize `buildSearchablePdf()` to accept multiple pages**

Find the current single-page implementation (currently `dossiary.html:2852-2876`):

```javascript
  async function buildSearchablePdf(imageDataUrl, imageFormat, dims, words){
    const { jsPDF } = await ensureJsPdf();
    const { width, height } = dims;
    const doc = new jsPDF({
      orientation: width > height ? 'landscape' : 'portrait',
      unit: 'px',
      format: [width, height],
      compress: true,
      // Without this, jsPDF's 'px' unit uses a non-1:1 scale factor historically kept
      // for backwards compatibility. This hotfix makes 1 unit == 1 real image pixel,
      // matching the coordinates addImage() and Tesseract's bbox both use.
      hotfixes: ['px_scaling'],
    });
    doc.addImage(imageDataUrl, imageFormat, 0, 0, width, height);

    const PX_TO_PT = 0.75; // setFontSize() always takes points, regardless of document unit
    for(const word of words){
      const { y0, y1, x0 } = word.bbox;
      const wordHeightPx = Math.max(1, y1 - y0);
      doc.setFontSize(wordHeightPx * PX_TO_PT);
      doc.text(word.text, x0, y1, { renderingMode: 'invisible', baseline: 'alphabetic' });
    }

    return doc.output('arraybuffer');
  }
```

Replace with:

```javascript
  // Takes one entry per output page -- { dataUrl, imageFormat, dims, words } --
  // and builds a multi-page PDF, one full-page image background plus an invisible
  // OCR'd text overlay per page. A single-image capture (the original use case)
  // simply passes a one-element array; this is a widening of the function's
  // contract, not a second parallel implementation, so both the image-capture
  // path and the PDF-capture path below share the exact same placement logic
  // and the same two jsPDF unit gotchas documented on each below.
  async function buildSearchablePdf(pages){
    const { jsPDF } = await ensureJsPdf();
    const first = pages[0];
    const doc = new jsPDF({
      orientation: first.dims.width > first.dims.height ? 'landscape' : 'portrait',
      unit: 'px',
      format: [first.dims.width, first.dims.height],
      compress: true,
      // Without this, jsPDF's 'px' unit uses a non-1:1 scale factor historically kept
      // for backwards compatibility. This hotfix makes 1 unit == 1 real image pixel,
      // matching the coordinates addImage() and Tesseract's bbox both use.
      hotfixes: ['px_scaling'],
    });

    const PX_TO_PT = 0.75; // setFontSize() always takes points, regardless of document unit
    const addPageContent = (page) => {
      const { width, height } = page.dims;
      doc.addImage(page.dataUrl, page.imageFormat, 0, 0, width, height);
      for(const word of page.words){
        const { y0, y1, x0 } = word.bbox;
        const wordHeightPx = Math.max(1, y1 - y0);
        doc.setFontSize(wordHeightPx * PX_TO_PT);
        doc.text(word.text, x0, y1, { renderingMode: 'invisible', baseline: 'alphabetic' });
      }
    };

    addPageContent(first);
    for(let i = 1; i < pages.length; i++){
      const page = pages[i];
      doc.addPage([page.dims.width, page.dims.height], page.dims.width > page.dims.height ? 'landscape' : 'portrait');
      addPageContent(page);
    }

    return doc.output('arraybuffer');
  }
```

- [ ] **Step 3: Add the new i18n key to all 6 `STRINGS` blocks**

In `STRINGS.en`, find the line
`captureOcrDoneNoWords: 'Done, but no words with position data were found.',`
(currently `dossiary.html:969`). Immediately after it, insert:

```javascript
      captureOcrPdfAlreadyText: 'This PDF already has real, searchable text — OCR skipped.',
```

In `STRINGS.es`, after its own
`captureOcrDoneNoWords: 'Listo, pero no se encontraron palabras con datos de posición.',`
(currently `dossiary.html:1164`), insert:

```javascript
      captureOcrPdfAlreadyText: 'Este PDF ya tiene texto real y buscable — OCR omitido.',
```

In `STRINGS.fr`, after its own
`captureOcrDoneNoWords: "Terminé, mais aucun mot avec des données de position n'a été trouvé.",`
(currently `dossiary.html:1359`), insert:

```javascript
      captureOcrPdfAlreadyText: 'Ce PDF contient déjà du texte réel et interrogeable — OCR ignoré.',
```

In `STRINGS.de`, after its own
`captureOcrDoneNoWords: 'Fertig, aber es wurden keine Wörter mit Positionsdaten gefunden.',`
(currently `dossiary.html:1554`), insert:

```javascript
      captureOcrPdfAlreadyText: 'Dieses PDF enthält bereits echten, durchsuchbaren Text — OCR übersprungen.',
```

In `STRINGS['zh-Hans']`, after its own
`captureOcrDoneNoWords: '完成，但未找到带位置数据的单词。',` (currently
`dossiary.html:1749`), insert:

```javascript
      captureOcrPdfAlreadyText: '此 PDF 已包含真实的可搜索文本 —— 已跳过 OCR。',
```

In `STRINGS['zh-Hant']`, after its own
`captureOcrDoneNoWords: '完成，但未找到帶位置數據的單詞。',` (currently
`dossiary.html:2039`), insert (a straight script conversion of the zh-Hans
text above, matching this repo's established zh-Hant derivation
convention):

```javascript
      captureOcrPdfAlreadyText: '此 PDF 已包含真實的可搜索文本 —— 已跳過 OCR。',
```

- [ ] **Step 4: Enable the OCR button/selector and remove the "not available" preview note for PDFs**

Find, inside `handlePickedFile(file)` (currently `dossiary.html:7215-7244`):

```javascript
  function handlePickedFile(file){
    pendingFile = file;
    pendingOcrWords = null;
    pendingImageDims = null;
    el('save-doc-btn').disabled = false;
    const isImage = file.type.startsWith('image/');
    el('run-ocr-btn').disabled = !isImage;
    el('ocr-lang').disabled = !isImage;

    const previewArea = el('file-preview-area');
    if(isImage){
      const url = URL.createObjectURL(file);
      const pdfNote = (file.type === 'image/jpeg' || file.type === 'image/png')
        ? t('pickedOcrPdfNote')
        : t('pickedOcrOtherImageNote');
      previewArea.innerHTML = `<div class="file-preview"><img src="${url}" alt="${t('sharedDocumentPreviewAlt')}"/><div><div class="doc-title">${escapeHtml(file.name)}</div><div class="doc-sub">${t('pickedFileSizeKb', {size: (file.size/1024).toFixed(0)})}</div><div class="doc-sub">${pdfNote}</div></div></div>`;
    }else{
      previewArea.innerHTML = `<div class="file-preview"><div class="file-icon">${escapeHtml(file.name.split('.').pop().toUpperCase())}</div><div><div class="doc-title">${escapeHtml(file.name)}</div><div class="doc-sub">${t('pickedFileSizeKb', {size: (file.size/1024).toFixed(0)})}${file.type === 'application/pdf' ? t('pickedOcrNotAvailablePdf') : ''}</div><div class="doc-sub" id="f-page-count"></div></div></div>`;
      if(file.type === 'application/pdf'){
        // Fire-and-forget: don't block showing the rest of the preview on this.
        // Guarded by pendingFile === file so a fast pick-another-file doesn't let a
        // stale count land on the new file's preview after this one resolves late.
        getPdfPageCount(file).then(count => {
          const countEl = el('f-page-count');
          if(countEl && count != null && pendingFile === file) countEl.textContent = count === 1 ? t('sharedPageCountSingular', {count}) : t('sharedPageCountPlural', {count});
        });
      }
    }
    if(!el('f-title').value) el('f-title').value = file.name.replace(/\.[^.]+$/, '');
  }
```

Replace with:

```javascript
  function handlePickedFile(file){
    pendingFile = file;
    pendingOcrWords = null;
    pendingImageDims = null;
    pendingPdfOcrPages = null;
    el('save-doc-btn').disabled = false;
    const isImage = file.type.startsWith('image/');
    const isPdf = file.type === 'application/pdf';
    el('run-ocr-btn').disabled = !isImage && !isPdf;
    el('ocr-lang').disabled = !isImage && !isPdf;

    const previewArea = el('file-preview-area');
    if(isImage){
      const url = URL.createObjectURL(file);
      const pdfNote = (file.type === 'image/jpeg' || file.type === 'image/png')
        ? t('pickedOcrPdfNote')
        : t('pickedOcrOtherImageNote');
      previewArea.innerHTML = `<div class="file-preview"><img src="${url}" alt="${t('sharedDocumentPreviewAlt')}"/><div><div class="doc-title">${escapeHtml(file.name)}</div><div class="doc-sub">${t('pickedFileSizeKb', {size: (file.size/1024).toFixed(0)})}</div><div class="doc-sub">${pdfNote}</div></div></div>`;
    }else{
      previewArea.innerHTML = `<div class="file-preview"><div class="file-icon">${escapeHtml(file.name.split('.').pop().toUpperCase())}</div><div><div class="doc-title">${escapeHtml(file.name)}</div><div class="doc-sub">${t('pickedFileSizeKb', {size: (file.size/1024).toFixed(0)})}</div><div class="doc-sub" id="f-page-count"></div></div></div>`;
      if(isPdf){
        // Fire-and-forget: don't block showing the rest of the preview on this.
        // Guarded by pendingFile === file so a fast pick-another-file doesn't let a
        // stale count land on the new file's preview after this one resolves late.
        getPdfPageCount(file).then(count => {
          const countEl = el('f-page-count');
          if(countEl && count != null && pendingFile === file) countEl.textContent = count === 1 ? t('sharedPageCountSingular', {count}) : t('sharedPageCountPlural', {count});
        });
      }
    }
    if(!el('f-title').value) el('f-title').value = file.name.replace(/\.[^.]+$/, '');
  }
```

(This drops the now-obsolete `pickedOcrNotAvailablePdf` interpolation entirely — OCR is available for PDFs now, so the note no longer applies. The `pickedOcrNotAvailablePdf` i18n key itself is left in place, unused, across all 6 languages — matching this app's established precedent for orphaned i18n keys, e.g. `scanBridgeNotConfigured`/`scanProfileNotConfigured` noted elsewhere in `CLAUDE.md`.)

- [ ] **Step 5: Add the PDF branch to `runOcr()`**

Find the current full function (currently `dossiary.html:7246-7277`):

```javascript
  async function runOcr(){
    if(!pendingFile) return;
    const lang = el('ocr-lang').value;
    const ocrStatusEl = el('ocr-status');
    el('run-ocr-btn').disabled = true;
    ocrStatusEl.innerHTML = '<span class="spinner"></span> ' + t('ocrLoadingEngine');
    try{
      const Tesseract = await ensureTesseract();
      ocrStatusEl.innerHTML = '<span class="spinner"></span> ' + t('ocrRecognizing');
      const worker = await Tesseract.createWorker(lang.split('+'));
      // Request the {blocks:true} output specifically -- by default Tesseract.js v5+
      // only returns plain text, not the per-word bounding boxes a searchable PDF needs.
      const { data } = await worker.recognize(pendingFile, {}, { blocks: true });
      await worker.terminate();
      pendingOcrText = data.text || '';
      el('f-ocr-text').value = pendingOcrText;

      pendingOcrWords = flattenOcrWords(data);
      const dataUrl = await fileToDataUrl(pendingFile);
      pendingImageDims = await loadImageDimensions(dataUrl);

      ocrStatusEl.textContent = pendingOcrWords.length
        ? (pendingOcrWords.length === 1
          ? t('captureOcrDoneWordsSingular', {count: pendingOcrWords.length})
          : t('captureOcrDoneWordsPlural', {count: pendingOcrWords.length}))
        : t('captureOcrDoneNoWords');
    }catch(e){
      ocrStatusEl.textContent = t('ocrFailedStatus', {error: e.message});
    }finally{
      el('run-ocr-btn').disabled = false;
    }
  }
```

Replace with:

```javascript
  async function runOcr(){
    if(!pendingFile) return;
    const lang = el('ocr-lang').value;
    const ocrStatusEl = el('ocr-status');
    el('run-ocr-btn').disabled = true;
    try{
      if(pendingFile.type === 'application/pdf'){
        ocrStatusEl.innerHTML = '<span class="spinner"></span> ' + t('ocrLoadingPdf');
        const pdfjsLib = await ensurePdfJs();
        const buf = await pendingFile.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data: buf }).promise;

        // Skip OCR entirely for a PDF that already has real, selectable text --
        // rebuilding it as a rasterized image-plus-text-layer would only degrade
        // an already-searchable document for no benefit. A simple length check is
        // enough here; this only needs to distinguish "this page has real embedded
        // text" from "this page is an image with nothing behind it", not classify
        // exactly how much text there is.
        let hasRealText = false;
        try{
          for(let pageNum = 1; pageNum <= pdf.numPages; pageNum++){
            const page = await pdf.getPage(pageNum);
            const textContent = await page.getTextContent();
            const pageText = textContent.items.map(item => item.str || '').join('').trim();
            if(pageText.length >= 20){ hasRealText = true; break; }
          }
        }catch(e){
          // Fail open toward attempting OCR rather than silently skipping it if the
          // text-content check itself throws.
          hasRealText = false;
        }

        if(hasRealText){
          pendingPdfOcrPages = null;
          ocrStatusEl.textContent = t('captureOcrPdfAlreadyText');
          return;
        }

        const Tesseract = await ensureTesseract();
        const worker = await Tesseract.createWorker(lang.split('+'));
        const pages = [];
        const pageTexts = [];
        for(let pageNum = 1; pageNum <= pdf.numPages; pageNum++){
          ocrStatusEl.innerHTML = '<span class="spinner"></span> ' + t('ocrRecognizingPage', {page: pageNum, total: pdf.numPages});
          const canvas = await renderPdfPageToCanvas(pdf, pageNum, 2);
          // Request the {blocks:true} output specifically -- capture-time OCR needs
          // per-word bounding boxes for the searchable-PDF rebuild below, unlike
          // runOcrForEdit()'s own PDF path, which only needs plain text.
          const { data } = await worker.recognize(canvas, {}, { blocks: true });
          pageTexts.push(data.text || '');
          pages.push({
            dataUrl: canvas.toDataURL('image/png'),
            imageFormat: 'PNG',
            dims: { width: canvas.width, height: canvas.height },
            words: flattenOcrWords(data),
          });
        }
        await worker.terminate();

        pendingOcrText = pageTexts.join('\n\n').trim();
        el('f-ocr-text').value = pendingOcrText;
        pendingPdfOcrPages = pages;

        const totalWords = pages.reduce((sum, p) => sum + p.words.length, 0);
        ocrStatusEl.textContent = totalWords
          ? (totalWords === 1
            ? t('captureOcrDoneWordsSingular', {count: totalWords})
            : t('captureOcrDoneWordsPlural', {count: totalWords}))
          : t('captureOcrDoneNoWords');
        return;
      }

      ocrStatusEl.innerHTML = '<span class="spinner"></span> ' + t('ocrLoadingEngine');
      const Tesseract = await ensureTesseract();
      ocrStatusEl.innerHTML = '<span class="spinner"></span> ' + t('ocrRecognizing');
      const worker = await Tesseract.createWorker(lang.split('+'));
      // Request the {blocks:true} output specifically -- by default Tesseract.js v5+
      // only returns plain text, not the per-word bounding boxes a searchable PDF needs.
      const { data } = await worker.recognize(pendingFile, {}, { blocks: true });
      await worker.terminate();
      pendingOcrText = data.text || '';
      el('f-ocr-text').value = pendingOcrText;

      pendingOcrWords = flattenOcrWords(data);
      const dataUrl = await fileToDataUrl(pendingFile);
      pendingImageDims = await loadImageDimensions(dataUrl);

      ocrStatusEl.textContent = pendingOcrWords.length
        ? (pendingOcrWords.length === 1
          ? t('captureOcrDoneWordsSingular', {count: pendingOcrWords.length})
          : t('captureOcrDoneWordsPlural', {count: pendingOcrWords.length}))
        : t('captureOcrDoneNoWords');
    }catch(e){
      ocrStatusEl.textContent = t('ocrFailedStatus', {error: e.message});
    }finally{
      el('run-ocr-btn').disabled = false;
    }
  }
```

- [ ] **Step 6: Wire the PDF branch into `saveNewDocument()`**

Find, inside `saveNewDocument()` (currently `dossiary.html:7386-7412`):

```javascript
    try{
      const id = nextDocId++;
      const canBuildSearchablePdf = pendingOcrWords && pendingOcrWords.length && pendingImageDims
        && (pendingFile.type === 'image/jpeg' || pendingFile.type === 'image/png');

      let filePathForDb, sidecarBaseName;

      const baseName = safeFilename((el('f-title').value.trim() || pendingFile.name.replace(/\.[^.]+$/, '')), 'document');
      // Preserve the untouched original from the moment the document is added,
      // regardless of file type or whether a searchable PDF gets built below.
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, pendingFile);
      let searchablePdfBuilt = 0;

      if(canBuildSearchablePdf){
        const imageFormat = pendingFile.type === 'image/jpeg' ? 'JPEG' : 'PNG';
        const dataUrl = await fileToDataUrl(pendingFile);
        const pdfBytes = await buildSearchablePdf(dataUrl, imageFormat, pendingImageDims, pendingOcrWords);

        const processedName = `${id}_${baseName}.pdf`;
        const processedHandle = await filesDirHandle.getFileHandle(processedName, { create: true });
        const processedWritable = await processedHandle.createWritable();
        await processedWritable.write(pdfBytes);
        await processedWritable.close();

        filePathForDb = `files/${processedName}`;
        sidecarBaseName = `${id}_${baseName}`;
        searchablePdfBuilt = 1;
      }else{
```

Replace with:

```javascript
    try{
      const id = nextDocId++;
      const isImageWithOcr = pendingOcrWords && pendingOcrWords.length && pendingImageDims
        && (pendingFile.type === 'image/jpeg' || pendingFile.type === 'image/png');
      const isPdfWithOcr = pendingFile.type === 'application/pdf' && pendingPdfOcrPages && pendingPdfOcrPages.length
        && pendingPdfOcrPages.some(p => p.words.length);
      const canBuildSearchablePdf = isImageWithOcr || isPdfWithOcr;

      let filePathForDb, sidecarBaseName;

      const baseName = safeFilename((el('f-title').value.trim() || pendingFile.name.replace(/\.[^.]+$/, '')), 'document');
      // Preserve the untouched original from the moment the document is added,
      // regardless of file type or whether a searchable PDF gets built below.
      const originalFilePathForDb = await writeOriginalToSubfolder(id, baseName, pendingFile);
      let searchablePdfBuilt = 0;

      if(canBuildSearchablePdf){
        let pdfBytes;
        if(isPdfWithOcr){
          pdfBytes = await buildSearchablePdf(pendingPdfOcrPages);
        }else{
          const imageFormat = pendingFile.type === 'image/jpeg' ? 'JPEG' : 'PNG';
          const dataUrl = await fileToDataUrl(pendingFile);
          pdfBytes = await buildSearchablePdf([{ dataUrl, imageFormat, dims: pendingImageDims, words: pendingOcrWords }]);
        }

        const processedName = `${id}_${baseName}.pdf`;
        const processedHandle = await filesDirHandle.getFileHandle(processedName, { create: true });
        const processedWritable = await processedHandle.createWritable();
        await processedWritable.write(pdfBytes);
        await processedWritable.close();

        filePathForDb = `files/${processedName}`;
        sidecarBaseName = `${id}_${baseName}`;
        searchablePdfBuilt = 1;
      }else{
```

Do not change anything in the `else{...}` branch below this point, or anything after it — only the lines shown above change.

- [ ] **Step 7: Extend the shared test stub with `getTextContent()`**

In `tests/stub_studio2.js`, find pdf.js's fake `getPage()` (currently
around line 373-382):

```javascript
        getPage: async (n) => ({
          getViewport: (opts2) => ({ width: 200 * (opts2.scale || 1), height: 260 * (opts2.scale || 1) }),
          render: (renderCtx) => ({
            promise: (async () => {
              const ctx = renderCtx.canvasContext;
              ctx.fillStyle = '#3355ff';
              ctx.fillRect(0, 0, renderCtx.viewport.width, renderCtx.viewport.height);
            })(),
          }),
        }),
```

Replace with:

```javascript
        getPage: async (n) => ({
          getViewport: (opts2) => ({ width: 200 * (opts2.scale || 1), height: 260 * (opts2.scale || 1) }),
          // Controllable via window.__STUB_PDF_HAS_REAL_TEXT (default falsy/false) --
          // lets a test simulate a PDF that already has real embedded text, without
          // affecting any existing test that never sets this flag (they all continue
          // to see empty text content, exactly as before this was added).
          getTextContent: async () => ({
            items: window.__STUB_PDF_HAS_REAL_TEXT ? [{ str: 'This PDF already has real embedded text content in it.' }] : [],
          }),
          render: (renderCtx) => ({
            promise: (async () => {
              const ctx = renderCtx.canvasContext;
              ctx.fillStyle = '#3355ff';
              ctx.fillRect(0, 0, renderCtx.viewport.width, renderCtx.viewport.height);
            })(),
          }),
        }),
```

- [ ] **Step 8: Add new scenarios to `tests/test_searchable_pdf.py`**

Find the end of the file:

```python
        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

Insert three new scenarios immediately before that block. First, fix this
file's own route handler, which is currently missing the `'pdf.js' in url`
check every other PDF-using test file already has (find, near the top of
the file):

```python
        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
```

Replace with:

```python
        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
```

Then add the new scenarios themselves:

```python
        # === Scenario: a PDF that already has real, selectable text -- OCR is
        # skipped entirely, and the file saves completely untouched ===
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = true;")
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('already_text.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 already has text")
        await page.set_input_files('#file-input', 'already_text.pdf')
        await page.wait_for_timeout(150)

        run_ocr_enabled_for_pdf = not await page.locator('#run-ocr-btn').is_disabled()
        print("Run OCR button is enabled for a PDF upload:", run_ocr_enabled_for_pdf)

        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(300)
        already_text_status = await page.locator('#ocr-status').inner_text()
        print("status for a PDF that already has real text:", already_text_status)

        await page.fill('#f-title', 'Already Searchable PDF')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        db_state_2 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc2 = [d for d in db_state_2['documents'] if d['id'] == 2][0]
        print("already-searchable PDF was NOT rebuilt (searchable_pdf_built should be 0):", doc2.get('searchable_pdf_built'))
        print("already-searchable PDF's ocr_text is empty (OCR never ran):", not doc2.get('ocr_text'))

        # === Scenario: a scanned (no real text) multi-page PDF gets OCR'd page by
        # page and rebuilt into a multi-page searchable PDF ===
        await page.evaluate("window.__STUB_PDF_HAS_REAL_TEXT = false;")
        await page.evaluate("window.__STUB_PDF_NUM_PAGES = 3;")
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('scanned_multipage.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 scanned multipage")
        await page.set_input_files('#file-input', 'scanned_multipage.pdf')
        await page.wait_for_timeout(150)

        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(500)
        multipage_status = await page.locator('#ocr-status').inner_text()
        print("status after OCR'ing a 3-page scanned PDF:", multipage_status)
        multipage_ocr_text = await page.locator('#f-ocr-text').input_value()
        print("OCR text combines all 3 pages:", multipage_ocr_text.count('Hello World') == 3)

        await page.fill('#f-title', 'Scanned Multipage PDF')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        jspdf_calls_multipage = await page.evaluate("window.__JSPDF_CALLS")
        addimage_calls = [c for c in jspdf_calls_multipage if c['type'] == 'addImage']
        addpage_present = any(c['type'] == 'construct' for c in jspdf_calls_multipage)
        print("jsPDF got one addImage call per page (3):", len(addimage_calls) == 3)

        db_state_3 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc3 = [d for d in db_state_3['documents'] if d['id'] == 3][0]
        print("scanned multi-page PDF was rebuilt (searchable_pdf_built should be 1):", doc3.get('searchable_pdf_built'))
        print("scanned multi-page PDF's ocr_text was populated:", bool(doc3.get('ocr_text')))

        # === Scenario: a scanned single-page PDF with no OCR run at all still
        # saves normally, with the OCR button available but never clicked ===
        await page.evaluate("window.__STUB_PDF_NUM_PAGES = 1;")
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('unocred.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 never ocred")
        await page.set_input_files('#file-input', 'unocred.pdf')
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Never OCRd PDF')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        db_state_4 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc4 = [d for d in db_state_4['documents'] if d['id'] == 4][0]
        print("a PDF saved without ever clicking Run OCR is not rebuilt:", doc4.get('searchable_pdf_built') == 0)
        print("a PDF saved without ever clicking Run OCR has no ocr_text:", not doc4.get('ocr_text'))

```

- [ ] **Step 9: Run the test and verify it passes**

Run: `cd tests && python3 test_searchable_pdf.py`
Expected: every `print()` line shows `True` (or the expected non-boolean
value where noted), and the final `JS ERRORS: []` line is empty.

- [ ] **Step 10: Run the static i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: passes cleanly — confirms the new key exists in all 6 languages
with identical key sets.

- [ ] **Step 11: Commit**

```bash
git add dossiary.html tests/stub_studio2.js tests/test_searchable_pdf.py
git commit -m "feat: run OCR and build a multi-page searchable PDF for scanned PDF captures"
```

---

### Task 2: Documentation — CLAUDE.md and tests/CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `tests/CLAUDE.md`

**Interfaces:**
- Consumes: the parameterized `buildSearchablePdf(pages)` and capture-time
  PDF OCR from Task 1 (documentation only — no code in this task).
- Produces: nothing consumed by a later task; this plan's last task.

- [ ] **Step 1: Update the "Searchable PDF generation" note's opening line**

In `CLAUDE.md`, find:

```
- **Searchable PDF generation** (JPEG/PNG only): `runOcr()` requests
```

Replace with:

```
- **Searchable PDF generation** (JPEG/PNG images, and — as of the
  2026-09-22 amendment below — scanned PDFs too): `runOcr()` requests
```

- [ ] **Step 2: Append a new paragraph documenting the PDF amendment**

In `CLAUDE.md`, find the end of the "Searchable PDF generation" bullet —
its last paragraph currently ends (around the lines just before
`- **Preserving an original file on ingestion**`):

```
  - When a searchable PDF is built, the *processed* file is the generated
    PDF (`file_path`), and the *original* upload is preserved untouched in
    a subfolder next to it (`original_file_path`) — mirroring the layout
    `migrate_to_new_library.py` produces for migrated documents and that
    Mariner Paperless itself used. See "Preserving an original file on
    ingestion" below for what happens when a searchable PDF *isn't* built.
- **Preserving an original file on ingestion** (`writeOriginalToSubfolder()`,
```

Insert a new paragraph right after that last bullet point, before the next
top-level bullet:

```
  **PDF capture OCR (2026-09-22 amendment)**: the capture form's "Run OCR"
  button and language selector, previously hard-disabled for any non-image
  upload, now also work for PDFs — an opt-in click before Save, at parity
  with images, not an automatic zero-click process. Clicking it on a PDF
  first checks every page for real, pre-existing text via pdf.js's
  `page.getTextContent()`; if any page has substantial real text, the whole
  document is treated as already-searchable and OCR is skipped entirely —
  the file saves completely untouched, since rebuilding an already-digital
  PDF through the rasterize-and-overlay technique below would only degrade
  it for no benefit. Otherwise, every page is rendered via
  `renderPdfPageToCanvas()` (the same helper `runOcrForEdit()` already
  uses) and OCR'd individually with `{blocks: true}` — unlike
  `runOcrForEdit()`'s own PDF path, which only needs plain text, capture-time
  OCR also needs each page's word-position data, since it feeds the
  searchable-PDF rebuild at Save. `buildSearchablePdf()` itself was
  generalized from a single-page function to `buildSearchablePdf(pages)`,
  taking an array of `{dataUrl, imageFormat, dims, words}` entries and
  looping `addPage()` for entries after the first — every existing
  image-capture call site now passes a single-element array, reusing the
  exact same per-page placement logic and the same two jsPDF unit gotchas
  documented above, rather than a second parallel implementation. The
  resulting rebuilt PDF is, necessarily, a rasterized copy of the original
  scanned pages (an image background per page, same as the image-capture
  case) — there is no code path anywhere in this app for merging a new text
  layer into an existing PDF's own vector/text content, which is exactly
  why the already-has-real-text check above exists: to make sure this
  rasterize-and-rebuild path is only ever taken for PDFs that didn't have
  real content worth preserving in the first place. See
  `docs/superpowers/specs/2026-09-22-pdf-capture-ocr-design.md` for the
  full design.
```

- [ ] **Step 3: Run the test suite once**

Run: `cd tests && python3 test_searchable_pdf.py`
Expected: unchanged from Task 1's Step 9 (docs-only changes in this task).

- [ ] **Step 4: Update `tests/CLAUDE.md`'s coverage description**

Read `tests/CLAUDE.md`'s existing paragraph describing `test_searchable_pdf.py`
(search for that filename) in full first, to match its established style,
then extend it with a description of the three new scenarios added in
Task 1: a PDF that already has real text skips OCR entirely and saves
untouched (`searchable_pdf_built` stays `0`, `ocr_text` stays empty); a
3-page scanned PDF with no real text gets OCR'd page-by-page (verified via
the combined `ocr_text` containing three copies of the stub's "Hello World"
recognition output, and via `window.__JSPDF_CALLS` showing exactly one
`addImage` call per page) and rebuilt into a multi-page searchable PDF; and
a PDF saved without ever clicking "Run OCR" is left completely alone,
matching this repo's own "don't silently do things a person didn't ask
for" principle. Also note the `tests/stub_studio2.js` extension this
required: pdf.js's fake `getPage()` gained a `getTextContent()` method,
controllable via a new `window.__STUB_PDF_HAS_REAL_TEXT` flag (default
falsy, so every pre-existing PDF-OCR test's behavior is completely
unaffected unless a test explicitly opts in to simulating an
already-text-bearing PDF).

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "docs: document the PDF capture OCR amendment"
```
