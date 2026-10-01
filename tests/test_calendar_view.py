import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json, datetime
from playwright.async_api import async_playwright

# The calendar view: a third view next to List and Grid, remembered per
# library, showing the listed documents as chips on their own date in a
# month grid (starting on the locale's first weekday), undated ones below.
# It opens on the newest dated document's month, moves by month, follows the
# search, and its chips select, open the context menu, drag and take J/K
# like rows. Month and weekday names follow the UI language.
def doc(i, title, date, category='Home'):
    return {"id": i, "title": title, "category": category, "document_type": "Letter", "date": date,
            "import_date": f"2026-04-0{i}T10:00:00Z", "created_at": f"2026-04-0{i}T10:00:00Z",
            "file_path": f"files/{i}.pdf", "source": "captured", "archived": 0, "needs_review": 0, "deleted": 0}
SEED = {
    "documents": [
        doc(1, "Gas bill", "2026-03-03T00:00:00+00:00"),
        doc(2, "Water bill", "2026-03-03"),
        doc(3, "Insurance letter", "2026-03-15", 'Insurance'),
        doc(4, "February receipt", "2026-02-10"),
        doc(5, "Undated note", None),
    ],
    "collections": [{"id": 1, "name": "Utilities", "kind": "manual", "criteria": None}],
}

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click('#open-btn')
        await page.wait_for_timeout(500)

        chips_on = lambda iso: page.locator(f'.cal-day[data-date="{iso}"] .cal-chip')
        print("The view switch offers Calendar:", await page.inner_text('#view-calendar-btn') == '▤ Calendar')
        await page.click('#view-calendar-btn')
        await page.wait_for_timeout(300)
        print("Calendar replaces the table:", await page.locator('#doc-calendar').is_visible() and not await page.locator('#doc-table').is_visible()
              and await page.get_attribute('#view-calendar-btn', 'aria-pressed') == 'true')
        print("It opens on the newest document's month:", await page.inner_text('#cal-title') == 'March 2026'
              and await page.inner_text('#cal-month-count') == '3 documents this month')
        weekdays = await page.locator('.cal-weekday').all_inner_texts()
        print("Weeks start on Sunday in English:", weekdays[0] == 'SUN' and len(weekdays) == 7)
        print("Documents sit on their own date (a date with a time too):", sorted(await chips_on('2026-03-03').all_inner_texts()) == ['Gas bill', 'Water bill'])
        print("March 1st 2026 (a Sunday) is the first cell:", await page.locator('.cal-day').first.get_attribute('data-date') == '2026-03-01')
        print("Days outside the month are dimmed and empty:", await page.locator('.cal-day.cal-outside').count() > 0
              and await page.locator('.cal-day.cal-outside .cal-chip').count() == 0)
        print("Undated documents are listed below:", await page.inner_text('.cal-undated-title') == 'NO DATE (1)'
              and await page.locator('.cal-undated .cal-chip').all_inner_texts() == ['Undated note'])

        # === Navigation ===
        await page.click('#cal-prev-btn')
        await page.wait_for_timeout(200)
        print("Previous month:", await page.inner_text('#cal-title') == 'February 2026'
              and await chips_on('2026-02-10').all_inner_texts() == ['February receipt']
              and await page.inner_text('#cal-month-count') == '1 document this month')
        await page.click('#cal-today-btn')
        await page.wait_for_timeout(200)
        today = datetime.date.today()
        print("Today jumps to this month, marking today:", await page.inner_text('#cal-title') == today.strftime('%B %Y')
              and await page.locator(f'.cal-day.cal-today[data-date="{today.isoformat()}"]').count() == 1)
        # back to March
        while await page.inner_text('#cal-title') != 'March 2026':
            await page.click('#cal-prev-btn' if (today.year, today.month) > (2026, 3) else '#cal-next-btn')
            await page.wait_for_timeout(100)

        # === Chips behave like rows ===
        await page.click('.cal-day[data-date="2026-03-15"] .cal-chip')
        await page.wait_for_timeout(300)
        print("Clicking a chip shows the document's details:", 'Insurance letter' in await page.inner_text('#detail-panel-body')
              and await page.locator('.cal-day[data-date="2026-03-15"] .cal-chip.row-selected').count() == 1)
        await page.keyboard.press('k')
        await page.wait_for_timeout(300)
        print("K moves to the previous chip:", await page.locator('.cal-chip.row-selected').count() == 1
              and await page.locator('.cal-day[data-date="2026-03-03"] .cal-chip.row-selected').count() == 1)
        await page.click('.cal-day[data-date="2026-03-15"] .cal-chip', button='right')
        await page.wait_for_timeout(200)
        print("Right-clicking a chip opens the context menu:", await page.locator('.row-context-menu').count() == 1)
        await page.keyboard.press('Escape')
        await page.mouse.click(700, 980)
        await page.drag_and_drop('.cal-day[data-date="2026-03-15"] .cal-chip', '#nav-item-collection-1')
        await page.wait_for_timeout(400)
        print("A chip can be dragged onto a collection:", await page.inner_text('#status') == 'Added 1 document to “Utilities”.')

        # === Search narrows the calendar ===
        await page.fill('#search', 'gas')
        await page.wait_for_timeout(300)
        print("The search narrows the chips:", await page.locator('.cal-chip').all_inner_texts() == ['Gas bill']
              and await page.inner_text('#cal-month-count') == '1 document this month')
        await page.fill('#search', '')
        await page.wait_for_timeout(300)

        # === Remembered per library ===
        await page.click('#reload-btn')
        await page.wait_for_timeout(200)
        await page.click('#open-btn')
        await page.wait_for_timeout(500)
        print("The calendar view is remembered:", await page.locator('#doc-calendar').is_visible()
              and await page.inner_text('#cal-title') == 'March 2026')

        # === German ===
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(300)
        weekdays = await page.locator('.cal-weekday').all_inner_texts()
        print("German: month name, Monday first, labels:", await page.inner_text('#cal-title') == 'März 2026'
              and weekdays[0] in ('MO.', 'MO') and await page.inner_text('#cal-today-btn') == 'Heute'
              and await page.inner_text('#view-calendar-btn') == '▤ Kalender')
        print("...and March 1st (a Sunday) is now the last cell of the first week:", await page.locator('.cal-day').nth(6).get_attribute('data-date') == '2026-03-01')

        # === Back to List ===
        await page.click('#view-list-btn')
        await page.wait_for_timeout(300)
        print("Switching back to List shows the table:", await page.locator('#doc-table').is_visible() and not await page.locator('#doc-calendar').is_visible())

        print("ERRORS:", errors)
        await browser.close()

asyncio.run(main())
