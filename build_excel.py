"""
build_excel.py
==============
Turn output/rmi_raw.json (the payload the GitHub Actions workflow fetches from
the Israel Land Authority API, apps.land.gov.il/MichrazimSite/api) into a
formatted Excel workbook.

Every value comes from that payload. Fields the API leaves empty are written
as "לא זמין" rather than guessed.

Run:  pip install pandas openpyxl && python3 build_excel.py
"""

import json
import os
import re
import urllib.request

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

NA = "לא זמין"

CATEGORY_HE = {
    "mechir_lemishtaken": "מחיר למשתכן",
    "yazamot": "יזמות",
    # The workflow filters this bucket on KodYeudMichraz 4/6/7, assumed to mean
    # hotels. The rows that come back are industrial and employment-zone plots,
    # so they are labelled for what they are until the hotel code is confirmed.
    "malonaut": "תעשייה/מסחר",
}

# RMI puts status messages in the winner field instead of a bidder name.
STATUS_MARKERS = ("הצעות לא תקינות", "אין הצעות", "המציע זכה במתחם אחר",
                  "הצעות לא בטווח", "לא נתקבלו הצעות")

# RMI writes company names with inconsistent quoting (בע"מ, בע״מ, בע''''מ), and
# many firms carry no ltd marker at all. A name counts as a company on any of:
# an ltd marker, an organisation word, or a line-of-business word.
_QUOTES = re.compile(r"['\"״׳`’‘“”]+")
_LTD = re.compile(r'בע\s*"?\s*[מם]\b')
_ORG = re.compile(r'\b(חברה|שותפות|אגודה|עמותה|קיבוץ|מושב|קבוצת|רשת)\b')
_BIZ = re.compile(
    r'\b(הנדסה|יזמות|ייזום|יזום|נדלן|נדל"ן|השקעות|אחזקות|החזקות|פיתוח|בניה|'
    r'בנייה|בנין|בניין|תעשיות|נכסים|מגורים|קבלנות|תשתיות|ליסינג|מלונות|'
    r'מלונאות|תיירות|סחר|מסחר|הובלות|שרותים|שירותים|ניהול|תכנון|קבלן|'
    r'בונה|בוני|מרכזי)\b')

# Individuals below this are housing-lottery winners; above it they bought land
# outright, so they get their own sheet instead of being dropped.
INDIVIDUAL_KEEP_FROM = 3_000_000

COLUMNS = ["מספר מכרז", "תאריך ועדה", "עיר", "שכונה", "שם הזוכה", "סוג זוכה",
           "סכום זכייה (₪)", "הוצאות פיתוח (₪)", "עלות כוללת (₪)",
           "יח\"ד במכרז", "שטח מגרש (מ\"ר)", "גוש/חלקה",
           "קטגוריה", "סטטוס", "קישור למכרז"]
MONEY = {"סכום זכייה (₪)", "הוצאות פיתוח (₪)", "עלות כוללת (₪)", "סך זכייה (₪)"}


def is_company(name):
    n = _QUOTES.sub('"', name)
    return bool(_LTD.search(n) or _ORG.search(n) or _BIZ.search(n))


def load_city_names():
    """KodYeshuv -> city name, from the public remy-mcp reference table."""
    url = "https://raw.githubusercontent.com/barvhaim/remy-mcp/master/data/kod_yeshuv.py"
    ns = {}
    exec(urllib.request.urlopen(url, timeout=20).read().decode("utf-8"), ns)
    return ns["KOD_YESHUV_MAPPING"]


def num(v):
    return v if isinstance(v, (int, float)) and v != 0 else NA


def build_rows(raw, cities):
    rows = []
    for key, body in raw["categories"].items():
        for entry in body["tenders"]:
            b, det = entry["basic"], entry["details"]
            base = {
                "מספר מכרז": b.get("MichrazName") or NA,
                "תאריך ועדה": (b.get("VaadaDate") or "")[:10] or NA,
                "עיר": cities.get(b.get("KodYeshuv"), NA),
                "שכונה": (b.get("Shchuna") or "").strip() or NA,
                "יח\"ד במכרז": num(b.get("YechidotDiur")),
                "קטגוריה": CATEGORY_HE.get(key, key),
                "קישור למכרז": f"https://apps.land.gov.il/MichrazimSite/#/michraz/{b.get('MichrazID', '')}",
            }
            tiks = det.get("Tik") or []
            if not tiks:
                rows.append({**base, "שם הזוכה": NA, "סוג זוכה": NA, "סכום זכייה (₪)": NA,
                             "הוצאות פיתוח (₪)": NA, "עלות כוללת (₪)": NA,
                             "שטח מגרש (מ\"ר)": NA, "גוש/חלקה": NA,
                             "סטטוס": "ללא פירוט מגרשים"})
                continue
            for tik in tiks:
                winner = (tik.get("ShemZoche") or "").strip()
                amount, dev = num(tik.get("SchumZchiya")), num(tik.get("HotzaotPituach"))
                total = (amount + dev if isinstance(amount, (int, float)) and isinstance(dev, (int, float))
                         else amount)
                gush = ", ".join(f"{g.get('Gush', '')}/{g.get('Helka', '')}"
                                 for g in tik.get("GushHelka") or []) or NA
                if not winner:
                    status, kind = "ללא זוכה", NA
                elif any(m in winner for m in STATUS_MARKERS):
                    status, kind = "הודעת מערכת", NA
                else:
                    status, kind = "זוכה", ("חברה" if is_company(winner) else "פרטי")
                rows.append({**base, "שם הזוכה": winner or NA, "סוג זוכה": kind,
                             "סכום זכייה (₪)": amount, "הוצאות פיתוח (₪)": dev,
                             "עלות כוללת (₪)": total, "שטח מגרש (מ\"ר)": num(tik.get("Shetach")),
                             "גוש/חלקה": gush, "סטטוס": status})
    return rows


def developer_table(df):
    real = df[df["סוג זוכה"] == "חברה"].copy()
    real["_amt"] = pd.to_numeric(real["סכום זכייה (₪)"], errors="coerce")
    g = real.groupby("שם הזוכה").agg(**{
        "מספר זכיות": ("שם הזוכה", "size"),
        "סך זכייה (₪)": ("_amt", "sum"),
        "ערים": ("עיר", lambda s: ", ".join(sorted({x for x in s if x != NA})) or NA),
        "קטגוריות": ("קטגוריה", lambda s: ", ".join(sorted(set(s)))),
    }).reset_index().sort_values(["מספר זכיות", "סך זכייה (₪)"], ascending=[False, False])
    g["סך זכייה (₪)"] = g["סך זכייה (₪)"].fillna(0).round(0)
    return g.reset_index(drop=True)


def summary_table(raw, df, companies, big_individuals, dropped):
    amt = pd.to_numeric(companies["סכום זכייה (₪)"], errors="coerce")
    return pd.DataFrame([
        ("מקור הנתונים", "רשות מקרקעי ישראל — apps.land.gov.il/MichrazimSite/api"),
        ("תאריך שליפה", raw["fetched_at"][:19].replace("T", " ")),
        ("טווח תאריכי ועדה", f'{raw["date_from"]} — {raw["date_to"]}'),
        ("מכרזים עם תוצאות במאגר רמ\"י (כל השנים)", raw["total_with_results"]),
        ("מתוכם בטווח התאריכים", raw["total_in_date_range"]),
        ("מכרזים שנשלפו במלואם", sum(len(b["tenders"]) for b in raw["categories"].values())),
        ("שורות שנשלפו (מגרש × זוכה)", len(df)),
        ("— מתוכן זכיות של חברות", len(companies)),
        ("— יחידים בסכום גבוה (גיליון נפרד)", len(big_individuals)),
        ("— זוכי הגרלה פרטיים שסוננו", dropped),
        ("חברות: מחיר למשתכן", int((companies["קטגוריה"] == "מחיר למשתכן").sum())),
        ("חברות: יזמות", int((companies["קטגוריה"] == "יזמות").sum())),
        ("חברות: תעשייה/מסחר", int((companies["קטגוריה"] == "תעשייה/מסחר").sum())),
        ("חברות ייחודיות", companies["שם הזוכה"].nunique()),
        ("סך זכיות החברות (₪)", round(float(amt.sum()))),
    ], columns=["מדד", "ערך"])


def format_sheet(ws, df):
    ws.sheet_view.rightToLeft = True
    ws.freeze_panes = "A2"
    for i, col in enumerate(df.columns, start=1):
        cell = ws.cell(row=1, column=i)
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        width = max([len(str(col))] + [len(str(v)) for v in df[col].head(300)])
        ws.column_dimensions[get_column_letter(i)].width = min(max(width + 2, 11), 42)
        if col in MONEY:
            for r in range(2, ws.max_row + 1):
                ws.cell(row=r, column=i).number_format = "#,##0"
    if len(df):
        ws.auto_filter.ref = ws.dimensions


def main():
    raw = json.load(open("output/rmi_raw.json", encoding="utf-8"))
    df = pd.DataFrame(build_rows(raw, load_city_names()), columns=COLUMNS)
    companies = df[df["סוג זוכה"] == "חברה"]
    individuals = df[df["סוג זוכה"] == "פרטי"]
    amt = pd.to_numeric(individuals["סכום זכייה (₪)"], errors="coerce")
    big = individuals[amt >= INDIVIDUAL_KEEP_FROM].sort_values("סכום זכייה (₪)", ascending=False)
    sheets = {
        "סיכום": summary_table(raw, df, companies, big, len(individuals) - len(big)),
        "כל הזכיות (חברות)": companies,
        "מחיר למשתכן": companies[companies["קטגוריה"] == "מחיר למשתכן"],
        "יזמות": companies[companies["קטגוריה"] == "יזמות"],
        "תעשייה-מסחר": companies[companies["קטגוריה"] == "תעשייה/מסחר"],
        "ניתוח יזמים": developer_table(df),
        "יחידים בסכום גבוה": big,
    }
    path = "output/מכרזי_רמי_2024-2026.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, sheet in sheets.items():
            sheet.to_excel(xl, sheet_name=name, index=False)
            format_sheet(xl.book[name], sheet)
    print(f"{path}  ({os.path.getsize(path):,} bytes)")
    for name, sheet in sheets.items():
        print(f"  {name}: {len(sheet)} rows")


if __name__ == "__main__":
    main()
