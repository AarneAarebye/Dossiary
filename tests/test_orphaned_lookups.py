import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

import asyncio, json
from playwright.async_api import async_playwright

TYPE_FIELD_ROWS = [
    {"document_type": "General", "field_name": "People", "position": 0},
]

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

        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededEmptyRoot({json.dumps(TYPE_FIELD_ROWS)}, []);")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        async def capture_document(title, file_bytes, filename, tags=None, people=None):
            await page.click('#add-btn')
            await page.wait_for_timeout(100)
            await page.set_input_files('#file-input', {
                'name': filename, 'mimeType': 'application/pdf', 'buffer': file_bytes,
            })
            await page.wait_for_timeout(150)
            await page.fill('#f-title', title)
            await page.fill('#f-type', 'General')
            await page.locator('#f-type').blur()
            await page.wait_for_timeout(150)
            if tags:
                await page.fill('#f-tags', tags)
            if people:
                await page.fill('[data-dynamic-field="People"] input', people)
            await page.click('#save-doc-btn')
            await page.wait_for_timeout(200)

        # Doc 1: tag "Kept" and person "Alice" -- both stay in use throughout.
        await capture_document('Doc One', b'%PDF-1.4 doc one', 'doc1.pdf', tags='Kept', people='Alice')

        # Doc 2: tag "WillOrphan" and person "Bob" -- both will become orphaned
        # once this document is deleted (moved to the Waste bin) below.
        await capture_document('Doc Two', b'%PDF-1.4 doc two', 'doc2.pdf', tags='WillOrphan', people='Bob')

        # === Create a brand new "Author" person-type field inline, and use it on
        # a third document -- proves a person is recognized as "in use" via ANY
        # person-type field, not just the built-in People field ===
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        await page.fill('#f-type', 'General')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)
        await page.click('#f-add-field-toggle')
        await page.wait_for_timeout(100)
        await page.fill('#f-new-field-name', 'Author')
        await page.select_option('#f-new-field-type', 'person')
        await page.click('#f-new-field-btn')
        await page.wait_for_timeout(150)
        await page.set_input_files('#file-input', {
            'name': 'doc3.pdf', 'mimeType': 'application/pdf', 'buffer': b'%PDF-1.4 doc three',
        })
        await page.wait_for_timeout(150)
        await page.fill('#f-title', 'Doc Three')
        await page.fill('[data-dynamic-field="Author"] input', 'Carol')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(200)

        # === Move Doc Two to the Waste bin -- its tag ("WillOrphan") and person
        # ("Bob") are now referenced only by a deleted document, so both should
        # be flagged as orphaned per this feature's own Waste-bin-only scoping ===
        await page.click('tr[data-id="2"]')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)

        # computeOrphanedTags()/computeOrphanedPeople() take an already-non-deleted-
        # filtered array as their own argument (matching computeBrokenFileLinks()'s
        # own signature) -- rather than reconstructing that filtered list here,
        # exercise the REAL modal-open path, which is the more meaningful,
        # end-to-end check anyway.
        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)

        orphaned_tag_names = await page.evaluate("""
            () => Array.from(document.querySelectorAll('.orphaned-row .doc-title')).map(el => el.textContent)
        """)
        print("Kept tag is not shown as orphaned:", 'Kept' not in orphaned_tag_names)
        print("WillOrphan tag (only on a Waste-bin document) IS shown as orphaned:", 'WillOrphan' in orphaned_tag_names)
        print("Alice (still in use) is not shown as orphaned:", 'Alice' not in orphaned_tag_names)
        print("Bob (only on a Waste-bin document) IS shown as orphaned:", 'Bob' in orphaned_tag_names)
        print("Carol (in use via the Author field, not People) is not shown as orphaned:", 'Carol' not in orphaned_tag_names)

        print("Exactly one 'Orphaned tags' section label is shown:",
              await page.locator('.duplicate-group-label:has-text("Orphaned tags")').count() == 1)
        print("Exactly one 'Orphaned people' section label is shown:",
              await page.locator('.duplicate-group-label:has-text("Orphaned people")').count() == 1)

        # === Declining the confirm() leaves everything unchanged ===
        page.once("dialog", lambda dialog: asyncio.ensure_future(dialog.dismiss()))
        await page.click('.orphaned-row:has-text("WillOrphan") .orphaned-delete-btn')
        await page.wait_for_timeout(200)
        print("Declining the per-row confirm() leaves the row in place:",
              await page.locator('.orphaned-row:has-text("WillOrphan")').count() == 1)

        # === Per-row Delete, confirmed: removes just that one tag ===
        dialog_messages = []
        def capture_and_accept(dialog):
            dialog_messages.append(dialog.message)
            asyncio.ensure_future(dialog.accept())
        page.once("dialog", capture_and_accept)
        await page.click('.orphaned-row:has-text("WillOrphan") .orphaned-delete-btn')
        await page.wait_for_timeout(300)
        print("Per-row delete confirm() names the tag being deleted:", 'WillOrphan' in dialog_messages[0])
        print("The deleted tag's row is gone:",
              await page.locator('.orphaned-row:has-text("WillOrphan")').count() == 0)

        persisted_after_tag_delete = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("The tags table no longer has a row named WillOrphan:",
              not any(t['name'] == 'WillOrphan' for t in persisted_after_tag_delete['tags']))
        print("document_tags has no dangling row pointing at the deleted tag's old id:",
              not any(link['tag_id'] not in [t['id'] for t in persisted_after_tag_delete['tags']] for link in persisted_after_tag_delete['document_tags']))

        # === Per-row Delete for a person, confirmed ===
        page.once("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))
        await page.click('.orphaned-row:has-text("Bob") .orphaned-delete-btn')
        await page.wait_for_timeout(300)
        print("Bob's row is gone after per-row delete:",
              await page.locator('.orphaned-row:has-text("Bob")').count() == 0)

        persisted_after_person_delete = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        print("The people table no longer has a row named Bob:",
              not any(p['name'] == 'Bob' for p in persisted_after_person_delete['people']))
        print("document_field_people has no dangling row pointing at Bob's old id:",
              not any(link['person_id'] not in [p['id'] for p in persisted_after_person_delete['people']] for link in persisted_after_person_delete['document_field_people']))

        # === Datalist refresh: the deleted tag/person no longer autocompletes ===
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)
        tag_list_options = await page.locator('#tag-list option').all_inner_texts()
        person_list_options = await page.locator('#person-list option').all_inner_texts()
        print("Deleted tag WillOrphan no longer appears in the tag datalist:", 'WillOrphan' not in tag_list_options)
        print("Deleted person Bob no longer appears in the person datalist:", 'Bob' not in person_list_options)

        # === Bulk "Delete all orphaned" ===
        # Doc Two (still in the Waste bin) originally had tag WillOrphan (now
        # gone) and person Bob (now gone) -- add a second, brand-new orphaned
        # tag/person pair by capturing then deleting a fourth document, so the
        # bulk-delete scenario has more than one row to clear in each section.
        await capture_document('Doc Four', b'%PDF-1.4 doc four', 'doc4.pdf', tags='BulkTagOne', people='BulkPersonOne')
        await capture_document('Doc Five', b'%PDF-1.4 doc five', 'doc5.pdf', tags='BulkTagTwo', people='BulkPersonTwo')
        await page.click('tr:has-text("Doc Four")')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)
        await page.click('tr:has-text("Doc Five")')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)

        await page.evaluate("window.__DEBUG_openLibraryCheckModal()")
        await page.wait_for_timeout(300)

        bulk_dialog_messages = []
        def capture_and_accept_bulk(dialog):
            bulk_dialog_messages.append(dialog.message)
            asyncio.ensure_future(dialog.accept())
        page.once("dialog", capture_and_accept_bulk)
        await page.click('.orphaned-delete-all-btn[data-kind="tag"]')
        await page.wait_for_timeout(300)
        print("Bulk-delete confirm() mentions both orphaned tags being removed (count of 2):", '2' in bulk_dialog_messages[0])
        print("Both bulk-orphaned tags are gone after confirming:",
              await page.locator('.orphaned-row:has-text("BulkTagOne")').count() == 0 and
              await page.locator('.orphaned-row:has-text("BulkTagTwo")').count() == 0)
        print("The 'Orphaned tags' section itself is gone (no tags left in it):",
              await page.locator('.duplicate-group-label:has-text("Orphaned tags")').count() == 0)

        page.once("dialog", lambda dialog: asyncio.ensure_future(dialog.accept()))
        await page.click('.orphaned-delete-all-btn[data-kind="person"]')
        await page.wait_for_timeout(300)
        print("Both bulk-orphaned people are gone after confirming:",
              await page.locator('.orphaned-row:has-text("BulkPersonOne")').count() == 0 and
              await page.locator('.orphaned-row:has-text("BulkPersonTwo")').count() == 0)
        print("The 'Orphaned people' section itself is gone (no people left in it):",
              await page.locator('.duplicate-group-label:has-text("Orphaned people")').count() == 0)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # === Restoring a Waste-bin document whose only tag was deleted while
        # orphaned comes back without that tag, per this feature's own
        # documented, accepted consequence -- rather than crashing or showing a
        # stale reference ===
        await page.click('#nav-item-trash')
        await page.wait_for_timeout(150)
        await page.click('tr:has-text("Doc Two")')
        await page.wait_for_timeout(150)
        await page.click('#delete-toggle-btn')
        await page.wait_for_timeout(150)
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        await page.click('tr:has-text("Doc Two")')
        await page.wait_for_timeout(150)
        detail_text = await page.locator('#detail-panel-body').inner_text()
        print("Restored Doc Two's detail panel does not crash and no longer shows the deleted tag WillOrphan:",
              'WillOrphan' not in detail_text)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
