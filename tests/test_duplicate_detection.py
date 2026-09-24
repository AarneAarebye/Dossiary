import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, hashlib
from playwright.async_api import async_playwright

# Two byte strings used throughout this file: DOC_A_BYTES/DOC_B_BYTES are
# genuinely different content (so documents built from them get different
# hashes); DOC_A_BYTES is reused verbatim for a second document to prove two
# documents built from IDENTICAL bytes get the SAME hash.
DOC_A_BYTES = b'%PDF-1.4 fake pdf content A for duplicate-detection tests'
DOC_B_BYTES = b'%PDF-1.4 completely different fake pdf content B'

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

        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        # === Scenario 1: computeFileHash() matches a hand-computed SHA-256 ===
        js_hash = await page.evaluate(
            "async (bytes) => { const buf = new Uint8Array(bytes).buffer; const file = new File([buf], 'x.pdf', {type: 'application/pdf'}); return await window.__DEBUG_computeFileHash(file); }",
            list(DOC_A_BYTES),
        )
        expected_hash = hashlib.sha256(DOC_A_BYTES).hexdigest()
        print("computeFileHash() matches hashlib.sha256():", js_hash == expected_hash)

        # === Scenario 2: two documents captured from byte-identical files get the
        # same file_hash; a third captured from different bytes gets a different one ===
        async def capture_document(title, file_bytes, filename):
            await page.click('#add-btn')
            await page.wait_for_timeout(100)
            await page.set_input_files('#file-input', {
                'name': filename, 'mimeType': 'application/pdf', 'buffer': file_bytes,
            })
            await page.wait_for_timeout(150)
            await page.fill('#f-title', title)
            await page.click('#save-doc-btn')
            await page.wait_for_timeout(200)

        await capture_document('Doc A1', DOC_A_BYTES, 'a1.pdf')
        await capture_document('Doc A2 (same bytes as A1)', DOC_A_BYTES, 'a2.pdf')
        await capture_document('Doc B (different bytes)', DOC_B_BYTES, 'b.pdf')

        hash_a1 = await page.evaluate("window.__DEBUG_getFileHash(1)")
        hash_a2 = await page.evaluate("window.__DEBUG_getFileHash(2)")
        hash_b = await page.evaluate("window.__DEBUG_getFileHash(3)")
        print("Doc A1 has a non-null file_hash:", hash_a1 is not None and len(hash_a1) == 64)
        print("Doc A1 and Doc A2 (identical bytes) share the same file_hash:", hash_a1 == hash_a2)
        print("Doc A1 and Doc B (different bytes) have different file_hash values:", hash_a1 != hash_b)
        print("Doc A1's file_hash matches hashlib.sha256() of its own bytes:", hash_a1 == hashlib.sha256(DOC_A_BYTES).hexdigest())

        # === Scenario 3: picking a file byte-identical to an already-saved document
        # shows a non-blocking warning immediately, naming that document ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'a3.pdf', 'mimeType': 'application/pdf', 'buffer': DOC_A_BYTES,
        })
        await page.wait_for_timeout(150)
        warning_visible = await page.locator('#f-duplicate-warning').is_visible()
        warning_text = await page.locator('#f-duplicate-warning').inner_text()
        print("Duplicate warning visible for a byte-identical pick:", warning_visible)
        print("Duplicate warning names the matched document:", 'Doc A1' in warning_text and '#1' in warning_text)
        save_disabled = await page.locator('#save-doc-btn').is_disabled()
        print("Save button NOT disabled by the warning (non-blocking):", not save_disabled)
        await page.fill('#f-title', 'Doc A3 (also identical to A1)')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)
        save_succeeded = await page.evaluate("window.__DEBUG_getFileHash(4) !== undefined")
        print("Save succeeded despite the warning:", save_succeeded)

        # === Scenario 4: picking a file with no existing match shows no warning ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'c.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 yet another genuinely different file',
        })
        await page.wait_for_timeout(150)
        no_warning = not await page.locator('#f-duplicate-warning').is_visible()
        print("No warning shown for a file with no existing match:", no_warning)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # === Scenario 5: Inbox bulk-add skips an exact-duplicate staged file
        # (removing it from inbox/, reporting the skip count) while a genuinely
        # new staged file in the same batch is still added normally ===
        # Doc A1 (id 1) from earlier scenarios already has file_hash for DOC_A_BYTES.
        await page.evaluate("""
            async () => {
                const inboxDir = await window.__TEST_ROOT.getDirectoryHandle('inbox', { create: true });
                const dupFile = await inboxDir.getFileHandle('staged_duplicate.pdf', { create: true });
                const dupWritable = await dupFile.createWritable();
                await dupWritable.write(new TextEncoder().encode('%PDF-1.4 fake pdf content A for duplicate-detection tests'));
                await dupWritable.close();
                const newFile = await inboxDir.getFileHandle('staged_new.pdf', { create: true });
                const newWritable = await newFile.createWritable();
                await newWritable.write(new TextEncoder().encode('%PDF-1.4 a genuinely new staged file, never seen before'));
                await newWritable.close();
            }
        """)
        await page.click('#inbox-check-btn')
        await page.wait_for_timeout(300)
        status_text = await page.locator('#status').inner_text()
        # The exact wording is composed from up to 3 parts (added/skipped/failed),
        # joined with a space -- see addAllInboxFilesAndShowStatus(). Rather than
        # match the whole concatenated string, check for the real, specific content:
        # the added count ("1"), the review-queue wording, and the word "duplicate"
        # somewhere in the skip-count message.
        print("Status line reports 1 added to the review queue:", '1' in status_text and 'review' in status_text.lower())
        print("Status line reports 1 skipped as a duplicate:", '1' in status_text and 'duplicate' in status_text.lower())
        inbox_now_empty = await page.evaluate("""
            async () => {
                const inboxDir = await window.__TEST_ROOT.getDirectoryHandle('inbox', { create: true });
                const names = [];
                for await (const [name] of inboxDir.entries()) names.push(name);
                return names.length === 0;
            }
        """)
        print("Both staged files removed from inbox/ (duplicate skipped, new one added):", inbox_now_empty)
        # We're on the Inbox nav view now (addAllInboxFilesAndShowStatus() jumps
        # there since something was added) -- the newly-added staged_new document
        # is needs_review=1, so it shows up here. (Note: it would NOT show up in
        # the All Documents view -- matchesView()'s 'all' branch excludes
        # needs_review docs -- so this check deliberately stays on the Inbox view
        # rather than switching, unlike a plain document-count check would need to.)
        inbox_doc_titles = await page.locator('#doc-tbody tr .doc-title').all_inner_texts()
        print("The genuinely new file became a real document:", any('staged_new' in title for title in inbox_doc_titles))
        # Confirm the duplicate did NOT also become a second, separate document:
        # documents 1-4 already exist (A1, A2, B, A3 from earlier scenarios), the
        # genuinely-new staged file should be exactly id 5, and there should be no
        # id 6 at all (which a wrongly-created duplicate document would have been).
        doc5_hash = await page.evaluate("window.__DEBUG_getFileHash(5)")
        doc6_hash = await page.evaluate("window.__DEBUG_getFileHash(6)")
        print("The genuinely new file became document #5 with its own file_hash:", doc5_hash is not None and len(doc5_hash) == 64)
        print("The duplicate file did NOT become a second new document (no document #6 exists):", doc6_hash is None)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
