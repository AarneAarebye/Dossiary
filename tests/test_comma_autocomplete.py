import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# Reported bug: comma-separated multi-value fields (People/person-type fields,
# Tags) only ever offered autocomplete suggestions for the FIRST entry typed --
# once you'd typed "Birgit, " and started a second name, nothing suggested,
# because native <input list> matches suggestions against the WHOLE input
# value, not the segment currently being typed. wireCommaAutocomplete()
# replaces the native mechanism with a hand-rolled comma-aware one.
SEED = {
    "documents": [
        {
            "id": 1, "title": "Doc 1", "category": "Travel", "document_type": "Receipt",
            "date": "2026-03-01T00:00:00+00:00", "notes": None, "ocr_text": None, "ocr_language": None,
            "file_path": "files/1_a.pdf", "original_file_path": None,
            "created_at": "2026-03-01T00:00:00+00:00", "source": "captured", "source_legacy_id": None,
            "archived": 0, "needs_review": 0, "deleted": 0,
        },
    ],
    "tags": [
        {"id": 1, "name": "Invoice"},
        {"id": 2, "name": "Important"},
        {"id": 3, "name": "Ink"},
    ],
    "document_tags": [],
    "people": [
        {"id": 1, "name": "Arne"},
        {"id": 2, "name": "Anna"},
        {"id": 3, "name": "Birgit"},
    ],
    "fields": [
        {"id": 1, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_type_fields": [
        {"document_type": "Receipt", "field_name": "People", "position": 0},
    ],
    "document_field_people": [],
}

async def route_stub(page):
    async def route_handler(route):
        url = route.request.url
        if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
            await route.fulfill(body="/* stubbed */", content_type='application/javascript')
        else:
            await route.continue_()
    await page.route('**/*', route_handler)
    stub_js = open('stub_studio2.js').read()
    await page.add_init_script(stub_js)

async def dropdown_texts(page, wrap_selector):
    return await page.evaluate(f"""
        () => Array.from(document.querySelector('{wrap_selector}').querySelectorAll('.comma-autocomplete-item')).map(el => el.textContent)
    """)

async def dropdown_visible(page, wrap_selector):
    return await page.evaluate(f"""
        () => {{
            const dd = document.querySelector('{wrap_selector}').querySelector('.comma-autocomplete-dropdown');
            return dd ? dd.style.display !== 'none' : false;
        }}
    """)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await route_stub(page)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click("#open-btn")
        await page.wait_for_timeout(400)

        # === Scenario 1: native list= attribute is removed once wireCommaAutocomplete()
        # takes over, both for the People field and for Tags ===
        await page.click('#add-btn')
        await page.wait_for_timeout(150)
        await page.fill('#f-type', 'Receipt')
        await page.locator('#f-type').blur()
        await page.wait_for_timeout(150)

        people_list_attr = await page.locator('[data-dynamic-field="People"] input').get_attribute('list')
        tags_list_attr = await page.locator('#f-tags').get_attribute('list')
        assert people_list_attr is None, f"People input should have list= removed, got {people_list_attr!r}"
        assert tags_list_attr is None, f"Tags input should have list= removed, got {tags_list_attr!r}"
        print("Native list= attribute removed on People and Tags inputs:", people_list_attr, tags_list_attr)

        # === Scenario 2: reproducing the exact reported bug -- after "Birgit, ",
        # typing "A" now shows suggestions for the SECOND name, not nothing ===
        people_input = page.locator('[data-dynamic-field="People"] input')
        await people_input.fill('Birgit, A')
        await page.wait_for_timeout(150)
        wrap = '[data-dynamic-field="People"] .field-with-clear'
        visible = await dropdown_visible(page, wrap)
        texts = await dropdown_texts(page, wrap)
        assert visible, "suggestion dropdown should be visible after typing 'Birgit, A'"
        assert set(texts) == {'Arne', 'Anna'}, f"expected Arne and Anna suggested (Birgit already used), got {texts}"
        print("Typing 'Birgit, A' suggests Arne and Anna (the bug this fixes):", texts)

        # === Scenario 3: clicking a suggestion completes that segment and appends
        # ", " so typing the next name can continue immediately ===
        await page.click(f"{wrap} .comma-autocomplete-item:has-text('Arne')")
        await page.wait_for_timeout(150)
        value_after_click = await people_input.input_value()
        assert value_after_click == 'Birgit, Arne, ', f"expected 'Birgit, Arne, ', got {value_after_click!r}"
        print("Clicking a suggestion completes the segment and appends ', ':", value_after_click)

        # === Scenario 4: a name already used earlier in the input is excluded from
        # suggestions for a later segment (Arne, now used, shouldn't suggest itself
        # again even though it starts with 'A') ===
        await people_input.fill('Birgit, Arne, An')
        await page.wait_for_timeout(150)
        texts2 = await dropdown_texts(page, wrap)
        assert texts2 == ['Anna'], f"expected only Anna (Arne already used), got {texts2}"
        print("Already-used names are excluded from later suggestions:", texts2)

        # === Scenario 5: keyboard navigation -- ArrowDown highlights an item,
        # Enter selects it ===
        await people_input.fill('An')
        await page.wait_for_timeout(150)
        await people_input.press('ArrowDown')
        await page.wait_for_timeout(80)
        active_text = await page.evaluate(f"""
            () => {{
                const el = document.querySelector('{wrap} .comma-autocomplete-item.active');
                return el ? el.textContent : null;
            }}
        """)
        assert active_text == 'Anna', f"expected 'Anna' highlighted after ArrowDown, got {active_text!r}"
        await people_input.press('Enter')
        await page.wait_for_timeout(150)
        value_after_enter = await people_input.input_value()
        assert value_after_enter == 'Anna, ', f"expected 'Anna, ' after Enter, got {value_after_enter!r}"
        print("ArrowDown highlights a suggestion and Enter selects it:", active_text, '->', value_after_enter)

        # === Scenario 6: an empty segment (nothing typed after the last comma, or
        # an empty field) shows no dropdown at all ===
        await people_input.fill('')
        await page.wait_for_timeout(150)
        visible_empty = await dropdown_visible(page, wrap)
        assert not visible_empty, "empty input should show no suggestion dropdown"
        print("Empty input shows no suggestion dropdown:", visible_empty)

        # === Scenario 7: the same comma-aware behavior works for Tags too ===
        tags_input = page.locator('#f-tags')
        await tags_input.fill('Important, In')
        await page.wait_for_timeout(150)
        tags_texts = await page.evaluate("""
            () => Array.from(document.getElementById('f-tags').closest('.field-with-clear').querySelectorAll('.comma-autocomplete-item')).map(el => el.textContent)
        """)
        assert set(tags_texts) == {'Invoice', 'Ink'}, f"expected Invoice and Ink suggested (Important already used), got {tags_texts}"
        print("Tags field shows the same comma-aware suggestions:", tags_texts)
        await tags_input.fill('')
        await page.wait_for_timeout(150)

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        # === Scenario 8: the same behavior works in the edit form too ===
        # .row-edit-btn is a hover-revealed button right on the table row itself --
        # it jumps straight to the edit form, skipping the detail view entirely, so
        # clicking the row first would only open a modal that blocks it. It only
        # renders below the 640px mobile breakpoint now (see "Hide the row-level
        # Edit shortcut except below the mobile breakpoint"), so a mobile viewport
        # is needed to reach it at all.
        await page.set_viewport_size({"width": 375, "height": 800})
        await page.wait_for_timeout(150)
        await page.click('.row-edit-btn')
        await page.wait_for_timeout(200)
        edit_people_input = page.locator('[data-dynamic-field="People"] input')
        edit_people_list_attr = await edit_people_input.get_attribute('list')
        assert edit_people_list_attr is None, f"edit-form People input should have list= removed, got {edit_people_list_attr!r}"
        await edit_people_input.fill('Birgit, A')
        await page.wait_for_timeout(150)
        edit_wrap = '[data-dynamic-field="People"] .field-with-clear'
        edit_texts = await dropdown_texts(page, edit_wrap)
        assert set(edit_texts) == {'Arne', 'Anna'}, f"edit form: expected Arne and Anna suggested, got {edit_texts}"
        print("Comma-aware suggestions also work in the edit form:", edit_texts)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
