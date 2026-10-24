"""Reddit collector (DISABLED until keys exist). Read-only, app-only OAuth via PRAW.
Needs REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET. Never stores authors."""
from __future__ import annotations

import argparse

from collectors.common import (env, extract_question, is_question, log, make_record, save_questions,
                               update_report)

SOURCE = "reddit"
SUBREDDITS = ["AskNYC", "nyc", "FoodNYC", "NYCapartments"]
POSTS_PER_SUB = 250


def collect(limit: int | None = None) -> tuple[list[dict], dict]:
    creds = env("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")
    if not creds:
        return [], {"skipped": "REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET not set (module disabled)"}
    import praw  # imported lazily so the package is only needed when enabled

    reddit = praw.Reddit(client_id=creds["REDDIT_CLIENT_ID"], client_secret=creds["REDDIT_CLIENT_SECRET"],
                         user_agent="nyc-insights/1.0 by rich-shrestha (read-only)")
    reddit.read_only = True
    stats = {"posts_read": 0, "question_style": 0, "kept": 0, "per_sub": {}}
    records, seen = [], set()
    per_sub = min(POSTS_PER_SUB, limit) if limit else POSTS_PER_SUB
    for sub in SUBREDDITS:
        ps = stats["per_sub"].setdefault(sub, {"read": 0, "kept": 0})
        for listing in (reddit.subreddit(sub).top(time_filter="month", limit=per_sub),
                        reddit.subreddit(sub).new(limit=per_sub)):
            for post in listing:
                if post.id in seen:
                    continue
                seen.add(post.id)
                stats["posts_read"] += 1
                ps["read"] += 1
                title, body = post.title or "", post.selftext or ""
                if not is_question(title):
                    continue
                stats["question_style"] += 1
                ps["kept"] += 1
                records.append(make_record(
                    question=extract_question(title),
                    source=SOURCE,
                    link=f"https://www.reddit.com{post.permalink}",
                    date=post.created_utc,
                    engagement=int(post.score) + int(post.num_comments),
                    raw_text=f"{title}. {body}",
                    origin=f"r/{sub}",
                ))
    stats["kept"] = len(records)
    return records, stats


def run(limit: int | None = None) -> dict:
    try:
        records, stats = collect(limit)
    except Exception as e:  # PRAW raises many exception types
        records, stats = [], {"error": str(e)}
        log(SOURCE, f"error: {e}")
    if "skipped" in stats:
        log(SOURCE, f"skipped: {stats['skipped']}")
    elif "error" not in stats:
        stats.update(save_questions(SOURCE, records))
        log(SOURCE, f"read {stats['posts_read']} posts, kept {stats['kept']} questions")
    update_report(SOURCE, stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    run(ap.parse_args().limit)
