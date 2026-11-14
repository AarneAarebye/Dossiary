import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths work regardless of the CWD this test is invoked from
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))

import asyncio
from playwright.async_api import async_playwright

# A title with an invisible format character (here a zero-width space, found in a real library) made Chrome refuse the
# export file name ("Name is not allowed"). The export names drop such characters.
async def main():
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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        names = await page.evaluate("""() => {
            const h = window.__DEBUG_exportFolderNames;
            const doc = (title, path) => ({ id: 7, title, date: '2022-09-21T10:00:00+00:00', file_path: path });
            return {
                zwsp: h.exportFileName(doc('21 Sept, 08.30\\u200b consultation with Martin', 'files/7_a.aac')),
                marks: h.exportFileName(doc('a\\u200eb\\u200fc\\u202ad\\u2060e\\ufefff\\u00adg', 'files/7_a.pdf')),
                plain: h.exportFileName(doc('Invoice: 2022/09', 'files/7_a.pdf')),
                onlyInvisible: h.exportFileName({ id: 7, title: '\\u200b\\u200b', date: null, file_path: 'files/7_a.pdf' }),
                folder: h.sanitizeFolderName('Arne\\u200b\\u2019s / Collection'),
            };
        }""")
        assert names['zwsp'] == '2022-09-21 21 Sept, 08.30 consultation with Martin.aac', names
        assert names['marks'] == '2022-09-21 abcdefg.pdf', names
        assert names['plain'] == '2022-09-21 Invoice- 2022-09.pdf', names
        assert names['onlyInvisible'].endswith('.pdf') and '​' not in names['onlyInvisible'], names
        assert names['folder'] == 'Arne’s - Collection', names
        assert not errors, errors
        await browser.close()
        print("ok")

asyncio.run(main())
