import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

# Covers a real reported gap: unlike files/, the inbox/ folder was never actually
# created by the app itself -- checkInbox() reads it with {create: false} and
# silently treats a missing folder as "nothing to review," which is correct for
# *checking*, but nothing ever brought the folder into existence in the first
# place, so a person couldn't just drag a file into it by hand (or point
# scan_watch.py's --drop-folder at it) without first creating it manually. Both
# initNewLibrary() and openLibrary()'s existing-library path now create inbox/
# alongside files/, same as files/ already was.

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

        # === Brand new library (initNewLibrary()) ===
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)
        new_lib_has_inbox = await page.evaluate("window.__TEST_ROOT._children.has('inbox')")
        print("inbox/ created for a brand new library:", new_lib_has_inbox)
        assert new_lib_has_inbox, "initNewLibrary() should create inbox/ alongside files/"

        # === Existing library that predates this fix (no inbox/ yet) ===
        # The app has no "switch library" control once one is open (by design -- see
        # CLAUDE.md's note on not persisting the folder handle), so reload the page
        # to get back to a fresh "Open library folder" state, same as test_studio.py
        # does with a second page for its own second-library scenario.
        await page.reload()
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeSeededRoot({});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)
        existing_lib_has_inbox = await page.evaluate("window.__TEST_ROOT._children.has('inbox')")
        print("inbox/ created when opening a pre-existing library that lacked one:", existing_lib_has_inbox)
        assert existing_lib_has_inbox, "openLibrary() should create inbox/ for existing libraries that don't have one yet"

        # Sanity: the inbox banner still correctly stays hidden (folder exists but is empty).
        banner_visible = await page.locator('#inbox-banner').is_visible()
        print("inbox banner stays hidden for a freshly-created, empty inbox/:", not banner_visible)
        assert not banner_visible

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
