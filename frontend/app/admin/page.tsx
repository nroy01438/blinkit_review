"use client";

import { useEffect, useState } from "react";
import { api, fetchSources } from "@/lib/api";

export default function AdminPage() {
  const [sources, setSources] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<any>(null);

  const [annotatorId, setAnnotatorId] = useState("me");
  const [labelDoc, setLabelDoc] = useState<any>(null);
  const [labelBusy, setLabelBusy] = useState(false);

  useEffect(() => {
    fetchSources().then(setSources).catch((e) => setError(String(e)));
  }, []);

  async function run(name: string, path: string) {
    setRunning(name);
    setLastResult(null);
    try {
      const result = await api.post(path);
      setLastResult({ name, result });
    } catch (e) {
      setLastResult({ name, error: String(e) });
    } finally {
      setRunning(null);
    }
  }

  async function runFullPipeline() {
    setRunning("full-pipeline");
    const steps: [string, string][] = [
      ["ingest (live)", "/admin/run/ingest?dry_run=false&limit_per_source=200"],
      ["classify", "/admin/run/classify"],
      ["cluster", "/admin/run/cluster"],
      ["insights", "/admin/run/insights"],
    ];
    const results: Record<string, any> = {};
    try {
      for (const [name, path] of steps) {
        setLastResult({ name: "full-pipeline", result: { ...results, currently_running: name } });
        results[name] = await api.post(path);
      }
      setLastResult({ name: "full-pipeline", result: results });
    } catch (e) {
      setLastResult({ name: "full-pipeline", result: results, error: String(e) });
    } finally {
      setRunning(null);
    }
  }

  async function loadNextLabel() {
    setLabelBusy(true);
    try {
      const doc = await api.get<any>(`/admin/label/next?annotator_id=${encodeURIComponent(annotatorId)}`);
      setLabelDoc(doc);
    } finally {
      setLabelBusy(false);
    }
  }

  async function submitLabel(isJunk: boolean, relevance: number | null) {
    if (!labelDoc) return;
    setLabelBusy(true);
    try {
      await api.post("/admin/label", {
        document_id: labelDoc.id,
        is_junk: isJunk,
        discovery_relevance: relevance,
        annotator_id: annotatorId,
        round: 1,
      });
      await loadNextLabel();
    } finally {
      setLabelBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Admin</h1>
        <p className="mt-1 text-sm text-slate-600">Sources, on-demand pipeline runs, cost, and the human labelling tool.</p>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Run pipeline stages</h2>
        <div className="flex flex-wrap gap-2">
          <RunButton
            label="Ingest (live — fetch real reviews)"
            busy={running === "ingest-live"}
            onClick={() => run("ingest-live", "/admin/run/ingest?dry_run=false&limit_per_source=200")}
          />
          <RunButton label="Ingest (dry-run preview)" busy={running === "ingest"} onClick={() => run("ingest", "/admin/run/ingest?dry_run=true")} />
          <RunButton label="Classify" busy={running === "classify"} onClick={() => run("classify", "/admin/run/classify")} />
          <RunButton label="Cluster" busy={running === "cluster"} onClick={() => run("cluster", "/admin/run/cluster")} />
          <RunButton label="Generate insights" busy={running === "insights"} onClick={() => run("insights", "/admin/run/insights")} />
          <RunButton
            label="Run full pipeline (ingest → classify → cluster → insights)"
            busy={running === "full-pipeline"}
            onClick={runFullPipeline}
          />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          A brand-new deployment starts with an empty database — every dashboard screen shows zeros until you
          run at least &quot;Ingest (live)&quot; once. &quot;Run full pipeline&quot; does ingest → classify →
          cluster → insights in one click.
        </p>
        {lastResult && (
          <pre className="mt-3 max-h-80 overflow-auto rounded bg-slate-950 p-3 text-xs text-slate-100">
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Sources</h2>
        {error && <p className="text-sm text-red-700">{error}</p>}
        {!sources ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : (
          <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Kind</th>
                  <th className="px-3 py-2">Brand</th>
                  <th className="px-3 py-2">Active</th>
                  <th className="px-3 py-2">Last fetched</th>
                </tr>
              </thead>
              <tbody>
                {sources.map((s) => (
                  <tr key={s.id} className="border-t border-slate-100">
                    <td className="px-3 py-2 font-medium text-slate-900">{s.name}</td>
                    <td className="px-3 py-2">{s.kind}</td>
                    <td className="px-3 py-2">{s.brand}</td>
                    <td className="px-3 py-2">{s.is_active ? "yes" : "no"}</td>
                    <td className="px-3 py-2">{s.last_fetched_at ? new Date(s.last_fetched_at).toLocaleString() : "never"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Human labelling (§6 golden set)</h2>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2">
            <label className="text-sm text-slate-600">Annotator ID</label>
            <input
              value={annotatorId}
              onChange={(e) => setAnnotatorId(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <button onClick={loadNextLabel} disabled={labelBusy} className="rounded bg-slate-900 px-3 py-1 text-sm text-white">
              Load next unlabelled document
            </button>
          </div>
          {labelDoc ? (
            <div>
              <p className="rounded bg-slate-50 p-3 text-sm text-slate-800">{labelDoc.raw_text}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button disabled={labelBusy} onClick={() => submitLabel(true, 0)} className="rounded bg-red-600 px-3 py-1 text-sm text-white">
                  Junk
                </button>
                {[0, 1, 2, 3, 4].map((rel) => (
                  <button
                    key={rel}
                    disabled={labelBusy}
                    onClick={() => submitLabel(false, rel)}
                    className="rounded bg-blue-600 px-3 py-1 text-sm text-white"
                  >
                    Not junk, relevance={rel}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">No document loaded yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}

function RunButton({ label, busy, onClick }: { label: string; busy: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
    >
      {busy ? "Running…" : label}
    </button>
  );
}
