"""NYC 311 summary via Socrata (no auth; optional SOCRATA_APP_TOKEN raises rate limits).
Top complaint types by neighborhood (community district) over the last 12 months -> data/311_summary.json"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

from collectors.common import DATA, log, update_report

SOURCE = "nyc311"
URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
OUT = DATA / "311_summary.json"

# Community district -> familiar neighborhood names
NEIGHBORHOODS = {
    "MANHATTAN": {1: "Financial District & Tribeca", 2: "Greenwich Village & SoHo", 3: "Lower East Side & Chinatown",
                  4: "Chelsea & Hell's Kitchen", 5: "Midtown", 6: "Murray Hill, Gramercy & Stuy Town",
                  7: "Upper West Side", 8: "Upper East Side", 9: "Morningside & Hamilton Heights",
                  10: "Central Harlem", 11: "East Harlem", 12: "Washington Heights & Inwood"},
    "BRONX": {1: "Mott Haven & Melrose", 2: "Hunts Point & Longwood", 3: "Morrisania & Crotona",
              4: "Highbridge & Concourse", 5: "Fordham & University Heights", 6: "Belmont & East Tremont",
              7: "Kingsbridge Heights & Bedford Park", 8: "Riverdale & Fieldston", 9: "Parkchester & Soundview",
              10: "Throgs Neck & Co-op City", 11: "Morris Park & Pelham Parkway", 12: "Williamsbridge & Wakefield"},
    "BROOKLYN": {1: "Williamsburg & Greenpoint", 2: "Downtown Brooklyn, Fort Greene & Brooklyn Heights",
                 3: "Bed-Stuy", 4: "Bushwick", 5: "East New York & Cypress Hills",
                 6: "Park Slope, Carroll Gardens & Red Hook", 7: "Sunset Park & Windsor Terrace",
                 8: "Crown Heights North & Prospect Heights", 9: "Crown Heights South & Prospect Lefferts",
                 10: "Bay Ridge & Dyker Heights", 11: "Bensonhurst & Bath Beach", 12: "Borough Park & Kensington",
                 13: "Coney Island & Brighton Beach", 14: "Flatbush & Midwood", 15: "Sheepshead Bay & Gravesend",
                 16: "Brownsville & Ocean Hill", 17: "East Flatbush", 18: "Canarsie & Flatlands"},
    "QUEENS": {1: "Astoria & Long Island City", 2: "Sunnyside & Woodside", 3: "Jackson Heights & East Elmhurst",
               4: "Elmhurst & Corona", 5: "Ridgewood, Maspeth & Middle Village", 6: "Forest Hills & Rego Park",
               7: "Flushing & Whitestone", 8: "Fresh Meadows & Briarwood", 9: "Kew Gardens, Woodhaven & Richmond Hill",
               10: "Howard Beach & Ozone Park", 11: "Bayside & Little Neck", 12: "Jamaica & Hollis",
               13: "Queens Village & Rosedale", 14: "The Rockaways"},
    "STATEN ISLAND": {1: "North Shore (St. George)", 2: "Mid-Island", 3: "South Shore"},
}
TOP_PER_HOOD = 10
TOP_CITYWIDE = 15


def _parse_cb(cb: str):
    """'08 MANHATTAN' -> ('MANHATTAN', 8, 'Upper East Side'); invalid/unspecified -> None."""
    parts = (cb or "").split(" ", 1)
    if len(parts) != 2 or not parts[0].isdigit():
        return None
    num, boro = int(parts[0]), parts[1].strip().upper()
    name = NEIGHBORHOODS.get(boro, {}).get(num)
    return (boro, num, name) if name else None


def _query(params: dict, tries: int = 4) -> list[dict]:
    headers = {}
    if os.environ.get("SOCRATA_APP_TOKEN"):
        headers["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]
    for i in range(tries):
        try:
            r = requests.get(URL, params=params, headers=headers, timeout=180)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log(SOURCE, f"attempt {i + 1} failed: {e}")
            time.sleep(10 * (i + 1))
    raise RuntimeError("311 query failed after retries")


def run(limit: int | None = None) -> dict:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=365)
    params = {
        "$select": "community_board, complaint_type, count(*) AS n",
        "$where": f"created_date >= '{start.isoformat()}T00:00:00' AND created_date < '{end.isoformat()}T00:00:00'",
        "$group": "community_board, complaint_type",
        "$order": "n DESC",
        "$limit": limit or 50000,
    }
    try:
        rows = _query(params)
    except RuntimeError as e:
        update_report(SOURCE, {"error": str(e)})
        return {"error": str(e)}

    city = defaultdict(int)
    hoods: dict[str, dict] = {}
    unmapped = 0
    for row in rows:
        n = int(float(row.get("n", 0)))
        ctype = (row.get("complaint_type") or "Unknown").strip()
        city[ctype] += n
        parsed = _parse_cb(row.get("community_board", ""))
        if not parsed:
            unmapped += n
            continue
        boro, num, name = parsed
        key = f"{boro.title()} CD{num}"
        h = hoods.setdefault(key, {"id": key, "name": name, "borough": boro.title(), "district": num,
                                   "total": 0, "types": defaultdict(int)})
        h["total"] += n
        h["types"][ctype] += n

    city_total = sum(city.values()) or 1
    city_share = {k: v / city_total for k, v in city.items()}
    neighborhoods = []
    for h in sorted(hoods.values(), key=lambda x: (x["borough"], x["district"])):
        types = sorted(h["types"].items(), key=lambda kv: kv[1], reverse=True)
        # "distinctive" = over-represented vs citywide (location quotient), with a minimum volume
        distinctive = sorted(
            ((t, n, (n / h["total"]) / city_share[t]) for t, n in types if n >= 200),
            key=lambda x: x[2], reverse=True)[:3]
        neighborhoods.append({
            "id": h["id"], "name": h["name"], "borough": h["borough"], "total": h["total"],
            "top": [{"type": t, "count": n, "share": round(n / h["total"], 4)} for t, n in types[:TOP_PER_HOOD]],
            "distinctive": [{"type": t, "count": n, "x_citywide": round(lq, 2)} for t, n, lq in distinctive],
        })

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "dataset": "erm2-nwe9",
        "query": params,
        "total_requests": city_total,
        "unmapped_requests": unmapped,
        "citywide_top": [{"type": t, "count": n, "share": round(n / city_total, 4)}
                         for t, n in sorted(city.items(), key=lambda kv: kv[1], reverse=True)[:TOP_CITYWIDE]],
        "neighborhoods": neighborhoods,
    }
    if limit:  # test mode: don't overwrite the real summary
        stats = {"test_rows": len(rows), "sample": rows[:3]}
        log(SOURCE, f"test pull OK: {len(rows)} grouped rows")
    else:
        DATA.mkdir(exist_ok=True)
        OUT.write_text(json.dumps(summary, indent=1))
        stats = {"grouped_rows": len(rows), "total_requests": city_total, "neighborhoods": len(neighborhoods)}
        log(SOURCE, f"{city_total:,} requests across {len(neighborhoods)} neighborhoods -> {OUT.name}")
    update_report(SOURCE, stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    run(ap.parse_args().limit)
