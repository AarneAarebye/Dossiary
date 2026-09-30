import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Back up library: the whole library folder copied into a new dated folder
# inside a folder the person picks (never inside the library itself), with a
# reminder on the "Opened library" status line when a backup is due.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Scan", "category": None, "document_type": None,
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": "files/1_a/a.pdf",
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
}

LIST_JS = """
    async (root) => {
        const out = [];
        const walk = async (dir, prefix) => {
            for await (const [name, h] of dir.entries()){
                if(h.kind === 'directory') await walk(h, prefix + name + '/');
                else out.push(prefix + name);
            }
        };
        await walk(root, '');
        return out.sort();
    }
"""

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 900})
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
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'MyLib';")
        await page.evaluate("""
            async () => {
                const put = async (path, text) => {
                    const parts = path.split('/');
                    let dir = window.__TEST_ROOT;
                    for(const part of parts.slice(0, -1)) dir = await dir.getDirectoryHandle(part, { create: true });
                    const w = await (await dir.getFileHandle(parts[parts.length - 1], { create: true })).createWritable();
                    await w.write(new TextEncoder().encode(text)); await w.close();
                };
                await put('files/1_a.pdf', 'active pdf');
                await put('files/1_a/a.pdf', 'original pdf');
                await put('files/1_a.txt', 'sidecar');
                await put('thumbnails/1.png', 'thumb');
                await put('inbox/staged.pdf', 'staged');
                await put('.DS_Store', 'junk');
                window.__BACKUP_PARENT = window.__makeEmptyRoot();
                window.__BACKUP_PARENT.name = 'External disk';
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(500)

        # === Scenario 1: the reminder on open, when there has never been a backup ===
        status = await page.inner_text('#status')
        print("Opening a never-backed-up library adds a reminder to the status line:", 'Opened' in status and 'No backup of this library yet' in status, repr(status))

        # === Scenario 2: a folder inside the library is refused ===
        await page.click('#tools-btn'); await page.click('#backup-btn')
        await page.wait_for_timeout(200)
        print("Dialog says there's no backup yet:", 'No backup' in await page.inner_text('#backup-last'))
        await page.evaluate("async () => { window.__NEXT_PICKED_DIR = await window.__TEST_ROOT.getDirectoryHandle('files'); }")
        await page.click('#backup-start-btn')
        await page.wait_for_timeout(300)
        print("A folder inside the library is refused:", 'inside' in await page.inner_text('#backup-status'))

        # === Scenario 3: a backup copies everything into a new dated folder ===
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__BACKUP_PARENT; }")
        await page.click('#backup-start-btn')
        await page.wait_for_timeout(800)
        status = await page.inner_text('#backup-status')
        folders = await page.evaluate("async () => { const n = []; for await (const [k] of window.__BACKUP_PARENT.entries()) n.push(k); return n; }")
        print("One new folder named after the library and the date:", len(folders) == 1 and folders[0].startswith('MyLib backup 20'), folders)
        copied = await page.evaluate("async (name) => {" + LIST_JS.replace("async (root) => {", "const root = await window.__BACKUP_PARENT.getDirectoryHandle(name);") , folders[0])
        print("Every library file is copied, macOS clutter skipped:",
              copied == ['files/1_a.pdf', 'files/1_a.txt', 'files/1_a/a.pdf', 'inbox/staged.pdf', 'library.sqlite', 'thumbnails/1.png'], copied)
        same = await page.evaluate("""async (name) => {
            const root = await window.__BACKUP_PARENT.getDirectoryHandle(name);
            const files = await root.getDirectoryHandle('files');
            return await (await (await (await files.getDirectoryHandle('1_a')).getFileHandle('a.pdf')).getFile()).text();
        }""", folders[0])
        print("...byte for byte:", same == 'original pdf')
        db_copy = await page.evaluate("async (name) => JSON.parse(await (await (await (await window.__BACKUP_PARENT.getDirectoryHandle(name)).getFileHandle('library.sqlite')).getFile()).text())", folders[0])
        print("The copied database holds the documents:", [d['title'] for d in db_copy['documents']] == ['Scan'])
        print("Status reports the count and where:", 'Backed up 6 files to “External disk/MyLib backup' in status, repr(status))
        print("Last-backup date shown:", 'Last backup' in await page.inner_text('#backup-last'))
        await page.click('#backup-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 4: a second backup in the same minute gets its own folder ===
        await page.click('#tools-btn'); await page.click('#backup-btn')
        await page.wait_for_timeout(200)
        await page.evaluate("() => { window.__NEXT_PICKED_DIR = window.__BACKUP_PARENT; }")
        await page.click('#backup-start-btn')
        await page.wait_for_timeout(800)
        folders = await page.evaluate("async () => { const n = []; for await (const [k] of window.__BACKUP_PARENT.entries()) n.push(k); return n.sort(); }")
        print("A second backup never reuses the first folder:", len(folders) == 2 and folders[1].endswith('(2)'), folders)
        await page.click('#backup-cancel-btn')
        await page.wait_for_timeout(150)

        # === Scenario 5: after a backup, opening the library shows no reminder ===
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("No reminder right after a backup:", 'backup' not in (await page.inner_text('#status')).lower())

        # === Scenario 6: overdue reminder, and switching reminders off ===
        await page.evaluate("async () => { window.__DEBUG_dbRun(\"INSERT OR REPLACE INTO settings (key, value) VALUES ('last_backup_at', ?)\", [new Date(Date.now() - 40 * 86400000).toISOString()]); }")
        await page.click('#tools-btn'); await page.click('#backup-btn')
        await page.wait_for_timeout(200)
        await page.fill('#backup-reminder-days', '60')
        await page.dispatch_event('#backup-reminder-days', 'change')
        await page.wait_for_timeout(200)
        await page.click('#backup-cancel-btn')
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("40 days since the last backup is fine with a 60-day reminder:", 'backup' not in (await page.inner_text('#status')).lower())
        await page.click('#tools-btn'); await page.click('#backup-btn')
        await page.wait_for_timeout(200)
        await page.fill('#backup-reminder-days', '30')
        await page.dispatch_event('#backup-reminder-days', 'change')
        await page.wait_for_timeout(200)
        await page.click('#backup-cancel-btn')
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("...but due with a 30-day one:", 'Last backup 40 days ago' in await page.inner_text('#status'))
        await page.select_option('#lang-select', 'de')
        await page.wait_for_timeout(200)
        print("...and the reminder follows a language switch:", 'Letzte Sicherung vor 40 Tagen' in await page.inner_text('#status'))
        await page.select_option('#lang-select', 'en')
        await page.wait_for_timeout(200)
        await page.click('#tools-btn'); await page.click('#backup-btn')
        await page.wait_for_timeout(200)
        await page.fill('#backup-reminder-days', '0')
        await page.dispatch_event('#backup-reminder-days', 'change')
        await page.wait_for_timeout(200)
        await page.click('#backup-cancel-btn')
        await page.click('#reload-btn'); await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("0 switches the reminder off:", 'backup' not in (await page.inner_text('#status')).lower())

        # === Scenario 7: Stop removes the incomplete copy ===
        await page.evaluate("""async () => {
            const files = await window.__TEST_ROOT.getDirectoryHandle('files');
            const h = await files.getFileHandle('1_a.pdf');
            const orig = h.getFile.bind(h);
            h.getFile = async () => { await new Promise(r => setTimeout(r, 1200)); return orig(); };
            window.__STOP_PARENT = window.__makeEmptyRoot();
            window.__NEXT_PICKED_DIR = window.__STOP_PARENT;
        }""")
        await page.click('#tools-btn'); await page.click('#backup-btn')
        await page.wait_for_timeout(200)
        await page.click('#backup-start-btn')
        await page.wait_for_timeout(300)
        await page.keyboard.press('Escape')
        print("Backup dialog can't be closed while copying:", await page.locator('#backup-status').count() == 1)
        await page.click('#backup-stop-btn')
        await page.wait_for_timeout(1800)
        left = await page.evaluate("async () => { const n = []; for await (const [k] of window.__STOP_PARENT.entries()) n.push(k); return n; }")
        print("Stopping removes the incomplete copy:", left == [] and 'incomplete copy was removed' in await page.inner_text('#backup-status'), left)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
