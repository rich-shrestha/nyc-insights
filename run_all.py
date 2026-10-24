"""Run the whole pipeline: collect from every source (skipping any without keys), then tag/cluster/score.

    python run_all.py                 # full run
    python run_all.py --test          # ~50 items per source, then process
    python run_all.py --only youtube  # one source
    python run_all.py --skip-collect  # just re-score (e.g. after editing configs)
"""
from __future__ import annotations

import argparse
import json
import traceback

from collectors import bluesky, nyc311, reddit, sheet, stackexchange, youtube
from collectors.common import REPORT_PATH
from pipeline import process

SOURCES = {"youtube": youtube, "bluesky": bluesky, "stackexchange": stackexchange,
           "sheet": sheet, "reddit": reddit, "nyc311": nyc311}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="small pull (~50 items per source)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", nargs="*", choices=list(SOURCES), default=None)
    ap.add_argument("--skip-collect", action="store_true")
    args = ap.parse_args()
    limit = args.limit or (50 if args.test else None)

    if not args.skip_collect:
        if REPORT_PATH.exists() and not args.only:
            REPORT_PATH.unlink()  # fresh report each full run
        for name in args.only or SOURCES:
            print(f"=== {name} ===", flush=True)
            try:
                SOURCES[name].run(limit)
            except Exception:  # one broken source never stops the others
                traceback.print_exc()
    process.main()
    if REPORT_PATH.exists():
        print(json.dumps(json.loads(REPORT_PATH.read_text()), indent=1)[:4000])


if __name__ == "__main__":
    main()
