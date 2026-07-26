"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchInsights, InsightSummary } from "@/lib/api";
import GradeBadge from "@/components/GradeBadge";
import PercentCI from "@/components/PercentCI";

const GRADES = ["A", "B", "C", "D"] as const;

export default function InsightsPage() {
  const [insights, setInsights] = useState<InsightSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gradeFilter, setGradeFilter] = useState<string | null>(null);

  useEffect(() => {
    setInsights(null);
    fetchInsights(gradeFilter ? { grade: gradeFilter } : {})
      .then(setInsights)
      .catch((e) => setError(String(e)));
  }, [gradeFilter]);

  if (error) return <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">{error}</div>;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Insights</h1>
        <p className="mt-1 text-sm text-slate-600">
          Sorted by IQS. D-grade insights are shown, not hidden — they carry a warning instead.
        </p>
      </header>

      <div className="flex gap-2">
        <FilterChip label="All" active={gradeFilter === null} onClick={() => setGradeFilter(null)} />
        {GRADES.map((g) => (
          <FilterChip key={g} label={g} active={gradeFilter === g} onClick={() => setGradeFilter(g)} />
        ))}
      </div>

      {!insights ? (
        <div className="p-8 text-center text-slate-500">Loading…</div>
      ) : insights.length === 0 ? (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          No insights yet — run insight generation from /admin.
        </p>
      ) : (
        <div className="space-y-3">
          {insights.map((i) => (
            <Link
              key={i.id}
              href={`/insights/${i.id}`}
              className={`block rounded-lg border bg-white p-4 hover:border-slate-400 ${
                i.grade === "D" ? "border-red-300" : "border-slate-200"
              }`}
            >
              {i.grade === "D" && (
                <div className="mb-2 rounded bg-red-50 px-2 py-1 text-xs font-medium text-red-700">
                  ⚠ Insufficient evidence — do not act on this
                </div>
              )}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <GradeBadge grade={i.grade} />
                  <h2 className="font-semibold text-slate-900">{i.title}</h2>
                </div>
                <span className="text-sm text-slate-500">IQS {i.iqs_total}</span>
              </div>
              <p className="mt-2 text-sm text-slate-600 line-clamp-2">{i.statement}</p>
              <div className="mt-2">
                <PercentCI successes={i.doc_count ?? 0} total={i.doc_total ?? 0} ciLow={i.ci_low} ciHigh={i.ci_high} />
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-sm font-medium transition ${
        active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
      }`}
    >
      {label}
    </button>
  );
}
