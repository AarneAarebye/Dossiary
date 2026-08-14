# UI language support (English / German) — design

## Context

Dossiary's UI (`dossiary.html`) is English-only — every button label, nav
item, table header, form label, hint, status message, and modal is a
hardcoded English string baked directly into HTML markup or JS template
literals. This repo already has a precedent for German as a second
language at the documentation level (`README.de.md`, `MIGRATION.de.md`),
but nothing in the app itself adapts to a person's language.

This project adds a real English/German toggle for the app's own
interface, translating the app's fixed chrome throughout — not just a
handful of top-level labels.

## Goal

Every piece of fixed UI text Dossiary itself displays — nav, toolbar,
table/column headers, capture/edit form labels and hints, detail-view
labels, all modals (Field Settings, Manage Collections, Libraries/
licenses, etc.), status/confirmation messages, and the pre-library
empty-state screen — renders in whichever of English or German is
currently selected, switchable at any time without reloading the page.

## Non-goals

- **User-entered data is never translated.** Category/Type/Subcategory/
  Tag/custom-field names and values, document titles, notes, and OCR text
  stay exactly as the person typed them, in whichever language that is —
  this project only translates strings Dossiary itself wrote into the
  markup, never anything sourced from `library.sqlite`.
- **`README.md`/`CLAUDE.md`/code comments are untouched.** `README.de.md`
  already exists as its own, separately maintained file; this project's
  in-app toggle has no relationship to it and doesn't change how the
  README translations are maintained.
- **No third language.** The `STRINGS` structure (below) is shaped so a
  third language could be added later by adding one more object key, but
  actually adding one is out of scope here.
- **No per-library override.** See "Persistence" below — this is one
  browser-wide setting, not a `settings`-table row that could differ
  library to library.
- **No OCR-language interaction.** The existing `#ocr-lang`/`#e-ocr-lang`
  selectors (which control what Tesseract.js recognizes) are completely
  separate from this feature and are not touched.

## Architecture

### `STRINGS` dictionary + `t()` lookup

A single module-level object near the top of `dossiary.html`, alongside
the other module-level constants:

```js
const STRINGS = {
  en: {
    navAllDocuments: 'All Documents',
    navInbox: 'Inbox',
    // ... one key per translatable string, flat namespace
    statusInboxAdded: 'Added {count} document(s) to the review queue from {folder}.',
  },
  de: {
    navAllDocuments: 'Alle Dokumente',
    navInbox: 'Posteingang',
    statusInboxAdded: '{count} Dokument(e) aus {folder} zur Prüfung hinzugefügt.',
  },
};

let currentLang = loadLang(); // 'en' | 'de', see Persistence below

function t(key, params){
  let str = STRINGS[currentLang][key] ?? STRINGS.en[key] ?? key;
  if(params){
    for(const [k, v] of Object.entries(params)) str = str.replaceAll(`{${k}}`, v);
  }
  return str;
}
```

Falling back to `STRINGS.en[key]` (and, failing that, the raw key itself)
means a key that's missing or not-yet-translated in German never renders
blank — worst case it shows English or the literal key, both of which are
obviously-wrong-and-fixable rather than silently empty UI.

Placeholder interpolation is a plain `{name}` token + `replaceAll` — no
pluralization rules, ICU syntax, or other i18n-library machinery. This
project's whole UI needs maybe a dozen strings with any interpolation at
all (counts, filenames, folder names); a real plural/ICU system is more
machinery than that warrants, and every existing count string in this app
already reads fine with a single invariant form (e.g. "1 document(s)"
rather than a grammatically-perfect singular/plural split — matching how
`renderStats()`'s existing "N documents" label already works today,
unchanged).

### Static markup: `data-i18n` attributes + `applyI18n()`

Any element whose text is fixed at parse time (nav items, toolbar
buttons, static column headers, form `<label>`s, static hint paragraphs,
modal titles baked into the HTML) gets a `data-i18n="<key>"` attribute in
the existing HTML. Two attribute-targeting variants cover the two other
places translatable text hides:

- `data-i18n-placeholder="<key>"` → sets `.placeholder`
- `data-i18n-title="<key>"` → sets `.title` (tooltips)

```html
<button id="inbox-check-btn" data-i18n="toolbarCheckInbox">📥 Check inbox</button>
<input id="search" data-i18n-placeholder="searchPlaceholder" placeholder="Search...">
```

`applyI18n()` walks all three attribute kinds once and applies `t()`:

```js
function applyI18n(){
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = t(el.dataset.i18nTitle);
  });
}
```

Called once during the app's existing static-wiring pass (the same pass
that wires the Libraries-link handler and sets the version label — see
CLAUDE.md's Versioning note; this pass is already documented as running
regardless of whether a library is open, which is exactly the property
this feature also needs for the empty-state screen), and again every time
the language toggle changes.

### Dynamic markup and JS-only strings: inline `t()` calls

Anything built fresh in JS — table rows, `openDetail()`'s modal body,
`renderNav()`'s badges, `setStatus()` messages, confirmation text — calls
`t('key')` (or `t('key', {params})`) directly inside its own template
string or argument, the same way these functions already reference other
module-level state. No `data-i18n` attribute is needed for these, since
the element doesn't exist until the moment it's rendered with the current
language already baked in — re-running the enclosing render function
(`render()`, `openDetail(id)`, etc.) after a language switch naturally
picks up the new language, same as it already does for other state
changes like `applyColumnVisibility()`.

### Switching language

```js
function setLang(lang){
  currentLang = lang;
  saveLang(lang);
  applyI18n();
  if(rootDirHandle){ render(); } // re-render whatever's on screen
  // if a modal is currently open (detail/edit/capture/Field Settings/...),
  // re-invoke whichever open*Modal/open*Form function produced it, using
  // the same pattern each of those already uses to refresh in place
  // after a data change (e.g. regenerateThumbnail()'s own
  // update -> persist -> render() -> re-open-the-modal sequence).
}
```

## Toggle: placement, detection, persistence

**Placement:** the footer, next to the existing `#app-version-label` —
the one place CLAUDE.md documents as "shown regardless of app state,"
which this feature needs since the empty-state "Open Library" screen (no
library open yet, no `settings` table to read from) must also translate.
Rendered as a small two-state button, `EN | DE`, following the same
toggle-button convention as `#nav-style-toggle` — clicking it calls
`setLang()` with the other language.

**Detection:** on first-ever load, before any explicit choice exists,
`loadLang()` checks `navigator.language`/`navigator.languages` for a
`de`-prefixed tag and returns `'de'` if found, else `'en'`:

```js
function loadLang(){
  const stored = localStorage.getItem('dossiary_lang');
  if(stored === 'en' || stored === 'de') return stored;
  const langs = navigator.languages || [navigator.language || ''];
  return langs.some(l => l.toLowerCase().startsWith('de')) ? 'de' : 'en';
}
function saveLang(lang){
  localStorage.setItem('dossiary_lang', lang);
}
```

**Persistence: `localStorage`, not the per-library `settings` table.**
This is a deliberate departure from the `nav_style`/`sort_key`/
`default_currency` pattern (all stored per-library in `settings`) — those
all assume a library is already open, but the language toggle has to work
on the pre-library empty-state screen too, where no database exists yet.
Once a person ever clicks the toggle, `localStorage` remembers that
choice permanently and `loadLang()` never consults `navigator.language`
again — an explicit choice always wins over auto-detection, and the
choice follows the browser (all libraries opened in it), not any one
library.

## Date formatting

The existing `toLocaleDateString(undefined, {...})` call (used for the
detail view's date display) passes `undefined` for locale, which means it
already follows the browser's own OS/browser locale — independent of, and
possibly inconsistent with, this new in-app toggle (e.g. an en-US browser
with German UI selected would still show English-formatted dates). This
project changes that one call site to pass `currentLang === 'de' ?
'de-DE' : 'en-US'` explicitly, so date formatting follows the selected UI
language rather than a separate, invisible signal.

## String coverage

Every user-facing string Dossiary's own code renders needs a `STRINGS`
entry and either a `data-i18n`-family attribute or an inline `t()` call,
across every area of the app: top nav (labels + badges' surrounding
text), toolbar (all buttons, Columns menu, filters, search placeholder),
table (column headers, empty states, per-row buttons' titles), capture
and edit forms (every field label, hint, guess-hint, button), the detail
modal (every label, action button, path-line "Copy"/"Copied!" text),
Field Settings modal, Manage Collections modal + bulk-action bar, Reports
view, the Libraries/licenses modal, the empty-state/recent-libraries
screen, drag-and-drop overlay text, and every `setStatus()` call site
across the file (capture/edit save confirmations, Inbox/drag-and-drop
summaries, error messages).

This is a large, mechanical pass across the whole file rather than a
single localized change — the implementation plan should decompose it
into one task per UI area listed above (each independently testable:
toggle the language, confirm that area's strings switch and nothing
else breaks), plus one task for the `STRINGS`/`t()`/`applyI18n()`
infrastructure itself that every area-task depends on.

## Testing

New `tests/test_i18n.py`, following the existing stub/Playwright
conventions (`stub_studio2.js`, no real `sql.js`), covering:

- Default language on first load with no `navigator.language` override
  matches the existing English strings (regression guard — confirms the
  toggle doesn't change default behavior for an unconfigured browser).
- Overriding `navigator.language` to `de-DE` before load (via Playwright's
  `page.add_init_script` or an equivalent locale-injection mechanism,
  already precedented by `test_scan_hint.py`'s OS-detection override —
  see CLAUDE.md's scan-hint note) results in German strings on first load
  with no stored preference.
- Clicking the toggle switches visible strings in: the nav, the toolbar,
  an open capture form, and an open detail modal (one assertion per area,
  not exhaustive per-string coverage).
- The choice persists across a reload (`localStorage` round-trip) and
  overrides `navigator.language` from then on, even if the browser
  locale would otherwise suggest the other language.
- The empty-state (no library open) screen's strings switch too,
  confirming the toggle and `applyI18n()` both work without a database.
- A string with a `{param}` placeholder (e.g. the Inbox-added status
  message) renders with the interpolated value correctly in both
  languages.
- Every key referenced by a `data-i18n*` attribute or a `t()` call in
  `dossiary.html` exists in both `STRINGS.en` and `STRINGS.de` — a static
  coverage check (e.g. a small Node/Python script cross-referencing
  `grep -o` output against the `STRINGS` object) rather than a
  per-string Playwright assertion, since asserting every one of several
  hundred strings individually in a browser test would be both slow and
  unmaintainable.

## Documentation

CLAUDE.md gets a new architecture note describing `STRINGS`/`t()`/
`applyI18n()`/`data-i18n`, the `localStorage`-not-`settings`-table
persistence decision and why (empty-state screen has no database yet),
and the auto-detect-then-manual-override behavior — following this
project's established pattern of explaining *why*, not just *what*, for
any non-obvious architectural choice.
