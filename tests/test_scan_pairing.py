import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Pairing with the scan helper (scanix500 0.3.0+): /health reports `paired`,
# POST /pair swaps the code the helper's menu shows for a token, and every
# later request carries `Authorization: Bearer <token>`. A fake fetch plays
# the bridge: it accepts code 123456 once, and /scan answers 401 without
# the token it handed out.
FAKE_BRIDGE = """
() => {
    window.__CALLS = [];
    window.__BRIDGE = { token: 'tok-1', forgotten: false, legacy: false };
    window.fetch = async (url, opts = {}) => {
        const headers = opts.headers || {};
        window.__CALLS.push({ url, method: opts.method || 'GET', auth: headers.Authorization || null,
                              body: opts.body || null, contentType: headers['Content-Type'] || null });
        const B = window.__BRIDGE;
        const valid = !B.forgotten && headers.Authorization === `Bearer ${B.token}`;
        const json = (status, body) => new Response(JSON.stringify(body), { status });
        if(url.endsWith('/health')){
            return json(200, B.legacy ? { service: 'scanix500-bridge' } : { service: 'scanix500-bridge', paired: valid });
        }
        if(url.endsWith('/pair')){
            const body = JSON.parse(opts.body || '{}');
            if(body.code !== '123456') return json(403, { error: "That code isn't right." });
            B.forgotten = false;
            return json(200, { ok: true, token: B.token });
        }
        if(url.includes('/scan?')){
            if(!B.legacy && !valid) return json(401, { error: 'not paired' });
            return json(200, { ok: true, partial: false, message: 'ok', output_paths: [],
                               files: [{ filename: 'scan.pdf', content_base64: btoa('%PDF-1.4 fake ' + window.__CALLS.length) }] });
        }
        return json(404, { error: 'not found' });
    };
}
"""

async def main():
    async with async_playwright() as p:
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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("localStorage.removeItem('dossiary_scan_tokens')")
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)
        await page.evaluate(FAKE_BRIDGE)

        async def calls():
            return await page.evaluate("window.__CALLS")
        async def rows():
            return await page.locator('#doc-tbody tr').count()

        # === Scenario 1: first scan with an unpaired browser -- the health
        # probe says paired: false, so the pairing dialog opens before any
        # scan request is sent; no Authorization header without a token ===
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        c = await calls()
        print("pairing dialog opens for an unpaired browser:", await page.locator('#scan-pair-code').count() == 1)
        print("no scan request was sent before pairing:", not any('/scan?' in x['url'] for x in c))
        print("health probe sent no Authorization header without a token:", c[0]['url'].endswith('/health') and c[0]['auth'] is None)
        status = await page.inner_text('#status')
        print("status line asks to pair:", 'Pair' in status)
        title = await page.inner_text('.modal h2')
        print("dialog title is translated:", title == 'Pair with the Scan Helper')

        # === Scenario 2: a malformed code is refused locally, a wrong code
        # shows the helper's refusal, and the dialog stays open ===
        await page.fill('#scan-pair-code', '12a')
        await page.click('#scan-pair-submit-btn')
        await page.wait_for_timeout(150)
        print("malformed code refused without contacting the helper:",
              'Enter the 6-digit code' in await page.inner_text('#scan-pair-status')
              and not any(x['url'].endswith('/pair') for x in await calls()))
        await page.fill('#scan-pair-code', '999999')
        await page.click('#scan-pair-submit-btn')
        await page.wait_for_timeout(200)
        print("wrong code shows a 'didn't work' message:", "didn't work" in await page.inner_text('#scan-pair-status'))
        print("dialog stays open after a wrong code:", await page.locator('#scan-pair-code').count() == 1)

        # === Scenario 3: the right code (typed with a space, as the helper
        # shows it) pairs: POST /pair with JSON {code, client}, the token is
        # stored per helper address, and the scan proceeds with it ===
        await page.fill('#scan-pair-code', '123 456')
        await page.press('#scan-pair-code', 'Enter')
        await page.wait_for_timeout(500)
        c = await calls()
        pair_call = [x for x in c if x['url'].endswith('/pair')][-1]
        print("POST /pair sent JSON with the code and client name:",
              pair_call['method'] == 'POST' and pair_call['contentType'] == 'application/json'
              and json.loads(pair_call['body']) == {'code': '123456', 'client': 'Dossiary'})
        tokens = await page.evaluate("JSON.parse(localStorage.getItem('dossiary_scan_tokens'))")
        print("token stored in localStorage under the helper's address:", tokens == {'http://localhost:8765': 'tok-1'})
        scan_calls = [x for x in c if '/scan?' in x['url']]
        print("the scan ran right after pairing, with the token:", len(scan_calls) == 1 and scan_calls[0]['auth'] == 'Bearer tok-1')
        print("dialog closed after pairing:", await page.locator('#scan-pair-code').count() == 0)
        print("the scanned file reached the library:", await rows() == 1)

        # === Scenario 4: later scans send the token straight away, no dialog ===
        await page.evaluate("window.__CALLS = []")
        await page.click('#scan-btn')
        await page.wait_for_timeout(400)
        c = await calls()
        print("a later scan goes straight to /scan with the token:",
              len(c) == 1 and '/scan?' in c[0]['url'] and c[0]['auth'] == 'Bearer tok-1')
        print("no pairing dialog for a paired browser:", await page.locator('#scan-pair-code').count() == 0)

        # === Scenario 5: the helper forgot its paired browsers -- the scan
        # answers 401, the stale token is dropped and the dialog comes back;
        # pairing again finishes the scan ===
        await page.evaluate("window.__BRIDGE.forgotten = true; window.__CALLS = []")
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        print("a 401 brings the pairing dialog back:", await page.locator('#scan-pair-code').count() == 1)
        tokens = await page.evaluate("JSON.parse(localStorage.getItem('dossiary_scan_tokens'))")
        print("the stale token was removed:", tokens == {})
        buttons = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both scan buttons re-enabled after the 401:", buttons)
        before = await rows()
        await page.fill('#scan-pair-code', '123456')
        await page.click('#scan-pair-submit-btn')
        await page.wait_for_timeout(500)
        print("re-pairing finishes the scan:", await rows() == before + 1)

        # === Scenario 6: Cancel closes the dialog without pairing ===
        await page.evaluate("window.__BRIDGE.forgotten = true")
        await page.click('#scan-multi-btn')
        await page.wait_for_timeout(300)
        await page.click('#scan-pair-cancel-btn')
        await page.wait_for_timeout(100)
        print("Cancel closes the pairing dialog:", await page.locator('#scan-pair-code').count() == 0)

        # === Scenario 7: a bridge older than 0.3.0 (no `paired` field, no
        # pairing) still scans without any dialog ===
        await page.evaluate("localStorage.removeItem('dossiary_scan_tokens')")
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(300)
        await page.evaluate(FAKE_BRIDGE)
        await page.evaluate("window.__BRIDGE.legacy = true")
        await page.click('#scan-btn')
        await page.wait_for_timeout(400)
        c = await calls()
        print("an older bridge scans with no pairing dialog:",
              await page.locator('#scan-pair-code').count() == 0 and any('/scan?' in x['url'] for x in c))
        print("no Authorization header sent to an older bridge without a token:", all(x['auth'] is None for x in c))

        # === Scenario 8: the dialog in another language ===
        await page.evaluate("window.__BRIDGE.legacy = false; localStorage.removeItem('dossiary_scan_tokens')")
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(150)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        print("pairing dialog title in German:", await page.inner_text('.modal h2') == 'Mit dem Scan-Helfer koppeln')

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
