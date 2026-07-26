const STATUS_STYLES: Record<string, string> = {
  new: "bg-purple-100 text-purple-800",
  growing: "bg-green-100 text-green-800",
  stable: "bg-slate-100 text-slate-700",
  decaying: "bg-orange-100 text-orange-800",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status] || STATUS_STYLES.stable}`}>
      {status}
    </span>
  );
}
