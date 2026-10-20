import os as _os
_os.chdir(_os.path.dirname(_os.path.abspath(__file__)))  # so relative paths (dossiary.html, stub_studio2.js) work regardless of the CWD

import os as _os2
APP_PATH = _os2.path.abspath(_os2.path.join('..', 'dossiary.html'))

# Writes smart-rule-cases.json for the iPhone app (dossiary-ios): a small
# library, many Smart Collection criteria (both stored formats), and the ids
# the real JavaScript matches for each -- so the Swift port can be checked
# against it. Not part of the suite. Usage:
#   python3 export_smart_rule_cases.py [output.json]
# Default output: ../../dossiary-ios/DossiaryCore/Tests/DossiaryCoreTests/Fixtures/smart-rule-cases.json

import asyncio, json, re, sys
from datetime import date, timedelta
from playwright.async_api import async_playwright

OUT = sys.argv[1] if len(sys.argv) > 1 else _os2.path.abspath(_os2.path.join(
    '..', '..', 'dossiary-ios', 'DossiaryCore', 'Tests', 'DossiaryCoreTests', 'Fixtures', 'smart-rule-cases.json'))

T = date.today()  # the same local day the page's todayIsoDate() returns (checked below)
def iso(d): return d.isoformat() + "T00:00:00+00:00"
LAST_MONTH_FIRST = (T.replace(day=1) - timedelta(days=1)).replace(day=1)
THIS_YEAR_JAN2 = T.replace(month=1, day=2)
LAST_YEAR_JUNE = date(T.year - 1, 6, 15)

def doc(i, title, **extra):
    d = {"id": i, "title": title, "category": None, "subcategory": None, "document_type": None,
         "date": None, "import_date": iso(T), "notes": None, "ocr_text": None, "ocr_language": None,
         "file_path": None, "original_file_path": None, "created_at": "2026-01-01T00:00:00+00:00",
         "source": "captured", "source_legacy_id": None, "archived": 0, "needs_review": 0, "deleted": 0}
    d.update(extra)
    return d

SEED = {
    "documents": [
        doc(1, "Hotel Berlin", category="Travel", subcategory="Hotel", document_type="Invoice", date=iso(T - timedelta(days=5)),
            import_date=iso(T - timedelta(days=4)), notes="Business trip", ocr_text="Grand Hotel Berlin total 120,00 EUR"),
        doc(2, "Train", category="Travel", document_type="Ticket", date=iso(T - timedelta(days=40)), import_date=iso(T - timedelta(days=39))),
        doc(3, "Groceries", category="Food", archived=1, date=iso(LAST_YEAR_JUNE)),
        doc(4, "Letter", needs_review=1, notes="important contract"),
        doc(5, "Old ticket", category="Travel", deleted=1, date=iso(T - timedelta(days=5))),
        doc(6, "Electricity", category="Home", document_type="Invoice", date=iso(LAST_MONTH_FIRST)),
        doc(7, "Dentist", category="Health", date=iso(THIS_YEAR_JAN2)),
    ],
    "tags": [{"id": 1, "name": "trip"}, {"id": 2, "name": "tax"}, {"id": 3, "name": "rail"}],
    "document_tags": [
        {"document_id": 1, "tag_id": 1}, {"document_id": 1, "tag_id": 2}, {"document_id": 2, "tag_id": 1},
        {"document_id": 2, "tag_id": 3}, {"document_id": 6, "tag_id": 2},
    ],
    "people": [{"id": 1, "name": "Arne"}, {"id": 2, "name": "Jana"}],
    "fields": [
        {"id": 1, "name": "People", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 2, "name": "Amount", "type": "number", "show_as_column": 0, "autocomplete": 0},
        {"id": 3, "name": "Currency", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 4, "name": "Payment method", "type": "text", "show_as_column": 1, "autocomplete": 1},
        {"id": 5, "name": "Reminder", "type": "reminder", "show_as_column": 0, "autocomplete": 0},
        {"id": 10, "name": "Organization", "type": "text", "show_as_column": 0, "autocomplete": 1},
        {"id": 11, "name": "Paid", "type": "checkbox", "show_as_column": 0, "autocomplete": 0},
        {"id": 12, "name": "Author", "type": "person", "show_as_column": 0, "autocomplete": 0},
        {"id": 13, "name": "Due", "type": "date", "show_as_column": 0, "autocomplete": 0},
    ],
    "document_field_values": [
        {"document_id": 1, "field_id": 2, "value": "120"}, {"document_id": 1, "field_id": 3, "value": "EUR"},
        {"document_id": 1, "field_id": 11, "value": "1"}, {"document_id": 1, "field_id": 10, "value": "Grand Hotel"},
        {"document_id": 1, "field_id": 13, "value": (T + timedelta(days=10)).isoformat()},
        {"document_id": 2, "field_id": 2, "value": "30.5"}, {"document_id": 2, "field_id": 11, "value": "0"},
        {"document_id": 3, "field_id": 2, "value": "55"}, {"document_id": 3, "field_id": 3, "value": "EUR"},
        {"document_id": 4, "field_id": 10, "value": "Insurance AG"},
        {"document_id": 6, "field_id": 2, "value": "73.50"}, {"document_id": 6, "field_id": 3, "value": "EUR"},
        {"document_id": 6, "field_id": 4, "value": "Direct debit"},
        {"document_id": 6, "field_id": 5, "value": (T + timedelta(days=3)).isoformat()},
        {"document_id": 7, "field_id": 2, "value": "0"}, {"document_id": 7, "field_id": 11, "value": "1"},
        {"document_id": 7, "field_id": 10, "value": ""}, {"document_id": 7, "field_id": 13, "value": ""},
    ],
    "document_field_people": [
        {"document_id": 1, "field_id": 1, "person_id": 1}, {"document_id": 2, "field_id": 1, "person_id": 2},
        {"document_id": 2, "field_id": 12, "person_id": 1},
        {"document_id": 6, "field_id": 1, "person_id": 1}, {"document_id": 6, "field_id": 1, "person_id": 2},
    ],
    "document_splits": [
        {"document_id": 3, "position": 0, "category": "Household", "amount": "20.00", "note": ""},
        {"document_id": 6, "position": 0, "category": "Office", "amount": "10.00", "note": "printer"},
    ],
    "settings": [{"key": "text_autocomplete_default_migrated", "value": "1"}],
}

def d(n): return (T + timedelta(days=n)).isoformat()

def rules(*rs, match="all"):
    return {"match": match, "rules": [dict(zip(("field", "op", "value", "value2"), r)) for r in rs]}

RULE_CASES = [
    ("any contains", rules(("any", "contains", "berlin"))),
    ("any not_contains", rules(("any", "not_contains", "trip"))),
    ("any contains empty", rules(("any", "contains", ""))),
    ("any not_contains empty", rules(("any", "not_contains", ""))),
    ("title is (case)", rules(("title", "is", "train"))),
    ("title is_not", rules(("title", "is_not", "Train"))),
    ("title contains", rules(("title", "contains", "o"))),
    ("title not_contains", rules(("title", "not_contains", "e"))),
    ("notes not_empty", rules(("notes", "not_empty"))),
    ("notes empty", rules(("notes", "empty"))),
    ("category is", rules(("category", "is", "travel"))),
    ("category is_not", rules(("category", "is_not", "Travel"))),
    ("category contains", rules(("category", "contains", "o"))),
    ("category not_contains", rules(("category", "not_contains", "o"))),
    ("category empty", rules(("category", "empty"))),
    ("category not_empty", rules(("category", "not_empty"))),
    ("category is split", rules(("category", "is", "Household"))),
    ("category is_not split", rules(("category", "is_not", "Office"))),
    ("subcategory is", rules(("subcategory", "is", "Hotel"))),
    ("document_type is", rules(("document_type", "is", "invoice"))),
    ("ocr_text contains", rules(("ocr_text", "contains", "120,00"))),
    ("tags includes", rules(("tags", "includes", "TRIP"))),
    ("tags excludes", rules(("tags", "excludes", "tax"))),
    ("tags empty", rules(("tags", "empty"))),
    ("tags not_empty", rules(("tags", "not_empty"))),
    ("date on", rules(("date", "on", d(-5)))),
    ("date before", rules(("date", "before", d(-30)))),
    ("date after", rules(("date", "after", d(-30)))),
    ("date between", rules(("date", "between", d(-50), d(-1)))),
    ("date last_days", rules(("date", "last_days", "30"))),
    ("date last_days invalid", rules(("date", "last_days", "x"))),
    ("date this_month", rules(("date", "this_month"))),
    ("date last_month", rules(("date", "last_month"))),
    ("date this_year", rules(("date", "this_year"))),
    ("date last_year", rules(("date", "last_year"))),
    ("date empty", rules(("date", "empty"))),
    ("date not_empty", rules(("date", "not_empty"))),
    ("import_date on", rules(("import_date", "on", d(0)))),
    ("import_date last_days", rules(("import_date", "last_days", "7"))),
    ("amount is", rules(("field:2", "is", "120"))),
    ("amount is number", rules(("field:2", "is", 120))),
    ("amount is_not", rules(("field:2", "is_not", "120"))),
    ("amount gte", rules(("field:2", "gte", "50"))),
    ("amount lte", rules(("field:2", "lte", "50"))),
    ("amount between", rules(("field:2", "between", "30", "60"))),
    ("amount empty", rules(("field:2", "empty"))),
    ("amount not_empty", rules(("field:2", "not_empty"))),
    ("amount is NaN", rules(("field:2", "is", "abc"))),
    ("amount is_not NaN", rules(("field:2", "is_not", "abc"))),
    ("paid checked", rules(("field:11", "checked"))),
    ("paid unchecked", rules(("field:11", "unchecked"))),
    ("paid empty", rules(("field:11", "empty"))),
    ("people includes", rules(("field:1", "includes", "arne"))),
    ("people excludes", rules(("field:1", "excludes", "Jana"))),
    ("people empty", rules(("field:1", "empty"))),
    ("people not_empty", rules(("field:1", "not_empty"))),
    ("author includes", rules(("field:12", "includes", "Arne"))),
    ("due after", rules(("field:13", "after", d(0)))),
    ("due on", rules(("field:13", "on", d(10)))),
    ("due empty", rules(("field:13", "empty"))),
    ("reminder not_empty", rules(("field:5", "not_empty"))),
    ("reminder before", rules(("field:5", "before", d(5)))),
    ("organization contains", rules(("field:10", "contains", "ag"))),
    ("organization is empty string", rules(("field:10", "is", ""))),
    ("organization empty", rules(("field:10", "empty"))),
    ("missing field empty", rules(("field:99", "empty"))),
    ("missing field is", rules(("field:99", "is", "x"))),
    ("status archived", rules(("status", "archived"))),
    ("status not_archived", rules(("status", "not_archived"))),
    ("status in_review", rules(("status", "in_review"))),
    ("status not_in_review", rules(("status", "not_in_review"))),
    ("match any", rules(("category", "is", "Food"), ("tags", "includes", "rail"), match="any")),
    ("match all", rules(("category", "is", "Travel"), ("field:2", "gte", "100"))),
    ("no rules", {"match": "all", "rules": []}),
]

BASE = {"q": "", "category": "", "type": "", "person": "", "showArchived": False, "dynamic": [],
        "amountMin": "", "amountMax": "", "amountUnset": False}
def snap(**changes): return {**BASE, **changes}
SNAPSHOT_CASES = [
    ("snapshot q", snap(q="hotel")),
    ("snapshot category", snap(category="Travel")),
    ("snapshot category split", snap(category="Household")),
    ("snapshot category unset", snap(category="__unset__")),
    ("snapshot type", snap(type="Invoice")),
    ("snapshot type unset", snap(type="__unset__")),
    ("snapshot person", snap(person="Arne")),
    ("snapshot person unset", snap(person="__unset__")),
    ("snapshot checkbox", snap(dynamic=[{"label": "Paid", "value": "1"}])),
    ("snapshot checkbox unset", snap(dynamic=[{"label": "Paid", "value": "__unset__"}])),
    ("snapshot person field", snap(dynamic=[{"label": "Author", "value": "Arne"}])),
    ("snapshot person field unset", snap(dynamic=[{"label": "Author", "value": "__unset__"}])),
    ("snapshot amount min", snap(amountMin="50")),
    ("snapshot amount max", snap(amountMax="50")),
    ("snapshot amount range", snap(amountMin="20", amountMax="100")),
    ("snapshot amount unset", snap(amountUnset=True)),
    ("snapshot old shape", {"category": "Travel", "dynamic": []}),
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        async def route_handler(route):
            url = route.request.url
            if 'sql-wasm.js' in url or 'tesseract' in url or 'jspdf' in url or 'pdf.js' in url:
                await route.fulfill(body="/* stubbed */", content_type='application/javascript')
            else:
                await route.continue_()
        await page.route('**/*', route_handler)
        await page.add_init_script(open('stub_studio2.js').read())
        await page.goto(f"file://{APP_PATH}")
        await page.wait_for_timeout(200)
        await page.evaluate(f"window.__TEST_ROOT = window.__makeSeededRoot({json.dumps(SEED)}); window.__TEST_ROOT.name = 'Cases';")
        await page.click("#open-btn")
        await page.wait_for_timeout(600)
        today = await page.evaluate("() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }")
        assert today == T.isoformat(), (today, T)
        tables = await page.evaluate("async () => JSON.parse(await (await (await window.__TEST_ROOT.getFileHandle('library.sqlite')).getFile()).text())")
        cases = []
        for name, criteria in RULE_CASES + SNAPSHOT_CASES:
            expected = await page.evaluate("(c) => window.__DEBUG_smartMatchIds(c)", criteria)
            cases.append({"name": name, "criteria": criteria, "expected": expected})
        await browser.close()
        # A page error may have made some expectations wrong: never write
        # them over a good fixture.
        if errors:
            print("JS ERRORS:", errors)
            print(f"Not writing {OUT}.")
            return 1
        version = re.search(r"const APP_VERSION = '([^']+)'", open(APP_PATH, encoding='utf-8').read()).group(1)
        out = {"generatedFrom": f"dossiary.html {version}", "today": today, "tables": tables, "cases": cases}
        _os2.makedirs(_os2.path.dirname(OUT), exist_ok=True)
        with open(OUT, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"Wrote {len(cases)} cases to {OUT}")
        print("JS ERRORS: []")
        return 0

sys.exit(asyncio.run(main()))
