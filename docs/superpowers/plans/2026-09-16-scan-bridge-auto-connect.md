# Scan Bridge Auto-Connect (Dossiary side) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "must manually type `scan_bridge_url`" gate with an
auto-connect flow (probe the default port, fall back to a small manual
port-entry dialog), and make `triggerScan()` decode the scan response's new
`files` field and write the scanned bytes directly into the library's own
`inbox/` folder instead of relying on filesystem placement.

**Architecture:** Two additive changes to `dossiary.html`'s existing
Scan/Scan Multi feature. A new auto-connect layer (`probeScanBridgeHealth()`,
a small "Configure Scanner Connection" modal, and a `connectScanBridgeAndTrigger()`
coordinator) sits in front of the existing `triggerScan()`, replacing its
"show a not-configured status" branch and adding a reconnect path for a
later network failure. A second, independent change extends `triggerScan()`'s
own success/partial handling to decode each `files` entry (base64) and write
it into `inbox/` — with collision-avoidance — before the existing
`checkInbox()`/`addAllInboxFilesAndShowStatus()` pipeline runs, unchanged.

**Tech Stack:** Vanilla JS (no framework), File System Access API,
`fetch()`/`AbortController`, Playwright for tests (`tests/test_scan_bridge.py`).

## Global Constraints

- The scanix500-side bridge changes this plan depends on are already merged
  to iX500's own `main` (commit `405fa5a` in `/Users/aarneaarebye/Projects/iX500`):
  a `GET /health` endpoint returning `200` with `{"service":
  "scanix500-bridge"}`, and a `files: [{filename, content_base64}, ...]`
  field added to the existing `POST /scan/<profile-name>` response,
  alongside the pre-existing `ok`/`partial`/`message`/`output_paths` keys.
  `files` is present (possibly empty) on both `ok:true` and `ok:false,
  partial:true` responses; it is absent or malformed only when talking to
  an older bridge that predates this change.
- Full spec: `docs/superpowers/specs/2026-09-16-scan-bridge-auto-connect-design.md`.
  This plan covers only that spec's Dossiary-side pieces (auto-connect,
  `files` decode-and-write); the scanix500 side is already done.
- No per-library scanix500 profiles — the existing fixed
  `SCAN_PROFILE_NAME = 'Dossiary Scan'` / `SCAN_MULTI_PROFILE_NAME =
  'Dossiary Scan Multi'` constants are unchanged and stay unchanged by this
  plan.
- The default bridge port is `8765` (matches scanix500's own
  `DEFAULT_PORT`). The health probe uses a short client-side timeout (a
  few seconds) via `AbortController` — unlike `triggerScan()`'s own POST,
  which deliberately has no timeout (see that function's existing
  comment) and must keep that property unchanged.
- Both toolbar buttons (`#scan-btn`/`#scan-multi-btn`) must never be left
  stuck disabled, on any path, including the new auto-connect/dialog
  paths — the existing `try/finally` re-enable guarantee in `triggerScan()`
  must be preserved.
- The existing Field Settings `#fs-scan-bridge-url` text field
  (`openFieldSettingsModal()`, `dossiary.html:6703-6704` and
  `:6738`) stays exactly as-is, unchanged, as a manual override — this
  plan does not touch it.
- The existing `scanBridgeNotConfigured` i18n key (referenced in
  `dossiary.html:7774` prior to this plan) becomes unreferenced once
  Task 1 lands, since an unconfigured `scan_bridge_url` now always
  attempts an auto-connect probe rather than showing a static status.
  Leave the key (and its 6 translations) in place, unused — removing an
  already-translated key from all 6 `STRINGS` blocks is out of scope for
  this plan and not required for correctness (`test_i18n_coverage.py`
  only checks that *referenced* keys have translations, not that every
  key is referenced).
- Follow `tests/CLAUDE.md`'s conventions exactly: standalone print-based
  Playwright scripts, `tests/stub_studio2.js` for the shared FSA/DB stub
  (never a new embedded copy), and `window.fetch` stubbed per-scenario
  directly inside `tests/test_scan_bridge.py` itself (not added to
  `stub_studio2.js`) — this is the one feature in the app that calls
  `fetch()`. Update the file's own paragraph in `tests/CLAUDE.md`
  describing `test_scan_bridge.py`'s scenarios in the same change that
  changes those scenarios, per that file's own explicit "don't let this
  description silently drift" instruction.

---

### Task 1: Auto-connect flow — health probe, dialog, and reconnect-on-failure

**Files:**
- Modify: `dossiary.html:7761-7826` (insert new constants/functions before
  `triggerScan()`, and modify `triggerScan()`'s unconfigured-branch and
  fetch-failure handling)
- Modify: `dossiary.html` `STRINGS.en`/`STRINGS.es`/`STRINGS.fr`/
  `STRINGS.de`/`STRINGS['zh-Hans']`/`STRINGS['zh-Hant']` blocks (new i18n
  keys, inserted after each block's existing `scanFailedMessage:` line —
  `en` at `:1027`, `es` at `:1208`, `fr` at `:1389`, `de` at `:1570`,
  `zh-Hans` at `:1751`, `zh-Hant` at `:2055`)
- Test: `tests/test_scan_bridge.py`

**Interfaces:**
- Consumes: `scanBridgeUrl` (module-level var), `loadScanBridgeUrl()`/
  `saveScanBridgeUrl(value)` (both already shipped, unchanged), `t(key,
  params)`, `setStatusT(key, params, statusClass)`, `el(id)`, `modalRoot`,
  `closeModal()`, `onModalKeydown(e)` (all already shipped, unchanged).
- Produces: `probeScanBridgeHealth(url) -> Promise<boolean>`,
  `connectScanBridgeAndTrigger(profileName) -> Promise<void>`,
  `openScanConnectDialog(profileName) -> void`,
  `submitScanConnectDialog(profileName) -> Promise<void>` — Task 2 does
  not call any of these directly, but relies on `triggerScan()`'s
  unchanged-by-Task-2 unconfigured/network-failure branches, which this
  task establishes.

- [ ] **Step 1: Add the 7 new i18n keys to all 6 `STRINGS` blocks**

In `STRINGS.en`, immediately after the line
`scanFailedMessage: 'Scan failed: {message}',` (currently `dossiary.html:1027`),
insert:

```javascript
      scanConnectTitle: 'Connect to Scanner',
      scanConnectInstructions: "Couldn't reach the scanner bridge on the default port. Check scanix500-menubar's own menu for its current port, then enter it below.",
      scanConnectPortLabel: 'Port',
      scanConnectSubmit: 'Connect',
      scanConnectInvalidPort: 'Enter a valid port number.',
      scanConnectProbing: 'Connecting…',
      scanConnectFailed: "Couldn't reach a scanner bridge at {url}.",
```

In `STRINGS.es`, immediately after that block's own
`scanFailedMessage: 'Error al escanear: {message}',` (currently
`dossiary.html:1208`), insert:

```javascript
      scanConnectTitle: 'Conectar con el escáner',
      scanConnectInstructions: 'No se pudo conectar con el puente del escáner en el puerto predeterminado. Consulte el puerto actual en el propio menú de scanix500-menubar e introdúzcalo a continuación.',
      scanConnectPortLabel: 'Puerto',
      scanConnectSubmit: 'Conectar',
      scanConnectInvalidPort: 'Introduzca un número de puerto válido.',
      scanConnectProbing: 'Conectando…',
      scanConnectFailed: 'No se pudo conectar con un puente del escáner en {url}.',
```

In `STRINGS.fr`, immediately after that block's own
`scanFailedMessage: 'Échec de la numérisation : {message}',` (currently
`dossiary.html:1389`), insert:

```javascript
      scanConnectTitle: 'Connexion au scanner',
      scanConnectInstructions: "Impossible de joindre le pont du scanner sur le port par défaut. Consultez le port actuel dans le menu de scanix500-menubar, puis saisissez-le ci-dessous.",
      scanConnectPortLabel: 'Port',
      scanConnectSubmit: 'Connecter',
      scanConnectInvalidPort: 'Saisissez un numéro de port valide.',
      scanConnectProbing: 'Connexion en cours…',
      scanConnectFailed: 'Impossible de joindre un pont du scanner à {url}.',
```

In `STRINGS.de`, immediately after that block's own
`scanFailedMessage: 'Scan fehlgeschlagen: {message}',` (currently
`dossiary.html:1570`), insert:

```javascript
      scanConnectTitle: 'Mit Scanner verbinden',
      scanConnectInstructions: 'Die Scanner-Bridge konnte auf dem Standardport nicht erreicht werden. Den aktuellen Port im Menü von scanix500-menubar nachsehen und unten eingeben.',
      scanConnectPortLabel: 'Port',
      scanConnectSubmit: 'Verbinden',
      scanConnectInvalidPort: 'Bitte eine gültige Portnummer eingeben.',
      scanConnectProbing: 'Verbindung wird hergestellt…',
      scanConnectFailed: 'Es konnte keine Scanner-Bridge unter {url} erreicht werden.',
```

In `STRINGS['zh-Hans']`, immediately after that block's own
`scanFailedMessage: '扫描失败：{message}',` (currently `dossiary.html:1751`),
insert:

```javascript
      scanConnectTitle: '连接扫描仪',
      scanConnectInstructions: '无法在默认端口连接到扫描桥接。请在 scanix500-menubar 的菜单中查看当前端口，然后在下方输入。',
      scanConnectPortLabel: '端口',
      scanConnectSubmit: '连接',
      scanConnectInvalidPort: '请输入有效的端口号。',
      scanConnectProbing: '正在连接…',
      scanConnectFailed: '无法连接到 {url} 的扫描桥接。',
```

In `STRINGS['zh-Hant']`, immediately after that block's own
`scanFailedMessage: '掃描失敗：{message}',` (currently `dossiary.html:2055`),
insert (a straight script conversion of the zh-Hans block above, matching
this repo's own established zh-Hant derivation convention — same wording,
traditional character forms only):

```javascript
      scanConnectTitle: '連接掃描儀',
      scanConnectInstructions: '無法在默認端口連接到掃描橋接。請在 scanix500-menubar 的菜單中查看當前端口，然後在下方輸入。',
      scanConnectPortLabel: '端口',
      scanConnectSubmit: '連接',
      scanConnectInvalidPort: '請輸入有效的端口號。',
      scanConnectProbing: '正在連接…',
      scanConnectFailed: '無法連接到 {url} 的掃描橋接。',
```

- [ ] **Step 2: Add the auto-connect functions and the dialog**

In `dossiary.html`, immediately before the line
`const SCAN_PROFILE_NAME = 'Dossiary Scan';` (currently `dossiary.html:7761`),
insert:

```javascript
  const SCAN_BRIDGE_DEFAULT_PORT = 8765;
  const SCAN_BRIDGE_HEALTH_TIMEOUT_MS = 3000;

  // Probes GET <url>/health with a short client-side timeout -- unlike
  // triggerScan()'s own deliberately-un-timed-out POST /scan/<profile>
  // (see that function's own comment below), this is a pure reachability
  // check and should fail fast rather than hang the auto-connect flow.
  async function probeScanBridgeHealth(url){
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), SCAN_BRIDGE_HEALTH_TIMEOUT_MS);
    try{
      const response = await fetch(`${url}/health`, { method: 'GET', signal: controller.signal });
      return response.ok;
    }catch(e){
      return false;
    }finally{
      clearTimeout(timeoutId);
    }
  }

  // Called when scanBridgeUrl is unset: tries the default port silently
  // first -- no dialog shown at all on success, the person's first click
  // just works -- falling back to the manual "Configure Scanner
  // Connection" dialog only if that fails.
  async function connectScanBridgeAndTrigger(profileName){
    const defaultUrl = `http://localhost:${SCAN_BRIDGE_DEFAULT_PORT}`;
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
    await saveScanBridgeUrl(url);
    closeModal();
    await triggerScan(profileName);
  }

```

- [ ] **Step 3: Wire `triggerScan()`'s unconfigured branch and fetch-failure branch**

Replace the current `triggerScan()` function body (currently
`dossiary.html:7773-7813`) with:

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
      if(result.ok){
        await checkInbox();
        await addAllInboxFilesAndShowStatus();
        return;
      }
      if(result.partial){
        // A partial scan (e.g. a multi-feed jam) still wrote a usable file --
        // run the Inbox pipeline same as a full success, but the bridge's own
        // message (naming what went wrong) is more important than the Inbox
        // pipeline's own "Added N document(s)" report, so it's shown last,
        // deliberately overwriting that report as the final status line.
        await checkInbox();
        await addAllInboxFilesAndShowStatus();
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

(This step is scoped to Task 1's own concern only: the unconfigured branch
and the fetch-failure branch. The `result.ok`/`result.partial` bodies
above are unchanged from today — Task 2 modifies them.)

- [ ] **Step 4: Update `tests/test_scan_bridge.py`'s Scenario 2**

Replace the existing "=== Scenario 2 ===" block (unconfigured
`scan_bridge_url` shows "not configured" with no fetch attempted) with:

```python
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
        print("the original scan proceeded after connecting:", any(u == 'http://localhost:9999/scan/Dossiary%20Scan' for u in fetch_calls_2b))

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
```

- [ ] **Step 5: Update `tests/test_scan_bridge.py`'s Scenario 9**

Replace the existing "=== Scenario 9 ===" block (network failure shows a
status naming the URL) with:

```python
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
```

Note: `seed_with_url_and_inbox_file` is already defined by the time the
script reaches the original Scenario 3 earlier in the file — this
replacement redeclares it locally right before use so Scenario 9 doesn't
depend on Task 2's own edits to Scenario 3 having landed in the same run;
harmless to redeclare the same dict twice in one script.

- [ ] **Step 6: Run the test and verify it passes**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: every `print()` line shows `True`, and the final `JS ERRORS: []`
line is empty. (Scenarios 3-8, 10-11 are unchanged by this task and should
still pass exactly as before.)

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_scan_bridge.py
git commit -m "feat: auto-connect the scan bridge (health probe + configure dialog)"
```

---

### Task 2: Decode and write the `files` field into `inbox/`

**Files:**
- Modify: `dossiary.html` (insert two new functions before `triggerScan()`,
  modify `triggerScan()`'s `result.ok`/`result.partial` handling)
- Test: `tests/test_scan_bridge.py`

**Interfaces:**
- Consumes: `rootDirHandle` (module-level, already shipped), `safeFilename(name,
  fallback)` (already shipped, `dossiary.html:2597`), `checkInbox()`/
  `addAllInboxFilesAndShowStatus()` (already shipped, unchanged), the
  response's `files: [{filename, content_base64}, ...]` array (from the
  now-merged scanix500 bridge).
- Produces: `uniqueInboxFilename(dirHandle, name) -> Promise<string>`,
  `writeScanFilesToInbox(files) -> Promise<void>` — neither is consumed by
  any other task in this plan; both are called only from `triggerScan()`.

- [ ] **Step 1: Add `uniqueInboxFilename()` and `writeScanFilesToInbox()`**

In `dossiary.html`, immediately before the `async function triggerScan(profileName){`
line (unchanged in position by Task 1 — it still directly follows the
pre-existing "Triggers a real scan via the scanix500 HTTP bridge..."
comment block), insert:

```javascript
  // Finds a filename inside dirHandle that doesn't already exist, so
  // writing a bridge-delivered scan into inbox/ never silently overwrites
  // an unrelated file already staged there (a manually dropped file, or a
  // previous scan's own output that hasn't been ingested yet). Not
  // atomic against a concurrent writer -- matches this app's existing
  // single-writer, single-tab concurrency assumption (see the Tag
  // dedup note elsewhere in this file's own architecture notes).
  async function uniqueInboxFilename(dirHandle, name){
    const dot = name.lastIndexOf('.');
    const base = dot > 0 ? name.slice(0, dot) : name;
    const ext = dot > 0 ? name.slice(dot) : '';
    let candidate = name;
    let n = 1;
    while(true){
      try{
        await dirHandle.getFileHandle(candidate, { create: false });
      }catch(e){
        return candidate; // NotFoundError -- this name is free
      }
      candidate = `${base} (${n})${ext}`;
      n++;
    }
  }

  // Decodes and writes every entry in a scan response's `files` array into
  // the library's own inbox/ folder, so the existing checkInbox()/
  // addAllInboxFilesAndShowStatus() pipeline picks them up exactly like
  // any other staged file -- no separate ingestion path. Throws on any
  // malformed entry or write failure; triggerScan()'s own catch block
  // turns that into the existing scanBridgeUnreachable-style status
  // message, the same as a malformed JSON response already does.
  async function writeScanFilesToInbox(files){
    const dirHandle = await rootDirHandle.getDirectoryHandle('inbox', { create: true });
    for(const entry of files){
      if(!entry || typeof entry.filename !== 'string' || typeof entry.content_base64 !== 'string'){
        throw new Error('malformed files entry from scan bridge');
      }
      const bytes = Uint8Array.from(atob(entry.content_base64), c => c.charCodeAt(0));
      const name = safeFilename(entry.filename, 'scan.pdf');
      const uniqueName = await uniqueInboxFilename(dirHandle, name);
      const fileHandle = await dirHandle.getFileHandle(uniqueName, { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(bytes);
      await writable.close();
    }
  }

```

- [ ] **Step 2: Wire the decode-and-write step into `triggerScan()`**

In `triggerScan()` (as left by Task 1), replace this block:

```javascript
      if(result.ok){
        await checkInbox();
        await addAllInboxFilesAndShowStatus();
        return;
      }
      if(result.partial){
        // A partial scan (e.g. a multi-feed jam) still wrote a usable file --
        // run the Inbox pipeline same as a full success, but the bridge's own
        // message (naming what went wrong) is more important than the Inbox
        // pipeline's own "Added N document(s)" report, so it's shown last,
        // deliberately overwriting that report as the final status line.
        await checkInbox();
        await addAllInboxFilesAndShowStatus();
        setStatusT('scanPartialMessage', {message: result.message || String(response.status)}, 'err');
        return;
      }
```

with:

```javascript
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
```

- [ ] **Step 3: Update `tests/test_scan_bridge.py`'s Scenario 3**

Replace the existing "=== Scenario 3 ===" block with:

```python
        # === Scenario 3 (updated): configured URL, successful scan
        # response includes a `files` array -- triggerScan() itself
        # decodes and writes the file into inbox/ (no manual pre-staging
        # needed), then the existing checkInbox()/
        # addAllInboxFilesAndShowStatus() pipeline picks it up and
        # navigates to the Inbox view ===
        # This is the first definition of seed_with_url_and_inbox_file in
        # the file (Scenarios 4-9 below all reuse this same variable) --
        # keep this definition line even though Task 1's own Scenario 9
        # replacement also happens to redeclare it locally there; Python
        # allows the harmless redefinition, and this one is the one that
        # actually needs to exist for everything between here and Scenario
        # 9 to have it in scope.
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
        print("Scan button POSTs to the 'Dossiary Scan' profile path:", fetch_url_scan == 'http://127.0.0.1:8765/scan/Dossiary%20Scan')
        current_view_is_inbox_after_success = await page.locator('#nav-item-inbox.active').count()
        print("view navigates to Inbox after a successful scan:", current_view_is_inbox_after_success == 1)
        rows_after_success = await page.locator('#doc-tbody tr').count()
        print("the scanned file from the `files` field was ingested as a document:", rows_after_success == 1)
        buttons_reenabled_after_success = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a successful scan:", buttons_reenabled_after_success)
```

- [ ] **Step 4: Update `tests/test_scan_bridge.py`'s Scenario 4**

Replace the existing "=== Scenario 4 ===" block's mocked `fetch` response
body from `{ok: true, partial: false, message: 'ok', output_paths: []}`
to include an explicit (empty) `files` array:

```python
        await page.evaluate("""
            () => {
                window.__FETCH_URLS = [];
                window.fetch = async (url, opts) => {
                    window.__FETCH_URLS.push(url);
                    return new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: [], files: []}), {status: 200});
                };
            }
        """)
```

(The rest of Scenario 4 — clicking `#scan-multi-btn` and asserting the
fetched URL — is unchanged. Without this `files: []` addition, Task 2's
own new "missing files is a hard failure" check would make this scenario
fail once Step 2 above lands.)

- [ ] **Step 5: Update `tests/test_scan_bridge.py`'s Scenario 5**

Replace the existing "=== Scenario 5 ===" block (partial scan) with:

```python
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
```

(Scenarios 6, 7, 8, 10, and 11 are unchanged by this task — leave them
exactly as they are. Scenario 6's hard-failure path never reaches the
`files` check at all, since it returns from the `ok:false, partial:false`
branch before that code runs.)

- [ ] **Step 6: Add three new scenarios at the end of the file**

Immediately before the line `print("JS ERRORS:", errors)`, insert:

```python
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

```

- [ ] **Step 7: Run the test and verify it passes**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: every `print()` line shows `True`, and the final `JS ERRORS: []`
line is empty.

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_scan_bridge.py
git commit -m "feat: decode and write the scan bridge's files field into inbox/"
```

---

### Task 3: Documentation — CLAUDE.md and tests/CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (the "Scan / Scan Multi toolbar buttons" architecture
  note)
- Modify: `tests/CLAUDE.md` (the `test_scan_bridge.py` coverage paragraph)

**Interfaces:**
- Consumes: the auto-connect flow and `files` decode-and-write behavior
  from Tasks 1-2 (documentation only — no code in this task).
- Produces: nothing consumed by later tasks; this is the plan's last task.

- [ ] **Step 1: Correct the now-inaccurate `scan_bridge_url` sentence in CLAUDE.md**

In `CLAUDE.md`, inside the "Scan / Scan Multi toolbar buttons" bullet,
find this sentence:

```
  **`scan_bridge_url`** (a `settings` row, `loadScanBridgeUrl()`/
  `saveScanBridgeUrl()`, configured via a new Field Settings text field) is
  the bridge's base URL — unset by default, in which case both buttons show
  a "not configured" status with no network request attempted at all.
```

Replace it with:

```
  **`scan_bridge_url`** (a `settings` row, `loadScanBridgeUrl()`/
  `saveScanBridgeUrl()`) is the bridge's base URL. As of the 2026-09-16
  auto-connect amendment (see
  `docs/superpowers/specs/2026-09-16-scan-bridge-auto-connect-design.md`
  and `docs/superpowers/plans/2026-09-16-scan-bridge-auto-connect.md`),
  it's no longer purely manual — see the auto-connect paragraph below for
  how it gets set without typing anything, in the common case. The Field
  Settings text field (`#fs-scan-bridge-url`) still exists as a manual
  override/escape hatch, unchanged.
```

- [ ] **Step 2: Correct the "never invents a new document-ingestion path" claim**

In `CLAUDE.md`, in the same bullet, find this sentence:

```
  **`triggerScan(profileName)` never invents a new document-ingestion
  path** — scanix500 already writes the finished PDF directly into the
  profile's configured destination folder (the library's `inbox/`), so a
  successful (`ok: true`) response just calls the *existing*
  `checkInbox()`/`addAllInboxFilesAndShowStatus()` pair verbatim, the same
  call the "Check inbox" button already makes — there is no separate
  Scan-specific way a document lands in the library.
```

Replace it with:

```
  **`triggerScan(profileName)` still routes every scan through the
  existing Inbox pipeline, never a separate ingestion path — but see the
  auto-connect paragraph below for a real change to how the file gets
  there.** As of the 2026-09-16 amendment, Dossiary itself decodes the
  response's `files` field and writes the bytes into the library's own
  `inbox/` folder (scanix500 no longer needs to write to a location
  Dossiary can read at all), and only *then* calls the same
  `checkInbox()`/`addAllInboxFilesAndShowStatus()` pair as before — so a
  scan still always lands exactly like any other Inbox-staged file, just
  via a different placement mechanism now.
```

- [ ] **Step 3: Append a new paragraph documenting the amendment**

In `CLAUDE.md`, immediately after the "Scan / Scan Multi toolbar buttons"
bullet's existing final paragraph (the one ending "...boundary given that
a successful scan's own follow-up work has nowhere else convenient to
run."), append a new paragraph, still part of the same bullet (same
indentation, no blank line before it):

```
  **Auto-connect (2026-09-16 amendment)**: the "must manually type
  `scan_bridge_url` before either button works" gate is gone. Clicking
  Scan or Scan Multi with no stored `scan_bridge_url` now probes
  `GET http://localhost:8765/health` first (`probeScanBridgeHealth()`, a
  short client-side `AbortController` timeout — unlike `triggerScan()`'s
  own deliberately un-timed-out POST) — a reachable default port is
  adopted silently, no dialog shown, and the originally-clicked scan
  proceeds immediately. An unreachable default port opens a small
  "Configure Scanner Connection" dialog (`openScanConnectDialog()`/
  `submitScanConnectDialog()`) with one Port field; a later scan against
  an already-configured URL that fails at the network level (not a 404/409
  from a reachable bridge) reopens the same dialog rather than just
  showing an unreachable-bridge status with no recovery path. The
  pre-existing Field Settings `scan_bridge_url` text field is untouched
  and still works as a manual override. **The scanned file itself now
  travels over the connection, not the filesystem**: `triggerScan()`
  decodes every entry in the response's `files` array (base64) and writes
  it into the library's own `inbox/` via `writeScanFilesToInbox()`, with
  `uniqueInboxFilename()` guarding against overwriting an unrelated
  same-named file already staged there, before running the unchanged
  `checkInbox()`/`addAllInboxFilesAndShowStatus()` pipeline. A
  missing/malformed `files` array on an otherwise-`ok` response (an older
  bridge that predates this change) is a hard failure, not a silent
  no-op — it falls into the same `scanBridgeUnreachable`-style catch a
  malformed JSON response already used. One consequence worth stating
  plainly: a scanix500 profile's `destination` folder no longer needs to
  point at any specific Dossiary library's `inbox/` — it's now purely a
  local safety-net copy on the scanix500 side (see that repo's own
  README). Per-library scanix500 profiles were considered during this
  amendment's design and explicitly rejected for the same reason: once the
  file arrives over the connection, scanix500 never needs to know which
  library it's serving.
```

- [ ] **Step 4: Update `tests/CLAUDE.md`'s `test_scan_bridge.py` paragraph**

In `tests/CLAUDE.md`, find the paragraph describing `test_scan_bridge.py`
(it begins "and the Scan/Scan Multi toolbar buttons (`test_scan_bridge.py`
— `scan_bridge_url` defaulting empty on a fresh library..." and ends
"...keeping the stub lightweight and focused on database/filesystem/Dialog
stubbing, not HTTP)."). Replace that whole paragraph with:

```
and the Scan/Scan Multi toolbar buttons (`test_scan_bridge.py` —
`scan_bridge_url` defaulting empty on a fresh library and persisting
across a reopen once configured; the auto-connect flow added in the
2026-09-16 amendment — an unconfigured `scan_bridge_url` probing the
default port's `/health` endpoint and adopting it silently on success with
no dialog shown at all (Scenario 2); the "Configure Scanner Connection"
dialog opening on a default-port failure, pre-filled with `8765`,
rejecting a non-numeric port without attempting to connect, staying open
with an inline error naming the attempted port when a manually-entered
port also fails, closing and saving + proceeding with the original scan
once one succeeds, and Cancel dismissing it with no scan ever attempted
(Scenario 2b/2c); a network failure against an *already-configured* URL
reopening that same dialog instead of just showing a static
unreachable-bridge status (Scenario 9, replacing its own earlier,
now-superseded "just show a status" version) — Scan vs. Scan Multi
POSTing to their own distinct, hardcoded profile-name endpoints
(`Dossiary Scan` and `Dossiary Scan Multi`, Scenario 4); a successful scan
response's `files` field (base64-encoded file bytes) being decoded and
written directly into `inbox/` by `triggerScan()` itself, with no manual
pre-staging, then picked up by the existing `checkInbox()` pipeline and
surfaced via the Inbox nav view (Scenario 3); a partial scan result
(`ok: false, partial: true`, e.g. a multi-feed jam) still writing and
ingesting its `files` entry, but surfacing the bridge's own error message
on the status line instead of the "Added N document(s)" report — the jam
warning is more important (Scenario 5); a hard failure (`ok: false,
partial: false`, verified against a library with a real file staged in
`inbox/` first, so the "no document was added" assertion could actually
fail if the Inbox pipeline wrongly ran) showing only the bridge's error
message with no document added at all (Scenario 6, unchanged); distinct,
legible status messages for 404/409/network-failure/malformed-JSON
outcomes (Scenarios 7, 8, 11, unchanged) — the malformed-JSON scenario
feeds a non-JSON response body through the same `try/catch` a genuinely
malformed `files` array now also hits, confirming `triggerScan()` treats
both as "the bridge answered, but not correctly" rather than "reconfigure
the port"; a missing/malformed `files` field on an otherwise-`ok` response
(an older bridge that predates this field) being a hard failure, not a
silent no-op, with no document added (Scenario 12, new); a file already
staged in `inbox/` under the same name a bridge-delivered file would use
NOT being silently overwritten — both end up as separate documents,
proving the new collision-avoidance logic actually renames rather than
clobbers (Scenario 13, new); a multi-file result (Scan Multi /
split-on-blank producing several PDFs) writing and ingesting every file in
`files`, not just the first (Scenario 14, new); and both buttons staying
correctly disabled throughout a request and always re-enabled via
`try/finally`, regardless of outcome, never stuck disabled (Scenario 10,
unchanged). This coverage is spread across fourteen scenarios (2 and 9
replaced from the original eleven, three appended), not one — settings
persistence first (Scenario 1), then the full auto-connect matrix
(Scenarios 2/2b/2c), then one scenario apiece for the button/`triggerScan()`
outcome matrix, so end-to-end confidence in the whole flow comes from that
matrix as a set, not from any single scenario. **By design, `window.fetch`
is overridden per-scenario directly in `test_scan_bridge.py` itself**
rather than added to the shared `stub_studio2.js`, since `dossiary.html`
calls `fetch()` in exactly this one feature and no other test file's app
code ever touches it — keeping the stub lightweight and focused on
database/filesystem/Dialog stubbing, not HTTP).
```

- [ ] **Step 5: Run the full test suite once**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: unchanged from Task 2's Step 7 (docs-only changes in this task).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "docs: document the scan bridge auto-connect amendment"
```
