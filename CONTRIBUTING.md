# Contributing to Dossiary

Thanks for considering a contribution. A few things specific to how this
project works before you dive in.

## The one big constraint

`dossiary.html` is a single, dependency-free file on purpose —
"download it, open it, it works," no build step, no `npm install`. Keep it
that way. If a change would need a bundler, a build step, or splitting the
file up, please open an issue to discuss first rather than sending a PR
that assumes it.

`scan_watch.py` is the one deliberate exception — a separate, optional,
stdlib-only companion script that's never loaded by the app itself. See its
own note in `CLAUDE.md` for why it lives outside the single file.

## Read `CLAUDE.md` first

It's not boilerplate — it documents *why* the code is shaped the way it is,
including several places where an earlier, more "obvious" implementation
was tried and deliberately reverted (a category→subcategory hierarchy, a
single `person` text column, automatic bulk thumbnail generation on open,
among others). If you're about to "fix" something that looks wrong at a
glance, check there first — it might be intentional, with the reasoning
already written down.

## Running the tests

There's a real Playwright regression suite in `tests/` (42 scripts, nothing
extra to install beyond Python 3 and Playwright's Chromium). Each is
standalone:

```
cd tests
python3 test_<name>.py
```

Nothing here touches a real browser dialog or real sql.js/Tesseract.js —
see `CLAUDE.md`'s "How this was tested" section for how the stubbing
approach works. Every test file loads the same shared
`tests/stub_studio2.js` — never write your own copy of it for a new test
file, even a small one; that's bitten this project before (see that same
section).

**Every test seeds its own synthetic library.** Don't commit real personal
documents or a real `library.sqlite`/`.paperless` fixture. `.gitignore`
already excludes the common patterns for this (test-run PDF/PNG/SQLite
fixtures, `.paperless` bundles, etc.) — extend it if you add a new kind of
generated fixture file, rather than working around it.

## Making a change

- **Add or extend a test for whatever you change.** This is a browser app
  verified only through Playwright + stubs — an untested change is
  effectively an unverified one.
- **Update `CLAUDE.md` in the same change** if you add a feature, change a
  data migration, or make a non-obvious design decision. Keeping that file
  accurate is a stated convention of this repo, not an afterthought — it's
  caught real regressions before precisely because it was kept current.
- **Don't add a new runtime dependency** without discussing it first.
  Everything the app needs is loaded from a CDN at runtime (see
  `OPEN_SOURCE_LIBRARIES` in `dossiary.html` and the "Third-party
  libraries" table in `README.md`), and each one's license was verified
  directly against its own upstream repo, not assumed from memory.
- Match the existing visual language (dark "ink" background, phosphor-green
  accents, amber for capture/new-document actions) — this app shares it
  with a sibling project, `document_ledger.html`, and people may use both.

## Schema changes

If you add a column to `library.sqlite`, add both a `SCHEMA` entry *and* a
`SCHEMA_MIGRATIONS` entry (an `ALTER TABLE ... ADD COLUMN ...`) in the same
change — `CREATE TABLE IF NOT EXISTS` alone won't retroactively add it to
anyone's existing library. See `CLAUDE.md`'s "Schema upgrades for
already-existing libraries" note.

## Reporting bugs / requesting features

Open a GitHub issue. Please include your browser — Chrome or Edge only,
since Safari/Firefox don't support the File System Access API this app
depends on — and, if it's a data issue, whether the library was created
fresh here or migrated from Mariner Paperless via `migrate_to_new_library.py`
in the sibling `LibraryLifeboat` repo (formerly MarinerPaperlessTools).

## License

By contributing, you agree your contribution is licensed under this
project's [MIT License](LICENSE).
