import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# A synced library deleted on another device (spec dossiary-ios
# docs/superpowers/specs/2026-10-25-delete-library-design.md): the state poll
# seeing `deleted` closes it with a notice, keeps unsaved changes aside or
# offers them for download, and a tab opened after the deletion turns local.
# The page's own Delete library (scenarios 1-7, 10-13) left in 1.71.0: Dossiary
# for Mac's Delete Library… replaces it. A fake fetch plays the service.
# config: { token, state (GET …/state answer), deletes (list of {status, body},
#           one per POST, the last repeating), hangDelete }
FAKE_SYNC = """
(config) => {
    window.__CALLS = [];
    window.__SYNC = config;
    const BASE = 'http://127.0.0.1:8769';
    const json = (status, body) => new Response(JSON.stringify(body), { status });
    window.fetch = async (url, opts = {}) => {
        const headers = opts.headers || {};
        window.__CALLS.push({ url, method: opts.method || 'GET', body: opts.body ? JSON.parse(opts.body) : null,
                              contentType: headers['Content-Type'] || null, at: Date.now() });
        const S = window.__SYNC;
        if(!url.startsWith(BASE + '/') || S.down) throw new TypeError('Failed to fetch');
        const path = url.slice(BASE.length);
        if(path === '/admin/health') return json(200, { service: 'dossiary-sync', version: '0.7.0', adminProtocol: 1, connected: headers.Authorization === `Bearer ${S.token}` });
        if(headers.Authorization !== `Bearer ${S.token}`) return json(401, { error: 'Unauthorized' });
        if(path === '/admin/libraries') return json(200, [{ id: 'lib-7f3a', name: 'Household', available: true }]);
        if(path === '/admin/devices') return json(200, []);
        const st = /^\\/admin\\/libraries\\/([^/]+)\\/state$/.exec(path);
        if(st && (opts.method || 'GET') === 'GET') return S.state ? json(200, S.state) : json(404, { error: 'Not found' });
        const del = /^\\/admin\\/libraries\\/([^/]+)\\/delete$/.exec(path);
        if(del && opts.method === 'POST'){
            if(headers['Content-Type'] !== 'application/json') return json(415, { error: 'JSON only' });
            if(S.hangDelete) await new Promise(r => { window.__releaseDelete = r; });
            const list = S.deletes || [];
            const answer = list.length > 1 ? list.shift() : (list[0] || { status: 404, body: { error: 'Not found' } });
            return json(answer.status, answer.body);
        }
        return json(404, { error: 'Not found' });
    };
}
"""

TOKEN_KEY = 'dossiary_sync_admin_token'
LIB_ID = 'lib-7f3a'
SEED = {
    "documents": [{
        "id": 1, "title": "Invoice", "category": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": "files/1_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }],
}
DELETED_200 = {"status": 200, "body": {"deleted": {"id": LIB_ID, "name": "Household", "deletedBy": "MacBook Pro", "deletedAt": "2026-10-25T10:00:00Z"}, "trashed": True}}
DELETE_URL = f'http://127.0.0.1:8769/admin/libraries/{LIB_ID}/delete'


async def open_app(p, sync, token='admin-tok', sync_file=True, lang=None, open_library=True, live=True):
    browser = await p.chromium.launch()
    context = await browser.new_context(viewport={'width': 1440, 'height': 900}, timezone_id='UTC', locale='en-US')
    page = await context.new_page()
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
    if lang:
        await page.add_init_script(f"localStorage.setItem('dossiary_lang', '{lang}')")
    await page.add_init_script(open('stub_studio2.js').read())
    await page.goto(f"file://{APP_PATH}")
    await page.wait_for_timeout(200)
    if token:
        await page.evaluate("([k, t]) => localStorage.setItem(k, t)", [TOKEN_KEY, token])
    await page.evaluate(FAKE_SYNC, sync)
    files = {}
    if sync_file:
        files['.dossiary-sync.json'] = json.dumps({"libraryId": LIB_ID, "hub": "https://pi.local:8443", "version": 3})
    await page.evaluate("""async ([seed, files]) => {
        const root = window.__makeSeededRoot(seed);
        root.name = 'Household.dossiary';
        window.__TEST_ROOT = root;
        for(const [path, text] of Object.entries(files)){
            const w = await (await root.getFileHandle(path, { create: true })).createWritable();
            await w.write(new TextEncoder().encode(text)); await w.close();
        }
    }""", [SEED, files])
    if open_library:
        await page.click('#open-btn')
        await page.wait_for_timeout(400)
        if live and sync_file and token:
            # One ordinary answer first: this tab has seen the library live (a tab that never
            # did treats a `deleted` answer as a copy opened afterwards -- scenario 20).
            await page.evaluate("window.__DEBUG_syncNow()")
            await page.wait_for_timeout(100)
    return browser, page, errors


async def admin_calls(page):
    return await page.evaluate("window.__CALLS.filter(c => c.url.startsWith('http://127.0.0.1:8769'))")


async def delete_calls(page):
    return [c for c in await admin_calls(page) if c['url'] == DELETE_URL]


async def recent_names(page):
    return await page.evaluate("""async () => {
        const req = indexedDB.open('dossiary-app-db', 1);
        const idb = await new Promise(r => { req.onsuccess = () => r(req.result); });
        const store = idb.transaction('recentLibraries', 'readonly').objectStore('recentLibraries');
        const all = await new Promise(r => { const q = store.getAll(); q.onsuccess = () => r(q.result); });
        return all.map(e => e.name);
    }""")


async def library_closed(page):
    return await page.locator('#empty-state').is_visible() and not await page.locator('#toolbar').is_visible()


async def text_of(page, sel):
    loc = page.locator(sel)
    return (await loc.inner_text()) if await loc.count() else ''


async def kept_aside_folders(page):
    return await page.evaluate("""() => {
        const k = window.__TEST_ROOT._children.get('.kept-aside');
        return k ? [...k._children.keys()] : [];
    }""")


async def main():
    async with async_playwright() as p:
        # === 8. Deleted on another Mac, nothing unsaved ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        await page.evaluate("window.__SYNC.state = { version: 3, lease: null, deleted: { deletedBy: 'iMac', deletedAt: '2026-10-25T10:00:00Z' } }")
        n = len(await admin_calls(page))
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(400)
        print("8 library closed:", await library_closed(page))
        notice = await text_of(page, '#sync-deleted-dialog')
        print("8 notice names the device:", "“Household” was deleted on iMac. Its folder is in this Mac's Trash." in notice and 'kept' not in notice, notice)
        print("8 status line too:", (await text_of(page, '#status')) == "“Household” was deleted on iMac. Its folder is in this Mac's Trash.")
        print("8 no .kept-aside copy:", await kept_aside_folders(page) == [])
        print("8 Recent entry gone:", 'Household.dossiary' not in await recent_names(page))
        after = [c for c in (await admin_calls(page))[n:] if not c['url'].endswith('/state')]
        print("8 no release or other call after:", after == [], after)
        await page.click('#sync-deleted-ok-btn')
        print("8 OK closes the notice:", await page.locator('#sync-deleted-dialog').count() == 0)
        print("8 JS errors:", errors == [], errors)
        await browser.close()

        # === 9. Deleted on another Mac, with a change not yet written ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Changed', 1])")
        print("9 memory holds an unwritten change:", (await page.evaluate("window.__DEBUG_syncState()"))['dirty'])
        await page.evaluate("window.__SYNC.state = { version: 3, lease: null, deleted: { deletedBy: 'iMac', deletedAt: '2026-10-25T10:00:00Z' } }")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(400)
        folders = await kept_aside_folders(page)
        print("9 a .kept-aside copy written first:", len(folders) == 1, folders)
        copy_title = await page.evaluate("""async (name) => {
            const f = window.__TEST_ROOT._children.get('.kept-aside')._children.get(name)._children.get('library.sqlite');
            return JSON.parse(await (await f.getFile()).text()).documents[0].title; }""", folders[0]) if folders else None
        print("9 the copy holds the change:", copy_title == 'Changed', copy_title)
        notice = await text_of(page, '#sync-deleted-dialog')
        print("9 notice mentions it:", f"What wasn't saved yet was kept in “.kept-aside/{folders[0] if folders else ''}” inside it." in notice, notice)
        print("9 library closed:", await library_closed(page))
        print("9 JS errors:", errors == [], errors)
        await browser.close()

        # === 14. A state answer without `deleted` (or a 404) never closes the library ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        for _ in range(3):
            await page.evaluate("window.__DEBUG_syncNow()")
        await page.evaluate("window.__SYNC.state = { version: 3, lease: null, deleted: null }")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.evaluate("window.__SYNC.state = null")   # the fake answers 404
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(300)
        print("14 still open after ordinary, deleted: null and 404 answers:", not await library_closed(page)
              and await page.locator('#sync-deleted-dialog').count() == 0)
        print("14 JS errors:", errors == [], errors)
        await browser.close()

        # === 15. Hostile device names shown as text ===
        evil = '<img src=x onerror=window.__PWNED=1>'
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        await page.evaluate("(e) => { window.__SYNC.state = { version: 3, lease: null, deleted: { deletedBy: e, deletedAt: '2026-10-25T10:00:00Z' } }; }", evil)
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(400)
        notice = await text_of(page, '#sync-deleted-dialog')
        print("15 hostile deletedBy as text:", evil in notice and await page.locator('#sync-deleted-dialog img').count() == 0
              and not await page.evaluate("!!window.__PWNED"), notice)
        print("15 JS errors:", errors == [], errors)
        await browser.close()

        # === 16. Late tab: deleted and already trashed, nothing unsaved → closed with the notice ===
        gone = {"deleted": {"deletedBy": "iMac", "deletedAt": "2026-10-25T10:00:00Z"}, "trashed": True}
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        await page.evaluate("(s) => { window.__SYNC.state = s; }", gone)
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(400)
        print("16 trashed answer without the other fields closes a clean tab:", await library_closed(page))
        print("16 with the notice:", "“Household” was deleted on iMac. Its folder is in this Mac's Trash." in await text_of(page, '#sync-deleted-dialog'))
        print("16 JS errors:", errors == [], errors)
        await browser.close()

        # === 17. Late tab with unsaved changes, already trashed: no kept-aside attempt, open read-only, download, close ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        await page.evaluate("""() => { const r = window.__TEST_ROOT, orig = r.getDirectoryHandle.bind(r); window.__KEPT_TRIES = 0;
            r.getDirectoryHandle = async (name, o) => { if(name === '.kept-aside') window.__KEPT_TRIES++; return orig(name, o); }; }""")
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Late change', 1])")
        disk_before = await page.evaluate("async () => await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()")
        await page.evaluate("(s) => { window.__SYNC.state = s; }", gone)
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(400)
        print("17 no kept-aside attempt:", await page.evaluate("window.__KEPT_TRIES") == 0)
        print("17 library stays open:", not await library_closed(page))
        text = await text_of(page, '#sync-deleted-text')
        print("17 the notice:", text == "“Household” was deleted on iMac. Changes made here since the last save weren't saved.", text)
        print("17 Download and Close offered:", (await text_of(page, '#sync-deleted-download-btn')) == 'Download unsaved changes'
              and (await text_of(page, '#sync-deleted-close-btn')) == 'Close library')
        await page.keyboard.press('Escape')
        print("17 Escape doesn't dismiss it:", await page.locator('#sync-deleted-dialog').count() == 1)
        async with page.expect_download() as info:
            await page.click('#sync-deleted-download-btn')
        dl = await info.value
        path = await dl.path()
        data = open(path, 'rb').read().decode('utf-8')
        print("17 the download is db.export():", data == await page.evaluate("window.__DEBUG_dbExportText()") and 'Late change' in data)
        import re as _re
        print("17 named '<name> unsaved <yyyy-mm-dd hhmm>.sqlite':", bool(_re.fullmatch(r'Household unsaved \d{4}-\d\d-\d\d \d{4}\.sqlite', dl.suggested_filename)), dl.suggested_filename)
        print("17 'Downloaded' note:", (await text_of(page, '#sync-deleted-downloaded')) == f'Downloaded “{dl.suggested_filename}”.')
        n = len(await admin_calls(page))
        saved = await page.evaluate("() => window.__DEBUG_persistDb()")
        editing = await page.evaluate("() => window.__DEBUG_ensureCurrentVersion()")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(300)
        disk_after = await page.evaluate("async () => await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()")
        print("17 saves and editing blocked, nothing written:", saved is False and editing is False and disk_after == disk_before)
        print("17 no admin calls while open read-only:", (await admin_calls(page))[n:] == [])
        await page.click('#sync-deleted-close-btn')
        await page.wait_for_timeout(300)
        print("17 Close closes the library:", await library_closed(page) and await page.locator('#sync-deleted-dialog').count() == 0)
        print("17 Recent entry gone:", 'Household.dossiary' not in await recent_names(page))
        print("17 no lease POST sent:", not any(c['url'].endswith('/lease') for c in await admin_calls(page)))
        print("17 JS errors:", errors == [], errors)
        await browser.close()

        # === 18. Not trashed, but the kept-aside copy fails: the same offer ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Unsaved', 1])")
        await page.evaluate("""() => { const r = window.__TEST_ROOT, orig = r.getDirectoryHandle.bind(r);
            r.getDirectoryHandle = async (name, o) => { if(name === '.kept-aside') throw new DOMException('The folder is read-only.', 'NoModificationAllowedError'); return orig(name, o); }; }""")
        await page.evaluate("window.__SYNC.state = { version: 3, lease: null, deleted: { deletedBy: 'iMac', deletedAt: '2026-10-25T10:00:00Z' } }")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(400)
        text = await text_of(page, '#sync-deleted-text')
        print("18 library stays open with the offer:", not await library_closed(page) and await page.locator('#sync-deleted-download-btn').count() == 1)
        print("18 the notice names the failed copy:", text.startswith("“Household” was deleted on iMac. Changes made here since the last save weren't saved. What wasn't saved yet couldn't be kept aside:"), text)
        print("18 JS errors:", errors == [], errors)
        await browser.close()

        # === 19. (Was: a lease call answering 404 library-deleted. No lease call is made any more; the state poll is
        # the only way a tab learns of a deletion.) A deleted answer that names no device; a save before the poll. ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        await page.evaluate("() => { window.__SYNC.state = { version: 3, lease: null, deleted: {} }; }")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(500)
        print("19 deleted with no device named closes a clean tab:", await library_closed(page))
        print("19 notice with the unknown device:", "“Household” was deleted on another Mac." in await text_of(page, '#sync-deleted-dialog'))
        print("19 JS errors:", errors == [], errors)
        await browser.close()
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Unsaved', 1])")
        await page.evaluate("(s) => { window.__SYNC.state = s; }", gone)
        await page.evaluate("() => window.__DEBUG_ensureCurrentVersion()")   # starting to edit asks the hub nothing
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(500)
        print("19 dirty, then a trashed state: open read-only with the offer:", not await library_closed(page)
              and "was deleted on iMac" in await text_of(page, '#sync-deleted-text'))
        print("19 JS errors (dirty):", errors == [], errors)
        await browser.close()

        # A save before the poll learns of the deletion goes to disk (into the folder on its way to the Trash);
        # the poll then finds nothing unsaved and closes the tab -- trashed or not.
        for trashed in (False, True):
            browser, page, errors = await open_app(p, {"token": "admin-tok", "state": {"version": 3, "lease": None}})
            await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Saved late', 1])")
            state = dict(gone) if trashed else {"version": 3, "lease": None, "deleted": {"deletedBy": "iMac", "deletedAt": "2026-10-25T10:00:00Z"}}
            await page.evaluate("(s) => { window.__SYNC.state = s; }", state)
            n = len(await admin_calls(page))
            saved = await page.evaluate("() => window.__DEBUG_persistDb()")
            disk = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).documents[0].title")
            print(f"19 trashed={trashed}: the save is written, with no admin call:", saved is True and disk == 'Saved late' and (await admin_calls(page))[n:] == [], saved, disk)
            await page.evaluate("window.__DEBUG_syncNow()")
            await page.wait_for_timeout(500)
            print(f"19 trashed={trashed}: ...then the poll closes it with the notice, nothing kept aside:", await library_closed(page)
                  and await page.locator('#sync-deleted-dialog').count() == 1 and await kept_aside_folders(page) == [])
            print(f"19 JS errors (save, trashed={trashed}):", errors == [], errors)
            await browser.close()

        # === 20. Opened after deletion (a folder taken back out of the Trash): a local library ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": dict(gone)}, live=False)
        await page.evaluate("window.__SYNC.state.deleted.deletedAt = '2026-10-20T10:00:00Z'")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(300)
        print("20 stays open, no notice:", not await library_closed(page) and await page.locator('#sync-deleted-dialog').count() == 0)
        status = await text_of(page, '#status')
        print("20 status line names the date:", status == "“Household” was deleted from your devices on Oct 20, 2026; this copy is now a local library that isn't synced.", status)
        print("20 Recent entry kept:", 'Household.dossiary' in await recent_names(page))
        n = len(await admin_calls(page))
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Local now', 1])")
        editing = await page.evaluate("() => window.__DEBUG_ensureCurrentVersion()")
        saved = await page.evaluate("() => window.__DEBUG_persistDb()")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(300)
        disk = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).documents[0].title")
        print("20 editing allowed and a save writes to disk:", editing is True and saved is not False and disk == 'Local now', editing, saved, disk)
        print("20 no admin calls after the first state answer:", (await admin_calls(page))[n:] == [], (await admin_calls(page))[n:])
        print("20 .dossiary-sync.json left alone:", await page.evaluate("window.__TEST_ROOT._children.has('.dossiary-sync.json')"))
        await page.click('#reload-btn'); await page.wait_for_timeout(300)
        await page.click('.recent-lib-target'); await page.wait_for_timeout(400)
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(200)
        print("20 reopened this session: still local, no admin calls:", not await library_closed(page) and (await admin_calls(page))[n:] == [])
        print("20 JS errors:", errors == [], errors)
        await browser.close()

        # === 21. Opened after deletion with a change made before the first answer (deleted and trashed): local,
        # and the change is saved. (Was: a lease 404 as the first answer. 21b, a lease 404 then a trashed state, is
        # now scenario 20.) ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": dict(gone)}, live=False)
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Local edit', 1])")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(300)   # the state is asked, then the decision: local
        saved = await page.evaluate("() => window.__DEBUG_persistDb()")
        await page.wait_for_timeout(300)
        disk = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).documents[0].title")
        print("21 stays open as a local library, the save written:", not await library_closed(page) and disk == 'Local edit'
              and await page.locator('#sync-deleted-dialog').count() == 0, disk)
        print("21 status line names it local:", "this copy is now a local library that isn't synced." in await text_of(page, '#status'))
        print("21 Recent entry kept:", 'Household.dossiary' in await recent_names(page))
        print("21 no base marker written for a local library:", not await page.evaluate("window.__TEST_ROOT._children.has('.dossiary-base.json')"))
        print("21 JS errors:", errors == [], errors)
        await browser.close()

        # === 22. First answer: deleted but not trashed yet (grace period) → the normal deleted path ===
        grace = {"version": 3, "lease": None, "deleted": {"deletedBy": "iMac", "deletedAt": "2026-10-25T10:00:00Z"}}
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": dict(grace)}, live=False)
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(400)
        print("22 clean: closed with the notice:", await library_closed(page)
              and "“Household” was deleted on iMac." in await text_of(page, '#sync-deleted-dialog'))
        print("22 clean: Recent entry gone:", 'Household.dossiary' not in await recent_names(page))
        print("22 JS errors (clean):", errors == [], errors)
        await browser.close()
        browser, page, errors = await open_app(p, {"token": "admin-tok", "state": dict(grace)}, live=False)
        await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Grace change', 1])")
        await page.evaluate("window.__DEBUG_syncNow()")
        await page.wait_for_timeout(400)
        folders = await kept_aside_folders(page)
        copy_title = await page.evaluate("""async (name) => {
            const f = window.__TEST_ROOT._children.get('.kept-aside')._children.get(name)._children.get('library.sqlite');
            return JSON.parse(await (await f.getFile()).text()).documents[0].title; }""", folders[0]) if folders else None
        print("22 dirty: kept aside, then closed:", copy_title == 'Grace change' and await library_closed(page), folders, copy_title)
        print("22 JS errors (dirty):", errors == [], errors)
        await browser.close()
        # (Was also: a lease 404 first, then the grace state. Without the lease that is the clean case above.)

asyncio.run(main())
