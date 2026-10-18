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
  premium_pct        winning bid / reserve price - 1        (needs MechirSaf)
  runner_up          highest bid strictly below the winning bid
  gap_pct            winning bid / runner_up - 1            (needs 2+ bids)
  top_not_winner     a bid higher than the winning bid exists on the lot.
                     The source marks the winning bid (HatzaaDescription=1)
                     but not why a higher bid lost, so no reason is given.
  land_ppsqm         winning bid / lot area (Shetach), land only
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
_ORG = re.compile(r'\b(חברה|שותפות|אגודה|עמותה|קיבוץ|מושב|קבוצת|רשת)\b')
_BIZ = re.compile(
    r'\b(הנדסה|יזמות|ייזום|יזום|נדלן|נדל"ן|השקעות|אחזקות|החזקות|פיתוח|בניה|'
    r'בנייה|בנין|בניין|תעשיות|נכסים|מגורים|קבלנות|תשתיות|ליסינג|מלונות|'
    r'מלונאות|תיירות|סחר|מסחר|הובלות|שרותים|שירותים|ניהול|תכנון|קבלן|'
    r'בונה|בוני|מרכזי)\b')
INDIVIDUAL_KEEP_FROM = 3_000_000  # individuals above this bought land, not a lottery


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


def build(raw, cities):
    lots, dropped = [], {"lottery": 0, "system": 0, "no_winner": 0, "no_lots": 0}
    for key, body in raw["categories"].items():
        for entry in body["tenders"]:
            b, det = entry["basic"], entry["details"]
            tiks = det.get("Tik") or []
            if not tiks:
                dropped["no_lots"] += 1
                continue
            for tik in tiks:
                winner = (tik.get("ShemZoche") or "").strip()
                if not winner:
                    dropped["no_winner"] += 1
                    continue
                if any(m in winner for m in STATUS_MARKERS):
                    dropped["system"] += 1
                    continue
                win = pos(tik.get("SchumZchiya"))
                company = is_company(winner)
                if not company and not (win and win >= INDIVIDUAL_KEEP_FROM):
                    dropped["lottery"] += 1
                    continue
                bids = sorted({y["HatzaaSum"] for y in tik.get("mpHatzaaotMitcham") or []
                               if pos(y.get("HatzaaSum"))}, reverse=True)
                bid_rows = [{"sum": y["HatzaaSum"], "win": y.get("HatzaaDescription") == 1}
                            for y in tik.get("mpHatzaaotMitcham") or [] if pos(y.get("HatzaaSum"))]
                bid_rows.sort(key=lambda r: -r["sum"])
                reserve = pos(tik.get("MechirSaf"))
                dev = pos(tik.get("HotzaotPituach"))
                area = pos(tik.get("Shetach"))
                runner = next((s for s in bids if win and s < win), None)
                lots.append({
                    "id": f'{b.get("MichrazID")}-{tik.get("TikID")}',
                    "tender": b.get("MichrazName"),
                    "url": f'https://apps.land.gov.il/MichrazimSite/#/michraz/{b.get("MichrazID")}',
                    "date": (b.get("VaadaDate") or "")[:10] or None,
                    "city": cities.get(b.get("KodYeshuv")),
                    "hood": (b.get("Shchuna") or "").strip() or None,
                    "cat": CATEGORY_HE.get(key, key),
                    "lot": (tik.get("MitchamName") or "").strip() or None,
                    "winner": winner,
                    "kind": "חברה" if company else "פרטי",
                    "win": win,
                    "reserve": reserve,
                    "dev": dev,
                    "area": area,
                    "units": pos(b.get("YechidotDiur")),
                    "gush": ", ".join(f'{g.get("Gush", "")}/{g.get("Helka", "")}'
                                      for g in tik.get("GushHelka") or []) or None,
                    "bids": bid_rows,
                    "bidders": len(bid_rows) or None,
                    "premium_pct": (win / reserve - 1) * 100 if win and reserve else None,
                    "runner_up": runner,
                    "gap_pct": (win / runner - 1) * 100 if win and runner else None,
                    "top_not_winner": bool(win and bids and bids[0] > win),
                    "land_ppsqm": win / area if win and area else None,
                    "dev_share_pct": dev / (win + dev) * 100 if win and dev else None,
                })
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
          f"{sum(1 for l in lots if l['premium_pct'] is not None)} with reserve price, "
          f"dropped {data['meta']['dropped']}")


if __name__ == "__main__":
    main()
