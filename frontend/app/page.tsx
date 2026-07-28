"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchDiscoveryQuestions, fetchOverview, DiscoveryQuestionResult, OverviewData } from "@/lib/api";

function humanize(code: string | null | undefined): string {
  if (!code) return "Not clear yet";
  return code.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function pct(rate: number | null | undefined): string {
  return rate != null ? `${(rate * 100).toFixed(1)}%` : "—";
}

/** Each question pack shapes `chart_data` differently (ranked list, crosstab,
 * dict-of-rates) — this pulls the single headline number/label out of each
 * shape, so a KPI tile doesn't need bespoke rendering per pack. */
function headline(pack: DiscoveryQuestionResult | undefined): { value: string; sublabel: string } {
  if (!pack) return { value: "—", sublabel: "no data yet" };
  const cd = pack.chart_data as any;
  switch (pack.id) {
    case "q1_repeat_categories":
    case "q4_habit_role":
      return {
        value: pct(pack.rate),
        sublabel: pack.successes != null ? `n=${pack.successes}/${pack.n}` : `n=${pack.n}`,
      };
    case "q2_exploration_barriers": {
      const top = Array.isArray(cd) && cd.length ? cd[0] : null;
      return { value: humanize(top?.barrier_code), sublabel: top ? `${top.n_matching}/${pack.n} reviews` : `n=${pack.n}` };
    }
    case "q3_discovery_surfaces": {
      const top = Array.isArray(cd) && cd.length ? cd[0] : null;
      return { value: humanize(top?.surface), sublabel: top ? `${top.n_matching}/${pack.n} reviews` : `n=${pack.n}` };
    }
    case "q5_information_gap": {
      const top = Array.isArray(cd) && cd.length ? cd[0] : null;
      return { value: humanize(top?.dimension), sublabel: top ? `${top.n_matching}/${pack.n} reviews` : `n=${pack.n}` };
    }
    case "q6_frequent_frustrations": {
      const top = Array.isArray(cd) && cd.length ? cd[0] : null;
      return { value: humanize(top?.label), sublabel: top ? `${top.doc_count} reviews` : `n=${pack.n}` };
    }
    case "q7_segment_experimentation": {
      if (!cd || typeof cd !== "object") return { value: "—", sublabel: `n=${pack.n}` };
      const entries = Object.entries(cd) as [string, any][];
      entries.sort((a, b) => (b[1]?.rate ?? 0) - (a[1]?.rate ?? 0));
      const [seg, stats] = entries[0] ?? [null, null];
      return { value: humanize(seg), sublabel: stats ? `${pct(stats.rate)} explore, n=${stats.n}` : `n=${pack.n}` };
    }
    case "q8_unmet_needs":
      return { value: String(Array.isArray(cd) ? cd.length : 0), sublabel: `recurring across ≥2 sources, n=${pack.n}` };
    default:
      return { value: pack.answer_summary, sublabel: `n=${pack.n}` };
  }
}

/** A best-effort, generic renderer for the varied `chart_data` shapes across
 * the eight packs — a ranked top-5 list rather than a raw JSON dump, without
 * needing bespoke UI per pack. */
function ChartBreakdown({ data }: { data: unknown }) {
  if (Array.isArray(data)) {
    const rows = data.slice(0, 5).map((item, i) => {
      if (Array.isArray(item)) return { key: String(item[0]), value: item[1] };
      if (item && typeof item === "object") {
        const obj = item as Record<string, unknown>;
        const labelKey = Object.keys(obj).find((k) => typeof obj[k] === "string") ?? Object.keys(obj)[0];
        const valueKey =
          Object.keys(obj).find((k) => k.startsWith("n") && typeof obj[k] === "number") ??
          Object.keys(obj).find((k) => typeof obj[k] === "number");
        return { key: String(obj[labelKey] ?? i), value: valueKey ? obj[valueKey] : "" };
      }
      return { key: String(item), value: "" };
    });
    if (rows.length === 0) return <p className="text-xs text-slate-500">No breakdown available.</p>;
    return (
      <ul className="space-y-1">
        {rows.map((r, i) => (
          <li key={i} className="flex justify-between text-xs text-slate-600">
            <span>{humanize(r.key)}</span>
            <span className="font-medium text-slate-800">{String(r.value)}</span>
          </li>
        ))}
      </ul>
    );
  }
  if (data && typeof data === "object") {
    const entries = Object.entries(data as Record<string, any>).slice(0, 5);
    return (
      <ul className="space-y-1">
        {entries.map(([k, v]) => (
          <li key={k} className="flex justify-between text-xs text-slate-600">
            <span>{humanize(k)}</span>
            <span className="font-medium text-slate-800">
              {typeof v === "object" && v !== null ? (v.rate != null ? pct(v.rate) : JSON.stringify(v)) : String(v)}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return <p className="text-xs text-slate-500">No breakdown available.</p>;
}

function KpiCard({
  question,
  value,
  sublabel,
  pack,
}: {
  question: string;
  value: string;
  sublabel: string;
  pack?: DiscoveryQuestionResult;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-xs font-medium text-slate-500">{question}</div>
      <div className="mt-1 text-2xl font-semibold leading-tight text-slate-900">{value}</div>
      <div className="mt-1 text-xs text-slate-400">{sublabel}</div>
      {pack && (pack.top_quotes?.length || pack.chart_data != null) && (
        <details className="mt-2 group">
          <summary className="cursor-pointer text-xs font-medium text-blue-600 group-open:mb-2">Why?</summary>
          <p className="mb-2 text-xs text-slate-600">{pack.answer_summary}</p>
          {pack.top_quotes && pack.top_quotes.length > 0 && (
            <div className="mb-2 space-y-1.5">
              {pack.top_quotes.slice(0, 2).map((q, i) => (
                <blockquote key={i} className="border-l-2 border-slate-200 pl-2 text-xs italic text-slate-600">
                  &ldquo;{q.quote}&rdquo;
                  <span className="ml-1 not-italic text-slate-400">— {q.source_name}</span>
                </blockquote>
              ))}
            </div>
          )}
          {pack.chart_data != null && (
            <div className="rounded-md bg-slate-50 p-2">
              <ChartBreakdown data={pack.chart_data} />
            </div>
          )}
        </details>
      )}
    </div>
  );
}

export default function HomePage() {
  const [overview, setOverview] = useState<OverviewData | null>(null);
  const [questions, setQuestions] = useState<DiscoveryQuestionResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchOverview(), fetchDiscoveryQuestions()])
      .then(([ov, q]) => {
        setOverview(ov);
        setQuestions(q);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">
        Couldn&apos;t reach the AISLE API. {error}
      </div>
    );
  }
  if (!overview || !questions) {
    return <div className="p-8 text-center text-slate-500">Loading real customer feedback…</div>;
  }

  const byId = (id: string) => questions.find((q) => q.id === id);
  const fetched = overview.funnel[0]?.n ?? 0;
  const discoveryRelevantPct = overview.funnel[4]?.retention_pct ?? 0;
  const noData = fetched === 0;

  const kpis: { question: string; pack?: DiscoveryQuestionResult }[] = [
    { question: "Why do users repeatedly buy from the same categories?", pack: byId("q1_repeat_categories") },
    { question: "What prevents users from exploring new categories?", pack: byId("q2_exploration_barriers") },
    { question: "How do users discover products today?", pack: byId("q3_discovery_surfaces") },
    { question: "What role do habits play in shopping behaviour?", pack: byId("q4_habit_role") },
    { question: "What information do users need before trying a new category?", pack: byId("q5_information_gap") },
    { question: "What frustrations emerge repeatedly?", pack: byId("q6_frequent_frustrations") },
    { question: "Which segments are more likely to experiment?", pack: byId("q7_segment_experimentation") },
    { question: "What unmet needs emerge consistently?", pack: byId("q8_unmet_needs") },
  ];

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl font-bold text-slate-900">Why don&apos;t users explore beyond their usual basket?</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Real Play Store, App Store, Reddit, and community feedback, read and organized by AI. Click &quot;Why?&quot;
          on any card for the evidence behind it.
        </p>
      </header>

      {noData && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          No reviews have been fetched yet, so everything below is empty. Go to{" "}
          <Link href="/admin" className="font-medium underline">
            Admin
          </Link>{" "}
          and click &quot;Run full pipeline&quot; to pull in real reviews and analyze them.
        </div>
      )}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KpiCard question="Reviews analyzed" value={fetched.toLocaleString()} sublabel="Play Store, App Store, Reddit & more" />
        <KpiCard
          question="Feedback that's about trying something new"
          value={`${discoveryRelevantPct}%`}
          sublabel="rest is delivery/app/pricing feedback"
        />
        {kpis.map(({ question, pack }) => {
          const h = headline(pack);
          return <KpiCard key={question} question={question} value={h.value} sublabel={h.sublabel} pack={pack} />;
        })}
      </section>

      <section className="rounded-xl border border-slate-200 bg-slate-50 p-5">
        <h2 className="text-sm font-semibold text-slate-900">Want to go deeper?</h2>
        <div className="mt-2 flex flex-wrap gap-3 text-sm">
          <Link href="/themes" className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-700 hover:border-slate-400">
            Browse themes
          </Link>
          <Link href="/insights" className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-700 hover:border-slate-400">
            Browse graded insights
          </Link>
          <Link href="/ask" className="rounded-md border border-slate-300 bg-white px-3 py-1.5 font-medium text-slate-700 hover:border-slate-400">
            Ask your own question
          </Link>
        </div>
        <p className="mt-3 text-xs text-slate-400">
          Curious how this is built, or how much to trust the AI&apos;s classifications?{" "}
          <Link href="/pipeline" className="underline hover:text-slate-600">
            See the pipeline &amp; methodology
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
