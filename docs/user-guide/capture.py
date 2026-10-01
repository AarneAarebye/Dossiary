"""Recapture the User Guide screenshots for every language.

Drives the real dossiary.html (real sql.js, Tesseract.js and pdf.js from the
CDN) served on localhost, in a fresh headless Chromium profile per language.
The only thing replaced is the native folder picker: showDirectoryPicker()
returns a "Documents" folder in the origin-private file system (OPFS), a real
FileSystemDirectoryHandle, so no one has to click through a dialog.

The demo library is fabricated (demo/*.png: a made-up invoice, letter,
receipt and inbox scan) -- never capture from a real library.

Usage: python3 docs/user-guide/capture.py [all|en,de,...] [output-dir]
Needs Playwright for Python and network access for the CDN libraries.
"""
import asyncio, os, sys, subprocess, time, base64
from playwright.async_api import async_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DEMO = os.path.join(HERE, 'demo')
PORT = 8833
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(REPO, 'docs', 'user-guide')
ONLY = sys.argv[1].split(',') if len(sys.argv) > 1 and sys.argv[1] != 'all' else ['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant']

EN_NAMES = {'no-library': '01-no-library', 'empty-folder': '02-empty-folder', 'library-ready': '03-library-ready',
            'capture-blank': '04-capture-blank', 'capture-ocr': '05-capture-ocr', 'capture-filled': '06-capture-filled',
            'table': '07-table', 'search': '08-search', 'inbox': '09-inbox', 'review-detail': '10-review-detail',
            'reports': '11-reports', 'collections': '12-collections'}
OTHER_NAMES = {'no-library': '01-no-library', 'table': '02-table', 'capture-blank': '03-capture-blank',
               'capture-ocr': '04-capture-ocr', 'capture-filled': '05-capture-filled', 'search': '06-search',
               'inbox': '07-inbox', 'review-detail': '08-review-detail', 'reports': '09-reports'}

DOCS = [
    dict(file='nordlicht_invoice_1042.png', type='Invoice', title='Nordlicht Hardware Invoice #1042', date='2026-03-03',
         category='Home', tags='hardware, warranty', amount='121.20'),
    dict(file='stadtwerke_statement.png', type='Letter', title='Stadtwerke Musterstadt Statement', date='2026-02-15',
         category='Home', tags='utilities', amount='73.50'),
    dict(file='marktfrisch_receipt.png', type='Receipt', title='Marktfrisch Grocery Receipt', date='2026-03-20',
         category='Groceries', tags='weekly shop', amount='15.66'),
]

INIT = """
window.showDirectoryPicker = async () => {
  const root = await navigator.storage.getDirectory();
  return root.getDirectoryHandle('Documents', { create: true });
};
document.addEventListener('DOMContentLoaded', () => {
  const s = document.createElement('style');
  s.textContent = '.scanline{display:none !important} *{caret-color:transparent !important}';
  document.head.appendChild(s);
});
"""

async def capture(browser, lang):
    names = EN_NAMES if lang == 'en' else OTHER_NAMES
    outdir = os.path.join(OUT, lang)
    os.makedirs(outdir, exist_ok=True)
    ctx = await browser.new_context(viewport={'width': 1440, 'height': 770}, device_scale_factor=1,
        locale={'en': 'en-US', 'de': 'de-DE', 'es': 'es-ES', 'fr': 'fr-FR', 'zh-Hans': 'zh-CN', 'zh-Hant': 'zh-TW'}[lang])
    page = await ctx.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    await page.add_init_script(f"try{{ localStorage.setItem('dossiary_lang', '{lang}'); }}catch(e){{}}" + INIT)
    await page.goto(f'http://localhost:{PORT}/dossiary.html')
    await page.wait_for_timeout(800)

    async def shot(key):
        if key not in names: return
        await page.mouse.move(1430, 760)
        await page.wait_for_timeout(500)
        await page.screenshot(path=os.path.join(outdir, names[key] + '.png'))
        print(f'  {lang}/{names[key]}.png')

    await shot('no-library')
    await page.click('#open-btn')
    await page.wait_for_selector('#init-state', state='visible')
    await page.wait_for_timeout(300)
    await shot('empty-folder')
    await page.click('#create-library-btn')
    await page.wait_for_selector('#toolbar', state='visible', timeout=60000)
    await page.wait_for_timeout(800)
    await page.evaluate("() => { const s = document.getElementById('status'); if(s) s.textContent = ''; }")
    await shot('library-ready')

    # Give the three demo types Amount and Currency fields, the way Field
    # Settings would, then reopen the library so they're loaded.
    await page.evaluate("""() => {
        const run = window.__DEBUG_dbRun;
        for(const type of ['Invoice', 'Letter', 'Receipt']){
            run('INSERT INTO document_type_fields (document_type, field_name, position) VALUES (?, ?, ?)', [type, 'Amount', 0]);
            run('INSERT INTO document_type_fields (document_type, field_name, position) VALUES (?, ?, ?)', [type, 'Currency', 1]);
        }
        document.getElementById('grid-size-range').dispatchEvent(new Event('change')); // saves the library
    }""")
    await page.wait_for_timeout(800)
    await page.click('#reload-btn')
    await page.wait_for_timeout(400)
    await page.click('.recent-lib-target')
    await page.wait_for_selector('#toolbar', state='visible', timeout=60000)
    await page.wait_for_timeout(800)

    for i, doc in enumerate(DOCS):
        await page.click('#add-btn')
        await page.wait_for_selector('#file-input', state='attached')
        await page.wait_for_timeout(400)
        if i == 0: await shot('capture-blank')
        await page.set_input_files('#file-input', os.path.join(DEMO, doc['file']))
        await page.wait_for_timeout(500)
        await page.click('#run-ocr-btn')
        await page.wait_for_function("() => (document.getElementById('f-ocr-text').value || '').length > 30", timeout=180000)
        await page.wait_for_timeout(800)
        if i == 0:
            await page.evaluate("() => document.querySelector('#modal-root .backdrop')?.scrollTo(0, 0)")
            await shot('capture-ocr')
        await page.fill('#f-type', doc['type'])
        await page.dispatch_event('#f-type', 'change')
        await page.wait_for_timeout(400)
        await page.fill('#f-title', doc['title'])
        await page.fill('#f-date', doc['date'])
        await page.dispatch_event('#f-date', 'input')
        await page.fill('#f-category', doc['category'])
        await page.fill('#f-tags', doc['tags'])
        amount = page.locator('[data-dynamic-field="Amount"] input')
        if await amount.count():
            await amount.fill(doc['amount']); await amount.dispatch_event('input')
        currency = page.locator('[data-dynamic-field="Currency"] input')
        if await currency.count():
            await currency.fill('EUR'); await currency.dispatch_event('input')
        await page.click('.modal h2')  # close any suggestion dropdown
        if i == 0:
            await page.locator('#save-doc-btn').scroll_into_view_if_needed()
            await shot('capture-filled')
        await page.click('#save-doc-btn')
        await page.wait_for_selector('#modal-root .backdrop', state='detached', timeout=60000)
        await page.wait_for_timeout(800)

    await page.evaluate("() => { const s = document.getElementById('status'); if(s) s.textContent = ''; }")
    await shot('table')

    await page.fill('#search', 'warranty')
    await page.wait_for_timeout(600)
    await shot('search')
    await page.fill('#search', '')
    await page.dispatch_event('#search', 'input')
    await page.wait_for_timeout(300)

    # Stage the scan in the library's inbox/ folder, as a scanner or
    # scan_watch.py would, then Check inbox.
    scan_b64 = base64.b64encode(open(os.path.join(DEMO, 'scan_20260321_0001.png'), 'rb').read()).decode()
    await page.evaluate("""async (b64) => {
        const root = await navigator.storage.getDirectory();
        const docs = await root.getDirectoryHandle('Documents');
        let lib = null;
        for await (const [name, h] of docs.entries()) if(h.kind === 'directory' && name.endsWith('.dossiary')) lib = h;
        const inbox = await lib.getDirectoryHandle('inbox', { create: true });
        const w = await (await inbox.getFileHandle('scan_20260321_0001.png', { create: true })).createWritable();
        await w.write(Uint8Array.from(atob(b64), c => c.charCodeAt(0))); await w.close();
    }""", scan_b64)
    await page.click('#inbox-check-btn')
    await page.wait_for_timeout(1500)
    await shot('inbox')

    await page.click('#doc-grid .doc-tile')
    await page.wait_for_timeout(1200)
    await page.evaluate("() => { const s = document.getElementById('status'); if(s) s.textContent = ''; document.querySelector('.detail-actions, #detail-panel-body .modal-actions')?.scrollIntoView({block: 'end'}); window.scrollTo(0, 0); document.querySelectorAll('#main-layout, .table-detail-row, #table-wrap').forEach(n => n.scrollTop = 0); }")
    await page.wait_for_timeout(400)
    await shot('review-detail')

    await page.click('#nav-item-reports')
    await page.wait_for_timeout(800)
    await shot('reports')

    if 'collections' in names:
        await page.click('#nav-item-all')
        await page.wait_for_timeout(500)
        for doc_id in (1, 2, 3):
            await page.check(f'#doc-grid .doc-tile[data-id="{doc_id}"] .row-select-checkbox')
        await page.click('#bulk-add-to-collection-btn')
        await page.click('#bulk-new-collection-option')
        await page.fill('#bulk-new-collection-input', 'Tax 2026')
        await page.click('#bulk-new-collection-save-btn')
        await page.wait_for_timeout(500)
        await page.check('#doc-grid .doc-tile[data-id="1"] .row-select-checkbox')
        await page.click('#bulk-add-to-collection-btn')
        await page.click('#bulk-new-collection-option')
        await page.fill('#bulk-new-collection-input', 'Warranties')
        await page.click('#bulk-new-collection-save-btn')
        await page.wait_for_timeout(500)
        await page.click('#tools-btn')
        await page.click('#manage-collections-btn')
        await page.wait_for_timeout(600)
        await shot('collections')

    if errors: print('  JS errors:', errors)
    await ctx.close()

async def main():
    server = subprocess.Popen([sys.executable, '-m', 'http.server', str(PORT)], cwd=REPO,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            for lang in ONLY:
                print(lang)
                await capture(browser, lang)
            await browser.close()
    finally:
        server.terminate()

asyncio.run(main())
