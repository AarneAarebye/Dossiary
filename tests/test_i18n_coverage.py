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
