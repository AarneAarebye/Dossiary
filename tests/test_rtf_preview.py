import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (stub_studio2.js, ...) work regardless of the CWD this test is invoked from
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, ssl, sys, urllib.request
from playwright.async_api import async_playwright

RTFJS_URL = 'https://cdn.jsdelivr.net/npm/rtf.js@3.0.9/dist/RTFJS.bundle.min.js'
try:
    # reachability probe only: python.org builds often lack a CA bundle, so skip certificate checks here (the browser verifies the real load)
    urllib.request.urlopen(RTFJS_URL, timeout=15, context=ssl._create_unverified_context()).read(10)
except Exception as e:
    print(f"SKIP: rtf.js is not reachable from here ({e})")
    sys.exit(0)

SIMPLE_RTF = (rb'{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\pard\fs36\b Hello RTF\b0\par'
              rb'\fs22 A paragraph of ordinary text to draw on the page.\par}')
BROKEN_RTF = b'this is not an rtf document at all'
TOO_BIG_RTF = b'{\\rtf1\\ansi ' + b'a' * (2 * 1024 * 1024 + 10) + b'}'

SEED = {
    "documents": [{
        "id": 1, "title": "Letter", "category": "Test", "subcategory": None,
        "document_type": None, "payment_method": None, "amount": None, "date": None,
        "import_date": None, "notes": None, "ocr_text": None, "ocr_language": None,
        "file_path": "files/1_letter.rtf", "original_file_path": None,
        "created_at": "2026-01-01T00:00:00Z", "source": "migrated", "source_legacy_id": 1,
        "thumbnail_path": None,
    }],
    "tags": [], "document_tags": [], "people": [], "document_people": [], "settings": [],
}

async def thumb_info(page, name):
    return await page.evaluate("""
        async (name) => {
            try {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('thumbnails');
                const f = await (await dir.getFileHandle(name)).getFile();
                const b = new Uint8Array(await f.arrayBuffer());
                return { exists: true, size: b.length, head: [b[0], b[1]] };
            } catch(e) { return { exists: false }; }
        }
    """, name)

async def persisted_docs(page):
    return (await page.evaluate("""
        (async () => {
            const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
            return JSON.parse(await (await fh.getFile()).text());
        })()
    """))['documents']

async def exists(page, name):
    return (await thumb_info(page, name))['exists']

async def wait_until(fn, timeout_s=15):
    """Polls an async predicate every 200 ms; returns its last value (truthy on success)."""
    end = asyncio.get_event_loop().time() + timeout_s
    while True:
        try:
            v = await fn()
        except Exception:
            v = False
        if v or asyncio.get_event_loop().time() >= end:
            return v
        await asyncio.sleep(0.2)

async def row_saved(page, title):
    return any(d['title'] == title for d in await persisted_docs(page))

async def capture(page, title, name, mime, data):
    await page.click('#add-btn')
    await page.wait_for_timeout(100)
    await page.set_input_files('#file-input', files=[{'name': name, 'mimeType': mime, 'buffer': data}])
    await page.wait_for_timeout(100)
    await page.fill('#f-title', title)
    await page.click('#save-doc-btn')
    # the row is persisted and the capture dialog is gone: the save has finished
    await wait_until(lambda: row_saved(page, title))
    await page.wait_for_selector('#save-doc-btn', state='hidden', timeout=15000)

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
                await route.continue_()   # rtf.js comes from the real CDN
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        # === 1: a normal RTF gets a JPEG preview of the right size ===
        await capture(page, 'Simple RTF', 'letter.rtf', 'text/rtf', SIMPLE_RTF)
        await wait_until(lambda: exists(page, '1.jpg'))
        t = await thumb_info(page, '1.jpg')
        print("RTF preview file written:", t['exists'])
        print("RTF preview is a JPEG:", t.get('head') == [255, 216])
        print("RTF preview is more than a blank stub (> 3 KB):", t.get('size', 0) > 3000)
        sizes = await page.evaluate("""
            (async () => {
                const dir = await window.__TEST_ROOT.getDirectoryHandle('thumbnails');
                const f = await (await dir.getFileHandle('1.jpg')).getFile();
                const bmp = await createImageBitmap(f);
                return [bmp.width, bmp.height];
            })()
        """)
        print("RTF preview longest side is 640 px (A4 portrait):", max(sizes) == 640 and sizes[1] > sizes[0])

        # === 2: the type is not needed -- the .rtf name is enough ===
        await capture(page, 'Octet RTF', 'other.rtf', 'application/octet-stream', SIMPLE_RTF)
        await wait_until(lambda: exists(page, '2.jpg'))
        print("RTF with a generic type still gets a preview:", (await thumb_info(page, '2.jpg'))['exists'])

        # === 3: a broken RTF keeps no preview, and nothing throws ===
        await capture(page, 'Broken RTF', 'broken.rtf', 'text/rtf', BROKEN_RTF)
        await page.wait_for_timeout(2000)   # settle: a late thumbnail write would show up now
        docs = await persisted_docs(page)
        broken = [d for d in docs if d['title'] == 'Broken RTF'][0]
        print("broken RTF is saved without a preview:", not broken['thumbnail_path'])
        print("broken RTF left no preview file:", not (await thumb_info(page, '3.jpg'))['exists'])

        # === 4: an RTF over 2 MB keeps no preview ===
        await capture(page, 'Huge RTF', 'huge.rtf', 'text/rtf', TOO_BIG_RTF)
        await page.wait_for_timeout(2000)   # settle: a late thumbnail write would show up now
        docs = await persisted_docs(page)
        huge = [d for d in docs if d['title'] == 'Huge RTF'][0]
        print("RTF over 2 MB is saved without a preview:", not huge['thumbnail_path'])
        print("RTF over 2 MB left no preview file:", not (await thumb_info(page, '4.jpg'))['exists'])

        # === 4b: a control character (RTF \'01) is illegal in XML but must not cost the preview ===
        await capture(page, 'Control char RTF', 'control.rtf', 'text/rtf', rb"{\rtf1\ansi Hello \'01 world\par}")
        await wait_until(lambda: exists(page, '5.jpg'))
        print("RTF with a control character still gets a preview:", (await thumb_info(page, '5.jpg'))['exists'])

        # === 5: "Create missing previews" counts an RTF document ===
        await page.close()
        page = await browser.new_page()
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("console", lambda msg: errors.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js + f"""
        window.__makeRtfRoot = function() {{
            const root = new FakeDirHandle('TestLib');
            const dbBytes = new TextEncoder().encode(JSON.stringify({json.dumps(SEED)}));
            root._children.set('library.sqlite', new FakeFileHandle('library.sqlite', dbBytes));
            const filesDir = new FakeDirHandle('files');
            root._children.set('files', filesDir);
            filesDir._children.set('1_letter.rtf', new FakeFileHandle('1_letter.rtf', new TextEncoder().encode({json.dumps(SIMPLE_RTF.decode())})));
            return root;
        }};
        """)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeRtfRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)
        await page.click("#view-grid-btn")   # the stub opens libraries in list view; the button lives on the grid toolbar
        await page.wait_for_timeout(300)
        btn = page.locator('#create-previews-btn')
        print("Create missing previews button is shown for an RTF:", await btn.is_visible())
        print("button counts 1 document:", '(1)' in (await btn.inner_text()))
        await btn.click()
        await wait_until(lambda: exists(page, '1.jpg'))
        print("bulk job made the RTF preview:", (await thumb_info(page, '1.jpg'))['exists'])

        print("no page or console errors:", errors == [])
        if errors: print(errors)
        await browser.close()

asyncio.run(main())
