import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio
from playwright.async_api import async_playwright

# The stub's createWritable() must behave like the real stream: every write()
# appends, close() commits, abort() discards. The zip export depends on it.
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        result = await page.evaluate("""async () => {
            const dir = window.__makeEmptyRoot();
            const h = await dir.getFileHandle('a.bin', { create: true });
            let w = await h.createWritable();
            await w.write(new Uint8Array([1, 2]));
            await w.write(new Uint8Array([9, 3, 4, 9]).subarray(1, 3));
            await w.write('AB');
            await w.write(new Uint8Array([5]).buffer);
            await w.write(new Blob([new Uint8Array([6])]));
            await w.close();
            const first = Array.from(new Uint8Array(await (await h.getFile()).arrayBuffer()));
            w = await h.createWritable();
            await w.write(new Uint8Array([7]));
            await w.abort();
            const afterAbort = Array.from(new Uint8Array(await (await h.getFile()).arrayBuffer()));
            return { first, afterAbort };
        }""")
        print("Writes append, views use only their own bytes:", result['first'] == [1, 2, 3, 4, 65, 66, 5, 6], result['first'])
        print("abort() keeps the earlier contents:", result['afterAbort'] == [1, 2, 3, 4, 65, 66, 5, 6])
        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
