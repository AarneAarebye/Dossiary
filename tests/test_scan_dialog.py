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


# === Task 2: the dialog, per-scanner settings, remembered settings, nothing found ===
async def scenario_dialog(p):
    browser, page, errors = await open_app(p, tokens={L1: 'tok-1', L2: 'tok-2'})
    await page.evaluate(FAKE_HELPERS, {L1: {"version": 1, "token": "tok-1"},
                                       L2: {"version": 2, "token": "tok-2", "scanners": V2_SCANNERS}})

    await page.evaluate("window.__DEBUG_openScanDialog({})")
    await page.wait_for_timeout(300)
    options = await page.eval_on_selector_all('#scan-dialog-scanner option', 'els => els.map(e => e.textContent)')
    print("dialog lists every found scanner:", options == ['ScanSnap iX500', 'Fake Flatbed', 'Fake Feeder', 'Fake Splitter'])
    print("dialog title:", await page.inner_text('.modal h2') == 'Scan')

    # The iX500 (version 1): no source/color/resolution choices, only split on blank pages.
    print("iX500 shows no source, color or resolution choice:",
          await page.locator('#scan-dialog-source').count() == 0 and await page.locator('#scan-dialog-color').count() == 0
          and await page.locator('#scan-dialog-resolution').count() == 0)
    extras = await page.eval_on_selector_all('.scan-dialog-extra', 'els => els.map(e => e.dataset.extra)')
    print("iX500 offers split on blank pages, unticked:", extras == ['splitOnBlank']
          and not await page.is_checked('.scan-dialog-extra[data-extra=splitOnBlank]'))
    print("iX500 hides two-sided:", not await page.is_visible('#scan-dialog-duplex-wrap'))

    # Fake Feeder: two sources; two-sided only with the feeder.
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:feeder')
    sources = await page.eval_on_selector_all('#scan-dialog-source option', 'els => els.map(e => e.textContent)')
    print("feeder scanner lists its sources:", sources == ['Document feeder', 'Flatbed'])
    print("two-sided shown with the feeder:", await page.is_visible('#scan-dialog-duplex-wrap'))
    await page.check('#scan-dialog-duplex')
    await page.select_option('#scan-dialog-source', 'flatbed')
    print("two-sided hidden and cleared on the flatbed:",
          not await page.is_visible('#scan-dialog-duplex-wrap') and not await page.is_checked('#scan-dialog-duplex'))
    colors = await page.eval_on_selector_all('#scan-dialog-color option', 'els => els.map(e => e.textContent)')
    print("color modes labelled:", colors == ['Color', 'Grayscale', 'Black & white'])
    res = await page.eval_on_selector_all('#scan-dialog-resolution option', 'els => els.map(e => e.textContent)')
    print("resolutions labelled in dpi:", res == ['150 dpi', '300 dpi', '600 dpi'])

    # Fake Splitter: known extras only, the unknown one never shown.
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:splitter')
    extras = await page.eval_on_selector_all('.scan-dialog-extra', 'els => els.map(e => e.dataset.extra)')
    print("only known extras shown:", extras == ['splitOnBlank', 'skipBlankPages'])

    # readScanDialogSettings() + saveLastScanSettings() round trip, then reopening restores them.
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:feeder')
    await page.select_option('#scan-dialog-source', 'feeder')
    await page.check('#scan-dialog-duplex')
    await page.select_option('#scan-dialog-color', 'gray')
    await page.select_option('#scan-dialog-resolution', '600')
    saved = await page.evaluate("(async () => { const s = window.__DEBUG_readScanDialogSettings(); await window.__DEBUG_saveLastScanSettings(s); return s; })()")
    print("settings read from the dialog:", saved == {"scanner": f"{L2}|fake:feeder", "source": "feeder", "duplex": True,
                                                       "colorMode": "gray", "resolution": 600, "extras": {}})
    db = await page.evaluate("(async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text()))()")
    row = next((r for r in db['settings'] if r['key'] == 'scan_last_settings'), None)
    print("last settings saved in the library:", row is not None and json.loads(row['value']) == saved)

    await page.click('#scan-dialog-cancel-btn')
    await page.evaluate("window.__DEBUG_openScanDialog({})")
    await page.wait_for_timeout(300)
    print("reopening selects the remembered scanner:", await page.eval_on_selector('#scan-dialog-scanner', 'e => e.value') == f'{L2}|fake:feeder')
    print("...and its remembered settings:",
          await page.eval_on_selector('#scan-dialog-source', 'e => e.value') == 'feeder'
          and await page.is_checked('#scan-dialog-duplex')
          and await page.eval_on_selector('#scan-dialog-color', 'e => e.value') == 'gray'
          and await page.eval_on_selector('#scan-dialog-resolution', 'e => e.value') == '600')

    # The splitOnBlank option ticks the extra (Scan Multi's shortcut, Task 5).
    await page.click('#scan-dialog-cancel-btn')
    await page.evaluate(f"window.__DEBUG_saveLastScanSettings({{scanner: '{L1}|scanix500', extras: {{}}}})")
    await page.evaluate("window.__DEBUG_openScanDialog({splitOnBlank: true})")
    await page.wait_for_timeout(300)
    print("splitOnBlank option ticks split on blank pages:", await page.is_checked('.scan-dialog-extra[data-extra=splitOnBlank]'))

    # A remembered scanner that's gone falls back to the first.
    await page.click('#scan-dialog-cancel-btn')
    await page.evaluate(f"window.__DEBUG_saveLastScanSettings({{scanner: '{L2}|fake:gone', extras: {{}}}})")
    await page.evaluate("window.__DEBUG_openScanDialog({})")
    await page.wait_for_timeout(300)
    print("a gone scanner falls back to the first:", await page.eval_on_selector('#scan-dialog-scanner', 'e => e.value') == f'{L1}|scanix500')
    print("Scan button enabled with a scanner:", await page.is_enabled('#scan-dialog-start-btn'))

    # Nothing found: links, address field, Look again with a new address.
    await page.click('#scan-dialog-cancel-btn')
    await page.evaluate(f"window.__HELPERS['{L1}'].down = true; window.__HELPERS['{L2}'].down = true;")
    await page.evaluate("window.__DEBUG_openScanDialog({})")
    await page.wait_for_timeout(300)
    body = await page.inner_text('#scan-dialog-body')
    print("nothing found explains a helper is needed:", 'No scan helper answered' in body)
    print("links to dossiary-scan-helper releases and scanix500:",
          await page.get_attribute('#scan-dialog-helper-link', 'href') == 'https://github.com/AarneAarebye/dossiary-scan-helper/releases'
          and await page.get_attribute('#scan-dialog-scanix500-link', 'href') == 'https://github.com/AarneAarebye/iX500')
    print("Scan button disabled with nothing found:", not await page.is_enabled('#scan-dialog-start-btn'))
    await page.fill('#scan-dialog-address', 'not a url')
    await page.click('#scan-dialog-retry-btn')
    print("an invalid address is refused:", 'http://localhost:8766' in await page.inner_text('#scan-dialog-status'))
    await page.evaluate("window.__HELPERS['http://localhost:9300'] = {version: 1, token: 'tok-3', legacy: true}")
    await page.fill('#scan-dialog-address', 'http://localhost:9300/')
    await page.click('#scan-dialog-retry-btn')
    await page.wait_for_timeout(300)
    print("Look again finds the helper at the new address:", await page.locator('#scan-dialog-scanner').count() == 1)
    db = await page.evaluate("(async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text()))()")
    print("the new address is saved as scan_bridge_url:",
          next(r['value'] for r in db['settings'] if r['key'] == 'scan_bridge_url') == 'http://localhost:9300')

    print("no page errors:", errors == [])
    await browser.close()

    # German labels.
    browser, page, errors = await open_app(p, tokens={L2: 'tok-2'}, lang='de')
    await page.evaluate(FAKE_HELPERS, {L2: {"version": 2, "token": "tok-2", "scanners": V2_SCANNERS}})
    await page.evaluate("window.__DEBUG_openScanDialog({})")
    await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:feeder')
    print("German dialog title:", await page.inner_text('.modal h2') == 'Scannen')
    print("German source label:", 'Dokumenteneinzug' in await page.inner_text('#scan-dialog-settings'))
    await browser.close()


async def db_state(page):
    return await page.evaluate("(async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text()))()")

async def inbox_names(page):
    return await page.evaluate("""(async () => {
        const dir = await window.__TEST_ROOT.getDirectoryHandle('inbox', {create: true});
        const names = []; for await (const [n] of dir.entries()) names.push(n); return names.sort();
    })()""")

async def start_scan(page, wait=400):
    await page.click('#scan-dialog-start-btn')
    await page.wait_for_timeout(wait)


# === Task 3: scanning through a version 1 helper (scanix500) ===
async def scenario_scan_v1(p):
    browser, page, errors = await open_app(p, tokens={L1: 'tok-1'})
    await page.evaluate(FAKE_HELPERS, {L1: {"version": 1, "token": "tok-1"}})

    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    print("toolbar Scan opens the scan dialog:", await page.locator('#scan-dialog-scanner').count() == 1)
    print("old port dialog is gone:", await page.locator('#scan-connect-port').count() == 0)
    await start_scan(page)
    c = await calls(page)
    scan = [x for x in c if '/scan?' in x['url']]
    print("version 1 request with split_on_blank=false:",
          len(scan) == 1 and scan[0]['url'] == f'{L1}/scan?skip_blank_filter=false&skip_ocr=false&split_on_blank=false'
          and scan[0]['method'] == 'POST' and scan[0]['auth'] == 'Bearer tok-1' and scan[0]['body'] is None)
    print("dialog closes after a successful scan:", await page.locator('#scan-dialog-body').count() == 0)
    db = await db_state(page)
    print("the scan became an Inbox document:", len(db['documents']) == 1 and int(db['documents'][0]['needs_review']) == 1)
    print("Inbox view shown:", await page.get_attribute('#nav-item-inbox', 'class') and 'active' in await page.get_attribute('#nav-item-inbox', 'class'))
    print("inbox/ folder emptied again:", await inbox_names(page) == [])

    # Split on blank pages ticked -> split_on_blank=true; several files all arrive.
    await page.evaluate(f"""window.__HELPERS['{L1}'].scanResponses = [{{status: 200, body: {{ok: true, partial: false, message: 'ok', output_paths: [],
        files: [{{filename: 'a.pdf', content_base64: btoa('%PDF-1.4 A')}}, {{filename: 'b.pdf', content_base64: btoa('%PDF-1.4 B')}}]}}}}]""")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await page.check('.scan-dialog-extra[data-extra=splitOnBlank]')
    await start_scan(page)
    c = await calls(page)
    print("split on blank pages sends split_on_blank=true:", c[[i for i, x in enumerate(c) if '/scan?' in x['url']][-1]]['url'].endswith('split_on_blank=true'))
    db = await db_state(page)
    print("every file of a multi-file result is added:", len(db['documents']) == 3)

    # A file already staged under the same name is never overwritten.
    await page.evaluate("""(async () => {
        const dir = await window.__TEST_ROOT.getDirectoryHandle('inbox', {create: true});
        const fh = await dir.getFileHandle('same.pdf', {create: true}); const w = await fh.createWritable(); await w.write('%PDF-1.4 staged'); await w.close();
    })()""")
    await page.evaluate(f"""window.__HELPERS['{L1}'].scanResponses = [{{status: 200, body: {{ok: true, partial: false, message: 'ok', output_paths: [],
        files: [{{filename: 'same.pdf', content_base64: btoa('%PDF-1.4 scanned')}}]}}}}]""")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await start_scan(page)
    db = await db_state(page)
    print("a same-named staged file and the scan both become documents:", len(db['documents']) == 5)

    # Partial result: files added, the helper's message is the final status line.
    await page.evaluate(f"""window.__HELPERS['{L1}'].scanResponses = [{{status: 200, body: {{ok: false, partial: true, message: 'Multi-feed at sheet 3', output_paths: [],
        files: [{{filename: 'p.pdf', content_base64: btoa('%PDF-1.4 partial')}}]}}}}]""")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await start_scan(page)
    db = await db_state(page)
    status = await page.inner_text('#status')
    print("partial result still adds its file:", len(db['documents']) == 6)
    print("partial result shows the helper's message:", 'Multi-feed at sheet 3' in status)

    # Hard failure: message in the dialog and on the status line, dialog stays open, nothing added.
    await page.evaluate(f"""window.__HELPERS['{L1}'].scanResponses = [{{status: 200, body: {{ok: false, partial: false, message: 'Scanner not found', output_paths: []}}}}]""")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await start_scan(page)
    print("hard failure keeps the dialog open with the message:", 'Scanner not found' in await page.inner_text('#scan-dialog-status'))
    print("hard failure adds nothing:", len((await db_state(page))['documents']) == 6)
    print("status line shows the failure:", 'Scanner not found' in await page.inner_text('#status'))

    # 404 from a version 1 helper: outdated scanix500.
    await page.evaluate(f"window.__HELPERS['{L1}'].scanResponses = [{{status: 404, body: {{error: 'not found'}}}}]")
    await start_scan(page)
    print("404 names an outdated scanix500:", 'scanix500' in await page.inner_text('#scan-dialog-status'))

    # 409: a scan is already running.
    await page.evaluate(f"window.__HELPERS['{L1}'].scanResponses = [{{status: 409, body: {{error: 'a scan is already in progress'}}}}]")
    await start_scan(page)
    print("409 says a scan is already running:", 'already in progress' in await page.inner_text('#scan-dialog-status'))

    # Network failure mid-scan: the helper is named, dialog stays open.
    await page.evaluate(f"window.__HELPERS['{L1}'].scanResponses = [{{network: true}}]")
    await start_scan(page)
    print("unreachable helper named in the dialog:", L1 in await page.inner_text('#scan-dialog-status'))

    # Not JSON / no files array: a bad answer, nothing added.
    await page.evaluate(f"window.__HELPERS['{L1}'].scanResponses = [{{status: 200, raw: 'not valid json'}}]")
    await start_scan(page)
    print("a non-JSON answer is reported:", "doesn't understand" in await page.inner_text('#scan-dialog-status'))
    await page.evaluate(f"window.__HELPERS['{L1}'].scanResponses = [{{status: 200, body: {{ok: true, partial: false, message: 'x', output_paths: []}}}}]")
    await start_scan(page)
    print("an ok answer without files is reported, nothing added:",
          "doesn't understand" in await page.inner_text('#scan-dialog-status') and len((await db_state(page))['documents']) == 6)

    # While a scan runs: button reads Scanning…, toolbar buttons disabled, Escape/close/backdrop blocked.
    await page.evaluate(f"window.__HELPERS['{L1}'].scanResponses = [{{delayMs: 800, status: 200, body: {{ok: false, partial: false, message: 'slow fail'}}}}]")
    await page.click('#scan-dialog-start-btn')
    await page.wait_for_timeout(150)
    print("Scan button reads Scanning… while scanning:", await page.inner_text('#scan-dialog-start-btn') == 'Scanning…'
          and not await page.is_enabled('#scan-dialog-start-btn'))
    print("toolbar Scan buttons disabled while scanning:", not await page.is_enabled('#scan-btn') and not await page.is_enabled('#scan-multi-btn'))
    await page.keyboard.press('Escape')
    await page.click('#modal-close-btn')
    await page.mouse.click(5, 5)
    print("Escape, close and backdrop don't close it mid-scan:", await page.locator('#scan-dialog-body').count() == 1)
    await page.wait_for_timeout(900)
    print("everything re-enabled afterwards:", await page.is_enabled('#scan-dialog-start-btn') and await page.is_enabled('#scan-btn')
          and await page.inner_text('#scan-dialog-start-btn') == 'Scan')
    await page.keyboard.press('Escape')
    print("Escape closes it again once idle:", await page.locator('#scan-dialog-body').count() == 0)

    print("no page errors:", errors == [])
    await browser.close()


# === Task 3: scanning through a version 2 helper ===
async def scenario_scan_v2(p):
    browser, page, errors = await open_app(p, tokens={L2: 'tok-2'})
    await page.evaluate(FAKE_HELPERS, {L2: {"version": 2, "token": "tok-2", "scanners": V2_SCANNERS}})

    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:feeder')
    await page.select_option('#scan-dialog-source', 'feeder')
    await page.check('#scan-dialog-duplex')
    await page.select_option('#scan-dialog-color', 'gray')
    await page.select_option('#scan-dialog-resolution', '300')
    await start_scan(page)
    c = await calls(page)
    scan = [x for x in c if x['url'] == f'{L2}/scan']
    body = json.loads(scan[0]['body']) if scan else None
    print("version 2 request is a JSON POST /scan with the token:",
          len(scan) == 1 and scan[0]['method'] == 'POST' and scan[0]['contentType'] == 'application/json' and scan[0]['auth'] == 'Bearer tok-2')
    print("body carries exactly the chosen settings:",
          body == {"scanner": "fake:feeder", "format": "pdf", "extras": {}, "source": "feeder", "colorMode": "gray", "resolution": 300, "duplex": True})
    db = await db_state(page)
    print("the version 2 result ({name, data}) became a document:", len(db['documents']) == 1)
    last = json.loads(next(r['value'] for r in db['settings'] if r['key'] == 'scan_last_settings'))
    print("the used settings are remembered:", last['scanner'] == f'{L2}|fake:feeder' and last['colorMode'] == 'gray' and last['duplex'] is True)

    # Extras: known ones sent as booleans, the unknown one never sent.
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L2}|fake:splitter')
    await page.check('.scan-dialog-extra[data-extra=splitOnBlank]')
    await start_scan(page)
    body = json.loads([x for x in await calls(page) if x['url'] == f'{L2}/scan'][-1]['body'])
    print("extras sent as known booleans only:", body['extras'] == {"splitOnBlank": True, "skipBlankPages": False})
    print("two-sided false for a scanner without duplex:", body['duplex'] is False)

    # Version 2 errors show the helper's message: 422, 503, 500.
    for status, message in [(422, 'This scanner has no 1200 dpi.'), (503, 'Scanner offline.'), (500, 'No paper in the feeder.')]:
        await page.evaluate(f"window.__HELPERS['{L2}'].scanResponses = [{{status: {status}, body: {{ok: false, partial: false, message: {json.dumps(message)}}}}}]")
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        await start_scan(page)
        print(f"{status} shows the helper's message in the dialog:", message in await page.inner_text('#scan-dialog-status'))
        await page.keyboard.press('Escape')

    # A version 2 partial result.
    await page.evaluate(f"""window.__HELPERS['{L2}'].scanResponses = [{{status: 200, body: {{ok: false, partial: true, message: 'Paper jam after page 2.',
        files: [{{name: 'jam.pdf', pages: 2, data: btoa('%PDF-1.4 jam')}}]}}}}]""")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await start_scan(page)
    db = await db_state(page)
    print("version 2 partial result added with its message:", len(db['documents']) == 3 and 'Paper jam' in await page.inner_text('#status'))

    print("no page errors:", errors == [])
    await browser.close()


# === Task 4: pairing inside the dialog (both protocol versions) ===
async def scenario_pairing(p):
    browser, page, errors = await open_app(p)
    await page.evaluate(FAKE_HELPERS, {L1: {"version": 1, "token": "tok-1"},
                                       L2: {"version": 2, "token": "tok-2", "helper": "dossiary-scan-helper-macos", "scanners": V2_SCANNERS}})

    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    rows = await page.eval_on_selector_all('.scan-pair-row', 'els => els.map(e => e.dataset.url)')
    print("both unpaired helpers get a pair row:", rows == [L1, L2])
    names = await page.inner_text('#scan-dialog-body')
    print("rows name the helpers:", 'scanix500: not paired yet' in names and 'dossiary-scan-helper-macos: not paired yet' in names)
    print("pairing instructions shown:", 'Pair a Browser' in await page.inner_text('#scan-pair-hint'))
    print("no scanner yet, Scan disabled:", await page.locator('#scan-dialog-scanner').count() == 0 and not await page.is_enabled('#scan-dialog-start-btn'))
    print("no scan request sent:", not any('/scan' in x['url'] and '/scanners' not in x['url'] for x in await calls(page)))

    row1 = f'.scan-pair-row[data-url="{L1}"]'
    await page.fill(f'{row1} .scan-pair-code', '12a')
    await page.click(f'{row1} .scan-pair-btn')
    await page.wait_for_timeout(150)
    print("malformed code refused without asking the helper:",
          'Enter the 6-digit code' in await page.inner_text(f'{row1} .scan-pair-status')
          and not any(x['url'].endswith('/pair') for x in await calls(page)))
    await page.fill(f'{row1} .scan-pair-code', '999999')
    await page.click(f'{row1} .scan-pair-btn')
    await page.wait_for_timeout(200)
    print("wrong code says it didn't work:", "didn't work" in await page.inner_text(f'{row1} .scan-pair-status'))

    await page.fill(f'{row1} .scan-pair-code', '123 456')
    await page.press(f'{row1} .scan-pair-code', 'Enter')
    await page.wait_for_timeout(400)
    pair = [x for x in await calls(page) if x['url'] == f'{L1}/pair'][-1]
    print("right code posted as JSON {code, client}:",
          json.loads(pair['body']) == {"code": "123456", "client": "Dossiary"} and pair['contentType'] == 'application/json' and pair['auth'] is None)
    tokens = await page.evaluate("JSON.parse(localStorage.getItem('dossiary_scan_tokens'))")
    print("token stored under the helper's address:", tokens.get(L1) == 'tok-1')
    print("paired helper's scanner appears, the other row stays:",
          await page.eval_on_selector_all('#scan-dialog-scanner option', 'els => els.map(e => e.value)') == [f'{L1}|scanix500']
          and await page.eval_on_selector_all('.scan-pair-row', 'els => els.map(e => e.dataset.url)') == [L2])
    print("Scan enabled once a scanner is there:", await page.is_enabled('#scan-dialog-start-btn'))

    # Pair the version 2 helper too; its scanners join the list.
    row2 = f'.scan-pair-row[data-url="{L2}"]'
    await page.fill(f'{row2} .scan-pair-code', '123456')
    await page.click(f'{row2} .scan-pair-btn')
    await page.wait_for_timeout(400)
    opts = await page.eval_on_selector_all('#scan-dialog-scanner option', 'els => els.map(e => e.value)')
    print("version 2 pairing adds its scanners, keeps the selection:",
          len(opts) == 4 and await page.eval_on_selector('#scan-dialog-scanner', 'e => e.value') == f'{L1}|scanix500'
          and await page.locator('.scan-pair-row').count() == 0)

    await start_scan(page)
    scan = [x for x in await calls(page) if '/scan?' in x['url']][-1]
    print("scan carries the new token:", scan['auth'] == 'Bearer tok-1')

    # The helper forgets its browsers: the scan answers 401, the token is dropped
    # and the pair row comes back; pairing again lets the next scan through.
    await page.evaluate(f"window.__HELPERS['{L1}'].forgotten = true")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    # /health already says not paired, so the row is there before any scan:
    print("a forgotten browser shows the pair row on opening:", await page.locator(row1).count() == 1)
    await page.keyboard.press('Escape')
    # Make /health still look paired so the stale token reaches /scan and gets a 401.
    await page.evaluate(f"""(() => {{ const f = window.fetch; window.fetch = async (url, opts = {{}}) => {{
        if(url === '{L1}/health') return new Response(JSON.stringify({{service: 'scanix500-bridge', paired: true}}), {{status: 200}});
        return f(url, opts); }}; }})()""")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await page.select_option('#scan-dialog-scanner', f'{L1}|scanix500')
    await start_scan(page)
    tokens = await page.evaluate("JSON.parse(localStorage.getItem('dossiary_scan_tokens'))")
    print("a 401 drops the stale token:", L1 not in tokens)
    print("...and says to pair again:", 'Pair it again' in await page.inner_text('#scan-dialog-status'))
    await page.keyboard.press('Escape')

    # A pre-0.3.0 scanix500 (no `paired` field) scans without any pairing or header.
    await browser.close()
    browser, page, errors = await open_app(p)
    await page.evaluate(FAKE_HELPERS, {L1: {"version": 1, "token": "x", "legacy": True}})
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    print("legacy bridge: no pair row:", await page.locator('.scan-pair-row').count() == 0)
    await start_scan(page)
    scan = [x for x in await calls(page) if '/scan?' in x['url']]
    print("legacy bridge scans without an Authorization header:", len(scan) == 1 and scan[0]['auth'] is None)
    print("no page errors:", errors == [])
    await browser.close()

    # German.
    browser, page, errors = await open_app(p, lang='de')
    await page.evaluate(FAKE_HELPERS, {L1: {"version": 1, "token": "tok-1"}})
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    print("German pair row:", 'noch nicht gekoppelt' in await page.inner_text('#scan-dialog-body')
          and await page.inner_text('.scan-pair-btn') == 'Koppeln')
    await browser.close()


SCENARIOS = [scenario_discovery, scenario_dialog, scenario_scan_v1, scenario_scan_v2, scenario_pairing]


async def main():
    async with async_playwright() as p:
        for scenario in SCENARIOS:
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
