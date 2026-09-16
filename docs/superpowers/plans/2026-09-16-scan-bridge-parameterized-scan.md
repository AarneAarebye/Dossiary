# Scan Bridge Parameterized Scan (Dossiary side) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `triggerScan()`'s profile-name-based request
(`POST /scan/<profile-name>`) with the new parameterized one
(`POST /scan?skip_blank_filter=...&skip_ocr=...&split_on_blank=...`),
matching the already-merged scanix500-side change, and drop the
`SCAN_PROFILE_NAME`/`SCAN_MULTI_PROFILE_NAME` constants entirely.

**Architecture:** `triggerScan(profileName)` and the three functions that
thread that same parameter through it (`connectScanBridgeAndTrigger()`,
`openScanConnectDialog()`, `submitScanConnectDialog()`) all rename their
parameter to `isMulti` (a boolean) — a pure rename for three of the four,
since they only pass the value through; `triggerScan()` itself gets a new
`URLSearchParams`-based query string builder replacing the old
`encodeURIComponent(profileName)` path segment. The `404` and new `400`
response-status branches get new, accurate status messages (there's no
more "profile not configured" case — no profile exists anymore to be
unconfigured).

**Tech Stack:** Vanilla JS (no framework), `URLSearchParams`, Playwright
for tests (`tests/test_scan_bridge.py`).

## Global Constraints

- The scanix500-side bridge change this plan depends on is already merged
  to iX500's own `main` (not yet pushed to `origin` — see that repo's own
  `docs/superpowers/plans/2026-09-16-scan-bridge-parameterized-scan.md`):
  `POST /scan/<profile-name>` is gone, replaced by
  `POST /scan?skip_blank_filter=<true|false>&skip_ocr=<true|false>&split_on_blank=<true|false>`,
  each parameter required and exactly `"true"`/`"false"`, else `400`. A
  `404` now means the bridge doesn't recognize the request shape at all
  (e.g. an outdated bridge predating this change) rather than "unknown
  profile name." The response body shape
  (`ok`/`partial`/`message`/`output_paths`/`files`), `GET /health`, and
  the `409` busy response are all unchanged.
- **This is a breaking, non-backward-compatible change on the wire.**
  Once this plan lands and both sides are deployed together, Dossiary can
  no longer talk to a pre-parameterized-scan scanix500 bridge (it would
  `404` against `POST /scan/...` with no profile-name segment). This
  plan's own docs task must not overstate readiness beyond what's true —
  see the sibling repo's own README for the exact wording used there
  about this same coordination requirement.
- `skip_blank_filter` and `skip_ocr` are always sent as `"false"` — Dossiary
  never exposes them as user-configurable settings, matching the old
  profiles' own unedited defaults. Only `split_on_blank` varies, `"true"`
  for Scan Multi and `"false"` for plain Scan.
- The existing `scanProfileNotConfigured` i18n key (no longer referenced
  once this plan lands) is left in place, unused, across all 6 languages
  — matching the established precedent for `scanBridgeNotConfigured` from
  the earlier auto-connect amendment. Do not remove it.
- `checkInbox()`/`addAllInboxFilesAndShowStatus()`, `writeScanFilesToInbox()`,
  `uniqueInboxFilename()`, the auto-connect flow's own health-probe/dialog
  mechanics (`probeScanBridgeHealth()`, the re-entrancy guard, the
  DOM-presence cancel guard), and the `try/finally` button re-enable
  guarantee are all unchanged by this plan — only the URL construction and
  the 400/404 status-handling branches change.
- Follow `tests/CLAUDE.md`'s conventions exactly: `window.fetch` stubbed
  per-scenario directly inside `tests/test_scan_bridge.py` itself, never
  added to the shared `stub_studio2.js`. Update that file's own paragraph
  describing `test_scan_bridge.py`'s scenarios in the same change that
  changes those scenarios.

---

### Task 1: Parameterize `triggerScan()`, update `test_scan_bridge.py`

**Files:**
- Modify: `dossiary.html` (rename four functions' `profileName` parameter
  to `isMulti`, rewrite the request-URL construction, rewrite the
  404/add a 400 branch, remove `SCAN_PROFILE_NAME`/`SCAN_MULTI_PROFILE_NAME`,
  update the click handlers, add 2 new i18n keys × 6 languages)
- Modify: `tests/test_scan_bridge.py` (replace entire file content)

**Interfaces:**
- Consumes: `scanBridgeUrl`, `saveScanBridgeUrl()`, `probeScanBridgeHealth()`,
  `setStatusT()`, `t()`, `el()`, `checkInbox()`/`addAllInboxFilesAndShowStatus()`,
  `writeScanFilesToInbox()` (all already shipped, unchanged).
- Produces: `triggerScan(isMulti)` (renamed parameter from `profileName`),
  `connectScanBridgeAndTrigger(isMulti)`, `openScanConnectDialog(isMulti)`,
  `submitScanConnectDialog(isMulti)` (all three renamed the same way,
  purely a rename — no other task in this plan calls these directly, but
  Task 2's docs describe them by their new names).

- [ ] **Step 1: Add the 2 new i18n keys to all 6 `STRINGS` blocks**

In `STRINGS.en`, immediately after the line
`scanConnectFailed: "Couldn't reach a scanner bridge at {url}.",`
(currently `dossiary.html:1034`), insert:

```javascript
      scanBadRequest: 'The scanner bridge rejected the request: {message}',
      scanBridgeOutdated: "The scanner bridge didn't recognize this request — update scanix500-menubar to the latest version.",
```

In `STRINGS.es`, immediately after that block's own
`scanConnectFailed: 'No se pudo conectar con un puente del escáner en {url}.',`
(currently `dossiary.html:1222`), insert:

```javascript
      scanBadRequest: 'El puente del escáner rechazó la solicitud: {message}',
      scanBridgeOutdated: 'El puente del escáner no reconoció esta solicitud — actualice scanix500-menubar a la última versión.',
```

In `STRINGS.fr`, immediately after that block's own
`scanConnectFailed: 'Impossible de joindre un pont du scanner à {url}.',`
(currently `dossiary.html:1410`), insert:

```javascript
      scanBadRequest: 'Le pont du scanner a rejeté la requête : {message}',
      scanBridgeOutdated: "Le pont du scanner n'a pas reconnu cette requête — mettez à jour scanix500-menubar vers la dernière version.",
```

In `STRINGS.de`, immediately after that block's own
`scanConnectFailed: 'Es konnte keine Scanner-Bridge unter {url} erreicht werden.',`
(currently `dossiary.html:1598`), insert:

```javascript
      scanBadRequest: 'Die Scanner-Bridge hat die Anfrage abgelehnt: {message}',
      scanBridgeOutdated: 'Die Scanner-Bridge hat diese Anfrage nicht erkannt — bitte scanix500-menubar auf die neueste Version aktualisieren.',
```

In `STRINGS['zh-Hans']`, immediately after that block's own
`scanConnectFailed: '无法连接到 {url} 的扫描桥接。',` (currently
`dossiary.html:1786`), insert:

```javascript
      scanBadRequest: '扫描桥接拒绝了该请求：{message}',
      scanBridgeOutdated: '扫描桥接无法识别此请求 —— 请将 scanix500-menubar 更新到最新版本。',
```

In `STRINGS['zh-Hant']`, immediately after that block's own
`scanConnectFailed: '無法連接到 {url} 的掃描橋接。',` (currently
`dossiary.html:2097`), insert (a straight script conversion of the
zh-Hans block above, matching this repo's established zh-Hant derivation
convention):

```javascript
      scanBadRequest: '掃描橋接拒絕了該請求：{message}',
      scanBridgeOutdated: '掃描橋接無法識別此請求 —— 請將 scanix500-menubar 更新到最新版本。',
```

- [ ] **Step 2: Remove the `SCAN_PROFILE_NAME`/`SCAN_MULTI_PROFILE_NAME` constants**

In `dossiary.html`, find:

```javascript
  const SCAN_PROFILE_NAME = 'Dossiary Scan';
  const SCAN_MULTI_PROFILE_NAME = 'Dossiary Scan Multi';

```

Delete those two lines (and the blank line after them) entirely.

- [ ] **Step 3: Rewrite `triggerScan()` and rename the three functions that call it**

Find `connectScanBridgeAndTrigger`, `openScanConnectDialog`, and
`submitScanConnectDialog` (currently using `profileName` as their
parameter name throughout):

```javascript
  async function connectScanBridgeAndTrigger(profileName){
    const defaultUrl = `http://localhost:${SCAN_BRIDGE_DEFAULT_PORT}`;
    setStatusT('scanConnectProbing', null, 'busy');
    const reachable = await probeScanBridgeHealth(defaultUrl);
    if(reachable){
      await saveScanBridgeUrl(defaultUrl);
      await triggerScan(profileName);
      return;
    }
    openScanConnectDialog(profileName);
  }

  function openScanConnectDialog(profileName){
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <h2>${t('scanConnectTitle')}</h2>
          <p style="font-size:12.5px; color:var(--text-dim); line-height:1.6; margin:0 0 16px;">
            ${t('scanConnectInstructions')}
          </p>
          <div class="field">
            <label for="scan-connect-port">${t('scanConnectPortLabel')}</label>
            <input type="text" id="scan-connect-port" value="${SCAN_BRIDGE_DEFAULT_PORT}" />
          </div>
          <div id="scan-connect-status" class="doc-sub" style="margin-top:8px; min-height:1.2em;"></div>
          <div class="modal-actions" style="margin-top:16px;">
            <button id="scan-connect-cancel-btn">${t('commonCancel')}</button>
            <button id="scan-connect-submit-btn">${t('scanConnectSubmit')}</button>
          </div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('scan-connect-cancel-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
    el('scan-connect-submit-btn').addEventListener('click', () => submitScanConnectDialog(profileName));
  }

  async function submitScanConnectDialog(profileName){
    const portInput = el('scan-connect-port');
    const statusEl = el('scan-connect-status');
    const port = portInput.value.trim();
    if(!/^\d+$/.test(port)){
      statusEl.textContent = t('scanConnectInvalidPort');
      return;
    }
    const submitBtn = el('scan-connect-submit-btn');
    submitBtn.disabled = true;
    statusEl.textContent = t('scanConnectProbing');
    const url = `http://localhost:${port}`;
    const reachable = await probeScanBridgeHealth(url);
    submitBtn.disabled = false;
    if(!reachable){
      statusEl.textContent = t('scanConnectFailed', {url});
      return;
    }
    if(!el('scan-connect-port')){
      // The dialog was dismissed (Cancel/close/backdrop/Escape) while this
      // probe was still in flight -- don't silently save a URL or start a
      // scan the person already walked away from.
      return;
    }
    await saveScanBridgeUrl(url);
    closeModal();
    await triggerScan(profileName);
  }
```

Replace all three with the identical logic, `profileName` renamed to
`isMulti` throughout (a pure rename — nothing else changes):

```javascript
  async function connectScanBridgeAndTrigger(isMulti){
    const defaultUrl = `http://localhost:${SCAN_BRIDGE_DEFAULT_PORT}`;
    setStatusT('scanConnectProbing', null, 'busy');
    const reachable = await probeScanBridgeHealth(defaultUrl);
    if(reachable){
      await saveScanBridgeUrl(defaultUrl);
      await triggerScan(isMulti);
      return;
    }
    openScanConnectDialog(isMulti);
  }

  function openScanConnectDialog(isMulti){
    modalRoot.innerHTML = `
      <div class="backdrop" id="modal-backdrop">
        <div class="modal" role="dialog" aria-modal="true">
          <button class="modal-close" id="modal-close-btn" aria-label="${t('detailCloseAriaLabel')}">✕</button>
          <h2>${t('scanConnectTitle')}</h2>
          <p style="font-size:12.5px; color:var(--text-dim); line-height:1.6; margin:0 0 16px;">
            ${t('scanConnectInstructions')}
          </p>
          <div class="field">
            <label for="scan-connect-port">${t('scanConnectPortLabel')}</label>
            <input type="text" id="scan-connect-port" value="${SCAN_BRIDGE_DEFAULT_PORT}" />
          </div>
          <div id="scan-connect-status" class="doc-sub" style="margin-top:8px; min-height:1.2em;"></div>
          <div class="modal-actions" style="margin-top:16px;">
            <button id="scan-connect-cancel-btn">${t('commonCancel')}</button>
            <button id="scan-connect-submit-btn">${t('scanConnectSubmit')}</button>
          </div>
        </div>
      </div>
    `;
    el('modal-close-btn').addEventListener('click', closeModal);
    el('scan-connect-cancel-btn').addEventListener('click', closeModal);
    el('modal-backdrop').addEventListener('click', (e) => { if(e.target.id === 'modal-backdrop') closeModal(); });
    document.addEventListener('keydown', onModalKeydown);
    el('scan-connect-submit-btn').addEventListener('click', () => submitScanConnectDialog(isMulti));
  }

  async function submitScanConnectDialog(isMulti){
    const portInput = el('scan-connect-port');
    const statusEl = el('scan-connect-status');
    const port = portInput.value.trim();
    if(!/^\d+$/.test(port)){
      statusEl.textContent = t('scanConnectInvalidPort');
      return;
    }
    const submitBtn = el('scan-connect-submit-btn');
    submitBtn.disabled = true;
    statusEl.textContent = t('scanConnectProbing');
    const url = `http://localhost:${port}`;
    const reachable = await probeScanBridgeHealth(url);
    submitBtn.disabled = false;
    if(!reachable){
      statusEl.textContent = t('scanConnectFailed', {url});
      return;
    }
    if(!el('scan-connect-port')){
      // The dialog was dismissed (Cancel/close/backdrop/Escape) while this
      // probe was still in flight -- don't silently save a URL or start a
      // scan the person already walked away from.
      return;
    }
    await saveScanBridgeUrl(url);
    closeModal();
    await triggerScan(isMulti);
  }
```

Then find `triggerScan()` itself:

```javascript
  async function triggerScan(profileName){
    if(!scanBridgeUrl){
      await connectScanBridgeAndTrigger(profileName);
      return;
    }
    try{
      el('scan-btn').disabled = true;
      el('scan-multi-btn').disabled = true;
      setStatusT('scanScanning', null, 'busy');
      let response;
      try{
        response = await fetch(`${scanBridgeUrl}/scan/${encodeURIComponent(profileName)}`, { method: 'POST' });
      }catch(networkErr){
        // Genuinely couldn't reach anything at scanBridgeUrl (bridge down,
        // wrong port after a restart, etc.) -- offer to reconfigure rather
        // than just showing an unreachable-bridge status with no recovery
        // path. Distinct from a malformed/non-JSON response below, which
        // means something DID answer at this URL, just not correctly --
        // reopening the port dialog wouldn't help there.
        openScanConnectDialog(profileName);
        return;
      }
      if(response.status === 404){ setStatusT('scanProfileNotConfigured', {profile: profileName}, 'err'); return; }
      if(response.status === 409){ setStatusT('scanAlreadyInProgress', null, 'err'); return; }
      const result = await response.json();
      if(result.ok || result.partial){
        // A malformed/missing `files` array here means the bridge is
        // reachable but doesn't speak this protocol version (e.g. an
        // older scanix500-menubar that predates the files field) -- a
        // hard failure, not a silent no-op, so it must not fall through
        // to the Inbox pipeline as if nothing were wrong. Falls into the
        // same catch block below as a malformed JSON response already
        // does.
        if(!Array.isArray(result.files)) throw new Error('missing files field in bridge response');
        await writeScanFilesToInbox(result.files);
        await checkInbox();
        await addAllInboxFilesAndShowStatus();
        if(result.ok) return;
        // A partial scan (e.g. a multi-feed jam) still wrote a usable file --
        // run the Inbox pipeline same as a full success, but the bridge's own
        // message (naming what went wrong) is more important than the Inbox
        // pipeline's own "Added N document(s)" report, so it's shown last,
        // deliberately overwriting that report as the final status line.
        setStatusT('scanPartialMessage', {message: result.message || String(response.status)}, 'err');
        return;
      }
      setStatusT('scanFailedMessage', {message: result.message || String(response.status)}, 'err');
    }catch(e){
      // Covers a malformed/non-JSON response body (e.g. scanBridgeUrl
      // misconfigured to point at some unrelated server that DID answer) --
      // the bridge was reachable here, so this is not the "wrong port"
      // case above; the existing unreachable-style message applies.
      setStatusT('scanBridgeUnreachable', {url: scanBridgeUrl}, 'err');
    }finally{
      // try/finally, not a re-enable call on each branch above, so the
      // buttons can never be left stuck disabled regardless of which path
      // was taken or whether an exception was thrown.
      el('scan-btn').disabled = false;
      el('scan-multi-btn').disabled = false;
    }
  }
```

Replace it with:

```javascript
  async function triggerScan(isMulti){
    if(!scanBridgeUrl){
      await connectScanBridgeAndTrigger(isMulti);
      return;
    }
    try{
      el('scan-btn').disabled = true;
      el('scan-multi-btn').disabled = true;
      setStatusT('scanScanning', null, 'busy');
      let response;
      try{
        // skip_blank_filter/skip_ocr are always sent false -- Dossiary
        // never exposes them as user-configurable settings, matching the
        // old profiles' own unedited defaults. split_on_blank is the one
        // flag that actually distinguishes the two buttons.
        const params = new URLSearchParams({
          skip_blank_filter: 'false',
          skip_ocr: 'false',
          split_on_blank: isMulti ? 'true' : 'false',
        });
        response = await fetch(`${scanBridgeUrl}/scan?${params}`, { method: 'POST' });
      }catch(networkErr){
        // Genuinely couldn't reach anything at scanBridgeUrl (bridge down,
        // wrong port after a restart, etc.) -- offer to reconfigure rather
        // than just showing an unreachable-bridge status with no recovery
        // path. Distinct from a malformed/non-JSON response below, which
        // means something DID answer at this URL, just not correctly --
        // reopening the port dialog wouldn't help there.
        openScanConnectDialog(isMulti);
        return;
      }
      if(response.status === 400){
        // Should never happen from a correctly-built request -- defensive
        // only, e.g. a version mismatch where the bridge's own validation
        // rules differ from what Dossiary sends.
        const errorBody = await response.json().catch(() => null);
        setStatusT('scanBadRequest', {message: (errorBody && errorBody.error) || String(response.status)}, 'err');
        return;
      }
      if(response.status === 404){
        // No more per-profile lookup, so this no longer means "profile not
        // configured" -- it means the bridge doesn't recognize this request
        // shape at all, almost certainly an outdated scanix500-menubar that
        // predates the parameterized /scan endpoint.
        setStatusT('scanBridgeOutdated', null, 'err');
        return;
      }
      if(response.status === 409){ setStatusT('scanAlreadyInProgress', null, 'err'); return; }
      const result = await response.json();
      if(result.ok || result.partial){
        // A malformed/missing `files` array here means the bridge is
        // reachable but doesn't speak this protocol version (e.g. an
        // older scanix500-menubar that predates the files field) -- a
        // hard failure, not a silent no-op, so it must not fall through
        // to the Inbox pipeline as if nothing were wrong. Falls into the
        // same catch block below as a malformed JSON response already
        // does.
        if(!Array.isArray(result.files)) throw new Error('missing files field in bridge response');
        await writeScanFilesToInbox(result.files);
        await checkInbox();
        await addAllInboxFilesAndShowStatus();
        if(result.ok) return;
        // A partial scan (e.g. a multi-feed jam) still wrote a usable file --
        // run the Inbox pipeline same as a full success, but the bridge's own
        // message (naming what went wrong) is more important than the Inbox
        // pipeline's own "Added N document(s)" report, so it's shown last,
        // deliberately overwriting that report as the final status line.
        setStatusT('scanPartialMessage', {message: result.message || String(response.status)}, 'err');
        return;
      }
      setStatusT('scanFailedMessage', {message: result.message || String(response.status)}, 'err');
    }catch(e){
      // Covers a malformed/non-JSON response body (e.g. scanBridgeUrl
      // misconfigured to point at some unrelated server that DID answer) --
      // the bridge was reachable here, so this is not the "wrong port"
      // case above; the existing unreachable-style message applies.
      setStatusT('scanBridgeUnreachable', {url: scanBridgeUrl}, 'err');
    }finally{
      // try/finally, not a re-enable call on each branch above, so the
      // buttons can never be left stuck disabled regardless of which path
      // was taken or whether an exception was thrown.
      el('scan-btn').disabled = false;
      el('scan-multi-btn').disabled = false;
    }
  }
```

- [ ] **Step 4: Update the click handlers**

Find:

```javascript
  el('scan-btn').addEventListener('click', () => startScan(SCAN_PROFILE_NAME));
  el('scan-multi-btn').addEventListener('click', () => startScan(SCAN_MULTI_PROFILE_NAME));
```

Replace with:

```javascript
  el('scan-btn').addEventListener('click', () => startScan(false));
  el('scan-multi-btn').addEventListener('click', () => startScan(true));
```

- [ ] **Step 5: Replace `tests/test_scan_bridge.py` with this full content**

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# The exact query string Dossiary's own triggerScan() builds via
# URLSearchParams for the two toolbar buttons -- skip_blank_filter/skip_ocr
# are always 'false', only split_on_blank varies.
SCAN_URL_SUFFIX = 'skip_blank_filter=false&skip_ocr=false&split_on_blank=false'
SCAN_MULTI_URL_SUFFIX = 'skip_blank_filter=false&skip_ocr=false&split_on_blank=true'

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
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededEmptyRoot([], []);")
        await page.click('#open-btn')
        await page.wait_for_timeout(300)

        # === Scenario 1: scan_bridge_url is unset by default, persists an
        # explicit value, and survives a reopen (mirrors reminder_lookahead_days'
        # own Scenario 2 in tests/test_reminders.py) ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        url_field_present = await page.locator('#fs-scan-bridge-url').count()
        print("Scanner bridge URL field present in Field Settings:", url_field_present == 1)
        url_default = await page.evaluate("document.getElementById('fs-scan-bridge-url').value")
        print("scan_bridge_url defaults to empty with no persisted setting:", url_default == '')

        await page.fill('#fs-scan-bridge-url', 'http://127.0.0.1:8765')
        await page.dispatch_event('#fs-scan-bridge-url', 'change')
        await page.wait_for_timeout(200)
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        persisted = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        url_row = next((s for s in persisted['settings'] if s['key'] == 'scan_bridge_url'), None)
        print("scan_bridge_url persisted as 'http://127.0.0.1:8765':", url_row['value'] if url_row else None)

        # Reopen (same convention test_reminders.py Scenario 2 uses -- re-seed a
        # fresh root with the setting already present, simulating a real reopen
        # reading the same on-disk library.sqlite back)
        seed_with_url = {'settings': [{'key': 'scan_bridge_url', 'value': 'http://127.0.0.1:8765'}]}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        url_after_reopen = await page.evaluate("document.getElementById('fs-scan-bridge-url').value")
        print("scan_bridge_url reads back as 'http://127.0.0.1:8765' after reopening:", url_after_reopen == 'http://127.0.0.1:8765')
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        # === Scenario 2: unset scan_bridge_url -- clicking Scan probes the
        # default port's /health endpoint first; a reachable bridge is
        # adopted silently (saved, and the original scan proceeds) with no
        # dialog ever shown ===
        seed_no_url = {}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_no_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        scan_btn_present = await page.locator('#scan-btn').count()
        scan_multi_btn_present = await page.locator('#scan-multi-btn').count()
        print("Scan button present in toolbar:", scan_btn_present == 1)
        print("Scan Multi button present in toolbar:", scan_multi_btn_present == 1)

        await page.evaluate("""
            () => {
                window.__FETCH_CALLS = [];
                window.fetch = async (url, opts) => {
                    window.__FETCH_CALLS.push(url);
                    if(url.endsWith('/health')) return new Response(JSON.stringify({service: 'scanix500-bridge'}), {status: 200});
                    return new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: [], files: []}), {status: 200});
                };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        fetch_calls_scenario2 = await page.evaluate("window.__FETCH_CALLS")
        print("health probe hit the default port first:", len(fetch_calls_scenario2) >= 1 and fetch_calls_scenario2[0] == 'http://localhost:8765/health')
        dialog_shown = await page.locator('#scan-connect-port').count()
        print("no configure dialog shown when the default port is reachable:", dialog_shown == 0)
        saved_url = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                const dbState = JSON.parse(await f.text());
                const row = dbState.settings.find(s => s.key === 'scan_bridge_url');
                return row ? row.value : null;
            })()
        """)
        print("scan_bridge_url auto-saved as the default port's URL:", saved_url == 'http://localhost:8765')

        # === Scenario 2b: default port unreachable -- the Configure Scanner
        # Connection dialog opens; entering a different port that IS
        # reachable saves it and proceeds with the original scan ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_no_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.__FETCH_CALLS = [];
                window.fetch = async (url, opts) => {
                    window.__FETCH_CALLS.push(url);
                    if(url.startsWith('http://localhost:8765')) throw new TypeError('Failed to fetch');
                    if(url.endsWith('/health')) return new Response(JSON.stringify({service: 'scanix500-bridge'}), {status: 200});
                    return new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: [], files: []}), {status: 200});
                };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        dialog_shown_after_default_fails = await page.locator('#scan-connect-port').count()
        print("configure dialog opens when the default port is unreachable:", dialog_shown_after_default_fails == 1)
        prefilled_port = await page.evaluate("document.getElementById('scan-connect-port').value")
        print("dialog's port field pre-filled with 8765:", prefilled_port == '8765')

        await page.fill('#scan-connect-port', '9999')
        await page.click('#scan-connect-submit-btn')
        await page.wait_for_timeout(300)
        dialog_closed_after_success = await page.locator('#scan-connect-port').count()
        print("dialog closes once the manually-entered port connects successfully:", dialog_closed_after_success == 0)
        saved_manual_url = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                const dbState = JSON.parse(await f.text());
                const row = dbState.settings.find(s => s.key === 'scan_bridge_url');
                return row ? row.value : null;
            })()
        """)
        print("scan_bridge_url saved as the manually-entered port's URL:", saved_manual_url == 'http://localhost:9999')
        fetch_calls_2b = await page.evaluate("window.__FETCH_CALLS")
        print("the original scan proceeded after connecting:", any(u == f'http://localhost:9999/scan?{SCAN_URL_SUFFIX}' for u in fetch_calls_2b))

        # === Scenario 2c: an invalid port entry is rejected without
        # attempting to connect; a validly-formatted but also-unreachable
        # port keeps the dialog open with an inline error; Cancel dismisses
        # it with no scan ever attempted ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_no_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => { throw new TypeError('Failed to fetch'); };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)

        await page.fill('#scan-connect-port', 'abc')
        await page.click('#scan-connect-submit-btn')
        await page.wait_for_timeout(150)
        invalid_port_message = await page.locator('#scan-connect-status').inner_text()
        print("dialog rejects a non-numeric port without attempting to connect:", len(invalid_port_message) > 0)
        dialog_still_open_after_invalid = await page.locator('#scan-connect-port').count()
        print("dialog stays open after an invalid port entry:", dialog_still_open_after_invalid == 1)

        await page.fill('#scan-connect-port', '9999')
        await page.click('#scan-connect-submit-btn')
        await page.wait_for_timeout(300)
        dialog_stays_open_after_failed_manual_entry = await page.locator('#scan-connect-port').count()
        print("dialog stays open when the manually-entered port also fails:", dialog_stays_open_after_failed_manual_entry == 1)
        error_shown = await page.locator('#scan-connect-status').inner_text()
        print("dialog shows an inline error naming the attempted port:", '9999' in error_shown)

        await page.click('#scan-connect-cancel-btn')
        await page.wait_for_timeout(150)
        dialog_closed_after_cancel = await page.locator('#scan-connect-port').count()
        print("Cancel closes the dialog:", dialog_closed_after_cancel == 0)

        # === Scenario 2d: clicking Cancel while a port probe is still in
        # flight prevents that probe from silently saving a URL or starting
        # a scan once it resolves ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_no_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => { throw new TypeError('Failed to fetch'); };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.__RESOLVE_SLOW_PROBE = null;
                window.fetch = async (url, opts) => new Promise((resolve) => {
                    window.__RESOLVE_SLOW_PROBE = () => resolve(new Response(JSON.stringify({service: 'scanix500-bridge'}), {status: 200}));
                });
            }
        """)
        await page.fill('#scan-connect-port', '9999')
        await page.click('#scan-connect-submit-btn')
        await page.wait_for_timeout(150)  # probe is now in flight, not yet resolved
        await page.click('#scan-connect-cancel-btn')
        await page.wait_for_timeout(150)
        dialog_closed_after_cancel_mid_probe = await page.locator('#scan-connect-port').count()
        print("dialog closes immediately on Cancel, even mid-probe:", dialog_closed_after_cancel_mid_probe == 0)
        await page.evaluate("window.__RESOLVE_SLOW_PROBE()")
        await page.wait_for_timeout(300)
        saved_url_after_cancel = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                const dbState = JSON.parse(await f.text());
                const row = dbState.settings.find(s => s.key === 'scan_bridge_url');
                return row ? row.value : null;
            })()
        """)
        print("scan_bridge_url was NOT silently saved after Cancel, even once the in-flight probe resolved successfully:", saved_url_after_cancel == None)

        # === Scenario 3 (updated): configured URL, successful scan
        # response includes a `files` array -- triggerScan() itself
        # decodes and writes the file into inbox/ (no manual pre-staging
        # needed), then the existing checkInbox()/
        # addAllInboxFilesAndShowStatus() pipeline picks it up and
        # navigates to the Inbox view ===
        # This is the first definition of seed_with_url_and_inbox_file in
        # the file (Scenarios 4-9 below all reuse this same variable) --
        # keep this definition line even though the network-failure
        # scenario further down also happens to redeclare it locally
        # there; Python allows the harmless redefinition, and this one is
        # the one that actually needs to exist for everything between
        # here and that scenario to have it in scope.
        seed_with_url_and_inbox_file = {'settings': [{'key': 'scan_bridge_url', 'value': 'http://127.0.0.1:8765'}]}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)

        await page.evaluate("""
            () => {
                window.__FETCH_URLS = [];
                window.fetch = async (url, opts) => {
                    window.__FETCH_URLS.push(url);
                    const content = btoa('scanned pdf bytes');
                    return new Response(JSON.stringify({
                        ok: true, partial: false, message: '/tmp/scans/scan_1.pdf',
                        output_paths: ['/tmp/scans/scan_1.pdf'],
                        files: [{filename: 'scan_1.pdf', content_base64: content}],
                    }), {status: 200});
                };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        fetch_url_scan = await page.evaluate("window.__FETCH_URLS[0]")
        print("Scan button POSTs with split_on_blank=false:", fetch_url_scan == f'http://127.0.0.1:8765/scan?{SCAN_URL_SUFFIX}')
        current_view_is_inbox_after_success = await page.locator('#nav-item-inbox.active').count()
        print("view navigates to Inbox after a successful scan:", current_view_is_inbox_after_success == 1)
        rows_after_success = await page.locator('#doc-tbody tr').count()
        print("the scanned file from the `files` field was ingested as a document:", rows_after_success == 1)
        buttons_reenabled_after_success = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a successful scan:", buttons_reenabled_after_success)

        # === Scenario 4 (updated): Scan Multi POSTs with split_on_blank=true,
        # a distinct query string from plain Scan ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.__FETCH_URLS = [];
                window.fetch = async (url, opts) => {
                    window.__FETCH_URLS.push(url);
                    return new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: [], files: []}), {status: 200});
                };
            }
        """)
        await page.click('#scan-multi-btn')
        await page.wait_for_timeout(300)
        fetch_url_scan_multi = await page.evaluate("window.__FETCH_URLS[0]")
        print("Scan Multi button POSTs with split_on_blank=true:", fetch_url_scan_multi == f'http://127.0.0.1:8765/scan?{SCAN_MULTI_URL_SUFFIX}')

        # === Scenario 5 (updated): partial scan (ok:false, partial:true)
        # includes a `files` entry for the usable file it did produce --
        # still runs the Inbox pipeline AND shows the bridge's own message ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                const content = btoa('partial scan pdf bytes');
                window.fetch = async (url, opts) => new Response(JSON.stringify({
                    ok: false, partial: true, message: 'Multi-feed detected at sheet 3',
                    output_paths: ['/tmp/scans/scan_2.pdf'],
                    files: [{filename: 'scan_2.pdf', content_base64: content}],
                }), {status: 200});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        view_is_inbox_after_partial = await page.locator('#nav-item-inbox.active').count()
        print("view navigates to Inbox after a partial scan (a usable file was still written):", view_is_inbox_after_partial == 1)
        rows_after_partial = await page.locator('#doc-tbody tr').count()
        print("the partial scan's usable file was ingested as a document:", rows_after_partial == 1)
        status_after_partial = await page.locator('#status').inner_text()
        print("status shows the bridge's own partial-scan message:", 'Multi-feed detected at sheet 3' in status_after_partial)

        # === Scenario 6: hard failure (ok:false, partial:false) shows the
        # bridge's own message and does NOT run the Inbox pipeline ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        # Stage a real file in inbox/ first (same as Scenario 3/5) -- without
        # this, both the before and after row counts are 0 regardless of
        # whether the Inbox pipeline correctly got skipped or wrongly ran,
        # so the assertion below couldn't actually catch a regression.
        await page.evaluate("window.__addInboxFile(window.__TEST_ROOT, 'scan3.pdf', new Uint8Array([1,2,3]));")
        rows_before_failure = await page.locator('#doc-tbody tr').count()
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Response(JSON.stringify({ok: false, partial: false, message: 'Scanner not found', output_paths: []}), {status: 200});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        status_after_failure = await page.locator('#status').inner_text()
        print("status shows the bridge's own failure message:", 'Scanner not found' in status_after_failure)
        rows_after_failure = await page.locator('#doc-tbody tr').count()
        print("no new document was added on a hard failure:", rows_after_failure == rows_before_failure)
        buttons_reenabled_after_failure = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a hard failure:", buttons_reenabled_after_failure)

        # === Scenario 7 (updated): HTTP 404 no longer means "unknown
        # profile" (there's no more profile to look up) -- it means the
        # bridge doesn't recognize this request shape at all, almost
        # certainly an outdated scanix500-menubar that predates the
        # parameterized /scan endpoint. Shows a clear status naming the
        # likely cause, re-enables both buttons, no Inbox pipeline run ===
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Response(JSON.stringify({error: 'not found'}), {status: 404});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        status_after_404 = await page.locator('#status').inner_text()
        print("status shows the bridge-outdated message on a 404:", 'scanix500-menubar' in status_after_404)
        buttons_reenabled_after_404 = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a 404:", buttons_reenabled_after_404)

        # === Scenario 7b (new): HTTP 400 (malformed/missing scan
        # parameters -- should never happen from Dossiary's own
        # correctly-built request, but is still handled defensively) shows
        # the bridge's own error message, re-enables both buttons ===
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Response(JSON.stringify({error: "missing or invalid parameter(s): skip_ocr (each must be 'true' or 'false')"}), {status: 400});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        status_after_400 = await page.locator('#status').inner_text()
        print("status shows the bridge's own error message on a 400:", 'skip_ocr' in status_after_400)
        buttons_reenabled_after_400 = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a 400:", buttons_reenabled_after_400)

        # === Scenario 8: HTTP 409 (already scanning) shows a clear status ===
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Response(JSON.stringify({error: 'a scan is already in progress'}), {status: 409});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        status_after_409 = await page.locator('#status').inner_text()
        print("status shows 'already scanning' on a 409:", len(status_after_409) > 0 and 'already' in status_after_409.lower())
        buttons_reenabled_after_409 = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a 409:", buttons_reenabled_after_409)

        # === Scenario 9 (updated): a network failure against an
        # ALREADY-configured scan_bridge_url reopens the Configure Scanner
        # Connection dialog, instead of just showing an unreachable-bridge
        # status with no recovery path ===
        seed_with_url_and_inbox_file = {'settings': [{'key': 'scan_bridge_url', 'value': 'http://127.0.0.1:8765'}]}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => { throw new TypeError('Failed to fetch'); };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        dialog_shown_after_network_failure = await page.locator('#scan-connect-port').count()
        print("configure dialog opens after a network failure against a configured URL:", dialog_shown_after_network_failure == 1)
        buttons_reenabled_after_network_failure = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a network failure:", buttons_reenabled_after_network_failure)
        await page.click('#scan-connect-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 10: both buttons are disabled while a request is in
        # flight (a slow-resolving fetch, checked mid-flight before it resolves) ===
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Promise((resolve) => {
                    window.__RESOLVE_SLOW_FETCH = () => resolve(new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: [], files: []}), {status: 200}));
                });
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(150)  # request is now in flight, not yet resolved
        buttons_disabled_mid_flight = await page.evaluate("document.getElementById('scan-btn').disabled && document.getElementById('scan-multi-btn').disabled")
        print("both buttons disabled while a scan request is in flight:", buttons_disabled_mid_flight)
        await page.evaluate("window.__RESOLVE_SLOW_FETCH()")
        await page.wait_for_timeout(200)

        # === Scenario 11: a malformed (non-JSON) response body from a
        # misconfigured scan_bridge_url is treated the same as a network
        # failure -- the try/catch around response.json() covers this, not
        # just genuine connection failures ===
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Response('not valid json', {status: 200});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        status_after_malformed = await page.locator('#status').inner_text()
        print("status names the configured URL when the bridge response is malformed:", 'http://127.0.0.1:8765' in status_after_malformed)
        buttons_reenabled_after_malformed = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a malformed response:", buttons_reenabled_after_malformed)

        # === Scenario 12: an ok:true response missing the `files` field
        # entirely (e.g. talking to an older bridge that hasn't shipped it
        # yet) is treated as a hard failure -- scanBridgeUnreachable-style
        # status, not a silent no-op, and no document is added ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        rows_before_missing_files = await page.locator('#doc-tbody tr').count()
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Response(JSON.stringify({ok: true, partial: false, message: '/tmp/scans/scan_1.pdf', output_paths: ['/tmp/scans/scan_1.pdf']}), {status: 200});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        status_after_missing_files = await page.locator('#status').inner_text()
        print("status shows the bridge-unreachable-style message when `files` is missing:", 'http://127.0.0.1:8765' in status_after_missing_files)
        rows_after_missing_files = await page.locator('#doc-tbody tr').count()
        print("no document was added when `files` is missing:", rows_after_missing_files == rows_before_missing_files)
        buttons_reenabled_after_missing_files = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a missing-files response:", buttons_reenabled_after_missing_files)

        # === Scenario 13: a file already staged in inbox/ under the same
        # name the bridge's `files` entry uses is NOT overwritten -- the
        # newly-written file gets a disambiguated name, and both end up as
        # separate documents ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("window.__addInboxFile(window.__TEST_ROOT, 'scan_1.pdf', new Uint8Array([9, 9, 9]));")
        await page.evaluate("""
            () => {
                const content = btoa('new scan bytes, different from the pre-staged file');
                window.fetch = async (url, opts) => new Response(JSON.stringify({
                    ok: true, partial: false, message: '/tmp/scans/scan_1.pdf',
                    output_paths: ['/tmp/scans/scan_1.pdf'],
                    files: [{filename: 'scan_1.pdf', content_base64: content}],
                }), {status: 200});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        rows_after_collision = await page.locator('#doc-tbody tr').count()
        print("both the pre-staged file and the newly-written file were ingested as separate documents:", rows_after_collision == 2)

        # === Scenario 14: a multi-file result (Scan Multi / split-on-blank
        # producing several PDFs) writes and ingests every file in `files`,
        # not just the first ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                const content1 = btoa('first document bytes');
                const content2 = btoa('second document bytes');
                window.fetch = async (url, opts) => new Response(JSON.stringify({
                    ok: true, partial: false, message: '2 documents',
                    output_paths: ['/tmp/scans/scan_1.pdf', '/tmp/scans/scan_2.pdf'],
                    files: [
                        {filename: 'scan_1.pdf', content_base64: content1},
                        {filename: 'scan_2.pdf', content_base64: content2},
                    ],
                }), {status: 200});
            }
        """)
        await page.click('#scan-multi-btn')
        await page.wait_for_timeout(300)
        rows_after_multi = await page.locator('#doc-tbody tr').count()
        print("both files from a multi-file scan result were ingested as separate documents:", rows_after_multi == 2)

        # === Scenario 15: a 200 response from /health that doesn't identify
        # itself as the scanix500 bridge (e.g. an unrelated local service
        # answering on the same port) is NOT adopted -- the configure
        # dialog opens instead of silently trusting it ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_no_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => {
                    if(url.endsWith('/health')) return new Response(JSON.stringify({status: 'ok'}), {status: 200});
                    return new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: [], files: []}), {status: 200});
                };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        dialog_shown_for_unidentified_service = await page.locator('#scan-connect-port').count()
        print("configure dialog opens when /health responds 200 but doesn't identify as the scanix500 bridge:", dialog_shown_for_unidentified_service == 1)
        saved_url_for_unidentified_service = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                const dbState = JSON.parse(await f.text());
                const row = dbState.settings.find(s => s.key === 'scan_bridge_url');
                return row ? row.value : null;
            })()
        """)
        print("scan_bridge_url was NOT saved for an unidentified service:", saved_url_for_unidentified_service == None)
        await page.click('#scan-connect-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 16: clicking Scan again while a scan flow is already
        # probing does not start a second, concurrent probe ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_no_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.__HEALTH_PROBE_COUNT = 0;
                window.__RESOLVE_SLOW_HEALTH = null;
                window.fetch = async (url, opts) => {
                    if(url.endsWith('/health')){
                        window.__HEALTH_PROBE_COUNT++;
                        return new Promise((resolve) => {
                            window.__RESOLVE_SLOW_HEALTH = () => resolve(new Response(JSON.stringify({service: 'scanix500-bridge'}), {status: 200}));
                        });
                    }
                    return new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: [], files: []}), {status: 200});
                };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(150)  # probe is now in flight
        await page.click('#scan-btn')
        await page.click('#scan-multi-btn')
        await page.wait_for_timeout(150)
        probe_count_mid_flight = await page.evaluate("window.__HEALTH_PROBE_COUNT")
        print("a second click while a scan flow is already probing does not start a second probe:", probe_count_mid_flight == 1)
        await page.evaluate("window.__RESOLVE_SLOW_HEALTH()")
        await page.wait_for_timeout(300)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 6: Run the test and verify it passes**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: every `print()` line shows `True`, and the final `JS ERRORS: []`
line is empty.

- [ ] **Step 7: Run the static i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: passes cleanly — confirms the 2 new keys exist in all 6
languages with identical key sets.

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_scan_bridge.py
git commit -m "feat: parameterize the scan bridge request, remove profile-name constants"
```

---

### Task 2: Documentation — CLAUDE.md and tests/CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (the "Scan / Scan Multi toolbar buttons" architecture note)
- Modify: `tests/CLAUDE.md` (the `test_scan_bridge.py` coverage paragraph)

**Interfaces:**
- Consumes: the parameterized request and updated status-handling from
  Task 1 (documentation only — no code in this task).
- Produces: nothing consumed by later tasks; this is the plan's last task.

- [ ] **Step 1: Update the bullet's opening reference**

In `CLAUDE.md`, find:

```
- **Scan / Scan Multi toolbar buttons** (`#scan-btn`/`#scan-multi-btn`,
  `triggerScan()`, `SCAN_PROFILE_NAME`/`SCAN_MULTI_PROFILE_NAME`) let a
```

Replace with:

```
- **Scan / Scan Multi toolbar buttons** (`#scan-btn`/`#scan-multi-btn`,
  `triggerScan()`) let a
```

- [ ] **Step 2: Replace the "two fixed, hardcoded profile names" paragraph**

Find this paragraph in full:

```
  **The two buttons trigger two fixed, hardcoded scanix500 profile names —
  `"Dossiary Scan"` and `"Dossiary Scan Multi"` — not anything user-
  configurable.** The person creates both profiles once, manually, in
  scanix500's own menu bar app (Add Profile…), with their destination set
  to this library's real `inbox/` folder; scanix500's own README documents
  this exact contract from its side. **Scan Multi is not "duplex" or
  "multi-page" in the legacy Mariner Paperless sense** (that app's original
  Scan/Scan Multi distinction was simplex vs. duplex, and scanix500 has no
  simplex mode — it always does ADF duplex capture with automatic blank-
  page filtering) — this feature deliberately repurposes the two-button
  layout for scanix500's own genuinely distinct capability instead:
  `split-on-blank`, letting several physical documents be fed in one ADF
  load and come back as separate PDFs.
```

Replace it with:

```
  **As of the 2026-09-16 parameterized-scan amendment, there is no more
  profile at all — Dossiary sends its scan settings directly as query
  parameters on the request** (`?skip_blank_filter=false&skip_ocr=false&split_on_blank=<isMulti>`,
  built via `URLSearchParams` in `triggerScan()`). The person no longer
  needs to manually create anything in scanix500's own menu bar app before
  either button works — see
  `docs/superpowers/specs/2026-09-16-scan-bridge-parameterized-scan-design.md`
  and `docs/superpowers/plans/2026-09-16-scan-bridge-parameterized-scan.md`
  for the full two-repo design; scanix500's own `route_scan_request()`
  builds an ephemeral, never-persisted `Profile` from these same three
  parameters rather than looking one up. `skip_blank_filter`/`skip_ocr`
  are always sent `false` — Dossiary doesn't expose them as
  user-configurable settings, matching the old profiles' own unedited
  defaults — only `split_on_blank` varies between the two buttons.
  **Scan Multi is not "duplex" or "multi-page" in the legacy Mariner
  Paperless sense** (that app's original Scan/Scan Multi distinction was
  simplex vs. duplex, and scanix500 has no simplex mode — it always does
  ADF duplex capture with automatic blank-page filtering) — this feature
  deliberately repurposes the two-button layout for scanix500's own
  genuinely distinct capability instead: `split-on-blank`, letting several
  physical documents be fed in one ADF load and come back as separate
  PDFs. **This was a breaking, non-backward-compatible wire change** — a
  `404` from the bridge no longer means "unknown profile" (there's no more
  profile to be unknown); it means the bridge doesn't recognize this
  request shape at all, most likely because it predates this amendment.
  Dossiary and scanix500 must be updated together; see scanix500's own
  README for the exact coordination note from its side.
```

- [ ] **Step 3: Update the `triggerScan(profileName)` reference**

Find:

```
  **`triggerScan(profileName)` still routes every scan through the
  existing Inbox pipeline, never a separate ingestion path — but see the
```

Replace with:

```
  **`triggerScan(isMulti)` still routes every scan through the
  existing Inbox pipeline, never a separate ingestion path — but see the
```

- [ ] **Step 4: Run the full test suite once**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: unchanged from Task 1's Step 6 (docs-only changes in this task).

- [ ] **Step 5: Update `tests/CLAUDE.md`'s `test_scan_bridge.py` paragraph**

In `tests/CLAUDE.md`, find the paragraph describing `test_scan_bridge.py`
(it begins "and the Scan/Scan Multi toolbar buttons (`test_scan_bridge.py`
— `scan_bridge_url` defaulting empty on a fresh library..." and ends
"...keeping the stub lightweight and focused on database/filesystem/Dialog
stubbing, not HTTP)."). Replace that whole paragraph with:

```
and the Scan/Scan Multi toolbar buttons (`test_scan_bridge.py` —
`scan_bridge_url` defaulting empty on a fresh library and persisting
across a reopen once configured; the auto-connect flow from the
2026-09-16 amendment — an unconfigured `scan_bridge_url` probing the
default port's `/health` endpoint and adopting it silently on success
with no dialog shown at all (Scenario 2); the "Configure Scanner
Connection" dialog opening on a default-port failure, pre-filled with
`8765`, rejecting a non-numeric port without attempting to connect,
staying open with an inline error naming the attempted port when a
manually-entered port also fails, closing and saving + proceeding with
the original scan once one succeeds, and Cancel dismissing it with no
scan ever attempted (Scenario 2b/2c) — plus Cancel clicked while a port
probe is still in-flight, confirming that in-flight probe can't silently
save a URL or start a scan once it later resolves, even successfully
(Scenario 2d); a network failure against an *already-configured* URL
reopening that same dialog instead of just showing a static
unreachable-bridge status (Scenario 9); Scan vs. Scan Multi POSTing with
distinct query strings — `split_on_blank=false` and `split_on_blank=true`
respectively, with `skip_blank_filter`/`skip_ocr` always `false` — rather
than to any profile-name path, from the 2026-09-16 parameterized-scan
amendment that removed profiles from the bridge contract entirely
(Scenario 3/4, updated); a successful scan response's `files` field
(base64-encoded file bytes) being decoded and written directly into
`inbox/` by `triggerScan()` itself, with no manual pre-staging, then
picked up by the existing `checkInbox()` pipeline and surfaced via the
Inbox nav view (Scenario 3); a partial scan result (`ok: false, partial:
true`, e.g. a multi-feed jam) still writing and ingesting its `files`
entry, but surfacing the bridge's own error message on the status line
instead of the "Added N document(s)" report — the jam warning is more
important (Scenario 5); a hard failure (`ok: false, partial: false`,
verified against a library with a real file staged in `inbox/` first, so
the "no document was added" assertion could actually fail if the Inbox
pipeline wrongly ran) showing only the bridge's error message with no
document added at all (Scenario 6, unchanged); an HTTP `404` — which, as
of the parameterized-scan amendment, means the bridge doesn't recognize
this request shape at all (most likely an outdated scanix500-menubar)
rather than "unknown profile" — showing a status naming
`scanix500-menubar` as what needs updating (Scenario 7, updated); an HTTP
`400` (malformed/missing scan parameters — should never happen from
Dossiary's own correctly-built request, but handled defensively) showing
the bridge's own error message (Scenario 7b, new); distinct, legible
status messages for 409/network-failure/malformed-JSON outcomes
(Scenarios 8, 9, 11, unchanged) — the malformed-JSON scenario feeds a
non-JSON response body through the same `try/catch` a genuinely malformed
`files` array now also hits, confirming `triggerScan()` treats both as
"the bridge answered, but not correctly" rather than "reconfigure the
port"; a missing/malformed `files` field on an otherwise-`ok` response
(an older bridge that predates this field) being a hard failure, not a
silent no-op, with no document added (Scenario 12, unchanged); a file
already staged in `inbox/` under the same name a bridge-delivered file
would use NOT being silently overwritten — both end up as separate
documents, proving the collision-avoidance logic actually renames rather
than clobbers (Scenario 13, unchanged); a multi-file result (Scan Multi /
split-on-blank producing several PDFs) writing and ingesting every file
in `files`, not just the first (Scenario 14, unchanged); a `/health`
responder that doesn't identify itself as the scanix500 bridge NOT being
silently adopted (Scenario 15, unchanged); and both buttons staying
correctly disabled throughout a request and always re-enabled via
`try/finally`, regardless of outcome, never stuck disabled (Scenario 10,
unchanged), plus a re-entrancy guard against a second click starting a
second concurrent probe (Scenario 16, unchanged). This coverage is
spread across sixteen numbered scenarios (2b/2c/2d sub-parts of Scenario
2's own auto-connect matrix, 7b a sub-part of Scenario 7's own
status-handling matrix), not one — settings persistence first (Scenario
1), then the full auto-connect matrix (Scenarios 2/2b/2c/2d), then one
scenario apiece for the button/`triggerScan()` outcome matrix, so
end-to-end confidence in the whole flow comes from that matrix as a set,
not from any single scenario. **By design, `window.fetch` is overridden
per-scenario directly in `test_scan_bridge.py` itself** rather than added
to the shared `stub_studio2.js`, since `dossiary.html` calls `fetch()` in
exactly this one feature and no other test file's app code ever touches
it — keeping the stub lightweight and focused on
database/filesystem/Dialog stubbing, not HTTP).
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "docs: document the parameterized scan bridge amendment"
```
