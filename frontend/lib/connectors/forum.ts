import * as cheerio from "cheerio";
import { FetchedReview, SourceRow } from "./types";

const USER_AGENT = "aisle-discovery-engine/0.2 (contact via GitHub repo)";

/** Best-effort text extraction from a public review/complaints page — no
 * per-site scraper, just strip obvious noise (nav/script/style/footer) and
 * take the remaining visible text. This is honestly weaker than a proper
 * per-site scraper: some sites block non-browser requests entirely (shows
 * up as 0 documents from this source, not a crash), and what comes back
 * for the ones that don't block it is a full page's on-topic text as ONE
 * document, not individually split-out reviews. Good enough as a starting
 * point; a real per-site parser is the natural next upgrade if a specific
 * source turns out to matter a lot. */
export async function fetchForumPages(source: SourceRow, limit: number): Promise<FetchedReview[]> {
  const seedUrls: string[] = source.config_json.seed_urls || [];
  const reviews: FetchedReview[] = [];

  for (const url of seedUrls.slice(0, limit)) {
    try {
      const res = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
      if (!res.ok) continue;
      const html = await res.text();
      const $ = cheerio.load(html);
      $("script, style, nav, header, footer, noscript").remove();
      const text = $("body").text().replace(/\s+/g, " ").trim();
      if (!text || text.length < 40) continue;
      reviews.push({
        externalId: url,
        rawText: text.slice(0, 8000),
        author: "unknown",
        rating: null,
        postedAt: null,
        url,
        meta: { crawled_via: "cheerio" },
      });
    } catch {
      continue; // one unreachable/blocking site must not kill the whole sync
    }
  }
  return reviews;
}
