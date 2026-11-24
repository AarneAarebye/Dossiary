import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Tools › "🔗 Dossiary Sync…" talks to Dossiary Sync's admin API on
# http://127.0.0.1:8769. Since 1.71.0 it only connects (devices, pairing,
# deleting and getting libraries left the page), and the page keeps
# its token so an open synced library is checked with Dossiary Sync. A fake
# fetch plays that service per scenario; the shared stub would refuse any
# real request to it anyway, so no test reaches a Dossiary Sync running on
# this machine.
# config: { down, token, code, tooSoon (Retry-After seconds), tooSoonBody,
#           libraries, forgotten (token revoked), librariesRaw (body for
#           /admin/libraries instead of the list), librariesStatus,
#           librariesError, libraries401 (a 401 although health says connected) }
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
        if(path === '/admin/libraries'){
            if(S.libraries401) return json(401, { error: 'Unauthorized' });
            if(S.librariesStatus) return json(S.librariesStatus, { error: S.librariesError || 'Library store broken' });
            return json(200, S.librariesRaw !== undefined ? S.librariesRaw : (S.libraries || []));
        }
        return json(404, { error: 'Not found' });
    };
}
"""

TOKEN_KEY = 'dossiary_sync_admin_token'
HOSTILE = '<img src=x onerror=window.__xss=1>'


def sample_sync():
    return {
        "token": "admin-tok",
        "libraries": [{"id": "lib-a", "name": "Household", "available": True},
                      {"id": "lib-b", "name": "Taxes", "available": False}],
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
    print("Tools menu has the Dossiary Sync entry:", await page.locator('#tools-menu #devices-btn').count() == 1)
    print("...named Dossiary Sync:", 'Dossiary Sync' in await page.locator('#devices-btn').text_content())
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
    print("connected view says so:", await page.locator('#devices-connected-text').count() == 1)
    libs = [c for c in await calls(page) if c['url'].endswith('/admin/libraries')]
    print("the token is checked with it:", libs and libs[-1]['auth'] == 'Bearer admin-tok')
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
    print("dialog titled Dossiary Sync:", (await page.inner_text('.devices-dialog h2')) == 'Dossiary Sync')
    print("a stored, valid token goes straight to the connected view:",
          'Connected to Dossiary Sync on this Mac' in await page.inner_text('#devices-connected-text'))
    body = await page.inner_text('#devices-dialog-body')
    print("no note about another app:", await page.locator('#devices-mac-note').count() == 0 and 'Dossiary for Mac' not in body)
    print("no devices, pairing or Get it any more:",
          await page.locator('.devices-row, #devices-add-btn, #devices-available-slot, #devices-libraries').count() == 0)
    print("...and no library names from the service:", 'Household' not in body and 'Taxes' not in body)
    print("only health and libraries asked:",
          sorted({c['url'].rsplit('8769', 1)[1] for c in await calls(page)}) == ['/admin/health', '/admin/libraries'])

    # Language switch is blocked while the dialog is open (existing modal rule).
    await page.select_option('#lang-select', 'de', force=True)
    await page.wait_for_timeout(200)
    print("language switch blocked while open:",
          await page.evaluate("document.getElementById('lang-select').value") == 'en'
          and 'Connected to Dossiary Sync' in await page.inner_text('#devices-dialog-body'))

    # Disconnect
    await page.click('#devices-disconnect-btn')
    await page.wait_for_timeout(300)
    disc = [c for c in await calls(page) if c['method'] == 'DELETE' and c['url'].endswith('/admin/connect')]
    print("Disconnect revokes the token:", len(disc) == 1 and disc[0]['auth'] == 'Bearer admin-tok')
    print("...drops it locally and shows Connect:", await stored_token(page) is None and await page.locator('#devices-connect-btn').count() == 1)
    print("...whose text says what connecting is for:", 'keep synced libraries safe' in await page.inner_text('#devices-dialog-body'))
    print("every call had a timeout signal:", all(c['hasSignal'] for c in await calls(page)))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_token_dropped(p):
    # The service forgot this token (admin-revoke): health says not connected.
    sync = sample_sync(); sync['forgotten'] = True
    browser, page, errors = await open_app(p, sync=sync, token='admin-tok')
    await open_dialog(page)
    print("a revoked token is dropped, back to Connect:", await stored_token(page) is None and await page.locator('#devices-connect-btn').count() == 1)
    print("...saying why:", 'connect again' in (await page.inner_text('#devices-dialog-body')).lower())
    await page.click('#modal-close-btn')

    # Revoked between health and the libraries call: the 401 drops it too.
    await page.evaluate("([k]) => localStorage.setItem(k, 'admin-tok')", [TOKEN_KEY])
    await page.evaluate("window.__SYNC.forgotten = false; window.__SYNC.libraries401 = true")
    await open_dialog(page)
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
    print("blocked localStorage: still connects (token in memory):", await page.locator('#devices-connected-text').count() == 1)
    print("no page errors:", not errors, errors)
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
    libs = [c for c in await calls(page) if c['url'].endswith('/admin/libraries')]
    print("token kept in memory when it can't be stored:", await page.locator('#devices-connected-text').count() == 1
          and libs and libs[-1]['auth'] == 'Bearer admin-tok')
    await page.click('#modal-close-btn')
    await open_dialog(page)
    print("...and used again on the next open:", await page.locator('#devices-connected-text').count() == 1)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_german(p):
    browser, page, errors = await open_app(p, sync=sample_sync(), lang='de')
    await page.click('#tools-btn')
    print("German menu label:", (await page.inner_text('#devices-btn')) == '🔗 Dossiary Sync…')
    await page.click('#devices-btn')
    await page.wait_for_timeout(300)
    print("German Connect text:", 'synchronisierte Bibliotheken schützen' in await page.inner_text('#devices-dialog-body'))
    await page.click('#modal-close-btn')
    await page.evaluate("([k]) => localStorage.setItem(k, 'admin-tok')", [TOKEN_KEY])
    await open_dialog(page)
    print("German connected text:", 'Mit Dossiary Sync auf diesem Mac verbunden' in await page.inner_text('#devices-connected-text'))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_bad_answers(p):
    # /admin/libraries answers an error: shown as text with Look again, the token kept.
    sync = sample_sync(); sync['librariesStatus'] = 500; sync['librariesError'] = HOSTILE
    browser, page, errors = await open_app(p, sync=sync, token='admin-tok')
    await open_dialog(page)
    body = await page.inner_text('#devices-dialog-body')
    print("a failing service: its error shown as text:", HOSTILE in body and '(500)' in body, body)
    print("...no element injected:", await page.locator('#devices-dialog-body img').count() == 0)
    print("...no script ran:", await page.evaluate("window.__xss") is None)
    print("...the token is kept:", await stored_token(page) == 'admin-tok')
    await page.evaluate("delete window.__SYNC.librariesStatus")
    await page.click('#devices-retry-btn')
    await page.wait_for_timeout(300)
    print("Look again connects:", await page.locator('#devices-connected-text').count() == 1)
    print("no page errors:", not [e for e in errors if '500' not in e], errors)
    await browser.close()


async def scenario_service_goes_down(p):
    browser, page, errors = await open_app(p, sync=sample_sync(), token='admin-tok')
    await page.evaluate("window.__SYNC.down = true")
    await open_dialog(page)
    print("the service gone: says it isn't running:", "isn't running" in await page.inner_text('#devices-dialog-body'))
    print("...the token is kept for when it's back:", await stored_token(page) == 'admin-tok')
    await page.evaluate("window.__SYNC.down = false")
    await page.click('#devices-retry-btn')
    await page.wait_for_timeout(300)
    print("Look again: connected without a new code:", await page.locator('#devices-connected-text').count() == 1)
    print("no page errors:", not [e for e in errors if 'Failed to fetch' not in e], errors)
    await browser.close()


async def scenario_admin_gone(p):
    # 1.71.0: the start screen, the Recent libraries rows and Tools have no device or delete entries any more.
    browser = await p.chromium.launch()
    page = await browser.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    await page.add_init_script(open('stub_studio2.js').read())
    await page.goto(f"file://{APP_PATH}")
    await page.wait_for_timeout(200)
    print("no devices button on the start screen:", await page.locator('#empty-devices-btn').count() == 0)
    await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({}); window.__TEST_ROOT.name = 'TestLib';")
    await page.click('#open-btn')
    await page.wait_for_timeout(300)
    print("no Delete this library in Tools:", await page.locator('#delete-library-btn').count() == 0)
    print("no page errors:", not errors, errors)
    await browser.close()


SCENARIOS = [scenario_admin_gone, scenario_not_running, scenario_connect, scenario_too_soon, scenario_connected, scenario_token_dropped,
             scenario_blocked_storage, scenario_storage_refuses_write, scenario_german, scenario_bad_answers, scenario_service_goes_down]


async def main():
    async with async_playwright() as p:
        for scenario in SCENARIOS:
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
