import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))

# Writes export-library-cases.json and three fixture libraries (export-library-a|b|c/library.sqlite) for the Mac app
# (dossiary-osx, MacCore LibraryDatabaseBuilder): for each fixture library and several (mode, ids) cases, every table of the
# database the page's own buildExportLibraryDb produces (window.__DEBUG_buildExportLibrary). Not part of the suite.
# Regenerate after a change to the page's export-as-library rules. Usage:
#   /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 export_library_cases.py [output folder]
# Default output folder: ../../dossiary-osx/MacCore/Tests/MacCoreTests/Fixtures
#
# The page under test runs on the test suite's fake database (stub_studio2.js: JSON tables). The source of each case is the
# library file the page itself wrote after opening the seeded library (so the page's migrations are included), and that same
# file is converted to a real SQLite database for the Mac tests. Limits of the fake, which the Mac tests take as they are:
# it never throws for a missing column or table, so the page copies `uid` / `folder_id` as NULL where a real older database
# would skip them (same resulting NULLs in a new library); and its fresh database starts with no seeded rows.
# Library (b) is the "older" one: its sqlite has no uid columns, no collections.folder_id and no collection_folders table.

import json, re, sqlite3, sys, asyncio
from playwright.async_api import async_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else _os.path.abspath(_os.path.join(
    '..', '..', 'dossiary-osx', 'MacCore', 'Tests', 'MacCoreTests', 'Fixtures'))
TEMPLATE = _os.path.join(OUT, 'schema-empty-template', 'library.sqlite')  # the current schema (same as the page's SCHEMA)

DOC_COLUMNS = ['id', 'title', 'category', 'subcategory', 'document_type', 'payment_method', 'amount', 'currency', 'date',
               'import_date', 'notes', 'ocr_text', 'ocr_language', 'file_path', 'original_file_path', 'created_at', 'source',
               'source_legacy_id', 'thumbnail_path', 'archived', 'needs_review', 'deleted', 'searchable_pdf_built',
               'file_hash', 'has_text_layer', 'text_checked', 'thumbnail_hd']

def doc(i, title, doc_type, path, original=None, thumb=None, uid=None, **extra):
    d = {c: None for c in DOC_COLUMNS}
    d.update({
        'id': i, 'title': title, 'category': 'Home', 'document_type': doc_type, 'date': '2026-03-0%d' % i,
        'import_date': '2026-03-0%dT00:00:00+00:00' % i, 'ocr_text': 'text %d' % i, 'file_path': path,
        'original_file_path': original, 'thumbnail_path': thumb, 'created_at': '2026-03-01T00:00:00+00:00',
        'source': 'captured', 'archived': 0, 'needs_review': 0, 'deleted': 0, 'searchable_pdf_built': 1,
        'file_hash': 'hash%d' % i, 'has_text_layer': 1, 'text_checked': 1, 'thumbnail_hd': 0, 'amount': None,
    })
    d.update(extra)
    if uid: d['uid'] = uid
    return d

def with_uids(rows, prefix):
    return [dict(r, uid='%s-%s' % (prefix, i)) for i, r in enumerate(rows, 1)]

SETTINGS_COMMON = [
    {'key': 'view_mode', 'value': 'list'}, {'key': 'scan_auto_ocr', 'value': '0'},  # what the fake adds itself, explicit here
    {'key': 'default_currency', 'value': 'EUR'},
    {'key': 'visible_columns', 'value': '["title","date","field:10"]'},
    {'key': 'sort_key', 'value': 'date'},
    {'key': 'last_backup_at', 'value': '2026-01-01T00:00:00.000Z'},
    {'key': 'scan_bridge_url', 'value': 'http://localhost:9999'},
    {'key': 'scan_last_settings', 'value': '{"dpi":300}'},
]

FIELDS = [
    {'id': 1, 'name': 'People', 'type': 'person', 'show_as_column': 0, 'autocomplete': 0},
    {'id': 2, 'name': 'Amount', 'type': 'number', 'show_as_column': 0, 'autocomplete': 0},
    {'id': 3, 'name': 'Currency', 'type': 'text', 'show_as_column': 1, 'autocomplete': 1},
    {'id': 4, 'name': 'Payment method', 'type': 'text', 'show_as_column': 1, 'autocomplete': 1},
    {'id': 5, 'name': 'Reminder', 'type': 'reminder', 'show_as_column': 0, 'autocomplete': 0},
    {'id': 10, 'name': 'Organization', 'type': 'text', 'show_as_column': 1, 'autocomplete': 1},
    {'id': 11, 'name': 'Author', 'type': 'person', 'show_as_column': 0, 'autocomplete': 0},
    {'id': 12, 'name': 'Unused', 'type': 'text', 'show_as_column': 0, 'autocomplete': 1},
    {'id': 13, 'name': 'Never', 'type': 'text', 'show_as_column': 0, 'autocomplete': 1},
    {'id': 14, 'name': 'Due', 'type': 'reminder', 'show_as_column': 0, 'autocomplete': 0},
]

def seed_a():
    s = {
        'documents': with_uids([
            doc(1, 'Invoice', 'Invoice', 'files/1_a.pdf', 'files/1_a/a.pdf', 'thumbnails/1.jpg', amount=12.5, currency='EUR', notes='n1'),
            doc(2, 'Letter', 'Letter', 'files/2_b.pdf', notes='Umlaute äöü "quote" \'apos\''),
            doc(3, 'Other', 'Other', 'files/3_c.pdf'),
            doc(4, 'Receipt', 'Invoice', 'files/4_d.pdf', amount=3.0, payment_method='Card'),
        ], 'doc'),
        'tags': with_uids([{'id': 1, 'name': 'tax'}, {'id': 2, 'name': 'private'}, {'id': 3, 'name': 'unused'}], 'tag'),
        'document_tags': [{'document_id': 1, 'tag_id': 1}, {'document_id': 3, 'tag_id': 2}, {'document_id': 4, 'tag_id': 1}],
        'people': with_uids([{'id': 1, 'name': 'Jana'}, {'id': 2, 'name': 'Arne'}, {'id': 3, 'name': 'Zed'}], 'person'),
        'document_people': [{'document_id': 2, 'person_id': 1}, {'document_id': 3, 'person_id': 3}],
        'fields': with_uids(FIELDS, 'field'),
        'document_field_values': [
            {'document_id': 1, 'field_id': 10, 'value': 'Stadtwerke'}, {'document_id': 1, 'field_id': 2, 'value': '12.50'},
            {'document_id': 1, 'field_id': 3, 'value': 'EUR'}, {'document_id': 3, 'field_id': 12, 'value': 'secret'},
            {'document_id': 4, 'field_id': 10, 'value': 'Café ☕'}],
        'document_field_people': [
            {'document_id': 1, 'field_id': 1, 'person_id': 1}, {'document_id': 2, 'field_id': 11, 'person_id': 2},
            {'document_id': 3, 'field_id': 1, 'person_id': 3}],
        'document_type_fields': [
            {'document_type': 'Invoice', 'field_name': 'Organization', 'position': 0},
            {'document_type': 'Invoice', 'field_name': 'Amount', 'position': 1},
            {'document_type': 'Invoice', 'field_name': 'Unused', 'position': 2},
            {'document_type': 'Letter', 'field_name': 'Author', 'position': 0},
            {'document_type': 'Other', 'field_name': 'Unused', 'position': 0},
            {'document_type': 'Never used type', 'field_name': 'Never', 'position': 0}],
        'field_descriptions': [
            {'field_name': 'Organization', 'description': 'Who sent it'}, {'field_name': 'Unused', 'description': 'x'},
            {'field_name': 'Category', 'description': 'cat hint'}, {'field_name': 'Tags', 'description': 'tag hint'},
            {'field_name': 'Never', 'description': 'nope'}],
        'document_splits': with_uids([
            {'document_id': 1, 'position': 0, 'category': 'Home', 'amount': '5.00', 'note': ''},
            {'document_id': 1, 'position': 1, 'category': 'Car', 'amount': '7.50', 'note': 'half'},
            {'document_id': 3, 'position': 0, 'category': 'Home', 'amount': '1.00', 'note': None}], 'split'),
        'reminder_snoozes': with_uids([
            {'document_id': 1, 'field_id': 5, 'snoozed_until': '2026-12-01', 'dismissed': 0},
            {'document_id': 3, 'field_id': 14, 'snoozed_until': '2026-12-02', 'dismissed': 1}], 'snooze'),
        'collection_folders': with_uids([{'id': 1, 'name': 'Folder A'}, {'id': 2, 'name': 'Folder B'}, {'id': 3, 'name': 'Empty folder'}], 'folder'),
        'collections': with_uids([
            {'id': 1, 'name': 'Taxes', 'kind': 'manual', 'criteria': None, 'folder_id': 1},
            {'id': 2, 'name': 'Private', 'kind': 'manual', 'criteria': None, 'folder_id': None},
            {'id': 3, 'name': 'Smart', 'kind': 'smart', 'criteria': json.dumps({'match': 'all', 'rules': []}), 'folder_id': 2},
            {'id': 4, 'name': 'Other folder', 'kind': 'manual', 'criteria': None, 'folder_id': 2}], 'coll'),
        'collection_documents': [
            {'collection_id': 1, 'document_id': 1}, {'collection_id': 1, 'document_id': 3},
            {'collection_id': 2, 'document_id': 3}, {'collection_id': 4, 'document_id': 2}],
        'settings': SETTINGS_COMMON + [{'key': 'stable_uids_migrated', 'value': '1'}],
        'not_duplicate_groups': [{'group_key': 'exact:1,3'}],
        'ocr_jobs': [{'document_id': 2, 'helper_url': 'http://localhost:8766', 'job_id': 'j', 'file_hash': 'hash2',
                      'created_at': '2026-03-01T00:00:00Z', 'ocr_language': None, 'requested_by': 'edit'}],
    }
    return s

def strip_uid(rows):
    return [{k: v for k, v in r.items() if k != 'uid'} for r in rows]

def seed_b():
    # An older library: no folders, no folder_id; its sqlite file has no uid columns (see nulled_uids).
    a = seed_a()
    s = {k: (strip_uid(v) if isinstance(v, list) else v) for k, v in a.items()}
    s['collection_folders'] = []
    s['collections'] = [{k: v for k, v in c.items() if k != 'folder_id'} for c in s['collections']]
    s['documents'] = s['documents'][:3]
    s['document_tags'] = [r for r in s['document_tags'] if r['document_id'] <= 3]
    s['document_field_values'] = [r for r in s['document_field_values'] if r['document_id'] <= 3]
    s['collection_documents'] = [r for r in s['collection_documents'] if r['document_id'] <= 3]
    return s

def seed_c():
    # Flags set on documents; no migration markers, so the page migrates (uids, built-in fields) when it opens.
    docs = [
        doc(1, 'Kept', 'Invoice', 'files/1_k.pdf', amount=1.25),
        doc(2, 'In the Waste bin', 'Invoice', 'files/2_w.pdf', deleted=1),
        doc(3, 'Needs review', 'Letter', 'files/3_r.pdf', needs_review=1, searchable_pdf_built=0, has_text_layer=0, text_checked=0),
        doc(4, 'Archived and trashed', None, None, archived=1, deleted=1, needs_review=1, thumbnail_hd=1),
    ]
    return {
        'documents': docs,
        'tags': [{'id': 1, 'name': 'x'}], 'document_tags': [{'document_id': 2, 'tag_id': 1}],
        'people': [{'id': 1, 'name': 'Ann'}],
        'fields': [{'id': 7, 'name': 'Note', 'type': 'text', 'show_as_column': 0, 'autocomplete': 1}],
        'document_field_values': [{'document_id': 2, 'field_id': 7, 'value': 'kept in the bin'}],
        'document_type_fields': [{'document_type': 'Invoice', 'field_name': 'Note', 'position': 0}],
        'collections': [{'id': 1, 'name': 'Bin things', 'kind': 'manual', 'criteria': None, 'folder_id': None}],
        'collection_documents': [{'collection_id': 1, 'document_id': 2}, {'collection_id': 1, 'document_id': 4}],
        'settings': SETTINGS_COMMON,
    }

LIBS = {
    'a': {'seed': seed_a, 'cases': [
        ('used', [1, 2, 3, 4]), ('used', [1, 2]), ('used', [3]), ('used', [4]), ('used', []),
        ('all', [1, 2, 3, 4]), ('all', [1, 2]), ('all', [4]),
    ]},
    'b': {'seed': seed_b, 'cases': [('used', [1, 2, 3]), ('used', [2]), ('all', [1, 2, 3]), ('all', [3])]},
    'c': {'seed': seed_c, 'cases': [('used', [1, 2, 3, 4]), ('used', [2]), ('used', [3, 4]), ('all', [1, 2, 3, 4]), ('all', [4])]},
}

TABLES = ['documents', 'tags', 'document_tags', 'people', 'document_people', 'document_field_people', 'settings',
          'document_type_fields', 'fields', 'document_field_values', 'collections', 'collection_documents',
          'field_descriptions', 'reminder_snoozes', 'not_duplicate_groups', 'ocr_jobs', 'collection_folders', 'document_splits']

BUILD_JS = "([ids, mode]) => JSON.parse(new TextDecoder().decode(window.__DEBUG_buildExportLibrary(ids, mode)))"
SOURCE_JS = "() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes))"

def write_sqlite(path, tables, older):
    """The page's library file (JSON tables) as a real SQLite database with the current schema (or the older one)."""
    if _os.path.exists(path): _os.remove(path)
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    src = sqlite3.connect(TEMPLATE)
    for (sql,) in src.execute("SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"):
        con.execute(sql)
    src.close()
    if older:
        for t in ['documents', 'tags', 'people', 'fields', 'collections', 'document_splits', 'collection_folders', 'reminder_snoozes']:
            if t == 'collection_folders':
                con.execute('DROP TABLE collection_folders')
            else:
                con.execute('ALTER TABLE %s DROP COLUMN uid' % t)
        con.execute('ALTER TABLE collections DROP COLUMN folder_id')
    for t in TABLES:
        if older and t == 'collection_folders': continue
        cols = [r[1] for r in con.execute('PRAGMA table_info(%s)' % t)]
        for row in tables.get(t, []):
            if older: row = {k: v for k, v in row.items() if k not in ('uid', 'folder_id')}  # the older schema has neither
            unknown = set(row) - set(cols)
            assert not unknown, (t, unknown)
            ks = [c for c in cols if c in row]
            con.execute('INSERT INTO %s (%s) VALUES (%s)' % (t, ', '.join(ks), ', '.join('?' * len(ks))), [row[c] for c in ks])
    con.execute('PRAGMA journal_mode=DELETE')
    con.commit(); con.close()

def nulled_uids(rows):
    # The page's migrations give every row a uid on open (even with the marker set), and the fake database cannot tell that
    # an older sqlite has no uid column. On a real older database the page's withUid() skips the column, so the new
    # library's rows carry NULL: that is what the Mac builder must produce, so library (b)'s golden says so.
    return [dict(r, uid=None) if 'uid' in r else r for r in rows]

def canon(rows):
    return sorted(rows, key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))

async def main():
    out_cases = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for lib, spec in LIBS.items():
            seed = spec['seed']()
            page = await browser.new_page(viewport={'width': 1440, 'height': 900})
            errors = []
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            async def route_handler(route):
                url = route.request.url
                if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                    await route.fulfill(body='/* stubbed */', content_type='application/javascript')
                else:
                    await route.continue_()
            await page.route('**/*', route_handler)
            await page.add_init_script(open('stub_studio2.js').read())
            await page.goto('file://' + APP_PATH)
            await page.wait_for_timeout(200)
            await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed)}); window.__TEST_ROOT.name = 'Lib {lib}';")
            await page.click('#open-btn')
            await page.wait_for_timeout(600)
            source = await page.evaluate(SOURCE_JS)  # the page's own file after opening (migrations included)
            assert len(source['documents']) == len(seed['documents']), 'the library did not open'
            write_sqlite(_os.path.join(OUT, 'export-library-' + lib, 'library.sqlite'), source, older=(lib == 'b'))
            for mode, ids in spec['cases']:
                built = await page.evaluate(BUILD_JS, [ids, mode])
                assert set(built) == set(TABLES), set(built) ^ set(TABLES)
                out_cases['%s-%s-%s' % (lib, mode, '+'.join(map(str, ids)) or 'none')] = {
                    'library': 'export-library-' + lib, 'mode': mode, 'ids': ids,
                    'tables': {t: canon(nulled_uids(built[t]) if lib == 'b' else built[t]) for t in TABLES}}
            assert not errors, errors
            await page.close()
        await browser.close()

    # Sanity checks that the page still behaves as the Mac tests assume.
    a = out_cases['a-used-1+2']['tables']
    assert sorted(d['id'] for d in a['documents']) == [1, 2]
    assert a['not_duplicate_groups'] == [] and a['ocr_jobs'] == []
    assert not {r['key'] for r in a['settings']} & {'last_backup_at', 'scan_bridge_url', 'scan_last_settings'}
    assert sorted(r['id'] for r in out_cases['a-all-1+2']['tables']['collections']) == [1, 3, 4]

    version = re.search(r"const APP_VERSION = '([^']+)'", open(APP_PATH, encoding='utf-8').read()).group(1)
    doc_out = {'generatedBy': 'Dossiary/tests/export_library_cases.py', 'pageVersion': version, 'cases': out_cases}
    with open(_os.path.join(OUT, 'export-library-cases.json'), 'w', encoding='utf-8') as f:
        json.dump(doc_out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write('\n')
    print('ok: %d cases -> %s' % (len(out_cases), OUT))

asyncio.run(main())
