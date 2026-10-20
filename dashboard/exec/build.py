"""
build.py
========
Builds the developer comparison dashboard (dashboard/exec/index.html) from
dashboard/data.json: one row per lot per company, for the seven companies with
the largest winnings (including development costs) among those that won in both
of the last two 12-month periods. A joint bid gives a row to each partner,
marked joint; solo totals leave joint lots out.

Usage:  python3 dashboard/exec/build.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data.json"
PERIODS = (("P1", "2024-10-19"), ("P2", "2025-10-19"), ("P3", "2026-10-19"))


def period(day):
    return next(p for p, end in PERIODS if day <= end)


# Words that describe the business rather than name it; dropped for chart labels.
GENERIC = ("חברה לבנין", "חברה לבניין", "הנדסה בניה והשקעות", "הנדסה בנייה והשקעות", "יזמות והשקעות",
           "בניה ופיתוח", "פיתוח וייזום", "יזום", ' בע"מ', " בעמ", " בע''''מ")


def short(name):
    for s in GENERIC:
        name = name.replace(s, "")
    return " ".join(name.split()).rstrip(".")


def rnd(v, n=4):
    return round(v, n) if isinstance(v, (int, float)) else v


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    lots = [l for l in data["lots"] if l["kind"] == "חברה" and not l["duplicate_of"]]
    tot, seen = {}, {}
    for l in lots:
        if l["joint"]:
            continue
        p = l["partners"][0]
        tot[p] = tot.get(p, 0) + l["total_cost"]
        seen.setdefault(p, set()).add(period(l["date"]))
    chosen = sorted((p for p in tot if {"P2", "P3"} <= seen[p]), key=lambda p: -tot[p])[:7]
    rows = []
    for l in lots:
        for p in l["partners"]:
            if p not in chosen:
                continue
            rows.append({
                "developer": short(p), "joint": l["joint"], "partners": ", ".join(short(x) for x in l["partners"]),
                "period": period(l["date"]), "date": l["date"], "tender": l["tender"], "tender_type": l["tender_type"],
                "market": l["market"], "region": l["region"], "place": l["place"],
                "win_m": rnd(l["win"] / 1e6), "dev_m": rnd((l["dev"] or 0) / 1e6), "total_m": rnd(l["total_cost"] / 1e6),
                "appraisal_m": rnd(l["appraisal"] / 1e6) if l["appraisal"] else None,
                "vs_appraisal_pct": rnd(l["vs_appraisal_pct"], 2), "runner_up_m": rnd(l["runner_up"] / 1e6) if l["runner_up"] else None,
                "gap_pct": rnd(l["gap_pct"], 2), "bids": l["bidders"], "units": l["units_attributed"],
                "reserve_of_appraisal_pct": rnd(l["reserve_of_appraisal_pct"], 4), "max_lots_per_bidder": l["max_to_win"],
                "url": l["url"],
            })
    rows.sort(key=lambda r: (r["developer"], r["date"]))
    meta = {"fetched": data["meta"]["fetched"], "date_from": data["meta"]["date_from"], "date_to": data["meta"]["date_to"],
            "tenders_in_range": data["meta"]["tenders_in_range"], "tenders_fetched": data["meta"]["tenders_fetched"]}
    (ROOT / "developer_lots.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    page = (ROOT / "template.html").read_text(encoding="utf-8")
    payload = json.dumps({"lots": rows, "meta": meta}, ensure_ascii=False).replace("</", "<\\/")
    (ROOT / "index.html").write_text(page.replace("__DATA__", payload), encoding="utf-8")
    print(len(rows), "rows;", ", ".join(short(p) for p in chosen))


if __name__ == "__main__":
    main()
