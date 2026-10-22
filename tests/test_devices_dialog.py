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
#           devices, forgotten (token revoked), failAllow (status),
#           librariesRaw (body for /admin/libraries instead of the list),
#           devicesStatus (status for /admin/devices), pairFail (status),
#           pairExpiresIn (seconds), pairCode, pairFingerprint }
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
                              contentType: headers['Content-Type'] || null, body: opts.body || null,
                              hasSignal: !!opts.signal });
        const S = window.__SYNC;
        if(!url.startsWith(BASE + '/') || S.down) throw new TypeError('Failed to fetch');
        const path = url.slice(BASE.length);
        const method = opts.method || 'GET';
        if(method === 'POST' && headers['Content-Type'] !== 'application/json') return json(415, { error: 'Content-Type must be application/json' });
        const valid = !S.forgotten && headers.Authorization === `Bearer ${S.token}`;
        if(path === '/admin/health') return json(200, { service: 'dossiary-sync', version: '0.3.0', adminProtocol: 1, connected: valid });
        if(path === '/admin/connect/start' && method === 'POST'){
            if(S.tooSoon) return json(429, S.tooSoonBody ? { error: 'Too soon', retryAfter: S.tooSoonBody } : { error: 'Too soon' }, S.tooSoonBody ? {} : { 'Retry-After': String(S.tooSoon) });
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
        if(path === '/admin/libraries') return json(200, S.librariesRaw !== undefined ? S.librariesRaw : (S.libraries || []));
        if(path === '/admin/devices') return S.devicesStatus ? json(S.devicesStatus, { error: 'Device store broken' }) : json(200, S.devices || []);
        if(path === '/admin/pair-code' && method === 'POST'){
            const libs = JSON.parse(opts.body || '{}').libraries;
            if(S.pairFail) return json(S.pairFail, { error: 'Unknown library' });
            if(!Array.isArray(libs) || !libs.length) return json(400, { error: 'Choose at least one library' });
            const code = S.pairCode || 'QWER7YUP', f = S.pairFingerprint || 'AB:CD:EF:01';
            S.pairCount = (S.pairCount || 0) + 1;
            return json(200, { code, fingerprint: f,
                               expires: new Date(Date.now() + (S.pairExpiresIn || 300) * 1000).toISOString(),
                               addresses: ['https://mac.local:8443'],
                               link: `dossiary-sync://pair?v=1&f=${encodeURIComponent(f)}&c=${code}&a=${encodeURIComponent('https://mac.local:8443')}&n=${S.pairCount}` });
        }
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

# Stands in for qrcode-generator (the real one comes from cdnjs, which the
# tests never reach): records what it was asked to encode.
FAKE_QR = """
() => {
    window.__QR_DATA = [];
    window.qrcode = (type, ecl) => ({
        addData(d){ window.__QR_DATA.push({ d, type, ecl }); }, make(){},
        getModuleCount(){ return 21; }, isDark(r, c){ return (r * c + r) % 3 === 0; },
    });
}
"""
HOSTILE = '<img src=x onerror=window.__xss=1>'


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


async def open_app(p, sync=None, token=None, lang=None, qr=True):
    browser = await p.chromium.launch()
    page = await browser.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)

    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        elif 'qrcode' in url:
            await route.abort()   # the QR library never loads from the network in tests
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
    if qr:
        await page.evaluate(FAKE_QR)
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

    # The wait time from the JSON body (no readable Retry-After header).
    sync = sample_sync(); sync['tooSoon'] = 1; sync['tooSoonBody'] = 17
    browser, page, errors = await open_app(p, sync=sync)
    await open_dialog(page)
    await page.click('#devices-connect-btn')
    await page.wait_for_timeout(200)
    text = await page.inner_text('#devices-connect-status')
    print("429 body retryAfter is used:", '17' in text and '30' not in text, text)
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
    print("German add button:", await page.inner_text('#devices-add-btn') == 'iPhone oder iPad hinzufügen…')
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_pair(p):
    sync = sample_sync(); sync['pairFail'] = 400; sync['pairExpiresIn'] = 3
    browser, page, errors = await open_app(p, sync=sync, token='admin-tok')
    await open_dialog(page)
    await page.click('#devices-add-btn')
    boxes = await page.eval_on_selector_all('.devices-pair-lib-checkbox', 'els => els.map(e => [e.dataset.library, e.checked])')
    print("Add iPhone or iPad lists the shared libraries, none ticked:", boxes == [['lib-a', False], ['lib-b', False]], boxes)
    print("Show QR code disabled with no library:", await page.is_disabled('#devices-show-qr-btn'))
    await page.check('.devices-pair-lib-checkbox[data-library="lib-a"]')
    print("...enabled once one is ticked:", not await page.is_disabled('#devices-show-qr-btn'))
    await page.uncheck('.devices-pair-lib-checkbox[data-library="lib-a"]')
    print("...disabled again when unticked:", await page.is_disabled('#devices-show-qr-btn'))
    await page.evaluate("document.getElementById('devices-show-qr-btn').disabled = false")
    await page.click('#devices-show-qr-btn')
    await page.wait_for_timeout(200)
    print("zero libraries: asks for one, sends nothing:",
          'at least one library' in await page.inner_text('#devices-pair-status')
          and not any(c['url'].endswith('/admin/pair-code') for c in await calls(page)))

    # The service refuses: its reason is shown, the choice stays.
    await page.check('.devices-pair-lib-checkbox[data-library="lib-a"]')
    await page.click('#devices-show-qr-btn')
    await page.wait_for_timeout(300)
    print("a refused pair-code shows the reason:", 'Unknown library' in await page.inner_text('#devices-pair-status'))
    print("...keeps the ticked library and the button usable:",
          await page.is_checked('.devices-pair-lib-checkbox[data-library="lib-a"]') and not await page.is_disabled('#devices-show-qr-btn'))

    await page.evaluate("window.__SYNC.pairFail = 0")
    await page.click('#devices-show-qr-btn')
    await page.wait_for_timeout(300)
    pc = [c for c in await calls(page) if c['url'].endswith('/admin/pair-code')][-1]
    print("pair-code posted {libraries} as JSON with the token:",
          json.loads(pc['body']) == {"libraries": ["lib-a"]} and pc['contentType'] == 'application/json' and pc['auth'] == 'Bearer admin-tok')
    link = await page.get_attribute('#devices-qr', 'data-link')
    print("QR drawn as SVG:", await page.locator('#devices-qr svg path').count() == 1)
    qr_data = await page.evaluate("window.__QR_DATA")
    print("...of the link:", link.startswith('dossiary-sync://pair?v=1&') and qr_data[-1]['d'] == link, link)
    print("code shown as text, grouped:", await page.inner_text('#devices-pair-code') == 'QWER 7YUP')
    print("fingerprint shown as text:", await page.inner_text('#devices-pair-fingerprint') == 'AB:CD:EF:01')
    print("instructions:", 'Add from Mac' in await page.inner_text('#devices-add-slot'))
    cd = await page.inner_text('#devices-pair-countdown')
    print("countdown:", cd in ('Valid for 0:03', 'Valid for 0:02'), cd)
    print("New code hidden while valid:", not await page.is_visible('#devices-qr-new-btn'))

    await page.wait_for_timeout(3500)
    print("expired: says so:", await page.inner_text('#devices-pair-countdown') == 'This code has expired.')
    print("...removes the QR:", await page.locator('#devices-qr svg').count() == 0)
    print("...offers New code:", await page.is_visible('#devices-qr-new-btn'))

    await page.evaluate("window.__SYNC.pairExpiresIn = 125")
    await page.click('#devices-qr-new-btn')
    await page.wait_for_timeout(300)
    link2 = await page.get_attribute('#devices-qr', 'data-link')
    print("New code asks again and draws the new link:",
          len([c for c in await calls(page) if c['url'].endswith('/admin/pair-code')]) == 3 and link2 != link
          and await page.locator('#devices-qr svg').count() == 1)
    cd = await page.inner_text('#devices-pair-countdown')
    print("countdown shows minutes:", cd in ('Valid for 2:05', 'Valid for 2:04'), cd)

    # A device removed meanwhile re-renders the list; the QR stays.
    page.once('dialog', lambda d: asyncio.ensure_future(d.accept()))
    await page.click('.devices-row[data-id="dev-3"] .devices-remove-btn')
    await page.wait_for_timeout(300)
    print("QR survives a removal:", await page.get_attribute('#devices-qr', 'data-link') == link2)

    n_dev_calls = len([c for c in await calls(page) if c['url'].endswith('/admin/devices')])
    await page.click('#devices-pair-done-btn')
    await page.wait_for_timeout(300)
    print("Done reloads the devices and folds the section:",
          len([c for c in await calls(page) if c['url'].endswith('/admin/devices')]) == n_dev_calls + 1
          and await page.locator('#devices-add-btn').count() == 1 and await page.locator('#devices-qr').count() == 0)

    # Closing the dialog with a QR open stops the countdown quietly.
    await page.click('#devices-add-btn')
    await page.check('.devices-pair-lib-checkbox[data-library="lib-b"]')
    await page.click('#devices-show-qr-btn')
    await page.wait_for_timeout(300)
    await page.click('#modal-close-btn')
    await page.wait_for_timeout(1300)
    print("every call had a timeout signal:", all(c['hasSignal'] for c in await calls(page)))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_pair_edge_cases(p):
    # 401 on pair-code: the token is gone.
    browser, page, errors = await open_app(p, sync=sample_sync(), token='admin-tok')
    await open_dialog(page)
    await page.click('#devices-add-btn')
    await page.check('.devices-pair-lib-checkbox[data-library="lib-a"]')
    await page.evaluate("window.__SYNC.forgotten = true")
    await page.click('#devices-show-qr-btn')
    await page.wait_for_timeout(300)
    print("401 on pair-code: back to Connect, token dropped:",
          await page.locator('#devices-connect-btn').count() == 1 and await stored_token(page) is None)
    await browser.close()

    # The QR library can't load (offline): the code and fingerprint still show.
    browser, page, errors = await open_app(p, sync=sample_sync(), token='admin-tok', qr=False)
    await open_dialog(page)
    await page.click('#devices-add-btn')
    await page.check('.devices-pair-lib-checkbox[data-library="lib-a"]')
    await page.click('#devices-show-qr-btn')
    await page.wait_for_timeout(600)
    print("QR library missing: says so:", "couldn't be drawn" in await page.inner_text('#devices-pair-status'))
    print("...still shows code and fingerprint:", await page.inner_text('#devices-pair-code') == 'QWER 7YUP'
          and await page.inner_text('#devices-pair-fingerprint') == 'AB:CD:EF:01')
    print("...and no SVG:", await page.locator('#devices-qr svg').count() == 0)
    print("...offers New code:", await page.is_visible('#devices-qr-new-btn'))
    n = await page.evaluate("window.__SYNC.pairCount")
    await page.click('#devices-qr-new-btn')
    await page.wait_for_timeout(600)
    print("...New code requests a fresh code:", await page.evaluate("window.__SYNC.pairCount") == n + 1)
    print("...and only one QR script tried per draw:",
          await page.evaluate("document.querySelectorAll('script[src*=qrcode-generator]').length") <= 1)
    print("no page errors:", not [e for e in errors if 'ERR_FAILED' not in e], errors)
    await browser.close()

    # No libraries shared: nothing to choose.
    sync = sample_sync(); sync['libraries'] = []
    browser, page, errors = await open_app(p, sync=sync, token='admin-tok')
    await open_dialog(page)
    await page.click('#devices-add-btn')
    print("no shared libraries: no QR button, says so:",
          await page.locator('#devices-show-qr-btn').count() == 0 and 'No libraries are shared yet' in await page.inner_text('#devices-add-slot'))
    await page.click('#devices-pair-cancel-btn')
    print("Cancel folds it again:", await page.locator('#devices-add-btn').count() == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_hostile_names(p):
    sync = sample_sync()
    sync['libraries'][0]['name'] = HOSTILE
    sync['devices'][0]['name'] = HOSTILE
    sync['pairFingerprint'] = HOSTILE
    sync['pairCode'] = HOSTILE
    browser, page, errors = await open_app(p, sync=sync, token='admin-tok')
    await open_dialog(page)
    await page.click('#devices-add-btn')
    await page.check('.devices-pair-lib-checkbox[data-library="lib-a"]')
    await page.click('#devices-show-qr-btn')
    await page.wait_for_timeout(400)
    body = await page.inner_text('#devices-dialog-body')
    print("hostile device/library/code/fingerprint shown as text:", body.count(HOSTILE) >= 5, body.count(HOSTILE))
    print("...no element injected:", await page.locator('#devices-dialog-body img').count() == 0)
    print("...no script ran:", await page.evaluate("window.__xss") is None)
    # The status line names them too.
    await page.check('.devices-row[data-id="dev-1"] .devices-lib-checkbox[data-library="lib-b"]')
    await page.wait_for_timeout(300)
    print("status line shows the name as text:", HOSTILE in await page.inner_text('#status')
          and await page.evaluate("window.__xss") is None)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_service_goes_down(p):
    browser, page, errors = await open_app(p, sync=sample_sync(), token='admin-tok')
    await open_dialog(page)
    await page.evaluate("window.__SYNC.down = true")
    box = '.devices-row[data-id="dev-1"] .devices-lib-checkbox[data-library="lib-b"]'
    await page.click(box)   # not check(): the refusal undoes the tick before check() could see it
    await page.wait_for_timeout(300)
    status = await page.inner_text('#status')
    print("toggling with the service gone: clear error:", "didn't answer" in status and 'err' in await page.get_attribute('#status', 'class'), status)
    print("...tick undone, checkbox usable again:", not await page.is_checked(box) and not await page.is_disabled(box))
    page.once('dialog', lambda d: asyncio.ensure_future(d.accept()))
    await page.click('.devices-row[data-id="dev-2"] .devices-remove-btn')
    await page.wait_for_timeout(300)
    status = await page.inner_text('#status')
    print("Remove with the service gone: clear error:", "Couldn't remove pi-copy" in status and "didn't answer" in status, status)
    print("...row kept:", await page.locator('.devices-row[data-id="dev-2"]').count() == 1)
    await page.click('#devices-add-btn')
    await page.check('.devices-pair-lib-checkbox[data-library="lib-a"]')
    await page.click('#devices-show-qr-btn')
    await page.wait_for_timeout(300)
    print("Show QR code with the service gone: clear error, button usable:",
          "didn't answer" in await page.inner_text('#devices-pair-status') and not await page.is_disabled('#devices-show-qr-btn'))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_bad_answers(p):
    # /admin/libraries answers 200 but not a list: say so, not "refused (200)".
    sync = sample_sync(); sync['librariesRaw'] = {"oops": True}
    browser, page, errors = await open_app(p, sync=sync, token='admin-tok')
    await open_dialog(page)
    body = await page.inner_text('#devices-dialog-body')
    print("libraries in an unknown shape: reported as such:", "doesn't understand" in body and '(200)' not in body, body)
    await browser.close()
    # /admin/devices fails while libraries are fine: that failure is reported.
    sync = sample_sync(); sync['devicesStatus'] = 500
    browser, page, errors = await open_app(p, sync=sync, token='admin-tok')
    await open_dialog(page)
    body = await page.inner_text('#devices-dialog-body')
    print("devices failing: its error is the one shown:", 'Device store broken (500)' in body, body)
    print("no page errors:", not [e for e in errors if '500' not in e], errors)
    await browser.close()


async def scenario_storage_refuses_write(p):
    # localStorage reads fine but won't store (quota): the token is still used.
    browser, page, errors = await open_app(p, sync=sample_sync())
    await page.evaluate("() => { Storage.prototype.setItem = () => { throw new Error('QuotaExceededError'); }; }")
    await open_dialog(page)
    await page.click('#devices-connect-btn')
    await page.wait_for_timeout(200)
    await page.fill('#devices-code-input', 'KX7P2M9Q')
    await page.click('#devices-code-submit')
    await page.wait_for_timeout(400)
    devs = [c for c in await calls(page) if c['url'].endswith('/admin/devices')]
    print("token kept in memory when it can't be stored:", await page.locator('.devices-row').count() == 3
          and devs and devs[-1]['auth'] == 'Bearer admin-tok')
    await page.click('#modal-close-btn')
    await open_dialog(page)
    print("...and used again on the next open:", await page.locator('.devices-row').count() == 3)
    print("no page errors:", not errors, errors)
    await browser.close()


SCENARIOS = [scenario_not_running, scenario_connect, scenario_too_soon, scenario_connected, scenario_token_dropped, scenario_blocked_storage, scenario_german,
             scenario_pair, scenario_pair_edge_cases, scenario_hostile_names, scenario_service_goes_down, scenario_bad_answers, scenario_storage_refuses_write]


async def main():
    async with async_playwright() as p:
        for scenario in SCENARIOS:
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
