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
