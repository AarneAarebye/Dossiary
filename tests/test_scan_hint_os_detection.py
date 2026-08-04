import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

# Covers detectOS()/scanHintHtml(): the scan-hint text used to hardcode macOS
# instructions (Image Capture / Preview) regardless of what OS the person is
# actually running Chrome/Edge on -- wrong and confusing for Windows/Linux users.
# navigator.userAgentData.platform is overridden per scenario (or navigator.platform/
# userAgent, for the "no signal at all" case) via an init script injected before
# stub_studio2.js and the app itself, since neither Playwright's user_agent context
# option nor the real host OS this test happens to run on should determine the result.

async def get_hint_text(platform_override, clear_navigator_platform=False):
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

        override_js = f"""
            Object.defineProperty(navigator, 'userAgentData', {{
                value: {{ platform: {platform_override!r} }}, configurable: true
            }});
        """
        if clear_navigator_platform:
            override_js += """
                Object.defineProperty(navigator, 'platform', { value: '', configurable: true });
                Object.defineProperty(navigator, 'userAgent', { value: '', configurable: true });
            """
        await page.add_init_script(override_js)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.click('#scan-hint-toggle')
        text = await page.locator('#scan-hint').inner_text()
        await browser.close()
        return text, errors

async def main():
    all_errors = []

    macos_text, errors = await get_hint_text('macOS')
    all_errors += errors
    print("macOS mentions Image Capture:", 'Image Capture' in macos_text)
    print("macOS mentions Preview:", 'Preview' in macos_text)
    print("macOS does NOT mention Windows Scan:", 'Windows Scan' not in macos_text)
    assert 'Image Capture' in macos_text and 'Preview' in macos_text

    windows_text, errors = await get_hint_text('Windows')
    all_errors += errors
    print("Windows mentions Windows Scan:", 'Windows Scan' in windows_text)
    print("Windows does NOT mention Image Capture:", 'Image Capture' not in windows_text)
    assert 'Windows Scan' in windows_text and 'Image Capture' not in windows_text

    linux_text, errors = await get_hint_text('Linux')
    all_errors += errors
    print("Linux gets the generic fallback:", "your scanner's own software" in linux_text)
    print("Linux does NOT mention Image Capture or Windows Scan:",
          'Image Capture' not in linux_text and 'Windows Scan' not in linux_text)
    assert "your scanner's own software" in linux_text
    assert 'Image Capture' not in linux_text and 'Windows Scan' not in linux_text

    unknown_text, errors = await get_hint_text('', clear_navigator_platform=True)
    all_errors += errors
    print("No OS signal at all falls back to generic text:", "your scanner's own software" in unknown_text)
    assert "your scanner's own software" in unknown_text

    # Every scenario ends the same way regardless of OS -- the actual instruction
    # ("use the file picker above") shouldn't vary.
    for label, text in [("macOS", macos_text), ("Windows", windows_text), ("Linux", linux_text)]:
        has_common_tail = 'Click to choose a file' in text
        print(f"{label} still points back at the file picker:", has_common_tail)
        assert has_common_tail

    print("JS ERRORS:", all_errors)

asyncio.run(main())
