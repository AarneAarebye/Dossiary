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
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        # ALREADY-CONFIGURED scan_bridge_url reopens the Configure Scanner
        # Connection dialog, instead of just showing an unreachable-bridge
        # status with no recovery path ===
        seed_with_url_and_inbox_file = {'settings': [{'key': 'scan_bridge_url', 'value': 'http://127.0.0.1:8765'}]}
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_with_url_and_inbox_file)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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
        await page.click('#tools-btn'); await page.click('#reload-btn')
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

        # === Scenario 17 (new): Field Settings has a "Scanner Integration"
        # section explaining what's needed and linking to scanix500-menubar's
        # latest release, next to the existing scan_bridge_url override field ===
        await page.click('#tools-btn'); await page.click('#manage-fields-btn')
        await page.wait_for_timeout(200)
        scanner_integration_heading_count = await page.locator('.fs-scanner-integration h3').count()
        print("Field Settings shows a Scanner Integration heading:", scanner_integration_heading_count == 1)
        scanner_integration_link_href = await page.locator('.fs-scanner-integration a').get_attribute('href')
        print("the Field Settings link points at the iX500 repo root:", scanner_integration_link_href == 'https://github.com/AarneAarebye/iX500')
        scanner_integration_link_text = await page.locator('.fs-scanner-integration a').inner_text()
        print("the Field Settings link has real, translated text:", bool(scanner_integration_link_text) and scanner_integration_link_text != 'fieldSettingsScannerIntegrationLink')
        await page.click('#fs-done-btn')
        await page.wait_for_timeout(150)

        # === Scenario 18 (new): the Configure Scanner Connection dialog
        # always shows a persistent download link alongside the Port field,
        # regardless of why the probe failed -- not conditionally shown ===
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(seed_no_url)}); window.__TEST_ROOT.name = 'TestLib';")
        await page.click('#tools-btn'); await page.click('#reload-btn')
        await page.wait_for_timeout(300)
        await page.evaluate("""
            () => {
                window.fetch = async (url, opts) => { throw new TypeError('Failed to fetch'); };
            }
        """)
        await page.click('#scan-btn')
        await page.wait_for_timeout(300)
        download_link_href = await page.locator('#scan-connect-download-link').get_attribute('href')
        print("the dialog shows a persistent download link pointing at the iX500 repo root:", download_link_href == 'https://github.com/AarneAarebye/iX500')
        download_link_text = await page.locator('#scan-connect-download-link').inner_text()
        print("the dialog's download link has real, translated text:", bool(download_link_text) and download_link_text != 'scanConnectDownloadLink')
        await page.click('#scan-connect-cancel-btn')
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
