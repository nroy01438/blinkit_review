import { FetchedReview, SourceRow } from "./types";

const USER_AGENT = "aisle-discovery-engine/0.2 (contact via GitHub repo)";

async function getAppOnlyToken(): Promise<string | null> {
  const id = process.env.REDDIT_CLIENT_ID;
  const secret = process.env.REDDIT_CLIENT_SECRET;
  if (!id || !secret) return null;
  const res = await fetch("https://www.reddit.com/api/v1/access_token", {
    method: "POST",
    headers: {
      Authorization: `Basic ${Buffer.from(`${id}:${secret}`).toString("base64")}`,
      "Content-Type": "application/x-www-form-urlencoded",
      "User-Agent": USER_AGENT,
    },
    body: "grant_type=client_credentials",
  });
  if (!res.ok) return null;
  const json = await res.json();
  return json.access_token ?? null;
}

/** Reddit discussions — uses OAuth app-only credentials if REDDIT_CLIENT_ID/
 * SECRET are set (free to create at reddit.com/prefs/apps, "script" type),
 * otherwise falls back to Reddit's public unauthenticated search endpoint,
 * which works for read-only access but is more likely to be rate-limited. */
export async function fetchRedditPosts(source: SourceRow, limit: number): Promise<FetchedReview[]> {
  const subreddits: string[] = source.config_json.subreddits || [];
  const terms: string[] = source.config_json.query_terms || [];
  if (subreddits.length === 0 || terms.length === 0) return [];

  const token = await getAppOnlyToken();
  const base = token ? "https://oauth.reddit.com" : "https://www.reddit.com";
  const headers: Record<string, string> = { "User-Agent": USER_AGENT };
  if (token) headers.Authorization = `Bearer ${token}`;

  const perTerm = Math.max(1, Math.ceil(limit / (subreddits.length * terms.length)));
  const reviews: FetchedReview[] = [];

  for (const sub of subreddits) {
    for (const term of terms) {
      const url = `${base}/r/${sub}/search.json?q=${encodeURIComponent(term)}&restrict_sr=1&sort=new&limit=${perTerm}`;
      try {
        const res = await fetch(url, { headers });
        if (!res.ok) continue;
        const json = await res.json();
        const children = json?.data?.children || [];
        for (const c of children) {
          const p = c.data;
          reviews.push({
            externalId: p.id,
            rawText: `${p.title || ""}\n\n${p.selftext || ""}`.trim(),
            author: p.author || "deleted",
            rating: null,
            postedAt: p.created_utc ? new Date(p.created_utc * 1000) : null,
            url: p.permalink ? `https://reddit.com${p.permalink}` : null,
            meta: { subreddit: sub, score: p.score, kind: "submission" },
          });
        }
      } catch {
        continue; // one bad subreddit/term must not kill the whole sync
      }
      if (reviews.length >= limit) return reviews.slice(0, limit);
    }
  }
  return reviews.slice(0, limit);
}
