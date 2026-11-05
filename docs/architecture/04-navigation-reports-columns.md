# Dossiary architecture notes: Navigation, reports, collections, detail panel, columns, tools, sorting, schema upgrades

Moved out of `AGENTS.md` (section "Architecture notes") without changes to the wording. Read this file when you touch the area it describes; `AGENTS.md` lists the notes it holds. Add a new note for this area here, not in `AGENTS.md`.

- **Top-level navigation** (`#main-layout`, `#app-nav`, `.nav-item`,
  `currentView`, `matchesView()`, `renderNav()`, `setView()`) unifies
  All Documents/Inbox/Waste bin — previously an always-visible Review
  Queue banner above the table plus a separately-modal Waste Bin reached
  via its own toolbar button — into one persistent nav switching between
  three views of the exact same real `<table>` (same columns, sorting,
  search, category/type/dynamic filters), directly modeled on Mariner
  Paperless's own "Everything"/"Inbox" sidebar. Clicking a row in any view
  opens the same `openDetail()` modal used everywhere else, which already
  renders the correct action set per document state (see the Archiving/
  Review queue/Waste bin notes above) — this is why unifying onto one
  table needed no new per-row action buttons at all, unlike the old
  review-queue rows' own inline Edit/Done buttons or the waste-bin modal's
  own inline Restore button, both now gone.
  **`matchesView(d, view, showArchived)`** is the single function
  encoding view membership, extracted from what used to be `applyFilters()`'s
  own inline logic: `'trash'` → `!!d.deleted`; `'inbox'` → (after excluding
  deleted) `!!d.needs_review && !d.archived`; `'all'` → (after excluding
  deleted) the pre-existing default-table rules, `archived && !showArchived`
  excluded and `needs_review && !archived` excluded. `applyFilters()` now
  reads `if(!matchesView(d, currentView, showArchived)) return false;`
  before its unchanged category/type/person/dynamic/search filters — so
  those filters compose correctly with whichever view is active for free,
  which the old separate Review Queue/Waste Bin renderers never supported
  (neither had its own search or category filtering at all).
  **`currentView`** (`'all'` | `'inbox'` | `'trash'` | `'reports'` |
  `'report-drilldown'` | `'collection-<id>'`) is session-only,
  never persisted — always starts `'all'` on every library open, via
  `resetAll()`. Switching views does **not** reset search text, filter
  selects, or "Show archived" — only the document set changes.
  **`renderNav()` replaces `renderReviewQueue()` in `render()`'s "always
  call this first" slot** (`render()`'s first statement, so every existing
  call site — initial load, post-edit, post-inbox-add, post-toggle — picks
  it up automatically): it computes `navCounts` (one `matchesView()` filter
  pass per view, against the *current* `showArchivedToggle` state),
  updates each `.nav-item`'s badge and `.active` class, and shows/hides
  `showArchivedWrap` (`currentView === 'all'` only — "Show archived" only
  means anything for the `'all'` view; `'inbox'` already excludes archived
  unconditionally, and `'trash'`'s `deleted` flag trumps `archived`
  regardless, so showing the checkbox in those views would just be inert
  UI). Badges reflect **view membership only**, not the live search/filter
  text — recomputing per keystroke would make navigation counts flicker
  while typing, and the existing `countLine` ("Showing X of Y", its
  denominator now `navCounts[currentView]` rather than `allDocs.length`)
  already covers the filtered-count case. `setView(view)` sets
  `currentView` and calls `render()`; wired from each `.nav-item[data-view]`'s
  click handler.
  **Visual style is a persisted, user-configurable setting**
  (`navStyle`, `'tabs'` | `'sidebar'`, default `'sidebar'`), toggled via a
  `#nav-style-toggle` button living inside the nav itself — no general
  settings-modal infrastructure exists in this app, so the control sits
  spatially attached to what it controls, the same reasoning behind where
  `default_document_type`/`default_currency` live in Field Settings.
  `loadNavStyle()`/`saveNavStyle()`/`applyNavStyle()` follow the exact
  existing `settings`-table `key`/`value` pattern used by
  `loadDefaultCurrency()`/`saveDefaultCurrency()` — `applyNavStyle()`
  just toggles a `nav-style-sidebar` class on `#main-layout`; one shared
  markup structure and one CSS class flips between a horizontal tab strip
  and a vertical sidebar, not two divergent markups. `loadNavStyle()` is
  called from `loadDocumentsFromDb()` alongside `loadDefaultCurrency()`.
  **Icons were chosen to avoid a real collision**: All Documents is 📁,
  Waste bin is 🗑 (already used elsewhere in the app), and Inbox is
  deliberately **🚩**, not 📥 — 📥 is already the separate, pre-existing
  "Check inbox" toolbar button for raw staged files (see the Inbox note
  below), and reusing it here would visually conflate two unrelated
  features; 🚩 instead matches the existing "Flag for review" button label
  already used for this exact `needs_review` concept.
  **`.table-wrap`'s sticky-header max-height calibration is nav-style-
  dependent** — see that note near the top of this file for the current
  values and the empirical-verification story, including why the two
  styles' constants are each independently calibrated to their own
  worst-case toolbar-wrapping width rather than related by a fixed
  structural offset.
- **Reports** (`#nav-item-reports`, `data-view="reports"`, `reportBreakdownFields()`,
  `reportBreakdownFieldInfo()`, `computeReportGroups()`, `renderReportsView()`) is a
  4th top-level nav view alongside All Documents/Inbox/Waste bin, giving totals
  for tax prep and expense reimbursement workflows Dossiary previously had no way
  to support. **`matchesView()`'s `'reports'` branch always includes archived and
  needs-review documents** — a report is about real financial history, not about
  what's currently decluttered out of the browse view; only `deleted` (Waste bin)
  documents are excluded, same as every other view. Totals are grouped by Currency
  first and never summed across different currency labels
  (`customFields['Currency']`, blank treated as its own "No currency set" group) —
  Dossiary never assumes a single-currency library. Within each currency group,
  documents are further grouped by a chosen breakdown field (`#report-breakdown-field`,
  populated from `reportBreakdownFields()`: Category/Type/People/Tags from `FIELD_DEFS`,
  plus any custom field flagged `show_as_column` via the same `dynamicColumnDefs()`
  table columns/filters already use — deliberately excludes `date`/`import_date`
  (near-unique per document, not a meaningful grouping key) and `amount` (the value
  being summed, not a grouping key). Tags joined later, as a multi-valued
  breakdown exactly like People (label `tableColTags`, "Tags includes: …" on
  its drill-down banner). **A document with more than one value for a multi-valued
  breakdown field (People, Tags, or a custom person-type field) contributes its full
  Amount to every value's row** — `renderReportsView()` shows an explicit caption
  when this applies, since row totals then legitimately don't sum to the currency
  group's own Grand total; that Grand total (`computeReportGroups()`'s `grandTotal`/
  `documentCount`) is deliberately computed independently over every document in
  the currency group, not by summing the rows above it, so it stays a reliable
  "true total" regardless. A separate, Reports-only date-range filter
  (`#report-date-from`/`#report-date-to`, `currentReportDateRange()`) filters on
  the document's own `date` field (its content date, not `import_date`) —
  `applyFilters()` only applies this filter when `currentView === 'reports'`; the
  existing search/category/type/dynamic-field filters continue to apply unchanged
  in this view too. No new dependency, no schema change — this is a pure
  read/aggregate view over `allDocs`. Printing (`#reports-print-btn` →
  `window.print()`) is the first `@media print` stylesheet in this app, hiding
  `#app-nav`/`.toolbar`/etc.; the browser's own print dialog already offers "Save
  as PDF" on every platform this app targets, so no separate PDF-generation path
  was needed.
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
  **Pie chart** (`reportPie()`, `reportPieSvg()`,
  `REPORT_PIE_COLORS`): each currency group gets a hand-built SVG pie of
  its row totals beside the table (`.report-group-body`, a wrapping flex
  row) -- no charting dependency. The table is the legend: a row with a
  slice gets a `.report-swatch` in its colour (`print-color-adjust:exact`,
  since browsers drop background colours when printing). Rows are already
  sorted by total, so the 7 largest positive values get their own colour
  and any further ones share one grey "Other" slice; with 8 or fewer, every
  value gets a colour. Only positive totals are drawn -- a pie can't show a
  refund -- with `reportsPieNegativeNote` when any row is negative; a group
  with no positive total gets no pie, and neither does a multi-valued
  breakdown (People, Tags, person fields), whose rows overlap. A slice is a
  focusable `role="button"` drilling down exactly like its row (Enter/Space
  too), "Other" into the union of its rows' documents; each has a
  `<title>` with value and share. A lone value draws a `<circle>`, since an
  arc from a point back to itself renders nothing.
- **Collections** (`collections` + `collection_documents` tables,
  `openManageCollectionsModal()`, `createManualCollection()`,
  `addDocumentsToCollection()`) are user-created document groupings, manually
  curated or automatically matching your current search/filter state as a
  live view. The schema stores only two tables: `collections` (name, `kind`,
  criteria JSON for smart collections) and `collection_documents` (the
  manual join for non-smart collections). Smart collections store no rows in
  `collection_documents` — instead, `matchesCriteria()` re-evaluates their
  filter criteria against each document on every `render()` call, the same
  criteria grammar `currentFilters()` extracts from the toolbar (Category,
  Type, Person dropdowns, dynamic-field filters, search text), so a smart
  collection always stays synchronized with new documents without any
  background sync logic. Manual collections are static rosters you build by
  selecting documents in the table and clicking "Add to Collection" (via the
  bulk-action toolbar that appears when checkboxes are checked), or one at a
  time from a document's own detail-panel action buttons ("Add to Collection"
  picks which one; "Remove from Collection" appears only when viewing from
  inside a specific manual collection). Removing a document from a collection
  and deleting a collection are both inline `DELETE FROM` statements in their
  respective click handlers, not named functions; deleting the collection
  currently being viewed (via its own nav item) falls back `currentView` to
  `'all'` first, so the person isn't left in a now-nonexistent view with
  nothing highlighted. The Collections nav section
  expands and collapses via a toggle button (`#nav-collections-toggle` →
  `saveCollectionsNavExpanded()`), defaulting to **expanded**
  (`collectionsNavExpanded = true` unconditionally at startup and in `resetAll()`)
  and staying expanded until the user explicitly collapses it, with that choice
  then persisted via the `collections_nav_expanded` setting. **That setting
  is the sidebar nav's only.** In the tabs nav the list is an absolutely
  positioned dropdown hanging over `.toolbar`, and left open it covered
  toolbar controls (🛠 Tools included, at 1280x720 with four collections),
  so there it's a real dropdown: closed by default and after every nav-style
  switch (`collectionsTabsOpen`, session-only), opened by the Collections
  toggle, and closed again by an outside click, Escape, or choosing a
  collection (`setCollectionsTabsOpen()`; `applyCollectionsNavExpanded()`
  picks the right flag for the current style). Closed, it adds no height, so
  `.table-wrap`'s calibration is untouched. Tests that pick a collection in
  tabs mode open the dropdown first (`test_collections.py`'s
  `click_collection()`); the list itself
  (`#nav-collections-list`) is rebuilt on **every `render()` call** (it lives
  inside `renderNav()`, called from `render()`'s "always call this first" slot —
  see the Top-level navigation note above), not just when a collection is
  created, deleted, or renamed — the same delete-then-reinsert-from-scratch
  pattern this app already uses for other dynamic containers, though those
  rebuild on their own separate triggers rather than every `render()` call
  (`renderDynamicTableHead()`'s `<th>`s rebuild when the columns menu
  changes, `populateFilters()`'s dynamic filters rebuild from their own
  explicit call sites — neither is invoked from inside `render()` itself).
  Smart collections
  are created only via the "☆ Save as Smart Collection" button
  (visible only in the All Documents view) — the Manage Collections modal's
  "+ New collection" creates manual collections only, never smart ones: a
  Smart Collection is only ever created by capturing a real, live filter
  snapshot at the moment "Save as Smart Collection" is clicked (its criteria
  coming straight from `currentFilters()`), and the Manage Collections modal
  has no filter state of its own to capture — a smart collection created
  there would have no criteria, which has no meaning for a collection whose
  entire membership is defined by its criteria. **"Save as Smart Collection"
  lives in the Collections nav section itself, not `.toolbar`** — moved there
  to fix a real toolbar-wrap regression (two new buttons pushed `.toolbar`
  from 2 rows to 3, landing `#reload-btn` directly under the open Columns
  dropdown); "⚙ Manage collections" stayed in the toolbar, since removing
  just the one button was already enough to restore the original 2-row
  layout (it has since moved into the "🛠 Tools" dropdown with the other
  occasional-use actions -- see that note). Multi-select
  checkboxes (`#select-all-checkbox`, per-row checkboxes with class
  `row-select-checkbox` and `data-id="${d.id}"`) reset whenever you switch views
  (`setView()` clears `selectedDocIds` and re-renders the table) or close the
  library — the selection state never persists across sessions and is scoped to a
  single view, so switching to a Smart Collection and back to All Documents doesn't
  retain your old All Documents selection. Creating a new manual collection
  and adding its first documents happen as one action via the same
  `addDocumentsToCollection()` and `createManualCollection()` functions that
  the detail-panel single-document action buttons use — no special
  code-path difference between a bulk add and a single add.
  **Bulk archive/delete/flag-for-review actions** (`bulkSetArchived()`,
  `bulkSetDeleted()`, `bulkSetNeedsReview()`, `renderBulkActionBar()`)
  extend the bulk-action bar with view-aware buttons for applying state
  changes to multiple documents at once. Button visibility and labels are
  context-sensitive: the Waste bin view shows only "Restore"; the Inbox
  view relabels "Flag for review" to "Done" (unflag); every other view
  (All Documents, Collections, Reports) shows Archive, Delete, and "Flag
  for review" alongside the existing "Add to collection" — but Reports
  view shows neither checkboxes nor a bulk bar at all. All three functions
  use **unconditional-set semantics** (not per-document toggle): "Archive
  selected" always sets `archived=1` for every selected document regardless
  of its current state, enabling correct behavior for mixed-state selections
  (e.g., selecting both archived and unarchived documents from a Collection
  view and clicking Archive leaves both archived, not toggling the already-
  archived one back to unarchived). Crucially, all database UPDATEs are
  queued first (`forEach`), then persisted and rendered exactly once via a
  single `persistDb()` / `render()` call, not per-document — unlike looping
  the single-document toggle functions, this avoids wasteful
  re-serialization of the entire SQLite database for bulk operations on
  multiple documents.
  **A collection view (`matchesView()`'s `'collection-<id>'` branch, both
  manual and smart) deliberately includes archived and needs-review
  documents** — the same choice, and the same reasoning, as the Reports view
  above: a collection is a saved/curated view (a manually-built roster, or a
  saved filter snapshot), conceptually closer to a report than to the
  day-to-day `'all'` browse view, so a document someone explicitly added to
  a collection — or that matches a Smart Collection's saved criteria —
  shouldn't silently vanish from that collection just because it got
  archived or flagged for review elsewhere. Only `deleted` (Waste bin) is
  excluded, via the same shared check every other view uses.
  **The bulk-action bar's height is part of `.table-wrap`'s sticky-header
  calibration too** — see that note near the top of this file. Selecting any
  row shows `#bulk-action-bar` (~74px of real page height above
  `.table-wrap`), so `renderBulkActionBar()` toggles a `.bulk-bar-visible`
  class on `#main-layout` and the CSS has dedicated `max-height` rules for
  all four combinations of nav style × bulk-bar visibility — don't assume
  the two nav-style constants alone are enough; selecting documents (this
  feature's own core workflow) is exactly the case that needs the other two.
- **The detail view is a persistent side panel (`#detail-panel`), not a
  modal** — `openDetail(id)` keeps its name (it still means "show this
  document's detail content") but now renders into `#detail-panel-body`
  instead of `#modal-root`, and drops the backdrop/close-button/Escape
  chrome that made it a modal (a panel isn't dismissed, it's collapsed).
  This replaced a full-screen modal that hid the table entirely while
  open, matching legacy Mariner Paperless's own persistent "Details" side
  panel instead. **`selectedDocId`** (module-level, distinct from
  `selectedDocIds`, the multi-select `Set` bulk actions use) tracks which
  single row the panel is showing, `null` meaning nothing selected — the
  panel then shows a plain empty-state message rather than blank content.
  Row click sets it, applies a `.row-selected` highlight to that `<tr>`,
  and calls `openDetail(id)`; `render()`'s own rebuild of `tbody` on every
  call means the highlight has to be reapplied after each rebuild (a
  `tbody.querySelector('tr[data-id=...]')` lookup right after the rows are
  rendered), and `render()` also invalidates `selectedDocId` back to
  `null` — refreshing the panel to its empty state — whenever the
  currently-selected document falls out of the active view's filtered/
  sorted set (deleted, archived out of view, or excluded by a filter/
  search change). **`openDetail(id)` itself is the authoritative setter of
  `selectedDocId`**, not just a content-rendering function — it sets
  `selectedDocId = d ? d.id : null` from whatever document it actually
  finds (or fails to find), right after its own `allDocs.find()` lookup.
  This means `render()`'s own invalidation above doesn't always have the
  last word: several action handlers (e.g. `toggleArchived()`) call
  `render()` first — which zeroes `selectedDocId` if the acted-on document
  fell out of the current filtered/sorted view — and then call
  `openDetail(id)` again afterward with that same original id purely to
  refresh the panel's displayed content. Because `openDetail()` re-asserts
  `selectedDocId` unconditionally, that trailing call re-selects the
  document too, re-highlighting its row if one still exists and leaving
  the panel showing its content even if the row doesn't (e.g. it just got
  archived out of the currently-visible view). This is intentional —
  quick "undo" reachability right after an action, not a bug — not an
  invalidation loophole to close. **`openDetail()` is async and can be
  superseded mid-flight** -- it awaits file reads (thumbnail, PDF page count)
  before writing the panel, and on a slow filesystem (a library in iCloud
  Drive) a newer call such as `render()`'s `openDetail(null)` can finish
  first. `detailRenderSeq` makes an older call drop its late write instead
  of putting a no-longer-selected document back into the panel. **Clicking a row never auto-expands a collapsed
  panel** — selection, highlighting, and content-refresh all happen
  unconditionally on every row click, but panel *visibility* is
  controlled only by the toolbar's own `#detail-panel-toggle-btn`,
  deliberately: if a row click also expanded the panel, the panel's own
  collapsed-by-default setting (see below) would stop mitigating anything
  — it would spring open on literally the first row click anyone ever
  makes.
  **The panel's expanded/collapsed state is a per-library `settings` row**
  (`detail_panel_expanded`), following `nav_style`'s exact
  `loadNavStyle()`/`saveNavStyle()`/`applyNavStyle()` pattern
  (`loadDetailPanelExpanded()`/`saveDetailPanelExpanded()`/
  `applyDetailPanelExpanded()`, toggling a `detail-panel-expanded` class on
  `#main-layout`) — except the default is collapsed (`false`) rather than
  one of two named states, since defaulting to expanded would undercut the
  entire reason this shipped collapsed-by-default: an always-visible panel
  costs real horizontal table width, and the person who raised this
  feature (comparing it to Mariner's own panel) explicitly worried about
  losing that space — **this default was later reversed to expanded; see
  below**. Below the app's one mobile breakpoint
  (`max-width:640px`), the panel force-collapses regardless of the saved
  preference — `#main-layout.detail-panel-expanded .detail-panel{
  display:none; }` inside the media query, matched in selector specificity
  to the base `#main-layout.detail-panel-expanded .detail-panel{
  display:flex; }` rule it overrides (a lower-specificity `.detail-panel{
  display:none; }` there would lose to the more specific rule and fail to
  collapse anything) — a true side panel doesn't fit a phone-width
  viewport any better than a full sidebar nav does (see that note's own
  mobile-collapse precedent above). The toggle button itself is hidden
  (not disabled) in Reports view, since that view renders its own
  aggregate content rather than the shared document table — there's no
  row for the panel to ever reflect there, same "hidden when the control
  is inert for this view" pattern already used for "Show archived".
  **The panel deliberately reuses `.table-wrap`'s own four `max-height`
  calibration constants (414/374/488/448, plus their nav-style/bulk-bar
  combinations) for its own `max-height`, rather than introducing new
  ones** — the panel is a flex sibling of `.table-wrap` inside a new
  `.table-detail-row` wrapper, sitting at exactly the same vertical offset
  under exactly the same header/toolbar/nav/bulk-bar/footer chrome, so the
  same "how much vertical room is left below that chrome" figure applies
  to both; the reasoning is sound and was spot-checked the same empirical
  way as everything else in this section at authoring time
  (`getBoundingClientRect()`, confirming the panel's own bottom edge lands
  at the fixed footer's top edge with no overlap), not assumed just
  because the numbers happened to match structurally. **It's now guarded
  by `tests/test_footer_pin.py`** (`measure_panel_not_clipped()`, run at
  every width/nav-style/bulk-bar combination of the desktop sweep), which
  checks the panel's real last visible line against the footer's top edge
  rather than its box edge -- and caught a real bug on its first run: at
  the widths where the toolbar wraps onto an extra row (about <=900px with
  tabs, <=1100px with the sidebar) the panel's last ~30px stayed hidden
  behind the footer even fully scrolled, because the panel had only 20px
  of bottom padding where `.table-wrap` has 70px to absorb exactly this
  (see the calibration note near the top). The panel now has the same
  70px. This is
  purely a **horizontal** layout change — the panel sits *beside* the
  table, not above or below it — so none of `.table-wrap`'s own four
  constants needed to move; reusing them for a same-height sibling is not
  the same thing as touching them.
  **Two call sites that used to rely on an implicit trick no longer can.**
  Before this change, `openEditForm()`'s Cancel button and
  `saveEditedDocument()`'s success path both called `openDetail(id)`,
  which — since the detail view and the edit form shared the same
  `#modal-root` — implicitly closed the edit modal *and* reopened detail
  content in one call, just by overwriting the same container. With the
  panel and the edit modal now separate, simultaneously-existing elements,
  that implicit behavior is gone: **Cancel** now just calls `closeModal()`
  and does nothing else — the panel, if open, already shows whatever
  document Edit was opened from, and Cancel deliberately does not force a
  collapsed panel open or re-render content that didn't change. **Save**'s
  success path now does two explicit things the old single call used to
  do for free: `closeModal()` to dismiss the edit modal, and
  `selectedDocId = id` (before the `render()` call that reapplies row
  highlighting) so the just-saved document becomes the new panel
  selection — this specifically covers editing reached via the row-level
  `.row-edit-btn` shortcut (see its own note above), which bypasses row
  selection entirely on the way in, so without this the panel would still
  be pointing at whatever (if anything) was selected before, not the
  document that was just edited.
  **The default flipped from collapsed to expanded** — `loadDetailPanelExpanded()`
  now treats "no saved `detail_panel_expanded` row at all" as expanded
  (`detailPanelExpanded = rows.length === 0 || rows[0][0] !== '0';`) rather
  than collapsed; an explicit saved `'0'` still means collapsed (a person
  who deliberately toggles the panel off keeps that choice across reopens),
  and an explicit `'1'` still means expanded, unchanged from the original
  design. This is a genuine reversal of the collapsed-by-default reasoning
  above, not a contradiction of it left unresolved: two of the panel's own
  original reasons for *duplicated* chrome — the row-level Edit shortcut
  competing with the panel's own Edit button, and no double-click
  file-open forcing a trip through the panel just to open a file — are
  gone now (see the next two paragraphs), so a collapsed-by-default panel
  no longer pays for itself the way it did at launch. The horizontal-space
  cost that originally justified collapsing by default hasn't changed;
  what changed is how much redundant UI the person was trading that space
  against.
  **Double-click a row opens its file.** A `dblclick` listener, added
  immediately after the existing per-row `click` listener in `render()`'s
  row-wiring pass, reuses the panel's own "Open file" logic verbatim
  (`resolveFileHandle` → `getFile` → `window.open`). It deliberately
  doesn't duplicate any selection/highlight logic of its own, because
  browsers fire two ordinary `click` events before a `dblclick` fires — by
  the time the `dblclick` handler runs, the existing single-click listener
  has already set `selectedDocId`, applied `.row-selected`, and called
  `openDetail()` for that row, twice over. A document with no `file_path`
  is a silent no-op, not an error. The panel's own "Open file" button
  stays exactly as it was — double-click isn't a discoverable gesture on
  its own, so the button remains the reliable, visible way to do the same
  thing; this is a shortcut for someone who already knows it's there, not
  a replacement for the button.
  **`.row-edit-btn` is now hidden except below the mobile breakpoint.** At
  normal widths it duplicated the panel's own Edit button, and that
  duplication only made sense back when the panel defaulted to collapsed
  and so wasn't reliably on screen — now that the panel defaults to
  expanded (see above), the panel's Edit button is reliably reachable, so
  `.row-edit-btn`/`.row-edit-col` are base-styled `display:none` (a
  CSS-only change; the button's own row-level rendering and click-wiring,
  described in the Editing note above, are untouched). It's restored
  inside the app's one mobile breakpoint (`@media (max-width:640px)`)
  specifically because that's the one place the panel is structurally
  unreachable regardless of the toggle: the existing
  `#main-layout.detail-panel-expanded .detail-panel{ display:none; }` rule
  inside that same media query force-hides the panel unconditionally (see
  the panel's own mobile-collapse paragraph above) — without restoring
  `.row-edit-btn` there, Edit would be completely unreachable from the
  table at that width. The one accepted trade-off: this reasoning holds for
  the *default* expanded state, not for someone who's deliberately
  collapsed the panel at desktop width — for them, reaching Edit now takes
  two clicks (re-expand the panel via the toolbar toggle, then click the
  row) instead of the old hover shortcut's one, a minor, honest regression
  for that specific case rather than something silently glossed over.
  **Right-click context menu** (`showRowContextMenu(id, x, y)`, the
  `contextmenu` listener on table rows, `.row-context-menu`/`.row-context-menu-item`)
  offers the same actions the panel does, rooted in a shared `buildDetailActions(id, d)`
  function — one source of truth for which actions apply to a document right now
  (deleted-document Restore-only, Add/Remove Collection's view-dependent visibility,
  etc.) and what each one does, so the two surfaces can't drift out of sync.
  **`buildDetailActions()` includes all actions** but marks "Regenerate preview"
  with `panelOnly: true` — the context menu filters these out via
  `.filter(a => !a.panelOnly)`, keeping that action panel-exclusive since it's
  an interactive process with explicit feedback, not a one-shot operation the way
  every context-menu action is. The `contextmenu` listener reuses the exact same
  `.select-col, .row-edit-col` opt-out guard the `dblclick` listener already
  established, for the same reason: those cells' `onclick="event.stopPropagation()"`
  only covers the `click` event, not right-click or double-click. **The "Detail"
  menu item toggles the panel's visibility** — it calls `saveDetailPanelExpanded(!detailPanelExpanded)`
  without touching `selectedDocId`, so it's orthogonal to which document is currently
  selected, the same "selection and visibility are independent" principle the
  "row click never auto-expands" rule already established from the opposite direction:
  selecting a document never touches panel *visibility*, and now, symmetrically,
  toggling panel *visibility* never touches which document is *selected*.
- **Configurable columns/filters** (`FIELD_DEFS`, `visibleColumns`,
  `renderColumnsMenu()`, `applyColumnVisibility()`) work by toggling
  `display` on any element carrying a matching `data-field="<id>"`
  attribute — table headers, table cells (added fresh in every `render()`
  call, so `applyColumnVisibility()` runs again at the end of `render()`
  to reapply to the new cells), and the `<span class="filter-wrap">`
  wrapping each filter `<select>`. `FIELD_DEFS` only holds the fixed,
  built-in columns (Category, Type, People, Date, Imported, Amount, Tags)
  now — Payment method was removed from it and, since it's a plain
  `fields` row with `show_as_column:1`, flows through `dynamicColumnDefs()`
  instead: any field with `show_as_column` set gets appended as a dynamic
  tail after the fixed ones, id `field-${id}`, everywhere `FIELD_DEFS` is
  consulted (`[...FIELD_DEFS, ...dynamicColumnDefs()]` in
  `loadColumnSettings()`/`renderColumnsMenu()`). `applyColumnVisibility()`
  needed **no changes** to support this — it was already fully generic
  (`[data-field]` query), which is exactly why the split works. Dynamic
  `<th>`s are (re)built by `renderDynamicTableHead()` (called from
  `renderColumnsMenu()`) by removing any previous `[data-dynamic-column]`
  headers and appending fresh ones; there's deliberately **no per-header
  click wiring** for these — sort-on-click is delegated once, on
  `#doc-thead-row` itself (`e.target.closest('th[data-key]')`), specifically
  so newly-appended dynamic headers sort correctly without needing to be
  individually wired at creation time. `populateFilters()` similarly
  rebuilds an entire `<span id="dynamic-filters">` container every call
  (dynamic filters only for `show_as_column` fields where `hasFilter` is
  true — i.e. `type === 'text' || type === 'checkbox' || type === 'person'`, the
  last shown as name pills (see the People note); Number/Date fields
  get a column but no filter dropdown, same reasoning as Date/Amount never
  having had one: a dropdown listing every distinct number/date isn't
  useful) -- and ends by calling `applyColumnVisibility()` itself, since a
  filter's visibility follows its column's and the Reports view's
  `render()` returns before applying it (a language switch on Reports
  used to expose hidden-column filters) -- and `currentFilters()`/`applyFilters()` read whatever dynamic
  `<select>`s currently exist via `document.querySelectorAll('#dynamic-filters select')`
  rather than named consts, so no code changes are needed as fields are
  flagged/unflagged. `sortDocs()` has a `sortKey.startsWith('field-')`
  branch: numeric compare for `type==='number'` fields, case-insensitive
  string compare otherwise. `populateDatalists()` follows the identical
  pattern for `autocomplete:1` text fields, rebuilding
  `<div id="dynamic-datalists">` with one `<datalist id="field-${id}-list">`
  per field; `renderGenericFieldHtml()` adds the matching `list=` attribute
  when `field.autocomplete` is set. If you add a new *fixed* (non-field-
  table) configurable column, you still need all three pieces the old note
  described: an entry in `FIELD_DEFS`, a `data-field` on the `<th>` (and
  matching `<td>`), and — if it has a filter — a `data-field`-wrapped
  `<span>` in the toolbar; missing any one means the toggle silently does
  nothing for that piece. The preference itself is stored in
  `library.sqlite`'s `settings` table (`INSERT OR REPLACE`, not the
  `ON CONFLICT ... DO UPDATE` upsert syntax — deliberately, since upsert
  support depends on the SQLite version sql.js happens to bundle, and
  `INSERT OR REPLACE` has been supported forever), not browser storage —
  keep it that way so the preference travels with the library folder.
- **The "🛠 Tools" toolbar dropdown** (`#tools-btn`, `#tools-menu`,
  `.tools-menu-item`, `toggleToolbarMenu()`) holds the occasional-use
  actions -- Manage fields, Manage collections, Library check, and Storage
  stats -- so the toolbar itself
  keeps only daily ones (Check inbox, Check reminders, Scan,
  Add document, Details, Columns). Moved there on request, and it also
  eases the recurring toolbar-wrap/`.table-wrap` calibration problem (see
  that note near the top): the toolbar got a row shorter at most desktop
  widths. **Each menu item keeps its original button id**
  (`#manage-fields-btn`, `#storage-stats-btn`, ...), so every existing click
  listener is untouched -- the menu only changes where the button lives;
  tests click `#tools-btn` first to reveal it. It reuses the Columns
  dropdown's markup/CSS (`.columns-menu-wrap`/`.columns-menu`), and
  `toggleToolbarMenu(e, menu)` is now shared by both: it closes any other
  open toolbar dropdown first (only one open at a time), keeps the
  existing mobile `position:fixed` promotion for when `.toolbar` becomes a
  scroll container, sets `aria-expanded`, and -- desktop only -- flips a
  right-aligned menu to open rightward (`left:0`) when its button sits at
  the start of a wrapped toolbar row, where it would otherwise spill over
  the nav sidebar. Choosing an item closes the menu (a delegated click
  listener that doesn't stop propagation, so the item's own listener
  still runs); Escape closes it and returns focus to `#tools-btn`; an
  outside click closes it like Columns. **Put new occasional actions in
  this menu rather than on the toolbar.** **"👁 Toolbar buttons…"**
  (`openToolbarButtonsModal()`, `OPTIONAL_TOOLBAR_BUTTONS`,
  `hidden_toolbar_buttons` setting, a JSON key list) lets a library hide
  daily buttons it doesn't use -- Check inbox, Check reminders, Scan,
  Details, Columns (its `.columns-menu-wrap`); never Add document or
  Tools, so nothing becomes unreachable. Hiding only, deliberately: a
  shorter toolbar can only free height, while adding or reordering buttons
  is what keeps breaking the `.table-wrap` calibration. `.toolbar-hidden`
  is `display:none !important`, because other code sets these buttons'
  inline display (Details is hidden in Reports and shown again after);
  hidden buttons keep their listeners. Copying a library's setup copies
  the choice (it's a `settings` row). **"Switch library"
  (`#reload-btn`) is not in this menu -- it's a small `.sub-switch-btn`
  text link right after the library's name (`#sub-label`) in the
  header**, where "which library am I in" and "change it" read together;
  shown only while a library is open (toggled alongside `toolbar` in
  `resetAll()` and `loadDocumentsFromDb()`, since `#sub-label` shows the
  empty-state prompt otherwise), and its "⇄" comes from CSS `::before` so
  it reuses the existing `toolbarSwitchLibrary` string. **Clicking it only
  calls `resetAll()`** -- back to the start screen's recent-libraries list
  and "Open or create a library…" button -- and deliberately does not also call
  `openLibrary()` the way it used to: the folder picker popping up on top
  of the recent-libraries list forced an extra cancel whenever the person
  just wanted a recent library (reported directly). Tests that used Switch
  library as a "reopen the re-seeded library" shortcut now click
  `#open-btn` right after it. **The header's
  height must not change** -- it's part of `.table-wrap`'s max-height
  budget -- so the name and link share one non-wrapping line
  (`header .sub:has(#reload-btn)` is a no-wrap flex row, and
  `header > div:first-child{ max-width:100% }` lets a long library name
  truncate with an ellipsis instead of pushing the link onto a second
  line). Verified at 320/640/1440px widths with a long name: header height
  identical to before the move.
- **Every filter dropdown built by `populateFilters()`** (Category, Type,
  People, and any dynamic custom-field filter) also carries a "— Not set —"
  option, right after "All X," so a document missing that field entirely
  can be filtered to directly. It's driven by a dedicated sentinel,
  `FILTER_UNSET` (`'__unset__'`), deliberately distinct from the plain
  empty string `populateFilters()`'s own "All X" option already uses to
  mean "this filter isn't active" — reusing the empty string for both
  would make "not set" indistinguishable from "no filter selected."
  `matchesCriteria()` — the single predicate both the live toolbar and
  saved Smart Collection criteria already share (see the Collections note
  above) — is the only place that interprets the sentinel, so this works
  everywhere filtering already composes (the toolbar, Smart Collections,
  Reports' own filter composition) with no separate code path: a scalar
  field (category/type) checks `!!d.category`, the multi-valued People
  field checks `(d.people||[]).length > 0`, and a dynamic field checks
  `actual !== undefined` against `d.customFields`. That last check is
  deliberately `!== undefined`, not a falsy check — a checkbox field
  explicitly saved as unchecked is stored as the string `'0'`, which is
  real, meaningful data, not "unset," matching
  `readDynamicFieldValues()`'s own existing rule for the save path (an
  unchecked box is meaningful data, not "empty"); only a field with no
  saved value at all should match "— Not set —".
- **Persisted default sort order** (`sortKey`, `sortDir`, `loadSortState()`,
  `saveSortState()`) mirrors the `nav_style`/`default_currency` pattern exactly:
  a per-library setting stored in the `settings` table, loaded once on library
  open via `loadDocumentsFromDb()`, and persisted back on every column-header
  click via the click handler's fire-and-forget call to `saveSortState()` —
  the async `persistDb()` happens in the background without blocking `render()`.
  **Defaults to `import_date` descending (newest-imported-first), not `date`
  descending**, because `date` (a document's own content date, e.g. invoice date)
  can be `NULL` for Inbox-imported documents until they're reviewed — sorting
  by a field that's `NULL` for a significant portion of a library would bury
  unreviewed documents in raw insertion order at the bottom of the table,
  making a review queue invisible. `import_date` (when the library imported the
  file) is always populated. **The "Imported" column is visible by default**
  specifically so this sort choice has a visible, highlighted header on first
  open — without seeing `th[data-key="import_date"]` highlighted in
  phosphor-green, a person has no way to know the table is already sorted. If
  the person never opens the Columns menu, they never disable this column, so
  the header stays visible and the sort stays legible. Clicking the header
  toggles direction (ascending on subsequent clicks); clicking a different
  column header sets that column as the new sort and defaults `date`/`import_date`
  to descending, all other columns to ascending — matching the existing click
  logic for those two special-case columns. `loadSortState()` validates the
  persisted `sort_key` against every currently-sortable column — `'title'`
  (sortable but deliberately absent from `FIELD_DEFS`, see that field's own
  note above), the rest of `FIELD_DEFS`, and `dynamicColumnDefs()`'s own ids
  (already in `'field-<id>'` form — don't re-prefix them, that was a real bug
  caught in review: re-prefixing produces `'field-field-<id>'`, which never
  matches anything, silently discarding every custom-field sort on reopen) —
  falling back to `import_date` for a stale or removed key, the same
  graceful-degradation convention `loadColumnSettings()` already uses.
- **Per-field capability checkboxes** (`toggleFieldCapability()`,
  `capabilitiesHtml()`/`wireCapabilities()` shared helpers inside
  `renderFieldSettingsFieldColumns()`) let a person flip a field's
  `show_as_column`/`autocomplete` flags directly in Field Settings — two
  small checkboxes ("Column", and "Autocomplete" for text-type fields
  only) rendered next to the field's name. **Deliberately shown in BOTH
  the Fields (available) and Display Fields (already-attached-to-this-type)
  columns**, via the same shared `capabilitiesHtml()`/`wireCapabilities()`
  helpers rather than only the Fields column — `show_as_column`/
  `autocomplete` are properties of the field itself, independent of
  `fsSelectedType`, so a field already attached to whichever type happens
  to be selected still needs a reachable way to toggle its own flags; the
  first version of this only rendered checkboxes in the Fields column and
  a field attached to every type in the library would have had no way to
  ever reach them. Not offered for People by name (it keeps its own fixed
  column -- other person-type fields get the Column checkbox but never
  Autocomplete, see the People note above) or for `'Amount'` by name (its flags
  are deliberately kept off — see the sentinel-fields note above — so an
  editable checkbox that visibly did nothing would just be confusing).
  Currency is no longer excluded here — it's a completely ordinary field
  for capability purposes now, same as Payment method, and gets these
  checkboxes like any other text field.
