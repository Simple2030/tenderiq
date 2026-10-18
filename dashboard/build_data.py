"""
build_data.py
=============
Turn output/rmi_raw.json (Israel Land Authority tender payload) into the data
the dashboard renders. Only values present in the source are used; nothing is
estimated or imputed.

Per lot (Tik) we keep: tender, committee date, city, neighbourhood, category,
winner, winning bid, reserve price, development costs, lot area, gush/helka,
and every bid placed on the lot.

Derived metrics, each computed only when its inputs exist in the source:
  bidders            number of bids on the lot (mpHatzaaotMitcham)
  vs_appraisal_pct   winning bid / land appraisal - 1       (needs mechirShuma)
  premium_pct        winning bid / reserve price - 1        (needs MechirSaf).
                     The reserve is published at a fraction of the appraisal
                     (median about a quarter), so this ratio says how low the
                     reserve was, not how hard bidders competed.
  win_rank           position of the winning bid among all bids, 1 = highest
  runner_up          the next bid below the winning bid; a second bid equal
                     to the winning bid counts, giving a 0% gap
  gap_pct            winning bid / runner_up - 1            (needs 2+ bids)
  top_not_winner     a bid higher than the winning bid exists on the lot.
                     The source marks the winning bid (HatzaaDescription=1)
                     but not why a higher bid lost. max_to_win records the
                     tender's cap on lots per bidder, when published.
  land_ppsqm         winning bid / lot area (Shetach), land only; left empty
                     for lots over 50,000 sqm (quarries, regional plots)

Lots are kept when the source gives a positive winning amount. Lots without one
are housing-lottery allocations (no price, no bids) or have no winner.
  dev_share_pct      development costs / (winning bid + development costs)

Usage:  python3 dashboard/build_data.py [raw.json] [out.json]
"""

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output" / "rmi_raw.json"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "dashboard" / "data.json"

CATEGORY_HE = {
    "mechir_lemishtaken": "מחיר למשתכן",
    "yazamot": "יזמות",
    # Fetched with land-use codes 4/6/7 on the assumption they meant hotels; the
    # lots returned are in industrial and employment zones.
    "malonaut": "תעשייה ומסחר",
}
STATUS_MARKERS = ("הצעות לא תקינות", "אין הצעות", "המציע זכה במתחם אחר",
                  "הצעות לא בטווח", "לא נתקבלו הצעות")

_QUOTES = re.compile(r"['\"״׳`’‘“”]+")
_LTD = re.compile(r'בע\s*"?\s*[מם]\b')
_ORG = re.compile(r'\b(חברה|שותפות|אגודה|עמותה|קיבוץ|מושב|קבוצת|רשת)\b|רשימת מציעים')
_BIZ = re.compile(
    r'\b(הנדסה|יזמות|ייזום|יזום|נדלן|נדל"ן|השקעות|אחזקות|החזקות|פיתוח|'
    r'בנייה|בנין|בניין|תעשיות|נכסים|מגורים|קבלנות|תשתיות|ליסינג|מלונות|'
    r'מלונאות|תיירות|מסחר|הובלות|שרותים|שירותים|ניהול|תכנון|קבלן|'
    r'בונה|בוני|מרכזי)\b')
MAX_AREA_FOR_PPSQM = 50_000  # larger lots are quarries or regional plots


def is_company(name):
    n = _QUOTES.sub('"', name)
    return bool(_LTD.search(n) or _ORG.search(n) or _BIZ.search(n))


def load_city_names():
    url = "https://raw.githubusercontent.com/barvhaim/remy-mcp/master/data/kod_yeshuv.py"
    ns = {}
    exec(urllib.request.urlopen(url, timeout=20).read().decode("utf-8"), ns)
    return ns["KOD_YESHUV_MAPPING"]


def pos(v):
    return v if isinstance(v, (int, float)) and v > 0 else None


GENERIC_AREAS = {"שלב א", "שלב ב", "שלב ג", "אזור תעשיה", "אזור תעשייה", 'אז"ת', "אזה\"ת"}


def place_name(code, hood, cities):
    """City name when the code is known. Otherwise the area name the tender
    gives (industrial zones and regional councils are missing from the code
    table), unless that name is generic, in which case the place is unknown."""
    city = cities.get(code)
    if city:
        return city.replace(")יישוב(", "").replace("(יישוב)", "").strip(), True
    if hood and hood not in GENERIC_AREAS:
        return hood, False
    return "יישוב לא מזוהה", False


def build(raw, cities):
    lots = []
    dropped = {"unpriced": 0, "system": 0, "no_winner": 0}
    for key, body in raw["categories"].items():
        for entry in body["tenders"]:
            b, det = entry["basic"], entry["details"]
            hood = (b.get("Shchuna") or "").strip() or None
            place, mapped = place_name(b.get("KodYeshuv"), hood, cities)
            for tik in det.get("Tik") or []:
                winner = (tik.get("ShemZoche") or "").strip()
                if not winner:
                    dropped["no_winner"] += 1
                    continue
                if any(m in winner for m in STATUS_MARKERS):
                    dropped["system"] += 1
                    continue
                win = pos(tik.get("SchumZchiya"))
                if not win:
                    dropped["unpriced"] += 1
                    continue
                raw_bids = [y for y in tik.get("mpHatzaaotMitcham") or [] if pos(y.get("HatzaaSum"))]
                bid_rows = sorted(({"sum": y["HatzaaSum"], "win": y.get("HatzaaDescription") == 1}
                                   for y in raw_bids), key=lambda r: -r["sum"])
                sums = [r["sum"] for r in bid_rows]
                others = list(sums)
                if win in others:
                    others.remove(win)          # the winning bid itself
                runner = max((x for x in others if x <= win), default=None)
                reserve = pos(tik.get("MechirSaf"))
                appraisal = pos(tik.get("mechirShuma"))
                dev = pos(tik.get("HotzaotPituach"))
                area = pos(tik.get("Shetach"))
                lots.append({
                    "id": f'{b.get("MichrazID")}-{tik.get("TikID")}',
                    "tender": b.get("MichrazName"),
                    "url": f'https://apps.land.gov.il/MichrazimSite/#/michraz/{b.get("MichrazID")}',
                    "date": (b.get("VaadaDate") or "")[:10] or None,
                    "place": place,
                    "place_is_city": mapped,
                    "hood": hood,
                    "cat": CATEGORY_HE.get(key, key),
                    "lot": (tik.get("MitchamName") or "").strip() or None,
                    "winner": winner,
                    "kind": "חברה" if is_company(winner) else "פרטי",
                    "win": win,
                    "reserve": reserve,
                    "appraisal": appraisal,
                    "dev": dev,
                    "area": area,
                    "tender_units": pos(b.get("YechidotDiur")),
                    "max_to_win": det.get("MaxToWin"),
                    "gush": ", ".join(f'{g.get("Gush", "")}/{g.get("Helka", "")}'
                                      for g in tik.get("GushHelka") or []) or None,
                    "bids": bid_rows,
                    "bidders": len(bid_rows) or None,
                    "win_rank": 1 + sum(1 for x in sums if x > win) if sums else None,
                    "vs_appraisal_pct": (win / appraisal - 1) * 100 if appraisal else None,
                    "premium_pct": (win / reserve - 1) * 100 if reserve else None,
                    "reserve_of_appraisal_pct": reserve / appraisal * 100 if reserve and appraisal else None,
                    "runner_up": runner,
                    "gap_pct": (win / runner - 1) * 100 if runner else None,
                    "top_not_winner": bool(sums and sums[0] > win),
                    "land_ppsqm": win / area if area and area <= MAX_AREA_FOR_PPSQM else None,
                    "dev_share_pct": dev / (win + dev) * 100 if dev else None,
                })
    # Guard against the source repeating a lot within a tender: same lot, winner,
    # amount, appraisal, area, development costs and bid list. Keep the first, flag the rest so they
    # stay visible but are left out of every statistic.
    seen = {}
    for lot in lots:
        key = (lot["tender"], lot["lot"], lot["winner"], lot["win"], lot["appraisal"],
               lot["area"], lot["dev"], tuple(b["sum"] for b in lot["bids"]))
        lot["duplicate_of"] = seen.get(key)
        seen.setdefault(key, lot["id"])
    # A lot offered again in a later tender (same place, lot and parcel):
    # both awards are real records; the earlier one likely did not close.
    by_parcel = {}
    for lot in lots:
        lot["retendered"] = False
        if lot["gush"]:
            by_parcel.setdefault((lot["place"], lot["lot"], lot["gush"]), []).append(lot)
    for group in by_parcel.values():
        tenders = {l["tender"] for l in group}
        for lot in group:
            lot["retendered"] = len(tenders) > 1
    meta = {
        "fetched": raw["fetched_at"][:10],
        "date_from": raw["date_from"],
        "date_to": raw["date_to"],
        "tenders_with_results_all_years": raw["total_with_results"],
        "tenders_in_range": raw["total_in_date_range"],
        "tenders_fetched": sum(len(b["tenders"]) for b in raw["categories"].values()),
        "dropped": dropped,
    }
    return {"meta": meta, "lots": lots}


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    data = build(raw, load_city_names())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    lots = data["lots"]
    print(f"{OUT}: {len(lots)} lots, "
          f"{sum(1 for l in lots if l['bidders'])} with bids, "
          f"{sum(1 for l in lots if l['vs_appraisal_pct'] is not None)} with appraisal, "
          f"dropped {data['meta']['dropped']}")


if __name__ == "__main__":
    main()
