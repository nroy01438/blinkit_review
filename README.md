# AISLE

**Why don't Blinkit users explore beyond their usual basket?**

A single page. Press **Sync reviews now**, and the app pulls the newest real
reviews and discussions from Play Store, App Store, and Reddit (plus a manual
upload for social media, since that can't be auto-scraped — see below), then
shows plain-English answers to the eight questions that matter for growing
category exploration, each backed by real quotes from the reviews it just
read. No schedule, no jargon, no separate technical dashboards.

## What changed from the previous version

The previous version of this project was a much bigger build: a separate
Python/FastAPI backend, a multi-stage LLM classification cascade, UMAP/HDBSCAN
theme clustering, IQS insight grading with adversarial verification, a formal
statistical evaluation harness (golden set, Cohen's kappa, calibration
curves), deployed across three platforms (Vercel + Render + Supabase) plus a
weekly GitHub Actions cron. It was real, tested engineering — and also
exactly the reason the product felt like an engineering console instead of a
PM tool.

This version keeps the goal and throws out the machinery in service of it:

- **One deployment, not three.** Everything lives in this one Next.js app
  (`frontend/`), deployed once to Vercel. There is no separate backend to
  host, monitor, or restart — the "backend" is just this app's own API
  routes, running as Vercel serverless functions.
- **One button, not a cron.** Sync is manual, on demand. No GitHub Actions,
  no scheduled job silently succeeding against a database nobody's looking
  at.
- **Direct AI synthesis, not a classification pipeline.** Each sync sends a
  sample of the real, most-recent reviews to Groq in one call, asking it to
  answer all eight questions in plain English with real supporting quotes.
  This trades away the formal statistics (confidence intervals, hypothesis
  tests) the old version had — if a specific number ever needs to be
  defensible in a board meeting, that's worth adding back deliberately, not
  by default.
- **The real data is kept.** The database (Supabase) is unchanged — the
  `sources` and `documents` tables already had real, already-synced reviews
  in them, and this app reads/writes the exact same tables. The only new
  thing is one small `question_answers` cache table, created automatically
  on first use.

## Setup

This app needs three environment variables, set in Vercel's project
settings (**Settings → Environment Variables** — not a local `.env` file,
since there's no separate backend to run):

| Variable | What it is |
|---|---|
| `DATABASE_URL` | The same Supabase connection string the previous backend used. |
| `GROQ_API_KEY` | Free at [console.groq.com](https://console.groq.com). |
| `AUTHOR_HASH_SALT` | Any random string — reviewers' usernames are hashed with this before being stored, never kept raw. |

Optional, for Reddit sync without rate-limit risk:

| Variable | What it is |
|---|---|
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Free, ~2 minutes at reddit.com/prefs/apps ("script" app type). Without these, Reddit sync falls back to Reddit's public unauthenticated search endpoint, which works but is more likely to get rate-limited. |

Once those are set, push to `main` (or click "Redeploy" in Vercel) and the
site is live. No database migration to run — the two tables it needs
(`sources`, `documents`) already exist with real data in them.

**You can shut down the old Render service and delete its Postgres
add-on if you had one separate from Supabase** — nothing points to Render
anymore. The old `backend/` (FastAPI/Python) directory, `Dockerfile`, and
`docker-compose.yml` were removed from this repo since nothing uses them;
they're still recoverable from git history if you ever want to reference
them.

## How sync actually works

Clicking **Sync reviews now** calls `POST /api/sync`, which:

1. Reads the active rows in the `sources` table (Play Store, App Store,
   Reddit, plus a couple of best-effort forum/review-site URLs already
   configured there from before).
2. Fetches up to ~50 of the newest items per source (`?limit=` to change
   this), skipping ones already in the database.
3. Sends a sample of the most recent ~300 real reviews to Groq in one call,
   asking it to answer all eight questions with real supporting quotes.
   Every quote is checked against the actual review text before being shown
   — a quote the model claims but that isn't a real substring of a real
   review is dropped, not displayed.
4. Caches the eight answers in `question_answers`, which is what the home
   page actually reads (so loading the page doesn't re-run the AI every
   time someone visits — only a sync does that).

**Honest limit**: Vercel serverless functions have a time cap (up to 60s is
configured here via `export const maxDuration = 60` in the sync route,
which is the practical ceiling on Vercel's Hobby plan). One click pulls a
bounded batch, not your whole history at once — click it again for more,
or raise `?limit=` a bit if a source's API allows it. If the real review
volume grows enough that this stops being enough per click, that's the
point to reconsider a dedicated background job instead of a
request/response click — not before.

**Social media conversations** are still not auto-scraped, on purpose — no
major platform's terms of service allow scraping logged-in surfaces
(X/Instagram/Facebook), and free API access no longer covers this either.
Use the **Upload** page: export what you have as a CSV with a `text`
column (optionally `author`, `rating`, `posted_at`, `url`), upload it, then
press sync to fold it into the answers.

## Local development

```bash
cd frontend
npm install
DATABASE_URL=<your-supabase-url> GROQ_API_KEY=<your-key> npm run dev
```

There's nothing else to start — no backend, no Docker, no local Postgres
required (though pointing `DATABASE_URL` at a local Postgres with the same
`sources`/`documents` tables works fine too, if you'd rather not develop
against production data).
