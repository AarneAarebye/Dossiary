import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))

# Writes export-name-cases.json for the Mac app (dossiary-osx): export file and folder names, the " (2)" numbering with
# the reserved names, index.csv in every UI language, the CSV separators, the INCOMPLETE marker names and texts and
# export-details.json -- each computed by the page's own functions (window.__DEBUG_exportFolderNames), so the Swift
# port (MacCore ExportNames/ExportCSV/ExportDetails/IncompleteMarker) can be checked against it. Not part of the suite.
# Regenerate after a change to the page's export naming. Usage:
#   python3 export_name_cases.py [output.json]
# Default output: ../../dossiary-osx/MacCore/Tests/MacCoreTests/Fixtures/export-name-cases.json
#
# The page cuts names at 120 / 100 UTF-16 code units, which can split an emoji and leave half of a surrogate pair (not
# a valid name on macOS, and not representable in a Swift String). Such a case is written with the half removed and
# "pageHadLoneSurrogate": true.

import asyncio, json, re, sys
from playwright.async_api import async_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else _os.path.abspath(_os.path.join(
    '..', '..', 'dossiary-osx', 'MacCore', 'Tests', 'MacCoreTests', 'Fixtures', 'export-name-cases.json'))

LANGS = ['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']
DATE = '2022-09-21T10:00:00+00:00'
INVISIBLE = '­​‌‍‎‏‪‫‬‭‮⁠⁡⁢⁣⁤' \
    + ''.join(chr(c) for c in range(0x2066, 0x2070)) + '﻿'

def doc(i, title, date=DATE, path='files/x.pdf', category=None, document_type=None):
    return {'id': i, 'title': title, 'category': category, 'document_type': document_type, 'date': date, 'file_path': path}

FILE_DOCS = [
    doc(1, 'Invoice'),
    doc(2, 'Rechnung Müller – Größe Ä Ö Ü ß'),
    doc(3, 'Trip 🏖️ receipts 📄'),
    doc(4, '21 Sept, 08.30​ consultation with Martin', path='files/7_a.aac'),
    doc(5, 'a' + INVISIBLE + 'b'),
    doc(6, 'Report...'),
    doc(7, 'Report   '),
    doc(8, 'Report. . .'),
    doc(9, 'L' * 200),
    doc(10, 'a' * 108 + '😀 tail'),  # the date and 108 letters are 119 units: the cut splits the emoji
    doc(11, 'b' * 108 + ' after'),  # the 120th unit is a space: kept, the page does not trim after the cut
    doc(12, '​​'),
    doc(13, '​​', date=None),
    doc(14, '', category='Insurance'),
    doc(15, None, category=None, document_type='Letter'),
    doc(16, None, category='', document_type=''),
    doc(17, '   '),
    doc(18, '   ', date=None),
    doc(19, 'a\\b/c:d*e?f"g<h>i|j'),
    doc(20, 'tab\there\nnew\rline\x00nul\x7fdel\x85nel\x9fend'),
    doc(21, 'non breaking　ideographic line para narrow math ogham em'),
    doc(22, 'No date', date=None),
    doc(23, 'Date only', date='2022-09-21'),
    doc(24, 'No file', path=None),
    doc(25, 'Upper ext', path='files/7_a.PDF'),
    doc(26, 'No ext', path='files/7_noext'),
    doc(27, 'Dot in folder', path='files/dir.v2/file'),
    doc(28, 'Hidden', path='files/.hidden'),
    doc(29, 'Two exts', path='files/a.tar.gz'),
    doc(30, 'index', date=None, path='files/x.csv'),
    doc(31, '发票 2024'),
    doc(32, 'Հաշիվ ապրիլ'),
    doc(33, 'Café decomposed'),
    doc(34, 'فاتورة ‏‫مهم‬'),
    doc(35, '   Leading spaces'),
    doc(36, 'INCOMPLETE - this export was not finished', date=None, path='files/x.txt'),
    doc(37, '...'),
    doc(38, '  '),
    doc(39, '📄'),
    doc(40, 'ä' * 130, date=None),
    doc(41, 'export-details', date=None, path='files/x.json'),
    doc(42, 'Mixed  \t  whitespace   inside'),
    doc(43, 'x' * 117 + '"', date=None),
    doc(44, 'Ends with dot.', date=None),
    doc(45, '  ​  ', date=None, category='Fallback ignored'),
    doc(46, 'Long date', date='2022-09-21 10:00:00 and more'),
]

FOLDER_TITLES = [
    None, '', '   ', 'Tax 2024', 'Arne​’s / Collection', 'a' + INVISIBLE + 'b', 'F' * 150,
    'c' * 99 + ' tail', 'd' * 99 + '😀', 'Ünïcödé · 发票 · Հաշիվ', 'Ends with dots...', 'ctrl\tchars\n\x85here',
    'a\\b/c:d*e?f"g<h>i|j', '​', '  spaced   out  ',
]

SUBFOLDERS = [
    ('Tax 2024', [2026, 11, 14, 9, 5, 3], '0a1b'),
    ('', [2026, 1, 2, 3, 4, 5], 'ffff'),
    ('   ', [2026, 12, 31, 23, 59, 59], '0000'),
    ('​', [2026, 6, 7, 0, 0, 0], 'abcd'),
    ('a/b', [2025, 2, 28, 12, 30, 0], '1234'),
    ('G' * 120, [2026, 11, 14, 18, 7, 9], 'beef'),
    (None, [2026, 11, 14, 18, 7, 9], 'c0de'),
]

# Each: names asked for one after another (taken starts with the page's reserved names), existing files in the folder.
UNIQUE = [
    (['a.pdf', 'a.pdf', 'A.PDF'], []),
    (['index.csv'], []),
    (['Index.CSV'], []),
    (['export-details.json'], []),
    (['INCOMPLETE - this export was not finished.txt'], []),
    (['incomplete - this backup was not finished.TXT'], []),
    (['.hidden', '.hidden'], []),
    (['noext', 'noext', 'NOEXT'], []),
    (['b.pdf'], ['b.pdf', 'b (2).pdf']),
    (['c.pdf', 'c.pdf'], ['c (2).pdf']),
    (['a.b.c', 'a.b.c'], []),
    (['Ä.pdf', 'ä.pdf'], []),
    (['ß.pdf', 'SS.pdf', 'ss.pdf'], []),
    (['İ.pdf', 'i̇.pdf'], []),
    (['2022-09-21 Invoice.pdf', '2022-09-21 invoice.pdf', '2022-09-21 INVOICE.pdf', '2022-09-21 Invoice.pdf'], []),
    (['x (2).pdf', 'x.pdf', 'x.pdf'], []),
    (['😀.pdf', '😀.pdf'], []),
]

def csv_doc(i, **kw):
    d = {'id': i, 'title': None, 'date': None, 'import_date': None, 'category': None, 'subcategory': None,
         'document_type': None, 'notes': None, 'customFields': {}, 'tags': [], 'people': []}
    d.update(kw)
    return d

CSV_ROWS_ALL = [
    {'d': csv_doc(1, title='Hotel Berlin', date=DATE, import_date='2022-09-22T08:00:00+00:00', category='Travel',
                  subcategory='Hotel', document_type='Invoice', notes='Business trip',
                  customFields={'Amount': '120.50', 'Currency': 'EUR', 'Payment method': 'Card', 'Organization': 'Grand Hotel'},
                  tags=['trip', 'tax'], people=['Arne', 'Jana']), 'fileName': '2022-09-21 Hotel Berlin.pdf'},
    {'d': csv_doc(2, title='Semi; colon, comma "quote"', date='2023-01-05', notes='line one\nline two\r\nthree',
                  customFields={'Amount': '1,5', 'Paid': '1'}, tags=['a, b', 'c;d']), 'fileName': '2023-01-05 Semi; colon, comma -quote-.pdf'},
    {'d': csv_doc(3), 'fileName': 'document-3.jpg'},
]
CSV_CASES = [{'lang': lang, 'rows': CSV_ROWS_ALL} for lang in LANGS] + [
    {'lang': 'en', 'rows': []},
    {'lang': 'de', 'rows': []},
    {'lang': 'en', 'rows': [
        {'d': csv_doc(4, title='Sorting', customFields={'Zeta': 'z', 'alpha': 'a', 'Ärger': 'ä', 'Beta': 'b', 'Amount': '',
                                                         '_under': 'u', '10 digits': 'd'}), 'fileName': 'Sorting.pdf'},
        {'d': csv_doc(5, title='Second', customFields={'Beta': 'only beta', 'Émile': 'e'}, people=['Ö']), 'fileName': 'Second.pdf'},
    ]},
    {'lang': 'fr', 'rows': [
        {'d': csv_doc(6, title='Montant', customFields={'Amount': '12,30', 'Currency': 'EUR'}, notes='avec ; point-virgule'),
         'fileName': 'Montant.pdf'},
    ]},
    {'lang': 'zh-Hans', 'rows': [
        {'d': csv_doc(7, title='发票, 2024', notes='"引号"'), 'fileName': '发票, 2024.pdf'},
    ]},
]

DETAILS = [
    ('Tax 2024', 'For the advisor'),
    ('', ''),
    ('Quotes "and" back\\slash / slash', 'Ünïcödé 发票 Հաշիվ 😀'),
    ('Tab', 'ctrl \x01 char'),
]

MARKER_NAMES = [
    'INCOMPLETE - this export was not finished.txt', 'incomplete - this export was not finished.txt',
    'INCOMPLETE - THIS BACKUP WAS NOT FINISHED.TXT', 'INCOMPLETE - this export was not finished', 'index.csv',
    ' INCOMPLETE - this backup was not finished.txt',
]

JS = r"""async (input) => {
    const h = window.__DEBUG_exportFolderNames;
    const lone = /[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/g;
    const fix = (s) => ({ value: s.replace(lone, ''), lone: lone.test(s) });
    const out = { fileNames: [], folderNames: [], subfolderNames: [], unique: [], details: [], markerNames: [] };
    for(const d of input.fileDocs){
      const r = fix(h.exportFileName(d));
      out.fileNames.push({ doc: d, displayName: h.displayName(d), expected: r.value, pageHadLoneSurrogate: r.lone });
    }
    for(const title of input.folderTitles){
      const r = fix(h.sanitizeFolderName(title));
      out.folderNames.push({ title, expected: r.value, pageHadLoneSurrogate: r.lone });
    }
    for(const [title, c, suffix] of input.subfolders){
      const r = fix(h.exportSubfolderName(title, new Date(c[0], c[1] - 1, c[2], c[3], c[4], c[5]), suffix));
      out.subfolderNames.push({ title, now: c, suffix, expected: r.value, pageHadLoneSurrogate: r.lone });
    }
    for(const [names, existing] of input.unique){
      const dir = { getFileHandle: async (n) => { if(existing.includes(n)) return {}; throw new DOMException('no', 'NotFoundError'); } };
      const taken = new Set([h.EXPORT_DETAILS_FILE, 'index.csv', h.EXPORT_INCOMPLETE_FILE.toLowerCase(), h.BACKUP_INCOMPLETE_FILE.toLowerCase()]);
      const got = [];
      for(const n of names) got.push(await h.uniqueFileNameIn(dir, n, taken));
      out.unique.push({ names, existing, expected: got });
    }
    for(const [title, description] of input.details){
      out.details.push({ title, description, expected: JSON.stringify({ format: 1, title, description }, null, 2) });
    }
    for(const n of input.markerNames) out.markerNames.push({ name: n, isMarker: h.isIncompleteMarkerName(n) });
    out.reserved = [h.EXPORT_DETAILS_FILE, 'index.csv', h.EXPORT_INCOMPLETE_FILE, h.BACKUP_INCOMPLETE_FILE];
    out.markerFiles = { export: h.EXPORT_INCOMPLETE_FILE, backup: h.BACKUP_INCOMPLETE_FILE };
    out.markerTexts = { export: {}, backup: {} };
    out.csvHeaderWords = {};
    const keys = ['exportCsvFile', 'editTitleLabel', 'tableColDate', 'tableColImported', 'tableColCategory', 'editSubcategoryLabel',
                  'tableColType', 'tableColTags', 'tableColPeople', 'detailSectionNotes'];
    for(const lang of input.langs){
      out.markerTexts.export[lang] = h.tIn(lang, 'exportIncompleteMarkerText') + '\n';
      out.markerTexts.backup[lang] = h.tIn(lang, 'backupIncompleteMarkerText') + '\n';
      out.csvHeaderWords[lang] = keys.map(k => h.tIn(lang, k));
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
        out = await page.evaluate(JS, {
            'fileDocs': FILE_DOCS, 'folderTitles': FOLDER_TITLES, 'subfolders': SUBFOLDERS, 'unique': UNIQUE,
            'details': DETAILS, 'markerNames': MARKER_NAMES, 'langs': LANGS})
        # index.csv and the separator follow the UI language: switch it as a person would.
        out['csv'] = []
        out['separators'] = {}
        for lang in LANGS:
            await page.select_option('#lang-select', lang)
            out['separators'][lang] = await page.evaluate("() => window.__DEBUG_exportFolderNames.csvSeparator()")
            for case in CSV_CASES:
                if case['lang'] != lang:
                    continue
                csv = await page.evaluate("(rows) => window.__DEBUG_exportFolderNames.buildExportCsv(rows)", case['rows'])
                out['csv'].append({'lang': lang, 'rows': case['rows'], 'expected': csv})
        await browser.close()
        assert not errors, errors

        # A few checks that the page still behaves as the Mac app expects (a failure means: look before regenerating).
        names = {c['doc']['id']: c['expected'] for c in out['fileNames']}
        assert names[1] == '2022-09-21 Invoice.pdf', names[1]
        assert names[13] == 'document-13.pdf', names[13]
        assert names[19] == '2022-09-21 a-b-c-d-e-f-g-h-i-j.pdf', names[19]
        assert out['separators'] == {'en': ',', 'de': ';', 'es': ';', 'fr': ';', 'zh-Hans': ',', 'zh-Hant': ',', 'hy': ';'}, out['separators']
        assert all(c['expected'].startswith('﻿') and c['expected'].endswith('\r\n') for c in out['csv'])
        total = sum(len(out[k]) for k in ('fileNames', 'folderNames', 'subfolderNames', 'unique', 'details', 'markerNames', 'csv'))
        assert total >= 40, total

        version = re.search(r"const APP_VERSION = '([^']+)'", open(APP_PATH, encoding='utf-8').read()).group(1)
        out = {'generatedBy': 'Dossiary/tests/export_name_cases.py', 'pageVersion': version, **out}
        _os.makedirs(_os.path.dirname(OUT), exist_ok=True)
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=False)
            f.write('\n')
        print(f"ok: {total} cases -> {OUT}")

asyncio.run(main())
