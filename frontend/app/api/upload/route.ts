import { parse } from "csv-parse/sync";
import { sql, ensureSchema } from "@/lib/db";
import { persistReviews } from "@/lib/persist";
import { FetchedReview } from "@/lib/connectors/types";

/** Manual CSV/XLSX-as-CSV import — the compliant path for social media
 * conversations (no logged-in scraping of X/Instagram/etc., per the
 * project's own rule). Expected columns: text (required), author, rating,
 * posted_at, url — anything else is ignored. */
export async function POST(req: Request) {
  await ensureSchema();
  const form = await req.formData();
  const file = form.get("file") as File | null;
  if (!file) return Response.json({ error: "No file uploaded." }, { status: 400 });

  const text = await file.text();
  let rows: any[];
  try {
    rows = parse(text, { columns: true, skip_empty_lines: true, trim: true });
  } catch (e: any) {
    return Response.json({ error: `Couldn't parse CSV: ${e.message}` }, { status: 400 });
  }

  const [source] = await sql()`
    SELECT id FROM sources WHERE kind = 'manual_upload' LIMIT 1
  `;
  if (!source) {
    return Response.json({ error: "No 'manual_upload' source configured in the sources table." }, { status: 500 });
  }

  const reviews: FetchedReview[] = rows
    .filter((r) => r.text && String(r.text).trim())
    .map((r, i) => ({
      externalId: r.id || r.external_id || `upload-${file.name}-${i}-${Date.now()}`,
      rawText: String(r.text),
      author: r.author || "unknown",
      rating: r.rating ? Number(r.rating) : null,
      postedAt: r.posted_at ? new Date(r.posted_at) : null,
      url: r.url || null,
      meta: { uploaded_filename: file.name },
    }));

  const counts = await persistReviews(source.id, reviews);
  return Response.json(counts);
}
