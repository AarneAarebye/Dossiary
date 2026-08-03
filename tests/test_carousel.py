import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (document_studio.html, stub_studio2.js, fake_folder/...) work regardless of the CWD this test is invoked from

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'document_studio.html'))  # tests/ sits alongside document_studio.html at the repo root

import asyncio, base64
from playwright.async_api import async_playwright

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

        # Doc 1: image -> gets a real thumbnail
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('carousel_img.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'carousel_img.png')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Carousel Doc A')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # Doc 2: PDF -> gets a stubbed-pdfjs thumbnail
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('carousel_doc.pdf', 'wb') as f:
            f.write(b"%PDF-1.4 fake pdf for carousel test")
        await page.set_input_files('#file-input', 'carousel_doc.pdf')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Carousel Doc B')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        # Doc 3: unrecognized file type -> generateThumbnail() returns null, no thumbnail
        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('carousel_nopreview.bin', 'wb') as f:
            f.write(b"not an image or pdf")
        await page.set_input_files('#file-input', 'carousel_nopreview.bin')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Carousel Doc C')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(300)

        carousel_visible = await page.locator('#carousel-wrap').is_visible()
        print("carousel visible after documents exist:", carousel_visible)

        card_count = await page.locator('.cf-card').count()
        print("carousel card count (3 docs, all within +-2 window):", card_count)

        center_title = await page.locator('.cf-card.cf-center').get_attribute('data-doc-id')
        print("initially centered doc id (should be 1, newest-date ties keep insertion order):", center_title)

        caption = await page.locator('#carousel-caption').inner_text()
        print("initial caption mentions 'Carousel Doc A':", 'Carousel Doc A' in caption)
        print("initial caption shows position (1 of 3):", '1 of 3' in caption)

        await page.wait_for_timeout(300)  # let async thumbnail loads settle
        img_count_before_nav = await page.locator('.cf-thumb-wrap img').count()
        print("thumbnail <img> elements rendered for docs 1 & 2 (should be 2):", img_count_before_nav)
        no_preview_text = await page.locator('.cf-card[data-doc-id="3"] .cf-thumb-empty').inner_text()
        print("doc 3 (no thumbnail) placeholder text:", no_preview_text)

        # Next button moves the center without touching the table
        rows_before = await page.locator('#doc-tbody tr').count()
        await page.click('#carousel-next')
        await page.wait_for_timeout(300)
        rows_after = await page.locator('#doc-tbody tr').count()
        center_after_next = await page.locator('.cf-card.cf-center').get_attribute('data-doc-id')
        print("centered doc id after clicking next (should be 2):", center_after_next)
        print("table row count unchanged by carousel nav:", rows_before == rows_after)

        # Prev button
        await page.click('#carousel-prev')
        await page.wait_for_timeout(300)
        center_after_prev = await page.locator('.cf-card.cf-center').get_attribute('data-doc-id')
        print("centered doc id after clicking prev (should be back to 1):", center_after_prev)

        # Clicking a side card recenters on it
        await page.click('.cf-card[data-doc-id="3"]')
        await page.wait_for_timeout(300)
        center_after_side_click = await page.locator('.cf-card.cf-center').get_attribute('data-doc-id')
        print("centered doc id after clicking doc 3's side card:", center_after_side_click)

        # Scrubber jumps directly to an index
        await page.evaluate("""
            () => {
                const el = document.getElementById('carousel-scrubber');
                el.value = 1;
                el.dispatchEvent(new Event('input', { bubbles: true }));
            }
        """)
        await page.wait_for_timeout(300)
        center_after_scrub = await page.locator('.cf-card.cf-center').get_attribute('data-doc-id')
        print("centered doc id after scrubbing to index 1 (should be 2):", center_after_scrub)

        # Clicking the center card opens the real detail modal
        await page.click('.cf-card.cf-center')
        await page.wait_for_timeout(200)
        modal_heading = await page.locator('.modal h2').inner_text()
        print("clicking center card opened detail modal for:", modal_heading)
        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        # Carousel mirrors the table's own filter/search
        await page.fill('#search', 'Doc B')
        await page.wait_for_timeout(300)
        filtered_card_count = await page.locator('.cf-card').count()
        filtered_center = await page.locator('.cf-card.cf-center').get_attribute('data-doc-id')
        print("carousel card count after searching 'Doc B' (should be 1):", filtered_card_count)
        print("carousel centers on the only remaining match (should be 2):", filtered_center)

        await page.fill('#search', 'nonexistent-search-term-xyz')
        await page.wait_for_timeout(300)
        empty_caption = await page.locator('#carousel-caption').inner_text()
        empty_card_count = await page.locator('.cf-card').count()
        print("carousel card count when search matches nothing:", empty_card_count)
        print("carousel caption when search matches nothing:", empty_caption)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
