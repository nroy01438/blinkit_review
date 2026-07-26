"use client";

import { useEffect, useState } from "react";
import { askAgent, AskResponse, fetchQuestionPacks, QuestionPack, runQuestionPack } from "@/lib/api";
import { ApiError } from "@/lib/api";

interface ChatTurn {
  question: string;
  response?: AskResponse;
  error?: string;
}

export default function AskPage() {
  const [packs, setPacks] = useState<QuestionPack[] | null>(null);
  const [packResult, setPackResult] = useState<{ pack: QuestionPack; data: any } | null>(null);
  const [packBusy, setPackBusy] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [thread, setThread] = useState<ChatTurn[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchQuestionPacks().then(setPacks).catch(() => setPacks([]));
  }, []);

  async function runPack(pack: QuestionPack) {
    setPackBusy(pack.id);
    setPackResult(null);
    try {
      const data = await runQuestionPack(pack.id);
      setPackResult({ pack, data });
    } finally {
      setPackBusy(null);
    }
  }

  async function ask(q: string) {
    setQuestion("");
    setBusy(true);
    setThread((t) => [...t, { question: q }]);
    try {
      const res = await askAgent(q);
      setThread((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, response: res } : turn)));
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 404 ? "The /ask endpoint isn't available." : String(e);
      setThread((t) => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: msg } : turn)));
    } finally {
      setBusy(false);
    }
  }

  function exportThread() {
    const lines = ["# AISLE research note", ""];
    for (const turn of thread) {
      lines.push(`## Q: ${turn.question}`, "");
      if (turn.response) {
        lines.push(turn.response.answer, "");
        if (turn.response.citations?.length) {
          lines.push("**Cited reviews:**");
          for (const c of turn.response.citations) lines.push(`- [doc #${c.document_id}] "${c.quote}"`);
          lines.push("");
        }
      } else if (turn.error) {
        lines.push(`_Error: ${turn.error}_`, "");
      }
    }
    const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `aisle-research-note-${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[340px,1fr]">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-slate-900">Ask</h1>
        <p className="mb-3 text-sm text-slate-600">
          Eight preset question packs (each its own analysis, not a chat prompt), or ask anything on the right.
        </p>
        {packs === null && <p className="text-sm text-slate-500">Loading…</p>}
        {packs?.map((p) => (
          <button
            key={p.id}
            onClick={() => runPack(p)}
            disabled={packBusy === p.id}
            className="block w-full rounded-lg border border-slate-200 bg-white p-3 text-left text-sm hover:border-slate-400 disabled:opacity-50"
          >
            {packBusy === p.id ? "Running…" : p.question}
          </button>
        ))}

        {packResult && (
          <div className="mt-4 rounded-lg border-2 border-slate-900 bg-white p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-900">{packResult.pack.question}</h2>
              <span className="text-xs text-slate-400">{new Date(packResult.data.generated_at).toLocaleTimeString()}</span>
            </div>
            <p className="mt-2 text-sm text-slate-800">{packResult.data.answer_summary}</p>
            {typeof packResult.data.n === "number" && <p className="mt-1 text-xs text-slate-500">n={packResult.data.n}</p>}
            {Array.isArray(packResult.data.top_quotes) && packResult.data.top_quotes.length > 0 && (
              <div className="mt-2 space-y-1 border-t border-slate-100 pt-2">
                {packResult.data.top_quotes.slice(0, 3).map((q: any, i: number) => (
                  <p key={i} className="text-xs text-slate-600">
                    [doc #{q.document_id}] &ldquo;{q.quote}&rdquo;
                  </p>
                ))}
              </div>
            )}
            <details className="mt-2">
              <summary className="cursor-pointer text-xs font-medium text-blue-600">Expand full evidence &amp; chart data</summary>
              <pre className="mt-2 max-h-64 overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-100">
                {JSON.stringify(packResult.data, null, 2)}
              </pre>
            </details>
          </div>
        )}
      </div>

      <div className="space-y-4">
        <div className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && question && !busy && ask(question)}
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
          {thread.length > 0 && (
            <button onClick={exportThread} className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700">
              Export thread
            </button>
          )}
        </div>

        <div className="space-y-3">
          {thread.map((turn, i) => (
            <div key={i} className="space-y-2">
              <div className="rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-900">{turn.question}</div>
              {turn.error && <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800">{turn.error}</div>}
              {turn.response && (
                <div className={`rounded-lg border p-4 ${turn.response.refused ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>
                  <p className="whitespace-pre-wrap text-sm text-slate-800">{turn.response.answer}</p>
                  {turn.response.citations?.length > 0 && (
                    <div className="mt-3 space-y-1 border-t border-slate-200 pt-3">
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Cited reviews</h3>
                      {turn.response.citations.map((c, ci) => (
                        <p key={ci} className="text-xs text-slate-600">
                          [doc #{c.document_id}] &ldquo;{c.quote}&rdquo;
                        </p>
                      ))}
                    </div>
                  )}
                  {turn.response.tool_outputs && Object.keys(turn.response.tool_outputs).length > 0 && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs font-medium text-blue-600">Computed tool outputs</summary>
                      <pre className="mt-1 max-h-48 overflow-auto rounded bg-slate-950 p-2 text-xs text-slate-100">
                        {JSON.stringify(turn.response.tool_outputs, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              )}
              {!turn.response && !turn.error && <p className="text-sm text-slate-500">Thinking…</p>}
            </div>
          ))}
          {thread.length === 0 && (
            <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
              Try: &ldquo;Is exploration different for new users vs. established users?&rdquo; or something the agent
              genuinely has no evidence for, to see the refusal behaviour.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
