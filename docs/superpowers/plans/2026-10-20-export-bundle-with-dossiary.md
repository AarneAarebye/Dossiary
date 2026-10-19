# Export as Library, Bundled with Dossiary — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export as library can also create a bundle — the library plus a copy of `dossiary.html` and a `How to open.txt` — as a folder, a `.zip` file, or both.

**Architecture:** Everything lives in `dossiary.html` (single-file app). A small built-in zip writer (stored entries, CRC32, ZIP64) streams entries into one `createWritable()` stream. Dossiary gets its own copy from jsDelivr at the running version's git tag, else from a copy the person chose once (contents kept in IndexedDB). The existing Export-as-library dialog gains a "What to create" choice; its export loop writes through a "sink" that is either a folder or the zip.

**Tech Stack:** Vanilla JS in `dossiary.html`; File System Access API; IndexedDB; Playwright for Python tests with `tests/stub_studio2.js`.

**Spec:** `docs/superpowers/specs/2026-10-20-export-bundle-with-dossiary-design.md`

## Global Constraints

- No new dependency, no build step: the zip writer and CRC32 are written in `dossiary.html`.
- Zip entries are stored (method 0), names UTF-8 (general-purpose flag bit 11, `0x0800`), paths start with `<Bundle>/`.
- ZIP64 when a size/offset is `>= zipLimits.zip64Bytes` (default `0xFFFFFFFF`) or the entry count `>= zipLimits.zip64Entries` (default `0xFFFF`).
- Download URL: `https://cdn.jsdelivr.net/gh/AarneAarebye/Dossiary@v${APP_VERSION}/dossiary.html`, accepted only if it contains `const APP_VERSION = '<APP_VERSION>'`; 15 s timeout.
- Stored copy: IndexedDB database `dossiary-bundle-source`, store `copies` (keyPath `id`), record `{id: 'dossiary.html', version, text, savedAt}`.
- Order on Start: name check → destination folder picker → refuse existing folder/zip → get dossiary.html → write. "Library only" never calls `fetch`.
- Bundle layout: `<Bundle>/dossiary.html`, `<Bundle>/<Name>.dossiary/…`, `<Bundle>/How to open.txt`; zip file `<Bundle>.zip`. `<Bundle>` is `libraryFolderName(raw)` without `.dossiary`.
- `How to open.txt`: current UI language, then (if not English) `\n\n----\n\n` and the English text.
- Email-size note when the zip is larger than `zipLimits.emailBytes` (default 25 MB = `25 * 1024 * 1024`).
- Nothing half-made remains after Stop/failure/nothing exported: partial zip aborted and removed, created folder removed recursively.
- Move puts documents in the Waste bin only after every chosen output is complete.
- Every new UI string exists in all seven `STRINGS` blocks (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`, `hy`) with the same `{placeholders}`.
- Tests print `True` for every passing check (see `tests/CLAUDE.md`); never print an expected `False`.
- Run single tests with `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_<name>.py`. Full suite: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && for f in /Users/aarneaarebye/Projects/Paperless/Dossiary/tests/test_*.py; do echo "== $f"; python3 "$f" 2>&1 | grep -E ": False|Error|Traceback|JS ERRORS: \[.+\]"; done` — any output line besides the `== file` headers is a failure.

---

### Task 1: The test stub's file writer appends, like the real one

The real `FileSystemWritableFileStream.write()` appends at the current position; the stub's replaces the buffer, so a zip written in many `write()` calls would keep only its last piece. Also add `abort()`.

**Files:**
- Modify: `tests/stub_studio2.js:13-31` (`FakeFileHandle.createWritable`)
- Test: `tests/test_stub_writable.py` (new)

**Interfaces:**
- Produces: stub writables whose `write()` appends (ArrayBuffer, any typed-array view, string, Blob), `close()` commits, `abort()` discards without committing.

- [ ] **Step 1: Write the failing test** — create `tests/test_stub_writable.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

# The stub's createWritable() must behave like the real stream: every write()
# appends, close() commits, abort() discards. The zip export depends on it.
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        result = await page.evaluate("""async () => {
            const dir = window.__makeEmptyRoot();
            const h = await dir.getFileHandle('a.bin', { create: true });
            let w = await h.createWritable();
            await w.write(new Uint8Array([1, 2]));
            await w.write(new Uint8Array([9, 3, 4, 9]).subarray(1, 3));
            await w.write('AB');
            await w.write(new Uint8Array([5]).buffer);
            await w.write(new Blob([new Uint8Array([6])]));
            await w.close();
            const first = Array.from(new Uint8Array(await (await h.getFile()).arrayBuffer()));
            w = await h.createWritable();
            await w.write(new Uint8Array([7]));
            await w.abort();
            const afterAbort = Array.from(new Uint8Array(await (await h.getFile()).arrayBuffer()));
            return { first, afterAbort };
        }""")
        print("Writes append, views use only their own bytes:", result['first'] == [1, 2, 3, 4, 65, 66, 5, 6], result['first'])
        print("abort() keeps the earlier contents:", result['afterAbort'] == [1, 2, 3, 4, 65, 66, 5, 6])
        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_stub_writable.py`
Expected: `Writes append…: False` (the stub keeps only the last write) and a page error or `False` for abort (no `abort` method).

- [ ] **Step 3: Change the stub** — in `tests/stub_studio2.js`, replace the `return { write: …, close: … };` object inside `FakeFileHandle.createWritable()` with:

```js
    return {
      // Like the real stream: each write appends at the current position.
      write: async (data) => {
        let chunk;
        if (data instanceof ArrayBuffer) chunk = new Uint8Array(data);
        else if (ArrayBuffer.isView(data)) chunk = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
        else if (typeof data === 'string') chunk = new TextEncoder().encode(data);
        else if (data && data.arrayBuffer) chunk = new Uint8Array(await data.arrayBuffer());
        else chunk = new Uint8Array(0);
        const next = new Uint8Array(buf.length + chunk.length);
        next.set(buf);
        next.set(chunk, buf.length);
        buf = next;
      },
      close: async () => { self._bytes = buf; },
      abort: async () => { buf = new Uint8Array(0); },
    };
```

- [ ] **Step 4: Run the new test, then the full suite** (other code may have relied on replace-on-write)

Run: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_stub_writable.py`
Expected: both lines `True`, `JS ERRORS: []`.
Then run the full-suite command from Global Constraints. Expected: only `== file` header lines. If a test fails, the app code it exercises writes twice to one stream expecting replacement — report it (DONE_WITH_CONCERNS) rather than changing app code.

- [ ] **Step 5: Commit**

```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
git add tests/stub_studio2.js tests/test_stub_writable.py
git commit -m "Test stub: writable streams append like the real API, and can abort"
```

---

### Task 2: Built-in zip writer (stored entries, CRC32, ZIP64)

**Files:**
- Modify: `dossiary.html` — insert the zip writer block directly before the line `  // --- Export selected documents ---`; add debug hooks directly after `window.__DEBUG_buildExportLibrary = …` (around line 4877).
- Test: `tests/test_zip_writer.py` (new)

**Interfaces:**
- Produces (module scope inside the app IIFE):
  - `const zipLimits = { zip64Bytes, zip64Entries, emailBytes }` (mutable object)
  - `function crc32(bytes: Uint8Array): number`
  - `function createZipWriter(writable: {write(Uint8Array): Promise}): { size: number (getter), add(name: string, data: Uint8Array): Promise, finish(): Promise }` — `add()` calls must not overlap.
  - `window.__DEBUG_buildZip(entries: [name, text][], limits?): Promise<number[]>`, `window.__DEBUG_setZipLimits(limits)`, `window.__DEBUG_crc32(text): number`

- [ ] **Step 1: Write the failing test** — create `tests/test_zip_writer.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, io, zipfile
from playwright.async_api import async_playwright

# The built-in zip writer behind "Export as library" bundles: stored entries,
# UTF-8 names, CRC32, and ZIP64 records -- read back with Python's zipfile.
def read_zip(data):
    return zipfile.ZipFile(io.BytesIO(bytes(data)))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        print("CRC32 of '123456789' is the standard check value:", await page.evaluate("() => window.__DEBUG_crc32('123456789')") == 0xCBF43926)

        entries = [["Tax 2025/How to open.txt", "Open it in Chrome.\n"],
                   ["Tax 2025/Tax 2025.dossiary/files/4_Հաշիվ_发票.pdf", "%PDF fake"],
                   ["Tax 2025/empty.txt", ""]]
        z = read_zip(await page.evaluate("(e) => window.__DEBUG_buildZip(e)", entries))
        print("Every entry listed, in order:", z.namelist() == [e[0] for e in entries], z.namelist())
        print("Contents read back:", all(z.read(n).decode() == c for n, c in entries))
        print("CRCs check out:", z.testzip() is None)
        print("Stored, not compressed:", all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist()))
        print("Names flagged as UTF-8:", all(i.flag_bits & 0x800 for i in z.infolist()))

        raw = await page.evaluate("(e) => window.__DEBUG_buildZip(e, { zip64Bytes: 4, zip64Entries: 2 })", entries)
        print("Lowered limits write ZIP64 end records:", b'PK\x06\x06' in bytes(raw) and b'PK\x06\x07' in bytes(raw))
        z = read_zip(raw)
        print("ZIP64 zip reads back:", z.namelist() == [e[0] for e in entries] and all(z.read(n).decode() == c for n, c in entries) and z.testzip() is None)
        print("Limits restored afterwards:", b'PK\x06\x06' not in bytes(await page.evaluate("(e) => window.__DEBUG_buildZip(e)", entries)))

        z = read_zip(await page.evaluate("() => window.__DEBUG_buildZip([])"))
        print("An empty zip is valid:", z.namelist() == [])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_zip_writer.py`
Expected: page error / `TypeError: window.__DEBUG_crc32 is not a function`.

- [ ] **Step 3: Add the zip writer** — insert directly before `  // --- Export selected documents ---` in `dossiary.html`:

```js
  // --- .zip writing (Export as library with Dossiary) ---
  // Stored entries only -- scans and PDFs barely compress -- appended to one
  // writable stream, so a bundle of any size never sits in memory. ZIP64
  // records are added once a size, an offset or the entry count passes what
  // the classic format can hold; tests lower those limits via zipLimits.
  const zipLimits = { zip64Bytes: 0xFFFFFFFF, zip64Entries: 0xFFFF, emailBytes: 25 * 1024 * 1024 };
  const CRC32_TABLE = (() => {
    const table = new Uint32Array(256);
    for(let n = 0; n < 256; n++){
      let c = n;
      for(let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
    return table;
  })();
  function crc32(bytes){
    let c = 0xFFFFFFFF;
    for(let i = 0; i < bytes.length; i++) c = CRC32_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  function dosDateTime(date){
    const time = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
    const day = ((Math.max(date.getFullYear(), 1980) - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
    return { time, day };
  }
  // writable: anything with an async write(Uint8Array). add() calls must not
  // overlap; finish() writes the central directory; size is the bytes written.
  function createZipWriter(writable){
    const encoder = new TextEncoder();
    const { time, day } = dosDateTime(new Date());
    const entries = [];
    let offset = 0;
    const put = async (bytes) => { await writable.write(bytes); offset += bytes.length; };
    const record = (length, fill) => { const buf = new Uint8Array(length); fill(new DataView(buf.buffer)); return buf; };
    return {
      get size(){ return offset; },
      async add(name, data){
        const nameBytes = encoder.encode(name);
        const size = data.length, crc = crc32(data), start = offset;
        const bigSize = size >= zipLimits.zip64Bytes;
        const local = record(30 + nameBytes.length + (bigSize ? 20 : 0), v => {
          v.setUint32(0, 0x04034b50, true);
          v.setUint16(4, bigSize ? 45 : 20, true);
          v.setUint16(6, 0x0800, true); // names are UTF-8
          v.setUint16(8, 0, true);      // stored
          v.setUint16(10, time, true);
          v.setUint16(12, day, true);
          v.setUint32(14, crc, true);
          v.setUint32(18, bigSize ? 0xFFFFFFFF : size, true);
          v.setUint32(22, bigSize ? 0xFFFFFFFF : size, true);
          v.setUint16(26, nameBytes.length, true);
          v.setUint16(28, bigSize ? 20 : 0, true);
          if(bigSize){
            const x = 30 + nameBytes.length;
            v.setUint16(x, 0x0001, true);
            v.setUint16(x + 2, 16, true);
            v.setBigUint64(x + 4, BigInt(size), true);
            v.setBigUint64(x + 12, BigInt(size), true);
          }
        });
        local.set(nameBytes, 30);
        await put(local);
        await put(data);
        entries.push({ nameBytes, size, crc, start });
      },
      async finish(){
        const cdStart = offset;
        for(const e of entries){
          const big = e.size >= zipLimits.zip64Bytes || e.start >= zipLimits.zip64Bytes;
          const central = record(46 + e.nameBytes.length + (big ? 28 : 0), v => {
            v.setUint32(0, 0x02014b50, true);
            v.setUint16(4, big ? 45 : 20, true);
            v.setUint16(6, big ? 45 : 20, true);
            v.setUint16(8, 0x0800, true);
            v.setUint16(10, 0, true);
            v.setUint16(12, time, true);
            v.setUint16(14, day, true);
            v.setUint32(16, e.crc, true);
            v.setUint32(20, big ? 0xFFFFFFFF : e.size, true);
            v.setUint32(24, big ? 0xFFFFFFFF : e.size, true);
            v.setUint16(28, e.nameBytes.length, true);
            v.setUint16(30, big ? 28 : 0, true);
            v.setUint32(42, big ? 0xFFFFFFFF : e.start, true);
            if(big){
              const x = 46 + e.nameBytes.length;
              v.setUint16(x, 0x0001, true);
              v.setUint16(x + 2, 24, true);
              v.setBigUint64(x + 4, BigInt(e.size), true);
              v.setBigUint64(x + 12, BigInt(e.size), true);
              v.setBigUint64(x + 20, BigInt(e.start), true);
            }
          });
          central.set(e.nameBytes, 46);
          await put(central);
        }
        const cdSize = offset - cdStart, count = entries.length;
        const big = count >= zipLimits.zip64Entries || cdStart >= zipLimits.zip64Bytes || cdSize >= zipLimits.zip64Bytes;
        if(big){
          const record64At = offset;
          await put(record(56, v => {
            v.setUint32(0, 0x06064b50, true);
            v.setBigUint64(4, 44n, true);
            v.setUint16(12, 45, true);
            v.setUint16(14, 45, true);
            v.setBigUint64(24, BigInt(count), true);
            v.setBigUint64(32, BigInt(count), true);
            v.setBigUint64(40, BigInt(cdSize), true);
            v.setBigUint64(48, BigInt(cdStart), true);
          }));
          await put(record(20, v => {
            v.setUint32(0, 0x07064b50, true);
            v.setBigUint64(8, BigInt(record64At), true);
            v.setUint32(16, 1, true);
          }));
        }
        await put(record(22, v => {
          v.setUint32(0, 0x06054b50, true);
          v.setUint16(8, big ? 0xFFFF : count, true);
          v.setUint16(10, big ? 0xFFFF : count, true);
          v.setUint32(12, big ? 0xFFFFFFFF : cdSize, true);
          v.setUint32(16, big ? 0xFFFFFFFF : cdStart, true);
        }));
      },
    };
  }

```

- [ ] **Step 4: Add the debug hooks** — directly after the `window.__DEBUG_buildExportLibrary = …` line:

```js
  // test-only hooks (tests/test_zip_writer.py, tests/test_export_bundle.py)
  window.__DEBUG_crc32 = (text) => crc32(new TextEncoder().encode(text));
  window.__DEBUG_setZipLimits = (limits) => { Object.assign(zipLimits, limits); };
  window.__DEBUG_buildZip = async (entries, limits) => {
    const saved = { ...zipLimits };
    Object.assign(zipLimits, limits || {});
    try{
      const chunks = [];
      const zip = createZipWriter({ write: async (bytes) => { chunks.push(bytes.slice()); } });
      for(const [name, text] of entries) await zip.add(name, new TextEncoder().encode(text));
      await zip.finish();
      const out = new Uint8Array(zip.size);
      let at = 0;
      for(const c of chunks){ out.set(c, at); at += c.length; }
      return Array.from(out);
    }finally{ Object.assign(zipLimits, saved); }
  };
```

(`zipLimits` and `createZipWriter` are declared later in the file than line 4877; that is fine because the hooks only run after the IIFE has finished. If `__DEBUG_buildExportLibrary` turns out to sit inside a function rather than at IIFE top level, place these hooks at IIFE top level right after the zip writer block instead.)

- [ ] **Step 5: Run the test**

Run: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_zip_writer.py`
Expected: every line `True`, `JS ERRORS: []`. Python's `zipfile` is the reference reader here.

- [ ] **Step 6: Commit**

```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
git add dossiary.html tests/test_zip_writer.py
git commit -m "Built-in zip writer: stored entries, UTF-8 names, CRC32, ZIP64"
```

---

### Task 3: Dossiary's own copy, bundle names, How to open text, and all new strings

**Files:**
- Modify: `dossiary.html` — `t()` (line ~3307); all seven `STRINGS` blocks (insert the new keys right after each block's `exportLibraryOpen` entry); new helper block directly after the zip writer block from Task 2; debug hooks next to Task 2's hooks.
- Test: `tests/test_export_bundle.py` (new; Task 4 extends it)

**Interfaces:**
- Consumes: `APP_VERSION`, `libraryFolderName()`, `LIBRARY_FOLDER_EXT`, `nowIso()`, `currentLang`, `STRINGS`.
- Produces:
  - `function tIn(lang, key, params): string` (`t()` becomes `tIn(currentLang, key, params)`)
  - `function bundleNames(raw): {library, bundle, zip}`
  - `function dossiaryVersionIn(text): string|null`
  - `async function downloadOwnCopy(): string|null`
  - `async function loadStoredOwnCopy(): {id, version, text, savedAt}|null`
  - `async function storeOwnCopy(text, version): void`
  - `async function getDossiaryHtmlForBundle(chosenText): {text} | {missing: true} | {declined: true}`
  - `function bundleReadmeText(libraryFolder): string`
  - hooks `window.__DEBUG_getDossiaryHtmlForBundle(chosen)`, `__DEBUG_bundleReadmeText(lib)`, `__DEBUG_bundleNames(raw)`, `__DEBUG_loadStoredOwnCopy()`, `__DEBUG_storeOwnCopy(text, version)`
  - the 24 string keys listed in Step 3.

- [ ] **Step 1: Write the failing test** — create `tests/test_export_bundle.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, io, json, re, zipfile
from playwright.async_api import async_playwright

# Export as library bundled with Dossiary: the library plus a copy of
# dossiary.html and "How to open.txt", as a folder, a .zip file, or both.
VERSION = re.search(r"const APP_VERSION = '([^']+)'", open(APP_PATH, encoding='utf-8').read()).group(1)
OWN_COPY_URL = f"https://cdn.jsdelivr.net/gh/AarneAarebye/Dossiary@v{VERSION}/dossiary.html"
OWN_COPY = f"<!DOCTYPE html><html><body><script>const APP_VERSION = '{VERSION}';</script>downloaded copy</body></html>"
CHOSEN = f"<!DOCTYPE html><html><body><script>const APP_VERSION = '{VERSION}';</script>chosen copy</body></html>"

def doc(i, title, file_path, original=None):
    return {
        "id": i, "title": title, "category": "Home", "document_type": "Invoice",
        "date": "2026-03-01T00:00:00+00:00", "import_date": f"2026-03-0{i}T00:00:00+00:00",
        "notes": None, "ocr_text": f"text {i}", "ocr_language": None,
        "file_path": file_path, "original_file_path": original, "thumbnail_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0, "file_hash": f"hash{i}",
    }

SEED = {
    "documents": [doc(1, "Invoice", "files/1_a.pdf", "files/1_a/a.pdf"), doc(2, "Letter", "files/2_Հաշիվ_发票.pdf")],
    "fields": [
        {"id": 1, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 5, "name": "Reminder", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
    ],
    "settings": [{"key": "text_autocomplete_default_migrated", "value": "1"}],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)

        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)

        # jsDelivr, faked: registered after the catch-all, so it wins.
        fetches = []
        net = {'online': True, 'body': OWN_COPY}
        async def own_copy_route(route):
            fetches.append(route.request.url)
            if not net['online']:
                await route.abort()
                return
            await route.fulfill(status=200, body=net['body'], content_type='text/html',
                                headers={'access-control-allow-origin': '*'})
        await page.route('https://cdn.jsdelivr.net/gh/**', own_copy_route)

        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'MyLib';")
        await page.click("#open-btn")
        await page.wait_for_timeout(500)
        await page.evaluate("""() => {
            window.__CONFIRM_ANSWER = true; window.__CONFIRM_MSGS = [];
            window.confirm = (m) => { window.__CONFIRM_MSGS.push(m); return window.__CONFIRM_ANSWER; };
        }""")

        # === Scenario 1: names ===
        n = await page.evaluate("() => [window.__DEBUG_bundleNames('Tax 2025'), window.__DEBUG_bundleNames('Old.DOSSIARY')]")
        print("Bundle names from 'Tax 2025':", n[0] == {'library': 'Tax 2025.dossiary', 'bundle': 'Tax 2025', 'zip': 'Tax 2025.zip'}, n[0])
        print("...and from a name already ending in .dossiary:", n[1] == {'library': 'Old.DOSSIARY', 'bundle': 'Old', 'zip': 'Old.zip'}, n[1])

        # === Scenario 2: the download ===
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("Downloads its own version from jsDelivr:", fetches == [OWN_COPY_URL], fetches)
        print("...and uses it:", got == {'text': OWN_COPY})
        net['body'] = OWN_COPY.replace(VERSION, '0.0.1')
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("A download of another version is not used:", got == {'missing': True}, got)
        net['body'] = OWN_COPY
        net['online'] = False
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("Offline with nothing stored: missing:", got == {'missing': True}, got)

        # === Scenario 3: a chosen copy, and the stored copy ===
        got = await page.evaluate(f"() => window.__DEBUG_getDossiaryHtmlForBundle({json.dumps(CHOSEN)})")
        print("Offline, a copy chosen in this dialog is used:", got == {'text': CHOSEN})
        await page.evaluate(f"() => window.__DEBUG_storeOwnCopy({json.dumps(CHOSEN)}, {json.dumps(VERSION)})")
        stored = await page.evaluate("() => window.__DEBUG_loadStoredOwnCopy()")
        print("The stored copy keeps text and version:", stored['text'] == CHOSEN and stored['version'] == VERSION and stored['id'] == 'dossiary.html')
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("Offline, the stored copy is used without asking:", got == {'text': CHOSEN} and await page.evaluate("() => window.__CONFIRM_MSGS.length") == 0)
        await page.evaluate(f"() => window.__DEBUG_storeOwnCopy({json.dumps(CHOSEN)}, '0.0.1')")
        await page.evaluate("() => { window.__CONFIRM_ANSWER = false; }")
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        msgs = await page.evaluate("() => window.__CONFIRM_MSGS")
        print("An older stored copy asks first, naming both versions:", len(msgs) == 1 and '0.0.1' in msgs[0] and VERSION in msgs[0], msgs)
        print("...declining stops:", got == {'declined': True})
        await page.evaluate("() => { window.__CONFIRM_ANSWER = true; }")
        got = await page.evaluate("() => window.__DEBUG_getDossiaryHtmlForBundle(null)")
        print("...accepting uses it:", got == {'text': CHOSEN})
        await page.evaluate(f"() => window.__DEBUG_storeOwnCopy({json.dumps(CHOSEN)}, {json.dumps(VERSION)})")
        net['online'] = True

        # === Scenario 4: How to open.txt ===
        readme = await page.evaluate("() => window.__DEBUG_bundleReadmeText('Tax 2025.dossiary')")
        print("English instructions name the button, the folder and Recent libraries:",
              'Open library folder' in readme and 'Tax 2025.dossiary' in readme and 'Recent libraries' in readme and 'Chrome' in readme, repr(readme))
        print("...the version, and no second language:", VERSION in readme and '----' not in readme)
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        readme = await page.evaluate("() => window.__DEBUG_bundleReadmeText('Steuer.dossiary')")
        de_part, _, en_part = readme.partition('\n\n----\n\n')
        print("German first, then English:", 'Bibliotheksordner öffnen' in de_part and 'Zuletzt geöffnete Bibliotheken' in de_part
              and 'Open library folder' in en_part and 'Steuer.dossiary' in en_part, repr(readme))
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(200)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_export_bundle.py`
Expected: `TypeError: window.__DEBUG_bundleNames is not a function`.

- [ ] **Step 3: Add the strings** — insert these keys right after `exportLibraryOpen` in each `STRINGS` block (the `en`/`es`/`fr`/`de`/`zh-Hans`/`zh-Hant` blocks are long single-line runs of `key: 'value',`; `hy` is one `key: "value",` per line — match each block's style and quote character; escape quotes as needed).

`en`:
```
exportLibraryOutputLabel: 'What to create', exportLibraryOutputLibrary: 'Library only', exportLibraryOutputFolder: 'Library + Dossiary, as a folder', exportLibraryOutputZip: 'Library + Dossiary, as a .zip file', exportLibraryOutputBoth: 'Both: folder and .zip file', exportLibraryOutputHint: 'With Dossiary included, the recipient needs nothing installed — just Chrome or Edge on a computer. A “How to open” note is included.', exportBundleHintFolder: 'Creates the folder “{name}” in the folder you choose, with Dossiary and the library “{library}” inside.', exportBundleHintZip: 'Creates the file “{name}” in the folder you choose.', exportBundleHintBoth: 'Creates the folder “{name}” and the file “{zip}” in the folder you choose.', exportBundleZipExists: 'There’s already a file named “{name}” there. Choose another name.', exportBundleGetting: 'Getting a copy of Dossiary…', exportBundleNeedFile: 'Dossiary couldn’t download its own copy (offline, or this version isn’t released). Choose dossiary.html once — it will be remembered — then click Export library again.', exportBundleChooseBtn: 'Choose dossiary.html…', exportBundleChosen: 'Using the chosen dossiary.html (version {version}).', exportBundleNotDossiary: 'That file isn’t Dossiary.', exportBundleVersionMismatch: 'This dossiary.html is version {found}; you are running {running}. Use it anyway?', exportBundleZipProgress: 'Writing the .zip file: {done} of {total} files', exportBundleZipDone: 'Created “{zip}” ({size}).', exportBundleZipLarge: 'That’s too large for most email. Use AirDrop, a shared folder, or a USB stick.', howToOpenTitle: 'How to open these documents', howToOpenUnzip: '1. If you received a .zip file, unzip it first (Mac: double-click it; Windows: right-click it and choose “Extract All”).', howToOpenBrowser: '2. Open dossiary.html in Google Chrome or Microsoft Edge on a computer (right-click it and choose “Open With”). Safari, Firefox, iPhone and iPad can’t run it.', howToOpenLibrary: '3. Click “{button}” and choose the folder “{library}”. Next time it is listed under “{recent}”.', howToOpenFooter: 'Made with Dossiary {version} — https://github.com/AarneAarebye/Dossiary',
```

`es`:
```
exportLibraryOutputLabel: 'Qué crear', exportLibraryOutputLibrary: 'Solo la biblioteca', exportLibraryOutputFolder: 'Biblioteca + Dossiary, como carpeta', exportLibraryOutputZip: 'Biblioteca + Dossiary, como archivo .zip', exportLibraryOutputBoth: 'Ambos: carpeta y archivo .zip', exportLibraryOutputHint: 'Con Dossiary incluido, quien lo reciba no necesita instalar nada: basta Chrome o Edge en un ordenador. Se incluye una nota «How to open».', exportBundleHintFolder: 'Crea la carpeta «{name}» en la carpeta que elijas, con Dossiary y la biblioteca «{library}» dentro.', exportBundleHintZip: 'Crea el archivo «{name}» en la carpeta que elijas.', exportBundleHintBoth: 'Crea la carpeta «{name}» y el archivo «{zip}» en la carpeta que elijas.', exportBundleZipExists: 'Ya hay un archivo llamado «{name}» ahí. Elige otro nombre.', exportBundleGetting: 'Obteniendo una copia de Dossiary…', exportBundleNeedFile: 'Dossiary no pudo descargar su propia copia (sin conexión, o esta versión no está publicada). Elige dossiary.html una vez —se recordará— y vuelve a pulsar Exportar biblioteca.', exportBundleChooseBtn: 'Elegir dossiary.html…', exportBundleChosen: 'Se usa el dossiary.html elegido (versión {version}).', exportBundleNotDossiary: 'Ese archivo no es Dossiary.', exportBundleVersionMismatch: 'Este dossiary.html es la versión {found}; estás usando la {running}. ¿Usarlo de todos modos?', exportBundleZipProgress: 'Escribiendo el archivo .zip: {done} de {total} archivos', exportBundleZipDone: 'Creado «{zip}» ({size}).', exportBundleZipLarge: 'Es demasiado grande para la mayoría de los correos. Usa AirDrop, una carpeta compartida o una memoria USB.', howToOpenTitle: 'Cómo abrir estos documentos', howToOpenUnzip: '1. Si recibiste un archivo .zip, descomprímelo primero (Mac: haz doble clic; Windows: clic derecho y «Extraer todo»).', howToOpenBrowser: '2. Abre dossiary.html en Google Chrome o Microsoft Edge en un ordenador (clic derecho y «Abrir con»). Safari, Firefox, iPhone y iPad no pueden ejecutarlo.', howToOpenLibrary: '3. Haz clic en «{button}» y elige la carpeta «{library}». La próxima vez aparecerá en «{recent}».', howToOpenFooter: 'Hecho con Dossiary {version} — https://github.com/AarneAarebye/Dossiary',
```

`fr`:
```
exportLibraryOutputLabel: 'Que créer', exportLibraryOutputLibrary: 'Bibliothèque seule', exportLibraryOutputFolder: 'Bibliothèque + Dossiary, en dossier', exportLibraryOutputZip: 'Bibliothèque + Dossiary, en fichier .zip', exportLibraryOutputBoth: 'Les deux : dossier et fichier .zip', exportLibraryOutputHint: 'Avec Dossiary inclus, le destinataire n’a rien à installer : Chrome ou Edge sur un ordinateur suffit. Une note « How to open » est jointe.', exportBundleHintFolder: 'Crée le dossier « {name} » dans le dossier que vous choisissez, avec Dossiary et la bibliothèque « {library} » à l’intérieur.', exportBundleHintZip: 'Crée le fichier « {name} » dans le dossier que vous choisissez.', exportBundleHintBoth: 'Crée le dossier « {name} » et le fichier « {zip} » dans le dossier que vous choisissez.', exportBundleZipExists: 'Un fichier nommé « {name} » existe déjà à cet endroit. Choisissez un autre nom.', exportBundleGetting: 'Récupération d’une copie de Dossiary…', exportBundleNeedFile: 'Dossiary n’a pas pu télécharger sa propre copie (hors ligne, ou cette version n’est pas publiée). Choisissez dossiary.html une fois — il sera mémorisé — puis cliquez à nouveau sur Exporter la bibliothèque.', exportBundleChooseBtn: 'Choisir dossiary.html…', exportBundleChosen: 'Le dossiary.html choisi est utilisé (version {version}).', exportBundleNotDossiary: 'Ce fichier n’est pas Dossiary.', exportBundleVersionMismatch: 'Ce dossiary.html est la version {found} ; vous utilisez la {running}. L’utiliser quand même ?', exportBundleZipProgress: 'Écriture du fichier .zip : {done} sur {total} fichiers', exportBundleZipDone: '« {zip} » créé ({size}).', exportBundleZipLarge: 'C’est trop volumineux pour la plupart des e-mails. Utilisez AirDrop, un dossier partagé ou une clé USB.', howToOpenTitle: 'Comment ouvrir ces documents', howToOpenUnzip: '1. Si vous avez reçu un fichier .zip, décompressez-le d’abord (Mac : double-cliquez dessus ; Windows : clic droit, puis « Extraire tout »).', howToOpenBrowser: '2. Ouvrez dossiary.html dans Google Chrome ou Microsoft Edge sur un ordinateur (clic droit, puis « Ouvrir avec »). Safari, Firefox, iPhone et iPad ne peuvent pas l’exécuter.', howToOpenLibrary: '3. Cliquez sur « {button} » et choisissez le dossier « {library} ». La prochaine fois, il apparaîtra sous « {recent} ».', howToOpenFooter: 'Créé avec Dossiary {version} — https://github.com/AarneAarebye/Dossiary',
```

`de`:
```
exportLibraryOutputLabel: 'Was erstellen', exportLibraryOutputLibrary: 'Nur die Bibliothek', exportLibraryOutputFolder: 'Bibliothek + Dossiary als Ordner', exportLibraryOutputZip: 'Bibliothek + Dossiary als .zip-Datei', exportLibraryOutputBoth: 'Beides: Ordner und .zip-Datei', exportLibraryOutputHint: 'Mit Dossiary dabei muss der Empfänger nichts installieren – Chrome oder Edge auf einem Computer genügt. Eine Anleitung „How to open“ liegt bei.', exportBundleHintFolder: 'Legt in dem Ordner, den du wählst, den Ordner „{name}“ an, darin Dossiary und die Bibliothek „{library}“.', exportBundleHintZip: 'Legt die Datei „{name}“ in dem Ordner an, den du wählst.', exportBundleHintBoth: 'Legt den Ordner „{name}“ und die Datei „{zip}“ in dem Ordner an, den du wählst.', exportBundleZipExists: 'Dort gibt es schon eine Datei „{name}“. Wähle einen anderen Namen.', exportBundleGetting: 'Hole eine Kopie von Dossiary…', exportBundleNeedFile: 'Dossiary konnte keine Kopie von sich herunterladen (offline, oder diese Version ist nicht veröffentlicht). Wähle einmal dossiary.html – das wird gemerkt – und klicke dann erneut auf „Bibliothek exportieren“.', exportBundleChooseBtn: 'dossiary.html wählen…', exportBundleChosen: 'Die gewählte dossiary.html wird verwendet (Version {version}).', exportBundleNotDossiary: 'Diese Datei ist nicht Dossiary.', exportBundleVersionMismatch: 'Diese dossiary.html ist Version {found}, du verwendest {running}. Trotzdem verwenden?', exportBundleZipProgress: 'Schreibe die .zip-Datei: {done} von {total} Dateien', exportBundleZipDone: '„{zip}“ angelegt ({size}).', exportBundleZipLarge: 'Das ist für die meisten E-Mails zu groß. Nimm AirDrop, einen geteilten Ordner oder einen USB-Stick.', howToOpenTitle: 'So öffnest du diese Dokumente', howToOpenUnzip: '1. Wenn du eine .zip-Datei bekommen hast, entpacke sie zuerst (Mac: doppelklicken; Windows: rechts klicken und „Alle extrahieren“ wählen).', howToOpenBrowser: '2. Öffne dossiary.html in Google Chrome oder Microsoft Edge auf einem Computer (rechts klicken, „Öffnen mit“). Safari, Firefox, iPhone und iPad können es nicht ausführen.', howToOpenLibrary: '3. Klicke auf „{button}“ und wähle den Ordner „{library}“. Beim nächsten Mal steht er unter „{recent}“.', howToOpenFooter: 'Erstellt mit Dossiary {version} — https://github.com/AarneAarebye/Dossiary',
```

`zh-Hans`:
```
exportLibraryOutputLabel: '要创建的内容', exportLibraryOutputLibrary: '仅资料库', exportLibraryOutputFolder: '资料库 + Dossiary，作为文件夹', exportLibraryOutputZip: '资料库 + Dossiary，作为 .zip 文件', exportLibraryOutputBoth: '两者：文件夹和 .zip 文件', exportLibraryOutputHint: '附带 Dossiary 后，接收者无需安装任何东西——电脑上有 Chrome 或 Edge 即可。其中附有“How to open”说明。', exportBundleHintFolder: '将在你选择的文件夹中创建文件夹“{name}”，其中包含 Dossiary 和资料库“{library}”。', exportBundleHintZip: '将在你选择的文件夹中创建文件“{name}”。', exportBundleHintBoth: '将在你选择的文件夹中创建文件夹“{name}”和文件“{zip}”。', exportBundleZipExists: '那里已有名为“{name}”的文件。请换一个名称。', exportBundleGetting: '正在获取 Dossiary 的副本…', exportBundleNeedFile: 'Dossiary 无法下载自身的副本（离线，或此版本尚未发布）。请选择一次 dossiary.html（会被记住），然后再次点击“导出资料库”。', exportBundleChooseBtn: '选择 dossiary.html…', exportBundleChosen: '使用所选的 dossiary.html（版本 {version}）。', exportBundleNotDossiary: '该文件不是 Dossiary。', exportBundleVersionMismatch: '此 dossiary.html 的版本是 {found}，你正在使用 {running}。仍要使用吗？', exportBundleZipProgress: '正在写入 .zip 文件：{done} / {total} 个文件', exportBundleZipDone: '已创建“{zip}”（{size}）。', exportBundleZipLarge: '对大多数电子邮件来说太大了。请使用隔空投送、共享文件夹或 U 盘。', howToOpenTitle: '如何打开这些文档', howToOpenUnzip: '1. 如果收到的是 .zip 文件，请先解压（Mac：双击；Windows：右键点击并选择“全部解压缩”）。', howToOpenBrowser: '2. 在电脑上用 Google Chrome 或 Microsoft Edge 打开 dossiary.html（右键点击并选择“打开方式”）。Safari、Firefox、iPhone 和 iPad 无法运行它。', howToOpenLibrary: '3. 点击“{button}”，然后选择文件夹“{library}”。下次它会列在“{recent}”中。', howToOpenFooter: '由 Dossiary {version} 制作 — https://github.com/AarneAarebye/Dossiary',
```

`zh-Hant` (same wording as zh-Hans in Traditional script, 「」 quotes, matching the block's existing OpenCC style):
```
exportLibraryOutputLabel: '要創建的內容', exportLibraryOutputLibrary: '僅資料庫', exportLibraryOutputFolder: '資料庫 + Dossiary，作爲文件夾', exportLibraryOutputZip: '資料庫 + Dossiary，作爲 .zip 文件', exportLibraryOutputBoth: '兩者：文件夾和 .zip 文件', exportLibraryOutputHint: '附帶 Dossiary 後，接收者無需安裝任何東西——電腦上有 Chrome 或 Edge 即可。其中附有「How to open」說明。', exportBundleHintFolder: '將在你選擇的文件夾中創建文件夾「{name}」，其中包含 Dossiary 和資料庫「{library}」。', exportBundleHintZip: '將在你選擇的文件夾中創建文件「{name}」。', exportBundleHintBoth: '將在你選擇的文件夾中創建文件夾「{name}」和文件「{zip}」。', exportBundleZipExists: '那裏已有名爲「{name}」的文件。請換一個名稱。', exportBundleGetting: '正在獲取 Dossiary 的副本…', exportBundleNeedFile: 'Dossiary 無法下載自身的副本（離線，或此版本尚未發佈）。請選擇一次 dossiary.html（會被記住），然後再次點擊「導出資料庫」。', exportBundleChooseBtn: '選擇 dossiary.html…', exportBundleChosen: '使用所選的 dossiary.html（版本 {version}）。', exportBundleNotDossiary: '該文件不是 Dossiary。', exportBundleVersionMismatch: '此 dossiary.html 的版本是 {found}，你正在使用 {running}。仍要使用嗎？', exportBundleZipProgress: '正在寫入 .zip 文件：{done} / {total} 個文件', exportBundleZipDone: '已創建「{zip}」（{size}）。', exportBundleZipLarge: '對大多數電子郵件來說太大了。請使用隔空投送、共享文件夾或 U 盤。', howToOpenTitle: '如何打開這些文檔', howToOpenUnzip: '1. 如果收到的是 .zip 文件，請先解壓（Mac：雙擊；Windows：右鍵點擊並選擇「全部解壓縮」）。', howToOpenBrowser: '2. 在電腦上用 Google Chrome 或 Microsoft Edge 打開 dossiary.html（右鍵點擊並選擇「打開方式」）。Safari、Firefox、iPhone 和 iPad 無法運行它。', howToOpenLibrary: '3. 點擊「{button}」，然後選擇文件夾「{library}」。下次它會列在「{recent}」中。', howToOpenFooter: '由 Dossiary {version} 製作 — https://github.com/AarneAarebye/Dossiary',
```

`hy` (one per line, double quotes, 6-space indent like its neighbours):
```
      exportLibraryOutputLabel: "Ինչ ստեղծել",
      exportLibraryOutputLibrary: "Միայն գրադարանը",
      exportLibraryOutputFolder: "Գրադարան + Dossiary՝ որպես թղթապանակ",
      exportLibraryOutputZip: "Գրադարան + Dossiary՝ որպես .zip ֆայլ",
      exportLibraryOutputBoth: "Երկուսն էլ՝ թղթապանակ և .zip ֆայլ",
      exportLibraryOutputHint: "Երբ Dossiary-ն ներառված է, ստացողը ոչինչ տեղադրելու կարիք չունի․ բավական է Chrome կամ Edge համակարգչում։ Կցված է «How to open» հրահանգը։",
      exportBundleHintFolder: "Ձեր ընտրած թղթապանակում ստեղծում է «{name}» թղթապանակը, որի մեջ Dossiary-ն է և «{library}» գրադարանը։",
      exportBundleHintZip: "Ձեր ընտրած թղթապանակում ստեղծում է «{name}» ֆայլը։",
      exportBundleHintBoth: "Ձեր ընտրած թղթապանակում ստեղծում է «{name}» թղթապանակը և «{zip}» ֆայլը։",
      exportBundleZipExists: "Այնտեղ արդեն կա «{name}» անունով ֆայլ։ Ընտրեք այլ անուն։",
      exportBundleGetting: "Dossiary-ի պատճենը բեռնվում է…",
      exportBundleNeedFile: "Dossiary-ն չկարողացավ ներբեռնել իր պատճենը (ցանց չկա, կամ այս տարբերակը թողարկված չէ)։ Մեկ անգամ ընտրեք dossiary.html-ը (այն կհիշվի), ապա կրկին սեղմեք «Արտահանել գրադարանը»։",
      exportBundleChooseBtn: "Ընտրել dossiary.html…",
      exportBundleChosen: "Օգտագործվում է ընտրված dossiary.html-ը (տարբերակ {version})։",
      exportBundleNotDossiary: "Այդ ֆայլը Dossiary չէ։",
      exportBundleVersionMismatch: "Այս dossiary.html-ը {found} տարբերակն է, իսկ դուք օգտագործում եք {running}-ը։ Օգտագործե՞լ այնուամենայնիվ։",
      exportBundleZipProgress: "Գրվում է .zip ֆայլը՝ {done}-ը {total} ֆայլից",
      exportBundleZipDone: "Ստեղծվեց «{zip}» ({size})։",
      exportBundleZipLarge: "Սա չափազանց մեծ է էլ. փոստերի մեծ մասի համար։ Օգտագործեք AirDrop, ընդհանուր թղթապանակ կամ USB կրիչ։",
      howToOpenTitle: "Ինչպես բացել այս փաստաթղթերը",
      howToOpenUnzip: "1. Եթե ստացել եք .zip ֆայլ, նախ բացեք արխիվը (Mac՝ կրկնակի սեղմեք, Windows՝ աջ սեղմեք և ընտրեք «Extract All»)։",
      howToOpenBrowser: "2. Բացեք dossiary.html-ը Google Chrome-ով կամ Microsoft Edge-ով համակարգչում (աջ սեղմեք և ընտրեք «Open With»)։ Safari-ն, Firefox-ը, iPhone-ը և iPad-ը չեն կարող այն գործարկել։",
      howToOpenLibrary: "3. Սեղմեք «{button}» և ընտրեք «{library}» թղթապանակը։ Հաջորդ անգամ այն կլինի «{recent}» ցանկում։",
      howToOpenFooter: "Պատրաստված է Dossiary {version}-ով — https://github.com/AarneAarebye/Dossiary",
```

- [ ] **Step 4: `tIn()`** — replace the body of `t()` (line ~3307) so both share one lookup:

```js
  function tIn(lang, key, params){
    let str = (STRINGS[lang] || STRINGS.en)[key] ?? STRINGS.en[key] ?? key;
    if(params){
      for(const [k, v] of Object.entries(params)) str = str.replaceAll(`{${k}}`, v);
    }
    return str;
  }
  function t(key, params){ return tIn(currentLang, key, params); }
```

- [ ] **Step 5: The helpers** — insert directly after the zip writer block (Task 2):

```js
  // --- Dossiary's own copy, for bundles ---
  // A file:// page can't read its own file, so a bundle's dossiary.html is
  // downloaded at the running version's tag; when that fails (offline, an
  // untagged build), a copy the person chose once is used. The copy's
  // contents are kept, not a file handle: re-reading a handle needs a
  // permission prompt, which would use up the click the folder picker needs.
  const OWN_COPY_DB = 'dossiary-bundle-source';
  const OWN_COPY_STORE = 'copies';
  function bundleNames(raw){
    const library = libraryFolderName(raw);
    const bundle = library.slice(0, -LIBRARY_FOLDER_EXT.length);
    return { library, bundle, zip: `${bundle}.zip` };
  }
  function dossiaryVersionIn(text){
    const m = /const APP_VERSION = '([^']+)'/.exec(text || '');
    return m ? m[1] : null;
  }
  async function downloadOwnCopy(){
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 15000);
    try{
      const res = await fetch(`https://cdn.jsdelivr.net/gh/AarneAarebye/Dossiary@v${APP_VERSION}/dossiary.html`, { signal: ctrl.signal });
      if(!res.ok) return null;
      const text = await res.text();
      return dossiaryVersionIn(text) === APP_VERSION ? text : null;
    }catch(e){ return null; }
    finally{ clearTimeout(timer); }
  }
  function openOwnCopyDb(){
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(OWN_COPY_DB, 1);
      req.onupgradeneeded = () => { req.result.createObjectStore(OWN_COPY_STORE, { keyPath: 'id' }); };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  async function loadStoredOwnCopy(){
    try{
      const idb = await openOwnCopyDb();
      return await new Promise((resolve, reject) => {
        const req = idb.transaction(OWN_COPY_STORE, 'readonly').objectStore(OWN_COPY_STORE).get('dossiary.html');
        req.onsuccess = () => resolve(req.result || null);
        req.onerror = () => reject(req.error);
      });
    }catch(e){ return null; }
  }
  async function storeOwnCopy(text, version){
    const idb = await openOwnCopyDb();
    await new Promise((resolve, reject) => {
      const req = idb.transaction(OWN_COPY_STORE, 'readwrite').objectStore(OWN_COPY_STORE)
        .put({ id: 'dossiary.html', version, text, savedAt: nowIso() });
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  }
  // chosenText: a copy picked in the open dialog (its version already confirmed).
  async function getDossiaryHtmlForBundle(chosenText){
    const downloaded = await downloadOwnCopy();
    if(downloaded) return { text: downloaded };
    if(chosenText) return { text: chosenText };
    const stored = await loadStoredOwnCopy();
    if(!stored) return { missing: true };
    if(stored.version !== APP_VERSION
       && !confirm(t('exportBundleVersionMismatch', {found: stored.version, running: APP_VERSION}))) return { declined: true };
    return { text: stored.text };
  }
  // "How to open.txt": the UI language, then English when that differs.
  function bundleReadmeText(libraryFolder){
    const block = (lang) => [
      tIn(lang, 'howToOpenTitle'),
      '',
      tIn(lang, 'howToOpenUnzip'),
      tIn(lang, 'howToOpenBrowser'),
      tIn(lang, 'howToOpenLibrary', {button: tIn(lang, 'emptyOpenButton'), library: libraryFolder, recent: tIn(lang, 'recentLibrariesHeading')}),
      '',
      tIn(lang, 'howToOpenFooter', {version: APP_VERSION}),
    ].join('\n');
    const langs = currentLang === 'en' ? ['en'] : [currentLang, 'en'];
    return langs.map(block).join('\n\n----\n\n') + '\n';
  }

```

- [ ] **Step 6: Debug hooks** — add after Task 2's hooks:

```js
  window.__DEBUG_bundleNames = (raw) => bundleNames(raw);
  window.__DEBUG_getDossiaryHtmlForBundle = (chosen) => getDossiaryHtmlForBundle(chosen);
  window.__DEBUG_bundleReadmeText = (lib) => bundleReadmeText(lib);
  window.__DEBUG_loadStoredOwnCopy = () => loadStoredOwnCopy();
  window.__DEBUG_storeOwnCopy = (text, version) => storeOwnCopy(text, version);
```

- [ ] **Step 7: Run the tests**

Run: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_export_bundle.py && python3 test_i18n_coverage.py && python3 test_i18n.py | grep -E ": False|Error" ; echo done`
Expected: `test_export_bundle.py` all `True` with `JS ERRORS: []`; `test_i18n_coverage.py` reports no missing keys or placeholder mismatches; no `False` from `test_i18n.py`.

- [ ] **Step 8: Commit**

```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
git add dossiary.html tests/test_export_bundle.py
git commit -m "Bundles: Dossiary's own copy (download or chosen), How to open text, strings"
```

---

### Task 4: The dialog — "What to create", Choose dossiary.html, folder/zip/both outputs

**Files:**
- Modify: `dossiary.html` — `openExportLibraryModal()` (starts ~line 7946): markup, wiring, and the Start handler; new small helpers `writeFileAt`, `bytesOf`, `listFilesUnder` placed directly before `function openExportLibraryModal`.
- Test: extend `tests/test_export_bundle.py` (insert before its final `print("JS ERRORS:", errors)`); `tests/test_export_library.py` must keep passing unchanged.

**Interfaces:**
- Consumes (Task 2/3): `createZipWriter`, `zipLimits`, `bundleNames`, `dossiaryVersionIn`, `storeOwnCopy`, `getDossiaryHtmlForBundle`, `bundleReadmeText`; existing `libraryFolderName`, `isInsideLibrary`, `buildExportLibraryDb`, `sidecarTextForDoc`, `sidecarBaseNameFromFilePath`, `withFileOp`, `resolveFileHandle`, `fileErrorText`, `recordRecentLibrary`, `bulkSetDeleted`, `formatBytes`, `escapeHtml`, `displayName`.
- Produces: DOM ids `input[name="export-library-output"]` (values `library|folder|zip|both`), `#export-library-output-hint`, `#export-bundle-choose`, `#export-bundle-choose-btn`, `#export-bundle-choose-note`.

- [ ] **Step 1: Write the failing tests** — insert into `tests/test_export_bundle.py` before `print("JS ERRORS:", errors)`:

```python
        # Files for the dialog scenarios
        await page.evaluate("""
            async () => {
                const put = async (path, text) => {
                    const parts = path.split('/');
                    let dir = window.__TEST_ROOT;
                    for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                    const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
                    await w.write(new TextEncoder().encode(text)); await w.close();
                };
                await put('files/1_a.pdf', 'active 1');
                await put('files/1_a/a.pdf', 'original 1');
                await put('files/2_Հաշիվ_发票.pdf', 'active 2');
                window.__EXPORT_PARENT = window.__makeEmptyRoot();
                window.__EXPORT_PARENT.name = 'Outside';
            }
        """)
        LIST_IN = """async (name) => {
            const out = [];
            const walk = async (dir, prefix) => {
                for await (const [n, h] of dir.entries()){
                    if(h.kind === 'directory') await walk(h, prefix + n + '/');
                    else out.push(prefix + n);
                }
            };
            await walk(await window.__EXPORT_PARENT.getDirectoryHandle(name), '');
            return out.sort();
        }"""
        READ_IN = """async ([name, path]) => {
            let dir = await window.__EXPORT_PARENT.getDirectoryHandle(name);
            const parts = path.split('/');
            for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part);
            return await (await (await dir.getFileHandle(parts[parts.length - 1])).getFile()).text();
        }"""
        ZIP_BYTES = "async (name) => Array.from(new Uint8Array(await (await (await window.__EXPORT_PARENT.getFileHandle(name)).getFile()).arrayBuffer()))"
        PARENT_NAMES = "async () => { const n = []; for await (const [k] of window.__EXPORT_PARENT.entries()) n.push(k); return n.sort(); }"
        SOURCE_DB = "async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())"
        RECENT = "() => [...window.__FAKE_IDB_DATABASES.get('dossiary-app-db')._stores.get('recentLibraries').map.values()].map(e => e.name)"

        async def open_dialog(ids, name, output):
            await page.click('#nav-item-all')
            await page.wait_for_timeout(150)
            for i in ids:
                await page.check(f'tr[data-id="{i}"] .row-select-checkbox')
            await page.click('#bulk-more-btn')
            await page.click('#bulk-export-library-btn')
            await page.wait_for_timeout(300)
            await page.fill('#export-library-name', name)
            await page.check(f'input[name="export-library-output"][value="{output}"]')

        async def start():
            await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT; }")
            await page.click('#export-library-start-btn')
            await page.wait_for_timeout(1200)

        async def close_dialog():
            await page.click('#export-library-cancel-btn')
            await page.wait_for_timeout(150)

        # === Scenario 5: Library only stays as it was, and offline ===
        fetches.clear()
        await open_dialog([1], 'Plain', 'library')
        print("Library only is the default output:", await page.evaluate("() => document.querySelector('input[name=\"export-library-output\"][value=\"library\"]').defaultChecked"))
        print("No bundle hint for Library only:", not await page.is_visible('#export-library-output-hint'))
        print("Hint names the library folder:", 'Plain.dossiary' in await page.inner_text('#export-library-hint'))
        await start()
        print("Library only never downloads:", fetches == [])
        print("...and makes just the library:", 'Plain.dossiary' in await page.evaluate(PARENT_NAMES))
        await close_dialog()

        # === Scenario 6: Library + Dossiary as a folder ===
        fetches.clear()
        await open_dialog([1, 2], 'Tax 2025', 'folder')
        print("Folder hint names bundle and library:", 'Tax 2025' in await page.inner_text('#export-library-hint')
              and 'Tax 2025.dossiary' in await page.inner_text('#export-library-hint'))
        print("The bundle explanation shows:", await page.is_visible('#export-library-output-hint'))
        await start()
        print("Downloaded its own copy:", fetches == [OWN_COPY_URL], fetches)
        files = await page.evaluate(LIST_IN, 'Tax 2025')
        print("Bundle folder layout:", files == ['How to open.txt', 'Tax 2025.dossiary/files/1_a.pdf', 'Tax 2025.dossiary/files/1_a.txt',
              'Tax 2025.dossiary/files/1_a/a.pdf', 'Tax 2025.dossiary/files/2_Հաշիվ_发票.pdf', 'Tax 2025.dossiary/files/2_Հաշիվ_发票.txt',
              'Tax 2025.dossiary/library.sqlite', 'dossiary.html'], files)
        print("dossiary.html is the downloaded copy:", await page.evaluate(READ_IN, ['Tax 2025', 'dossiary.html']) == OWN_COPY)
        readme = await page.evaluate(READ_IN, ['Tax 2025', 'How to open.txt'])
        print("How to open names the library folder:", 'Tax 2025.dossiary' in readme and 'Open library folder' in readme)
        status = await page.inner_text('#export-library-status')
        print("Summary names the bundle folder:", 'Outside/Tax 2025' in status and 'Documents exported: 2' in status, repr(status))
        print("Open it is offered:", await page.is_visible('#export-library-open-btn'))
        print("Recent libraries gets the inner library:", 'Tax 2025.dossiary' in await page.evaluate(RECENT))
        await close_dialog()

        # === Scenario 7: an existing bundle folder is refused ===
        await open_dialog([1], 'Tax 2025', 'folder')
        await start()
        print("Existing bundle folder refused:", 'already a folder' in await page.inner_text('#export-library-status'))
        await close_dialog()

        # === Scenario 8: offline, nothing stored -> Choose dossiary.html ===
        await page.evaluate("() => window.__FAKE_IDB_DATABASES.delete('dossiary-bundle-source')")
        net['online'] = False
        await open_dialog([1], 'Offline', 'folder')
        print("Choose button hidden at first:", not await page.is_visible('#export-bundle-choose'))
        await start()
        print("Asks for dossiary.html:", 'couldn’t download' in await page.inner_text('#export-library-status')
              and await page.is_visible('#export-bundle-choose'))
        print("...and wrote nothing:", 'Offline' not in await page.evaluate(PARENT_NAMES))
        await page.evaluate("""() => {
            window.__PICKED_HTML = '<html>not it</html>';
            window.showOpenFilePicker = async () => [{ kind: 'file', name: 'dossiary.html',
                getFile: async () => new File([window.__PICKED_HTML], 'dossiary.html', { type: 'text/html' }) }];
        }""")
        await page.click('#export-bundle-choose-btn')
        await page.wait_for_timeout(200)
        print("A file that isn't Dossiary is refused:", 'isn’t Dossiary' in await page.inner_text('#export-bundle-choose-note'))
        await page.evaluate(f"() => {{ window.__PICKED_HTML = {json.dumps(CHOSEN)}; }}")
        await page.click('#export-bundle-choose-btn')
        await page.wait_for_timeout(200)
        print("The chosen copy is confirmed with its version:", VERSION in await page.inner_text('#export-bundle-choose-note'))
        print("...and stored:", (await page.evaluate("() => window.__DEBUG_loadStoredOwnCopy()") or {}).get('text') == CHOSEN)
        await start()
        print("Second click exports with the chosen copy:", await page.evaluate(READ_IN, ['Offline', 'dossiary.html']) == CHOSEN)
        await close_dialog()

        # === Scenario 9: the stored copy is used later without asking ===
        await open_dialog([1], 'Again', 'folder')
        await start()
        print("Stored copy used, no Choose step:", await page.evaluate(READ_IN, ['Again', 'dossiary.html']) == CHOSEN
              and not await page.is_visible('#export-bundle-choose'))
        await close_dialog()

        # === Scenario 10: an outdated stored copy, declined ===
        await page.evaluate("() => { window.__FAKE_IDB_DATABASES.get('dossiary-bundle-source')._stores.get('copies').map.get('dossiary.html').version = '0.0.1'; window.__CONFIRM_ANSWER = false; window.__CONFIRM_MSGS = []; }")
        await open_dialog([1], 'Declined', 'folder')
        await start()
        print("Outdated copy asks first:", len(await page.evaluate("() => window.__CONFIRM_MSGS")) == 1)
        print("Declining writes nothing and offers Choose:", 'Declined' not in await page.evaluate(PARENT_NAMES)
              and await page.is_visible('#export-bundle-choose'))
        await close_dialog()
        await page.evaluate(f"() => {{ window.__CONFIRM_ANSWER = true; return window.__DEBUG_storeOwnCopy({json.dumps(CHOSEN)}, {json.dumps(VERSION)}); }}")
        net['online'] = True

        # === Scenario 11: zip only ===
        await open_dialog([1, 2], 'Zipped', 'zip')
        print("Zip hint names the zip:", 'Zipped.zip' in await page.inner_text('#export-library-hint'))
        await start()
        names = await page.evaluate(PARENT_NAMES)
        print("Only the zip is made:", 'Zipped.zip' in names and 'Zipped' not in names, names)
        z = zipfile.ZipFile(io.BytesIO(bytes(await page.evaluate(ZIP_BYTES, 'Zipped.zip'))))
        print("Zip entries:", sorted(z.namelist()) == ['Zipped/How to open.txt', 'Zipped/Zipped.dossiary/files/1_a.pdf',
              'Zipped/Zipped.dossiary/files/1_a.txt', 'Zipped/Zipped.dossiary/files/1_a/a.pdf',
              'Zipped/Zipped.dossiary/files/2_Հաշիվ_发票.pdf', 'Zipped/Zipped.dossiary/files/2_Հաշիվ_发票.txt',
              'Zipped/Zipped.dossiary/library.sqlite', 'Zipped/dossiary.html'], sorted(z.namelist()))
        print("Zip contents and CRCs:", z.read('Zipped/Zipped.dossiary/files/1_a.pdf') == b'active 1'
              and z.read('Zipped/dossiary.html').decode() == OWN_COPY and z.testzip() is None)
        db_in_zip = json.loads(z.read('Zipped/Zipped.dossiary/library.sqlite'))
        print("The zipped library holds both documents:", sorted(d['id'] for d in db_in_zip['documents']) == [1, 2])
        status = await page.inner_text('#export-library-status')
        print("Summary names the zip and its size:", re.search(r'Outside/Zipped\.zip.*\(\d', status) is not None, repr(status))
        print("No email note for a small zip:", 'too large' not in status)
        print("No Open it for a zip:", not await page.is_visible('#export-library-open-btn'))
        print("Nothing added to Recent libraries:", not any('Zipped' in n for n in await page.evaluate(RECENT)))
        await close_dialog()

        # === Scenario 12: an existing zip is refused ===
        await open_dialog([1], 'Zipped', 'zip')
        await start()
        print("Existing zip refused:", 'already a file' in await page.inner_text('#export-library-status'))
        await close_dialog()

        # === Scenario 13: both ===
        await open_dialog([1, 2], 'Pair', 'both')
        print("Both hint names folder and zip:", 'Pair.zip' in await page.inner_text('#export-library-hint'))
        await start()
        folder_files = await page.evaluate(LIST_IN, 'Pair')
        z = zipfile.ZipFile(io.BytesIO(bytes(await page.evaluate(ZIP_BYTES, 'Pair.zip'))))
        print("Folder and zip hold the same files:", sorted(n[len('Pair/'):] for n in z.namelist()) == folder_files, folder_files)
        same = True
        for f in folder_files:
            same = same and z.read('Pair/' + f).decode() == await page.evaluate(READ_IN, ['Pair', f])
        print("...with the same contents:", same and z.testzip() is None)
        status = await page.inner_text('#export-library-status')
        print("Summary names both:", 'Outside/Pair' in status and 'Outside/Pair.zip' in status)
        print("Open it is offered:", await page.is_visible('#export-library-open-btn'))
        await close_dialog()

        # === Scenario 14: the email-size note, and ZIP64 + UTF-8 end to end ===
        await page.evaluate("() => window.__DEBUG_setZipLimits({ emailBytes: 10, zip64Bytes: 4, zip64Entries: 2 })")
        await open_dialog([1, 2], 'Հարկ 2025', 'zip')
        await start()
        print("Large zip gets the email note:", 'too large' in await page.inner_text('#export-library-status'))
        raw = bytes(await page.evaluate(ZIP_BYTES, 'Հարկ 2025.zip'))
        z = zipfile.ZipFile(io.BytesIO(raw))
        print("ZIP64 zip with Armenian and Chinese names reads back:", b'PK\x06\x06' in raw and z.testzip() is None
              and 'Հարկ 2025/Հարկ 2025.dossiary/files/2_Հաշիվ_发票.pdf' in z.namelist())
        await page.evaluate("() => window.__DEBUG_setZipLimits({ emailBytes: 25 * 1024 * 1024, zip64Bytes: 0xFFFFFFFF, zip64Entries: 0xFFFF })")
        await close_dialog()

        # === Scenario 15: Stop removes a partial zip ===
        await open_dialog([1, 2], 'Stopped', 'zip')
        await page.evaluate("""async () => {
            const h = await (await window.__TEST_ROOT.getDirectoryHandle('files')).getFileHandle('1_a.pdf');
            const orig = h.getFile.bind(h);
            h.getFile = async () => { await new Promise(r => setTimeout(r, 1200)); h.getFile = orig; return orig(); };
            window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT;
        }""")
        await page.click('#export-library-start-btn')
        await page.wait_for_timeout(300)
        await page.click('#export-library-stop-btn')
        await page.wait_for_timeout(1800)
        print("Stopping removes the partial zip:", 'Stopped.zip' not in await page.evaluate(PARENT_NAMES)
              and 'removed' in await page.inner_text('#export-library-status'))
        await close_dialog()

        # === Scenario 16: Move with a zip ===
        await open_dialog([1], 'MoveZip', 'zip')
        await page.check('input[name="export-library-mode"][value="move"]')
        await start()
        src = await page.evaluate(SOURCE_DB)
        flags = {d['id']: d['deleted'] for d in src['documents']}
        print("Moved after the zip was written:", 'MoveZip.zip' in await page.evaluate(PARENT_NAMES) and flags[1] == 1 and not flags[2], flags)
        await close_dialog()

        # === Scenario 17: German labels ===
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        await page.click('#nav-item-all')
        await page.check('tr[data-id="2"] .row-select-checkbox')
        await page.click('#bulk-more-btn')
        await page.click('#bulk-export-library-btn')
        await page.wait_for_timeout(300)
        body = await page.inner_text('.modal')
        print("German output choices:", 'Bibliothek + Dossiary als Ordner' in body and 'Beides: Ordner und .zip-Datei' in body)
        await close_dialog()
        await page.select_option('#lang-select', 'en')
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_export_bundle.py`
Expected: Scenarios 1–4 still `True`; Scenario 5 times out on `input[name="export-library-output"]`.

- [ ] **Step 3: Helpers** — insert directly before `function openExportLibraryModal(ids){`:

```js
  async function writeFileAt(dir, path, data){
    const parts = path.split('/');
    for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
    const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
    await w.write(data);
    await w.close();
  }
  function bytesOf(data){
    if(typeof data === 'string') return new TextEncoder().encode(data);
    return data instanceof Uint8Array ? data : new Uint8Array(data);
  }
  // [relative path, file handle] for every file under dir, subfolders included.
  async function listFilesUnder(dir, prefix = ''){
    const out = [];
    for await (const [name, handle] of dir.entries()){
      if(name === '.DS_Store' || name.startsWith('._')) continue;
      if(handle.kind === 'directory') out.push(...await listFilesUnder(handle, `${prefix}${name}/`));
      else out.push([`${prefix}${name}`, handle]);
    }
    return out;
  }

```

- [ ] **Step 4: Markup** — in `openExportLibraryModal()`'s template, directly after the closing `</div>` of the `export-library-setup` field (the one containing `#export-library-setup-hint`), insert:

```html
          <div class="field">
            <label>${t('exportLibraryOutputLabel')}</label>
            <label class="show-archived-toggle"><input type="radio" name="export-library-output" value="library" checked /> ${t('exportLibraryOutputLibrary')}</label>
            <label class="show-archived-toggle"><input type="radio" name="export-library-output" value="folder" /> ${t('exportLibraryOutputFolder')}</label>
            <label class="show-archived-toggle"><input type="radio" name="export-library-output" value="zip" /> ${t('exportLibraryOutputZip')}</label>
            <label class="show-archived-toggle"><input type="radio" name="export-library-output" value="both" /> ${t('exportLibraryOutputBoth')}</label>
            <div class="field-hint" id="export-library-output-hint" style="display:none;">${t('exportLibraryOutputHint')}</div>
          </div>
          <div class="field" id="export-bundle-choose" style="display:none;">
            <button id="export-bundle-choose-btn">${t('exportBundleChooseBtn')}</button>
            <div class="field-hint" id="export-bundle-choose-note"></div>
          </div>
```

- [ ] **Step 5: Wiring** — replace the existing `updateHint` definition (the `const updateHint = () => { … };` that sets `exportLibraryHint`) with:

```js
    const selectedOutput = () => document.querySelector('input[name="export-library-output"]:checked').value;
    const updateHint = () => {
      const raw = nameInput.value.trim();
      const hint = el('export-library-hint');
      if(!raw){ hint.textContent = ''; return; }
      const names = bundleNames(raw);
      const output = selectedOutput();
      hint.textContent = output === 'library' ? t('exportLibraryHint', {name: names.library})
        : output === 'folder' ? t('exportBundleHintFolder', {name: names.bundle, library: names.library})
        : output === 'zip' ? t('exportBundleHintZip', {name: names.zip})
        : t('exportBundleHintBoth', {name: names.bundle, zip: names.zip});
    };
    document.querySelectorAll('input[name="export-library-output"]').forEach(r => r.addEventListener('change', () => {
      el('export-library-output-hint').style.display = selectedOutput() === 'library' ? 'none' : '';
      updateHint();
    }));
    let chosenOwnCopy = null; // a dossiary.html picked in this dialog
    el('export-bundle-choose-btn').addEventListener('click', async () => {
      const note = el('export-bundle-choose-note');
      let handles;
      try{ handles = await window.showOpenFilePicker({ types: [{ description: 'Dossiary', accept: { 'text/html': ['.html'] } }] }); }
      catch(e){ return; } // picker cancelled
      const text = await (await handles[0].getFile()).text();
      const version = dossiaryVersionIn(text);
      if(!version){ note.textContent = t('exportBundleNotDossiary'); return; }
      if(version !== APP_VERSION && !confirm(t('exportBundleVersionMismatch', {found: version, running: APP_VERSION}))) return;
      chosenOwnCopy = text;
      try{ await storeOwnCopy(text, version); }catch(e){ /* still used for this dialog */ }
      note.textContent = t('exportBundleChosen', {version});
    });
```

(Keep the existing `nameInput.addEventListener('input', updateHint); updateHint();` lines after it.)

- [ ] **Step 6: The Start handler** — in the `export-library-start-btn` click handler, replace everything from `const folderName = libraryFolderName(raw);` up to and including the line `const setupMode = …;` with:

```js
      const names = bundleNames(raw);
      const folderName = names.library;
      const output = selectedOutput();
      const bundle = output !== 'library';
      const wantsFolder = output !== 'zip';
      const wantsZip = output === 'zip' || output === 'both';
      const topFolder = bundle ? names.bundle : folderName;
      let parent;
      try{ parent = await window.showDirectoryPicker({ mode: 'readwrite' }); }
      catch(e){ return; } // picker cancelled
      if(await isInsideLibrary(parent)) return fail(t('backupInsideLibrary'));
      const taken = async (name, kind) => {
        try{ await (kind === 'dir' ? parent.getDirectoryHandle(name) : parent.getFileHandle(name)); return true; }
        catch(e){ return false; }
      };
      if(wantsFolder && await taken(topFolder, 'dir')) return fail(t('newLibraryExists', {name: topFolder}));
      if(wantsZip && await taken(names.zip, 'file')) return fail(t('exportBundleZipExists', {name: names.zip}));
      let appHtml = null;
      if(bundle){
        statusEl.className = 'status busy';
        statusEl.innerHTML = '<span class="spinner"></span> ' + escapeHtml(t('exportBundleGetting'));
        const got = await getDossiaryHtmlForBundle(chosenOwnCopy);
        if(!got.text){
          el('export-bundle-choose').style.display = '';
          if(got.declined){ statusEl.className = 'status'; statusEl.textContent = ''; }
          else fail(t('exportBundleNeedFile'));
          return;
        }
        appHtml = got.text;
        statusEl.className = 'status';
        statusEl.textContent = '';
      }
      const move = document.querySelector('input[name="export-library-mode"]:checked').value === 'move';
      const setupMode = document.querySelector('input[name="export-library-setup"]:checked').value;
```

Then, in the same handler:

a) Next to `startBtn.disabled = cancelBtn.disabled = nameInput.disabled = true;` add `el('export-bundle-choose-btn').disabled = true;`.

b) Replace the whole `try{ … }catch(e){ … }` block that starts with `dest = await parent.getDirectoryHandle(folderName, { create: true });`, **and** the following `if(outcome !== 'done' && dest){ … }` cleanup block, with:

```js
      let bundleDir = null, zipHandle = null, zipStream = null, zip = null, madeTopFolder = false;
      try{
        let sink;
        if(wantsFolder){
          const top = await parent.getDirectoryHandle(topFolder, { create: true });
          madeTopFolder = true;
          if(bundle){ bundleDir = top; dest = await top.getDirectoryHandle(folderName, { create: true }); }
          else dest = top;
          await dest.getDirectoryHandle('files', { create: true });
          await dest.getDirectoryHandle('inbox', { create: true });
          sink = (path, data) => writeFileAt(dest, path, data);
        }
        if(wantsZip){
          zipHandle = await parent.getFileHandle(names.zip, { create: true });
          zipStream = await zipHandle.createWritable();
          zip = createZipWriter(zipStream);
        }
        if(!sink){
          // Zip only: the library goes straight into the zip, one entry at a time.
          let queue = Promise.resolve();
          const prefix = `${names.bundle}/${folderName}/`;
          sink = (path, data) => (queue = queue.then(() => zip.add(prefix + path, bytesOf(data))));
        }
        const readPath = (path) => withFileOp('read', path, async () => (await (await resolveFileHandle(path, false)).getFile()).arrayBuffer());
        let next = 0, done = 0;
        const worker = async () => {
          while(!stopRequested && next < docs.length){
            const d = docs[next++];
            try{
              // Both read before anything is written, so a document left out
              // leaves no files behind in the new library.
              const main = d.file_path ? await readPath(d.file_path) : null;
              const original = d.original_file_path ? await readPath(d.original_file_path) : null;
              if(main) await sink(d.file_path, main);
              if(original) await sink(d.original_file_path, original);
              if(d.thumbnail_path){
                let thumb = null;
                try{ thumb = await readPath(d.thumbnail_path); }catch(e){ /* best-effort */ }
                if(thumb) await sink(d.thumbnail_path, thumb);
              }
              const stem = sidecarBaseNameFromFilePath(d.file_path);
              if(stem) await sink(`files/${stem}.txt`, sidecarTextForDoc(d));
              exported.add(d.id);
            }catch(e){
              if(!e.fileOp){ stopRequested = true; throw e; } // the new library can't be written: give up
              leftOut.push({ d, reason: fileErrorText(e, 'exportLibraryError') });
            }
            done++;
            statusEl.innerHTML = '<span class="spinner"></span> ' + escapeHtml(t('exportLibraryProgress', {done, total: docs.length}));
          }
        };
        await Promise.all(Array.from({length: Math.min(4, docs.length)}, worker));
        if(stopRequested) outcome = 'stopped';
        else if(!exported.size) outcome = 'nothing';
        else{
          await sink('library.sqlite', buildExportLibraryDb(db, docs.map(d => d.id).filter(id => exported.has(id)), setupMode).export());
          if(bundle){
            const readme = bundleReadmeText(folderName);
            if(bundleDir){
              await writeFileAt(bundleDir, 'dossiary.html', appHtml);
              await writeFileAt(bundleDir, 'How to open.txt', readme);
            }else{
              await zip.add(`${names.bundle}/dossiary.html`, bytesOf(appHtml));
              await zip.add(`${names.bundle}/How to open.txt`, bytesOf(readme));
            }
          }
          if(zip && bundleDir){
            // Both: zip the folder just written, so the two hold the same files.
            const files = await listFilesUnder(bundleDir);
            for(let i = 0; i < files.length && !stopRequested; i++){
              const [path, handle] = files[i];
              await zip.add(`${names.bundle}/${path}`, new Uint8Array(await (await handle.getFile()).arrayBuffer()));
              statusEl.innerHTML = '<span class="spinner"></span> ' + escapeHtml(t('exportBundleZipProgress', {done: i + 1, total: files.length}));
            }
          }
          if(stopRequested) outcome = 'stopped';
          else if(zip){ await zip.finish(); await zipStream.close(); zipStream = null; }
        }
      }catch(e){
        outcome = 'error';
        errorMessage = e.message;
      }
      if(outcome !== 'done'){
        // Nothing half-made stays behind looking finished.
        if(zipStream){ try{ await zipStream.abort(); }catch(e){} }
        if(zipHandle){ try{ await parent.removeEntry(names.zip); }catch(e){} }
        if(madeTopFolder){ try{ await parent.removeEntry(topFolder, { recursive: true }); }catch(e){} }
        dest = null;
        zip = null;
      }
```

Note the thumbnail change: previously a thumbnail write failure was swallowed together with the read; now only the read is best-effort and a write failure (the destination is broken) aborts like any other write. Keep it.

c) Change `recordRecentLibrary(dest).catch(() => {});` to `if(dest) recordRecentLibrary(dest).catch(() => {});`.

d) In the `if(outcome === 'done'){ const lines = [ … ]` summary, replace the `const lines = [t('exportLibraryDone', …), t('exportLibraryExported', …)];` line with:

```js
        const lines = [];
        if(dest) lines.push(t('exportLibraryDone', {folder: `${parent.name}/${topFolder}`}));
        if(zip){
          lines.push(t('exportBundleZipDone', {zip: `${parent.name}/${names.zip}`, size: formatBytes(zip.size)}));
          if(zip.size > zipLimits.emailBytes) lines.push(t('exportBundleZipLarge'));
        }
        lines.push(t('exportLibraryExported', {count: exported.size}));
```

e) Change `el('export-library-open-btn').style.display = '';` to `if(dest) el('export-library-open-btn').style.display = '';`.

- [ ] **Step 7: Run the tests**

Run: `cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 test_export_bundle.py && python3 test_export_library.py`
Expected: every line `True`, `JS ERRORS: []` in both.

- [ ] **Step 8: Run the full suite** (command in Global Constraints). Expected: only `== file` headers.

- [ ] **Step 9: Commit**

```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
git add dossiary.html tests/test_export_bundle.py
git commit -m "Export as library: bundle with Dossiary as a folder, a .zip, or both"
```

---

### Task 5: Documentation

**Files:**
- Modify: `README.md` (Export as library bullet, ~line 239), `README.de.md` (~line 277), `CLAUDE.md` (the "**Export as library**" architecture note), `tests/CLAUDE.md` (coverage narrative + script count).

- [ ] **Step 1: README.md** — append to the end of the **Export as library** bullet (after "…is left out and listed."):

```markdown
  **What to create** can also bundle Dossiary itself: the library plus a copy
  of `dossiary.html` and a short `How to open.txt`, as a folder, a `.zip`
  file, or both — something you can send to a person who doesn't have
  Dossiary. They unzip it, open `dossiary.html` in Chrome or Edge on a
  computer, and choose the library folder. Dossiary downloads its own copy at
  the version you're running; offline, it asks you once to choose
  `dossiary.html` and remembers it. The zip isn't compressed (scans barely
  shrink), so large bundles are better sent by AirDrop, a shared folder or a
  USB stick than by email.
```

- [ ] **Step 2: README.de.md** — append to the end of the **Als Bibliothek exportieren** bullet (README.de addresses the reader with "Sie"):

```markdown
  Unter **Was erstellen** lässt sich Dossiary selbst mitgeben: die Bibliothek
  plus eine Kopie von `dossiary.html` und eine kurze `How to open.txt`, als
  Ordner, als `.zip`-Datei oder beides — zum Weitergeben an jemanden ohne
  Dossiary. Die Person entpackt es, öffnet `dossiary.html` in Chrome oder Edge
  auf einem Computer und wählt den Bibliotheksordner. Dossiary lädt seine
  eigene Kopie in der laufenden Version herunter; offline fragt es einmal nach
  `dossiary.html` und merkt sie sich. Die Zip-Datei ist nicht komprimiert
  (Scans werden kaum kleiner), große Pakete schicken Sie daher besser per
  AirDrop, geteiltem Ordner oder USB-Stick als per E-Mail.
```

- [ ] **Step 3: CLAUDE.md** — append to the end of the "**Export as library**" note (the bullet ending "`exportLibraryRunning` blocks closing the dialog meanwhile."):

```markdown
  **Bundles** (spec
  `docs/superpowers/specs/2026-10-20-export-bundle-with-dossiary-design.md`):
  "What to create" (`export-library-output`: `library` | `folder` | `zip` |
  `both`) can add Dossiary itself -- `<Bundle>/dossiary.html`,
  `<Bundle>/<Name>.dossiary/`, `<Bundle>/How to open.txt`
  (`bundleReadmeText()`: the UI language, then English) -- as a folder,
  `<Bundle>.zip`, or both. A `file://` page can't read its own file, so
  `getDossiaryHtmlForBundle()` downloads
  `cdn.jsdelivr.net/gh/AarneAarebye/Dossiary@v<APP_VERSION>/dossiary.html`
  (checked for the same `APP_VERSION`, 15 s timeout), else uses a copy
  chosen once ("Choose dossiary.html…"), whose *contents* are kept in
  IndexedDB (`dossiary-bundle-source`/`copies`) -- not a handle, since
  re-reading one needs a permission prompt that would use up the click the
  folder picker needs; that is also why the download happens only after the
  folder is picked. Library only never calls `fetch`. The zip comes from a
  built-in writer (`createZipWriter()`, `crc32()`, `zipLimits`): stored
  entries, UTF-8 names, ZIP64 past 4 GB or 65,535 entries, appended to one
  `createWritable()` stream so nothing large sits in memory. Zip only writes
  the library straight into the zip through the export loop's `sink`; Both
  writes the folder, then zips it (`listFilesUnder()`). Stop or a failure
  aborts and removes the partial zip and the created folder. The test stub's
  writable streams append like the real API (they used to replace).
```

- [ ] **Step 4: tests/CLAUDE.md** — change "**101 scripts covering most of the app's actual functionality** (98 of them Playwright-driven;" to "**104 scripts covering most of the app's actual functionality** (101 of them Playwright-driven;". Then, in the coverage narrative, directly after the export-as-library entry (it ends "…and "Open it" switching to the new library)"), insert:

```markdown
, bundles with Dossiary (`test_export_bundle.py` -- bundle names; the
download from jsDelivr at the running version (faked with `page.route`,
`access-control-allow-origin: *`), another version's download ignored,
offline with nothing stored, a copy chosen in the dialog, the stored copy
used silently, an outdated stored copy asking and declining/accepting;
`How to open.txt` in English, and German followed by English; then the
dialog: Library only unchanged and never fetching; a folder bundle's layout,
downloaded `dossiary.html`, instructions, summary, Open it and Recent
libraries entry; an existing bundle folder or zip refused; offline → Choose
dossiary.html (a non-Dossiary file refused, the chosen one stored and used on
the next click, and later without asking); an outdated stored copy declined
writing nothing; zip only read back with Python's `zipfile` (entries,
contents, CRCs, the zipped database, no folder, no Open it, no Recent
libraries entry); Both with identical folder and zip contents; the email
note and a ZIP64 zip with Armenian/Chinese names via
`__DEBUG_setZipLimits`; Stop removing a partial zip; Move only after the
zip is written; German labels), the zip writer itself
(`test_zip_writer.py` -- CRC32's check value, entries/contents/CRCs/stored/
UTF-8 flag read back with Python's `zipfile`, ZIP64 records with lowered
limits, an empty zip), and the stub's writable streams appending like the
real API (`test_stub_writable.py`)
```

(Adjust the joining punctuation so the sentence still reads correctly where it is inserted.)

- [ ] **Step 5: Commit**

```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
git add README.md README.de.md CLAUDE.md tests/CLAUDE.md
git commit -m "Docs: Export as library bundled with Dossiary"
```

---

## After the plan (controller, not a subagent)

- Add the 24 new Armenian strings to the Armenian review page (`hy/build_review.py` in the scratchpad; republish the review artifact) and write their English to `~/Desktop/export-bundle-english-for-grammarly.txt`.
- Manual check in real Chrome: export a small bundle as zip, unzip it in Finder, open `dossiary.html`, open the library folder; and check one zip with `unzip -t`.
