"use client";

import { useEffect, useState } from "react";

interface QuoteRow {
  quote: string;
  source_name: string;
}

interface QuestionAnswer {
  question_id: string;
  question: string;
  answer: string;
  quotes: QuoteRow[];
  n_reviews: number;
  generated_at: string;
}

interface QuestionsResponse {
  questions: QuestionAnswer[];
  total_reviews: number;
  source_mix: { name: string; brand: string; n: number }[];
  sources: { name: string; kind: string; is_active: boolean; last_fetched_at: string | null }[];
}

function QuestionCard({ qa }: { qa: QuestionAnswer }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-xs font-medium text-slate-500">{qa.question}</div>
      <p className="mt-1 text-sm font-medium text-slate-900">{qa.answer}</p>
      <div className="mt-1 text-xs text-slate-400">based on {qa.n_reviews} reviews</div>
      {qa.quotes && qa.quotes.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs font-medium text-blue-600">See the evidence</summary>
          <div className="mt-2 space-y-1.5">
            {qa.quotes.map((q, i) => (
              <blockquote key={i} className="border-l-2 border-slate-200 pl-2 text-xs italic text-slate-600">
                &ldquo;{q.quote}&rdquo;
                <span className="ml-1 not-italic text-slate-400">— {q.source_name}</span>
              </blockquote>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

export default function HomePage() {
  const [data, setData] = useState<QuestionsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState<any>(null);

  async function load() {
    try {
      const res = await fetch("/api/questions", { cache: "no-store" });
      if (!res.ok) throw new Error(await res.text());
      setData(await res.json());
      setError(null);
    } catch (e: any) {
      setError(String(e.message || e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runSync() {
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await fetch("/api/sync?limit=50", { method: "POST" });
      const json = await res.json();
      setSyncResult(json);
      await load();
    } catch (e: any) {
      setSyncResult({ errors: { _fetch: String(e.message || e) } });
    } finally {
      setSyncing(false);
    }
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">
        Couldn&apos;t reach the database. {error}
      </div>
    );
  }
  if (!data) {
    return <div className="p-8 text-center text-slate-500">Loading…</div>;
  }

  const byId = (id: string) => data.questions.find((q) => q.question_id === id);
  const hasAnyAnswers = data.questions.length > 0;

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Why don&apos;t users explore beyond their usual basket?</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-600">
            Real Play Store, App Store, and Reddit feedback, read by AI. Press sync to pull in the newest reviews
            and refresh the answers below.
          </p>
        </div>
        <div className="text-right">
          <button
            onClick={runSync}
            disabled={syncing}
            className="rounded-md bg-slate-900 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50"
          >
            {syncing ? "Syncing…" : "Sync reviews now"}
          </button>
          <p className="mt-1 text-xs text-slate-400">pulls the newest ~50 per source, takes under a minute</p>
        </div>
      </header>

      {syncResult && (
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
          {Object.entries(syncResult.per_source || {}).map(([name, counts]: [string, any]) => (
            <div key={name}>
              <strong>{name}</strong>: fetched {counts.fetched}, added {counts.inserted} new
            </div>
          ))}
          {syncResult.answers && (
            <div className="mt-1">
              Refreshed {syncResult.answers.regenerated} answers from {syncResult.answers.n_reviews} reviews.
            </div>
          )}
          {syncResult.errors && Object.keys(syncResult.errors).length > 0 && (
            <div className="mt-1 text-amber-700">
              {Object.entries(syncResult.errors).map(([name, err]: [string, any]) => (
                <div key={name}>
                  ⚠ {name}: {String(err)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!hasAnyAnswers && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          No answers yet — press &quot;Sync reviews now&quot; above to pull in real reviews and let the AI analyze
          them.
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs font-medium text-slate-500">Reviews analyzed</div>
          <div className="mt-1 text-2xl font-semibold text-slate-900">{data.total_reviews.toLocaleString()}</div>
          <div className="mt-1 text-xs text-slate-400">
            {data.source_mix.map((s) => `${s.name} (${s.n})`).join(" · ") || "no reviews yet"}
          </div>
        </div>
        {data.questions.map((qa) => (
          <QuestionCard key={qa.question_id} qa={qa} />
        ))}
      </section>

      <section className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <h2 className="text-sm font-semibold text-slate-900">Sources</h2>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-600">
          {data.sources.map((s) => (
            <span key={s.name} className="rounded-full border border-slate-200 bg-white px-2.5 py-1">
              {s.name} · {s.is_active ? "active" : "off"}
              {s.last_fetched_at ? ` · synced ${new Date(s.last_fetched_at).toLocaleString()}` : " · never synced"}
            </span>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-400">
          Social media conversations aren&apos;t auto-synced (no logged-in scraping) — use{" "}
          <a href="/upload" className="underline">
            Upload
          </a>{" "}
          for those.
        </p>
      </section>
    </div>
  );
}
