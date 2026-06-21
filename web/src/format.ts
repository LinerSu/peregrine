// Shared display formatting for jobs/applications tables.

export function salaryRange(
  min: number | null,
  max: number | null,
  currency = "USD"
): string {
  if (min == null && max == null) return "—";
  const fmt = (n: number) =>
    new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(n);
  if (min != null && max != null) return `${fmt(min)}–${fmt(max)}`;
  return fmt((min ?? max) as number);
}

const STATUS_STYLES: Record<string, string> = {
  open: "bg-green-100 text-green-700",
  applied: "bg-blue-100 text-blue-700",
  interviewing: "bg-amber-100 text-amber-700",
  offer: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
  closed: "bg-gray-100 text-gray-600",
  removed: "bg-gray-100 text-gray-600",
};

export function statusClass(status: string): string {
  return STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600";
}

// Color a fit score: green ≥0.70, amber 0.40–0.69, red <0.40, gray when unscored.
export function fitClass(score: number | null | undefined): string {
  if (score == null) return "bg-gray-100 text-gray-500";
  if (score >= 0.7) return "bg-green-100 text-green-700";
  if (score >= 0.4) return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}
