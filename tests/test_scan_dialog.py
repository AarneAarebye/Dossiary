import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# A fake fetch playing any number of scan helpers, keyed by base URL.
# config: { '<base url>': { version: 1 | 2 | 'other', token, helper, scanners,
#            legacy (v1 without pairing), forgotten (tokens revoked), down
#            (unreachable), code (pairing code, default '123456'),
#            scanResponses: [{status, body} | {network: true}] (consumed one per scan) } }
# Every request is logged in window.__CALLS.
FAKE_HELPERS = """
(config) => {
    window.__CALLS = [];
    window.__HELPERS = config;
    const json = (status, body) => new Response(JSON.stringify(body), { status });
    window.fetch = async (url, opts = {}) => {
        const headers = opts.headers || {};
        window.__CALLS.push({ url, method: opts.method || 'GET', auth: headers.Authorization || null,
                              contentType: headers['Content-Type'] || null, body: opts.body || null });
        const base = Object.keys(window.__HELPERS).find(b => url === b || url.startsWith(b + '/') || url.startsWith(b + '?'));
        if(!base) throw new TypeError('Failed to fetch');
        const H = window.__HELPERS[base];
        if(H.down) throw new TypeError('Failed to fetch');
        const path = url.slice(base.length);
        const valid = !H.forgotten && headers.Authorization === `Bearer ${H.token}`;
        const v2err = (status, message) => json(status, { ok: false, partial: false, message });
        if(path === '/health'){
            if(H.version === 'other') return json(200, { hello: 'world' });
            if(H.version === 2) return json(200, { ok: true, helper: H.helper || 'dossiary-scan-helper-test', version: '1.0.0', protocol: 2, paired: valid });
            return json(200, H.legacy ? { service: 'scanix500-bridge' } : { service: 'scanix500-bridge', paired: valid });
        }
        if(path === '/pair'){
            const body = JSON.parse(opts.body || '{}');
            if(body.code !== (H.code || '123456')) return H.version === 2 ? v2err(403, 'Choose Pair a browser… and try the new code.') : json(403, { error: "That code isn't right." });
            H.forgotten = false;
            return json(200, { ok: true, token: H.token });
        }
        if(path === '/scanners' && H.version === 2){
            if(!valid) return v2err(401, 'Pair this browser first.');
            return json(200, { scanners: H.scanners || [] });
        }
        if(path === '/scan' || path.startsWith('/scan?')){
            if(!H.legacy && !valid) return H.version === 2 ? v2err(401, 'Pair this browser first.') : json(401, { error: 'not paired' });
            const next = (H.scanResponses || []).shift();
            if(next && next.network) throw new TypeError('Failed to fetch');
            if(next && next.delayMs) await new Promise(r => setTimeout(r, next.delayMs));
            if(next && next.status) return next.raw ? new Response(next.raw, { status: next.status }) : json(next.status, next.body);
            const n = window.__CALLS.length;
            if(H.version === 2) return json(200, { ok: true, partial: false, message: '1 page scanned.',
                                                   files: [{ name: `scan_${n}.pdf`, pages: 1, data: btoa('%PDF-1.4 fake v2 ' + n) }] });
            return json(200, { ok: true, partial: false, message: 'ok', output_paths: [],
                               files: [{ filename: `scan_${n}.pdf`, content_base64: btoa('%PDF-1.4 fake v1 ' + n) }] });
        }
        return H.version === 2 ? v2err(404, 'Not found.') : json(404, { error: 'not found' });
    };
}
"""

V2_SCANNERS = [
    {"id": "fake:flatbed", "name": "Fake Flatbed", "sources": ["flatbed"], "duplex": False,
     "colorModes": ["color", "gray", "bw"], "resolutions": [150, 300, 600], "extras": []},
    {"id": "fake:feeder", "name": "Fake Feeder", "sources": ["feeder", "flatbed"], "duplex": True,
     "colorModes": ["color", "gray", "bw"], "resolutions": [150, 300, 600], "extras": []},
    {"id": "fake:splitter", "name": "Fake Splitter", "sources": ["feeder"], "duplex": False,
     "colorModes": ["color", "gray", "bw"], "resolutions": [150, 300, 600],
     "extras": ["splitOnBlank", "skipBlankPages", "futureThing"]},
]

L1 = 'http://localhost:8765'
L2 = 'http://localhost:8766'


async def open_app(p, tokens=None, lang=None, helpers=None):
    """Opens the app on a fresh seeded library. `tokens` seeds stored pairing
    tokens, `lang` the UI language, `helpers` installs FAKE_HELPERS before the
    library opens (otherwise call it yourself afterwards)."""
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
    await page.evaluate("(t) => localStorage.setItem('dossiary_scan_tokens', JSON.stringify(t))", tokens or {})
    if helpers is not None:
        await page.evaluate(FAKE_HELPERS, helpers)
    await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({}); window.__TEST_ROOT.name = 'TestLib';")
    await page.click('#open-btn')
    await page.wait_for_timeout(300)
    return browser, page, errors


async def calls(page):
    return await page.evaluate("window.__CALLS")


# === Task 1: discovery ===
async def scenario_discovery(p):
    browser, page, errors = await open_app(p)

    # With no fake helpers, the stub's guard makes every helper unreachable --
    # no test ever talks to a real scanix500 running on this machine.
    d = await page.evaluate("window.__DEBUG_scanDiscovery()")
    print("no helpers found when nothing answers:", d['helpers'] == [] and d['choices'] == [])

    await page.evaluate(FAKE_HELPERS, {
        L1: {"version": 1, "token": "tok-1"},
        L2: {"version": 2, "token": "tok-2", "helper": "dossiary-scan-helper-macos",
             "scanners": V2_SCANNERS + [{"id": "ic:ix", "name": "ScanSnap iX500", "sources": ["feeder"], "duplex": True,
                                         "colorModes": ["color"], "resolutions": [300], "extras": []},
                                        {"id": 7, "name": "broken entry"}]},
        'http://localhost:9000': {"version": 2, "token": "tok-9"},
        'http://localhost:9100': {"version": 'other'},
    })
    await page.evaluate("(t) => localStorage.setItem('dossiary_scan_tokens', JSON.stringify(t))",
                        {L1: 'tok-1', L2: 'tok-2'})

    # The manual address is probed too; 127.0.0.1:8765 is the same helper as localhost:8765.
    await page.evaluate("window.__DEBUG_setScanBridgeUrl('http://127.0.0.1:8765/')")
    d = await page.evaluate("window.__DEBUG_scanDiscovery()")
    print("127.0.0.1 manual address isn't probed twice:", [h['url'] for h in d['helpers']] == [L1, L2])

    await page.evaluate("window.__DEBUG_setScanBridgeUrl('http://localhost:9000')")
    d = await page.evaluate("window.__DEBUG_scanDiscovery()")
    by_url = {h['url']: h for h in d['helpers']}
    print("version 1 helper found, paired, with the iX500 entry:",
          by_url[L1]['version'] == 1 and by_url[L1]['paired'] and by_url[L1]['scannerIds'] == ['scanix500'])
    print("version 2 helper found with its valid scanners only:",
          by_url[L2]['version'] == 2 and by_url[L2]['scannerIds'] == ['fake:flatbed', 'fake:feeder', 'fake:splitter', 'ic:ix'])
    print("manual address probed; unpaired version 2 helper lists no scanners:",
          by_url['http://localhost:9000']['paired'] is False and by_url['http://localhost:9000']['scannerIds'] == [])
    labels = [c['label'] for c in d['choices']]
    print("same scanner name on two helpers gets the helper in brackets:",
          'ScanSnap iX500 (scanix500)' in labels and 'ScanSnap iX500 (dossiary-scan-helper-macos)' in labels)
    print("unique names stay plain:", 'Fake Feeder' in labels)
    print("choice keys are '<helper url>|<scanner id>':", f'{L2}|fake:feeder' in [c['key'] for c in d['choices']])

    c = await calls(page)
    health_9000 = [x for x in c if x['url'] == 'http://localhost:9000/health']
    print("no Authorization header without a stored token:", health_9000 and health_9000[-1]['auth'] is None)
    scanners_l2 = [x for x in c if x['url'] == f'{L2}/scanners']
    print("/scanners is asked with the stored token:", scanners_l2 and scanners_l2[-1]['auth'] == 'Bearer tok-2')

    # A helper that forgot this browser answers /scanners with 401 -> not paired.
    await page.evaluate(f"window.__HELPERS['{L2}'].forgotten = true")
    d = await page.evaluate("window.__DEBUG_scanDiscovery()")
    l2 = next(h for h in d['helpers'] if h['url'] == L2)
    print("a 401 from /scanners marks the helper not paired:", l2['paired'] is False and l2['scannerIds'] == [])

    # A manual address where something answers /health but isn't a scan helper.
    await page.evaluate("window.__DEBUG_setScanBridgeUrl('http://localhost:9100')")
    d = await page.evaluate("window.__DEBUG_scanDiscovery()")
    probed = any(x['url'] == 'http://localhost:9100/health' for x in await calls(page))
    print("a /health that isn't a scan helper is probed but ignored:",
          probed and 'http://localhost:9100' not in [h['url'] for h in d['helpers']])

    print("no page errors:", errors == [])
    await browser.close()


SCENARIOS = [scenario_discovery]


async def main():
    async with async_playwright() as p:
        for scenario in SCENARIOS:
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
