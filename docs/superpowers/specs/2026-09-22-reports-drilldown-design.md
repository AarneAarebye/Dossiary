# Reports drill-down — Design

**Status:** Approved, ready for implementation planning.

## Problem

Reports groups documents into totals by Currency and a chosen breakdown
field (Category, Type, People, or a custom field), but each row only shows
aggregate numbers — count and total. There's no way to see *which*
documents actually make up a row without leaving Reports and manually
reconstructing the same filter by hand. Clicking a row should show exactly
those documents.

## Scope

- Every per-value row in a report table becomes clickable, jumping to a
  filtered document list showing exactly the documents that contributed to
  that row.
- The Grand Total row is also clickable, showing every document in that
  currency group.
- The "(none)" row (documents with no value for the breakdown field) is
  also clickable.
- The resulting document list is a real, ordinary view of the existing
  shared document table — detail panel, right-click context menu, bulk
  actions, and everything else that already works on any other view keeps
  working here for free.

Out of scope: any change to how reports are computed or grouped, any new
persistence (this is an ephemeral, per-click state — not a saved
Collection), and any change to the toolbar's existing filter dropdowns.

## Architecture

`computeReportGroups()` gains one field per row: `docIds` — the array of
document IDs that contributed to that row, trivial to add since the
function already iterates every document to build each row's count/total.
The Grand Total gets the same treatment (it's already computed
independently from the full currency-group document list, so its own
`docIds` is just that list).

`renderReportsView()` wires a click handler on each row (including the
`<tfoot>` Grand Total row) that calls a new `drillIntoReportRow(docIds,
label)`: stores the IDs into a module-level `reportDrilldownIds` (a `Set`,
for fast membership checks), stores `label` (a string built from the
breakdown field's name and the row's own value, e.g. "Category: Mail") for
the banner, and calls `setView('report-drilldown')` — a new view value
added to `setView()`'s existing allowlist check.

`matchesView()` gets one new branch, inserted alongside the existing
`'collection-<id>'` branch (same "archived and needs-review documents stay
included; only `deleted` is excluded" rule collections and reports already
use, since a drill-down is conceptually the same kind of saved/curated
view, not a day-to-day browse view): `if(view === 'report-drilldown')
return reportDrilldownIds.has(d.id);`.

A banner renders above the table whenever `currentView ===
'report-drilldown'`, showing the stored label, a document count, and a
"← Back to Reports" link that calls `setView('reports')` — the same
conditional-banner pattern `#inbox-banner` already uses for the Inbox
view's own staged-files notice.

## Data flow & multi-valued fields

`docIds` is a frozen snapshot captured at the moment a row is clicked —
not a live-updating filter. Editing a document afterward (e.g. changing
its Category away from the value you drilled into) won't remove it from
the list you're currently looking at; it only stops appearing in a
*future* click on a freshly-rendered report. Deleting a document (Waste
bin) still removes it immediately, since `matchesView()`'s existing
`deleted` exclusion runs before the new branch, exactly like every other
view.

For a multi-valued breakdown field (People, or a custom person-type
field), a single document can belong to more than one row's `docIds` at
once — this mirrors the existing "counted once per name" caption Reports
already shows for multi-valued breakdowns. The drill-down banner's label
makes this explicit (e.g. "People includes: Jana") rather than implying an
exclusive set.

## Error handling

No new failure modes. `docIds` is always derived from documents just
iterated to build that row, so it's never stale or invalid at click time.
An empty set can't occur in practice (a row only exists if at least one
document produced it), but if it somehow did, the drill-down view would
simply show zero documents with the banner still naming what was clicked —
the same as any other view with nothing matching today.

## Testing

New Playwright scenarios extending Reports' existing test coverage:
clicking a breakdown row lands on the drill-down view with the correct
document set and banner text; clicking the Grand Total row shows the whole
currency group; clicking a "(none)" row shows only documents missing that
field; "Back to Reports" returns to the Reports view with its own
breakdown-field selection and date-range filter still intact (view
switches don't reset other view state, matching this app's existing
behavior); a multi-valued (People) row's drill-down includes documents
that also belong to other rows, confirming the snapshot isn't
artificially made exclusive.
