import { sql, ensureSchema } from "@/lib/db";
import { fetchPlayStoreReviews } from "@/lib/connectors/playstore";
import { fetchAppStoreReviews } from "@/lib/connectors/appstore";
import { fetchRedditPosts } from "@/lib/connectors/reddit";
import { fetchForumPages } from "@/lib/connectors/forum";
import { FetchedReview, SourceRow } from "@/lib/connectors/types";
import { persistReviews } from "@/lib/persist";
import { regenerateAnswers } from "@/lib/groq";
import { saveKpis } from "@/lib/kpis";
import { withTimeout } from "@/lib/withTimeout";

// Vercel's default function timeout is short (10s on Hobby) — this route
// does several external fetches plus one LLM call, so it needs more room.
// Hobby plans can raise this up to 60s; if a sync still needs more than
// that once real data volume grows, that's the point to reconsider a
// dedicated background job instead of a request/response click.
export const maxDuration = 60;

async function fetchForSource(source: SourceRow, limit: number): Promise<FetchedReview[]> {
  switch (source.kind) {
    case "playstore":
      return fetchPlayStoreReviews(source, limit);
    case "appstore":
      return fetchAppStoreReviews(source, limit);
    case "reddit":
      return fetchRedditPosts(source, limit);
    case "forum":
    case "marketplace":
      return fetchForumPages(source, limit);
    default:
      return [];
  }
}

export async function POST(req: Request) {
  await ensureSchema();
  const { searchParams } = new URL(req.url);
  const limitPerSource = Math.min(200, Number(searchParams.get("limit")) || 50);

  const sources = (await sql()`
    SELECT id, name, kind, config_json FROM sources WHERE is_active = true
  `) as unknown as SourceRow[];

  const perSource: Record<string, { fetched: number; inserted: number }> = {};
  const errors: Record<string, string> = {};

  for (const source of sources) {
    // Social/manual-upload sources have no automated fetch path by design
    // (no logged-in scraping) — they only ever get data via the Upload page.
    if (source.kind === "social" || source.kind === "manual_upload") continue;
    try {
      const reviews = await withTimeout(fetchForSource(source, limitPerSource), 20000, []);
      perSource[source.name] = await persistReviews(source.id, reviews);
      await sql()`UPDATE sources SET last_fetched_at = now() WHERE id = ${source.id}`;
    } catch (e: any) {
      errors[source.name] = String(e?.message || e);
    }
  }

  // KPIs are deterministic SQL counts, not an LLM call — computed and saved
  // unconditionally so the discovery-engine numbers are never blocked by a
  // Groq failure/rate-limit. The narrative below is best-effort on top.
  let kpisComputed = 0;
  try {
    kpisComputed = Object.keys(await saveKpis()).length;
  } catch (e: any) {
    errors["_kpis"] = String(e?.message || e);
  }

  let answers = { regenerated: 0, n_reviews: 0 };
  try {
    answers = await regenerateAnswers();
  } catch (e: any) {
    errors["_answers"] = String(e?.message || e);
  }

  return Response.json({ per_source: perSource, errors, kpis_computed: kpisComputed, answers });
}
