import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, io, zipfile
from playwright.async_api import async_playwright

# The built-in zip writer behind "Export as library" bundles: stored entries,
# UTF-8 names, CRC32, and ZIP64 records -- read back with Python's zipfile.
def read_zip(data):
    return zipfile.ZipFile(io.BytesIO(bytes(data)))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)

        print("CRC32 of '123456789' is the standard check value:", await page.evaluate("() => window.__DEBUG_crc32('123456789')") == 0xCBF43926)

        entries = [["Tax 2025/How to open.txt", "Open it in Chrome.\n"],
                   ["Tax 2025/Tax 2025.dossiary/files/4_Հաշիվ_发票.pdf", "%PDF fake"],
                   ["Tax 2025/empty.txt", ""]]
        z = read_zip(await page.evaluate("(e) => window.__DEBUG_buildZip(e)", entries))
        print("Every entry listed, in order:", z.namelist() == [e[0] for e in entries], z.namelist())
        print("Contents read back:", all(z.read(n).decode() == c for n, c in entries))
        print("CRCs check out:", z.testzip() is None)
        print("Stored, not compressed:", all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist()))
        print("Names flagged as UTF-8:", all(i.flag_bits & 0x800 for i in z.infolist()))

        raw = await page.evaluate("(e) => window.__DEBUG_buildZip(e, { zip64Bytes: 4, zip64Entries: 2 })", entries)
        print("Lowered limits write ZIP64 end records:", b'PK\x06\x06' in bytes(raw) and b'PK\x06\x07' in bytes(raw))
        z = read_zip(raw)
        print("ZIP64 zip reads back:", z.namelist() == [e[0] for e in entries] and all(z.read(n).decode() == c for n, c in entries) and z.testzip() is None)
        print("Limits restored afterwards:", b'PK\x06\x06' not in bytes(await page.evaluate("(e) => window.__DEBUG_buildZip(e)", entries)))

        z = read_zip(await page.evaluate("() => window.__DEBUG_buildZip([])"))
        print("An empty zip is valid:", z.namelist() == [])

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
