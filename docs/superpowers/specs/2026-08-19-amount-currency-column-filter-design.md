# Amount/Currency column and filter

## Context

Amount and Currency are plain generic `fields` rows (`type: 'number'` /
`type: 'text'`) that deliberately opted **out** of the generic
column/filter/autocomplete system when the sentinel-fields migration
landed (`migrateSentinelFieldsToGeneric()`, dossiary.html:2963) —
`show_as_column: 0, autocomplete: 0` for both, and `capabilitiesHtml()`
(dossiary.html:4971) hides their capability checkboxes in Field Settings
by name so nobody can toggle something that would visibly do nothing.
The reason: their table cell and detail-view line stay intentionally
combined into one `"123.45 EUR"` display (`formatAmount()`,
dossiary.html:3640), driven by a dedicated fixed `FIELD_DEFS` entry
(`{id: 'amount', hasFilter: false, defaultVisible: true}`,
dossiary.html:2008) rather than the generic per-field system.

Sorting by Amount already works today (`sortDocs()` has a dedicated
numeric-compare branch, dossiary.html:3894) — that part needs no changes.
What's missing: filtering to one currency, filtering/finding documents by
an amount range, and "not set" filtering for either — none of which exist
anywhere in the app today. This adds all three, in the main toolbar
alongside Category/Type/People, so they work everywhere those already do
(All Documents, Inbox, Collections, Waste bin — not just Reports).

## Approach

### Currency: opt into the existing generic system

Currency already qualifies for `dynamicColumnDefs()` (dossiary.html:2018)
and `populateFilters()` (dossiary.html:3551) exactly like any other
`show_as_column` text field (e.g. Payment method) — it's excluded purely
by the two hardcoded name checks below. Removing the Currency exclusion
from both gives it, through code that already exists and is already
tested: a standalone "Currency" table column (toggleable via the Columns
menu, sortable, defaulting to **hidden** — `defaultVisible: false` — since
the existing combined Amount column already shows currency inline, so a
visible-by-default duplicate would be redundant), a filter dropdown with
every distinct currency value plus "— Not set —" (same `FILTER_UNSET`
sentinel and `matchesCriteria()` dynamic-field branch every other
`show_as_column` text field already uses — no new matching code), and an
autocomplete datalist. Amount stays excluded from all of this — it never
gets a filter dropdown from this mechanism regardless (number fields
don't), so exposing an editable-but-inert checkbox for it would just be
confusing, per the existing comment at dossiary.html:4973.

**Two exclusion points to update**, both currently name-based checks —
remove `'Currency'` from each, leave `'Amount'` in place:
- `capabilitiesHtml()` (dossiary.html:4973): `if(!fieldDef ||
  fieldDef.type === 'person' || fieldName === 'Amount' || fieldName ===
  'Currency') return '';` → drop the `'Currency'` arm.
- The detail view's generic "Fields" section exclusion
  (dossiary.html:4333): `.filter(([name]) => name !== 'Amount' && name
  !== 'Currency' && name !== 'Payment method')` — this one **stays
  unchanged**. It exists to avoid double-showing Amount/Currency, which
  already appear on the combined header line (dossiary.html:4296); that
  reason doesn't go away just because Currency also gets a table column.

**Defaults for Currency's `show_as_column`/`autocomplete`:**
- New libraries: `migrateSentinelFieldsToGeneric()` itself runs on every
  library open, including a brand new one (`initNewLibrary()` calls it,
  same as `loadDb()` does) — for a new library its idempotency check
  finds no `'Payment method'` row yet, so it proceeds and creates
  Currency's field row fresh from the array literal at dossiary.html:2970
  (`{ name: 'Currency', type: 'text', showAsColumn: 0, autocomplete: 0
  }`). Changing that literal to `showAsColumn: 1, autocomplete: 1` is
  sufficient for every new library — no separate new-library code path
  needed. Amount's own entry (dossiary.html:2969) is unchanged.
- Existing libraries: a new one-time backfill migration,
  `migrateCurrencyColumnDefault()`, following the exact pattern
  `migrateTextFieldsAutocompleteDefault()` (dossiary.html:3076) already
  established — tracked via its own `settings` row (e.g.
  `currency_column_default_migrated`) rather than an implicit data-shape
  check, so it runs exactly once and doesn't silently re-enable something
  a person deliberately turned back off in Field Settings afterward. Sets
  `show_as_column = 1, autocomplete = 1` on the `'Currency'` field row if
  not already migrated. Called from both `initNewLibrary()` and
  `loadDb()`, same call sites as its sibling migrations.

**Reports interaction:** `reportBreakdownFields()` (dossiary.html:3657)
spreads `dynamicColumnDefs()` directly — once Currency has
`show_as_column: 1`, it appears there automatically. But Reports already
groups totals by Currency at the top level (a separate, pre-existing
mechanism — `computeReportGroups()`), so offering Currency *again* as a
breakdown-within-a-currency-group dimension would be a redundant, mildly
confusing option. Add an explicit filter: `dynamicColumnDefs().filter(f
=> f.label !== 'Currency')` before spreading into
`reportBreakdownFields()`'s return — the same name-based exclusion
convention this codebase already uses for Amount/Currency/Payment method
elsewhere, joining Date/Amount/Tags as fields already excluded from
breakdown for their own stated reasons.

### Amount: a new range filter, not part of the generic system

Two new toolbar controls, positioned next to the new Currency filter
dropdown:
- `#amount-filter-min`, `#amount-filter-max` — plain `<input
  type="number">`, unlabeled placeholder text (e.g. "Min", "Max"), no
  clear button (Reports' own existing date-range filter,
  `#report-date-from`/`#report-date-to` at dossiary.html:548-550, has
  neither — this is the one existing precedent for a range filter in this
  app, and the new one follows its shape).
- `#amount-filter-unset` — a checkbox, mirroring the existing "Show
  archived" toolbar checkbox pattern. Checking it disables (and visually
  greys) the two number inputs; typing a value into either number input
  unchecks it and re-enables the other — the two states are mutually
  exclusive (a document can't simultaneously have no Amount and have one
  within a range).

**`currentFilters()`** (dossiary.html:3776) gains `amountMin`,
`amountMax`, `amountUnset` fields, read directly from the three new
controls' current values (same as every other toolbar filter already
does — no debouncing or extra state).

**`matchesCriteria()`** (dossiary.html:3788) gains a new block, after the
existing scalar/array checks and before the `dynamic` loop:
```js
if(amountUnset){
  if((d.customFields || {})['Amount'] !== undefined) return false;
} else if(amountMin !== '' || amountMax !== ''){
  const raw = (d.customFields || {})['Amount'];
  const amt = raw != null && raw !== '' ? parseFloat(raw) : NaN;
  if(isNaN(amt)) return false;
  if(amountMin !== '' && amt < parseFloat(amountMin)) return false;
  if(amountMax !== '' && amt > parseFloat(amountMax)) return false;
}
```
The not-set check is deliberately `!== undefined` on the raw stored
value, **not** a check against `formatAmount()`'s "amount is `0` or
`NaN` displays as `—`" rule (dossiary.html:3643) — those are different
concepts. A document with Amount explicitly saved as `0` has real,
meaningful saved data (matching the exact same checkbox-`'0'`-is-not-
unset distinction this codebase already enforces for every other field,
e.g. the dynamic-fields loop two lines below this new block); only a
document with no `document_field_values` row for Amount at all counts as
"not set."

Because both new pieces flow through the same shared `matchesCriteria()`
already used by the live toolbar, `matchesView()`'s Smart Collection
branch, and the Manage Collections member count, they get Smart
Collection support for free (e.g. "save a collection of everything over
€500 with no currency set") and compose correctly with every existing
filter via the same implicit AND — including the specific combination of
"Amount not set AND Currency is set," which needs no dedicated code of
its own.

### i18n

New keys needed in all six `STRINGS` blocks (en/de/es/fr/zh-Hans/
zh-Hant), following existing naming conventions:
- Currency's "All Currencies" option needs no new key at all — since
  Currency flows through the existing *dynamic* filter template
  (dossiary.html:3561-3567) rather than a dedicated Category/Type/People-
  style one, it already reuses the existing `toolbarAllDynamic` key with
  `{label: 'currency'}`, exactly like Payment method's filter does today.
- Titles/placeholders for the two number inputs (e.g.
  `toolbarAmountMinTitle`, `toolbarAmountMaxTitle`).
- Label for the "not set" checkbox (e.g. `toolbarAmountUnsetLabel`).

`tests/test_i18n_coverage.py` enforces key parity across all six blocks
automatically once added — no test-file changes needed there.

## Out of scope

- No change to the combined `"123.45 EUR"` Amount column or the detail
  view's combined header line — both stay exactly as they are. This adds
  an *additional*, independently-toggleable Currency column, not a
  replacement.
- No min>max guard or validation — an empty-result range is a legitimate
  (if unhelpful) filter state, same as any other min>max range filter;
  not worth extra logic for, consistent with this app's "don't validate
  scenarios that can't meaningfully happen" convention.
- No change to the capture/edit form's existing Currency behavior — it
  keeps its own hardcoded `currency-list` datalist and `defaultCurrency`
  guess-on-capture special cases (dossiary.html:3255,3305) untouched;
  this spec only touches table/filter behavior, not the form.
- No Amount range support in Reports' own breakdown/grouping — Reports
  already computes real totals per currency group and per breakdown
  dimension; a toolbar Amount range filter narrows *which documents* feed
  those totals (via the shared `applyFilters()`/`matchesCriteria()` path
  every view already goes through), which is sufficient — no separate
  Reports-specific amount UI is being added.

## Critical files

- `dossiary.html`:
  - `migrateSentinelFieldsToGeneric()` (~line 2963) / `initNewLibrary()`'s
    field-creation call (~line 2970) — Currency's `showAsColumn`/
    `autocomplete` defaults flip to `1`/`1` for new libraries.
  - New `migrateCurrencyColumnDefault()` function, called from both
    `initNewLibrary()` and `loadDb()`, following
    `migrateTextFieldsAutocompleteDefault()`'s (~line 3076) exact pattern
    — one-time backfill for existing libraries, tracked via a new
    `settings` row.
  - `capabilitiesHtml()` (~line 4971) — drop the `fieldName === 'Currency'`
    arm from the exclusion check at ~line 4973.
  - `reportBreakdownFields()` (~line 3657) — filter Currency out of the
    spread `dynamicColumnDefs()` result by name.
  - New toolbar markup: `#amount-filter-min`, `#amount-filter-max`,
    `#amount-filter-unset` (near the existing Category/Type/People
    filters and the `#dynamic-filters` container).
  - `currentFilters()` (~line 3776) — three new fields read from the new
    controls.
  - `matchesCriteria()` (~line 3788) — new Amount range/not-set block, as
    shown above.
  - `STRINGS` — new keys (title/placeholder/label strings for the three
    new controls) added to all six language blocks.

## Testing

A new Playwright test file (`tests/test_amount_currency_filter.py`),
following `test_not_set_filter.py`'s shape, covering:
- Currency column appears in the Columns menu (hidden by default),
  toggling it on shows the right values, sorting works.
- Currency filter dropdown lists distinct values plus "— Not set —";
  selecting a value/not-set narrows correctly; a Smart Collection saved
  with a Currency filter active reproduces the same filtering on reopen.
- Amount range filter: min only, max only, both, and the empty-result
  min>max case, against documents with a spread of Amount values.
- Amount "not set" checkbox: matches only documents with no saved Amount
  value at all — critically, **not** a document with Amount explicitly
  saved as `0` (real data, not unset) — and unchecking it (or typing into
  either number input) restores range-filter behavior.
- The combined case: Currency filter set to one value AND Amount "not
  set" checked simultaneously, confirming AND composition with no
  dedicated combo code.
- Existing-library backfill: a seeded library with Currency's
  `show_as_column`/`autocomplete` still at `0`/`0` (pre-migration shape)
  gets flipped to `1`/`1` on open, and stays that way — but a library
  where a person already manually toggled `show_as_column` back off
  *after* an earlier run of the migration stays off across a reopen
  (idempotency, same property `migrateTextFieldsAutocompleteDefault()`'s
  own test already covers for its own migration).
- Reports' breakdown-field dropdown does **not** list Currency as an
  option, before and after the migration runs.
- `tests/test_i18n_coverage.py` passes unmodified once the new keys are
  added to all six language blocks.
