# RTF previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** RTF documents get a first-page preview in Dossiary (grid, Inbox add, capture, Regenerate, "Create missing previews").

**Architecture:** `generateThumbnail(file)` in `dossiary.html` gets an RTF branch. rtf.js (three pinned CDN bundles, loaded lazily) turns the RTF into HTML in a hidden A4-sized white box; the box is serialized into an SVG `foreignObject`, drawn to a canvas, scaled and encoded by the existing `canvasToThumbBytes()`. Any failure returns `null` (the card keeps "No preview").

**Tech Stack:** single-file `dossiary.html` (no build step), rtf.js 3.0.9 from jsDelivr, Playwright for Python tests under `tests/`.

Spec: `docs/superpowers/specs/2026-11-13-rtf-previews-design.md`.

## Global Constraints

- Keep the single-file structure; no vendored libraries, no `package.json`. Libraries load from a CDN at runtime, pinned to an exact version (`AGENTS.md`).
- No automatic bulk preview generation when a library opens; "Create missing previews (N)" stays explicit and stoppable (`docs/architecture/02-data-and-fields.md`).
- `generateThumbnail()` returns `null` for anything it cannot draw. That is an expected outcome, never an error.
- Previews are JPEG files `thumbnails/<id>.jpg`, longest side `THUMB_MAX_DIM` (640 px), written by `writeThumbnail()` after `canvasToThumbBytes()`.
- RTF limits: files over 2 MB (`2 * 1024 * 1024` bytes) and renders over 10 s give `null`.
- Preview picture: white page, black text, A4 at 96 dpi (794 × 1123 CSS px), 20 mm margins (76 px), only the first page.
- rtf.js version `3.0.9`; bundle load order `WMFJS.bundle.min.js`, `EMFJS.bundle.min.js`, `RTFJS.bundle.min.js` from `https://cdn.jsdelivr.net/npm/rtf.js@3.0.9/dist/`.
- Every printed check in a test reads `True` on pass (`tests/CLAUDE.md`); a full run prints no `False`.
- All seven UI languages (en, de, es, fr, zh-Hans, zh-Hant, hy) stay complete; `tests/test_i18n.py` fails on a missing key.
- Version: `APP_VERSION` 1.66.0, `scan_watch.py` `__version__` and `tests/test_scan_watch_version.py` change together. Tag and push only when the user asks.

---

### Task 1: Spike — does the foreignObject snapshot work on real RTFs?

A throw-away check outside the repo's `tests/`. Nothing from this task is committed except one "Spike result" paragraph in the spec. If it fails, stop and report to the user: the plan then switches to html2canvas.

**Files:**
- Create (scratch, not in the repo): `$SPIKE/rtf_preview_spike.js`, `$SPIKE/spike.py` where `SPIKE` is a scratch folder outside the repo (the session scratchpad)
- Modify: `docs/superpowers/specs/2026-11-13-rtf-previews-design.md` (add "Spike result" section)

**Interfaces:**
- Produces: the exact JS of `rtfFirstPageCanvas(file)` (and its helpers) that Task 2 pastes into `dossiary.html` unchanged apart from the CDN loader.

- [ ] **Step 1: Write the JS under test**

`$SPIKE/rtf_preview_spike.js`:

```js
const RTF_PAGE_W = 794, RTF_PAGE_H = 1123, RTF_MARGIN = 76;
const RTF_MAX_BYTES = 2 * 1024 * 1024;

function blobToDataUrl(blob){
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(blob);
  });
}

// A snapshot can't load outside references: turn blob:/http images into data URLs.
async function inlineRtfImages(root){
  for(const img of root.querySelectorAll('img')){
    const src = img.getAttribute('src') || '';
    if(!src || src.startsWith('data:')) continue;
    try{ img.setAttribute('src', await blobToDataUrl(await (await fetch(src)).blob())); }
    catch(e){ img.remove(); }
  }
}

async function rtfFirstPageCanvas(file, RTFJS){
  if(file.size > RTF_MAX_BYTES) return null;
  const doc = new RTFJS.Document(await file.arrayBuffer());
  const elements = await doc.render();
  const box = document.createElement('div');
  box.style.cssText = `position:fixed; left:-10000px; top:0; width:${RTF_PAGE_W}px; height:${RTF_PAGE_H}px;`
    + ` overflow:hidden; background:#fff; color:#000; box-sizing:border-box; padding:${RTF_MARGIN}px;`
    + ` font:16px/1.3 'Times New Roman', serif;`;
  for(const e of elements) box.appendChild(e);
  document.body.appendChild(box);
  try{
    await inlineRtfImages(box);
    box.style.position = 'static';
    box.style.left = '0';
    const xhtml = new XMLSerializer().serializeToString(box);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${RTF_PAGE_W}" height="${RTF_PAGE_H}">`
      + `<foreignObject width="100%" height="100%">${xhtml}</foreignObject></svg>`;
    const img = await new Promise((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error('Could not draw RTF page'));
      el.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
    });
    const canvas = document.createElement('canvas');
    canvas.width = RTF_PAGE_W; canvas.height = RTF_PAGE_H;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    return canvas;
  } finally {
    box.remove();
  }
}
window.rtfFirstPageCanvas = rtfFirstPageCanvas;
```

- [ ] **Step 2: Write the driver**

`$SPIKE/spike.py` (usage: `python3 spike.py OUT_DIR [real.rtf ...]`):

```python
import asyncio, base64, struct, sys, zlib
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
REAL = [Path(p) for p in sys.argv[2:]]
BASE = 'https://cdn.jsdelivr.net/npm/rtf.js@3.0.9/dist/'
JS = (Path(__file__).with_name('rtf_preview_spike.js')).read_text()

def red_png(n=40):
    raw = b''.join(b'\x00' + b'\xe0\x20\x20' * n for _ in range(n))
    def chunk(t, d): c = struct.pack('>I', len(d)) + t + d; return c + struct.pack('>I', zlib.crc32(t + d))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')

FORMATTED = rb'{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}{\colortbl;\red200\green0\blue0;}' \
    rb'\pard\fs36\b Heading in bold\b0\par\fs22 Plain text with \i italic\i0 and \cf1 red\cf0 words.\par' \
    rb'\trowd\cellx3000\cellx6000\intbl Cell A\cell Cell B\cell\row\pard Last line.\par}'
PICTURE = b'{\\rtf1\\ansi Text before the picture.\\par {\\pict\\pngblip\\picw40\\pich40\\picwgoal1200\\pichgoal1200 ' \
    + red_png().hex().encode() + b'}\\par Text after.\\par}'
SAMPLES = {'formatted': FORMATTED, 'picture': PICTURE, 'broken': b'this is not rtf at all'}
for p in REAL: SAMPLES[p.stem[:40]] = p.read_bytes()

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('about:blank')
        for name in ('WMFJS.bundle.min.js', 'EMFJS.bundle.min.js', 'RTFJS.bundle.min.js'):
            await page.add_script_tag(url=BASE + name)
        await page.evaluate('RTFJS.loggingEnabled(false); WMFJS.loggingEnabled(false); EMFJS.loggingEnabled(false);')
        await page.add_script_tag(content=JS)
        for name, data in SAMPLES.items():
            res = await page.evaluate('''async ([b64, name]) => {
                const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                const file = new File([bytes], name + '.rtf', {type: 'text/rtf'});
                try{
                    const canvas = await rtfFirstPageCanvas(file, RTFJS);
                    if(!canvas) return {ok: false, why: 'null'};
                    const blob = await new Promise(r => canvas.toBlob(r, 'image/png'));   // throws if tainted
                    const px = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
                    let ink = 0; for(let i = 0; i < px.length; i += 4) if(px[i] < 200 || px[i+1] < 200 || px[i+2] < 200) ink++;
                    const buf = new Uint8Array(await blob.arrayBuffer());
                    let s = ''; for(const b of buf) s += String.fromCharCode(b);
                    return {ok: true, ink: ink / (canvas.width * canvas.height), png: btoa(s)};
                }catch(e){ return {ok: false, why: String(e)}; }
            }''', [base64.b64encode(data).decode(), name])
            if res['ok']:
                (OUT / f'{name}.png').write_bytes(base64.b64decode(res['png']))
            print(f"{name}: ok={res['ok']} " + (f"ink={res['ink']:.4f}" if res['ok'] else f"why={res['why']}"))
        await browser.close()
asyncio.run(main())
```

- [ ] **Step 3: Run it on the built-in samples and three real RTFs**

Run (from the scratch folder; the three real files are any RTFs from the machine, for example three from `mdfind -onlyin ~ 'kMDItemFSName == "*.rtf"c'`, preferably ones with more than a few lines):

```bash
python3 spike.py out /path/one.rtf /path/two.rtf /path/three.rtf
```

Expected: `formatted: ok=True ink=0.0xxx`, `picture: ok=True ink=…` (the picture adds ink), `broken: ok=False why=…` or a nearly blank page; each real file `ok=True` with `ink` above 0.005. PNGs appear in `out/`.

- [ ] **Step 4: Look at the pictures**

Open each PNG in `out/` with the Read tool. Check: text readable and in black on white; bold, italic and the red word visible in `formatted`; the table cells in a row; the red square visible in `picture`; real files look like a document's first page, clipped at the page bottom.

- [ ] **Step 5: Decide and record**

If every `ok=True` sample is readable: add this to the spec under a new heading `## Spike result` (replace the bracketed parts with what was seen, no placeholders left):

```markdown
## Spike result

2026-11-13: the foreignObject snapshot works in headless Chromium on the built-in samples (formatted text, table,
embedded PNG) and on three real RTFs; the canvas is not tainted (`toBlob` succeeds) and text, bold, colour and the
picture are visible. A malformed file gives [null / a blank page]. The code in Task 2 is the spike's JS.
```

If the snapshot is tainted, blank, or unreadable for real files: STOP, do not continue, and report to the human partner (fallback is html2canvas).

- [ ] **Step 6: Commit the spec paragraph**

```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
git add docs/superpowers/specs/2026-11-13-rtf-previews-design.md
git commit -m "docs: RTF preview spike result"
```

---

### Task 2: RTF branch in `generateThumbnail()` and the missing-preview count

**Files:**
- Modify: `dossiary.html` — after `ensurePdfJs()` (around line 4472, before `getPdfPageCount`), inside `generateThumbnail()` (line ~4524), and `docsMissingPreview()` (line ~15160)
- Test: `tests/test_rtf_preview.py` (created in Task 3; Task 2 is checked by Task 3's test, plus the manual run in Step 4 below)

**Interfaces:**
- Consumes: `canvasToThumbBytes(canvas) -> Promise<Uint8Array>`, `scaledCanvasFromImage(img)` (reads `width`/`height` and calls `drawImage`, so a canvas works as its input), `THUMB_MAX_DIM`.
- Produces: `isRtfFile(file) -> boolean`, `ensureRtfJs() -> Promise<RTFJS>`, `rtfFirstPageCanvas(file) -> Promise<HTMLCanvasElement|null>`; `generateThumbnail(file)` returns JPEG bytes for RTF files or `null`.

- [ ] **Step 1: Add the RTF helpers**

Insert directly above `// Reads just the page count from a PDF File` (the comment before `getPdfPageCount`):

```js
  // --- RTF previews ---------------------------------------------------------
  // Browsers can't draw RTF, so rtf.js turns it into HTML, which is snapshotted
  // through an SVG foreignObject onto a canvas. Lazy and pinned, like pdf.js.
  const RTFJS_VERSION = '3.0.9'; // the three bundles must come from the same release
  const RTF_MAX_BYTES = 2 * 1024 * 1024;
  const RTF_RENDER_TIMEOUT_MS = 10000;
  const RTF_PAGE_W = 794, RTF_PAGE_H = 1123, RTF_MARGIN = 76; // A4 at 96 dpi, 20 mm margins
  let RtfJsLoaded = false;

  function isRtfFile(file){
    return file.type === 'text/rtf' || file.type === 'application/rtf' || /\.rtf$/i.test(file.name || '');
  }

  async function ensureRtfJs(){
    if(RtfJsLoaded && window.RTFJS) return window.RTFJS;
    // Order matters: RTFJS draws embedded pictures with the WMFJS and EMFJS globals.
    for(const name of ['WMFJS.bundle.min.js', 'EMFJS.bundle.min.js', 'RTFJS.bundle.min.js']){
      await new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = `https://cdn.jsdelivr.net/npm/rtf.js@${RTFJS_VERSION}/dist/${name}`;
        s.onload = resolve;
        s.onerror = () => reject(new Error('Failed to load RTF reader from CDN'));
        document.head.appendChild(s);
      });
    }
    window.RTFJS.loggingEnabled(false);
    window.WMFJS.loggingEnabled(false);
    window.EMFJS.loggingEnabled(false);
    RtfJsLoaded = true;
    return window.RTFJS;
  }

  function blobToDataUrl(blob){
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(r.error);
      r.readAsDataURL(blob);
    });
  }

  // A snapshot can't load outside references: turn blob:/http images into data URLs.
  async function inlineRtfImages(root){
    for(const img of root.querySelectorAll('img')){
      const src = img.getAttribute('src') || '';
      if(!src || src.startsWith('data:')) continue;
      try{ img.setAttribute('src', await blobToDataUrl(await (await fetch(src)).blob())); }
      catch(e){ img.remove(); }
    }
  }

  // First page of an RTF as a canvas, or null when it is too big. Throws when the RTF can't be read.
  async function rtfFirstPageCanvas(file){
    if(file.size > RTF_MAX_BYTES) return null;
    const RTFJS = await ensureRtfJs();
    const doc = new RTFJS.Document(await file.arrayBuffer());
    const elements = await doc.render();
    const box = document.createElement('div');
    box.style.cssText = `position:fixed; left:-10000px; top:0; width:${RTF_PAGE_W}px; height:${RTF_PAGE_H}px;`
      + ` overflow:hidden; background:#fff; color:#000; box-sizing:border-box; padding:${RTF_MARGIN}px;`
      + ` font:16px/1.3 'Times New Roman', serif;`;
    for(const e of elements) box.appendChild(e);
    document.body.appendChild(box);
    try{
      await inlineRtfImages(box);
      box.style.position = 'static';
      box.style.left = '0';
      const xhtml = new XMLSerializer().serializeToString(box);
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${RTF_PAGE_W}" height="${RTF_PAGE_H}">`
        + `<foreignObject width="100%" height="100%">${xhtml}</foreignObject></svg>`;
      const img = await new Promise((resolve, reject) => {
        const el = new Image();
        el.onload = () => resolve(el);
        el.onerror = () => reject(new Error('Could not draw RTF page'));
        el.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      });
      const canvas = document.createElement('canvas');
      canvas.width = RTF_PAGE_W; canvas.height = RTF_PAGE_H;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#fff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      return canvas;
    } finally {
      box.remove();
    }
  }

  // Resolves to null when the promise takes longer than ms (the work itself can't be cancelled).
  function nullAfter(promise, ms){
    return Promise.race([promise, new Promise(resolve => setTimeout(() => resolve(null), ms))]);
  }

```

- [ ] **Step 2: Add the branch to `generateThumbnail()`**

In `generateThumbnail(file)`, replace the final lines

```js
      return canvasToThumbBytes(canvas);
    }
    return null; // unsupported format -- not an error, just nothing to generate from
  }
```

with

```js
      return canvasToThumbBytes(canvas);
    }
    if(isRtfFile(file)){
      // Any trouble (unreadable RTF, CDN unreachable, too big, too slow) just means no preview.
      try{
        const canvas = await nullAfter(rtfFirstPageCanvas(file), RTF_RENDER_TIMEOUT_MS);
        if(!canvas) return null;
        return canvasToThumbBytes(scaledCanvasFromImage(canvas));
      }catch(e){
        return null;
      }
    }
    return null; // unsupported format -- not an error, just nothing to generate from
  }
```

`scaledCanvasFromImage(img)` only reads `img.width`/`img.height` and calls `drawImage`, which a canvas supports, so it scales the page to 640 px as for other sources.

Also update the comment above `generateThumbnail` (the one starting `// Generates a small PNG preview`): change "Images are just downscaled directly; PDFs get their first page rendered via pdf.js." to "Images are just downscaled directly; PDFs get their first page rendered via pdf.js; RTFs are drawn by rtf.js." and keep the rest.

- [ ] **Step 3: Count RTF documents as missing a preview**

In `docsMissingPreview(sorted)` change the regex `\.(pdf|jpe?g|png)$` to `\.(pdf|jpe?g|png|rtf)$`. Leave `docsWithOlderPreview` as it is.

- [ ] **Step 4: Check it by hand against a real RTF**

```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
python3 - <<'E'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page()
        errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto('file:///Users/aarneaarebye/Projects/Paperless/Dossiary/dossiary.html')
        print('page loads without errors:', errs == [])
        await b.close()
asyncio.run(main())
E
```

Expected: `page loads without errors: True`. (The full behaviour is checked by Task 3's test.)

- [ ] **Step 5: Commit**

```bash
git add dossiary.html
git commit -m "feat: first-page previews for RTF documents (rtf.js)"
```

---

### Task 3: Playwright test

**Files:**
- Create: `tests/test_rtf_preview.py`

**Interfaces:**
- Consumes: `tests/stub_studio2.js` (`window.__makeEmptyRoot()`, `FakeDirHandle`, `FakeFileHandle`), the capture flow used by `tests/test_thumbnails.py` (`#add-btn`, `#file-input`, `#f-title`, `#save-doc-btn`), `#create-previews-btn`.

- [ ] **Step 1: Write the test**

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (stub_studio2.js, ...) work regardless of the CWD this test is invoked from
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, sys, urllib.request
from playwright.async_api import async_playwright

RTFJS_URL = 'https://cdn.jsdelivr.net/npm/rtf.js@3.0.9/dist/RTFJS.bundle.min.js'
try:
    urllib.request.urlopen(RTFJS_URL, timeout=15).read(10)
except Exception as e:
    print(f"SKIP: rtf.js is not reachable from here ({e})")
    sys.exit(0)

SIMPLE_RTF = (rb'{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\pard\fs36\b Hello RTF\b0\par'
              rb'\fs22 A paragraph of ordinary text to draw on the page.\par}')
BROKEN_RTF = b'this is not an rtf document at all'
TOO_BIG_RTF = b'{\\rtf1\\ansi ' + b'a' * (2 * 1024 * 1024 + 10) + b'}'

SEED = {
    "documents": [{
        "id": 1, "title": "Letter", "category": "Test", "subcategory": None,
        "document_type": None, "payment_method": None, "amount": None, "date": None,
        "import_date": None, "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": "files/1_letter.rtf", "original_file_path": None,
        "created_at": "2026-01-01T00:00:00Z", "source": "migrated", "source_legacy_id": 1,
        "thumbnail_path": None,
    }],
    "tags": [], "document_tags": [], "people": [], "document_people": [], "settings": [],
}

async def thumb_info(page, name):
    return await page.evaluate("""
        async (name) => {
            try {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('thumbnails');
                const f = await (await dir.getFileHandle(name)).getFile();
                const b = new Uint8Array(await f.arrayBuffer());
                return { exists: true, size: b.length, head: [b[0], b[1]] };
            } catch(e) { return { exists: false }; }
        }
    """, name)

async def persisted_docs(page):
    return (await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            return JSON.parse(await (await fh.getFile()).text());
        })()
    """))['documents']

async def capture(page, title, name, mime, data):
    await page.click('#add-btn')
    await page.wait_for_timeout(100)
    await page.set_input_files('#file-input', files=[{'name': name, 'mimeType': mime, 'buffer': data}])
    await page.wait_for_timeout(100)
    await page.fill('#f-title', title)
    await page.click('#save-doc-btn')
    await page.wait_for_timeout(1500)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)

        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()   # rtf.js comes from the real CDN
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        # === 1: a normal RTF gets a JPEG preview of the right size ===
        await capture(page, 'Simple RTF', 'letter.rtf', 'text/rtf', SIMPLE_RTF)
        t = await thumb_info(page, '1.jpg')
        print("RTF preview file written:", t['exists'])
        print("RTF preview is a JPEG:", t.get('head') == [255, 216])
        print("RTF preview is more than a blank stub (> 3 KB):", t.get('size', 0) > 3000)
        sizes = await page.evaluate("""
            (async () => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('thumbnails');
                const f = await (await dir.getFileHandle('1.jpg')).getFile();
                const bmp = await createImageBitmap(f);
                return [bmp.width, bmp.height];
            })()
        """)
        print("RTF preview longest side is 640 px (A4 portrait):", max(sizes) == 640 and sizes[1] > sizes[0])

        # === 2: the type is not needed -- the .rtf name is enough ===
        await capture(page, 'Octet RTF', 'other.rtf', 'application/octet-stream', SIMPLE_RTF)
        print("RTF with a generic type still gets a preview:", (await thumb_info(page, '2.jpg'))['exists'])

        # === 3: a broken RTF keeps no preview, and nothing throws ===
        await capture(page, 'Broken RTF', 'broken.rtf', 'text/rtf', BROKEN_RTF)
        docs = await persisted_docs(page)
        broken = [d for d in docs if d['title'] == 'Broken RTF'][0]
        print("broken RTF is saved without a preview:", not broken['thumbnail_path'])

        # === 4: an RTF over 2 MB keeps no preview ===
        await capture(page, 'Huge RTF', 'huge.rtf', 'text/rtf', TOO_BIG_RTF)
        docs = await persisted_docs(page)
        huge = [d for d in docs if d['title'] == 'Huge RTF'][0]
        print("RTF over 2 MB is saved without a preview:", not huge['thumbnail_path'])

        # === 5: "Create missing previews" counts an RTF document ===
        await page.close()
        page = await browser.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js + f"""
        window.__makeRtfRoot = function() {{
            const root = new FakeDirHandle('TestLib');
            const dbBytes = new TextEncoder().encode(JSON.stringify({json.dumps(SEED)}));
            root._children.set('library.sqlite', new FakeFileHandle('library.sqlite', dbBytes));
            const filesDir = new FakeDirHandle('files');
            root._children.set('files', filesDir);
            filesDir._children.set('1_letter.rtf', new FakeFileHandle('1_letter.rtf', new TextEncoder().encode({json.dumps(SIMPLE_RTF.decode())})));
            return root;
        }};
        """)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeRtfRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)
        btn = page.locator('#create-previews-btn')
        print("Create missing previews button is shown for an RTF:", await btn.is_visible())
        print("button counts 1 document:", '(1)' in (await btn.inner_text()))
        await btn.click()
        await page.wait_for_timeout(3000)
        print("bulk job made the RTF preview:", (await thumb_info(page, '1.jpg'))['exists'])

        print("no page or console errors:", errors == [])
        if errors: print(errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run it and read every line**

Run: `cd tests && python3 test_rtf_preview.py`
Expected: every printed line ends in `True` (or `SKIP: …` and exit 0 when offline). If the grid view is not the default view in the seeded library, the button check fails: in that case click the grid switch first (`#view-grid-btn` or the control the grid test uses — check `tests/test_grid_view.py` for the selector) and rerun.

- [ ] **Step 3: Run the neighbours to check nothing else moved**

Run: `cd tests && for t in test_thumbnails test_regenerate test_grid_view test_page_count; do echo "== $t"; python3 $t.py 2>&1 | grep -c ": False"; done`
Expected: `0` for each.

- [ ] **Step 4: Commit**

```bash
git add tests/test_rtf_preview.py
git commit -m "test: RTF previews (capture, type-less file, broken, oversized, bulk job)"
```

---

### Task 4: Libraries list, docs, version

**Files:**
- Modify: `dossiary.html` (`OPEN_SOURCE_LIBRARIES`, seven translation blocks, `APP_VERSION`), `scan_watch.py` (`__version__`), `tests/test_scan_watch_version.py`, `docs/architecture/02-data-and-fields.md`, `README.md`, `README.de.md`, `tests/coverage/01-capture-ocr-fields-inbox-nav.md`

**Interfaces:**
- Produces: translation key `librariesUseRtfJs` in all seven languages.

- [ ] **Step 1: Add rtf.js to the open-source libraries list**

In `OPEN_SOURCE_LIBRARIES`, after the pdf.js line add:

```js
    { name: 'rtf.js', url: 'https://github.com/tbluemel/rtf.js', license: 'MIT', useKey: 'librariesUseRtfJs' },
```

- [ ] **Step 2: Add the seven translations**

Run this once (it inserts a new line after each `librariesUsePdfJs:` line, in file order en, es, fr, de, zh-Hans, zh-Hant, hy):

```bash
python3 - <<'E'
import re
p = 'dossiary.html'
s = open(p, encoding='utf-8').read()
texts = [
  "'Reading RTF documents to make previews (first page)'",
  "'Lectura de documentos RTF para crear vistas previas (primera página)'",
  '"Lecture des documents RTF pour créer des aperçus (première page)"',
  "'Lesen von RTF-Dokumenten für Vorschauen (erste Seite)'",
  "'读取 RTF 文档以生成预览（首页）'",
  "'讀取 RTF 文件以產生預覽（首頁）'",
  '"RTF փաստաթղթերի ընթերցում նախադիտումների համար (առաջին էջը)"',
]
lines = s.split('\n'); out = []; i = 0
for line in lines:
    out.append(line)
    m = re.match(r'(\s*)librariesUsePdfJs:', line)
    if m:
        out.append(f"{m.group(1)}librariesUseRtfJs: {texts[i]},"); i += 1
assert i == 7, i
open(p, 'w', encoding='utf-8').write('\n'.join(out))
print('inserted', i)
E
```

Expected: `inserted 7`. Then run `cd tests && python3 test_i18n.py 2>&1 | grep -c ": False"` → `0`.

- [ ] **Step 3: Update the docs**

- `docs/architecture/02-data-and-fields.md`: in the "Document previews" note replace "`generateThumbnail()` handles two input types only: `image/*` (direct canvas downscale) and `application/pdf` (first page rendered via pdf.js) — anything else returns `null`, which is an expected, non-error outcome, not something to add more format branches for without being asked." with: "`generateThumbnail()` handles three input types: `image/*` (direct canvas downscale), `application/pdf` (first page rendered via pdf.js) and RTF (`isRtfFile()`: type `text/rtf` or `application/rtf`, or a `.rtf` name) — anything else returns `null`, which is an expected, non-error outcome, not something to add more format branches for without being asked. RTF was added on request (most documents in Mariner-migrated libraries are RTF): `rtfFirstPageCanvas()` loads rtf.js (three bundles, pinned to `RTFJS_VERSION`, loaded in WMFJS, EMFJS, RTFJS order), draws the first A4 page in a hidden box and snapshots it through an SVG `foreignObject`; files over 2 MB, renders over 10 s and unreadable RTF return `null`. The design is `docs/superpowers/specs/2026-11-13-rtf-previews-design.md`."
- `README.md` "Document previews" bullet: change "(an image gets downscaled directly; a PDF gets its first page rendered via [pdf.js](https://mozilla.github.io/pdf.js/))" to "(an image gets downscaled directly; a PDF gets its first page rendered via [pdf.js](https://mozilla.github.io/pdf.js/); an RTF gets its first page drawn via [rtf.js](https://github.com/tbluemel/rtf.js))". In the Grid view bullet, after "**Create missing previews** makes them for the listed documents" add "(images, PDFs and RTF files)". Make the same two changes in `README.de.md` in German (find the matching sentences with `grep -n "pdf.js" README.de.md` and `grep -n "Vorschauen erstellen" README.de.md`).
- `tests/coverage/01-capture-ocr-fields-inbox-nav.md`: after the sentence about `test_thumbnails.py`/`test_regenerate.py` add one sentence: "`test_rtf_preview.py` captures RTF documents (a real rtf.js from the CDN, skipped when offline): a JPEG of 640 px longest side, a type-less `.rtf`, a broken and an oversized RTF without a preview, and the grid's Create missing previews counting and making an RTF preview."

- [ ] **Step 4: Bump the version**

`dossiary.html`: `const APP_VERSION = '1.66.0';`. `scan_watch.py`: `__version__ = '1.66.0'`. `tests/test_scan_watch_version.py`: `'scan_watch.py 1.66.0'`.

- [ ] **Step 5: Run the affected tests**

Run: `cd tests && for t in test_i18n test_scan_watch_version test_thumbnails test_regenerate test_grid_view test_rtf_preview; do echo "== $t"; python3 $t.py 2>&1 | grep -c ": False"; done`
Expected: `0` for each.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html scan_watch.py tests docs README.md README.de.md
git commit -m "feat: RTF previews (1.66.0): libraries list, docs, version"
```

Do not tag or push. Report to the human partner that 1.66.0 is committed and ready for the release steps in `.claude/skills/cutting-a-release/SKILL.md`.
