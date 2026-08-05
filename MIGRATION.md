# Migrating from Mariner Paperless

*Part of [Dossiary](README.md) — see the main README for everything else.
[Diese Anleitung auf Deutsch lesen](MIGRATION.de.md).*

If you're coming from the discontinued Mariner Paperless app, first
convert your library using one of the tools in the sibling
[LibraryLifeboat](https://github.com/AarneAarebye/LibraryLifeboat)
repo — a one-time conversion that reads a `.paperless` library and
produces a `library.sqlite` + `files/` folder in the schema Dossiary
expects. Point Dossiary at that output folder afterward.

- **[`migrate_to_new_library.py`](https://github.com/AarneAarebye/LibraryLifeboat#migrate_to_new_librarypy-migration-to-dossiary)** —
  the underlying script, run from the Terminal. This is the single source
  of truth for the actual migration logic; both GUIs below are thin
  wrappers around this exact script, not separate implementations.
- **[`migrate_gui.py`](https://github.com/AarneAarebye/LibraryLifeboat#migrate_guipy-desktop-app)** —
  a small native desktop app (tkinter) if you'd rather not use the
  Terminal: choose the folder your libraries live in, select which ones
  to migrate, pick an output folder, click Migrate. (This app also has
  an Export mode for a separate, lossless-copy use case — see its own
  repo — but Migrate is what you want for Dossiary.)
- **[`migrate_web.py`](https://github.com/AarneAarebye/LibraryLifeboat#migrate_webpy-browser-based-alternative)** —
  the same thing, including the same Migrate/Export mode choice, as a
  local web page instead of a native window, for anyone who'd rather use
  a browser tab.

If you have several libraries to migrate, either GUI is likely more
convenient than running the script by hand once per library.
