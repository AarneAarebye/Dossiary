# Armenian in Dossiary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dossiary in Armenian (`hy`, Հայերեն): all interface strings, Armenian dates, auto-detection, Armenian OCR and OCR suggestions, Armenian CSV export — reviewed by an Armenian speaker on a review page before release. Sub-project 1 of `docs/superpowers/specs/2026-10-17-armenian-design.md`.

**Architecture:** A seventh `STRINGS` block generated from `STRINGS.en` (values translated, keys and `{placeholders}` identical), plus the per-language tables (`SUPPORTED_LANGS`, `NATIVE_LANG_NAMES`, `LANG_AUTODETECT`, `DATE_LOCALE`). OCR gains `hye`, Armenian month/total words, the dram, and month-name date patterns that accept any script. A review page (claude.ai artifact with a shared database) collects corrections; a final task applies them and releases.

**Tech Stack:** `dossiary.html` (vanilla JS), Node (to read `STRINGS` exactly), Playwright tests, claude.ai Artifact with the `db` capability.

## Global Constraints

- Language code `hy`; native name `Հայերեն`; date locale `hy-AM`; it goes after `zh-Hant` in `SUPPORTED_LANGS`.
- `STRINGS.hy` has exactly the keys of `STRINGS.en`, every value keeps exactly the `{placeholders}` of the English value, and strings are written as double-quoted JSON strings (one key per line) so no escaping can break the file.
- Brand and protocol words stay as they are: Dossiary, scanix500, iX500, ScanSnap, PDF, OCR as a code (`hye`), CSV, `index.csv`, file paths, `inbox/`, keyboard keys.
- New key `ocrLangArmenian` in all seven languages: en "Armenian", de "Armenisch", es "Armenio", fr "Arménien", zh-Hans "亚美尼亚语", zh-Hant "亞美尼亞語", hy "Հայերեն".
- Release only after the reviewer's corrections are applied (Task 5).
- Run browser tests from `tests/` with `python3 <file>`; a check passes when it prints `True`.

---

### Task 1: Placeholder check in the coverage test

**Files:** Modify `tests/test_i18n_coverage.py`.

- [ ] **Step 1: Add the check** — before the final `print("PASS")`:

```python
# Every translation must keep exactly the {placeholders} of the English text:
# a dropped {count} would otherwise only show up as a wrong message at runtime.
value_re = re.compile(r'''(?:^|[{,])\s*(\w+):\s*(['"])((?:\\.|(?!\2).)*)\2''', re.MULTILINE)
placeholder_re = re.compile(r'\{(\w+)\}')
lang_values = {}
for m in lang_block_re.finditer(strings_body):
    code = m.group(1) or m.group(2)
    lang_values[code] = {k: set(placeholder_re.findall(v)) for k, _, v in value_re.findall(m.group(3))}
placeholder_problems = []
for code, values in sorted(lang_values.items()):
    if code == 'en':
        continue
    for key, english in lang_values['en'].items():
        if key in values and values[key] != english:
            placeholder_problems.append(f"STRINGS.{code}.{key}: {sorted(values[key])} vs English {sorted(english)}")
for problem in placeholder_problems:
    print("Placeholder mismatch:", problem)
assert not placeholder_problems, f"{len(placeholder_problems)} translation(s) don't keep the English placeholders"
```

- [ ] **Step 2: Run** — `cd tests && python3 test_i18n_coverage.py`. Expected `PASS`. If it reports mismatches in the existing six languages, fix those translations (a real bug the check found), then rerun.

- [ ] **Step 3: Commit** — `git add tests/test_i18n_coverage.py dossiary.html && git commit -m "i18n coverage: translations must keep the English {placeholders}"`

---

### Task 2: Armenian language and strings

**Files:** Modify `dossiary.html` (language tables ~line 1099-1121, `STRINGS` end ~line 2575, `ocrLanguageOptionsHtml()`), `tests/test_i18n.py`, `README.md`, `README.de.md`, `CLAUDE.md`.

**Interfaces:**
- Produces: `STRINGS.hy`; `ocrLangArmenian` in every block; `hye` among the OCR options.

- [ ] **Step 1: Extract the English strings** (scratch, not committed):

```bash
node -e '
const html = require("fs").readFileSync("dossiary.html", "utf8");
const start = html.indexOf("const STRINGS = ") + "const STRINGS = ".length;
const end = html.indexOf("\n  };", start) + 4;
const STRINGS = (0, eval)("(" + html.slice(start, end) + ")");
require("fs").writeFileSync(process.argv[1], JSON.stringify(STRINGS.en, null, 1));
console.log(Object.keys(STRINGS.en).length, "English strings");
' "$SCRATCH/en.json"
```

- [ ] **Step 2: Translate** — write `$SCRATCH/hy.json`, the same object with every value in Armenian (Eastern Armenian, the standard of the Republic of Armenia; the formal "Դուք" when addressing the person; otherwise follow the English tone). Work in batches of ~100 keys. Keep `{placeholders}`, emoji prefixes (📷, 🛠 …), punctuation like "…" and "→", brand names and file paths exactly. Then check:

```bash
node -e '
const en = require(process.argv[1]), hy = require(process.argv[2]);
const ph = s => (s.match(/\{\w+\}/g) || []).sort().join();
const missing = Object.keys(en).filter(k => !(k in hy)), extra = Object.keys(hy).filter(k => !(k in en));
const bad = Object.keys(en).filter(k => k in hy && ph(en[k]) !== ph(hy[k]));
const same = Object.keys(en).filter(k => hy[k] === en[k] && /[a-z]{4}/i.test(en[k]));
console.log({missing, extra, placeholderMismatch: bad, untranslatedLooking: same.length});
' "$SCRATCH/en.json" "$SCRATCH/hy.json"
```

Expected: `missing`, `extra`, `placeholderMismatch` empty; `untranslatedLooking` only brand/technical strings (inspect the list).

- [ ] **Step 3: Insert the block** — generate it and insert it after the `'zh-Hant'` block's closing `    },` (the line before `  };`):

```bash
node -e '
const fs = require("fs");
const hy = require(process.argv[1]);
const body = Object.entries(hy).map(([k, v]) => `      ${k}: ${JSON.stringify(v)},`).join("\n");
const block = `    hy: {\n${body}\n    },\n`;
let html = fs.readFileSync("dossiary.html", "utf8");
const end = html.indexOf("\n  };", html.indexOf("const STRINGS = "));
html = html.slice(0, end + 1) + block + html.slice(end + 1);
fs.writeFileSync("dossiary.html", html);
' "$SCRATCH/hy.json"
```

- [ ] **Step 4: Language tables** — in `dossiary.html`:

```js
  const SUPPORTED_LANGS = ['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']; // grows by one entry per new-language task
  const NATIVE_LANG_NAMES = { en: 'English', de: 'Deutsch', es: 'Español', fr: 'Français', 'zh-Hans': '简体中文', 'zh-Hant': '繁體中文', hy: 'Հայերեն' }; // …(keep the comment)
```

`LANG_AUTODETECT` gains, after the `fr` rule: `{ code: 'hy', test: l => l === 'hy' || l.startsWith('hy-') },`; `DATE_LOCALE` gains `hy: 'hy-AM'`.

- [ ] **Step 5: OCR language** — `ocrLanguageOptionsHtml()`'s list gains `['hye', 'ocrLangArmenian']` after `['chi_tra', 'ocrLangChineseTraditional']`. Add `ocrLangArmenian` to every `STRINGS` block right after its `ocrLangChineseTraditional` entry, with the values from Global Constraints (in `hy.json` too, so Step 3's block has it — or add it to the block by hand).

- [ ] **Step 6: Tests** — in `tests/test_i18n.py` Scenario 28, the expected codes become `['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']` and the message says "seven"; also assert `'Հայերեն' in lang_option_labels_28`. Add a scenario at the end of `main()` (copy Scenario 28's page setup, which sets `navigator.languages` by init script):

```python
        # === Scenario 30: Armenian ===
        page30 = await browser.new_page()
        await page30.add_init_script("Object.defineProperty(navigator, 'languages', { get: () => ['hy-AM', 'en'] }); Object.defineProperty(navigator, 'language', { get: () => 'hy-AM' });")
        await page30.add_init_script(stub_js)
        await page30.goto(f"file://{APP_PATH}")
        await page30.wait_for_timeout(200)
        print("Scenario 30 -- an Armenian browser starts in Armenian:", await page30.locator('#lang-select').input_value() == 'hy')
        title_hy = await page30.locator('#empty-state h2').inner_text()
        print("Scenario 30 -- the start screen is in Armenian script:", any('Ա' <= c <= '֏' for c in title_hy), title_hy)
        await page30.select_option('#lang-select', 'en')
        await page30.wait_for_timeout(150)
        print("Scenario 30 -- switching back to English works:", await page30.locator('#empty-state h2').inner_text() == "No library open")
        await page30.close()
```

(Use the variable the file already uses for the stub source; if it isn't `stub_js`, use that name.)

- [ ] **Step 7: Run** — `cd tests && python3 test_i18n_coverage.py && python3 test_i18n.py | grep -E "False|Traceback|ERRORS"` → coverage `PASS`, no `False`, `JS ERRORS: []`.

- [ ] **Step 8: Docs** — where `README.md`, `README.de.md` and `CLAUDE.md` name the six UI languages or "six languages", add Armenian / "seven"; `CLAUDE.md`'s `STRINGS` key count stays as the coverage test prints it.

- [ ] **Step 9: Commit** — `git add dossiary.html tests/test_i18n.py README.md README.de.md CLAUDE.md && git commit -m "Armenian (Հայերեն) interface: STRINGS.hy, auto-detection, hy-AM dates, Armenian OCR language"`

---

### Task 3: Armenian in OCR suggestions and CSV export

**Files:** Modify `dossiary.html` (`OCR_MONTHS`, `OCR_TOTAL_WORDS`, `OCR_CURRENCY_TOKENS`, `OCR_CURRENCY_SYMBOLS`, `suggestDateFromText()`, `suggestAmountFromText()`, `csvSeparator()`), `tests/test_ocr_suggestions.py`, `tests/test_export.py`.

- [ ] **Step 1: Failing tests** — append to `PARSER_CASES` in `test_ocr_suggestions.py`:

```python
    ("Armenian date, day month year", "Ամսաթիվ՝ 17 հոկտեմբերի 2026 թ.", {"date": "2026-10-17", "amount": None, "currency": None}),
    ("Armenian date, official order", "Երևան, 2026 թ. հոկտեմբերի 5", {"date": "2026-10-05", "amount": None, "currency": None}),
    ("Armenian total in dram", "Ապրանք 2000,00\nԸնդամենը 12500,00 ֏", {"date": None, "amount": "12500.00", "currency": "AMD"}),
    ("Armenian total with AMD", "Վճարման ենթակա գումար\n3450,50 AMD", {"date": None, "amount": "3450.50", "currency": "AMD"}),
```

In `test_export.py`, after the German scenario, add one that switches `#lang-select` to `hy`, exports again into a fresh folder (same steps as the German scenario) and prints `"Armenian uses ';':", lines[0].count(';') > 3`.

- [ ] **Step 2: Run** — `python3 test_ocr_suggestions.py | grep Armenian` → `False` for all four; `test_export.py` Armenian check `False`.

- [ ] **Step 3: Implement** — `OCR_MONTHS` gains:

```js
    'հունվար': 1, 'հունվարի': 1, 'փետրվար': 2, 'փետրվարի': 2, 'մարտ': 3, 'մարտի': 3,
    'ապրիլ': 4, 'ապրիլի': 4, 'մայիս': 5, 'մայիսի': 5, 'հունիս': 6, 'հունիսի': 6,
    'հուլիս': 7, 'հուլիսի': 7, 'օգոստոս': 8, 'օգոստոսի': 8, 'սեպտեմբեր': 9, 'սեպտեմբերի': 9,
    'հոկտեմբեր': 10, 'հոկտեմբերի': 10, 'նոյեմբեր': 11, 'նոյեմբերի': 11, 'դեկտեմբեր': 12, 'դեկտեմբերի': 12,
```

`OCR_TOTAL_WORDS` becomes:

```js
  const OCR_TOTAL_WORDS = /(gesamt|summe|total|endbetrag|rechnungsbetrag|zahlbetrag|zu zahlen|betrag|amount due|balance due|montant|importe|ընդամենը|ընդհանուր գումար|վճարման ենթակա|գումար)/i;
```

`OCR_CURRENCY_TOKENS` gains `'֏': 'AMD', 'AMD': 'AMD'`; `OCR_CURRENCY_SYMBOLS` gains `AMD: '֏'`.

In `suggestDateFromText()`, replace the two month-name loops with these three (JS `\b` only knows ASCII letters, so a letter start uses a lookbehind instead):

```js
    for(const m of text.matchAll(/\b(\d{1,2})\.?\s+(\p{L}{3,})\.?,?\s+(\d{4})\b/gu)){
      const month = OCR_MONTHS[m[2].toLowerCase()];
      if(month) add(m.index, ocrIsoDate(+m[3], month, +m[1]));
    }
    for(const m of text.matchAll(/(?<!\p{L})(\p{L}{3,})\.?\s+(\d{1,2}),?\s+(\d{4})\b/gu)){
      const month = OCR_MONTHS[m[1].toLowerCase()];
      if(month) add(m.index, ocrIsoDate(+m[3], month, +m[2]));
    }
    // Armenian official order: "2026 թ. հոկտեմբերի 17".
    for(const m of text.matchAll(/\b(\d{4})\s*թ\.?\s+(\p{L}{3,})\s+(\d{1,2})\b/gu)){
      const month = OCR_MONTHS[m[2].toLowerCase()];
      if(month) add(m.index, ocrIsoDate(+m[1], month, +m[3]));
    }
```

In `suggestAmountFromText()`, `moneyRe` and the currency fallback gain the dram:

```js
    const moneyRe = /(€|\$|£|֏|\bEUR\b|\bUSD\b|\bGBP\b|\bCHF\b|\bAMD\b)?\s?(\d{1,3}(?:[.,'\s]\d{3})*[.,]\d{2}|\d+[.,]\d{2})\b\s?(€|\$|£|֏|EUR\b|USD\b|GBP\b|CHF\b|AMD\b)?/g;
```

```js
      const m = text.match(/€|\bEUR\b|\$|\bUSD\b|£|\bGBP\b|\bCHF\b|֏|\bAMD\b/);
```

`csvSeparator()`: `['de', 'fr', 'es', 'hy'].includes(currentLang)`.

- [ ] **Step 4: Run** — `python3 test_ocr_suggestions.py` and `python3 test_export.py`: no `False`, `JS ERRORS: []`. The existing Latin month cases must still pass.

- [ ] **Step 5: Commit** — `git add dossiary.html tests/test_ocr_suggestions.py tests/test_export.py && git commit -m "Armenian OCR suggestions (month names, totals, dram) and ';' CSV export"`

---

### Task 4: Review page

**Files:** Create `$SCRATCH/armenian-review.html` (not in the repo).

- [ ] **Step 1:** Load the `artifact-capabilities` skill (the page needs the `db` capability) and follow it for the page code.
- [ ] **Step 2: Build the page** — data embedded in the page: every key with its English and Armenian (from the `STRINGS` blocks as they are after Task 3) plus a group "OCR words" (the Armenian month names and total words from Task 3). Per row: key (small), English, current Armenian, a correction box, a note box, a "reviewed" tick; correction, note and tick save to the database as one document per key (`{correction, note, reviewed}`) as they change. Filters: all / not reviewed / corrected; a count "N of M reviewed". `{placeholders}` highlighted in both texts; a warning on a row whose correction lacks a placeholder of the English. Written in English and Armenian (headings in both), since the reviewer reads Armenian.
- [ ] **Step 3: Publish** and check once (one row edit saved and read back through `ArtifactData`, then deleted). Give the user the link and tell them to share it with the reviewer (edit access).

---

### Task 5: Apply the review, release

Only when the user says the review is done.

- [ ] **Step 1:** Read every document from the review page's database (`ArtifactData` list), list what changed (key, old → new, note), and apply each non-empty correction to `STRINGS.hy` (and the OCR word lists in Task 3's code) with the Step 3 generator or by hand.
- [ ] **Step 2:** `python3 test_i18n_coverage.py` (placeholders!), `test_i18n.py`, `test_ocr_suggestions.py`, then the full suite.
- [ ] **Step 3:** Commit, merge locally, bump `APP_VERSION`/`scan_watch.py`/`tests/test_scan_watch_version.py` (minor), release with the user's OK, copy to `/Applications/Dossiary/dossiary.html`.
