import { sql } from "./db";
import { contentHash, hashAuthor } from "./hash";
import { FetchedReview } from "./connectors/types";

export async function persistReviews(sourceId: number, reviews: FetchedReview[]): Promise<{ fetched: number; inserted: number }> {
  let inserted = 0;
  for (const r of reviews) {
    if (!r.rawText || r.rawText.trim().length === 0) continue;
    const rows = await sql()`
      INSERT INTO documents (source_id, external_id, raw_text, author_hash, rating, posted_at, url, meta_json, content_hash)
      VALUES (
        ${sourceId}, ${r.externalId}, ${r.rawText}, ${hashAuthor(r.author)}, ${r.rating},
        ${r.postedAt}, ${r.url}, ${sql().json(r.meta as any)}, ${contentHash(r.rawText)}
      )
      ON CONFLICT (source_id, external_id) DO NOTHING
      RETURNING id
    `;
    if (rows.length > 0) inserted++;
  }
  return { fetched: reviews.length, inserted };
}
