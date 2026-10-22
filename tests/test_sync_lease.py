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
    browser, page, errors = await open_app(p, token=None)
    await edit_title(page, 'Unconnected change')
    print("no token: the write goes through:", await saved_title(page) == 'Unconnected change')
    print("...with no admin calls:", await admin_calls(page) == [])
    m = await marker(page)
    print("...marker reads 'not connected':", m['visible'] and m['text'] == 'not connected', m)
    print("...its tooltip points to the devices dialog:", m['title'] == 'Connect in Tools › iPhone & other devices…', m['title'])
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_service_down(p):
    browser, page, errors = await open_app(p, sync={"token": "admin-tok", "down": True})
    await edit_title(page, 'Down change')
    print("service down: the write goes through:", await saved_title(page) == 'Down change')
    m = await marker(page)
    print("...marker reads 'not synced yet':", m['visible'] and m['text'] == 'not synced yet', m)
    print("...with the reason as its tooltip:", "didn't answer" in m['title'], m['title'])
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
    # 6. After an unanswered acquire, don't ask again for about a minute.
    browser, page, errors = await open_app(p, seed=SEED2, sync={"token": "admin-tok", "down": True})
    await edit_title(page, 'One')
    n1 = len(await lease_calls(page, 'acquire'))
    await edit_title(page, 'Two')
    print("unanswered acquire: the next save within a minute doesn't ask:", len(await lease_calls(page, 'acquire')) == n1 == 1 and await disk_doc_title(page, 1) == 'Two')
    await page.evaluate("window.__DEBUG_syncNow(61 * 1000)")
    await edit_title(page, 'Three')
    print("...after a minute it asks again:", len(await lease_calls(page, 'acquire')) == 2 and await disk_doc_title(page, 1) == 'Three')
    print("no page errors:", not errors, errors)
    await browser.close()


SCENARIOS = [scenario_no_sync_file, scenario_first_change, scenario_busy, scenario_offline, scenario_no_token,
             scenario_service_down, scenario_heartbeat, scenario_release, scenario_backup, scenario_german, scenario_header_height,
             scenario_reload_keeps_view, scenario_reload_keeps_scroll, scenario_reload_waits_for_dialog, scenario_holding_no_reload,
             scenario_acquire_newer_version, scenario_lost_via_state, scenario_kept_aside, scenario_last_error, scenario_german_task2,
             scenario_view_write_newer_on_disk, scenario_cancel_followups, scenario_background_writes_wait,
             scenario_takeover_layer_removed, scenario_sync_read_before_writes, scenario_unanswered_backoff,
             scenario_safety_net, scenario_sleep_lost_lease, scenario_background_files]


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
