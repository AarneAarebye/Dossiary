import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, re
from playwright.async_api import async_playwright

# The Dossiary Sync folder (spec dossiary-sync
# docs/superpowers/specs/2026-11-08-standard-libraries-folder-design.md,
# sections 2, 3 and 5): Share shows the refusal for a 409
# {"error":"cloud-drive","provider"}; a library opened from
# directly inside the stored, marked libraries folder that isn't synced gets
# the "Not shared yet" hint. A fake fetch plays the Mac service.
# config: { token, check: body dict (ok is set from the probe) | 'missing' (404),
#           share: {status, body} }
# The devices dialog's folder line and cloud warning, and Get it's refusal,
# left the page in 1.71.0 (Dossiary for Mac has them).
ROOT_PATH = '/Users/test/Dossiary'
FAKE_SYNC = """
(config) => {
    window.__CALLS = [];
    window.__SYNC = config;
    const BASE = 'http://127.0.0.1:8769';
    const json = (status, body) => new Response(JSON.stringify(body), { status });
    window.fetch = async (url, opts = {}) => {
        const headers = opts.headers || {};
        const method = opts.method || 'GET';
        window.__CALLS.push({ url, method, body: opts.body ? JSON.parse(opts.body) : null, contentType: headers['Content-Type'] || null });
        const S = window.__SYNC;
        if(!url.startsWith(BASE + '/')) throw new TypeError('Failed to fetch');
        const path = url.slice(BASE.length);
        if(path === '/admin/health') return json(200, { service: 'dossiary-sync', version: '0.17.0', adminProtocol: 1, connected: headers.Authorization === `Bearer ${S.token}` });
        if(headers.Authorization !== `Bearer ${S.token}`) return json(401, { error: 'Unauthorized' });
        if(method === 'POST' && headers['Content-Type'] !== 'application/json') return json(415, { error: 'JSON only' });
        if(path === '/admin/devices') return json(200, S.devices || [{ id: 'phone-1', name: 'iPhone', role: 'phone', libraries: [] }]);
        if(path === '/admin/libraries') return json(200, S.libraries || []);
        if(path === '/admin/libraries/available') return json(200, S.available || []);
        if(path === '/admin/libraries-root/check' && method === 'POST'){
            if(S.check === 'missing') return json(404, { error: 'Not found' });
            const probe = JSON.parse(opts.body).probe;
            if(!/^\\.dossiary-probe-[A-Za-z0-9-]{1,64}$/.test(probe)) return json(400, { error: 'bad-probe' });
            const lib = window.__LIB_ROOT;
            const h = lib && lib._children.get(probe);
            return json(200, Object.assign({}, S.check, { ok: !!(h && h.kind === 'file') }));
        }
        if(path === '/admin/libraries/share' && method === 'POST'){
            const list = S.shares || [];
            const a = (list.length > 1 ? list.shift() : list[0]) || S.share || { status: 200 };
            if(a.status !== 200) return json(a.status, a.body);
            return json(200, { id: 'lib-new', name: 'Tax 2026' });
        }
        const get = /^\\/admin\\/libraries\\/([^/]+)\\/get$/.exec(path);
        if(get && method === 'POST'){ const a = S.get; return json(a.status, a.body); }
        const st = /^\\/admin\\/libraries\\/([^/]+)\\/state$/.exec(path);
        if(st) return json(200, { version: 0, lease: null });
        return json(404, { error: 'Not found' });
    };
}
"""

TOKEN_KEY = 'dossiary_sync_admin_token'
SEED = {"documents": []}
CHECK_LOCAL = {"root": ROOT_PATH, "marker": True, "cloud": None, "path": "~/Dossiary"}


async def open_app(p, sync, lang=None, in_place=True, store_root=True, granted=True, marker=True, synced=False):
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
    await page.evaluate("([k, t]) => localStorage.setItem(k, t)", [TOKEN_KEY, sync['token']])
    await page.evaluate(FAKE_SYNC, sync)
    await page.evaluate("""async ([seed, inPlace, granted, marker, synced]) => {
        const put = async (dir, name, text) => {
            const w = await (await dir.getFileHandle(name, { create: true })).createWritable();
            await w.write(new TextEncoder().encode(text)); await w.close();
        };
        const libRoot = window.__makeEmptyRoot(); libRoot.name = 'Dossiary';
        libRoot._granted = granted;
        if(marker) await put(libRoot, '.dossiary-root.json', '{"format":1,"kind":"synced-libraries","by":"dossiary-sync 0.17.0"}');
        const elsewhere = window.__makeEmptyRoot(); elsewhere.name = 'Documents';
        const root = window.__makeSeededRoot(seed);
        root.name = 'Tax 2026.dossiary';
        if(synced) await put(root, '.dossiary-sync.json', JSON.stringify({ libraryId: 'lib-1', hub: 'https://pi.local:8443', version: 0 }));
        (inPlace ? libRoot : elsewhere)._children.set(root.name, root);
        window.__LIB_ROOT = libRoot; window.__TEST_ROOT = root;
    }""", [SEED, in_place, granted, marker, synced])
    if store_root:
        await page.evaluate("""async (root) => {
            const req = indexedDB.open('dossiary-libraries-root', 1);
            req.onupgradeneeded = () => req.result.createObjectStore('librariesRoot', { keyPath: 'id' });
            const idb = await new Promise(r => { req.onsuccess = () => r(req.result); });
            await new Promise(r => { const q = idb.transaction('librariesRoot', 'readwrite').objectStore('librariesRoot').put({ id: 'root', handle: window.__LIB_ROOT, root }); q.onsuccess = r; });
        }""", ROOT_PATH)
    await page.click('#open-btn')
    await page.wait_for_timeout(500)
    return browser, page, errors


async def text_of(page, sel):
    loc = page.locator(sel)
    return (await loc.inner_text()) if await loc.count() else ''


async def calls(page, suffix):
    return [c for c in await page.evaluate("window.__CALLS") if c['url'].endswith(suffix)]


async def status_text(page):
    return (await page.get_attribute('#status', 'title')) or (await text_of(page, '#status'))


async def main():
    async with async_playwright() as p:
        # === 5. Share refused for a cloud drive: the refusal text, nothing else changes ===
        browser, page, errors = await open_app(p, {"token": "tok", "check": CHECK_LOCAL,
            "share": {"status": 409, "body": {"error": "cloud-drive", "provider": "iCloud <img src=x onerror=window.__XSS=1>"}}},
            marker=False)
        before = await page.evaluate("() => [...window.__LIB_ROOT._children.keys()].sort()")
        await page.click('#tools-btn'); await page.click('#share-library-btn'); await page.wait_for_timeout(300)
        await page.click('#share-library-share-btn'); await page.wait_for_timeout(600)
        st = await text_of(page, '#share-library-status')
        print("5 the refusal text:", st == "iCloud <img src=x onerror=window.__XSS=1> is a cloud drive. Dossiary Sync can't share libraries from there.", repr(st))
        print("5 the provider stays text:", await page.locator('#share-library-status img').count() == 0 and await page.evaluate("window.__XSS === undefined"))
        print("5 one share call:", len(await calls(page, '/admin/libraries/share')) == 1)
        print("5 the dialog stays open, Share can be pressed again:", await page.locator('#share-library-body').count() == 1 and await page.locator('#share-library-share-btn').is_enabled())
        print("5 no folder created or removed in the libraries folder:", await page.evaluate("() => [...window.__LIB_ROOT._children.keys()].sort()") == before)
        print("5 the library is still not synced:", await page.evaluate("window.__DEBUG_syncState().version") is None
              and not await page.evaluate("window.__TEST_ROOT._children.has('.dossiary-sync.json')"))
        print("5 no page errors:", errors == [], errors)
        await browser.close()

        # === 5b. A copy share refused: the copy it made in the libraries folder goes again ===
        browser, page, errors = await open_app(p, {"token": "tok", "check": CHECK_LOCAL,
            "share": {"status": 409, "body": {"error": "cloud-drive", "provider": "Dropbox"}}}, in_place=False)
        before = await page.evaluate("() => [...window.__LIB_ROOT._children.keys()].sort()")
        await page.click('#tools-btn'); await page.click('#share-library-btn'); await page.wait_for_timeout(300)
        await page.click('#share-library-share-btn'); await page.wait_for_timeout(800)
        shares = await calls(page, '/admin/libraries/share')
        print("5b the copy was offered to the service:", len(shares) == 1 and shares[0]['body']['folder'] == 'Tax 2026.dossiary', shares)
        st = await text_of(page, '#share-library-status')
        print("5b the refusal text, no 'copy kept':", st == "Dropbox is a cloud drive. Dossiary Sync can't share libraries from there.", repr(st))
        print("5b the copy is removed again:", await page.evaluate("() => [...window.__LIB_ROOT._children.keys()].sort()") == before)
        print("5b Share is a plain Share again:", (await page.inner_text('#share-library-share-btn')) == 'Share' and await page.locator('#share-library-share-btn').is_enabled())
        print("5b the original is still open:", (await text_of(page, '#sub-label')) == 'Tax 2026.dossiary' and await page.evaluate("window.__DEBUG_syncState().version") is None)
        print("5b no page errors:", errors == [], errors)
        await browser.close()

        # === 5c. A kept copy, then Try again refused: removed only while it is still that same folder ===
        KEPT = "The copy “Tax 2026.dossiary” was kept but isn't shared yet. Try again to share it."
        REFUSED = "Dropbox is a cloud drive. Dossiary Sync can't share libraries from there."
        for label, tamper in [("the same folder", None), ("a folder replaced under the same name", "replace")]:
            browser, page, errors = await open_app(p, {"token": "tok", "check": CHECK_LOCAL,
                "shares": [{"status": 500, "body": {"error": "boom"}},
                           {"status": 409, "body": {"error": "cloud-drive", "provider": "Dropbox"}}]}, in_place=False)
            await page.click('#tools-btn'); await page.click('#share-library-btn'); await page.wait_for_timeout(300)
            await page.click('#share-library-share-btn'); await page.wait_for_timeout(800)
            st = await text_of(page, '#share-library-status')
            print(f"5c [{label}] first answer 500: the copy is kept and named:", KEPT in st
                  and await page.evaluate("window.__LIB_ROOT._children.has('Tax 2026.dossiary')"), repr(st))
            if tamper == "replace":
                await page.evaluate("""() => { const other = window.__makeEmptyRoot(); other.name = 'Tax 2026.dossiary';
                    window.__LIB_ROOT._children.set('Tax 2026.dossiary', other); window.__REPLACED = other; }""")
            await page.click('#share-library-share-btn'); await page.wait_for_timeout(800)
            shares = await calls(page, '/admin/libraries/share')
            print(f"5c [{label}] Try again shares the same copy:", len(shares) == 2 and shares[1]['body']['folder'] == 'Tax 2026.dossiary', shares)
            st = await text_of(page, '#share-library-status')
            if tamper is None:
                print(f"5c [{label}] refused: the copy is removed, nothing said about a kept copy:", st == REFUSED
                      and not await page.evaluate("window.__LIB_ROOT._children.has('Tax 2026.dossiary')"), repr(st))
            else:
                print(f"5c [{label}] refused: the replaced folder is left alone:",
                      await page.evaluate("window.__LIB_ROOT._children.get('Tax 2026.dossiary') === window.__REPLACED"), repr(st))
                print(f"5c [{label}] ...and still named as kept:", st.startswith(REFUSED) and KEPT in st, repr(st))
            print(f"5c [{label}] no page errors:", errors == [], errors)
            await browser.close()

        # === 5d. Removing the refused copy fails: kept, named, and Try again makes no second copy ===
        browser, page, errors = await open_app(p, {"token": "tok", "check": CHECK_LOCAL,
            "share": {"status": 409, "body": {"error": "cloud-drive", "provider": "Dropbox"}}}, in_place=False)
        await page.evaluate("""() => { const real = window.__LIB_ROOT.removeEntry.bind(window.__LIB_ROOT);
            window.__LIB_ROOT.removeEntry = async (name, opts) => { if(name === 'Tax 2026.dossiary') throw Object.assign(new Error('busy'), { name: 'NoModificationAllowedError' }); return real(name, opts); }; }""")
        await page.click('#tools-btn'); await page.click('#share-library-btn'); await page.wait_for_timeout(300)
        await page.click('#share-library-share-btn'); await page.wait_for_timeout(800)
        st = await text_of(page, '#share-library-status')
        print("5d a failed removal isn't hidden: refusal plus the copy-kept text:", st.startswith(REFUSED) and KEPT in st, repr(st))
        print("5d the copy is still there:", await page.evaluate("window.__LIB_ROOT._children.has('Tax 2026.dossiary')"))
        print("5d the button offers Try again:", (await page.inner_text('#share-library-share-btn')) == 'Try again')
        await page.click('#share-library-share-btn'); await page.wait_for_timeout(800)
        shares = await calls(page, '/admin/libraries/share')
        print("5d Try again shares that same copy, no second numbered copy:", len(shares) == 2 and shares[1]['body']['folder'] == 'Tax 2026.dossiary'
              and await page.evaluate("() => [...window.__LIB_ROOT._children.keys()].sort()") == ['.dossiary-root.json', 'Tax 2026.dossiary'], shares)
        print("5d no page errors:", errors == [], errors)
        await browser.close()

        # === 7. "Not shared yet" hint ===
        hint = 'Not shared yet: Tools → Share this library…'
        browser, page, errors = await open_app(p, {"token": "tok", "check": CHECK_LOCAL})
        st = await status_text(page)
        print("7 unsynced library directly in the marked libraries folder: the hint:", hint in st and st.startswith('Opened'), repr(st))
        print("7 ...without asking for any permission:", await page.evaluate("window.__STUB_LOG.filter(l => l.startsWith('showDirectoryPicker')).length") == 1)
        await browser.close()
        for label, kwargs in [("not in the libraries folder", {"in_place": False}),
                              ("a folder without the marker", {"marker": False}),
                              ("a synced library", {"synced": True}),
                              ("the folder's permission not granted", {"granted": False}),
                              ("no libraries folder stored", {"store_root": False})]:
            browser, page, errors = await open_app(p, {"token": "tok", "check": CHECK_LOCAL}, **kwargs)
            st = await status_text(page)
            print(f"7 no hint for {label}:", 'Not shared yet' not in st and st.startswith('Opened'), repr(st))
            await browser.close()
        browser, page, errors = await open_app(p, {"token": "tok", "check": CHECK_LOCAL}, lang='de')
        st = await status_text(page)
        print("7 German hint:", 'Noch nicht geteilt: Werkzeuge → Diese Bibliothek teilen…' in st, repr(st))
        await page.select_option('#lang-select', 'fr')
        await page.wait_for_timeout(200)
        st = await status_text(page)
        print("7 the hint follows a language change:", 'Pas encore partagée : Outils → Partager cette bibliothèque…' in st, repr(st))
        await browser.close()


asyncio.run(main())
