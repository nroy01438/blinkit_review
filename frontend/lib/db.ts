import postgres from "postgres";

/** Single process-wide connection pool. Vercel runs each serverless function
 * invocation as its own short-lived process, so this doesn't stay warm
 * across requests the way a long-lived server's pool would — but `postgres`
 * still batches statements within one invocation and avoids the overhead of
 * hand-rolling connection setup per query inside a single request. */
declare global {
  // eslint-disable-next-line no-var
  var __sql: ReturnType<typeof postgres> | undefined;
}

export function sql() {
  if (!process.env.DATABASE_URL) {
    throw new Error(
      "DATABASE_URL is not set. Add it in Vercel's project environment variables (Settings -> Environment Variables) — same Supabase connection string the old backend used."
    );
  }
  if (!global.__sql) {
    global.__sql = postgres(process.env.DATABASE_URL, {
      ssl: "require",
      max: 3, // small — this runs in a serverless function, not a long-lived server
    });
  }
  return global.__sql;
}

let schemaReady: Promise<void> | null = null;

/** Reused tables (`sources`, `documents`) already exist in the real
 * database from the previous version of this project — nothing to migrate,
 * real review data already sitting there is kept. The only new thing this
 * app needs is a small cache table for the AI's answers, created here
 * instead of via a separate migration step, so there's nothing to run by
 * hand before the app works. */
export function ensureSchema() {
  if (!schemaReady) {
    schemaReady = (async () => {
      await sql()`
        CREATE TABLE IF NOT EXISTS question_answers (
          question_id    TEXT PRIMARY KEY,
          question       TEXT NOT NULL,
          answer         TEXT NOT NULL DEFAULT '',
          quotes         JSONB NOT NULL DEFAULT '[]'::jsonb,
          n_reviews      INT NOT NULL DEFAULT 0,
          generated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
      `;
      // Added after the table already existed in some deployments —
      // additive, safe to run every time.
      await sql()`ALTER TABLE question_answers ADD COLUMN IF NOT EXISTS kpi JSONB`;
    })();
  }
  return schemaReady;
}
