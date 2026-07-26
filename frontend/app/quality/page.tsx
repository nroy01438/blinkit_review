"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fetchNegativeControl, fetchQualityMetrics, fetchThemes } from "@/lib/api";
import StatTile from "@/components/StatTile";

export default function QualityPage() {
  const [metrics, setMetrics] = useState<any>(null);
  const [negControl, setNegControl] = useState<any>(null);
  const [stabilityAri, setStabilityAri] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchQualityMetrics(), fetchNegativeControl(), fetchThemes()])
      .then(([m, nc, themes]) => {
        setMetrics(m);
        setNegControl(nc);
        setStabilityAri(themes[0]?.stability_ari ?? null);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">{error}</div>;
  if (!metrics) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  const gate = metrics.acceptance_gate;
  const calibration = (metrics.calibration || []).map((b: any) => ({
    bin: `${(b.bin_low * 100).toFixed(0)}–${(b.bin_high * 100).toFixed(0)}%`,
    predicted: b.avg_predicted_confidence,
    actual: b.actual_accuracy,
    n: b.n,
  }));

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Quality — the classifier&apos;s report card</h1>
        {metrics.annotator_id_note && (
          <p className="mt-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">{metrics.annotator_id_note}</p>
        )}
      </header>

      <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <GateTile title="Stage-1 junk recall" check={gate.checks.stage1_junk_recall} />
        <GateTile title="Stage-3 relevance F1" check={gate.checks.stage3_relevance_f1} />
        <GateTile title="Cohen's κ" check={gate.checks.kappa} />
        <StatTile
          label="Overall acceptance gate"
          value={gate.all_passed ? "PASS" : "FAIL"}
          warn={!gate.all_passed}
        />
      </section>

      <section className="grid gap-6 md:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Stage-1 junk P/R/F1</h2>
          <Metric label="Precision" value={metrics.stage1_junk.precision} n={metrics.stage1_junk.n} />
          <Metric label="Recall" value={metrics.stage1_junk.recall} n={metrics.stage1_junk.n} />
          <Metric label="F1" value={metrics.stage1_junk.f1} n={metrics.stage1_junk.n} />
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Stage-3 relevance P/R/F1</h2>
          <Metric label="Precision" value={metrics.stage3_relevance.precision} n={metrics.stage3_relevance.n} />
          <Metric label="Recall" value={metrics.stage3_relevance.recall} n={metrics.stage3_relevance.n} />
          <Metric label="F1" value={metrics.stage3_relevance.f1} n={metrics.stage3_relevance.n} />
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <StatTile
          label="Abstention rate"
          value={`${(metrics.abstention.rate * 100).toFixed(1)}%`}
          sublabel={`n=${metrics.abstention.n}, target 5–12%`}
          warn={metrics.abstention.rate < 0.05 || metrics.abstention.rate > 0.15}
        />
        <StatTile
          label="Cluster stability (mean ARI)"
          value={stabilityAri != null ? stabilityAri.toFixed(3) : "—"}
          sublabel="across 3 UMAP seeds"
        />
        <StatTile label="Classifier κ vs. human" value={metrics.classifier_vs_human_kappa.kappa?.toFixed(3) ?? "—"} sublabel={`n=${metrics.classifier_vs_human_kappa.n}`} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Calibration — predicted confidence vs. actual accuracy
        </h2>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={calibration}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="bin" tick={{ fontSize: 12 }} />
              <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} />
              <Tooltip />
              <Line type="monotone" dataKey="predicted" stroke="#2563eb" name="avg predicted confidence" />
              <Line type="monotone" dataKey="actual" stroke="#15803d" name="actual accuracy" />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-2 text-xs text-slate-500">A well-calibrated classifier has the two lines close together.</p>
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
          §9 negative-control experiment
        </h2>
        <div
          className={`rounded-lg border-2 p-4 ${
            negControl.verdict === "PASS" ? "border-green-300 bg-green-50" : "border-red-400 bg-red-50"
          }`}
        >
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-3 py-1 text-sm font-bold ${
                negControl.verdict === "PASS" ? "bg-green-600 text-white" : "bg-red-600 text-white"
              }`}
            >
              {negControl.verdict}
            </span>
            <span className="text-sm text-slate-700">
              {negControl.total_negative_control_docs} fabricated reviews injected into the corpus
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-800">{negControl.explanation}</p>
          {negControl.majority_fabricated_insights?.length > 0 && (
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-slate-500">
                  <th className="pb-1">Insight</th>
                  <th className="pb-1">Grade</th>
                  <th className="pb-1">IQS</th>
                  <th className="pb-1">% fabricated</th>
                </tr>
              </thead>
              <tbody>
                {negControl.majority_fabricated_insights.map((i: any) => (
                  <tr key={i.insight_id} className="border-t border-slate-200">
                    <td className="py-1">{i.title}</td>
                    <td className="py-1">{i.grade}</td>
                    <td className="py-1">{i.iqs_total}</td>
                    <td className="py-1">{(i.negative_control_fraction * 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}

function GateTile({ title, check }: { title: string; check: { value: number | null; threshold: number; passed: boolean } }) {
  return (
    <StatTile
      label={title}
      value={check.value != null ? check.value.toFixed(3) : "—"}
      sublabel={`threshold ≥${check.threshold}`}
      warn={!check.passed}
    />
  );
}

function Metric({ label, value, n }: { label: string; value: number | null; n: number }) {
  return (
    <div className="flex justify-between border-b border-slate-100 py-1 text-sm last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-900">{value != null ? value.toFixed(3) : "—"} (n={n})</span>
    </div>
  );
}
