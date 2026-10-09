# Scan Dialog (Scanner Helper Step 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Dossiary's fixed Scan/Scan Multi requests with a scan dialog that finds every scan helper on this computer (scanix500 and dossiary-scan-helper), lists their scanners with the settings each supports, pairs with helpers that need it, and sends the scan in the helper's own protocol version.

**Architecture:** All code lives in `dossiary.html` (single file, no build). A discovery layer probes `localhost:8765`, `localhost:8766` and the stored manual address (`scan_bridge_url`), then reads `GET /scanners` from version 2 helpers; a version 1 helper (scanix500) contributes one fixed "ScanSnap iX500" entry. The dialog renders from that result, remembers the last scanner and settings per library (`scan_last_settings`), and its Scan button builds a version 1 query-string request or a version 2 JSON request. Results go through the existing `writeScanFilesToInbox()` → `checkInbox()` → `addAllInboxFilesAndShowStatus()` pipeline.

**Tech Stack:** Vanilla JS in `dossiary.html`; tests are standalone Playwright-for-Python scripts under `tests/` using the shared `tests/stub_studio2.js` and a fake `window.fetch` defined in the test file.

**Spec:** `docs/superpowers/specs/2026-10-09-system-scanner-helper-design.md`, section 2 ("Dossiary"). Wire format: `~/Projects/Paperless/dossiary-scan-helper/PROTOCOL.md` (version 2 sections, and "Version 1" at the end).

## Global Constraints

- Keep `dossiary.html` a single file: no new dependency, no build step, nothing vendored.
- Ports: scanix500 `8765`, dossiary-scan-helper `8766`. Default helper URLs are exactly `http://localhost:8765` and `http://localhost:8766` (pairing tokens already stored under `http://localhost:8765` must keep working).
- `GET /health` probes use the existing `SCAN_BRIDGE_HEALTH_TIMEOUT_MS` (3000 ms) abort; `POST /scan` has **no** client timeout (a feeder batch can take minutes).
- Send `Authorization: Bearer <token>` only when a token exists (`scanAuthHeaders()`); a pre-0.3.0 scanix500 rejects the preflight for that header.
- Tokens stay in `localStorage` (`dossiary_scan_tokens`), keyed by helper URL — per browser, not per library.
- Version 2 is used only with a helper whose `/health` has `protocol: 2`; anything answering `{"service": "scanix500-bridge"}` is version 1. A version 1 health without `paired` is a pre-0.3.0 bridge and counts as paired.
- Version 2 `POST /scan` body: `{scanner, source, duplex, colorMode, resolution, format: "pdf", extras}`; response files are `{name, pages, data}`. Version 1: `POST /scan?skip_blank_filter=false&skip_ocr=false&split_on_blank=<true|false>`, files `{filename, content_base64}`, errors `{"error"}`.
- Known extras: `splitOnBlank`, `skipBlankPages`. Unknown extras are ignored (never shown, never sent as `true`).
- Remembered settings: one per-library `settings` row, key `scan_last_settings`, JSON. A remembered scanner that's gone falls back to the first in the list.
- While a scan runs: the dialog's Scan button reads "Scanning…", and Escape, the backdrop and the close button are blocked (the `makeSearchableRunning` pattern).
- No new toolbar buttons (the toolbar's height is part of `.table-wrap`'s calibration — see CLAUDE.md). Scan Multi is only hidden more often, never added.
- Every user-facing string goes into all six `STRINGS` blocks (`en`, `es`, `fr`, `de`, `zh-Hans`, `zh-Hant`); `zh-Hant` is derived from `zh-Hans` with OpenCC `s2t` (see "Translations" below). `python3 tests/test_i18n_coverage.py` must print `PASS`.
- Every printed test check reads `True` on pass; a full run prints no `False` (tests/CLAUDE.md).
- Every test file loads `tests/stub_studio2.js`, never its own stub.
- Commits end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01AnMx4wtUcaKMWsQm9eXUTo
  ```

### Translations

English and German text is given in each task. Translate Spanish, French and Simplified Chinese yourself, keeping the same placeholders (`{url}`, `{helper}`, `{dpi}`, `{message}`). Derive Traditional Chinese from your Simplified Chinese with OpenCC, as the rest of `STRINGS['zh-Hant']` was:

```bash
python3 -m venv /tmp/opencc-venv && /tmp/opencc-venv/bin/pip install -q opencc-python-reimplemented
/tmp/opencc-venv/bin/python -c "import opencc,sys; print(opencc.OpenCC('s2t').convert(sys.argv[1]))" '扫描助手'
```

New keys go at the start of each language block, on one line per task, the way `scanPairNeeded: …` already sits as the first line of every block (search for `scanPairNeeded:` to find all six). Keep straight quotes inside single-quoted values escaped, or use double-quoted values as those lines do.

### Running tests

Each test is a standalone script: `cd tests && python3 test_<name>.py`. Print lines end in `True` on pass. `python3 tests/test_i18n_coverage.py` prints `PASS`.

---

## File Structure

- `dossiary.html` — all app changes:
  - discovery: `normalizeHelperUrl()`, `scanHelperUrls()`, `probeScanHelper()`, `loadHelperScanners()`, `discoverScanHelpers()`, `scannerChoices()` (Task 1)
  - dialog: `openScanDialog()`, `refreshScanDialog()`, `renderScanDialogBody()`, `renderScanSettings()`, `readScanDialogSettings()`, `readLastScanSettings()`, `saveLastScanSettings()`, nothing-found state (Task 2)
  - scanning: `decodeScanFiles()`, `buildScanRequest()`, `performScanRequest()`, `startScanFromDialog()`; removal of the old auto-connect/pair/trigger flow (Task 3)
  - inline pairing: `submitInlinePairing()` and pair rows (Task 4)
  - Scan Multi availability: `updateScanMultiAvailability()`, discovery on library open (Task 5)
  - Field Settings "Scanner Integration" text and links (Task 6)
- `tests/stub_studio2.js` — a default `fetch` guard so no test ever reaches a real helper on the developer's machine (Task 1).
- `tests/test_scan_dialog.py` — new; grows one scenario group per task.
- `tests/test_scan_bridge.py`, `tests/test_scan_pairing.py` — deleted in Task 3 (their coverage moves into `test_scan_dialog.py` in Tasks 3–4).
- `tests/test_toolbar_buttons.py`, `tests/test_tools_menu.py` — adjusted in Task 5 (Scan Multi is hidden without a helper).
- `tests/manual_scan_reference_helper.py` — new, manual check against the real reference helper (not part of the suite; named `manual_*` so suite runners skip it) (Task 6).
- Docs (Task 6): `CLAUDE.md`, `tests/CLAUDE.md`, `README.md`, `README.de.md`, the six `USER_GUIDE*.md`, the spec's step 2 status.

---

### Task 1: Scanner discovery

**Files:**
- Modify: `tests/stub_studio2.js` (append the fetch guard at the end of the file)
- Modify: `dossiary.html` (insert after `function scanAuthHeaders(url){ … }`)
- Create: `tests/test_scan_dialog.py`

**Interfaces:**
- Produces:
  - `SCAN_HELPER_PORTS = [8765, 8766]`
  - `V1_SCANNER` — `{id: 'scanix500', name: 'ScanSnap iX500', sources: [], duplex: false, colorModes: [], resolutions: [], extras: ['splitOnBlank']}`
  - `SCAN_EXTRA_LABEL_KEYS = {splitOnBlank: 'scanExtraSplitOnBlank', skipBlankPages: 'scanExtraSkipBlankPages'}` (the i18n keys are added in Task 2; the object is only read by later tasks)
  - `normalizeHelperUrl(value) → string|null` — trims, strips trailing `/`, accepts only `http(s)://host[:port]`
  - `scanHelperUrls() → string[]` — `http://localhost:8765`, `http://localhost:8766`, then `scanBridgeUrl` if it's a different helper (`127.0.0.1` counts as `localhost`)
  - `probeScanHelper(url) → Promise<Helper|null>` where `Helper = {url, version: 1|2, paired: boolean, label: string, scanners: Scanner[]}`
  - `loadHelperScanners(helper) → Promise<Helper>` — fills `helper.scanners`; a 401 from `/scanners` sets `helper.paired = false`
  - `discoverScanHelpers() → Promise<Helper[]>`
  - `scannerChoices(helpers) → Choice[]` where `Choice = {key: '<helper url>|<scanner id>', helper, scanner, label}`; `label` is the scanner name, plus ` (<helper label>)` when two choices share a name
  - `window.__DEBUG_scanDiscovery()` → `{helpers: [{url, version, paired, label, scannerIds}], choices: [{key, label}]}`
- Test file produces (used by every later task): `FAKE_HELPERS` (JS function taking a config object), `V2_SCANNERS`, `open_app()`, `SCENARIOS` list.

- [ ] **Step 1: Add the fetch guard to the shared stub**

Append to the end of `tests/stub_studio2.js`:

```js
// No test may reach a real scan helper on the developer's machine (scanix500
// may well be running on :8765): a request to localhost/127.0.0.1 on another
// origin than the page's own fails like an unreachable helper. Tests that
// fake helpers replace window.fetch entirely, which removes this guard.
// manual_scan_reference_helper.py sets window.__ALLOW_REAL_HELPERS to talk to
// the real reference helper.
(() => {
  const realFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    let target = null;
    try{ target = new URL(url, location.href); }catch(e){ /* relative or odd -- let the real fetch decide */ }
    if(!window.__ALLOW_REAL_HELPERS && target && /^(localhost|127\.0\.0\.1)$/i.test(target.hostname) && target.origin !== location.origin){
      return Promise.reject(new TypeError('Failed to fetch'));
    }
    return realFetch(input, init);
  };
})();
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_scan_dialog.py`:

```python
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
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `cd tests && python3 test_scan_dialog.py`
Expected: a page error / exception because `window.__DEBUG_scanDiscovery` is not a function.

- [ ] **Step 4: Implement discovery**

In `dossiary.html`, directly after the closing `}` of `function scanAuthHeaders(url){ … }`, insert:

```js
  // ---- Scan helpers: discovery (scanner helper spec, section 2) ----
  // Every helper speaks the bridge protocol (dossiary-scan-helper's
  // PROTOCOL.md): scanix500 on 8765 (version 1, one fixed scanner), the
  // system scanner helper on 8766 (version 2, any number of scanners), plus
  // the manual address in Field Settings (scan_bridge_url) when it's another
  // helper. A version 1 helper contributes V1_SCANNER, whose one extra is
  // split on blank pages.
  const SCAN_HELPER_PORTS = [8765, 8766];
  const V1_SCANNER = Object.freeze({ id: 'scanix500', name: 'ScanSnap iX500', sources: [], duplex: false, colorModes: [], resolutions: [], extras: ['splitOnBlank'] });
  const SCAN_EXTRA_LABEL_KEYS = { splitOnBlank: 'scanExtraSplitOnBlank', skipBlankPages: 'scanExtraSkipBlankPages' };

  function normalizeHelperUrl(value){
    const s = String(value || '').trim().replace(/\/+$/, '');
    return /^https?:\/\/[^\s/?#]+$/i.test(s) ? s : null;
  }
  const sameHelperUrl = (a, b) => a.replace('//127.0.0.1', '//localhost') === b.replace('//127.0.0.1', '//localhost');
  function scanHelperUrls(){
    const urls = SCAN_HELPER_PORTS.map(port => `http://localhost:${port}`);
    const manual = normalizeHelperUrl(scanBridgeUrl);
    if(manual && !urls.some(u => sameHelperUrl(u, manual))) urls.push(manual);
    return urls;
  }

  // GET <url>/health with a short timeout. Returns null when nothing (or
  // something that isn't a scan helper) answers there.
  async function probeScanHelper(url){
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), SCAN_BRIDGE_HEALTH_TIMEOUT_MS);
    try{
      const response = await fetch(`${url}/health`, { method: 'GET', headers: scanAuthHeaders(url), signal: controller.signal });
      if(!response.ok) return null;
      const body = await response.json().catch(() => null);
      if(!body || typeof body !== 'object') return null;
      if(body.protocol === 2){
        return { url, version: 2, paired: body.paired === true, label: typeof body.helper === 'string' && body.helper ? body.helper : url, scanners: [] };
      }
      if(body.service === 'scanix500-bridge'){
        // No `paired` field: a bridge older than 0.3.0, which has no pairing.
        return { url, version: 1, paired: body.paired !== false, label: 'scanix500', scanners: [] };
      }
      return null;
    }catch(e){
      return null;
    }finally{
      clearTimeout(timeoutId);
    }
  }

  function validHelperScanner(s){
    return !!s && typeof s.id === 'string' && !!s.id && typeof s.name === 'string'
      && Array.isArray(s.sources) && Array.isArray(s.colorModes) && Array.isArray(s.resolutions);
  }
  async function loadHelperScanners(helper){
    helper.scanners = [];
    if(!helper.paired) return helper;
    if(helper.version === 1){ helper.scanners = [V1_SCANNER]; return helper; }
    try{
      const response = await fetch(`${helper.url}/scanners`, { method: 'GET', headers: scanAuthHeaders(helper.url) });
      if(response.status === 401){ helper.paired = false; return helper; }
      const body = response.ok ? await response.json().catch(() => null) : null;
      if(!body || !Array.isArray(body.scanners)) return helper;
      helper.scanners = body.scanners.filter(validHelperScanner).map(s => ({
        id: s.id,
        name: s.name,
        sources: s.sources.filter(x => x === 'flatbed' || x === 'feeder'),
        duplex: s.duplex === true,
        colorModes: s.colorModes.filter(x => x === 'color' || x === 'gray' || x === 'bw'),
        resolutions: s.resolutions.filter(Number.isInteger),
        extras: Array.isArray(s.extras) ? s.extras.filter(x => typeof x === 'string') : [],
      }));
    }catch(e){ /* unreachable mid-way: no scanners from it */ }
    return helper;
  }

  async function discoverScanHelpers(){
    const found = (await Promise.all(scanHelperUrls().map(probeScanHelper))).filter(Boolean);
    await Promise.all(found.map(loadHelperScanners));
    return found;
  }

  function scannerChoices(helpers){
    const all = [];
    for(const helper of helpers){
      for(const scanner of helper.scanners) all.push({ key: `${helper.url}|${scanner.id}`, helper, scanner, label: scanner.name });
    }
    const counts = {};
    for(const c of all) counts[c.scanner.name] = (counts[c.scanner.name] || 0) + 1;
    for(const c of all) if(counts[c.scanner.name] > 1) c.label = `${c.scanner.name} (${c.helper.label})`;
    return all;
  }

  window.__DEBUG_scanDiscovery = async () => {
    const helpers = await discoverScanHelpers();
    return {
      helpers: helpers.map(h => ({ url: h.url, version: h.version, paired: h.paired, label: h.label, scannerIds: h.scanners.map(s => s.id) })),
      choices: scannerChoices(helpers).map(c => ({ key: c.key, label: c.label })),
    };
  };
  window.__DEBUG_setScanBridgeUrl = (value) => saveScanBridgeUrl(value);
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd tests && python3 test_scan_dialog.py`
Expected: every line ends in `True`.

Also run `cd tests && python3 test_scan_bridge.py && python3 test_scan_pairing.py` — they replace `window.fetch` themselves, so the guard doesn't affect them; every line must still be `True`.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/stub_studio2.js tests/test_scan_dialog.py
git commit -m "Scan helpers: discover helpers and their scanners

Probes localhost:8765, localhost:8766 and the manual address, reads
/scanners from version 2 helpers and gives a version 1 helper its one
iX500 entry. The shared test stub now keeps tests away from any real
helper running on the machine.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AnMx4wtUcaKMWsQm9eXUTo"
```

---

### Task 2: The scan dialog and remembered settings

The dialog is reachable only through `window.__DEBUG_openScanDialog()` in this task; Task 3 wires the toolbar to it and adds scanning.

**Files:**
- Modify: `dossiary.html` (CSS block near `.toolbar-hidden`; strings in all six `STRINGS` blocks; code after Task 1's discovery block)
- Modify: `tests/test_scan_dialog.py` (add a scenario function and append it to `SCENARIOS`)

**Interfaces:**
- Consumes: `discoverScanHelpers()`, `scannerChoices()`, `normalizeHelperUrl()`, `SCAN_EXTRA_LABEL_KEYS`, `readSetting()`, `writeSetting()`, `persistDb()`, `saveScanBridgeUrl()`, `onModalKeydown`, `closeModal()`, `escapeHtml()`, `t()`.
- Produces:
  - `let scanDialogRunning = false` and `let scanDialogState = null` (`{helpers, choices, forceSplit}`)
  - `openScanDialog({splitOnBlank = false} = {}) → Promise<void>`
  - `refreshScanDialog() → Promise<void>` — rediscovers and redraws, keeping the current selection
  - `renderScanDialogBody(keep)`; `renderScanSettings(keep)`; `currentScanChoice() → Choice|null`
  - `readScanDialogSettings() → {scanner, source, duplex, colorMode, resolution, extras}|null`
  - `readLastScanSettings() → object|null`; `saveLastScanSettings(settings) → Promise<void>`
  - DOM ids: `#scan-dialog-body`, `#scan-dialog-status`, `#scan-dialog-start-btn`, `#scan-dialog-cancel-btn`, `#scan-dialog-scanner`, `#scan-dialog-settings`, `#scan-dialog-source`, `#scan-dialog-duplex`, `#scan-dialog-duplex-wrap`, `#scan-dialog-color`, `#scan-dialog-resolution`, `.scan-dialog-extra[data-extra]`, `#scan-dialog-address`, `#scan-dialog-retry-btn`, `#scan-dialog-helper-link`, `#scan-dialog-scanix500-link`
  - `window.__DEBUG_openScanDialog(opts)`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scan_dialog.py`, above `SCENARIOS = [...]`, and change the list to `SCENARIOS = [scenario_discovery, scenario_dialog]`:

```python
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
    print("German source label:", 'Einzug' in await page.inner_text('#scan-dialog-settings'))
    await browser.close()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd tests && python3 test_scan_dialog.py`
Expected: `scenario_discovery` all `True`; `scenario_dialog` fails with `window.__DEBUG_openScanDialog is not a function`.

- [ ] **Step 3: Add the strings**

English (first line of `STRINGS.en`):

```js
      scanDialogTitle: "Scan", scanDialogSearching: "Looking for scanners…", scanDialogStart: "Scan", scanDialogScannerLabel: "Scanner", scanDialogSourceLabel: "Paper source", scanSourceFlatbed: "Flatbed", scanSourceFeeder: "Document feeder", scanDialogDuplex: "Both sides", scanDialogColorLabel: "Color", scanColorColor: "Color", scanColorGray: "Grayscale", scanColorBw: "Black & white", scanDialogResolutionLabel: "Resolution", scanDialogDpi: "{dpi} dpi", scanExtraSplitOnBlank: "Split on blank pages (a blank sheet starts a new document)", scanExtraSkipBlankPages: "Skip blank pages", scanDialogNothingFound: "No scan helper answered. Scanning needs a small helper app on this computer: dossiary-scan-helper for most scanners, or scanix500 for a ScanSnap iX500. If yours runs at another address, enter it below.", scanDialogGetHelper: "Get dossiary-scan-helper", scanDialogGetScanix500: "Get scanix500", scanDialogAddressLabel: "Helper address (optional)", scanDialogRetry: "Look again", scanDialogAddressInvalid: "Enter an address like http://localhost:8766.",
```

German (first line of `STRINGS.de`):

```js
      scanDialogTitle: "Scannen", scanDialogSearching: "Suche nach Scannern…", scanDialogStart: "Scannen", scanDialogScannerLabel: "Scanner", scanDialogSourceLabel: "Papierquelle", scanSourceFlatbed: "Flachbett", scanSourceFeeder: "Dokumenteneinzug", scanDialogDuplex: "Beidseitig", scanDialogColorLabel: "Farbe", scanColorColor: "Farbe", scanColorGray: "Graustufen", scanColorBw: "Schwarzweiß", scanDialogResolutionLabel: "Auflösung", scanDialogDpi: "{dpi} dpi", scanExtraSplitOnBlank: "An leeren Seiten trennen (ein leeres Blatt beginnt ein neues Dokument)", scanExtraSkipBlankPages: "Leere Seiten weglassen", scanDialogNothingFound: "Kein Scan-Helfer hat geantwortet. Zum Scannen braucht es eine kleine Hilfs-App auf diesem Computer: dossiary-scan-helper für die meisten Scanner oder scanix500 für einen ScanSnap iX500. Läuft deiner unter einer anderen Adresse, trag sie unten ein.", scanDialogGetHelper: "dossiary-scan-helper herunterladen", scanDialogGetScanix500: "scanix500 herunterladen", scanDialogAddressLabel: "Adresse des Helfers (optional)", scanDialogRetry: "Erneut suchen", scanDialogAddressInvalid: "Gib eine Adresse wie http://localhost:8766 ein.",
```

Spanish, French, Simplified Chinese: translate the English line (keep `{dpi}`, product names and the example address unchanged). Traditional Chinese: OpenCC `s2t` of the Simplified line.

- [ ] **Step 4: Add the CSS**

Directly after the `.toolbar-hidden{ display:none !important; }` rule:

```css
  .scan-dialog-check{ display:flex; align-items:center; gap:8px; margin:8px 0; font-size:13px; }
  .scan-dialog-text{ font-size:12.5px; color:var(--text-dim); line-height:1.6; margin:0 0 12px; }
  .scan-dialog a{ color:var(--phosphor); font-weight:600; }
```

- [ ] **Step 5: Implement the dialog**

Insert directly after Task 1's `window.__DEBUG_setScanBridgeUrl = …;` line:

```js
  // ---- Scan dialog ----
  // Lists every scanner the helpers report, with only the settings the
  // chosen one supports. The last scanner and its settings are remembered
  // per library (scan_last_settings).
  let scanDialogRunning = false; // a scan request is in flight -- blocks closing the dialog
  let scanDialogState = null;    // {helpers, choices, forceSplit} for the open dialog
  const SCAN_HELPER_DOWNLOAD_URL = 'https://github.com/AarneAarebye/dossiary-scan-helper/releases';
  const SCANIX500_URL = 'https://github.com/AarneAarebye/iX500';
  const SCAN_SETTING_LABEL_KEYS = {
    source: { flatbed: 'scanSourceFlatbed', feeder: 'scanSourceFeeder' },
    colorMode: { color: 'scanColorColor', gray: 'scanColorGray', bw: 'scanColorBw' },
  };

  function readLastScanSettings(){
    try{
      const value = JSON.parse(readSetting('scan_last_settings') || 'null');
      return value && typeof value === 'object' ? value : null;
    }catch(e){ return null; }
  }
  async function saveLastScanSettings(settings){
    writeSetting('scan_last_settings', JSON.stringify(settings));
    await persistDb();
  }

  async function openScanDialog({ splitOnBlank = false } = {}){
    if(scanDialogRunning) return;
    scanDialogState = { helpers: [], choices: [], forceSplit: splitOnBlank };
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal scan-dialog" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <h2>${t('scanDialogTitle')}</h2>
          <div id="scan-dialog-body"><p class="scan-dialog-text">${t('scanDialogSearching')}</p></div>
          <div id="scan-dialog-status" class="doc-sub" style="margin-top:8px; min-height:1.2em;"></div>
          <div class="modal-actions" style="margin-top:16px;">
            <button id="scan-dialog-cancel-btn">${t('commonCancel')}</button>
            <button id="scan-dialog-start-btn" disabled>${t('scanDialogStart')}</button>
          </div>
        </div>
      </div>`;
    const tryClose = () => { if(!scanDialogRunning) closeModal(); };
    el('modal-close-btn').addEventListener('click', tryClose);
    el('scan-dialog-cancel-btn').addEventListener('click', tryClose);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') tryClose(); });
    document.addEventListener('keydown', onModalKeydown);
    await refreshScanDialog();
  }

  // Discovers the helpers again and redraws the dialog, keeping the scanner
  // and settings currently chosen (or, on first open, the remembered ones).
  async function refreshScanDialog(){
    const keep = el('scan-dialog-scanner') ? readScanDialogSettings() : readLastScanSettings();
    const helpers = await discoverScanHelpers();
    if(!el('scan-dialog-body')) return; // closed while looking
    scanDialogState.helpers = helpers;
    scanDialogState.choices = scannerChoices(helpers);
    renderScanDialogBody(keep);
  }

  function renderScanDialogBody(keep){
    const body = el('scan-dialog-body');
    const startBtn = el('scan-dialog-start-btn');
    const { choices } = scanDialogState;
    if(!choices.length){
      body.innerHTML = scanNothingFoundHtml();
      wireScanNothingFound();
      startBtn.disabled = true;
      return;
    }
    const selectedKey = keep && choices.some(c => c.key === keep.scanner) ? keep.scanner : choices[0].key;
    body.innerHTML = `
      <div class="field">
        <label for="scan-dialog-scanner">${t('scanDialogScannerLabel')}</label>
        <select id="scan-dialog-scanner">${choices.map(c => `<option value="${escapeHtml(c.key)}" ${c.key === selectedKey ? 'selected' : ''}>${escapeHtml(c.label)}</option>`).join('')}</select>
      </div>
      <div id="scan-dialog-settings"></div>`;
    renderScanSettings(keep && keep.scanner === selectedKey ? keep : null);
    el('scan-dialog-scanner').addEventListener('change', () => renderScanSettings(null));
    startBtn.disabled = false;
  }

  function currentScanChoice(){
    const select = el('scan-dialog-scanner');
    return select && scanDialogState ? scanDialogState.choices.find(c => c.key === select.value) || null : null;
  }

  // Only what the chosen scanner supports: a choice with one value isn't
  // shown (its value is sent), two-sided only for a duplex feeder, and only
  // the extras Dossiary knows.
  function renderScanSettings(keep){
    const choice = currentScanChoice();
    const box = el('scan-dialog-settings');
    if(!choice || !box) return;
    const s = choice.scanner;
    const pick = (values, wanted) => values.includes(wanted) ? wanted : values[0];
    const source = pick(s.sources, keep && keep.source);
    const selectHtml = (id, labelKey, values, current, labelOf) => values.length > 1 ? `
      <div class="field">
        <label for="${id}">${t(labelKey)}</label>
        <select id="${id}">${values.map(v => `<option value="${escapeHtml(String(v))}" ${v === current ? 'selected' : ''}>${escapeHtml(labelOf(v))}</option>`).join('')}</select>
      </div>` : '';
    const extras = s.extras.filter(x => SCAN_EXTRA_LABEL_KEYS[x]);
    const extraOn = (x) => (x === 'splitOnBlank' && scanDialogState.forceSplit) || !!(keep && keep.extras && keep.extras[x]);
    box.innerHTML = `
      ${selectHtml('scan-dialog-source', 'scanDialogSourceLabel', s.sources, source, v => t(SCAN_SETTING_LABEL_KEYS.source[v]))}
      <label class="scan-dialog-check" id="scan-dialog-duplex-wrap"><input type="checkbox" id="scan-dialog-duplex" ${keep && keep.duplex ? 'checked' : ''} /> ${t('scanDialogDuplex')}</label>
      ${selectHtml('scan-dialog-color', 'scanDialogColorLabel', s.colorModes, pick(s.colorModes, keep && keep.colorMode), v => t(SCAN_SETTING_LABEL_KEYS.colorMode[v]))}
      ${selectHtml('scan-dialog-resolution', 'scanDialogResolutionLabel', s.resolutions, pick(s.resolutions, keep && keep.resolution), v => t('scanDialogDpi', {dpi: v}))}
      ${extras.map(x => `<label class="scan-dialog-check"><input type="checkbox" class="scan-dialog-extra" data-extra="${x}" ${extraOn(x) ? 'checked' : ''} /> ${t(SCAN_EXTRA_LABEL_KEYS[x])}</label>`).join('')}`;
    const syncDuplex = () => {
      const current = el('scan-dialog-source') ? el('scan-dialog-source').value : source;
      const allowed = s.duplex && current === 'feeder';
      el('scan-dialog-duplex-wrap').style.display = allowed ? '' : 'none';
      if(!allowed) el('scan-dialog-duplex').checked = false;
    };
    if(el('scan-dialog-source')) el('scan-dialog-source').addEventListener('change', syncDuplex);
    syncDuplex();
  }

  function readScanDialogSettings(){
    const choice = currentScanChoice();
    if(!choice) return null;
    const s = choice.scanner;
    const value = (id, fallback) => el(id) ? el(id).value : fallback;
    const extras = {};
    modalRoot.querySelectorAll('.scan-dialog-extra').forEach(cb => { extras[cb.dataset.extra] = cb.checked; });
    return {
      scanner: choice.key,
      source: value('scan-dialog-source', s.sources[0]),
      duplex: !!(el('scan-dialog-duplex') && el('scan-dialog-duplex').checked),
      colorMode: value('scan-dialog-color', s.colorModes[0]),
      resolution: el('scan-dialog-resolution') ? Number(el('scan-dialog-resolution').value) : s.resolutions[0],
      extras,
    };
  }

  function scanNothingFoundHtml(){
    return `
      <p class="scan-dialog-text">${t('scanDialogNothingFound')}</p>
      <p class="scan-dialog-text">
        <a href="${SCAN_HELPER_DOWNLOAD_URL}" target="_blank" rel="noopener noreferrer" id="scan-dialog-helper-link">${t('scanDialogGetHelper')}</a>
        · <a href="${SCANIX500_URL}" target="_blank" rel="noopener noreferrer" id="scan-dialog-scanix500-link">${t('scanDialogGetScanix500')}</a>
      </p>
      <div class="field">
        <label for="scan-dialog-address">${t('scanDialogAddressLabel')}</label>
        <input type="text" id="scan-dialog-address" value="${escapeHtml(scanBridgeUrl || '')}" placeholder="http://localhost:8766" />
      </div>
      <button id="scan-dialog-retry-btn">${t('scanDialogRetry')}</button>`;
  }
  function wireScanNothingFound(){
    el('scan-dialog-retry-btn').addEventListener('click', async () => {
      const raw = el('scan-dialog-address').value.trim();
      const address = normalizeHelperUrl(raw);
      if(raw && !address){ el('scan-dialog-status').textContent = t('scanDialogAddressInvalid'); return; }
      el('scan-dialog-status').textContent = '';
      if((address || null) !== (normalizeHelperUrl(scanBridgeUrl) || null)) await saveScanBridgeUrl(address || '');
      el('scan-dialog-body').innerHTML = `<p class="scan-dialog-text">${t('scanDialogSearching')}</p>`;
      await refreshScanDialog();
    });
  }

  window.__DEBUG_openScanDialog = (opts) => openScanDialog(opts || {});
  window.__DEBUG_readScanDialogSettings = () => readScanDialogSettings();
  window.__DEBUG_saveLastScanSettings = (s) => saveLastScanSettings(s);
```

Also extend `onModalKeydown` (search `function onModalKeydown`) so Escape can't close the dialog mid-scan — append `&& !scanDialogRunning` to its condition:

```js
  function onModalKeydown(e){ if(e.key === 'Escape' && !findDuplicatesBackfillRunning && !makeSearchableRunning && !exportRunning && !backupRunning && !pageToolsRunning && !scanDialogRunning) closeModal(); }
```

`scanDialogRunning` is declared later in the file than `onModalKeydown`; that's fine (`let` at the same IIFE scope, read only when a key is pressed).

- [ ] **Step 6: Run the tests**

Run: `cd tests && python3 test_scan_dialog.py && python3 test_i18n_coverage.py`
Expected: every line `True`, then `PASS`.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_scan_dialog.py
git commit -m "Scan dialog: scanner list, per-scanner settings, remembered choice

Not wired to the toolbar yet. Shows only what the chosen scanner
supports, remembers the last scanner and settings per library, and
explains what to install when no helper answers.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AnMx4wtUcaKMWsQm9eXUTo"
```

---

### Task 3: Scanning from the dialog (replaces the old flow)

The toolbar's Scan and Scan Multi buttons open the dialog; the dialog's Scan button sends the request in the helper's protocol version. The old auto-connect port dialog, the old pairing dialog and `triggerScan()` go, with their two test files. Pairing inside the dialog comes in Task 4: until then a 401 shows a message.

**Files:**
- Modify: `dossiary.html`
- Delete: `tests/test_scan_bridge.py`, `tests/test_scan_pairing.py`
- Modify: `tests/test_scan_dialog.py`

**Interfaces:**
- Consumes: everything from Tasks 1–2; `writeScanFilesToInbox()`, `checkInbox()`, `addAllInboxFilesAndShowStatus()`, `setScanToken()`, `scanAuthHeaders()`, `setStatusT()`.
- Produces:
  - `decodeScanFiles(files) → [{name, bytes: Uint8Array}]` — accepts version 2 `{name, data}` and version 1 `{filename, content_base64}` entries; throws if `files` isn't an array or an entry is malformed
  - `writeScanFilesToInbox(decoded)` — now takes the decoded list
  - `buildScanRequest(choice, settings) → {url, init}`
  - `performScanRequest(choice, request) → Promise<{done: true} | {needsPairing: true} | {key, params}>`
  - `startScanFromDialog() → Promise<void>`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_scan_dialog.py` above `SCENARIOS`, and append `scenario_scan_v1, scenario_scan_v2` to `SCENARIOS`:

```python
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
    print("the scan became an Inbox document:", len(db['documents']) == 1 and db['documents'][0]['needs_review'] == 1)
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

    # 401: token dropped, the person is told to pair again.
    await page.evaluate(f"window.__HELPERS['{L1}'].forgotten = true")
    await page.evaluate(f"window.__HELPERS['{L1}'].legacy = false")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    # The forgotten helper now reports paired: false, so there's no scanner to pick yet --
    # force a stale scan through a paired-looking state by re-enabling validity for /health only:
    print("a helper that forgot this browser offers no scanner:", await page.locator('#scan-dialog-scanner').count() == 0)
    await page.keyboard.press('Escape')

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
```

The last block of `scenario_scan_v1` (a helper that forgot this browser) only checks that no scanner is offered; Task 4 adds the pairing rows and the full 401 path.

- [ ] **Step 2: Run them to make sure they fail**

Run: `cd tests && python3 test_scan_dialog.py`
Expected: `scenario_scan_v1` fails at "toolbar Scan opens the scan dialog" (the old flow still runs).

- [ ] **Step 3: Add the strings**

English (append to the Task 2 line at the start of `STRINGS.en`):

```js
      scanHelperUnreachable: "Couldn't reach the scan helper at {url}. Is it running?", scanHelperBadAnswer: "The scan helper at {url} sent an answer Dossiary doesn't understand. Updating the helper should fix this.", scanNeedsPairing: "The scan helper doesn't know this browser any more. Pair it again.",
```

German:

```js
      scanHelperUnreachable: "Der Scan-Helfer unter {url} ist nicht erreichbar. Läuft er?", scanHelperBadAnswer: "Der Scan-Helfer unter {url} hat eine Antwort geschickt, die Dossiary nicht versteht. Ein Update des Helfers sollte das beheben.", scanNeedsPairing: "Der Scan-Helfer kennt diesen Browser nicht mehr. Bitte erneut koppeln.",
```

Other languages as described under Translations.

- [ ] **Step 4: Replace the old flow**

In `dossiary.html`:

1. Delete these functions entirely: `probeScanBridgeHealth`, `connectScanBridgeAndTrigger`, `openScanConnectDialog`, `submitScanConnectDialog`, `openScanPairDialog`, `submitScanPairDialog`, `triggerScan`, `startScan`, and the `let scanRequestInFlight = false;` line. Delete the `SCAN_BRIDGE_DEFAULT_PORT` constant (keep `SCAN_BRIDGE_HEALTH_TIMEOUT_MS`).
2. Replace `writeScanFilesToInbox` with:

```js
  // Writes decoded scan files (see decodeScanFiles()) into the library's own
  // inbox/ folder, so the existing checkInbox()/addAllInboxFilesAndShowStatus()
  // pipeline picks them up like any other staged file.
  async function writeScanFilesToInbox(files){
    const dirHandle = await rootDirHandle.getDirectoryHandle('inbox', { create: true });
    for(const file of files){
      const name = safeFilename(file.name, 'scan.pdf');
      const uniqueName = await uniqueInboxFilename(dirHandle, name);
      const fileHandle = await dirHandle.getFileHandle(uniqueName, { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(file.bytes);
      await writable.close();
    }
  }

  // A scan result's files in either wire format: version 2 {name, pages,
  // data} or version 1 {filename, content_base64}. Throws on anything else.
  function decodeScanFiles(files){
    if(!Array.isArray(files)) throw new Error('no files array in scan result');
    return files.map(entry => {
      const name = entry && (typeof entry.name === 'string' ? entry.name : entry.filename);
      const data = entry && (typeof entry.data === 'string' ? entry.data : entry.content_base64);
      if(typeof name !== 'string' || typeof data !== 'string') throw new Error('malformed files entry from scan helper');
      return { name, bytes: Uint8Array.from(atob(data), c => c.charCodeAt(0)) };
    });
  }

  // Version 1 (scanix500): POST /scan?… with no body; skip_blank_filter and
  // skip_ocr are always false, as before. Version 2: a JSON body with the
  // chosen settings; two-sided only for a duplex scanner's feeder, extras
  // only the ones the scanner offers and Dossiary knows.
  function buildScanRequest(choice, settings){
    const url = choice.helper.url;
    const auth = scanAuthHeaders(url);
    const extrasChosen = settings.extras || {};
    if(choice.helper.version === 1){
      const params = new URLSearchParams({ skip_blank_filter: 'false', skip_ocr: 'false', split_on_blank: extrasChosen.splitOnBlank ? 'true' : 'false' });
      return { url: `${url}/scan?${params}`, init: { method: 'POST', headers: auth } };
    }
    const s = choice.scanner;
    const extras = {};
    for(const x of s.extras) if(SCAN_EXTRA_LABEL_KEYS[x]) extras[x] = !!extrasChosen[x];
    const body = { scanner: s.id, format: 'pdf', extras };
    if(settings.source) body.source = settings.source;
    if(settings.colorMode) body.colorMode = settings.colorMode;
    if(Number.isInteger(settings.resolution)) body.resolution = settings.resolution;
    body.duplex = !!(settings.duplex && s.duplex && settings.source === 'feeder');
    return { url: `${url}/scan`, init: { method: 'POST', headers: { 'Content-Type': 'application/json', ...auth }, body: JSON.stringify(body) } };
  }

  // Sends the scan (no timeout: a feeder batch can take minutes) and handles
  // the answer. {done: true}: files reached the Inbox and the dialog is
  // closed. {needsPairing: true}: a 401, token dropped. {key, params}: a
  // message for the dialog and the status line; the dialog stays open.
  async function performScanRequest(choice, request){
    const helperUrl = choice.helper.url;
    let response;
    try{ response = await fetch(request.url, request.init); }
    catch(e){ return { key: 'scanHelperUnreachable', params: { url: helperUrl } }; }
    if(response.status === 401){ setScanToken(helperUrl, null); return { needsPairing: true }; }
    const body = await response.json().catch(() => null);
    const helperMessage = body && (body.message || body.error);
    if(response.status === 404 && choice.helper.version === 1) return { key: 'scanBridgeOutdated', params: null };
    if(response.status === 409) return { key: 'scanAlreadyInProgress', params: null };
    if(!response.ok) return { key: 'scanFailedMessage', params: { message: helperMessage || String(response.status) } };
    if(!body) return { key: 'scanHelperBadAnswer', params: { url: helperUrl } };
    if(!body.ok && !body.partial) return { key: 'scanFailedMessage', params: { message: helperMessage || String(response.status) } };
    let files;
    try{ files = decodeScanFiles(body.files); }
    catch(e){ return { key: 'scanHelperBadAnswer', params: { url: helperUrl } }; }
    closeModal();
    try{
      await writeScanFilesToInbox(files);
    }catch(e){
      setStatusT('scanFailedMessage', { message: e.message || String(e) }, 'err');
      return { done: true };
    }
    await checkInbox();
    await addAllInboxFilesAndShowStatus();
    // A partial scan (a jam, a multi-feed) still delivered usable pages; the
    // helper's account of what went wrong matters more than the Inbox report.
    if(!body.ok) setStatusT('scanPartialMessage', { message: helperMessage || '' }, 'err');
    return { done: true };
  }

  async function startScanFromDialog(){
    const choice = currentScanChoice();
    const settings = readScanDialogSettings();
    if(!choice || !settings || scanDialogRunning) return;
    scanDialogRunning = true;
    const startBtn = el('scan-dialog-start-btn');
    startBtn.disabled = true;
    startBtn.textContent = t('scanScanning');
    el('scan-dialog-status').textContent = '';
    el('scan-btn').disabled = true;
    el('scan-multi-btn').disabled = true;
    setStatusT('scanScanning', null, 'busy');
    let outcome;
    try{
      await saveLastScanSettings(settings);
      outcome = await performScanRequest(choice, buildScanRequest(choice, settings));
    }finally{
      scanDialogRunning = false;
      el('scan-btn').disabled = false;
      el('scan-multi-btn').disabled = false;
      if(el('scan-dialog-start-btn')){
        el('scan-dialog-start-btn').disabled = false;
        el('scan-dialog-start-btn').textContent = t('scanDialogStart');
      }
    }
    if(outcome.done) return;
    if(outcome.needsPairing){
      await refreshScanDialog();
      if(el('scan-dialog-status')) el('scan-dialog-status').textContent = t('scanNeedsPairing');
      setStatusT('scanNeedsPairing', null, 'err');
      return;
    }
    if(el('scan-dialog-status')) el('scan-dialog-status').textContent = t(outcome.key, outcome.params);
    setStatusT(outcome.key, outcome.params, 'err');
  }
```

3. In `openScanDialog()`, after `document.addEventListener('keydown', onModalKeydown);`, add:

```js
    el('scan-dialog-start-btn').addEventListener('click', startScanFromDialog);
```

4. Replace the two toolbar listeners (`el('scan-btn').addEventListener('click', () => startScan(false));` and the Scan Multi one) with:

```js
  el('scan-btn').addEventListener('click', () => openScanDialog());
  el('scan-multi-btn').addEventListener('click', () => openScanDialog({ splitOnBlank: true }));
```

5. Fix every remaining reference: `grep -n "probeScanBridgeHealth\|connectScanBridgeAndTrigger\|openScanConnectDialog\|openScanPairDialog\|triggerScan\|startScan(\|SCAN_BRIDGE_DEFAULT_PORT\|scanRequestInFlight" dossiary.html` must print only comments you then update (e.g. the comment above `loadScanBridgeUrl()` that mentions `connectScanBridgeAndTrigger()` — reword it to "or the scan dialog's Look again"). No code reference may remain.

6. Remove i18n keys that no code uses any more. For each of `scanConnectTitle scanConnectInstructions scanConnectPortLabel scanConnectDownloadPrompt scanConnectDownloadLink scanConnectSubmit scanConnectInvalidPort scanConnectProbing scanConnectFailed scanBadRequest scanBridgeNotConfigured scanProfileNotConfigured scanBridgeUnreachable scanPairNeeded scanPairTitle scanPairInstructions scanPairSubmit`, run `grep -c "t('KEY'\|t(\"KEY\"\|data-i18n[a-z-]*=\"KEY\"" dossiary.html`; if it's `0`, delete `KEY: …,` from all six language blocks. Keep `scanPairCodeLabel`, `scanPairInvalidCode`, `scanPairWrongCode` (Task 4 uses them).

7. `git rm tests/test_scan_bridge.py tests/test_scan_pairing.py`.

- [ ] **Step 5: Run the tests**

Run: `cd tests && python3 test_scan_dialog.py && python3 test_i18n_coverage.py && python3 test_toolbar_buttons.py && python3 test_tools_menu.py`
Expected: every line `True`; `PASS`.

- [ ] **Step 6: Commit**

```bash
git add -A dossiary.html tests/test_scan_dialog.py tests/test_scan_bridge.py tests/test_scan_pairing.py
git commit -m "Scan: scan from the dialog in the helper's protocol version

Scan and Scan Multi open the scan dialog. Its Scan button sends a
version 1 or version 2 request, writes the files to the Inbox, and keeps
the dialog open with the helper's message on failure. Replaces the
port dialog, the separate pairing dialog and triggerScan(), and moves
their tests into test_scan_dialog.py.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AnMx4wtUcaKMWsQm9eXUTo"
```

---

### Task 4: Pairing inside the dialog

A helper whose `/health` says `paired: false` (version 1 or 2) shows as "<helper>: not paired yet" with a code field and a Pair button, above the scanner list. "Nothing found" now means no helper answered at all.

**Files:**
- Modify: `dossiary.html`
- Modify: `tests/test_scan_dialog.py`

**Interfaces:**
- Consumes: `scanDialogState.helpers` (each with `paired`), `refreshScanDialog()`, `setScanToken()`.
- Produces: `submitInlinePairing(row) → Promise<void>`; DOM: `.scan-pair-row[data-url]`, `.scan-pair-code`, `.scan-pair-btn`, `.scan-pair-status`, `#scan-pair-hint`.

- [ ] **Step 1: Write the failing test**

Add above `SCENARIOS` and append `scenario_pairing` to the list:

```python
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
```

Also delete the last block of `scenario_scan_v1` that starts with `# 401: token dropped, the person is told to pair again.` up to (not including) `print("no page errors:", errors == [])` — this scenario covers it now.

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd tests && python3 test_scan_dialog.py`
Expected: `scenario_pairing` fails at "both unpaired helpers get a pair row" (the dialog shows "nothing found").

- [ ] **Step 3: Add the strings**

English (append to the start-of-block line):

```js
      scanPairHelperNotPaired: "{helper}: not paired yet", scanPairButton: "Pair", scanPairHint: "Pair this browser once: choose “Pair a Browser…” in the helper's menu and type the 6-digit code it shows.", scanPairPairing: "Pairing…",
```

German:

```js
      scanPairHelperNotPaired: "{helper}: noch nicht gekoppelt", scanPairButton: "Koppeln", scanPairHint: "Diesen Browser einmal koppeln: Im Menü des Helfers „Pair a Browser…“ wählen und den 6-stelligen Code eingeben, den er anzeigt.", scanPairPairing: "Kopple…",
```

Other languages as described under Translations ("Pair a Browser…" stays in English: it's the helper's own menu item).

- [ ] **Step 4: Implement**

Replace `renderScanDialogBody` with:

```js
  function renderScanDialogBody(keep){
    const body = el('scan-dialog-body');
    const startBtn = el('scan-dialog-start-btn');
    const { helpers, choices } = scanDialogState;
    if(!helpers.length){
      body.innerHTML = scanNothingFoundHtml();
      wireScanNothingFound();
      startBtn.disabled = true;
      return;
    }
    // A helper that doesn't know this browser yet: a code field per helper.
    const unpaired = helpers.filter(h => !h.paired);
    const pairHtml = unpaired.length ? `
      <p class="scan-dialog-text" id="scan-pair-hint">${t('scanPairHint')}</p>
      ${unpaired.map(h => `
        <div class="scan-pair-row" data-url="${escapeHtml(h.url)}">
          <div class="scan-dialog-text" style="margin:0 0 4px;">${escapeHtml(t('scanPairHelperNotPaired', { helper: h.label }))}</div>
          <div style="display:flex; gap:8px; align-items:center;">
            <input type="text" class="scan-pair-code" inputmode="numeric" autocomplete="one-time-code" maxlength="7" placeholder="123 456" aria-label="${t('scanPairCodeLabel')}" style="width:9em;" />
            <button class="scan-pair-btn">${t('scanPairButton')}</button>
          </div>
          <div class="scan-pair-status doc-sub" style="min-height:1.2em; margin:4px 0 12px;"></div>
        </div>`).join('')}` : '';
    if(!choices.length){
      body.innerHTML = pairHtml;
      wireScanPairRows();
      startBtn.disabled = true;
      return;
    }
    const selectedKey = keep && choices.some(c => c.key === keep.scanner) ? keep.scanner : choices[0].key;
    body.innerHTML = `
      ${pairHtml}
      <div class="field">
        <label for="scan-dialog-scanner">${t('scanDialogScannerLabel')}</label>
        <select id="scan-dialog-scanner">${choices.map(c => `<option value="${escapeHtml(c.key)}" ${c.key === selectedKey ? 'selected' : ''}>${escapeHtml(c.label)}</option>`).join('')}</select>
      </div>
      <div id="scan-dialog-settings"></div>`;
    wireScanPairRows();
    renderScanSettings(keep && keep.scanner === selectedKey ? keep : null);
    el('scan-dialog-scanner').addEventListener('change', () => renderScanSettings(null));
    startBtn.disabled = false;
  }

  function wireScanPairRows(){
    modalRoot.querySelectorAll('.scan-pair-row').forEach(row => {
      row.querySelector('.scan-pair-btn').addEventListener('click', () => submitInlinePairing(row));
      row.querySelector('.scan-pair-code').addEventListener('keydown', (e) => { if(e.key === 'Enter') submitInlinePairing(row); });
    });
  }

  // Swaps the code the helper shows for a token (POST /pair, JSON, so a
  // preflight), stores it under the helper's address, and redraws the
  // dialog with that helper's scanners.
  async function submitInlinePairing(row){
    const url = row.dataset.url;
    const status = row.querySelector('.scan-pair-status');
    const btn = row.querySelector('.scan-pair-btn');
    if(btn.disabled) return;
    const code = row.querySelector('.scan-pair-code').value.replace(/\s+/g, '');
    if(!/^\d{6}$/.test(code)){ status.textContent = t('scanPairInvalidCode'); return; }
    btn.disabled = true;
    status.textContent = t('scanPairPairing');
    let response = null;
    try{
      response = await fetch(`${url}/pair`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, client: 'Dossiary' }),
      });
    }catch(e){ response = null; }
    if(!row.isConnected) return; // dialog closed or redrawn meanwhile
    btn.disabled = false;
    if(!response){ status.textContent = t('scanHelperUnreachable', { url }); return; }
    const body = await response.json().catch(() => null);
    if(!response.ok || !body || typeof body.token !== 'string' || !body.token){
      status.textContent = response.status === 403 || response.status === 400 ? t('scanPairWrongCode') : t('scanHelperUnreachable', { url });
      return;
    }
    setScanToken(url, body.token);
    await refreshScanDialog();
  }
```

- [ ] **Step 5: Run the tests**

Run: `cd tests && python3 test_scan_dialog.py && python3 test_i18n_coverage.py`
Expected: every line `True`; `PASS`.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_scan_dialog.py
git commit -m "Scan dialog: pair with each helper inline

A helper that doesn't know this browser shows a code field in the
dialog; pairing stores the token and brings in its scanners. Works the
same for scanix500 (version 1) and version 2 helpers.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AnMx4wtUcaKMWsQm9eXUTo"
```

---

### Task 5: Scan Multi as a shortcut, discovery when a library opens

Scan Multi is shown only while some helper can split on blank pages: a found scanner with `splitOnBlank`, or an unpaired version 1 helper (its one scanner, the iX500, can). Dossiary checks once when a library opens (read-only requests to localhost) and again whenever the dialog opens.

**Files:**
- Modify: `dossiary.html` (CSS, `#scan-multi-btn` markup, `updateScanMultiAvailability()`, `refreshScanDialog()`, `afterDbReady()`, `resetAll()`)
- Modify: `tests/test_scan_dialog.py`, `tests/test_toolbar_buttons.py`, `tests/test_tools_menu.py`

**Interfaces:**
- Consumes: `discoverScanHelpers()`, `refreshScanDialog()`.
- Produces: `updateScanMultiAvailability(helpers)`; CSS class `.scan-unavailable`.

- [ ] **Step 1: Write the failing test**

Add above `SCENARIOS` and append `scenario_scan_multi`:

```python
# === Task 5: Scan Multi only while a scanner can split on blank pages ===
async def scenario_scan_multi(p):
    async def visible(page, sel):
        return await page.is_visible(sel)

    browser, page, errors = await open_app(p)
    await page.wait_for_timeout(200)
    print("no helper: Scan Multi hidden, Scan shown:", not await visible(page, '#scan-multi-btn') and await visible(page, '#scan-btn'))
    await browser.close()

    browser, page, errors = await open_app(p, helpers={L2: {"version": 2, "token": "tok-2", "scanners": V2_SCANNERS[:2]}}, tokens={L2: 'tok-2'})
    await page.wait_for_timeout(300)
    print("version 2 scanners without splitOnBlank: Scan Multi hidden:", not await visible(page, '#scan-multi-btn'))
    await page.evaluate(f"window.__HELPERS['{L2}'].scanners = {json.dumps(V2_SCANNERS)}")
    await page.click('#scan-btn')
    await page.wait_for_timeout(300)
    await page.keyboard.press('Escape')
    print("opening the dialog re-checks: a splitter appears, Scan Multi shown:", await visible(page, '#scan-multi-btn'))
    await browser.close()

    browser, page, errors = await open_app(p, helpers={L1: {"version": 1, "token": "tok-1"}})
    await page.wait_for_timeout(300)
    print("unpaired scanix500 on library open: Scan Multi shown:", await visible(page, '#scan-multi-btn'))
    await page.click('#scan-multi-btn')
    await page.wait_for_timeout(300)
    await page.fill('.scan-pair-code', '123456')
    await page.click('.scan-pair-btn')
    await page.wait_for_timeout(400)
    print("Scan Multi opens the dialog with split on blank pages ticked:", await page.is_checked('.scan-dialog-extra[data-extra=splitOnBlank]'))
    await start_scan(page)
    scan = [x for x in await calls(page) if '/scan?' in x['url']][-1]
    print("...and scans with split_on_blank=true:", scan['url'].endswith('split_on_blank=true'))

    # Hidden by the person (Toolbar buttons…) stays hidden even when available.
    await page.click('#tools-btn')
    await page.click('#toolbar-buttons-btn')
    await page.uncheck('.toolbar-buttons-list input[data-key=scan-multi]')
    await page.click('#toolbar-buttons-done-btn')
    print("hidden via Toolbar buttons stays hidden:", not await visible(page, '#scan-multi-btn'))

    # Switching library resets it until the new library's check finishes.
    await page.evaluate(f"window.__HELPERS['{L1}'].down = true")
    await page.click('#reload-btn')
    await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({}); window.__TEST_ROOT.name = 'Other';")
    await page.click('#open-btn')
    await page.wait_for_timeout(400)
    print("another library without a reachable helper: Scan Multi hidden:",
          await page.eval_on_selector('#scan-multi-btn', 'e => e.classList.contains("scan-unavailable")'))
    print("no page errors:", errors == [])
    await browser.close()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `cd tests && python3 test_scan_dialog.py`
Expected: `scenario_scan_multi`'s first line prints `False` (Scan Multi is always shown).

- [ ] **Step 3: Implement**

1. CSS, next to `.toolbar-hidden`:

```css
  .scan-unavailable{ display:none !important; } /* Scan Multi while no found scanner can split on blank pages */
```

2. Markup: give the button the class from the start, so it never flashes before the first check:

```html
        <button id="scan-multi-btn" class="scan-unavailable" data-i18n="toolbarScanMulti">📸 Scan Multi</button>
```

3. Add after `scannerChoices()`:

```js
  // Scan Multi is a shortcut to the dialog with "Split on blank pages"
  // ticked, so it's shown only while some helper can do that: a scanner
  // offering splitOnBlank, or a scanix500 not paired yet (its one scanner,
  // the iX500, can -- pairing happens in the dialog). Kept apart from
  // .toolbar-hidden, which is the person's own choice in Toolbar buttons….
  function updateScanMultiAvailability(helpers){
    const available = helpers.some(h => (h.version === 1 && !h.paired) || h.scanners.some(s => s.extras.includes('splitOnBlank')));
    el('scan-multi-btn').classList.toggle('scan-unavailable', !available);
  }
```

4. In `refreshScanDialog()`, after `const helpers = await discoverScanHelpers();` add `updateScanMultiAvailability(helpers);` (before the `if(!el('scan-dialog-body')) return;` line, so a closed dialog still updates the button).

5. At the end of `afterDbReady()` add:

```js
    // Read-only requests to localhost: is there a scanner that can split on
    // blank pages (Scan Multi)? Ignored if another library opened meanwhile.
    const scanCheckRoot = rootDirHandle;
    discoverScanHelpers().then(helpers => { if(rootDirHandle === scanCheckRoot) updateScanMultiAvailability(helpers); });
```

6. In `resetAll()`, next to `scanBridgeUrl = null;`, add `el('scan-multi-btn').classList.add('scan-unavailable');`.

- [ ] **Step 4: Adjust the two toolbar tests**

`tests/test_toolbar_buttons.py` and `tests/test_tools_menu.py` expect Scan Multi visible on a fresh library. In each, right before the click on `#open-btn` that opens the library they check, install a minimal fake scanix500 so the check finds it:

```python
        await page.evaluate("""() => { window.fetch = async (url) => {
            if(url === 'http://localhost:8765/health') return new Response(JSON.stringify({service: 'scanix500-bridge'}), {status: 200});
            throw new TypeError('Failed to fetch'); }; }""")
```

and after that click add `await page.wait_for_timeout(200)` if the next line checks visibility. Leave their checks unchanged.

- [ ] **Step 5: Run the tests, including the layout ones**

Run:
```bash
cd tests
python3 test_scan_dialog.py
python3 test_toolbar_buttons.py
python3 test_tools_menu.py
python3 test_footer_pin.py
python3 test_collections.py
python3 test_i18n_coverage.py
```
Expected: every line `True`; `PASS`. `test_footer_pin.py` and `test_collections.py` (Scenario 30) measure the toolbar's wrapping; with Scan Multi hidden the toolbar is shorter, which only adds room. If either prints `False`, follow CLAUDE.md's `.table-wrap` note (re-run the sweep, adjust the test's reliability thresholds, never the four CSS constants) and record what you changed in your report.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_scan_dialog.py tests/test_toolbar_buttons.py tests/test_tools_menu.py
git commit -m "Scan Multi: a shortcut shown only when a scanner can split

Opens the scan dialog with split on blank pages ticked. Dossiary checks
for such a scanner when a library opens and whenever the dialog opens.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AnMx4wtUcaKMWsQm9eXUTo"
```

---

### Task 6: Field Settings text, documentation, manual check against the reference helper

**Files:**
- Modify: `dossiary.html` (Field Settings "Scanner Integration" text and links)
- Create: `tests/manual_scan_reference_helper.py`
- Modify: `CLAUDE.md`, `tests/CLAUDE.md`, `README.md`, `README.de.md`, `USER_GUIDE.md`, `USER_GUIDE.de.md`, `USER_GUIDE.es.md`, `USER_GUIDE.fr.md`, `USER_GUIDE.zh-Hans.md`, `USER_GUIDE.zh-Hant.md`, `docs/superpowers/specs/2026-10-09-system-scanner-helper-design.md`

- [ ] **Step 1: Field Settings**

Change the English strings:

```js
      fieldSettingsScannerIntegrationText: 'Scanning from the toolbar needs a small helper app running on this computer: dossiary-scan-helper for most scanners, or scanix500 for a ScanSnap iX500. Dossiary finds either one by itself; the address below is only for a helper on another port.',
      fieldSettingsScannerIntegrationLink: 'Get dossiary-scan-helper', fieldSettingsScannerIntegrationLinkScanix500: 'Get scanix500 (ScanSnap iX500)',
```

German:

```js
      fieldSettingsScannerIntegrationText: 'Zum Scannen aus der Werkzeugleiste braucht es eine kleine Hilfs-App auf diesem Computer: dossiary-scan-helper für die meisten Scanner oder scanix500 für einen ScanSnap iX500. Dossiary findet beide von selbst; die Adresse unten ist nur für einen Helfer auf einem anderen Port nötig.',
      fieldSettingsScannerIntegrationLink: 'dossiary-scan-helper herunterladen', fieldSettingsScannerIntegrationLinkScanix500: 'scanix500 herunterladen (ScanSnap iX500)',
```

Update the other four languages to match. In the Field Settings markup (`<div class="fs-scanner-integration" …>`), replace the single link with:

```html
            <a href="https://github.com/AarneAarebye/dossiary-scan-helper/releases" target="_blank" rel="noopener noreferrer" style="color:var(--phosphor); font-weight:600; font-size:13px;">${t('fieldSettingsScannerIntegrationLink')}</a>
            · <a href="https://github.com/AarneAarebye/iX500" target="_blank" rel="noopener noreferrer" style="color:var(--phosphor); font-weight:600; font-size:13px;">${t('fieldSettingsScannerIntegrationLinkScanix500')}</a>
```

Also change the `fieldSettingsScanBridgeUrlLabel` English text to `'Scan helper address (only if not on port 8765 or 8766)'` and German to `'Adresse des Scan-Helfers (nur wenn nicht auf Port 8765 oder 8766)'`, others to match.

Run `python3 tests/test_i18n_coverage.py` → `PASS`.

- [ ] **Step 2: Manual check against the real reference helper**

Create `tests/manual_scan_reference_helper.py` (not part of the suite; it needs the sibling repo):

```python
"""Manual check: Dossiary's scan dialog against the real reference helper.

Not part of the suite (named manual_* so suite runners skip it): it needs
~/Projects/Paperless/dossiary-scan-helper next to this repo. Starts the
reference helper on port 8766 (fake scanners, pairing code 000000), opens
Dossiary with the test stub's fake library, pairs through the dialog, scans
with "Fake Splitter" and split on blank pages, and expects two documents.
"""
import os, subprocess, sys, time, asyncio
os.chdir(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.abspath(os.path.join('..', 'dossiary.html'))
HELPER_REPO = os.path.expanduser('~/Projects/Paperless/dossiary-scan-helper/reference')
from playwright.async_api import async_playwright


async def main():
    helper = subprocess.Popen([sys.executable, '-m', 'scanbridge_ref', '--port', '8766'], cwd=HELPER_REPO,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(1)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))

            async def route_handler(route):
                url = route.request.url
                if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                    await route.fulfill(body="/* stubbed */", content_type='application/javascript')
                else:
                    await route.continue_()
            await page.route('**/*', route_handler)
            await page.add_init_script("window.__ALLOW_REAL_HELPERS = true;")
            await page.add_init_script(open('stub_studio2.js').read())
            await page.goto(f"file://{APP_PATH}")
            await page.wait_for_timeout(200)
            await page.evaluate("localStorage.removeItem('dossiary_scan_tokens')")
            await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({}); window.__TEST_ROOT.name = 'RefLib';")
            await page.click('#open-btn')
            await page.wait_for_timeout(1500)

            await page.click('#scan-btn')
            await page.wait_for_timeout(1500)
            row = '.scan-pair-row[data-url="http://localhost:8766"]'
            print("reference helper shows a pair row:", await page.locator(row).count() == 1)
            await page.fill(f'{row} .scan-pair-code', '000000')
            await page.click(f'{row} .scan-pair-btn')
            await page.wait_for_timeout(1500)
            options = await page.eval_on_selector_all('#scan-dialog-scanner option', 'els => els.map(e => e.textContent)')
            print("its seven fake scanners are listed:", sum(1 for o in options if o.startswith('Fake ')) == 7)
            print("Scan Multi shown (Fake Splitter can split):", await page.is_visible('#scan-multi-btn'))
            await page.select_option('#scan-dialog-scanner', 'http://localhost:8766|fake:splitter')
            await page.check('.scan-dialog-extra[data-extra=splitOnBlank]')
            await page.click('#scan-dialog-start-btn')
            await page.wait_for_timeout(3000)
            db = await page.evaluate("(async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text()))()")
            print("split on blank pages gave two documents:", len(db['documents']) == 2)

            await page.click('#scan-btn')
            await page.wait_for_timeout(1500)
            await page.select_option('#scan-dialog-scanner', 'http://localhost:8766|fake:offline')
            await page.click('#scan-dialog-start-btn')
            await page.wait_for_timeout(1500)
            print("an offline scanner's 503 message is shown:", len(await page.inner_text('#scan-dialog-status')) > 0)
            print("no page errors:", errors == [])
            await browser.close()
    finally:
        helper.terminate()
        helper.wait()

asyncio.run(main())
```

Run: `cd tests && python3 manual_scan_reference_helper.py`
Expected: every line `True`. If the reference helper's port 8766 is busy, stop whatever uses it first. Report the output in your task report.

- [ ] **Step 3: CLAUDE.md**

In `CLAUDE.md`, the bullet starting `- **Scan / Scan Multi toolbar buttons**` runs through the end of the `**Pairing (scanix500 0.3.0)**` paragraph. Replace that whole bullet (up to, not including, the next `- **Searchable PDF generation**` bullet) with:

```markdown
- **Scanning: the scan dialog and its helpers** (`openScanDialog()`,
  `discoverScanHelpers()`, `startScanFromDialog()`; spec
  `docs/superpowers/specs/2026-10-09-system-scanner-helper-design.md`,
  section 2; wire format in dossiary-scan-helper's `PROTOCOL.md`). A browser
  can't reach a scanner (see "No direct scanner integration" above), so a
  small helper app on the computer does the scanning and Dossiary talks to
  it over `fetch()`: scanix500 on `localhost:8765` (version 1 of the
  protocol, one fixed "ScanSnap iX500" entry, `V1_SCANNER`) and
  dossiary-scan-helper on `localhost:8766` (version 2: `GET /scanners`,
  JSON `POST /scan`). The Field Settings address (`scan_bridge_url`) is
  probed too, for a helper on another port. **Discovery**
  (`probeScanHelper()`, `loadHelperScanners()`) uses a 3 s `/health`
  timeout; a health with `protocol: 2` is version 2, one with
  `service: 'scanix500-bridge'` version 1, anything else is ignored.
  **📷 Scan opens the dialog**: every found scanner (a duplicated name gets
  its helper in brackets), and only the settings the chosen one supports --
  source, two-sided (only a duplex feeder), color, resolution, and the
  extras Dossiary knows (`splitOnBlank`, `skipBlankPages`; unknown ones are
  never shown or sent). The last scanner and settings are remembered per
  library (`scan_last_settings`); a gone scanner falls back to the first.
  **The scan request has no timeout** (a feeder batch can take minutes);
  while it runs the dialog's button reads "Scanning…" and Escape, backdrop
  and close are blocked (`scanDialogRunning`). Results, in either wire
  format (`decodeScanFiles()`), go through `writeScanFilesToInbox()` →
  `checkInbox()` → `addAllInboxFilesAndShowStatus()`, like any staged file;
  a `partial` result does the same, then shows the helper's message. A
  failure keeps the dialog open with the helper's message. **Pairing**:
  `Origin: null` can't tell this `file://` page from a sandboxed iframe on
  any website, so each browser pairs once per helper: a helper whose
  `/health` says `paired: false` shows a code field in the dialog
  (`submitInlinePairing()`, `POST /pair` `{code, client: 'Dossiary'}`), and
  the token is kept in `localStorage` (`dossiary_scan_tokens`, keyed by the
  helper's address -- per browser, not per library). `Authorization:
  Bearer <token>` is only sent when there is a token: a pre-0.3.0
  scanix500 (no `paired` field, counts as paired) rejects the preflight for
  that header. A 401 drops the token and brings the code field back.
  **📸 Scan Multi** opens the same dialog with split on blank pages ticked,
  and is shown only while a found scanner offers `splitOnBlank` or a
  scanix500 waits to be paired (`updateScanMultiAvailability()`,
  `.scan-unavailable`, kept apart from the person's own `.toolbar-hidden`).
  Dossiary checks when a library opens (read-only requests to localhost)
  and whenever the dialog opens. **Nothing found** explains what to
  install, links dossiary-scan-helper's releases and scanix500, and offers
  the address field with "Look again". **Tests**: the shared stub fails
  every request to another localhost origin, so no test reaches a real
  helper on the machine; `tests/test_scan_dialog.py` fakes helpers per
  scenario, and `tests/manual_scan_reference_helper.py` checks against the
  real reference helper by hand.
```

Also in the "Tools" dropdown note, the sentence listing the toolbar's daily buttons stays as is (Scan Multi is still a toolbar button).

- [ ] **Step 4: tests/CLAUDE.md**

1. Change "**97 scripts**" to "**96 scripts**" and "(94 of them Playwright-driven" to "(93 of them Playwright-driven".
2. Delete the `scan-helper pairing (\`test_scan_pairing.py\` -- …)` item (from `scan-helper pairing (` through its closing `repeat),`).
3. Replace the long `the Scan/Scan Multi toolbar buttons (\`test_scan_bridge.py\` — …` item, through its closing `not HTTP).` sentence, with:

```markdown
the scan dialog (`test_scan_dialog.py` -- a fake `fetch` defined in the
test plays any number of helpers by base URL (`FAKE_HELPERS`, version 1,
version 2, legacy, unreachable, or not a helper), each request logged in
`window.__CALLS`: discovery across both default ports and the manual
address (127.0.0.1 not probed twice, a non-helper `/health` ignored,
invalid scanner entries dropped, a 401 from `/scanners` meaning not
paired, no Authorization header without a token); the dialog's scanner
list with the helper in brackets for a duplicated name, only the settings
each scanner supports (two-sided only for a duplex feeder, known extras
only), remembered settings per library and the fallback for a gone
scanner; "nothing found" with its links and Look again saving a new
address; version 1 scans (query string, split on blank pages, multi-file,
an already-staged same name kept, partial, hard failure keeping the
dialog open, 404 outdated, 409, unreachable, non-JSON, missing files) and
version 2 scans (the exact JSON body, extras as known booleans, 422/503/500
messages, partial); the running state (button text, toolbar disabled,
Escape/close/backdrop blocked); inline pairing for both versions (local
code check, wrong code, `{code, client}` JSON, token per helper, a 401
dropping it, a legacy bridge scanning without a header); and Scan Multi
shown only while a scanner can split, opening the dialog with split
ticked, respecting Toolbar buttons…, reset on a library switch. The shared
stub fails every request to another localhost origin unless
`window.__ALLOW_REAL_HELPERS` is set, which only
`manual_scan_reference_helper.py` (a manual check against the real
reference helper, not part of the suite) does),
```

- [ ] **Step 5: READMEs**

In `README.md`, find the scanning description (`grep -n "Scan Multi\|scanix500\|pairing\|Pair a Browser" README.md`). Replace the paragraph(s) describing the Scan/Scan Multi buttons, auto-connect, the port dialog and pairing with:

```markdown
- **Scanning** — 📷 **Scan** opens a dialog listing every scanner a scan
  helper on this computer offers, with only the settings that scanner
  supports (paper source, both sides, color, resolution, and for the
  ScanSnap iX500 "split on blank pages"). Two helpers are supported:
  [dossiary-scan-helper](https://github.com/AarneAarebye/dossiary-scan-helper)
  for most scanners (macOS and Windows), and
  [scanix500](https://github.com/AarneAarebye/iX500) for a ScanSnap iX500.
  Dossiary finds them by itself on ports 8766 and 8765; a helper on another
  port can be entered in the dialog or in Field Settings. Each browser pairs
  with a helper once: the helper's "Pair a Browser…" shows a 6-digit code to
  type into the dialog. Scanned pages land in the Inbox. 📸 **Scan Multi**
  opens the same dialog with "split on blank pages" ticked and only shows
  while a scanner that can do that is available. Dossiary remembers the last
  scanner and settings per library.
```

Do the same in `README.de.md` with:

```markdown
- **Scannen** — 📷 **Scannen** öffnet einen Dialog mit allen Scannern, die
  ein Scan-Helfer auf diesem Computer anbietet, und nur den Einstellungen,
  die der jeweilige Scanner kann (Papierquelle, beidseitig, Farbe,
  Auflösung, beim ScanSnap iX500 „An leeren Seiten trennen“). Zwei Helfer
  werden unterstützt:
  [dossiary-scan-helper](https://github.com/AarneAarebye/dossiary-scan-helper)
  für die meisten Scanner (macOS und Windows) und
  [scanix500](https://github.com/AarneAarebye/iX500) für einen ScanSnap
  iX500. Dossiary findet sie selbst auf den Ports 8766 und 8765; ein Helfer
  auf einem anderen Port lässt sich im Dialog oder in den Feldeinstellungen
  eintragen. Jeder Browser wird einmal mit einem Helfer gekoppelt: „Pair a
  Browser…“ im Helfer zeigt einen 6-stelligen Code, der im Dialog
  eingegeben wird. Gescannte Seiten landen im Posteingang. 📸 **Mehrfach
  scannen** öffnet denselben Dialog mit „An leeren Seiten trennen“
  angehakt und erscheint nur, solange ein Scanner das kann. Dossiary merkt
  sich den letzten Scanner und seine Einstellungen pro Bibliothek.
```

In both READMEs update the test count (`97` → `96`) wherever it appears (`grep -n "97" README*.md`).

- [ ] **Step 6: User Guides**

In each of the six guides, add a short "Scanning" section right after the section about the Inbox (find it with `grep -n "^## " USER_GUIDE.md`). English:

```markdown
## Scanning straight into Dossiary

If you have a scanner, Dossiary can scan into the Inbox for you. It needs a
small helper app on your computer: [dossiary-scan-helper](https://github.com/AarneAarebye/dossiary-scan-helper)
for most scanners, or [scanix500](https://github.com/AarneAarebye/iX500) for
a ScanSnap iX500.

1. Start the helper.
2. Click **📷 Scan**. The first time, the dialog asks for a pairing code:
   choose **Pair a Browser…** in the helper's menu and type the 6-digit
   code it shows.
3. Pick your scanner and settings, then click **Scan**. The pages arrive in
   the Inbox, ready to review.

Dossiary remembers your scanner and settings for next time. With a scanner
that can split a stack on blank sheets, **📸 Scan Multi** turns one stack
into several documents.
```

German (`USER_GUIDE.de.md`):

```markdown
## Direkt in Dossiary scannen

Mit einem Scanner kann Dossiary direkt in den Posteingang scannen. Dafür
braucht es eine kleine Hilfs-App auf deinem Computer:
[dossiary-scan-helper](https://github.com/AarneAarebye/dossiary-scan-helper)
für die meisten Scanner oder [scanix500](https://github.com/AarneAarebye/iX500)
für einen ScanSnap iX500.

1. Starte den Helfer.
2. Klicke auf **📷 Scannen**. Beim ersten Mal fragt der Dialog nach einem
   Kopplungscode: Wähle **Pair a Browser…** im Menü des Helfers und gib den
   6-stelligen Code ein, den er anzeigt.
3. Wähle Scanner und Einstellungen und klicke auf **Scannen**. Die Seiten
   landen im Posteingang und warten auf die Prüfung.

Dossiary merkt sich Scanner und Einstellungen für das nächste Mal. Mit einem
Scanner, der einen Stapel an leeren Blättern trennen kann, macht
**📸 Mehrfach scannen** aus einem Stapel mehrere Dokumente.
```

Spanish, French, Simplified Chinese: translate the English section, using each language's UI labels for the buttons (`toolbarScan`, `toolbarScanMulti` in that language's `STRINGS` block). Traditional Chinese: OpenCC `s2t` of the Simplified section, then make sure button labels match `STRINGS['zh-Hant']`. No screenshots are added (the capture script has no scanner).

- [ ] **Step 7: Spec status**

In `docs/superpowers/specs/2026-10-09-system-scanner-helper-design.md`, section "4. Order of work", append to item 2: ` **Done (2026-10-09):** plan docs/superpowers/plans/2026-10-09-scan-dialog.md.`

- [ ] **Step 8: Run the full scan-related set and commit**

Run:
```bash
cd tests
python3 test_scan_dialog.py
python3 test_i18n_coverage.py
python3 test_toolbar_buttons.py
python3 test_tools_menu.py
python3 test_i18n.py
```
Expected: every line `True`; `PASS`.

```bash
git add dossiary.html tests/manual_scan_reference_helper.py CLAUDE.md tests/CLAUDE.md README.md README.de.md USER_GUIDE*.md docs/superpowers/specs/2026-10-09-system-scanner-helper-design.md
git commit -m "Docs: the scan dialog, both helpers, and a manual reference-helper check

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AnMx4wtUcaKMWsQm9eXUTo"
```

---

## After the last task

Run the whole suite once (every `tests/test_*.py`; `test_i18n_coverage.py` prints `PASS`, everything else prints only `True` lines) before the final review. The release (version bump, screenshot recapture, tag) happens only when the owner asks for it.
