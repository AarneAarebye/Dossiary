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

async def tick(page):
    await page.evaluate(f"window.__DEBUG_syncNow()")
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
    await tick(page)
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


# ---- Carried over from test_sync_lease.py (deleted with the lease): the behaviour that survives the cut ----

async def sort_on_disk(page, key='title'):
    return await page.evaluate("async (k) => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).settings.some(r => r.key === 'sort_key' && r.value === k)", key)


async def disk_file_hash(page, id):
    return await page.evaluate("async (id) => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).documents.find(d => d.id === id).file_hash", id)


async def file_text(page, path):
    return await page.evaluate("""async (path) => {
        let dir = window.__TEST_ROOT; const parts = path.split('/');
        for(const p of parts.slice(0, -1)){ dir = dir._children.get(p); if(!dir) return null; }
        const h = dir._children.get(parts[parts.length - 1]);
        return h ? await (await h.getFile()).text() : null;
    }""", path)


async def unload_asks(page):
    return await page.evaluate("() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }")


async def scenario_no_token(p):
    # (test_sync_lease: no_token, cancel_followups) No admin token: written at once, nothing warned about, Switch
    # library switches without asking.
    browser, page, errors = await open_app(p, token=None)
    await edit_title(page, 'Unconnected change')
    print("no token: the change is written:", await saved_title(page) == 'Unconnected change')
    print("...with no admin calls:", await admin_calls(page) == [])
    print("...no 'not saved' on the status line:", 'not saved' not in (await status(page)).lower(), await status(page))
    print("...closing the tab asks nothing:", not await unload_asks(page))
    print("...the base marker is written:", marker_ok(await base_marker(page), 3), await base_marker(page))
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    print("...Switch library switches at once:", await page.locator('#empty-state').is_visible())
    print("...and beforeunload still asks nothing:", not await unload_asks(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_service_down(p):
    # (service_down, job_data_retried) The service not answering: a person's change and a job's data are written at
    # once, with the base marker; nothing says "not saved".
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "down": True})
    await edit_title(page, 'Down change')
    print("service down: the change is written:", await disk_doc_title(page, 1) == 'Down change')
    print("...and no 'Not saved' on the status line:", 'Not saved' not in await status(page), await status(page))
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    await edit_title(page, 'Down again')
    print("...a second edit is written too:", await disk_doc_title(page, 1) == 'Down again')
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET file_hash = ? WHERE id = ?', ['abc', 2])")
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    st = await sync_state(page)
    print("...a job's data is written at once:", await disk_file_hash(page, 2) == 'abc' and not st['dirty'], st)
    print("...with the base marker:", marker_ok(await base_marker(page), 3), await base_marker(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_backup(p):
    # (backup) A backup leaves the sync bookkeeping out.
    browser, page, errors = await open_app(p, extra_files={'.kept-aside/2026-05-03/library.sqlite': 'old', 'files/1_a.pdf': 'pdf',
                                                           '.dossiary-base.json': '{"version": 3, "sha256": "x"}'})
    await page.evaluate("() => { window.__BACKUP_PARENT = window.__makeEmptyRoot(); window.__NEXT_PICKED_DIR = window.__BACKUP_PARENT; }")
    await page.route('https://cdn.jsdelivr.net/gh/**', lambda route: route.abort())
    await page.click('#tools-btn'); await page.click('#backup-btn')
    await page.wait_for_timeout(200)
    await page.click('#backup-start-btn')
    await page.wait_for_timeout(800)
    copied = await page.evaluate("""async () => {
        let name; for await (const [k] of window.__BACKUP_PARENT.entries()) name = k;
        const out = [];
        const walk = async (dir, prefix) => { for await (const [n, h] of dir.entries()){ if(h.kind === 'directory') await walk(h, prefix + n + '/'); else out.push(prefix + n); } };
        await walk(await window.__BACKUP_PARENT.getDirectoryHandle(name), '');
        return out.sort();
    }""")
    print("a backup has no .dossiary-sync.json:", '.dossiary-sync.json' not in copied, copied)
    print("...and no .kept-aside:", not any(c.startswith('.kept-aside') for c in copied))
    print("...and no base marker (.dossiary-base.json):", '.dossiary-base.json' not in copied)
    print("...but has the library:", 'library.sqlite' in copied and 'files/1_a.pdf' in copied)
    errors = [e for e in errors if 'ERR_FAILED' not in e]
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_reload_keeps_view(p):
    # (reload_keeps_view, reload_keeps_scroll) A reload keeps what the person is looking at.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.click('#nav-item-inbox')
    await page.wait_for_timeout(150)
    await page.select_option('#category-filter', 'Mail')
    await page.fill('#search', 'Lette')
    await page.wait_for_timeout(150)
    await page.click('tr[data-id="3"]')
    await page.wait_for_timeout(150)
    await tick(page)
    print("same version: no reload:", (await sync_state(page))['reloads'] == 0)
    await disk_change(page, {3: 'Letter from the bank'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    print("a newer version reloads: the detail panel shows it:", 'Letter from the bank' in await page.inner_text('#detail-panel-body'))
    print("...the Inbox view is kept:", await page.evaluate("document.getElementById('nav-item-inbox').classList.contains('active')"))
    print("...the category filter is kept:", await page.input_value('#category-filter') == 'Mail')
    print("...the filtered list still applies (Leaflet hidden):", await page.locator('tr[data-id="4"]').count() == 0)
    print("...the selection is kept:", await page.evaluate("!!document.querySelector('tr[data-id=\"3\"].row-selected')"))
    await tick(page)
    print("...and the next poll doesn't reload again:", (await sync_state(page))['reloads'] == 1)
    print("no page errors:", not errors, errors)
    await browser.close()
    seed = {"documents": [doc(i, f"Document {i:02d}") for i in range(1, 61)]}
    browser, page, errors = await open_app(p, seed=seed, sync={"token": "admin-tok", "state": state(3)}, height=700)
    await page.evaluate("document.getElementById('table-wrap').scrollTop = 400")
    await page.wait_for_timeout(100)
    top = await page.evaluate("document.getElementById('table-wrap').scrollTop")
    await disk_change(page, {1: 'Document one'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    after = await page.evaluate("document.getElementById('table-wrap').scrollTop")
    print("reload keeps the table's scroll position:", top > 100 and abs(after - top) < 2 and (await sync_state(page))['reloads'] == 1, top, after)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_reload_waits_for_dialog(p):
    # (reload_waits_for_dialog) No reload under an open form; the next poll after it closes reloads.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await open_edit(page)
    await disk_change(page, {1: 'Invoice B'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    print("Edit form open: no reload:", (await sync_state(page))['reloads'] == 0 and 'Invoice B' not in await row_text(page, 1))
    print("...the form is still there:", await page.locator('#e-title').count() == 1)
    await page.click('#cancel-edit-btn')
    await page.wait_for_timeout(150)
    await tick(page)
    print("after it closes the next poll reloads:", (await sync_state(page))['reloads'] == 1 and 'Invoice B' in await row_text(page, 1))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_edit_on_newer_version(p):
    # (acquire_newer_version) Opening Edit while the sync file names a newer version reloads first; the save lands on it.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await open_edit(page)
    st = await sync_state(page)
    print("opening Edit on a newer version reloads before the form opens:", st['reloads'] == 1 and st['version'] == 4 and 'Receipt (iMac)' in await row_text(page, 2), st)
    print("...then the form opens:", await page.locator('#e-title').count() == 1)
    await page.fill('#e-title', 'Edited here')
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(400)
    print("the newer version's content survives:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    print("...and this tab's change is on top of it:", await disk_doc_title(page, 1) == 'Edited here')
    print("...nothing kept aside:", not await kept_aside_names(page))
    print("...'Saved' shown:", 'Saved' in await status(page))
    print("...the base marker names version 4:", marker_ok(await base_marker(page), 4), await base_marker(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_guard_more(p):
    # (safety_net, base_marker) The guard a second and a third time: each keep-aside gets its own folder, a
    # background save is kept aside quietly, and keep-aside copies get no base marker.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    print("opening writes no base marker:", await base_marker(page) is None)
    await edit_title(page, 'Before')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    before = await base_marker(page)
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Mine (old base)', 1])")
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    ok = await page.evaluate("window.__DEBUG_persistDb()")
    await page.wait_for_timeout(500)
    names = await kept_aside_names(page)
    print("guard: persistDb() answers false and keeps memory aside:", ok is False and len(names) == 1 and await kept_aside_title(page, names[0]) == 'Mine (old base)', ok, names)
    print("...the status line names the folder too:", bool(names) and f'.kept-aside/{names[0]}' in await status(page), await status(page))
    print("...the copy has no base marker of its own:", bool(names) and await base_marker(page, '.kept-aside/' + names[0] + '/.dossiary-base.json') is None)
    after = await base_marker(page)
    print("...the live marker is still the one from the last live write:", before is not None and after is not None and (after['version'], after['sha256']) == (before['version'], before['sha256']))
    await page.click('#sync-notice-ok-btn')
    await page.wait_for_timeout(150)
    print("...OK closes the notice:", await page.locator('#sync-notice-dialog').count() == 0)
    # A second time never overwrites the first folder.
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Mine again', 1])")
    await disk_change(page, {2: 'Receipt (iMac 2)'}, sync_version=5)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(5))
    await tick(page)
    await page.evaluate("window.__DEBUG_persistDb()")
    await page.wait_for_timeout(500)
    names2 = await kept_aside_names(page)
    print("a second one gets its own folder:", len(names2) == 2 and names[0] in names2, names2)
    if await page.locator('#sync-notice-ok-btn').count():
        await page.click('#sync-notice-ok-btn')
        await page.wait_for_timeout(150)
    # A background job's save behind a newer version: kept aside quietly, no notice.
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(6))
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET file_hash = ? WHERE id = ?', ['abc', 2])")
    await disk_change(page, {2: 'Receipt (iMac 3)'}, sync_version=6)
    await tick(page)
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    await page.wait_for_timeout(500)
    names3 = await kept_aside_names(page)
    quiet = [n for n in names3 if n not in names2]
    print("a background save behind a newer version: kept aside in a folder of its own, no notice:", len(quiet) == 1 and await page.locator('#sync-notice-dialog').count() == 0, names3)
    print("...the copy holds this tab's memory (the job's data with it):", bool(quiet) and await page.evaluate("""async (n) => JSON.parse(await (await window.__TEST_ROOT._children.get('.kept-aside')._children.get(n)._children.get('library.sqlite').getFile()).text()).documents.find(d => d.id === 2).file_hash""", quiet[0]) == 'abc')
    st = await status(page)
    print("...a plain status line names the folder:", bool(quiet) and f'.kept-aside/{quiet[0]}' in st and 'please make it again' not in st, st)
    print("...the newer version is loaded:", 'Receipt (iMac 3)' in await row_text(page, 2))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_form_open_newer_arrives(p):
    # (sleep_lost_lease, dialog_open_refuses) An Edit form open on v3 while v4 arrives: Field Settings from it is
    # refused, and Save keeps the typed change aside instead of writing over v4.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await open_edit(page)
    await page.fill('#e-title', 'Typed on the old version')
    await disk_change(page, {1: 'Invoice (iMac)', 2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    await page.click('#e-type-fields-btn')
    await page.wait_for_timeout(400)
    st = await sync_state(page)
    print("Set up fields from the stale Edit form: no reload under it:", st['reloads'] == 0 and st['version'] == 3, st)
    print("...Field Settings doesn't open:", await page.evaluate("document.getElementById('modal-root-over').innerHTML === ''"))
    print("...the status line says to close and start again:", 'close this dialog and start again' in await status(page), await status(page))
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(600)
    print("...Save then doesn't write over the iMac's version:", await disk_doc_title(page, 1) == 'Invoice (iMac)' and await disk_doc_title(page, 2) == 'Receipt (iMac)')
    names = await kept_aside_names(page)
    print("...the typed change is kept aside:", len(names) == 1 and await kept_aside_title(page, names[0]) == 'Typed on the old version', names)
    print("...and the iMac's version is loaded:", 'Receipt (iMac)' in await row_text(page, 2))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_library_check_stale(p):
    # (library_check_stale) Library check's lists come from v3; v4 uses the "orphaned" tag again.
    seed = dict(SEED2); seed["tags"] = [{"id": 1, "name": "old"}]
    browser, page, errors = await open_app(p, seed=seed, sync={"token": "admin-tok", "state": state(3)})
    page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
    await page.click('#tools-btn'); await page.click('#library-check-btn')
    await page.wait_for_timeout(600)
    await page.evaluate("""async () => {
        const root = window.__TEST_ROOT, h = root._children.get('library.sqlite');
        const data = JSON.parse(await (await h.getFile()).text());
        data.document_tags = [{ document_id: 2, tag_id: 1 }];
        h._bytes = new TextEncoder().encode(JSON.stringify(data));
        const f = root._children.get('.dossiary-sync.json');
        f._bytes = new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-7f3a', hub: 'x', version: 4 }));
    }""")
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    btn = page.locator('.orphaned-row button').first
    print("Library check lists the tag as orphaned:", await btn.count() == 1)
    await btn.click()
    await page.wait_for_timeout(600)
    disk = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text())")
    print("Delete after a foreign version bump: the other device's tag survives:", any(t['name'] == 'old' for t in disk['tags']) and disk['document_tags'] == [{"document_id": 2, "tag_id": 1}], disk.get('tags'), disk.get('document_tags'))
    print("...the status line says to close and start again:", 'close this dialog and start again' in await status(page), await status(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_reload_refused(p):
    # (reload_refused) The reload a gated action needs is refused (a background job runs) -> the action doesn't start.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.click('tr[data-id="1"]')
    await page.wait_for_timeout(150)
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("window.__DEBUG_syncBackgroundBusy(true)")
    await page.click('#archive-toggle-btn')
    await page.wait_for_timeout(500)
    disk = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text())")
    print("reload refused: the archive doesn't start:", not disk['documents'][0]['archived'] and await kept_aside_names(page) == [])
    print("...the status line says the library is updating:", await status(page) == 'The library is updating — try again in a moment.', await status(page))
    await page.evaluate("window.__DEBUG_syncBackgroundBusy(false)")
    await page.click('#archive-toggle-btn')
    await page.wait_for_timeout(500)
    disk = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text())")
    print("...once free, it reloads and archives on the newer version:", disk['documents'][0]['archived'] and disk['documents'][1]['title'] == 'Receipt (iMac)')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_person_change_not_dropped(p):
    # (person_change_not_dropped) A person's flow is mid-way when a job's save meets a newer version.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.evaluate("window.__DEBUG_ensureCurrentVersion()")
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Person change', 1])")
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    await page.wait_for_timeout(600)
    names = await kept_aside_names(page)
    print("a job's save during a person's flow: the person's change is kept aside, not dropped:", len(names) == 1 and await kept_aside_title(page, names[0]) == 'Person change', names)
    print("...nothing written over the iMac's version:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    print("...and the notice says so:", await page.locator('#sync-notice-dialog').count() == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def drop_files(page, names):
    parts = ",".join(f"new File([new TextEncoder().encode({('dropped:' + n)!r})], {n!r}, {{type: 'application/pdf'}})" for n in names)
    await page.evaluate(f"""() => {{
        const dt = new DataTransfer();
        [{parts}].forEach(f => dt.items.add(f));
        document.dispatchEvent(new DragEvent('drop', {{ bubbles: true, cancelable: true, dataTransfer: dt }}));
    }}""")


async def where_titles(page, titles):
    """For each title: 'library' if library.sqlite holds it, else the .kept-aside folder that does, else None."""
    return await page.evaluate("""async (titles) => {
        const root = window.__TEST_ROOT;
        const read = async (h) => JSON.parse(await (await h.getFile()).text()).documents.map(d => d.title);
        const live = await read(root._children.get('library.sqlite'));
        const kept = [];
        const k = root._children.get('.kept-aside');
        if(k) for await (const [n, d] of k.entries()) kept.push([n, await read(d._children.get('library.sqlite'))]);
        const out = {};
        for(const t of titles){
            if(live.includes(t)) out[t] = 'library';
            else { const hit = kept.find(([, ts]) => ts.includes(t)); out[t] = hit ? hit[0] : null; }
        }
        return out;
    }""", titles)


# Another device changes the library while this tab's drop is mid-way: the hub is at v4, and a job's save comes
# along. Installed on the files folder: when the active copy of a file is about to be written (after the gate,
# before its INSERT) a tick can run; when its sidecar is (after its INSERT, before its own save) v4 lands, the poll
# sees it and a job's save runs.
HOOK_FILES = """([copyName, sidecarName, tickBeforeCopy]) => {
    const files = window.__TEST_ROOT._children.get('files');
    const orig = files.getFileHandle.bind(files);
    window.__HOOK_LOG = [];
    files.getFileHandle = async (name, opts) => {
        if(tickBeforeCopy && name.endsWith(copyName) && !window.__HOOK_COPY_DONE){
            window.__HOOK_COPY_DONE = true;
            await window.__DEBUG_syncNow();          // a tick between the gate and the first INSERT
            window.__HOOK_LOG.push('tick');
        }
        if(name.endsWith(sidecarName) && !window.__HOOK_SIDECAR_DONE){
            window.__HOOK_SIDECAR_DONE = true;
            const root = window.__TEST_ROOT;
            const h = root._children.get('library.sqlite');
            const data = JSON.parse(await (await h.getFile()).text());
            data.documents.find(x => x.id === 2).title = 'Receipt (iMac)';
            h._bytes = new TextEncoder().encode(JSON.stringify(data));
            root._children.get('.dossiary-sync.json')._bytes = new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-7f3a', hub: 'https://pi.local:8443', version: 4 }));
            window.__SYNC.state = { libraryId: 'lib-7f3a', version: 4, hubReachable: true, lease: null, offline: false, keptAside: [], lastError: null };
            await window.__DEBUG_syncNow();          // the poll: v4 exists
            window.__HOOK_LOG.push('job:' + await window.__DEBUG_persistDb({ background: true }));   // a job's save, behind
            await new Promise(r => setTimeout(r, 400));   // the sidecar write takes a while (iCloud)
        }
        return orig(name, opts);
    };
}"""


async def scenario_drops_meet_newer(p):
    # (multi_drop_job_save, tick_before_insert) A drop mid-way when a job's save meets a newer version.
    browser, page, errors = await open_app(p, seed=SEED2)
    await page.evaluate(HOOK_FILES, ['_two.pdf', '_two.txt', False])
    await drop_files(page, ['one.pdf', 'two.pdf'])
    await page.wait_for_timeout(1500)
    log = await page.evaluate("window.__HOOK_LOG")
    print("the job's save ran between file 2's INSERT and its save:", any(x.startswith('job:') for x in log), log)
    where = await where_titles(page, ['one', 'two'])
    print("file 1 is in the library or a kept-aside copy:", where['one'] is not None, where)
    print("file 2's row survives, in the library or a kept-aside copy (never silently lost):", where['two'] is not None, where)
    print("...nothing written over the iMac's version:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    print("...the notice is shown (a person's flow was running):", await page.locator('#sync-notice-dialog').count() == 1)
    st = await status(page)
    print("...the drop's own final status names the kept-aside folder:", bool(where['two']) and where['two'] != 'library' and f'.kept-aside/{where["two"]}' in st and 'Added 2 documents' in st, st)
    print("no page errors:", not errors, errors)
    await browser.close()
    browser, page, errors = await open_app(p, seed=SEED2)
    await page.evaluate(HOOK_FILES, ['_solo.pdf', '_solo.txt', True])
    await drop_files(page, ['solo.pdf'])
    await page.wait_for_timeout(1500)
    log = await page.evaluate("window.__HOOK_LOG")
    print("a tick ran before the INSERT and a job's save after it:", log[:1] == ['tick'] and any(x.startswith('job:') for x in log), log)
    where = await where_titles(page, ['solo'])
    print("the dropped document survives, in the library or a kept-aside copy (never silently lost):", where['solo'] is not None, where)
    print("...nothing written over the iMac's version:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_quiet_copy_reused(p):
    # (quiet_copy_reused) Quiet copies while a job blocks the reload: one folder, updated in place.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok"})
    await page.evaluate("window.__DEBUG_syncBackgroundBusy(true)")
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    for h in ['h1', 'h2']:
        await page.evaluate(f"window.__DEBUG_dbRun('UPDATE documents SET file_hash = ? WHERE id = ?', ['{h}', 1])")
        await page.evaluate("window.__DEBUG_persistDb({ background: true })")
        await page.wait_for_timeout(200)
    names = await kept_aside_names(page)
    latest = names and await page.evaluate("""async (n) => JSON.parse(await (await window.__TEST_ROOT._children.get('.kept-aside')._children.get(n)._children.get('library.sqlite').getFile()).text()).documents.find(d => d.id === 1).file_hash""", names[0])
    print("two quiet saves behind the same version: one folder with the latest memory:", len(names) == 1 and latest == 'h2', names, latest)
    print("...nothing written over the iMac's version:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    await page.evaluate("window.__DEBUG_syncBackgroundBusy(false)")
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    await page.wait_for_timeout(300)
    print("...once the job ends the newer version loads:", 'Receipt (iMac)' in await row_text(page, 2))
    print("no notice for a job's data:", await page.locator('#sync-notice-dialog').count() == 0)
    print("no page errors:", not errors, errors)
    await browser.close()


# A db.run during the reload's own awaits: the hook runs a person's change inside crypto.subtle.digest the first
# time an algorithm matching `algo` is hashed after it's armed.
DIGEST_HOOK = """([algo, sql, params]) => {
    const orig = crypto.subtle.digest.bind(crypto.subtle);
    window.__DIGEST_FIRED = 0;
    crypto.subtle.digest = async (alg, data) => {
        const r = await orig(alg, data);
        if(window.__DIGEST_ARMED && String(alg).toUpperCase() === algo){
            window.__DIGEST_ARMED = false;
            window.__DIGEST_FIRED++;
            window.__DEBUG_dbRun(sql, params);
        }
        return r;
    };
}"""

SEED_FIELDS = dict(SEED2, fields=[{"id": 12, "name": "Organization", "type": "text", "show_as_column": 0, "autocomplete": 1}])


async def scenario_reload_race(p):
    # (reload_race, reload_giveup_field_maps) A change during the reload's awaits: the reload gives up, nothing lost.
    for algo, label in [('SHA-256', "the file's hash"), ('SHA-1', 'the stable-uid migration')]:
        browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok"})
        await page.evaluate(DIGEST_HOOK, [algo, 'UPDATE documents SET title = ? WHERE id = ?', ['Changed during reload', 1]])
        await page.evaluate("""async (dropUid) => {
            const h = window.__TEST_ROOT._children.get('library.sqlite');
            const data = JSON.parse(await (await h.getFile()).text());
            data.documents.find(x => x.id === 2).title = 'Receipt (iMac)';
            if(dropUid) data.documents.find(x => x.id === 4).uid = null;
            h._bytes = new TextEncoder().encode(JSON.stringify(data));
        }""", algo == 'SHA-1')
        await page.evaluate("(s) => { window.__SYNC.state = s; window.__DIGEST_ARMED = true; }", state(4))
        await tick(page)
        await page.wait_for_timeout(300)
        fired = await page.evaluate("window.__DIGEST_FIRED")
        st = await sync_state(page)
        print(f"[{label}] a person's change lands during the reload's await:", fired == 1, fired)
        print(f"[{label}] ...the reload gave up: it's still in memory and counted as unwritten:", st['reloads'] == 0 and st['dirty'], st)
        await page.evaluate("window.__DEBUG_persistDb()")
        await page.wait_for_timeout(600)
        where = await where_titles(page, ['Changed during reload'])
        print(f"[{label}] ...the next save keeps it (library or a kept-aside copy):", where['Changed during reload'] is not None, where)
        print(f"[{label}] ...the iMac's version isn't overwritten:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
        print(f"[{label}] no page errors:", not errors, errors)
        await browser.close()
    browser, page, errors = await open_app(p, seed=SEED_FIELDS, sync={"token": "admin-tok"})
    before = await page.evaluate("window.__DEBUG_findFieldByName('Organization')")
    await page.evaluate(DIGEST_HOOK, ['SHA-1', 'UPDATE documents SET title = ? WHERE id = ?', ['Changed during reload', 1]])
    await page.evaluate("""async () => {
        const h = window.__TEST_ROOT._children.get('library.sqlite');
        const data = JSON.parse(await (await h.getFile()).text());
        data.fields.find(f => f.id === 12).name = 'Warranty';
        data.documents.find(x => x.id === 4).uid = null;
        h._bytes = new TextEncoder().encode(JSON.stringify(data));
    }""")
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__DIGEST_ARMED = true; }", state(4))
    await tick(page)
    await page.wait_for_timeout(300)
    st = await sync_state(page)
    print("the reload gave up (a person's change during its await):", await page.evaluate("window.__DIGEST_FIRED") == 1 and st['reloads'] == 0, st)
    org = await page.evaluate("window.__DEBUG_findFieldByName('Organization')")
    war = await page.evaluate("window.__DEBUG_findFieldByName('Warranty')")
    print("...the field maps still describe this tab's database (Organization is 12, no Warranty):", bool(before and org and org['id'] == 12 and war is None), org, war)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_doc_ids(p):
    # (drop_skips_foreign_ids, reserved_ids) New document ids skip other devices' files and ids in flight.
    foreign = {'files/5_Scan.pdf': 'IMAC-5', 'thumbnails/5.jpg': 'IMAC-THUMB-5', 'files/6_Other.pdf': 'IMAC-6'}
    browser, page, errors = await open_app(p, seed=SEED2, extra_files=foreign)
    await drop_files(page, ['Scan.pdf', 'Other.pdf', 'third.pdf'])
    await page.wait_for_timeout(1500)
    kept = {path: await file_text(page, path) for path in foreign}
    print("the other device's files, original and preview are not written over:", kept == foreign, {k: (v or '')[:20] for k, v in kept.items()})
    ids = await page.evaluate("""async () => {
        const data = JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text());
        return data.documents.filter(d => d.source === 'dropped').map(d => [d.title, d.id]);
    }""")
    got = dict(ids)
    print("all three dropped documents are added:", sorted(got) == ['Other', 'Scan', 'third'], ids)
    print("...on free ids, none of the other device's:", bool(got) and not ({5, 6} & set(got.values())) and len(set(got.values())) == 3, ids)
    print("no page errors:", not errors, errors)
    await browser.close()

    foreign = {'files/5_Scan.pdf': 'IMAC-5', 'thumbnails/6.jpg': 'IMAC-THUMB-6', 'files/7_x/orig.pdf': 'IMAC-7'}
    browser, page, errors = await open_app(p, seed=SEED2, extra_files=foreign)
    await page.evaluate("""() => {
        window.__WALKS = 0;
        const files = window.__TEST_ROOT._children.get('files');
        const orig = files.entries.bind(files);
        files.entries = (...a) => { window.__WALKS++; return orig(...a); };
    }""")
    r1 = await page.evaluate("window.__DEBUG_reserveDocId()")
    walks = await page.evaluate("window.__WALKS")
    print("reserving skips every id with files on disk:", r1['id'] == 8, r1)
    print("...walking files/ once, not once per id:", walks == 1, walks)
    await page.evaluate("(r) => window.__DEBUG_releaseDocId(r)", r1)
    print("releasing the last reservation gives its id back:", await page.evaluate("window.__DEBUG_nextDocId()") == 8)
    a = await page.evaluate("window.__DEBUG_reserveDocId()")
    b = await page.evaluate("window.__DEBUG_reserveDocId()")
    await page.evaluate("(r) => window.__DEBUG_releaseDocId(r)", a)
    c = await page.evaluate("window.__DEBUG_reserveDocId()")
    print("...but not when a later one was reserved after it:", (a['id'], b['id'], c['id']) == (8, 9, 10), a, b, c)
    print("check with no reload in between passes:", (await page.evaluate("(r) => window.__DEBUG_checkReservedDocId(r)", b))['ok'])
    await browser.close()

    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    res = await page.evaluate("window.__DEBUG_reserveDocId()")
    other = await page.evaluate("window.__DEBUG_reserveDocId()")
    await page.evaluate("""async (id) => {
        const h = window.__TEST_ROOT._children.get('library.sqlite');
        const data = JSON.parse(await (await h.getFile()).text());
        data.documents.push(Object.assign({}, data.documents[0], { id, title: 'iMac doc', uid: null }));
        h._bytes = new TextEncoder().encode(JSON.stringify(data));
    }""", res['id'])
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    print("a reload brought another device's row with the reserved id:", (await sync_state(page))['reloads'] == 1 and 'iMac doc' in await row_text(page, res['id']))
    chk = await page.evaluate("(r) => window.__DEBUG_checkReservedDocId(r)", res)
    print("...checking the reservation refuses it as taken:", not chk['ok'] and chk['idTaken'] and 'changed on another Mac' in chk['message'], chk)
    n = await page.evaluate("window.__DEBUG_nextDocId()")
    await page.evaluate("(r) => window.__DEBUG_releaseDocId(r)", res)
    print("...releasing it after the reload leaves the counter alone:", await page.evaluate("window.__DEBUG_nextDocId()") == n)
    chk2 = await page.evaluate("(r) => window.__DEBUG_checkReservedDocId(r)", other)
    print("an id the reload didn't bring passes, the counter kept past it:", chk2['ok'] and await page.evaluate("window.__DEBUG_nextDocId()") > other['id'], chk2)
    await browser.close()

    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    first = await page.evaluate("window.__DEBUG_reserveDocId()")
    await disk_change(page, {2: 'Receipt (iMac)'})
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    second = await page.evaluate("window.__DEBUG_reserveDocId()")
    print("after a reload, an id in flight isn't reserved again:", (await sync_state(page))['reloads'] == 1 and second['id'] != first['id'], first, second)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_open_race(p):
    # (open_race) A pull swaps in v4 right after this tab read library.sqlite: memory never counts as v4.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(4)})
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    await page.evaluate("""() => {
        const root = window.__TEST_ROOT;
        const h = root._children.get('library.sqlite');
        const orig = h.getFile.bind(h);
        let swapped = false;
        h.getFile = async () => {
            const f = await orig();
            if(!swapped){
                swapped = true;   // the pull lands between this read and the sync file's
                const data = JSON.parse(await f.text());
                data.documents.find(d => d.id === 2).title = 'Receipt (iMac)';
                h._bytes = new TextEncoder().encode(JSON.stringify(data));
                root._children.get('.dossiary-sync.json')._bytes = new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-7f3a', hub: 'x', version: 4 }));
            }
            return f;
        };
        window.__DB_WRITES = 0;
    }""")
    await page.click('#open-btn')
    await page.wait_for_timeout(500)
    print("opening a synced library writes nothing (migrations stay in memory):", await writes(page) == 0, await writes(page))
    print("...the iMac's version on disk survives opening:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    st = await sync_state(page)
    print("...memory isn't taken for version 4:", st['version'] == 3 and not st['dirty'], st)
    await tick(page)
    print("the next poll reloads the iMac's version:", 'Receipt (iMac)' in await row_text(page, 2) and (await sync_state(page))['version'] == 4)
    await edit_title(page, 'Mine on top')
    print("...an edit then lands on top of it:", await disk_doc_title(page, 2) == 'Receipt (iMac)' and await disk_doc_title(page, 1) == 'Mine on top')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_no_reload_while_opening(p):
    # (no_reload_while_opening) The poll never reloads while loadDb() is still opening the library.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    await page.evaluate("""() => {
        const orig = crypto.subtle.digest.bind(crypto.subtle);
        let calls = 0;
        window.__OPEN_PAUSED = false;
        window.__OPEN_GATE = new Promise(r => { window.__OPEN_RELEASE = r; });
        crypto.subtle.digest = async (...a) => {
            calls++;
            if(calls === 2){ window.__OPEN_PAUSED = true; await window.__OPEN_GATE; }
            return orig(...a);
        };
    }""")
    await page.click('#open-btn')
    await page.wait_for_timeout(300)
    print("opening paused after the database was set up:", await page.evaluate("window.__OPEN_PAUSED"))
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await page.evaluate("window.__DEBUG_syncNow()")
    await page.wait_for_timeout(300)
    print("a tick while opening doesn't reload:", (await sync_state(page))['reloads'] == 0, await sync_state(page))
    await page.evaluate("window.__OPEN_RELEASE()")
    await page.wait_for_timeout(400)
    await tick(page)
    st = await sync_state(page)
    print("...once open, the next tick reloads version 4:", st['reloads'] == 1 and st['version'] == 4 and 'Receipt (iMac)' in await row_text(page, 2), st)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_sync_read_before_writes(p):
    # (sync_read_before_writes) A write right after opening waits for the sync file to be read, so it is marked.
    browser, page, errors = await open_app(p, seed=SEED2, sync_file=False)
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    await page.evaluate("""async () => {
        const root = window.__TEST_ROOT;
        const w = await (await root.getFileHandle('.dossiary-sync.json', { create: true })).createWritable();
        await w.write(new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-7f3a', hub: 'x', version: 3 }))); await w.close();
        const orig = root.getFileHandle.bind(root);
        root.getFileHandle = async (name, o) => { if(name === '.dossiary-sync.json') await new Promise(r => setTimeout(r, 400)); return orig(name, o); };
    }""")
    await page.click('#open-btn')
    await page.wait_for_timeout(30)
    await page.evaluate("window.__DEBUG_persistDb()")
    await page.wait_for_timeout(600)
    print("a real write right after opening waits for the sync file and writes the base marker:", marker_ok(await base_marker(page), 3), await base_marker(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_view_prefs(p):
    # (view_write_newer_on_disk, view_prefs_not_holding, first_change) A view preference in a synced library stays
    # in memory (a pull may be running) and goes out with the next real save; meeting a newer version, it reloads.
    browser, page, errors = await open_app(p, seed=SEED2)
    w = await writes(page)
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(300)
    print("view preference in a synced library: not written:", await writes(page) == w and not await sort_on_disk(page))
    print("...but applied in this window:", await page.evaluate("document.querySelector('th[data-key=\"title\"]').classList.contains('active')"))
    await edit_title(page, 'Real change')
    print("...and written with the next real save:", await sort_on_disk(page) and await disk_doc_title(page, 1) == 'Real change')
    await browser.close()
    browser, page, errors = await open_app(p, seed=SEED2)
    await disk_change(page, {2: 'Receipt (pulled)'}, sync_version=4)
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(400)
    print("view-only write with a newer version on disk: the pulled file survives:", await disk_doc_title(page, 2) == 'Receipt (pulled)')
    print("...the library reloads instead:", 'Receipt (pulled)' in await row_text(page, 2) and (await sync_state(page))['version'] == 4)
    print("...the sort is still applied, kept in memory:", not await sort_on_disk(page) and await page.evaluate("document.querySelector('th[data-key=\"title\"]').classList.contains('active')"))
    await edit_title(page, 'Edited')
    print("...and written with the next real save:", await sort_on_disk(page) and await disk_doc_title(page, 2) == 'Receipt (pulled)')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_kept_aside(p):
    # (kept_aside, german_task2) The service's kept-aside versions: one status line each, a reload, remembered.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await disk_change(page, {1: 'Invoice (Pi)'})
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(3, None, KEPT))
    await tick(page)
    print("kept aside: one status line:", await status(page) == KEPT_TEXT, await status(page))
    print("...and the library reloads (the folder was replaced):", 'Invoice (Pi)' in await row_text(page, 1))
    seen = await page.evaluate("localStorage.getItem('dossiary_kept_aside_seen')")
    print("...the stamp is remembered:", seen is not None and 'MacBook Pro-2026-05-03-1402' in seen, seen)
    await page.evaluate("document.getElementById('status').textContent = ''")
    await tick(page)
    print("...not repeated on the next poll:", await status(page) == '')
    await page.reload()
    await page.wait_for_timeout(200)
    await seed_and_open(page, {"token": "admin-tok", "state": state(3, None, KEPT)}, seed=SEED2)
    await tick(page)
    print("...not repeated after reopening the page:", 'kept safe' not in await status(page), await status(page))
    await page.click('#tools-btn'); await page.click('#devices-btn')
    await page.wait_for_timeout(400)
    libs = await page.inner_text('#devices-libraries') if await page.locator('#devices-libraries').count() else ''
    print("the devices dialog shows it under the library:", 'Household' in libs and KEPT_TEXT in libs, repr(libs))
    print("no page errors:", not errors, errors)
    await browser.close()
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, None, KEPT)}, lang='de')
    await tick(page)
    print("German kept-aside line:", await status(page) == "Änderungen, die am 03. Mai 2026 auf diesem Mac gemacht wurden, ließen sich nicht mit denen von iMac zusammenführen. Sie sind sicher aufbewahrt und werden durch ein späteres Update zusammengeführt.", await status(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_export_leaves_sync_files(p):
    # (export_open_asks) Export as library writes no sync file and no base marker into the new library.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)},
                                           extra_files={'files/1_a.pdf': 'pdf 1', '.dossiary-base.json': '{"version": 3, "sha256": "x"}'})
    await page.evaluate("() => { window.__EXPORT_PARENT = window.__makeEmptyRoot(); window.__EXPORT_PARENT.name = 'Outside'; window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT; }")
    await page.check('tr[data-id="1"] .row-select-checkbox')
    await page.click('#bulk-more-btn')
    await page.click('#bulk-export-library-btn')
    await page.wait_for_timeout(300)
    await page.click('#export-library-start-btn')
    await page.wait_for_timeout(1000)
    print("exported:", await page.is_visible('#export-library-open-btn'))
    exported = await page.evaluate("""async () => {
        const out = [];
        let dir; for await (const [, h] of window.__EXPORT_PARENT.entries()) dir = h;
        if(!dir) return out;
        for await (const [n] of dir.entries()) out.push(n);
        return out.sort();
    }""")
    print("...the exported library has no sync file and no base marker:",
          'library.sqlite' in exported and '.dossiary-base.json' not in exported and '.dossiary-sync.json' not in exported, exported)
    errors = [e for e in errors if 'ERR_FAILED' not in e]
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_tokenless_write_pulled_over(p):
    # (leaseless_write_pulled_over) No token, so no poll reports the service's own keep-aside: an edit written, then a
    # pull of another device's version over it. Opening Edit (or a sort click) keeps the edit aside with the notice.
    browser, page, errors = await open_app(p, seed=SEED2, token=None)
    await edit_title(page, 'Lease-less edit')
    print("no token: the edit is written:", await disk_doc_title(page, 1) == 'Lease-less edit')
    await disk_change(page, {1: 'Invoice', 2: 'Receipt (iMac)'}, sync_version=4)
    await open_edit(page)
    names = await kept_aside_names(page)
    kept = bool(names) and await kept_aside_title(page, names[-1]) == 'Lease-less edit'
    print("...opening Edit after a pull over it keeps the edit in .kept-aside:", kept, names)
    notice = await page.inner_text('#sync-notice-dialog') if await page.locator('#sync-notice-dialog').count() else ''
    print("...a notice names the folder:", bool(names) and f'.kept-aside/{names[-1]}' in notice, repr(notice))
    print("...the library shows the newer version:", 'Receipt (iMac)' in await row_text(page, 2), await row_text(page, 2))
    if await page.locator('#sync-notice-ok-btn').count():
        await page.click('#sync-notice-ok-btn'); await page.wait_for_timeout(150)
    if await page.evaluate("document.getElementById('modal-root').innerHTML !== ''"):
        await page.keyboard.press('Escape'); await page.wait_for_timeout(150)
    await edit_title(page, 'Second lease-less edit')
    await disk_change(page, {1: 'Invoice', 2: 'Receipt (iMac 2)'}, sync_version=5)
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(600)
    names2 = await kept_aside_names(page)
    fresh = [n for n in names2 if n not in names]
    print("...a sort click after a pull over the next edit keeps it aside too:", len(fresh) == 1 and await kept_aside_title(page, fresh[0]) == 'Second lease-less edit', names2)
    print("...with the notice:", await page.locator('#sync-notice-dialog').count() == 1)
    print("...and the newer version loaded:", 'Receipt (iMac 2)' in await row_text(page, 2))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_token_write_then_foreign_reloads_quietly(p):
    # (leased_write_clears_leaseless_flag) With a token the state poll reports the service's own keep-aside, so after
    # an ordinary save (pushed as v4) another device's later version reloads quietly: no copy, no notice.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await edit_title(page, 'Mine, pushed')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    await page.evaluate("""() => {
        const f = window.__TEST_ROOT._children.get('.dossiary-sync.json');
        f._bytes = new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-7f3a', hub: 'https://pi.local:8443', version: 4 }));
    }""")
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    await disk_change(page, {1: 'Invoice (iMac)', 2: 'Receipt'}, sync_version=5)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(5))
    await tick(page)
    await tick(page)
    print("after a save, another device's version reloads quietly:", 'Invoice (iMac)' in await row_text(page, 1) and not await kept_aside_names(page)
          and await page.locator('#sync-notice-dialog').count() == 0, await kept_aside_names(page), await sync_state(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_token_rejected(p):
    # (disconnected_token_rejected) A 401 from the state poll forgets the token; edits are still written.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.evaluate("window.__SYNC.token = 'another-token'")
    await tick(page)
    print("a 401 forgets the token:", await page.evaluate(f"localStorage.getItem('{TOKEN_KEY}')") is None)
    await edit_title(page, 'After the 401')
    print("...edits are still written:", await disk_doc_title(page, 1) == 'After the 401')
    print("...with the base marker:", marker_ok(await base_marker(page), 3), await base_marker(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_ocr_job_runs(p):
    # (background_files) A file-writing background job (the OCR runner) runs in a synced library.
    seed = dict(SEED2)
    seed["ocr_jobs"] = [{"document_id": 1, "helper_url": None, "job_id": None, "file_hash": None,
                         "created_at": "2026-03-01T00:00:00Z", "ocr_language": "eng", "requested_by": "edit"}]
    browser, page, errors = await open_app(p, seed=seed, sync={"token": "admin-tok", "state": state(3)},
                                           extra_files={'files/1_a.pdf': 'pdf'})
    await page.evaluate("window.__DEBUG_holdOcrJobs(true)")
    await tick(page)
    await page.evaluate("window.__DEBUG_runOcrJobPass()")
    for _ in range(20):
        await page.wait_for_timeout(200)
        if await page.evaluate("window.__DEBUG_ocrJobRows().length") == 0: break
    print("a synced library: the OCR job runs:", await page.evaluate("window.__DEBUG_ocrJobRows().length") == 0)
    errors = [e for e in errors if 'ERR_FAILED' not in e]
    print("no page errors:", not errors, errors)
    await browser.close()


SET_SYNC_VERSION = """(v) => {
    const f = window.__TEST_ROOT._children.get('.dossiary-sync.json');
    f._bytes = new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-7f3a', hub: 'https://pi.local:8443', version: v }));
}"""


async def scenario_base_follows_own_push(p):
    # The base the marker names follows this Mac's own pushes (Dossiary Sync accepts only its last 20 own pushes as
    # a chain from an older base), but only when nothing can have been pulled under this tab's last write.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await edit_title(page, 'First')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    print("own push: the first save names version 3:", marker_ok(await base_marker(page), 3), await base_marker(page))
    await page.evaluate(SET_SYNC_VERSION, 4)   # Dossiary Sync pushed it as version 4; library.sqlite untouched
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    st = await sync_state(page)
    print("...the poll takes version 4 over, base too, with no reload:", st['version'] == 4 and st['base'] == 4 and st['reloads'] == 0, st)
    await edit_title(page, 'Second')
    print("...the next save names version 4:", marker_ok(await base_marker(page), 4), await base_marker(page))
    print("no page errors:", not errors, errors)
    await browser.close()

    # No token (no poll): the sync file alone, read by the next save.
    browser, page, errors = await open_app(p, seed=SEED2, token=None)
    await edit_title(page, 'First')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    await page.evaluate(SET_SYNC_VERSION, 4)
    await edit_title(page, 'Second')
    st = await sync_state(page)
    print("no token, own push: the next save is written, not kept aside:", await disk_doc_title(page, 1) == 'Second' and not await kept_aside_names(page))
    print("...and names version 4:", st['version'] == 4 and marker_ok(await base_marker(page), 4), st, await base_marker(page))
    print("no page errors:", not errors, errors)
    await browser.close()

    # The sync file changed while the write was under way (a pull may have landed under it): the number is taken
    # over, the base is not.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.evaluate("""() => {
        const h = window.__TEST_ROOT._children.get('library.sqlite');
        const orig = h.createWritable.bind(h);
        h.createWritable = async () => {
            const w = await orig();
            const close = w.close.bind(w);
            w.close = async () => { await close(); if(window.__RACE_ONCE){ window.__RACE_ONCE = false;
                const f = window.__TEST_ROOT._children.get('.dossiary-sync.json');
                f._bytes = new TextEncoder().encode(JSON.stringify({ libraryId: 'lib-7f3a', hub: 'x', version: 4 })); } };
            return w;
        };
        window.__RACE_ONCE = true;
    }""")
    await edit_title(page, 'Raced')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    st = await sync_state(page)
    print("a write the sync file changed under: version 4 known, base stays 3:", st['version'] == 4 and st['base'] == 3 and st['reloads'] == 0, st)
    await edit_title(page, 'After the race')
    print("...the next save still names version 3:", marker_ok(await base_marker(page), 3), await base_marker(page))
    print("no page errors:", not errors, errors)
    await browser.close()

    # Dossiary Sync's own base marker replaced this tab's (it installs one with every pull): base stays.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await edit_title(page, 'Mine')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    await page.evaluate("""() => {
        const f = window.__TEST_ROOT._children.get('.dossiary-base.json');
        f._bytes = new TextEncoder().encode(JSON.stringify({ version: 4, sha256: 'feed', writtenAt: '2026-10-28T10:00:00Z' }));
    }""")
    await page.evaluate(SET_SYNC_VERSION, 4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    st = await sync_state(page)
    print("a base marker that isn't this tab's: version 4 known, base stays 3:", st['version'] == 4 and st['base'] == 3, st)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_many_own_pushes(p):
    # 25 saves, each pushed by Dossiary Sync as the next version: the marker keeps up (never more than one behind).
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    ok = True
    for i in range(25):
        await page.evaluate("(t) => window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', [t, 1])", f'Save {i}')
        await page.evaluate("window.__DEBUG_persistDb()")
        m = await base_marker(page)
        ok = ok and marker_ok(m, 3 + i)
        await page.evaluate(SET_SYNC_VERSION, 4 + i)
        await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4 + i))
        await page.evaluate("window.__DEBUG_syncNow()")
    print("25 own pushes: each save's marker names the version before it:", ok, await base_marker(page))
    print("...nothing kept aside, never reloaded:", not await kept_aside_names(page) and (await sync_state(page))['reloads'] == 0, await sync_state(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_base_pull_between_write_and_marker(p):
    # Review fix: a pull of a phone version is installed just before this tab's write closes (the write lands on
    # top of it). Its base marker is written after the write but before this tab's marker, and its sync file only
    # after this tab's marker. The write must not count as proven: base stays 3, so the next save never names 4
    # (which would push this Mac's version over the phone edit).
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.evaluate("""() => {
        const root = window.__TEST_ROOT;
        const origGet = root.getFileHandle.bind(root);
        const put = async (name, text) => { const w = await (await origGet(name, { create: true })).createWritable();
            await w.write(new TextEncoder().encode(text)); await w.close(); };
        window.__PULL = 'armed';
        const h = root._children.get('library.sqlite');
        const origDb = h.createWritable.bind(h);
        h.createWritable = async () => {
            const w = await origDb();
            const close = w.close.bind(w);
            w.close = async () => { await close();
                // The pull's base marker, after this tab's write landed.
                if(window.__PULL === 'armed'){ window.__PULL = 'marker'; await put('.dossiary-base.json', JSON.stringify({ version: 4, sha256: 'hub-sha', writtenAt: '2026-10-28T10:00:00Z' })); } };
            return w;
        };
        root.getFileHandle = async (name, opts) => {
            const fh = await origGet(name, opts);
            if(name === '.dossiary-base.json' && opts && opts.create && window.__PULL === 'marker'){
                window.__PULL = 'sync';
                const orig = fh.createWritable.bind(fh);
                fh.createWritable = async () => { const w = await orig(); const close = w.close.bind(w);
                    // The pull's sync file, after this tab's marker.
                    w.close = async () => { await close(); if(window.__PULL === 'sync'){ window.__PULL = 'done';
                        await put('.dossiary-sync.json', JSON.stringify({ libraryId: 'lib-7f3a', hub: 'x', version: 4 })); } };
                    return w; };
            }
            return fh;
        };
    }""")
    await edit_title(page, 'Mine on 3')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    print("pull between write and marker: the hook ran in that order:", await page.evaluate("window.__PULL") == 'done')
    print("...this tab's marker is the one on disk:", marker_ok(await base_marker(page), 3), await base_marker(page))
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    st = await sync_state(page)
    print("...the write is not proven: version 4 known, base stays 3:", st['version'] == 4 and st['base'] == 3, st)
    await edit_title(page, 'Next save')
    print("...the next save still names version 3:", marker_ok(await base_marker(page), 3), await base_marker(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_switch_asks_when_unsaved(p):
    # Review fix: a change only in memory (its keep-aside copy failed) is never dropped by Switch library, Export's
    # "Open it" or Get it's "Open" without asking.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.evaluate("""() => { const r = window.__TEST_ROOT, orig = r.getDirectoryHandle.bind(r);
        r.getDirectoryHandle = async (name, o) => { if(name === '.kept-aside') throw new DOMException('The folder is read-only.', 'NoModificationAllowedError'); return orig(name, o); }; }""")
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Only in memory', 1])")
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("window.__DEBUG_persistDb()")
    await page.wait_for_timeout(400)
    st = await sync_state(page)
    print("keep-aside failed: the change is only in memory:", st['dirty'] and await disk_doc_title(page, 1) == 'Invoice' and await page.evaluate("window.__DEBUG_dbExportText().includes('Only in memory')"), st)
    await page.click('#reload-btn')
    await page.wait_for_timeout(300)
    text = await page.inner_text('#sync-discard-dialog') if await page.locator('#sync-discard-dialog').count() else ''
    print("...Switch library asks first:", 'Discard the unsaved change?' in text and "couldn't be saved" in text, repr(text))
    print("...the library is still open meanwhile:", await page.locator('tr[data-id="1"]').count() == 1)
    await page.click('#sync-discard-cancel-btn')
    await page.wait_for_timeout(200)
    print("...Cancel keeps it open, with the change:", await page.locator('#sync-discard-dialog').count() == 0 and await page.evaluate("window.__DEBUG_dbExportText().includes('Only in memory')"))
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    await page.click('#sync-discard-btn')
    await page.wait_for_timeout(300)
    print("...'Switch anyway' switches:", await page.locator('#empty-state').is_visible())
    print("no page errors:", not errors, errors)
    await browser.close()
    # Export as library's "Open it" asks the same way.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)}, extra_files={'files/1_a.pdf': 'pdf 1'})
    await page.evaluate("() => { window.__EXPORT_PARENT = window.__makeEmptyRoot(); window.__EXPORT_PARENT.name = 'Outside'; window.__NEXT_PICKED_DIR = window.__EXPORT_PARENT; }")
    await page.check('tr[data-id="1"] .row-select-checkbox')
    await page.click('#bulk-more-btn')
    await page.click('#bulk-export-library-btn')
    await page.wait_for_timeout(300)
    await page.click('#export-library-start-btn')
    await page.wait_for_timeout(1000)
    await page.evaluate("""() => { const r = window.__TEST_ROOT, orig = r.getDirectoryHandle.bind(r);
        r.getDirectoryHandle = async (name, o) => { if(name === '.kept-aside') throw new DOMException('The folder is read-only.', 'NoModificationAllowedError'); return orig(name, o); }; }""")
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Only in memory', 1])")
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("window.__DEBUG_persistDb()")
    await page.wait_for_timeout(400)
    if not await page.locator('#export-library-open-btn').count():
        print("...export dialog still open:", False)
    else:
        await page.click('#export-library-open-btn')
        await page.wait_for_timeout(300)
        print("Export 'Open it' asks first:", await page.locator('#sync-discard-dialog').count() == 1)
        await page.click('#sync-discard-cancel-btn')
        await page.wait_for_timeout(200)
        print("...staying keeps this library and the change:", await page.inner_text('#sub-label') == 'Household' and (await sync_state(page))['dirty'])
    print("no page errors:", not errors, errors)
    await browser.close()


async def main():
    import sys
    only = sys.argv[1:]
    async with async_playwright() as p:
        for scenario in (scenario_synced_save, scenario_base_follows_loaded_version, scenario_guard, scenario_newer_reloads,
                         scenario_poll_reads_state, scenario_poll_deleted, scenario_no_sync_file, scenario_devices_dialog,
                         scenario_no_token, scenario_service_down, scenario_backup, scenario_reload_keeps_view,
                         scenario_reload_waits_for_dialog, scenario_edit_on_newer_version, scenario_guard_more,
                         scenario_form_open_newer_arrives, scenario_library_check_stale, scenario_reload_refused,
                         scenario_person_change_not_dropped, scenario_drops_meet_newer, scenario_quiet_copy_reused,
                         scenario_reload_race, scenario_doc_ids, scenario_open_race, scenario_no_reload_while_opening,
                         scenario_sync_read_before_writes, scenario_view_prefs, scenario_kept_aside,
                         scenario_export_leaves_sync_files, scenario_tokenless_write_pulled_over,
                         scenario_token_write_then_foreign_reloads_quietly, scenario_token_rejected, scenario_ocr_job_runs,
                         scenario_base_follows_own_push, scenario_many_own_pushes,
                         scenario_base_pull_between_write_and_marker, scenario_switch_asks_when_unsaved):
            if only and not any(o in scenario.__name__ for o in only):
                continue
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
