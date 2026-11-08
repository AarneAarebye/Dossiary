import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, re
from playwright.async_api import async_playwright

# Upload progress, step 1 (spec docs/superpowers/specs/2026-11-08-upload-progress-design.md):
# while Dossiary Sync's state answer says `uploading: true` for the open synced
# library, the status line shows a spinner and "Uploading to the Pi… m:ss"
# (the elapsed time ticking every second, the state polled every 2 s), then
# the done line; a waiting line while the Pi is unreachable, a problem line for
# lastError. A fake fetch plays the Mac service (as in test_no_lease.py): the
# state answer is window.__SYNC.state (or 'missing' for a 404, 'garbage' for a
# body that isn't JSON). Every state request is logged with its time in
# window.__STATE_CALLS. Real time (the page's timers aren't faked), with
# generous waits.
FAKE_SYNC = """
(config) => {
    window.__SYNC = config;
    window.__STATE_CALLS = [];
    const BASE = 'http://127.0.0.1:8769';
    const json = (status, body) => new Response(JSON.stringify(body), { status });
    window.fetch = async (url, opts = {}) => {
        const headers = opts.headers || {};
        const S = window.__SYNC;
        if(!url.startsWith(BASE + '/')) throw new TypeError('Failed to fetch');
        const path = url.slice(BASE.length);
        if(path === '/admin/health') return json(200, { service: 'dossiary-sync', version: '0.16.0', adminProtocol: 1, connected: headers.Authorization === `Bearer ${S.token}` });
        if(headers.Authorization !== `Bearer ${S.token}`) return json(401, { error: 'Unauthorized' });
        if(path === '/admin/libraries') return json(200, [{ id: 'lib-7f3a', name: 'Household', available: true }]);
        if(path === '/admin/devices') return json(200, []);
        const st = /^\\/admin\\/libraries\\/([^/]+)\\/state$/.exec(path);
        if(st){
            window.__STATE_CALLS.push(performance.now());
            if(S.state === 'missing') return json(404, { error: 'Not found' });
            if(S.state === 'garbage') return new Response('<html>nonsense</html>', { status: 200 });
            return json(200, S.state);
        }
        return json(404, { error: 'Not found' });
    };
}
"""

TOKEN_KEY = 'dossiary_sync_admin_token'
LIB_ID = 'lib-7f3a'
SEED = {
    "documents": [{
        "id": 1, "title": "Invoice", "category": None, "document_type": None,
        "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": "files/1_a.pdf", "original_file_path": None,
        "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
        "archived": 0, "needs_review": 0, "deleted": 0,
    }],
}

UPLOADING_RE = re.compile(r'^Uploading to the Pi… (\d+):(\d\d)$')
DONE_TEXT = 'Uploaded “Household” to the Pi (version 1). Other devices can get it now.'
WAITING_TEXT = 'Waiting for the Pi… it is not reachable. The upload continues when it is back.'


def state(version=0, uploading=True, hub=True, last_error=None):
    """A GET …/state answer. uploading=None leaves the key out, as the real Dossiary Sync does when it is
    false (EditorControl.swift encodes it only when true)."""
    s = {"libraryId": LIB_ID, "version": version, "hubReachable": hub, "lease": None, "offline": False,
         "keptAside": [], "lastError": last_error}
    if uploading is not None:
        s["uploading"] = uploading
    return s


async def open_app(p, st, token='admin-tok', lang=None):
    browser = await p.chromium.launch()
    context = await browser.new_context(viewport={'width': 1440, 'height': 900}, timezone_id='UTC', locale='en-US')
    page = await context.new_page()
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
    await page.evaluate(FAKE_SYNC, {"token": "admin-tok", "state": st})
    await page.evaluate("""async ([seed, sync]) => {
        const root = window.__makeSeededRoot(seed);
        root.name = 'Household.dossiary';
        window.__TEST_ROOT = root;
        const w = await (await root.getFileHandle('.dossiary-sync.json', { create: true })).createWritable();
        await w.write(new TextEncoder().encode(sync)); await w.close();
    }""", [SEED, json.dumps({"libraryId": LIB_ID, "hub": "https://pi.local:8443", "version": 0})])
    await page.click('#open-btn')
    await page.wait_for_timeout(400)
    return browser, page, errors


async def set_state(page, st):
    await page.evaluate("(s) => { window.__SYNC.state = s; }", st)


async def tick(page):
    await page.evaluate("window.__DEBUG_syncNow()")
    await page.wait_for_timeout(150)


async def status(page):
    return (await page.inner_text('#status')).strip()


async def status_class(page):
    return await page.get_attribute('#status', 'class')


def elapsed_of(text):
    """Seconds shown in the uploading line, or None when it isn't the uploading line."""
    m = UPLOADING_RE.match(text.split('\n')[0].strip()) if text else None
    if not m:
        # The line can carry a second sentence (waiting, problem): the elapsed time comes first.
        m = re.match(r'^Uploading to the Pi… (\d+):(\d\d)', text or '')
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


async def state_calls_between(page, seconds):
    """State requests made during the next `seconds` seconds of real time."""
    before = await page.evaluate("window.__STATE_CALLS.length")
    await page.wait_for_timeout(int(seconds * 1000))
    return await page.evaluate("window.__STATE_CALLS.length") - before


async def scenario_uploading_then_done(p, done_uploading=None):
    # done_uploading: the `uploading` of the answer that ends it (None: the key left out, as Dossiary Sync sends it).
    print("the done answer is", 'without the uploading key' if done_uploading is None else 'an explicit uploading: false', "-- set up:", True)
    browser, page, errors = await open_app(p, state())
    await tick(page)
    text = await status(page)
    print("uploading line shown:", elapsed_of(text) is not None, text)
    print("...with a spinner:", await page.locator('#status .spinner').count() == 1)
    print("...kind busy:", 'busy' in (await status_class(page) or ''), await status_class(page))
    first = elapsed_of(text)
    await page.evaluate("window.__SPINNER = document.querySelector('#status .spinner'); window.__TITLE = document.getElementById('status').title;")
    await page.wait_for_timeout(2300)
    later = elapsed_of(await status(page))
    print("elapsed time advances:", later is not None and first is not None and later >= first + 2, first, later)
    print("...the spinner is not re-created each second:", await page.evaluate("document.querySelector('#status .spinner') === window.__SPINNER"))
    # Polled every 2 s while uploading (every 5 s otherwise): in 4.6 s at least 2 state requests.
    n = await state_calls_between(page, 4.6)
    print("state polled every 2 s while uploading:", n >= 2, n)

    await set_state(page, state(version=1, uploading=done_uploading))
    await tick(page)
    text = await status(page)
    print("done line:", text == DONE_TEXT, text)
    print("...kind ok:", 'ok' in (await status_class(page) or ''), await status_class(page))
    print("...no spinner:", await page.locator('#status .spinner').count() == 0)
    await page.wait_for_timeout(1500)
    print("...the ticker stopped (line unchanged):", await status(page) == DONE_TEXT)
    n = await state_calls_between(page, 5.5)
    print("back to polling every 5 s:", 1 <= n <= 2, n)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_uploading_then_done_explicit_false(p):
    await scenario_uploading_then_done(p, done_uploading=False)


async def scenario_hub_unreachable(p):
    browser, page, errors = await open_app(p, state(hub=False))
    await tick(page)
    text = await status(page)
    print("waiting line:", WAITING_TEXT in text, text)
    first = elapsed_of(text)
    print("...elapsed shown with it:", first is not None, text)
    await page.wait_for_timeout(2300)
    text = await status(page)
    later = elapsed_of(text)
    print("...elapsed keeps running:", later is not None and first is not None and later >= first + 2, first, later)
    print("...still the waiting line:", WAITING_TEXT in text, text)
    await set_state(page, state(hub=True))
    await tick(page)
    text = await status(page)
    print("recovered: back to the plain uploading line:", UPLOADING_RE.match(text) is not None and WAITING_TEXT not in text, text)
    print("...elapsed not restarted:", (elapsed_of(text) or 0) >= (later or 99), elapsed_of(text), later)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_last_error(p):
    browser, page, errors = await open_app(p, state(last_error='<b>disk</b> full & "x"'))
    await tick(page)
    text = await status(page)
    print("problem line:", 'The upload has a problem: <b>disk</b> full & "x"' in text, text)
    print("...elapsed line kept:", elapsed_of(text) is not None, text)
    print("...error shown as text, not HTML:", await page.locator('#status b').count() == 0)
    print("...kind err:", 'err' in (await status_class(page) or ''), await status_class(page))
    first = elapsed_of(text)
    await page.wait_for_timeout(1300)
    later = elapsed_of(await status(page))
    print("...elapsed keeps ticking:", later is not None and first is not None and later >= first + 1, first, later)
    await set_state(page, state(last_error=''))
    await tick(page)
    text = await status(page)
    print("error cleared: back to normal:", UPLOADING_RE.match(text) is not None and 'problem' not in text, text)
    print("...kind busy again:", 'busy' in (await status_class(page) or ''), await status_class(page))
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_replaced_line_returns(p):
    browser, page, errors = await open_app(p, state())
    await tick(page)
    print("uploading line shown:", elapsed_of(await status(page)) is not None, await status(page))
    # Another message takes the line (a save).
    await page.click('tr[data-id="1"]')
    await page.wait_for_timeout(150)
    await page.click('#edit-doc-btn')
    await page.wait_for_timeout(250)
    await page.fill('#e-title', 'Invoice 2')
    await page.click('#save-edit-btn')
    await page.wait_for_timeout(300)
    other = await status(page)
    print("another message replaced the line:", elapsed_of(other) is None, other)
    # The first change of the line after that must come from a poll, never from the 1 s ticker.
    await page.evaluate("""() => {
        const calls = window.__STATE_CALLS.length;
        window.__FIRST_CHANGE_AFTER_POLL = null;
        const obs = new MutationObserver(() => {
            if(window.__FIRST_CHANGE_AFTER_POLL === null) window.__FIRST_CHANGE_AFTER_POLL = window.__STATE_CALLS.length > calls;
            obs.disconnect();
        });
        obs.observe(document.getElementById('status'), { childList: true, subtree: true, characterData: true });
    }""")
    await page.wait_for_timeout(2800)
    print("...the ticker does not write over it (the first change follows a poll):", await page.evaluate("window.__FIRST_CHANGE_AFTER_POLL") is True)
    print("...the upload line returns on the next poll:", elapsed_of(await status(page)) is not None, await status(page))
    # A language change keeps it (retranslated).
    await page.select_option('#lang-select', 'de')
    await page.wait_for_timeout(300)
    de = await status(page)
    print("German line after a language change:", de.startswith('Wird auf den Pi hochgeladen…'), de)
    await page.wait_for_timeout(1300)
    de2 = await status(page)
    print("...still ticking in German:", de2.startswith('Wird auf den Pi hochgeladen…') and de2 != de, de, de2)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_nothing_new(p):
    # No admin token: no state request, no upload line.
    browser, page, errors = await open_app(p, state(), token=None)
    before = await status(page)
    await tick(page)
    await page.wait_for_timeout(2300)
    print("no token: no state request:", await page.evaluate("window.__STATE_CALLS.length") == 0)
    print("...status unchanged:", await status(page) == before, before)
    print("...no page errors:", not errors, errors)
    await browser.close()
    for label, st in (('404', 'missing'), ('not JSON', 'garbage'), ('no uploading field', {"libraryId": LIB_ID, "version": 0, "lease": None}),
                      ('uploading not a boolean', dict(state(), uploading='yes')), ('not uploading (false)', state(version=4, uploading=False)),
                      ('not uploading (key left out), version 4', state(version=4, uploading=None)),
                      ('not uploading (key left out), version 0', state(version=0, uploading=None))):
        browser, page, errors = await open_app(p, st)
        before = await status(page)
        await tick(page)
        await page.wait_for_timeout(1300)
        text = await status(page)
        print(f"{label}: no upload line:", text == before and 'Pi' not in text, text)
        n = await state_calls_between(page, 3.0)
        print(f"...polling stays at 5 s:", n <= 1, n)
        print("...no page errors:", not errors, errors)
        await browser.close()


async def scenario_switch_library_stops(p):
    browser, page, errors = await open_app(p, state())
    await tick(page)
    print("uploading line shown:", elapsed_of(await status(page)) is not None, await status(page))
    await page.click('#reload-btn')   # Switch library: closes this one
    await page.wait_for_timeout(300)
    after_close = await status(page)
    calls = await page.evaluate("window.__STATE_CALLS.length")
    await page.wait_for_timeout(2500)
    print("closed: no further status updates:", await status(page) == after_close, after_close, await status(page))
    print("...no further state requests:", await page.evaluate("window.__STATE_CALLS.length") == calls)
    # Another, unsynced library opens: its own message stays.
    await page.evaluate("""(seed) => { const r = window.__makeSeededRoot(seed); r.name = 'Other.dossiary'; window.__TEST_ROOT = r; }""", SEED)
    await page.click('#open-btn')
    await page.wait_for_timeout(500)
    opened = await status(page)
    await page.wait_for_timeout(2500)
    print("another library: its message is left alone:", await status(page) == opened and 'Pi' not in opened, opened)
    print("...no spinner:", await page.locator('#status .spinner').count() == 0)
    print("no page errors:", not errors, errors)
    await browser.close()


async def scenario_share_grace(p):
    # Right after a share the first answers may not say uploading yet (key left out, version 0): the 2 s poll
    # and the share's start time are kept for 30 s, a late uploading: true continues the elapsed time.
    browser, page, errors = await open_app(p, state(uploading=None))
    before = await status(page)
    print("share finished (hook):", await page.evaluate("window.__DEBUG_uploadShareFinished(0)"))
    await tick(page)
    print("no flag yet: no upload line, no message:", await status(page) == before, await status(page))
    n = await state_calls_between(page, 4.6)
    print("...the 2 s poll is kept:", n >= 2, n)
    await set_state(page, state())
    await tick(page)
    text = await status(page)
    e = elapsed_of(text)
    print("a late uploading: true continues the time from the share (not 0:00):", e is not None and e >= 4, text)
    await set_state(page, state(version=1, uploading=None))
    await tick(page)
    print("...and the key left out at version 1 is done:", await status(page) == DONE_TEXT, await status(page))
    await browser.close()

    # The grace runs out: back to the 5 s poll without a message.
    browser, page, errors2 = await open_app(p, state(uploading=None))
    before = await status(page)
    await page.evaluate("window.__DEBUG_uploadShareFinished(29000)")
    await page.wait_for_timeout(3500)   # the 2 s poll answers after the 30 s
    n = await state_calls_between(page, 5.5)
    print("grace over: back to polling every 5 s:", 1 <= n <= 2, n)
    print("...without a message:", await status(page) == before and 'Pi' not in await status(page), await status(page))
    await browser.close()

    # A small library done before the first poll after the share: the done line.
    browser, page, errors3 = await open_app(p, state(version=1, uploading=None))
    await page.evaluate("window.__DEBUG_uploadShareFinished(0)")
    await tick(page)
    print("done before the first poll after a share: the done line:", await status(page) == DONE_TEXT, await status(page))
    print("no page errors:", not (errors + errors2 + errors3), errors + errors2 + errors3)
    await browser.close()


async def main():
    import sys
    only = sys.argv[1:]
    async with async_playwright() as p:
        for scenario in (scenario_uploading_then_done, scenario_uploading_then_done_explicit_false, scenario_hub_unreachable,
                         scenario_last_error, scenario_replaced_line_returns, scenario_nothing_new, scenario_switch_library_stops,
                         scenario_share_grace):
            if only and not any(o in scenario.__name__ for o in only):
                continue
            print(f"--- {scenario.__name__}")
            await scenario(p)

asyncio.run(main())
