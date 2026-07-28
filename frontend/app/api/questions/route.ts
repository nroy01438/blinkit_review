import { sql, ensureSchema } from "@/lib/db";

// Otherwise Next tries to statically prerender this at build time, which
// fails without DATABASE_URL set in the build environment — this route
// always needs a live DB read, never a cached static response.
export const dynamic = "force-dynamic";

export async function GET() {
  await ensureSchema();

  const answers = await sql()`
    SELECT question_id, question, answer, quotes, n_reviews, generated_at
    FROM question_answers ORDER BY question_id
  `;

  const [{ n: totalReviews }] = await sql()`
    SELECT count(*) AS n FROM documents WHERE dupe_of_id IS NULL
  `;

  const sourceMix = await sql()`
    SELECT s.name, s.brand, count(*) AS n
    FROM documents d JOIN sources s ON s.id = d.source_id
    WHERE d.dupe_of_id IS NULL
    GROUP BY 1, 2 ORDER BY n DESC
  `;

  const sources = await sql()`
    SELECT name, kind, is_active, last_fetched_at FROM sources ORDER BY name
  `;

  return Response.json({
    questions: answers,
    total_reviews: Number(totalReviews),
    source_mix: sourceMix,
    sources,
  });
}
