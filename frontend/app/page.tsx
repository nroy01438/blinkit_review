"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchDiscoveryQuestions, fetchOverview, DiscoveryQuestionResult, OverviewData } from "@/lib/api";
import StatTile from "@/components/StatTile";
import PercentCI from "@/components/PercentCI";

function humanize(code: string | null | undefined): string {
  if (!code) return "Not clear from the data yet";
  return code
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Each question pack shapes `chart_data` differently (ranked list, crosstab,
 * dict-of-rates) — this pulls out just "what's #1" for the KPI strip, so the
 * strip doesn't need to know every pack's internal shape. */
function topLabel(pack: DiscoveryQuestionResult | undefined): string | null {
  if (!pack) return null;
  const cd = pack.chart_data as any;
  switch (pack.id) {
    case "q2_exploration_barriers":
      return Array.isArray(cd) && cd.length ? cd[0].barrier_code : null;
    case "q3_discovery_surfaces":
      return Array.isArray(cd) && cd.length ? cd[0].surface : null;
    case "q6_frequent_frustrations":
      return Array.isArray(cd) && cd.length ? cd[0].label : null;
    case "q7_segment_experimentation": {
      if (!cd || typeof cd !== "object") return null;
      const entries = Object.entries(cd) as [string, any][];
      entries.sort((a, b) => (b[1]?.rate ?? 0) - (a[1]?.rate ?? 0));
      return entries.length ? entries[0][0] : null;
    }
    default:
      return null;
  }
}

/** A best-effort, generic renderer for the varied `chart_data` shapes across
 * the eight packs — a ranked top-5 list rather than a raw JSON dump, without
 * needing bespoke UI per pack. */
function ChartBreakdown({ data }: { data: unknown }) {
  if (Array.isArray(data)) {
    const rows = data.slice(0, 5).map((item, i) => {
      if (Array.isArray(item)) {
        return { key: String(item[0]), value: item[1] };
      }
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
              {typeof v === "object" && v !== null ? (v.rate != null ? `${(v.rate * 100).toFixed(1)}%` : JSON.stringify(v)) : String(v)}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return <p className="text-xs text-slate-500">No breakdown available.</p>;
}

function QuestionCard({ pack }: { pack: DiscoveryQuestionResult }) {
  const hasRate = pack.rate != null && pack.ci_low != null && pack.ci_high != null && pack.successes != null;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h3 className="text-base font-semibold text-slate-900">{pack.question}</h3>
      <p className="mt-2 text-sm text-slate-700">{pack.answer_summary}</p>
      {hasRate ? (
        <div className="mt-3">
          <PercentCI successes={pack.successes!} total={pack.n} ciLow={pack.ci_low!} ciHigh={pack.ci_high!} />
        </div>
      ) : (
        <p className="mt-2 text-xs text-slate-400">based on {pack.n} reviews</p>
      )}

      {pack.top_quotes && pack.top_quotes.length > 0 && (
        <div className="mt-4 space-y-2 border-t border-slate-100 pt-3">
          {pack.top_quotes.slice(0, 2).map((q, i) => (
            <blockquote key={i} className="border-l-2 border-slate-200 pl-3 text-xs italic text-slate-600">
              &ldquo;{q.quote}&rdquo;
              <span className="ml-1 not-italic text-slate-400">— {q.source_name}</span>
            </blockquote>
          ))}
        </div>
      )}

      {pack.chart_data != null && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-blue-600">See the full breakdown</summary>
          <div className="mt-2 rounded-md bg-slate-50 p-3">
            <ChartBreakdown data={pack.chart_data} />
          </div>
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

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-3xl font-bold text-slate-900">Why don&apos;t users explore beyond their usual basket?</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-600">
          Real Play Store, App Store, Reddit, and community feedback, read and organized by AI, answering the eight
          questions that matter for growing category exploration on Blinkit.
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
        <StatTile label="Reviews analyzed" value={fetched.toLocaleString()} sublabel="across Play Store, App Store, Reddit & more" />
        <StatTile
          label="Feedback that's about trying something new"
          value={`${discoveryRelevantPct}%`}
          sublabel="the rest is delivery/app/pricing feedback"
        />
        <StatTile label="Top barrier to exploring" value={humanize(topLabel(byId("q2_exploration_barriers")))} />
        <StatTile label="How users discover products today" value={humanize(topLabel(byId("q3_discovery_surfaces")))} />
        <StatTile label="Segment most likely to experiment" value={humanize(topLabel(byId("q7_segment_experimentation")))} />
        <StatTile label="Top recurring frustration" value={humanize(topLabel(byId("q6_frequent_frustrations")))} />
      </section>

      <section>
        <h2 className="mb-4 text-lg font-semibold text-slate-900">The eight questions, answered</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          {questions.map((pack) => (
            <QuestionCard key={pack.id} pack={pack} />
          ))}
        </div>
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
