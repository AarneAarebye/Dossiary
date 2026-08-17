# User Guide (English / German) — design

## Context

`README.md`/`README.de.md` are Dossiary's only current user-facing docs,
and they're written for people who want to understand the internals
(schema, architecture, limitations) — not for someone who just wants to
start using the app. There's no on-ramp for a non-technical person asking
"what is this, and how do I get my paper documents into it."

This project adds a separate, beginner-oriented user guide, in English
and German, following the repo's existing `README.de.md`/`MIGRATION.de.md`
precedent for bilingual docs.

## Audience and scope

The guide is written for a first-time user starting from physical paper,
with no prior digital archive system — not for someone migrating an
existing Mariner Paperless library (that's `MIGRATION.md`'s job; the guide
just points to it in its final section).

Coverage is "core loop, plus a light tour of everything else":

1. **What is Dossiary?** — one paragraph: local-first, files stay on your
   disk, no account/cloud/subscription.
2. **Getting started** — download the file, choose a folder to hold your
   library, what gets created (`library.sqlite`, `files/`).
3. **Adding your first document** — the capture form walkthrough
   (scan/photo/PDF upload → OCR → save), step-by-step with screenshots.
4. **Finding it again** — search, filters, tags, sorting.
5. **The everyday paper pile** — the Inbox/scan-folder workflow (a
   watched folder or drag-and-drop, then the review queue) — the
   practical answer to "how do I bring my whole paper archive in."
6. **A quick tour of everything else** — short, screenshot-light
   subsections on Collections, Reports, Archive/Waste bin, and custom
   fields: enough to know each exists and where to click, not full
   how-tos (those stay README territory).
7. **Where to go next** — pointer to the technical README for
   schema/internals, and to `MIGRATION.md` for Mariner Paperless users.

Non-goals: replacing or duplicating README's technical depth; covering
Mariner migration in detail; documenting every advanced feature
(`scan_watch.py` flags, Field Settings' full capability system, Reports'
multi-value caveat) at how-to depth — the tour section links intent, not
implementation.

## Files and linking

- `USER_GUIDE.md` / `USER_GUIDE.de.md` at repo root, matching the existing
  `README.de.md`/`MIGRATION.de.md` naming convention.
- A short callout added near the top of `README.md`/`README.de.md`:
  *"New here? Start with the [User Guide](USER_GUIDE.md) instead — this
  README covers the technical internals."* (German equivalent in
  `README.de.md`.)
- `CLAUDE.md`'s repo-layout section gets the two new files (and the new
  `docs/user-guide/` image folder) added to its file listing, following
  the same one-line-per-file convention already used there.

## Screenshots

Stored under `docs/user-guide/en/*.png` and `docs/user-guide/de/*.png`
(~10-12 per language) — empty state, capture form, OCR running, table
after a few captures, search/filter, Inbox banner, and small ones for the
feature-tour section (Collections, Reports, Archive).

Each language's guide shows that language's own UI (the German guide's
screenshots show the German-toggled app, not reused English images) — the
app already supports this via the in-app language toggle from the
UI-language-support project, so this is a same-session toggle, not two
separate app builds.

**Capture method:** a small seeded demo library (fabricated sample
documents — invoices, a letter, a receipt — nothing personal), opened in
a real Chrome tab via browser automation, driven through each guide step
to produce the screenshots, toggling the in-app language control between
the English and German passes. The native "choose folder" picker can't be
automated — the person following along needs to click through it once at
the start of the capture session; everything else is scripted.

The demo library itself is not committed to the repo — only the
resulting PNG screenshots are. `.gitignore` already excludes personal
library data by pattern; the demo library is created in a scratch
location outside the repo, not inside it, so no extra `.gitignore` entry
is needed.

## Non-goals (repeated for clarity)

- No new build step, no static-site generator — plain Markdown files,
  consistent with every other doc in this repo.
- No screenshot-diffing or automated visual-regression testing — these
  are static images refreshed manually on a future UI change, same
  maintenance model as any other doc.
- No restructuring of the existing README/MIGRATION docs beyond the one
  callout line each.

## Verification

- Every internal link (README ↔ User Guide ↔ MIGRATION.md, and each
  guide's own section anchors) resolves.
- Every screenshot referenced in each guide file actually exists at the
  referenced path, and is the correct language variant for its file.
- A read-through confirms the German guide reads as a natural translation
  rather than a literal one, matching the tone `README.de.md` already
  established.
