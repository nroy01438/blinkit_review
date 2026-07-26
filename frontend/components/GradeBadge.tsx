const GRADE_STYLES: Record<string, string> = {
  A: "bg-green-100 text-green-800 border-green-300",
  B: "bg-blue-100 text-blue-800 border-blue-300",
  C: "bg-amber-100 text-amber-800 border-amber-300",
  D: "bg-red-100 text-red-800 border-red-300",
};

export default function GradeBadge({ grade }: { grade: string }) {
  const style = GRADE_STYLES[grade] || GRADE_STYLES.D;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-bold ${style}`}>
      Grade {grade}
      {grade === "D" && <span title="Insufficient evidence — do not act on this">⚠</span>}
    </span>
  );
}
