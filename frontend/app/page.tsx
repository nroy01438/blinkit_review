"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchOverview, OverviewData } from "@/lib/api";
import StatTile from "@/components/StatTile";
import PercentCI from "@/components/PercentCI";
import StatusBadge from "@/components/StatusBadge";
import GradeBadge from "@/components/GradeBadge";

const PIE_COLORS = ["#0f172a", "#2563eb", "#15803d", "#b45309", "#7c3aed", "#be185d", "#0891b2", "#65a30d"];

export default function OverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchOverview().then(setData).catch((e) => setError(String(e)));
  }, []);

  if (error) return <ErrorPanel error={error} />;
  if (!data) return <Loading />;

  const health = data.pmgate_health;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Overview</h1>
        <p className="mt-1 text-sm text-slate-600">
          Why don&apos;t Blinkit users explore beyond their usual basket? Every number below ships with n, a
          denominator, and a 95% CI.
        </p>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Corpus funnel</h2>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.funnel} margin={{ left: 0, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="stage" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v: number, _n, p: any) => [`${v} docs (${p.payload.retention_pct}% of fetched)`, "count"]} />
              <Bar dataKey="n" fill="#0f172a" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-600">
            {data.funnel.map((f) => (
              <span key={f.stage}>
                <strong>{f.stage}</strong>: {f.n} ({f.retention_pct}% retained)
              </span>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <StatTile
          label="Classifier κ (vs. proxy)"
          value={health.kappa != null ? health.kappa.toFixed(3) : "—"}
          sublabel="Acceptance gate ≥0.65 — see /quality"
          warn={health.kappa != null && health.kappa < 0.65}
        />
        <StatTile
          label="Stage-3 relevance F1"
          value={health.stage3_relevance_f1 != null ? health.stage3_relevance_f1.toFixed(3) : "—"}
          sublabel="Acceptance gate ≥0.80"
          warn={health.stage3_relevance_f1 != null && health.stage3_relevance_f1 < 0.8}
        />
        <StatTile
          label="Abstention rate"
          value={`${(health.abstention_rate * 100).toFixed(1)}%`}
          sublabel="Target band 5–12%"
          warn={health.abstention_rate < 0.05 || health.abstention_rate > 0.15}
        />
        <StatTile label="Cost per 1k docs" value={`$${health.cost_per_1k_docs_usd.toFixed(2)}`} />
        <StatTile
          label="Acceptance gate"
          value={health.acceptance_gate_passed ? "PASS" : "FAIL"}
          warn={!health.acceptance_gate_passed}
          sublabel="vs. synthetic-proxy labels — see /quality"
        />
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Source mix</h2>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={data.source_mix} dataKey="n" nameKey="name" outerRadius={80} label={(e) => e.name}>
                {data.source_mix.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Language mix</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.lang_mix} layout="vertical" margin={{ left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 12 }} />
              <YAxis dataKey="lang" type="category" tick={{ fontSize: 12 }} width={60} />
              <Tooltip />
              <Bar dataKey="n" fill="#2563eb" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Top themes by prevalence</h2>
        <div className="space-y-2">
          {data.top_themes.map((t) => (
            <Link
              key={t.id}
              href={`/themes/${t.id}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white p-3 hover:border-slate-400"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-900">{t.label}</span>
                <StatusBadge status={t.status} />
              </div>
              <PercentCI successes={t.doc_count} total={t.doc_total} ciLow={t.ci_low} ciHigh={t.ci_high} />
            </Link>
          ))}
          {data.top_themes.length === 0 && <EmptyState text="No themes yet — run the clustering pipeline from /admin." />}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Top A-grade insights</h2>
        <div className="space-y-2">
          {data.top_insights.map((i) => (
            <Link
              key={i.id}
              href={`/insights/${i.id}`}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white p-3 hover:border-slate-400"
            >
              <div className="flex items-center gap-2">
                <GradeBadge grade={i.grade} />
                <span className="font-medium text-slate-900">{i.title}</span>
              </div>
              <PercentCI
                successes={i.doc_count ?? 0}
                total={i.doc_total ?? 0}
                ciLow={i.ci_low}
                ciHigh={i.ci_high}
                label={`IQS ${i.iqs_total}`}
              />
            </Link>
          ))}
          {data.top_insights.length === 0 && <EmptyState text="No A-grade insights yet — run insight generation from /admin." />}
        </div>
      </section>
    </div>
  );
}

function Loading() {
  return <div className="p-8 text-center text-slate-500">Loading…</div>;
}

function EmptyState({ text }: { text: string }) {
  return <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">{text}</div>;
}

function ErrorPanel({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">
      Couldn&apos;t reach the AISLE API ({process.env.NEXT_PUBLIC_AISLE_API_URL || "http://localhost:8000"}). {error}
    </div>
  );
}
