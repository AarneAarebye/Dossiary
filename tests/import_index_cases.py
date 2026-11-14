import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))

# Writes import-index-cases.json for the Mac app (dossiary-osx, MacCore ImportIndex / ImportFolderScan): the page's own
# parseCsv + readImportIndex (index.csv in every UI language), importCollectionDefaultName + importExportCollectionNames
# (the " (2)" rule), settleExtraIndexFiles, isExtraIndexFileName and readExportDetails, evaluated on fixture inputs.
# Not part of the suite. The functions are cut out of dossiary.html as they are (the page needs no test hook) and run in a
# blank page; the translated header words come from the page's own translations (window.__DEBUG_exportFolderNames.tIn).
# Regenerate after a change to the page's import code. Usage:
#   /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 import_index_cases.py [output.json]
# Default output: ../../dossiary-osx/MacCore/Tests/MacCoreTests/Fixtures/import-index-cases.json

import asyncio, json, re, sys
from playwright.async_api import async_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else _os.path.abspath(_os.path.join(
    '..', '..', 'dossiary-osx', 'MacCore', 'Tests', 'MacCoreTests', 'Fixtures', 'import-index-cases.json'))

html = open(APP_PATH, encoding='utf-8').read()

def cut_function(name, asynchronous=False):
    m = re.search(r'^  %sfunction %s\(.*?\n  }\n' % ('async ' if asynchronous else '', name), html, re.S | re.M)
    assert m, name
    return m.group(0)

def cut_const(name):
    m = re.search(r'^  const %s = .*?;\n' % re.escape(name), html, re.S | re.M)
    assert m, name
    return m.group(0)

SOURCE = ''.join([
    cut_function('parseCsv'), cut_const('IMPORT_CSV_COLUMNS'), cut_function('readImportIndex'),
    cut_const('isoDay'), cut_const('splitList'), cut_function('importCollectionDefaultName'),
    cut_function('importExportCollectionNames'), cut_function('settleExtraIndexFiles'),
    cut_const('EXTRA_INDEX_FILE_RES'), cut_const('isExtraIndexFileName'), cut_function('cleanLibraryText'),
    cut_const('LIBRARY_TITLE_MAX = 60, LIBRARY_DESCRIPTION_MAX'),
    cut_function('readExportDetails', asynchronous=True),
])
version = re.search(r"const APP_VERSION = '([^']+)'", html).group(1)

LANGS = ['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']
KEYS = ['exportCsvFile', 'editTitleLabel', 'tableColDate', 'tableColImported', 'tableColCategory', 'editSubcategoryLabel',
        'tableColType', 'tableColTags', 'tableColPeople', 'detailSectionNotes']
BOM = '﻿'

# --- index.csv texts ------------------------------------------------------------------------------------------------

def csv_line(cells, sep):
    def cell(v):
        return '"' + v.replace('"', '""') + '"' if ('"' in v or '\n' in v or '\r' in v or sep in v) else v
    return sep.join(cell(c) for c in cells)

INDEX_CASES = []   # (name, text, header words language or None)

def add(name, text):
    INDEX_CASES.append({'name': name, 'text': text})

# Every language, written the way Export writes it (BOM, CRLF, ';' for de/fr/es/hy), with the three English standard
# fields and an unknown column, two documents, one with a quote, a separator and a line break in its notes.
def per_language(words):
    for lang in LANGS:
        sep = ';' if lang in ('de', 'es', 'fr', 'hy') else ','
        w = words[lang]
        header = w[0:7] + ['Amount', 'Currency', 'Payment method'] + w[7:10] + ['Organization']
        rows = [
            ['2022-09-21 Invoice.pdf', 'Rechnung "A"', '2022-09-21', '2022-09-22T08:00:00+00:00', 'Home', 'Rent', 'Invoice',
             '12.50', 'EUR', 'Card', 'tax, private', 'Jana, Arne', 'Line 1\nLine 2, with ' + sep + ' sep', 'Acme'],
            ['scan 2.JPG', '', '', '', '', '', '', '', '', '', '', '', '', ''],
        ]
        text = BOM + '\r\n'.join(csv_line(r, sep) for r in [header] + rows) + '\r\n'
        add('export-' + lang, text)
        # the same file with LF line ends, no BOM
        add('export-lf-' + lang, text[1:].replace('\r\n', '\n'))
        # and with the other separator (the page picks the one the header uses more)
        other = ';' if sep == ',' else ','
        add('otherSep-' + lang, '\r\n'.join(csv_line(r, other) for r in [header] + rows) + '\r\n')

OTHER_CASES = [
    ('basic-en', 'File,Title,Date,Category,Type,Tags,People,Notes\nA.pdf,Invoice,2024-03-01,Home,Bill,"x, y",Jana,hello\n'),
    ('keys-lowercased-and-trimmed', 'File,Title\nA B.PDF ,  Spaced  \na b.pdf,Second\n'),
    ('header-case-and-spaces', '  FILE  , title ,DATE,imported\nA.pdf,T,2024-01-02,2024-01-03\n'),
    ('mixed-languages', 'Datei,Title,Fecha,Importé,Catégorie,Unterkategorie,Typ,Etiquetas,Personnes,Notizen\nA.pdf,T,2024-01-02,2024-01-03,C,S,Y,t1,p1,n\n'),
    ('no-file-column', 'Title,Date\nA,2024-01-01\n'),
    ('empty', ''),
    ('blank-lines-only', '\n\r\n  \n'),
    ('header-only', 'File,Title\n'),
    ('header-only-no-newline', 'File'),
    ('file-column-second-copy-becomes-field', 'File,File,Title\nA.pdf,B.pdf,T\n'),
    ('duplicate-title-columns-first-wins', 'File,Title,Title,Notes,Notes\nA.pdf,One,Two,N1,N2\n'),
    ('duplicate-custom-columns', 'File,Foo,Foo,Bar,Bar\nA.pdf,1,2,x,\nB.pdf,,3,,y\nC.pdf,,,,\n'),
    ('unknown-columns', 'File,Plate,Organization,,Amount\nA.pdf,B-XY 123,Dr. Schröter,ignored,5\nB.pdf,,,x,\n'),
    ('empty-header-column-ignored', 'File,,Title\nA.pdf,skipped,T\n'),
    ('integer-like-custom-names', 'File,2024,Zeta,7,Alpha\nA.pdf,a,b,c,d\n'),
    ('quotes-and-newlines', 'File,Title,Notes\n"A, B.pdf","He said ""hi""","l1\r\nl2\nl3"\n'),
    ('quote-mid-cell', 'File,Title\nA.pdf,ab"c,d"e\nB.pdf,x\n'),
    ('unterminated-quote', 'File,Title\nA.pdf,"never closed\nB.pdf,x\n'),
    ('semicolon-header', 'File;Title;Notes\nA.pdf;T;a, b\n'),
    ('semicolon-in-quoted-header', '"Fi;le",Title,Notes\nA.pdf,T,n\n'),
    ('tie-prefers-comma', 'File;Title,Notes\nA.pdf;T,n\n'),
    ('bom-only-first', BOM + 'File,Title\n' + BOM + 'A.pdf,T\n'),
    ('lone-cr-line-ends', 'File,Title\rA.pdf,T\rB.pdf,U\r'),
    ('crlf', 'File,Title\r\nA.pdf,T\r\nB.pdf,U'),
    ('ragged-rows', 'File,Title,Date,Notes\nA.pdf\nB.pdf,T\nC.pdf,T,2024-01-01,n,extra,extra2\n'),
    ('blank-and-separator-only-rows-dropped', 'File,Title\n\n,\n ; \nA.pdf,T\n,,,\n'),
    ('rows-without-file-dropped', 'File,Title\n,No file\n  ,Blank\nA.pdf,T\n'),
    ('duplicate-file-names-last-wins', 'File,Title,Notes\nA.pdf,First,n1\na.PDF,Second,\nB.pdf,B,\n'),
    ('dates', 'File,Date,Imported\n' + '\n'.join('f%d.pdf,%s,%s' % (i, d, d) for i, d in enumerate([
        '2026-02-30', '2026-02-29', '2024-02-29', '2026-13-01', '2026-00-10', '2026-04-31', '2026-01-32', '2026-1-1',
        '20260101', '2026-03-04T10:00:00Z', '2026-03-04 10:00', ' 2026-03-04 ', 'abc', '', '0000-01-01', '0001-01-01',
        '9999-12-31', '1900-02-29', '2000-02-29', '2100-02-29', '2026-02-31', '2026-01-00', '2026-02-28junk', '２０２６-03-04', '2026-03-04-05'])) + '\n'),
    ('tag-and-people-lists', 'File,Tags,People,Author\nA.pdf,"a, b ,,c,a, ,B,b","Jana,  Arne,,Jana, ",Jana;Arne\nB.pdf,,,\n'),
    ('only-separators-in-list', 'File,Tags,People\nA.pdf," , ,, ", ,\n'),
    ('unicode-names', 'File,Title\nÄrger.pdf,x\nÄRGER2.pdf,y\n発票.PDF,z\n'),
    ('header-trailing-separator', 'File,Title,\nA.pdf,T,extra\n'),
    ('whitespace-only-cells', 'File,Title,Notes\nA.pdf,   ,\t\n'),
    ('values-trimmed', 'File,Title,Foo\nA.pdf,  T  ,  v  \n'),
    ('first-line-quoted-with-commas', '"File, name",Title\nA.pdf,T\n'),
    ('no-trailing-newline', 'File,Title\nA.pdf,T'),
    ('trailing-empty-cell', 'File,Title\nA.pdf,'),
]
for n, t in OTHER_CASES:
    add(n, t)

# --- other inputs ----------------------------------------------------------------------------------------------------

# [title, folder name, [y, m, d, h, mi], existing collection names]
COLLECTION_CASES = [
    [None, 'Scans', [2026, 11, 7, 14, 32], []],
    ['Tax 2024', 'Folder', [2026, 1, 2, 3, 4], []],
    ['', 'Folder', [2026, 12, 31, 23, 59], []],
    ['Tax 2024', 'Folder', [2026, 11, 7, 14, 32], ['Tax 2024 · 2026-11-07 14:32']],
    ['Tax 2024', 'Folder', [2026, 11, 7, 14, 32], ['  tax 2024 · 2026-11-07 14:32  ', 'Tax 2024 · 2026-11-07 14:32 (2)']],
    [None, 'Ünïcödé 発票', [2026, 11, 7, 0, 0], ['Other']],
    [None, 'Folder', [2026, 11, 7, 9, 5], ['FOLDER · 2026-11-07 09:05', 'folder · 2026-11-07 09:05 (2)', 'Folder · 2026-11-07 09:05 (4)']],
]

# [regular files, extra index files, has index.csv, names the index lists (lower case)]
SETTLE_CASES = [
    [['b.pdf', 'a.pdf'], ['index (2).csv', 'export-details (2).json'], True, ['a.pdf']],
    [['b.pdf', 'a.pdf'], ['index (2).csv', 'export-details (2).json'], False, []],
    [['b.pdf'], ['index (2).csv', 'export-details (3).json', 'index (4).csv'], True, ['index (2).csv', 'export-details (3).json']],
    [['b.pdf'], ['Index (2).CSV'], True, ['index (2).csv']],
    [['b.pdf'], ['Index (2).CSV'], True, ['b.pdf']],
    [[], [], True, []],
    [['B.pdf', 'a.pdf', 'C.pdf', 'b2.pdf', 'Ä.pdf', 'z.pdf', 'A.pdf'], ['index (2).csv'], False, []],
]

EXTRA_NAMES = ['index (2).csv', 'INDEX (10).CSV', 'index (2).csv.bak', 'index(2).csv', 'index ().csv', 'index (a).csv',
               'export-details (2).json', 'Export-Details (12).JSON', 'export-details (2).jsn', 'index.csv',
               'export-details.json', 'xindex (2).csv', 'index (２).csv', 'index (2) .csv', 'index (2).csv ']

DETAILS_CASES = [
    '{"format":1,"title":"Tax 2024","description":"For the advisor"}',
    '{"format": 1, "title": "Tax", "description": ""}',
    '{"title": "", "description": "Only text"}',
    '{"title": "", "description": ""}',
    '{"title": "  a \\n\\t b  ", "description": " x   y\\n\\nz "}',
    '{"title": "' + 'x' * 70 + '", "description": "' + 'y' * 320 + '"}',
    '{"title": "' + 'x' * 59 + ' tail", "description": "' + 'y' * 299 + ' z"}',
    '{"title": 5, "description": ["a"]}',
    '{"title": 5, "description": "ok"}',
    '{"title": null}',
    '{}',
    '[]',
    '[{"title":"x"}]',
    'null',
    '"text"',
    '12',
    'true',
    '',
    'not json',
    '{"title": "Ünïcödé 発票 Հաշիվ 😀", "description": "Quotes \\"and\\" back\\\\slash"}',
    '﻿{"title": "With BOM"}',
    '{"title": "Dup", "title": "Last"}',
]

JS = r"""async (input) => {
    const h = window.__DEBUG_exportFolderNames;
    const STRINGS = {};
    for(const lang of input.langs){ STRINGS[lang] = {}; for(const k of input.keys) STRINGS[lang][k] = h.tIn(lang, k); }
    const f = new Function('STRINGS', 'SUPPORTED_LANGS', input.source + `; return {readImportIndex, isoDay, splitList,
        importCollectionDefaultName, importExportCollectionNames, settleExtraIndexFiles, isExtraIndexFileName, readExportDetails};`)(STRINGS, input.langs);
    const out = { headerWords: {}, index: [], collections: [], settle: [], extraNames: [], details: [] };
    for(const lang of input.langs) out.headerWords[lang] = input.keys.map(k => STRINGS[lang][k]);
    const nul = (v) => v ? v : null;
    for(const c of input.index){
      const map = f.readImportIndex(c.text);
      if(!map){ out.index.push({ name: c.name, text: c.text, expected: null }); continue; }
      const rows = [...map.values()].map(r => ({
        file: r.file, title: nul(r.title), date: f.isoDay(r.date), import_date: f.isoDay(r.import_date),
        category: nul(r.category), subcategory: nul(r.subcategory), document_type: nul(r.document_type),
        tags: [...new Set(f.splitList(r.tags))], people: [...new Set(f.splitList(r.people))], notes: nul(r.notes),
        fields: Object.entries(r.fields) }));
      out.index.push({ name: c.name, text: c.text, expected: { keys: [...map.keys()], rows } });
    }
    for(const [title, folder, n, existing] of input.collections){
      const now = new Date(n[0], n[1] - 1, n[2], n[3], n[4]);
      const about = title === null ? null : { title };
      out.collections.push({ title, folderName: folder, now: n, existing,
        plain: f.importCollectionDefaultName(about, folder, now),
        expected: f.importExportCollectionNames([{ about, name: folder }], existing.map(name => ({ name })), now)[0] });
    }
    for(const [files, extra, hasIndex, listed] of input.settle){
      const scan = { files: files.map(name => ({ name })), extraIndexFiles: extra.map(name => ({ name })), indexHandle: hasIndex ? {} : null };
      const index = hasIndex ? new Map(listed.map(k => [k, {}])) : null;
      const r = f.settleExtraIndexFiles(scan, index);
      out.settle.push({ files, extra, hasIndex, listed, expected: { files: r.files.map(x => x.name), extraIndexSkipped: r.extraIndexSkipped } });
    }
    for(const n of input.extraNames) out.extraNames.push({ name: n, isExtra: f.isExtraIndexFileName(n) });
    for(const text of input.details){
      const d = await f.readExportDetails({ getFile: async () => ({ text: async () => text }) });
      out.details.push({ text, expected: d });
    }
    return out;
}"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        # the per-language texts need the page's own header words first
        words = await page.evaluate("""([langs, keys]) => { const h = window.__DEBUG_exportFolderNames; const o = {};
            for(const l of langs) o[l] = keys.map(k => h.tIn(l, k)); return o; }""", [LANGS, KEYS])
        per_language(words)
        out = await page.evaluate(JS, {
            'source': SOURCE, 'langs': LANGS, 'keys': KEYS, 'index': INDEX_CASES, 'collections': COLLECTION_CASES,
            'settle': SETTLE_CASES, 'extraNames': EXTRA_NAMES, 'details': DETAILS_CASES})
        await browser.close()
        assert not errors, errors

        # A few checks that the page still behaves as the Mac app expects (a failure means: look before regenerating).
        assert out['headerWords']['en'] == ['File', 'Title', 'Date', 'Imported', 'Category', 'Subcategory', 'Type', 'Tags', 'People', 'Notes']
        by = {c['name']: c['expected'] for c in out['index']}
        for lang in LANGS:
            e = by['export-' + lang]
            assert e and e['keys'] == ['2022-09-21 invoice.pdf', 'scan 2.jpg'], (lang, e)
            assert e['rows'][0]['category'] == 'Home' and e['rows'][0]['tags'] == ['tax', 'private'], (lang, e['rows'][0])
            assert e['rows'][0]['fields'][0] == ['Amount', '12.50'], (lang, e['rows'][0]['fields'])
        assert by['no-file-column'] is None and by['empty'] is None
        assert by['bom-only-first']['keys'] == ['a.pdf'] or by['bom-only-first']['keys'], by['bom-only-first']
        assert by['duplicate-title-columns-first-wins']['rows'][0]['title'] == 'One'
        assert by['duplicate-file-names-last-wins']['keys'] == ['a.pdf', 'b.pdf']
        assert by['duplicate-file-names-last-wins']['rows'][0]['title'] == 'Second'
        assert out['collections'][0]['expected'] == 'Scans · 2026-11-07 14:32'
        assert out['collections'][3]['expected'].endswith('(2)')
        assert [c['isExtra'] for c in out['extraNames']][:3] == [True, True, False]
        assert out['details'][0]['expected'] == {'title': 'Tax 2024', 'description': 'For the advisor'}
        total = len(out['index']) + len(out['collections']) + len(out['settle']) + len(out['extraNames']) + len(out['details'])
        assert total >= 100, total

        out = {'generatedBy': 'Dossiary/tests/import_index_cases.py', 'pageVersion': version, **out}
        _os.makedirs(_os.path.dirname(OUT), exist_ok=True)
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write('\n')
        print(f"ok: {total} cases -> {OUT}")

asyncio.run(main())
