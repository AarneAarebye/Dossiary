# Hide Document Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide the detail panel's document-preview thumbnail image (and its
empty-state placeholder) plus the "Generate preview"/"Regenerate preview"
action, behind a single named toggle that can be flipped back on with a
one-word edit, without touching thumbnail generation itself.

**Architecture:** One new boolean constant, `SHOW_DOCUMENT_PREVIEW`, gates
two existing code paths in `dossiary.html`: the block in `openDetail()`
that builds the thumbnail's HTML, and the `regen-thumb` action descriptor
in `buildDetailActions()`. Thumbnail *generation* on capture/Inbox-add is
untouched, so `thumbnail_path` stays populated the whole time the toggle
is off.

**Tech Stack:** Vanilla JS inside `dossiary.html` (no build step); Python +
Playwright for the existing test suite (`tests/test_*.py`).

## Global Constraints

- The new constant is named `SHOW_DOCUMENT_PREVIEW`, declared as
  `const SHOW_DOCUMENT_PREVIEW = false;` immediately after the existing
  `const APP_VERSION = '1.14.0';` line in `dossiary.html`.
- When `SHOW_DOCUMENT_PREVIEW` is `false`, `openDetail()`'s `thumbHtml`
  variable must end up as an empty string `''` — not the "no preview yet"
  placeholder — so nothing renders in `.modal-head` for it at all. An
  empty placeholder box would still cost the same 110x140px of space,
  defeating the entire point of this change.
- When `SHOW_DOCUMENT_PREVIEW` is `false`, `buildDetailActions()` must not
  add a `regen-thumb` descriptor to its returned array at all (not add it
  and filter it out downstream).
- Thumbnail *generation* — `generateThumbnail()`/`writeThumbnail()` and
  their call sites in `saveNewDocument()` (`dossiary.html:6072-6073`) and
  `createReviewDocumentFromFile()` (`dossiary.html:6344-6345`) — must not
  be modified in any way by this plan.
- No new dependency, no schema change, no new settings-table row, no
  user-facing toggle UI — this is a hardcoded, developer-facing constant.

---

### Task 1: Add the toggle and gate the two display code paths

**Files:**
- Modify: `dossiary.html:738` (new constant), `dossiary.html:4883-4892`
  (`openDetail()`'s `thumbHtml` block), `dossiary.html:4763-4766`
  (`buildDetailActions()`'s `regen-thumb` descriptor)

**Interfaces:**
- Produces: `SHOW_DOCUMENT_PREVIEW` (module-scope `const`, `boolean`),
  read by both `openDetail()` and `buildDetailActions()`. Task 2 (the test
  suite fixes) relies on this exact name and on `thumbHtml` ending up
  `''` when it's `false`.

- [ ] **Step 1: Add the constant right after `APP_VERSION`**

In `dossiary.html`, find:

```js
  const APP_VERSION = '1.14.0'; // shown in the footer; bump alongside the matching git tag on release
```

Change to:

```js
  const APP_VERSION = '1.14.0'; // shown in the footer; bump alongside the matching git tag on release
  // Hides the detail panel's document-preview thumbnail (and its "no
  // preview yet"/"preview missing" placeholder) plus the Generate/
  // Regenerate preview action, without touching thumbnail *generation* on
  // capture/Inbox-add -- thumbnail_path stays populated the whole time
  // this is off, so flipping it back to true needs no backfill. Off until
  // there's a carousel/gallery-style view that would make a single static
  // preview image worth its panel space again.
  const SHOW_DOCUMENT_PREVIEW = false;
```

- [ ] **Step 2: Gate `openDetail()`'s thumbnail-rendering block**

In `dossiary.html`, inside `openDetail(id)`, find:

```js
    let thumbHtml = `<div class="modal-thumb-empty" id="modal-thumb-slot">${t('detailNoPreviewYet')}</div>`;
    if(d.thumbnail_path){
      try{
        const fh = await resolveFileHandle(d.thumbnail_path, false);
        const file = await fh.getFile();
        thumbHtml = `<img class="modal-thumb" id="modal-thumb-slot" src="${URL.createObjectURL(file)}" alt="${t('sharedDocumentPreviewAlt')}" />`;
      }catch(e){
        thumbHtml = `<div class="modal-thumb-empty" id="modal-thumb-slot">${t('detailPreviewMissing')}</div>`;
      }
    }
```

Change to:

```js
    let thumbHtml = '';
    if(SHOW_DOCUMENT_PREVIEW){
      thumbHtml = `<div class="modal-thumb-empty" id="modal-thumb-slot">${t('detailNoPreviewYet')}</div>`;
      if(d.thumbnail_path){
        try{
          const fh = await resolveFileHandle(d.thumbnail_path, false);
          const file = await fh.getFile();
          thumbHtml = `<img class="modal-thumb" id="modal-thumb-slot" src="${URL.createObjectURL(file)}" alt="${t('sharedDocumentPreviewAlt')}" />`;
        }catch(e){
          thumbHtml = `<div class="modal-thumb-empty" id="modal-thumb-slot">${t('detailPreviewMissing')}</div>`;
        }
      }
    }
```

This is the exact same logic, just wrapped — the three cases (real image,
"no preview yet", "preview missing") are untouched, only reachable when
the flag is on. `.modal-head` (`display:flex; gap:20px;`) already
collapses correctly to just its metadata child when `thumbHtml` is `''`
and nothing else changes about how it's interpolated into the template
(`${thumbHtml}` inside `.modal-head`, unchanged) — an empty string
interpolates to nothing, no empty `<div>` left behind.

- [ ] **Step 3: Gate `buildDetailActions()`'s `regen-thumb` descriptor**

In `dossiary.html`, inside `buildDetailActions(id, d)`, find:

```js
    if(!d.deleted){
      actions.push({ key: 'edit', label: t('detailEdit'), variant: null, onClick: () => openEditForm(id) });
      actions.push({
        key: 'regen-thumb', label: d.thumbnail_path ? t('detailRegeneratePreview') : t('detailGeneratePreview'),
        variant: null, panelOnly: true, onClick: () => regenerateThumbnail(id),
      });
      actions.push({
        key: 'archive-toggle', label: d.archived ? t('detailUnarchive') : t('detailArchive'),
        variant: null, onClick: () => toggleArchived(id),
      });
```

Change to:

```js
    if(!d.deleted){
      actions.push({ key: 'edit', label: t('detailEdit'), variant: null, onClick: () => openEditForm(id) });
      if(SHOW_DOCUMENT_PREVIEW){
        actions.push({
          key: 'regen-thumb', label: d.thumbnail_path ? t('detailRegeneratePreview') : t('detailGeneratePreview'),
          variant: null, panelOnly: true, onClick: () => regenerateThumbnail(id),
        });
      }
      actions.push({
        key: 'archive-toggle', label: d.archived ? t('detailUnarchive') : t('detailArchive'),
        variant: null, onClick: () => toggleArchived(id),
      });
```

Everything else in `buildDetailActions()` (open-file, open-original,
archive-toggle, review-toggle, add-to-collection, remove-from-collection,
delete-toggle) is untouched.

- [ ] **Step 4: Verify the gate works, with a throwaway script**

This isn't a permanent test file — it's a quick, disposable check that the
gating logic actually suppresses rendering, before Task 2 fixes the
permanent suite (which currently still expects the old, always-on
behavior, and would give an ambiguous crash/pass signal if used as the
check right now). Write this to a scratch file and run it, then delete it
— don't commit it.

```bash
cat > /tmp/verify_preview_hidden.py << 'PYEOF'
import asyncio, base64, os as _os
from playwright.async_api import async_playwright

# Run from tests/ (the wrapping `cd` below does this) so these relative
# paths match every other test file's own convention.
APP_PATH = _os.path.abspath(_os.path.join('..', 'dossiary.html'))

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

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

        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        with open('thumbimg_scratch.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'thumbimg_scratch.png')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Image Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        thumb_count = await page.locator('.modal-thumb, .modal-thumb-empty').count()
        regen_btn_count = await page.locator('#regen-thumb-btn').count()
        print("thumbnail slot count (should be 0):", thumb_count)
        print("regen-thumb-btn count (should be 0):", regen_btn_count)
        print("JS ERRORS:", errors)
        _os.remove('thumbimg_scratch.png')
        await browser.close()

asyncio.run(main())
PYEOF
cd /Users/aarneaarebye/Projects/Paperless/Dossiary/tests && python3 /tmp/verify_preview_hidden.py
rm /tmp/verify_preview_hidden.py
```

Expected: `thumbnail slot count (should be 0): 0`, `regen-thumb-btn count
(should be 0): 0`, `JS ERRORS: []`. If either count is nonzero, the gating
in Step 2 or Step 3 isn't correctly suppressing rendering — go back and
check the exact code against what's shown above before continuing.

- [ ] **Step 5: Commit**

```bash
git add dossiary.html
git commit -m "Add SHOW_DOCUMENT_PREVIEW toggle to hide the detail panel's thumbnail

Hides the document-preview image/placeholder and its Generate/Regenerate
action behind one constant, without touching thumbnail generation on
capture/Inbox-add -- thumbnail_path stays populated the whole time this
is off, so reactivating needs no backfill."
```

---

### Task 2: Update the existing thumbnail tests for the new default

**Files:**
- Modify: `tests/test_thumbnails.py` (fix Scenario 1's now-stale
  assertions, add a new Scenario 3 for default-off behavior)
- Modify: `tests/test_regenerate.py` (patch the served copy of
  `dossiary.html` so its whole flow, which depends on the preview being
  visible, keeps proving the underlying generate/regenerate pipeline
  still works)

**Interfaces:**
- Consumes: `SHOW_DOCUMENT_PREVIEW` (Task 1), exact declaration text
  `const SHOW_DOCUMENT_PREVIEW = false;` in `dossiary.html` — both files'
  patching helper does a literal string replace of this exact text, so it
  must match Task 1's Step 1 output exactly.

With Task 1 done, `dossiary.html` now defaults to hiding the thumbnail —
`tests/test_thumbnails.py`'s Scenario 1 (which asserts `.modal-thumb`
exists and reads `#regen-thumb-btn`'s label) and all of
`tests/test_regenerate.py` (which clicks `#regen-thumb-btn` and asserts on
`.modal-thumb`/`.modal-thumb-empty`) are now testing against a UI element
that no longer exists by default. Both files need the same technique: run
against a copy of `dossiary.html` with `SHOW_DOCUMENT_PREVIEW` patched to
`true`, so they keep proving the real underlying pipeline (generation,
display, the Regenerate button's label switching) still works correctly —
not just get deleted, which would let that code silently bit-rot while
it's hidden.

- [ ] **Step 1: Add the patching helper to `tests/test_thumbnails.py`**

In `tests/test_thumbnails.py`, right after the existing `APP_PATH` line
(currently line 5), add:

```python
import tempfile

def _write_patched_app_with_preview_enabled():
    """Writes a copy of dossiary.html with SHOW_DOCUMENT_PREVIEW flipped to
    true, so this test can keep exercising the real thumbnail-display
    pipeline even though it now defaults to off (see dossiary.html's own
    SHOW_DOCUMENT_PREVIEW comment). Returns the temp file's path; caller
    is responsible for deleting it."""
    with open(APP_PATH) as f:
        html = f.read()
    target = "const SHOW_DOCUMENT_PREVIEW = false;"
    replacement = "const SHOW_DOCUMENT_PREVIEW = true;"
    assert target in html, "SHOW_DOCUMENT_PREVIEW declaration not found -- did its exact text change in dossiary.html?"
    patched = html.replace(target, replacement)
    fd, path = tempfile.mkstemp(suffix='.html', dir=_os2.path.dirname(APP_PATH))
    with _os2.fdopen(fd, 'w') as f:
        f.write(patched)
    return path
```

- [ ] **Step 2: Serve the patched copy instead of the real file**

In `tests/test_thumbnails.py`, find:

```python
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
```

Change to:

```python
        await page.route('**/*', route_handler)
        stub_js = open('stub_studio2.js').read()
        await page.add_init_script(stub_js)
        patched_app_path = _write_patched_app_with_preview_enabled()
        await page.goto(f"file://{patched_app_path}")
```

- [ ] **Step 3: Clean up the temp file and confirm the existing assertions still hold**

At the very end of `main()`, find:

```python
        print("JS ERRORS:", errors)
        await browser.close()
```

Change to:

```python
        print("JS ERRORS:", errors)
        await browser.close()
        _os2.remove(patched_app_path)
```

Run: `cd tests && python3 test_thumbnails.py`
Expected: identical output to before Task 1 — `modal shows <img>
thumbnail: 1`, `button label (should be 'Regenerate preview'):
Regenerate preview`, `pdfjsLib was called: True`, `JS ERRORS: []` — proving
the underlying pipeline (image thumbnail, PDF thumbnail, the Regenerate
label) still works exactly as before once the flag is patched back to
`true`.

- [ ] **Step 4: Add a new Scenario 3 confirming the default (flag off) behavior**

Still in `tests/test_thumbnails.py`, at the end of `main()` (right before
`print("JS ERRORS:", errors)` and `await browser.close()`), add a third
scenario that runs against the *real*, unpatched `dossiary.html` — proving
the actual shipped default hides the UI while still writing a real
thumbnail to disk:

```python
        # === Scenario 3: with the real (unpatched) app, the preview is
        # hidden by default -- no image, no empty-state placeholder, no
        # Generate/Regenerate button -- but a real thumbnail_path and a
        # real file in thumbnails/ still get written, proving generation
        # itself is untouched by SHOW_DOCUMENT_PREVIEW ===
        await page.close()
        page = await browser.new_page()
        errors3 = []
        page.on("pageerror", lambda exc: errors3.append(str(exc)))
        page.on("console", lambda msg: errors3.append(f"[console.{msg.type}] {msg.text}") if msg.type == "error" else None)
        await page.route('**/*', route_handler)
        await page.add_init_script(stub_js)
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate("window.__TEST_ROOT = window.__makeEmptyRoot();")
        await page.click("#open-btn")
        await page.wait_for_timeout(200)
        await page.click("#init-btn")
        await page.wait_for_timeout(200)

        await page.click('#add-btn')
        await page.wait_for_timeout(100)
        with open('thumbimg2.png', 'wb') as f:
            f.write(png_bytes)
        await page.set_input_files('#file-input', 'thumbimg2.png')
        await page.wait_for_timeout(100)
        await page.fill('#f-title', 'Hidden Preview Doc')
        await page.click('#save-doc-btn')
        await page.wait_for_timeout(400)

        await page.click('tr[data-id="1"]')
        await page.wait_for_timeout(200)
        thumb_slot_count = await page.locator('.modal-thumb, .modal-thumb-empty').count()
        regen_btn_count = await page.locator('#regen-thumb-btn').count()
        print("preview slot present with default (should be False -- flag is off):", thumb_slot_count > 0)
        print("regen-thumb-btn present with default (should be False -- flag is off):", regen_btn_count > 0)

        persisted3 = await page.evaluate("""
            (async () => {
                const fh = await window.__TEST_ROOT.getFileHandle('library.sqlite');
                const f = await fh.getFile();
                return JSON.parse(await f.text());
            })()
        """)
        doc3 = persisted3['documents'][0]
        thumb_on_disk3 = await page.evaluate("""
            (async () => {
                try {
                    const thumbsDir = await window.__TEST_ROOT.getDirectoryHandle('thumbnails');
                    const fh = await thumbsDir.getFileHandle('1.png');
                    const f = await fh.getFile();
                    return { exists: true, size: f.size };
                } catch(e) { return { exists: false, error: e.message }; }
            })()
        """)
        print("thumbnail_path still written despite hidden preview (should be truthy):", doc3['thumbnail_path'])
        print("thumbnail file still on disk despite hidden preview:", thumb_on_disk3)
```

Then, right at the very end, change the final error-reporting line so both
pages' errors are reported:

```python
        print("JS ERRORS:", errors + errors3)
        await browser.close()
```

(Remove the old standalone `print("JS ERRORS:", errors)` line from Step 3
above, since this replaces it — Scenario 3's errors need reporting too.)

Run: `cd tests && python3 test_thumbnails.py`
Expected: `preview slot present with default (should be False -- flag is
off): False`, `regen-thumb-btn present with default (should be False --
flag is off): False`, `thumbnail_path still written despite hidden
preview (should be truthy): thumbnails/1.png` (or similar non-null path),
`thumbnail file still on disk despite hidden preview: {'exists': True,
'size': ...}`, `JS ERRORS: []`.

- [ ] **Step 5: Apply the identical patching technique to `tests/test_regenerate.py`**

`tests/test_regenerate.py`'s entire flow (clicking `#regen-thumb-btn`,
asserting on `.modal-thumb`/`.modal-thumb-empty`) depends on the preview
being visible, so the whole file needs to run against the patched
(flag-on) copy — there's no default-off scenario to add here, since
`test_thumbnails.py`'s new Scenario 3 already covers that.

In `tests/test_regenerate.py`, add the identical helper right after the
existing `APP_PATH` line (currently line 5):

```python
import tempfile

def _write_patched_app_with_preview_enabled():
    """Writes a copy of dossiary.html with SHOW_DOCUMENT_PREVIEW flipped to
    true, so this test can keep exercising the real Generate/Regenerate
    preview pipeline even though it now defaults to off (see
    dossiary.html's own SHOW_DOCUMENT_PREVIEW comment). Returns the temp
    file's path; caller is responsible for deleting it."""
    with open(APP_PATH) as f:
        html = f.read()
    target = "const SHOW_DOCUMENT_PREVIEW = false;"
    replacement = "const SHOW_DOCUMENT_PREVIEW = true;"
    assert target in html, "SHOW_DOCUMENT_PREVIEW declaration not found -- did its exact text change in dossiary.html?"
    patched = html.replace(target, replacement)
    fd, path = tempfile.mkstemp(suffix='.html', dir=_os2.path.dirname(APP_PATH))
    with _os2.fdopen(fd, 'w') as f:
        f.write(patched)
    return path
```

Then find:

```python
        await page.add_init_script(combined)
        await page.goto(f"file://{APP_PATH}")
```

Change to:

```python
        await page.add_init_script(combined)
        patched_app_path = _write_patched_app_with_preview_enabled()
        await page.goto(f"file://{patched_app_path}")
```

And find the ending:

```python
        print("JS ERRORS:", errors)
        await browser.close()
```

Change to:

```python
        print("JS ERRORS:", errors)
        await browser.close()
        _os2.remove(patched_app_path)
```

Run: `cd tests && python3 test_regenerate.py`
Expected: identical output to before Task 1 — `button label before
(should be 'Generate preview'): Generate preview`, `thumbnail image
present after generate: 1`, `button label after (should be 'Regenerate
preview'): Regenerate preview`, `thumbnail image still present after
second regenerate: 1`, `persisted thumbnail_path: thumbnails/1.png` (or
similar), `JS ERRORS: []`.

- [ ] **Step 6: Run both files together to confirm no interference**

Run:
```bash
cd tests && python3 test_thumbnails.py && python3 test_regenerate.py
```
Expected: both scripts exit 0 with the outputs described in Steps 3, 4,
and 5 above, and no leftover `*.html` temp files in `tests/` afterward
(`ls tests/*.html` should show nothing — confirm with `ls tests/*.html
2>&1` printing "No such file or directory").

- [ ] **Step 7: Commit**

```bash
git add tests/test_thumbnails.py tests/test_regenerate.py
git commit -m "Update thumbnail tests for the SHOW_DOCUMENT_PREVIEW default

Both files now run against a copy of dossiary.html with the flag patched
to true, so they keep proving the underlying generate/regenerate/display
pipeline still works even though the UI is hidden by default. Adds a new
scenario to test_thumbnails.py confirming the real, unpatched app hides
the preview UI while still writing a real thumbnail file to disk."
```

---

### Task 3: Document the toggle in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md:420-438` (the existing "Document previews" note)

**Interfaces:**
- Consumes: the finished behavior from Tasks 1-2 (this task only
  documents it — no code changes).

- [ ] **Step 1: Read the existing note first**

Read CLAUDE.md's "Document previews" note in full (search for `**Document
previews**`) to match voice and confirm where the new paragraph should
land — at the end of that note, before the next `- **` bullet
("Dynamic per-type fields").

- [ ] **Step 2: Add a new paragraph**

In `CLAUDE.md`, find the end of the "Document previews" bullet:

```
  library and its worker script **must be the exact same pinned CDN
  version** (`PDFJS_VERSION`) — pdf.js throws a hard error if they
  mismatch, so don't update one without the other.
- **Dynamic per-type fields** (`typeFieldOrder`, `loadTypeFieldOrder()`,
```

Insert a new paragraph between them:

```
  library and its worker script **must be the exact same pinned CDN
  version** (`PDFJS_VERSION`) — pdf.js throws a hard error if they
  mismatch, so don't update one without the other.
  **The detail panel's own display of this preview is currently hidden
  behind `SHOW_DOCUMENT_PREVIEW` (`const`, declared right after
  `APP_VERSION`), a hardcoded developer-facing toggle, not a user-facing
  setting.** Off until there's a carousel/gallery-style view that would
  make a single static thumbnail worth its 110x140px of panel space
  again — see the `docs/superpowers/specs/2026-08-26-hide-document-preview-design.md`
  spec for the full reasoning. It gates exactly two things: the block in
  `openDetail()` that builds `thumbHtml` (when off, `thumbHtml` is `''`,
  not even the "no preview yet" empty-state placeholder, since that would
  still cost the same panel space), and the `regen-thumb` action
  descriptor in `buildDetailActions()` (when off, it's never added to the
  actions array, so "Generate preview"/"Regenerate preview" doesn't
  appear in the panel — it was already `panelOnly: true`, so it was never
  reachable from the row context menu regardless). Generation itself —
  `generateThumbnail()`/`writeThumbnail()` on capture and Inbox-add — is
  completely untouched by this flag and keeps running exactly as before,
  so `thumbnail_path` stays populated for every document captured while
  the toggle is off; reactivating the feature later needs no backfill,
  just flipping the constant back to `true`.
- **Dynamic per-type fields** (`typeFieldOrder`, `loadTypeFieldOrder()`,
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the SHOW_DOCUMENT_PREVIEW toggle"
```

---

### Task 4: Fix `test_detail_panel.py`'s Regenerate preview scenario

**Added after execution began** — Task 2's implementer correctly scoped
their brief to the two thumbnail-focused test files named in it, but
surfaced a real gap this plan's author missed while writing Task 2: a
scenario inside `tests/test_detail_panel.py` (part of that file's
"every action available in the old detail modal still working from the
panel" coverage) also clicks `#regen-thumb-btn` directly, and now fails
with a Playwright timeout since that element is hidden by default per
Task 1. This task closes that gap using the exact same technique Task 2
already established, applied to the one file it didn't cover.

**Files:**
- Modify: `tests/test_detail_panel.py`

**Interfaces:**
- Consumes: `SHOW_DOCUMENT_PREVIEW` (Task 1) and the same
  `_write_patched_app_with_preview_enabled()` pattern Task 2 introduced
  in `tests/test_thumbnails.py`/`tests/test_regenerate.py` — same helper
  body, same target/replacement strings.

Unlike `test_thumbnails.py`/`test_regenerate.py`, this file's Scenarios
1-16+ all share a single `page`/`page.goto()` call near the top of
`main()` — the Regenerate preview assertion (currently around line 165,
`await page.click('#regen-thumb-btn')`) is one assertion embedded deep in
that one continuous session, not an isolated scenario with its own fresh
page. The fix is the same as Task 2's: serve a copy of `dossiary.html`
with `SHOW_DOCUMENT_PREVIEW` patched to `true` for this file's one
`page.goto()` call, so every scenario in the file — including the later
one confirming "Regenerate preview never appears in the context menu"
(this stays true regardless of the flag, since that action was already
`panelOnly: true` before this plan) — keeps running exactly as it did
before Task 1, with no behavior-coverage lost.

- [ ] **Step 1: Add the identical patching helper**

In `tests/test_detail_panel.py`, right after the existing `APP_PATH` line
(currently line 5), add:

```python
import tempfile

def _write_patched_app_with_preview_enabled():
    """Writes a copy of dossiary.html with SHOW_DOCUMENT_PREVIEW flipped to
    true, so this file's "every panel action still works" coverage
    (including Regenerate preview) keeps exercising the real pipeline even
    though it now defaults to off (see dossiary.html's own
    SHOW_DOCUMENT_PREVIEW comment). Returns the temp file's path; caller
    is responsible for deleting it."""
    with open(APP_PATH) as f:
        html = f.read()
    target = "const SHOW_DOCUMENT_PREVIEW = false;"
    replacement = "const SHOW_DOCUMENT_PREVIEW = true;"
    assert target in html, "SHOW_DOCUMENT_PREVIEW declaration not found -- did its exact text change in dossiary.html?"
    patched = html.replace(target, replacement)
    fd, path = tempfile.mkstemp(suffix='.html', dir=_os2.path.dirname(APP_PATH))
    with _os2.fdopen(fd, 'w') as f:
        f.write(patched)
    return path
```

- [ ] **Step 2: Serve the patched copy**

Find the file's one `page.goto()` call (currently):

```python
        await page.goto(f"file://{APP_PATH}")
```

Change to:

```python
        patched_app_path = _write_patched_app_with_preview_enabled()
        await page.goto(f"file://{patched_app_path}")
```

- [ ] **Step 3: Clean up the temp file at the end**

Find the end of `main()` — this file's own final lines (structure may
differ slightly from Task 2's two files; find the actual
`await browser.close()` call) — and add cleanup immediately after it:

```python
        await browser.close()
        _os2.remove(patched_app_path)
```

- [ ] **Step 4: Run the full file and confirm everything passes**

Run: `cd tests && python3 test_detail_panel.py`
Expected: every scenario passes exactly as it did before Task 1 —
including `Regenerate preview reports the expected error (seed docs have
no file_path): True` and, later in the same run, `Regenerate preview
never appears in the context menu: True` — with `JS ERRORS: []`. If any
other assertion in this file changed behavior as a side effect of running
against the patched copy, stop and investigate before continuing — this
file should behave identically to its pre-Task-1 state from here on.

- [ ] **Step 5: Run the full 63-script suite**

Run:
```bash
cd tests && for f in test_*.py; do python3 "$f" > /tmp/task4_$f.log 2>&1; echo "EXIT:$? for $f"; done
```
Expected: 63/63 exit 0. This confirms the gap Task 2's implementer found
is fully closed and nothing else regressed.

- [ ] **Step 6: Commit**

```bash
git add tests/test_detail_panel.py
git commit -m "Fix test_detail_panel.py's Regenerate preview scenario for the SHOW_DOCUMENT_PREVIEW default

This file's own Regenerate-preview assertion (part of its broader "every
panel action still works" coverage) started failing once Task 1 hid that
button by default -- a real gap this plan missed, surfaced during Task 2's
implementation. Same patched-copy technique Task 2 already established,
applied to the one file it didn't cover."
```

---

## Self-Review

**1. Spec coverage** — every requirement from the approved spec
(`docs/superpowers/specs/2026-08-26-hide-document-preview-design.md`)
maps to a task: the single named toggle near `APP_VERSION` (Task 1 Step
1); gating `openDetail()`'s thumbnail block so nothing renders, not even
a placeholder, when off (Task 1 Step 2); gating `buildDetailActions()`'s
`regen-thumb` descriptor (Task 1 Step 3); leaving thumbnail generation on
capture/Inbox-add completely untouched (explicitly not modified by any
task, called out in Global Constraints and Task 3's doc note); the two
existing tests kept green via a patched-copy technique rather than
deleted (Task 2 Steps 1-3, 5); a new scenario proving default-off
behavior including that generation still happens (Task 2 Step 4); CLAUDE.md
documentation (Task 3). Out-of-scope items from the spec (a carousel/
gallery view, a user-facing setting, removing any of the underlying
generation code) are not implemented by any task.

**2. Placeholder scan** — no TBD/TODO; every step shows exact before/
after code, exact file locations, and exact expected output.

**3. Type/name consistency** — `SHOW_DOCUMENT_PREVIEW` is spelled
identically everywhere it's introduced (Task 1) and consumed (Task 2's
patching helper does an exact-string match against Task 1's own output
text, Task 3's doc note); `_write_patched_app_with_preview_enabled()` is
named and used identically in both `tests/test_thumbnails.py` and
`tests/test_regenerate.py` (Task 2 Steps 1 and 5) rather than drifting
into two slightly different helpers.

**4. A real ordering dependency worth restating**: Task 2's patching
helper does a literal string replace of `"const SHOW_DOCUMENT_PREVIEW =
false;"` — this must match Task 1 Step 1's added line character-for-
character (including the trailing semicolon, before the line's own
trailing comment). If a future change to that line's formatting doesn't
also update the two copies of this helper, the `assert target in html`
guard in both test files will fail loudly (not silently run against an
unpatched, still-hidden copy) — that assertion is deliberate, not
incidental, precisely to catch this kind of drift immediately rather than
letting these two tests quietly start testing the wrong thing again.
