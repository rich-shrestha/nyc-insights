"""Stack Exchange collector: travel.stackexchange.com, tag new-york-city, last 2 years.
No key required (300 requests/day). Optional STACKEXCHANGE_KEY raises the quota."""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from collectors.common import extract_question, log, make_record, save_questions, update_report

SOURCE = "stackexchange"
API = "https://api.stackexchange.com/2.3/questions"


def collect(limit: int | None = None) -> tuple[list[dict], dict]:
    since = int((datetime.now(timezone.utc) - timedelta(days=730)).timestamp())
    stats = {"questions_read": 0, "kept": 0}
    records, page = [], 1
    while True:
        params = {"site": "travel", "tagged": "new-york-city", "fromdate": since, "sort": "creation",
                  "order": "desc", "pagesize": min(100, limit or 100), "page": page, "filter": "withbody"}
        if os.environ.get("STACKEXCHANGE_KEY"):
            params["key"] = os.environ["STACKEXCHANGE_KEY"]
        r = requests.get(API, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for q in data.get("items", []):
            stats["questions_read"] += 1
            title = q.get("title", "")
            body = q.get("body", "")
            question = title if title.strip().endswith("?") else f"{title}?"
            records.append(make_record(
                question=extract_question(question),
                source=SOURCE,
                link=q.get("link", ""),
                date=q.get("creation_date"),
                engagement=int(q.get("score", 0)) + int(q.get("answer_count", 0)),
                raw_text=f"{title}. {body}",
                origin="travel.stackexchange.com",
            ))
        if limit and stats["questions_read"] >= limit:
            break
        if not data.get("has_more"):
            break
        if data.get("backoff"):
            time.sleep(int(data["backoff"]))
        page += 1
    records = records[:limit] if limit else records
    stats["kept"] = len(records)
    stats["quota_remaining"] = data.get("quota_remaining")
    return records, stats


def run(limit: int | None = None) -> dict:
    try:
        records, stats = collect(limit)
        stats.update(save_questions(SOURCE, records))
        log(SOURCE, f"kept {stats['kept']} questions")
    except requests.RequestException as e:
        stats = {"error": str(e)}
        log(SOURCE, f"error: {e}")
    update_report(SOURCE, stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    run(ap.parse_args().limit)
