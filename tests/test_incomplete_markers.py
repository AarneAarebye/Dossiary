import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, base64, json
from playwright.async_api import async_playwright

# Unfinished export and backup folders carry an "INCOMPLETE - ..." text file from
# the start of the run until it ends cleanly. Import labels such an export and asks
# before importing it; opening a library with the backup marker asks first; the
# marker is never a document. An encrypted PDF is reported as encrypted in the
# export result line (pdf-lib from the CDN, a qpdf AES-256 file with an empty
# user password).
EXPORT_MARKER = 'INCOMPLETE - this export was not finished.txt'
BACKUP_MARKER = 'INCOMPLETE - this backup was not finished.txt'
ENCRYPTED_PDF = base64.b64decode(
    "JVBERi0xLjcKJb/3ov4KMSAwIG9iago8PCAvRXh0ZW5zaW9ucyA8PCAvQURCRSA8PCAvQmFzZVZlcnNpb24gLzEuNyAvRXh0ZW5zaW9uTGV2ZWwgOCA+PiA+PiAvUGFnZXMgMiAwIFIgL1R5cGUgL0NhdGFsb2cgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL0NvdW50IDAgL0tpZHMgWyBdIC9UeXBlIC9QYWdlcyA+PgplbmRvYmoKMyAwIG9iago8PCAvQ0YgPDwgL1N0ZENGIDw8IC9BdXRoRXZlbnQgL0RvY09wZW4gL0NGTSAvQUVTVjMgL0xlbmd0aCAzMiA+PiA+PiAvRmlsdGVyIC9TdGFuZGFyZCAvTGVuZ3RoIDI1NiAvTyA8ODBiOTQ0MzVjODUzZjZhYWQ0OGQxYWE3NjEwN2E5NmJiNjI3NjYzMGUyNTliNGFlZmMyYmQwMWNkNDRjNmUzNWQ4ZTc3MTlkNjJhOGY5N2M0MDc0YjNiZWYyOWNhOWI3PiAvT0UgPGMyOGE3NGVkMzU3MDYxMzA4NmY0ODIxY2M1OTY2MWE2ZTg1NWZkMzlkYWQzYjcwOTRiMzEwMjk5MTczYWU5OWE+IC9QIC00IC9QZXJtcyA8NTQxMjhlNWYzZmYzNzkwZTQ2ZmUwMGUxYzZjNTk1MWY+IC9SIDYgL1N0bUYgL1N0ZENGIC9TdHJGIC9TdGRDRiAvVSA8ZWIxOGRmNjRkOGE4MDM2OGJkOWMwNTZlZGZmNDU0OGI0ODliOTNlZjM3OTIzMTViYmY2ZGRlMTBlNjA5YTlkNWRkN2VhNDY3Y2NlZDE4NWE0YmYwODM0YTJmYzk0NTFjPiAvVUUgPGNjMDAzMDA5YTk4ZGZiNTBhMTIzMDY3NDM1YTcxMWFiY2QzYTgzZWI3MWJkZTFlMTBlMDZhOGUyMzc5ZjBmNTY+IC9WIDUgPj4KZW5kb2JqCnhyZWYKMCA0CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAwMTMwIDAwMDAwIG4gCjAwMDAwMDAxODMgMDAwMDAgbiAKdHJhaWxlciA8PCAvUm9vdCAxIDAgUiAvU2l6ZSA0IC9JRCBbPGExMjE5ZTA1ZGY1ZDIzNDA5OWFiMmVhMzU4OGZmN2Q4Pjw0ODAzOWEwNzMwZmIyOGU1NjJkMzAyZDMyYzAwMzA4MD5dIC9FbmNyeXB0IDMgMCBSID4+CnN0YXJ0eHJlZgo3MzAKJSVFT0YK")
VALID_PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"

def doc(i, title, date="2026-01-10T00:00:00+00:00", ext='pdf'):
    return {
        "id": i, "title": title, "category": "Home", "subcategory": None, "document_type": "Invoice",
        "date": date, "import_date": "2026-03-01T00:00:00+00:00",
        "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": f"files/{i}_a.{ext}", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }

results = []
def check(label, ok, extra=''):
    results.append(bool(ok))
    print(f"{label}:", bool(ok), extra if not ok else '')

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        errors = []

        async def start(docs, files):
            # files: {file name in files/: bytes}
            page = await browser.new_page(viewport={'width': 1440, 'height': 900})
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" and 'ERR_FAILED' not in msg.text else None)
            page.dialogs = []
            page.accept_dialogs = True
            async def on_dialog(d):
                page.dialogs.append(d.message)
                await (d.accept() if page.accept_dialogs else d.dismiss())
            page.on("dialog", on_dialog)
            async def route_handler(route):
                url = route.request.url
                if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                    await route.fulfill(body="/* stubbed */", content_type='application/javascript')
                elif 'cdn.jsdelivr.net/gh/' in url:
                    await route.abort()  # the backup's own copy of dossiary.html: offline here
                else:
                    await route.continue_()
            await page.route('**/*', route_handler)
            await page.add_init_script(open('stub_studio2.js').read())
            await page.goto(f"file://{APP_PATH}")
            await page.wait_for_timeout(200)
            await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps({'documents': docs, 'tags': [], 'document_tags': []})}); window.__TEST_ROOT.name = 'MyLib';")
            await page.evaluate("""async (files) => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                for(const [n, b64] of Object.entries(files)){
                    const w = await (await dir.getFileHandle(n, { create: true })).createWritable();
                    await w.write(Uint8Array.from(atob(b64), c => c.charCodeAt(0))); await w.close();
                }
            }""", {n: base64.b64encode(b).decode() for n, b in files.items()})
            await page.click("#open-btn")
            await page.wait_for_timeout(500)
            return page

        async def export(page, ids, dest='window.__makeEmptyRoot()', hook_js=None):
            for i in ids:
                await page.check(f'.row-select-checkbox[data-id="{i}"]')
            await page.click('#bulk-more-btn'); await page.click('#bulk-export-btn')
            await page.wait_for_timeout(200)
            await page.fill('#export-title', 'Marker test')
            await page.evaluate("() => { if(!window.__DEST) window.__DEST = %s; window.__NEXT_PICKED_DIR = window.__DEST; }" % dest)
            if hook_js: await page.evaluate(hook_js)
            await page.click('#export-start-btn')
            await page.wait_for_function("() => /\\b(ok|err)\\b/.test(document.getElementById('export-status').className)", timeout=20000)

        LIST_DEST = """async () => {
            const out = {};
            for await (const [k, h] of window.__DEST.entries()){
                if(h.kind !== 'directory') continue;
                const files = {};
                for await (const [k2, f] of h.entries()) files[k2] = await (await f.getFile()).text();
                out[k] = files;
            }
            return out;
        }"""

        # A hook on the file handles' createWritable: on the n-th export .pdf, note whether the
        # export's subfolder holds the marker, and optionally click Stop.
        def write_hook(n, stop):
            return """async () => {
                const proto = Object.getPrototypeOf(await window.__makeEmptyRoot().getFileHandle('probe', { create: true }));
                const orig = proto.createWritable;
                window.__HOOK = { count: 0 };
                proto.createWritable = async function(){
                    const h = window.__HOOK;
                    if(/^2026-.*\\.pdf$/.test(this.name) && ++h.count === %d){
                        for await (const [k, d] of window.__DEST.entries()){
                            if(d.kind === 'directory'){ try{ await d.getFileHandle(%s); h.markerDuringRun = true; }catch(e){ h.markerDuringRun = false; } }
                        }
                        if(%s) document.getElementById('export-cancel-btn').click();
                    }
                    return orig.call(this);
                };
            }""" % (n, json.dumps(EXPORT_MARKER), 'true' if stop else 'false')

        docs = [doc(i, f"Doc {i}", f"2026-01-{i:02d}T00:00:00+00:00") for i in range(1, 7)]
        files = {f"{i}_a.pdf": VALID_PDF for i in range(1, 7)}

        # === 1. Export: the marker during a run, kept after Stop, removed after a clean finish ===
        page = await start(docs, files)
        await export(page, range(1, 7), hook_js=write_hook(2, True))
        hook = await page.evaluate("() => window.__HOOK")
        check("Export: the marker is in the subfolder while files are being copied", hook.get('markerDuringRun') is True, hook)
        top = await page.evaluate(LIST_DEST)
        sub = list(top.values())[0] if top else {}
        check("Export: after Stop the marker stays beside the copied files and index.csv",
              EXPORT_MARKER in sub and 'index.csv' in sub and len([k for k in sub if k.endswith('.pdf')]) == 2, list(sub))
        check("Export: the marker says the export was not finished and can be deleted",
              'not finished' in sub.get(EXPORT_MARKER, '') and 'delete this note' in sub.get(EXPORT_MARKER, ''), sub.get(EXPORT_MARKER))
        status = await page.inner_text('#export-status')
        check("Export: the Stop line says the folder is marked as incomplete",
              status.startswith(f'Stopped after 2 of 6 files. They are in “{list(top)[0]}”, which is marked as incomplete.'), status)
        await page.click('#export-cancel-btn'); await page.wait_for_timeout(150)
        await page.close()

        page = await start(docs, files)
        await export(page, range(1, 7), hook_js=write_hook(3, False))
        hook = await page.evaluate("() => window.__HOOK")
        top = await page.evaluate(LIST_DEST)
        sub = list(top.values())[0] if top else {}
        check("Export: the marker is there during a clean run too", hook.get('markerDuringRun') is True, hook)
        check("Export: a clean finish removes the marker", EXPORT_MARKER not in sub and len([k for k in sub if k.endswith('.pdf')]) == 6, list(sub))
        await page.close()

        # Stop before anything was copied: no folder, a plain line
        page = await start(docs, files)
        await export(page, range(1, 7), hook_js="""async () => {
            const proto = Object.getPrototypeOf(await window.__makeEmptyRoot().getFileHandle('probe', { create: true }));
            const orig = proto.getFile; let done = false;
            proto.getFile = async function(){
                // The 1st file fails to read while Stop is clicked: nothing gets copied.
                if(!done && /_a\\.pdf$/.test(this.name)){ done = true; document.getElementById('export-cancel-btn').click(); throw new Error('Read failed'); }
                return orig.call(this);
            };
        }""")
        top = await page.evaluate(LIST_DEST)
        status = await page.inner_text('#export-status')
        check("Export: Stop with nothing copied leaves no folder and says so",
              top == {} and status.startswith('Stopped before any file was copied.'), (top, status))
        await page.close()

        # The marker's name is reserved: a document named like it is numbered
        mdocs = [doc(1, "INCOMPLETE - this export was not finished", None, 'txt')]
        page = await start(mdocs, {"1_a.txt": b"hello"})
        await export(page, [1])
        sub = list((await page.evaluate(LIST_DEST)).values())[0]
        check("Export: a document named like the marker is numbered and the marker removed",
              'INCOMPLETE - this export was not finished (2).txt' in sub and EXPORT_MARKER not in sub, list(sub))
        await page.close()

        # === 2a. Import: a parent with a stopped and a complete export ===
        page = await start([], {})
        await page.evaluate("""async ([marker]) => {
            const put = async (dir, n, c) => { const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); };
            const parent = window.__makeEmptyRoot(); parent.name = 'Exports';
            const a = await parent.getDirectoryHandle('A stopped', {create: true});
            await put(a, 'index.csv', 'File,Title\\na1.pdf,A one\\n'); await put(a, 'a1.pdf', '%PDF-1.4 a1'); await put(a, marker, 'not finished');
            const b = await parent.getDirectoryHandle('B complete', {create: true});
            await put(b, 'index.csv', 'File,Title\\nb1.pdf,B one\\n'); await put(b, 'b1.pdf', '%PDF-1.4 b1');
            window.__PARENT = parent; window.__NEXT_PICKED_DIR = parent;
        }""", [EXPORT_MARKER])
        await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
        await page.click('#import-start-btn'); await page.wait_for_timeout(500)
        rows = await page.locator('.import-export-row').all_inner_texts()
        check("Import: the stopped export is labelled as not finished, the complete one not",
              len(rows) == 2 and 'Not finished: files may be missing' in rows[0] and 'Not finished' not in rows[1], rows)
        check("Import: the marker is not counted as a file", '1 file' in rows[0], rows)
        page.accept_dialogs = False
        await page.click('#import-run-btn'); await page.wait_for_timeout(300)
        check("Import: Import asks first, naming the unfinished export",
              len(page.dialogs) == 1 and 'A stopped' in page.dialogs[0] and 'Import them anyway?' in page.dialogs[0], page.dialogs)
        check("Import: declining keeps the list and imports nothing", await page.locator('#import-run-btn').count() == 1
              and await page.is_visible('#import-exports-list'))
        await page.uncheck('#import-export-check-0')
        page.dialogs.clear()
        await page.click('#import-run-btn'); await page.wait_for_timeout(1500)
        check("Import: with only the complete export ticked, no question", page.dialogs == [], page.dialogs)
        await page.close()

        page = await start([], {})
        await page.evaluate("""async ([marker]) => {
            const put = async (dir, n, c) => { const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); };
            const parent = window.__makeEmptyRoot(); parent.name = 'Exports';
            const a = await parent.getDirectoryHandle('A stopped', {create: true});
            await put(a, 'index.csv', 'File,Title\\na1.pdf,A one\\n'); await put(a, 'a1.pdf', '%PDF-1.4 a1'); await put(a, marker, 'not finished');
            window.__NEXT_PICKED_DIR = parent;
        }""", [EXPORT_MARKER])
        await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
        await page.click('#import-start-btn'); await page.wait_for_timeout(500)
        await page.click('#import-run-btn'); await page.wait_for_timeout(1500)
        summary = await page.inner_text('#import-summary')
        titles = await page.evaluate("() => JSON.parse(new TextDecoder().decode(window.__TEST_ROOT._children.get('library.sqlite')._bytes)).documents.map(d => d.title)")
        check("Import: accepting imports the export, the marker never a document",
              summary.startswith('Added: 1\n') and titles == ['A one'], (summary, titles))
        await page.close()

        # === 2b. Import: picking the stopped export folder itself ===
        for accept in (False, True):
            page = await start([], {})
            await page.evaluate("""async ([marker]) => {
                const put = async (dir, n, c) => { const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); };
                const a = window.__makeEmptyRoot(); a.name = 'A stopped';
                await put(a, 'index.csv', 'File,Title\\na1.pdf,A one\\n'); await put(a, 'a1.pdf', '%PDF-1.4 a1'); await put(a, marker, 'not finished');
                window.__NEXT_PICKED_DIR = a;
            }""", [EXPORT_MARKER])
            page.accept_dialogs = accept
            await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
            await page.click('#import-start-btn'); await page.wait_for_timeout(500)
            asked = len(page.dialogs) == 1 and page.dialogs[0] == 'This export was not finished and may be missing files. Import it anyway?'
            if not accept:
                check("Import (one folder): an unfinished export asks first; declining starts nothing",
                      asked and await page.locator('#import-run-btn').count() == 0 and await page.is_visible('#import-start-btn'), page.dialogs)
            else:
                await page.click('#import-run-btn'); await page.wait_for_timeout(1500)
                summary = await page.inner_text('#import-summary')
                check("Import (one folder): accepting imports its one file, the marker never a document",
                      asked and summary.startswith('Added: 1\n'), (page.dialogs, summary))
            await page.close()

        # === 3. Backup: the marker during the run, gone after a clean finish ===
        page = await start(docs[:2], {"1_a.pdf": VALID_PDF, "2_a.pdf": VALID_PDF})
        await page.evaluate("""async (marker) => {
            window.__BACKUP_PARENT = window.__makeEmptyRoot();
            const files = await window.__TEST_ROOT.getDirectoryHandle('files');
            const h = await files.getFileHandle('1_a.pdf');
            const orig = h.getFile.bind(h);
            h.getFile = async () => {
                for await (const [k, d] of window.__BACKUP_PARENT.entries()){
                    try{ await d.getFileHandle(marker); window.__BACKUP_MARKER_SEEN = true; }catch(e){ window.__BACKUP_MARKER_SEEN = false; }
                }
                return orig();
            };
            window.__NEXT_PICKED_DIR = window.__BACKUP_PARENT;
        }""", BACKUP_MARKER)
        await page.click('#tools-btn'); await page.click('#backup-btn'); await page.wait_for_timeout(200)
        await page.click('#backup-start-btn')
        await page.wait_for_function("() => /\\b(ok|err)\\b/.test(document.getElementById('backup-status').className)", timeout=20000)
        seen = await page.evaluate("() => window.__BACKUP_MARKER_SEEN")
        left = await page.evaluate("""async (marker) => { for await (const [k, d] of window.__BACKUP_PARENT.entries()){ try{ await d.getFileHandle(marker); return true; }catch(e){ return false; } } return null; }""", BACKUP_MARKER)
        check("Backup: the marker is in the backup folder while copying", seen is True, seen)
        check("Backup: a clean finish removes it", left is False, left)
        check("Backup: a clean finish is reported as done", 'ok' in await page.get_attribute('#backup-status', 'class')
              and (await page.inner_text('#backup-status')).startswith('Backed up '))
        await page.close()

        BACKUP_LEFT_JS = """async (marker) => { for await (const [k, d] of window.__BACKUP_PARENT.entries()){ try{ await d.getFileHandle(marker); return true; }catch(e){ return false; } } return null; }"""

        async def run_backup(page):
            await page.click('#tools-btn'); await page.click('#backup-btn'); await page.wait_for_timeout(200)
            await page.click('#backup-start-btn')
            await page.wait_for_function("() => /\\b(ok|err)\\b/.test(document.getElementById('backup-status').className)", timeout=20000)

        # === 3a. Backup with a file that can't be copied: the marker stays, no success claimed ===
        page = await start(docs[:2], {"1_a.pdf": VALID_PDF, "2_a.pdf": VALID_PDF})
        await page.evaluate("""async () => {
            window.__BACKUP_PARENT = window.__makeEmptyRoot();
            const files = await window.__TEST_ROOT.getDirectoryHandle('files');
            const h = await files.getFileHandle('2_a.pdf');
            h.getFile = async () => { throw new Error('Read failed'); };
            window.__NEXT_PICKED_DIR = window.__BACKUP_PARENT;
        }""")
        await run_backup(page)
        left = await page.evaluate(BACKUP_LEFT_JS, BACKUP_MARKER)
        status = await page.inner_text('#backup-status')
        cls = await page.get_attribute('#backup-status', 'class')
        check("Backup with a failed file: the marker stays", left is True, left)
        check("Backup with a failed file: red, says not complete and marked as incomplete, lists the failure",
              'err' in cls and status.startswith('Backup not complete: ') and 'The folder is marked as incomplete.' in status
              and 'Could not copy: 1.' in status and 'files/2_a.pdf' in status, (cls, status))
        check("Backup with a failed file: it doesn't count as the last backup",
              await page.inner_text('#backup-last') == 'No backup of this library yet.', await page.inner_text('#backup-last'))
        await page.close()

        # === 3c. Removing the marker after a clean finish fails: the status says so ===
        REMOVE_FAILS_JS = """async ([marker]) => {
            const proto = Object.getPrototypeOf(window.__makeEmptyRoot());
            const orig = proto.removeEntry;
            proto.removeEntry = async function(name, opts){
                if(name === marker) throw new DOMException('Permission denied', 'NotAllowedError');
                return orig.call(this, name, opts);
            };
        }"""
        page = await start(docs[:2], {"1_a.pdf": VALID_PDF, "2_a.pdf": VALID_PDF})
        await page.evaluate("() => { window.__BACKUP_PARENT = window.__makeEmptyRoot(); window.__NEXT_PICKED_DIR = window.__BACKUP_PARENT; }")
        await page.evaluate(REMOVE_FAILS_JS, [BACKUP_MARKER])
        await run_backup(page)
        status = await page.inner_text('#backup-status')
        check("Backup: a marker that can't be removed is named in the status",
              f'The note “{BACKUP_MARKER}” could not be removed; delete it by hand once you have checked the folder.' in status
              and 'err' in await page.get_attribute('#backup-status', 'class'), status)
        await page.close()

        page = await start(docs, files)
        await page.evaluate(REMOVE_FAILS_JS, [EXPORT_MARKER])
        await export(page, range(1, 7))
        status = await page.inner_text('#export-status')
        sub = list((await page.evaluate(LIST_DEST)).values())[0]
        check("Export: a marker that can't be removed stays and is named in the status",
              EXPORT_MARKER in sub and f'The note “{EXPORT_MARKER}” could not be removed; delete it by hand once you have checked the folder.' in status
              and 'err' in await page.get_attribute('#export-status', 'class'), status)
        await page.close()

        # === 3d. Both marker names are reserved in an export ===
        bdocs = [doc(1, "INCOMPLETE - this export was not finished", None, 'txt'), doc(2, "INCOMPLETE - this backup was not finished", None, 'txt')]
        page = await start(bdocs, {"1_a.txt": b"one", "2_a.txt": b"two"})
        await export(page, [1, 2])
        sub = list((await page.evaluate(LIST_DEST)).values())[0]
        check("Export: documents named like either marker are numbered",
              'INCOMPLETE - this export was not finished (2).txt' in sub and 'INCOMPLETE - this backup was not finished (2).txt' in sub
              and EXPORT_MARKER not in sub and BACKUP_MARKER not in sub, list(sub))
        await page.close()

        # === 3e. Importing a folder with the backup marker asks with backup wording ===
        page = await start([], {})
        await page.evaluate("""async ([marker]) => {
            const put = async (dir, n, c) => { const w = await (await dir.getFileHandle(n, {create: true})).createWritable(); await w.write(new TextEncoder().encode(c)); await w.close(); };
            const a = window.__makeEmptyRoot(); a.name = 'Some backup';
            await put(a, 'a1.pdf', '%PDF-1.4 a1'); await put(a, marker, 'not finished');
            window.__NEXT_PICKED_DIR = a;
        }""", [BACKUP_MARKER])
        page.accept_dialogs = False
        await page.click('#tools-btn'); await page.click('#import-folder-btn'); await page.wait_for_timeout(200)
        await page.click('#import-start-btn'); await page.wait_for_timeout(500)
        check("Import: a folder with the backup marker asks with backup wording",
              page.dialogs == ['This backup was not finished and may be missing files. Import it anyway?'], page.dialogs)
        await page.close()

        # === 3b. Opening a library that has the backup marker asks first ===
        for accept in (False, True):
            page = await browser.new_page(viewport={'width': 1440, 'height': 900})
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            asked = []
            async def on_dialog(d, accept=accept, asked=asked):
                asked.append(d.message); await (d.accept() if accept else d.dismiss())
            page.on("dialog", on_dialog)
            async def stub_route(route):
                url = route.request.url
                if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                    await route.fulfill(body="/* stubbed */", content_type='application/javascript')
                else:
                    await route.continue_()
            await page.route('**/*', stub_route)
            await page.add_init_script(open('stub_studio2.js').read())
            await page.goto(f"file://{APP_PATH}"); await page.wait_for_timeout(200)
            await page.evaluate(f"""async () => {{
                window.__TEST_ROOT = window.__makeSeededRoot({json.dumps({'documents': [doc(1, 'Backed up')], 'tags': [], 'document_tags': []})});
                window.__TEST_ROOT.name = 'MyLib backup 2026-11-14 1000';
                const w = await (await window.__TEST_ROOT.getFileHandle({json.dumps(BACKUP_MARKER)}, {{ create: true }})).createWritable();
                await w.write('not finished'); await w.close();
            }}""")
            await page.click('#open-btn'); await page.wait_for_timeout(600)
            q = asked[0] if asked else ''
            ok_q = q == 'This backup was not finished, so “MyLib backup 2026-11-14 1000” may be missing files. Open it anyway?'
            if not accept:
                check("Open: a library with the backup marker asks first; Cancel does not open it",
                      ok_q and not await page.is_visible('#table-wrap') and await page.is_visible('#open-btn'), (asked,))
            else:
                rows = await page.locator('.row-select-checkbox').count()
                check("Open: OK opens it, the marker is no document", ok_q and rows == 1, (asked, rows))
            await page.close()

        # === 4. Encrypted PDFs are reported as encrypted ===
        edocs = [doc(1, "Locked", "2026-01-01T00:00:00+00:00"), doc(2, "Broken", "2026-01-02T00:00:00+00:00"), doc(3, "Fine", "2026-01-03T00:00:00+00:00")]
        page = await start(edocs, {"1_a.pdf": ENCRYPTED_PDF, "2_a.pdf": b"not a pdf at all", "3_a.pdf": VALID_PDF})
        await export(page, [1, 2, 3])
        status = await page.inner_text('#export-status')
        check("Encrypted: the encrypted PDF is counted as encrypted", 'PDFs copied without details because they are encrypted: 1.' in status, status)
        check("Encrypted: the broken one keeps the old wording", 'PDFs copied without details because they could not be opened: 1.' in status, status)
        same = await page.evaluate("""async (b64) => {
            for await (const [k, d] of window.__DEST.entries()){
                const f = await (await d.getFileHandle('2026-01-01 Locked.pdf')).getFile();
                const a = new Uint8Array(await f.arrayBuffer()), b = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                return a.length === b.length && a.every((x, i) => x === b[i]);
            }
        }""", base64.b64encode(ENCRYPTED_PDF).decode())
        check("Encrypted: the encrypted file is copied unchanged", same)
        await page.close()

        check("No page errors", not errors, errors)
        await browser.close()
        print(f"{sum(results)}/{len(results)} checks passed")
        assert all(results)

asyncio.run(main())
