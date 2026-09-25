# Orphaned Tags/People Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new sections to the "Library check" modal — "Orphaned tags" and "Orphaned people" — that detect `tags`/`people` rows not referenced by any non-deleted document, with a per-row "Delete" action and a per-section "Delete all orphaned" bulk action, both gated behind a native `confirm()`.

**Architecture:** `computeOrphanedTags(docs)`/`computeOrphanedPeople(docs)` are two small, persistence-free functions computed entirely in-memory from data already loaded onto `allDocs` (`d.tags`, `d.personFieldValues`) plus the existing `tagNameToId`/`personNameToId` maps — no new SQL query. `renderLibraryCheckResults()` gains two more parameters and two more sections; each orphaned row is a new, non-clickable markup shape (name + Delete button) since — unlike every other row in this modal — it doesn't represent a document. Deletion cascades into the relevant join table, updates the in-memory name maps, and refreshes the autocomplete datalists.

**Tech Stack:** Vanilla JS in `dossiary.html` (no framework), Playwright-driven Python test scripts against `tests/stub_studio2.js`.

## Global Constraints

- A tag/person is orphaned if its name is not referenced by any *non-deleted* document — a document sitting in the Waste bin does not count as "using" its tags/people.
- A person is checked against *every* person-type field (People, Author, Collaborator, ...) via `d.personFieldValues`, not just the built-in People field via `d.people`.
- Detection is entirely in-memory (`allDocs`, `tagNameToId`, `personNameToId`) — no new database query, no persisted state, no backfill. Runs fresh on every "Library check" open, same as `computeBrokenFileLinks()`.
- The two new sections render after the existing broken-file-links section, each omitted entirely when empty (same as every existing section).
- Orphaned rows are **not** clickable and do **not** reuse `.duplicate-row` — there's no document to open a detail panel for.
- Per-row Delete requires a `confirm()` naming the specific tag/person before deleting. Per-section "Delete all orphaned" requires its own single `confirm()` covering the whole section (not one confirm per row), with correct singular/plural wording.
- "Delete all orphaned" is a real bulk action: every `DELETE` for that section is queued first, then exactly one `persistDb()`/DOM update at the end — never one persist per row. A single per-row Delete is just one row, one write — no batching needed.
- Deleting a tag cascades: `DELETE FROM document_tags WHERE tag_id = ?` then `DELETE FROM tags WHERE id = ?`. Deleting a person cascades: `DELETE FROM document_field_people WHERE person_id = ?` then `DELETE FROM people WHERE id = ?`. Both refresh `populateDatalists()` afterward so the tag/person stops being suggested immediately.
- These `confirm()` dialogs are the first anywhere in this app's UI — no existing precedent to match, but every new i18n key must still follow the established per-language dense-line convention.
- Every test file must load `tests/stub_studio2.js` — never an embedded copy.

---

### Task 1: Detect orphaned tags/people and render them (no delete action yet)

**Files:**
- Modify: `dossiary.html` (new `computeOrphanedTags()`/`computeOrphanedPeople()` functions; `openLibraryCheckModal()` extended; `renderLibraryCheckResults()` extended with two more parameters and two more sections; new CSS; two new i18n keys across six languages; one new test-only debug hook)
- Test: `tests/test_orphaned_lookups.py` (new file)

**Interfaces:**
- Consumes: `allDocs` (existing module-level array, each document object already carrying `d.tags: string[]` and `d.personFieldValues: {[fieldName: string]: string[]}`). `tagNameToId`/`personNameToId` (existing module-level maps, `{name: id}`, the full roster of every tag/person row). `escapeHtml(s)`, `t(key, params)` (existing). `openLibraryCheckModal()`/`renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks)` (existing, from the shipped Library check / broken-file-links feature).
- Produces: `computeOrphanedTags(docs)` — sync function, takes an array of already non-deleted-filtered document objects, returns a sorted array of orphaned tag name strings. `computeOrphanedPeople(docs)` — same shape, for person names. `renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks, orphanedTags, orphanedPeople)` — now takes two more parameters, both arrays of plain name strings. New CSS classes `.duplicate-group-label-row`, `.orphaned-row` for Task 2 to also use. New i18n keys `libraryCheckOrphanedTagsLabel`, `libraryCheckOrphanedPeopleLabel` for Task 2's own additions to build on.

This task adds detection and read-only display only — no Delete button, no confirm(), no database writes for tags/people yet (that's Task 2). Rows show just the name, so this task's own tests only cover detection and rendering, not deletion.

- [ ] **Step 1: Add `computeOrphanedTags()` and `computeOrphanedPeople()`**

In `dossiary.html`, immediately after `computeBrokenFileLinks()` (which ends at line 5611, right before the blank line and `async function openLibraryCheckModal(){` at line 5613), insert:

```javascript
  // A tag is orphaned if no non-deleted document's own d.tags array contains
  // its name -- entirely in-memory, no new query, since every document's tags
  // are already loaded for display and tagNameToId already holds the full
  // roster of every tags row. A document sitting in the Waste bin doesn't
  // count as "using" its tags -- docs is expected to already be filtered to
  // non-deleted documents by the caller, same convention every other
  // compute*() function in this section already follows.
  function computeOrphanedTags(docs){
    const used = new Set(docs.flatMap(d => d.tags || []));
    return Object.keys(tagNameToId).filter(name => !used.has(name)).sort();
  }

  // Same as computeOrphanedTags() but for people -- checked across EVERY
  // person-type field a document might carry (d.personFieldValues holds all
  // of them keyed by field name, e.g. { People: [...], Author: [...] }), not
  // just the built-in People field's own d.people alias, since personNameToId
  // is a single global name registry shared across every person-type field.
  function computeOrphanedPeople(docs){
    const used = new Set(docs.flatMap(d => Object.values(d.personFieldValues || {}).flat()));
    return Object.keys(personNameToId).filter(name => !used.has(name)).sort();
  }

```

- [ ] **Step 2: Wire both into `openLibraryCheckModal()`**

In `dossiary.html`, find (lines 5672-5677):
```javascript
    const activeDocs = allDocs.filter(d => !d.deleted);
    const exactGroups = computeExactHashDuplicateGroups(activeDocs);
    const metadataGroups = computeMetadataDuplicateGroups(activeDocs);
    const brokenLinks = await computeBrokenFileLinks(activeDocs);
    renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks);
  }
```
Replace with:
```javascript
    const activeDocs = allDocs.filter(d => !d.deleted);
    const exactGroups = computeExactHashDuplicateGroups(activeDocs);
    const metadataGroups = computeMetadataDuplicateGroups(activeDocs);
    const brokenLinks = await computeBrokenFileLinks(activeDocs);
    const orphanedTags = computeOrphanedTags(activeDocs);
    const orphanedPeople = computeOrphanedPeople(activeDocs);
    renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks, orphanedTags, orphanedPeople);
  }
```

- [ ] **Step 3: Extend `renderLibraryCheckResults()` with the two new sections**

In `dossiary.html`, find the current function (lines 5679-5742):
```javascript
  function renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks){
    // Defensive: the modal could have been replaced by something else (e.g.
    // another modal opened via keyboard Tab-through while this one's close
    // button was disabled during a backfill) by the time this runs -- not a
    // full focus-trap, just a guard against writing into a container that's
    // no longer there.
    const listEl = el('duplicates-list');
    if(!listEl) return;
    if(!exactGroups.length && !metadataGroups.length && !brokenLinks.length){
      listEl.innerHTML = `<p id="duplicates-empty">${t('libraryCheckNoneFound')}</p>`;
      return;
    }
    const groupHtml = (group, labelKey) => `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label">${t(labelKey)}</div>
        ${group.map(d => `
          <div class="duplicate-row" data-document-id="${d.id}">
            <span class="doc-title">${escapeHtml(displayName(d))}</span>
            <span class="doc-sub">#${d.id}${d.date ? ' · ' + formatDate(d.date) : ''}</span>
          </div>
        `).join('')}
      </div>
    `;
    // Each broken-link row reuses .duplicate-row (for its existing click-to-
    // detail-panel wiring below) plus its own .broken-link-row marker class.
    // The indicators span stops propagation so clicking "Re-link..." (wired
    // just below) doesn't also trigger the row's own click-through.
    const brokenLinkRowHtml = (entry) => `
      <div class="duplicate-row broken-link-row" data-document-id="${entry.doc.id}">
        <span class="doc-title">${escapeHtml(displayName(entry.doc))}</span>
        <span class="broken-link-indicators" onclick="event.stopPropagation()">
          ${entry.broken.file ? `<span class="broken-link-indicator" data-path-field="file_path">${t('libraryCheckFileLabel')} <button type="button" class="relink-btn" data-document-id="${entry.doc.id}" data-path-field="file_path">${t('libraryCheckRelinkBtn')}</button></span>` : ''}
          ${entry.broken.original ? `<span class="broken-link-indicator" data-path-field="original_file_path">${t('libraryCheckOriginalLabel')} <button type="button" class="relink-btn" data-document-id="${entry.doc.id}" data-path-field="original_file_path">${t('libraryCheckRelinkBtn')}</button></span>` : ''}
        </span>
      </div>
    `;
    const brokenLinksSection = brokenLinks.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label">${t('libraryCheckBrokenLinksLabel')}</div>
        ${brokenLinks.map(brokenLinkRowHtml).join('')}
      </div>
    ` : '';
    listEl.innerHTML = [
      ...exactGroups.map(g => groupHtml(g, 'duplicatesExactMatchLabel')),
      ...metadataGroups.map(g => groupHtml(g, 'duplicatesMetadataMatchLabel')),
      brokenLinksSection,
    ].join('');
    listEl.querySelectorAll('.duplicate-row').forEach(row => {
      row.addEventListener('click', () => {
        const documentId = Number(row.dataset.documentId);
        closeModal();
        selectedDocId = documentId;
        render();
        openDetail(documentId);
      });
    });
    listEl.querySelectorAll('.relink-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const documentId = Number(btn.dataset.documentId);
        const pathField = btn.dataset.pathField;
        triggerRelink(documentId, pathField, btn.closest('.broken-link-indicator'));
      });
    });
  }
```

Replace it with:
```javascript
  function renderLibraryCheckResults(exactGroups, metadataGroups, brokenLinks, orphanedTags, orphanedPeople){
    // Defensive: the modal could have been replaced by something else (e.g.
    // another modal opened via keyboard Tab-through while this one's close
    // button was disabled during a backfill) by the time this runs -- not a
    // full focus-trap, just a guard against writing into a container that's
    // no longer there.
    const listEl = el('duplicates-list');
    if(!listEl) return;
    if(!exactGroups.length && !metadataGroups.length && !brokenLinks.length && !orphanedTags.length && !orphanedPeople.length){
      listEl.innerHTML = `<p id="duplicates-empty">${t('libraryCheckNoneFound')}</p>`;
      return;
    }
    const groupHtml = (group, labelKey) => `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label">${t(labelKey)}</div>
        ${group.map(d => `
          <div class="duplicate-row" data-document-id="${d.id}">
            <span class="doc-title">${escapeHtml(displayName(d))}</span>
            <span class="doc-sub">#${d.id}${d.date ? ' · ' + formatDate(d.date) : ''}</span>
          </div>
        `).join('')}
      </div>
    `;
    // Each broken-link row reuses .duplicate-row (for its existing click-to-
    // detail-panel wiring below) plus its own .broken-link-row marker class.
    // The indicators span stops propagation so clicking "Re-link..." (wired
    // just below) doesn't also trigger the row's own click-through.
    const brokenLinkRowHtml = (entry) => `
      <div class="duplicate-row broken-link-row" data-document-id="${entry.doc.id}">
        <span class="doc-title">${escapeHtml(displayName(entry.doc))}</span>
        <span class="broken-link-indicators" onclick="event.stopPropagation()">
          ${entry.broken.file ? `<span class="broken-link-indicator" data-path-field="file_path">${t('libraryCheckFileLabel')} <button type="button" class="relink-btn" data-document-id="${entry.doc.id}" data-path-field="file_path">${t('libraryCheckRelinkBtn')}</button></span>` : ''}
          ${entry.broken.original ? `<span class="broken-link-indicator" data-path-field="original_file_path">${t('libraryCheckOriginalLabel')} <button type="button" class="relink-btn" data-document-id="${entry.doc.id}" data-path-field="original_file_path">${t('libraryCheckRelinkBtn')}</button></span>` : ''}
        </span>
      </div>
    `;
    const brokenLinksSection = brokenLinks.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label">${t('libraryCheckBrokenLinksLabel')}</div>
        ${brokenLinks.map(brokenLinkRowHtml).join('')}
      </div>
    ` : '';
    // Orphaned tag/person rows deliberately do NOT use .duplicate-row -- unlike
    // every row above, these don't represent a document, so there's nothing to
    // click through to a detail panel for. Just the name and a Delete button
    // (wired in Task 2); .duplicate-group-label-row lets each section's own
    // label sit next to its own "Delete all orphaned" bulk button (also wired
    // in Task 2).
    const orphanedTagRowHtml = (name) => `
      <div class="orphaned-row">
        <span class="doc-title">${escapeHtml(name)}</span>
      </div>
    `;
    const orphanedPersonRowHtml = (name) => `
      <div class="orphaned-row">
        <span class="doc-title">${escapeHtml(name)}</span>
      </div>
    `;
    const orphanedTagsSection = orphanedTags.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label-row">
          <div class="duplicate-group-label">${t('libraryCheckOrphanedTagsLabel')}</div>
        </div>
        ${orphanedTags.map(orphanedTagRowHtml).join('')}
      </div>
    ` : '';
    const orphanedPeopleSection = orphanedPeople.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label-row">
          <div class="duplicate-group-label">${t('libraryCheckOrphanedPeopleLabel')}</div>
        </div>
        ${orphanedPeople.map(orphanedPersonRowHtml).join('')}
      </div>
    ` : '';
    listEl.innerHTML = [
      ...exactGroups.map(g => groupHtml(g, 'duplicatesExactMatchLabel')),
      ...metadataGroups.map(g => groupHtml(g, 'duplicatesMetadataMatchLabel')),
      brokenLinksSection,
      orphanedTagsSection,
      orphanedPeopleSection,
    ].join('');
    listEl.querySelectorAll('.duplicate-row').forEach(row => {
      row.addEventListener('click', () => {
        const documentId = Number(row.dataset.documentId);
        closeModal();
        selectedDocId = documentId;
        render();
        openDetail(documentId);
      });
    });
    listEl.querySelectorAll('.relink-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const documentId = Number(btn.dataset.documentId);
        const pathField = btn.dataset.pathField;
        triggerRelink(documentId, pathField, btn.closest('.broken-link-indicator'));
      });
    });
  }
```

(Task 2 will add the Delete button markup inside each `.orphaned-row`, the "Delete all orphaned" button inside each `.duplicate-group-label-row`, and their click wiring, right after this function.)

- [ ] **Step 4: Add the new CSS**

In `dossiary.html`, right after the existing `.relink-error{ color:var(--red); }` rule (line 195), insert:

```css
  .duplicate-group-label-row{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:6px; }
  .duplicate-group-label-row .duplicate-group-label{ margin-bottom:0; }
  .orphaned-row{ display:flex; justify-content:space-between; align-items:center; gap:12px; padding:8px 10px; border-radius:var(--radius); }
```

- [ ] **Step 5: Add the two new i18n keys across all six languages**

Same dense-line convention as the prior broken-file-links feature — append to the same line each language's `libraryCheckRelinkFailed` key sits on.

English (line 1072) — append after `libraryCheckRelinkFailed: 'Could not re-link: {error}',`:
```
libraryCheckOrphanedTagsLabel: 'Orphaned tags', libraryCheckOrphanedPeopleLabel: 'Orphaned people',
```

Spanish (line 1273) — append after `libraryCheckRelinkFailed: 'No se pudo volver a enlazar: {error}',`:
```
libraryCheckOrphanedTagsLabel: 'Etiquetas sin usar', libraryCheckOrphanedPeopleLabel: 'Personas sin usar',
```

French (line 1474) — append after `libraryCheckRelinkFailed: 'Impossible de relier le fichier : {error}',`:
```
libraryCheckOrphanedTagsLabel: 'Étiquettes inutilisées', libraryCheckOrphanedPeopleLabel: 'Personnes inutilisées',
```

German (line 1675) — append after `libraryCheckRelinkFailed: 'Datei konnte nicht neu verknüpft werden: {error}',`:
```
libraryCheckOrphanedTagsLabel: 'Unbenutzte Tags', libraryCheckOrphanedPeopleLabel: 'Unbenutzte Personen',
```

Chinese Simplified (line 1876) — append after `libraryCheckRelinkFailed: '无法重新链接：{error}',`:
```
libraryCheckOrphanedTagsLabel: '未使用的标签', libraryCheckOrphanedPeopleLabel: '未使用的人员',
```

Chinese Traditional (line 2203) — append after `libraryCheckRelinkFailed: '無法重新連結：{error}',`:
```
libraryCheckOrphanedTagsLabel: '未使用的標籤', libraryCheckOrphanedPeopleLabel: '未使用的人員',
```

- [ ] **Step 6: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: PASS — the two new keys must exist identically across all six `STRINGS` blocks.

- [ ] **Step 7: Add a test-only debug hook**

In `dossiary.html`, near line 3717 (right after `window.__DEBUG_computeBrokenFileLinks = computeBrokenFileLinks;`), add:

```javascript
  // Test-only: exposes computeOrphanedTags()/computeOrphanedPeople() directly,
  // same reasoning as __DEBUG_computeBrokenFileLinks above -- lets a test verify
  // detection output without going through the full modal-open flow.
  window.__DEBUG_computeOrphanedTags = computeOrphanedTags;
  window.__DEBUG_computeOrphanedPeople = computeOrphanedPeople;
```

- [ ] **Step 8: Write `tests/test_orphaned_lookups.py` (detection scenarios)**

This suite's real convention (confirmed by reading `tests/test_broken_links.py`, `tests/test_people.py`, and `tests/test_person_type_field.py` in full) is: `async def main(): ...; asyncio.run(main())` using `playwright.async_api`, stubbing `sql-wasm.js`/`tesseract`/`jspdf`/`pdf.js`, driving the real app UI to create documents, and printing `print("<description>:", <bool>)` lines. Tags don't need any per-type field configuration (`#f-tags` is always present, not part of the dynamic per-type fields system), so a plain `window.__makeEmptyRoot()` + `#open-btn` + `#init-btn` flow works for tag scenarios. People, however, **is** a per-type dynamic field now — it only renders for a document type it's configured for — so people-related scenarios need `window.__makeSeededEmptyRoot(typeFieldRows, fieldRows)` to pre-seed `document_type_fields` (exactly as `tests/test_people.py` and `tests/test_person_type_field.py` already do), and the non-People person-field scenario creates a brand new "Author" field inline via the real capture-form "+ Add a custom field" flow (exactly as `tests/test_person_type_field.py` already does), rather than trying to seed a custom `fields` row directly.

Create `tests/test_orphaned_lookups.py` with exactly this content:

```python
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
        await page.click('tr:has-text("Doc Two")')
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

        await page.click('#modal-close-btn')
        await page.wait_for_timeout(100)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

- [ ] **Step 9: Run the new test**

Run: `cd tests && python3 test_orphaned_lookups.py`
Expected: PASS, all checks green, `JS ERRORS: []`.

- [ ] **Step 10: Run the existing duplicate-detection and broken-links suites to confirm no regression**

Run: `cd tests && python3 test_duplicate_detection.py`
Run: `cd tests && python3 test_broken_links.py`
Expected: both PASS — the two extra `renderLibraryCheckResults()` parameters and the two new sections must not disturb any existing section's rendering or the "no issues found" empty-state check (which now must also account for `orphanedTags.length`/`orphanedPeople.length` being zero in those tests' own fixtures).

- [ ] **Step 11: Commit**

```bash
git add dossiary.html tests/test_orphaned_lookups.py
git commit -m "$(cat <<'EOF'
Detect orphaned tags/people in the Library check modal

Adds two persistence-free checks -- tags/people not referenced by any
non-deleted document -- rendered as two new sections in the Library
check modal. Detection and display only; delete actions land in the
next commit.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```

---

### Task 2: Add per-row and bulk Delete actions

**Files:**
- Modify: `dossiary.html` (Delete button markup added to `renderLibraryCheckResults()`'s orphaned-row/section-header HTML and its click wiring; new `deleteOrphanedTags()`/`deleteOrphanedPeople()` functions; seven new i18n keys across six languages)
- Test: `tests/test_orphaned_lookups.py` (extended with delete scenarios)

**Interfaces:**
- Consumes: `tagNameToId`/`personNameToId` (existing, mutated by this task). `populateDatalists()` (existing, dossiary.html:4701) — rebuilds every datalist, including `#tag-list`/`#person-list`, from the current `tagNameToId`/`personNameToId` maps. `persistDb()` (existing, dossiary.html:3440-ish) — no params. `db.run(sql, params)` (existing). `.orphaned-row`/`.duplicate-group-label-row` (from Task 1).
- Produces: `deleteOrphanedTags(names)` — async, takes an array of tag name strings (1 or many), deletes each from `tags`/cascades `document_tags`, updates `tagNameToId`, refreshes datalists, persists once at the end. `deleteOrphanedPeople(names)` — same shape for `people`/`document_field_people`/`personNameToId`. New i18n keys: `libraryCheckDeleteAllBtn`, `libraryCheckConfirmDeleteTag`, `libraryCheckConfirmDeletePerson`, `libraryCheckConfirmDeleteAllTagsSingular`, `libraryCheckConfirmDeleteAllTagsPlural`, `libraryCheckConfirmDeleteAllPeopleSingular`, `libraryCheckConfirmDeleteAllPeoplePlural`. Reuses the existing `commonDelete` key for the per-row Delete button text (already `'Delete'`/`'Eliminar'`/`'Supprimer'`/`'Löschen'`/`'删除'`/`'刪除'` in all six languages — do not mint a duplicate key for this).

- [ ] **Step 1: Add `deleteOrphanedTags()` and `deleteOrphanedPeople()`**

In `dossiary.html`, right after `performRelink()`'s closing `}` (the function ending at line 5822, right before `function openRemindersModal(dueReminders){`), insert:

```javascript
  // Deletes one or more orphaned tags outright: DELETE FROM tags (the row
  // itself) plus a cascade DELETE FROM document_tags WHERE tag_id = ? (cleans
  // up any stale join rows -- by construction, any remaining ones can only
  // belong to Waste-bin documents, since a live reference would have kept the
  // tag out of the orphaned list in the first place). Removes each name from
  // the in-memory tagNameToId map and refreshes every autocomplete datalist
  // (populateDatalists() rebuilds #tag-list from tagNameToId) so a deleted tag
  // stops being suggested immediately. A single-row delete and a many-row bulk
  // delete are the same operation here -- names.forEach queues every DELETE
  // first, then persistDb() runs exactly once at the end, matching this app's
  // existing bulk-action convention (bulkSetArchived() and siblings) rather
  // than persisting once per row.
  async function deleteOrphanedTags(names){
    names.forEach(name => {
      const id = tagNameToId[name];
      if(id === undefined) return;
      db.run('DELETE FROM document_tags WHERE tag_id = ?', [id]);
      db.run('DELETE FROM tags WHERE id = ?', [id]);
      delete tagNameToId[name];
    });
    populateDatalists();
    await persistDb();
  }

  // Same shape as deleteOrphanedTags() but for people -- DELETE FROM people
  // plus a cascade DELETE FROM document_field_people WHERE person_id = ?.
  async function deleteOrphanedPeople(names){
    names.forEach(name => {
      const id = personNameToId[name];
      if(id === undefined) return;
      db.run('DELETE FROM document_field_people WHERE person_id = ?', [id]);
      db.run('DELETE FROM people WHERE id = ?', [id]);
      delete personNameToId[name];
    });
    populateDatalists();
    await persistDb();
  }

```

- [ ] **Step 2: Add the Delete/Delete-all-orphaned button markup and wiring**

In `dossiary.html`, in `renderLibraryCheckResults()` (from Task 1), find:
```javascript
    const orphanedTagRowHtml = (name) => `
      <div class="orphaned-row">
        <span class="doc-title">${escapeHtml(name)}</span>
      </div>
    `;
    const orphanedPersonRowHtml = (name) => `
      <div class="orphaned-row">
        <span class="doc-title">${escapeHtml(name)}</span>
      </div>
    `;
    const orphanedTagsSection = orphanedTags.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label-row">
          <div class="duplicate-group-label">${t('libraryCheckOrphanedTagsLabel')}</div>
        </div>
        ${orphanedTags.map(orphanedTagRowHtml).join('')}
      </div>
    ` : '';
    const orphanedPeopleSection = orphanedPeople.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label-row">
          <div class="duplicate-group-label">${t('libraryCheckOrphanedPeopleLabel')}</div>
        </div>
        ${orphanedPeople.map(orphanedPersonRowHtml).join('')}
      </div>
    ` : '';
```
Replace with:
```javascript
    const orphanedTagRowHtml = (name) => `
      <div class="orphaned-row">
        <span class="doc-title">${escapeHtml(name)}</span>
        <button type="button" class="danger orphaned-delete-btn" data-kind="tag" data-name="${escapeHtml(name)}">${t('commonDelete')}</button>
      </div>
    `;
    const orphanedPersonRowHtml = (name) => `
      <div class="orphaned-row">
        <span class="doc-title">${escapeHtml(name)}</span>
        <button type="button" class="danger orphaned-delete-btn" data-kind="person" data-name="${escapeHtml(name)}">${t('commonDelete')}</button>
      </div>
    `;
    const orphanedTagsSection = orphanedTags.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label-row">
          <div class="duplicate-group-label">${t('libraryCheckOrphanedTagsLabel')}</div>
          <button type="button" class="danger orphaned-delete-all-btn" data-kind="tag">${t('libraryCheckDeleteAllBtn')}</button>
        </div>
        ${orphanedTags.map(orphanedTagRowHtml).join('')}
      </div>
    ` : '';
    const orphanedPeopleSection = orphanedPeople.length ? `
      <div class="fs-list-item duplicate-group">
        <div class="duplicate-group-label-row">
          <div class="duplicate-group-label">${t('libraryCheckOrphanedPeopleLabel')}</div>
          <button type="button" class="danger orphaned-delete-all-btn" data-kind="person">${t('libraryCheckDeleteAllBtn')}</button>
        </div>
        ${orphanedPeople.map(orphanedPersonRowHtml).join('')}
      </div>
    ` : '';
```

Then, still inside `renderLibraryCheckResults()`, right after the existing `.relink-btn` click-wiring block (`listEl.querySelectorAll('.relink-btn').forEach(...)`), add two new wiring blocks:
```javascript
    listEl.querySelectorAll('.orphaned-delete-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const kind = btn.dataset.kind;
        const name = btn.dataset.name;
        const confirmKey = kind === 'tag' ? 'libraryCheckConfirmDeleteTag' : 'libraryCheckConfirmDeletePerson';
        if(!confirm(t(confirmKey, {name}))) return;
        if(kind === 'tag') await deleteOrphanedTags([name]);
        else await deleteOrphanedPeople([name]);
        const row = btn.closest('.orphaned-row');
        const section = row.closest('.duplicate-group');
        row.remove();
        if(section && !section.querySelector('.orphaned-row')) section.remove();
      });
    });
    listEl.querySelectorAll('.orphaned-delete-all-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const kind = btn.dataset.kind;
        const section = btn.closest('.duplicate-group');
        const names = Array.from(section.querySelectorAll('.orphaned-delete-btn')).map(rowBtn => rowBtn.dataset.name);
        const count = names.length;
        const confirmKey = kind === 'tag'
          ? (count === 1 ? 'libraryCheckConfirmDeleteAllTagsSingular' : 'libraryCheckConfirmDeleteAllTagsPlural')
          : (count === 1 ? 'libraryCheckConfirmDeleteAllPeopleSingular' : 'libraryCheckConfirmDeleteAllPeoplePlural');
        if(!confirm(t(confirmKey, {count}))) return;
        if(kind === 'tag') await deleteOrphanedTags(names);
        else await deleteOrphanedPeople(names);
        section.remove();
      });
    });
```

- [ ] **Step 3: Add the seven new i18n keys across all six languages**

Append to the same dense line each language's Task-1 keys sit on, right after `libraryCheckOrphanedPeopleLabel: '...',`.

English (line 1072) — append:
```
libraryCheckDeleteAllBtn: 'Delete all orphaned', libraryCheckConfirmDeleteTag: 'Delete the unused tag "{name}"? This can\'t be undone.', libraryCheckConfirmDeletePerson: 'Delete the unused person "{name}"? This can\'t be undone.', libraryCheckConfirmDeleteAllTagsSingular: 'Delete this unused tag? This can\'t be undone.', libraryCheckConfirmDeleteAllTagsPlural: 'Delete these {count} unused tags? This can\'t be undone.', libraryCheckConfirmDeleteAllPeopleSingular: 'Delete this unused person? This can\'t be undone.', libraryCheckConfirmDeleteAllPeoplePlural: 'Delete these {count} unused people? This can\'t be undone.',
```

Spanish (line 1273) — append:
```
libraryCheckDeleteAllBtn: 'Eliminar todas las no usadas', libraryCheckConfirmDeleteTag: '¿Eliminar la etiqueta sin usar "{name}"? Esto no se puede deshacer.', libraryCheckConfirmDeletePerson: '¿Eliminar la persona sin usar "{name}"? Esto no se puede deshacer.', libraryCheckConfirmDeleteAllTagsSingular: '¿Eliminar esta etiqueta sin usar? Esto no se puede deshacer.', libraryCheckConfirmDeleteAllTagsPlural: '¿Eliminar estas {count} etiquetas sin usar? Esto no se puede deshacer.', libraryCheckConfirmDeleteAllPeopleSingular: '¿Eliminar esta persona sin usar? Esto no se puede deshacer.', libraryCheckConfirmDeleteAllPeoplePlural: '¿Eliminar estas {count} personas sin usar? Esto no se puede deshacer.',
```

French (line 1474) — append:
```
libraryCheckDeleteAllBtn: 'Supprimer tout ce qui est inutilisé', libraryCheckConfirmDeleteTag: 'Supprimer l\'étiquette inutilisée « {name} » ? Cette action est irréversible.', libraryCheckConfirmDeletePerson: 'Supprimer la personne inutilisée « {name} » ? Cette action est irréversible.', libraryCheckConfirmDeleteAllTagsSingular: 'Supprimer cette étiquette inutilisée ? Cette action est irréversible.', libraryCheckConfirmDeleteAllTagsPlural: 'Supprimer ces {count} étiquettes inutilisées ? Cette action est irréversible.', libraryCheckConfirmDeleteAllPeopleSingular: 'Supprimer cette personne inutilisée ? Cette action est irréversible.', libraryCheckConfirmDeleteAllPeoplePlural: 'Supprimer ces {count} personnes inutilisées ? Cette action est irréversible.',
```

German (line 1675) — append:
```
libraryCheckDeleteAllBtn: 'Alle unbenutzten löschen', libraryCheckConfirmDeleteTag: 'Unbenutzten Tag "{name}" löschen? Dies kann nicht rückgängig gemacht werden.', libraryCheckConfirmDeletePerson: 'Unbenutzte Person "{name}" löschen? Dies kann nicht rückgängig gemacht werden.', libraryCheckConfirmDeleteAllTagsSingular: 'Diesen unbenutzten Tag löschen? Dies kann nicht rückgängig gemacht werden.', libraryCheckConfirmDeleteAllTagsPlural: 'Diese {count} unbenutzten Tags löschen? Dies kann nicht rückgängig gemacht werden.', libraryCheckConfirmDeleteAllPeopleSingular: 'Diese unbenutzte Person löschen? Dies kann nicht rückgängig gemacht werden.', libraryCheckConfirmDeleteAllPeoplePlural: 'Diese {count} unbenutzten Personen löschen? Dies kann nicht rückgängig gemacht werden.',
```

Chinese Simplified (line 1876) — append:
```
libraryCheckDeleteAllBtn: '删除所有未使用项', libraryCheckConfirmDeleteTag: '删除未使用的标签"{name}"？此操作无法撤销。', libraryCheckConfirmDeletePerson: '删除未使用的人员"{name}"？此操作无法撤销。', libraryCheckConfirmDeleteAllTagsSingular: '删除这个未使用的标签？此操作无法撤销。', libraryCheckConfirmDeleteAllTagsPlural: '删除这 {count} 个未使用的标签？此操作无法撤销。', libraryCheckConfirmDeleteAllPeopleSingular: '删除这个未使用的人员？此操作无法撤销。', libraryCheckConfirmDeleteAllPeoplePlural: '删除这 {count} 个未使用的人员？此操作无法撤销。',
```

Chinese Traditional (line 2203) — append:
```
libraryCheckDeleteAllBtn: '刪除所有未使用項', libraryCheckConfirmDeleteTag: '刪除未使用的標籤"{name}"？此操作無法撤銷。', libraryCheckConfirmDeletePerson: '刪除未使用的人員"{name}"？此操作無法撤銷。', libraryCheckConfirmDeleteAllTagsSingular: '刪除這個未使用的標籤？此操作無法撤銷。', libraryCheckConfirmDeleteAllTagsPlural: '刪除這 {count} 個未使用的標籤？此操作無法撤銷。', libraryCheckConfirmDeleteAllPeopleSingular: '刪除這個未使用的人員？此操作無法撤銷。', libraryCheckConfirmDeleteAllPeoplePlural: '刪除這 {count} 個未使用的人員？此操作無法撤銷。',
```

- [ ] **Step 4: Run the i18n coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: PASS.

- [ ] **Step 5: Extend `tests/test_orphaned_lookups.py` with delete scenarios**

Playwright's Python API auto-dismisses any native `confirm()`/`alert()`/`prompt()` dialog unless a handler is registered — since this is the **first** `confirm()` anywhere in this app, there is no existing test-file precedent for handling it; use `page.once("dialog", ...)` immediately before the click that triggers each one, so each handler is scoped to exactly the one dialog it's meant for. Add these scenarios to `tests/test_orphaned_lookups.py`, inside the same `main()` (after the render-check scenarios from Task 1's Step 8, before `await browser.close()`), reusing the same still-open modal:

```python
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
```

- [ ] **Step 6: Run the extended test**

Run: `cd tests && python3 test_orphaned_lookups.py`
Expected: PASS, all checks green, including every delete/confirm/datalist/restore scenario.

- [ ] **Step 7: Run the full duplicate-detection and broken-links suites again**

Run: `cd tests && python3 test_duplicate_detection.py`
Run: `cd tests && python3 test_broken_links.py`
Expected: both PASS — confirms the new Delete/Delete-all buttons and their click wiring don't interfere with the pre-existing `.duplicate-row`/`.relink-btn` wiring in the same function.

- [ ] **Step 8: Commit**

```bash
git add dossiary.html tests/test_orphaned_lookups.py
git commit -m "$(cat <<'EOF'
Add per-row and bulk Delete for orphaned tags/people

Both require a native confirm() before acting -- the first confirm()
dialog anywhere in this app's UI, since this is the first genuinely
destructive action the Library check maintenance-feature family has
added. Deletion cascades into document_tags/document_field_people and
refreshes the tag/person autocomplete datalists immediately.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```

---

### Task 3: Document the feature in CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: nothing code-level — this is a documentation-only task.
- Produces: an updated architecture note for future readers of `CLAUDE.md`.

- [ ] **Step 1: Add an "Orphaned tags/people cleanup" architecture note**

In `CLAUDE.md`, immediately after the existing "Duplicate detection" note (search for `**Duplicate detection**` — the note ends right before `## How this was tested`; the broken-file-links rename note from the prior feature should already sit there too, right after Duplicate detection and before `## How this was tested`), add a new note in this repo's established voice (rationale-first, exact function/id names, explicit "what's deliberately not covered" callouts):

```markdown
- **Orphaned tags/people cleanup** (`computeOrphanedTags()`, `computeOrphanedPeople()`,
  `deleteOrphanedTags()`, `deleteOrphanedPeople()`) adds two more sections to the
  "Library check" modal: any `tags`/`people` row not referenced by any non-deleted
  document. Detection is entirely in-memory — every document already carries
  `d.tags` and `d.personFieldValues` (the latter covering *every* person-type
  field, not just the built-in People field, since `personNameToId` is one
  global name registry shared across all of them) — so no new database query,
  no persisted state, and no backfill are needed; both run fresh on every
  modal open, the same reasoning `computeBrokenFileLinks()` already uses.
  **A document sitting in the Waste bin doesn't count as "using" its
  tags/people** — a tag/person referenced only by a deleted document is
  flagged as orphaned — with one accepted, documented consequence: if such a
  tag/person is deleted while orphaned and the document is later restored, it
  comes back silently missing that tag/person, since the join row pointing at
  the now-gone id is harmless dead weight, not a broken reference.
  **Orphaned rows deliberately don't reuse `.duplicate-row`** — unlike every
  other row in this modal, an orphaned tag/person doesn't represent a
  document, so there's nothing to click through to a detail panel for; they
  get their own non-clickable `.orphaned-row` markup instead, just a name and
  a Delete button. **Deletion cascades into the relevant join table** —
  `DELETE FROM document_tags WHERE tag_id = ?` / `DELETE FROM
  document_field_people WHERE person_id = ?` — before removing the row
  itself, and refreshes every autocomplete datalist via the existing
  `populateDatalists()` so a deleted name stops being suggested immediately.
  **This is the first destructive action this maintenance-feature family has
  added** (duplicate detection and broken-file-links never destroy data), and
  correspondingly the first `confirm()` dialog anywhere in this app's own UI —
  both the per-row Delete and the per-section "Delete all orphaned" bulk
  action require one. The bulk action follows this app's existing
  bulk-action convention exactly: one shared `confirm()` for the whole
  section (not one per row), every `DELETE` queued first, and exactly one
  `persistDb()` at the end — `deleteOrphanedTags(names)`/
  `deleteOrphanedPeople(names)` take an array specifically so a single-row
  delete and a many-row bulk delete are the same function call with a
  1-element array, not two separate code paths.
```

- [ ] **Step 2: Verify the new note reads correctly in context**

Read the surrounding paragraphs in `CLAUDE.md` once the insertion is made, confirming it doesn't duplicate or contradict anything already said about the Library check modal, `computeBrokenFileLinks()`, or `populateDatalists()`, and that it's inserted in shipping-chronological order relative to its neighbors (right after the broken-file-links note, right before `## How this was tested`).

- [ ] **Step 3: Update `tests/CLAUDE.md`'s test-count and coverage summary**

`tests/CLAUDE.md`'s own "How this was tested" section states an exact test-script count near its top (currently 69 scripts, 67 Playwright-driven — confirm the exact current numbers by reading that file before editing, since they may have shifted again) and lists every test file's own coverage in one long paragraph. Add one more sentence to that paragraph (following the exact style of its existing `test_broken_links.py` entry) describing `test_orphaned_lookups.py`'s coverage: a tag/person still used by a non-deleted document is never flagged; one used only by a Waste-bin document is flagged; a person used via a non-People person-type field (Author) is correctly recognized as in-use; per-row Delete (with its own `confirm()`) removes just that row and cascades into the join table; declining the `confirm()` leaves everything unchanged; "Delete all orphaned" clears every row in a section in one action behind its own single `confirm()`; a deleted tag/person disappears from its autocomplete datalist immediately; and restoring a Waste-bin document whose tag was deleted while orphaned comes back without it. Also bump the script-count numbers by one (69→70 total, 67→68 Playwright-driven) to match the new file.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document orphaned tags/people cleanup

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01HoNFcEvEmmgGvnEBteYYty
EOF
)"
```
