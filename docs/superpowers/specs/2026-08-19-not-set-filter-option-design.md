# "Not set" filter option

## Context

Dossiary's toolbar filters (Category, Type, People, plus any custom text/
checkbox field flagged `show_as_column`) are plain `<select>` dropdowns
populated via `populateFilters()` with the distinct values actually present
across the library, plus an "All X" default that means "no filter active."
There is currently no way to filter *to* documents where a given field is
blank — e.g. "show me every document with no Category," useful for finding
gaps in a large library.

This adds exactly that: one new option per existing filter dropdown,
"— Not set —," that filters to documents missing that field entirely.

## Approach

**The core problem to solve:** the empty string (`""`) is already the
sentinel `currentFilters()`/`matchesCriteria()` use for "this filter isn't
active" (the value of the "All Categories" option). A "not set" option
needs a *different* sentinel value that can never collide with a real
category/type/person/field-value string, since those are free text a
person can type anything into.

**The sentinel:** a module-level constant, e.g. `const FILTER_UNSET =
'__unset__';`, used consistently in two places:

1. `populateFilters()` — each dropdown's option list gains one new
   `<option value="__unset__">— Not set —</option>`, inserted right after
   the existing "All X" option and before the real distinct values. This
   applies uniformly to Category, Type, People, and every dynamic
   (`show_as_column` + `hasFilter`) custom field's own generated dropdown
   — one small change to `populateFilters()`'s template strings, not four
   separate implementations.

2. `matchesCriteria()` — the single function both the live toolbar filters
   and Smart Collections' saved criteria already funnel through. Each
   field's match check gains a `=== FILTER_UNSET` branch:
   - **Category / Type** (scalar `documents` columns): currently
     `if(category && d.category !== category) return false;`. Becomes: if
     `category === FILTER_UNSET`, exclude any document that *has* a
     category (`!!d.category`); otherwise the existing real-value
     comparison, unchanged. Same shape for `type`.
   - **People** (multi-valued array): currently `if(person &&
     !(d.people||[]).includes(person)) return false;`. Becomes: if
     `person === FILTER_UNSET`, exclude any document whose People array is
     non-empty; otherwise the existing `.includes()` check, unchanged.
   - **Dynamic custom fields**: currently `if((d.customFields ||
     {})[f.label] !== f.value) return false;` inside the loop over active
     dynamic filters. Becomes: read `actual = (d.customFields ||
     {})[f.label]` once; if `f.value === FILTER_UNSET`, exclude any
     document where `actual !== undefined` (the field has *any* saved
     value — including an unchecked checkbox's `'0'`, which is real saved
     data, not "unset"); otherwise the existing `actual !== f.value`
     comparison, unchanged.

Because `matchesCriteria()` is the single shared predicate for both the
live toolbar and Smart Collections' stored JSON criteria, and because
`currentFilters()` needs no changes at all (it already just reads whatever
value is selected in each `<select>`, sentinel or not), this one function
change is sufficient to make "not set" work everywhere filters already
apply — including inside a Smart Collection and inside the Reports view's
own filter composition — with no separate code path for either.

**Label and i18n.** One shared string, not four separate keys — a single
`toolbarFieldNotSet` key ("— Not set —" in English) reused for every
field's dropdown, the same way `toolbarAllDynamic` is already reused
(with a `{label}` parameter) for every dynamic field's "All X" option.
Unlike that key, this one doesn't need a `{label}` parameter — "— Not
set —" reads correctly standing alone in any of the dropdowns. Needs a
translation in all six supported languages (`STRINGS.en`/`.de`/`.es`/`.fr`/
`['zh-Hans']`/`['zh-Hant']`), following the same convention every other UI
string in this app already uses.

## Out of scope

- Number/Date/Amount/Currency fields have no filter dropdown at all today
  (a deliberate existing choice — a dropdown of distinct numbers/dates
  isn't useful), so they get no "not set" filter either. Adding one would
  mean building a new UI affordance from scratch, not extending an
  existing dropdown — a separate feature, not this one.
- No change to `populateFilters()`'s existing distinct-value computation,
  sorting, or the datalist/autocomplete system (`populateDatalists()`) —
  those are unrelated (autocomplete suggests values while typing into
  free-text fields elsewhere in the app; this feature is about the
  toolbar's filter dropdowns specifically).
- No change to the Reports view's own Currency-blank grouping
  (`computeReportGroups()`'s existing "No currency set" bucket) — that's
  a separate, pre-existing mechanism for a different purpose (grouping
  totals), not a filter; this spec doesn't touch it, just notes it as
  existing precedent for the same underlying idea.

## Critical files

- `dossiary.html`:
  - A new `FILTER_UNSET` constant, defined once near the other
    module-level constants.
  - `populateFilters()` (~line 3543) — Category/Type/People's static
    option-list template strings, and the dynamic-filter template string,
    each gain the one new `<option>`.
  - `matchesCriteria()` (~line 3778) — the category/type/person checks and
    the dynamic-fields loop, each gain the `=== FILTER_UNSET` branch
    described above.
  - `STRINGS` — one new key (`toolbarFieldNotSet`) added to all six
    language blocks.

## Testing

- A real Playwright test seeding documents with a mix of set and blank
  Category/Type/People/a custom text field, confirming: the "— Not set —"
  option appears in each dropdown, selecting it shows only the
  blank-field documents, and switching back to "All X" restores the full
  set.
- A checkbox-specific case: a document where a checkbox custom field was
  explicitly saved as unchecked (`'0'`) must NOT appear under "— Not
  set —" for that field (it has real saved data), while a document where
  that field was never configured/saved at all must appear.
- A Smart Collection created with a "not set" filter active, confirming
  its saved criteria correctly reproduce the same "blank" filtering on
  reopen (proving the shared `matchesCriteria()` path works for saved
  criteria, not just the live toolbar).
- `tests/test_i18n_coverage.py` (the existing static key-coverage check)
  should pass unmodified once the new key is added to all six language
  blocks — no test-file changes needed there, just don't forget any
  language.
