# Armenian (Հայերեն) in Dossiary and its helpers

Date: 2026-10-17

## Goal and order

Armenian becomes a seventh language, everywhere the apps talk to a person.
Four sub-projects, each with its own plan and release:

1. **Dossiary: interface and Armenian documents** — this spec, below.
2. **Dossiary: an Armenian User Guide** (`USER_GUIDE.hy.md`, its 9
   screenshots made by `docs/user-guide/capture.py` in Armenian, `hy` added
   to `USER_GUIDE_LANGS`).
3. **Dossiary Scan Helper (macOS)**: its menu and panels localized into all
   seven languages (en, de, es, fr, zh-Hans, zh-Hant, hy) with a String
   Catalog; macOS picks the language from the person's preferred languages
   (Armenian can be added there, or set for this app alone).
4. **scanix500**: the menu bar app and `scanix500-server`'s command output in
   the same seven languages.

Out of scope everywhere: messages the helpers send to Dossiary inside
protocol answers ("A scan is already running…") stay English; translating
them needs a protocol field for Dossiary's language and gets its own spec.

Every sub-project's Armenian is reviewed by an Armenian speaker (the user's
neighbour) on a review page before it is released.

## Sub-project 1: Dossiary

### Language

- Code `hy`; `SUPPORTED_LANGS` gains it after `zh-Hant`; `NATIVE_LANG_NAMES`
  `hy: 'Հայերեն'`; `DATE_LOCALE` `hy: 'hy-AM'`; `LANG_AUTODETECT` gains a rule
  matching a locale that is `hy` or starts with `hy-`, so a browser set to
  Armenian starts in Armenian (the locale-major matching stays as it is).
- `STRINGS.hy` with every key `STRINGS.en` has (719 today), translated.
  Count-dependent pairs keep both keys; Armenian uses the singular after a
  numeral, so both forms are often the same text.
- `tests/test_i18n_coverage.py` loops over `SUPPORTED_LANGS`, so it covers
  `hy` without changes.

### Armenian documents

- **OCR language**: `['hye', 'ocrLangArmenian']` joins
  `ocrLanguageOptionsHtml()`, so it appears in capture, Edit and "Make
  searchable"; the new key `ocrLangArmenian` exists in all seven languages
  ("Armenian", "Armenisch", "Armenio", "Arménien", "亚美尼亚语", "亞美尼亞語",
  "Հայերեն"). Tesseract.js downloads `hye.traineddata` on first use, like
  every other language. "Auto" stays English + German.
- **Suggested values** (`suggestFromOcrText()`):
  - `OCR_MONTHS` gains the Armenian month names in nominative and genitive
    (հունվար/հունվարի … դեկտեմբեր/դեկտեմբերի).
  - The two month-name date patterns match letters in any script (`\p{L}`,
    `u` flag) instead of Latin only, so "17 հոկտեմբերի 2026 թ." is read.
    A third pattern reads the official order "2026 թ. հոկտեմբերի 17".
  - `OCR_TOTAL_WORDS` gains ընդամենը, ընդհանուր գումար, վճարման ենթակա and
    գումար.
  - `OCR_CURRENCY_TOKENS` gains `֏` and `AMD` (Armenian dram); the dram's
    symbol is `֏`.
- **Export CSV**: `csvSeparator()` returns `;` for `hy` too (Armenian writes
  decimals with a comma). Import already matches header names against every
  language's `STRINGS`, so an Armenian `index.csv` imports without changes.

### Review page

A private claude.ai page the user shares with the reviewer:

- One row per string: key, English, the Armenian, a correction box and a
  note box; corrections save as they are typed (the page's database, one
  document per key: `{key, correction, note, reviewed}`).
- Filters: all, not reviewed yet, corrected; a count of reviewed strings.
- Strings with `{placeholders}` show them highlighted, with a warning when a
  correction drops or renames one.
- The Armenian for the OCR words (month names, total words) is listed on the
  page too, as its own group, since those are also language.
- When the review is done, Claude reads the corrections from the page's
  database, applies them to `STRINGS.hy` (and the OCR word lists), and
  reports which strings changed.

### Release

Only after the review: merge, `APP_VERSION` and `scan_watch.py` bumped
(minor version), User Guide screenshots unchanged (sub-project 2 adds the
Armenian ones), GitHub release, `/Applications/Dossiary/dossiary.html`
updated.

### Testing

- `test_i18n_coverage.py`: all keys in `hy` (as today), plus a new check
  that every language's text for a key has exactly the `{placeholders}` the
  English text has -- a translation that drops `{count}` would otherwise
  only show up as a wrong message at runtime.
- `test_i18n.py` gains scenarios: `navigator.languages = ['hy-AM']` starts in
  Armenian and the dropdown shows Հայերեն; dates format as `hy-AM`;
  switching to Armenian and back retranslates the nav and toolbar.
- `test_ocr_suggestions.py` gains Armenian cases: "17 հոկտեմբերի 2026 թ.",
  "2026 թ. հոկտեմբերի 17", a total line "Ընդամենը 12500,00 ֏" giving 12500.00 AMD.
- `test_export.py`: Armenian UI exports with `;`.
- The full suite stays green.
