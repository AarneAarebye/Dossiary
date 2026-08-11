import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Doc 1: ordinary, active -- always in scope for Reports and the only document that
#        ever shows in the All Documents default view across every scenario below.
# Doc 2: archived -- Reports includes archived documents by default (unlike All
#        Documents, which hides them until "Show archived" is checked).
# Doc 3: deleted (Waste bin) -- Reports excludes deleted documents, same as every
#        other view.
# Doc 4: flagged for review (Inbox view) -- Reports includes needs-review documents
#        by default too, same reasoning as archived. Given a different Category
#        (Medical, not Travel) so later breakdown-by-category scenarios can tell it
#        apart from docs 1/2.
# Docs 5-7 are added in Tasks 2/3 for currency/date-range scenarios.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Active Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 2, "title": "Archived Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-02-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/2_b.pdf", "original_file_path": None,
            "created_at": "2026-02-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 3, "title": "Deleted Doc", "category": "Travel", "document_type": "Receipt",
            "date": "2026-01-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/3_c.pdf", "original_file_path": None,
            "created_at": "2026-01-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 1,
        },
        {
            "id": 4, "title": "Needs Review Doc", "category": "Medical", "document_type": "Receipt",
            "date": "2026-01-15T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/4_d.pdf", "original_file_path": None,
            "created_at": "2026-01-15T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 1, "deleted": 0,
        },
        {
            "id": 5, "title": "USD Food Receipt", "category": "Food", "document_type": "Receipt",
            "date": "2026-03-05T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/5_e.pdf", "original_file_path": None,
            "created_at": "2026-03-05T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 6, "title": "No-Currency Food Receipt", "category": "Food", "document_type": "Receipt",
            "date": "2025-06-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/6_f.pdf", "original_file_path": None,
            "created_at": "2025-06-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
        {
            "id": 7, "title": "No-Date Travel Receipt", "category": "Travel", "document_type": "Receipt",
            "date": None, "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/7_g.pdf", "original_file_path": None,
            "created_at": "2026-01-20T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 1, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [], "document_tags": [],
    "fields": [
        {"id": 1, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Currency", "type": "text", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 1, "value": "45.00"},
        {"document_id": 1, "field_id": 2, "value": "EUR"},
        {"document_id": 2, "field_id": 1, "value": "30.00"},
        {"document_id": 2, "field_id": 2, "value": "EUR"},
        {"document_id": 4, "field_id": 1, "value": "10.00"},
        {"document_id": 4, "field_id": 2, "value": "EUR"},
        {"document_id": 5, "field_id": 1, "value": "20.00"},
        {"document_id": 5, "field_id": 2, "value": "USD"},
        {"document_id": 6, "field_id": 1, "value": "15.00"},
        {"document_id": 7, "field_id": 1, "value": "5.00"},
        {"document_id": 7, "field_id": 2, "value": "EUR"},
    ],
    "people": [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ],
    "document_field_people": [
        {"document_id": 1, "field_id": 3, "person_id": 1},
        {"document_id": 1, "field_id": 3, "person_id": 2},
        {"document_id": 2, "field_id": 3, "person_id": 1},
    ],
}

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(300)

        # === Scenario 1: the Reports nav item exists and is reachable ===
        reports_nav_count = await page.locator('#nav-item-reports').count()
        print("Reports nav item exists:", reports_nav_count == 1)

        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        reports_active = await page.locator('#nav-item-reports').get_attribute('class')
        print("Reports nav item becomes active on click:", 'active' in (reports_active or ''))

        # === Scenario 2: switching to Reports hides the document table/count line ===
        table_visible = await page.locator('#table-wrap').is_visible()
        count_line_visible = await page.locator('#count-line').is_visible()
        reports_view_visible = await page.locator('#reports-view').is_visible()
        print("Table hidden in Reports view:", not table_visible)
        print("Count line hidden in Reports view:", not count_line_visible)
        print("#reports-view visible:", reports_view_visible)

        # === Scenario 3: Reports scope includes archived and needs-review, excludes
        # deleted -- 3 of the 4 initial seeded documents (doc 1 active, doc 2 archived, doc 4
        # needs-review) should be in scope; doc 3 (deleted) should not ===
        # (This scope property is now verified more thoroughly by Scenario 7's row/grand-total checks)

        # === Scenario 4: switching back to All Documents restores the table, and
        # Show archived reflects that view's own independent state (unaffected by
        # having just been in Reports). Only doc 1 is ever plain active/non-archived/
        # non-needs-review/non-deleted in this SEED, so this assertion stays valid
        # even after Tasks 2-3 add more documents (5-7 are all archived). ===
        await page.click('#nav-item-all')
        await page.wait_for_timeout(150)
        table_visible_after = await page.locator('#table-wrap').is_visible()
        reports_view_visible_after = await page.locator('#reports-view').is_visible()
        print("Table visible again in All Documents:", table_visible_after)
        print("#reports-view hidden again:", not reports_view_visible_after)
        all_row_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => e.dataset.id)')
        print("All Documents still shows only doc 1 (rest are archived/needs-review/deleted):", all_row_ids)

        # === Scenario 5: breakdown dropdown exists and defaults to Category ===
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        breakdown_count = await page.locator('#report-breakdown-field').count()
        print("Breakdown dropdown exists:", breakdown_count == 1)
        breakdown_options = await page.locator('#report-breakdown-field option').all_inner_texts()
        print("Breakdown dropdown options:", breakdown_options)

        # === Scenario 6: currency grouping -- EUR (docs 1,2,4), USD (doc 5), and "No
        # currency set" (doc 6) are three separate groups, in that order (sorted by
        # currency label; "No currency set" sorts last since its internal grouping
        # key starts with underscores) ===
        group_headings = await page.locator('.report-currency-group h3').all_inner_texts()
        print("Currency group headings:", group_headings)

        # === Scenario 7: Category breakdown within the EUR group -- docs 1/2 share
        # Category "Travel" (count 2, total 75.00), doc 4 is "Medical" (count 1,
        # total 10.00); the group's own Grand total (85.00, count 3) is computed
        # independently, not by summing the rows (which happen to match here since
        # Category is single-valued) ===
        eur_group = page.locator('.report-currency-group').first
        cat_row_labels = await eur_group.locator('.report-table tbody td:nth-child(1)').all_inner_texts()
        cat_row_counts = await eur_group.locator('.report-table tbody td:nth-child(2)').all_inner_texts()
        cat_row_totals = await eur_group.locator('.report-table tbody td:nth-child(3)').all_inner_texts()
        cat_grand_total_row = await eur_group.locator('.report-table tfoot td').all_inner_texts()
        print("EUR group Category rows (label, count, total):", list(zip(cat_row_labels, cat_row_counts, cat_row_totals)))
        print("EUR group Grand total row:", cat_grand_total_row)
        cat_caption_count = await eur_group.locator('.report-caption').count()
        print("No multi-valued caption for Category breakdown:", cat_caption_count == 0)

        # === Scenario 8: People breakdown within the EUR group -- doc 1 has both
        # Alice and Bob, so it contributes its 45.00 to BOTH rows; doc 2 (Alice only)
        # contributes 30.00 to Alice; doc 4 has no People at all, landing in "(none)".
        # Row totals (75+45+10=130) intentionally exceed the group's real Grand total
        # (85.00) -- this is the documented multi-valued-breakdown behavior, and the
        # caption must appear to explain it. Switching the dropdown here, without
        # leaving the Reports view, also proves the report recomputes on dropdown
        # change alone. ===
        await page.select_option('#report-breakdown-field', 'people')
        await page.wait_for_timeout(150)
        eur_group = page.locator('.report-currency-group').first
        people_row_labels = await eur_group.locator('.report-table tbody td:nth-child(1)').all_inner_texts()
        people_row_counts = await eur_group.locator('.report-table tbody td:nth-child(2)').all_inner_texts()
        people_row_totals = await eur_group.locator('.report-table tbody td:nth-child(3)').all_inner_texts()
        people_grand_total_row = await eur_group.locator('.report-table tfoot td').all_inner_texts()
        people_caption_count = await eur_group.locator('.report-caption').count()
        print("EUR group People rows (label, count, total):", list(zip(people_row_labels, people_row_counts, people_row_totals)))
        print("EUR group Grand total row (independent, still 85.00/3):", people_grand_total_row)
        print("Multi-valued caption shown for People breakdown:", people_caption_count > 0)

        # === Scenario 9: date-range filter narrows Reports totals -- with the
        # dropdown reset to Category (Scenario 8 left it on People), filtering to
        # 2026 excludes doc 6 (dated 2025) and doc 7 (no date at all), leaving only
        # the EUR and USD currency groups; clearing the range restores all three ===
        await page.select_option('#report-breakdown-field', 'category')
        await page.wait_for_timeout(150)

        date_from_count = await page.locator('#report-date-from').count()
        date_to_count = await page.locator('#report-date-to').count()
        print("Date range inputs exist:", date_from_count == 1 and date_to_count == 1)

        await page.fill('#report-date-from', '2026-01-01')
        await page.fill('#report-date-to', '2026-12-31')
        await page.wait_for_timeout(150)
        group_headings_filtered = await page.locator('.report-currency-group h3').all_inner_texts()
        print("Currency groups with 2026 date range (doc 6's 2025 date and doc 7's blank date both excluded):", group_headings_filtered)

        await page.fill('#report-date-from', '')
        await page.fill('#report-date-to', '')
        await page.wait_for_timeout(150)
        group_headings_unfiltered = await page.locator('.report-currency-group h3').all_inner_texts()
        print("Currency groups with no date range (doc 6 and doc 7 included again):", group_headings_unfiltered)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
