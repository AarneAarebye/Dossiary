# Additional UI languages: Spanish, French, Chinese (Simplified & Traditional) — design

## Context

Dossiary's UI currently supports English and German (`STRINGS.en`/`STRINGS.de`,
a two-state footer toggle, `t()`/`applyI18n()`, `localStorage`-backed
persistence with browser-locale auto-detection — see CLAUDE.md's own
architecture note for the full mechanism). The original design explicitly
left a third language out of scope but shaped `STRINGS` so one could be
added later "by adding one more object key."

Separately, Dossiary's OCR feature (`#ocr-lang`/`#e-ocr-lang`) already
recognizes six languages: German, English, French, Spanish, Chinese
Simplified, and Chinese Traditional. This project brings the **UI**
language toggle to parity with that list — adding Spanish, French,
Chinese (Simplified), and Chinese (Traditional) as full UI languages,
alongside the existing English/German. UI language and OCR language
remain two completely independent settings, per the original design's own
explicit non-goal ("no OCR-language interaction") — this project doesn't
change that; it just happens to result in the same six-language list
existing on both settings, by coincidence of scope, not by coupling them.

Also in scope: a User Guide (`USER_GUIDE.<lang>.md`) per new language, and
extending `USER_GUIDE_LANGS` (added in a just-landed, adjacent change that
put a footer link to the User Guide into the app itself) so the in-app
link points at each language's own guide once it exists.

## Non-goals

- **No OCR-language coupling.** The UI-language and OCR-language settings
  stay two independent selectors, as before. This project's six-language
  UI list matching the six-language OCR list is coincidental scope
  alignment, not a shared mechanism.
- **No further languages beyond these four.** Same "shaped for it, not
  doing it now" posture the original spec took toward a third language.
- **No regional variants beyond the Traditional/Simplified Chinese
  split** (no separate `es-MX` vs `es-ES`, no separate `fr-CA` vs
  `fr-FR`) — one Spanish, one French, consistent with how English and
  German are each a single variant today.

## Architecture

### `STRINGS` and `SUPPORTED_LANGS`

`STRINGS` gains four new top-level blocks: `es`, `fr`, `zh-Hans`, `zh-Hant`
— each a full translation of every existing key (currently ~272, per the
coverage check). `currentLang` generalizes from a hardcoded `'en'|'de'`
type to a value drawn from a new module-level constant:

```js
const SUPPORTED_LANGS = ['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant'];
```

`t()`'s fallback chain is unchanged (`STRINGS[currentLang][key] ??
STRINGS.en[key] ?? key`) — it was already written generically enough to
need no change for more languages.

### Chinese pluralization

Chinese does not inflect for grammatical number. The existing
singular/plural key-pair convention (e.g. `sharedPageCountSingular`/
`...Plural`, picked by a `count === 1 ? ... : ...` ternary at the call
site) still applies mechanically — `zh-Hans`/`zh-Hant` simply get
*identical* text in both slots of every pair, rather than a new
no-plural code path. This keeps every existing call site untouched.

### Deriving Traditional from Simplified

`zh-Hans` is translated natively (as real translation work, same as
`es`/`fr`). `zh-Hant` is **derived programmatically from the finished
`zh-Hans` block**, using `opencc-python-reimplemented`'s `s2t` (Simplified
→ Traditional) conversion profile — the same OpenCC engine Wikipedia and
other major projects use for this exact conversion — rather than
translated a second time independently. Simplified and Traditional
Chinese are the same language with two different character sets, not two
different languages; converting is both faster and guarantees the two
stay in lockstep (no risk of `zh-Hans` and `zh-Hant` drifting to say
subtly different things for the same key). This is a one-time conversion
run whose *output* (the literal `STRINGS['zh-Hant']` object) is committed
to `dossiary.html` as plain text — the app itself has no OpenCC
dependency at runtime; nothing changes about the app's zero-dependency,
single-file nature.

### Auto-detection and Chinese region disambiguation

`loadLang()` generalizes from a single `de`-prefix check to matching
`navigator.languages` against all six codes, first match wins. Chinese
needs real disambiguation, since `navigator.language` reports a region
(`zh-CN`, `zh-TW`, ...) or sometimes a script (`zh-Hans`, `zh-Hant`)
rather than reliably indicating simplified/traditional on its own:

- Region `CN`, `SG`, `MY`, or explicit script `Hans` → `zh-Hans`
- Region `TW`, `HK`, `MO`, or explicit script `Hant` → `zh-Hant`
- Bare `zh` with no recognizable region/script → `zh-Hans` (more widely
  read globally; same "best guess, dismissible by the existing
  manual-override-wins rule" spirit as every other auto-detect default
  in this app)

Like today, this only ever runs once, on first load with no stored
preference — any manual selection permanently overrides it from then on.

### Footer toggle: dropdown replaces the two-state button

The `EN | DE` two-state `#lang-toggle` button is replaced with a
`<select id="lang-select">` listing all six languages by their own native
name (`English`, `Deutsch`, `Español`, `Français`, `简体中文`, `繁體中文`).
`setLang(lang)` keeps its existing signature and behavior (`applyI18n()`,
conditional `render()`/`renderStats()`/`populateFilters()`/
`renderColumnsMenu()`/`renderRecentLibraries()`/`userGuideLink` update
calls) — only the control that invokes it changes, from a click handler
toggling between two hardcoded values to a `change` handler reading
`event.target.value`. The existing modal-open guard (`if(modalRoot.innerHTML)
return;`, added during the original project's final review to fix the
keyboard-accessibility gap) moves to this handler unchanged.

### Date formatting

`toLocaleDateString`'s currentLang→locale map gains `es-ES`, `fr-FR`,
`zh-CN` (for `zh-Hans`), and `zh-TW` (for `zh-Hant`).

### User Guides

`USER_GUIDE.es.md`, `USER_GUIDE.fr.md`, `USER_GUIDE.zh-Hans.md`,
`USER_GUIDE.zh-Hant.md` — same structure and scope as `USER_GUIDE.de.md`
(non-technical, paper-only first-time user, core capture/find/Inbox loop
plus a light tour), each with its own full screenshot set under
`docs/user-guide/<lang>/`, captured the same way as before: a small
fabricated demo library driven through the real app via browser
automation, toggling the new dropdown to each language between passes.
`USER_GUIDE_LANGS` (in the just-landed footer-link change) grows to
`['de', 'es', 'fr', 'zh-Hans', 'zh-Hant']` so the in-app "User Guide" link
resolves to each language's own guide instead of silently falling back to
English for these four.

`USER_GUIDE.zh-Hant.md` is translated the same way as its `STRINGS['zh-Hant']`
counterpart — OpenCC conversion of the finished `USER_GUIDE.zh-Hans.md`
prose — for the same consistency reason. Screenshots are **not** shared
between the two Chinese guides, since the UI itself renders different
characters in each language state; each still gets its own real
screenshot pass.

## String coverage

Every one of the ~272 existing keys needs a translation in all four new
blocks — this is the dominant cost of this project, not new mechanism.
`tests/test_i18n_coverage.py` generalizes from its current hardcoded
`STRINGS.en`/`STRINGS.de` comparison to looping over every language in
`SUPPORTED_LANGS`, so it continues to guarantee no `data-i18n`/`t()`
reference is ever missing from any language, present or future.

## Testing

`tests/test_i18n.py` gets a **small, targeted set of new scenarios** —
not a full re-run of all 22 existing scenarios per new language, which
would be excessive:

- Auto-detection for each of `es`, `fr`, `zh-Hans` (via a `zh-CN` browser
  locale), and `zh-Hant` (via a `zh-TW` browser locale) — confirming the
  region-disambiguation logic specifically, since that's the one place
  with real new branching logic.
- The dropdown lists all six languages and switching via `change` (not
  `click`) correctly updates the UI, mirroring one existing
  toggle-behavior scenario but through the new control.
- A spot-check of translated content in each of the four new languages
  (one nav item, one form label, one status message — same
  "one assertion per area, not exhaustive per-string" bar the original
  spec set) — not all 22 areas repeated four times over.
- The existing modal-open guard still blocks the dropdown the same way
  it blocked the old button (reusing the existing keyboard-accessibility
  test's approach, adapted to a `<select>`).

`tests/test_i18n_coverage.py`'s generalization (above) is itself the
primary safety net for the bulk of the new content — it will catch any
missing key in any of the four new blocks without needing a Playwright
assertion for it.

## Documentation

CLAUDE.md's existing i18n architecture note gets extended (not
rewritten) to cover: `SUPPORTED_LANGS`, the dropdown replacing the old
two-state button, Chinese's shared-singular-plural-text handling, the
region-disambiguation rules for Chinese auto-detect, and the
OpenCC-derivation approach for `zh-Hant` (from both `STRINGS['zh-Hant']`
and `USER_GUIDE.zh-Hant.md`) — including *why* (same language, different
script, vs. independent translation risking drift).
