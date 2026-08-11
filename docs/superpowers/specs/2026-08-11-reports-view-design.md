# Reports view — design

Date: 2026-08-11
Status: approved, ready for implementation plan

## Context

Prompted by reading Mariner Paperless's own User Guide (the app Dossiary
migrates from) end-to-end and comparing it against Dossiary's current
feature set. Paperless's Reports feature (Expense/Table/Chart views over a
collection, printable) directly serves two use cases the manual calls out
repeatedly: tax preparation ("the IRS will accept electronic copies... it
makes gathering information for taxes a snap") and flexible-spending
reimbursement (categorize receipts, then total by category for a date
range). Dossiary already tracks everything a report needs — Amount,
Currency, Category, Document Type, Payment method, People, custom fields —
but has no way to total or summarize any of it; the table only ever shows
individual rows.

This is sub-project 1 of two independent candidates identified during that
comparison (the other, Collections/Smart Collections, is a separate,
not-yet-brainstormed spec). Reports was chosen to go first because it
requires no schema changes and no new dependency, reusing data plumbing
(`allDocs`, `dynamicColumnDefs()`, `matchesView()`, `applyFilters()`) that
already exists.

## Goal

A fourth top-level nav view, **Reports**, that totals the currently
in-scope documents' Amount by a chosen breakdown dimension (Category, Type,
People, or any custom field), grouped by Currency so unlike currencies are
never summed together, with a print-friendly layout for handing a summary
to an accountant or attaching to a reimbursement claim.

## Non-goals

- **No chart/visualization in v1** — table only. A pie or bar chart is a
  reasonable future addition but was explicitly deferred to keep this spec
  small; nothing here blocks adding one later.
- **No Collections/Smart Collections dependency** — Reports operates on
  the existing search/category/type/custom-field filters plus a new
  date-range filter (see below), not on a saved Collection. If Collections
  ships later, "report on this Collection" can be added as a filter
  source without changing anything else here.
- **No CSV or other structured export** — printing (which can already be
  saved as a PDF via any OS's print dialog) is the only output path.
- **No editing from the Reports view** — it's read-only; clicking a total
  doesn't drill into the underlying documents in v1 (a reasonable future
  addition, not required for the core use case).
- **Tags are not a breakdown dimension** — excluded from the breakdown
  field list despite being multi-valued like People; not part of the
  agreed scope, and can be added later the same way People was included
  (see Breakdown dimension list below).

## UI/nav integration

A fourth `.nav-item` (icon 📊, label "Reports", `id="nav-item-reports"`,
`data-view="reports"`), added to `#app-nav` after the existing three,
following the exact markup pattern of `#nav-item-all`/`#nav-item-inbox`/
`#nav-item-trash` (`dossiary.html` ~line 325-339). No badge count needed
next to it (a document *count* isn't the meaningful number for a Reports
entry point the way it is for the other three) — the `.nav-item-count`
span is simply omitted for this one item; `renderNav()`'s
`document.querySelectorAll('.nav-item[data-view]')` loop for active-state
highlighting still applies to it unchanged since that part doesn't
reference the count span.

`setView()` (`dossiary.html:2161`) gains `'reports'` to its allow-list:

```js
function setView(view){
  if(view !== 'all' && view !== 'inbox' && view !== 'trash' && view !== 'reports') return;
  if(currentView === view) return;
  currentView = view;
  render();
}
```

## matchesView() extension

New branch, added after the existing `'trash'`/`'inbox'` checks and before
the `'all'` fallthrough logic (`dossiary.html:2044-2070`):

```js
// Reports always includes archived and needs-review documents -- a report is
// about real financial history, not about what's currently cluttering the
// browse view. Only `deleted` (soft-deleted, Waste bin) is excluded, same as
// every other view.
if(view === 'reports') return true; // `d.deleted` already returned false above
```

This must be placed *after* the shared `if(d.deleted) return false;` line
(already shared by `'inbox'` and `'all'`) so Waste bin documents are still
excluded from reports without duplicating that check.

`renderNav()`'s `navCounts` computation and `showArchivedWrap` visibility
line both extend narrowly:

```js
navCounts = {
  all: allDocs.filter(d => matchesView(d, 'all', showArchived)).length,
  inbox: allDocs.filter(d => matchesView(d, 'inbox', showArchived)).length,
  trash: allDocs.filter(d => matchesView(d, 'trash', showArchived)).length,
  // no `reports` entry -- there's no badge to populate, see UI/nav integration above
};
...
if(showArchivedWrap) showArchivedWrap.style.display = currentView === 'all' ? 'flex' : 'none';
```

`showArchivedWrap` already only shows for `'all'`, so Reports already hides
it correctly with zero changes — Reports always includes archived
regardless, so a visible-but-inert checkbox would be exactly the
consistency problem CLAUDE.md's existing comment on this line already
guards against for `'inbox'`/`'trash'`.

## Filtering: date range + existing filters

A new `#report-date-from`/`#report-date-to` pair of `<input type="date">`
elements, wrapped like `showArchivedWrap` (`display:none` by default,
shown only when `currentView === 'reports'`, toggled in `renderNav()`
alongside the `showArchivedWrap` line). Filters on the document's `date`
field (its own content date, e.g. an invoice date — not `import_date`,
consistent with every other date-based feature in this app treating `date`
as the meaningful one).

The existing search box, category filter, type filter, and dynamic
custom-field filters all continue to apply unchanged — `applyFilters()`
(`dossiary.html:2071`) gains one more condition, only active for the
`'reports'` view:

```js
function applyFilters(docs){
  const { q, category, type, person, showArchived, dynamic } = currentFilters();
  return docs.filter(d => {
    if(!matchesView(d, currentView, showArchived)) return false;
    if(currentView === 'reports'){
      const { dateFrom, dateTo } = currentReportDateRange(); // reads the two new inputs
      if(dateFrom && (!d.date || d.date < dateFrom)) return false;
      if(dateTo && (!d.date || d.date > dateTo)) return false;
    }
    if(category && d.category !== category) return false;
    // ...unchanged from here down
```

A document with no `date` set is excluded once either bound is set (can't
know if it falls in range), included when no date range is set at all —
consistent with how other optional filters in this app already behave
(compare `dynamic` field filters, which only apply when a value is chosen).

## Breakdown dimension list

A `<select id="report-breakdown-field">` populated from:

```js
function reportBreakdownFields(){
  const fixed = FIELD_DEFS.filter(f => ['category', 'document_type', 'people'].includes(f.id));
  return [...fixed, ...dynamicColumnDefs()];
}
```

This reuses `dynamicColumnDefs()` (`dossiary.html:544`) exactly as it
already exists for table columns/filters — no new field-enumeration logic.
`fixed` deliberately excludes `date`, `import_date`, `amount`, and `tags`
from `FIELD_DEFS`:

- **`date`/`import_date`** — near-unique per document, not a meaningful
  grouping key; the new date-range filter above is how Reports handles
  time-scoping instead.
- **`amount`** — this is the value being summed, not something to group
  by.
- **`tags`** — multi-valued like People, but out of scope for v1 per
  Non-goals above.

`dynamicColumnDefs()` already includes Payment method (flagged
`show_as_column: 1` by `migrateSentinelFieldsToGeneric()`) and any other
custom field someone has flagged `show_as_column` in Field Settings,
including person-type fields like "Author" — so nothing extra is needed to
support those.

## Report table structure

Given the filtered document set (`applyFilters()`'s result for
`currentView === 'reports'`) and the chosen breakdown field:

1. **Group by Currency first.** Read each document's `customFields['Currency']`
   (blank/missing treated as its own group, labeled "No currency set") —
   never sum Amount values across different currency labels. Each currency
   group renders as its own sub-table with its own subtotal line.
2. **Within each currency group, group by the breakdown field's value(s).**
   - For `category`/`document_type`: read `d.category`/`d.document_type`
     directly (single-valued).
   - For `people` or any person-type custom field (id `field-<id>` where
     that field's type is `'person'`): read `d.personFieldValues[fieldName]`
     (an array) — **a document with multiple names in that field
     contributes its full Amount to every name's row.** This means a
     multi-valued breakdown's rows will not sum back to the currency's own
     subtotal; the report explicitly notes this next to the table (a small
     caption: "Documents with more than one {field name} are counted once
     per name, so this breakdown's totals may exceed the currency
     subtotal above.") so it reads as documented behavior, not a bug.
   - For any other custom field (`field-<id>`): read
     `d.customFields[fieldName]` (single string value, same as
     `formatCustomFieldValue()` already does for display).
   - A document with no value for the chosen field lands in a `(none)`
     row rather than being dropped from the report.
3. **Each row shows Count and Total.** Count = number of documents in that
   group (including ones with no Amount). Total = sum of `parseFloat()`
   on `customFields['Amount']` for documents in that group that have one
   (mirrors `formatAmount()`'s existing `isNaN`/`=== 0` treatment of "no
   real amount" as excluded from the sum, not counted as `0`).
4. **Rows sort by Total descending** within each currency group (most
   spent first — the useful ordering for "where did this money go");
   ties broken alphabetically by group label. The `(none)`/"No currency
   set" rows are not pinned to top or bottom — they sort into place by
   Total exactly like any other row.
5. **A grand-total line** closes each currency group, computed
   independently as the sum of `Amount` across every document in that
   currency group (i.e. the same number `formatAmount()`-style summing
   over the pre-breakdown document set would produce) — **not** the sum of
   the rows above it. For a single-valued breakdown field these are always
   equal anyway; stating it as an independent computation is what makes
   the grand-total a reliable "true total" to compare against when the
   breakdown field is multi-valued and its rows over-count (per point 2
   above).

## Printing

A new `@media print` block hides `#app-nav`, `.toolbar`, and anything else
outside the report table itself (same technique as any standard
print-stylesheet — nothing exotic, no new dependency). A "Print" button in
the Reports view calls `window.print()` directly; the browser's own print
dialog already offers "Save as PDF" on every platform this app targets, so
no separate PDF-generation path is needed. This is the first print-specific
CSS anywhere in `dossiary.html` — additive only, doesn't touch any existing
screen styling.

## Visible consequences

- No schema change, no new CDN dependency, no change to how documents are
  stored or ingested — this is a pure read/aggregate view over data that
  already exists.
- A document with `Amount` set but no `Currency` groups under "No currency
  set" rather than being silently dropped or guessed into a default —
  worth stating explicitly since `default_currency` only affects new
  captures, not how existing blank-Currency documents are reported on.
- Switching to the Reports view for the first time in a session shows
  today's date range (both inputs blank = no filtering) and whatever
  breakdown field was last selected this session — neither is persisted
  across a library reopen, matching `currentView` itself already being
  session-only state (`resetAll()` always starts at `'all'`).

## Testing

New `tests/test_reports.py`, following this suite's existing
print-based-observation convention (see `tests/test_nav.py` for the most
recent example of the same pattern), covering:

- The Reports nav item switches the table view to the report layout;
  `#waste-bin-btn`/other views' own controls stay unaffected.
- An archived document and a needs-review document both appear in Reports
  totals by default (the `matchesView()` behavior this spec's whole
  premise depends on) — seed one of each alongside an ordinary document,
  confirm all three are counted.
- A deleted (Waste bin) document is excluded from Reports totals.
- Two documents with different Currency values produce two separate
  currency groups with independent subtotals, never summed together.
- A document with Amount set but Currency blank groups under "No currency
  set" rather than vanishing.
- Breakdown by Category/Type produces the expected single-valued grouping;
  breakdown by People with a two-person document confirms the "counted
  once per name" behavior and that the caption appears.
- The date-range filter excludes documents outside the range and documents
  with no `date` set (once a bound is active), while leaving them included
  when both bounds are blank.
- Switching the breakdown dropdown recomputes the table without needing a
  full view switch.
- `@media print` hides `#app-nav`/`.toolbar` (can be asserted via
  `page.emulate_media(media="print")` and checking computed `display`,
  a Playwright-supported check already usable with this suite's existing
  stub setup).

## Documentation

`CLAUDE.md` gains a new architecture note (following the density/style of
the existing "Top-level navigation" note) describing: the `'reports'`
`matchesView()` branch and why it always includes archived/needs-review;
the date-range filter and why it's scoped to Reports rather than being a
global toolbar addition; the breakdown-field list and why `date`/
`import_date`/`amount`/`tags` are excluded from it; and the multi-valued
People-breakdown caveat. `README.md`/`README.de.md`'s feature list gains a
short entry for Reports alongside the existing nav-related entries.
