import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Share this library (spec dossiary-ios docs/superpowers/specs/2026-10-25-share-library-design.md):
# Tools › "Share this library…" shares the open, unsynced library through
# Dossiary Sync -- in place when it's directly in this Mac's libraries folder,
# otherwise as a copy made there first -- and iPhone & other devices… gets a
# library on the Pi this Mac doesn't have ("Get it"). A fake fetch plays the
# Mac service; the libraries folder is a fake directory (window.__LIB_ROOT).
# config: { token, devices, shares (list of {status, body}, one per POST, the
#           last repeating; default 200), uploading, available (list, or
#           'missing' for 404), gets (list of answers), hangGet }
ROOT_PATH = '/Users/test/Documents Local/Dossiary'
FAKE_SYNC = """
(config) => {
    window.__CALLS = [];
    window.__SYNC = config;
    window.__PROBES = [];
    const BASE = 'http://127.0.0.1:8769';
    const ROOT = '%s';
    const json = (status, body) => new Response(JSON.stringify(body), { status });
    const libRoot = () => window.__LIB_ROOT;
    window.fetch = async (url, opts = {}) => {
        const headers = opts.headers || {};
        const method = opts.method || 'GET';
        window.__CALLS.push({ url, method, body: opts.body ? JSON.parse(opts.body) : null, contentType: headers['Content-Type'] || null });
        const S = window.__SYNC;
        if(!url.startsWith(BASE + '/') || S.down) throw new TypeError('Failed to fetch');
        const path = url.slice(BASE.length);
        if(path === '/admin/health') return json(200, { service: 'dossiary-sync', version: '0.8.0', adminProtocol: 1, connected: headers.Authorization === `Bearer ${S.token}` });
        if(headers.Authorization !== `Bearer ${S.token}`) return json(401, { error: 'Unauthorized' });
        if(method === 'POST' && headers['Content-Type'] !== 'application/json') return json(415, { error: 'JSON only' });
        if(path === '/admin/devices') return json(200, S.devices || []);
        if(path === '/admin/libraries') return json(200, S.libraries || []);
        if(path === '/admin/libraries/available'){
            if(S.available === 'missing') return json(404, { error: 'Not found' });
            return json(200, S.available || []);
        }
        if(path === '/admin/libraries-root/check' && method === 'POST'){
            const probe = JSON.parse(opts.body).probe;
            if(!/^\\.dossiary-probe-[A-Za-z0-9-]{1,64}$/.test(probe)) return json(400, { error: 'bad-probe' });
            const where = [];
            for(const [label, dir] of [['root', libRoot()], ['wrong', window.__WRONG_DIR]]){
                const h = dir && dir._children.get(probe);
                if(h && h.kind === 'file') where.push(label);
            }
            window.__PROBES.push({ probe, where });
            return json(200, { ok: where.includes('root'), root: ROOT });
        }
        if(path === '/admin/libraries/share' && method === 'POST'){
            const body = JSON.parse(opts.body);
            const dir = libRoot()._children.get(body.folder);
            window.__SHARED_DB = dir && dir._children.get('library.sqlite') ? new TextDecoder().decode(dir._children.get('library.sqlite')._bytes) : null;
            const list = S.shares || [];
            const answer = list.length > 1 ? list.shift() : (list[0] || null);
            // As the Mac does: the sync file, so reopening makes it a synced library.
            const writeSync = async () => {
                const w = await (await dir.getFileHandle('.dossiary-sync.json', { create: true })).createWritable();
                await w.write(new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-new', hub: 'https://pi.local:8443', version: 0 })));
                await w.close();
            };
            // hang: wait for window.__releaseShare() (an abort of the request rejects, as fetch does).
            if(answer && answer.hang) await new Promise((res, rej) => {
                window.__releaseShare = res;
                if(opts.signal) opts.signal.addEventListener('abort', () => { window.__SHARE_ABORTED = true; rej(new DOMException('The user aborted a request.', 'AbortError')); });
            });
            // status 0: no answer reaches Dossiary (write: the Mac shared it anyway).
            if(answer && answer.status === 0){ if(answer.write) await writeSync(); throw new TypeError('Failed to fetch'); }
            if(answer && answer.status !== 200) return json(answer.status, answer.body);
            const name = (answer && answer.body && answer.body.name) || body.folder.replace(/\\.dossiary$/, '');
            await writeSync();
            return json(200, { id: 'lib-new', name, uploading: true });
        }
        const st = /^\\/admin\\/libraries\\/([^/]+)\\/state$/.exec(path);
        if(st) return json(200, { version: 0, lease: null, uploading: !!S.uploading });
        const lease = /^\\/admin\\/libraries\\/([^/]+)\\/lease$/.exec(path);
        if(lease && method === 'POST'){
            const body = JSON.parse(opts.body);
            return json(200, { result: body.action === 'release' ? 'released' : 'granted', lease: { holder: 'this', deviceName: 'MacBook Pro' }, version: 0 });
        }
        const get = /^\\/admin\\/libraries\\/([^/]+)\\/get$/.exec(path);
        if(get && method === 'POST'){
            if(S.hangGet) await new Promise(r => { window.__releaseGet = r; });
            const list = S.gets || [];
            const answer = list.length > 1 ? list.shift() : list[0];
            if(answer.status === 200){
                const folder = answer.body.folder.split('/').pop();
                const lib = window.__makeSeededRoot({ documents: [] });
                lib.name = folder;
                libRoot()._children.set(folder, lib);
            }
            return json(answer.status, answer.body);
        }
        return json(404, { error: 'Not found' });
    };
}
""" % ROOT_PATH

IDB_SPY = """
(() => {
    window.__IDB_OPENS = [];
    const real = window.indexedDB.open.bind(window.indexedDB);
    window.indexedDB.open = (name, version) => {
        window.__IDB_OPENS.push([name, version]);
        if(name === 'dossiary-libraries-root' && window.__IDB_FAIL){
            const req = { onsuccess: null, onerror: null, onblocked: null, onupgradeneeded: null, result: undefined, error: null };
            setTimeout(() => {
                if(window.__IDB_FAIL === 'blocked'){ if(req.onblocked) req.onblocked({ target: req }); }
                else { req.error = new DOMException('Simulated failure', 'UnknownError'); if(req.onerror) req.onerror({ target: req }); }
            }, 0);
            return req;
        }
        return real(name, version);
    };
})();
"""

TOKEN_KEY = 'dossiary_sync_admin_token'
SEED = {
    "documents": [{
        "id": 1, "title": "Invoice", "category": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": "files/1_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }],
}
DEVICES = [
    {"id": "phone-1", "name": "Arne's iPhone", "role": "phone", "libraries": []},
    {"id": "pi-1", "name": "Pi copy", "role": "mirror", "libraries": []},
]
SHARE_URL = 'http://127.0.0.1:8769/admin/libraries/share'


async def open_app(p, sync, token='admin-tok', lang=None, in_place=True, extra_files=None, store_root=False):
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
    # Log every IndexedDB open; window.__IDB_FAIL = 'blocked' | 'error' makes
    # opens of the libraries-folder database fail that way.
    await page.add_init_script(IDB_SPY)
    await page.goto(f"file://{APP_PATH}")
    await page.wait_for_timeout(200)
    if token:
        await page.evaluate("([k, t]) => localStorage.setItem(k, t)", [TOKEN_KEY, token])
    await page.evaluate(FAKE_SYNC, sync)
    await page.evaluate("""async ([seed, inPlace, files]) => {
        const libRoot = window.__makeEmptyRoot(); libRoot.name = 'Dossiary';
        const elsewhere = window.__makeEmptyRoot(); elsewhere.name = 'Documents';
        const wrong = window.__makeEmptyRoot(); wrong.name = 'Somewhere else';
        const root = window.__makeSeededRoot(seed);
        root.name = 'Tax 2026.dossiary';
        (inPlace ? libRoot : elsewhere)._children.set(root.name, root);
        window.__LIB_ROOT = libRoot; window.__ELSEWHERE = elsewhere; window.__WRONG_DIR = wrong; window.__TEST_ROOT = root;
        for(const [path, text] of Object.entries(files)){
            const parts = path.split('/');
            let dir = root;
            for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
            const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
            await w.write(new TextEncoder().encode(text)); await w.close();
        }
    }""", [SEED, in_place, extra_files or {"files/1_a.pdf": "%PDF-1.4 a"}])
    await page.click('#open-btn')
    await page.wait_for_timeout(400)
    if store_root:
        await page.evaluate("""async (root) => {
            const req = indexedDB.open('dossiary-libraries-root', 1);
            req.onupgradeneeded = () => req.result.createObjectStore('librariesRoot', { keyPath: 'id' });
            const idb = await new Promise(r => { req.onsuccess = () => r(req.result); });
            await new Promise(r => { const q = idb.transaction('librariesRoot', 'readwrite').objectStore('librariesRoot').put({ id: 'root', handle: window.__LIB_ROOT, root }); q.onsuccess = r; });
        }""", ROOT_PATH)
    return browser, page, errors


async def calls(page, url=None):
    all_calls = await page.evaluate("window.__CALLS")
    return [c for c in all_calls if url is None or c['url'] == url]


async def text_of(page, sel):
    loc = page.locator(sel)
    return (await loc.inner_text()) if await loc.count() else ''


async def recent_names(page):
    return await page.evaluate("() => [...window.__FAKE_IDB_DATABASES.get('dossiary-app-db')._stores.get('recentLibraries').map.values()].map(e => e.name)")


async def stored_root(page):
    return await page.evaluate("() => { const d = window.__FAKE_IDB_DATABASES.get('dossiary-libraries-root'); const s = d && d._stores.get('librariesRoot'); const e = s && s.map.get('root'); return e ? { name: e.handle.name, root: e.root } : null; }")


async def children(page, expr):
    return await page.evaluate(f"() => {{ const d = {expr}; return d ? [...d._children.keys()].sort() : null; }}")


async def tree(page, expr):
    return await page.evaluate("""(expr) => {
        const d = eval(expr); if(!d) return null;
        const out = [];
        const walk = (dir, prefix) => { for(const [n, h] of dir._children){ if(h.kind === 'directory') walk(h, prefix + n + '/'); else out.push(prefix + n); } };
        walk(d, ''); return out.sort();
    }""", expr)


async def picker_calls(page):
    return await page.evaluate("window.__STUB_LOG.filter(l => l.startsWith('showDirectoryPicker')).length")


async def open_share(page):
    await page.click('#tools-btn')
    await page.click('#share-library-btn')
    await page.wait_for_timeout(300)


async def header_height(page):
    return await page.evaluate("document.querySelector('header').getBoundingClientRect().height")


async def main():
    async with async_playwright() as p:
        # === 1. Libraries folder chosen and verified; share in place ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "uploading": True})
        header_before = await header_height(page)
        await page.click('#tools-btn')
        item = page.locator('#share-library-btn')
        print("1 Tools has Share this library for an unsynced library:", await item.is_visible() and (await item.inner_text()).strip() == '⇪ Share this library…')
        await page.click('#share-library-btn')
        await page.wait_for_timeout(300)
        print("1 dialog title:", (await text_of(page, '#share-library-title')) == 'Share this library')
        print("1 name prefilled without .dossiary:", await page.input_value('#share-library-name') == 'Tax 2026')
        phones = await page.locator('.share-library-phone').evaluate_all("els => els.map(e => [e.dataset.id, e.checked])")
        print("1 one checkbox per phone (not the Pi), none ticked:", phones == [['phone-1', False]])
        ph = await text_of(page, "#share-library-phones"); print("1 phone name shown:", "Arne's iPhone" in ph, repr(ph))
        await page.evaluate("window.__NEXT_PICKED_DIR = window.__WRONG_DIR")
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(300)
        chooser = await text_of(page, '#share-library-root-slot')
        print("1 no stored folder: the chooser names the root from a check call:", f"Choose this Mac's libraries folder: {ROOT_PATH}." in chooser, chooser[:160])
        print("1 that check used a probe that doesn't exist:", (await page.evaluate("window.__PROBES"))[0]['where'] == [])
        print("1 nothing shared yet:", len(await calls(page, SHARE_URL)) == 0)
        await page.click('#share-library-root-slot .libraries-root-choose-btn')
        await page.wait_for_timeout(300)
        probes = await page.evaluate("window.__PROBES")
        print("1 wrong folder: probe written there before the check:", len(probes) == 2 and probes[1]['where'] == ['wrong'], probes)
        print("1 ...and removed again:", not any(n.startswith('.dossiary-probe-') for n in await children(page, 'window.__WRONG_DIR')))
        err = await text_of(page, '#share-library-root-slot .libraries-root-error')
        print("1 wrong folder refused:", err == f"That isn't {ROOT_PATH}. Choose that folder.", err)
        print("1 wrong folder not stored:", await stored_root(page) is None)
        print("1 still nothing shared:", len(await calls(page, SHARE_URL)) == 0)
        before_root = await children(page, 'window.__LIB_ROOT')
        await page.evaluate("window.__NEXT_PICKED_DIR = window.__LIB_ROOT")
        await page.click('#share-library-root-slot .libraries-root-choose-btn')
        await page.wait_for_timeout(800)
        probes = await page.evaluate("window.__PROBES")
        print("1 right folder: probe found by the check:", probes[-1]['where'] == ['root'])
        print("1 ...and removed again:", not any(n.startswith('.dossiary-probe-') for n in await children(page, 'window.__LIB_ROOT')))
        print("1 right folder stored with its path:", await stored_root(page) == {"name": "Dossiary", "root": ROOT_PATH})
        opens = await page.evaluate("window.__IDB_OPENS")
        print("1 the folder lives in its own database, version 1:", ['dossiary-libraries-root', 1] in opens and all(v == 1 for n, v in opens if n == 'dossiary-libraries-root'))
        print("1 Recent libraries still opens dossiary-app-db at version 1:", all(v == 1 for n, v in opens if n == 'dossiary-app-db') and any(n == 'dossiary-app-db' for n, v in opens))
        print("1 dossiary-app-db holds only recentLibraries:", await page.evaluate("[...window.__FAKE_IDB_DATABASES.get('dossiary-app-db')._stores.keys()]") == ['recentLibraries'])
        shares = await calls(page, SHARE_URL)
        print("1 one share POST {folder, phones: []} as JSON:", len(shares) == 1 and shares[0]['body'] == {"folder": "Tax 2026.dossiary", "phones": []} and shares[0]['contentType'] == 'application/json', shares)
        print("1 library.sqlite was saved before the share call:", await page.evaluate("window.__SHARED_DB !== null"))
        print("1 in place: no copy made:", await children(page, 'window.__LIB_ROOT') == before_root, await children(page, 'window.__LIB_ROOT'))
        print("1 dialog closed:", await page.locator('#share-library-body').count() == 0)
        print("1 reopened on the same folder, now synced:", await page.evaluate("window.__DEBUG_syncState().version") == 0 and (await text_of(page, '#sub-label')) == 'Tax 2026.dossiary')
        status = await page.get_attribute('#status', 'title') or await text_of(page, '#status')
        print("1 status line:", status.startswith('Shared “Tax 2026” — uploading to the Pi.'), status)
        state_gets = [c for c in await calls(page) if c['method'] == 'GET' and c['url'].endswith('/state')]
        print("1 the page read GET .../state after the share (it learns the upload is running):", len(state_gets) >= 1, len(state_gets))
        print("1 header height unchanged:", abs(await header_height(page) - header_before) < 0.5, header_before, await header_height(page))
        await page.evaluate("window.__SYNC.uploading = false")
        await page.evaluate("window.__DEBUG_syncNow(6000)")
        await page.wait_for_timeout(200)
        n_state = len(state_gets)
        state_gets = [c for c in await calls(page) if c['method'] == 'GET' and c['url'].endswith('/state')]
        print("1 the page polls the state again once uploading is over:", len(state_gets) > n_state, n_state, len(state_gets))
        await page.click('#tools-btn')
        print("1 a synced library has no Share item:", not await page.locator('#share-library-btn').is_visible())
        await page.keyboard.press('Escape')

        # === 2. Share from elsewhere: copy, numbering, skipped files, Recent replaced; stored folder reused ===
        await page.evaluate("""async () => {
            const lib = window.__makeSeededRoot({ documents: [] });
            lib.name = 'Tax 2026.dossiary';
            window.__ELSEWHERE._children.set(lib.name, lib);
            const put = async (path, text) => {
                const parts = path.split('/'); let dir = lib;
                for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
                await w.write(new TextEncoder().encode(text)); await w.close();
            };
            for(const f of ['files/1_a.pdf', 'files/1_a.txt', 'thumbnails/1.jpg', 'inbox/new.pdf', '.dossiary-base.json', '.DS_Store', 'files/._junk', '.kept-aside/Mac-1/library.sqlite']) await put(f, 'x ' + f);
            window.__TEST_ROOT = lib;
            window.__ORIGINAL = lib;
        }""")
        await page.click('#reload-btn')
        await page.click('#open-btn')
        await page.wait_for_timeout(400)
        original_before = await tree(page, 'window.__ORIGINAL')
        await page.evaluate("window.__DEBUG_dbRun(\"INSERT OR REPLACE INTO settings (key, value) VALUES ('marker_from_memory', 'yes')\")")
        print("2 opened the second library:", (await text_of(page, '#sub-label')) == 'Tax 2026.dossiary' and await page.evaluate("window.__DEBUG_syncState().version") is None)
        await page.evaluate("window.__SYNC.shares = [{status: 200, body: {name: 'Tax 2026 2'}}]; window.__SYNC.uploading = true;")
        await open_share(page)
        print("2 name editable for a copy:", await page.locator('#share-library-name').get_attribute('readonly') is None)
        await page.check('.share-library-phone[data-id="phone-1"]')
        pickers = await picker_calls(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(1000)
        print("2 stored folder reused, no picker:", await picker_calls(page) == pickers)
        shares = await calls(page, SHARE_URL)
        print("2 shared the numbered copy with the ticked phone:", shares[-1]['body'] == {"folder": "Tax 2026 2.dossiary", "phones": ["phone-1"]}, shares[-1]['body'])
        copy = await tree(page, "window.__LIB_ROOT._children.get('Tax 2026 2.dossiary')")
        print("2 copy holds library.sqlite and the files:", copy is not None and all(f in copy for f in ['library.sqlite', 'files/1_a.pdf', 'files/1_a.txt', 'thumbnails/1.jpg', 'inbox/new.pdf']), copy)
        print("2 sync bookkeeping and clutter skipped:", copy is not None and not any(f.startswith('.kept-aside') or f in ('.dossiary-base.json', '.DS_Store', 'files/._junk') for f in copy))
        print("2 library.sqlite came from memory:", await page.evaluate("window.__SHARED_DB && window.__SHARED_DB.includes('marker_from_memory')"))
        print("2 original folder unchanged:", await tree(page, 'window.__ORIGINAL') == original_before)
        print("2 now open on the copy:", (await text_of(page, '#sub-label')) == 'Tax 2026 2.dossiary' and await page.evaluate("window.__DEBUG_syncState().version") == 0)
        await page.wait_for_timeout(200)
        recent = await recent_names(page)
        print("2 Recent: copy in, original out:", 'Tax 2026 2.dossiary' in recent and await page.evaluate("""async () => {
            const entries = [...window.__FAKE_IDB_DATABASES.get('dossiary-app-db')._stores.get('recentLibraries').map.values()];
            return !entries.some(e => e.handle === window.__ORIGINAL);
        }"""), recent)
        result = await text_of(page, '#share-library-result')
        note = await text_of(page, '#share-library-original-note')
        print("2 result uses the hub's name:", result == 'Shared “Tax 2026 2” — uploading to the Pi.', result)
        print("2 note names the copy and the original:", note == f"Dossiary now uses {ROOT_PATH}/Tax 2026 2.dossiary. The original at Tax 2026.dossiary is no longer used — once you've checked the shared copy, you can move it to the Trash.", note)
        await page.click('#share-library-ok-btn')
        print("2 no errors:", errors == [], errors)
        await browser.close()

        # === 3. Stop and a copy failure remove the copy ===
        files = {f"files/{i}_d.pdf": f"doc {i}" for i in range(1, 9)}
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES}, in_place=False, extra_files=files, store_root=True)
        await page.evaluate("""() => {
            window.__GATE = new Promise(r => { window.__OPEN_GATE = r; });
            const files = window.__TEST_ROOT._children.get('files');
            for(const h of files._children.values()){
                const orig = Object.getPrototypeOf(h).getFile;
                h.getFile = async function(){ await window.__GATE; return orig.call(this); };
            }
        }""")
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(300)
        print("3 copy in progress with Stop shown:", await page.locator('#share-library-stop-btn').is_visible() and 'Tax 2026.dossiary' in await children(page, 'window.__LIB_ROOT'))
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(100)
        print("3 Escape doesn't close while copying:", await page.locator('#share-library-body').count() == 1)
        await page.click('#share-library-stop-btn')
        await page.evaluate("window.__OPEN_GATE()")
        await page.wait_for_timeout(500)
        print("3 stopped: the copy is removed:", 'Tax 2026.dossiary' not in await children(page, 'window.__LIB_ROOT'))
        st = await text_of(page, '#share-library-status')
        print("3 stopped message:", st == 'Stopped. The copy was removed; nothing was shared.', st)
        print("3 nothing shared:", len(await calls(page, SHARE_URL)) == 0)
        await page.evaluate("""() => {
            const h = window.__TEST_ROOT._children.get('files')._children.get('3_d.pdf');
            h.getFile = async () => { const e = new Error('The file is not readable.'); e.name = 'NotReadableError'; throw e; };
        }""")
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(600)
        st = await text_of(page, '#share-library-status')
        print("3 copy failure names the file and reason:", 'Tax 2026.dossiary/files/3_d.pdf' in st and 'not readable' in st and st.endswith('The copy was removed; nothing was shared.'), st)
        print("3 failed copy removed:", 'Tax 2026.dossiary' not in await children(page, 'window.__LIB_ROOT'))
        print("3 still nothing shared:", len(await calls(page, SHARE_URL)) == 0)
        print("3 no errors:", errors == [], errors)
        await browser.close()

        # === 4. Share fails after the copy: copy kept, Try again posts again ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "shares": [{"status": 503, "body": {"error": "hub-unreachable"}}, {"status": 200, "body": {}}]}, in_place=False, store_root=True)
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(600)
        st = await text_of(page, '#share-library-status')
        print("4 hub unreachable, copy named as kept:", "The Raspberry Pi can't be reached." in st and 'The copy “Tax 2026.dossiary” was kept but isn\'t shared yet.' in st, st)
        print("4 copy still there:", 'Tax 2026.dossiary' in await children(page, 'window.__LIB_ROOT'))
        print("4 button reads Try again:", (await text_of(page, '#share-library-share-btn')) == 'Try again')
        print("4 library still open here, unchanged:", await page.locator('#share-library-body').count() == 1)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(800)
        shares = await calls(page, SHARE_URL)
        print("4 Try again posts the same copy again:", len(shares) == 2 and shares[1]['body']['folder'] == 'Tax 2026.dossiary')
        print("4 no second copy made:", [n for n in await children(page, 'window.__LIB_ROOT') if n.startswith('Tax')] == ['Tax 2026.dossiary'])
        print("4 then shared and reopened:", await page.evaluate("window.__DEBUG_syncState().version") == 0)
        print("4 no errors:", errors == [], errors)
        await browser.close()

        # === 5. Not connected → Connect; 409 already shared ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES}, token=None)
        await open_share(page)
        print("5 not connected explains:", 'Connect Dossiary to it first.' in await text_of(page, '#share-library-connect-text'))
        print("5 no admin call for devices:", not any(c['url'].endswith('/admin/devices') for c in await calls(page)))
        await page.click('#share-library-connect-btn')
        await page.wait_for_timeout(300)
        print("5 Connect opens the devices dialog:", await page.locator('#devices-dialog-body').count() == 1 and await page.locator('#devices-connect-btn').count() == 1)
        await page.keyboard.press('Escape')
        await page.evaluate("([k, t]) => localStorage.setItem(k, t)", [TOKEN_KEY, 'admin-tok'])
        await page.evaluate("window.__SYNC.shares = [{status: 409, body: {error: 'already-shared'}}]")
        await page.evaluate("""async (root) => {
            const req = indexedDB.open('dossiary-libraries-root', 1);
            req.onupgradeneeded = () => req.result.createObjectStore('librariesRoot', { keyPath: 'id' });
            const idb = await new Promise(r => { req.onsuccess = () => r(req.result); });
            await new Promise(r => { const q = idb.transaction('librariesRoot', 'readwrite').objectStore('librariesRoot').put({ id: 'root', handle: window.__LIB_ROOT, root }); q.onsuccess = r; });
            window.__LIB_ROOT._granted = true;
        }""", ROOT_PATH)
        await open_share(page)
        print("5 in place known up front: name read-only:", await page.locator('#share-library-name').get_attribute('readonly') is not None)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(500)
        st = await text_of(page, '#share-library-status')
        print("5 409 already-shared message:", st == 'This library is already shared.', st)
        print("5 unknown error codes are shown with the code:", await page.evaluate("""async () => {
            window.__SYNC.shares = [{status: 500, body: {error: 'not-an-editor'}}];
            document.getElementById('share-library-share-btn').click();
            await new Promise(r => setTimeout(r, 400));
            return document.getElementById('share-library-status').textContent;
        }""") == 'Sharing failed: not-an-editor (500).')
        print("5 no errors:", errors == [], errors)
        await browser.close()

        # === 6. Get it: list, disabled while uploading, download, Open ===
        available = [{"id": "lib-a", "name": "Household", "available": True}, {"id": "lib-b", "name": "Tax 2027", "available": False}]
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "available": available, "hangGet": True,
                                                   "gets": [{"status": 200, "body": {"id": "lib-a", "name": "Household", "folder": f"{ROOT_PATH}/Household.dossiary"}}]})
        await page.click('#tools-btn')
        await page.click('#devices-btn')
        await page.wait_for_timeout(500)
        slot = await text_of(page, '#devices-available-slot')
        print("6 section listed:", 'On the Pi, not on this Mac' in slot and 'Household' in slot and 'Tax 2027' in slot, slot)
        rows = await page.locator('#devices-available-list li').evaluate_all("els => els.map(li => [li.dataset.library, li.querySelector('button').disabled, li.textContent.includes('being uploaded')])")
        print("6 still-uploading one disabled with a note:", rows == [['lib-a', False, False], ['lib-b', True, True]])
        await page.click('#devices-available-list li[data-library="lib-a"] .devices-get-btn')
        await page.wait_for_timeout(300)
        print("6 no stored folder: the chooser opens under the row:", f"Choose this Mac's libraries folder: {ROOT_PATH}." in await text_of(page, '#devices-available-list li[data-library="lib-a"]'))
        await page.evaluate("window.__NEXT_PICKED_DIR = window.__LIB_ROOT")
        await page.click('#devices-available-list .libraries-root-choose-btn')
        await page.wait_for_timeout(300)
        btn = page.locator('#devices-available-list li[data-library="lib-a"] .devices-get-btn')
        print("6 running: Downloading…", (await btn.inner_text()) == 'Downloading…' and await btn.is_disabled())
        gets = await calls(page, 'http://127.0.0.1:8769/admin/libraries/lib-a/get')
        print("6 one get POST as JSON {}:", len(gets) == 1 and gets[0]['body'] == {} and gets[0]['contentType'] == 'application/json')
        await page.evaluate("window.__releaseGet()")
        await page.wait_for_timeout(300)
        print("6 done: Open offered:", await page.locator('#devices-available-list .devices-open-btn').count() == 1 and '“Household” is now on this Mac.' in await text_of(page, '#devices-available-list'))
        await page.click('#devices-available-list .devices-open-btn')
        await page.wait_for_timeout(600)
        print("6 Open opens the downloaded folder:", (await text_of(page, '#sub-label')) == 'Household.dossiary' and await page.locator('#devices-dialog-body').count() == 0)
        await page.wait_for_timeout(200)
        print("6 added to Recent:", 'Household.dossiary' in await recent_names(page))
        print("6 no errors:", errors == [], errors)
        await browser.close()

        # Errors under the row, hidden when empty / older service
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "available": available[:1],
                                                   "gets": [{"status": 409, "body": {"error": "not-ready"}}]}, store_root=True)
        await page.click('#tools-btn'); await page.click('#devices-btn'); await page.wait_for_timeout(500)
        await page.click('#devices-available-list .devices-get-btn')
        await page.wait_for_timeout(400)
        print("6 not-ready shown under the row:", (await text_of(page, '#devices-available-list .devices-get-error')) == "It hasn't finished uploading yet. Try again in a moment.")
        await page.evaluate("window.__SYNC.gets = [{status: 502, body: {error: 'download-failed'}}]")
        await page.click('#devices-available-list .devices-get-btn')
        await page.wait_for_timeout(400)
        print("6 unknown code shown with the code:", (await text_of(page, '#devices-available-list .devices-get-error')) == "Couldn't get it: download-failed (502).")
        await page.keyboard.press('Escape')
        for avail, label in (([], 'empty list'), ('missing', 'older service (404)')):
            await page.evaluate(f"window.__SYNC.available = {json.dumps(avail)}")
            await page.click('#tools-btn'); await page.click('#devices-btn'); await page.wait_for_timeout(500)
            print(f"6 section hidden for an {label}:", (await text_of(page, '#devices-available-slot')).strip() == '' and await page.locator('#devices-list').count() == 1)
            await page.keyboard.press('Escape')
        print("6 no errors (errors run):", errors == [], errors)
        await browser.close()

        # === 7. German labels ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "available": available[:1]}, lang='de', store_root=True)
        await page.click('#tools-btn')
        print("7 German Tools item:", (await text_of(page, '#share-library-btn')).strip() == '⇪ Diese Bibliothek teilen…')
        await page.click('#share-library-btn'); await page.wait_for_timeout(300)
        print("7 German dialog:", (await text_of(page, '#share-library-title')) == 'Diese Bibliothek teilen' and (await text_of(page, '#share-library-share-btn')) == 'Teilen')
        await page.keyboard.press('Escape')
        await page.click('#tools-btn'); await page.click('#devices-btn'); await page.wait_for_timeout(500)
        slot = await text_of(page, '#devices-available-slot')
        print("7 German Get it section:", 'Auf dem Pi, nicht auf diesem Mac' in slot and 'Holen' in slot, slot)
        print("7 no errors:", errors == [], errors)
        await browser.close()

        # === 9. The share call has no timeout; background saves are held meanwhile ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "shares": [{"hang": True, "status": 200, "body": {}}]}, store_root=True)
        # Every 15 s timer fires at once: an admin call with the default timeout would be aborted.
        await page.evaluate("""() => { const real = window.setTimeout; window.setTimeout = (fn, ms, ...a) => real(fn, ms === 15000 ? 0 : ms, ...a); }""")
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(500)
        print("9 share call still waiting, not aborted:", await page.evaluate("!window.__SHARE_ABORTED") and len(await calls(page, SHARE_URL)) == 1 and await page.locator('#share-library-body').count() == 1)
        held = await page.evaluate("""async () => {
            window.__DEBUG_dbRun("INSERT OR REPLACE INTO settings (key, value) VALUES ('from_background', 'yes')");
            const r = await window.__DEBUG_persistDb({ background: true });
            const bytes = window.__TEST_ROOT._children.get('library.sqlite')._bytes;
            return { r, written: new TextDecoder().decode(bytes).includes('from_background') };
        }""")
        print("9 a background save during the share is held:", held == {"r": False, "written": False}, held)
        await page.evaluate("window.__releaseShare()")
        await page.wait_for_timeout(800)
        print("9 then shared and reopened:", await page.evaluate("window.__DEBUG_syncState().version") == 0 and await page.locator('#share-library-body').count() == 0)
        print("9 no errors:", errors == [], errors)
        await browser.close()

        # A failed share lets background saves through again.
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "shares": [{"status": 503, "body": {"error": "hub-unreachable"}}]}, store_root=True)
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(500)
        after = await page.evaluate("""async () => {
            window.__DEBUG_dbRun("INSERT OR REPLACE INTO settings (key, value) VALUES ('from_background', 'yes')");
            return await window.__DEBUG_persistDb({ background: true });
        }""")
        print("9 after a failed share background saves work again:", after is not False, after)
        print("9 no errors (failed share):", errors == [], errors)
        await browser.close()

        # === 10. No answer, but the Mac shared it: finished from the folder's sync file ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "shares": [{"status": 0, "write": True}]}, in_place=False, store_root=True)
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(1000)
        print("10 no answer, sync file written: reopened on the copy, synced:", (await text_of(page, '#sub-label')) == 'Tax 2026.dossiary' and await page.evaluate("window.__DEBUG_syncState().version") == 0)
        print("10 the copy in the libraries folder is open:", await page.evaluate("window.__LIB_ROOT._children.get('Tax 2026.dossiary') !== undefined"))
        result = await text_of(page, '#share-library-result')
        print("10 result shown:", result == 'Shared “Tax 2026” — uploading to the Pi.', result)
        print("10 no errors:", errors == [], errors)
        await browser.close()

        # No answer and nothing written: kept copy; Try again answers 409 once the Mac had shared it -> finished.
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "shares": [{"status": 0}, {"status": 409, "body": {"error": "already-shared"}}]}, in_place=False, store_root=True)
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(800)
        st = await text_of(page, '#share-library-status')
        print("10 no answer, no sync file: error and copy kept:", "didn't answer" in st and 'was kept' in st and (await text_of(page, '#share-library-share-btn')) == 'Try again', st)
        await page.evaluate("""async () => {
            const dir = window.__LIB_ROOT._children.get('Tax 2026.dossiary');
            const w = await (await dir.getFileHandle('.dossiary-sync.json', { create: true })).createWritable();
            await w.write(new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-new', hub: 'https://pi.local:8443', version: 0 })));
            await w.close();
        }""")
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(1000)
        print("10 Try again: 409 with the sync file there -> finished:", len(await calls(page, SHARE_URL)) == 2 and await page.evaluate("window.__DEBUG_syncState().version") == 0 and (await text_of(page, '#sub-label')) == 'Tax 2026.dossiary')
        print("10 no errors (409):", errors == [], errors)
        await browser.close()

        # 409 with no sync file stays an error.
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "shares": [{"status": 409, "body": {"error": "already-shared"}}]}, store_root=True)
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(600)
        print("10 409 without a sync file: already shared:", (await text_of(page, '#share-library-status')) == 'This library is already shared.')
        await browser.close()

        # === 11. A same-named folder appearing between the name check and the create is not used ===
        files = {f"files/{i}_d.pdf": f"doc {i}" for i in range(1, 5)}
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES}, in_place=False, extra_files=files, store_root=True)
        await page.evaluate("""() => {
            const root = window.__LIB_ROOT;
            const real = root.getDirectoryHandle.bind(root);
            root.getDirectoryHandle = async (name, opts) => {
                if(name === 'Tax 2026.dossiary' && opts && opts.create && !window.__RACED){
                    window.__RACED = true;
                    const other = await real(name, { create: true });   // someone else's folder, just made
                    const w = await (await other.getFileHandle('theirs.txt', { create: true })).createWritable();
                    await w.write(new TextEncoder().encode('not ours')); await w.close();
                }
                return real(name, opts);
            };
            window.__GATE = new Promise(r => { window.__OPEN_GATE = r; });
            for(const h of window.__TEST_ROOT._children.get('files')._children.values()){
                const orig = Object.getPrototypeOf(h).getFile;
                h.getFile = async function(){ await window.__GATE; return orig.call(this); };
            }
        }""")
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(400)
        print("11 the copy goes to the next free name:", 'Tax 2026 2.dossiary' in await children(page, 'window.__LIB_ROOT'))
        await page.click('#share-library-stop-btn')
        await page.evaluate("window.__OPEN_GATE()")
        await page.wait_for_timeout(500)
        kids = await children(page, 'window.__LIB_ROOT')
        print("11 Stop removes only our copy:", 'Tax 2026 2.dossiary' not in kids and 'Tax 2026.dossiary' in kids, kids)
        print("11 the other folder is untouched:", await tree(page, "window.__LIB_ROOT._children.get('Tax 2026.dossiary')") == ['theirs.txt'])
        print("11 nothing shared:", len(await calls(page, SHARE_URL)) == 0)
        print("11 no errors:", errors == [], errors)
        await browser.close()

        # === 12. The libraries folder is the open library itself: refused ===
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES}, store_root=True)
        await page.evaluate("""async () => {
            const req = indexedDB.open('dossiary-libraries-root', 1);
            const idb = await new Promise(r => { req.onsuccess = () => r(req.result); });
            await new Promise(r => { const q = idb.transaction('librariesRoot', 'readwrite').objectStore('librariesRoot').put({ id: 'root', handle: window.__TEST_ROOT, root: '/Users/test/Tax 2026.dossiary' }); q.onsuccess = r; });
        }""")
        before = await tree(page, 'window.__TEST_ROOT')
        await open_share(page)
        await page.click('#share-library-share-btn')
        await page.wait_for_timeout(500)
        st = await text_of(page, '#share-library-status')
        print("12 refused with a message:", st == "Dossiary Sync's libraries folder (/Users/test/Tax 2026.dossiary) is this library's own folder or lies inside it, so the library can't be copied there. Move the library into a folder of its own, open it from there and share it again.", st)
        print("12 nothing copied into the library:", await tree(page, 'window.__TEST_ROOT') == before)
        print("12 nothing shared:", len(await calls(page, SHARE_URL)) == 0)
        print("12 Share can be clicked again:", await page.locator('#share-library-share-btn').is_enabled())
        print("12 no errors:", errors == [], errors)
        await browser.close()

        # === 13. Devices dialog: the share note; Get it refreshes the libraries; a dropped chooser frees its row ===
        available = [{"id": "lib-a", "name": "Household", "available": True}, {"id": "lib-c", "name": "Cars", "available": True}]
        browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES, "available": available, "libraries": [],
                                                   "gets": [{"status": 200, "body": {"id": "lib-c", "name": "Cars", "folder": f"{ROOT_PATH}/Cars.dossiary"}}]})
        await page.click('#tools-btn'); await page.click('#devices-btn'); await page.wait_for_timeout(500)
        nt = await text_of(page, '#devices-share-note')
        print("13 share note points at Tools:", nt == 'To share another library, open it in Dossiary and choose “Share this library…” in the Tools menu.', nt)
        print("13 no command line in the dialog:", 'dossiary-sync share' not in await text_of(page, '#devices-dialog-body'))
        await page.click('#devices-available-list li[data-library="lib-a"] .devices-get-btn')
        await page.wait_for_timeout(300)
        print("13 chooser under Household, its button disabled:", await page.locator('#devices-available-list li[data-library="lib-a"] .libraries-root-choose-btn').count() == 1 and await page.locator('#devices-available-list li[data-library="lib-a"] .devices-get-btn').is_disabled())
        await page.click('#devices-available-list li[data-library="lib-c"] .devices-get-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""() => { window.__SYNC.libraries = [{ id: 'lib-c', name: 'Cars', available: true }]; window.__NEXT_PICKED_DIR = window.__LIB_ROOT; }""")
        await page.click('#devices-available-list li[data-library="lib-c"] .libraries-root-choose-btn')
        await page.wait_for_timeout(600)
        libs = await text_of(page, '#devices-libraries')
        print("13 after Get it the library is listed at once:", 'Cars' in libs, libs)
        print("13 ...and offered to the phone:", await page.locator('.devices-row[data-id="phone-1"] .devices-lib-checkbox[data-library="lib-c"]').count() == 1)
        print("13 Open still offered:", await page.locator('#devices-available-list li[data-library="lib-c"] .devices-open-btn').count() == 1)
        print("13 the dropped chooser frees Household's Get it:", await page.locator('#devices-available-list li[data-library="lib-a"] .devices-get-btn').is_enabled())
        print("13 no errors:", errors == [], errors)
        await browser.close()

        # === 8. The libraries-folder database blocked or failing: the chooser, never a hang ===
        for mode in ('blocked', 'error'):
            browser, page, errors = await open_app(p, {"token": "admin-tok", "devices": DEVICES}, store_root=True)
            await page.evaluate(f"window.__IDB_FAIL = '{mode}'")
            await open_share(page)
            print(f"8 {mode}: the dialog still opens:", await page.locator('#share-library-share-btn').count() == 1)
            await page.click('#share-library-share-btn')
            await page.wait_for_timeout(400)
            print(f"8 {mode}: falls back to the chooser:", f"Choose this Mac's libraries folder: {ROOT_PATH}." in await text_of(page, '#share-library-root-slot'))
            await page.evaluate("window.__NEXT_PICKED_DIR = window.__LIB_ROOT")
            await page.click('#share-library-root-slot .libraries-root-choose-btn')
            await page.wait_for_timeout(800)
            shares = await calls(page, SHARE_URL)
            print(f"8 {mode}: the chosen folder is used anyway and the share goes ahead:", len(shares) == 1 and await page.evaluate("window.__DEBUG_syncState().version") == 0)
            print(f"8 {mode}: Recent libraries unaffected:", 'Tax 2026.dossiary' in await recent_names(page))
            print(f"8 {mode}: no errors:", errors == [], errors)
            await browser.close()


asyncio.run(main())
