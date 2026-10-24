"""Add/remove a cluster in config/used.yml. Called by the mark-used workflow from an issue title:
    used: <cluster_id>      -> mark used
    unuse: <cluster_id>     -> remove
Usage: python scripts/mark_used.py "<issue title>"
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
USED = ROOT / "config" / "used.yml"
CLUSTERS = ROOT / "data" / "clusters.json"

HEADER = """# Clusters you've already made videos for. They drop off the Top 10.
# Add entries by tapping "Mark used" on the site (opens a GitHub issue the bot processes),
# or edit this file directly on GitHub. `question` is used as a fallback match
# if a cluster's id changes between runs.
"""


def main(title: str) -> int:
    m = re.match(r"^\s*(used|unuse)\s*:\s*([0-9a-f]{6,16})\s*$", title or "", re.I)
    if not m:
        print(f"Title not recognized: {title!r}")
        return 1
    action, cid = m.group(1).lower(), m.group(2).lower()
    data = yaml.safe_load(USED.read_text()) if USED.exists() else {}
    used = (data or {}).get("used") or []
    used = [u for u in used if str(u.get("id") if isinstance(u, dict) else u) != cid]
    if action == "used":
        question = ""
        if CLUSTERS.exists():
            for c in json.loads(CLUSTERS.read_text()).get("clusters", []):
                if c["id"] == cid:
                    question = c["question"]
                    break
        used.append({"id": cid, "question": question,
                     "date": datetime.now(timezone.utc).date().isoformat()})
    USED.write_text(HEADER + yaml.safe_dump({"used": used}, sort_keys=False, allow_unicode=True, width=1000))
    print(f"{action} {cid}: used.yml now has {len(used)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:])))
