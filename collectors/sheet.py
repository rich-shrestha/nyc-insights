"""Manual Google Sheet collector. Needs SHEET_CSV_URL (File > Share > Publish to web > CSV).
Columns: question, source, link, date, notes. Rows get a 1.5x weight in scoring (config/scoring.yml)."""
from __future__ import annotations

import argparse
import csv
import io

import requests

from collectors.common import env, load_config, log, make_record, save_questions, update_report

SOURCE = "sheet"


def collect(limit: int | None = None) -> tuple[list[dict], dict]:
    creds = env("SHEET_CSV_URL")
    if not creds:
        return [], {"skipped": "SHEET_CSV_URL not set"}
    r = requests.get(creds["SHEET_CSV_URL"], timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    rows = list(csv.DictReader(io.StringIO(r.text)))
    base = load_config("scoring.yml").get("sheet_base_engagement", 5)
    records = []
    for row in rows:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        q = row.get("question", "")
        if not q:
            continue
        records.append(make_record(
            question=q,
            source=SOURCE,
            link=row.get("link", ""),
            date=row.get("date", ""),
            engagement=base,
            raw_text=" | ".join(x for x in [q, row.get("notes", "")] if x),
            origin=row.get("source") or "manual",
            notes=row.get("notes", ""),
        ))
        if limit and len(records) >= limit:
            break
    return records, {"rows": len(rows), "kept": len(records)}


def run(limit: int | None = None) -> dict:
    try:
        records, stats = collect(limit)
    except requests.RequestException as e:
        records, stats = [], {"error": str(e)}
        log(SOURCE, f"error: {e}")
    if "skipped" in stats:
        log(SOURCE, f"skipped: {stats['skipped']}")
    elif "error" not in stats:
        stats.update(save_questions(SOURCE, records))
        log(SOURCE, f"kept {stats['kept']} rows")
    update_report(SOURCE, stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    run(ap.parse_args().limit)
