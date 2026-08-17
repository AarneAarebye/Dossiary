# Additional UI Languages (ES/FR/ZH-Hans/ZH-Hant) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Dossiary's in-app UI language toggle from English/German to
six languages (adding Spanish, French, Chinese Simplified, Chinese
Traditional), plus a `USER_GUIDE.<lang>.md` for each new language.

**Architecture:** Generalize the existing binary `'en'|'de'` mechanism
(`STRINGS`, `t()`, `applyI18n()`, `loadLang()`/`saveLang()`, `setLang()`)
to be driven by a `SUPPORTED_LANGS` array instead of hardcoded language
checks, replace the two-state footer button with a `<select>` dropdown,
then add each new language's `STRINGS` block, auto-detect rule, and
date-locale entry as its own task. Chinese Traditional is derived from
Chinese Simplified via OpenCC conversion rather than translated
independently (same language, different script).

**Tech Stack:** Plain JS (no new runtime dependency — `dossiary.html`
stays a single file), Python + Playwright for tests (existing
convention), `opencc-python-reimplemented` (a one-time, dev-only
conversion tool run locally to produce the committed `zh-Hant` text —
never loaded by the app itself).

## Global Constraints

- No new runtime dependency in `dossiary.html` — it stays one file, no
  build step. `opencc-python-reimplemented` is a one-time authoring tool,
  never referenced by the app.
- UI language and OCR language (`#ocr-lang`/`#e-ocr-lang`) stay
  completely independent settings — this project does not couple them,
  despite the six-language lists now matching by coincidence of scope.
- One Spanish, one French — no regional variants (matches how English
  and German are each a single variant today).
- Chinese Traditional's `STRINGS['zh-Hant']` and `USER_GUIDE.zh-Hant.md`
  are derived from the finished Simplified versions via OpenCC `s2t`
  conversion, not translated independently — this keeps the two
  guaranteed in lockstep rather than risking drift between two
  independent translations of the same underlying language.
- Chinese does not inflect for grammatical number — every existing
  `...Singular`/`...Plural` key pair gets **identical text** in both
  slots for `zh-Hans`/`zh-Hant`, not a new no-plural mechanism.
- `tests/test_i18n_coverage.py` must pass for every language in
  `SUPPORTED_LANGS` at the end of every task that touches it.
- `SUPPORTED_LANGS` only ever grows by one entry per task, in the same
  commit as that language's `STRINGS` block — the app must never be in a
  state where a language is listed in the dropdown but has an incomplete
  or missing `STRINGS` block.

---

## Task 1: Generalize the language mechanism to N languages; dropdown replaces the two-state button

**Files:**
- Modify: `dossiary.html` (CSS ~line 420-421, footer markup ~line 624,
  `STRINGS`/`t()`/`applyI18n()` block ~line 655-1076, `formatDate()`
  ~line 2778-2783, static-wiring block ~line 1680-1702)
- Modify: `tests/test_i18n_coverage.py` (full rewrite of the
  language-block extraction logic)
- Modify: `tests/test_i18n.py` (every `#lang-toggle` interaction site —
  see Step 5 below for the complete list)

**Interfaces:**
- Consumes: nothing new — this generalizes existing infrastructure.
- Produces: `SUPPORTED_LANGS` (array of language codes, currently
  `['en', 'de']`), `NATIVE_LANG_NAMES` (object, code → that language's own
  name for itself, e.g. `{en: 'English', de: 'Deutsch'}`), `LANG_AUTODETECT`
  (array of `{code, test}` objects used by `loadLang()`), `DATE_LOCALE`
  (object, code → `toLocaleDateString` locale string). Every later task
  (2-5) adds exactly one entry to each of these four.

This task changes **nothing user-visible about which languages are
offered** (still just English/German) — it's a pure mechanism swap so
Tasks 2-5 can each add one language as a small, self-contained diff.

- [ ] **Step 1: Replace the footer's two-state button with a dropdown**

In the footer markup (~line 624), replace:

```html
    <button type="button" id="lang-toggle" data-i18n-title="langToggleTitle"></button> ·
```

with:

```html
    <select id="lang-select" data-i18n-title="langToggleTitle"></select> ·
```

In the CSS block (~line 420-421), replace:

```css
  #lang-toggle{ font-family:var(--font-mono); font-size:11px; padding:2px 6px; border:1px solid var(--line); border-radius:var(--radius); background:transparent; color:var(--text-dim); cursor:pointer; }
  #lang-toggle:hover{ color:var(--phosphor); border-color:var(--phosphor-dim); }
```

with:

```css
  #lang-select{ font-family:var(--font-mono); font-size:11px; padding:2px 6px; border:1px solid var(--line); border-radius:var(--radius); background:transparent; color:var(--text-dim); cursor:pointer; color-scheme:dark; }
  #lang-select:hover{ color:var(--phosphor); border-color:var(--phosphor-dim); }
```

(`color-scheme:dark` here is the same fix already applied to
`input[type=date]` elsewhere in this file — without it, the dropdown's
own options popup renders with light-mode browser chrome against this
app's dark background. Scoped to this one selector, not page-wide, for
the same reasoning that existing note gives.)

- [ ] **Step 2: Generalize `STRINGS`/`t()`/`loadLang()`/`saveLang()`/`formatDate()`**

Just above the `STRINGS` declaration (~line 655), add:

```js
  const SUPPORTED_LANGS = ['en', 'de']; // grows by one entry per new-language task
  const NATIVE_LANG_NAMES = { en: 'English', de: 'Deutsch' }; // each language's own name for itself -- shown in the dropdown regardless of currentLang, so these are never run through t()
  // Auto-detect rules, checked in order, first match wins. Each new
  // SUPPORTED_LANGS entry's own task adds one entry here.
  const LANG_AUTODETECT = [
    { code: 'de', test: l => l.startsWith('de') },
  ];
  const DATE_LOCALE = { en: 'en-US', de: 'de-DE' }; // grows alongside SUPPORTED_LANGS
```

Replace `loadLang()` (~line 1002-1008) — keep the existing localStorage
try/catch exactly as-is, only generalize the stored-value check and the
detection loop:

```js
  function loadLang(){
    let stored = null;
    try{ stored = localStorage.getItem('dossiary_lang'); }catch(e){ stored = null; }
    if(SUPPORTED_LANGS.includes(stored)) return stored;
    const langs = (navigator.languages || [navigator.language || '']).map(l => l.toLowerCase());
    for(const {code, test} of LANG_AUTODETECT){
      if(langs.some(test)) return code;
    }
    return 'en';
  }
```

`saveLang()` (~line 1009) is unchanged — it already just stores whatever
string it's given.

`t()` (~line 976-982) is unchanged — `STRINGS[currentLang][key] ??
STRINGS.en[key] ?? key` was already written generically.

Replace `formatDate()`'s locale expression (~line 2782):

```js
    // was: return d.toLocaleDateString(currentLang === 'de' ? 'de-DE' : 'en-US', { year:'numeric', month:'short', day:'2-digit' });
    return d.toLocaleDateString(DATE_LOCALE[currentLang] || 'en-US', { year:'numeric', month:'short', day:'2-digit' });
```

- [ ] **Step 3: Replace the toggle's click handler with the dropdown's change handler**

Replace the static-wiring block (~line 1684-1699):

```js
  el('lang-toggle').textContent = currentLang === 'de' ? 'EN' : 'DE'; // shows the language you'd SWITCH TO
  el('lang-toggle').addEventListener('click', () => {
    // ...(existing comment block)...
    if(modalRoot.innerHTML !== '') return;
    setLang(currentLang === 'de' ? 'en' : 'de');
    el('lang-toggle').textContent = currentLang === 'de' ? 'EN' : 'DE';
  });
```

with:

```js
  function populateLangSelect(){
    const sel = el('lang-select');
    sel.innerHTML = SUPPORTED_LANGS.map(l => `<option value="${l}">${NATIVE_LANG_NAMES[l]}</option>`).join('');
    sel.value = currentLang;
  }
  populateLangSelect();
  el('lang-select').addEventListener('change', (e) => {
    // A mouse click on the old button was already blocked by a modal's own backdrop
    // while one was open, but keyboard Tab-through could still reach and activate it.
    // A native <select> is a stricter case than the old button: picking an option
    // changes the control's own displayed value immediately, keyboard or mouse, with
    // no backdrop able to intercept that the way it blocks a button click -- so this
    // guard must actively RESET the select's value, not just skip acting on it, or
    // the dropdown would visually show a language the app never actually switched to.
    // Re-rendering the open modal in place instead isn't safe in general -- capture/edit
    // would lose whatever's already been typed into the form, the exact same in-progress-
    // work hazard applyDynamicFieldsForType()'s own note documents for switching document
    // types mid-edit. modalRoot.innerHTML is '' exactly when no modal is open (see
    // closeModal()); this reads the same signal the old button's guard used.
    if(modalRoot.innerHTML !== ''){
      e.target.value = currentLang;
      return;
    }
    setLang(e.target.value);
  });
```

Native option names are never translated (`NATIVE_LANG_NAMES` values are
each language's own name for itself, shown as-is regardless of
`currentLang`), so `populateLangSelect()` only needs to run once at
init — it's not part of `setLang()`'s reactive chain.

- [ ] **Step 4: Generalize `tests/test_i18n_coverage.py`**

Replace the whole file's language-extraction section (from the
`strings_match`/`en_match`/`de_match` block through the two `assert`
statements at the end) with:

```python
import os, re, json, subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.abspath(os.path.join('..', 'dossiary.html'))
html = open(APP_PATH, encoding='utf-8').read()

strings_match = re.search(r'const STRINGS = \{(.*?)\n  \};', html, re.DOTALL)
assert strings_match, "Could not locate STRINGS object in dossiary.html"
strings_body = strings_match.group(1)

# Extract every top-level language block. Language keys are either bare
# identifiers (en, de, es, fr) or quoted (required for a key containing a
# hyphen, e.g. 'zh-Hans') -- STRINGS only ever nests one level deep
# (language -> flat key:value pairs), so a top-level block ends at the
# first top-level "},\n" back at the STRINGS object's own 4-space
# indentation.
lang_block_re = re.compile(
    r"""(?:^|\n)\s{4}(?:(\w[\w-]*)|'([\w-]+)'):\s*\{(.*?)\n\s{4}\},""",
    re.DOTALL,
)
key_re = re.compile(r'''(?:^|[{,])\s*(\w+):\s*['"]''', re.MULTILINE)

lang_keys = {}
for m in lang_block_re.finditer(strings_body):
    lang_code = m.group(1) or m.group(2)
    lang_keys[lang_code] = set(key_re.findall(m.group(3)))

print(f"Found {len(lang_keys)} language block(s): {sorted(lang_keys)}")
for lang_code, keys in sorted(lang_keys.items()):
    print(f"  STRINGS.{lang_code} has {len(keys)} keys")
assert 'en' in lang_keys and 'de' in lang_keys, "Expected at least 'en' and 'de' language blocks"

# Every referenced key -- from data-i18n*="key" attributes and t('key'...)/t("key"...) calls.
attr_keys = set(re.findall(r'data-i18n(?:-placeholder|-title|-aria-label)?="([a-zA-Z0-9]+)"', html))
call_keys = set(re.findall(r"""\bt\(\s*['"]([a-zA-Z0-9]+)['"]""", html))
referenced_keys = attr_keys | call_keys

any_missing = False
for lang_code, keys in sorted(lang_keys.items()):
    missing = referenced_keys - keys
    if missing:
        any_missing = True
        print(f"Keys referenced in markup/code but missing from STRINGS.{lang_code}:", sorted(missing))
assert not any_missing, "one or more languages have keys referenced in code but missing from their STRINGS block"

# Every language's key SET should match English's exactly -- catches a
# typo'd key name in a translated block (e.g. STRINGS.es defining
# "commmonCancel" instead of "commonCancel") that the referenced-keys
# check above wouldn't catch on its own, since t('commonCancel') would
# just silently fall back to English rather than reporting "missing".
en_keys = lang_keys['en']
any_keyset_mismatch = False
for lang_code, keys in sorted(lang_keys.items()):
    if lang_code == 'en':
        continue
    extra = keys - en_keys
    missing_vs_en = en_keys - keys
    if extra or missing_vs_en:
        any_keyset_mismatch = True
        print(f"STRINGS.{lang_code} key set differs from STRINGS.en -- extra: {sorted(extra)}, missing: {sorted(missing_vs_en)}")
assert not any_keyset_mismatch, "one or more languages have a key set that doesn't exactly match STRINGS.en"

unused_en_only = en_keys - referenced_keys
print("Keys defined in STRINGS.en but never referenced (informational only):", sorted(unused_en_only))
print("PASS")
```

- [ ] **Step 5: Run it to verify it still passes against the current 2-language file**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `Found 2 language block(s): ['de', 'en']`, then `PASS`.

- [ ] **Step 6: Update every `#lang-toggle` interaction in `tests/test_i18n.py`**

Locate each occurrence by searching for `#lang-toggle` — there are 9
`.click()` call sites and 3 `.inner_text()` label-reads (all 3 inside one
scenario, rewritten together in the block below). Apply each change
exactly as given; do not guess a target language for any of them, they
are all resolved here:

**Scenario 3** (switches German → English) — locate the `#lang-toggle`
click immediately before `title_after_toggle = ...`:
```python
# was: await page2.click('#lang-toggle')
await page2.select_option('#lang-select', 'en')
```

**Scenario 4** (switches back English → German) — locate the
`#lang-toggle` click immediately before the `SEED = {...}` dict:
```python
# was: await page2.click('#lang-toggle')
await page2.select_option('#lang-select', 'de')
```

**Scenario 5** (initial toggle to German) — locate the `#lang-toggle`
click immediately after `await page3.click("#open-btn")` /
`wait_for_timeout(300)`, before `nav_all_text = ...`:
```python
# was: await page3.click('#lang-toggle')
await page3.select_option('#lang-select', 'de')
```

**Scenario 7** (English → German) — locate the `#lang-toggle` click
immediately before `recent_heading_after = ...`:
```python
# was: await page5.click('#lang-toggle')
await page5.select_option('#lang-select', 'de')
```

**Scenario 18** (German → English) — locate the `#lang-toggle` click
immediately before `nav_all_text_toggled = ...`:
```python
# was: await page6.click('#lang-toggle')
await page6.select_option('#lang-select', 'en')
```

**Scenario 21** — replace the entire block from `await page3.click('#add-btn')`
through the line right before `# === Scenario 22` with:

```python
        await page3.click('#add-btn')
        await page3.wait_for_timeout(200)
        lang_value_before_guard = await page3.locator('#lang-select').input_value()
        modal_heading_before_guard = await page3.locator('.modal h2').inner_text()
        # A plain select_option() call is itself already blocked by nothing -- unlike
        # the old button, a native <select> has no backdrop that can intercept a pointer
        # event on it, so this exercises the "activated while a modal is open" case
        # directly via force=True (skips Playwright's own actionability checks), the
        # same case the button's own guard was built for. The change handler's guard
        # (dossiary.html) must reset the select's value back to currentLang, not just
        # skip acting on it, or the dropdown would visually show a language the app
        # never actually switched to.
        await page3.select_option('#lang-select', 'en', force=True)
        await page3.wait_for_timeout(150)
        lang_value_after_guard = await page3.locator('#lang-select').input_value()
        modal_heading_after_guard = await page3.locator('.modal h2').inner_text()
        print("Scenario 21 -- lang-select change while a modal is open is a no-op (value reverted):", lang_value_before_guard == lang_value_after_guard == "de")
        print("Scenario 21 -- the open modal's own language is untouched by the blocked toggle:", modal_heading_before_guard == modal_heading_after_guard == "Dokument hinzufügen")
        await page3.click('#cancel-doc-btn')
        await page3.wait_for_timeout(150)
        # Once the modal is closed, the dropdown works normally again -- confirming
        # this is a scoped-to-open-modal guard, not a general regression in the control.
        await page3.select_option('#lang-select', 'en')
        await page3.wait_for_timeout(150)
        lang_value_after_close = await page3.locator('#lang-select').input_value()
        print("Scenario 21 -- lang-select works again once the modal is closed:", lang_value_after_close == "en")
        # Switch back to German so the reused-page3 scenarios below see what they expect.
        await page3.select_option('#lang-select', 'de')
        await page3.wait_for_timeout(150)

```

**Scenario 23** (German → English, final toggle) — locate the
`#lang-toggle` click immediately before `user_guide_href_en = ...`:
```python
# was: await page3.click('#lang-toggle')
await page3.select_option('#lang-select', 'en')
```

- [ ] **Step 7: Run the full test to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: all 23 scenarios print `True`, `JS ERRORS: []`.

- [ ] **Step 8: Run the full baseline suite**

Run: `cd tests && python3 -c "
import subprocess, glob
failed = []
files = sorted(glob.glob('test_*.py'))
for f in files:
    p = subprocess.run(['python3', f], capture_output=True, text=True, timeout=180)
    if p.returncode != 0 or 'Traceback' in p.stdout or 'Traceback' in p.stderr:
        failed.append(f)
        print(f'FAILED: {f}')
print(f'TOTAL: {len(files)}  FAILED: {failed}')
"`
Expected: `TOTAL: 57  FAILED: []` (this task modifies existing test files,
it doesn't add a new one).

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_i18n_coverage.py tests/test_i18n.py
git commit -m "Generalize the language mechanism to N languages; dropdown replaces the two-state toggle"
```

---

## Task 2: Add Spanish (`es`)

**Files:**
- Modify: `dossiary.html` (`STRINGS` object, `SUPPORTED_LANGS`,
  `NATIVE_LANG_NAMES`, `LANG_AUTODETECT`, `DATE_LOCALE` — all defined in
  Task 1)
- Modify: `tests/test_i18n.py` (append one new scenario)

**Interfaces:**
- Consumes: `SUPPORTED_LANGS`/`NATIVE_LANG_NAMES`/`LANG_AUTODETECT`/
  `DATE_LOCALE` (Task 1)
- Produces: `STRINGS.es` (full translation of every key in `STRINGS.en`)

- [ ] **Step 1: Translate every key**

Read `STRINGS.en` directly from `dossiary.html` (don't rely on a copy
elsewhere — it's the live source of truth and this plan doesn't
reproduce all 272 keys). Add a new `es: { ... }` block to the `STRINGS`
object (place it directly after the `de` block, before the closing
`};`), containing a natural, idiomatic Spanish translation of **every**
key `STRINGS.en` defines — same key names, same `{param}` interpolation
tokens left untouched (e.g. `{count}`, `{name}`, `{folder}`, `{id}`,
`{title}`, `{error}`), same singular/plural key-pair structure (every
`...Singular`/`...Plural` pair gets its own grammatically correct Spanish
singular and plural form — Spanish pluralizes similarly to English/German,
so this is a real two-form translation, not a Chinese-style identical-text
case).

Two worked examples for calibration (exact key names, your own Spanish
wording for the rest is expected to differ from these — these just show
the interpolation/pluralization conventions to follow):

```js
      commonCancel: 'Cancelar', commonSave: 'Guardar', commonDone: 'Hecho', commonDelete: 'Eliminar',
      // ...
      emptyTitle: 'Ninguna biblioteca abierta',
      // ...
      sharedPageCountSingular: '{count} página', sharedPageCountPlural: '{count} páginas',
```

- [ ] **Step 2: Wire up the four registries in Task 1's infrastructure**

`SUPPORTED_LANGS`:
```js
  const SUPPORTED_LANGS = ['en', 'de', 'es'];
```

`NATIVE_LANG_NAMES`:
```js
  const NATIVE_LANG_NAMES = { en: 'English', de: 'Deutsch', es: 'Español' };
```

`LANG_AUTODETECT` (append, after the existing `de` entry):
```js
    { code: 'es', test: l => l.startsWith('es') },
```

`DATE_LOCALE`:
```js
  const DATE_LOCALE = { en: 'en-US', de: 'de-DE', es: 'es-ES' };
```

- [ ] **Step 3: Run the coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `Found 3 language block(s): ['de', 'en', 'es']`, then `PASS`
(this fails loudly with the specific missing/extra keys if any key was
skipped or a key name was typo'd — fix and re-run until it passes).

- [ ] **Step 4: Add a Playwright scenario**

Append to `tests/test_i18n.py`, immediately before `print("JS ERRORS:",
errors)`:

```python
        # === Scenario 24: Spanish auto-detects and translates (new page,
        # es-ES browser locale, no stored preference yet) ===
        page_es = await browser.new_page()
        await page_es.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'es-ES' });
            Object.defineProperty(navigator, 'languages', { get: () => ['es-ES', 'es'] });
        """)
        await page_es.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page_es.add_init_script(stub_js)
        await page_es.goto(f"file://{APP_PATH}")
        await page_es.wait_for_timeout(200)
        es_title = await page_es.locator('#empty-state h2').inner_text()
        print("Scenario 24 -- es-ES browser locale auto-detects Spanish:", es_title == "Ninguna biblioteca abierta")
        es_lang_value = await page_es.locator('#lang-select').input_value()
        print("Scenario 24 -- dropdown shows 'es' as the selected value:", es_lang_value == "es")
        await page_es.close()
```

Use the exact `emptyTitle` Spanish translation you wrote in Step 1 for
the `es_title ==` comparison (the value above is only correct if your
translation matches it verbatim — update this assertion to match your
own wording if it differs).

- [ ] **Step 5: Run it to verify it passes**

Run: `cd tests && python3 test_i18n.py`
Expected: all scenarios including the new one print `True`.

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Add Spanish as a UI language"
```

---

## Task 3: Add French (`fr`)

**Files:** same as Task 2, French instead of Spanish.

**Interfaces:**
- Consumes: `SUPPORTED_LANGS`/etc. (Task 1), same pattern Task 2 used to
  add its language.
- Produces: `STRINGS.fr`

- [ ] **Step 1: Translate every key into French**, following the exact
same process as Task 2 Step 1 (read `STRINGS.en` directly from the file,
translate every key, preserve interpolation tokens and singular/plural
pairs — French also pluralizes similarly to English, real two-form
translation). Add the `fr: { ... }` block after `es`.

- [ ] **Step 2: Wire up the four registries**

```js
  const SUPPORTED_LANGS = ['en', 'de', 'es', 'fr'];
  const NATIVE_LANG_NAMES = { en: 'English', de: 'Deutsch', es: 'Español', fr: 'Français' };
```

`LANG_AUTODETECT` (append after `es`):
```js
    { code: 'fr', test: l => l.startsWith('fr') },
```

```js
  const DATE_LOCALE = { en: 'en-US', de: 'de-DE', es: 'es-ES', fr: 'fr-FR' };
```

- [ ] **Step 3: Run the coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `Found 4 language block(s): ['de', 'en', 'es', 'fr']`, then `PASS`.

- [ ] **Step 4: Add a Playwright scenario**

Same shape as Task 2 Step 4 — append before `print("JS ERRORS:", errors)`:

```python
        # === Scenario 25: French auto-detects and translates ===
        page_fr = await browser.new_page()
        await page_fr.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'fr-FR' });
            Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr'] });
        """)
        await page_fr.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page_fr.add_init_script(stub_js)
        await page_fr.goto(f"file://{APP_PATH}")
        await page_fr.wait_for_timeout(200)
        fr_title = await page_fr.locator('#empty-state h2').inner_text()
        print("Scenario 25 -- fr-FR browser locale auto-detects French:", fr_title == "Aucune bibliothèque ouverte")
        fr_lang_value = await page_fr.locator('#lang-select').input_value()
        print("Scenario 25 -- dropdown shows 'fr' as the selected value:", fr_lang_value == "fr")
        await page_fr.close()
```

Use `'Aucune bibliothèque ouverte'` as your own `emptyTitle` translation
in Step 1 for this key specifically, so the assertion above matches
exactly — the rest of the ~272 keys are yours to translate freely.

- [ ] **Step 5: Run it to verify it passes**

Run: `cd tests && python3 test_i18n.py`

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Add French as a UI language"
```

---

## Task 4: Add Chinese Simplified (`zh-Hans`)

**Files:** same shape as Tasks 2-3.

**Interfaces:**
- Consumes: `SUPPORTED_LANGS`/etc. (Task 1)
- Produces: `STRINGS['zh-Hans']` — this is what Task 5 derives
  `STRINGS['zh-Hant']` from, so it must be complete and correct before
  Task 5 starts.

- [ ] **Step 1: Translate every key into Simplified Chinese**

Same process as Tasks 2-3, with one difference: Chinese does not inflect
for grammatical number, so **every `...Singular`/`...Plural` key pair
gets identical text in both slots** — do not invent a plural form that
doesn't exist in Chinese. Worked example:

```js
      sharedPageCountSingular: '{count} 页', sharedPageCountPlural: '{count} 页',
```

Since the object key syntax requires quotes for a hyphenated key, add the
block as:

```js
    'zh-Hans': {
      commonCancel: '取消', commonSave: '保存', commonDone: '完成', commonDelete: '删除',
      // ...every other key, following STRINGS.en...
    },
```

Place it after `fr`, before the closing `};`.

- [ ] **Step 2: Wire up the four registries**

```js
  const SUPPORTED_LANGS = ['en', 'de', 'es', 'fr', 'zh-Hans'];
  const NATIVE_LANG_NAMES = { en: 'English', de: 'Deutsch', es: 'Español', fr: 'Français', 'zh-Hans': '简体中文' };
```

`LANG_AUTODETECT` (append after `fr` — note this entry also matches a
**bare** `zh` with no region/script, per the spec's "best guess, dismissible"
rule; it must be added before any `zh-Hant` entry, since first-match-wins
and Task 5 relies on this ordering):
```js
    { code: 'zh-Hans', test: l => l === 'zh' || l.startsWith('zh-cn') || l.startsWith('zh-sg') || l.startsWith('zh-my') || l.startsWith('zh-hans') },
```

```js
  const DATE_LOCALE = { en: 'en-US', de: 'de-DE', es: 'es-ES', fr: 'fr-FR', 'zh-Hans': 'zh-CN' };
```

- [ ] **Step 3: Run the coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `Found 5 language block(s): ['de', 'en', 'es', 'fr', 'zh-Hans']`,
then `PASS`.

- [ ] **Step 4: Add a Playwright scenario**

```python
        # === Scenario 26: Chinese Simplified auto-detects (zh-CN browser
        # locale) and a bare "zh" locale also defaults to Simplified ===
        page_zhs = await browser.new_page()
        await page_zhs.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'zh-CN' });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
        """)
        await page_zhs.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page_zhs.add_init_script(stub_js)
        await page_zhs.goto(f"file://{APP_PATH}")
        await page_zhs.wait_for_timeout(200)
        zhs_title = await page_zhs.locator('#empty-state h2').inner_text()
        print("Scenario 26 -- zh-CN browser locale auto-detects Chinese Simplified:", zhs_title == "未打开资料库")
        zhs_lang_value = await page_zhs.locator('#lang-select').input_value()
        print("Scenario 26 -- dropdown shows 'zh-Hans' as the selected value:", zhs_lang_value == "zh-Hans")
        await page_zhs.close()

        page_zh_bare = await browser.new_page()
        await page_zh_bare.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'zh' });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh'] });
        """)
        await page_zh_bare.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page_zh_bare.add_init_script(stub_js)
        await page_zh_bare.goto(f"file://{APP_PATH}")
        await page_zh_bare.wait_for_timeout(200)
        zh_bare_lang_value = await page_zh_bare.locator('#lang-select').input_value()
        print("Scenario 26 -- bare 'zh' locale (no region) defaults to Simplified:", zh_bare_lang_value == "zh-Hans")
        await page_zh_bare.close()
```

Use `'未打开资料库'` as your own `emptyTitle` translation in Step 1 for
this key specifically, so the assertion above matches exactly.

- [ ] **Step 5: Run it to verify it passes**

Run: `cd tests && python3 test_i18n.py`

- [ ] **Step 6: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Add Chinese (Simplified) as a UI language"
```

---

## Task 5: Add Chinese Traditional (`zh-Hant`), derived from Simplified via OpenCC

**Files:**
- Modify: `dossiary.html` (same registries as Tasks 2-4)
- Create (scratch, not committed): a one-off conversion script — write it
  wherever the plan's execution environment keeps scratch files, it is
  not part of the repo
- Modify: `tests/test_i18n.py`

**Interfaces:**
- Consumes: `STRINGS['zh-Hans']` (Task 4) — the source this task converts
  from. `SUPPORTED_LANGS`/etc. (Task 1).
- Produces: `STRINGS['zh-Hant']`

- [ ] **Step 1: Install the conversion tool**

Run: `pip3 install opencc-python-reimplemented`

- [ ] **Step 2: Extract `STRINGS['zh-Hans']`'s values and convert them**

Write a one-off Python script (in a scratch location, not committed) that:
1. Reads `dossiary.html`, locates the `'zh-Hans': { ... },` block exactly
   as Task 4 wrote it.
2. For each `key: 'value'` (or `key: "value"`) pair, runs the value
   through `opencc.OpenCC('s2t').convert(value)` — the `s2t` profile
   converts Simplified characters to Traditional while leaving
   interpolation tokens (`{count}`, `{name}`, etc., which contain no
   Chinese characters) untouched.
3. Prints a new `'zh-Hant': { ... },` block with the same key order and
   the converted values, ready to paste into `dossiary.html`.

Example of what one converted line looks like (for calibration — your
script generates all of them from Task 4's actual translations, not by
hand-transcribing this one line):

```python
import opencc
c = opencc.OpenCC('s2t')
print(c.convert('取消'))  # -> 取消 or 取消 (verify against your own Task 4 value; many common words are identical in both scripts)
```

- [ ] **Step 3: Paste the generated block into `dossiary.html`**

Add the printed `'zh-Hant': { ... },` block after `'zh-Hans'`, before the
closing `};`.

- [ ] **Step 4: Spot-check a handful of converted values by eye**

OpenCC's `s2t` profile is character-mapping, not phrase-aware regional
localization (it won't, for example, swap Mainland terminology for
Taiwan-preferred terminology for the same concept) — this is an accepted,
documented tradeoff (see the design spec's rationale), not a bug to fix
here. Spot-check 5-10 values render as valid Traditional characters (no
mangled/missing characters) rather than checking for regional-phrasing
"correctness."

- [ ] **Step 5: Wire up the four registries**

```js
  const SUPPORTED_LANGS = ['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant'];
  const NATIVE_LANG_NAMES = { en: 'English', de: 'Deutsch', es: 'Español', fr: 'Français', 'zh-Hans': '简体中文', 'zh-Hant': '繁體中文' };
```

`LANG_AUTODETECT` (append after `zh-Hans` — order matters, this must come
after `zh-Hans`'s entry since that entry's bare-`zh` fallback would
otherwise shadow it):
```js
    { code: 'zh-Hant', test: l => l.startsWith('zh-tw') || l.startsWith('zh-hk') || l.startsWith('zh-mo') || l.startsWith('zh-hant') },
```

```js
  const DATE_LOCALE = { en: 'en-US', de: 'de-DE', es: 'es-ES', fr: 'fr-FR', 'zh-Hans': 'zh-CN', 'zh-Hant': 'zh-TW' };
```

- [ ] **Step 6: Run the coverage check**

Run: `cd tests && python3 test_i18n_coverage.py`
Expected: `Found 6 language block(s): ['de', 'en', 'es', 'fr', 'zh-Hans', 'zh-Hant']`,
then `PASS`.

- [ ] **Step 7: Add a Playwright scenario**

```python
        # === Scenario 27: Chinese Traditional auto-detects (zh-TW browser
        # locale) -- and, since zh-Hans's own auto-detect rule matches bare
        # "zh" (Scenario 26), confirm zh-TW correctly picks Traditional
        # instead, proving the two rules don't shadow each other ===
        page_zht = await browser.new_page()
        await page_zht.add_init_script("""
            Object.defineProperty(navigator, 'language', { get: () => 'zh-TW' });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-TW', 'zh'] });
        """)
        await page_zht.route('**/*', lambda route: route.fulfill(body="/* stubbed */", content_type='application/javascript')
                          if any(s in route.request.url for s in ('sql-wasm.js', 'tesseract', 'jspdf', 'pdf.js'))
                          else route.continue_())
        await page_zht.add_init_script(stub_js)
        await page_zht.goto(f"file://{APP_PATH}")
        await page_zht.wait_for_timeout(200)
        zht_lang_value = await page_zht.locator('#lang-select').input_value()
        print("Scenario 27 -- zh-TW browser locale auto-detects Chinese Traditional (not Simplified):", zht_lang_value == "zh-Hant")
        await page_zht.close()
```

- [ ] **Step 8: Run it to verify it passes**

Run: `cd tests && python3 test_i18n.py`

- [ ] **Step 9: Commit**

```bash
git add dossiary.html tests/test_i18n.py
git commit -m "Add Chinese (Traditional) as a UI language, derived from Simplified via OpenCC"
```

---

## Task 6: `USER_GUIDE.es.md` with Spanish screenshots

**Files:**
- Create: `USER_GUIDE.es.md`
- Create: `docs/user-guide/es/*.png`
- Modify: `dossiary.html` (`USER_GUIDE_LANGS` array, ~line 1071)

**Interfaces:**
- Consumes: `USER_GUIDE.md` (existing English guide — structural
  template), `STRINGS.es` (Task 2 — the app must be fully Spanish-capable
  before this task's screenshots are captured), `USER_GUIDE_LANGS`
  (existing array, defined alongside the User Guide footer link)
- Produces: nothing later tasks depend on

- [ ] **Step 1: Write `USER_GUIDE.es.md`**

Same structure as `USER_GUIDE.md` (What is Dossiary? / Getting started /
Adding your first document / Finding it again / The everyday paper pile /
A quick tour of everything else / Where to go next), translated into
natural Spanish — not a section-for-section literal translation of the
English prose, a guide written to read naturally in Spanish covering the
same content. Add the language-switch links at the top matching the
existing `USER_GUIDE.de.md` pattern (`*[This guide in English](USER_GUIDE.md)*`
plus links to whichever other guides already exist at the time this task
runs).

- [ ] **Step 2: Capture screenshots**

Follow the exact process already established for `docs/user-guide/de/`
(documented in CLAUDE.md's "User Guide vs. README" section): a small
fabricated demo library (synthetic invoice/letter/receipt images, no real
personal data), the real app driven via browser automation over
`python3 -m http.server` (not `file://`, which the automation tooling
can't script), toggling the language dropdown to Spanish (`select_option`
to `'es'`, or the native picker if driving a real browser session
manually) before each capture. Save into `docs/user-guide/es/`, referenced
from `USER_GUIDE.es.md` via `docs/user-guide/es/<name>.png` relative
paths, matching the English/German guides' naming convention
(`01-no-library.png`, `02-...`, etc.).

- [ ] **Step 3: Add `es` to `USER_GUIDE_LANGS`**

In `dossiary.html` (~line 1071):

```js
  const USER_GUIDE_LANGS = ['de', 'es'];
```

- [ ] **Step 4: Verify every screenshot reference resolves**

Run:
```bash
cd /Users/aarneaarebye/Projects/Paperless/Dossiary
grep -oE '!\[[^]]*\]\([^)]+\)' USER_GUIDE.es.md | sed -E 's/.*\(([^)]+)\)/\1/' | while read -r p; do
  if [ -f "$p" ]; then echo "OK   $p"; else echo "MISSING $p"; fi
done
```
Expected: every line reads `OK`.

- [ ] **Step 5: Verify internal links resolve**

Run:
```bash
grep -oE '\]\(([A-Za-z_.]+\.md)\)' USER_GUIDE.es.md | sed -E 's/\]\(([^)]+)\)/\1/' | sort -u | while read -r p; do
  if [ -f "$p" ]; then echo "OK   $p"; else echo "MISSING $p"; fi
done
```

- [ ] **Step 6: Commit**

```bash
git add USER_GUIDE.es.md docs/user-guide/es/ dossiary.html
git commit -m "Add the Spanish User Guide"
```

---

## Task 7: `USER_GUIDE.fr.md` with French screenshots

Same shape as Task 6, French instead of Spanish, run after Task 3
(French UI translation must exist first). `USER_GUIDE_LANGS` becomes
`['de', 'es', 'fr']`. Screenshots go in `docs/user-guide/fr/`. Commit
message: `"Add the French User Guide"`.

---

## Task 8: `USER_GUIDE.zh-Hans.md` with Chinese Simplified screenshots

Same shape as Task 6, Simplified Chinese instead of Spanish, run after
Task 4. `USER_GUIDE_LANGS` becomes `['de', 'es', 'fr', 'zh-Hans']`.
Screenshots go in `docs/user-guide/zh-Hans/`. File name is
`USER_GUIDE.zh-Hans.md` (matches the `STRINGS['zh-Hans']` key naming —
the app's `userGuideUrl()` function already builds this from
`currentLang` directly, so no special-casing is needed for the hyphenated
code). Commit message: `"Add the Chinese (Simplified) User Guide"`.

---

## Task 9: `USER_GUIDE.zh-Hant.md`, derived from Simplified via OpenCC, with its own screenshots

**Files:**
- Create: `USER_GUIDE.zh-Hant.md`
- Create: `docs/user-guide/zh-Hant/*.png`
- Modify: `dossiary.html` (`USER_GUIDE_LANGS`)

**Interfaces:**
- Consumes: `USER_GUIDE.zh-Hans.md` (Task 8 — the source this task
  converts from), `STRINGS['zh-Hant']` (Task 5 — the app must be fully
  Traditional-Chinese-capable before this task's screenshots are
  captured)
- Produces: nothing later tasks depend on

- [ ] **Step 1: Convert `USER_GUIDE.zh-Hans.md`'s prose via OpenCC**

Same tool and approach as Task 5's `STRINGS['zh-Hant']` derivation
(`opencc.OpenCC('s2t').convert(...)`), run over the finished
`USER_GUIDE.zh-Hans.md`'s full text. Markdown syntax (`#`, `*`, `[]()`,
etc.) and the embedded `docs/user-guide/zh-Hans/*.png` image paths pass
through the conversion unchanged (OpenCC only touches Chinese
characters) — after conversion, **update the image paths** from
`docs/user-guide/zh-Hans/` to `docs/user-guide/zh-Hant/` (this task
captures its own screenshot set, per the design spec's explicit "not
shared between the two Chinese guides" rule — the converted prose's
image references need to point at that new set, not Task 8's).

- [ ] **Step 2: Capture screenshots**

Same process as Task 6 Step 2, toggling the language dropdown to
`zh-Hant`. Save into `docs/user-guide/zh-Hant/`.

- [ ] **Step 3: Add `zh-Hant` to `USER_GUIDE_LANGS`**

```js
  const USER_GUIDE_LANGS = ['de', 'es', 'fr', 'zh-Hans', 'zh-Hant'];
```

- [ ] **Step 4: Verify screenshot references and internal links**, same
two checks as Task 6 Steps 4-5, run against `USER_GUIDE.zh-Hant.md`.

- [ ] **Step 5: Commit**

```bash
git add USER_GUIDE.zh-Hant.md docs/user-guide/zh-Hant/ dossiary.html
git commit -m "Add the Chinese (Traditional) User Guide, derived from Simplified via OpenCC"
```

---

## Task 10: CLAUDE.md documentation and final verification

**Files:**
- Modify: `CLAUDE.md` (extend the existing "UI language support" note,
  ~line 1592, and the "User Guide vs. README" note added alongside
  `USER_GUIDE.md`)
- Modify: `README.md`/`README.de.md` (the existing User Guide pointer —
  no content change needed unless it names a specific language; verify
  only)

**Interfaces:**
- Consumes: everything from Tasks 1-9 — this is the terminal
  documentation/verification task.
- Produces: nothing — terminal task.

- [ ] **Step 1: Extend CLAUDE.md's existing "UI language support" note**

Find the note (search for `**UI language support`). Add coverage for,
without rewriting the existing English/German-era content: the
generalization to `SUPPORTED_LANGS`/`NATIVE_LANG_NAMES`/`LANG_AUTODETECT`/
`DATE_LOCALE`, the dropdown replacing the two-state button (and why the
modal-open guard had to actively reset the select's value rather than
just skip acting, unlike the old button), Chinese's
identical-singular-plural-text handling, the Chinese
Simplified/Traditional region-disambiguation rules (including the
bare-`zh`-defaults-to-Simplified case and why `LANG_AUTODETECT`'s order
matters for it), and the OpenCC-derivation approach for both
`STRINGS['zh-Hant']` and `USER_GUIDE.zh-Hant.md` (what tool, why
derivation instead of independent translation, what tradeoff it accepts
per the design spec).

- [ ] **Step 2: Extend the "User Guide vs. README" note**

Update the "each guide showing its own language's UI" sentence to name
all six languages instead of just English/German, and note the
`USER_GUIDE_LANGS` array's growth (now `['de', 'es', 'fr', 'zh-Hans',
'zh-Hant']`) alongside the description already there of how the footer
link falls back to English for languages without their own guide (no
longer a live case once all four are added, but worth keeping the
fallback's existence documented since it's still real code).

- [ ] **Step 3: Run the full baseline suite one final time**

Run the same command as Task 1 Step 8.
Expected: `TOTAL: 57  FAILED: []` (none of Tasks 1-9 add a new
`test_*.py` file — all new coverage lives inside `test_i18n.py`).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Document the six-language i18n architecture and OpenCC-derivation approach"
```
