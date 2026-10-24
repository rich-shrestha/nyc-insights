"""Bluesky collector (app.bsky.feed.searchPosts). Needs BSKY_HANDLE + BSKY_APP_PASSWORD."""
from __future__ import annotations

import argparse

import requests

from collectors.common import (env, extract_question, is_question, load_config, log, make_record,
                               mentions_nyc, save_questions, update_report)

SOURCE = "bluesky"
PDS = "https://bsky.social/xrpc"


def _session(handle: str, password: str) -> str:
    r = requests.post(f"{PDS}/com.atproto.server.createSession",
                      json={"identifier": handle, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["accessJwt"]


def _post_link(uri: str) -> str:
    # at://did:plc:xyz/app.bsky.feed.post/rkey -> link by DID (no handle stored)
    parts = uri.replace("at://", "").split("/")
    return f"https://bsky.app/profile/{parts[0]}/post/{parts[-1]}"


def collect(limit: int | None = None) -> tuple[list[dict], dict]:
    creds = env("BSKY_HANDLE", "BSKY_APP_PASSWORD")
    if not creds:
        return [], {"skipped": "BSKY_HANDLE / BSKY_APP_PASSWORD not set"}
    cfg = load_config("bluesky.yml")
    token = _session(creds["BSKY_HANDLE"].lstrip("@"), creds["BSKY_APP_PASSWORD"])
    headers = {"Authorization": f"Bearer {token}"}
    stats = {"posts_read": 0, "question_style": 0, "nyc_relevant": 0, "kept": 0, "per_query": {}}
    records, seen = [], set()
    per_page = min(100, cfg.get("posts_per_query", 100))

    for q in cfg.get("queries", []):
        pq = stats["per_query"].setdefault(q, {"read": 0, "kept": 0})
        cursor = None
        for _ in range(cfg.get("pages_per_query", 1)):
            if limit and stats["posts_read"] >= limit:
                break
            n = min(per_page, limit - stats["posts_read"]) if limit else per_page
            params = {"q": q, "limit": n, "sort": cfg.get("sort", "latest"), "lang": "en"}
            if cursor:
                params["cursor"] = cursor
            r = requests.get(f"{PDS}/app.bsky.feed.searchPosts", params=params, headers=headers, timeout=30)
            if r.status_code != 200:
                log(SOURCE, f"query '{q}' -> HTTP {r.status_code}: {r.text[:200]}")
                break
            data = r.json()
            for p in data.get("posts", []):
                stats["posts_read"] += 1
                pq["read"] += 1
                if p["uri"] in seen:
                    continue
                seen.add(p["uri"])
                text = p.get("record", {}).get("text", "")
                if not is_question(text):
                    continue
                stats["question_style"] += 1
                if not mentions_nyc(text):
                    continue
                stats["nyc_relevant"] += 1
                pq["kept"] += 1
                records.append(make_record(
                    question=extract_question(text),
                    source=SOURCE,
                    link=_post_link(p["uri"]),
                    date=p.get("record", {}).get("createdAt") or p.get("indexedAt"),
                    engagement=p.get("likeCount", 0) + p.get("repostCount", 0) + p.get("replyCount", 0),
                    raw_text=text,
                    origin=f"search: {q}",
                ))
            cursor = data.get("cursor")
            if not cursor:
                break
    stats["kept"] = len(records)
    return records, stats


def run(limit: int | None = None) -> dict:
    try:
        records, stats = collect(limit)
    except requests.HTTPError as e:
        records, stats = [], {"error": str(e)}
        log(SOURCE, f"error: {e}")
    if "skipped" in stats:
        log(SOURCE, f"skipped: {stats['skipped']}")
    elif "error" not in stats:
        stats.update(save_questions(SOURCE, records))
        log(SOURCE, f"read {stats['posts_read']} posts, {stats['question_style']} question-style, kept {stats['kept']} NYC questions")
    update_report(SOURCE, stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    run(ap.parse_args().limit)
