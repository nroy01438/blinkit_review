import gplayModule from "google-play-scraper";
import { FetchedReview, SourceRow } from "./types";

const gplay: any = (gplayModule as any).default ?? gplayModule;

/** Public Play Store reviews — no API key needed. Bounded to `limit` per
 * click since this runs inside a Vercel serverless function with a time
 * limit, not an always-on worker that can page through a whole app's
 * history in one go. */
export async function fetchPlayStoreReviews(source: SourceRow, limit: number): Promise<FetchedReview[]> {
  const packageName = source.config_json.package_name;
  const country = source.config_json.country || "in";
  const lang = source.config_json.lang || "en";
  if (!packageName) return [];

  const { data } = await gplay.reviews({
    appId: packageName,
    lang,
    country,
    sort: gplay.sort.NEWEST,
    num: limit,
  });

  return (data || []).map((r: any) => ({
    externalId: r.id,
    rawText: r.text || "",
    author: r.userName || "unknown",
    rating: r.score ?? null,
    postedAt: r.date ? new Date(r.date) : null,
    url: r.url || null,
    meta: { thumbs_up: r.thumbsUp, app_version: r.version, reply_text: r.replyText },
  }));
}
