import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Seed data mimicking what migrate_to_new_library.py already produced from the real library
SEED = {
    "documents": [
        {
            "id": 1, "title": "Rechnung", "category": "Medical", "document_type": "Invoice",
            "payment_method": "Deutsche Bank", "amount": 244.0, "date": "2018-12-27T11:00:00+00:00",
            "notes": None, "ocr_text": "RECHNUNG-ORIGINAL sample text", "ocr_language": None,
            "file_path": "files/1_doc.pdf", "original_file_path": "files/1_doc/original.pdf",
            "created_at": "2026-07-28T08:19:45+00:00", "source": "migrated", "source_legacy_id": 529
        }
    ],
    "tags": [{"id": 1, "name": "Haus"}],
    "document_tags": [],
    "document_type_fields": [{"document_type": "Note", "field_name": "Amount", "position": 0}],
}

STUB_JS = r"""
window.__STUB_LOG = [];

// ---- Fake File System Access API ----
class FakeFileHandle {
  constructor(name, bytes) { this.name = name; this.kind = 'file'; this._bytes = bytes || new Uint8Array(0); }
  async getFile() {
    const bytes = this._bytes;
    return {
      name: this.name, size: bytes.length, type: '',
      arrayBuffer: async () => bytes.slice().buffer,
      text: async () => new TextDecoder().decode(bytes),
    };
  }
  async createWritable() {
    const self = this;
    let buf = new Uint8Array(0);
    return {
      write: async (data) => {
        if (data instanceof ArrayBuffer) buf = new Uint8Array(data);
        else if (data instanceof Uint8Array) buf = data;
        else if (typeof data === 'string') buf = new TextEncoder().encode(data);
        else if (data && data.arrayBuffer) buf = new Uint8Array(await data.arrayBuffer());
        else buf = new Uint8Array(0);
      },
      close: async () => { self._bytes = buf; },
    };
  }
}
class FakeDirHandle {
  constructor(name) { this.name = name; this.kind = 'directory'; this._children = new Map(); }
  async getFileHandle(name, opts) {
    if (this._children.has(name)) {
      const h = this._children.get(name);
      if (h.kind !== 'file') throw new Error('Not a file: ' + name);
      return h;
    }
    if (opts && opts.create) { const h = new FakeFileHandle(name); this._children.set(name, h); return h; }
    const err = new Error('File not found: ' + name); err.name = 'NotFoundError'; throw err;
  }
  async getDirectoryHandle(name, opts) {
    if (this._children.has(name)) {
      const h = this._children.get(name);
      if (h.kind !== 'directory') throw new Error('Not a directory: ' + name);
      return h;
    }
    if (opts && opts.create) { const h = new FakeDirHandle(name); this._children.set(name, h); return h; }
    const err = new Error('Dir not found: ' + name); err.name = 'NotFoundError'; throw err;
  }
}

window.__makeSeededRoot = function(seed) {
  const root = new FakeDirHandle('TestLibrary');
  const dbJson = JSON.stringify(seed);
  const dbBytes = new TextEncoder().encode(dbJson);
  root._children.set('library.sqlite', new FakeFileHandle('library.sqlite', dbBytes));
  const filesDir = new FakeDirHandle('files');
  root._children.set('files', filesDir);
  filesDir._children.set('1_doc.pdf', new FakeFileHandle('1_doc.pdf', new TextEncoder().encode('%PDF fake processed')));
  const subDir = new FakeDirHandle('1_doc');
  filesDir._children.set('1_doc', subDir);
  subDir._children.set('original.pdf', new FakeFileHandle('original.pdf', new TextEncoder().encode('%PDF fake original')));
  return root;
};

window.__makeEmptyRoot = function() { return new FakeDirHandle('EmptyLibrary'); };

window.showDirectoryPicker = async function(opts) {
  window.__STUB_LOG.push('showDirectoryPicker called with ' + JSON.stringify(opts));
  if (!window.__TEST_ROOT) throw Object.assign(new Error('no test root set'), { name: 'AbortError' });
  return window.__TEST_ROOT;
};

// ---- Fake sql.js (generic enough to handle the app's actual INSERT/SELECT patterns) ----
class FakeStatementResult {}

class FakeDatabase {
  constructor(bytes) {
    if (bytes && bytes.length) {
      try {
        const parsed = JSON.parse(new TextDecoder().decode(bytes));
        this.tables = { documents: parsed.documents || [], tags: parsed.tags || [], document_tags: parsed.document_tags || [] };
      } catch (e) {
        this.tables = { documents: [], tags: [], document_tags: [] };
      }
    } else {
      this.tables = { documents: [], tags: [], document_tags: [] };
    }
  }
  run(sql, params) {
    params = params || [];
    const n = sql.trim();
    if (/^CREATE TABLE/i.test(n)) return; // schema no-op, tables are implicit
    const insertMatch = n.match(/INSERT(?:\s+OR\s+IGNORE)?\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)/is);
    if (!insertMatch) throw new Error('FakeDatabase.run: unhandled SQL: ' + n);
    const table = insertMatch[1];
    const cols = insertMatch[2].split(',').map(s => s.trim());
    const valueTokens = insertMatch[3].split(',').map(s => s.trim());
    let paramIdx = 0;
    const row = {};
    cols.forEach((col, i) => {
      const tok = valueTokens[i];
      if (tok === '?') { row[col] = params[paramIdx++]; }
      else if (/^NULL$/i.test(tok)) { row[col] = null; }
      else if (/^'.*'$/.test(tok)) { row[col] = tok.slice(1, -1); }
      else { row[col] = tok; }
    });
    const isIgnore = /INSERT\s+OR\s+IGNORE/i.test(n);
    if (table === 'tags' && isIgnore) {
      if (this.tables.tags.some(t => t.name === row.name)) return;
    }
    if (table === 'document_tags' && isIgnore) {
      if (this.tables.document_tags.some(dt => dt.document_id === row.document_id && dt.tag_id === row.tag_id)) return;
    }
    this.tables[table].push(row);
  }
  exec(sql) {
    const n = sql.trim();
    const selMatch = n.match(/SELECT\s+([\s\S]+?)\s+FROM\s+(\w+)/i);
    if (!selMatch) throw new Error('FakeDatabase.exec: unhandled SQL: ' + n);
    const cols = selMatch[1].split(',').map(s => s.trim());
    const table = selMatch[2];
    const rows = this.tables[table] || [];
    if (!rows.length) return [];
    const values = rows.map(r => cols.map(c => (r[c] === undefined ? null : r[c])));
    return [{ columns: cols, values }];
  }
  export() {
    return new TextEncoder().encode(JSON.stringify(this.tables));
  }
}

window.initSqlJs = async function(config) {
  window.__STUB_LOG.push('initSqlJs called');
  return { Database: FakeDatabase };
};

// ---- Fake Tesseract ----
window.Tesseract = {
  createWorker: async function(langs) {
    window.__STUB_LOG.push('Tesseract.createWorker(' + JSON.stringify(langs) + ')');
    return {
      recognize: async (file) => ({ data: { text: 'FAKE OCR TEXT for ' + file.name } }),
      terminate: async () => {},
    };
  }
};
"""

# Note: STUB_JS above is no longer used -- this test now uses the shared,
# actively-maintained stub_studio2.js (see route_handler below) instead of this
# stale embedded copy, which predates that standardization and was missing
# several tables added since (people, settings, document_type_fields, fields,
# document_field_values). Left in place only for historical reference; don't
# revive it without bringing it up to date with stub_studio2.js first.


async def run_test():
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
                await route.continue_()
        await page.route('**/*', route_handler)

        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)

        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        # === SCENARIO 1: open a seeded (migrated) library ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        status1 = await page.locator("#status").inner_text()
        row_count1 = await page.locator("#doc-tbody tr").count()
        print("--- Scenario 1: open seeded library ---")
        print("status:", status1)
        print("row count:", row_count1)

        # open detail modal, check migrated doc shows both file buttons
        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        open_file_btn = await page.locator('#open-file-btn').count()
        open_original_btn = await page.locator('#open-original-btn').count()
        print("open-file button:", open_file_btn, " open-original button:", open_original_btn)
        await page.click('#modal-close-btn')

        # === SCENARIO 2: add a new document (image, OCR, tags incl. reused tag) ===
        await page.click('#add-btn')
        await page.wait_for_timeout(150)

        # create a tiny fake image file on disk to feed the file input
        import base64
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('tiny.png', 'wb') as f:
            f.write(png_bytes)

        await page.set_input_files('#file-input', 'tiny.png')
        await page.wait_for_timeout(150)
        run_ocr_enabled = not await page.locator('#run-ocr-btn').is_disabled()
        print("OCR button enabled for image:", run_ocr_enabled)

        await page.click('#run-ocr-btn')
        await page.wait_for_timeout(300)
        ocr_text_value = await page.locator('#f-ocr-text').input_value()
        print("OCR text field after run:", ocr_text_value)

        await page.fill('#f-title', 'Test Scan')
        await page.fill('#f-category', 'Testing')
        await page.fill('#f-type', 'Note')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.fill('[data-dynamic-field="Amount"] input', '12.50')
        await page.fill('#f-date', '2026-07-28')
        await page.fill('#f-tags', 'Haus, NewTag')  # 'Haus' already exists in seed -> should be reused, not duplicated
        await page.fill('#f-notes', 'a test note')

        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        status2 = await page.locator("#status").inner_text()
        row_count2 = await page.locator("#doc-tbody tr").count()
        print("--- Scenario 2: add new document ---")
        print("status after save:", status2)
        print("row count after save:", row_count2)

        # check the new row rendered correctly with a 'new' badge
        row2_html = await page.locator('tr[data-id="2"]').inner_html()
        print("new row contains 'new' badge:", 'captured' in row2_html)
        print("new row contains tags:", 'Haus' in row2_html and 'NewTag' in row2_html)

        # === SCENARIO 3: simulate reopening (fresh page load) with the SAME root handle to verify persistence ===
        page2 = await browser.new_page()
        errors2 = []
        page2.on("pageerror", lambda exc: errors2.append(str(exc)))
        await page2.route('**/*', route_handler)
        await page2.add_init_script(stub_js)
        await page2.goto(f"file://{APP_PATH}")
        await page2.wait_for_timeout(200)
        # reuse the SAME root handle object by re-evaluating a reference stored on window across pages isn't possible
        # (each page has its own window) -- instead, verify persistence by re-reading the bytes we wrote via scenario 2's page
        exported_bytes_check = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                const text = await f.text();
                const parsed = JSON.parse(text);
                return { docCount: parsed.documents.length, tagCount: parsed.tags.length, tagNames: parsed.tags.map(t=>t.name) };
            })()
        """)
        print("--- Scenario 3: verify persisted bytes on 'disk' after save ---")
        print("persisted state:", exported_bytes_check)

        print("JS ERRORS (page1):", errors)
        print("JS ERRORS (page2, unused nav):", errors2)
        await browser.close()

asyncio.run(run_test())
