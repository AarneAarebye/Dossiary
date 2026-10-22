import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from datetime import datetime, timezone
from playwright.async_api import async_playwright

# The sync lease (two-Mac editing, part 2): a library with a
# .dossiary-sync.json at its root takes an edit lease from Dossiary Sync's
# admin API (127.0.0.1:8769) at its first real change. A fake fetch plays the
# service per scenario.
# config: { token, down, acquire ('granted'|'busy'|'offline'), busyLease,
#           takeOver ('granted'|...), heartbeat ('granted'|'lost'|'offline'),
#           lostLease (lease object or None) }
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
        if(path === '/admin/health') return json(200, { service: 'dossiary-sync', version: '0.4.0', adminProtocol: 1, connected: headers.Authorization === `Bearer ${S.token}` });
        if(path === '/admin/connect/start' && opts.method === 'POST') return json(200, { validFor: 300 });
        if(path === '/admin/connect' && opts.method === 'POST'){
            const body = JSON.parse(opts.body || '{}');
            return body.code === 'KX7P2M9Q' ? json(200, { token: S.token }) : json(403, { error: 'Wrong code' });
        }
        if(headers.Authorization !== `Bearer ${S.token}`) return json(401, { error: 'Unauthorized' });
        if(path === '/admin/libraries') return json(200, S.libraries || [{ id: 'lib-7f3a', name: 'Household', available: true }]);
        if(path === '/admin/devices') return json(200, []);
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
                const result = body.takeOver ? (S.takeOver || 'granted') : (S.acquire || 'granted');
                if(result === 'busy') return json(200, { result, lease: S.busyLease, version: S.acquireVersion || 3 });
                return json(200, { result, lease: result === 'granted' ? { holder: 'this', deviceName: 'MacBook Pro', since: new Date().toISOString() } : null, version: S.acquireVersion || 3 });
            }
            if(body.action === 'heartbeat'){
                const result = S.heartbeat || 'granted';
                return json(200, { result, lease: result === 'lost' ? (S.lostLease || null) : null, version: 3 });
            }
            if(body.action === 'release') return json(200, { result: 'released', lease: null, version: 3 });
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


async def scenario_no_sync_file(p):
    browser, page, errors = await open_app(p, sync_file=False)
    before = await writes(page)
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(200)
    await edit_title(page, 'Edited')
    print("no sync file: the edit is saved:", await saved_title(page) == 'Edited' and await writes(page) >= before + 2)
    print("...with zero admin calls (sort click and edit):", await admin_calls(page) == [], await admin_calls(page))
    print("...and no marker:", not (await marker(page))['visible'])
    print("...state stays none:", (await page.evaluate("window.__DEBUG_syncLease()"))['state'] == 'none')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_first_change(p):
    browser, page, errors = await open_app(p)
    print("opening a synced library makes no lease call:", await lease_calls(page) == [])
    print("...and shows no marker yet:", not (await marker(page))['visible'])
    before = await writes(page)
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(200)
    print("a sort click before any edit takes no lease:", await lease_calls(page) == [])
    sort_saved = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).settings.some(r => r.key === 'sort_key' && r.value === 'title')")
    print("...but the sort setting is written:", sort_saved and await writes(page) == before + 1)
    await page.click('#detail-panel-toggle-btn')
    await page.wait_for_timeout(150)
    await page.click('#detail-panel-toggle-btn')
    await page.wait_for_timeout(150)
    print("panel toggles take no lease either:", await lease_calls(page) == [])
    await edit_title(page, 'First change')
    acq = await lease_calls(page, 'acquire')
    print("the first Edit save sends one acquire:", len(acq) == 1 and acq[0]['body'] == {"action": "acquire", "takeOver": False}, acq)
    print("...as JSON with the token:", acq[0]['contentType'] == 'application/json' and acq[0]['auth'] == 'Bearer admin-tok')
    print("...and the file is written:", await saved_title(page) == 'First change')
    m = await marker(page)
    print("marker reads '✎ editing':", m['visible'] and m['text'] == '✎ editing', m)
    print("state is holding:", (await page.evaluate("window.__DEBUG_syncLease()"))['state'] == 'holding')
    await edit_title(page, 'Second change')
    print("a second save while holding asks nothing:", len(await lease_calls(page, 'acquire')) == 1 and await saved_title(page) == 'Second change')
    print("no page errors:", not errors, errors)
    await browser.close()


async def open_edit(page, row=1):
    await page.click(f'tr[data-id="{row}"]')
    await page.wait_for_timeout(150)
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(300)


async def hold_back_change(page, title):
    """Open the Edit form while holding the lease, lose it to the other Mac (poll), then save: busy → Cancel."""
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(3, THIS_LEASE))
    await open_edit(page)
    await page.fill('#e-title', title)
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquire = 'busy'; window.__SYNC.busyLease = s.lease; }", state(3, BUSY_LEASE))
    await tick(page)
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(300)


async def scenario_busy(p):
    browser, page, errors = await open_app(p, sync={"token": "admin-tok", "acquire": "busy", "busyLease": BUSY_LEASE})
    before = await writes(page)
    await open_edit(page)
    text = await page.inner_text('#sync-takeover-dialog') if await page.locator('#sync-takeover-dialog').count() else ''
    print("busy: opening Edit shows the take-over dialog first:", 'Being edited on MacBook Pro since 02:02 PM.' in text, repr(text))
    print("...with Take over and Cancel:", await page.locator('#sync-takeover-btn').count() == 1 and await page.locator('#sync-takeover-cancel-btn').count() == 1)
    print("...and the form isn't open yet:", await page.locator('#e-title').count() == 0)
    await page.click('#sync-takeover-cancel-btn')
    await page.wait_for_timeout(300)
    print("Cancel: the Edit form doesn't open:", await page.locator('#e-title').count() == 0 and await page.locator('#sync-takeover-dialog').count() == 0)
    print("...the status line names who's editing:", await status(page) == 'Not started: MacBook Pro is editing this library.', await status(page))
    m = await marker(page)
    print("...marker reads 'editing on MacBook Pro':", m['visible'] and m['text'] == 'editing on MacBook Pro', m)
    print("...nothing written:", await writes(page) == before)

    # A one-shot action asks the same way (Archive in the panel).
    await page.click('#archive-toggle-btn')
    await page.wait_for_timeout(300)
    print("Archive asks too:", await page.locator('#sync-takeover-dialog').count() == 1)
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(300)
    archived = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).documents[0].archived")
    print("...Escape cancels it: not archived, nothing written:", not archived and await writes(page) == before)

    # Take over: the form opens, and the save writes.
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(300)
    await page.click('#sync-takeover-btn')
    await page.wait_for_timeout(300)
    acq = await lease_calls(page, 'acquire')
    print("Take over acquires with takeOver true:", acq[-1]['body'] == {"action": "acquire", "takeOver": True}, acq[-1])
    print("...then the Edit form opens:", await page.locator('#e-title').count() == 1)
    await page.fill('#e-title', 'Taken over')
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(400)
    print("...and the save writes:", await saved_title(page) == 'Taken over')
    m = await marker(page)
    print("...marker reads '✎ editing':", m['text'] == '✎ editing', m)
    print("no page errors:", not errors, errors)
    await browser.close()

    # Held back: the lease goes to the other Mac while the form is open.
    browser, page, errors = await open_app(p)
    before_title = await saved_title(page)
    await hold_back_change(page, 'Mine')
    print("lease lost while editing: Save asks:", await page.locator('#sync-takeover-dialog').count() == 1)
    await page.click('#sync-takeover-cancel-btn')
    await page.wait_for_timeout(300)
    print("Cancel writes nothing:", await saved_title(page) == before_title)
    m = await marker(page)
    print("...marker says unsaved changes:", m['visible'] and m['text'] == 'unsaved changes', m)
    print("...the change stays in this window:", 'Mine' in await page.inner_text('tr[data-id="1"]'))
    print("...and no 'Saved' line:", 'Saved' not in await status(page), await status(page))
    w = await writes(page)
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(200)
    print("a sort click now doesn't write the held-back change:", await writes(page) == w and await saved_title(page) == before_title)
    # The next change asks again; Take over writes everything.
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(300)
    print("the next change asks again:", await page.locator('#sync-takeover-dialog').count() == 1)
    await page.click('#sync-takeover-btn')
    await page.wait_for_timeout(300)
    await page.fill('#e-title', 'Mine again')
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(400)
    print("...Take over writes:", await saved_title(page) == 'Mine again' and (await marker(page))['text'] == '✎ editing')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_offline(p):
    browser, page, errors = await open_app(p, sync={"token": "admin-tok", "acquire": "offline"})
    await edit_title(page, 'Offline change')
    print("offline: the write goes through:", await saved_title(page) == 'Offline change')
    m = await marker(page)
    print("...marker reads '✎ editing offline':", m['visible'] and m['text'] == '✎ editing offline', m)
    await edit_title(page, 'Offline again')
    print("...the next save doesn't ask again:", len(await lease_calls(page, 'acquire')) == 1 and await saved_title(page) == 'Offline again')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_no_token(p):
    # X1: no admin token in this browser → a real change is held back, not written.
    browser, page, errors = await open_app(p, token=None)
    before = await saved_title(page)
    await edit_title(page, 'Unconnected change')
    print("no token: the change isn't written:", await saved_title(page) == before)
    print("...with no admin calls:", await admin_calls(page) == [])
    m = await marker(page)
    print("...marker reads 'not connected — changes not saved':", m['visible'] and m['text'] == 'not connected — changes not saved', m)
    print("...its tooltip points to the devices dialog:", m['title'] == 'Connect in Tools › iPhone & other devices…', m['title'])
    print("...the status line says so:", (await status(page)).startswith("Not saved: this browser isn't connected"), await status(page))
    print("...the change stays in this window:", 'Unconnected change' in await page.inner_text('tr[data-id="1"]'))
    prevented = await page.evaluate("() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }")
    print("...closing the tab asks first:", prevented)
    w = await writes(page)
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    print("...a background write is held back too:", await writes(page) == w)
    # Connecting in the devices dialog takes the lease and writes it.
    await page.click('#tools-btn'); await page.click('#devices-btn')
    await page.wait_for_timeout(300)
    await page.click('#devices-connect-btn')
    await page.wait_for_timeout(200)
    await page.fill('#devices-code-input', 'KX7P2M9Q')
    await page.click('#devices-code-submit')
    await page.wait_for_timeout(600)
    print("after connecting: the held-back change is written:", await saved_title(page) == 'Unconnected change', await saved_title(page))
    print("...through an acquire:", len(await lease_calls(page, 'acquire')) == 1)
    m = await marker(page)
    print("...marker reads '✎ editing':", m['text'] == '✎ editing', m)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_service_down(p):
    # X1: the service not answering → held back, written once it answers.
    browser, page, errors = await open_app(p, sync={"token": "admin-tok", "down": True})
    before = await saved_title(page)
    # NEW-2: only a job's change pending → held silently.
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET file_hash = ? WHERE id = ?', ['abc', 1])")
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    prevented = await page.evaluate("() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }")
    m = await marker(page)
    print("a job's change alone is held silently (no 'not saved', no beforeunload):", not prevented and 'changes not saved' not in m['text'] and not (await sync_state(page))['unsaved'], m)
    print("...the tooltip says it may not be running or installed:", 'may not be running, or not be installed' in m['title'], m['title'])
    await edit_title(page, 'Down change')
    print("service down: the change isn't written:", await saved_title(page) == before)
    m = await marker(page)
    print("...marker reads 'Dossiary Sync not answering — changes not saved':", m['visible'] and m['text'] == 'Dossiary Sync not answering — changes not saved', m)
    print("...with the reason as its tooltip:", 'may not be running' in m['title'], m['title'])
    print("...the status line says so:", (await status(page)).startswith("Not saved: Dossiary Sync isn't answering"), await status(page))
    n = len(await lease_calls(page, 'acquire'))
    await tick(page)
    print("...a tick within the minute (no answer) doesn't ask again:", len(await lease_calls(page, 'acquire')) == n)
    w = await writes(page)
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    print("...a background write is held back too:", await writes(page) == w)
    await page.evaluate("window.__SYNC.down = false")
    await tick(page)
    await page.wait_for_timeout(300)
    print("once it answers, the next tick writes it:", await saved_title(page) == 'Down change')
    print("...marker reads '✎ editing':", (await marker(page))['text'] == '✎ editing')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_heartbeat(p):
    browser, page, errors = await open_app(p)
    await edit_title(page, 'Holding')
    await page.evaluate("window.__DEBUG_syncNow(30 * 1000)")
    print("no heartbeat after 30 s:", await lease_calls(page, 'heartbeat') == [])
    await page.evaluate("window.__DEBUG_syncNow(31 * 1000)")
    print("a heartbeat after 60 s:", len(await lease_calls(page, 'heartbeat')) == 1)

    # A timed-out / failed heartbeat is "try again", not offline, not lost.
    await page.evaluate("window.__SYNC.down = true")
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    print("a failed heartbeat keeps holding:", (await page.evaluate("window.__DEBUG_syncLease()"))['state'] == 'holding' and (await marker(page))['text'] == '✎ editing')
    await page.evaluate("window.__SYNC.down = false")

    # Lost with no lease: merely expired -- re-acquire silently.
    await page.evaluate("window.__SYNC.heartbeat = 'lost'; window.__SYNC.lostLease = null;")
    acquires = len(await lease_calls(page, 'acquire'))
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    print("lost with no lease re-acquires silently:", len(await lease_calls(page, 'acquire')) == acquires + 1 and (await marker(page))['text'] == '✎ editing')

    # Lost to the other Mac.
    await page.evaluate("""window.__SYNC.lostLease = { holder: 'other', deviceName: 'iMac', since: new Date().toISOString() };""")
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    m = await marker(page)
    print("lost to the iMac: marker reads 'editing on iMac':", m['text'] == 'editing on iMac', m)
    print("...state other:", (await page.evaluate("window.__DEBUG_syncLease()"))['state'] == 'other')
    hb = len(await lease_calls(page, 'heartbeat'))
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    print("...and no more heartbeats:", len(await lease_calls(page, 'heartbeat')) == hb)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_release(p):
    # After 10 quiet minutes.
    browser, page, errors = await open_app(p)
    await edit_title(page, 'Holding')
    await page.evaluate("window.__DEBUG_syncNow(9 * 60 * 1000)")
    print("no release after 9 minutes:", await lease_calls(page, 'release') == [])
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    rel = await lease_calls(page, 'release')
    print("released after 10 quiet minutes:", len(rel) == 1 and rel[0]['body'] == {"action": "release", "takeOver": False}, rel)
    print("...marker hidden, state none:", not (await marker(page))['visible'] and (await page.evaluate("window.__DEBUG_syncLease()"))['state'] == 'none')
    await edit_title(page, 'Again')
    print("...the next change takes it again:", len(await lease_calls(page, 'acquire')) == 2 and (await marker(page))['text'] == '✎ editing')

    # On Switch library.
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    rel = await lease_calls(page, 'release')
    print("Switch library releases:", len(rel) == 2)
    print("...and the marker goes away:", not (await marker(page))['visible'])
    print("no page errors:", not errors, errors)
    await browser.close()

    # On pagehide (keepalive, no await).
    browser, page, errors = await open_app(p)
    await edit_title(page, 'Holding')
    await page.evaluate("window.dispatchEvent(new PageTransitionEvent('pagehide', { persisted: false }))")
    await page.wait_for_timeout(100)
    rel = await lease_calls(page, 'release')
    print("pagehide releases with keepalive:", len(rel) == 1 and rel[0]['keepalive'], rel)
    print("no page errors:", not errors, errors)
    await browser.close()

    # Nothing held, nothing to release.
    browser, page, errors = await open_app(p)
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    print("Switch library without the lease sends nothing:", await admin_calls(page) == [])
    await browser.close()


async def scenario_backup(p):
    browser, page, errors = await open_app(p, extra_files={'.kept-aside/2026-05-03/library.sqlite': 'old', 'files/1_a.pdf': 'pdf'})
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
    print("...but has the library:", 'library.sqlite' in copied and 'files/1_a.pdf' in copied)
    errors = [e for e in errors if 'ERR_FAILED' not in e]
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_german(p):
    browser, page, errors = await open_app(p, sync={"token": "admin-tok", "acquire": "busy", "busyLease": BUSY_LEASE}, lang='de')
    await open_edit(page)
    text = await page.inner_text('#sync-takeover-dialog')
    print("German take-over dialog:", 'Wird seit 14:02 auf MacBook Pro bearbeitet.' in text and 'Übernehmen' in text, repr(text))
    await page.click('#sync-takeover-cancel-btn')
    await page.wait_for_timeout(300)
    print("German 'not started':", await status(page) == 'Nicht begonnen: MacBook Pro bearbeitet diese Bibliothek.', await status(page))
    await page.evaluate("window.__SYNC.acquire = 'granted'")
    await edit_title(page, 'Meins')
    print("German '✎ editing':", (await marker(page))['text'] == '✎ in Bearbeitung', await marker(page))
    await page.select_option('#lang-select', 'en')
    await page.wait_for_timeout(200)
    print("the marker follows a language switch:", (await marker(page))['text'] == '✎ editing')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_header_height(p):
    ok = True
    for width in (320, 1440):
        browser, page, errors = await open_app(p, sync={"token": "admin-tok", "down": True}, width=width)
        before = await page.evaluate("document.querySelector('header').getBoundingClientRect().height")
        if width > 640:
            await edit_title(page, 'Down change')
        else:
            await page.click('tr[data-id="1"] .row-edit-btn')
            await page.wait_for_timeout(200)
            await page.fill('#e-title', 'Down change')
            await page.click('#save-edit-btn')
            await page.wait_for_timeout(400)
        m = await marker(page)
        after = await page.evaluate("document.querySelector('header').getBoundingClientRect().height")
        same = m['visible'] and abs(before - after) < 0.5
        print(f"header height unchanged with the marker shown at {width}px:", same, before, after, m)
        ok = ok and same
        await page.evaluate("document.getElementById('sub-label').textContent = 'A very long library name that needs to be truncated somewhere'")
        long_after = await page.evaluate("document.querySelector('header').getBoundingClientRect().height")
        print(f"...also with a long library name at {width}px:", abs(before - long_after) < 0.5, before, long_after)
        print("no page errors:", not errors, errors)
        await browser.close()


# ---- Task 2: staying current, lease lost, kept-aside notice, and Task 1's review follow-ups ----

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


async def scenario_reload_keeps_view(p):
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
    before = await writes(page)
    await disk_change(page, {3: 'Letter from the bank'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4))
    await tick(page)
    st = await sync_state(page)
    print("a newer version reloads once:", st['reloads'] == 1 and st['version'] == 4, st)
    print("...the new title is in the table:", 'Letter from the bank' in await row_text(page, 3))
    print("...and in the detail panel:", 'Letter from the bank' in await page.inner_text('#detail-panel-body'))
    print("...the Inbox view is kept:", await page.evaluate("document.getElementById('nav-item-inbox').classList.contains('active')"))
    print("...the search text is kept:", await page.input_value('#search') == 'Lette')
    print("...the category filter is kept:", await page.input_value('#category-filter') == 'Mail')
    print("...the filtered list still applies (Leaflet hidden):", await page.locator('tr[data-id="4"]').count() == 0)
    print("...the selection is kept:", await page.evaluate("!!document.querySelector('tr[data-id=\"3\"].row-selected')"))
    print("...a reload writes nothing:", await writes(page) == before)
    await tick(page)
    print("...and the next poll doesn't reload again:", (await sync_state(page))['reloads'] == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_reload_keeps_scroll(p):
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
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3)})
    await page.click('tr[data-id="1"]')
    await page.wait_for_timeout(150)
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(200)
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


async def scenario_holding_no_reload(p):
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, THIS_LEASE)})
    await edit_title(page, 'Mine')
    print("holding:", (await sync_state(page))['state'] == 'holding')
    await disk_change(page, {2: 'Receipt pushed'}, sync_version=5)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(5, THIS_LEASE))
    await tick(page)
    st = await sync_state(page)
    print("holding: a newer version doesn't reload:", st['reloads'] == 0 and 'Receipt pushed' not in await row_text(page, 2), st)
    print("...it is taken as this Mac's own push:", st['version'] == 5)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_acquire_newer_version(p):
    # Constraint (e) / review Critical 1: the service pulls the newer version before answering granted.
    # Opening Edit takes the lease first and reloads, so the save lands on the newer version.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "acquireVersion": 4, "state": state(3)})
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await open_edit(page)
    st = await sync_state(page)
    print("opening Edit on a newer hub version reloads before the form opens:", st['reloads'] == 1 and st['version'] == 4 and 'Receipt (iMac)' in await row_text(page, 2), st)
    print("...then the form opens:", await page.locator('#e-title').count() == 1)
    await page.fill('#e-title', 'Edited here')
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(400)
    print("the newer version's content survives:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    print("...and this tab's change is on top of it:", await disk_doc_title(page, 1) == 'Edited here')
    print("...nothing kept aside:", not await kept_aside_names(page))
    print("...'Saved' shown:", 'Saved' in await status(page))
    print("no page errors:", not errors, errors)
    await browser.close()


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


async def scenario_safety_net(p):
    # B: memory with a real change, based on v3; the grant reports v4 (pulled onto disk). Nothing is written over it.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "acquireVersion": 4})
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Mine (old base)', 1])")
    await disk_change(page, {2: 'Receipt (iMac)'})
    w = await writes(page)
    ok = await page.evaluate("window.__DEBUG_persistDb()")
    await page.wait_for_timeout(500)
    print("safety net: persistDb() answers false:", ok is False, ok)
    print("...library.sqlite isn't written:", await writes(page) == w and await disk_doc_title(page, 2) == 'Receipt (iMac)' and await disk_doc_title(page, 1) == 'Invoice')
    names = await kept_aside_names(page)
    print("...this tab's bytes are kept aside under .kept-aside/<this Mac>-<time>/:", len(names) == 1 and names[0].startswith('MacBook Pro-'), names)
    print("...with this tab's change in them:", names and await kept_aside_title(page, names[0]) == 'Mine (old base)')
    print("...the library reloads to the newer version:", 'Receipt (iMac)' in await row_text(page, 2) and 'Mine' not in await row_text(page, 1))
    notice = await page.inner_text('#sync-notice-dialog') if await page.locator('#sync-notice-dialog').count() else ''
    print("...a notice names the folder:", f'.kept-aside/{names[0]}' in notice and 'please make it again' in notice, repr(notice))
    print("...and the status line too:", '.kept-aside/' in await status(page))
    await page.click('#sync-notice-ok-btn')
    await page.wait_for_timeout(150)
    print("...OK closes it:", await page.locator('#sync-notice-dialog').count() == 0)
    # A second time never overwrites the first folder.
    # (This tab now holds the lease; it lapses and the iMac edits again.)
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Mine again', 1])")
    await disk_change(page, {2: 'Receipt (iMac 2)'})
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquireVersion = 5; }", state(5))
    await tick(page)
    await page.evaluate("window.__DEBUG_persistDb()")
    await page.wait_for_timeout(500)
    names2 = await kept_aside_names(page)
    print("...a second one gets its own folder:", len(names2) == 2 and names[0] in names2, names2)
    # A background job's save behind a newer version: never dropped (R1, fix round 4) -- kept aside quietly, no notice.
    await page.click('#sync-notice-ok-btn')
    await page.wait_for_timeout(150)
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquireVersion = 6; }", state(6))
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET file_hash = ? WHERE id = ?', ['abc', 2])")
    await disk_change(page, {2: 'Receipt (iMac 3)'})
    await tick(page)
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    await page.wait_for_timeout(500)
    names3 = await kept_aside_names(page)
    quiet = [n for n in names3 if n not in names2]
    print("a background save behind a newer version: kept aside in a folder of its own, no notice:", len(quiet) == 1 and await page.locator('#sync-notice-dialog').count() == 0, names3)
    print("...the copy holds this tab's memory (the job's data with it):", quiet and await page.evaluate("""async (n) => JSON.parse(await (await window.__TEST_ROOT._children.get('.kept-aside')._children.get(n)._children.get('library.sqlite').getFile()).text()).documents.find(d => d.id === 2).file_hash""", quiet[0]) == 'abc')
    st = await status(page)
    print("...a plain status line names the folder:", quiet and f'.kept-aside/{quiet[0]}' in st and 'please make it again' not in st, st)
    print("...the newer version is loaded:", 'Receipt (iMac 3)' in await row_text(page, 2))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_sleep_lost_lease(p):
    # Important 3: the lease expired while this tab thought it held it, and the iMac changed the library.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, THIS_LEASE)})
    await open_edit(page)
    await page.fill('#e-title', 'Typed before sleeping')
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquireVersion = 4; }", state(4))
    await tick(page)
    st = await sync_state(page)
    print("poll: lease gone while 'holding' → not holding any more:", st['state'] == 'none', st)
    print("...the bump isn't taken as this Mac's push:", st['version'] == 3)
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(600)
    print("...Save then doesn't write over the iMac's version:", await disk_doc_title(page, 2) == 'Receipt (iMac)' and await disk_doc_title(page, 1) == 'Invoice')
    names = await kept_aside_names(page)
    print("...this tab's change is kept aside:", len(names) == 1 and await kept_aside_title(page, names[0]) == 'Typed before sleeping', names)
    print("...and the iMac's version is loaded:", 'Receipt (iMac)' in await row_text(page, 2))
    print("no page errors:", not errors, errors)
    await browser.close()

    # Heartbeat: lost with no holder, the silent re-acquire reports a newer version → reload.
    browser, page, errors = await open_app(p, seed=SEED2)
    await edit_title(page, 'Mine')
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("window.__SYNC.heartbeat = 'lost'; window.__SYNC.lostLease = null; window.__SYNC.acquireVersion = 4;")
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    await page.wait_for_timeout(400)
    st = await sync_state(page)
    print("heartbeat re-acquire with a newer version reloads:", 'Receipt (iMac)' in await row_text(page, 2) and st['version'] == 4 and st['state'] == 'holding', st)
    print("...nothing written over it:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_background_files(p):
    # Important 2: background jobs write files only with the lease (OCR job runner).
    seed = dict(SEED2)
    seed["ocr_jobs"] = [{"document_id": 1, "helper_url": None, "job_id": None, "file_hash": None,
                         "created_at": "2026-03-01T00:00:00Z", "ocr_language": "eng", "requested_by": "edit"}]
    browser, page, errors = await open_app(p, seed=seed, sync={"token": "admin-tok", "state": state(3, IMAC_LEASE),
                                                                "acquire": "busy", "busyLease": IMAC_LEASE},
                                           extra_files={'files/1_a.pdf': 'pdf'})
    await page.evaluate("window.__DEBUG_holdOcrJobs(true)")
    await tick(page)
    await page.evaluate("window.__DEBUG_runOcrJobPass()")
    await page.wait_for_timeout(400)
    rows = await page.evaluate("window.__DEBUG_ocrJobRows().length")
    print("iMac editing: the OCR job doesn't run, stays queued:", rows == 1 and await page.evaluate("window.__DEBUG_ocrFallbackIdle()"))
    print("...no dialog, and never a take-over:", await page.locator('#sync-takeover-dialog').count() == 0 and all(not c['body']['takeOver'] for c in await lease_calls(page, 'acquire')))
    # Lease free but taken when the job wants it: still busy → waits, silently.
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(3))
    await tick(page)
    await page.evaluate("window.__DEBUG_runOcrJobPass()")
    await page.wait_for_timeout(400)
    print("lease free but busy at the moment: still queued, no dialog:", await page.evaluate("window.__DEBUG_ocrJobRows().length") == 1 and await page.locator('#sync-takeover-dialog').count() == 0)
    # Granted: the job runs (and finishes, whatever OCR makes of the fake file).
    await page.evaluate("window.__SYNC.acquire = 'granted'")
    await tick(page)   # the poll sees the lease free again
    await page.evaluate("window.__DEBUG_runOcrJobPass()")
    for _ in range(20):
        await page.wait_for_timeout(200)
        if await page.evaluate("window.__DEBUG_ocrJobRows().length") == 0: break
    print("with the lease taken silently, the job runs:", await page.evaluate("window.__DEBUG_ocrJobRows().length") == 0 and (await sync_state(page))['state'] == 'holding')
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    await page.wait_for_timeout(200)
    print("...a lease only the job took goes back after a minute:", len(await lease_calls(page, 'release')) == 1 and (await sync_state(page))['state'] == 'none')
    errors = [e for e in errors if 'ERR_FAILED' not in e]
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_lost_via_state(p):
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, THIS_LEASE)})
    await edit_title(page, 'Mine')
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(3, IMAC_LEASE))
    await tick(page)
    m = await marker(page)
    print("lease lost (state shows the iMac): marker 'editing on iMac':", m['text'] == 'editing on iMac', m)
    print("...state other:", (await sync_state(page))['state'] == 'other')
    print("...status line says so:", await status(page) == 'iMac took over editing this library.', await status(page))
    await page.select_option('#lang-select', 'de')
    await page.wait_for_timeout(200)
    print("...and retranslates:", await status(page) == 'iMac hat die Bearbeitung dieser Bibliothek übernommen.', await status(page))
    await page.select_option('#lang-select', 'en')
    await page.wait_for_timeout(100)
    # The iMac's later version is then loaded.
    await disk_change(page, {2: 'Receipt from iMac'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4, IMAC_LEASE))
    await tick(page)
    print("...then the iMac's newer version is loaded:", 'Receipt from iMac' in await row_text(page, 2))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_kept_aside(p):
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
    # A fresh page (same browser): still not shown again.
    await page.reload()
    await page.wait_for_timeout(200)
    await seed_and_open(page, {"token": "admin-tok", "state": state(3, None, KEPT)}, seed=SEED2)
    await tick(page)
    print("...not repeated after reopening the page:", 'kept safe' not in await status(page), await status(page))
    # The devices dialog shows it under the library while the entry exists.
    await page.click('#tools-btn'); await page.click('#devices-btn')
    await page.wait_for_timeout(400)
    libs = await page.inner_text('#devices-libraries') if await page.locator('#devices-libraries').count() else ''
    print("the devices dialog shows it under the library:", 'Household' in libs and KEPT_TEXT in libs, repr(libs))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_last_error(p):
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, THIS_LEASE)})
    await edit_title(page, 'Mine')
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(3, THIS_LEASE, None, 'The Pi refused the upload (disk full).'))
    await tick(page)
    m = await marker(page)
    print("lastError while holding: marker 'not synced yet':", m['text'] == 'not synced yet', m)
    print("...with the error as its tooltip:", m['title'] == 'The Pi refused the upload (disk full).')
    print("...still holding (saves go on):", (await sync_state(page))['state'] == 'holding')
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(3, THIS_LEASE))
    await tick(page)
    print("...back to '✎ editing' once it clears:", (await marker(page))['text'] == '✎ editing')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_german_task2(p):
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, None, KEPT)}, lang='de')
    await tick(page)
    print("German kept-aside line:", await status(page) == "Änderungen, die am 03. Mai 2026 auf diesem Mac gemacht wurden, ließen sich nicht mit denen von iMac zusammenführen. Sie sind sicher aufbewahrt und werden durch ein späteres Update zusammengeführt.", await status(page))
    print("no page errors:", not errors, errors)
    await browser.close()


# Task 1 review follow-ups.

async def scenario_view_write_newer_on_disk(p):
    # 1. A view-only write mustn't overwrite a newer library.sqlite that Dossiary Sync just pulled.
    browser, page, errors = await open_app(p, seed=SEED2)
    before = await writes(page)
    await disk_change(page, {2: 'Receipt (pulled)'}, sync_version=4)
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(400)
    print("view-only write with a newer version on disk: the pulled file survives:", await disk_doc_title(page, 2) == 'Receipt (pulled)')
    print("...the library reloads instead:", 'Receipt (pulled)' in await row_text(page, 2) and (await sync_state(page))['version'] == 4)
    sort_saved = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).settings.some(r => r.key === 'sort_key' && r.value === 'title')")
    print("...and the sort is applied and saved afterwards:", sort_saved and await page.evaluate("document.querySelector('th[data-key=\"title\"]').classList.contains('active')"))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_cancel_followups(p):
    # 2. After Cancel: a status line of our own, beforeunload, and Switch library asks.
    browser, page, errors = await open_app(p, seed=SEED2)
    await hold_back_change(page, 'Mine')
    await page.click('#sync-takeover-cancel-btn')
    await page.wait_for_timeout(300)
    print("Cancel: the status line says it isn't saved:", await status(page) == 'Not saved: MacBook Pro is editing this library. Your change stays in this window; your next change asks again.', await status(page))
    prevented = await page.evaluate("() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }")
    print("...closing the tab asks first (beforeunload):", prevented)
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    print("...Switch library asks in a dialog:", await page.locator('#sync-discard-dialog').count() == 1)
    print("...the library is still open meanwhile:", await page.locator('tr[data-id="1"]').count() == 1)
    await page.click('#sync-discard-cancel-btn')
    await page.wait_for_timeout(150)
    print("...Cancel keeps it open:", await page.locator('#sync-discard-dialog').count() == 0 and await page.locator('tr[data-id="1"]').count() == 1 and 'Mine' in await row_text(page, 1))
    await page.click('#reload-btn')
    await page.wait_for_timeout(150)
    await page.click('#sync-discard-btn')
    await page.wait_for_timeout(200)
    print("...Switch anyway switches:", await page.locator('#empty-state').is_visible())
    prevented = await page.evaluate("() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }")
    print("...and nothing is left to warn about:", not prevented)
    print("no page errors:", not errors, errors)
    await browser.close()
    # Without unsaved changes, Switch library doesn't ask.
    browser, page, errors = await open_app(p, seed=SEED2)
    await page.click('#reload-btn')
    await page.wait_for_timeout(200)
    print("without unsaved changes Switch library doesn't ask:", await page.locator('#sync-discard-dialog').count() == 0 and await page.locator('#empty-state').is_visible())
    prevented = await page.evaluate("() => { const e = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(e); return e.defaultPrevented; }")
    print("...and beforeunload doesn't ask:", not prevented)
    await browser.close()


async def scenario_background_writes_wait(p):
    # 3. Background writers never open the take-over dialog.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, IMAC_LEASE)})
    await tick(page)
    print("the poll shows the iMac editing:", (await sync_state(page))['state'] == 'other' and (await marker(page))['text'] == 'editing on iMac')
    await page.evaluate("(l) => { window.__SYNC.acquire = 'busy'; window.__SYNC.busyLease = l; }", IMAC_LEASE)
    before = await writes(page)
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Job change', 2])")
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    await page.wait_for_timeout(200)
    print("a background write while 'other': no dialog:", await page.locator('#sync-takeover-dialog').count() == 0)
    print("...no acquire:", await lease_calls(page, 'acquire') == [])
    print("...nothing written:", await writes(page) == before)
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(200)
    print("a view-only click then doesn't carry the job's unleased change:", await writes(page) == before)
    await disk_change(page, {3: 'Letter from iMac'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4, IMAC_LEASE))
    await tick(page)
    print("...and a newer version doesn't reload it away:", (await sync_state(page))['reloads'] == 0 and (await sync_state(page))['unsaved'])
    # A person's click (Create missing previews) does ask.
    await page.click('#view-grid-btn')
    await page.wait_for_timeout(200)
    if await page.locator('#create-previews-btn').is_visible():
        await page.click('#create-previews-btn')
        await page.wait_for_timeout(300)
    print("Create missing previews is a person's click: it asks:", await page.locator('#sync-takeover-dialog').count() == 1)
    await page.click('#sync-takeover-cancel-btn')
    await page.wait_for_timeout(200)
    await browser.close()

    # State none, lease busy: a background write asks nothing either and becomes 'other'.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "acquire": "busy", "busyLease": IMAC_LEASE})
    before = await writes(page)
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Job change', 2])")
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    await page.wait_for_timeout(300)
    print("background write, lease busy: no dialog:", await page.locator('#sync-takeover-dialog').count() == 0)
    print("...nothing written, state other:", await writes(page) == before and (await sync_state(page))['state'] == 'other')
    await open_edit(page)
    print("...a person's edit afterwards still asks:", await page.locator('#sync-takeover-dialog').count() == 1)
    await page.click('#sync-takeover-btn')
    await page.wait_for_timeout(300)
    await page.fill('#e-title', 'Mine')
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(400)
    print("...and Take over writes both:", await disk_doc_title(page, 1) == 'Mine' and await disk_doc_title(page, 2) == 'Job change')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_takeover_layer_removed(p):
    # 4. The take-over promise settles when its layer goes away.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "acquire": "busy", "busyLease": BUSY_LEASE})
    await open_edit(page)
    print("dialog open:", await page.locator('#sync-takeover-dialog').count() == 1)
    await page.evaluate("document.getElementById('sync-takeover-layer').remove()")
    await page.wait_for_timeout(200)
    print("removing its layer settles it (no acquire left pending):", not (await sync_state(page))['pending'])
    print("...nothing written, no form:", await disk_doc_title(page, 1) == 'Invoice' and await page.locator('#e-title').count() == 0)
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(300)
    print("...the next attempt asks again:", await page.locator('#sync-takeover-dialog').count() == 1 and len(await lease_calls(page, 'acquire')) == 2)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_sync_read_before_writes(p):
    # 5. A write right after opening waits for the sync file to be read (and takes the lease).
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
    print("a real write right after opening waits for the sync file and takes the lease:", len(await lease_calls(page, 'acquire')) == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_unanswered_backoff(p):
    # 6. After an unanswered acquire, a person's save doesn't ask again for about a minute (it holds back at once).
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "down": True})
    await edit_title(page, 'One')
    n1 = len(await lease_calls(page, 'acquire'))
    await edit_title(page, 'Two')
    print("unanswered acquire: the next edit within a minute doesn't ask:", n1 == 1 and len(await lease_calls(page, 'acquire')) == 1)
    print("...both held back, nothing written:", await disk_doc_title(page, 1) == 'Invoice' and (await sync_state(page))['unsaved'])
    await page.evaluate("window.__SYNC.down = false")
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    await page.wait_for_timeout(300)
    print("...the tick's retry writes the latest:", await disk_doc_title(page, 1) == 'Two')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_idle_and_forms(p):
    # N4: an open Edit form counts as activity -- no idle release under it.
    browser, page, errors = await open_app(p, seed=SEED2)
    await open_edit(page)
    print("holding with the Edit form open:", (await sync_state(page))['state'] == 'holding')
    for _ in range(11):
        await page.evaluate("window.__DEBUG_syncNow(60 * 1000)")
    print("...no release after 11 minutes while it's open:", await lease_calls(page, 'release') == [] and (await sync_state(page))['state'] == 'holding')
    await page.click('#cancel-edit-btn')
    await page.wait_for_timeout(150)
    for _ in range(11):
        await page.evaluate("window.__DEBUG_syncNow(60 * 1000)")
    print("...released 10 quiet minutes after it closes:", len(await lease_calls(page, 'release')) == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_dialog_open_refuses(p):
    # N1 (a): an Edit form open on v3; the lease lapsed and the iMac changed the document (v4).
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, THIS_LEASE)})
    await open_edit(page)
    await page.fill('#e-title', 'Typed on the old version')
    await disk_change(page, {1: 'Invoice (iMac)'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquireVersion = 4; }", state(4))
    await tick(page)
    await page.click('#e-type-fields-btn')
    await page.wait_for_timeout(400)
    st = await sync_state(page)
    print("Set up fields from the stale Edit form: no reload under it:", st['reloads'] == 0, st)
    print("...Field Settings doesn't open:", await page.evaluate("document.getElementById('modal-root-over').innerHTML === ''"))
    print("...the status line says to close and start again:", 'close this dialog and start again' in await status(page), await status(page))
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(600)
    print("...Save then doesn't overwrite the iMac's change:", await disk_doc_title(page, 1) == 'Invoice (iMac)')
    print("...it's kept aside instead:", len(await kept_aside_names(page)) == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_library_check_stale(p):
    # N1 (b): Library check's lists come from v3; the iMac's v4 uses the "orphaned" tag again.
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
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquireVersion = 4; }", state(4))
    await tick(page)
    btn = page.locator('.orphaned-row button').first
    print("Library check lists the tag as orphaned:", await btn.count() == 1)
    await btn.click()
    await page.wait_for_timeout(600)
    disk = await page.evaluate("async () => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text())")
    print("Delete after a foreign version bump: the iMac's tag survives:", any(t['name'] == 'old' for t in disk['tags']) and disk['document_tags'] == [{"document_id": 2, "tag_id": 1}], disk.get('tags'), disk.get('document_tags'))
    print("...the status line says to close and start again:", 'close this dialog and start again' in await status(page), await status(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_reload_refused(p):
    # N2: the reload a gated action needs is refused (a background job runs) → the action doesn't start.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3), "acquireVersion": 4})
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


async def scenario_connected_elsewhere(p):
    # NEW-3: connected in another tab: the token appears in localStorage; the next tick writes the held-back change.
    browser, page, errors = await open_app(p, token=None)
    await edit_title(page, 'Held back')
    print("held back while not connected:", (await sync_state(page))['unsaved'])
    await page.evaluate("([k, t]) => localStorage.setItem(k, t)", [TOKEN_KEY, 'admin-tok'])
    await tick(page)
    await page.wait_for_timeout(300)
    print("connected in another tab: the next tick writes it:", await saved_title(page) == 'Held back' and (await marker(page))['text'] == '✎ editing')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_held_back_copy(p):
    # Held-back changes don't live only in memory: 30 s after the last one, a .kept-aside copy.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "down": True})
    await edit_title(page, 'Kept in a copy')
    await page.evaluate("window.__DEBUG_syncNow(20 * 1000)")
    print("20 s after holding back: no copy yet:", await kept_aside_names(page) == [])
    await page.evaluate("window.__DEBUG_syncNow(11 * 1000)")
    await page.wait_for_timeout(200)
    names = await kept_aside_names(page)
    print("after 30 s: a .kept-aside copy with this tab's change:", len(names) == 1 and await kept_aside_title(page, names[0]) == 'Kept in a copy', names)
    print("...the live library.sqlite unchanged:", await disk_doc_title(page, 1) == 'Invoice')
    m = await marker(page)
    print("...the marker's tooltip names the folder:", f'.kept-aside/{names[0]}' in m['title'], m['title'])
    print("...and the status line:", f'.kept-aside/{names[0]}' in await status(page), await status(page))
    await edit_title(page, 'Changed again')
    await page.evaluate("window.__DEBUG_syncNow(31 * 1000)")
    await page.wait_for_timeout(200)
    names2 = await kept_aside_names(page)
    print("...a further change updates the same copy:", names2 == names and await kept_aside_title(page, names[0]) == 'Changed again', names2)
    await page.evaluate("window.__SYNC.down = false")
    await tick(page)
    await page.wait_for_timeout(300)
    print("once the service answers it's written for real, the copy kept:", await disk_doc_title(page, 1) == 'Changed again' and await kept_aside_names(page) == names)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_person_change_not_dropped(p):
    # NEW-1: a person's flow is mid-way (its change in memory, its save still to come) when a job's save meets a newer version.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "state": state(3, THIS_LEASE)})
    await page.evaluate("window.__DEBUG_ensureEditLease()")
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET title = ? WHERE id = ?', ['Person change', 1])")
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquireVersion = 4; }", state(4))
    await tick(page)
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    await page.wait_for_timeout(600)
    names = await kept_aside_names(page)
    print("a job's save during a person's flow: the person's change is kept aside, not dropped:", len(names) == 1 and await kept_aside_title(page, names[0]) == 'Person change', names)
    print("...nothing written over the iMac's version:", await disk_doc_title(page, 2) == 'Receipt (iMac)')
    print("...and the notice says so:", await page.locator('#sync-notice-dialog').count() == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_idle_non_edit_dialogs(p):
    # Concern 4: only an editing flow's dialog keeps the lease; and not past an hour without input.
    browser, page, errors = await open_app(p, seed=SEED2)
    await edit_title(page, 'Mine')
    await page.click('#tools-btn'); await page.click('#storage-stats-btn')
    await page.wait_for_timeout(300)
    for _ in range(11):
        await page.evaluate("window.__DEBUG_syncNow(60 * 1000)")
    print("Storage stats open: the lease still goes after 10 quiet minutes:", len(await lease_calls(page, 'release')) == 1)
    await browser.close()
    browser, page, errors = await open_app(p, seed=SEED2)
    await open_edit(page)
    for _ in range(72):
        await page.evaluate("window.__DEBUG_syncNow(60 * 1000)")
    print("an Edit form left an hour without input: the lease goes after all:", len(await lease_calls(page, 'release')) == 1)
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


# The iMac changes the library while this tab's drop is mid-way: the lease
# has lapsed (no lease in the state), the hub is at v4, and a job's save
# comes along. Installed on the files folder: `before_copy` runs when the
# active copy of a file is about to be written (after the gate, before its
# INSERT), `before_sidecar` when its sidecar is (after its INSERT, before
# its own save).
HOOK_FILES = """([copyName, sidecarName, tickBeforeCopy]) => {
    const files = window.__TEST_ROOT._children.get('files');
    const orig = files.getFileHandle.bind(files);
    window.__HOOK_LOG = [];
    files.getFileHandle = async (name, opts) => {
        if(tickBeforeCopy && name.endsWith(copyName) && !window.__HOOK_COPY_DONE){
            window.__HOOK_COPY_DONE = true;
            await window.__DEBUG_syncNow(0);          // a tick between the gate and the first INSERT
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
            window.__SYNC.acquireVersion = 4;
            await window.__DEBUG_syncNow(0);          // the poll: the lease lapsed, v4 exists
            window.__HOOK_LOG.push('job:' + await window.__DEBUG_persistDb({ background: true }));   // a job's save, behind
            await new Promise(r => setTimeout(r, 400));   // the sidecar write takes a while (iCloud)
        }
        return orig(name, opts);
    };
}"""


async def scenario_multi_drop_job_save(p):
    # R1 (a): a two-file drop. File 1's save clears the pending flag; file 2's INSERT is in memory when a job's save meets v4.
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
    # F2: a person's flow is running -- the keep-aside is announced, never quiet.
    print("...the notice is shown (a person's flow was running):", await page.locator('#sync-notice-dialog').count() == 1)
    st = await status(page)
    print("...the drop's own final status names the kept-aside folder:", where['two'] and where['two'] != 'library' and f'.kept-aside/{where["two"]}' in st and 'Added 2 documents' in st, st)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_tick_before_insert(p):
    # R1 (b): one dropped file. A tick runs between the gate and the INSERT (nothing dirty yet), then a job's save meets v4.
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


async def disk_file_hash(page, id):
    return await page.evaluate("async (id) => JSON.parse(await (await window.__TEST_ROOT._children.get('library.sqlite').getFile()).text()).documents.find(d => d.id === id).file_hash", id)


async def scenario_held_back_copy_race(p):
    # R2: a held-back copy still being written when the change is written for real doesn't claim the episode afterwards;
    # two copies at once (a tick and pagehide) make one folder.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "down": True})
    await page.evaluate("""() => {
        const root = window.__TEST_ROOT;
        const orig = root.getDirectoryHandle.bind(root);
        root.getDirectoryHandle = async (name, opts) => {
            if(name === '.kept-aside' && window.__SLOW_KEPT) await new Promise(r => setTimeout(r, 600));
            return orig(name, opts);
        };
    }""")
    await edit_title(page, 'First episode')
    await page.evaluate("() => { window.__SLOW_KEPT = true; window.dispatchEvent(new Event('pagehide')); window.dispatchEvent(new Event('pagehide')); }")
    await page.wait_for_timeout(50)
    await page.evaluate("window.__SYNC.down = false")
    await tick(page, 5 * 1000)          # the service answers: the change is written for real while the copy is still being written
    await page.wait_for_timeout(1500)
    print("the change is written for real:", await disk_doc_title(page, 1) == 'First episode' and not (await sync_state(page))['unsaved'])
    names = await kept_aside_names(page)
    print("two copies started at once made one folder:", len(names) == 1, names)
    st = await status(page)
    print("...the late copy doesn't claim 'also kept safe' for a change already saved:", 'also kept safe' not in st, st)
    m = await marker(page)
    print("...nor the marker's tooltip:", '.kept-aside' not in m['title'], m['title'])
    # A new held-back episode gets its own folder, not the late copy's.
    await page.evaluate("window.__SLOW_KEPT = false; window.__SYNC.down = true")
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(3, None))
    await release_and_hold_back(page, 'Second episode')
    await page.evaluate("window.__DEBUG_syncNow(31 * 1000)")
    await page.wait_for_timeout(300)
    names2 = await kept_aside_names(page)
    new = [n for n in names2 if n not in names]
    print("a later episode gets a folder of its own:", len(new) == 1 and await kept_aside_title(page, new[0]) == 'Second episode', names2)
    print("no page errors:", not errors, errors)
    await browser.close()


async def release_and_hold_back(page, title):
    """Give the lease back (idle), then make a change while the service doesn't answer: held back."""
    for _ in range(11):
        await page.evaluate("window.__DEBUG_syncNow(60 * 1000)")
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    await edit_title(page, title)


async def scenario_job_data_retried(p):
    # R3: a job's data held silently while the service didn't answer is written by a tick once it answers ...
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "down": True})
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET file_hash = ? WHERE id = ?', ['abc', 2])")
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    st = await sync_state(page)
    print("a job's data held silently:", st['dirty'] and not st['unsaved'], st)
    await page.evaluate("window.__SYNC.down = false")
    await tick(page, 61 * 1000)
    await page.wait_for_timeout(300)
    print("once the service answers, a tick writes it:", await disk_file_hash(page, 2) == 'abc' and not (await sync_state(page))['dirty'], await sync_state(page))
    await page.wait_for_timeout(100)
    print("no page errors:", not errors, errors)
    await browser.close()
    # ... and a person's flow meeting a newer version with only a job's data unwritten keeps it aside quietly and goes on.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "down": True})
    await page.evaluate("window.__DEBUG_dbRun('UPDATE documents SET file_hash = ? WHERE id = ?', ['abc', 2])")
    await page.evaluate("window.__DEBUG_persistDb({ background: true })")
    await disk_change(page, {2: 'Receipt (iMac)'}, sync_version=4)
    await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquireVersion = 4; window.__SYNC.down = false; }", state(4))
    await open_edit(page)
    print("Edit opens on the newer version (no 'couldn't be saved' notice):", await page.locator('#e-title').count() == 1 and await page.locator('#sync-notice-dialog').count() == 0)
    print("...the iMac's version is loaded:", 'Receipt (iMac)' in await row_text(page, 2))
    names = await kept_aside_names(page)
    held = names and await page.evaluate("""async (n) => JSON.parse(await (await window.__TEST_ROOT._children.get('.kept-aside')._children.get(n)._children.get('library.sqlite').getFile()).text()).documents.find(d => d.id === 2).file_hash""", names[0])
    print("...the job's data is kept aside quietly, not dropped:", len(names) == 1 and held == 'abc', names)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_quiet_copy_reused(p):
    # Quiet copies while a job blocks the reload: one folder, updated in place, holding the latest memory.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "acquireVersion": 4})
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
    await page.evaluate("(s) => { window.__SYNC.state = s; }", state(4, THIS_LEASE))
    await tick(page)
    await page.wait_for_timeout(300)
    print("...once the job ends the newer version loads:", 'Receipt (iMac)' in await row_text(page, 2))
    print("no notice for a job's data:", await page.locator('#sync-notice-dialog').count() == 0)
    print("no page errors:", not errors, errors)
    await browser.close()


# F1: a db.run during the reload's own awaits. The hook runs a person's change
# inside crypto.subtle.digest the first time an algorithm matching `algo` is
# hashed after it's armed.
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


async def scenario_reload_race(p):
    for algo, label in [('SHA-256', "the file's hash"), ('SHA-1', 'the stable-uid migration')]:
        browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok"})
        await page.evaluate(DIGEST_HOOK, [algo, 'UPDATE documents SET title = ? WHERE id = ?', ['Changed during reload', 1]])
        # The iMac's v4 is on disk; for the uid case one row there lacks its uid, so the reload's migration hashes.
        await page.evaluate("""async (dropUid) => {
            const h = window.__TEST_ROOT._children.get('library.sqlite');
            const data = JSON.parse(await (await h.getFile()).text());
            data.documents.find(x => x.id === 2).title = 'Receipt (iMac)';
            if(dropUid) data.documents.find(x => x.id === 4).uid = null;
            h._bytes = new TextEncoder().encode(JSON.stringify(data));
        }""", algo == 'SHA-1')
        await page.evaluate("(s) => { window.__SYNC.state = s; window.__SYNC.acquireVersion = 4; window.__DIGEST_ARMED = true; }", state(4))
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


async def scenario_held_back_saved_status(p):
    # F3: once the tick writes a held-back change, the stale "Not saved" line is replaced.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "down": True})
    await edit_title(page, 'Waited')
    print("held back: 'Not saved' on the status line:", (await status(page)).startswith('Not saved'), await status(page))
    await page.evaluate("window.__SYNC.down = false")
    await tick(page, 61 * 1000)
    await page.wait_for_timeout(300)
    st = await status(page)
    print("written by the tick: the status line says it's saved now:", await disk_doc_title(page, 1) == 'Waited' and 'Not saved' not in st and 'in the library now' in st, st)
    print("no page errors:", not errors, errors)
    await browser.close()


SCENARIOS = [scenario_no_sync_file, scenario_first_change, scenario_busy, scenario_offline, scenario_no_token,
             scenario_service_down, scenario_heartbeat, scenario_release, scenario_backup, scenario_german, scenario_header_height,
             scenario_reload_keeps_view, scenario_reload_keeps_scroll, scenario_reload_waits_for_dialog, scenario_holding_no_reload,
             scenario_acquire_newer_version, scenario_lost_via_state, scenario_kept_aside, scenario_last_error, scenario_german_task2,
             scenario_view_write_newer_on_disk, scenario_cancel_followups, scenario_background_writes_wait,
             scenario_takeover_layer_removed, scenario_sync_read_before_writes, scenario_unanswered_backoff,
             scenario_safety_net, scenario_sleep_lost_lease, scenario_background_files,
             scenario_idle_and_forms, scenario_dialog_open_refuses, scenario_library_check_stale, scenario_reload_refused,
             scenario_connected_elsewhere, scenario_held_back_copy, scenario_person_change_not_dropped, scenario_idle_non_edit_dialogs,
             scenario_multi_drop_job_save, scenario_tick_before_insert,
             scenario_held_back_copy_race, scenario_job_data_retried, scenario_quiet_copy_reused,
             scenario_reload_race, scenario_held_back_saved_status]


async def main():
    import sys
    only = sys.argv[1:]
    async with async_playwright() as p:
        for scenario in SCENARIOS:
            if only and not any(o in scenario.__name__ for o in only):
                continue
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
