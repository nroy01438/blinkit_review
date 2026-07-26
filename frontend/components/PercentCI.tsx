/**
 * §15's anti-pattern #1: "A percentage without n, a denominator, and a CI.
 * Anywhere." This component is the enforcement mechanism — it always
 * renders n/denominator alongside the percentage and its Wilson CI, so a
 * naked percentage can't slip into the UI without deliberately bypassing
 * this component.
 */
export default function PercentCI({
  successes,
  total,
  ciLow,
  ciHigh,
  label,
}: {
  successes: number;
  total: number;
  ciLow: number;
  ciHigh: number;
  label?: string;
}) {
  const pct = total > 0 ? (successes / total) * 100 : 0;
  return (
    <span className="inline-flex flex-wrap items-baseline gap-1">
      <span className="text-lg font-semibold text-slate-900">{pct.toFixed(1)}%</span>
      <span className="text-xs text-slate-500">
        (n={successes}/{total}, 95% CI [{(ciLow * 100).toFixed(1)}%, {(ciHigh * 100).toFixed(1)}%])
      </span>
      {label && <span className="text-xs text-slate-400">{label}</span>}
    </span>
  );
}
