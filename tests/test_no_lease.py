import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from datetime import datetime, timezone
from playwright.async_api import async_playwright

# Saving without a lease (the hub option cut from dossiary.html): a library with a
# .dossiary-sync.json at its root saves straight to disk and never asks Dossiary
# Sync's admin API (127.0.0.1:8769) for an edit lease. A fake fetch plays the
# service (copied from test_sync_lease.py; its lease answers stay so that any
# lease request the page still makes is logged and can be asserted absent).
# config: { token, down, acquire ('granted'|'busy'|'offline'), busyLease,
#           takeOver ('granted'|...), heartbeat ('granted'|'lost'|'offline'),
#           lostLease (lease object or None), hang (no answer until aborted) }
# Every request is logged in window.__CALLS (url, method, body, keepalive).
FAKE_SYNC = """
(config) => {
    window.__CALLS = [];
    window.__SYNC = config;
    const BASE = 'http://127.0.0.1:8769';
    const json = (status, body) => new Response(JSON.stringify(body), { status });
    window.fetch = async (url, opts = {}) => {
        const headers = opts.headers || {};
        window.__CALLS.push({ url, method: opts.method || 'GET', body: opts.body ? JSON.parse(opts.body) : null,
                              keepalive: !!opts.keepalive, contentType: headers['Content-Type'] || null,
                              auth: headers.Authorization || null });
        const S = window.__SYNC;
        if(!url.startsWith(BASE + '/') || S.down) throw new TypeError('Failed to fetch');
        const path = url.slice(BASE.length);
        // A hung service: no answer until the caller's own timeout aborts the request.
        if(S.hang && path !== '/admin/health') return new Promise((_, reject) => {
            if(opts.signal) opts.signal.addEventListener('abort', () => reject(new DOMException('The operation was aborted.', 'AbortError')));
        });
        if(path === '/admin/health') return json(200, { service: 'dossiary-sync', version: '0.4.0', adminProtocol: 1, connected: headers.Authorization === `Bearer ${S.token}` });
        if(path === '/admin/connect/start' && opts.method === 'POST') return json(200, { validFor: 300 });
        if(path === '/admin/connect' && opts.method === 'POST'){
            const body = JSON.parse(opts.body || '{}');
            return body.code === 'KX7P2M9Q' ? json(200, { token: S.token }) : json(403, { error: 'Wrong code' });
        }
        if(headers.Authorization !== `Bearer ${S.token}`) return json(401, { error: 'Unauthorized' });
        if(path === '/admin/libraries') return json(200, S.libraries || [{ id: 'lib-7f3a', name: 'Household', available: true }]);
        if(path === '/admin/devices') return json(200, []);
        const cn = /^\\/admin\\/libraries\\/([^/]+)\\/connection$/.exec(path);
        if(cn && opts.method === 'POST'){
            if(headers['Content-Type'] !== 'application/json') return json(415, { error: 'JSON only' });
            const body = JSON.parse(opts.body);
            if(S.connectionDelay) await new Promise(r => setTimeout(r, S.connectionDelay));
            if(S.connectionFail) return json(500, { error: S.connectionFail });
            S.state = Object.assign({}, S.state || {}, { disconnectedSince: body.connected ? null : (S.disconnectAt || new Date().toISOString()), lease: null });
            return json(200, S.state);
        }
        const st = /^\\/admin\\/libraries\\/([^/]+)\\/state$/.exec(path);
        if(st && (opts.method || 'GET') === 'GET'){
            const s = (S.states || {})[decodeURIComponent(st[1])] || (decodeURIComponent(st[1]) === 'lib-7f3a' ? S.state : null);
            return s ? json(200, s) : json(404, { error: 'Not found' });
        }
        const m = /^\\/admin\\/libraries\\/([^/]+)\\/lease$/.exec(path);
        if(m && opts.method === 'POST'){
            if(headers['Content-Type'] !== 'application/json') return json(415, { error: 'JSON only' });
            const body = JSON.parse(opts.body);
            if(body.action === 'acquire'){
                if(S.state && S.state.disconnectedSince) return json(200, { result: 'disconnected', lease: null, version: S.state.version });
                const result = body.takeOver ? (S.takeOver || 'granted') : (S.acquire || 'granted');
                if(result === 'busy') return json(200, { result, lease: S.busyLease, version: S.acquireVersion || 3 });
                const granted = result === 'granted' ? { holder: 'this', deviceName: 'MacBook Pro', since: new Date().toISOString() } : null;
                // Like the real service: once granted, its state names this Mac as the holder.
                if(granted && S.state) S.state = Object.assign({}, S.state, { lease: granted });
                return json(200, { result, lease: granted, version: S.acquireVersion || 3 });
            }
            if(body.action === 'heartbeat'){
                const result = S.heartbeat || 'granted';
                return json(200, { result, lease: result === 'lost' ? (S.lostLease || null) : null, version: 3 });
            }
            if(body.action === 'release'){
                if(S.state && S.state.lease && S.state.lease.holder === 'this') S.state = Object.assign({}, S.state, { lease: null });
                return json(200, { result: 'released', lease: null, version: 3 });
            }
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
TODAY_1402 = datetime.now(timezone.utc).strftime('%Y-%m-%dT14:02:00Z')
BUSY_LEASE = {"holder": "other", "deviceName": "MacBook Pro", "since": TODAY_1402}
LEASE_URL = f'http://127.0.0.1:8769/admin/libraries/{LIB_ID}/lease'


async def open_app(p, sync=None, token='admin-tok', sync_file=True, lang=None, width=1440, extra_files=None, seed=None, height=900):
    browser = await p.chromium.launch()
    context = await browser.new_context(viewport={'width': width, 'height': height}, timezone_id='UTC', locale='en-US')
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
    await seed_and_open(page, sync, sync_file, extra_files, seed)
    return browser, page, errors


async def seed_and_open(page, sync=None, sync_file=True, extra_files=None, seed=None):
    await page.evaluate(FAKE_SYNC, sync or {"token": "admin-tok"})
    files = dict(extra_files or {})
    if sync_file:
        files['.dossiary-sync.json'] = json.dumps({"libraryId": LIB_ID, "hub": "https://pi.local:8443", "version": 3})
    await page.evaluate("""async ([seed, files]) => {
        const root = window.__makeSeededRoot(seed);
        root.name = 'Household';
        window.__TEST_ROOT = root;
        for(const [path, text] of Object.entries(files)){
            const parts = path.split('/');
            let dir = root;
            for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
            const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
            await w.write(new TextEncoder().encode(text)); await w.close();
        }
        // Count every write of library.sqlite.
        window.__DB_WRITES = 0;
        const h = root._children.get('library.sqlite');
        const orig = h.createWritable.bind(h);
        h.createWritable = async () => { window.__DB_WRITES++; return orig(); };
    }""", [seed or SEED, files])
    await page.click('#open-btn')
    await page.wait_for_timeout(400)


async def admin_calls(page):
    return await page.evaluate("window.__CALLS.filter(c => c.url.startsWith('http://127.0.0.1:8769'))")


async def lease_calls(page, action=None):
    return [c for c in await admin_calls(page) if c['url'] == LEASE_URL and (action is None or c['body']['action'] == action)]


async def writes(page):
    return await page.evaluate("window.__DB_WRITES")


async def marker(page):
    return await page.evaluate("""() => {
        const m = document.getElementById('sync-marker');
        if(!m) return null;
        return { text: m.textContent, title: m.title, visible: getComputedStyle(m).display !== 'none' };
    }""")


async def edit_title(page, title, wait=400):
    await page.click('tr[data-id="1"]')
    await page.wait_for_timeout(150)
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(200)
    await page.fill('#e-title', title)
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(wait)


async def saved_title(page):
    return await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).documents[0].title")


async def base_marker(page, path='.dossiary-base.json'):
    """The base marker at `path` (None when absent), plus the SHA-256 of library.sqlite on disk (diskSha)."""
    return await page.evaluate("""async (path) => {
        let dir = window.__TEST_ROOT;
        const parts = path.split('/');
        try{ for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part); }catch(e){ return null; }
        let text;
        try{ text = await (await (await dir.getFileHandle(parts[parts.length - 1])).getFile()).text(); }catch(e){ return null; }
        const m = JSON.parse(text);
        const bytes = new Uint8Array(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).arrayBuffer());
        const d = await crypto.subtle.digest('SHA-256', bytes);
        m.diskSha = [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
        return m;
    }""", path)


def marker_ok(m, version):
    """The marker names `version` and the bytes on disk."""
    return bool(m) and m.get('version') == version and isinstance(m.get('sha256'), str) and m['sha256'] == m['diskSha'] \
        and str(m.get('writtenAt', '')).endswith('Z')

def doc(id, title, **kw):
    d = {"id": id, "title": title, "category": None, "document_type": None,
         "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
         "file_path": f"files/{id}_a.pdf", "original_file_path": None,
         "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
         "archived": 0, "needs_review": 0, "deleted": 0}
    d.update(kw)
    return d


SEED2 = {"documents": [doc(1, "Invoice", category="Bills"), doc(2, "Receipt", category="Food"),
                       doc(3, "Letter", category="Mail", needs_review=1), doc(4, "Leaflet", category="Mail", needs_review=1)]}


def state(version=3, lease=None, kept=None, last_error=None, offline=False):
    return {"libraryId": LIB_ID, "version": version, "hubReachable": True, "lease": lease, "offline": offline,
            "keptAside": kept or [], "lastError": last_error}


IMAC_LEASE = {"holder": "other", "deviceName": "iMac", "since": TODAY_1402}
THIS_LEASE = {"holder": "this", "deviceName": "MacBook Pro", "since": TODAY_1402}
KEPT = [{"stamp": "MacBook Pro-2026-05-03-1402", "otherDevice": "iMac"}]
KEPT_TEXT = "Changes made on this Mac on May 03, 2026 couldn't be combined with iMac's. They're kept safe and will be merged by a later update."


async def disk_change(page, titles=None, sync_version=None):
    """What a pull by Dossiary Sync does: a new library.sqlite (and sync file) on disk, written without Dossiary."""
    await page.evaluate("""async ([titles, v]) => {
        const root = window.__TEST_ROOT;
        const h = root._children.get('library.sqlite');
        const data = JSON.parse(await (await h.getFile()).text());
        for(const [id, title] of Object.entries(titles || {})){ const d = data.documents.find(x => x.id === Number(id)); if(d) d.title = title; }
        h._bytes = new TextEncoder().encode(JSON.stringify(data));
        if(v !== null){
            const f = root._children.get('.dossiary-sync.json');
            f._bytes = new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-7f3a', hub: 'https://pi.local:8443', version: v }));
        }
    }""", [{str(k): v for k, v in (titles or {}).items()}, sync_version])

async def tick(page, ms=0):
    await page.evaluate(f"window.__DEBUG_syncNow({ms})")
    await page.wait_for_timeout(200)


async def sync_state(page):
    return await page.evaluate("window.__DEBUG_syncState()")


async def status(page):
    return await page.inner_text('#status')


async def disk_doc_title(page, id):
    return await page.evaluate("async (id) => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).documents.find(d => d.id === id).title", id)


async def row_text(page, id):
    loc = page.locator(f'tr[data-id="{id}"]')
    return await loc.inner_text() if await loc.count() else ''


async def kept_aside_names(page):
    return await page.evaluate("""async () => {
        const k = window.__TEST_ROOT._children.get('.kept-aside');
        if(!k) return [];
        const out = []; for await (const [n] of k.entries()) out.push(n); return out;
    }""")


async def kept_aside_title(page, name):
    return await page.evaluate("""async (n) => {
        const d = window.__TEST_ROOT._children.get('.kept-aside')._children.get(n);
        return JSON.parse(await (await d._children.get('library.sqlite').getFile()).text()).documents[0].title;
    }""", name)


# ---- helpers for this file ----

async def open_edit(page, row=1):
    await page.click(f'tr[data-id="{row}"]')
    await page.wait_for_timeout(150)
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(300)


def lease_posts(calls):
    """Requests that ask the service for (or give back) an editing lease."""
    return [c for c in calls if c['method'] == 'POST' and c['url'].endswith('/lease')]


async def marker_gone(page):
    """No sync marker text anywhere: the element is absent, or empty and not shown."""
    m = await marker(page)
    return m is None or (m['text'].strip() == '' and not m['visible'])


async def disconnect_button_count(page):
    """Open the devices dialog and count 'Work disconnected' / 'Reconnect' switches in it."""
    await page.click('#tools-btn')
    await page.click('#devices-btn')
    await page.wait_for_timeout(400)
    n = await page.locator('.devices-lib-disconnect-btn, .devices-lib-reconnect-btn').count()
    text = await page.inner_text('#modal-root') if await page.locator('#modal-root').count() else ''
    return n, 'Work disconnected' in text



async def scenario_synced_save(p):
    # 1. A synced library with a token: a save goes straight to disk, with no lease and no marker.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(200)
    await edit_title(page, 'Saved without a lease')
    print("synced library: the edit is on disk:", await disk_doc_title(page, 1) == 'Saved without a lease')
    calls = await admin_calls(page)
    print("...no lease request was made:", lease_posts(calls) == [], lease_posts(calls))
    print("...no connection request was made:", not any(c['url'].endswith('/connection') for c in calls))
    print("...no sync marker text:", await marker_gone(page), await marker(page))
    n, text = await disconnect_button_count(page)
    print("...no Work disconnected / Reconnect button in the devices dialog:", n == 0 and not text, n, text)
    # The base marker the service needs: written on every save, equal to the version loaded.
    m = await base_marker(page)
    print("...the save wrote .dossiary-base.json: version 3, the hash of the bytes written:", marker_ok(m, 3), m)
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(150)
    await edit_title(page, 'Second save')
    m2 = await base_marker(page)
    print("...a second save rewrites it for the new bytes:", marker_ok(m2, 3) and m2['sha256'] != m['sha256'], m2)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_base_follows_loaded_version(p):
    # 5. The base marker keeps naming the version the tab loaded, also after a newer version is pulled and reloaded.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await edit_title(page, 'On version 3')
    print("base marker names version 3 before the pull:", marker_ok(await base_marker(page), 3), await base_marker(page))
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    st = await sync_state(page)
    print("a newer version on disk is loaded:", st['version'] == 4 and 'Receipt (iMac)' in await row_text(page, 2), st)
    await edit_title(page, 'On version 4')
    m = await base_marker(page)
    print("...the next save's base marker names version 4:", marker_ok(m, 4), m)
    print("...and no lease request was made:", lease_posts(await admin_calls(page)) == [])
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_newer_reloads(p):
    # 6a. A newer version on disk reloads (the reduced poll): the view is kept, nothing is written.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.click('#nav-item-inbox')
    await page.fill('#search', 'Lette')
    await page.wait_for_timeout(150)
    before = await writes(page)
    await disk_change(page, {3: 'Letter from the bank'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    st = await sync_state(page)
    print("a newer version reloads once:", st['reloads'] == 1 and st['version'] == 4, st)
    print("...the new title is in the table:", 'Letter from the bank' in await row_text(page, 3))
    print("...the search text is kept:", await page.input_value('#search') == 'Lette')
    print("...a reload writes nothing:", await writes(page) == before)
    print("...and no lease request was made:", lease_posts(await admin_calls(page)) == [])
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_guard(p):
    # 2. The guard: a newer version is on disk than the tab's memory when the person saves. Run three ways: through
    # the Edit form with no token, and straight through persistDb() (a person's save with the change already in
    # memory) with and without a token. (acquireVersion 4: today's service answers a lease request with the version
    # on disk, as the real one does; after the cut nothing asks, and the page finds the newer version in
    # .dossiary-sync.json itself.)
    for label, token, mode in (("Edit form, no token", None, 'form'), ("persistDb, with a token", 'admin-tok', 'persist'),
                               ("persistDb, no token", None, 'persist')):
        browser, page, errors = await open_app(p, seed=SEED2, token=token, sync={"token": "admin-tok", "state": state(3), "acquireVersion": 4})
        if mode == 'form':
            await open_edit(page)
            await page.fill('#e-title', 'Mine (old base)')
        else:
            await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Mine (old base)', 1])")
        await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
        w = await writes(page)
        if mode == 'form':
            await page.click('#save-edit-btn')
        else:
            await page.evaluate("window.__DEBUG_persistDb()")
        await page.wait_for_timeout(700)
        names = await kept_aside_names(page)
        print(f"guard ({label}): the person's version is kept aside:", len(names) == 1 and await kept_aside_title(page, names[0]) == 'Mine (old base)', names)
        print("...library.sqlite is not written over the newer one:", await writes(page) == w and await disk_doc_title(page, 2) == 'Receipt (iMac)' and await disk_doc_title(page, 1) == 'Invoice')
        notice = await page.inner_text('#sync-notice-dialog') if await page.locator('#sync-notice-dialog').count() else ''
        print("...#sync-notice-dialog is shown and names the folder:", bool(names) and f'.kept-aside/{names[0]}' in notice, repr(notice))
        print("...the newer version is loaded:", 'Receipt (iMac)' in await row_text(page, 2) and 'Mine' not in await row_text(page, 1))
        print("...and no lease request was made:", lease_posts(await admin_calls(page)) == [])
        print("no page errors:", not errors, errors)
        await browser.close()


async def scenario_poll_reads_state(p):
    # 6b. The reduced poll still reads keptAside from GET .../state (state requests are allowed, lease requests are not).
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await disk_change(page, {1: 'Invoice (Pi)'})
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(3, None, KEPT))
    await tick(page)
    calls = await admin_calls(page)
    print("the poll reads GET .../state:", any(c['method'] == 'GET' and c['url'].endswith(f'/admin/libraries/{LIB_ID}/state') for c in calls))
    print("...kept aside is reported on the status line:", await status(page) == KEPT_TEXT, await status(page))
    print("...and no lease request was made:", lease_posts(calls) == [])
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_poll_deleted(p):
    # 6c. The reduced poll still reads deleted from GET .../state: a library deleted elsewhere is noticed and closed.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Changed', 1])")
    await page.evaluate("(s) => { window.__SYNC.state = s; }",
                        dict(state(3), deleted={"deletedBy": "iMac", "deletedAt": "2026-10-25T10:00:00Z"}))
    await tick(page, 6000)
    await page.wait_for_timeout(300)
    notice = await page.inner_text('#sync-deleted-dialog') if await page.locator('#sync-deleted-dialog').count() else ''
    print("a library deleted elsewhere: the notice is shown:", 'iMac' in notice, repr(notice))
    print("...what wasn't saved is kept aside first:", len(await kept_aside_names(page)) == 1, await kept_aside_names(page))
    print("...and no lease request was made:", lease_posts(await admin_calls(page)) == [])
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_no_sync_file(p):
    # 3. No .dossiary-sync.json: saving works, no admin call at all.
    browser, page, errors = await open_app(p, sync_file=False)
    await edit_title(page, 'Plain save')
    print("no sync file: the edit is saved:", await saved_title(page) == 'Plain save')
    print("...with zero admin calls:", await admin_calls(page) == [], await admin_calls(page))
    print("...no sync marker text:", await marker_gone(page))
    print("...and no base marker file:", await base_marker(page) is None)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_devices_dialog(p):
    # 4. The devices dialog still opens and lists libraries; share and delete are still offered.
    browser, page, errors = await open_app(p, sync={"token": "admin-tok", "state": state(3),
                                                    "libraries": [{"id": LIB_ID, "name": "Household", "available": True}]})
    await page.click('#tools-btn')
    await page.click('#devices-btn')
    await page.wait_for_timeout(400)
    libs = await page.inner_text('#devices-libraries') if await page.locator('#devices-libraries').count() else ''
    print("the devices dialog opens and lists the library:", 'Household' in libs, repr(libs))
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(200)
    await page.click('#tools-btn')
    print("Delete this library is still offered:", await page.locator('#delete-library-btn').is_visible())
    await page.click('#delete-library-btn')
    await page.wait_for_timeout(400)
    print("...and opens its dialog:", await page.locator('#delete-library-body').count() == 1)
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(200)
    await browser.close()
    # Share is offered for a library that is not synced yet.
    browser, page, errors = await open_app(p, sync_file=False, sync={"token": "admin-tok"})
    await page.click('#tools-btn')
    await page.wait_for_timeout(400)
    print("Share this library is offered for a library that isn't shared yet:", await page.locator('#share-library-btn').is_visible())
    print("no page errors:", not errors, errors)
    await browser.close()


async def main():
    import sys
    only = sys.argv[1:]
    async with async_playwright() as p:
        for scenario in (scenario_synced_save, scenario_base_follows_loaded_version, scenario_guard, scenario_newer_reloads,
                         scenario_poll_reads_state, scenario_poll_deleted, scenario_no_sync_file, scenario_devices_dialog):
            if only and not any(o in scenario.__name__ for o in only):
                continue
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
