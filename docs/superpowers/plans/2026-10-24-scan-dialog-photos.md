# The scan dialog and photo scans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The scan dialog offers Format (PDF/JPEG/PNG) and Paper size (the scan area) for scanners that list `formats` and `areas`, sends them in the scan request, hides resolutions over the 100-megapixel limit, and scanned images get the same automatic OCR as PDFs.

**Architecture:** All code is in the single file `dossiary.html`, in the scan-dialog section (`loadHelperScanners()`, `renderScanSettings()`, `readScanDialogSettings()`, `buildScanRequest()`). Two pure helpers (pixel count, resolution filter) sit next to `validHelperScanner()`. The existing result path (inbox, `queueScanOcr()`, the own-OCR fallback) already handles image files; a test proves it.

**Tech Stack:** Vanilla JS in `dossiary.html`; Playwright (Python) tests in `tests/` (`tests/test_scan_dialog.py` plays fake helpers with a fake `fetch`).

Spec: `docs/superpowers/specs/2026-10-24-scan-dialog-photos-design.md`. Protocol: dossiary-scan-helper's `PROTOCOL.md` ("Formats and areas").

## Global Constraints

- Branch: create `feat/scan-photos` from `spec/scan-photos` (it carries the spec); never work on `main`.
- Every commit message ends with these two lines, exactly:
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` and `Claude-Session: https://claude.ai/code/session_01StJnZRLwuzVCfrXxxywjpc`
- **Every printed check in a test script reads `True` on pass; a `: False` in any script's output is a regression.** Phrase checks so (see `tests/CLAUDE.md`).
- Tests run from `tests/`: `cd tests && python3 test_scan_dialog.py 2>&1 | grep -c ": False"` must print `0` after every task. Baseline first (Task 1, Step 1).
- A helper that lists no `formats`/`areas` (version 1, older helpers) behaves exactly as today: no new control, request body without `area`, `format: 'pdf'`, saved settings without `format`/`area` keys (existing tests compare the saved object exactly).
- Area table (mm), from the protocol: `a4` 210x297, `a5` 148x210, `a6` 105x148, `10x15` 100x150, `13x18` 130x180; `full` has no size known to Dossiary. `SCAN_MAX_PIXELS` = 100,000,000, inclusive (exactly that is allowed). Pixel count = `round(w_mm / 25.4 * dpi) * round(h_mm / 25.4 * dpi)`.
- Images come only from the flatbed: with the feeder as source, format is `pdf` and no `area` is sent (the Paper size control is hidden too; a feeder scan has no area).
- Images carry no `ocr`/`ocrLanguages` in the request (the helpers refuse it). Black & white is not offered with JPEG.
- New UI text goes into all seven STRINGS blocks (`en`, `de`, `es`, `fr`, `zh-Hans`, `zh-Hant`, `hy`); `tests/test_i18n_coverage.py` must stay green.
- Do not touch port 8766/8765 or any real scanner; tests use fake helpers only.

---

### Task 1: Read `formats` and `areas`; the pure size helpers

**Files:**
- Modify: `dossiary.html` (scan section: before `function validHelperScanner(s){`, inside `loadHelperScanners()`, after `window.__DEBUG_scanDiscovery`)
- Modify: `tests/test_scan_dialog.py` (new fixtures, new scenario)

**Interfaces:**
- Produces (used by Tasks 3-4): constants `SCAN_FORMAT_IDS`, `SCAN_AREA_IDS`, `SCAN_AREA_MM`, `SCAN_MAX_PIXELS`; functions `scanPixelCount(areaId, dpi)` (number, or `null` for an area without a known size), `scanResolutionsFor(resolutions, areaId)` (the resolutions within the limit; if none remains, `[lowest]`), `scanPickResolution(list, wanted)` (`wanted` if in `list`, else the largest value below it, else `list[0]`). Each scanner object gains `formats` (array, default `['pdf']`) and `areas` (array, default `[]`).
- Test hooks: `window.__DEBUG_scanScanners()` returns `[{helper, id, formats, areas}]` for every found scanner; `window.__DEBUG_scanPixels(areaId, dpi)`.

- [ ] **Step 1: Create the branch and record the baseline**

```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
git checkout spec/scan-photos && git checkout -b feat/scan-photos
cd tests && python3 test_scan_dialog.py > /tmp/scan_dialog_baseline.txt 2>&1; grep -c ": False" /tmp/scan_dialog_baseline.txt; grep -c ": True" /tmp/scan_dialog_baseline.txt
```
Expected: `0` then a positive count. If the first number is not `0`, stop and report BLOCKED: the baseline must be green. (Use the session scratchpad instead of `/tmp` if one is given.)

- [ ] **Step 2: Write the failing test**

In `tests/test_scan_dialog.py`, directly after the `V2_OCR_SCANNER = ...` definition add the fixtures:

```python
PHOTO_FLATBED = {"id": "fake:photo", "name": "Fake Photo", "sources": ["flatbed"], "duplex": False,
                 "colorModes": ["color", "gray", "bw"], "resolutions": [150, 300, 600, 1200], "extras": [],
                 "formats": ["pdf", "jpeg", "png"], "areas": ["a4", "10x15"], "ocr": {"languages": ["deu", "eng"]}}
PHOTO_GLASS = {"id": "fake:glass", "name": "Fake Glass", "sources": ["feeder", "flatbed"], "duplex": True,
               "colorModes": ["color", "gray", "bw"], "resolutions": [150, 300, 600, 1200], "extras": [],
               "formats": ["pdf", "jpeg", "png"], "areas": ["full", "a4", "a5"]}
PHOTO_ODD = {"id": "fake:odd", "name": "Fake Odd", "sources": ["flatbed"], "duplex": False,
             "colorModes": ["color"], "resolutions": [300], "extras": [],
             "formats": ["pdf", "tiff", "jpeg"], "areas": ["a4", "b5", "10x15"]}
PHOTO_HELPERS = {L2: {"version": 2, "token": "tok-2", "scanners": [V2_SCANNERS[0], PHOTO_FLATBED, PHOTO_GLASS, PHOTO_ODD]}}
```

Add the scenario before the `SCENARIOS = [...]` line, and append `scenario_photo_data` to the `SCENARIOS` list:

```python
# === Photos, Task 1: formats and areas are read; the size helpers ===
async def scenario_photo_data(p):
    browser, page, errors = await open_app(p, tokens={L2: 'tok-2'}, helpers=PHOTO_HELPERS)
    found = {s['id']: s for s in await page.evaluate("window.__DEBUG_scanScanners()")}
    print("a scanner without the fields gets formats ['pdf'] and no areas:",
          found['fake:flatbed']['formats'] == ['pdf'] and found['fake:flatbed']['areas'] == [])
    print("formats and areas are read as listed:",
          found['fake:photo']['formats'] == ['pdf', 'jpeg', 'png'] and found['fake:glass']['areas'] == ['full', 'a4', 'a5'])
    print("unknown format and area ids are dropped:",
          found['fake:odd']['formats'] == ['pdf', 'jpeg'] and found['fake:odd']['areas'] == ['a4', '10x15'])
    px = lambda a, d: page.evaluate("([a, d]) => window.__DEBUG_scanPixels(a, d)", [a, d])
    print("10x15 at 300 dpi is 1181 x 1772 px:", await px('10x15', 300) == 1181 * 1772)
    print("A4 at 1200 dpi is 139,201,551 px:", await px('a4', 1200) == 139201551)
    print("A5 at 1200 dpi is 69,367,632 px:", await px('a5', 1200) == 69367632)
    print("full has no known size:", await px('full', 300) is None)
    res = lambda r, a: page.evaluate("([r, a]) => window.__DEBUG_scanResolutionsFor(r, a)", [r, a])
    print("A4 drops 1200 dpi, keeps the rest:", await res([150, 300, 600, 1200], 'a4') == [150, 300, 600])
    print("10x15 keeps every resolution:", await res([150, 300, 600, 1200], '10x15') == [150, 300, 600, 1200])
    print("full and no area filter nothing:", await res([150, 1200], 'full') == [150, 1200] and await res([150, 1200], None) == [150, 1200])
    print("nothing left keeps the lowest:", await res([2400, 4800], 'a4') == [2400])
    pick = lambda l, w: page.evaluate("([l, w]) => window.__DEBUG_scanPickResolution(l, w)", [l, w])
    print("pick keeps a listed value:", await pick([150, 300, 600], 300) == 300)
    print("pick falls to the next lower value:", await pick([150, 300, 600], 1200) == 600 and await pick([150, 600], 300) == 150)
    print("pick falls to the first when none is lower:", await pick([300, 600], 150) == 300)
    print("no page errors:", errors == [])
    await browser.close()
```

- [ ] **Step 3: Run it and see it fail**

Run: `cd tests && python3 test_scan_dialog.py 2>&1 | sed -n '/scenario_photo_data/,$p'`
Expected: a Playwright error (`window.__DEBUG_scanScanners is not a function`).

- [ ] **Step 4: Implement**

In `dossiary.html`, immediately before `function validHelperScanner(s){` insert:

```js
  // Photo scans (protocol "Formats and areas"): the formats and scan areas a scanner can list, the sizes of
  // the fixed areas in mm ('full' is the scanner's own whole glass: no size known here), and the helpers'
  // limit on the pixels of one scan (inclusive).
  const SCAN_FORMAT_IDS = ['pdf', 'jpeg', 'png'];
  const SCAN_AREA_IDS = ['full', 'a4', 'a5', 'a6', '10x15', '13x18'];
  const SCAN_AREA_MM = { a4: [210, 297], a5: [148, 210], a6: [105, 148], '10x15': [100, 150], '13x18': [130, 180] };
  const SCAN_MAX_PIXELS = 100000000;
  function scanPixelCount(areaId, dpi){
    const mm = SCAN_AREA_MM[areaId];
    if(!mm) return null;
    return Math.round(mm[0] / 25.4 * dpi) * Math.round(mm[1] / 25.4 * dpi);
  }
  // The resolutions a scan of this area may use; with no area, or one of unknown size ('full'), all of them.
  // If none is within the limit the lowest is kept, so the helper's refusal explains.
  function scanResolutionsFor(resolutions, areaId){
    const ok = resolutions.filter(r => { const n = scanPixelCount(areaId, r); return n === null || n <= SCAN_MAX_PIXELS; });
    return ok.length ? ok : [Math.min(...resolutions)];
  }
  // `wanted` if it is in the list, else the largest value below it, else the first.
  function scanPickResolution(list, wanted){
    if(list.includes(wanted)) return wanted;
    const lower = list.filter(r => r < wanted);
    return lower.length ? Math.max(...lower) : list[0];
  }

```

In `loadHelperScanners()`, in the object returned by `.map(s => ({ ... }))`, add after the `ocr:` line:

```js
        formats: Array.isArray(s.formats) ? s.formats.filter(x => SCAN_FORMAT_IDS.includes(x)) : ['pdf'],
        areas: Array.isArray(s.areas) ? s.areas.filter(x => SCAN_AREA_IDS.includes(x)) : [],
```

Immediately after the `window.__DEBUG_scanDiscovery = ...;` block (before `window.__DEBUG_setScanBridgeUrl`) add:

```js
  window.__DEBUG_scanScanners = async () => {
    const helpers = await discoverScanHelpers();
    return helpers.flatMap(h => h.scanners.map(s => ({ helper: h.url, id: s.id, formats: s.formats, areas: s.areas })));
  };
  window.__DEBUG_scanPixels = (areaId, dpi) => scanPixelCount(areaId, dpi);
  window.__DEBUG_scanResolutionsFor = (resolutions, areaId) => scanResolutionsFor(resolutions, areaId);
  window.__DEBUG_scanPickResolution = (list, wanted) => scanPickResolution(list, wanted);
```

- [ ] **Step 5: Run the tests**

Run: `cd tests && python3 test_scan_dialog.py > /tmp/out.txt 2>&1; grep -c ": False" /tmp/out.txt; sed -n '/scenario_photo_data/,$p' /tmp/out.txt`
Expected: `0`, and every line of the new scenario ends `True`.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_scan_dialog.py
git commit -m "Scan dialog: read formats and areas from helpers; pixel-limit helpers

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01StJnZRLwuzVCfrXxxywjpc"
```

---

### Task 2: Translations (seven languages)

**Files:**
- Modify: `dossiary.html` (the seven `STRINGS` blocks)

**Interfaces:**
- Produces (used by Task 3), identical keys in every language: `scanDialogFormatLabel`, `scanDialogAreaLabel`, `scanFormatPdf`, `scanFormatJpeg`, `scanFormatPng`, `scanAreaFull`, `scanAreaA4`, `scanAreaA5`, `scanAreaA6`, `scanArea10x15`, `scanArea13x18`.

- [ ] **Step 1: The check already exists**

`tests/test_i18n_coverage.py` fails when a key is in one language and not the others. Add the keys to `en` only first and run it to see it fail:

Insert, in the `en` block, a new line directly after the line containing `scanDialogAddressInvalid:` (it is the end of the scan-dialog key group):

```js
      scanDialogFormatLabel: "Format", scanDialogAreaLabel: "Paper size", scanFormatPdf: "PDF", scanFormatJpeg: "JPEG", scanFormatPng: "PNG", scanAreaFull: "Whole glass", scanAreaA4: "A4", scanAreaA5: "A5", scanAreaA6: "A6", scanArea10x15: "10 × 15 cm", scanArea13x18: "13 × 18 cm",
```

Run: `cd tests && python3 test_i18n_coverage.py 2>&1 | grep -c ": False"`
Expected: at least `1` (the other languages lack the keys).

- [ ] **Step 2: Add the other six languages**

Directly after the line containing `scanDialogAddressInvalid:` in each of the other blocks, insert that language's line (in `hy` the keys are one per line after `scanDialogAddressInvalid: "...",`; either layout is fine as long as each key is a `key: "value"` pair the coverage test's regex finds, i.e. preceded by `{`, `,` or a line start):

`de`:
```js
      scanDialogFormatLabel: "Format", scanDialogAreaLabel: "Papiergröße", scanFormatPdf: "PDF", scanFormatJpeg: "JPEG", scanFormatPng: "PNG", scanAreaFull: "Ganze Glasfläche", scanAreaA4: "A4", scanAreaA5: "A5", scanAreaA6: "A6", scanArea10x15: "10 × 15 cm", scanArea13x18: "13 × 18 cm",
```
`es`:
```js
      scanDialogFormatLabel: "Formato", scanDialogAreaLabel: "Tamaño del papel", scanFormatPdf: "PDF", scanFormatJpeg: "JPEG", scanFormatPng: "PNG", scanAreaFull: "Todo el cristal", scanAreaA4: "A4", scanAreaA5: "A5", scanAreaA6: "A6", scanArea10x15: "10 × 15 cm", scanArea13x18: "13 × 18 cm",
```
`fr`:
```js
      scanDialogFormatLabel: "Format", scanDialogAreaLabel: "Format du papier", scanFormatPdf: "PDF", scanFormatJpeg: "JPEG", scanFormatPng: "PNG", scanAreaFull: "Toute la vitre", scanAreaA4: "A4", scanAreaA5: "A5", scanAreaA6: "A6", scanArea10x15: "10 × 15 cm", scanArea13x18: "13 × 18 cm",
```
`zh-Hans`:
```js
      scanDialogFormatLabel: "格式", scanDialogAreaLabel: "纸张尺寸", scanFormatPdf: "PDF", scanFormatJpeg: "JPEG", scanFormatPng: "PNG", scanAreaFull: "整个玻璃板", scanAreaA4: "A4", scanAreaA5: "A5", scanAreaA6: "A6", scanArea10x15: "10 × 15 厘米", scanArea13x18: "13 × 18 厘米",
```
`zh-Hant`:
```js
      scanDialogFormatLabel: "格式", scanDialogAreaLabel: "紙張尺寸", scanFormatPdf: "PDF", scanFormatJpeg: "JPEG", scanFormatPng: "PNG", scanAreaFull: "整個玻璃板", scanAreaA4: "A4", scanAreaA5: "A5", scanAreaA6: "A6", scanArea10x15: "10 × 15 公分", scanArea13x18: "13 × 18 公分",
```
`hy`:
```js
      scanDialogFormatLabel: "Ձևաչափ", scanDialogAreaLabel: "Թղթի չափս", scanFormatPdf: "PDF", scanFormatJpeg: "JPEG", scanFormatPng: "PNG", scanAreaFull: "Ամբողջ ապակին", scanAreaA4: "A4", scanAreaA5: "A5", scanAreaA6: "A6", scanArea10x15: "10 × 15 սմ", scanArea13x18: "13 × 18 սմ",
```

- [ ] **Step 3: Run the checks**

Run: `cd tests && python3 test_i18n_coverage.py 2>&1 | grep -c ": False"; python3 test_scan_dialog.py 2>&1 | grep -c ": False"`
Expected: `0` and `0`.

- [ ] **Step 4: Commit**

```bash
git add dossiary.html
git commit -m "Scan dialog: Format and Paper size texts in all seven languages

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01StJnZRLwuzVCfrXxxywjpc"
```

---

### Task 3: The Format and Paper size controls

**Files:**
- Modify: `dossiary.html` (`renderScanSettings()`, `readScanDialogSettings()`, a label-key table)
- Modify: `tests/test_scan_dialog.py`

**Interfaces:**
- Consumes: Task 1's constants/functions and scanner fields; Task 2's strings.
- Produces: DOM ids `#scan-dialog-format` / `#scan-dialog-format-field` and `#scan-dialog-area` / `#scan-dialog-area-field` (a select exists only when the scanner lists more than one value; the `-field` wrapper is the `.field` div around it, hidden with `display:none` when it doesn't apply); `readScanDialogSettings()` additionally returns `format` (when the scanner lists more than one format) and `area` (when it lists any area), each the *chosen* value, even while hidden for the feeder. Behaviour: Format and Paper size hidden when the source is `feeder`; black & white removed from Color while the effective format is `jpeg`; Resolution rebuilt from `scanResolutionsFor()` for the effective area (none for a feeder).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scan_dialog.py` (and append `scenario_photo_controls` to `SCENARIOS`):

```python
async def option_texts(page, selector):
    return await page.eval_on_selector_all(f'{selector} option', 'els => els.map(e => e.textContent)')


# === Photos, Task 3: the controls ===
async def scenario_photo_controls(p):
    browser, page, errors = await open_app(p, tokens={L2: 'tok-2'}, helpers=PHOTO_HELPERS)
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)

    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:flatbed')
    print("no Format or Paper size for a scanner without them:",
          await page.locator('#scan-dialog-format').count() == 0 and await page.locator('#scan-dialog-area').count() == 0)
    settings = await page.evaluate("window.__DEBUG_readScanDialogSettings()")
    print("...and the settings carry neither:", 'format' not in settings and 'area' not in settings)

    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:photo')
    print("Format lists PDF, JPEG, PNG, PDF first:", await option_texts(page, '#scan-dialog-format') == ['PDF', 'JPEG', 'PNG']
          and await page.eval_on_selector('#scan-dialog-format', 'e => e.value') == 'pdf')
    print("Paper size lists the scanner's areas, the first selected:",
          await option_texts(page, '#scan-dialog-area') == ['A4', '10 × 15 cm'] and await page.eval_on_selector('#scan-dialog-area', 'e => e.value') == 'a4')
    print("A4 hides 1200 dpi:", await option_texts(page, '#scan-dialog-resolution') == ['150 dpi', '300 dpi', '600 dpi'])
    await page.select_option('#scan-dialog-area', '10x15')
    print("10 × 15 cm offers 1200 dpi:", await option_texts(page, '#scan-dialog-resolution') == ['150 dpi', '300 dpi', '600 dpi', '1200 dpi'])
    await page.select_option('#scan-dialog-resolution', '1200')
    await page.select_option('#scan-dialog-area', 'a4')
    print("back to A4 the resolution falls to 600 dpi:", await page.eval_on_selector('#scan-dialog-resolution', 'e => e.value') == '600')

    await page.select_option('#scan-dialog-format', 'jpeg')
    print("JPEG hides black & white:", await option_texts(page, '#scan-dialog-color') == ['Color', 'Grayscale'])
    await page.select_option('#scan-dialog-format', 'png')
    print("PNG offers black & white:", await option_texts(page, '#scan-dialog-color') == ['Color', 'Grayscale', 'Black & white'])
    await page.select_option('#scan-dialog-color', 'bw')
    await page.select_option('#scan-dialog-format', 'jpeg')
    print("switching to JPEG moves a chosen black & white to the first mode:", await page.eval_on_selector('#scan-dialog-color', 'e => e.value') == 'color')
    await page.select_option('#scan-dialog-format', 'pdf')
    print("PDF offers black & white again:", 'Black & white' in await option_texts(page, '#scan-dialog-color'))

    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:odd')
    print("unknown ids never reach the selects:",
          await option_texts(page, '#scan-dialog-format') == ['PDF', 'JPEG'] and await option_texts(page, '#scan-dialog-area') == ['A4', '10 × 15 cm'])

    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:glass')
    print("whole glass is the first area and the default:",
          await option_texts(page, '#scan-dialog-area') == ['Whole glass', 'A4', 'A5'] and await page.eval_on_selector('#scan-dialog-area', 'e => e.value') == 'full')
    print("the whole glass filters no resolution:", await option_texts(page, '#scan-dialog-resolution') == ['150 dpi', '300 dpi', '600 dpi', '1200 dpi'])
    await page.select_option('#scan-dialog-format', 'jpeg')
    await page.select_option('#scan-dialog-source', 'feeder')
    print("the feeder hides Format and Paper size:",
          not await page.is_visible('#scan-dialog-format-field') and not await page.is_visible('#scan-dialog-area-field'))
    print("...the feeder offers black & white even though JPEG is chosen:", 'Black & white' in await option_texts(page, '#scan-dialog-color'))
    settings = await page.evaluate("window.__DEBUG_readScanDialogSettings()")
    print("the chosen format and area are still read while hidden:", settings['format'] == 'jpeg' and settings['area'] == 'full')
    await page.select_option('#scan-dialog-source', 'flatbed')
    print("back on the flatbed Format shows again with the earlier choice:",
          await page.is_visible('#scan-dialog-format-field') and await page.eval_on_selector('#scan-dialog-format', 'e => e.value') == 'jpeg')
    print("...and JPEG hides black & white again:", 'Black & white' not in await option_texts(page, '#scan-dialog-color'))
    print("no page errors:", errors == [])
    await browser.close()
```

- [ ] **Step 2: Run it and see it fail**

Run: `cd tests && python3 test_scan_dialog.py 2>&1 | sed -n '/scenario_photo_controls/,$p' | head -8`
Expected: first photo checks print `False` (no `#scan-dialog-format`).

- [ ] **Step 3: Implement the label tables**

Directly after `const SCAN_SETTING_LABEL_KEYS = { ... };` (in the scan-dialog section) add:

```js
  const SCAN_FORMAT_LABEL_KEYS = { pdf: 'scanFormatPdf', jpeg: 'scanFormatJpeg', png: 'scanFormatPng' };
  const SCAN_AREA_LABEL_KEYS = { full: 'scanAreaFull', a4: 'scanAreaA4', a5: 'scanAreaA5', a6: 'scanAreaA6', '10x15': 'scanArea10x15', '13x18': 'scanArea13x18' };
```

- [ ] **Step 4: Implement the controls in `renderScanSettings()`**

(a) Give the select wrapper an id. Replace

```js
    const selectHtml = (id, labelKey, values, current, labelOf) => values.length > 1 ? `
      <div class="field">
        <label for="${id}">${t(labelKey)}</label>
```
with
```js
    const selectHtml = (id, labelKey, values, current, labelOf) => values.length > 1 ? `
      <div class="field" id="${id}-field">
        <label for="${id}">${t(labelKey)}</label>
```

(b) After the line `const duplexOn = keep ? !!keep.duplex : s.duplex;` add:

```js
    const format = pick(s.formats, keep && keep.format);
    const area = pick(s.areas, keep && keep.area);
```

(c) In the `box.innerHTML` template, directly after the line
`      ${selectHtml('scan-dialog-source', 'scanDialogSourceLabel', s.sources, source, v => t(SCAN_SETTING_LABEL_KEYS.source[v]))}`
add two lines:

```js
      ${selectHtml('scan-dialog-format', 'scanDialogFormatLabel', s.formats, format, v => t(SCAN_FORMAT_LABEL_KEYS[v]))}
      ${selectHtml('scan-dialog-area', 'scanDialogAreaLabel', s.areas, area, v => t(SCAN_AREA_LABEL_KEYS[v]))}
```

(d) Replace the tail of the function

```js
    if(el('scan-dialog-source')) el('scan-dialog-source').addEventListener('change', syncDuplex);
    syncDuplex();
  }
```
with
```js
    // Images only come from the flatbed, and only a flatbed scan has a scan area: with the feeder as source
    // Format and Paper size are hidden, the format is pdf and no area applies.
    const currentSource = () => el('scan-dialog-source') ? el('scan-dialog-source').value : source;
    const onFlatbed = () => currentSource() !== 'feeder';
    const effectiveFormat = () => {
      if(!onFlatbed()) return 'pdf';
      return el('scan-dialog-format') ? el('scan-dialog-format').value : format;
    };
    const effectiveArea = () => {
      if(!onFlatbed() || !s.areas.length) return null;
      return el('scan-dialog-area') ? el('scan-dialog-area').value : s.areas[0];
    };
    const fillSelect = (select, values, wanted, labelOf) => {
      select.innerHTML = values.map(v => `<option value="${escapeHtml(String(v))}" ${v === wanted ? 'selected' : ''}>${escapeHtml(labelOf(v))}</option>`).join('');
    };
    const syncImageFields = () => {
      for(const id of ['scan-dialog-format-field', 'scan-dialog-area-field']){
        if(el(id)) el(id).style.display = onFlatbed() ? '' : 'none';
      }
    };
    // JPEG can't be black & white: the option goes while JPEG is the format.
    const syncColor = () => {
      const select = el('scan-dialog-color');
      if(!select) return;
      const allowed = effectiveFormat() === 'jpeg' ? s.colorModes.filter(x => x !== 'bw') : s.colorModes;
      const list = allowed.length ? allowed : s.colorModes;
      fillSelect(select, list, list.includes(select.value) ? select.value : list[0], v => t(SCAN_SETTING_LABEL_KEYS.colorMode[v]));
    };
    // Resolutions over the helpers' pixel limit are not offered for an area of known size.
    const syncResolution = () => {
      const select = el('scan-dialog-resolution');
      if(!select) return;
      const list = scanResolutionsFor(s.resolutions, effectiveArea());
      fillSelect(select, list, scanPickResolution(list, Number(select.value)), v => t('scanDialogDpi', {dpi: v}));
    };
    if(el('scan-dialog-source')) el('scan-dialog-source').addEventListener('change', () => { syncDuplex(); syncImageFields(); syncColor(); syncResolution(); });
    if(el('scan-dialog-format')) el('scan-dialog-format').addEventListener('change', syncColor);
    if(el('scan-dialog-area')) el('scan-dialog-area').addEventListener('change', syncResolution);
    syncDuplex();
    syncImageFields();
    syncColor();
    syncResolution();
  }
```

- [ ] **Step 5: Implement the reading in `readScanDialogSettings()`**

Replace

```js
    return {
      scanner: choice.key,
      source: value('scan-dialog-source', s.sources[0]),
      duplex: !!(el('scan-dialog-duplex') && el('scan-dialog-duplex').checked),
      colorMode: value('scan-dialog-color', s.colorModes[0]),
      resolution: el('scan-dialog-resolution') ? Number(el('scan-dialog-resolution').value) : s.resolutions[0],
      extras,
    };
```
with
```js
    const settings = {
      scanner: choice.key,
      source: value('scan-dialog-source', s.sources[0]),
      duplex: !!(el('scan-dialog-duplex') && el('scan-dialog-duplex').checked),
      colorMode: value('scan-dialog-color', s.colorModes[0]),
      resolution: el('scan-dialog-resolution') ? Number(el('scan-dialog-resolution').value) : s.resolutions[0],
      extras,
    };
    // Only for a scanner that offers a choice, so a helper without the fields leaves the object as it was.
    if(s.formats.length > 1) settings.format = value('scan-dialog-format', s.formats[0]);
    if(s.areas.length) settings.area = value('scan-dialog-area', s.areas[0]);
    return settings;
```

- [ ] **Step 6: Run the tests**

Run: `cd tests && python3 test_scan_dialog.py > /tmp/out.txt 2>&1; grep -c ": False" /tmp/out.txt; sed -n '/scenario_photo_controls/,$p' /tmp/out.txt`
Expected: `0`, all new lines `True`. If an *existing* check turns `False` (for example the exact saved-settings comparison), fix the implementation, not the check.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_scan_dialog.py
git commit -m "Scan dialog: Format and Paper size controls

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01StJnZRLwuzVCfrXxxywjpc"
```

---

### Task 4: The request, remembering, and image results

**Files:**
- Modify: `dossiary.html` (`buildScanRequest()`)
- Modify: `tests/test_scan_dialog.py` (the fake helper returns real images; new scenario)

**Interfaces:**
- Consumes: Task 3's `readScanDialogSettings()` (`format`, `area`).
- Produces: the version 2 request body: `format` is the chosen format when the source is the flatbed and the scanner lists it, else `'pdf'`; `area` only for a scanner that lists areas and a flatbed scan (the chosen one if listed, else the first); `ocr`/`ocrLanguages` only when the format is `pdf`. Remembering needs no further code: `renderScanSettings(keep)` already reads `keep.format` / `keep.area` through `pick()`, which falls back to the first listed value.

- [ ] **Step 1: Make the fake helper return images**

In `FAKE_HELPERS` (top of `tests/test_scan_dialog.py`), replace

```js
            if(H.version === 2) return json(200, { ok: true, partial: false, message: '1 page scanned.',
                                                   files: [{ name: `scan_${n}.pdf`, pages: 1, data: btoa('%PDF-1.4 fake v2 ' + n), ...(req.ocr ? { ocrJob: 'job-' + n } : {}) }] });
```
with
```js
            if(H.version === 2){
                const kind = req.format === 'jpeg' ? ['jpg', 'image/jpeg'] : req.format === 'png' ? ['png', 'image/png'] : null;
                if(kind){
                    const c = document.createElement('canvas'); c.width = 4; c.height = 4;
                    c.getContext('2d').fillRect(0, 0, 2, 2);
                    return json(200, { ok: true, partial: false, message: '1 image scanned.',
                                       files: [{ name: `scan_${n}.${kind[0]}`, pages: 1, data: c.toDataURL(kind[1]).split(',')[1] }] });
                }
                return json(200, { ok: true, partial: false, message: '1 page scanned.',
                                   files: [{ name: `scan_${n}.pdf`, pages: 1, data: btoa('%PDF-1.4 fake v2 ' + n), ...(req.ocr ? { ocrJob: 'job-' + n } : {}) }] });
            }
```

- [ ] **Step 2: Write the failing test**

Add (and append `scenario_photo_request` to `SCENARIOS`):

```python
async def last_scan_body(page):
    return json.loads([x for x in await calls(page) if x['url'] == f'{L2}/scan'][-1]['body'])


# === Photos, Task 4: the request, remembering, image results ===
async def scenario_photo_request(p):
    browser, page, errors = await open_app(p, tokens={L2: 'tok-2'}, helpers=PHOTO_HELPERS, keep_auto_ocr=True)
    await page.evaluate("window.__DEBUG_holdOcrJobs(true)")  # no timer: OCR passes are explicit

    # An older scanner: no area, pdf, exactly as before.
    await page.click('#scan-btn'); await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:flatbed')
    await start_scan(page)
    body = await last_scan_body(page)
    print("a scanner without the fields: pdf and no area:", body['format'] == 'pdf' and 'area' not in body)

    # A PDF from a scanner with areas: the default area, and OCR as before.
    await page.click('#scan-btn'); await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:photo')
    await start_scan(page)
    body = await last_scan_body(page)
    print("a PDF carries the first area:", body['format'] == 'pdf' and body['area'] == 'a4')
    print("a PDF asks for OCR as before:", body.get('ocr') is True)

    # A JPEG: format and area, no OCR.
    await page.click('#scan-btn'); await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:photo')
    await page.select_option('#scan-dialog-format', 'jpeg')
    await page.select_option('#scan-dialog-area', '10x15')
    await page.select_option('#scan-dialog-color', 'gray')
    await page.select_option('#scan-dialog-resolution', '300')
    await start_scan(page, wait=900)
    body = await last_scan_body(page)
    print("the JPEG request carries exactly the chosen settings:",
          body == {"scanner": "fake:photo", "format": "jpeg", "extras": {}, "source": "flatbed", "colorMode": "gray",
                   "resolution": 300, "duplex": False, "area": "10x15"})
    print("an image request has no ocr:", 'ocr' not in body and 'ocrLanguages' not in body)

    # Remembered: the dialog comes back with the same format and area.
    saved = json.loads(next(r['value'] for r in (await db_state(page))['settings'] if r['key'] == 'scan_last_settings'))
    print("format and area are remembered:", saved.get('format') == 'jpeg' and saved.get('area') == '10x15')
    await page.click('#scan-btn'); await page.wait_for_timeout(300)
    print("reopening restores them:", await page.eval_on_selector('#scan-dialog-format', 'e => e.value') == 'jpeg'
          and await page.eval_on_selector('#scan-dialog-area', 'e => e.value') == '10x15')
    await page.keyboard.press('Escape')
    # An area the scanner no longer lists is ignored.
    narrowed = dict(PHOTO_FLATBED, areas=["a4"])
    await page.evaluate("(s) => { window.__HELPERS['%s'].scanners = [s]; }" % L2, narrowed)
    await page.click('#scan-btn'); await page.wait_for_timeout(300)
    print("a remembered area that is gone falls back to the first:", await page.locator('#scan-dialog-area').count() == 0
          and (await page.evaluate("window.__DEBUG_readScanDialogSettings()"))['area'] == 'a4')
    await page.keyboard.press('Escape')
    await page.evaluate("(s) => { window.__HELPERS['%s'].scanners = s; }" % L2, PHOTO_HELPERS[L2]["scanners"])

    # The feeder: pdf, no area, whatever format was chosen.
    await page.click('#scan-btn'); await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:glass')
    await page.select_option('#scan-dialog-format', 'png')
    await page.select_option('#scan-dialog-source', 'feeder')
    await start_scan(page)
    body = await last_scan_body(page)
    print("a feeder scan is a pdf without an area:", body['format'] == 'pdf' and 'area' not in body and body['source'] == 'feeder')
    # The flatbed of the same scanner: png, the whole glass.
    await page.click('#scan-btn'); await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:glass')
    await page.select_option('#scan-dialog-source', 'flatbed')
    await page.select_option('#scan-dialog-format', 'png')
    await start_scan(page, wait=900)
    body = await last_scan_body(page)
    print("a flatbed PNG of the whole glass:", body['format'] == 'png' and body['area'] == 'full' and 'ocr' not in body)

    # Results: the images became documents, and (OCR is on) wait for Dossiary's own OCR.
    db = await db_state(page)
    names = [d['original_file_path'] or d['file_path'] for d in db['documents']]
    print("the image scans became documents:", sum(1 for n in names if n.endswith('.jpg')) == 1 and sum(1 for n in names if n.endswith('.png')) == 1)
    rows = await ocr_rows(page)
    image_ids = [d['id'] for d in db['documents'] if (d['original_file_path'] or d['file_path']).endswith(('.jpg', '.png'))]
    print("each image waits for Dossiary's own OCR (no helper job):",
          sorted(r['document_id'] for r in rows if r['job_id'] is None and r['document_id'] in image_ids) == sorted(image_ids))
    jpg = next(d for d in db['documents'] if (d['original_file_path'] or d['file_path']).endswith('.jpg'))
    # The runner is held and runs one fallback per pass, oldest row first (earlier PDF scans wait too):
    # pass until the JPEG's row is gone.
    finished = False
    for _ in range(8):
        await run_pass(page)
        if await wait_fallback_done(page, jpg['id']):
            finished = True
            break
    print("the own OCR finishes the JPEG:", finished)
    jpg = await doc_row(page, jpg['id'])
    print("the JPEG is now a searchable PDF, the original JPEG kept:",
          jpg['searchable_pdf_built'] == 1 and jpg['file_path'].endswith('.pdf') and (jpg['original_file_path'] or '').endswith('.jpg'))
    print("no page errors:", errors == [])
    await browser.close()

    # With automatic OCR off, a scanned image stays an image.
    browser, page, errors = await open_app(p, tokens={L2: 'tok-2'}, helpers=PHOTO_HELPERS)
    await page.click('#scan-btn'); await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:photo')
    await page.select_option('#scan-dialog-format', 'jpeg')
    await start_scan(page, wait=900)
    db = await db_state(page)
    print("OCR off: the scan is an image document with no OCR row:",
          len(db['documents']) == 1 and (db['documents'][0]['file_path'] or '').endswith('.jpg') and await ocr_rows(page) == [])
    print("no page errors:", errors == [])
    await browser.close()
```

- [ ] **Step 3: Run it and see it fail**

Run: `cd tests && python3 test_scan_dialog.py 2>&1 | sed -n '/scenario_photo_request/,$p' | head -12`
Expected: `False` on the request checks (the body always says `pdf`, never has `area`).

- [ ] **Step 4: Implement `buildScanRequest()`**

Replace

```js
    const body = { scanner: s.id, format: 'pdf', extras };
    if(settings.source) body.source = settings.source;
```
with
```js
    // Images only come from the flatbed (the helpers refuse them from a feeder), and only a flatbed scan has an
    // area. A format or area the scanner doesn't list is never sent.
    const flatbed = settings.source !== 'feeder';
    const format = flatbed && s.formats.includes(settings.format) ? settings.format : 'pdf';
    const body = { scanner: s.id, format, extras };
    if(flatbed && s.areas.length) body.area = s.areas.includes(settings.area) ? settings.area : s.areas[0];
    if(settings.source) body.source = settings.source;
```

and replace

```js
    if(scanAutoOcr && s.ocr && typeof s.ocr === 'object'){
```
with
```js
    if(format === 'pdf' && scanAutoOcr && s.ocr && typeof s.ocr === 'object'){
```

- [ ] **Step 5: Run the tests**

Run: `cd tests && python3 test_scan_dialog.py > /tmp/out.txt 2>&1; grep -c ": False" /tmp/out.txt; sed -n '/scenario_photo_request/,$p' /tmp/out.txt`
Expected: `0`, all new lines `True`.

**If the "own OCR finishes the JPEG" or "searchable PDF" checks fail,** this is the risk named in the spec (the fallback's first run on a scanned image): investigate `runOcrFallback()` / `makeDocumentSearchable()` for the image path (extension change from `.jpg` to `.pdf`, the document's `file_path`/`original_file_path`), fix it minimally in `dossiary.html`, and say so in the report. Do not weaken the check.

- [ ] **Step 6: Run the neighbouring suites**

Run: `cd tests && for t in test_i18n_coverage.py test_user_guides.py; do python3 $t 2>&1 | grep -c ": False"; done`
Expected: `0` `0`. Also run any existing test that exercises Inbox import of JPEG/PNG or the own OCR, to be sure nothing moved: `ls tests | grep -i -E "ocr|inbox"` and run each of those scripts, expecting no `: False`.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_scan_dialog.py
git commit -m "Scan dialog: send format and area; scanned images are OCRed like PDFs

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01StJnZRLwuzVCfrXxxywjpc"
```

---

### Task 5: Documentation

**Files:**
- Modify: `AGENTS.md` (the "Scanning: the scan dialog and its helpers" bullet)
- Modify: the seven `USER_GUIDE*.md` files
- Modify: `docs/superpowers/specs/2026-10-24-scan-dialog-photos-design.md` (two clarifications)

**Interfaces:** none (text only).

- [ ] **Step 1: AGENTS.md**

Insert a new paragraph directly before the text `**Background OCR (2026-10-11)**: when` in that bullet (keep the surrounding two-space bullet indentation):

```
  **Photos (2026-10-24)** (spec `docs/superpowers/specs/2026-10-24-scan-dialog-photos-design.md`):
  a scanner that lists `formats` (pdf/jpeg/png) and `areas` (full/a4/a5/a6/10x15/13x18) gets a
  Format and a Paper size select (shown when there is more than one value; ids
  `scan-dialog-format`/`-area`, wrappers `-field`). Both are hidden with the feeder as source: images
  only come from the flatbed (the helpers refuse them from a feeder), so the request says `pdf` and
  carries no `area`. Black & white is not offered with JPEG. For the standard areas
  `scanResolutionsFor()` hides resolutions over the helpers' 100-megapixel limit
  (`SCAN_MAX_PIXELS`, inclusive; `scanPixelCount()` = round(w/25.4*dpi)*round(h/25.4*dpi), sizes in
  `SCAN_AREA_MM`); `full` has no known size, so nothing is filtered and a helper's 422 message is shown.
  The request has `area` for a flatbed scan on a scanner with areas, and `ocr` only for PDFs; a scanned
  image has no `ocrJob`, so `queueScanOcr()` queues it for Dossiary's own OCR when `scan_auto_ocr` is
  on, and it ends as a searchable PDF with the image kept as the original. `scan_last_settings` gains
  `format` and `area` only for a scanner that offers a choice (so older saved objects and helpers
  without the fields are unchanged).
```

- [ ] **Step 2: The user guides**

In each guide, add the paragraph below directly after the paragraph in the "Scanning straight into Dossiary" section (localized title) that ends with "(Scan Multi)" (find it with `grep -n "Scan Multi" USER_GUIDE*.md`; in each file the section has exactly one such paragraph). Leave a blank line before and after.

`USER_GUIDE.md`:
```
To scan a photo, choose **JPEG** or **PNG** under **Format** (the document feeder only scans PDFs) and the size of the print under **Paper size**, for example 10 × 15 cm. Resolutions that would give an enormous image aren't offered for the standard sizes.
```
`USER_GUIDE.de.md`:
```
Um ein Foto zu scannen, wähle unter **Format** **JPEG** oder **PNG** (der Dokumenteneinzug scannt nur PDF) und unter **Papiergröße** die Größe des Abzugs, zum Beispiel 10 × 15 cm. Auflösungen, die ein riesiges Bild ergäben, werden für die Standardgrößen nicht angeboten.
```
`USER_GUIDE.es.md`:
```
Para escanear una foto, elija **JPEG** o **PNG** en **Formato** (el alimentador de documentos solo escanea PDF) y el tamaño de la copia en **Tamaño del papel**, por ejemplo 10 × 15 cm. Las resoluciones que darían una imagen enorme no se ofrecen para los tamaños estándar.
```
`USER_GUIDE.fr.md`:
```
Pour numériser une photo, choisissez **JPEG** ou **PNG** sous **Format** (le chargeur de documents ne numérise qu'en PDF) et la taille du tirage sous **Format du papier**, par exemple 10 × 15 cm. Les résolutions qui donneraient une image énorme ne sont pas proposées pour les formats standard.
```
`USER_GUIDE.zh-Hans.md`:
```
要扫描照片，请在**格式**中选择 **JPEG** 或 **PNG**（自动进纸器只能扫描为 PDF），并在**纸张尺寸**中选择照片的尺寸，例如 10 × 15 厘米。对于标准尺寸，会产生超大图像的分辨率不会提供。
```
`USER_GUIDE.zh-Hant.md`:
```
要掃描照片，請在**格式**中選擇 **JPEG** 或 **PNG**（自動進紙器只能掃描為 PDF），並在**紙張尺寸**中選擇相片的尺寸，例如 10 × 15 公分。對於標準尺寸，會產生超大影像的解析度不會提供。
```
`USER_GUIDE.hy.md`:
```
Լուսանկար սկանավորելու համար **Ձևաչափ**-ում ընտրեք **JPEG** կամ **PNG** (փաստաթղթերի սնուցիչը սկանավորում է միայն PDF) և **Թղթի չափս**-ում՝ նկարի չափը, օրինակ՝ 10 × 15 սմ։ Ստանդարտ չափերի համար չեն առաջարկվում այն թույլատրությունները, որոնք հսկայական պատկեր կտային։
```

- [ ] **Step 3: Spec clarifications**

In the spec's "The dialog" section, change the bullet beginning `- **Images only from the flatbed.**` so it ends with: `Paper size is hidden too and no \`area\` is sent: only a flatbed scan has a scan area.` And in "The request" replace "`area` is added when the scanner lists areas" with "`area` is added when the scanner lists areas and the source is the flatbed". Replace the Testing bullet "A test pins the table to the protocol" in Risks item 2 with "tests pin the pixel counts of three known cases (10x15 at 300, A4 and A5 at 1200 dpi)".

- [ ] **Step 4: Check and commit**

Run: `cd tests && python3 test_user_guides.py 2>&1 | grep -c ": False"; python3 test_i18n_coverage.py 2>&1 | grep -c ": False"; python3 test_scan_dialog.py 2>&1 | grep -c ": False"`
Expected: `0` `0` `0`.

```bash
git add AGENTS.md USER_GUIDE*.md docs/superpowers/specs/2026-10-24-scan-dialog-photos-design.md
git commit -m "Docs: photo scans in the scan dialog (AGENTS.md, user guides, spec)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01StJnZRLwuzVCfrXxxywjpc"
```

---

### Task 6: Manual check with real hardware (controller with the user, not a subagent)

- [ ] Open `dossiary.html` in the browser against a **test copy** of a library (never the user's real one), with the real macOS helper (port 8766, already running and paired) and the Pi's 8800F paired through it.
- [ ] Scan dialog: the Canon MF650C lists Format (PDF/JPEG/PNG) and Paper size starting with "Whole glass"; the 8800F lists A4, A5, A6, 10 × 15 cm, 13 × 18 cm; the iX500 (if connected) shows neither.
- [ ] A 10 × 15 cm JPEG at 300 dpi from the 8800F lands in the Inbox as an image, is added, and with automatic OCR on becomes a searchable PDF with the JPEG as its original.
- [ ] A PNG from the MF650C flatbed (Whole glass) lands; switching Source to the document feeder hides Format and Paper size, and that scan is a PDF.
- [ ] Choose A4 on the 8800F: 1200 dpi is not in the list; choose 10 × 15 cm: it is.
- [ ] Close and reopen the dialog: format, area and the rest are remembered.
- [ ] Delete the test scans and the test library copy.
