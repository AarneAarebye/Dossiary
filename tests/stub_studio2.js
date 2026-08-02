window.__STUB_LOG = [];

// ---- Fake File System Access API (same as before) ----
class FakeFileHandle {
  constructor(name, bytes) { this.name = name; this.kind = 'file'; this._bytes = bytes || new Uint8Array(0); }
  async getFile() {
    const bytes = this._bytes;
    const ext = (this.name.split('.').pop() || '').toLowerCase();
    const mimeMap = { png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', pdf: 'application/pdf', txt: 'text/plain' };
    const type = mimeMap[ext] || '';
    return new File([bytes], this.name, { type });
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

window.__makeEmptyRoot = function() { return new FakeDirHandle('EmptyLibrary'); };

window.showDirectoryPicker = async function(opts) {
  window.__STUB_LOG.push('showDirectoryPicker called with ' + JSON.stringify(opts));
  if (!window.__TEST_ROOT) throw Object.assign(new Error('no test root set'), { name: 'AbortError' });
  return window.__TEST_ROOT;
};

// ---- Fake sql.js (generic, same approach as before) ----
class FakeDatabase {
  constructor(bytes) {
    if (bytes && bytes.length) {
      try {
        const parsed = JSON.parse(new TextDecoder().decode(bytes));
        this.tables = { documents: parsed.documents || [], tags: parsed.tags || [], document_tags: parsed.document_tags || [], people: parsed.people || [], document_people: parsed.document_people || [], settings: parsed.settings || [], document_type_fields: parsed.document_type_fields || [], fields: parsed.fields || [], document_field_values: parsed.document_field_values || [] };
      } catch (e) {
        this.tables = { documents: [], tags: [], document_tags: [], people: [], document_people: [], settings: [], document_type_fields: [], fields: [], document_field_values: [] };
      }
    } else {
      this.tables = { documents: [], tags: [], document_tags: [], people: [], document_people: [], settings: [], document_type_fields: [], fields: [], document_field_values: [] };
    }
  }
  run(sql, params) {
    params = params || [];
    const n = sql.trim();
    if (/^CREATE TABLE/i.test(n)) return;
    if (/^ALTER TABLE/i.test(n)) return; // no-op here; missing keys already read back as null via exec()

    const deleteMatch = n.match(/^DELETE\s+FROM\s+(\w+)\s+WHERE\s+(\w+)\s*=\s*\?(?:\s+AND\s+(\w+)\s*=\s*\?)?/i);
    if (deleteMatch) {
      const table = deleteMatch[1];
      const col1 = deleteMatch[2];
      const col2 = deleteMatch[3];
      const val1 = params[0];
      const val2 = params[1];
      this.tables[table] = this.tables[table].filter(row => {
        if (row[col1] !== val1) return true; // keep rows that don't match col1
        if (col2 && row[col2] !== val2) return true; // col1 matches but col2 doesn't -- keep
        return false; // matches all specified conditions -- delete
      });
      return;
    }

    const updateMatch = n.match(/^UPDATE\s+(\w+)\s+SET\s+([\s\S]+?)\s+WHERE\s+(\w+)\s*=\s*\?/i);
    if (updateMatch) {
      const table = updateMatch[1];
      const assignments = updateMatch[2].split(',').map(s => s.trim());
      const whereCol = updateMatch[3];
      // last param is the WHERE id; the rest are the SET values in order
      const whereVal = params[params.length - 1];
      const setParams = params.slice(0, params.length - 1);
      let paramIdx = 0;
      const updates = {};
      for (const assignment of assignments) {
        const col = assignment.split('=')[0].trim();
        updates[col] = setParams[paramIdx++];
      }
      const row = this.tables[table].find(r => r[whereCol] === whereVal);
      if (row) Object.assign(row, updates);
      return;
    }

    const insertMatch = n.match(/INSERT(?:\s+OR\s+(?:IGNORE|REPLACE))?\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)/is);
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
    const isReplace = /INSERT\s+OR\s+REPLACE/i.test(n);
    if (table === 'settings' && isReplace) {
      this.tables.settings = this.tables.settings.filter(r => r.key !== row.key);
    }
    if (table === 'tags' && isIgnore) { if (this.tables.tags.some(t => t.name === row.name)) return; }
    if (table === 'document_tags' && isIgnore) {
      if (this.tables.document_tags.some(dt => dt.document_id === row.document_id && dt.tag_id === row.tag_id)) return;
    }
    if (table === 'people' && isIgnore) { if (this.tables.people.some(p => p.name === row.name)) return; }
    if (table === 'document_people' && isIgnore) {
      if (this.tables.document_people.some(dp => dp.document_id === row.document_id && dp.person_id === row.person_id)) return;
    }
    this.tables[table].push(row);
  }
  exec(sql) {
    const n = sql.trim();
    const selMatch = n.match(/SELECT\s+([\s\S]+?)\s+FROM\s+(\w+)(?:\s+WHERE\s+(\w+)\s*=\s*'([^']*)')?/i);
    if (!selMatch) throw new Error('FakeDatabase.exec: unhandled SQL: ' + n);
    const cols = selMatch[1].split(',').map(s => s.trim());
    const table = selMatch[2];
    const whereCol = selMatch[3];
    const whereVal = selMatch[4];
    let rows = this.tables[table] || [];
    if (whereCol !== undefined) rows = rows.filter(r => r[whereCol] === whereVal);
    if (!rows.length) return [];
    const values = rows.map(r => cols.map(c => (r[c] === undefined ? null : r[c])));
    return [{ columns: cols, values }];
  }
  export() { return new TextEncoder().encode(JSON.stringify(this.tables)); }
}

window.initSqlJs = async function(config) { window.__STUB_LOG.push('initSqlJs called'); return { Database: FakeDatabase }; };

// ---- Fake Tesseract with realistic word/bbox output ----
window.Tesseract = {
  createWorker: async function(langs) {
    window.__STUB_LOG.push('Tesseract.createWorker(' + JSON.stringify(langs) + ')');
    return {
      recognize: async (file, options, output) => {
        window.__STUB_LOG.push('recognize called with output=' + JSON.stringify(output));
        return {
          data: {
            text: 'Hello World',
            blocks: [{
              paragraphs: [{
                lines: [{
                  words: [
                    { text: 'Hello', bbox: { x0: 10, y0: 20, x1: 80, y1: 45 } },
                    { text: 'World', bbox: { x0: 90, y0: 20, x1: 160, y1: 45 } },
                  ]
                }]
              }]
            }]
          }
        };
      },
      terminate: async () => {},
    };
  }
};

// ---- Fake jsPDF: records calls, produces dummy bytes we can inspect ----
window.__JSPDF_CALLS = [];
class FakeJsPDFDoc {
  constructor(opts) { window.__JSPDF_CALLS.push({ type: 'construct', opts }); this._textCalls = []; }
  addImage(...args) { window.__JSPDF_CALLS.push({ type: 'addImage', args: [args[0] ? 'dataurl...' : args[0], args[1], args[2], args[3], args[4], args[5]] }); }
  setFontSize(size) { window.__JSPDF_CALLS.push({ type: 'setFontSize', size }); }
  text(str, x, y, options) { this._textCalls.push({ str, x, y, options }); window.__JSPDF_CALLS.push({ type: 'text', str, x, y, options }); }
  output(fmt) {
    window.__JSPDF_CALLS.push({ type: 'output', fmt, textCallCount: this._textCalls.length });
    return new TextEncoder().encode('FAKE-PDF-BYTES:' + JSON.stringify(this._textCalls)).buffer;
  }
}
window.jspdf = { jsPDF: FakeJsPDFDoc };

// ---- Fake pdf.js: renders a solid-color rectangle so canvas operations are real ----
window.pdfjsLib = {
  GlobalWorkerOptions: { workerSrc: '' },
  getDocument: function(opts) {
    window.__STUB_LOG.push('pdfjsLib.getDocument called');
    return {
      promise: Promise.resolve({
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
      }),
    };
  },
};

// Reusable helper: an empty library, but with document_type_fields pre-seeded so
// tests can select a document type and have People/custom fields actually render
// (matching the app's real behavior: fields only show for types they're configured
// for). typeFieldRows is [{document_type, field_name, position}, ...].
window.__makeSeededEmptyRoot = function(typeFieldRows, fieldRows) {
  const root = new FakeDirHandle('TestLib');
  const seed = {
    documents: [], tags: [], document_tags: [], people: [], document_people: [], settings: [],
    document_type_fields: typeFieldRows || [],
    fields: fieldRows || [],
    document_field_values: [],
  };
  const dbBytes = new TextEncoder().encode(JSON.stringify(seed));
  root._children.set('library.sqlite', new FakeFileHandle('library.sqlite', dbBytes));
  root._children.set('files', new FakeDirHandle('files'));
  return root;
};

// Generic seeded library: takes an arbitrary partial seed object (documents, tags,
// etc.) and fills in any missing tables as empty arrays, so callers only need to
// specify what they actually care about seeding.
window.__makeSeededRoot = function(seed) {
  const root = new FakeDirHandle('TestLib');
  const full = {
    documents: seed.documents || [], tags: seed.tags || [], document_tags: seed.document_tags || [],
    people: seed.people || [], document_people: seed.document_people || [], settings: seed.settings || [],
    document_type_fields: seed.document_type_fields || [], fields: seed.fields || [],
    document_field_values: seed.document_field_values || [],
  };
  const dbBytes = new TextEncoder().encode(JSON.stringify(full));
  root._children.set('library.sqlite', new FakeFileHandle('library.sqlite', dbBytes));
  root._children.set('files', new FakeDirHandle('files'));
  return root;
};
