import { sql, ensureSchema } from "./db";
import { QUESTIONS } from "./questions";

/** Deterministic, keyword-derived KPIs — computed directly against the real
 * corpus with SQL regex counts, not asked of the LLM. This is the actual
 * "discovery engine" numbers: always available even if the Groq call fails
 * or is rate-limited, and verifiable (anyone can re-run the same regex
 * against the same data and get the same count). The LLM's job (see
 * groq.ts) is the plain-English narrative and quotes on top of this, not
 * the number itself.
 *
 * Patterns are deliberately simple keyword proxies, not a claim of
 * exhaustive coverage — good enough to answer "roughly how often does this
 * show up," not a formal classifier.
 *
 * These are Postgres regex strings (passed straight to `~*`), not
 * JavaScript RegExp — Postgres's engine uses `\y` for a word boundary,
 * not `\b` (that's a backspace escape there, not a boundary — using `\b`
 * silently matched nothing, every single-word pattern below came back
 * zero until this was caught by sanity-checking real counts against
 * plain ILIKE). */
const PATTERNS: Record<string, Record<string, string>> = {
  q1: { reorder: "reorder|usual (list|basket|order)|same (order|list|items)" },
  q2: {
    return_policy: "return polic",
    freshness: "\\yfreshness\\y|fresh (nahi|check)",
    trust: "\\ytrust\\y|\\yfake\\y|duplicate|counterfeit",
    price_comparison: "price comparison|compare price|expensive than (local|other)",
    insufficient_info: "not enough (info|detail)|insufficient (info|detail)|no description",
  },
  q3: {
    search: "\\ysearch(ed|ing)?\\y",
    home_feed: "home (feed|page|screen)",
    banner: "\\ybanner\\y",
    notification: "\\ynotification\\y",
    word_of_mouth: "\\yfriend\\y|recommend(ed)?|word of mouth",
    offline: "local store|offline|physical store",
  },
  q4: { habit: "\\yalways\\y|every week|\\yusual\\y|as usual|\\yroutine\\y|every time" },
  q5: {
    freshness: "\\yfreshness\\y",
    size: "\\ysize\\y|exact size",
    origin: "\\yorigin\\y",
    expiry: "\\yexpiry\\y",
    authenticity: "authentic",
    return_policy: "return polic",
  },
  q6: {
    refund: "\\yrefund\\y",
    damaged: "\\ydamaged\\y",
    delay: "\\ydelay(ed)?\\y|late deliver",
    cancelled: "cancel(led)?",
    payment_failed: "payment fail|amount (got )?deducted",
    support_unresponsive: "support (has )?not responded|support never",
  },
  q7: { explore: "\\ytry(ing)? (a |new )|\\yexplore\\y|\\yexperiment\\y|\\ybrowse\\y" },
  q8: { unmet_need: "\\ywish\\y|\\yshould have\\y|\\yneed(s)? an? option|missing (an? )?(option|feature)|please add" },
};

export interface Kpi {
  value: string; // human label, e.g. "37.2%" or "Return policy"
  n_matching: number;
  n_total: number;
  breakdown: { label: string; n: number }[];
}

function humanize(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export async function computeKpis(): Promise<Record<string, Kpi>> {
  // Build one query with a count(*) filter per pattern across every
  // question — one round trip instead of one query per question.
  const filters: string[] = [];
  const params: string[] = [];
  const order: { qid: string; key: string }[] = [];
  for (const [qid, patterns] of Object.entries(PATTERNS)) {
    for (const [key, pattern] of Object.entries(patterns)) {
      filters.push(`count(*) FILTER (WHERE raw_text ~* $${params.length + 1}) AS "${qid}__${key}"`);
      params.push(pattern);
      order.push({ qid, key });
    }
  }

  const query = `
    SELECT count(*) AS total, ${filters.join(", ")}
    FROM documents WHERE dupe_of_id IS NULL
  `;
  const [row] = await sql().unsafe(query, params);
  const total = Number(row.total);

  const results: Record<string, Kpi> = {};
  for (const qid of Object.keys(PATTERNS)) {
    const breakdown = order
      .filter((o) => o.qid === qid)
      .map((o) => ({ label: humanize(o.key), n: Number(row[`${qid}__${o.key}`]) }))
      .sort((a, b) => b.n - a.n);
    const top = breakdown[0];
    const isSinglePattern = breakdown.length === 1;
    results[qid] = {
      value: isSinglePattern
        ? total > 0
          ? `${((top.n / total) * 100).toFixed(1)}%`
          : "—"
        : top?.n > 0
          ? top.label
          : "Not clear yet",
      n_matching: top?.n ?? 0,
      n_total: total,
      breakdown,
    };
  }
  return results;
}

/** Persists KPIs independently of the LLM narrative — a row gets its number
 * every sync regardless of whether the Groq call below succeeds. If the row
 * doesn't exist yet, insert a placeholder narrative rather than leaving the
 * page with nothing until the first successful Groq call. */
export async function saveKpis(): Promise<Record<string, Kpi>> {
  await ensureSchema();
  const kpis = await computeKpis();
  for (const q of QUESTIONS) {
    const kpi = kpis[q.id];
    if (!kpi) continue;
    await sql()`
      INSERT INTO question_answers (question_id, question, answer, kpi, n_reviews, generated_at)
      VALUES (${q.id}, ${q.question}, ${`${kpi.value} (based on keyword analysis of ${kpi.n_total} reviews).`}, ${sql().json(kpi as any)}, ${kpi.n_total}, now())
      ON CONFLICT (question_id) DO UPDATE SET
        question = EXCLUDED.question, kpi = EXCLUDED.kpi
    `;
  }
  return kpis;
}
