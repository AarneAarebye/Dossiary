#!/usr/bin/env python3
"""
migrate_to_new_library.py

One-time migration from a Mariner Paperless v3 library (.paperless package)
into a clean, simple SQLite-based library for the replacement app
(document_studio.html).

USAGE:
    python3 migrate_to_new_library.py "/path/to/Library.paperless" "/path/to/new_library_folder"

WHAT IT DOES:
    Creates <new_library_folder>/library.sqlite with a small, purpose-built
    schema (see below), and copies every document's processed PDF (falling
    back to the original file if no processed PDF exists) into
    <new_library_folder>/files/, named by the new document's own id.

    This is a ONE-TIME conversion, not a sync tool. It reads the old library
    read-only and never modifies it. Run it once, then use
    document_studio.html against the new library folder going forward.

NEW SCHEMA (deliberately much simpler than Mariner's Core Data schema):

    documents
        id                 INTEGER PRIMARY KEY
        title              TEXT     -- was ZMERCHANT / fallback to category
        category           TEXT
        document_type      TEXT
        payment_method     TEXT     -- nullable, only meaningful for receipts/invoices
        amount             REAL     -- nullable
        date               TEXT     -- ISO 8601, the document's own date (e.g. invoice date)
        import_date        TEXT     -- ISO 8601, when the document was originally scanned/imported
                                     -- into Mariner Paperless (NULL for documents captured directly
                                     -- in the new app, where created_at already covers this)
        notes              TEXT
        ocr_text           TEXT
        ocr_language       TEXT     -- 'deu' / 'eng' / 'auto' / NULL (unknown, pre-migration)
        file_path          TEXT     -- relative to library root, e.g. "files/1_invoice.pdf"
        original_file_path TEXT     -- relative to library root, NULL if there's no separate
                                     -- original (e.g. the document was scanned directly, so the
                                     -- processed file IS the source). When present, it lives in a
                                     -- subfolder next to the processed file -- same layout Mariner
                                     -- used -- e.g. "files/1_invoice/original_scan.pdf"
        created_at         TEXT     -- ISO 8601, when the record was created in the NEW library
        source             TEXT     -- 'migrated' or 'captured'
        source_legacy_id   INTEGER  -- original ZRECEIPT.Z_PK, for traceability only

    tags
        id     INTEGER PRIMARY KEY
        name   TEXT UNIQUE

    document_tags
        document_id  INTEGER
        tag_id       INTEGER
        PRIMARY KEY (document_id, tag_id)

Deliberately dropped from the old schema: subcategory, custom1-6, shipping/
tax/tip amounts, collections, payment-method-as-a-separate-table, in_trash/
in_inbox flags. If you relied on any of those, the full detail is still in
export.json from export_paperless.py -- this migration is meant to produce a
clean go-forward archive, not a lossless mirror. Nothing here modifies the
original .paperless library, so it's always still there as the source of
truth if you need something this migration didn't carry over.
"""

import argparse
import datetime
import shutil
import sqlite3
import sys
from pathlib import Path

CORE_DATA_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01

NEW_SCHEMA = """
CREATE TABLE documents (
    id                INTEGER PRIMARY KEY,
    title             TEXT,
    category          TEXT,
    document_type     TEXT,
    payment_method    TEXT,
    amount            REAL,
    date              TEXT,
    import_date       TEXT,
    notes             TEXT,
    ocr_text          TEXT,
    ocr_language      TEXT,
    file_path         TEXT,
    original_file_path TEXT,
    created_at        TEXT,
    source            TEXT,
    source_legacy_id  INTEGER
);

CREATE TABLE tags (
    id    INTEGER PRIMARY KEY,
    name  TEXT UNIQUE
);

CREATE TABLE document_tags (
    document_id  INTEGER,
    tag_id       INTEGER,
    PRIMARY KEY (document_id, tag_id)
);
"""


def coredata_to_iso(value):
    if value is None:
        return None
    try:
        dt = datetime.datetime.fromtimestamp(
            float(value) + CORE_DATA_EPOCH_OFFSET, tz=datetime.timezone.utc
        )
        return dt.isoformat()
    except (ValueError, OSError, OverflowError):
        return None


def safe_filename(name: str, fallback: str) -> str:
    if not name:
        name = fallback
    cleaned = "".join(c if (c.isalnum() or c in "-_. ()") else "_" for c in name)
    cleaned = cleaned.strip().strip(".")
    return cleaned or fallback


def find_database(library_path: Path) -> Path:
    candidates = list(library_path.glob("*.documentwalletsql"))
    if not candidates:
        candidates = list(library_path.rglob("*.documentwalletsql"))
    if not candidates:
        sys.exit(f"ERROR: no .documentwalletsql database found under {library_path}")
    return candidates[0]


def original_relpath(receipt_path: str, original_filename: str):
    if not original_filename or not receipt_path:
        return None
    p = Path(receipt_path)
    stem_folder = p.with_suffix("")
    return str(stem_folder / original_filename)


def build_lookup(cur, table, name_col="ZNAME"):
    cur.execute(f"SELECT Z_PK, {name_col} FROM {table}")
    return {row[0]: row[1] for row in cur.fetchall()}


def main():
    ap = argparse.ArgumentParser(description="Migrate a Mariner Paperless library into the new clean-schema library.")
    ap.add_argument("library", help="Path to the old .paperless package")
    ap.add_argument("output", help="Path to the new library folder (will be created)")
    ap.add_argument("--include-trash", action="store_true", help="Include documents marked as in-trash (excluded by default)")
    args = ap.parse_args()

    old_library = Path(args.library).expanduser().resolve()
    new_library = Path(args.output).expanduser().resolve()
    if not old_library.exists():
        sys.exit(f"ERROR: library not found: {old_library}")

    db_path = find_database(old_library)
    print(f"Reading old database: {db_path}")

    files_dir = new_library / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    new_db_path = new_library / "library.sqlite"
    if new_db_path.exists():
        sys.exit(f"ERROR: {new_db_path} already exists. Refusing to overwrite an existing new library.")

    old_con = sqlite3.connect(str(db_path))
    old_cur = old_con.cursor()

    new_con = sqlite3.connect(str(new_db_path))
    new_cur = new_con.cursor()
    new_cur.executescript(NEW_SCHEMA)

    categories = build_lookup(old_cur, "ZCATEGORY")
    datatypes = build_lookup(old_cur, "ZDATATYPE")
    payment_methods = build_lookup(old_cur, "ZPAYMENTMETHOD")
    tags = build_lookup(old_cur, "ZTAG")

    tag_links = {}
    old_cur.execute("SELECT Z_14RECEIPTS1, Z_18TAGS FROM Z_14TAGS")
    for receipt_id, tag_id in old_cur.fetchall():
        tag_links.setdefault(receipt_id, []).append(tags.get(tag_id))

    old_cur.execute("""
        SELECT Z_PK, ZINTRASHVALUE, ZCATEGORY, ZDATATYPE, ZPAYMENTMETHOD,
               ZAMOUNT, ZDATE, ZIMPORTDATE, ZMERCHANT, ZNOTES, ZOCRRESULT,
               ZORIGINALFILENAME, ZPATH
        FROM ZRECEIPT
    """)
    columns = [d[0] for d in old_cur.description]
    rows = old_cur.fetchall()
    print(f"Found {len(rows)} documents in the old library.")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tag_name_to_id = {}
    migrated = 0
    skipped_no_file = 0
    missing_original = 0

    for row in rows:
        rec = dict(zip(columns, row))
        legacy_id = rec["Z_PK"]

        if rec["ZINTRASHVALUE"] and not args.include_trash:
            continue

        processed_rel = rec["ZPATH"]
        original_filename = rec["ZORIGINALFILENAME"]

        processed_src = None
        if processed_rel:
            candidate = old_library / processed_rel
            if candidate.exists():
                processed_src = candidate

        original_src = None
        if original_filename and processed_rel:
            orig_rel = original_relpath(processed_rel, original_filename)
            candidate = old_library / orig_rel
            if candidate.exists():
                original_src = candidate
            else:
                missing_original += 1
                print(f"  [missing original] expected but not found for legacy id={legacy_id}: {orig_rel}", file=sys.stderr)

        # Primary file: prefer the processed PDF; fall back to the original if
        # the processed one is missing (matches export_paperless.py's behavior).
        primary_src = processed_src or original_src
        if primary_src is None:
            skipped_no_file += 1
            print(f"  [skip] no file found on disk for legacy id={legacy_id}", file=sys.stderr)
            continue

        new_cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM documents")
        new_id = new_cur.fetchone()[0]

        dest_name = f"{new_id}_{safe_filename(primary_src.name, 'document.pdf')}"
        dest = files_dir / dest_name
        shutil.copy2(primary_src, dest)

        # If there's a genuinely separate original (i.e. we used the processed
        # file as primary AND a distinct original exists), copy it into a
        # subfolder next to the processed file -- mirroring the layout Mariner
        # itself used (subfolder named after the processed file's stem).
        original_dest_relpath = None
        if primary_src is processed_src and original_src is not None:
            original_subdir = files_dir / dest.stem
            original_subdir.mkdir(exist_ok=True)
            original_dest_name = safe_filename(original_src.name, 'original')
            original_dest = original_subdir / original_dest_name
            shutil.copy2(original_src, original_dest)
            original_dest_relpath = f"files/{dest.stem}/{original_dest_name}"

        title = rec["ZMERCHANT"] or categories.get(rec["ZCATEGORY"]) or datatypes.get(rec["ZDATATYPE"]) or f"Document {legacy_id}"

        new_cur.execute("""
            INSERT INTO documents (id, title, category, document_type, payment_method,
                                    amount, date, import_date, notes, ocr_text, ocr_language,
                                    file_path, original_file_path, created_at, source, source_legacy_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_id, title, categories.get(rec["ZCATEGORY"]), datatypes.get(rec["ZDATATYPE"]),
            payment_methods.get(rec["ZPAYMENTMETHOD"]), rec["ZAMOUNT"], coredata_to_iso(rec["ZDATE"]),
            coredata_to_iso(rec["ZIMPORTDATE"]),
            rec["ZNOTES"], rec["ZOCRRESULT"], None,
            f"files/{dest_name}", original_dest_relpath, now_iso, "migrated", legacy_id,
        ))

        for tag_name in tag_links.get(legacy_id, []):
            if not tag_name:
                continue
            if tag_name not in tag_name_to_id:
                new_cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
                new_cur.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                tag_name_to_id[tag_name] = new_cur.fetchone()[0]
            new_cur.execute(
                "INSERT OR IGNORE INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (new_id, tag_name_to_id[tag_name]),
            )

        migrated += 1

    new_con.commit()
    new_con.close()
    old_con.close()

    print(f"\nDone.")
    print(f"  Migrated:            {migrated}")
    print(f"  Skipped (no file):   {skipped_no_file}")
    print(f"  Missing originals:   {missing_original} (processed file was found, but its separate original was not)")
    print(f"  New library:         {new_library}")
    print(f"  Database:            {new_db_path}")
    print(f"  Files:               {files_dir}")


if __name__ == "__main__":
    main()
