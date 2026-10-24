# NYC Insights

A question radar for a data-driven NYC content account. Every week it:

1. **Collects** real questions young New Yorkers ask (YouTube comments, Bluesky, Stack Exchange, a hand-curated Google Sheet, and Reddit once API access is approved), plus a 12-month NYC 311 summary.
2. **Decides what to answer and why** by tagging themes, clustering near-duplicate questions, and scoring each cluster on demand, answerability with NYC Open Data, and freshness.
3. **Points to the data** with the matching NYC Open Data datasets (Socrata IDs) for each question.

**Live site:** https://rich-shrestha.github.io/nyc-insights/ (mobile-first; open it on your phone)

---

## How it fits together

```
collectors/            one module per source -> data/questions.json (same schema)
  youtube.py           YT_API_KEY
  bluesky.py           BSKY_HANDLE + BSKY_APP_PASSWORD
  stackexchange.py     no key needed
  sheet.py             SHEET_CSV_URL
  reddit.py            REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET (off until keys exist)
  nyc311.py            no key -> data/311_summary.json
pipeline/process.py    theme -> cluster -> score -> "why" -> data/clusters.json + docs/data/site.json
docs/                  the GitHub Pages site (static HTML/JS)
config/                everything you can tune (see below)
run_all.py             runs it all
.github/workflows/     weekly refresh, mark-used bot, brief queries
content_briefs.md      first 5 video briefs
```

Every question record has: `question, source, link, date, engagement, raw_text` (+ `id`, `origin`, `first_seen`). **No usernames are stored.** @mentions and u/names are scrubbed from text, and links point to the post itself (Bluesky links use the account's anonymous DID, not its handle).

A source with missing keys is skipped cleanly, so you can turn sources on one at a time by adding secrets.

## Scoring

| Part | What it measures | 0–10 how |
|---|---|---|
| **Demand** | total engagement + times asked + distinct sources | each part log-scaled against the top cluster, blended 40/40/20 |
| **Answerability** | can NYC Open Data answer it? | best dataset in `datasets.yml`: +4 theme match, +3 per keyword match (max 2) |
| **Freshness** | how recent the asks are | 10 = today, halves every 45 days (blend of newest + median ask) |

**Content score = 0.5 × Demand + 0.35 × Answerability + 0.15 × Freshness.** Sheet questions count 1.5×.

Each cluster gets a plain-English **why**, e.g. *"Asked 14 times on YouTube and Bluesky (9 in the last 30 days); 1,240 total likes/replies/votes; answerable with DOHMH Restaurant Inspection Results (matches 'pizza'); strong recommendation angle."*

---

## Editing the configs (on your phone)

Open the file on github.com → tap the **pencil** (Edit) → change it → **Commit changes**. The next run uses it. To re-score right away without re-collecting, run the workflow (see "Trigger a refresh") in `rescore` mode.

| File | What to change |
|---|---|
| `config/youtube.yml` | Channels (`handle: "@name"` from the channel URL, or `channel_id: UC...`), videos per channel, comments per video, search queries |
| `config/bluesky.yml` | Search phrases, posts per query, `latest` vs `top` |
| `config/filters.yml` | What counts as a question (starter words, min length), phrases to drop (e.g. "what song"), NYC terms Bluesky posts must mention |
| `config/themes.yml` | Theme keywords. Most hits wins; ties go to the theme listed first; no hits = "other" |
| `config/datasets.yml` | NYC Open Data datasets: Socrata ID, what it answers, which themes/keywords it matches, optional `max_score` cap |
| `config/scoring.yml` | Score weights, demand blend, sheet weight, freshness half-life, cluster similarity threshold (higher = tighter clusters), recommendation-angle patterns, Top N |
| `config/used.yml` | Clusters you've already made (drop off the Top 10) |
| `config/brief_queries.yml` | Socrata queries behind `content_briefs.md` (run via the "Run brief queries" workflow) |

**Tip:** if clusters look too fragmented (same question split up), lower `cluster.similarity_threshold` to 0.4. If unrelated questions are lumped together, raise it to 0.6.

## Marking a cluster as used

On the site, tap **Mark used** on any card → GitHub opens a pre-filled issue (`used: <id>`) → tap **Submit new issue**. The "Mark used" workflow adds it to `config/used.yml`, rebuilds the site, and closes the issue (≈2 min). The card hides on your phone right away.

- Undo: open a new issue titled `unuse: <id>`.
- Or edit `config/used.yml` directly. Each entry has `id`, `question`, `date`. If a cluster's id changes between weeks, it's still matched by its question wording.
- Only issues opened by the repo owner are processed.

## Adding questions via the Google Sheet

### One-time setup (5 minutes; use a browser, since the Sheets app can't publish)
1. On your phone browser, go to **sheets.google.com**. If it pushes you to the app, open the browser menu and choose **Desktop site**.
2. Tap **+ / Blank spreadsheet**. Name it `NYC Insights questions`.
3. In row 1, type these headers in A–E exactly: `question` | `source` | `link` | `date` | `notes`
4. **File → Share → Publish to web**.
5. Under **Link**, change "Entire document" to the tab (`Sheet1`) and "Web page" to **Comma-separated values (.csv)**.
6. Tap **Publish** → **OK**. Copy the URL (it ends in `output=csv`). Keep "Automatically republish when changes are made" checked (under *Published content & settings*).
7. Add it as the GitHub secret **`SHEET_CSV_URL`** (see "Secrets" below).

### Adding a question
Add a row anytime (the Sheets app works fine for this):

| question | source | link | date | notes |
|---|---|---|---|---|
| What's the quietest neighborhood under $3k? | r/AskNYC | https://reddit.com/r/AskNYC/... | 2026-10-20 | 300 upvotes |

- `source` = where you saw it (r/AskNYC, TikTok, Instagram, friend). Free text.
- `date` = YYYY-MM-DD (blank = today).
- Rows count 1.5× in Demand. They show up after the next run.

## Secrets (API keys)

github.com/rich-shrestha/nyc-insights → **Settings → Secrets and variables → Actions → New repository secret**. On a phone, use the browser's **Desktop site** mode if the page is cut off.

| Secret | Source | Where to get it |
|---|---|---|
| `YT_API_KEY` | YouTube | console.cloud.google.com → New project → APIs & Services → Library → *YouTube Data API v3* → Enable → Credentials → Create credentials → API key (restrict it to YouTube Data API v3) |
| `BSKY_HANDLE` | Bluesky | your handle, e.g. `name.bsky.social` |
| `BSKY_APP_PASSWORD` | Bluesky | Bluesky → Settings → Privacy and security → App passwords → Add |
| `SHEET_CSV_URL` | Sheet | the published CSV link above |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | Reddit | reddit.com/prefs/apps after approval → create a **script** app (read-only) |
| `SOCRATA_APP_TOKEN` *(optional)* | 311/NYC Open Data | data.cityofnewyork.us → sign in → Developer settings → Create new app token (higher rate limits) |
| `STACKEXCHANGE_KEY` *(optional)* | Stack Exchange | stackapps.com/apps/oauth/register (raises daily quota) |

## Trigger a refresh

- **Automatic:** every Sunday ~11pm New York time.
- **Now:** repo → **Actions** → **Weekly refresh** → **Run workflow** → pick `full`, `test` (~50 items per source), or `rescore` (re-score after config edits, no collecting) → optionally type sources in `only` (e.g. `youtube bluesky`) → **Run workflow**. Takes ~5–10 minutes; the site updates a minute after it finishes.
- Each run's **Summary** tab shows how many questions each source returned. If a source is thin, adjust its config.
- The site's **How it works** tab also has a "Run a refresh now" link.

## Run locally (optional)

```bash
pip install -r requirements.txt
export YT_API_KEY=...   # any keys you have
python run_all.py --test         # small pull
python run_all.py                # full
python run_all.py --skip-collect # re-score only
cd docs && python -m http.server # view the site at localhost:8000
```

## Data sources & quotas

- **YouTube Data API:** 10,000 units/day free. A full run uses ~400–600 (each search query = 100).
- **Bluesky:** authenticated `app.bsky.feed.searchPosts`; generous limits.
- **Stack Exchange:** 300 requests/day without a key; a run uses 1–3.
- **NYC Open Data (Socrata):** no key needed; an app token avoids throttling.
- **Citi Bike trips** aren't on Socrata. Monthly CSVs are at citibikenyc.com/system-data. They're listed in `datasets.yml` so bike questions still score as answerable.
