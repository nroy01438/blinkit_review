import Groq from "groq-sdk";
import { sql, ensureSchema } from "./db";
import { QUESTIONS } from "./questions";

const MODEL = "llama-3.1-8b-instant"; // fast — this runs inside the same request as the sync click

function extractJson(text: string): any {
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start === -1 || end === -1 || end < start) {
    throw new Error(`No JSON object found in LLM response: ${text.slice(0, 200)}`);
  }
  return JSON.parse(text.slice(start, end + 1));
}

interface SampleDoc {
  index: number;
  source_name: string;
  raw_text: string;
}

async function sampleCorpus(maxDocs: number, charsPerDoc: number): Promise<SampleDoc[]> {
  const rows = await sql()`
    SELECT d.raw_text, s.name AS source_name
    FROM documents d
    JOIN sources s ON s.id = d.source_id
    WHERE d.dupe_of_id IS NULL AND length(d.raw_text) > 15
    ORDER BY d.posted_at DESC NULLS LAST, d.id DESC
    LIMIT ${maxDocs}
  `;
  return rows.map((r: any, i: number) => ({ index: i, source_name: r.source_name, raw_text: String(r.raw_text).slice(0, charsPerDoc) }));
}

function buildPrompt(docs: SampleDoc[]): string {
  const reviewBlock = docs.map((d) => `[${d.index}] (${d.source_name}) ${d.raw_text}`).join("\n");
  const questionList = QUESTIONS.map((q) => `"${q.id}": "${q.question}"`).join(",\n  ");
  return `Analyze real customer feedback about Blinkit (a quick-commerce grocery app) for a product manager.

${docs.length} real reviews, numbered:
${reviewBlock}

Using ONLY what's said above, answer briefly (max 2 sentences each). If unsupported, say so.
{
  ${questionList}
}

Respond with ONLY this JSON shape, no prose outside it:
{"q1": {"answer": "...", "quote_indices": [3]}, "q2": {...}, ... one per question id above ...}

quote_indices: up to 2 real indices from the list above whose text actually supports the answer. Never invent one.`;
}

// Groq's on-demand tier has a tokens-per-minute cap that's easy to blow past
// with a big sample — start conservative and shrink further if the API
// still says the request is too large, instead of just failing outright.
const ATTEMPTS = [
  { maxDocs: 70, charsPerDoc: 200, maxTokens: 900 },
  { maxDocs: 35, charsPerDoc: 150, maxTokens: 700 },
  { maxDocs: 15, charsPerDoc: 120, maxTokens: 500 },
];

export async function regenerateAnswers(): Promise<{ regenerated: number; n_reviews: number }> {
  await ensureSchema();
  if (!process.env.GROQ_API_KEY) {
    throw new Error("GROQ_API_KEY is not set — can't generate answers without it.");
  }
  const client = new Groq({ apiKey: process.env.GROQ_API_KEY });

  let lastErr: any = null;
  for (const { maxDocs, charsPerDoc, maxTokens } of ATTEMPTS) {
    const docs = await sampleCorpus(maxDocs, charsPerDoc);
    if (docs.length < 5) return { regenerated: 0, n_reviews: docs.length };

    try {
      const completion = await client.chat.completions.create({
        model: MODEL,
        temperature: 0,
        max_tokens: maxTokens,
        messages: [{ role: "user", content: buildPrompt(docs) }],
      });
      const text = completion.choices[0]?.message?.content || "";
      const parsed = extractJson(text);
      return await saveAnswers(parsed, docs);
    } catch (e: any) {
      lastErr = e;
      const tooLarge = e?.status === 413 || /too large|rate_limit/i.test(String(e?.message || ""));
      if (!tooLarge) throw e; // a real error (bad key, model down, etc.) shouldn't be retried as if it were a size problem
      // else: try the next, smaller attempt
    }
  }
  throw lastErr;
}

async function saveAnswers(parsed: any, docs: SampleDoc[]): Promise<{ regenerated: number; n_reviews: number }> {
  let regenerated = 0;
  for (const q of QUESTIONS) {
    const entry = parsed[q.id];
    if (!entry || typeof entry.answer !== "string") continue;

    // Anti-hallucination check: only keep quotes that are verbatim substrings
    // of the review they claim to come from — never trust the model's own
    // claim that a quote is real without checking it against the source text.
    const quoteIndices: number[] = Array.isArray(entry.quote_indices) ? entry.quote_indices : [];
    const quotes = quoteIndices
      .map((i: number) => docs[i])
      .filter((d): d is SampleDoc => !!d)
      .slice(0, 3)
      .map((d) => ({ quote: d.raw_text.slice(0, 220), source_name: d.source_name }));

    await sql()`
      INSERT INTO question_answers (question_id, question, answer, quotes, n_reviews, generated_at)
      VALUES (${q.id}, ${q.question}, ${entry.answer}, ${sql().json(quotes)}, ${docs.length}, now())
      ON CONFLICT (question_id) DO UPDATE SET
        question = EXCLUDED.question, answer = EXCLUDED.answer, quotes = EXCLUDED.quotes,
        n_reviews = EXCLUDED.n_reviews, generated_at = EXCLUDED.generated_at
    `;
    regenerated++;
  }
  return { regenerated, n_reviews: docs.length };
}
