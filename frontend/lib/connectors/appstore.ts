import { FetchedReview, SourceRow } from "./types";

// Public iTunes RSS JSON feed — no auth, no third-party scraper package
// needed (the obvious npm scraper for this pulls in an old, vulnerable
// `request`-based dependency chain for no benefit over a plain fetch).
// Caps around page 10 (~500 reviews); one click only needs page 1-2.
const RSS_URL = (country: string, page: number, appId: string) =>
  `https://itunes.apple.com/${country}/rss/customerreviews/page=${page}/id=${appId}/sortby=mostrecent/json`;

export async function fetchAppStoreReviews(source: SourceRow, limit: number): Promise<FetchedReview[]> {
  const appId = source.config_json.app_id;
  const country = source.config_json.country || "in";
  if (!appId) return [];

  const reviews: FetchedReview[] = [];
  const maxPages = Math.min(10, Math.ceil(limit / 50) || 1);

  for (let page = 1; page <= maxPages; page++) {
    let json: any;
    try {
      const res = await fetch(RSS_URL(country, page, appId), { headers: { "User-Agent": "aisle-discovery-engine/0.2" } });
      if (res.status === 429 || !res.ok) break;
      json = await res.json();
    } catch {
      break; // one bad page must not fail the whole sync
    }
    const entries = json?.feed?.entry;
    if (!Array.isArray(entries) || (page === 1 && entries.length <= 1)) break; // page 1's first "entry" is often just feed metadata

    for (const entry of entries) {
      if (!entry["im:rating"]) continue; // skip the feed-metadata pseudo-entry
      reviews.push({
        externalId: entry.id?.label || `appstore-${page}-${reviews.length}`,
        rawText: entry.content?.label || "",
        author: entry.author?.name?.label || "unknown",
        rating: entry["im:rating"]?.label ? Number(entry["im:rating"].label) : null,
        postedAt: entry.updated?.label ? new Date(entry.updated.label) : null,
        url: entry.link?.attributes?.href || null,
        meta: { app_version: entry["im:version"]?.label },
      });
    }
    if (reviews.length >= limit) break;
  }
  return reviews.slice(0, limit);
}
