import os, re, json, subprocess

os.chdir(os.path.dirname(os.path.abspath(__file__)))
APP_PATH = os.path.abspath(os.path.join('..', 'dossiary.html'))
html = open(APP_PATH, encoding='utf-8').read()

# Extract the STRINGS object's two language blocks by locating "const STRINGS = {"
# and the matching top-level "en:" / "de:" object bodies, then pulling every
# `key:` identifier out of each with a regex -- deliberately not a real JS
# parser (no such dependency in this repo), just enough structure-awareness
# to avoid false matches inside string values that happen to contain a colon.
strings_match = re.search(r'const STRINGS = \{(.*?)\n  \};', html, re.DOTALL)
assert strings_match, "Could not locate STRINGS object in dossiary.html"
strings_body = strings_match.group(1)

en_match = re.search(r'en:\s*\{(.*?)\n    \},\s*\n    de:', strings_body, re.DOTALL)
de_match = re.search(r'de:\s*\{(.*?)\n    \},', strings_body, re.DOTALL)
assert en_match and de_match, "Could not split STRINGS into en/de blocks"

# NOTE on this regex: a naive `^\s*(\w+):` (key must start a line) undercounts
# badly here -- dossiary.html packs several `key: 'value',` pairs onto a single
# source line throughout STRINGS (see e.g. the commonCancel/commonSave/... line),
# so anchoring to line-start only ever catches the first key per line. Anchoring
# each key to being preceded by `{`, `,`, or a line start instead (still requiring
# a `:` then a quote right after, so we don't also match ": " sequences that
# happen to appear inside a string *value*, e.g. the literal value `'Important:'`
# has a colon immediately followed by its own closing quote) catches every key
# regardless of how many share a line, without needing a real JS parser.
key_re = re.compile(r'''(?:^|[{,])\s*(\w+):\s*['"]''', re.MULTILINE)
en_keys = set(key_re.findall(en_match.group(1)))
de_keys = set(key_re.findall(de_match.group(1)))

print(f"STRINGS.en has {len(en_keys)} keys, STRINGS.de has {len(de_keys)} keys")

# Every referenced key -- from data-i18n*="key" attributes and t('key'...)/t("key"...) calls.
# The call-site regex requires a word boundary before the "t" so it only matches
# the actual t() translation helper, not any other function whose name happens to
# end in "t" followed by a quoted string argument (createElement('div'),
# getContext('2d'), dispatchEvent(new Event('change')), closest('th...'), etc. --
# all real calls in this file that a bare `t\(` pattern would misfire on).
attr_keys = set(re.findall(r'data-i18n(?:-placeholder|-title|-aria-label)?="([a-zA-Z0-9]+)"', html))
call_keys = set(re.findall(r"""\bt\(\s*['"]([a-zA-Z0-9]+)['"]""", html))
referenced_keys = attr_keys | call_keys

missing_from_en = referenced_keys - en_keys
missing_from_de = referenced_keys - de_keys
unused_en_only = en_keys - referenced_keys  # defined but never referenced -- not a failure, just reported

print("Keys referenced in markup/code but missing from STRINGS.en:", sorted(missing_from_en))
print("Keys referenced in markup/code but missing from STRINGS.de:", sorted(missing_from_de))
print("Keys defined in STRINGS but never referenced (informational only):", sorted(unused_en_only))

assert not missing_from_en, f"{len(missing_from_en)} key(s) missing from STRINGS.en"
assert not missing_from_de, f"{len(missing_from_de)} key(s) missing from STRINGS.de"
print("PASS")
