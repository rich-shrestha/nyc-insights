"""Shared helpers for every collector: schema, question filter, privacy scrubbing, saving."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
QUESTIONS_PATH = DATA / "questions.json"
REPORT_PATH = DATA / "run_report.json"

SCHEMA_FIELDS = ["question", "source", "link", "date", "engagement", "raw_text"]

USER_AGENT = "nyc-insights/1.0 (https://github.com/rich-shrestha/nyc-insights)"


def load_config(name: str) -> dict:
    path = CONFIG / name
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


FILTERS = load_config("filters.yml")


def env(*names: str) -> dict | None:
    """Return {name: value} if every env var is set and non-empty, else None (source is skipped)."""
    vals = {n: os.environ.get(n, "").strip() for n in names}
    if all(vals.values()):
        return vals
    return None


# ---------- privacy ----------
_MENTION = re.compile(r"(?<![\w.])@[\w.\-]+")
_REDDIT_USER = re.compile(r"(?<!\w)/?u/[\w\-]+", re.I)
_URL = re.compile(r"https?://\S+")


def scrub(text: str) -> str:
    """Remove @mentions, u/usernames and URLs so no usernames are stored."""
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)  # strip HTML tags
    text = _MENTION.sub("@user", text)
    text = _REDDIT_USER.sub("u/user", text)
    text = _URL.sub("[link]", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------- question detection ----------
def _starters() -> list[str]:
    return [s.lower() for s in FILTERS.get("question_starters", [])]


def is_question(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if len(t.split()) < FILTERS.get("min_words", 4):
        return False
    if any(p in t for p in FILTERS.get("exclude_phrases", [])):
        return False
    if "?" in t:
        return True
    first = re.split(r"[\s,']+", t, maxsplit=1)[0]
    return first in _starters()


_NYC_RE = None


def mentions_nyc(text: str) -> bool:
    global _NYC_RE
    if _NYC_RE is None:
        terms = sorted(FILTERS.get("nyc_terms", []), key=len, reverse=True)
        _NYC_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in terms) + r")\b", re.I)
    return bool(_NYC_RE.search(text or ""))


def extract_question(text: str) -> str:
    """Pull out the question sentence(s); fall back to the (trimmed) full text."""
    max_chars = FILTERS.get("max_chars", 600)
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    qs = [s for s in sentences if "?" in s]
    out = " ".join(qs[:2]) if qs else text.strip()
    if len(out) > max_chars:
        out = out[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return out


# ---------- records ----------
def to_iso(dt) -> str:
    if isinstance(dt, (int, float)):
        dt = datetime.fromtimestamp(dt, tz=timezone.utc)
    if isinstance(dt, str):
        s = dt.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S", "%b %d, %Y", "%B %d, %Y"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    continue
            else:
                return datetime.now(timezone.utc).date().isoformat()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).date().isoformat()


def make_record(*, question: str, source: str, link: str, date, engagement: float,
                raw_text: str, **extra) -> dict:
    q = scrub(question)
    rec = {
        "question": q,
        "source": source,
        "link": link or "",
        "date": to_iso(date),
        "engagement": float(engagement or 0),
        "raw_text": scrub(raw_text)[:2000],
    }
    rec.update({k: v for k, v in extra.items() if v not in (None, "")})
    key = f"{source}|{link}|{q.lower()}"
    rec["id"] = hashlib.sha1(key.encode()).hexdigest()[:12]
    return rec


def save_questions(source: str, records: list[dict]) -> dict:
    """Upsert this source's records into data/questions.json. Returns stats."""
    DATA.mkdir(exist_ok=True)
    existing = []
    if QUESTIONS_PATH.exists():
        existing = json.loads(QUESTIONS_PATH.read_text() or "[]")
    by_id = {r["id"]: r for r in existing}
    added = 0
    for r in records:
        if r["id"] not in by_id:
            added += 1
        else:
            # keep first-seen date, refresh engagement
            r["first_seen"] = by_id[r["id"]].get("first_seen", by_id[r["id"]]["date"])
        r.setdefault("first_seen", datetime.now(timezone.utc).date().isoformat())
        by_id[r["id"]] = r
    out = sorted(by_id.values(), key=lambda r: (r["date"], r["engagement"]), reverse=True)
    QUESTIONS_PATH.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return {"source": source, "kept": len(records), "new": added, "total_in_file": len(out)}


def update_report(source: str, stats: dict) -> None:
    DATA.mkdir(exist_ok=True)
    report = {}
    if REPORT_PATH.exists():
        report = json.loads(REPORT_PATH.read_text() or "{}")
    stats["ran_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report[source] = stats
    REPORT_PATH.write_text(json.dumps(report, indent=1))


def log(source: str, msg: str) -> None:
    print(f"[{source}] {msg}", flush=True)
