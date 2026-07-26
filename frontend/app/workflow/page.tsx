"use client";

import { useEffect, useState } from "react";
import { fetchRuns, RunSummary } from "@/lib/api";

const STAGE_LABELS = ["Collect", "Curate", "Classify", "Aggregate", "Insights", "Synthesize", "Store", "Explore"];

export default function WorkflowPage() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<RunSummary | null>(null);

  useEffect(() => {
    fetchRuns(30)
      .then((r) => {
        setRuns(r);
        if (r.length) setSelected(r[0]);
      })
      .catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">{error}</div>;
  if (!runs) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Workflow &amp; Provenance</h1>
        <p className="mt-1 text-sm text-slate-600">
          Reads live from <code className="rounded bg-slate-100 px-1">runs.stage_stats_json</code> — not a static
          diagram. Click a run to see exactly what it did.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[280px,1fr]">
        <div className="space-y-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Run timeline</h2>
          {runs.map((r) => (
            <button
              key={r.id}
              onClick={() => setSelected(r)}
              className={`block w-full rounded-lg border p-3 text-left text-sm transition ${
                selected?.id === r.id ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white hover:border-slate-400"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">Run #{r.id}</span>
                <StatusPill status={r.status} inverted={selected?.id === r.id} />
              </div>
              <div className={`mt-1 text-xs ${selected?.id === r.id ? "text-slate-300" : "text-slate-500"}`}>
                {r.trigger} · {new Date(r.started_at).toLocaleString()} · ${Number(r.cost_usd).toFixed(4)}
              </div>
            </button>
          ))}
          {runs.length === 0 && <p className="text-sm text-slate-500">No runs yet.</p>}
        </div>

        <div className="space-y-4">
          {selected ? (
            <>
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Run #{selected.id} — {selected.trigger}
                </h2>
                <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                  <Stat label="Status" value={selected.status} />
                  <Stat label="Started" value={new Date(selected.started_at).toLocaleString()} />
                  <Stat label="Finished" value={selected.finished_at ? new Date(selected.finished_at).toLocaleString() : "—"} />
                  <Stat label="Cost" value={`$${Number(selected.cost_usd).toFixed(4)}`} />
                </dl>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">stage_stats_json</h2>
                <pre className="max-h-[500px] overflow-auto rounded-md bg-slate-950 p-4 text-xs text-slate-100">
                  {JSON.stringify(selected.stage_stats_json, null, 2)}
                </pre>
              </div>

              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
                The 8-stage pipeline this run is part of: {STAGE_LABELS.join(" → ")}. Not every run touches every
                stage — an ingestion run&apos;s stats look different from a classify/cluster/insight run&apos;s.
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-500">Select a run.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-900">{value}</dd>
    </div>
  );
}

function StatusPill({ status, inverted }: { status: string; inverted: boolean }) {
  const colors: Record<string, string> = {
    completed: inverted ? "bg-green-400 text-slate-900" : "bg-green-100 text-green-800",
    running: inverted ? "bg-blue-400 text-slate-900" : "bg-blue-100 text-blue-800",
    partial: inverted ? "bg-amber-400 text-slate-900" : "bg-amber-100 text-amber-800",
    failed: inverted ? "bg-red-400 text-slate-900" : "bg-red-100 text-red-800",
  };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors[status] || colors.running}`}>{status}</span>;
}
