import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))

# Writes sidecar-cases.json for the Mac app (dossiary-osx, MacCore Sidecar): the page's own buildSidecarText,
# sidecarTextForDoc and sidecarBaseNameFromFilePath, evaluated on a set of documents. Not part of the suite.
# The functions are cut out of dossiary.html as they are (the page needs no test hook) and run in a blank page.
# The page writes custom and person fields in object insertion order (row order of the document's values); each case
# records that order (customOrder / personOrder, the dict's key order as written here, integer-like names are put first by
# JavaScript itself) because the Mac app's Document keeps the fields in unordered dictionaries.
# Usage: /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 export_sidecar_cases.py [output file]
# Default output: ../../dossiary-osx/MacCore/Tests/MacCoreTests/Fixtures/sidecar-cases.json

import json, re, sys, asyncio
from playwright.async_api import async_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else _os.path.abspath(_os.path.join(
    '..', '..', 'dossiary-osx', 'MacCore', 'Tests', 'MacCoreTests', 'Fixtures', 'sidecar-cases.json'))

html = open(APP_PATH, encoding='utf-8').read()

def cut(name):
    m = re.search(r'^  function %s\(.*?\n  }\n' % name, html, re.S | re.M)
    assert m, name
    return m.group(0)

SOURCE = cut('buildSidecarText') + cut('sidecarBaseNameFromFilePath') + cut('sidecarTextForDoc')
version = re.search(r"const APP_VERSION = '([^']+)'", html).group(1)

def doc(**kw):
    d = {'id': 1, 'title': None, 'category': None, 'subcategory': None, 'document_type': None, 'date': None,
         'import_date': None, 'notes': None, 'ocr_text': None, 'file_path': 'files/1_a.pdf',
         'customFields': {}, 'personFieldValues': {}, 'tags': [], 'splits': []}
    d.update(kw)
    d['people'] = d['personFieldValues'].get('People', [])  # as the page's loader fills it
    return d

DOCS = [
    doc(),
    doc(title='Invoice', category='Home', subcategory='Rent', document_type='Invoice', date='2026-03-01',
        import_date='2026-03-02T00:00:00+00:00', notes='Line 1\nLine 2', ocr_text='some ocr\ntext',
        customFields={'Amount': '12.5', 'Currency': 'EUR', 'Organization': 'Dr. Schröter', 'Payment method': 'Card',
                      'Plate': 'B-XY 123'},
        personFieldValues={'Author': ['Jana', 'Arne'], 'People': ['Jana', 'Arne']}, tags=['tax', 'private']),
    doc(title='Amount only', customFields={'Amount': '3'}),
    doc(title='Zero amount', customFields={'Amount': '0', 'Currency': 'USD'}),
    doc(title='Currency alone', customFields={'Currency': 'EUR'}),
    doc(title='Empty amount', customFields={'Amount': '', 'Currency': 'EUR'}),
    doc(title='Splits', customFields={'Amount': '100'}, splits=[
        {'category': 'Food', 'amount': 0.125, 'note': ''}, {'category': 'Home', 'amount': 2.675, 'note': 'rent (part)'},
        {'category': 'Car', 'amount': 1.005, 'note': ''}, {'category': 'Misc', 'amount': -0.125, 'note': 'refund'},
        {'category': 'Zero', 'amount': 0, 'note': ''}, {'category': None, 'amount': 12.5, 'note': ''},
        {'category': 'Tiny', 'amount': 1e-7, 'note': ''}, {'category': 'Big', 'amount': 123456789.987, 'note': ''},
        {'category': 'Whole', 'amount': 3, 'note': ''}, {'category': 'Neg', 'amount': -0.004, 'note': ''},
    ]),
    doc(title='Order', customFields={'Zeta': '1', 'Alpha': '2', '2024': 'y', 'Organization': 'o', '7': 's', 'Amount': '5',
                                     'Currency': 'EUR', 'Mid': 'm', 'Beta': 'b'},
        personFieldValues={'People': ['P'], 'Writer': ['W1'], 'Author': ['A1', 'A2'], '10': ['T'], '9': ['N']}),
    doc(title='No people', personFieldValues={'Author': []}, tags=[]),
    doc(title='Umlaute äöü "quote" \'apos\'', notes='  spaced  ', file_path=None),
]

BASE_PATHS = [None, '', 'files/1_a.pdf', 'files/Invoice 2026.final.pdf', 'files/noext', 'files/a.', 'other/x.pdf',
              'files/sub/x.pdf', 'files/files/x.pdf', 'x.tar.gz', 'files/dir.d/name', 'files/.hidden', 'files/ä ö.jpg']

JS = """([source, docs, paths]) => {
  const f = new Function(source + '; return {sidecarTextForDoc, sidecarBaseNameFromFilePath};')();
  return {texts: docs.map(d => f.sidecarTextForDoc(d)), bases: paths.map(p => f.sidecarBaseNameFromFilePath(p))};
}"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('about:blank')
        res = await page.evaluate(JS, [SOURCE, DOCS, BASE_PATHS])
        await browser.close()
    out = {'pageVersion': version,
           'docs': [{'doc': d, 'expected': t, 'customOrder': list(d['customFields']),
                     'personOrder': list(d['personFieldValues'])} for d, t in zip(DOCS, res['texts'])],
           'baseNames': [{'path': p, 'expected': b} for p, b in zip(BASE_PATHS, res['bases'])]}
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
        fh.write('\n')
    print('wrote', OUT, 'page', version)

asyncio.run(main())
