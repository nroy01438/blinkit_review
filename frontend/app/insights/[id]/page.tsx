"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import { api, fetchInsight } from "@/lib/api";
import GradeBadge from "@/components/GradeBadge";
import PercentCI from "@/components/PercentCI";

export default function InsightDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [insight, setInsight] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingStatus, setSavingStatus] = useState(false);

  useEffect(() => {
    fetchInsight(id).then(setInsight).catch((e) => setError(String(e)));
  }, [id]);

  async function setStatus(status: string) {
    setSavingStatus(true);
    try {
      await api.post(`/insights/${id}/status`, { status });
      setInsight((prev: any) => ({ ...prev, status }));
    } finally {
      setSavingStatus(false);
    }
  }

  if (error) return <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">{error}</div>;
  if (!insight) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  const breakdown = insight.iqs_breakdown_json || {};
  const chartData = Object.entries(breakdown)
    .filter(([k]) => !k.startsWith("_"))
    .map(([k, v]) => ({ component: k.replace(/_/g, " "), score: v as number }));

  return (
    <div className="space-y-6">
      <header>
        <div className="flex flex-wrap items-center gap-2">
          <GradeBadge grade={insight.grade} />
          <h1 className="text-2xl font-bold text-slate-900">{insight.title}</h1>
        </div>
        {insight.grade === "D" && (
          <div className="mt-2 rounded bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
            ⚠ Insufficient evidence — do not act on this insight.
          </div>
        )}
        <div className="mt-3">
          <PercentCI successes={insight.doc_count ?? 0} total={insight.doc_total ?? 0} ciLow={insight.ci_low} ciHigh={insight.ci_high} />
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Field label="Statement" value={insight.statement} />
          <Field label="So what" value={insight.so_what} />
          <Field label="Opportunity" value={insight.opportunity} />
          <div className="grid grid-cols-2 gap-4">
            <TagList label="Affected segments" tags={insight.affected_segments} />
            <TagList label="Affected categories" tags={insight.affected_categories} />
          </div>

          <div className="rounded-lg border-2 border-amber-300 bg-amber-50 p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-amber-800">Counter-evidence (mandatory)</h2>
            <p className="mt-1 text-sm text-amber-900">{insight.counter_evidence}</p>
          </div>

          <div>
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Evidence ({insight.evidence?.length ?? 0} documents)
            </h2>
            <div className="space-y-2">
              {(insight.evidence || []).map((e: any) => (
                <div key={e.id} className="rounded-lg border border-slate-200 bg-white p-3">
                  <p className="text-sm text-slate-800">&ldquo;{e.quote}&rdquo;</p>
                  <div className="mt-1 flex gap-3 text-xs text-slate-500">
                    <span>doc #{e.document_id}</span>
                    <span>{e.source_name}</span>
                    <span>{e.brand}</span>
                    <span>{e.supports}</span>
                    {e.posted_at && <span>{new Date(e.posted_at).toLocaleDateString()}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              IQS breakdown — total {insight.iqs_total}
            </h2>
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={chartData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="component" tick={{ fontSize: 10 }} />
                <Radar dataKey="score" stroke="#0f172a" fill="#0f172a" fillOpacity={0.4} />
                <Tooltip />
              </RadarChart>
            </ResponsiveContainer>
            {breakdown._grade_capped_reason && (
              <p className="mt-2 rounded bg-amber-50 p-2 text-xs text-amber-800">
                Grade capped: {breakdown._grade_capped_reason}
              </p>
            )}
          </div>

          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Human review</h2>
            <p className="mb-2 text-sm text-slate-600">
              Current status: <strong>{insight.status}</strong>
            </p>
            <div className="flex gap-2">
              <button
                disabled={savingStatus}
                onClick={() => setStatus("human_approved")}
                className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                disabled={savingStatus}
                onClick={() => setStatus("human_rejected")}
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</h2>
      <p className="mt-1 text-sm text-slate-800">{value}</p>
    </div>
  );
}

function TagList({ label, tags }: { label: string; tags?: string[] }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</h2>
      <div className="mt-2 flex flex-wrap gap-1">
        {(tags || []).map((t) => (
          <span key={t} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
            {t}
          </span>
        ))}
        {(!tags || tags.length === 0) && <span className="text-xs text-slate-400">—</span>}
      </div>
    </div>
  );
}
