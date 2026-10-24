"""Run the Socrata queries listed in config/brief_queries.yml and save results to data/brief_results/.
Used to check the exact queries in content_briefs.md and get real numbers for scripts.
Run from GitHub Actions ("Run brief queries" workflow) or locally: python scripts/run_queries.py"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "brief_results"


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config" / "brief_queries.yml").read_text()) or {}
    OUT.mkdir(parents=True, exist_ok=True)
    headers = {"X-App-Token": os.environ["SOCRATA_APP_TOKEN"]} if os.environ.get("SOCRATA_APP_TOKEN") else {}
    failures = 0
    for q in cfg.get("queries", []):
        url = f"https://{q['domain']}/resource/{q['dataset']}.json"
        try:
            r = requests.get(url, params=q["params"], headers=headers, timeout=240)
            r.raise_for_status()
            rows = r.json()
            (OUT / f"{q['key']}.json").write_text(json.dumps({"url": r.url, "rows": rows}, indent=1))
            print(f"OK   {q['key']}: {len(rows)} rows")
            for row in rows[:5]:
                print("     ", row)
        except Exception as e:  # report and keep going
            failures += 1
            print(f"FAIL {q['key']}: {e}")
            (OUT / f"{q['key']}.json").write_text(json.dumps({"error": str(e)}, indent=1))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
