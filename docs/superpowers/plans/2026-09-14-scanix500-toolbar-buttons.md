# Scan / Scan Multi Toolbar Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Scan" and "Scan Multi" toolbar buttons to Dossiary that trigger a real scan via the already-completed scanix500 HTTP bridge (a separate repo, `AarneAarebye/iX500`, merged and working) and pull the result into the library through the existing Inbox pipeline.

**Architecture:** A new per-library `scan_bridge_url` setting (configured in Field Settings) stores the bridge's base URL. Two toolbar buttons call a shared `triggerScan(profileName)` function that POSTs to `${scanBridgeUrl}/scan/<fixed-profile-name>`, and on success calls the *existing* `checkInbox()`/`addAllInboxFilesAndShowStatus()` pair verbatim — no new document-ingestion code, since scanix500 already writes the finished PDF directly into the library's `inbox/` folder.

**Tech Stack:** Plain JS (`dossiary.html`), no new dependency — `fetch()` is a standard browser API already available in every browser this app targets.

## Global Constraints

- Fixed, hardcoded profile-name contract with the (already-shipped) scanix500 bridge: `"Dossiary Scan"` and `"Dossiary Scan Multi"` — not user-configurable, not derived from any setting.
- `scan_bridge_url` follows the exact `default_currency` settings pattern: a `settings` table row, `loadScanBridgeUrl()`/`saveScanBridgeUrl()`, loaded in `loadDocumentsFromDb()`, reset in `resetAll()`.
- On success (`ok:true`), `triggerScan()` calls the existing `checkInbox()` + `addAllInboxFilesAndShowStatus()` pair — do not duplicate their logic or write a parallel document-ingestion path.
- `triggerScan()` must re-enable both buttons in every outcome, including thrown exceptions (network failure, malformed JSON) — use `try/finally`, not scattered re-enable calls on each branch, to avoid ever leaving a button stuck disabled.
- Every new user-facing string needs all six `STRINGS` blocks (`en`, `de`, `es`, `fr`, `zh-Hans`, `zh-Hant`) — `zh-Hant` is derived from the finished `zh-Hans` wording via a real OpenCC `s2t` run (Task 2's own step gives the exact commands), never hand-guessed.
- Two more toolbar buttons are exactly the class of change that has broken `.table-wrap`'s sticky-header `max-height` calibration before (the reminders feature's own "🔔 Check reminders" button did the same) — Task 3 re-verifies this empirically via `tests/test_footer_pin.py`, never by assuming the existing constants still hold.
- Tests are standalone, print-based Playwright scripts (`cd tests && python3 test_<name>.py`) — no `assert`, no pytest, no exit-code-based pass/fail; each check prints a label and a boolean/value, and a human (or reviewer) reads the output alongside the final `print("JS ERRORS:", errors)` line. Follow this repo's existing test files' exact style.

---

### Task 1: `scan_bridge_url` setting + Field Settings UI field

**Files:**
- Modify: `dossiary.html`
- Test: `tests/test_scan_bridge.py` (new file — this task adds its first scenario; Task 2 extends it)

**Interfaces:**
- Produces: module-level `let scanBridgeUrl = null;`. `function loadScanBridgeUrl()` (reads `settings` table, sets `scanBridgeUrl`). `async function saveScanBridgeUrl(value)` (trims, persists, updates `scanBridgeUrl`). Both consumed by Task 2's `triggerScan()`.
- Consumes: existing `queryAll()`, `db.run()`, `persistDb()`, `escapeHtml()`, `t()` helpers (all already defined elsewhere in `dossiary.html`, no new signatures).

- [ ] **Step 1: Write the failing test**

Create `tests/test_scan_bridge.py`:

```python
import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

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

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 2: Run the test to confirm it fails for the right reason**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: `Scanner bridge URL field present in Field Settings: False` (the `#fs-scan-bridge-url` element doesn't exist yet) — everything after that line will also print wrong/blank values as a consequence, which is expected until Step 3 lands.

- [ ] **Step 3: Add the setting variable, load/save functions, and wiring**

In `dossiary.html`, add the new module-level variable right after the existing `reminderLookaheadDays` declaration (around line 2312, inside the same block as `defaultCurrency`/`defaultDocumentType`):

```js
  let scanBridgeUrl = null; // base URL of the scanix500 HTTP bridge (e.g. "http://127.0.0.1:8765"), configured per-library; unset means the Scan/Scan Multi buttons show a "not configured" status instead of attempting a request
```

Add `scanBridgeUrl = null;` to the existing reset line in `resetAll()` (currently `defaultDocumentType = null; defaultCurrency = null; fsSelectedType = null; reminderLookaheadDays = 30;`, around line 3061) so it reads:

```js
    defaultDocumentType = null; defaultCurrency = null; fsSelectedType = null; reminderLookaheadDays = 30; scanBridgeUrl = null;
```

Add the load/save functions right after `saveReminderLookaheadDays()` (currently ends around line 3273), following `loadDefaultCurrency()`/`saveDefaultCurrency()`'s exact pattern (empty string persisted as `''`, read back as `null` when absent):

```js
  // Base URL of the scanix500 HTTP bridge (see the "Reminder-type custom
  // fields" and "The default-reminder context menu" architecture notes above
  // for the general pattern this follows) -- a per-library settings row,
  // same as default_currency. Unset until someone configures it; the
  // Scan/Scan Multi toolbar buttons check this before attempting a request.
  function loadScanBridgeUrl(){
    const rows = queryAll("SELECT value FROM settings WHERE key = 'scan_bridge_url'").rows;
    scanBridgeUrl = rows.length ? rows[0][0] : null;
  }

  async function saveScanBridgeUrl(value){
    scanBridgeUrl = value.trim() || null;
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('scan_bridge_url', ?)", [scanBridgeUrl || '']);
    await persistDb();
  }
```

Wire `loadScanBridgeUrl()` into `loadDocumentsFromDb()` right after the existing `loadReminderLookaheadDays();` call (around line 3192), so the block reads:

```js
    loadColumnSettings();
    loadDefaultDocumentType();
    loadDefaultCurrency();
    loadReminderLookaheadDays();
    loadScanBridgeUrl();
    loadNavStyle();
```

- [ ] **Step 4: Add the Field Settings UI field**

In `openFieldSettingsModal()`'s template string, add a fourth `.field` div inside the existing `.field-row` (currently three fields: `fs-default-type`, `fs-default-currency`, `fs-reminder-lookahead`, ending around line 6633), right after the `fs-reminder-lookahead` field:

```js
            <div class="field">
              <label for="fs-scan-bridge-url">${t('fieldSettingsScanBridgeUrlLabel')}</label>
              <input type="text" id="fs-scan-bridge-url" value="${escapeHtml(scanBridgeUrl || '')}" placeholder="http://127.0.0.1:8765" />
            </div>
```

Add the change-handler wiring right after the existing `el('fs-reminder-lookahead').addEventListener(...)` line (around line 6665):

```js
    el('fs-scan-bridge-url').addEventListener('change', (e) => saveScanBridgeUrl(e.target.value));
```

- [ ] **Step 5: Add the i18n key across all six `STRINGS` blocks**

Add `fieldSettingsScanBridgeUrlLabel` right after each language's existing `fieldSettingsReminderLookaheadLabel` key (same line, or the next line — follow whatever that language block's existing formatting looks like at that spot):

`STRINGS.en` (after line 984):
```js
      fieldSettingsScanBridgeUrlLabel: 'Scanner bridge URL (e.g. http://127.0.0.1:8765)',
```

`STRINGS.es` (after line 1157):
```js
      fieldSettingsScanBridgeUrlLabel: 'URL del puente del escáner (p. ej. http://127.0.0.1:8765)',
```

`STRINGS.fr` (after line 1330):
```js
      fieldSettingsScanBridgeUrlLabel: 'URL du pont du scanner (p. ex. http://127.0.0.1:8765)',
```

`STRINGS.de` (after line 1503):
```js
      fieldSettingsScanBridgeUrlLabel: 'Scanner-Bridge-URL (z. B. http://127.0.0.1:8765)',
```

`STRINGS['zh-Hans']` (after line 1676, i.e. right after `fieldSettingsReminderLookaheadLabel`'s zh-Hans line):
```js
      fieldSettingsScanBridgeUrlLabel: '扫描桥接地址（例如 http://127.0.0.1:8765）',
```

`STRINGS['zh-Hant']` — derive from the `zh-Hans` line above via a real OpenCC `s2t` run, this repo's established, non-negotiable convention (never hand-guess Traditional characters). Run this in a scratch venv:

```bash
python3 -m venv /tmp/opencc_venv
/tmp/opencc_venv/bin/pip install opencc-python-reimplemented
/tmp/opencc_venv/bin/python3 -c "
import opencc
c = opencc.OpenCC('s2t')
print(c.convert('扫描桥接地址（例如 http://127.0.0.1:8765）'))
"
```

Insert the printed output as the value for `fieldSettingsScanBridgeUrlLabel` in `STRINGS['zh-Hant']` (after line 1958, i.e. right after that block's own `fieldSettingsReminderLookaheadLabel` line):
```js
      fieldSettingsScanBridgeUrlLabel: '<OpenCC output pasted here>',
```

- [ ] **Step 6: Run the test to confirm it passes**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: all three prints show `True` (or the matching URL string), and `JS ERRORS: []`.

Also run the static i18n coverage check, since six new key entries were just added:

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: passes with no missing/extra key reported (confirms all six languages now have `fieldSettingsScanBridgeUrlLabel`, including `zh-Hant`'s freshly-converted value).

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_scan_bridge.py
git commit -m "Add scan_bridge_url setting and its Field Settings UI field"
```

---

### Task 2: Toolbar buttons + `triggerScan()` + full status-message matrix

**Files:**
- Modify: `dossiary.html`
- Test: `tests/test_scan_bridge.py` (extends Task 1's file with new scenarios)

**Interfaces:**
- Consumes: Task 1's `scanBridgeUrl` variable. Existing `checkInbox()`, `addAllInboxFilesAndShowStatus()`, `setStatusT()`, `t()`, `el()` helpers.
- Produces: `const SCAN_PROFILE_NAME = 'Dossiary Scan';`, `const SCAN_MULTI_PROFILE_NAME = 'Dossiary Scan Multi';`, `async function triggerScan(profileName)`. Not consumed by any later task in this plan (Task 3/4 don't call it), but this is the feature's own primary deliverable.

- [ ] **Step 1: Write the failing tests**

This task needs a way to intercept `fetch()` calls with scenario-specific canned responses. **Decision: override `window.fetch` per-scenario via `page.evaluate()`, directly in this test file — do NOT add fetch-stubbing to the shared `tests/stub_studio2.js`.** Reasoning: `dossiary.html` calls `fetch()` in exactly one place (this feature, `triggerScan()`) — no other test file's app code ever touches `fetch()`, so there's no risk of leaving `window.fetch` un-stubbed elsewhere, and a shared stub would need scenario-specific configuration machinery this single-caller feature doesn't justify. This mirrors how test files already customize seeded state via one-off `page.evaluate()` calls (e.g. `window.__TEST_ROOT = window.__makeSeededRoot(...)`) without needing shared stub changes.

Append these scenarios to `tests/test_scan_bridge.py`, right after Scenario 1's closing (`await page.click('#fs-done-btn')` / `await page.wait_for_timeout(150)`, before the final `print("JS ERRORS:", errors)` line — move that final print block down, it stays last):

```python
        # === Scenario 2: unset scan_bridge_url shows "not configured" with no
        # fetch attempted, and both buttons are present in the toolbar ===
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
                window.__FETCH_CALLED = false;
                window.fetch = async (url, opts) => { window.__FETCH_CALLED = true; throw new Error('fetch should not have been called'); };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(150)
        fetch_called_when_unconfigured = await page.evaluate("window.__FETCH_CALLED")
        print("fetch NOT attempted when scan_bridge_url is unset:", fetch_called_when_unconfigured == False)
        status_text_unconfigured = await page.locator('#status').inner_text()
        print("status shows 'not configured' message:", 'Field Settings' in status_text_unconfigured)

        # === Scenario 3: configured URL, successful scan (ok:true) runs the
        # Inbox pipeline and navigates to the Inbox view ===
        seed_with_url_and_inbox_file = {'settings': [{'key': 'scan_bridge_url', 'value': 'http://127.0.0.1:8765'}]}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        # Stage a file in inbox/ the same way scanix500 would have written one,
        # so the Inbox pipeline this success path triggers has something real
        # to pick up -- __addInboxFile is stub_studio2.js's own existing helper
        # for exactly this, already used by tests/test_inbox.py.
        await page.evaluate("window.__addInboxFile(window.__TEST_ROOT, 'scan1.pdf', new Uint8Array([1,2,3]));")

        await page.evaluate("""
            () => {
                window.__FETCH_URLS = [];
                window.fetch = async (url, opts) => {
                    window.__FETCH_URLS.push(url);
                    return new Response(JSON.stringify({ok: true, partial: false, message: '/tmp/scans/scan_1.pdf', output_paths: ['/tmp/scans/scan_1.pdf']}), {status: 200});
                };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        fetch_url_scan = await page.evaluate("window.__FETCH_URLS[0]")
        print("Scan button POSTs to the 'Dossiary Scan' profile path:", fetch_url_scan == 'http://127.0.0.1:8765/scan/Dossiary%20Scan')
        current_view_is_inbox_after_success = await page.locator('#nav-item-inbox.active').count()
        print("view navigates to Inbox after a successful scan:", current_view_is_inbox_after_success == 1)
        buttons_reenabled_after_success = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a successful scan:", buttons_reenabled_after_success)

        # === Scenario 4: Scan Multi POSTs to the distinct 'Dossiary Scan Multi'
        # profile path, not the same URL as Scan ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.__FETCH_URLS = [];
                window.fetch = async (url, opts) => {
                    window.__FETCH_URLS.push(url);
                    return new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: []}), {status: 200});
                };
            }
        """)
        await page.click('#scan-multi-btn')
        await page.wait_for_timeout(300)
        fetch_url_scan_multi = await page.evaluate("window.__FETCH_URLS[0]")
        print("Scan Multi button POSTs to the 'Dossiary Scan Multi' profile path:", fetch_url_scan_multi == 'http://127.0.0.1:8765/scan/Dossiary%20Scan%20Multi')

        # === Scenario 5: partial scan (ok:false, partial:true) still runs the
        # Inbox pipeline AND shows the bridge's own message ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("window.__addInboxFile(window.__TEST_ROOT, 'scan2.pdf', new Uint8Array([1,2,3]));")
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Response(JSON.stringify({ok: false, partial: true, message: 'Multi-feed detected at sheet 3', output_paths: ['/tmp/scans/scan_2.pdf']}), {status: 200});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        view_is_inbox_after_partial = await page.locator('#nav-item-inbox.active').count()
        print("view navigates to Inbox after a partial scan (a usable file was still written):", view_is_inbox_after_partial == 1)
        status_after_partial = await page.locator('#status').inner_text()
        print("status shows the bridge's own partial-scan message:", 'Multi-feed detected at sheet 3' in status_after_partial)

        # === Scenario 6: hard failure (ok:false, partial:false) shows the
        # bridge's own message and does NOT run the Inbox pipeline ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#reload-btn')
        await page.wait_for_timeout(300)
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

        # === Scenario 7: HTTP 404 (unknown profile) shows a clear status,
        # re-enables both buttons, no Inbox pipeline run ===
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Response(JSON.stringify({error: "no profile named 'Dossiary Scan'"}), {status: 404});
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        status_after_404 = await page.locator('#status').inner_text()
        print("status shows 'profile not configured' on a 404:", 'Dossiary Scan' in status_after_404)
        buttons_reenabled_after_404 = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a 404:", buttons_reenabled_after_404)

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

        # === Scenario 9: network failure (fetch rejects entirely, e.g.
        # scanix500-menubar isn't running) shows a clear status naming the URL ===
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => { throw new TypeError('Failed to fetch'); };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        status_after_network_failure = await page.locator('#status').inner_text()
        print("status names the configured URL when the bridge is unreachable:", 'http://127.0.0.1:8765' in status_after_network_failure)
        buttons_reenabled_after_network_failure = await page.evaluate("!document.getElementById('scan-btn').disabled && !document.getElementById('scan-multi-btn').disabled")
        print("both buttons re-enabled after a network failure:", buttons_reenabled_after_network_failure)

        # === Scenario 10: both buttons are disabled while a request is in
        # flight (a slow-resolving fetch, checked mid-flight before it resolves) ===
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => new Promise((resolve) => {
                    window.__RESOLVE_SLOW_FETCH = () => resolve(new Response(JSON.stringify({ok: true, partial: false, message: 'ok', output_paths: []}), {status: 200}));
                });
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(150)  # request is now in flight, not yet resolved
        buttons_disabled_mid_flight = await page.evaluate("document.getElementById('scan-btn').disabled && document.getElementById('scan-multi-btn').disabled")
        print("both buttons disabled while a scan request is in flight:", buttons_disabled_mid_flight)
        await page.evaluate("window.__RESOLVE_SLOW_FETCH()")
        await page.wait_for_timeout(200)
```

- [ ] **Step 2: Run the tests to confirm they fail for the right reason**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: `Scan button present in toolbar: False` (the buttons don't exist yet), with most later checks printing `False`/errors as a consequence — expected until Step 3 lands.

- [ ] **Step 3: Add the toolbar buttons**

In `dossiary.html`'s toolbar HTML, add two new buttons between the existing `#check-reminders-btn` and `#add-btn` (currently lines 693-694):

```html
        <button id="scan-btn" data-i18n="toolbarScan">📷 Scan</button>
        <button id="scan-multi-btn" data-i18n="toolbarScanMulti">📸 Scan Multi</button>
```

- [ ] **Step 4: Add `triggerScan()` and wire both buttons**

Add these two `const` profile-name declarations and the `triggerScan()` function right after the existing `checkRemindersAndShowStatus()` function (currently ends around line 7686, right before the existing button-wiring block that starts with `el('inbox-add-all-btn')...`):

```js
  const SCAN_PROFILE_NAME = 'Dossiary Scan';
  const SCAN_MULTI_PROFILE_NAME = 'Dossiary Scan Multi';

  // Triggers a real scan via the scanix500 HTTP bridge (a separate app --
  // see docs/superpowers/specs/2026-09-14-scanix500-bridge-design.md for the
  // full two-repo design). profileName is one of the two fixed constants
  // above; the bridge's own profile system (configured once, manually, in
  // scanix500's menu bar app) decides where the resulting PDF actually gets
  // written -- it's expected to be the current library's real inbox/ folder,
  // so a successful scan is picked up by the exact same checkInbox()/
  // addAllInboxFilesAndShowStatus() pair the "Check inbox" button already
  // uses, with no new ingestion code here.
  async function triggerScan(profileName){
    if(!scanBridgeUrl){ setStatusT('scanBridgeNotConfigured', null, 'err'); return; }
    el('scan-btn').disabled = true;
    el('scan-multi-btn').disabled = true;
    setStatusT('scanScanning', null, 'busy');
    try{
      const response = await fetch(`${scanBridgeUrl}/scan/${encodeURIComponent(profileName)}`, { method: 'POST' });
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
        setStatusT('scanPartialMessage', {message: result.message}, 'err');
        return;
      }
      setStatusT('scanFailedMessage', {message: result.message}, 'err');
    }catch(e){
      // Covers both a genuine network failure (bridge unreachable) and a
      // malformed/non-JSON response body (e.g. scanBridgeUrl misconfigured
      // to point at some unrelated server) -- either way, nothing about the
      // configured bridge worked, so the same message applies.
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

Add the click-handler wiring right after the existing `el('check-reminders-btn').addEventListener('click', checkRemindersAndShowStatus);` line (around line 7697):

```js
  el('scan-btn').addEventListener('click', () => triggerScan(SCAN_PROFILE_NAME));
  el('scan-multi-btn').addEventListener('click', () => triggerScan(SCAN_MULTI_PROFILE_NAME));
```

- [ ] **Step 5: Add the i18n keys across all six `STRINGS` blocks**

Add `toolbarScan`/`toolbarScanMulti` on the same line as each language's existing `toolbarCheckReminders` key (right before `toolbarAddDocument`, following the existing multi-key-per-line convention at that exact spot):

`STRINGS.en` (line 873) — becomes:
```js
      toolbarCheckInbox: '📥 Check inbox', toolbarCheckReminders: '🔔 Check reminders', toolbarScan: '📷 Scan', toolbarScanMulti: '📸 Scan Multi', toolbarAddDocument: '＋ Add document',
```

`STRINGS.es` (line 1046) — becomes:
```js
      toolbarCheckInbox: '📥 Revisar bandeja de entrada', toolbarCheckReminders: '🔔 Ver recordatorios', toolbarScan: '📷 Escanear', toolbarScanMulti: '📸 Escaneo múltiple', toolbarAddDocument: '＋ Añadir documento',
```

`STRINGS.fr` (line 1219) — becomes:
```js
      toolbarCheckInbox: '📥 Vérifier la boîte de réception', toolbarCheckReminders: '🔔 Vérifier les rappels', toolbarScan: '📷 Numériser', toolbarScanMulti: '📸 Numérisation multiple', toolbarAddDocument: '＋ Ajouter un document',
```

`STRINGS.de` (line 1392) — becomes:
```js
      toolbarCheckInbox: '📥 Posteingang prüfen', toolbarCheckReminders: '🔔 Erinnerungen prüfen', toolbarScan: '📷 Scannen', toolbarScanMulti: '📸 Mehrfach scannen', toolbarAddDocument: '＋ Dokument hinzufügen',
```

`STRINGS['zh-Hans']` (line 1565) — becomes:
```js
      toolbarCheckInbox: '📥 检查收件箱', toolbarCheckReminders: '🔔 检查提醒', toolbarScan: '📷 扫描', toolbarScanMulti: '📸 多页扫描', toolbarAddDocument: '＋ 添加文档',
```

`STRINGS['zh-Hant']` — derive `toolbarScan`/`toolbarScanMulti` from the `zh-Hans` values above via a real OpenCC `s2t` run (same scratch venv as Task 1 Step 5 — reuse `/tmp/opencc_venv` if it's still there, or recreate it):

```bash
/tmp/opencc_venv/bin/python3 -c "
import opencc
c = opencc.OpenCC('s2t')
print(c.convert('📷 扫描'))
print(c.convert('📸 多页扫描'))
"
```

Insert both printed outputs into `STRINGS['zh-Hant']` (line 1762) — becomes:
```js
      toolbarCheckInbox: '📥 檢查收件箱', toolbarCheckReminders: '🔔 檢查提醒', toolbarScan: '<OpenCC output 1>', toolbarScanMulti: '<OpenCC output 2>', toolbarAddDocument: '＋ 添加文檔',
```

Now add the six status-message keys. Add all six on new lines right after each language's existing `dragdropNoFilesWaiting`/`reminderNoneDue` line (that line already establishes the "recent-feature status messages" grouping spot in each block):

`STRINGS.en` (after line 1017):
```js
      scanBridgeNotConfigured: 'Configure the scanner bridge URL in Field Settings first.',
      scanScanning: 'Scanning…',
      scanBridgeUnreachable: "Couldn't reach the scanner bridge at {url} — is scanix500-menubar running?",
      scanProfileNotConfigured: 'Profile "{profile}" isn\'t configured in scanix500 — create it in the menu bar app.',
      scanAlreadyInProgress: 'A scan is already in progress.',
      scanPartialMessage: 'Scan partially completed: {message}',
      scanFailedMessage: 'Scan failed: {message}',
```

`STRINGS.es` (after line 1190):
```js
      scanBridgeNotConfigured: 'Configure primero la URL del puente del escáner en Configuración de campos.',
      scanScanning: 'Escaneando…',
      scanBridgeUnreachable: 'No se pudo conectar con el puente del escáner en {url}; ¿está scanix500-menubar en ejecución?',
      scanProfileNotConfigured: 'El perfil "{profile}" no está configurado en scanix500; créelo en la aplicación de la barra de menús.',
      scanAlreadyInProgress: 'Ya hay un escaneo en curso.',
      scanPartialMessage: 'Escaneo completado parcialmente: {message}',
      scanFailedMessage: 'Error al escanear: {message}',
```

`STRINGS.fr` (after line 1363):
```js
      scanBridgeNotConfigured: "Configurez d'abord l'URL du pont du scanner dans les paramètres des champs.",
      scanScanning: 'Numérisation en cours…',
      scanBridgeUnreachable: 'Impossible de joindre le pont du scanner à {url} — scanix500-menubar est-il lancé ?',
      scanProfileNotConfigured: 'Le profil « {profile} » n\'est pas configuré dans scanix500 — créez-le dans l\'application de la barre de menus.',
      scanAlreadyInProgress: 'Une numérisation est déjà en cours.',
      scanPartialMessage: 'Numérisation partiellement terminée : {message}',
      scanFailedMessage: 'Échec de la numérisation : {message}',
```

`STRINGS.de` (after line 1536):
```js
      scanBridgeNotConfigured: 'Bitte zuerst die Scanner-Bridge-URL in den Feldeinstellungen konfigurieren.',
      scanScanning: 'Scan läuft…',
      scanBridgeUnreachable: 'Die Scanner-Bridge unter {url} ist nicht erreichbar — läuft scanix500-menubar?',
      scanProfileNotConfigured: 'Profil „{profile}" ist in scanix500 nicht konfiguriert — bitte in der Menüleisten-App anlegen.',
      scanAlreadyInProgress: 'Es läuft bereits ein Scan.',
      scanPartialMessage: 'Scan teilweise abgeschlossen: {message}',
      scanFailedMessage: 'Scan fehlgeschlagen: {message}',
```

`STRINGS['zh-Hans']` (after line 1709):
```js
      scanBridgeNotConfigured: '请先在字段设置中配置扫描桥接地址。',
      scanScanning: '扫描中…',
      scanBridgeUnreachable: '无法连接到 {url} 的扫描桥接 —— scanix500-menubar 正在运行吗？',
      scanProfileNotConfigured: 'scanix500 中未配置配置文件"{profile}" —— 请在菜单栏应用中创建。',
      scanAlreadyInProgress: '已有扫描正在进行中。',
      scanPartialMessage: '扫描部分完成：{message}',
      scanFailedMessage: '扫描失败：{message}',
```

`STRINGS['zh-Hant']` — derive all seven from the `zh-Hans` block above via OpenCC:

```bash
/tmp/opencc_venv/bin/python3 -c "
import opencc
c = opencc.OpenCC('s2t')
lines = [
    '请先在字段设置中配置扫描桥接地址。',
    '扫描中…',
    '无法连接到 {url} 的扫描桥接 —— scanix500-menubar 正在运行吗？',
    'scanix500 中未配置配置文件\"{profile}\" —— 请在菜单栏应用中创建。',
    '已有扫描正在进行中。',
    '扫描部分完成：{message}',
    '扫描失败：{message}',
]
for line in lines:
    print(c.convert(line))
"
```

Insert the seven printed outputs (after line 2005) as:
```js
      scanBridgeNotConfigured: '<OpenCC output 1>',
      scanScanning: '<OpenCC output 2>',
      scanBridgeUnreachable: '<OpenCC output 3>',
      scanProfileNotConfigured: '<OpenCC output 4>',
      scanAlreadyInProgress: '<OpenCC output 5>',
      scanPartialMessage: '<OpenCC output 6>',
      scanFailedMessage: '<OpenCC output 7>',
```

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: every print shows `True` (or the matching string/value), and `JS ERRORS: []`.

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: passes with no missing/extra key across all six languages.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_scan_bridge.py
git commit -m "Add Scan/Scan Multi toolbar buttons and triggerScan()"
```

---

### Task 3: Recalibrate `.table-wrap`'s sticky-header `max-height` (empirical)

**Files:**
- Modify: `dossiary.html`

**Interfaces:**
- Consumes: nothing from Tasks 1-2's own interfaces — this task only reacts to their *side effect* on toolbar layout.
- Produces: nothing new — this task only adjusts existing CSS constants (see CLAUDE.md's own "`.table-wrap` is a deliberate, bounded scroll container" note for the full history of these numbers).

- [ ] **Step 1: Run the existing calibration regression test to see whether the two new buttons broke it**

Run: `cd tests && python3 test_footer_pin.py`

Read the full output. Every scenario prints either `PASS` (with a `gap=`/`clip=` value) or an `AssertionError` naming the exact combination (nav style, viewport width, bulk-bar visibility) and the measured overlap in pixels.

- [ ] **Step 2: If any scenario fails, sweep to find the worst-case new bump needed**

If Step 1 was all green already, skip to Step 4 — the two new buttons didn't push `.toolbar` onto an extra wrapped row at any of `test_footer_pin.py`'s already-swept widths, and no CSS change is needed. (Still worth double-checking by eye at a few in-between widths not in that file's own sweep, e.g. open the app directly in a browser and resize between 700-1600px watching for `.toolbar` wrapping — but don't hand-tune CSS speculatively without a real observed failure.)

If any scenario failed, note the largest reported overlap for each of the four nav-style/bulk-bar combinations (tabs/no-bulk-bar, sidebar/no-bulk-bar, tabs/bulk-bar, sidebar/bulk-bar) at the specific width(s) that failed. Per this repo's established "accept extra gap, never accept overlap" principle (see `CLAUDE.md`'s own `.table-wrap` note), increase all four desktop `max-height` constants (`dossiary.html` lines 281-284, currently `414`/`374`/`488`/`448`) by the same uniform amount — round up to the nearest even number, matching every previous bump in this file's own history — that closes the worst overlap found. If any of the four mobile-breakpoint scenarios (320/375/640px width, inside the `@media (max-width: 640px)` block, `dossiary.html` lines 543-547, currently `392`/`416`/`494`/`518`) also failed, apply the same uniform-bump treatment to those four independently — the desktop and mobile bumps are not required to be the same size, since they're calibrated against different worst-case widths (see CLAUDE.md's own note on why the mobile four are not simply the desktop four plus a fixed offset).

- [ ] **Step 3: Re-run to confirm the bump closes the gap with no new overlap introduced**

Run: `cd tests && python3 test_footer_pin.py`
Expected: every scenario now prints `PASS`.

- [ ] **Step 4: Update `CLAUDE.md`'s `.table-wrap` architecture note**

If Step 2 required a real bump, extend `CLAUDE.md`'s existing `.table-wrap` note (in the root `CLAUDE.md`, the long paragraph already documenting the two prior bumps — from `364`/`370`/`438`/`444` to `410`/`370`/`484`/`444`, then to the current `414`/`374`/`488`/`448`) with one more sentence in the same style, naming the old and new values, which feature caused it (the Scan/Scan Multi toolbar buttons), and the empirical worst-case gap before/after — following that paragraph's own established narrative pattern exactly (see its existing "These four desktop numbers were bumped a third time..." sentence as the template to extend from). If Step 2 found no failures and no change was needed, add a brief sentence instead noting that the Scan/Scan Multi buttons were verified via the same `test_footer_pin.py` sweep and did NOT require a recalibration, so a future reader doesn't wonder whether this was checked.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html CLAUDE.md
git commit -m "Recalibrate .table-wrap sticky-header max-height for the new Scan buttons"
```

(If Step 2 found no failures and Step 4 only added a documentation sentence with no CSS change, adjust the commit message accordingly, e.g. "Document that the Scan/Scan Multi buttons don't require sticky-header recalibration".)

---

### Task 4: Document the feature in `CLAUDE.md` and `tests/CLAUDE.md`; final full-suite run

**Files:**
- Modify: `CLAUDE.md`
- Modify: `tests/CLAUDE.md`

**Interfaces:**
- Consumes: nothing new — this task documents Tasks 1-3's finished behavior.

- [ ] **Step 1: Add a new architecture note to `CLAUDE.md`**

Add a new bullet to `CLAUDE.md`'s "Architecture notes" section, positioned near the existing "Inbox" note (since this feature is a third way of getting a document into the library's `inbox/` folder, alongside the Inbox/`scan_watch.py` pipeline and drag-and-drop) — following the same level of detail and narrative style those existing notes use:

```markdown
- **Scan / Scan Multi toolbar buttons** (`#scan-btn`/`#scan-multi-btn`,
  `triggerScan()`, `SCAN_PROFILE_NAME`/`SCAN_MULTI_PROFILE_NAME`) let a
  person trigger a real scan on a physical scanner directly from Dossiary's
  toolbar, via a separate companion app: `scanix500` (a sibling repo,
  `AarneAarebye/iX500`) drives a specific ScanSnap iX500 directly via SANE
  and embeds a small local HTTP bridge in its own macOS menu bar app
  (`scanix500-menubar`). Dossiary has no direct scanner integration itself
  — see the "No direct scanner integration in the app itself" note above,
  which still holds; this feature works *around* that boundary by talking
  to a companion native app over `fetch()`, the same way `scan_watch.py`
  works around it by watching a folder, not by Dossiary itself gaining
  hardware access.
  **`scan_bridge_url`** (a `settings` row, `loadScanBridgeUrl()`/
  `saveScanBridgeUrl()`, configured via a new Field Settings text field) is
  the bridge's base URL — unset by default, in which case both buttons show
  a "not configured" status with no network request attempted at all.
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
  **`triggerScan(profileName)` never invents a new document-ingestion
  path** — scanix500 already writes the finished PDF directly into the
  profile's configured destination folder (the library's `inbox/`), so a
  successful (`ok: true`) response just calls the *existing*
  `checkInbox()`/`addAllInboxFilesAndShowStatus()` pair verbatim, the same
  call the "Check inbox" button already makes — there is no separate
  Scan-specific way a document lands in the library. A partial result
  (`ok: false, partial: true` — e.g. a multi-feed jam that still produced a
  usable file) still runs that same pipeline, since a real file was
  written, but shows the bridge's own message afterward rather than the
  Inbox pipeline's own "Added N document(s)" report — the jam warning is
  more important information and deliberately becomes the final status
  line. A hard failure (`ok: false, partial: false`) shows the bridge's
  message and does not touch the Inbox at all. Both buttons are disabled
  for the duration of a request and always re-enabled via `try/finally`,
  regardless of which outcome (success, 404, 409, network failure,
  malformed response) actually occurred — never left stuck disabled.
  **No polling, no progress bar** — the request simply blocks until
  scanix500's own bridge resolves it (which itself blocks until the real
  scan finishes), matching the "single explicit click, wait for the real
  result" pattern `checkInbox()`'s own button already established.
```

- [ ] **Step 2: Update `tests/CLAUDE.md`'s test-coverage narrative**

Add a paragraph describing `tests/test_scan_bridge.py`'s coverage to the long "How this was tested" narrative in `tests/CLAUDE.md`, in the same dense style as the file's existing feature-by-feature paragraphs (see the file's own reminder-feature paragraph, immediately preceding this new one in the file, as the closest stylistic template) — summarizing: `scan_bridge_url` defaulting empty/persisting/surviving a reopen; the "not configured" no-fetch-attempted path; a successful scan running the Inbox pipeline and navigating to the Inbox view; Scan vs. Scan Multi POSTing to their own distinct, fixed profile-name paths; a partial scan still running the Inbox pipeline while also surfacing the bridge's own message; a hard failure showing the bridge's message with no document added; 404/409/network-failure each showing a distinct, clear status; and both buttons staying correctly enabled/disabled across every one of those outcomes, including mid-flight. Also note the deliberate design choice this test file made: `window.fetch` is overridden per-scenario directly in `test_scan_bridge.py` itself rather than added to the shared `stub_studio2.js`, since `dossiary.html` calls `fetch()` in exactly this one feature and no other test file's app code ever touches it.

- [ ] **Step 3: Run the full test suite one final time**

Run: `cd tests && for f in test_*.py; do echo "=== $f ==="; python3 "$f" 2>&1 | tail -5; done`

Expected: every file's tail output shows all-`True`/matching prints and `JS ERRORS: []` (or, for `test_i18n_coverage.py`, its own pass message — it's the one non-Playwright file in the suite).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "Document the Scan/Scan Multi toolbar buttons feature"
```
