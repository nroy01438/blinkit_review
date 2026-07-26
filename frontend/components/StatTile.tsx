export default function StatTile({
  label,
  value,
  sublabel,
  warn,
}: {
  label: string;
  value: string;
  sublabel?: string;
  warn?: boolean;
}) {
  return (
    <div className={`rounded-lg border p-4 ${warn ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"}`}>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
      {sublabel && <div className="mt-1 text-xs text-slate-500">{sublabel}</div>}
    </div>
  );
}
