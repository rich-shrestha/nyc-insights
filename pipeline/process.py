"""Tag -> cluster -> score -> explain. Reads data/questions.json, writes data/clusters.json and docs/data/*.json."""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from collections import Counter
from datetime import date, datetime, timezone

import numpy as np
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from collectors.common import DATA, QUESTIONS_PATH, REPORT_PATH, ROOT, load_config

SITE_DATA = ROOT / "docs" / "data"
SOURCE_LABELS = {"youtube": "YouTube", "bluesky": "Bluesky", "stackexchange": "Stack Exchange",
                 "sheet": "your sheet", "reddit": "Reddit"}
EXTRA_STOP = {"nyc", "new", "york", "city", "anyone", "know", "guys", "does", "just", "like", "really",
              "im", "i'm", "ur", "u", "pls", "please", "thanks", "thank", "lol", "hey", "hi", "ve", "ll"}


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _age_days(d: str) -> int:
    try:
        return max(0, (_today() - date.fromisoformat(d[:10])).days)
    except ValueError:
        return 9999


def _phrase_regex(words) -> re.Pattern:
    words = sorted({w.lower() for w in words}, key=len, reverse=True)
    return re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in words) + r")(?![\w])", re.I)


# ---------------- 1. THEME ----------------
class Tagger:
    def __init__(self, cfg: dict):
        self.rules = [(theme, _phrase_regex(words)) for theme, words in (cfg.get("themes") or {}).items() if words]

    def tag(self, *texts: str) -> str:
        for text in texts:
            best, best_hits = "other", 0
            for theme, rx in self.rules:
                hits = len(rx.findall(text or ""))
                if hits > best_hits:
                    best, best_hits = theme, hits
            if best_hits:
                return best
        return "other"


# ---------------- 2. CLUSTER ----------------
def _normalize(q: str) -> str:
    q = q.lower()
    q = re.sub(r"\[link\]|@user|u/user", " ", q)
    q = re.sub(r"[^a-z0-9' ]+", " ", q)
    return re.sub(r"\s+", " ", q).strip()


_STOP = ENGLISH_STOP_WORDS | EXTRA_STOP


def _clean_for_vec(q: str) -> str:
    """Normalize, drop stop words, and crudely singularize (apartments -> apartment)."""
    words = [w for w in _normalize(q).split() if w not in _STOP]
    return " ".join(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words)


def cluster_questions(questions: list[dict], threshold: float):
    """Leader clustering on TF-IDF cosine similarity. Questions are visited in engagement order;
    each joins the most similar existing leader if similarity >= threshold, else starts a cluster."""
    texts = [q["question"] for q in questions]
    vec = TfidfVectorizer(preprocessor=_clean_for_vec, token_pattern=r"[a-z0-9']+", sublinear_tf=True)
    try:
        X = vec.fit_transform(texts)
    except ValueError:  # empty vocabulary
        return [[i] for i in range(len(questions))], None, None
    from scipy.sparse import vstack

    order = sorted(range(len(questions)), key=lambda i: (-questions[i]["_w_eng"], questions[i]["date"]))
    members: list[list[int]] = []   # members[k] = question indexes in leader k's cluster
    L, pending = None, []           # leader matrix (rows aligned with `members`) + rows not yet stacked
    for i in order:
        row = X[i]
        if row.nnz and (L is not None or pending):
            if pending:
                L = vstack(([L] if L is not None else []) + pending).tocsr()
                pending = []
            sims = (L @ row.T).toarray().ravel()
            j = int(np.argmax(sims))
            if sims[j] >= threshold:
                members[j].append(i)
                continue
        members.append([i])
        pending.append(row)
    return members, X, vec


# ---------------- 3. SCORE ----------------
class DatasetMatcher:
    def __init__(self, cfg: dict):
        self.datasets = []
        for d in cfg.get("datasets", []):
            self.datasets.append({**d, "_rx": _phrase_regex(d.get("keywords", []) or ["\u0000"])})

    def match(self, theme: str, text: str):
        results = []
        for d in self.datasets:
            found = {m.lower() for m in d["_rx"].findall(text)}
            kws = sorted(k for k in found if not (k.endswith("s") and k[:-1] in found))  # bagel/bagels -> bagel
            theme_hit = theme in (d.get("themes") or [])
            score = min(float(d.get("max_score", 10)), (4 if theme_hit else 0) + 3 * min(2, len(kws)))
            if score > 0:
                results.append({"key": d["key"], "name": d["name"], "socrata_id": d.get("socrata_id"),
                                "domain": d.get("domain"), "answers": d.get("answers", ""),
                                "score": score, "keywords": kws[:4], "theme_match": theme_hit})
        results.sort(key=lambda r: (r["score"], len(r["keywords"])), reverse=True)
        return results


def _freshness(ages: list[int], half_life: float) -> float:
    if not ages:
        return 0.0
    recent = min(ages)
    median = float(np.median(ages))
    return round(10 * (0.6 * 0.5 ** (recent / half_life) + 0.4 * 0.5 ** (median / half_life)), 2)


def _angle(text: str, scfg: dict) -> str:
    for a in scfg.get("angles", []):
        if re.search(a["pattern"], text, re.I):
            return a["angle"]
    return scfg.get("default_angle", "explainer angle")


def _human_list(items: list[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _why(c: dict, scfg: dict) -> str:
    window = scfg.get("freshness", {}).get("recent_window_days", 30)
    srcs = _human_list([SOURCE_LABELS.get(s, s) for s in c["sources"]])
    times = "once" if c["count"] == 1 else f"{c['count']} times"
    parts = [f"Asked {times} on {srcs}"]
    if c["recent_count"]:
        parts[0] += f" ({c['recent_count']} in the last {window} days)"
    else:
        parts[0] += f" (latest {c['latest_date']})"
    if c["engagement"] >= 1:
        parts.append(f"{int(round(c['engagement'])):,} total likes/replies/votes")
    if c["datasets"] and c["scores"]["answerability"] >= 5:
        d = c["datasets"][0]
        kw = f" (matches {', '.join(repr(k) for k in d['keywords'][:2])})" if d["keywords"] else ""
        parts.append(f"answerable with {d['name']}{kw}")
    elif c["datasets"]:
        parts.append(f"partly answerable with {c['datasets'][0]['name']}")
    else:
        parts.append("no clear NYC Open Data match, would need outside data")
    parts.append(c["angle"])
    s = "; ".join(parts) + "."
    return s[0].upper() + s[1:]


def _cluster_id(qs: list[dict]) -> str:
    anchor = min(qs, key=lambda q: (q.get("first_seen", q["date"]), q["date"], q["id"]))
    return hashlib.sha1(anchor["id"].encode()).hexdigest()[:10]


_DEICTIC = re.compile(r"\b(this|that|these|those|he|she|his|her|you|your|ur)\b", re.I)


def _pick_canonical(qs: list[dict], idxs: list[int], X) -> dict:
    if X is None or len(idxs) == 1:
        return qs[0]
    sub = X[idxs]
    centroid = np.asarray(sub.mean(axis=0)).ravel()
    sims = sub @ centroid
    max_eng = max(q["_w_eng"] for q in qs) or 1
    best, best_s = qs[0], -1
    for q, s in zip(qs, sims):
        words = len(q["question"].split())
        well_formed = (q["question"].strip().endswith("?")) + (5 <= words <= 25)
        deictic = bool(_DEICTIC.search(q["question"]))  # "where is THIS place?" needs the video for context
        score = (0.6 * float(s) / (float(sims.max()) or 1) + 0.15 * well_formed
                 + 0.1 * q["_w_eng"] / max_eng - 0.4 * deictic)
        if score > best_s:
            best, best_s = q, score
    return best


def _load_used() -> list[dict]:
    used = (load_config("used.yml") or {}).get("used") or []
    return [u if isinstance(u, dict) else {"id": str(u)} for u in used]


def main() -> dict:
    scfg = load_config("scoring.yml")
    tagger = Tagger(load_config("themes.yml"))
    matcher = DatasetMatcher(load_config("datasets.yml"))
    weights = scfg.get("weights", {"demand": 0.5, "answerability": 0.35, "freshness": 0.15})
    dparts = scfg.get("demand_parts", {"engagement": 0.4, "times_asked": 0.4, "distinct_sources": 0.2})
    sw = scfg.get("source_weights", {})
    half_life = scfg.get("freshness", {}).get("half_life_days", 45)
    window = scfg.get("freshness", {}).get("recent_window_days", 30)
    max_age = scfg.get("max_question_age_days", 730)

    all_q = json.loads(QUESTIONS_PATH.read_text()) if QUESTIONS_PATH.exists() else []
    # Dedupe identical wording within a source, drop stale
    seen, pool = set(), []
    for q in all_q:
        k = (q["source"], _normalize(q["question"]))
        if k in seen or _age_days(q["date"]) > max_age or not q["question"].strip():
            continue
        seen.add(k)
        w = float(sw.get(q["source"], 1.0))
        q = {**q, "_w": w, "_w_eng": q.get("engagement", 0) * w}
        q["theme"] = tagger.tag(q["question"], q.get("raw_text", ""))
        pool.append(q)
    cap = scfg.get("cluster", {}).get("max_questions", 8000)
    if len(pool) > cap:
        pool = sorted(pool, key=lambda q: q["_w_eng"], reverse=True)[:cap]

    groups, X, vec = cluster_questions(pool, scfg.get("cluster", {}).get("similarity_threshold", 0.45)) if pool else ([], None, None)
    active_sources = sorted({q["source"] for q in pool})

    clusters = []
    for idxs in groups:
        qs = [pool[i] for i in idxs]
        canon = _pick_canonical(qs, idxs, X)
        themes = Counter(q["theme"] for q in qs if q["theme"] != "other")
        theme = themes.most_common(1)[0][0] if themes else "other"
        text = " ".join(q["question"] for q in qs)
        ages = [_age_days(q["date"]) for q in qs]
        datasets = [d for d in matcher.match(theme, text) if d["score"] >= 3][:3]
        c = {
            "id": _cluster_id(qs),
            "question": canon["question"],
            "theme": theme,
            "count": len(qs),
            "weighted_count": round(sum(q["_w"] for q in qs), 2),
            "engagement": round(sum(q["_w_eng"] for q in qs), 1),
            "sources": sorted({q["source"] for q in qs}),
            "latest_date": max(q["date"] for q in qs),
            "first_date": min(q["date"] for q in qs),
            "recent_count": sum(1 for a in ages if a <= window),
            "datasets": datasets,
            "angle": _angle(canon["question"] + " " + text, scfg),
            "freshness_raw": _freshness(ages, half_life),
            "members": [{"question": q["question"], "source": q["source"], "origin": q.get("origin", ""),
                         "link": q["link"], "date": q["date"], "engagement": q["engagement"], "id": q["id"]}
                        for q in sorted(qs, key=lambda q: q["_w_eng"], reverse=True)],
            "_canon_idx": idxs[qs.index(canon)],
        }
        clusters.append(c)

    # Normalize demand parts across clusters
    max_e = max((math.log1p(c["engagement"]) for c in clusters), default=1) or 1
    max_n = max((math.log1p(c["weighted_count"]) for c in clusters), default=1) or 1
    n_src = max(1, len(active_sources))
    for c in clusters:
        e = 10 * math.log1p(c["engagement"]) / max_e
        n = 10 * math.log1p(c["weighted_count"]) / max_n
        s = 10 * len(c["sources"]) / n_src
        tot = sum(dparts.values()) or 1
        demand = (dparts["engagement"] * e + dparts["times_asked"] * n + dparts["distinct_sources"] * s) / tot
        answer = c["datasets"][0]["score"] if c["datasets"] else 0.0
        fresh = c.pop("freshness_raw")
        content = weights["demand"] * demand + weights["answerability"] * answer + weights["freshness"] * fresh
        c["scores"] = {"content": round(content, 2), "demand": round(demand, 2), "answerability": round(answer, 2),
                       "freshness": round(fresh, 2),
                       "demand_parts": {"engagement": round(e, 2), "times_asked": round(n, 2), "sources": round(s, 2)}}
        c["why"] = _why(c, scfg)

    # Used clusters: match by id, or by wording similarity to a used question
    used = _load_used()
    used_ids = {str(u.get("id")) for u in used}
    used_vecs = None
    used_qs = [u["question"] for u in used if u.get("question")]
    if vec is not None and used_qs:
        used_vecs = vec.transform(used_qs)
    for c in clusters:
        is_used = c["id"] in used_ids
        if not is_used and used_vecs is not None:
            sims = (used_vecs @ X[c["_canon_idx"]].T).toarray().ravel()
            is_used = bool(sims.size and sims.max() >= 0.6)
        c["used"] = is_used
        c.pop("_canon_idx")

    clusters.sort(key=lambda c: c["scores"]["content"], reverse=True)
    top_n = scfg.get("top_n", 10)
    top = [c for c in clusters if not c["used"]][:top_n]
    for rank, c in enumerate(top, 1):
        c["rank"] = rank

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    DATA.mkdir(exist_ok=True)
    (DATA / "clusters.json").write_text(json.dumps({"generated_at": now, "clusters": clusters}, indent=1, ensure_ascii=False))

    report = json.loads(REPORT_PATH.read_text()) if REPORT_PATH.exists() else {}
    site = {
        "generated_at": now,
        "weights": weights,
        "stats": {
            "questions": len(pool),
            "clusters": len(clusters),
            "by_source": dict(Counter(q["source"] for q in pool)),
            "by_theme": dict(Counter(c["theme"] for c in clusters)),
            "used": sum(c["used"] for c in clusters),
        },
        "run_report": report,
        "themes": list((load_config("themes.yml").get("themes") or {}).keys()) + ["other"],
        "top": [c["id"] for c in top],
        "clusters": [{**c, "members": c["members"][:25]} for c in clusters],
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "site.json").write_text(json.dumps(site, ensure_ascii=False, separators=(",", ":")))
    if (DATA / "311_summary.json").exists():
        shutil.copy(DATA / "311_summary.json", SITE_DATA / "311.json")
    print(f"[process] {len(pool)} questions -> {len(clusters)} clusters; top: "
          + "; ".join(f"{c['scores']['content']:.1f} {c['question'][:50]}" for c in top[:3]))
    return site


if __name__ == "__main__":
    main()
