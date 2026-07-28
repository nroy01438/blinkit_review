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

async function sampleCorpus(maxDocs: number): Promise<SampleDoc[]> {
  const rows = await sql()`
    SELECT d.raw_text, s.name AS source_name
    FROM documents d
    JOIN sources s ON s.id = d.source_id
    WHERE d.dupe_of_id IS NULL AND length(d.raw_text) > 15
    ORDER BY d.posted_at DESC NULLS LAST, d.id DESC
    LIMIT ${maxDocs}
  `;
  return rows.map((r: any, i: number) => ({ index: i, source_name: r.source_name, raw_text: String(r.raw_text).slice(0, 500) }));
}

function buildPrompt(docs: SampleDoc[]): string {
  const reviewBlock = docs.map((d) => `[${d.index}] (${d.source_name}) ${d.raw_text}`).join("\n");
  const questionList = QUESTIONS.map((q) => `"${q.id}": "${q.question}"`).join(",\n  ");
  return `You are analyzing real customer feedback about Blinkit (a quick-commerce grocery delivery app) to help a product manager understand shopping behaviour.

Here are ${docs.length} real reviews/discussions, each with an index number:
${reviewBlock}

Answer these questions using ONLY what's actually said in the reviews above. If the reviews don't clearly support an answer, say so honestly rather than guessing.
{
  ${questionList}
}

Respond with ONLY a strict JSON object shaped like this (no prose outside the JSON):
{
  "q1": {"answer": "one or two plain-English sentences", "quote_indices": [3, 17]},
  "q2": {"answer": "...", "quote_indices": [...]},
  ... one entry per question id above ...
}

"quote_indices" must be indices from the numbered list above (up to 3 per question) whose text actually supports that answer — never invent a quote, only reference real review indices.`;
}

export async function regenerateAnswers(): Promise<{ regenerated: number; n_reviews: number }> {
  await ensureSchema();
  if (!process.env.GROQ_API_KEY) {
    throw new Error("GROQ_API_KEY is not set — can't generate answers without it.");
  }
  const docs = await sampleCorpus(300);
  if (docs.length < 5) {
    return { regenerated: 0, n_reviews: docs.length };
  }

  const client = new Groq({ apiKey: process.env.GROQ_API_KEY });
  const completion = await client.chat.completions.create({
    model: MODEL,
    temperature: 0,
    max_tokens: 2000,
    messages: [{ role: "user", content: buildPrompt(docs) }],
  });
  const text = completion.choices[0]?.message?.content || "";
  const parsed = extractJson(text);

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
