"""YouTube Data API v3 collector. Needs YT_API_KEY. Channels/queries in config/youtube.yml."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import requests

from collectors.common import (env, extract_question, is_question, load_config, log, make_record,
                               save_questions, update_report)

SOURCE = "youtube"
API = "https://www.googleapis.com/youtube/v3"


def _get(key: str, path: str, **params) -> dict:
    params["key"] = key
    r = requests.get(f"{API}/{path}", params=params, timeout=30)
    if r.status_code == 403 and "commentsDisabled" in r.text:
        return {"items": []}
    r.raise_for_status()
    return r.json()


def _resolve_channel(key: str, ch: dict) -> tuple[str | None, str | None]:
    """Return (uploads_playlist_id, title)."""
    params = {"part": "contentDetails,snippet"}
    if ch.get("channel_id"):
        params["id"] = ch["channel_id"]
    elif ch.get("handle"):
        params["forHandle"] = ch["handle"]
    else:
        return None, None
    items = _get(key, "channels", **params).get("items", [])
    if not items:
        return None, None
    it = items[0]
    return it["contentDetails"]["relatedPlaylists"]["uploads"], it["snippet"]["title"]


def _recent_videos(key: str, playlist: str, n: int, max_age_days: int) -> list[str]:
    data = _get(key, "playlistItems", part="contentDetails", playlistId=playlist, maxResults=min(50, n * 2))
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    vids = []
    for it in data.get("items", []):
        published = it["contentDetails"].get("videoPublishedAt")
        if published and datetime.fromisoformat(published.replace("Z", "+00:00")) < cutoff:
            continue
        vids.append(it["contentDetails"]["videoId"])
    return vids[:n]


def _search_videos(key: str, query: str, n: int) -> list[str]:
    after = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = _get(key, "search", part="id", q=query, type="video", order="viewCount",
                maxResults=n, publishedAfter=after, regionCode="US", relevanceLanguage="en")
    return [it["id"]["videoId"] for it in data.get("items", [])]


def _comments(key: str, video_id: str, n: int) -> list[dict]:
    out, token = [], None
    while len(out) < n:
        params = dict(part="snippet", videoId=video_id, maxResults=min(100, n - len(out)),
                      order="relevance", textFormat="plainText")
        if token:
            params["pageToken"] = token
        data = _get(key, "commentThreads", **params)
        out.extend(data.get("items", []))
        token = data.get("nextPageToken")
        if not token:
            break
    return out


def collect(limit: int | None = None) -> tuple[list[dict], dict]:
    creds = env("YT_API_KEY")
    if not creds:
        return [], {"skipped": "YT_API_KEY not set"}
    key = creds["YT_API_KEY"]
    cfg = load_config("youtube.yml")
    stats = {"channels_ok": [], "channels_unresolved": [], "videos": 0, "comments_read": 0,
             "question_style": 0, "kept": 0, "per_channel": {}}

    video_jobs: list[tuple[str, str]] = []  # (video_id, label)
    for ch in cfg.get("channels", []):
        label = ch.get("handle") or ch.get("channel_id")
        try:
            playlist, title = _resolve_channel(key, ch)
        except requests.HTTPError as e:
            log(SOURCE, f"channel {label} error: {e}")
            playlist = None
        if not playlist:
            stats["channels_unresolved"].append(label)
            log(SOURCE, f"could not resolve channel {label}")
            continue
        stats["channels_ok"].append(f"{label} ({title})")
        for v in _recent_videos(key, playlist, cfg.get("videos_per_channel", 6), cfg.get("max_video_age_days", 365)):
            video_jobs.append((v, label))
    for q in cfg.get("search_queries", []) or []:
        try:
            for v in _search_videos(key, q, cfg.get("search_results_per_query", 5)):
                video_jobs.append((v, f"search: {q}"))
        except requests.HTTPError as e:
            log(SOURCE, f"search '{q}' error: {e}")

    seen_videos, records = set(), []
    per_video = cfg.get("comments_per_video", 100)
    for vid, label in video_jobs:
        if vid in seen_videos:
            continue
        seen_videos.add(vid)
        if limit and stats["comments_read"] >= limit:
            break
        n = min(per_video, limit - stats["comments_read"]) if limit else per_video
        try:
            threads = _comments(key, vid, n)
        except requests.HTTPError as e:
            log(SOURCE, f"comments for {vid} error: {e}")
            continue
        stats["videos"] += 1
        pc = stats["per_channel"].setdefault(label, {"read": 0, "kept": 0})
        for t in threads:
            sn = t["snippet"]["topLevelComment"]["snippet"]
            text = sn.get("textDisplay") or sn.get("textOriginal") or ""
            stats["comments_read"] += 1
            pc["read"] += 1
            if not is_question(text):
                continue
            stats["question_style"] += 1
            pc["kept"] += 1
            records.append(make_record(
                question=extract_question(text),
                source=SOURCE,
                link=f"https://www.youtube.com/watch?v={vid}&lc={t['snippet']['topLevelComment']['id']}",
                date=sn.get("publishedAt"),
                engagement=int(sn.get("likeCount", 0)) + int(t["snippet"].get("totalReplyCount", 0)),
                raw_text=text,
                origin=label,
            ))
    stats["kept"] = len(records)
    return records, stats


def run(limit: int | None = None) -> dict:
    records, stats = collect(limit)
    if "skipped" in stats:
        log(SOURCE, f"skipped: {stats['skipped']}")
    else:
        stats.update(save_questions(SOURCE, records))
        log(SOURCE, f"read {stats['comments_read']} comments from {stats['videos']} videos, kept {stats['kept']} questions")
    update_report(SOURCE, stats)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    run(ap.parse_args().limit)
