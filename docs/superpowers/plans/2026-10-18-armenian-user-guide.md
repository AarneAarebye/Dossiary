# Armenian User Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `USER_GUIDE.hy.md`, an Armenian User Guide with its own nine Armenian screenshots, linked from Dossiary's footer when the interface is in Armenian.

**Architecture:** Sub-project 2 of `docs/superpowers/specs/2026-10-17-armenian-design.md`. The Armenian interface itself shipped in v1.49.0 (sub-project 1). `docs/user-guide/capture.py` gains `hy`, so it writes `docs/user-guide/hy/` with the nine shots every translated guide uses. The guide is translated from `USER_GUIDE.md`, laid out like the other translated guides (`USER_GUIDE.fr.md` is the model), and quotes the app's own Armenian labels from `STRINGS.hy`. The footer link already falls back to English for a language without a guide, so the app change is one array entry. Every guide's language line gains the Armenian link. A new static test keeps the guides, their images and the footer list consistent. The neighbour's review page gains the guide.

**Tech Stack:** Markdown, Python 3 + Playwright (capture script and tests), one array in `dossiary.html`, the review Artifact from sub-project 1.

## Global Constraints

- Armenian register: polite «Դուք» (capitalised «Ձեր», «Ձեզ»), Armenian punctuation «։» for full stops, «՝», «՞» where the grammar needs them, quotes «…».
- Every interface label the guide names (buttons, menus, views, fields) is spelled exactly as in `STRINGS.hy` in `dossiary.html`, without the emoji prefix. Never invent a label.
- The guide shows the nine images every translated guide has, under `docs/user-guide/hy/`, with these exact file names: `01-no-library.png`, `02-table.png`, `03-capture-blank.png`, `04-capture-ocr.png`, `05-capture-filled.png`, `06-search.png`, `07-inbox.png`, `08-review-detail.png`, `09-reports.png`.
- Screenshots come only from `docs/user-guide/capture.py`, never by hand. The demo documents stay the existing fabricated ones (no real personal data).
- Dossiary stays one file with no build step. The only app change is `USER_GUIDE_LANGS`.
- Every test script prints `True` on pass. A `: False` anywhere is a failure (see `tests/CLAUDE.md`).
- Commit messages end with the two attribution lines given in the session (`Co-Authored-By: …`, `Claude-Session: …`).
- Releasing (tag, push, GitHub release) needs the user's OK. After a release, copy `dossiary.html` to `/Applications/Dossiary/dossiary.html`.

## File map

| File | Change |
|---|---|
| `docs/user-guide/capture.py` | `hy` in the default language list and the locale map |
| `docs/user-guide/hy/*.png` | new, 9 screenshots |
| `USER_GUIDE.hy.md` | new, the guide |
| `USER_GUIDE.md`, `.de`, `.es`, `.fr`, `.zh-Hans`, `.zh-Hant` | Armenian link added to each language line |
| `dossiary.html` | `USER_GUIDE_LANGS` gains `'hy'` |
| `tests/test_user_guides.py` | new static check of all guides |
| `tests/test_i18n.py` | Scenario 30 checks the footer link in Armenian |
| `CLAUDE.md`, `tests/CLAUDE.md` | layout list, guide notes, image count, new test |
| review page (`scratchpad/hy/build_review.py`, `review-template.html`) | a "User Guide" group, one item per paragraph |

---

### Task 1: Armenian screenshots

**Files:**
- Modify: `docs/user-guide/capture.py:23` and `:59`
- Create: `docs/user-guide/hy/` (9 PNGs, written by the script)

**Interfaces:**
- Produces: `docs/user-guide/hy/01-no-library.png` … `09-reports.png`, used by Task 2's image links.

- [ ] **Step 1: Add `hy` to the script.** In `docs/user-guide/capture.py`, change the default list on line 23:

```python
ONLY = sys.argv[1].split(',') if len(sys.argv) > 1 and sys.argv[1] != 'all' else ['en', 'de', 'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']
```

and the locale map in `capture()` (line 59):

```python
        locale={'en': 'en-US', 'de': 'de-DE', 'es': 'es-ES', 'fr': 'fr-FR', 'zh-Hans': 'zh-CN', 'zh-Hant': 'zh-TW', 'hy': 'hy-AM'}[lang])
```

Nothing else in the script is language-specific. `hy` is not `'en'`, so it gets `OTHER_NAMES`, the nine shots.

- [ ] **Step 2: Capture.** Run `python3 docs/user-guide/capture.py hy` from the repo root.

Expected: nine lines `hy/01-no-library.png` … `hy/09-reports.png`, and no `JS errors:` line. OCR runs for real, so this takes a few minutes.

- [ ] **Step 3: Look at every image.** Open all nine with the Read tool and check:
  - the interface is in Armenian script;
  - no glyph boxes (□) appear; headless Chromium on macOS uses the system Armenian font;
  - the footer shows the current `APP_VERSION`;
  - `01-no-library.png` shows the language menu reading «Հայերեն».

  If glyphs are missing, stop and report it. Don't swap fonts in the app.

- [ ] **Step 4: Commit**

```bash
git add docs/user-guide/capture.py docs/user-guide/hy
git commit -m "User Guide screenshots in Armenian (capture.py hy)"
```

---

### Task 2: Write `USER_GUIDE.hy.md`

**Files:**
- Create: `USER_GUIDE.hy.md`
- Read: `USER_GUIDE.md` (source text), `USER_GUIDE.fr.md` (layout model), `dossiary.html` (`STRINGS.hy` labels)

**Interfaces:**
- Consumes: the nine images from Task 1.
- Produces: `USER_GUIDE.hy.md`. Its line 9 is the language line, in the same shape as the other guides'. Task 3 checks it.

- [ ] **Step 1: Extract the labels you will quote.** Run from the repo root:

```bash
node -e '
const h=require("fs").readFileSync("dossiary.html","utf8");
const s=h.indexOf("const STRINGS = "), e=h.indexOf("\n  };", s);
const S=eval("("+h.slice(s+16,e+4)+")");
for(const k of Object.keys(S.en)) console.log(k+"\t"+S.en[k]+"\t"+S.hy[k]);' > /tmp/claude-labels.tsv
```

(Use the session scratchpad instead of `/tmp` if one is listed.) Whenever the English guide names a control or view, such as "Open library folder", "Add document", "Make searchable", "Check inbox", "Inbox", "Done", "Waste bin", "Reports", "Collections", "Tools", "Library check", "Back up library…", "Scan", "Field settings", "Show archived" or "Archive", find its row by the English text and use the third column. Drop a leading emoji and «…»/«▾» decorations when the label sits in running text.

- [ ] **Step 2: Lay the guide out like the French one.** `USER_GUIDE.fr.md` follows `USER_GUIDE.md` section by section with the same nine headings:

  | English | Armenian |
  |---|---|
  | What is Dossiary? | Ի՞նչ է Dossiary-ն |
  | Getting started | Ինչպես սկսել |
  | Adding your first document | Ձեր առաջին փաստաթղթի ավելացումը |
  | Finding it again | Ինչպես այն նորից գտնել |
  | The everyday paper pile | Ամենօրյա թղթերի կույտը |
  | Scanning straight into Dossiary | Սկանավորում անմիջապես Dossiary-ի մեջ |
  | A quick tour of everything else | Արագ շրջայց մնացած ամեն ինչով |
  | Where to go next | Ինչ անել հետո |

  The French guide uses the English guide's three extra images (`02-empty-folder`, `03-library-ready`, `12-collections`) as plain text, without a picture. Do the same. Put each of the nine images where the French guide puts it, with the same file number under `docs/user-guide/hy/`, and translate its alt text.

- [ ] **Step 3: Write the guide.** Translate `USER_GUIDE.md` in full into Armenian, following the Global Constraints:
  - The title is `# Dossiary-ի օգտագործողի ուղեցույց` (matches `footerUserGuideLink` «Օգտագործողի ուղեցույց»).
  - The italic intro paragraph points technical readers to `README.md` (English) and `README.de.md` (German), as `USER_GUIDE.fr.md`'s does.
  - The language line comes right after it, exactly:

```markdown
*[This guide in English](USER_GUIDE.md) · [Diese Anleitung auf Deutsch](USER_GUIDE.de.md) · [Esta guía en español](USER_GUIDE.es.md) · [Ce guide en français](USER_GUIDE.fr.md) · [简体中文版](USER_GUIDE.zh-Hans.md) · [繁體中文版](USER_GUIDE.zh-Hant.md)*
```

  - Links to other repo files (`MIGRATION.md`, `README.md`, releases, scanix500, dossiary-scan-helper) stay exactly as in `USER_GUIDE.md`. After a link to an English-only document, add «(անգլերեն)».
  - Keep the demo content as the screenshots show it: document titles such as "Nordlicht Hardware Invoice #1042", the search word `warranty`, EUR amounts. Don't translate text that appears in a screenshot.
  - Armenian-specific details belong where the English guide talks about OCR language and amounts. Mention that **Հայերեն** is an OCR language and that Dossiary recognises Armenian dates and dram amounts (֏). One sentence each, no new sections.

- [ ] **Step 4: Check labels and links by hand.**

```bash
grep -o '\*\*[^*]*\*\*' USER_GUIDE.hy.md | sort -u
grep -o '](docs/user-guide/[^)]*)' USER_GUIDE.hy.md
```

Every bold term that names a control must be in the third column of the labels file: `grep -F "<term>" <labels file>`. Exactly nine image links, all `docs/user-guide/hy/…`.

- [ ] **Step 5: Commit**

```bash
git add USER_GUIDE.hy.md
git commit -m "Armenian User Guide (USER_GUIDE.hy.md)"
```

---

### Task 3: Link it everywhere, with a consistency test

**Files:**
- Create: `tests/test_user_guides.py`
- Modify: `USER_GUIDE.md:7`, `USER_GUIDE.de.md:8`, `USER_GUIDE.es.md:9`, `USER_GUIDE.fr.md:9`, `USER_GUIDE.zh-Hans.md:7`, `USER_GUIDE.zh-Hant.md:7` (language lines)
- Modify: `dossiary.html` (`USER_GUIDE_LANGS`, near line 3439)
- Modify: `tests/test_i18n.py` (Scenario 30)
- Modify: `CLAUDE.md`, `tests/CLAUDE.md`

**Interfaces:**
- Consumes: `USER_GUIDE.hy.md` (Task 2), `docs/user-guide/hy/` (Task 1).

- [ ] **Step 1: Write the failing static test** `tests/test_user_guides.py`:

```python
# Static check of the User Guides: every image a guide shows exists, every
# guide links every other guide on its language line, and Dossiary's footer
# list USER_GUIDE_LANGS names exactly the translated guides that exist.
import os, re, glob
os.chdir(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.abspath('..')

guides = sorted(glob.glob(os.path.join(REPO, 'USER_GUIDE*.md')))
names = [os.path.basename(g) for g in guides]
langs = sorted(re.match(r'USER_GUIDE\.(.+)\.md$', n).group(1) for n in names if n != 'USER_GUIDE.md')
print("Guides found:", names)

for g in guides:
    text = open(g, encoding='utf-8').read()
    name = os.path.basename(g)
    images = re.findall(r'\]\((docs/user-guide/[^)]+\.png)\)', text)
    missing = [i for i in images if not os.path.exists(os.path.join(REPO, i))]
    print(f"{name}: every image exists:", images != [] and missing == [], missing)
    own = 'en' if name == 'USER_GUIDE.md' else re.match(r'USER_GUIDE\.(.+)\.md$', name).group(1)
    print(f"{name}: images come from its own language folder:",
          all(i.startswith(f'docs/user-guide/{own}/') for i in images))
    line = next((l for l in text.splitlines() if l.startswith('*[') and 'USER_GUIDE' in l), '')
    linked = set(re.findall(r'\]\((USER_GUIDE[^)]*\.md)\)', line))
    others = set(names) - {name}
    print(f"{name}: language line links every other guide:", linked == others, sorted(others - linked))

html = open(os.path.join(REPO, 'dossiary.html'), encoding='utf-8').read()
m = re.search(r"const USER_GUIDE_LANGS = \[([^\]]*)\]", html)
app_langs = sorted(re.findall(r"'([^']+)'", m.group(1)))
print("USER_GUIDE_LANGS matches the translated guides:", app_langs == langs, app_langs, langs)
supported = re.findall(r"'([^']+)'", re.search(r"const SUPPORTED_LANGS = \[([^\]]*)\]", html).group(1))
print("every translated guide is a UI language:", set(langs) <= set(supported))
```

- [ ] **Step 2: Run it to see it fail.** Run `cd tests && python3 test_user_guides.py`.

Expected `False` lines:
- the six older guides: "language line links every other guide" (missing `USER_GUIDE.hy.md`);
- "USER_GUIDE_LANGS matches the translated guides" (`hy` missing);
- `USER_GUIDE.hy.md` itself is all `True`.

- [ ] **Step 3: Add the Armenian link to each older guide's language line.** Append ` · [Այս ուղեցույցը հայերեն](USER_GUIDE.hy.md)` just before the closing `*` on each line:
  - `USER_GUIDE.md` line 7
  - `USER_GUIDE.de.md` line 8
  - `USER_GUIDE.es.md` line 9
  - `USER_GUIDE.fr.md` line 9
  - `USER_GUIDE.zh-Hans.md` line 7
  - `USER_GUIDE.zh-Hant.md` line 7

  For example, `USER_GUIDE.md`'s line becomes:

```markdown
*[Diese Anleitung auf Deutsch](USER_GUIDE.de.md) · [Esta guía en español](USER_GUIDE.es.md) · [Ce guide en français](USER_GUIDE.fr.md) · [简体中文版](USER_GUIDE.zh-Hans.md) · [繁體中文版](USER_GUIDE.zh-Hant.md) · [Այս ուղեցույցը հայերեն](USER_GUIDE.hy.md)*
```

- [ ] **Step 4: Footer list.** In `dossiary.html`:

```js
  const USER_GUIDE_LANGS = ['de', 'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']; // languages with their own USER_GUIDE.<lang>.md; English has no suffix
```

- [ ] **Step 5: Extend Scenario 30 in `tests/test_i18n.py`.** Right after the line printing `"Scenario 30 -- hy-AM browser locale auto-detects Armenian:"`, insert:

```python
        hy_guide_href_30 = await page30.locator('#user-guide-link').get_attribute('href')
        print("Scenario 30 -- footer User Guide link points at the Armenian guide:",
              hy_guide_href_30.endswith('/USER_GUIDE.hy.md'))
```

- [ ] **Step 6: Run the tests.**

```bash
cd tests && python3 test_user_guides.py && python3 test_i18n.py | grep -v ": True$" && python3 test_i18n_coverage.py | tail -1
```

Expected:
- `test_user_guides.py` prints only `True` checks;
- `test_i18n.py` prints only `JS ERRORS: []`;
- coverage ends with `PASS`.

- [ ] **Step 7: Docs.**
  - `CLAUDE.md` repository layout: add `USER_GUIDE.hy.md         Armenian translation of USER_GUIDE.md` after the zh-Hant entry, and add `hy/` to the `docs/user-guide/` subfolder list.
  - `CLAUDE.md` "User Guide vs. README" section:
    - `USER_GUIDE_LANGS` is quoted as `['de', 'es', 'fr', 'zh-Hans', 'zh-Hant']`; make it `['de', 'es', 'fr', 'zh-Hans', 'zh-Hant', 'hy']`;
    - "rewrites all 57 images" becomes "rewrites all 66 images";
    - "the five translated guides 9" becomes "the six translated guides 9".
  - `tests/CLAUDE.md`:
    - raise the script count in "There's a real, runnable Playwright regression suite in `tests/` — **98 scripts**" by one;
    - add `test_user_guides.py` to the list of non-Playwright scripts (next to `test_i18n_coverage.py`), described as "a static check that every User Guide's images exist, every guide links all the others, and `USER_GUIDE_LANGS` matches the translated guides".

- [ ] **Step 8: Commit**

```bash
git add tests/test_user_guides.py tests/test_i18n.py dossiary.html USER_GUIDE*.md CLAUDE.md tests/CLAUDE.md
git commit -m "Link the Armenian User Guide from every guide and the footer; static guide check"
```

---

### Task 4: Add the guide to the neighbour's review page

**Files:**
- Modify: `<scratchpad>/hy/build_review.py`, `<scratchpad>/hy/review-template.html` (session scratchpad; if it's gone, read the live page with `Artifact` `action: "read"` on `https://claude.ai/artifact/Bysut9bJ4JpHCFGer7pPtt` and rebuild from it)
- Republish: the same artifact URL (its `reviews` data is kept)

**Interfaces:**
- Consumes: `USER_GUIDE.hy.md` and `USER_GUIDE.md`.
- Produces: review items with ids `guide-<section>-<n>`, saved under the same `reviews/<id>` documents as the strings.

- [ ] **Step 1: Split the guide into paragraphs.** In `build_review.py`, before `groups = …`, add:

```python
def paragraphs(path):
    out, section, n, buf = [], 'intro', 0, []
    def flush():
        nonlocal n
        text = '\n'.join(buf).strip()
        buf.clear()
        if text and not text.startswith('!['):
            n += 1
            out.append((section, n, text))
    for line in open(path, encoding='utf-8').read().splitlines():
        if line.startswith('## '):
            flush()
            section, n = str(len({s for s, _, _ in out}) + 1), 0
            out.append((section, 0, line[3:].strip()))
        elif not line.strip():
            flush()
        else:
            buf.append(line)
    flush()
    return out

repo = '/Users/aarneaarebye/Projects/Paperless/Dossiary'
hy_paras = paragraphs(os.path.join(repo, 'USER_GUIDE.hy.md'))
en_paras = paragraphs(os.path.join(repo, 'USER_GUIDE.md'))
en_by_section = {}
for s, n, t in en_paras:
    en_by_section.setdefault(s, []).append(t)
for s, n, t in hy_paras:
    en_list = en_by_section.get(s, [])
    en_text = en_list[n] if n < len(en_list) else ''
    items.append({'id': f'guide-{s}-{n:02d}', 'group': 'guide', 'en': en_text, 'hy': t})
```

The English column is the paragraph at the same position in the same section, a guide for orientation only. The English guide may have more paragraphs where it shows an image the translated guides leave out, so the pairing can drift by one. The group note says so.

- [ ] **Step 2: Add the group.** In `GROUPS`, insert before `('other', …)`:

```python
    ('guide', 'Օգտագործողի ուղեցույց', 'User Guide (USER_GUIDE.hy.md)'),
```

and after the `groups[-1]['note'] = …` line add:

```python
for g in groups:
    if g['id'] == 'guide':
        g['note'] = ('Each item is one paragraph of the Armenian guide; the English beside it is the nearest paragraph of the English guide. · '
                     'Յուրաքանչյուր տարր ուղեցույցի մեկ պարբերություն է։')
```

- [ ] **Step 3: Rebuild and check.** Run `python3 build_review.py` in the scratchpad's `hy/` folder. Expected: the item count grows by the guide's paragraph count (about 80–120). Syntax-check the page script as before:
  - extract the `<script>` body to a file;
  - run `node --check` on it.

- [ ] **Step 4: Republish** with the Artifact tool:
  - same `file_path`;
  - `label: "User Guide added"`;
  - no `capabilities`, so the `db`/`user` declaration carries forward;
  - no `icon`.

- [ ] **Step 5: Verify.** Run `ArtifactData` `list` on collection `reviews` and confirm the answers already saved are still there. Tell the user the page now has a "User Guide" group at the end.

---

### Task 5: Release

The user decided on 2026-10-18, for sub-project 1, to release before the neighbour's review and apply his corrections afterwards. Follow the same order here unless the user says otherwise.

- [ ] **Step 1: Full suite.** Run every test script and list only failures:

```bash
cd tests && for t in test_*.py; do out=$(python3 "$t" 2>&1); bad=$(echo "$out" | grep -E ": False|Traceback|Error:" | grep -v "JS ERRORS" | head -3); [ -n "$bad" ] && echo "== $t" && echo "$bad"; done; echo ALLDONE
```

(No `timeout` wrapper: macOS has none.) Expected: just `ALLDONE`. If a failure is unrelated to this plan, report it rather than fixing it here.

- [ ] **Step 2: Version.** Follow `.claude/skills/cutting-a-release/SKILL.md`:
  - bump `APP_VERSION` in `dossiary.html`, `__version__` in `scan_watch.py`, and the expectation in `tests/test_scan_watch_version.py` to the next patch version;
  - re-run `python3 docs/user-guide/capture.py all`, so the footers of all 66 images show it;
  - commit.

- [ ] **Step 3: Ask the user for the OK to release**, then:
  - merge the branch into main locally;
  - push main and the tag;
  - create the GitHub release with assets `dossiary.html scan_watch.py USER_GUIDE.md USER_GUIDE.de.md USER_GUIDE.es.md USER_GUIDE.fr.md USER_GUIDE.zh-Hans.md USER_GUIDE.zh-Hant.md USER_GUIDE.hy.md`. The release notes state that the Armenian guide is awaiting the native speaker's review.

- [ ] **Step 4: Install.** `cp dossiary.html /Applications/Dossiary/dossiary.html`, then confirm the version with `grep -o "APP_VERSION = '[0-9.]*'" /Applications/Dossiary/dossiary.html`.

- [ ] **Step 5: Memory.** Update `project_armenian_review.md` in the memory folder:
  - the review page now also covers the guide;
  - guide corrections go into `USER_GUIDE.hy.md`;
  - sub-projects 3 and 4 remain.
