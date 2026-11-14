import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))

# Writes export-bundle-cases.json for the Mac app (dossiary-osx): the bundle names (bundleNames) and the "How to open.txt"
# text (bundleReadmeText) in every UI language, computed by the page's own functions (window.__DEBUG_bundleNames,
# window.__DEBUG_bundleReadmeText), so the Swift port (MacCore LibraryBundle) can be checked against it. Not part of the suite.
# Regenerate after a change to the page's bundle texts. Usage:
#   python3 export_bundle_cases.py [output.json]
# Default output: ../../dossiary-osx/MacCore/Tests/MacCoreTests/Fixtures/export-bundle-cases.json

import asyncio, json, re, sys
from playwright.async_api import async_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else _os.path.abspath(_os.path.join(
    '..', '..', 'dossiary-osx', 'MacCore', 'Tests', 'MacCoreTests', 'Fixtures', 'export-bundle-cases.json'))

LANGS = ['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']
NAMES = ['Tax 2025', 'Old.DOSSIARY', 'Old.dossiary', '  Spaced out  ', 'Tax 2025.dossiary ', 'a.dossiary.dossiary', 'Ünï · 发票 · Հաշիվ',
         '(export) Copy', 'x', 'My.Dossiary']
LIBS = ['Tax 2025.dossiary', 'Steuer.dossiary', 'Ünï 发票 Հաշիվ.dossiary', 'Old.DOSSIARY']

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
        out = {'names': [], 'readmes': []}
        for raw in NAMES:
            out['names'].append({'raw': raw, 'expected': await page.evaluate("(r) => window.__DEBUG_bundleNames(r)", raw)})
        for lang in LANGS:
            await page.select_option('#lang-select', lang)
            await page.wait_for_timeout(100)
            for lib in LIBS:
                text = await page.evaluate("(l) => window.__DEBUG_bundleReadmeText(l)", lib)
                out['readmes'].append({'lang': lang, 'library': lib, 'expected': text})
        await browser.close()
        assert not errors, errors

        assert out['names'][0]['expected'] == {'library': 'Tax 2025.dossiary', 'bundle': 'Tax 2025', 'zip': 'Tax 2025.zip'}, out['names'][0]
        assert out['names'][1]['expected']['bundle'] == 'Old', out['names'][1]
        en = [r for r in out['readmes'] if r['lang'] == 'en'][0]['expected']
        assert 'Open or create a library…' in en and '----' not in en, en
        de = [r for r in out['readmes'] if r['lang'] == 'de'][0]['expected']
        assert '\n\n----\n\n' in de and 'Bibliothek öffnen oder anlegen…' in de, de

        version = re.search(r"const APP_VERSION = '([^']+)'", open(APP_PATH, encoding='utf-8').read()).group(1)
        out = {'generatedBy': 'Dossiary/tests/export_bundle_cases.py', 'pageVersion': version, **out}
        _os.makedirs(_os.path.dirname(OUT), exist_ok=True)
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
            f.write('\n')
        print(f"ok: {len(out['names'])} names, {len(out['readmes'])} readmes -> {OUT}")

asyncio.run(main())
