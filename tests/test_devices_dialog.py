import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from datetime import datetime, timedelta, timezone
from playwright.async_api import async_playwright

# The "📱 iPhone & other devices…" dialog talks to Dossiary Sync's admin API
# on http://127.0.0.1:8769. A fake fetch plays that service per scenario; the
# shared stub would refuse any real request to it anyway, so no test reaches
# a Dossiary Sync running on this machine.
# config: { down, token, code, tooSoon (Retry-After seconds), libraries,
#           devices, forgotten (token revoked), failAllow (status) }
# Every request is logged in window.__CALLS.
FAKE_SYNC = """
(config) => {
    window.__CALLS = [];
    window.__SYNC = config;
    const BASE = 'http://127.0.0.1:8769';
    const json = (status, body, headers) => new Response(JSON.stringify(body), { status, headers: headers || {} });
    window.fetch = async (url, opts = {}) => {
        const headers = opts.headers || {};
        window.__CALLS.push({ url, method: opts.method || 'GET', auth: headers.Authorization || null,
                              contentType: headers['Content-Type'] || null, body: opts.body || null });
        const S = window.__SYNC;
        if(!url.startsWith(BASE + '/') || S.down) throw new TypeError('Failed to fetch');
        const path = url.slice(BASE.length);
        const method = opts.method || 'GET';
        if(method === 'POST' && headers['Content-Type'] !== 'application/json') return json(415, { error: 'Content-Type must be application/json' });
        const valid = !S.forgotten && headers.Authorization === `Bearer ${S.token}`;
        if(path === '/admin/health') return json(200, { service: 'dossiary-sync', version: '0.3.0', adminProtocol: 1, connected: valid });
        if(path === '/admin/connect/start' && method === 'POST'){
            if(S.tooSoon) return json(429, { error: 'Too soon' }, { 'Retry-After': String(S.tooSoon) });
            return json(200, { validFor: 300 });
        }
        if(path === '/admin/connect' && method === 'POST'){
            const body = JSON.parse(opts.body || '{}');
            if(body.code !== (S.code || 'KX7P2M9Q')) return json(403, { error: 'Wrong or expired code' });
            S.forgotten = false;
            return json(200, { token: S.token });
        }
        if(!valid) return json(401, { error: 'Unauthorized' });
        if(path === '/admin/connect' && method === 'DELETE'){ S.forgotten = true; return new Response(null, { status: 204 }); }
        if(path === '/admin/libraries') return json(200, S.libraries || []);
        if(path === '/admin/devices') return json(200, S.devices || []);
        const m = /^\\/admin\\/devices\\/([^/]+)(?:\\/(allow|deny))?$/.exec(path);
        if(m){
            const id = decodeURIComponent(m[1]);
            const device = (S.devices || []).find(d => d.id === id);
            if(!device) return json(404, { error: 'Unknown device' });
            if(m[2]){
                if(S.failAllow) return json(S.failAllow, { error: 'Unknown library' });
                const lib = JSON.parse(opts.body || '{}').library;
                if(m[2] === 'allow' && !device.libraries.includes(lib)) device.libraries.push(lib);
                if(m[2] === 'deny') device.libraries = device.libraries.filter(x => x !== lib);
                return json(200, device);
            }
            if(method === 'DELETE'){ S.devices = S.devices.filter(d => d.id !== id); return new Response(null, { status: 204 }); }
        }
        return json(404, { error: 'Not found' });
    };
}
"""

TOKEN_KEY = 'dossiary_sync_admin_token'


def iso_ago(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).strftime('%Y-%m-%dT%H:%M:%SZ')


def sample_sync():
    return {
        "token": "admin-tok",
        "libraries": [{"id": "lib-a", "name": "Household", "available": True},
                      {"id": "lib-b", "name": "Taxes", "available": False}],
        "devices": [
            {"id": "dev-1", "name": "Arne's iPhone", "role": "phone", "libraries": ["lib-a"], "lastSeen": iso_ago(minutes=5)},
            {"id": "dev-2", "name": "pi-copy", "role": "mirror", "libraries": [], "lastSeen": iso_ago(days=2)},
            {"id": "dev-3", "name": "Old Mac", "role": "restore", "libraries": [], "lastSeen": None},
        ],
    }


async def open_app(p, sync=None, token=None, lang=None):
    browser = await p.chromium.launch()
    page = await browser.new_page()
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
    if sync is not None:
        await page.evaluate(FAKE_SYNC, sync)
    await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({}); window.__TEST_ROOT.name = 'TestLib';")
    await page.click('#open-btn')
    await page.wait_for_timeout(300)
    return browser, page, errors


async def open_dialog(page):
    await page.click('#tools-btn')
    await page.click('#devices-btn')
    await page.wait_for_timeout(300)


async def calls(page):
    return await page.evaluate("window.__CALLS")


async def stored_token(page):
    return await page.evaluate("(k) => localStorage.getItem(k)", TOKEN_KEY)


async def scenario_not_running(p):
    browser, page, errors = await open_app(p)
    print("Tools menu has the devices entry:", await page.locator('#tools-menu #devices-btn').count() == 1)
    await open_dialog(page)
    body = await page.inner_text('#devices-dialog-body')
    print("nothing answering: says Dossiary Sync isn't running:", "isn't running" in body)
    href = await page.get_attribute('#devices-sync-link', 'href')
    print("...with the install link:", href == 'https://github.com/AarneAarebye/dossiary-sync')
    print("...and no Connect button:", await page.locator('#devices-connect-btn').count() == 0)

    # It starts while the dialog is open: Look again finds it.
    await page.evaluate(FAKE_SYNC, sample_sync())
    await page.click('#devices-retry-btn')
    await page.wait_for_timeout(300)
    print("Look again finds the service and offers Connect:", await page.locator('#devices-connect-btn').count() == 1)
    health = [c for c in await calls(page) if c['url'] == 'http://127.0.0.1:8769/admin/health']
    print("health asked without a token:", health and health[-1]['auth'] is None)
    await page.click('#modal-close-btn')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_connect(p):
    browser, page, errors = await open_app(p, sync=sample_sync())
    await open_dialog(page)
    await page.click('#devices-connect-btn')
    await page.wait_for_timeout(200)
    start = [c for c in await calls(page) if c['url'].endswith('/admin/connect/start')]
    print("Connect asks for a code, as JSON:", len(start) == 1 and start[0]['method'] == 'POST' and start[0]['contentType'] == 'application/json')
    print("code field with the notification hint:",
          await page.locator('#devices-code-input').count() == 1
          and 'enter the code shown in the notification' in (await page.inner_text('#devices-dialog-body')).lower())

    await page.fill('#devices-code-input', 'AAAA BBBB')
    await page.click('#devices-code-submit')
    await page.wait_for_timeout(200)
    print("wrong code says so:", "didn't work" in await page.inner_text('#devices-code-status'))
    print("...and stores no token:", await stored_token(page) is None)

    await page.fill('#devices-code-input', 'kx7p 2m9q')
    await page.press('#devices-code-input', 'Enter')
    await page.wait_for_timeout(400)
    conn = [c for c in await calls(page) if c['url'].endswith('/admin/connect') and c['method'] == 'POST'][-1]
    print("right code posted as {code, client}, normalised:",
          json.loads(conn['body']) == {"code": "KX7P2M9Q", "client": "Dossiary"} and conn['contentType'] == 'application/json')
    print("token stored in localStorage:", await stored_token(page) == 'admin-tok')
    print("connected view shows the devices:", await page.locator('.devices-row').count() == 3)
    devs = [c for c in await calls(page) if c['url'].endswith('/admin/devices')]
    print("devices asked with the token:", devs and devs[-1]['auth'] == 'Bearer admin-tok')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_too_soon(p):
    sync = sample_sync(); sync['tooSoon'] = 24
    browser, page, errors = await open_app(p, sync=sync)
    await open_dialog(page)
    await page.click('#devices-connect-btn')
    await page.wait_for_timeout(200)
    text = await page.inner_text('#devices-connect-status')
    print("429 says how long to wait:", '24' in text and 'second' in text, text)
    print("...and shows no code field:", await page.locator('#devices-code-input').count() == 0)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_connected(p):
    browser, page, errors = await open_app(p, sync=sample_sync(), token='admin-tok')
    await open_dialog(page)
    print("a stored, valid token goes straight to the devices:", await page.locator('.devices-row').count() == 3)
    roles = await page.eval_on_selector_all('.devices-row .devices-role', 'els => els.map(e => e.textContent)')
    print("role labels:", roles == ['iPhone or iPad', 'Raspberry Pi copy', 'Restore'], roles)
    seen = await page.eval_on_selector_all('.devices-row .devices-seen', 'els => els.map(e => e.textContent)')
    print("last seen is relative:", '5 minutes ago' in seen[0] and '2 days ago' in seen[1] and 'never' in seen[2].lower(), seen)
    phone_boxes = await page.eval_on_selector_all('.devices-row[data-id="dev-1"] .devices-lib-checkbox',
                                                  'els => els.map(e => [e.dataset.library, e.checked])')
    print("a phone gets one checkbox per shared library:", phone_boxes == [['lib-a', True], ['lib-b', False]], phone_boxes)
    print("a mirror gets none:", await page.locator('.devices-row[data-id="dev-2"] .devices-lib-checkbox').count() == 0)
    libs = await page.inner_text('#devices-libraries')
    print("shared libraries listed read-only, unavailable marked:", 'Household' in libs and 'Taxes' in libs and 'not available' in libs)
    print("...with the share-command note:", 'dossiary-sync share' in await page.inner_text('#devices-dialog-body'))

    # Allow
    await page.check('.devices-row[data-id="dev-1"] .devices-lib-checkbox[data-library="lib-b"]')
    await page.wait_for_timeout(300)
    allow = [c for c in await calls(page) if c['url'].endswith('/admin/devices/dev-1/allow')]
    print("ticking sends allow {library} as JSON with the token:",
          len(allow) == 1 and json.loads(allow[0]['body']) == {"library": "lib-b"}
          and allow[0]['contentType'] == 'application/json' and allow[0]['auth'] == 'Bearer admin-tok')
    status = await page.inner_text('#status')
    print("status line confirms:", "Arne's iPhone" in status and 'Taxes' in status, status)
    print("fake service updated:", await page.evaluate("window.__SYNC.devices[0].libraries") == ['lib-a', 'lib-b'])

    # Deny
    await page.uncheck('.devices-row[data-id="dev-1"] .devices-lib-checkbox[data-library="lib-a"]')
    await page.wait_for_timeout(300)
    deny = [c for c in await calls(page) if c['url'].endswith('/admin/devices/dev-1/deny')]
    print("unticking sends deny:", len(deny) == 1 and json.loads(deny[0]['body']) == {"library": "lib-a"})
    print("fake service updated again:", await page.evaluate("window.__SYNC.devices[0].libraries") == ['lib-b'])

    # Failure reverts the box and shows the error
    await page.evaluate("window.__SYNC.failAllow = 400")
    await page.check('.devices-row[data-id="dev-1"] .devices-lib-checkbox[data-library="lib-a"]')
    await page.wait_for_timeout(300)
    box = page.locator('.devices-row[data-id="dev-1"] .devices-lib-checkbox[data-library="lib-a"]')
    print("a refused change is undone:", not await box.is_checked())
    print("...and the status line shows the error:", 'err' in (await page.get_attribute('#status', 'class')) and 'Unknown library' in await page.inner_text('#status'))
    await page.evaluate("window.__SYNC.failAllow = 0")

    # Remove: cancel first, then accept
    dialogs = []
    async def dismiss(d):
        dialogs.append(d.message); await d.dismiss()
    page.once('dialog', lambda d: asyncio.ensure_future(dismiss(d)))
    await page.click('.devices-row[data-id="dev-2"] .devices-remove-btn')
    await page.wait_for_timeout(200)
    print("Remove asks first, naming the device:", dialogs and 'pi-copy can no longer fetch anything' in dialogs[0], dialogs)
    print("cancel removes nothing:", not any(c['method'] == 'DELETE' for c in await calls(page)) and await page.locator('.devices-row').count() == 3)
    page.once('dialog', lambda d: asyncio.ensure_future(d.accept()))
    await page.click('.devices-row[data-id="dev-2"] .devices-remove-btn')
    await page.wait_for_timeout(300)
    rm = [c for c in await calls(page) if c['method'] == 'DELETE' and c['url'].endswith('/admin/devices/dev-2')]
    print("confirming sends DELETE with the token:", len(rm) == 1 and rm[0]['auth'] == 'Bearer admin-tok')
    print("...and the row is gone:", await page.locator('.devices-row[data-id="dev-2"]').count() == 0 and await page.locator('.devices-row').count() == 2)
    print("...status confirms:", 'pi-copy' in await page.inner_text('#status'))

    # Language switch is blocked while the dialog is open (existing modal rule).
    await page.select_option('#lang-select', 'de', force=True)
    await page.wait_for_timeout(200)
    print("language switch blocked while open:",
          await page.evaluate("document.getElementById('lang-select').value") == 'en'
          and 'iPhone or iPad' in await page.inner_text('#devices-dialog-body'))

    # Disconnect
    await page.click('#devices-disconnect-btn')
    await page.wait_for_timeout(300)
    disc = [c for c in await calls(page) if c['method'] == 'DELETE' and c['url'].endswith('/admin/connect')]
    print("Disconnect revokes the token:", len(disc) == 1 and disc[0]['auth'] == 'Bearer admin-tok')
    print("...drops it locally and shows Connect:", await stored_token(page) is None and await page.locator('#devices-connect-btn').count() == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_token_dropped(p):
    # The service forgot this token (admin-revoke): health says not connected.
    sync = sample_sync(); sync['forgotten'] = True
    browser, page, errors = await open_app(p, sync=sync, token='admin-tok')
    await open_dialog(page)
    print("a revoked token is dropped, back to Connect:", await stored_token(page) is None and await page.locator('#devices-connect-btn').count() == 1)
    await page.click('#modal-close-btn')

    # Revoked while the dialog is open: the next protected call gets 401.
    await page.evaluate("([k]) => localStorage.setItem(k, 'admin-tok')", [TOKEN_KEY])
    await page.evaluate("window.__SYNC.forgotten = false")
    await open_dialog(page)
    print("connected again:", await page.locator('.devices-row').count() == 3)
    await page.evaluate("window.__SYNC.forgotten = true")
    await page.check('.devices-row[data-id="dev-1"] .devices-lib-checkbox[data-library="lib-b"]')
    await page.wait_for_timeout(300)
    print("a 401 drops the token and returns to Connect:", await stored_token(page) is None and await page.locator('#devices-connect-btn').count() == 1)
    print("...saying why:", 'connect again' in (await page.inner_text('#devices-dialog-body')).lower())
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_blocked_storage(p):
    # localStorage throwing must not break the dialog; the token lives in memory.
    browser = await p.chromium.launch()
    page = await browser.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    await page.route('**/*', lambda r: r.fulfill(body="/* stubbed */", content_type='application/javascript')
                     if any(s in r.request.url for s in ['sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js']) else r.continue_())
    await page.add_init_script(open('stub_studio2.js').read())
    await page.goto(f"file://{APP_PATH}")
    await page.wait_for_timeout(200)
    await page.evaluate(FAKE_SYNC, sample_sync())
    await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({});")
    await page.click('#open-btn')
    await page.wait_for_timeout(300)
    await page.evaluate("""() => { Storage.prototype.getItem = () => { throw new Error('blocked'); };
                                   Storage.prototype.setItem = () => { throw new Error('blocked'); };
                                   Storage.prototype.removeItem = () => { throw new Error('blocked'); }; }""")
    await open_dialog(page)
    await page.click('#devices-connect-btn')
    await page.wait_for_timeout(200)
    await page.fill('#devices-code-input', 'KX7P2M9Q')
    await page.click('#devices-code-submit')
    await page.wait_for_timeout(400)
    print("blocked localStorage: still connects (token in memory):", await page.locator('.devices-row').count() == 3)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_german(p):
    browser, page, errors = await open_app(p, sync=sample_sync(), token='admin-tok', lang='de')
    await page.click('#tools-btn')
    print("German menu label:", 'iPhone' in await page.inner_text('#devices-btn') and 'Geräte' in await page.inner_text('#devices-btn'))
    await page.click('#devices-btn')
    await page.wait_for_timeout(300)
    roles = await page.eval_on_selector_all('.devices-row .devices-role', 'els => els.map(e => e.textContent)')
    print("German role labels:", roles == ['iPhone oder iPad', 'Raspberry-Pi-Kopie', 'Wiederherstellung'], roles)
    seen = await page.eval_on_selector_all('.devices-row .devices-seen', 'els => els.map(e => e.textContent)')
    print("German relative time:", 'vor 5 Minuten' in seen[0], seen)
    print("no page errors:", not errors, errors)
    await browser.close()


SCENARIOS = [scenario_not_running, scenario_connect, scenario_too_soon, scenario_connected, scenario_token_dropped, scenario_blocked_storage, scenario_german]


async def main():
    async with async_playwright() as p:
        for scenario in SCENARIOS:
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
