# Reports drill-down Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Reports row (breakdown rows, the Grand Total row, and the "(none)" row) clickable, jumping to an ordinary, filtered view of the real document table showing exactly the documents that contributed to that row.

**Architecture:** `computeReportGroups()` gains a `docIds` array per row (and `grandTotalDocIds` on the group), trivial to add since it already iterates every document. A new `'report-drilldown'` nav view reuses the existing `currentView`/`matchesView()`/`setView()` machinery: clicking a row calls `drillIntoReportRow(docIds, label)`, which snapshots the IDs into a module-level `Set` and a label string, then switches views. A banner (mirroring `#inbox-banner`'s existing pattern) shows the label and a "← Back to Reports" link. No persistence, no schema change — this is ephemeral, per-click session state exactly like `currentView` itself.

**Tech Stack:** Vanilla JS inside `dossiary.html`'s single IIFE; Playwright tests extending `tests/test_reports.py`; no new dependencies.

## Global Constraints

- Single-file app — all changes live in `dossiary.html`, `tests/test_reports.py`, `CLAUDE.md`, `tests/CLAUDE.md`. No new files.
- No new persistence — `reportDrilldownIds`/`reportDrilldownLabel` are session-only module-level state, reset in `resetAll()`, never written to `settings` or any table.
- `docIds` is a frozen snapshot at click time, not a live filter (per the approved spec's "Data flow & multi-valued fields" section).
- `matchesView()`'s new `'report-drilldown'` branch must include archived and needs-review documents, excluding only `deleted` — the same rule Reports/Collections already use, since a drill-down is conceptually the same kind of saved/curated view.
- All 6 supported languages (`en`, `de`, `es`, `fr`, `zh-Hans`, `zh-Hant`) need every new i18n key — `tests/test_i18n_coverage.py` fails the whole suite otherwise.
- Reuse the `.inbox-banner` CSS class for the new banner (identical styling to the existing conditional-banner pattern), not a new CSS block.
- Reuse `reportsGrandTotal`/`reportsNone`/`reportsNoCurrencySet` i18n keys rather than minting near-duplicates, matching this codebase's established "reuse existing keys" convention (see `CLAUDE.md`'s UI-language-support note).

---

### Task 1: Drill-down data model, view plumbing, and click-through UI

**Files:**
- Modify: `dossiary.html` (multiple sections, exact line numbers below — re-verify with `grep`/`Read` before editing, since line numbers shift as the file is edited within this task)
- Test: `tests/test_reports.py` (extend with new scenarios)

**Interfaces:**
- Produces: `drillIntoReportRow(docIds, label)` — module-level function; `reportDrilldownIds` (Set of doc ids), `reportDrilldownLabel` (string) — module-level state; `updateReportDrilldownBanner()` — module-level function called from `render()`.
- Consumes: `computeReportGroups()` (extended, same task), `matchesView()`, `setView()`, `render()`, `resetAll()`, `el()`, `t()`, `escapeHtml()` — all pre-existing.

#### Step 1: Add `docIds` to `computeReportGroups()`

`computeReportGroups()` currently lives around line 4722-4750 of `dossiary.html` (confirm with `grep -n "function computeReportGroups"` before editing, since earlier tasks in this session may have shifted it). Current code:

```js
  function computeReportGroups(docs, fieldId){
    const info = reportBreakdownFieldInfo(fieldId);
    if(!info) return [];
    const byCurrency = {};
    for(const d of docs){
      const currency = (d.customFields || {})['Currency'] || null;
      const key = currency || '__no_currency__';
      (byCurrency[key] = byCurrency[key] || { currency, docs: [] }).docs.push(d);
    }
    return Object.keys(byCurrency).sort().map(key => {
      const group = byCurrency[key];
      const rows = {};
      for(const d of group.docs){
        const amount = numericAmount(d);
        for(const rawValue of info.getValues(d)){
          const label = (rawValue == null || rawValue === '') ? t('reportsNone') : rawValue;
          const row = (rows[label] = rows[label] || { label, count: 0, total: 0 });
          row.count += 1;
          if(amount != null) row.total += amount;
        }
      }
      const rowList = Object.values(rows).sort((a, b) => (b.total - a.total) || a.label.localeCompare(b.label));
      const grandTotal = group.docs.reduce((sum, d) => { const a = numericAmount(d); return sum + (a != null ? a : 0); }, 0);
      return {
        currency: group.currency, rows: rowList, grandTotal,
        documentCount: group.docs.length, multiValued: info.multiValued, breakdownLabel: info.label,
      };
    });
  }
```

Replace it with:

```js
  function computeReportGroups(docs, fieldId){
    const info = reportBreakdownFieldInfo(fieldId);
    if(!info) return [];
    const byCurrency = {};
    for(const d of docs){
      const currency = (d.customFields || {})['Currency'] || null;
      const key = currency || '__no_currency__';
      (byCurrency[key] = byCurrency[key] || { currency, docs: [] }).docs.push(d);
    }
    return Object.keys(byCurrency).sort().map(key => {
      const group = byCurrency[key];
      const rows = {};
      for(const d of group.docs){
        const amount = numericAmount(d);
        for(const rawValue of info.getValues(d)){
          const label = (rawValue == null || rawValue === '') ? t('reportsNone') : rawValue;
          const row = (rows[label] = rows[label] || { label, count: 0, total: 0, docIds: [] });
          row.count += 1;
          row.docIds.push(d.id);
          if(amount != null) row.total += amount;
        }
      }
      const rowList = Object.values(rows).sort((a, b) => (b.total - a.total) || a.label.localeCompare(b.label));
      const grandTotal = group.docs.reduce((sum, d) => { const a = numericAmount(d); return sum + (a != null ? a : 0); }, 0);
      return {
        currency: group.currency, rows: rowList, grandTotal,
        documentCount: group.docs.length, multiValued: info.multiValued, breakdownLabel: info.label,
        // The Grand Total row's own docIds -- every document in this currency group,
        // independent of the breakdown field (same "computed independently, not by
        // summing the rows" property grandTotal itself already has).
        grandTotalDocIds: group.docs.map(d => d.id),
      };
    });
  }
```

#### Step 2: Add module-level drill-down state

Find `let currentView = 'all';     // 'all' | 'inbox' | 'trash' | 'reports'` (around line 2374; confirm with `grep -n "let currentView = 'all'"`). Replace with:

```js
  let currentView = 'all';     // 'all' | 'inbox' | 'trash' | 'reports' | 'report-drilldown' | 'collection-<id>'
  // A frozen, ad-hoc snapshot captured the moment a Reports row is clicked -- see
  // drillIntoReportRow() and matchesView()'s own 'report-drilldown' branch below.
  // Not a live filter: editing a document afterward doesn't remove it from a
  // still-open drill-down, only a future click on a freshly-rendered report can.
  let reportDrilldownIds = new Set();
  let reportDrilldownLabel = '';
```

#### Step 3: Add `drillIntoReportRow()` and `updateReportDrilldownBanner()`

Insert these two new functions immediately after `renderReportsView()` closes (currently ending around line 4773 with `el('reports-print-btn').addEventListener('click', () => window.print());\n  }`), before the `formatCustomFieldValue()` function:

```js
  // Stores a frozen snapshot of document IDs from a clicked Reports row (or its
  // Grand Total row) and switches to the report-drilldown view -- an ordinary
  // view of the real document table, filtered to exactly those IDs via
  // matchesView()'s own 'report-drilldown' branch below.
  function drillIntoReportRow(docIds, label){
    reportDrilldownIds = new Set(docIds);
    reportDrilldownLabel = label;
    setView('report-drilldown');
  }

  // Shows/hides the banner above the document table whenever currentView is
  // 'report-drilldown' -- the same conditional-banner pattern updateInboxBanner()
  // already uses for the Inbox view's own staged-files notice. Called from
  // render()'s normal document-table path (Reports view itself returns earlier
  // and never reaches this call).
  function updateReportDrilldownBanner(){
    const banner = el('report-drilldown-banner');
    if(currentView === 'report-drilldown'){
      banner.style.display = 'flex';
      const count = reportDrilldownIds.size;
      const countText = count === 1 ? t('reportDrilldownCountSingular', {count}) : t('reportDrilldownCountPlural', {count});
      el('report-drilldown-banner-text').textContent = `${reportDrilldownLabel} — ${countText}`;
    } else {
      banner.style.display = 'none';
    }
  }
```

#### Step 4: Wire click handlers in `renderReportsView()`

`renderReportsView()` currently reads (around line 4754-4773; confirm with `grep -n "function renderReportsView"`):

```js
  function renderReportsView(docs){
    const breakdownSelect = el('report-breakdown-field');
    const fieldId = breakdownSelect ? breakdownSelect.value : 'category';
    const groups = computeReportGroups(docs, fieldId);
    const groupsHtml = groups.length ? groups.map(g => `
      <div class="report-currency-group">
        <h3>${g.currency ? escapeHtml(g.currency) : t('reportsNoCurrencySet')}</h3>
        ${g.multiValued ? `<p class="report-caption">${t('reportsMultiValueCaption', {label: escapeHtml(g.breakdownLabel)})}</p>` : ''}
        <table class="report-table">
          <thead><tr><th>${escapeHtml(g.breakdownLabel)}</th><th>${t('reportsColCount')}</th><th>${t('reportsColTotal')}</th></tr></thead>
          <tbody>
            ${g.rows.map(r => `<tr><td>${escapeHtml(r.label)}</td><td>${r.count}</td><td>${r.total.toFixed(2)}</td></tr>`).join('')}
          </tbody>
          <tfoot><tr><td>${t('reportsGrandTotal')}</td><td>${g.documentCount}</td><td>${g.grandTotal.toFixed(2)}</td></tr></tfoot>
        </table>
      </div>
    `).join('') : `<p id="reports-empty">${t('reportsNoDocuments')}</p>`;
    reportsView.innerHTML = `<button type="button" id="reports-print-btn" class="report-print-btn">${t('reportsPrintButton')}</button>` + groupsHtml;
    el('reports-print-btn').addEventListener('click', () => window.print());
  }
```

Replace it with:

```js
  function renderReportsView(docs){
    const breakdownSelect = el('report-breakdown-field');
    const fieldId = breakdownSelect ? breakdownSelect.value : 'category';
    const groups = computeReportGroups(docs, fieldId);
    const groupsHtml = groups.length ? groups.map((g, gi) => `
      <div class="report-currency-group">
        <h3>${g.currency ? escapeHtml(g.currency) : t('reportsNoCurrencySet')}</h3>
        ${g.multiValued ? `<p class="report-caption">${t('reportsMultiValueCaption', {label: escapeHtml(g.breakdownLabel)})}</p>` : ''}
        <table class="report-table">
          <thead><tr><th>${escapeHtml(g.breakdownLabel)}</th><th>${t('reportsColCount')}</th><th>${t('reportsColTotal')}</th></tr></thead>
          <tbody>
            ${g.rows.map((r, ri) => `<tr class="report-row" data-group-idx="${gi}" data-row-idx="${ri}"><td>${escapeHtml(r.label)}</td><td>${r.count}</td><td>${r.total.toFixed(2)}</td></tr>`).join('')}
          </tbody>
          <tfoot><tr class="report-row" data-group-idx="${gi}" data-row-idx="grand"><td>${t('reportsGrandTotal')}</td><td>${g.documentCount}</td><td>${g.grandTotal.toFixed(2)}</td></tr></tfoot>
        </table>
      </div>
    `).join('') : `<p id="reports-empty">${t('reportsNoDocuments')}</p>`;
    reportsView.innerHTML = `<button type="button" id="reports-print-btn" class="report-print-btn">${t('reportsPrintButton')}</button>` + groupsHtml;
    el('reports-print-btn').addEventListener('click', () => window.print());
    // Every row -- breakdown rows, the "(none)" row (just another row from
    // computeReportGroups()'s own perspective), and each group's Grand Total row --
    // is clickable, jumping to a filtered document list of exactly the documents
    // that contributed to it. `groups` stays in closure scope for these listeners,
    // so data-group-idx/data-row-idx are enough to look the right row back up.
    reportsView.querySelectorAll('.report-row').forEach(tr => {
      tr.addEventListener('click', () => {
        const group = groups[Number(tr.dataset.groupIdx)];
        const currencyLabel = group.currency || t('reportsNoCurrencySet');
        if(tr.dataset.rowIdx === 'grand'){
          drillIntoReportRow(group.grandTotalDocIds, t('reportDrilldownGrandTotalLabel', {currency: currencyLabel}));
        } else {
          const row = group.rows[Number(tr.dataset.rowIdx)];
          const labelKey = group.multiValued ? 'reportDrilldownMultiValueLabel' : 'reportDrilldownRowLabel';
          drillIntoReportRow(row.docIds, t(labelKey, {field: group.breakdownLabel, value: row.label}));
        }
      });
    });
  }
```

#### Step 5: Add the `matchesView()` branch

`matchesView()` currently has, right after `if(view === 'reports') return true;` and its trailing comment (around line 4881), a comment block then `if(view.startsWith('collection-')){...}` (around line 4896). Confirm current line numbers with `grep -n "if(view === 'reports') return true;" dossiary.html` and `grep -n "if(view.startsWith('collection-'))" dossiary.html`. Insert the new branch between them, immediately before the `// A collection view -- 'collection-<id>'.` comment:

```js
    // Report drill-down: a frozen, ad-hoc snapshot of document IDs captured at
    // the moment a Reports row was clicked (see drillIntoReportRow()) -- not a
    // live-updating filter, so editing a document afterward doesn't remove it
    // from a still-open drill-down; only a future click on a freshly-rendered
    // report can produce a different snapshot. Same archived/needs-review-
    // inclusive semantics as Reports and Collections above, since this is
    // conceptually the same kind of saved/curated view, not a day-to-day browse
    // view. Only `deleted` is excluded, via the shared check above.
    if(view === 'report-drilldown') return reportDrilldownIds.has(d.id);
```

#### Step 6: Update `setView()`'s allowlist

`setView()` currently reads (around line 5035-5041):

```js
  function setView(view){
    if(view !== 'all' && view !== 'inbox' && view !== 'trash' && view !== 'reports' && !view.startsWith('collection-')) return;
    if(currentView === view) return;
    currentView = view;
    selectedDocIds = new Set();
    render();
  }
```

Change the allowlist line to also permit `'report-drilldown'`:

```js
  function setView(view){
    if(view !== 'all' && view !== 'inbox' && view !== 'trash' && view !== 'reports' && view !== 'report-drilldown' && !view.startsWith('collection-')) return;
    if(currentView === view) return;
    currentView = view;
    selectedDocIds = new Set();
    render();
  }
```

#### Step 7: Wire the banner and fix the denominator in `render()`

`render()`'s normal document-table path currently reads (around line 5077-5087):

```js
    reportsView.style.display = 'none';
    tableWrap.style.display = 'block';
    countLine.style.display = 'block';
    // For collections, compute the denominator directly since navCounts only has keys for all/inbox/trash
    let denominator;
    if(currentView.startsWith('collection-')){
      denominator = allDocs.filter(d => matchesView(d, currentView, showArchivedToggle.checked)).length;
    } else {
      denominator = navCounts[currentView];
    }
    countLine.textContent = t('tableShowingCount', {shown: sorted.length, total: denominator});
```

Replace with:

```js
    reportsView.style.display = 'none';
    tableWrap.style.display = 'block';
    countLine.style.display = 'block';
    updateReportDrilldownBanner();
    // For collections, compute the denominator directly since navCounts only has keys for all/inbox/trash.
    // report-drilldown has no navCounts entry either (it's not one of the four
    // persistent nav views) -- its own denominator is just the snapshot's own size.
    let denominator;
    if(currentView.startsWith('collection-')){
      denominator = allDocs.filter(d => matchesView(d, currentView, showArchivedToggle.checked)).length;
    } else if(currentView === 'report-drilldown'){
      denominator = reportDrilldownIds.size;
    } else {
      denominator = navCounts[currentView];
    }
    countLine.textContent = t('tableShowingCount', {shown: sorted.length, total: denominator});
```

#### Step 8: Reset drill-down state in `resetAll()`

`resetAll()` currently has (around line 3221-3223):

```js
    collections = []; collectionDocIds = {}; nextCollectionId = 1; collectionsNavExpanded = true; selectedDocIds = new Set();
    reminderSnoozes = {};
    selectedDocId = null;
```

Change to:

```js
    collections = []; collectionDocIds = {}; nextCollectionId = 1; collectionsNavExpanded = true; selectedDocIds = new Set();
    reminderSnoozes = {};
    reportDrilldownIds = new Set(); reportDrilldownLabel = '';
    selectedDocId = null;
```

And a few lines further down, `resetAll()` currently has (around line 3239):

```js
    el('inbox-banner').style.display = 'none';
```

Change to:

```js
    el('inbox-banner').style.display = 'none';
    el('report-drilldown-banner').style.display = 'none';
```

#### Step 9: Add the banner HTML

Find the existing `#inbox-banner` markup (around line 705-708) and the `#count-line`/`#bulk-action-bar` markup a little further down (around line 733-735; confirm with `grep -n 'id="count-line"' dossiary.html` and `grep -n 'id="bulk-action-bar"' dossiary.html`):

```html
      <div class="count-line" id="count-line" style="display:none;"></div>

      <div class="bulk-action-bar" id="bulk-action-bar" style="display:none;">
```

Insert the new banner between them, reusing the `.inbox-banner` class (identical amber-toned styling, per this app's established "reuse this exact CSS class" pattern for conditional banners):

```html
      <div class="count-line" id="count-line" style="display:none;"></div>

      <div class="inbox-banner" id="report-drilldown-banner" style="display:none;">
        <span id="report-drilldown-banner-text"></span>
        <button type="button" id="report-drilldown-back-btn" data-i18n="reportDrilldownBackLink">← Back to Reports</button>
      </div>

      <div class="bulk-action-bar" id="bulk-action-bar" style="display:none;">
```

#### Step 10: Wire the back button

Find the static event-wiring block near the bottom of the IIFE, right after `el('inbox-add-all-btn').addEventListener('click', addAllInboxFilesAndShowStatus);` (around line 8219; confirm with `grep -n "inbox-add-all-btn').addEventListener"`). Add immediately after it:

```js
  el('inbox-add-all-btn').addEventListener('click', addAllInboxFilesAndShowStatus);
  // "← Back to Reports" in the drill-down banner -- setView() itself handles the
  // "already on this view" no-op case, so this needs no guard of its own.
  el('report-drilldown-back-btn').addEventListener('click', () => setView('reports'));
```

#### Step 11: Update the report-table CSS -- rows are clickable now

Find (around line 335-341; confirm with `grep -n "Report headers aren't sortable"`):

```css
  /* Report headers aren't sortable and report rows aren't clickable, unlike the
     generic .table/thead/tbody styling this reuses -- override the inherited
     clickable/sortable hover cues so they don't mislead. */
  .report-table thead th{ cursor:default; }
  .report-table thead th:hover{ color:var(--text-dim); }
  .report-table tbody tr{ cursor:default; }
  .report-table tbody tr:hover{ background:transparent; }
```

Replace with:

```css
  /* Report headers still aren't sortable -- override the inherited sortable hover
     cue so it doesn't mislead. Body/footer rows, unlike headers, ARE now
     clickable (see drillIntoReportRow()), so they get a pointer cursor and a
     hover highlight instead of the inherited-but-wrong "clickable row" default
     this app's plain .table styling already establishes elsewhere. */
  .report-table thead th{ cursor:default; }
  .report-table thead th:hover{ color:var(--text-dim); }
  .report-table tbody tr, .report-table tfoot tr{ cursor:pointer; }
  .report-table tbody tr:hover, .report-table tfoot tr:hover{ background:var(--ink-2); }
```

(No `@media print` change needed: the new banner reuses the `.inbox-banner` class, which is already in that block's hide-list, and it's never visible from the Reports view the print button lives in anyway.)

#### Step 12: Add the new i18n keys to all six languages

Find each language's `reportsBreakdownCategory: ..., reportsBreakdownType: ..., reportsBreakdownPeople: ...,` line and insert a new line immediately after it, before that block's next line (`librariesTitle: ...`). Confirm current line numbers with `grep -n "reportsBreakdownPeople:" dossiary.html` (6 matches, one per language, in `en`/`es`/`fr`/`de`/`zh-Hans`/`zh-Hant` order as they appear in the file).

**English** (after `reportsBreakdownCategory: 'Category', reportsBreakdownType: 'Type', reportsBreakdownPeople: 'People',`):

```js
      reportDrilldownRowLabel: '{field}: {value}', reportDrilldownMultiValueLabel: '{field} includes: {value}',
      reportDrilldownGrandTotalLabel: 'Grand total ({currency})', reportDrilldownBackLink: '← Back to Reports',
      reportDrilldownCountSingular: '{count} document', reportDrilldownCountPlural: '{count} documents',
```

**Spanish** (after `reportsBreakdownCategory: 'Categoría', reportsBreakdownType: 'Tipo', reportsBreakdownPeople: 'Personas',`):

```js
      reportDrilldownRowLabel: '{field}: {value}', reportDrilldownMultiValueLabel: '{field} incluye: {value}',
      reportDrilldownGrandTotalLabel: 'Total general ({currency})', reportDrilldownBackLink: '← Volver a Informes',
      reportDrilldownCountSingular: '{count} documento', reportDrilldownCountPlural: '{count} documentos',
```

**French** (after `reportsBreakdownCategory: 'Catégorie', reportsBreakdownType: 'Type', reportsBreakdownPeople: 'Personnes',`):

```js
      reportDrilldownRowLabel: '{field} : {value}', reportDrilldownMultiValueLabel: '{field} inclut : {value}',
      reportDrilldownGrandTotalLabel: 'Total général ({currency})', reportDrilldownBackLink: '← Retour aux rapports',
      reportDrilldownCountSingular: '{count} document', reportDrilldownCountPlural: '{count} documents',
```

**German** (after `reportsBreakdownCategory: 'Kategorie', reportsBreakdownType: 'Typ', reportsBreakdownPeople: 'Personen',`):

```js
      reportDrilldownRowLabel: '{field}: {value}', reportDrilldownMultiValueLabel: '{field} enthält: {value}',
      reportDrilldownGrandTotalLabel: 'Gesamtsumme ({currency})', reportDrilldownBackLink: '← Zurück zu Berichten',
      reportDrilldownCountSingular: '{count} Dokument', reportDrilldownCountPlural: '{count} Dokumente',
```

**Chinese Simplified** (after `reportsBreakdownCategory: '分类', reportsBreakdownType: '类型', reportsBreakdownPeople: '人员',`):

```js
      reportDrilldownRowLabel: '{field}：{value}', reportDrilldownMultiValueLabel: '{field}包含：{value}',
      reportDrilldownGrandTotalLabel: '总计（{currency}）', reportDrilldownBackLink: '← 返回报表',
      reportDrilldownCountSingular: '{count} 份文档', reportDrilldownCountPlural: '{count} 份文档',
```

**Chinese Traditional** (this block is split one-key-per-line, unlike the
denser style the other five languages use; insert after the line
`reportsBreakdownPeople: '人員',`, immediately before `librariesTitle: '開源庫',`,
following this language block's own one-key-per-line style):

```js
      reportDrilldownRowLabel: '{field}：{value}',
      reportDrilldownMultiValueLabel: '{field}包含：{value}',
      reportDrilldownGrandTotalLabel: '總計（{currency}）',
      reportDrilldownBackLink: '← 返回報表',
      reportDrilldownCountSingular: '{count} 份文檔',
      reportDrilldownCountPlural: '{count} 份文檔',
```

#### Step 13: Run the existing suite to confirm nothing regressed

```bash
cd tests && python3 test_reports.py
```

Expected: every existing `print()` line still reports the same values as before this task's changes (Scenarios 1-12 are unchanged in behavior — only new rows/CSS/state were added, no existing return values changed). `JS ERRORS: []`.

Also run:

```bash
cd tests && python3 test_i18n_coverage.py
```

Expected: passes — confirms all 6 new keys exist in every language with matching key sets.

#### Step 14: Add drill-down test scenarios to `tests/test_reports.py`

Insert these new scenarios after the existing Scenario 12 (`await page.emulate_media(media="screen")`, just before the `print("JS ERRORS:", errors)` line at the end of `main()`). Add this helper function above `async def main():` (after the `SEED` dict, before `async def main():`):

```python
async def click_report_row_by_label(page, currency_group_index, label_text):
    """Clicks the row (breakdown row or Grand Total row) in the given currency
    group whose first cell reads exactly label_text. Locating by cell text,
    not row index, keeps these scenarios robust to sort-order changes in
    computeReportGroups()."""
    group = page.locator('.report-currency-group').nth(currency_group_index)
    rows = group.locator('.report-table tbody tr, .report-table tfoot tr')
    n = await rows.count()
    for i in range(n):
        text = (await rows.nth(i).locator('td').first.inner_text()).strip()
        if text == label_text:
            await rows.nth(i).click()
            return
    raise AssertionError(f"No report row with label {label_text!r} found in currency group {currency_group_index}")
```

Then, replacing the file's existing closing lines:

```python
        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

with:

```python
        # === Scenario 13: clicking a breakdown row (Category "Travel" in the EUR
        # group -- docs 1, 2, 7, per Scenario 7's own breakdown) lands on the
        # report-drilldown view showing exactly those documents, with the correct
        # banner text and document count ===
        await page.click('#nav-item-reports')
        await page.wait_for_timeout(150)
        await click_report_row_by_label(page, 0, 'Travel')
        await page.wait_for_timeout(150)
        table_visible_drilldown = await page.locator('#table-wrap').is_visible()
        drilldown_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => Number(e.dataset.id)).sort((a,b) => a-b)')
        banner_visible = await page.locator('#report-drilldown-banner').is_visible()
        banner_text = await page.locator('#report-drilldown-banner-text').inner_text()
        print("Table visible after clicking a breakdown row:", table_visible_drilldown)
        print("Drill-down shows exactly docs 1, 2, 7 (Travel/EUR):", drilldown_ids)
        print("Drill-down banner visible:", banner_visible)
        print("Drill-down banner text names the row and a count:", "Travel" in banner_text and "3" in banner_text)

        # === Scenario 14: "Back to Reports" returns to the Reports view ===
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(150)
        back_view_is_reports = await page.locator('#reports-view').is_visible()
        back_banner_hidden = not await page.locator('#report-drilldown-banner').is_visible()
        print("Back to Reports restores the Reports view:", back_view_is_reports)
        print("Drill-down banner hidden again after Back:", back_banner_hidden)

        # === Scenario 15: clicking the Grand Total row shows every document in
        # that currency group (EUR: docs 1, 2, 4, 7) ===
        await click_report_row_by_label(page, 0, 'Grand total')
        await page.wait_for_timeout(150)
        grand_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => Number(e.dataset.id)).sort((a,b) => a-b)')
        grand_banner_text = await page.locator('#report-drilldown-banner-text').inner_text()
        print("Grand Total drill-down shows all 4 EUR-group docs (1, 2, 4, 7):", grand_ids)
        print("Grand Total banner mentions the currency and a count of 4:", "EUR" in grand_banner_text and "4" in grand_banner_text)
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(150)

        # === Scenario 16: clicking a "(none)" row -- switch breakdown to People
        # first (docs 4 and 7 have no People at all, per Scenario 8's own setup) ===
        await page.select_option('#report-breakdown-field', 'people')
        await page.wait_for_timeout(150)
        await click_report_row_by_label(page, 0, '(none)')
        await page.wait_for_timeout(150)
        none_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => Number(e.dataset.id)).sort((a,b) => a-b)')
        print("'(none)' row drill-down shows only docs missing People (4, 7):", none_ids)
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(150)

        # === Scenario 17: "Back to Reports" preserves the breakdown-field
        # selection and date-range filter -- set both before drilling in ===
        await page.select_option('#report-breakdown-field', 'people')
        await page.fill('#report-date-from', '2026-01-01')
        await page.wait_for_timeout(150)
        await click_report_row_by_label(page, 0, 'Grand total')
        await page.wait_for_timeout(150)
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(150)
        breakdown_after_back = await page.locator('#report-breakdown-field').input_value()
        date_from_after_back = await page.locator('#report-date-from').input_value()
        print("Breakdown field selection survives Back to Reports:", breakdown_after_back == 'people')
        print("Date-range filter survives Back to Reports:", date_from_after_back == '2026-01-01')
        await page.fill('#report-date-from', '')
        await page.wait_for_timeout(150)

        # === Scenario 18: a multi-valued (People) row's drill-down includes a
        # document that also belongs to another row, proving the snapshot isn't
        # artificially made exclusive -- doc 1 has both Alice and Bob, so it must
        # appear in BOTH the Alice-row drill-down and the Bob-row drill-down ===
        await page.select_option('#report-breakdown-field', 'people')
        await page.wait_for_timeout(150)
        await click_report_row_by_label(page, 0, 'Alice')
        await page.wait_for_timeout(150)
        alice_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => Number(e.dataset.id)).sort((a,b) => a-b)')
        print("Alice-row drill-down (docs 1, 2):", alice_ids)
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(150)
        await page.select_option('#report-breakdown-field', 'people')
        await page.wait_for_timeout(150)
        await click_report_row_by_label(page, 0, 'Bob')
        await page.wait_for_timeout(150)
        bob_ids = await page.locator('#doc-tbody tr').evaluate_all('els => els.map(e => Number(e.dataset.id)).sort((a,b) => a-b)')
        print("Bob-row drill-down (doc 1 only):", bob_ids)
        print("Doc 1 belongs to both the Alice and Bob drill-downs (not made artificially exclusive):", 1 in alice_ids and 1 in bob_ids)
        await page.click('#report-drilldown-back-btn')
        await page.wait_for_timeout(150)

        print("JS ERRORS:", errors)
        await browser.close()

asyncio.run(main())
```

#### Step 15: Run the extended test file and verify every new line

```bash
cd tests && python3 test_reports.py
```

Expected, matching each new scenario's own comment above:
- `Table visible after clicking a breakdown row: True`
- `Drill-down shows exactly docs 1, 2, 7 (Travel/EUR): [1, 2, 7]`
- `Drill-down banner visible: True`
- `Drill-down banner text names the row and a count: True`
- `Back to Reports restores the Reports view: True`
- `Drill-down banner hidden again after Back: True`
- `Grand Total drill-down shows all 4 EUR-group docs (1, 2, 4, 7): [1, 2, 4, 7]`
- `Grand Total banner mentions the currency and a count of 4: True`
- `'(none)' row drill-down shows only docs missing People (4, 7): [4, 7]`
- `Breakdown field selection survives Back to Reports: True`
- `Date-range filter survives Back to Reports: True`
- `Alice-row drill-down (docs 1, 2): [1, 2]`
- `Bob-row drill-down (doc 1 only): [1]`
- `Doc 1 belongs to both the Alice and Bob drill-downs (not made artificially exclusive): True`
- `JS ERRORS: []`

If any line disagrees, fix the corresponding `dossiary.html` code from Steps 1-12 (not the test) unless the test itself has a bug — re-derive from the SEED data table in this plan's own research (Section 3 of this plan's originating research, reproduced in the SEED comments already in `tests/test_reports.py`).

#### Step 16: Commit

```bash
git add dossiary.html tests/test_reports.py
git commit -m "feat: make Reports rows clickable, drilling into a filtered document list"
```

---

### Task 2: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `tests/CLAUDE.md`

**Interfaces:**
- Consumes: the shipped behavior from Task 1 (this task only documents it, no code changes).

#### Step 1: Add a drill-down amendment to `CLAUDE.md`'s Reports note

Find the existing Reports architecture note, which ends with (confirm with `grep -n "no separate PDF-generation path" CLAUDE.md`):

```
  as PDF" on every platform this app targets, so no separate PDF-generation path
  was needed.
- **Collections** (`collections` + `collection_documents` tables,
```

Insert a new paragraph between them (after `was needed.`, before `- **Collections**`):

```markdown
  **Report drill-down (2026-09-22 amendment)**: every Reports row -- each
  breakdown value, the "(none)" row, and each currency group's own Grand
  Total row -- is clickable, jumping to an ordinary, filtered view of the
  real document table showing exactly the documents that contributed to it.
  `computeReportGroups()` gained a `docIds` array per row (and a
  `grandTotalDocIds` array on the group, computed the same
  independently-of-the-rows way `grandTotal` itself already is) --
  `renderReportsView()` wires a click handler on each `<tr>` (breakdown rows
  and the `<tfoot>` Grand Total row alike, both carrying `.report-row` plus
  `data-group-idx`/`data-row-idx` attributes so the listener can look the
  right row back up in `groups`, which stays in closure scope) that calls
  `drillIntoReportRow(docIds, label)`. This reuses the exact same
  `currentView`/`matchesView()`/`setView()` machinery every other nav view
  already runs through, rather than a bespoke rendering path: a new
  `'report-drilldown'` value added to `setView()`'s allowlist, and a new
  `matchesView()` branch (`reportDrilldownIds.has(d.id)`, same
  archived/needs-review-inclusive semantics as Reports and Collections,
  since this is conceptually the same kind of saved/curated view) is all it
  took to get the detail panel, right-click context menu, and bulk actions
  working here for free -- none of them needed to change at all.
  `reportDrilldownIds` (a `Set`) and `reportDrilldownLabel` (a string) are
  session-only module-level state, reset in `resetAll()` -- there is
  deliberately no persistence here, matching the spec's explicit scope cut
  ("this is an ephemeral, per-click state -- not a saved Collection").
  **`docIds` is a frozen snapshot, not a live filter**: it's captured once,
  at the moment a row is clicked, from whichever documents
  `computeReportGroups()` happened to iterate into that row at that moment
  -- editing a document afterward (e.g. changing its Category away from the
  value just drilled into) doesn't remove it from the still-open drill-down;
  only a *future* click on a freshly-rendered report produces a new
  snapshot. Deleting a document (Waste bin) still removes it immediately,
  since `matchesView()`'s existing `deleted` exclusion runs before every
  other branch, including this new one, exactly like every other view.
  A banner (`#report-drilldown-banner`, reusing the `.inbox-banner` CSS
  class verbatim for identical styling -- deliberately not a new CSS block)
  shows the row's label, a document count (`reportDrilldownCountSingular`/
  `Plural`, the same count-dependent key-pair convention every other
  count-dependent string in this app uses), and a "← Back to Reports" link
  that calls `setView('reports')` -- the same conditional-banner pattern
  `#inbox-banner`/`updateInboxBanner()` already established for the Inbox
  view's own staged-files notice, right down to being driven from
  `render()`'s own normal document-table path via a new
  `updateReportDrilldownBanner()` call. Because `setView()` only resets
  `currentView`/`selectedDocIds` -- never search text, the breakdown-field
  dropdown, or the Reports-only date-range filter -- "Back to Reports"
  naturally restores the Reports view exactly as it was left, with no extra
  state-preservation code needed. **The Grand Total row's own label**
  (`reportDrilldownGrandTotalLabel`, e.g. "Grand total (EUR)") and a
  **multi-valued breakdown row's label** (`reportDrilldownMultiValueLabel`,
  e.g. "People includes: Jana" -- distinct from
  `reportDrilldownRowLabel`'s plain "Category: Mail" for a single-valued
  breakdown) are two separate i18n keys, chosen by the same `group.multiValued`
  flag `renderReportsView()`'s own caption already reads, so a multi-valued
  drill-down's banner is explicit that the shown set isn't an exclusive
  partition -- the same document can legitimately appear in more than one
  row's drill-down (e.g. a document with both "Alice" and "Bob" values
  appears in both people's drill-downs), mirroring the existing "counted
  once per name" caption Reports already shows for multi-valued
  breakdowns. See
  `docs/superpowers/specs/2026-09-22-reports-drilldown-design.md` for the
  full design.
```

#### Step 2: Extend `tests/CLAUDE.md`'s Reports test-coverage paragraph

Find (confirm with `grep -n "active; and the print button" tests/CLAUDE.md`):

```
active; and the print button/`@media print` layout hiding the nav and
toolbar), Collections (`test_collections.py` — manual and smart collection
```

Replace with:

```
active; the print button/`@media print` layout hiding the nav and
toolbar; and, extending this same file, the drill-down feature added on
top of it -- clicking a breakdown row landing on an ordinary, filtered
document-table view of exactly the documents that contributed to that row
(a Category breakdown's "Travel" row resolving to exactly the 3 documents
that share it); "Back to Reports" restoring the Reports view; clicking a
currency group's own Grand Total row showing every document in that
group, independent of the breakdown field; clicking a "(none)" row
showing only documents genuinely missing that field; "Back to Reports"
specifically preserving the breakdown-field dropdown's own selection and
the Reports-only date-range filter, not just returning to the view;
and a multi-valued (People) breakdown's drill-down proving the per-row
snapshot isn't artificially made exclusive -- a document with two People
values (Alice and Bob) shows up in both that Alice row's own drill-down
and that Bob row's own drill-down, not just whichever one happened to be
clicked first), Collections (`test_collections.py` — manual and smart collection
```

#### Step 3: Commit

```bash
git add CLAUDE.md tests/CLAUDE.md
git commit -m "docs: document the Reports drill-down feature"
```
