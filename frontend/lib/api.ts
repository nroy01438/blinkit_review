const BASE_URL = process.env.NEXT_PUBLIC_AISLE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, text || `Request to ${path} failed`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

export interface FunnelStage {
  stage: string;
  n: number;
  retention_pct: number;
}

export interface PmGateHealth {
  kappa: number | null;
  stage1_junk_recall: number | null;
  stage3_relevance_f1: number | null;
  abstention_rate: number;
  cost_per_1k_docs_usd: number;
  acceptance_gate_passed: boolean;
}

export interface ThemeSummary {
  id: number;
  label: string;
  description?: string;
  taxonomy_node: string | null;
  doc_count: number;
  doc_total: number;
  prevalence: number;
  ci_low: number;
  ci_high: number;
  status: "new" | "growing" | "stable" | "decaying";
  delta_vs_prev_run: number | null;
  source_spread_json?: Record<string, unknown>;
  noise_pct?: number;
  stability_ari?: number | null;
  first_seen_run?: number;
}

export interface OverviewData {
  funnel: FunnelStage[];
  source_mix: { name: string; brand: string; n: number }[];
  lang_mix: { lang: string; n: number }[];
  sentiment_mix: { sentiment: string; n: number }[];
  top_themes: ThemeSummary[];
  top_insights: InsightSummary[];
  pmgate_health: PmGateHealth;
}

export interface InsightSummary {
  id: number;
  title: string;
  statement?: string;
  so_what?: string;
  opportunity?: string;
  affected_segments?: string[];
  affected_categories?: string[];
  counter_evidence?: string;
  prevalence: number;
  ci_low: number;
  ci_high: number;
  doc_count?: number;
  doc_total?: number;
  iqs_total: number;
  iqs_breakdown_json?: Record<string, number>;
  grade: "A" | "B" | "C" | "D";
  status: string;
  theme_ids?: number[];
  run_id?: number;
}

export interface InsightEvidenceRow {
  id: number;
  document_id: number;
  quote: string;
  supports: string;
  posted_at: string | null;
  source_name: string;
  brand: string;
}

export interface RunSummary {
  id: number;
  started_at: string;
  finished_at: string | null;
  trigger: string;
  status: string;
  cost_usd: number;
  stage_stats_json: Record<string, unknown>;
}

export function fetchOverview() {
  return api.get<OverviewData>("/overview");
}

export function fetchThemes(runId?: number) {
  return api.get<ThemeSummary[]>(`/themes${runId ? `?run_id=${runId}` : ""}`);
}

export function fetchTheme(id: number) {
  return api.get<ThemeSummary & { members: unknown[]; sparkline: unknown[] }>(`/themes/${id}`);
}

export function fetchInsights(params: { grade?: string; status?: string } = {}) {
  const qs = new URLSearchParams();
  if (params.grade) qs.set("grade", params.grade);
  if (params.status) qs.set("status", params.status);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return api.get<InsightSummary[]>(`/insights${suffix}`);
}

export function fetchInsight(id: number) {
  return api.get<InsightSummary & { evidence: InsightEvidenceRow[] }>(`/insights/${id}`);
}

export function fetchRuns(limit = 20) {
  return api.get<RunSummary[]>(`/runs?limit=${limit}`);
}

export function fetchRun(id: number) {
  return api.get<RunSummary>(`/runs/${id}`);
}

export function fetchQualityMetrics() {
  return api.get<Record<string, unknown>>("/quality/metrics");
}

export function fetchNegativeControl() {
  return api.get<Record<string, unknown>>("/quality/negative-control");
}

export function fetchSources() {
  return api.get<
    { id: number; name: string; kind: string; brand: string; is_active: boolean; last_fetched_at: string | null }[]
  >("/admin/sources");
}
