"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { fetchTheme } from "@/lib/api";
import PercentCI from "@/components/PercentCI";
import StatusBadge from "@/components/StatusBadge";

interface Member {
  document_id: number;
  raw_text: string;
  posted_at: string | null;
  source_name: string;
  brand: string;
  is_exemplar: boolean;
  segment_label: string | null;
  sentiment: string | null;
}

export default function ThemeDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const [theme, setTheme] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    fetchTheme(id).then(setTheme).catch((e) => setError(String(e)));
  }, [id]);

  if (error) return <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">{error}</div>;
  if (!theme) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  const members: Member[] = theme.members || [];
  const exemplars = members.filter((m) => m.is_exemplar);
  const rest = members.filter((m) => !m.is_exemplar);
  const shown = showAll ? rest : rest.slice(0, 10);
  const spread = theme.source_spread_json || {};

  return (
    <div className="space-y-6">
      <header>
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold text-slate-900">{theme.label}</h1>
          <StatusBadge status={theme.status} />
        </div>
        <p className="mt-2 text-sm text-slate-600">{theme.description}</p>
        <div className="mt-3">
          <PercentCI successes={theme.doc_count} total={theme.doc_total} ciLow={theme.ci_low} ciHigh={theme.ci_high} />
        </div>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SpreadCard title="Sources" data={spread.sources} />
        <SpreadCard title="Brands" data={spread.brands} />
        <SpreadCard title="Segments" data={spread.segments} />
        <SpreadCard title="Categories" data={spread.categories} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">Exemplar documents (medoids)</h2>
        <div className="space-y-2">
          {exemplars.map((m) => (
            <DocCard key={m.document_id} m={m} />
          ))}
        </div>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
            Other members ({rest.length})
          </h2>
          {rest.length > 10 && (
            <button onClick={() => setShowAll(!showAll)} className="text-xs font-medium text-blue-600 hover:underline">
              {showAll ? "Show fewer" : `Show all ${rest.length}`}
            </button>
          )}
        </div>
        <div className="space-y-2">
          {shown.map((m) => (
            <DocCard key={m.document_id} m={m} />
          ))}
        </div>
      </section>
    </div>
  );
}

function SpreadCard({ title, data }: { title: string; data?: Record<string, number> }) {
  const entries = Object.entries(data || {}).sort((a, b) => b[1] - a[1]);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {entries.length === 0 && <li className="text-slate-400">—</li>}
        {entries.map(([k, v]) => (
          <li key={k} className="flex justify-between">
            <span className="truncate text-slate-700">{k}</span>
            <span className="font-medium text-slate-900">{v}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DocCard({ m }: { m: Member }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <p className="text-sm text-slate-800">{m.raw_text}</p>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
        <span>{m.source_name}</span>
        <span>{m.brand}</span>
        {m.segment_label && <span>{m.segment_label}</span>}
        {m.sentiment && <span>{m.sentiment}</span>}
        {m.posted_at && <span>{new Date(m.posted_at).toLocaleDateString()}</span>}
        {m.is_exemplar && <span className="font-medium text-blue-600">exemplar</span>}
      </div>
    </div>
  );
}
