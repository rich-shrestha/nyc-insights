# NYC Insights: Handoff for Claude Code

This file has the full context for continuing the **NYC Insights** build. The code is in this repo (committed locally, **not yet pushed**). Read this first, then `README.md`.

- **Owner:** Rich (GitHub: `rich-shrestha`)
- **Repo to create/push:** `github.com/rich-shrestha/nyc-insights` (public)
- **Site (after Pages is on):** https://rich-shrestha.github.io/nyc-insights/ (served from `main` → `/docs`)
- **Status date:** 2026-10-24

---

## 1. What this project is

Rich is starting "NYC Insights," a content account. He makes short videos that answer questions young New Yorkers actually ask, using NYC Open Data. This repo is the system behind it. It does three things:

1. **Collects** real questions from several sources into one file (`data/questions.json`).
2. **Decides which to answer and why.** It tags each question with a theme, groups near-duplicate questions into clusters, scores each cluster, and writes a plain-English reason for the score.
3. **Points to the data**: the NYC Open Data datasets (Socrata IDs) that could answer each cluster.

Everything runs in GitHub Actions on a weekly schedule, and the results show on a static GitHub Pages site that Rich checks from his phone.

**How Rich works:** he's on his phone most of the time. Before anything that needs his accounts (creating the repo, API keys, GitHub secrets, enabling Pages), **stop and give him exact step-by-step instructions he can follow on a phone.** Never ask him to paste API keys into chat; keys go in GitHub Actions secrets.

---

## 2. Original requirements (complete)

### Part 1: Collect questions
Each source is its own Python module. All write the same schema to `data/questions.json`: `question, source, link, date, engagement, raw_text`. **Never store usernames.** Each module **skips cleanly** if its keys are missing, so sources can be turned on one at a time.

1. **YouTube Data API** (`YT_API_KEY`): comments from NYC channels in `config/youtube.yml` (seeded with 10–15 popular NYC food, apartment-tour, and things-to-do channels). Keep only question-style comments: they contain "?" or start with who/what/where/how/is/does/anyone/best. Engagement = likes + replies.
2. **Bluesky** (`BSKY_HANDLE`, `BSKY_APP_PASSWORD`): `searchPosts` for the phrases in `config/bluesky.yml`. Seed phrases: "moving to NYC", "anyone know NYC", "best in Brooklyn", "NYC apartment", "NYC recommendations". Question-style posts only. Engagement = likes + reposts + replies.
3. **Stack Exchange API:** travel.stackexchange.com, tag `new-york-city`, last 2 years. Engagement = score + answer count.
4. **Manual Google Sheet** (published CSV link in `SHEET_CSV_URL`): columns `question, source, link, date, notes`. These rows get a **1.5x weight**. Walk Rich through creating the sheet and publishing it as CSV.
5. **Reddit** (disabled for now): PRAW, read-only app-only auth (`REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`), covering r/AskNYC, r/nyc, r/FoodNYC, and r/NYCapartments. Runs only if the keys exist. Rich has applied for API access.

Separately: **NYC 311 data** via Socrata (no auth). Save the top complaint types by neighborhood for the last 12 months to `data/311_summary.json`.

### Part 2: Decide what to answer and why
1. **Theme:** tag each question as one of: food & drink, apartments & neighborhoods, transit, safety, nightlife, things to do, cost of living, moving to NYC, other. Keyword rules live in editable `config/themes.yml`.
2. **Cluster:** group near-duplicates with TF-IDF and cosine similarity. Each cluster gets a canonical question, a count, and the sources it appeared in.
3. **Score** each cluster:
   - **Demand:** engagement + times asked + distinct sources, normalized to 0–10.
   - **Answerability:** whether an NYC Open Data dataset can answer it. Themes and keywords map to datasets in `config/datasets.yml`, which is seeded with restaurant inspections, 311, Citi Bike trips, MTA ridership, NYPD complaints, the street tree census, DOB permits, and rent/housing data. Each entry has a Socrata ID and a one-line note on what it answers. Scored 0–10.
   - **Freshness:** how recent the asks are, 0–10.
   - **Content score = 0.5 Demand + 0.35 Answerability + 0.15 Freshness.** The weights live in config.
4. **Why:** a plain-English explanation per cluster, e.g. "Asked 14 times across YouTube and Bluesky this month; answerable with restaurant inspection data; strong recommendation angle."

### Part 3: Site (GitHub Pages, static, mobile-first, clean)
- **This Week's Top 10 to Make:** score breakdown, the why, suggested datasets, and links to example source questions.
- **All Questions:** search; filter by theme and source; sort by content score, demand, or recency.
- **What NYC Complains About:** a 311 chart by complaint type and neighborhood.
- **Used toggle:** mark a cluster done (stored in `config/used.yml` through a simple documented process) so it drops off the Top 10.

### Part 4: Automation
- A GitHub Actions workflow runs **every Sunday night**: collect → tag, cluster, score → rebuild the site → commit. It also has a manual "run now" trigger.
- All keys are GitHub Actions secrets.

### Part 5: First content briefs (one time, after the first full run)
Write `content_briefs.md` for the **top 5 clusters**. Each brief covers:
- the question and why it's worth making (cite the score)
- the dataset and the **exact Socrata query** to run
- the analysis to do and the **one chart** to make
- a likely recommendation angle ("so if you want X, go to Y")
- a **60-second script outline**: hook, finding, recommendation, call to action

### How to work
- Stop before anything that needs Rich's accounts, and give exact phone-friendly steps.
- **Test each source on a small pull (~50 items) before the full run.**
- If a source returns too little NYC-relevant data, tell Rich and suggest better channels or queries.
- Finish with the README (project overview, how to edit each config, how to add questions via the sheet, how to trigger a refresh). Then send Rich the **live site URL** and **`content_briefs.md`**.

---

## 3. Current status

| Item | Status |
|---|---|
| All code (collectors, pipeline, site, workflows, README) | ✅ Written, committed locally (1 commit on `main`) |
| Local test on ~26 synthetic questions + mobile screenshots (390px, light/dark) | ✅ Works; no horizontal scroll, no JS errors |
| Mark-used script (add/remove/reject bad titles) | ✅ Tested locally |
| GitHub repo created | ❌ Rich has to create it (instructions sent) |
| Pushed to GitHub | ❌ Not yet |
| GitHub Pages enabled | ❌ Not yet |
| Secrets added | ❌ Not yet |
| Live ~50-item test pull per source | ❌ Not yet (has to run in Actions; see §4) |
| Full run | ❌ |
| `content_briefs.md` + `config/brief_queries.yml` | ❌ (`brief_queries.yml` is currently `queries: []`) |
| Send Rich the live URL + briefs | ❌ |

### Why nothing has run against live APIs yet
The previous environment (a cloud sandbox) was blocked by its egress proxy from reaching YouTube, Bluesky, Stack Exchange, and `data.cityofnewyork.us`/`data.ny.gov`. Its `gh` token was also invalid. So the plan was to push the repo and run every live test inside **GitHub Actions** with `workflow_dispatch` (mode `test`), using a short-lived fine-grained PAT from Rich. **If your environment has normal internet, run the tests locally first** (`python run_all.py --test`), which is faster.

---

## 4. Next steps (in order)

### Step A: Repo + auth (Rich does this)
Rich was asked to:
1. Create `github.com/new` → name `nyc-insights` → **Public** → no README/.gitignore/license → Create.
2. Either authenticate `gh` locally himself, **or** create a fine-grained PAT: github.com/settings/personal-access-tokens/new, 7-day expiry, only `nyc-insights`, Read+Write on **Actions, Contents, Issues, Pages, Workflows**.

If you're in Claude Code on Rich's own machine, the simplest path is `gh auth login`, then `gh repo create rich-shrestha/nyc-insights --public --source=. --push`.

### Step B: Push + enable Pages
```bash
git remote add origin https://github.com/rich-shrestha/nyc-insights.git
git push -u origin main
# Enable Pages from main /docs
gh api -X POST repos/rich-shrestha/nyc-insights/pages \
  -f "source[branch]=main" -f "source[path]=/docs"
```
Workflows declare `permissions: contents: write`, so the repo's default token setting doesn't need changing.

### Step C: Small-pull tests (~50 items per source)
Run locally if you have internet:
```bash
pip install -r requirements.txt
python run_all.py --test --only stackexchange nyc311   # no keys needed
cat data/run_report.json
```
Or in Actions:
```bash
gh workflow run weekly.yml -f mode=test -f only="stackexchange nyc311"
gh run watch; gh run view --log | tail -100
git pull   # results are committed by the bot
```
Note: `nyc311 --test` fetches only 50 grouped rows and **does not overwrite** `311_summary.json`. That's intentional.

Then, once Rich has added secrets, test `youtube bluesky sheet` the same way. **Check `data/run_report.json`:**
- `youtube.channels_unresolved`: these handles in `config/youtube.yml` are guesses. Fix or replace any that don't resolve (see §7).
- `youtube.per_channel`: a channel with lots of `read` and very few `kept` isn't useful; swap it out.
- `bluesky.per_query`: `question_style` vs `nyc_relevant` vs `kept`. If kept is low, suggest better phrases.
- `stackexchange.kept`: travel.SE's NYC tag is low-volume. Expect roughly tens of questions over 2 years. Tell Rich if it's thin.
- **Report thin sources to Rich with concrete alternative channels or queries** (this is a requirement).

### Step D: Secrets (Rich does this; do not ask for the values)
Repo → Settings → Secrets and variables → Actions → New repository secret:
`YT_API_KEY`, `BSKY_HANDLE`, `BSKY_APP_PASSWORD`, `SHEET_CSV_URL`. Optional: `SOCRATA_APP_TOKEN`, `STACKEXCHANGE_KEY`. Later: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`.
Phone instructions for each key are in `README.md` → "Secrets" and "Adding questions via the Google Sheet." **The Sheet walkthrough still has to be given to Rich directly**; copy it from the README.

### Step E: Full run
`gh workflow run weekly.yml -f mode=full`. Then check the site, `data/clusters.json`, and the run summary. Tune `config/scoring.yml → cluster.similarity_threshold` if clusters look fragmented (lower to 0.4) or lumped together (raise to 0.6). Use `mode=rescore` to re-score without re-collecting.

### Step F: Content briefs
1. Read the top 5 unused clusters from `data/clusters.json` (sorted by `scores.content`).
2. For each one, write the Socrata query (SoQL) that answers it and add it to `config/brief_queries.yml`:
   ```yaml
   queries:
     - key: pizza_grades_by_nta          # becomes data/brief_results/<key>.json
       domain: data.cityofnewyork.us
       dataset: 43nn-pn8j
       params:
         $select: "nta, count(distinct camis) AS restaurants, sum(case(grade='A',1,true,0)) AS a_rows"
         $where: "cuisine_description='Pizza' AND inspection_date >= '2025-10-01'"
         $group: "nta"
         $order: "restaurants DESC"
         $limit: 50
   ```
3. Run `python scripts/run_queries.py` (or `gh workflow run brief-queries.yml`). It saves results to `data/brief_results/` and fails loudly on a bad query. **Every query in the briefs must have actually executed.**
4. Write `content_briefs.md` at the repo root using the real numbers. Each brief needs: question + why (cite content/demand/answerability/freshness scores and the why text), dataset + exact query (as a full URL **and** the SoQL params), the analysis, the one chart, the recommendation angle, and a 60-second script (hook / finding / recommendation / CTA).
5. Commit and push. Send Rich the live site URL and `content_briefs.md`.

### Step G: Wrap up
- Tell Rich to revoke the PAT if one was used.
- Update the project note (claude.ai Project "NYC insights content", doc `claude/nyc-insights-build-status.md`) if you have access.

---

## 5. Architecture

```
collectors/
  common.py         schema, is_question(), mentions_nyc(), scrub() (removes @mentions/u/names/URLs),
                    extract_question(), make_record() (adds stable id), save_questions() (upsert),
                    update_report() -> data/run_report.json
  youtube.py        channels.list(forHandle|id) -> uploads playlist -> recent videos ->
                    commentThreads (order=relevance) + optional search.list queries
  bluesky.py        createSession @ bsky.social -> app.bsky.feed.searchPosts (auth'd).
                    Must be question-style AND mention an NYC term. Link uses DID, not handle.
  stackexchange.py  /2.3/questions site=travel tagged=new-york-city fromdate=-730d, filter=withbody
  sheet.py          CSV via requests; origin = the sheet's "source" column; engagement = sheet_base_engagement
  reddit.py         PRAW read_only; top(month)+new per subreddit; lazy import; skipped without keys
  nyc311.py         one grouped SoQL query (community_board, complaint_type, count(*)) for the last 365 days;
                    maps community districts to neighborhood names; citywide top 15; per-hood top 10;
                    "distinctive" = location quotient vs citywide (min 200 requests)
pipeline/process.py tag -> cluster -> score -> why -> used -> outputs
run_all.py          --test (limit 50) | --limit N | --only <sources> | --skip-collect
scripts/mark_used.py   parses issue title "used: <id>" / "unuse: <id>" (strict regex) -> config/used.yml
scripts/run_queries.py runs config/brief_queries.yml -> data/brief_results/*.json
docs/               index.html, style.css, app.js (vanilla JS; loads data/site.json + data/311.json)
.github/workflows/
  weekly.yml        cron "17 3 * * 1" (Sun ~11pm ET) + workflow_dispatch(mode: full|test|rescore, only)
  mark-used.yml     on issues.opened; only if author == repo owner and title starts used:/unuse:
                    -> mark_used.py -> run_all --skip-collect -> commit -> close issue
  brief-queries.yml manual; runs scripts/run_queries.py and commits results
```
All three workflows share `concurrency: data-writes` and use `git pull --rebase --autostash` before pushing.

### Data files
- `data/questions.json`: accumulating store, upserted by `id` = sha1(source|link|question)[:12]. Fields: schema fields + `id`, `origin` (channel/query/subreddit/sheet source), `first_seen`, optional `notes`.
- `data/run_report.json`: per-source stats from the last run (reset on a full run of all sources).
- `data/311_summary.json`: copied to `docs/data/311.json`.
- `data/clusters.json`: all clusters, full members.
- `docs/data/site.json`: what the site reads (clusters with ≤25 members, top ids, stats, run report, weights, themes).

### Pipeline details (`pipeline/process.py`)
- **Pool:** dedupe identical normalized wording within a source; drop items older than `max_question_age_days` (730); cap at `cluster.max_questions` (8000, keeping the most engaged).
- **Theme:** whole-word regex per theme; most hits wins; ties go to the theme listed first in the YAML; tries the question first, then `raw_text`. A cluster's theme = most common non-"other" member theme.
- **Clustering:** TF-IDF on **unigrams** after stop-word removal (sklearn English + extras like nyc/new/york/anyone) and crude singularization; `sublinear_tf`; L2-normalized. **Leader clustering:** questions are visited by weighted engagement (desc); each joins the most similar leader if cosine ≥ `similarity_threshold` (0.5), otherwise it becomes a new leader. Bigrams and char n-grams were tested and dropped: unigrams separated same-topic pairs (~0.71) from different-topic pairs (~0.42) best.
- **Canonical question:** maximizes 0.6·sim-to-centroid + 0.15·well-formed (ends with "?", 5–25 words) + 0.1·engagement − 0.4·deictic (contains this/that/he/she/you…, e.g. "where is this place?" needs the video for context).
- **Cluster id:** sha1 of the earliest member's id (by first_seen, date, id)[:10]. Stays stable as new questions join.
- **Demand:** engagement part = 10·log1p(E)/log1p(maxE); times-asked part = 10·log1p(weighted count)/log1p(max); sources part = 10·n_sources/n_active_sources; blended 0.4/0.4/0.2 (`demand_parts`). Source weights multiply both count and engagement (sheet 1.5).
- **Answerability:** per dataset, min(max_score or 10, 4·theme_match + 3·min(2, keyword hits)). Plural duplicates are collapsed (bagel/bagels count once). The best dataset sets the score; the top 3 with score ≥3 are suggested.
- **Freshness:** 10·(0.6·0.5^(newest_age/45) + 0.4·0.5^(median_age/45)).
- **Angle:** the first regex in `scoring.yml → angles` that matches the canonical question + member text. Order: ranking → recommendation → safety → price → comparison → myth-busting → timing → default "explainer".
- **Why:** "Asked N times on A and B (k in the last 30 days); X total likes/replies/votes; answerable with <dataset> (matches 'kw1', 'kw2'); <angle>."
- **Used:** a cluster counts as used if its id is in `used.yml`, OR its canonical question has cosine ≥0.6 with a used entry's `question` (fallback in case ids drift). Used clusters are excluded from the Top 10.

### Site behavior (`docs/app.js`)
- Owner and repo are derived from the Pages URL (fallback `rich-shrestha/nyc-insights`).
- **All scraped text is HTML-escaped; only http(s) links are allowed.** Keep it that way: this is untrusted content.
- "Mark used" opens `github.com/<owner>/<repo>/issues/new?title=used: <id>&body=…` and hides the card locally right away (localStorage, wrapped in try/catch, best-effort). The bot makes it permanent.
- 311 tab: a neighborhood `<select>` (citywide + 59 community districts); horizontal bars in one hue (light `#2a78d6`, dark `#3987e5`); hover/focus tooltip; "Unusually common here" list.
- Dark mode uses the `prefers-color-scheme` and `[data-theme]` tokens in `style.css`.

---

## 6. Config files (all user-editable)

| File | Purpose |
|---|---|
| `config/youtube.yml` | 14 channels (handle or channel_id + category), `videos_per_channel: 6`, `comments_per_video: 100`, `max_video_age_days: 365`, 3 `search_queries` (100 quota units each) |
| `config/bluesky.yml` | 5 seed queries, 100 posts/page, 2 pages, `sort: latest` |
| `config/filters.yml` | question starters (who, what, where, how, is, does, anyone, best, which, can, should, any, are), `min_words: 4`, `max_chars: 600`, `exclude_phrases` (what song, what camera, subscribe…), `nyc_terms` (for Bluesky relevance) |
| `config/themes.yml` | keyword lists per theme |
| `config/datasets.yml` | 16 datasets (below) with themes, keywords, key_fields, optional `max_score` |
| `config/scoring.yml` | weights 0.5/0.35/0.15, demand_parts, source_weights (sheet 1.5), sheet_base_engagement 5, half_life 45, recent window 30, threshold 0.5, max_questions 8000, max age 730, top_n 10, angles |
| `config/used.yml` | `used: []`, list of `{id, question, date}` |
| `config/brief_queries.yml` | `queries: []` (fill in for Step F) |

---

## 7. NYC Open Data datasets (IDs and columns verified 2026-10-24 via Socrata metadata)

| Key | Dataset | Domain / ID | Useful columns |
|---|---|---|---|
| restaurant_inspections | DOHMH Restaurant Inspection Results | data.cityofnewyork.us / `43nn-pn8j` | camis, dba, boro, zipcode, cuisine_description, inspection_date, action, violation_code, violation_description, critical_flag, score, grade, grade_date, inspection_type, latitude, longitude, community_board, nta |
| service_requests_311 | 311 Service Requests 2020–present | data.cityofnewyork.us / `erm2-nwe9` | created_date, closed_date, agency, complaint_type, descriptor, location_type, incident_zip, city, status, community_board (e.g. "08 MANHATTAN"), borough, latitude, longitude |
| citibike_trips | Citi Bike trip histories | **not on Socrata**: monthly CSVs at citibikenyc.com/system-data (S3 `tripdata`) | started_at, ended_at, start/end_station_name, member_casual, rideable_type |
| bicycle_counts | Bicycle Counts (Historical) | data.cityofnewyork.us / `uczf-rk3c` | countid, id, date, counts, status (counter metadata is in a separate dataset) |
| mta_subway_hourly | MTA Subway Hourly Ridership: Beginning 2025 | **data.ny.gov** / `5wq4-mkjj` | transit_timestamp, transit_mode, station_complex_id, station_complex, borough, payment_method, fare_class_category, ridership, transfers, latitude, longitude |
| mta_daily_ridership | MTA Daily Ridership and Traffic: Beginning 2020 | **data.ny.gov** / `sayj-mze2` | date, mode, count |
| nypd_complaints_ytd | NYPD Complaint Data Current (YTD) | data.cityofnewyork.us / `5uac-w243` | cmplnt_fr_dt, boro_nm, addr_pct_cd, ofns_desc, law_cat_cd, prem_typ_desc, station_name, transit_district, latitude, longitude |
| nypd_shootings | Shootings (2006–present) | data.cityofnewyork.us / `5ucz-vwe8` | incident_key, occur_date, occur_time, boro, precinct, loc_classfctn_desc, location_desc, latitude, longitude |
| street_trees | 2015 Street Tree Census | data.cityofnewyork.us / `uvpi-gqnh` | spc_common, health, tree_dbh, status, nta, nta_name, boroname, zipcode, latitude, longitude |
| dob_permits_now | DOB NOW: Build – Approved Permits | data.cityofnewyork.us / `rbx6-tga4` | work_type, borough, zip_code, community_board, issued_date, approved_date, job_description, estimated_job_costs, permit_status |
| dob_permit_issuance | DOB Permit Issuance (legacy) | data.cityofnewyork.us / `ipu4-2q9a` | borough, zip_code, job_type, permit_type, work_type, issuance_date, residential, community_board |
| hpd_violations | HPD Housing Maintenance Code Violations | data.cityofnewyork.us / `wvxf-dwi5` | boro, housenumber, streetname, zip, class, inspectiondate, novdescription, currentstatus, violationstatus, rentimpairing, communityboard |
| hpd_complaints | HPD Complaints and Problems | data.cityofnewyork.us / `ygpa-z7cr` | received_date, borough, post_code, major_category, minor_category, problem_status, community_board, nta |
| rodent_inspections | DOHMH Rodent Inspection | data.cityofnewyork.us / `p937-wjvj` | inspection_date, inspection_type, result, zip_code, borough, nta, latitude, longitude |
| affordable_housing | Affordable Housing Production by Building | data.cityofnewyork.us / `hg8x-zxpr` (max_score 6: it doesn't give market rent) | project_name, borough, neighborhood_tabulation_area, building_completion_date, studio_units, _1_br_units, all_counted_units, *_income_units |
| permitted_events | NYC Permitted Event Information | data.cityofnewyork.us / `tvpp-9vvx` | event_name, start_date_time, end_date_time, event_type, event_borough, event_location |

Query pattern: `https://<domain>/resource/<id>.json?$select=...&$where=...&$group=...&$order=...&$limit=...`. Dataset page: `https://<domain>/d/<id>`.

**Gap to flag to Rich:** NYC Open Data has no good **market-rent** dataset. "How much is rent in X?" questions can only be partly answered (affordable-housing units, HPD complaints as proxies). Mention this if rent clusters rank high.

---

## 8. Known risks / things to verify

1. **YouTube handles are best guesses.** Likely correct: `@eater`, `@FoodInsider`, `@munchies`, `@calebsimpson`, `@RyanSerhant`, `@ErikConover`, `@UntappedNewYork`, `@Thrillist`. **Uncertain:** `@theinfatuation`, `@BrunchBoys`, `@spencerhardwick`, `@Elegran`, `@TimeOut`, `@SecretNYC`. The test run lists unresolved ones in `run_report.json → youtube.channels_unresolved`. Replace them with real NYC channels (food reviewers, apartment-tour/rent channels, NYC vloggers).
2. **YouTube comment noise:** many comments are "where is this place?" (context-dependent) or off-topic. `exclude_phrases` plus the deictic penalty help. Inspect the kept comments and extend `exclude_phrases` if needed. National channels (Eater, Insider, Munchies, Thrillist) have non-NYC videos, and the collector doesn't filter videos by NYC title. **Possible improvement:** only keep videos whose title or description mentions an NYC term (`mentions_nyc`) for channels with `category` other than an NYC-only channel.
3. **Bluesky:** `searchPosts` needs auth, which the code handles through `createSession` at `bsky.social`. Rate limits are generous. If the PDS host differs for Rich's account, `bsky.social` usually still works for session creation. The `lang=en` param is passed.
4. **311 query size:** one grouped query over ~3M+ rows. It uses a 180s timeout with 4 retries and backoff. If it times out, add `SOCRATA_APP_TOKEN` or split it by month or borough.
5. **Stack Exchange** volume is probably low; that's expected.
6. **Clustering quality** has only been checked on synthetic data. Look at real clusters after the full run and tune the threshold.
7. **Theme keywords** like "free", "show", "car", "path", "heat" are broad. Watch for mis-tags.
8. The scheduled run on a **public** repo is disabled by GitHub after 60 days without repo activity. Weekly bot commits keep it alive.
9. Never print secrets in logs. The collectors log counts only.

---

## 9. Local dev quick reference

```bash
pip install -r requirements.txt           # requests, PyYAML, scikit-learn, numpy, scipy, praw
python run_all.py --test                  # ~50/source, then process
python run_all.py --only youtube --limit 50
python run_all.py --skip-collect          # re-score after config edits
python scripts/mark_used.py "used: <id>"  # same as the bot
python scripts/run_queries.py             # brief queries
cd docs && python -m http.server 8000     # preview the site
```
Commits should end with Rich's attribution lines if your environment specifies them. The first commit was authored as "Rich Shrestha <richshre@gmail.com>".

---

## 10. Definition of done
- [ ] Repo public on GitHub, Pages live at https://rich-shrestha.github.io/nyc-insights/
- [ ] Each enabled source passed a ~50-item test; thin sources reported to Rich with suggestions
- [ ] Full run committed; Top 10 looks sensible; 311 tab populated
- [ ] Mark-used flow tested end to end (open an issue as the owner → bot commits → card gone)
- [ ] `config/brief_queries.yml` filled; every query executed successfully
- [ ] `content_briefs.md` (top 5) committed with real numbers
- [ ] Rich receives the live URL + `content_briefs.md`; PAT revoked if one was used
