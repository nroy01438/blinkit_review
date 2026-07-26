"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";

const QUESTION_PACKS = [
  { id: "q1_repeat_categories", question: "Why do users repeatedly buy from the same categories?" },
  { id: "q2_exploration_barriers", question: "What prevents users from exploring new categories?" },
  { id: "q3_discovery_surfaces", question: "How do users discover products today?" },
  { id: "q4_habit_role", question: "What role do habits play in shopping behaviour?" },
  { id: "q5_information_gap", question: "What information do users need before trying a new category?" },
  { id: "q6_frequent_frustrations", question: "What frustrations emerge repeatedly?" },
  { id: "q7_segment_experimentation", question: "Which segments are more likely to experiment?" },
  { id: "q8_unmet_needs", question: "What unmet needs emerge consistently across discussions?" },
];

interface AskResponse {
  answer: string;
  citations: { document_id: number; quote: string }[];
  refused: boolean;
}

export default function AskPage() {
  const [question, setQuestion] = useState("");
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [notAvailable, setNotAvailable] = useState(false);

  async function ask(q: string) {
    setQuestion(q);
    setBusy(true);
    setResponse(null);
    setNotAvailable(false);
    try {
      const res = await api.post<AskResponse>("/ask", { question: q });
      setResponse(res);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setNotAvailable(true);
      } else {
        setResponse({ answer: `Error: ${String(e)}`, citations: [], refused: true });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[320px,1fr]">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900">Ask</h1>
        <p className="mb-3 text-sm text-slate-600">Eight preset question packs, or ask anything.</p>
        {QUESTION_PACKS.map((p) => (
          <button
            key={p.id}
            onClick={() => ask(p.question)}
            className="block w-full rounded-lg border border-slate-200 bg-white p-3 text-left text-sm hover:border-slate-400"
          >
            {p.question}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        <div className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && question && ask(question)}
            placeholder="Ask anything about the corpus…"
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            disabled={!question || busy}
            onClick={() => ask(question)}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Ask
          </button>
        </div>

        {notAvailable && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
            The QnA agent backend (Phase 7) isn&apos;t wired up yet — this screen is the shell built in Phase 6,
            ready for the retrieval + agent endpoint to land at <code>POST /ask</code>.
          </div>
        )}

        {busy && <p className="text-sm text-slate-500">Thinking…</p>}

        {response && (
          <div className={`rounded-lg border p-4 ${response.refused ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>
            <p className="text-sm text-slate-800 whitespace-pre-wrap">{response.answer}</p>
            {response.citations?.length > 0 && (
              <div className="mt-3 space-y-1 border-t border-slate-200 pt-3">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cited reviews</h3>
                {response.citations.map((c, i) => (
                  <p key={i} className="text-xs text-slate-600">
                    [doc #{c.document_id}] &ldquo;{c.quote}&rdquo;
                  </p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
