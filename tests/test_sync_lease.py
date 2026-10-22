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
        if(headers.Authorization !== `Bearer ${S.token}`) return json(401, { error: 'Unauthorized' });
        const m = /^\\/admin\\/libraries\\/([^/]+)\\/lease$/.exec(url.slice(BASE.length));
        if(m && opts.method === 'POST'){
            if(headers['Content-Type'] !== 'application/json') return json(415, { error: 'JSON only' });
            const body = JSON.parse(opts.body);
            if(body.action === 'acquire'){
                const result = body.takeOver ? (S.takeOver || 'granted') : (S.acquire || 'granted');
                if(result === 'busy') return json(200, { result, lease: S.busyLease, version: 3 });
                return json(200, { result, lease: result === 'granted' ? { holder: 'this', deviceName: 'MacBook Pro', since: new Date().toISOString() } : null, version: 3 });
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


async def open_app(p, sync=None, token='admin-tok', sync_file=True, lang=None, width=1440, extra_files=None):
    browser = await p.chromium.launch()
    context = await browser.new_context(viewport={'width': width, 'height': 900}, timezone_id='UTC', locale='en-US')
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
    }""", [SEED, files])
    await page.click('#open-btn')
    await page.wait_for_timeout(400)
    return browser, page, errors


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


async def scenario_busy(p):
    browser, page, errors = await open_app(p, sync={"token": "admin-tok", "acquire": "busy", "busyLease": BUSY_LEASE})
    before = await writes(page)
    await page.click('tr[data-id="1"]')
    await page.wait_for_timeout(150)
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(200)
    await page.fill('#e-title', 'Mine')
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(300)
    text = await page.inner_text('#sync-takeover-dialog') if await page.locator('#sync-takeover-dialog').count() else ''
    print("busy: the take-over dialog names the device and time:", 'Being edited on MacBook Pro since 02:02 PM.' in text, repr(text))
    print("...with Take over and Cancel:", await page.locator('#sync-takeover-btn').count() == 1 and await page.locator('#sync-takeover-cancel-btn').count() == 1)
    print("...and nothing is written while it's open:", await writes(page) == before)
    await page.click('#sync-takeover-cancel-btn')
    await page.wait_for_timeout(300)
    print("Cancel writes nothing:", await writes(page) == before and await saved_title(page) == 'Invoice')
    print("...the dialog is gone:", await page.locator('#sync-takeover-dialog').count() == 0)
    m = await marker(page)
    print("...marker says unsaved changes:", m['visible'] and m['text'] == 'unsaved changes', m)
    print("...the change stays in this window:", 'Mine' in await page.inner_text('tr[data-id="1"]'))
    await page.click('th[data-key="title"]')
    await page.wait_for_timeout(200)
    print("a sort click now doesn't write the held-back change:", await writes(page) == before and await saved_title(page) == 'Invoice')

    # The next real save asks again; Escape is Cancel.
    await edit_title(page, 'Mine again', wait=300)
    print("the next save asks again:", await page.locator('#sync-takeover-dialog').count() == 1 and len(await lease_calls(page, 'acquire')) == 2)
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(300)
    print("Escape cancels (nothing written):", await page.locator('#sync-takeover-dialog').count() == 0 and await writes(page) == before)

    # And once more: Take over.
    await edit_title(page, 'Taken over', wait=300)
    await page.click('#sync-takeover-btn')
    await page.wait_for_timeout(400)
    acq = await lease_calls(page, 'acquire')
    print("Take over acquires with takeOver true:", acq[-1]['body'] == {"action": "acquire", "takeOver": True}, acq[-1])
    print("...then writes everything:", await saved_title(page) == 'Taken over' and await writes(page) > before)
    m = await marker(page)
    print("...marker reads '✎ editing':", m['text'] == '✎ editing', m)
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
    await edit_title(page, 'Meins', wait=300)
    text = await page.inner_text('#sync-takeover-dialog')
    print("German take-over dialog:", 'Wird seit 14:02 auf MacBook Pro bearbeitet.' in text and 'Übernehmen' in text, repr(text))
    await page.click('#sync-takeover-cancel-btn')
    await page.wait_for_timeout(300)
    print("German 'unsaved changes':", (await marker(page))['text'] == 'ungespeicherte Änderungen', await marker(page))
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


SCENARIOS = [scenario_no_sync_file, scenario_first_change, scenario_busy, scenario_offline, scenario_no_token,
             scenario_service_down, scenario_heartbeat, scenario_release, scenario_backup, scenario_german, scenario_header_height]


async def main():
    async with async_playwright() as p:
        for scenario in SCENARIOS:
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
