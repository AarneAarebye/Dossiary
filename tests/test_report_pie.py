import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))  # tests/ sits alongside dossiary.html at the repo root

import asyncio, json
from playwright.async_api import async_playwright

# The Reports pie: one per currency group, beside its table, with the table
# rows as its legend (matching swatches). The 7 largest positive values get
# their own colour and the rest share an "Other" slice; negative totals are
# left out with a note; a group with nothing positive, and a multi-valued
# breakdown (Tags), get no pie. A slice drills down like its row, "Other"
# into all of its rows' documents.
CATS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']  # amounts 100, 90, ..., 10
docs, values = [], []
def add(doc_id, category, amount, currency):
    docs.append({"id": doc_id, "title": f"Doc {doc_id}", "category": category, "document_type": "Receipt",
                 "date": "2026-03-01T00:00:00+00:00", "import_date": "2026-03-01T00:00:00+00:00",
                 "created_at": "2026-03-01T00:00:00+00:00", "file_path": f"files/{doc_id}.pdf", "source": "captured",
                 "archived": 0, "needs_review": 0, "deleted": 0})
    if amount is not None: values.append({"document_id": doc_id, "field_id": 1, "value": amount})
    if currency: values.append({"document_id": doc_id, "field_id": 2, "value": currency})
for i, c in enumerate(CATS):
    add(i + 1, c, f"{100 - i * 10}.00", "EUR")
add(11, 'Refund', '-5.00', 'EUR')
add(12, 'Travel', '20.00', 'USD')
add(13, 'Misc', None, None)
SEED = {
    "documents": docs,
    "fields": [
        {"id": 1, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Currency", "type": "text", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": values,
    "tags": [{"id": 1, "name": "tax"}, {"id": 2, "name": "work"}],
    "document_tags": [{"document_id": 1, "tag_id": 1}, {"document_id": 1, "tag_id": 2}],
}

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
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)});")
        await page.click('#open-btn')
        await page.wait_for_timeout(500)
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(300)

        groups = page.locator('.report-currency-group')
        headings = [await groups.nth(i).locator('h3').inner_text() for i in range(await groups.count())]
        eur = groups.nth(headings.index('EUR'))
        usd = groups.nth(headings.index('USD'))
        none = groups.nth(len(headings) - 1)

        # === EUR: 7 own slices + Other, the table as legend ===
        titles = await eur.locator('.report-slice title').all_text_contents()
        print("EUR pie has 8 slices, 7 values plus Other:", len(titles) == 8 and titles[-1] == 'Other: 60.00 (10.9%)')
        print("The largest slice comes first, with its share:", titles[0] == 'A: 100.00 (18.2%)')
        swatches = await eur.evaluate("""g => [...g.querySelectorAll('tbody tr')].map(tr => {
            const s = tr.querySelector('.report-swatch');
            return [tr.querySelector('td').innerText.trim(), s ? s.style.background : null];
        })""")
        fills = await eur.evaluate("g => [...g.querySelectorAll('.report-slice')].map(s => s.getAttribute('fill'))")
        sw = dict(swatches)
        def rgb(hexcol):
            h = hexcol.lstrip('#'); return f"rgb({int(h[0:2],16)}, {int(h[2:4],16)}, {int(h[4:6],16)})"
        print("Each of the 7 largest rows has its slice's colour:", [sw[c] for c in CATS[:7]] == [rgb(f) for f in fills[:7]])
        print("The smaller rows share the Other colour:", sw['H'] == sw['I'] == sw['J'] == rgb(fills[7]) and len(set(fills)) == 8)
        print("A negative row has no swatch, and the chart says so:", sw['Refund'] is None
              and await eur.locator('.report-pie-note').inner_text() == 'Negative totals are left out of the chart.')
        print("The pie sits beside the table:", await eur.evaluate("""g => {
            const t = g.querySelector('.report-table').getBoundingClientRect(), p = g.querySelector('.report-pie').getBoundingClientRect();
            return p.left >= t.right && p.top < t.bottom; }"""))
        print("The chart is labelled for screen readers:", await eur.locator('.report-pie svg').get_attribute('aria-label') == 'Share of the total by Category')

        # === Other groups ===
        print("A group with one value draws a full circle:", await usd.locator('circle.report-slice').count() == 1
              and await usd.locator('.report-pie-note').count() == 0)
        print("A group with no positive total gets no pie:", headings[-1] != 'EUR' and await none.locator('.report-pie').count() == 0)

        # === Drilling down from a slice ===
        await eur.locator('.report-slice').first.click()
        await page.wait_for_timeout(300)
        print("Clicking a slice drills down like its row:", await page.inner_text('#report-drilldown-banner-text') == 'Category: A — 1 document'
              and await page.locator('#doc-tbody tr').count() == 1)
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(300)
        await page.locator('.report-currency-group').nth(headings.index('EUR')).locator('.report-slice').nth(7).click()
        await page.wait_for_timeout(300)
        print("Other drills into all of its rows' documents:", await page.inner_text('#report-drilldown-banner-text') == 'Category: Other — 3 documents'
              and sorted(await page.locator('#doc-tbody tr .doc-title').all_inner_texts()) == ['Doc 10', 'Doc 8', 'Doc 9'])
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(300)
        await page.locator('.report-currency-group').nth(headings.index('EUR')).locator('.report-slice').nth(1).focus()
        await page.keyboard.press('Enter')
        await page.wait_for_timeout(300)
        print("A focused slice drills down with Enter:", await page.inner_text('#report-drilldown-banner-text') == 'Category: B — 1 document')
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(300)

        # === Multi-valued breakdown: no pie ===
        await page.select_option('#report-breakdown-field', 'tags')
        await page.wait_for_timeout(300)
        print("A multi-valued breakdown (Tags) shows no pie or swatches:", await page.locator('.report-pie').count() == 0
              and await page.locator('.report-swatch').count() == 0)
        await page.select_option('#report-breakdown-field', 'category')
        await page.wait_for_timeout(300)

        # === Language ===
        await page.evaluate("() => { const s = document.getElementById('lang-select'); s.value = 'de'; s.dispatchEvent(new Event('change')); }")
        await page.wait_for_timeout(300)
        g2 = page.locator('.report-currency-group').nth(headings.index('EUR'))
        print("Labels follow the language:", await g2.locator('.report-slice title').nth(7).text_content() == 'Sonstige: 60.00 (10.9%)'
              and await g2.locator('.report-pie-note').inner_text() == 'Negative Summen sind im Diagramm nicht enthalten.')

        print("ERRORS:", errors)
        await browser.close()

asyncio.run(main())
