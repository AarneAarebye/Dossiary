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

        # Fix 4: the skipped duplicate (which was assigned and then rolled back
        # from id 5, the same id the genuinely-new file went on to reuse) must
        # not have left any orphaned file behind under that id -- the hash check
        # now runs BEFORE either file-write in createReviewDocumentFromFile(), so
        # a skipped duplicate should never touch files/ at all. The only files
        # under id 5 should belong to the genuinely-new "staged_new" document.
        files_dir_entries = await page.evaluate("""
            async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                const names = [];
                for await (const [name] of filesDir.entries()) names.push(name);
                return names;
            }
        """)
        print("No orphaned file was written under the rolled-back id for the skipped duplicate:", not any('staged_duplicate' in n for n in files_dir_entries))
        print("The genuinely-new document's own file IS present under id 5:", any('staged_new' in n for n in files_dir_entries))

        # === Scenario 6: "Library check" groups exact-hash matches and
        # Title+Date metadata matches correctly, excludes a blank-title/date
        # document, and clicking a document in a group opens its detail panel ===
        # By this point the library has: docs 1/2/4 sharing DOC_A_BYTES' hash
        # (Scenarios 2 and 3), doc 3 with a different hash, and doc 5 from
        # Scenario 4's no-warning pick (also a unique hash). None of these five
        # share a Title+Date pair yet, so add two more documents that do.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'meta1.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 metadata-match doc one',
        })
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Electric Bill')
        await page.fill('#f-date', '2026-03-01')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'meta2.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 metadata-match doc two, different bytes',
        })
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Electric Bill')
        await page.fill('#f-date', '2026-03-01')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)

        # A same-title, different-date document -- must NOT be grouped with the pair above.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'meta3.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 same title different date',
        })
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Electric Bill')
        await page.fill('#f-date', '2026-04-01')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)

        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)
        # .duplicate-group-label has text-transform:uppercase in CSS, so
        # inner_text() (which reflects rendered text, not raw textContent)
        # returns the label in all-caps -- compare case-insensitively.
        exact_group_labels = await page.locator('.duplicate-group-label').all_inner_texts()
        print("Modal shows at least one 'Exact file match' group:", any('exact' in l.lower() for l in exact_group_labels))
        print("Modal shows at least one 'Likely duplicate' (title+date) group:", any('likely duplicate' in l.lower() for l in exact_group_labels))

        # Exactly 2 documents share the Electric Bill / 2026-03-01 pairing -- find
        # the specific metadata-match group by its label and confirm it holds
        # exactly the two same-date rows, not the third (different-date) one.
        metadata_group = page.locator('.duplicate-group').filter(has_text='Likely duplicate (title + date)')
        metadata_group_row_titles = await metadata_group.locator('.duplicate-row .doc-title').all_inner_texts()
        electric_bill_rows_in_group = [t for t in metadata_group_row_titles if t == 'Electric Bill']
        print("Both same-date Electric Bill documents appear together, and only those two:", len(electric_bill_rows_in_group) == 2 and len(metadata_group_row_titles) == 2)

        first_row = page.locator('.duplicate-row').first
        first_row_doc_id = await first_row.get_attribute('data-document-id')
        # Capture the clicked row's whole group before the click closes the modal.
        first_group_ids = sorted(int(x) for x in await page.evaluate(
            "() => [...document.querySelector('.duplicate-group').querySelectorAll('.duplicate-row')].map(r => r.dataset.documentId)"
        ))
        await first_row.click()
        await page.wait_for_timeout(200)
        modal_closed = await page.locator('#modal-backdrop').count() == 0
        detail_panel_text = await page.locator('#detail-panel-body').inner_text()
        print("Clicking a duplicate-group document closes the modal:", modal_closed)
        print("...and opens that exact document's detail panel:", f'#{first_row_doc_id}' in detail_panel_text)

        # Clicking a document in a group also filters the table down to exactly
        # that group's documents (the Reports drill-down view, reused), with a
        # banner whose back link returns to Library check.
        table_ids = sorted(int(x) for x in await page.locator('#doc-tbody tr[data-id]').evaluate_all("rows => rows.map(r => r.dataset.id)"))
        print("...and filters the table to exactly that duplicate group:", table_ids == first_group_ids, table_ids, first_group_ids)
        clicked_row_selected = await page.locator(f'#doc-tbody tr[data-id="{first_row_doc_id}"].row-selected').count() == 1
        print("...with the clicked document's row selected:", clicked_row_selected)
        banner_visible = await page.locator('#report-drilldown-banner').is_visible()
        banner_text = await page.locator('#report-drilldown-banner-text').inner_text()
        back_text = await page.locator('#report-drilldown-back-btn').inner_text()
        print("Drill-down banner names the group and its size:", banner_visible and 'Exact file match' in banner_text and str(len(first_group_ids)) in banner_text, repr(banner_text))
        print("Banner's back link points to Library check, not Reports:", back_text == '← Back to Library check', repr(back_text))
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(300)
        print("Back link reopens the Library check modal:", await page.locator('#duplicates-list').count() == 1)
        print("...over the unfiltered All Documents view (banner hidden):", not await page.locator('#report-drilldown-banner').is_visible())
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # === Scenario 7: a second "Library check" open does not re-hash
        # already-hashed documents (no progress shown, since nothing is unhashed) ===
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)
        progress_hidden = not await page.locator('#duplicates-progress').is_visible()
        print("No backfill progress shown on a second open (everything already hashed):", progress_hidden)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # === Scenario 8: a deleted document is excluded from every grouping pass ===
        # Doc A1/A2/A3 (ids 1, 2, 4) share DOC_A_BYTES' hash -- a 3-member exact-hash
        # group. Delete doc 4 (Doc A3) and confirm the group shrinks to 2 members,
        # and that doc 4's own title no longer appears anywhere in the modal.
        # We're still on the Inbox nav view (from Scenario 5's jump there) -- doc 4
        # is an ordinary captured document, never flagged for review, so it isn't
        # rendered in that view's table at all. Switch to All Documents first so
        # the row is actually clickable.
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.click('tr[data-id="4"]')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)
        list_text_after_delete = await page.locator('#duplicates-list').inner_text()
        print("Deleted document's title no longer appears in any duplicate group:", 'Doc A3' not in list_text_after_delete)
        # The exact-hash group containing Doc A1 now has exactly 2 rows (A1 and A2),
        # not the original 3.
        exact_group_locator = page.locator('.duplicate-group').filter(has_text='Doc A1')
        exact_group_row_count = await exact_group_locator.locator('.duplicate-row').count()
        print("Exact-hash group shrinks from 3 to 2 members after the deletion:", exact_group_row_count == 2)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # === Scenario 9 (Minor item): a drag-and-drop batch that's entirely
        # duplicates is skipped end to end -- no navigation to the Inbox view,
        # and the status line reports the skip without ever mentioning an
        # addition. Doc A1 (id 1) is still active (non-deleted) with
        # DOC_A_BYTES' hash, so a dropped file with the same bytes matches it. ===
        async def dispatch_drag_with_content(page, event_type, files=None):
            parts_js = ""
            if files is not None:
                parts = ",".join(
                    f"new File([new TextEncoder().encode({content!r})], {name!r}, {{type: 'application/pdf'}})"
                    for name, content in files
                )
                parts_js = f"[{parts}].forEach(f => dt.items.add(f));"
            await page.evaluate(f"""
                () => {{
                    const dt = new DataTransfer();
                    {parts_js}
                    const ev = new DragEvent({event_type!r}, {{ bubbles: true, cancelable: true, dataTransfer: dt }});
                    document.dispatchEvent(ev);
                }}
            """)

        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await dispatch_drag_with_content(page, 'dragenter')
        await page.wait_for_timeout(100)
        await dispatch_drag_with_content(page, 'drop', [('dup_drop.pdf', '%PDF-1.4 fake pdf content A for duplicate-detection tests')])
        await page.wait_for_timeout(300)
        drop_status_text = await page.locator('#status').inner_text()
        print("All-duplicates drop status line mentions a skipped duplicate:", 'duplicate' in drop_status_text.lower())
        print("All-duplicates drop status line does NOT mention an addition:", 'added' not in drop_status_text.lower())
        stayed_off_inbox = await page.locator('#nav-item-all.active').count() == 1
        print("An all-duplicates drop does not navigate to the Inbox view:", stayed_off_inbox)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())

# === Fix 1: Title+Date grouping must slice both dates to their first 10
# characters before comparing, so a migrated document's full ISO timestamp
# ('2019-05-15T00:00:00+00:00') matches a captured document's plain
# 10-character date ('2019-05-15') for the exact same real-world date. ===
SEED_ISO_DATE = {
    "documents": [
        {
            "id": 1, "title": "Electric Bill", "category": None, "document_type": None,
            "date": "2019-05-15T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_migrated.pdf", "original_file_path": None,
            "created_at": "2019-05-15T00:00:00+00:00", "source": "migrated", "source_legacy_id": 42,
        },
    ],
    "tags": [], "document_tags": [],
}

async def main_iso_date_match():
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

        import json
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED_ISO_DATE)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # Capture a second document with the same Title and a plain 10-character
        # Date representing the exact same real-world date as doc 1's full ISO
        # timestamp.
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.set_input_files('#file-input', {
            'name': 'recaptured.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 a freshly recaptured copy of the same real-world document',
        })
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Electric Bill')
        await page.fill('#f-date', '2019-05-15')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)

        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)

        metadata_group = page.locator('.duplicate-group').filter(has_text='Likely duplicate (title + date)')
        row_titles = await metadata_group.locator('.duplicate-row .doc-title').all_inner_texts()
        print("Migrated doc (full ISO timestamp) and recaptured doc (plain date) are grouped together as a Title+Date match:", len(row_titles) == 2 and all(t == 'Electric Bill' for t in row_titles))

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main_iso_date_match())


# === Fix 2: the lazy backfill (openLibraryCheckModal()/backfillFileHash())
# is exercised end to end against a pre-existing library seeded with documents
# that have NO file_hash set yet -- simulating a library from before this
# feature shipped, the exact scenario every real Dossiary library hits the
# first time "Library check" is opened after upgrading. ===
SEED_UNHASHED = {
    "documents": [
        {
            "id": 1, "title": "Backfill Doc A", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00Z", "source": "captured", "source_legacy_id": None,
        },
        {
            "id": 2, "title": "Backfill Doc B", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00Z", "source": "captured", "source_legacy_id": None,
        },
        {
            "id": 3, "title": "Missing File Doc", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            # This file is never actually created in the fake filesystem below --
            # exercises the missing-file skip.
            "file_path": "files/3_missing.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00Z", "source": "captured", "source_legacy_id": None,
        },
    ],
    "tags": [], "document_tags": [],
}

async def main_lazy_backfill():
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

        import json
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED_UNHASHED)});")
        # Stage real, matching bytes for docs 1 and 2 under files/ -- doc 3's
        # file_path is deliberately left unwritten, to exercise the
        # missing-file skip.
        await page.evaluate("""
            async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                const bytes = new TextEncoder().encode('%PDF-1.4 identical content for the lazy-backfill pair');
                const aHandle = await filesDir.getFileHandle('1_a.pdf', { create: true });
                const aWritable = await aHandle.createWritable(); await aWritable.write(bytes); await aWritable.close();
                const bHandle = await filesDir.getFileHandle('2_b.pdf', { create: true });
                const bWritable = await bHandle.createWritable(); await bWritable.write(bytes); await bWritable.close();
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # The fake filesystem + a real (but tiny) crypto.subtle.digest() call are
        # fast enough that a 3-document backfill can complete well within a single
        # Playwright round-trip, making "is the progress indicator visible mid-run"
        # a real race rather than a reliable check. Slow down crypto.subtle.digest()
        # artificially, for this test only, so the backfill loop stays observably
        # in-progress long enough to check -- this doesn't touch dossiary.html
        # itself, just the underlying Web Crypto API this one test call goes through.
        await page.evaluate("""
            () => {
                const originalDigest = window.crypto.subtle.digest.bind(window.crypto.subtle);
                window.crypto.subtle.digest = async (...args) => {
                    await new Promise(r => setTimeout(r, 150));
                    return originalDigest(...args);
                };
            }
        """)

        # Don't await this call's own completion -- kick off the backfill and
        # poll, so we can observe the progress indicator while it's still running
        # (a single fully-awaited call would only ever observe the final,
        # already-hidden state).
        await page.evaluate("() => { window.__DEBUG_openLibraryCheckModal(); }")
        await page.wait_for_timeout(50)
        progress_visible = await page.locator('#duplicates-progress').is_visible()
        print("Progress indicator appears while the backfill is running:", progress_visible)

        await page.wait_for_timeout(1200)
        progress_hidden = not await page.locator('#duplicates-progress').is_visible()
        print("Progress indicator disappears once the backfill completes:", progress_hidden)

        hash1 = await page.evaluate("window.__DEBUG_getFileHash(1)")
        hash2 = await page.evaluate("window.__DEBUG_getFileHash(2)")
        hash3 = await page.evaluate("window.__DEBUG_getFileHash(3)")
        print("Doc A and Doc B (matching staged bytes, no original_file_path) got the same real, non-null hash -- backfill fell back to hashing file_path:", hash1 is not None and len(hash1) == 64 and hash1 == hash2)
        print("Missing-file doc's hash stays null/undefined (backfill skipped it without throwing):", hash3 is None)

        exact_group = page.locator('.duplicate-group').filter(has_text='Backfill Doc A')
        exact_group_titles = await exact_group.locator('.duplicate-row .doc-title').all_inner_texts()
        print("Backfill Doc A and Doc B appear together in an Exact file match group:", sorted(exact_group_titles) == ['Backfill Doc A', 'Backfill Doc B'])
        exact_group_label = await exact_group.locator('.duplicate-group-label').inner_text()
        print("...and that group is labeled as an exact match:", 'exact' in exact_group_label.lower())

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main_lazy_backfill())


# === Fix 3: if persistDb() throws partway through the backfill (a revoked
# filesystem permission, a full disk, ...), findDuplicatesBackfillRunning must
# still end up false and the app must still be left in a usable state --
# specifically, Escape must still work for a SEPARATE, later-opened modal,
# since findDuplicatesBackfillRunning also gates the shared onModalKeydown()
# handler used by every modal in the app, not just this one. ===
SEED_BACKFILL_FAILURE = {
    "documents": [
        {
            "id": 1, "title": "Doc Needing Backfill", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00Z", "source": "captured", "source_legacy_id": None,
        },
    ],
    "tags": [], "document_tags": [],
}

async def main_backfill_failure():
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

        import json
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED_BACKFILL_FAILURE)});")
        await page.evaluate("""
            async () => {
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files', { create: true });
                const bytes = new TextEncoder().encode('%PDF-1.4 needs a hash');
                const aHandle = await filesDir.getFileHandle('1_a.pdf', { create: true });
                const aWritable = await aHandle.createWritable(); await aWritable.write(bytes); await aWritable.close();
            }
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # Force persistDb() to throw -- dbFileHandle is the exact same
        # FakeFileHandle instance the app already holds a reference to (FakeDirHandle.
        # getFileHandle() returns the existing entry from its _children map, not a
        # copy), so patching createWritable() on the handle we get here affects the
        # app's own in-flight persistDb() call too.
        await page.evaluate("""
            async () => {
                const handle = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                handle.createWritable = async () => { throw new Error('Simulated disk failure'); };
            }
        """)

        threw = await page.evaluate("""
            async () => {
                try { await window.__DEBUG_openLibraryCheckModal(); return false; }
                catch (e) { return true; }
            }
        """)
        print("openLibraryCheckModal() propagates the persistDb() failure rather than swallowing it:", threw)

        backfill_flag_cleared = not await page.evaluate("window.__DEBUG_findDuplicatesBackfillRunning()")
        print("findDuplicatesBackfillRunning is cleared back to false even though persistDb() threw:", backfill_flag_cleared)

        close_btn_reenabled = not await page.locator('#modal-close-btn').is_disabled()
        print("The (still-open) duplicates modal's close button is re-enabled, not stuck disabled:", close_btn_reenabled)

        # The real proof this doesn't leak app-wide: open a completely separate,
        # unrelated modal afterward and confirm Escape still closes it -- this
        # would fail (Escape silently doing nothing) if findDuplicatesBackfillRunning
        # were left stuck true, since onModalKeydown() is shared across every modal.
        await page.evaluate("window.__DEBUG_openRemindersModal([]);")
        await page.wait_for_timeout(100)
        await page.keyboard.press('Escape')
        await page.wait_for_timeout(150)
        reminders_modal_closed = await page.locator('#modal-backdrop').count() == 0
        print("Escape still closes a subsequently-opened, unrelated modal (Reminders):", reminders_modal_closed)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main_backfill_failure())


# === Backfill Stop/resume, batched persistence, and concurrency: a large first
# backfill (e.g. a library on an iCloud-synced folder, where every evicted file
# has to be downloaded before it can be hashed) must (a) read several files at
# once, (b) persist progress in batches rather than only at the very end, and
# (c) offer a Stop button that keeps what's been hashed so far, shows results,
# and lets the next Library check resume with only the remaining documents. ===
BACKFILL_STOP_DOC_COUNT = 60
SEED_BACKFILL_STOP = {
    "documents": [
        {
            "id": i, "title": f"Stop Doc {i}", "category": None, "document_type": None,
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": f"files/{i}_doc.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00Z", "source": "captured", "source_legacy_id": None,
        }
        for i in range(1, BACKFILL_STOP_DOC_COUNT + 1)
    ],
    "tags": [], "document_tags": [],
}

async def main_backfill_stop_resume():
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

        import json
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED_BACKFILL_STOP)});")
        await page.evaluate(f"""
            async () => {{
                const filesDir = await window.__TEST_ROOT.getDirectoryHandle('files', {{ create: true }});
                for(let i = 1; i <= {BACKFILL_STOP_DOC_COUNT}; i++){{
                    const h = await filesDir.getFileHandle(i + '_doc.pdf', {{ create: true }});
                    const w = await h.createWritable(); await w.write(new TextEncoder().encode('%PDF-1.4 unique ' + i)); await w.close();
                }}
            }}
        """)
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # Slow every digest down (standing in for a slow cloud download) and
        # record the peak number of hashes in flight at once; also count every
        # write to library.sqlite, to observe batched persistence.
        await page.evaluate("""
            async () => {
                const originalDigest = window.crypto.subtle.digest.bind(window.crypto.subtle);
                window.__inFlight = 0; window.__peakInFlight = 0;
                window.crypto.subtle.digest = async (...args) => {
                    window.__inFlight++; window.__peakInFlight = Math.max(window.__peakInFlight, window.__inFlight);
                    await new Promise(r => setTimeout(r, 60));
                    window.__inFlight--;
                    return originalDigest(...args);
                };
                const dbHandle = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const originalCreateWritable = dbHandle.createWritable.bind(dbHandle);
                window.__dbWrites = 0;
                dbHandle.createWritable = async (...args) => { window.__dbWrites++; return originalCreateWritable(...args); };
            }
        """)

        await page.evaluate("() => { window.__modalDone = window.__DEBUG_openLibraryCheckModal().then(() => true); }")
        # Wait until well past the first persist batch (25), but short of all 60.
        await page.wait_for_function("() => window.__DEBUG_countHashed && window.__DEBUG_countHashed() >= 32", timeout=10000)
        stop_visible = await page.locator('#duplicates-stop-btn').is_visible()
        print("Stop button is shown while the backfill is running:", stop_visible)
        writes_before_stop = await page.evaluate("window.__dbWrites")
        print("Progress was persisted mid-pass (before Stop, before the pass finished):", writes_before_stop >= 1)
        peak = await page.evaluate("window.__peakInFlight")
        print("Several files are hashed concurrently (peak in flight > 1, <= 4):", 1 < peak <= 4, peak)

        await page.click('#duplicates-stop-btn')
        await page.wait_for_function("() => window.__modalDone === true || window.__DEBUG_findDuplicatesBackfillRunning() === false", timeout=10000)
        await page.wait_for_timeout(200)
        hashed_after_stop = await page.evaluate("window.__DEBUG_countHashed()")
        print("Stop halted the pass early (some, but not all, documents hashed):", 0 < hashed_after_stop < BACKFILL_STOP_DOC_COUNT, hashed_after_stop)
        note_text = await page.locator('#duplicates-stopped-note').inner_text() if await page.locator('#duplicates-stopped-note').count() else ''
        print("A stopped-early note is shown above the results:", f"{hashed_after_stop} of {BACKFILL_STOP_DOC_COUNT}" in note_text, repr(note_text))
        close_enabled = not await page.locator('#modal-close-btn').is_disabled()
        print("Close button is re-enabled after Stop:", close_enabled)
        print("Backfill-running flag cleared after Stop:", not await page.evaluate("window.__DEBUG_findDuplicatesBackfillRunning()"))

        # Resume: a fresh Library check only works through what's left.
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)
        await page.evaluate("() => { window.__DEBUG_openLibraryCheckModal(); }")
        await page.wait_for_timeout(30)
        progress_text = await page.locator('#duplicates-progress-text').inner_text()
        remaining = BACKFILL_STOP_DOC_COUNT - hashed_after_stop
        print("Re-opening resumes with only the remaining documents:", f"of {remaining} " in progress_text, repr(progress_text))
        await page.wait_for_function("() => window.__DEBUG_findDuplicatesBackfillRunning() === false", timeout=15000)
        print("Every document is hashed once the resumed pass finishes:", await page.evaluate("window.__DEBUG_countHashed()") == BACKFILL_STOP_DOC_COUNT)
        print("No stopped-early note after a pass that ran to completion:", await page.locator('#duplicates-stopped-note').count() == 0)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main_backfill_stop_resume())
