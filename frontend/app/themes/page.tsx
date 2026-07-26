"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchThemes, ThemeSummary } from "@/lib/api";
import PercentCI from "@/components/PercentCI";
import StatusBadge from "@/components/StatusBadge";

export default function ThemesPage() {
  const [themes, setThemes] = useState<ThemeSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchThemes().then(setThemes).catch((e) => setError(String(e)));
  }, []);

  if (error) return <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-800">{error}</div>;
  if (!themes) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Themes</h1>
        <p className="mt-1 text-sm text-slate-600">
          Most recent clustering run. Prevalence is Wilson 95% CI, never a naked percentage.
        </p>
      </header>

      {themes.length === 0 && (
        <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          No themes yet — run clustering from /admin.
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {themes.map((t) => (
          <Link key={t.id} href={`/themes/${t.id}`} className="rounded-lg border border-slate-200 bg-white p-4 hover:border-slate-400">
            <div className="flex items-center justify-between gap-2">
              <h2 className="font-semibold text-slate-900">{t.label}</h2>
              <StatusBadge status={t.status} />
            </div>
            <p className="mt-1 text-sm text-slate-600 line-clamp-2">{t.description}</p>
            <div className="mt-3">
              <PercentCI successes={t.doc_count} total={t.doc_total} ciLow={t.ci_low} ciHigh={t.ci_high} />
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
              {t.taxonomy_node && <span>taxonomy: {t.taxonomy_node}</span>}
              {t.delta_vs_prev_run != null && (
                <span>Δ vs. prior run: {t.delta_vs_prev_run > 0 ? "+" : ""}{(t.delta_vs_prev_run * 100).toFixed(1)}pp</span>
              )}
              {t.stability_ari != null && <span>stability ARI: {t.stability_ari.toFixed(2)}</span>}
              {t.noise_pct != null && <span>noise: {(t.noise_pct * 100).toFixed(1)}%</span>}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
