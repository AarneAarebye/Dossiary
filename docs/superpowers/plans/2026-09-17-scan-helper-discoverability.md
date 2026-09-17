# Scan Helper Discoverability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Dossiary's scan-toolbar setup discoverable — explain what's
needed and link directly to `scanix500-menubar`'s latest release from
inside Dossiary itself, instead of requiring a person to already know that
separate companion app exists.

**Architecture:** Two purely additive UI/docs changes in Dossiary
(`dossiary.html`) plus one documentation-only change in the sibling iX500
repo. No new app, no new code in iX500 beyond its README, and no change to
the scan bridge's wire contract or `triggerScan()`'s own request/response
handling.

**Tech Stack:** Vanilla JS (no framework), this repo's existing `t()`/
`STRINGS` i18n mechanism, Playwright for tests
(`tests/test_scan_bridge.py`).

## Global Constraints

- No changes to the bridge's wire contract (`GET /health`, `POST /scan?...`),
  `triggerScan()`'s request construction, or any status-handling branch
  (`400`/`404`/`409`/network-failure/malformed-response) — this plan adds UI
  only, it does not touch scan outcomes.
- No changes to `scanix500-menubar`'s own feature set (profiles,
  hardware-button scanning, the bridge scan folder setting) and no renaming
  of the app or the iX500 repo. The download link always points at
  `https://github.com/AarneAarebye/iX500/releases/latest` — use this exact
  URL everywhere it appears, in both repos.
- The "Configure Scanner Connection" dialog's new download line is shown
  **unconditionally, every time the dialog opens** — never behind an
  if/else trying to detect "not installed" vs. "wrong port" vs. "network
  blocked." A browser `fetch()` failure cannot distinguish these cases; do
  not add detection logic that pretends otherwise.
- Both new pieces of Dossiary UI copy (the Field Settings section, the
  dialog's download line) must be translated across all 6 supported
  languages (`en`, `de`, `es`, `fr`, `zh-Hans`, `zh-Hant`) — this app has no
  untranslated user-facing strings.
- Both `openFieldSettingsModal()` and `openScanConnectDialog()` are
  rebuilt from scratch via a template string on every modal open — per
  this repo's own established i18n convention, that means new text in
  either of them uses **inline `${t('key')}` calls**, not
  `data-i18n` attributes (attributes only work on static page markup that
  survives across renders — see `CLAUDE.md`'s own i18n note for why).

---

### Task 1: Dossiary UI — Field Settings section, dialog download line, i18n, tests

**Files:**
- Modify: `dossiary.html`
- Modify: `tests/test_scan_bridge.py`

**Interfaces:**
- Consumes: `t(key, params)`, `openFieldSettingsModal()`,
  `openScanConnectDialog(isMulti)` (all already shipped, unchanged in
  signature).
- Produces: no new functions — this task only adds markup inside two
  existing template strings and 5 new i18n keys. Nothing in a later task
  depends on new function names or signatures.

- [ ] **Step 1: Add 5 new i18n keys to all 6 `STRINGS` blocks**

In `STRINGS.en`, find the line
`fieldSettingsScanBridgeUrlLabel: 'Scanner bridge URL (e.g. http://127.0.0.1:8765)',`
(currently `dossiary.html:987`). Immediately after it, insert:

```javascript
      fieldSettingsScannerIntegrationHeading: 'Scanner Integration',
      fieldSettingsScannerIntegrationText: 'Scanning from the toolbar needs a small companion app, scanix500-menubar, running locally on your Mac.',
      fieldSettingsScannerIntegrationLink: 'Download scanix500-menubar',
```

Then find the line `scanConnectPortLabel: 'Port',` in the same block
(currently `dossiary.html:1030`). Immediately after it, insert:

```javascript
      scanConnectDownloadPrompt: "Don't have the scan helper installed?",
      scanConnectDownloadLink: 'Download it',
```

In `STRINGS.es`, after its own
`fieldSettingsScanBridgeUrlLabel: 'URL del puente del escáner (p. ej. http://127.0.0.1:8765)',`
(currently `dossiary.html:1177`), insert:

```javascript
      fieldSettingsScannerIntegrationHeading: 'Integración del escáner',
      fieldSettingsScannerIntegrationText: 'Escanear desde la barra de herramientas requiere una pequeña aplicación complementaria, scanix500-menubar, ejecutándose localmente en su Mac.',
      fieldSettingsScannerIntegrationLink: 'Descargar scanix500-menubar',
```

After its own `scanConnectPortLabel: 'Puerto',` (currently
`dossiary.html:1220`), insert:

```javascript
      scanConnectDownloadPrompt: '¿No tiene instalado el ayudante de escaneo?',
      scanConnectDownloadLink: 'Descargarlo',
```

In `STRINGS.fr`, after its own
`fieldSettingsScanBridgeUrlLabel: 'URL du pont du scanner (p. ex. http://127.0.0.1:8765)',`
(currently `dossiary.html:1367`), insert:

```javascript
      fieldSettingsScannerIntegrationHeading: 'Intégration du scanner',
      fieldSettingsScannerIntegrationText: "Numériser depuis la barre d'outils nécessite une petite application complémentaire, scanix500-menubar, exécutée localement sur votre Mac.",
      fieldSettingsScannerIntegrationLink: 'Télécharger scanix500-menubar',
```

After its own `scanConnectPortLabel: 'Port',` (currently
`dossiary.html:1410`), insert:

```javascript
      scanConnectDownloadPrompt: "Vous n'avez pas installé l'assistant de numérisation ?",
      scanConnectDownloadLink: 'Le télécharger',
```

In `STRINGS.de`, after its own
`fieldSettingsScanBridgeUrlLabel: 'Scanner-Bridge-URL (z. B. http://127.0.0.1:8765)',`
(currently `dossiary.html:1557`), insert:

```javascript
      fieldSettingsScannerIntegrationHeading: 'Scanner-Integration',
      fieldSettingsScannerIntegrationText: 'Zum Scannen über die Symbolleiste wird eine kleine Begleit-App, scanix500-menubar, benötigt, die lokal auf dem Mac läuft.',
      fieldSettingsScannerIntegrationLink: 'scanix500-menubar herunterladen',
```

After its own `scanConnectPortLabel: 'Port',` (currently
`dossiary.html:1600`), insert:

```javascript
      scanConnectDownloadPrompt: 'Noch keinen Scan-Helfer installiert?',
      scanConnectDownloadLink: 'Jetzt herunterladen',
```

In `STRINGS['zh-Hans']`, after its own
`fieldSettingsScanBridgeUrlLabel: '扫描桥接地址（例如 http://127.0.0.1:8765）',`
(currently `dossiary.html:1747`), insert:

```javascript
      fieldSettingsScannerIntegrationHeading: '扫描仪集成',
      fieldSettingsScannerIntegrationText: '从工具栏扫描需要一个小型配套应用 scanix500-menubar，在您的 Mac 上本地运行。',
      fieldSettingsScannerIntegrationLink: '下载 scanix500-menubar',
```

After its own `scanConnectPortLabel: '端口',` (currently
`dossiary.html:1790`), insert:

```javascript
      scanConnectDownloadPrompt: '还没有安装扫描助手？',
      scanConnectDownloadLink: '立即下载',
```

In `STRINGS['zh-Hant']`, after its own
`fieldSettingsScanBridgeUrlLabel: '掃描橋接地址（例如 http://127.0.0.1:8765）',`
(currently `dossiary.html:2046`), insert (a straight script conversion of
the zh-Hans text above, matching this repo's established zh-Hant
derivation convention):

```javascript
      fieldSettingsScannerIntegrationHeading: '掃描儀整合',
      fieldSettingsScannerIntegrationText: '從工具列掃描需要一個小型配套應用 scanix500-menubar，在您的 Mac 上本地執行。',
      fieldSettingsScannerIntegrationLink: '下載 scanix500-menubar',
```

After its own `scanConnectPortLabel: '端口',` (currently
`dossiary.html:2103`), insert:

```javascript
      scanConnectDownloadPrompt: '還沒有安裝掃描助手？',
      scanConnectDownloadLink: '立即下載',
```

- [ ] **Step 2: Add the Field Settings "Scanner Integration" section**

Find, inside `openFieldSettingsModal()` (currently `dossiary.html:6741-6761`):

```javascript
          <div class="field-row">
            <div class="field">
              <label for="fs-default-type">${t('fieldSettingsDefaultDocTypeLabel')}</label>
              <select id="fs-default-type">
                <option value="">${t('commonNone')}</option>
                ${usedTypes.map(t => `<option value="${escapeHtml(t)}" ${t === defaultDocumentType ? 'selected' : ''}>${escapeHtml(t)}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label for="fs-default-currency">${t('fieldSettingsDefaultCurrencyLabel')}</label>
              <input type="text" id="fs-default-currency" list="currency-list" value="${escapeHtml(defaultCurrency || '')}" placeholder="${t('commonNone')}" />
            </div>
            <div class="field">
              <label for="fs-reminder-lookahead">${t('fieldSettingsReminderLookaheadLabel')}</label>
              <input type="number" id="fs-reminder-lookahead" min="0" step="1" value="${reminderLookaheadDays}" />
            </div>
            <div class="field">
              <label for="fs-scan-bridge-url">${t('fieldSettingsScanBridgeUrlLabel')}</label>
              <input type="text" id="fs-scan-bridge-url" value="${escapeHtml(scanBridgeUrl || '')}" placeholder="http://127.0.0.1:8765" />
            </div>
          </div>
          <div class="fs-columns">
```

Replace with (one new `<div class="fs-scanner-integration">` block
inserted between the existing `.field-row` and `.fs-columns`, following the
same `<h3>` + explanatory-paragraph shape the `.fs-descriptions` block
further down in this same modal already uses):

```javascript
          <div class="field-row">
            <div class="field">
              <label for="fs-default-type">${t('fieldSettingsDefaultDocTypeLabel')}</label>
              <select id="fs-default-type">
                <option value="">${t('commonNone')}</option>
                ${usedTypes.map(t => `<option value="${escapeHtml(t)}" ${t === defaultDocumentType ? 'selected' : ''}>${escapeHtml(t)}</option>`).join('')}
              </select>
            </div>
            <div class="field">
              <label for="fs-default-currency">${t('fieldSettingsDefaultCurrencyLabel')}</label>
              <input type="text" id="fs-default-currency" list="currency-list" value="${escapeHtml(defaultCurrency || '')}" placeholder="${t('commonNone')}" />
            </div>
            <div class="field">
              <label for="fs-reminder-lookahead">${t('fieldSettingsReminderLookaheadLabel')}</label>
              <input type="number" id="fs-reminder-lookahead" min="0" step="1" value="${reminderLookaheadDays}" />
            </div>
            <div class="field">
              <label for="fs-scan-bridge-url">${t('fieldSettingsScanBridgeUrlLabel')}</label>
              <input type="text" id="fs-scan-bridge-url" value="${escapeHtml(scanBridgeUrl || '')}" placeholder="http://127.0.0.1:8765" />
            </div>
          </div>
          <div class="fs-scanner-integration" style="margin-top:16px;">
            <h3>${t('fieldSettingsScannerIntegrationHeading')}</h3>
            <p style="font-size:12.5px; color:var(--text-dim); line-height:1.6; margin:0 0 8px;">
              ${t('fieldSettingsScannerIntegrationText')}
            </p>
            <a href="https://github.com/AarneAarebye/iX500/releases/latest" target="_blank" rel="noopener noreferrer">${t('fieldSettingsScannerIntegrationLink')}</a>
          </div>
          <div class="fs-columns">
```

- [ ] **Step 3: Add the persistent download line to the Configure Scanner Connection dialog**

Find, inside `openScanConnectDialog(isMulti)` (currently
`dossiary.html:7863-7867`):

```javascript
          <div class="field">
            <label for="scan-connect-port">${t('scanConnectPortLabel')}</label>
            <input type="text" id="scan-connect-port" value="${SCAN_BRIDGE_DEFAULT_PORT}" />
          </div>
          <div id="scan-connect-status" class="doc-sub" style="margin-top:8px; min-height:1.2em;"></div>
```

Replace with:

```javascript
          <div class="field">
            <label for="scan-connect-port">${t('scanConnectPortLabel')}</label>
            <input type="text" id="scan-connect-port" value="${SCAN_BRIDGE_DEFAULT_PORT}" />
          </div>
          <p style="font-size:12.5px; color:var(--text-dim); line-height:1.6; margin:8px 0 0;">
            ${t('scanConnectDownloadPrompt')} <a href="https://github.com/AarneAarebye/iX500/releases/latest" target="_blank" rel="noopener noreferrer">${t('scanConnectDownloadLink')}</a>
          </p>
          <div id="scan-connect-status" class="doc-sub" style="margin-top:8px; min-height:1.2em;"></div>
```

This line shows every time the dialog opens — no conditional logic. It is
never removed by any later step in this dialog's flow (the existing
Cancel/close/backdrop/Escape dismiss paths all clear the whole
`modalRoot.innerHTML`, same as they already do today).

- [ ] **Step 4: Add two new test scenarios to `tests/test_scan_bridge.py`**

Find the end of the file, right before the final print/browser-close block:

```python
        print("JS ERRORS:", errors)
        await browser.close()
```

Insert two new scenarios immediately before that block (after Scenario
16's own closing code):

```python
        # === Scenario 17 (new): Field Settings has a "Scanner Integration"
        # section explaining what's needed and linking to scanix500-menubar's
        # latest release, next to the existing scan_bridge_url override field ===
        await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        scanner_integration_heading_count = await page.locator('.fs-scanner-integration h3').count()
        print("Field Settings shows a Scanner Integration heading:", scanner_integration_heading_count == 1)
        scanner_integration_link_href = await page.locator('.fs-scanner-integration a').get_attribute('href')
        print("the Field Settings link points at scanix500-menubar's latest release:", scanner_integration_link_href == 'https://github.com/AarneAarebye/iX500/releases/latest')
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        # === Scenario 18 (new): the Configure Scanner Connection dialog
        # always shows a persistent download link alongside the Port field,
        # regardless of why the probe failed -- not conditionally shown ===
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
        download_link_href = await page.locator('.modal a[target="_blank"]').get_attribute('href')
        print("the dialog shows a persistent download link pointing at the latest release:", download_link_href == 'https://github.com/AarneAarebye/iX500/releases/latest')
        await page.click('#scan-connect-cancel-btn')
        await page.wait_for_timeout(150)

```

- [ ] **Step 5: Run the test and verify it passes**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: every `print()` line shows `True`, and the final `JS ERRORS: []`
line is empty.

- [ ] **Step 6: Run the static i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: passes cleanly — confirms the 5 new keys exist in all 6
languages with identical key sets.

- [ ] **Step 7: Commit**

```bash
git add dossiary.html tests/test_scan_bridge.py
git commit -m "feat: surface scanner-integration setup and a download link in Dossiary's UI"
```

---

### Task 2: Dossiary documentation — CLAUDE.md and tests/CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `tests/CLAUDE.md`

**Interfaces:**
- Consumes: nothing new — documents Task 1's already-landed UI.
- Produces: nothing consumed by a later task; this repo's own two doc
  tasks are independent of Task 3 (a separate repo).

- [ ] **Step 1: Append a discoverability amendment to the "Scan / Scan Multi toolbar buttons" note**

In `CLAUDE.md`, find the end of that bullet — its last paragraph currently
ends (around `CLAUDE.md:2036-2042`):

```
  plainly: a scanix500 profile's `destination` folder no longer needs to
  point at any specific Dossiary library's `inbox/` — it's now purely a
  local safety-net copy on the scanix500 side (see that repo's own
  README). Per-library scanix500 profiles were considered during this
  amendment's design and explicitly rejected for the same reason: once the
  file arrives over the connection, scanix500 never needs to know which
  library it's serving.
- **Searchable PDF generation** (JPEG/PNG only): `runOcr()` requests
```

Insert a new paragraph right after that paragraph's closing sentence,
before the next bullet (`- **Searchable PDF generation**`):

```
  **Scan helper discoverability (2026-09-17 amendment)**: installing
  scanix500-menubar was previously undiscoverable from within Dossiary
  itself — nothing named it, explained it, or linked to it. Field
  Settings now has a "Scanner Integration" section (`.fs-scanner-integration`,
  next to the `scan_bridge_url` manual-override field) explaining what's
  needed and linking directly to scanix500-menubar's latest GitHub
  release, and the "Configure Scanner Connection" dialog
  (`openScanConnectDialog()`) shows a persistent "Don't have the scan
  helper installed?" download link alongside its existing Port field,
  every time it opens — not conditionally, since a browser `fetch()`
  failure can't distinguish "nothing installed" from "installed on a
  different port" from "blocked by a firewall"; all three surface as the
  same generic network error. This is purely additive UI — no change to
  the bridge's wire contract, to `triggerScan()`'s own request/response
  handling, or to scanix500-menubar's own feature set. See
  `docs/superpowers/specs/2026-09-17-scan-helper-discoverability-design.md`
  for the full design.
```

- [ ] **Step 2: Run the test suite once**

Run: `cd tests && python3 test_scan_bridge.py`
Expected: unchanged from Task 1's Step 5 (docs-only changes in this task).

- [ ] **Step 3: Update `tests/CLAUDE.md`'s test_scan_bridge.py coverage paragraph**

In `tests/CLAUDE.md`, find the sentence (currently around
`tests/CLAUDE.md:701-706`):

```
silently adopted (Scenario 15, unchanged); and both buttons staying
correctly disabled throughout a request and always re-enabled via
`try/finally`, regardless of outcome, never stuck disabled (Scenario 10,
unchanged), plus a re-entrancy guard against a second click starting a
second concurrent probe (Scenario 16, unchanged). This coverage is
spread across sixteen numbered scenarios (2b/2c/2d sub-parts of Scenario
```

Replace with:

```
silently adopted (Scenario 15, unchanged); both buttons staying
correctly disabled throughout a request and always re-enabled via
`try/finally`, regardless of outcome, never stuck disabled (Scenario 10,
unchanged), plus a re-entrancy guard against a second click starting a
second concurrent probe (Scenario 16, unchanged); Field Settings' own
"Scanner Integration" section rendering a heading and a link to
scanix500-menubar's latest release (Scenario 17, new, from the
2026-09-17 scan-helper-discoverability amendment); and the Configure
Scanner Connection dialog always showing a persistent download link
alongside its Port field, regardless of why the probe failed — not
conditionally, since a `fetch()` failure alone can't distinguish "not
installed" from "wrong port" (Scenario 18, new). This coverage is
spread across eighteen numbered scenarios (2b/2c/2d sub-parts of Scenario
```

Then, a few lines later, find:

```
1), then the full auto-connect matrix (Scenarios 2/2b/2c/2d), then one
scenario apiece for the button/`triggerScan()` outcome matrix, so
end-to-end confidence in the whole flow comes from that matrix as a set,
not from any single scenario. **By design, `window.fetch` is overridden
```

Leave this paragraph otherwise unchanged — the matrix description still
accurately describes Scenarios 1-16; Scenarios 17/18 are additive UI
checks, not part of that outcome matrix, and are already described in the
sentence just edited above.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "docs: document the scan-helper-discoverability amendment"
```

---

### Task 3: iX500 README — "New here via Dossiary?" callout

**Files:**
- Modify: `/Users/aarneaarebye/Projects/iX500/README.md`

**Interfaces:**
- Consumes: nothing from Tasks 1-2 (separate repo, docs-only).
- Produces: nothing — this is this plan's last task.

- [ ] **Step 1: Add the callout above the existing "Why" section**

In `/Users/aarneaarebye/Projects/iX500/README.md`, find the top of the
file:

```markdown
# scanix500

A vendor-independent scan pipeline for the ScanSnap iX500, driving it
directly via SANE instead of ScanSnap Home.

## Why
```

Replace with:

```markdown
# scanix500

A vendor-independent scan pipeline for the ScanSnap iX500, driving it
directly via SANE instead of ScanSnap Home.

## New here via Dossiary?

If you followed a link from [Dossiary](https://github.com/AarneAarebye/Dossiary)
to get its Scan/Scan Multi toolbar buttons working, here's the fast path:

1. Download the latest release from
   [Releases](https://github.com/AarneAarebye/iX500/releases/latest).
2. Run `scanix500-menubar.app`.
3. That's it — Dossiary auto-connects to it on `localhost:8765` with no
   further setup.

The rest of this README covers the full project (the CLI scan pipeline,
the menu bar app's own profile system, hardware-button scanning, and the
HTTP bridge's internals) for anyone who wants to understand or build on
it — not required just to get Dossiary's scan buttons working.

## Why
```

- [ ] **Step 2: Commit**

```bash
cd /Users/aarneaarebye/Projects/iX500
git add README.md
git commit -m "docs: add a fast-path callout for people arriving via Dossiary"
```
